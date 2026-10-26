# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning an uploaded photo into the two JPEGs that are kept (ADR 0007).

The photo is turned the right way up, and its EXIF data, with the place it
was taken, is dropped: only the time it was taken is read from it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from PIL import Image, ImageOps, UnidentifiedImageError

LARGE = 2560
THUMBNAIL = 480
FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
# A 60-megapixel photo is larger than any phone takes; more is not a photo.
MAX_PIXELS = 60_000_000
EXIF_IFD = 0x8769
DATE_TIME = 0x0132
DATE_TIME_ORIGINAL = 0x9003
OFFSET_TIME_ORIGINAL = 0x9011


class UnsupportedImage(ValueError):
    pass


@dataclass(frozen=True)
class Processed:
    large: bytes
    thumbnail: bytes
    width: int
    height: int
    # When the camera says the photo was taken; naive when it gives no time zone.
    taken_at: datetime | None


def exif_time(exif: Image.Exif) -> datetime | None:
    details = exif.get_ifd(EXIF_IFD)
    text = details.get(DATE_TIME_ORIGINAL) or exif.get(DATE_TIME)
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.strptime(text.strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    offset = details.get(OFFSET_TIME_ORIGINAL)
    if isinstance(offset, str) and len(offset.strip("\x00 ")) == 6:
        offset = offset.strip("\x00 ")
        try:
            sign = -1 if offset[0] == "-" else 1
            delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
        except ValueError:
            return moment
        return moment.replace(tzinfo=timezone(sign * delta))
    return moment


def jpeg(image: Image.Image, size: int) -> tuple[bytes, tuple[int, int]]:
    """The image as a JPEG at most `size` pixels on its longer side, and its size."""
    copy = image.copy()
    copy.thumbnail((size, size), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    # No exif argument: nothing of the original's metadata is written.
    copy.save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue(), copy.size


def process(data: bytes) -> Processed:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format not in FORMATS:
                raise UnsupportedImage("not a JPEG, PNG or WebP image")
            if opened.width * opened.height > MAX_PIXELS:
                raise UnsupportedImage("the image is larger than 60 megapixels")
            taken_at = exif_time(opened.getexif())
            # A JPEG decodes at a smaller scale when that is enough: less memory.
            opened.draft("RGB", (LARGE, LARGE))
            image = ImageOps.exif_transpose(opened)
            if image.mode in ("RGBA", "LA", "P"):
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = image.convert("RGB")
            large, (width, height) = jpeg(image, LARGE)
            thumbnail, _ = jpeg(image, THUMBNAIL)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise UnsupportedImage("not a JPEG, PNG or WebP image") from error
    return Processed(large, thumbnail, width, height, taken_at)


def resolve_time(
    camera: datetime | None, client: datetime | None, now: datetime
) -> tuple[datetime, str]:
    """When the photo was taken, and from where: the camera, the client, or the upload.

    A camera time without a time zone is read in the client's, else as UTC.
    A time in the future is not believed.
    """
    if camera is not None:
        if camera.tzinfo is None:
            zone = client.tzinfo if client is not None and client.tzinfo else UTC
            camera = camera.replace(tzinfo=zone)
        if camera <= now:
            return camera.astimezone(UTC), "camera"
    if client is not None and client <= now:
        return client.astimezone(UTC), "client"
    return now, "upload"
