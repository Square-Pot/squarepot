# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes for plant photos (ADR 0007)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse

from squarepot_server.api.models import (
    MainPhotoChoice,
    Photo,
    PhotoChange,
    ThumbnailRequest,
    Thumbnails,
)
from squarepot_server.api.routes import RuntimeDep, errors, require_token
from squarepot_server.db import PhotoRow
from squarepot_server.photos.images import UnsupportedImage
from squarepot_server.photos.service import URLS_LAST, PhotoIdTaken, PhotoNotFound, Photos
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
        "a number can have photos. A comment given here can be changed later with `PATCH`."
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
    comment: Annotated[
        str,
        Query(
            max_length=1000,
            description=(
                "The owner's comment, so that a queued photo is one request. It travels in "
                "the address, which access logs record: a longer or private note is better "
                "sent with `PATCH`."
            ),
        ),
    ] = "",
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
    row = await run_in_threadpool(
        run, lambda: photos.add(photo_id, tag, bytes(data), taken_at, comment)
    )
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


def redirect_to(photos: Photos, photo_id: UUID, thumbnail: bool) -> RedirectResponse:
    row = run(lambda: photos.get(photo_id))
    key = row.thumbnail_key if thumbnail else row.key
    url = run(lambda: photos.storage.url(key, photos.clock() + URLS_LAST))
    # The address lasts six hours; a client may keep the redirect for one.
    return RedirectResponse(
        url, status.HTTP_307_TEMPORARY_REDIRECT, headers={"Cache-Control": "private, max-age=3600"}
    )


REDIRECT: dict[int | str, dict[str, Any]] = {
    status.HTTP_307_TEMPORARY_REDIRECT: {
        "description": "To an address of the file that works without the token for six hours."
    }
}


@router.post(
    "/photos/thumbnails",
    summary="Sign the thumbnail addresses of many photos",
    description=(
        "For a list of plants in a web page, where an image cannot send the token to "
        "`/thumbnail`: up to 200 photo ids in, one signed address each out. Ask again after "
        "`expires_at`."
    ),
)
def sign_thumbnails(body: ThumbnailRequest, runtime: RuntimeDep) -> Thumbnails:
    photos = photos_of(runtime)
    urls, expires_at = run(lambda: photos.thumbnails(body.ids))
    return Thumbnails(urls=urls, expires_at=expires_at)


@router.get(
    "/photos/{photo_id}/thumbnail",
    summary="Show a photo's thumbnail",
    description=(
        "Redirects to the JPEG at most 480 pixels on its longer side. A stable address for "
        "`Plant.main_photo_id`, whose own addresses would expire."
    ),
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    responses=REDIRECT,
)
def photo_thumbnail(photo_id: UUID, runtime: RuntimeDep) -> RedirectResponse:
    return redirect_to(photos_of(runtime), photo_id, thumbnail=True)


@router.get(
    "/photos/{photo_id}/image",
    summary="Show a photo",
    description="Redirects to the JPEG at most 2560 pixels on its longer side.",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    responses=REDIRECT,
)
def photo_image(photo_id: UUID, runtime: RuntimeDep) -> RedirectResponse:
    return redirect_to(photos_of(runtime), photo_id, thumbnail=False)


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
