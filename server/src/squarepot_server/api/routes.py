# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes of API version 1."""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import date
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from squarepot_server import __version__
from squarepot_server.api.models import (
    AUTO_TEMPLATE,
    Collection,
    EditConflict,
    Error,
    FieldSchema,
    Health,
    LabelFormat,
    LabelRequest,
    LabelTemplate,
    NewPlant,
    Plant,
    PlantEdit,
    Sync,
    SyncKind,
    TagLookup,
)
from squarepot_server.backoff import client_key
from squarepot_server.db import CollectionRow, PlantRow, current_seq, get_meta
from squarepot_server.edits import Conflict, Editor, InvalidEdit, NotEditable, NotFound
from squarepot_server.fields import STATUS, STATUS_DATE
from squarepot_server.labels.caption import NAME, caption, entries, extra_text
from squarepot_server.labels.layout import TEMPLATES, Item, LayoutError, Page, layout_pages
from squarepot_server.labels.render import to_pdf, to_svg
from squarepot_server.labels.text import Run
from squarepot_server.photos.summary import PhotoSummary, summaries
from squarepot_server.runtime import Runtime
from squarepot_server.store import EditableStore, StoreError

log = logging.getLogger(__name__)
bearer = HTTPBearer(
    auto_error=False,
    description="The API token set by the operator at installation.",
)


CURSOR_SEQ = re.compile(r"[0-9]{1,18}")
LABEL_TYPES = {LabelFormat.PDF: "application/pdf", LabelFormat.SVG: "image/svg+xml"}
LABELS_TITLE = "Square-Pot labels"
SHEET_URL = "https://docs.google.com/spreadsheets/d/{}/edit"


def get_runtime(request: Request) -> Runtime:
    return cast(Runtime, request.app.state.runtime)


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    runtime = get_runtime(request)
    # The client's own address: behind a trusted proxy, the one it forwarded.
    client = client_key(request.client.host) if request.client else ""
    if (wait := runtime.backoff.retry_after(client)) is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests with a wrong API token; try again later.",
            headers={"Retry-After": str(wait)},
        )
    expected = runtime.settings.api_token.get_secret_value().encode()
    given = credentials.credentials.encode() if credentials else b""
    if not secrets.compare_digest(given, expected):
        if runtime.backoff.fail(client):
            log.warning("client %s: too many wrong API tokens, backing off", client)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "A valid API token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_session(runtime: Annotated[Runtime, Depends(get_runtime)]) -> Iterator[Session]:
    with runtime.sessions.begin() as session:
        yield session


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
SessionDep = Annotated[Session, Depends(get_session)]


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": Error} for code in codes}


def sheet_url(runtime: Runtime, collection_id: str) -> str | None:
    """The collection's sheet in Google Sheets; only for clients holding the token."""
    config = next((c for c in runtime.settings.collections if c.id == collection_id), None)
    if config is None or config.spreadsheet_id is None:
        return None
    url = SHEET_URL.format(config.spreadsheet_id)
    return url if config.gid is None else f"{url}#gid={config.gid}"


def to_collection(row: CollectionRow, runtime: Runtime) -> Collection:
    return Collection(
        id=row.id,
        name=row.name,
        plant_count=row.plant_count,
        former_count=row.former_count,
        synced_at=row.synced_at,
        error=row.error,
        custom_columns=row.custom_columns,
        editable=editable(runtime, row.id),
        sheet_url=sheet_url(runtime, row.id),
    )


def editable(runtime: Runtime, collection_id: str) -> bool:
    """Whether the collection is read with the service account, which may edit its sheet."""
    store = runtime.syncer.store
    config = next((c for c in runtime.settings.collections if c.id == collection_id), None)
    return config is not None and isinstance(store, EditableStore) and store.can_edit(config)


def to_plant(row: PlantRow, photos: Mapping[str, PhotoSummary]) -> Plant:
    summary = photos.get(row.tag) if row.tag is not None else None
    return Plant(
        id=row.id,
        collection_id=row.collection_id,
        tag=row.tag,
        row=row.row,
        fields=row.fields,
        custom=row.custom,
        invalid=row.invalid,
        status_since=status_since(row),
        photo_count=summary.count if summary else 0,
        last_photo=summary.last if summary else None,
        main_photo_id=UUID(summary.main_id) if summary else None,
    )


