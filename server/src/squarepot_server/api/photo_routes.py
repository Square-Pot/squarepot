# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes for plant photos (ADR 0007)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from squarepot_server.api.models import MainPhotoChoice, Photo, PhotoChange
from squarepot_server.api.routes import RuntimeDep, errors, require_token
from squarepot_server.db import PhotoRow
from squarepot_server.photos.images import UnsupportedImage
from squarepot_server.photos.service import PhotoIdTaken, PhotoNotFound, Photos
from squarepot_server.photos.storage import DiskStorage, PhotoStorageError
from squarepot_server.runtime import PHOTO_FILES_ROUTE, Runtime

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
IMAGE_BODY = {"schema": {"type": "string", "format": "binary"}}

public = APIRouter()
router = APIRouter(
    prefix="/api/v1",
    tags=["photos"],
    dependencies=[Depends(require_token)],
    responses=errors(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
TagPath = Annotated[str, Path(pattern=r"^[0-9]{6}$", examples=["004217"])]


def photos_of(runtime: Runtime) -> Photos:
    if runtime.photos is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Photos are not set up on this server."
        )
    return runtime.photos


def run[T](action: Callable[[], T]) -> T:
    """Run a photo action, turning its failures into error responses."""
    try:
        return action()
    except PhotoNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except PhotoIdTaken as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except UnsupportedImage as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{error}.") from error
    except PhotoStorageError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Photos cannot be stored: {error}."
        ) from error


def as_photo(photos: Photos, row: PhotoRow) -> Photo:
    _, main = photos.of_plant(row.tag, deleted=True)
    return photos.to_api(row, main)


@router.put(
    "/photos/{photo_id}",
    summary="Upload a photo of a plant",
    description=(
        "The body is the photo itself: a JPEG, PNG or WebP image of at most 30 MB. The "
        "server turns it the right way up, drops its EXIF data, including where it was taken, "
        "and keeps a large JPEG and a thumbnail. The client chooses the id: sending the same "
        "photo again, after a lost answer, changes nothing and returns it. Only a plant with "
        "a number can have photos."
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
async def upload_photo(
    photo_id: UUID,
    tag: Annotated[str, Query(pattern=r"^[0-9]{6}$", description="The plant's number.")],
    request: Request,
    runtime: RuntimeDep,
    taken_at: Annotated[
        datetime | None,
        Query(description="When the client took the photo, if the camera did not record it."),
    ] = None,
) -> Photo:
    photos = photos_of(runtime)
    if int(request.headers.get("content-length") or 0) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The photo is larger than 30 MB.")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, "The photo is larger than 30 MB."
            )
    if taken_at is not None and taken_at.tzinfo is None:
        taken_at = taken_at.replace(tzinfo=UTC)
    row = await run_in_threadpool(run, lambda: photos.add(photo_id, tag, bytes(data), taken_at))
    return await run_in_threadpool(as_photo, photos, row)


@router.get(
    "/plants/by-tag/{tag}/photos",
    summary="List a plant's photos in the order they were taken",
    description=(
        "Deleted photos are left out unless `deleted` is true. Their addresses expire: ask "
        "again after `urls_expire_at`."
    ),
)
def list_photos(
    tag: TagPath,
    runtime: RuntimeDep,
    deleted: Annotated[
        bool, Query(description="Include photos deleted in the last 30 days.")
    ] = False,
) -> list[Photo]:
    photos = photos_of(runtime)
    rows, main = run(lambda: photos.of_plant(tag, deleted))
    return [photos.to_api(row, main) for row in rows]


@router.patch("/photos/{photo_id}", summary="Change a photo's comment or the time it was taken")
def change_photo(photo_id: UUID, body: PhotoChange, runtime: RuntimeDep) -> Photo:
    photos = photos_of(runtime)
    return as_photo(photos, run(lambda: photos.change(photo_id, body)))


@router.delete(
    "/photos/{photo_id}",
    summary="Delete a photo",
    description="The photo leaves the plant's photos at once and can be restored for 30 days.",
)
def delete_photo(photo_id: UUID, runtime: RuntimeDep) -> Photo:
    photos = photos_of(runtime)
    return as_photo(photos, run(lambda: photos.delete(photo_id)))


@router.post("/photos/{photo_id}/restore", summary="Restore a deleted photo")
def restore_photo(photo_id: UUID, runtime: RuntimeDep) -> Photo:
    photos = photos_of(runtime)
    return as_photo(photos, run(lambda: photos.restore(photo_id)))


@router.put(
    "/plants/by-tag/{tag}/main-photo",
    summary="Choose the plant's main photo",
    status_code=status.HTTP_204_NO_CONTENT,
)
def choose_main_photo(tag: TagPath, body: MainPhotoChoice, runtime: RuntimeDep) -> Response:
    photos = photos_of(runtime)
    run(lambda: photos.choose_main(tag, body.photo_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public.get(f"{PHOTO_FILES_ROUTE}/{{key:path}}", include_in_schema=False)
def photo_file(key: str, expires: int, signature: str, runtime: RuntimeDep) -> FileResponse:
    """A photo file kept on the server's disk, at an address the server signed."""
    storage = runtime.photos.storage if runtime.photos is not None else None
    if not isinstance(storage, DiskStorage):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    path = storage.open(key, expires, signature, datetime.now(UTC))
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    media_type = "application/json" if key.endswith(".json") else "image/jpeg"
    return FileResponse(
        path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"}
    )
