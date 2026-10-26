# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uploaded photos become two JPEGs, upright, with no EXIF data left (ADR 0007)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta, timezone

import pytest
from PIL import Image, ImageCms

from squarepot_server.photos import images
from squarepot_server.photos.images import UnsupportedImage, process, resolve_time

EXIF_IFD = 0x8769
GPS_IFD = 0x8825
ORIENTATION = 0x0112
XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/'
    b'22-rdf-syntax-ns#"><rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" '
    b'exif:GPSLatitude="55,45.35N" exif:GPSLongitude="37,37.04E"/></rdf:RDF></x:xmpmeta>'
)
COMMENT = b"GPS 55.7558N 37.6173E home greenhouse"


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
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif, xmp=XMP, comment=COMMENT, icc_profile=icc)
    return out.getvalue()


def test_the_test_photo_carries_a_place_a_comment_and_a_profile() -> None:
    with Image.open(io.BytesIO(photo())) as image:
        assert image.getexif().get_ifd(GPS_IFD)
        assert image.info["comment"] == COMMENT
        assert "icc_profile" in image.info
        assert b"GPSLatitude" in image.info["xmp"]


def test_a_photo_is_turned_upright_and_loses_its_exif_data() -> None:
    result = process(photo())
    for data in (result.large, result.thumbnail):
        with Image.open(io.BytesIO(data)) as image:
            assert image.format == "JPEG"
            assert len(image.getexif()) == 0
            assert not {"exif", "xmp", "comment", "icc_profile"} & set(image.info)
        assert b"GPS" not in data
        assert b"greenhouse" not in data
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


def test_a_png_or_webp_is_refused_above_a_smaller_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(images, "MAX_DECODED_PIXELS", 99)
    out = io.BytesIO()
    Image.new("RGB", (10, 10)).save(out, "PNG")
    with pytest.raises(UnsupportedImage, match="larger than 0 megapixels"):
        process(out.getvalue())
    small = io.BytesIO()
    Image.new("RGB", (9, 11)).save(small, "WEBP")
    assert process(small.getvalue()).width == 9
    # A JPEG decodes at a reduced scale, so it keeps the larger limit.
    assert process(photo(size=(10, 10), orientation=1)).width == 10


def test_a_palette_image_and_a_grey_one_become_rgb() -> None:
    for mode in ("P", "L", "LA"):
        out = io.BytesIO()
        Image.new(mode, (20, 10)).save(out, "PNG")
        with Image.open(io.BytesIO(process(out.getvalue()).large)) as image:
            assert (image.mode, image.size) == ("RGB", (20, 10))


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
