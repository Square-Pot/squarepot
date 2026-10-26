# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning an uploaded photo into the two JPEGs that are kept (ADR 0007).

The photo is turned the right way up, its colours are converted to sRGB, and
nothing of its metadata is kept: no EXIF data (with the place it was taken),
no XMP, no comment and no colour profile. Only the time it was taken is read
from it.

Memory: a JPEG is decoded at the smallest scale that still gives the large
size, and every image is shrunk before any copy of it is made. Other formats
decode in full, so they are refused above a smaller size.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from PIL import Image, ImageCms, UnidentifiedImageError

LARGE = 2560
THUMBNAIL = 480
FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
# JPEG decodes at a reduced scale. A 60-megapixel photo is larger than any phone
# takes; more is not a photo.
MAX_PIXELS = 60_000_000
JPEG_FORMATS = {"JPEG", "MPO"}
# PNG and WebP decode in full, up to 4 bytes a pixel: 24 megapixels is ~100 MB.
MAX_DECODED_PIXELS = 24_000_000
ORIENTATION = 0x0112
# How to turn an image by its EXIF orientation, as ImageOps.exif_transpose does.
TURNS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
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


def jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    # Explicitly empty: Pillow would otherwise carry the source's comment along.
    image.save(out, "JPEG", quality=85, optimize=True, progressive=True, exif=b"", comment=b"")
    return out.getvalue()


def to_srgb(image: Image.Image, icc: bytes | None) -> Image.Image:
    """The image in sRGB, so that it looks the same with its profile left out."""
    if not icc:
        return image
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        converted = ImageCms.profileToProfile(
            image, source, ImageCms.createProfile("sRGB"), outputMode=image.mode
        )
    except (OSError, ValueError, ImageCms.PyCMSError):
        # A broken or unusual profile: keep the colours as they are.
        return image
    return converted if converted is not None else image


def decode(opened: Image.Image) -> Image.Image:
    """The image at most LARGE pixels on its longer side, upright, in RGB or RGBA."""
    exif = opened.getexif()
    orientation = exif.get(ORIENTATION, 1)
    icc = opened.info.get("icc_profile")
    transparent = opened.mode in ("RGBA", "LA", "PA") or "transparency" in opened.info
    # A JPEG decodes at a smaller scale when that is enough: less memory.
    opened.draft("RGB", (LARGE, LARGE))
    image: Image.Image = opened
    if image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGBA" if transparent else "RGB")
    image.thumbnail((LARGE, LARGE), Image.Resampling.LANCZOS)
    if orientation in TURNS:
        image = image.transpose(TURNS[orientation])
    if image.mode == "L":
        image = image.convert("RGB")
    image = to_srgb(image, icc)
    if image.mode == "RGBA":
        flat = Image.new("RGB", image.size, "white")
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    image.info = {}
    return image


def process(data: bytes) -> Processed:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format not in FORMATS:
                raise UnsupportedImage("not a JPEG, PNG or WebP image")
            limit = MAX_PIXELS if opened.format in JPEG_FORMATS else MAX_DECODED_PIXELS
            if opened.width * opened.height > limit:
                raise UnsupportedImage(f"the image is larger than {limit // 1_000_000} megapixels")
            taken_at = exif_time(opened.getexif())
            image = decode(opened)
            large = jpeg(image)
            width, height = image.size
            image.thumbnail((THUMBNAIL, THUMBNAIL), Image.Resampling.LANCZOS)
            thumbnail = jpeg(image)
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
