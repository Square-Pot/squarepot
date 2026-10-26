# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes for batch photo imports and their review queue (ADR 0008)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from squarepot_server.api.models import ImportedPhoto, ImportFiling
from squarepot_server.api.photo_routes import IMAGE_BODY, read_photo, run
from squarepot_server.api.routes import RuntimeDep, errors, require_token
from squarepot_server.db import ImportRow
from squarepot_server.photos.imports import (
    ImportClosed,
    ImportNotFound,
    Imports,
    ImportState,
)
from squarepot_server.photos.service import URLS_LAST
from squarepot_server.runtime import Runtime

router = APIRouter(
    prefix="/api/v1",
    tags=["imports"],
    dependencies=[Depends(require_token)],
    responses=errors(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)


def imports_of(runtime: Runtime) -> Imports:
    if runtime.imports is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Photos are not set up on this server."
        )
    return runtime.imports


def checked[T](action: Callable[[], T]) -> T:
    try:
        return run(action)
    except ImportNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ImportClosed as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


def as_imported(imports: Imports, row: ImportRow) -> ImportedPhoto:
    open_ = row.state not in (ImportState.FILED, ImportState.DISCARDED)
    expires_at = imports.clock() + URLS_LAST if open_ else None
    return ImportedPhoto(
        id=UUID(row.id),
        state=row.state,  # type: ignore[arg-type]
        reason=row.reason,
        numbers=row.numbers,
        tag=row.tag,
        file_time=row.file_time,
        uploaded_at=row.uploaded_at,
        url=imports.storage.url(row.staged_key, expires_at) if expires_at else None,
        url_expires_at=expires_at,
    )


@router.put(
    "/imports/{import_id}",
    summary="Add a photo to a batch import",
    description=(
        "The body is the photo, as for an upload. It is kept as it is until the import "
        "worker reads its label codes; one known number files it into that plant, anything "
        "else waits in the review queue. The time taken comes from its EXIF data, else from "
        "`file_time`, else from now. The client chooses the id: sending it again changes "
        "nothing."
    ),
    status_code=status.HTTP_201_CREATED,
    responses=errors(status.HTTP_413_CONTENT_TOO_LARGE),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "image/jpeg": IMAGE_BODY,
                "image/png": IMAGE_BODY,
                "image/webp": IMAGE_BODY,
            },
        }
    },
)
async def stage_import(
    import_id: UUID,
    request: Request,
    runtime: RuntimeDep,
    file_time: Annotated[
        datetime | None, Query(description="The file's own date, as the browser gives it.")
    ] = None,
) -> ImportedPhoto:
    imports = imports_of(runtime)
    data = await read_photo(request)
    if file_time is not None and file_time.tzinfo is None:
        file_time = file_time.replace(tzinfo=UTC)
    row = await run_in_threadpool(checked, lambda: imports.stage(import_id, data, file_time))
    return as_imported(imports, row)


@router.get(
    "/imports",
    summary="List the photos of batch imports not yet filed",
    description="Oldest first. With `state=review`, the queue that waits for the owner.",
)
def list_imports(
    runtime: RuntimeDep,
    state: Annotated[
        ImportState | None, Query(description="Only the photos in this state.")
    ] = None,
) -> list[ImportedPhoto]:
    imports = imports_of(runtime)
    return [as_imported(imports, row) for row in checked(lambda: imports.waiting(state))]


@router.get("/imports/{import_id}", summary="Show one photo of a batch import")
def get_import(import_id: UUID, runtime: RuntimeDep) -> ImportedPhoto:
    imports = imports_of(runtime)
    return as_imported(imports, checked(lambda: imports.get(import_id)))


@router.post(
    "/imports/{import_id}/file",
    summary="File an imported photo into the plant the owner picked",
    description="`409` if it was already filed or discarded; `404` if no plant has the number.",
)
def file_import(import_id: UUID, body: ImportFiling, runtime: RuntimeDep) -> ImportedPhoto:
    imports = imports_of(runtime)
    return as_imported(imports, checked(lambda: imports.file(import_id, body.tag)))


@router.post(
    "/imports/{import_id}/discard",
    summary="Discard an imported photo",
    description="Its staged file is removed. `409` if it was already filed.",
)
def discard_import(import_id: UUID, runtime: RuntimeDep) -> ImportedPhoto:
    imports = imports_of(runtime)
    return as_imported(imports, checked(lambda: imports.discard(import_id)))