def to_plants(session: Session, rows: Sequence[PlantRow]) -> list[Plant]:
    photos = summaries(session, (row.tag for row in rows if row.tag is not None))
    return [to_plant(row, photos) for row in rows]


def plant_out(runtime: Runtime, row: PlantRow) -> Plant:
    with runtime.sessions.begin() as session:
        return to_plants(session, [row])[0]


def status_since(row: PlantRow) -> date | None:
    """The sheet's status date wins over the day the server first saw the status."""
    if STATUS not in row.fields:
        return None
    if STATUS_DATE in row.fields:
        return date.fromisoformat(row.fields[STATUS_DATE])
    return row.status_since


def make_cursor(session: Session, seq: int) -> str:
    return f"{get_meta(session, 'epoch')}.{get_meta(session, 'schema_version')}.{seq}"


def read_cursor(session: Session, cursor: str | None) -> int | None:
    """The position a cursor stands for, or None when it cannot be served."""
    if cursor is None:
        return None
    epoch, _, rest = cursor.partition(".")
    schema_version, _, seq = rest.partition(".")
    if (
        epoch != get_meta(session, "epoch")
        or schema_version != get_meta(session, "schema_version")
        or not CURSOR_SEQ.fullmatch(seq)
        or int(seq) > current_seq(session)
    ):
        return None
    return int(seq)


public = APIRouter(prefix="/api/v1")
router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_token)],
    responses=errors(status.HTTP_401_UNAUTHORIZED, status.HTTP_429_TOO_MANY_REQUESTS),
)


@public.get("/health", tags=["service"], summary="Check that the server is up")
def health() -> Health:
    return Health(status="ok", version=__version__)


@router.get(
    "/schema",
    tags=["schema"],
    summary="Get the field schema",
    description=(
        "Field definitions, computed fields and presets, which clients need to render names "
        "and captions. Fetch it again when `Sync.schema_version` changes."
    ),
)
def get_schema(runtime: RuntimeDep) -> FieldSchema:
    return runtime.schema


@router.get(
    "/collections",
    tags=["collections"],
    summary="List collections and how fresh their copies are",
)
def list_collections(session: SessionDep, runtime: RuntimeDep) -> list[Collection]:
    rows = session.scalars(
        select(CollectionRow).where(~CollectionRow.removed).order_by(CollectionRow.id)
    )
    return [to_collection(row, runtime) for row in rows]


@router.get(
    "/plants/by-tag/{tag}",
    tags=["plants"],
    summary="Find the plant with a tag number",
    description=(
        "Leading zeros may be left out: `4217` finds `004217`. Responds `404` when no plant "
        "has the number, and `422` when it is not a valid tag."
    ),
    responses=errors(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT),
)
def get_plants_by_tag(
    tag: Annotated[str, Path(pattern=r"^[0-9]{1,6}$", examples=["004217", "4217"])],
    session: SessionDep,
) -> TagLookup:
    if int(tag) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "000000 is reserved.")
    tag = tag.zfill(6)
    rows = session.scalars(
        select(PlantRow).where(PlantRow.tag == tag, ~PlantRow.removed).order_by(PlantRow.id)
    ).all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No plant has the number {tag}.")
    return TagLookup(tag=tag, plants=to_plants(session, rows))


EDIT_RESPONSES: dict[int | str, dict[str, Any]] = {
    **errors(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    status.HTTP_409_CONFLICT: {
        "model": EditConflict,
        "description": "Nothing was written: the sheet changed, or the collection is read-only.",
    },
}
EDIT_RULES = (
    " Values are checked first: `422` names every value that would not read back as "
    "itself, and every column the sheet lacks; Square-Pot never adds columns. `503` when "
    "Google cannot be reached. Only collections with `editable` can be edited (ADR 0006)."
)


def edited(runtime: Runtime, action: Callable[[], PlantRow]) -> Plant | JSONResponse:
    """The plant an edit left, or the error response an edit failed with."""
    try:
        return plant_out(runtime, action())
    except NotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except InvalidEdit as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except StoreError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"The sheet cannot be reached: {error}."
        ) from error
    except NotEditable as error:
        body = EditConflict(code="not_editable", message=str(error), plant=None)
    except Conflict as error:
        plant = plant_out(runtime, error.plant) if error.plant is not None else None
        body = EditConflict(code="changed_in_sheet", message=str(error), plant=plant)
    return JSONResponse(body.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)


