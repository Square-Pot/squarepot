# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading the label numbers in a photo of plants (ADR 0008).

First on a grey copy at most FIRST_PASS pixels on its longer side, which is
enough for a label in a normal photo and quick; then, if nothing was read, on
the full image.
"""

from __future__ import annotations

import io

import zxingcpp
from PIL import Image, UnidentifiedImageError

from squarepot_server.labels.datamatrix import TAG
from squarepot_server.photos.images import (
    FORMATS,
    JPEG_FORMATS,
    MAX_DECODED_PIXELS,
    MAX_PIXELS,
    UnsupportedImage,
)

FIRST_PASS = 2000
DATA_MATRIX = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.DataMatrix)


def numbers_in(image: Image.Image) -> list[str]:
    """The label numbers read, each once, in the order found."""
    found: list[str] = []
    for result in zxingcpp.read_barcodes(image, formats=DATA_MATRIX):
        if TAG.fullmatch(result.text) and result.text not in found:
            found.append(result.text)
    return found


def read_numbers(data: bytes) -> list[str]:
    """The label numbers in a photo; raises UnsupportedImage for what is not one."""
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format not in FORMATS:
                raise UnsupportedImage("not a JPEG, PNG or WebP image")
            limit = MAX_PIXELS if opened.format in JPEG_FORMATS else MAX_DECODED_PIXELS
            if opened.width * opened.height > limit:
                raise UnsupportedImage(f"the image is larger than {limit // 1_000_000} megapixels")
            full = opened.width, opened.height
            opened.draft("L", (FIRST_PASS, FIRST_PASS))
            # Codes are read in any orientation, so the EXIF turn is not needed.
            image = opened.convert("L")
            image.thumbnail((FIRST_PASS, FIRST_PASS))
            found = numbers_in(image)
            if found or max(full) <= FIRST_PASS:
                return found
        # Nothing read on the small copy: the whole image, decoded again at full size.
        # A JPEG is decoded straight to grey: a third of the memory of RGB.
        with Image.open(io.BytesIO(data)) as opened:
            opened.draft("L", full)
            return numbers_in(opened.convert("L"))
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise UnsupportedImage("not a JPEG, PNG or WebP image") from error
