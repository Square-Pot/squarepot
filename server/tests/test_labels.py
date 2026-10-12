# SPDX-License-Identifier: AGPL-3.0-or-later
"""Label sheets: every symbol whole, readable by a real decoder, in every template."""

from __future__ import annotations

import pytest
import zxingcpp
from PIL import Image

from squarepot_server.labels import datamatrix

DATA_MATRIX = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.DataMatrix)


# The encoder


def test_encoder_draws_the_finder_and_timing_patterns() -> None:
    matrix = datamatrix.encode("004217")
    assert all(row[0] for row in matrix)
    assert all(matrix[-1])
    assert [cell for cell in matrix[0]] == [index % 2 == 0 for index in range(10)]
    assert [row[-1] for row in matrix] == [index % 2 == 1 for index in range(10)]


def test_encoder_codewords() -> None:
    # Digit pairs 00, 42, 17 as 130 + n, then the Reed-Solomon codewords.
    words = datamatrix.codewords("004217")
    assert words[:3] == [130, 172, 147]
    assert len(words) == 8


@pytest.mark.parametrize("tag", ["000000", "4217", "0042170", "00421a", "", "٠٠٤٢١٧"])
def test_encoder_refuses_what_is_not_a_label_number(tag: str) -> None:
    with pytest.raises(ValueError, match="not a label number"):
        datamatrix.encode(tag)


def test_every_digit_pair_decodes() -> None:
    # 100 symbols cover every value of every codeword position.
    tags = [f"{n:02d}{(n * 37) % 100:02d}{(n * 71 + 1) % 100:02d}" for n in range(100)]
    tags = [tag for tag in tags if tag != "000000"]
    module = 6
    for tag in tags:
        image = Image.new("L", (14 * module, 14 * module), 255)
        for row, cells in enumerate(datamatrix.encode(tag)):
            for column, dark in enumerate(cells):
                if dark:
                    x, y = (column + 2) * module, (row + 2) * module
                    image.paste(0, (x, y, x + module, y + module))
        [result] = zxingcpp.read_barcodes(image, formats=DATA_MATRIX)
        assert result.text == tag
        assert result.symbology_identifier == "]d1"