@router.post(
    "/collections/{collection_id}/plants",
    tags=["plants"],
    summary="Add a plant as a new row of the sheet",
    description=(
        "Appends a row after the last row of the collection's tab, with the next free number "
        "unless `issue_number` is false, then reads the tab again and returns the plant as "
        "the sheet has it." + EDIT_RULES
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=Plant,
    responses=EDIT_RESPONSES,
)
def create_plant(
    collection_id: Annotated[str, Path(examples=["main"])],
    body: NewPlant,
    runtime: RuntimeDep,
) -> Plant | JSONResponse:
    return edited(runtime, lambda: Editor(runtime.syncer).create(collection_id, body))


@router.patch(
    "/plants/{plant_id}",
    tags=["plants"],
    summary="Change cells of a plant's row in the sheet",
    description=(
        "Reads the plant's row from the sheet first. If any cell to change no longer holds "
        "the value the client `seen`, nothing is written, and `409` carries the plant as it "
        "now is. Otherwise only the changed cells are written, and the plant is returned as "
        "the sheet then has it. A plant without a number gets a new `id` when its cells "
        "change." + EDIT_RULES
    ),
    response_model=Plant,
    responses=EDIT_RESPONSES,
)
def edit_plant(
    plant_id: Annotated[str, Path(examples=["main:004217"])],
    body: PlantEdit,
    runtime: RuntimeDep,
) -> Plant | JSONResponse:
    return edited(runtime, lambda: Editor(runtime.syncer).edit(plant_id, body))


@router.get(
    "/sync",
    tags=["sync"],
    summary="Get changes to the local copy since a cursor",
    description=(
        "Without `cursor`, returns a full copy of every collection. With the `cursor` of the "
        "previous response, returns only what changed since then, or a full copy when the "
        "cursor can no longer be served. See `kind`. A plant is sent again when its photos "
        "change. Responses are gzip-compressed when the client accepts it."
    ),
    responses=errors(status.HTTP_422_UNPROCESSABLE_CONTENT),
)
def sync(
    cursor: Annotated[
        str | None,
        Query(
            description=(
                "`cursor` from the previous sync response; omit for a full copy. Any value is "
                "accepted: one the server cannot use gives a full copy, never an error."
            )
        ),
    ] = None,
    *,
    session: SessionDep,
    runtime: RuntimeDep,
) -> Sync:
    # The new cursor is taken first: anything changed while reading is sent again next time.
    seq = current_seq(session)
    since = read_cursor(session, cursor)
    collections = select(CollectionRow).order_by(CollectionRow.id)
    plants = select(PlantRow).order_by(PlantRow.id)
    if since is None:
        collections = collections.where(~CollectionRow.removed)
        plants = plants.where(~PlantRow.removed)
    else:
        collections = collections.where(CollectionRow.seq > since)
        plants = plants.where(PlantRow.seq > since)
    collection_rows = session.scalars(collections).all()
    plant_rows = session.scalars(plants).all()
    return Sync(
        kind=SyncKind.FULL if since is None else SyncKind.DELTA,
        cursor=make_cursor(session, seq),
        schema_version=runtime.schema.version,
        collections=[to_collection(row, runtime) for row in collection_rows if not row.removed],
        removed_collections=[row.id for row in collection_rows if row.removed],
        plants=to_plants(session, [row for row in plant_rows if not row.removed]),
        removed_plants=[row.id for row in plant_rows if row.removed],
    )


@router.get(
    "/labels/templates",
    tags=["labels"],
    summary="List label templates",
    description="Built-in label sizes and sheet layouts, to start a `/labels` request from.",
)
def list_label_templates() -> list[LabelTemplate]:
    return list(TEMPLATES.values())


def chosen_template(template: str, fields: dict[str, str]) -> str:
    """The template a plant is printed with: its `label_type` decides with `auto`."""
    if template != AUTO_TEMPLATE:
        return template
    return "horizontal" if fields.get("label_type") == "h" else "vertical"


def cut_captions(plants: list[str], pages: list[Page]) -> list[str]:
    """The requested plants whose text was cut short, each once, in request order."""
    cut = {plant_id for page in pages for plant_id in page.cut}
    return [plant_id for plant_id in dict.fromkeys(plants) if plant_id in cut]


def listed(values: list[str]) -> str:
    shown = ", ".join(values[:10])
    return shown + (f" and {len(values) - 10} more" if len(values) > 10 else "")


@router.post(
    "/labels",
    tags=["labels"],
    summary="Print labels for plants",
    description=(
        "Lays out a label for each plant on pages, as PDF (every page) or SVG (one page). "
        "Each label holds the plant's code, whole and with its quiet zone, and a caption from "
        "the preset. A layout too small for the code is refused with `422`, never cropped; "
        "a caption too long for the label is shrunk, then cut short with an ellipsis, and "
        "the plant is named in `X-Cut-Captions`."
    ),
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "description": "The label sheet.",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in LABEL_TYPES.values()
            },
            "headers": {
                "X-Page-Count": {
                    "description": "Number of pages in the layout.",
                    "schema": {"type": "integer"},
                },
                "X-Cut-Captions": {
                    "description": (
                        "Ids of the plants whose caption or burial text was cut short, "
                        "comma-separated, in request order, on every page of the layout "
                        "(also when the response is one SVG page). Empty when nothing was cut."
                    ),
                    "schema": {"type": "string"},
                },
            },
        },
        **errors(status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT),
    },
)
def create_labels(body: LabelRequest, session: SessionDep, runtime: RuntimeDep) -> Response:
    if body.template != AUTO_TEMPLATE and body.template not in TEMPLATES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"No label template {body.template!r}."
        )
    preset = next((p for p in runtime.schema.presets if p.key == body.preset), None)
    if preset is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No preset {body.preset!r}.")
    burial_preset = None
    if body.burial_preset is not None:
        burial_preset = next(
            (p for p in runtime.schema.presets if p.key == body.burial_preset), None
        )
        if burial_preset is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"No preset {body.burial_preset!r}."
            )
    keys = {definition.key for definition in runtime.schema.fields}
    for name, chosen, allowed in [
        ("caption_fields", body.caption_fields, keys | {NAME}),
        ("extra_fields", body.extra_fields, keys),
    ]:
        named = [entry.field for entry in chosen or [] if entry.field]
        if unknown := [key for key in named if key not in allowed]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{name} names fields that cannot be printed there: {listed(unknown)}.",
            )
    in_caption = body.caption_fields if body.caption_fields is not None else entries(preset)
    # Extras go into a burial zone that has room for text, and after the caption on other
    # templates when the request chose them.
    in_burial = body.extra_fields
    if in_burial is None:
        in_burial = entries(burial_preset) if burial_preset else []
    after_caption = body.extra_fields or []
    rows = {
        row.id: row
        for row in session.scalars(
            select(PlantRow).where(PlantRow.id.in_(set(body.plants)), ~PlantRow.removed)
        )
    }
    if missing := [plant_id for plant_id in body.plants if plant_id not in rows]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No plant with the id {listed(missing)}.")
    if untagged := [plant_id for plant_id in body.plants if rows[plant_id].tag is None]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"These plants have no number to print: {listed(untagged)}.",
        )
    overrides = body.layout.model_dump(exclude_none=True)
    batches: dict[str, list[Item]] = {}
    for plant_id in body.plants:
        fields, custom = rows[plant_id].fields, rows[plant_id].custom
        key = chosen_template(body.template, fields)
        lines = caption(runtime.schema, in_caption, fields, custom)
        burial: list[list[Run]] = []
        if TEMPLATES[key].layout.model_copy(update=overrides).burial_text:
            burial = extra_text(runtime.schema, in_burial, fields, body.language, custom)
        else:
            lines += extra_text(runtime.schema, after_caption, fields, body.language, custom)
        batches.setdefault(key, []).append(
            Item(cast(str, rows[plant_id].tag), lines, burial, plant_id)
        )
    pages: list[Page] = []
    try:
        # A partly used sheet is the first one fed in.
        for key in sorted(batches, key=list(TEMPLATES).index):
            layout = TEMPLATES[key].layout.model_copy(update=overrides)
            pages += layout_pages(layout, batches[key], 0 if pages else body.skip)
    except LayoutError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    if body.format == LabelFormat.SVG:
        if body.page > len(pages):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"There is no page {body.page}: the labels take {len(pages)}.",
            )
        content = to_svg(pages[body.page - 1], LABELS_TITLE)
    else:
        content = to_pdf(pages, LABELS_TITLE)
    return Response(
        content,
        media_type=LABEL_TYPES[body.format],
        headers={
            "X-Page-Count": str(len(pages)),
            "X-Cut-Captions": ",".join(cut_captions(body.plants, pages)),
            "Content-Disposition": f'inline; filename="labels.{body.format.value}"',
        },
    )
