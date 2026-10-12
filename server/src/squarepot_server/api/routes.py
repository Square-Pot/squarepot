# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes of API version 1."""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from squarepot_server import __version__
from squarepot_server.api.models import (
    Collection,
    Error,
    FieldSchema,
    Health,
    Sync,
    TagLookup,
)

bearer = HTTPBearer(
    auto_error=False,
    description="The API token set by the operator at installation.",
)


def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    """Placeholder until the token check is implemented; declares the scheme in the contract."""


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": Error} for code in codes}


def not_implemented() -> NoReturn:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet.")


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
def get_schema() -> FieldSchema:
    not_implemented()


@router.get(
    "/collections",
    tags=["collections"],
    summary="List collections and how fresh their copies are",
)
def list_collections() -> list[Collection]:
    not_implemented()


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
) -> TagLookup:
    if int(tag) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "000000 is reserved.")
    not_implemented()


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
) -> Sync:
    not_implemented()
