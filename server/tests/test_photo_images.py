# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uploaded photos become two JPEGs, upright, with no EXIF data left (ADR 0007)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta, timezone

import pytest
from PIL import Image

from squarepot_server.photos.images import UnsupportedImage, process, resolve_time

EXIF_IFD = 0x8769
GPS_IFD = 0x8825
ORIENTATION = 0x0112


def photo(
    size: tuple[int, int] = (400, 300),
    orientation: int = 6,
    taken: str | None = "2025:06:01 10:00:00",
    offset: str | None = "+03:00",
) -> bytes:
    """A JPEG as a phone writes it: turned by its EXIF orientation, with a time and a place."""
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    details = exif.get_ifd(EXIF_IFD)
    if taken is not None:
        details[0x9003] = taken
    if offset is not None:
        details[0x9011] = offset
    gps = exif.get_ifd(GPS_IFD)
    gps[1] = "N"
    gps[2] = (55.0, 45.0, 21.0)
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_the_test_photo_carries_a_place() -> None:
    with Image.open(io.BytesIO(photo())) as image:
        assert image.getexif().get_ifd(GPS_IFD)


def test_a_photo_is_turned_upright_and_loses_its_exif_data() -> None:
    result = process(photo())
    for data in (result.large, result.thumbnail):
        with Image.open(io.BytesIO(data)) as image:
            assert image.format == "JPEG"
            assert len(image.getexif()) == 0
            assert "exif" not in image.info
    with Image.open(io.BytesIO(result.large)) as image:
        assert image.size == (300, 400)
    assert (result.width, result.height) == (300, 400)
    assert result.taken_at == datetime(2025, 6, 1, 10, tzinfo=timezone(timedelta(hours=3)))


def test_a_large_photo_is_made_smaller() -> None:
    result = process(photo(size=(5000, 1000), orientation=1))
    assert (result.width, result.height) == (2560, 512)
    with Image.open(io.BytesIO(result.thumbnail)) as image:
        assert image.size == (480, 96)


def test_a_camera_time_without_a_zone_stays_naive() -> None:
    assert process(photo(offset=None)).taken_at == datetime(2025, 6, 1, 10)
    assert process(photo(taken=None, offset=None)).taken_at is None
    assert process(photo(taken="not a date", offset=None)).taken_at is None


def test_transparency_becomes_white() -> None:
    out = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(out, "PNG")
    result = process(out.getvalue())
    with Image.open(io.BytesIO(result.large)) as image:
        red, green, blue = image.convert("RGB").getpixel((25, 25))  # type: ignore[misc]
    assert min(red, green, blue) > 245


@pytest.mark.parametrize("kind", ["GIF", "BMP"])
def test_other_formats_are_refused(kind: str) -> None:
    out = io.BytesIO()
    Image.new("RGB", (10, 10)).save(out, kind)
    with pytest.raises(UnsupportedImage):
        process(out.getvalue())


def test_something_else_is_refused() -> None:
    with pytest.raises(UnsupportedImage):
        process(b"not an image at all")


NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
MOSCOW = timezone(timedelta(hours=3))


@pytest.mark.parametrize(
    ("camera", "client", "expected"),
    [
        (
            datetime(2025, 6, 1, 10, tzinfo=MOSCOW),
            None,
            (datetime(2025, 6, 1, 7, tzinfo=UTC), "camera"),
        ),
        (
            datetime(2025, 6, 1, 10),
            datetime(2026, 1, 1, tzinfo=MOSCOW),
            (datetime(2025, 6, 1, 7, tzinfo=UTC), "camera"),
        ),
        (datetime(2025, 6, 1, 10), None, (datetime(2025, 6, 1, 10, tzinfo=UTC), "camera")),
        (datetime(2027, 1, 1, tzinfo=UTC), None, (NOW, "upload")),
        (None, datetime(2026, 10, 1, tzinfo=UTC), (datetime(2026, 10, 1, tzinfo=UTC), "client")),
        (None, datetime(2027, 1, 1, tzinfo=UTC), (NOW, "upload")),
        (None, None, (NOW, "upload")),
    ],
)
def test_the_time_taken_comes_from_the_camera_then_the_client_then_the_upload(
    camera: datetime | None, client: datetime | None, expected: tuple[datetime, str]
) -> None:
    assert resolve_time(camera, client, NOW) == expected
