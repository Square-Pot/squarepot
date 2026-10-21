# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes of API version 1."""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterator
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from squarepot_server import __version__
from squarepot_server.api.models import (
    AUTO_TEMPLATE,
    Collection,
    Error,
    FieldSchema,
    Health,
    LabelFormat,
    LabelRequest,
    LabelTemplate,
    Plant,
    Sync,
    SyncKind,
    TagLookup,
)
from squarepot_server.db import CollectionRow, PlantRow, current_seq, get_meta
from squarepot_server.labels.caption import burial_text, caption
from squarepot_server.labels.layout import TEMPLATES, Item, LayoutError, Page, layout_pages
from squarepot_server.labels.render import to_pdf, to_svg
from squarepot_server.runtime import Runtime

bearer = HTTPBearer(
    auto_error=False,
    description="The API token set by the operator at installation.",
)


CURSOR_SEQ = re.compile(r"[0-9]{1,18}")
LABEL_TYPES = {LabelFormat.PDF: "application/pdf", LabelFormat.SVG: "image/svg+xml"}
LABELS_TITLE = "Square-Pot labels"


def get_runtime(request: Request) -> Runtime:
    return cast(Runtime, request.app.state.runtime)


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = get_runtime(request).settings.api_token.get_secret_value().encode()
    given = credentials.credentials.encode() if credentials else b""
    if not secrets.compare_digest(given, expected):
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


def to_collection(row: CollectionRow) -> Collection:
    return Collection(
        id=row.id,
        name=row.name,
        plant_count=row.plant_count,
        synced_at=row.synced_at,
        error=row.error,
    )


def to_plant(row: PlantRow) -> Plant:
    return Plant(
        id=row.id, collection_id=row.collection_id, tag=row.tag, row=row.row, fields=row.fields
    )


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
    responses=errors(status.HTTP_401_UNAUTHORIZED),
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
def list_collections(session: SessionDep) -> list[Collection]:
    rows = session.scalars(
        select(CollectionRow).where(~CollectionRow.removed).order_by(CollectionRow.id)
    )
    return [to_collection(row) for row in rows]


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
    return TagLookup(tag=tag, plants=[to_plant(row) for row in rows])


@router.get(
    "/sync",
    tags=["sync"],
    summary="Get changes to the local copy since a cursor",
    description=(
        "Without `cursor`, returns a full copy of every collection. With the `cursor` of the "
        "previous response, returns only what changed since then, or a full copy when the "
        "cursor can no longer be served. See `kind`. Responses are gzip-compressed when the "
        "client accepts it."
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
        collections=[to_collection(row) for row in collection_rows if not row.removed],
        removed_collections=[row.id for row in collection_rows if row.removed],
        plants=[to_plant(row) for row in plant_rows if not row.removed],
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
        "a caption too long for the label is shrunk, then cut short with an ellipsis."
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
                }
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
    batches: dict[str, list[Item]] = {}
    for plant_id in body.plants:
        fields = rows[plant_id].fields
        batches.setdefault(chosen_template(body.template, fields), []).append(
            Item(
                cast(str, rows[plant_id].tag),
                caption(runtime.schema, preset, fields),
                burial_text(runtime.schema, burial_preset, fields, body.language)
                if burial_preset
                else [],
            )
        )
    overrides = body.layout.model_dump(exclude_none=True)
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
            "Content-Disposition": f'inline; filename="labels.{body.format.value}"',
        },
    )
