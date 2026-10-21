# SPDX-License-Identifier: AGPL-3.0-or-later
"""The symbols under test are standard: checked against the server and libdmtx.

For random tags: the research 10x10 symbol is the server's, module for module;
libdmtx, asked for each size, encodes the same modules; and the clean symbol
of each size decodes back to its tag with zxing-cpp and with libdmtx.
"""

from __future__ import annotations

import numpy as np
import zxingcpp
from PIL import Image
from pylibdmtx import pylibdmtx

import symbols
from symbols import datamatrix

TAGS = 500
# libdmtx's encoder output: 5 pixels per module after a 10 pixel margin.
LIBDMTX_MODULE, LIBDMTX_MARGIN = 5, 10


def libdmtx_modules(tag: str, size: int) -> np.ndarray:
    encoded = pylibdmtx.encode(tag.encode(), size=f"{size}x{size}")
    pixels = np.frombuffer(encoded.pixels, np.uint8).reshape(encoded.height, encoded.width, -1)
    centres = LIBDMTX_MARGIN + LIBDMTX_MODULE * np.arange(size) + LIBDMTX_MODULE // 2
    return pixels[np.ix_(centres, centres)][:, :, 0] < 128


def clean_image(modules: np.ndarray, px: int = 8, quiet: int = 2) -> Image.Image:
    image = np.kron(~modules, np.ones((px, px), bool))
    return Image.fromarray(np.pad(image, quiet * px, constant_values=True).astype(np.uint8) * 255)


def main() -> None:
    rng = np.random.default_rng(1)
    tags = ["000001", "999999", "004217"] + [
        f"{value:06d}" for value in rng.integers(1, 1_000_000, TAGS)
    ]
    failures: list[str] = []
    for tag in tags:
        if not np.array_equal(symbols.encode(tag, 10), np.array(datamatrix.encode(tag))):
            failures.append(f"{tag}: the 10x10 symbol is not the server's")
        for size in symbols.SIZES:
            modules = symbols.encode(tag, size)
            if not np.array_equal(modules, libdmtx_modules(tag, size)):
                failures.append(f"{tag}: the {size}x{size} symbol is not libdmtx's")
            image = clean_image(modules)
            read = [barcode.text for barcode in zxingcpp.read_barcodes(image)]
            if read != [tag]:
                failures.append(f"{tag}: zxing-cpp reads the clean {size}x{size} as {read}")
            read = [found.data.decode() for found in pylibdmtx.decode(image)]
            if read != [tag]:
                failures.append(f"{tag}: libdmtx reads the clean {size}x{size} as {read}")
    for failure in failures[:20]:
        print(failure)
    if failures:
        raise SystemExit(f"{len(failures)} check failures")
    print(f"check: {len(tags)} tags x {len(symbols.SIZES)} sizes are standard")


if __name__ == "__main__":
    main()
