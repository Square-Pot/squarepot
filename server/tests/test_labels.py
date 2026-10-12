# SPDX-License-Identifier: AGPL-3.0-or-later
"""Label sheets: every symbol whole, readable by a real decoder, in every template."""

from __future__ import annotations

import pytest
import zxingcpp
from PIL import Image

from squarepot_server.config import DEFAULT_SCHEMA_FILE
from squarepot_server.fields import load_schema
from squarepot_server.labels import datamatrix
from squarepot_server.labels.caption import caption
from squarepot_server.labels.text import Run, Style

SCHEMA = load_schema(DEFAULT_SCHEMA_FILE)
LABEL = next(preset for preset in SCHEMA.presets if preset.key == "label")
DATA_MATRIX = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.DataMatrix)
PLANTS = [
    {"field_number": "SB 1234", "genus": "lithops", "species": "lesliei", "ex": "Mesa Garden"},
    {"genus": "Conophytum", "affinity": "minimum"},
    {
        "field_number": "VG 671",
        "genus": "Gymnocalycium",
        "species": "spegazzinii",
        "subspecies": "cardenasianum",
        "cultivar": "Big Red",
        "ex": "a seller whose name is far too long for any small label",
    },
]


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


# The caption


def text(runs: list[Run]) -> str:
    return "".join(run.text for run in runs)


def test_caption_follows_the_preset_and_the_display_rules() -> None:
    items = caption(SCHEMA, LABEL, PLANTS[2])
    assert [text(item) for item in items] == [
        "VG 671",
        "Gymnocalycium spegazzinii subsp. cardenasianum \u2018Big Red\u2019",
        "ex a seller whose name is far too long for any small label",
    ]
    assert {run.style for run in items[0]} == {Style.BOLD}
    name = {run.text.strip(): run.style for run in items[1] if run.text.strip()}
    assert name["Gymnocalycium"] == Style.ITALIC
    assert name["subsp."] == Style.REGULAR
    assert name["\u2018Big Red\u2019"] == Style.REGULAR


def test_caption_normalises_case_and_skips_empty_fields() -> None:
    items = caption(SCHEMA, LABEL, {"field_number": "sb 12", "genus": "LITHOPS", "ex": " "})
    assert [text(item) for item in items] == ["SB 12", "Lithops"]


def test_a_name_first_is_not_set_in_bold() -> None:
    items = caption(SCHEMA, LABEL, PLANTS[1])
    assert [text(item) for item in items] == ["Conophytum aff. minimum"]
    assert Style.BOLD not in {run.style for run in items[0]}
