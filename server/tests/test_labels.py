# SPDX-License-Identifier: AGPL-3.0-or-later
"""Label sheets: every symbol whole, readable by a real decoder, in every template."""

from __future__ import annotations

import io
import time
from collections import Counter
from typing import Any

import pypdfium2
import pytest
import resvg_py
import zxingcpp
from fastapi.testclient import TestClient
from PIL import Image

from squarepot_server.api.models import LabelLayout, PageSize
from squarepot_server.config import DEFAULT_SCHEMA_FILE
from squarepot_server.fields import load_schema
from squarepot_server.labels import datamatrix
from squarepot_server.labels.caption import caption
from squarepot_server.labels.layout import (
    CUT_GREY,
    MIN_FONT,
    TEMPLATES,
    Item,
    LayoutError,
    Page,
    Rect,
    fit,
    layout_pages,
    symbol_path,
)
from squarepot_server.labels.render import to_pdf, to_svg
from squarepot_server.labels.text import ELLIPSIS, Command, Run, Style

SCHEMA = load_schema(DEFAULT_SCHEMA_FILE)
LABEL = next(preset for preset in SCHEMA.presets if preset.key == "label")
DPI = 300
DATA_MATRIX = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.DataMatrix)
PX_PER_MM = DPI / 25.4
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
TAGS = ["000001", "004217", "999999", "123456", "100000", "054321", "777777"]


def items(count: int) -> list[Item]:
    return [
        Item(TAGS[index % len(TAGS)], caption(SCHEMA, LABEL, PLANTS[index % len(PLANTS)]))
        for index in range(count)
    ]


def layout(template: str, **changes: object) -> LabelLayout:
    return TEMPLATES[template].layout.model_copy(update=changes)


# Every template, and each at the edges of what it allows: the smallest label that holds the
# symbol, the smallest module, no caption, no frame, with and without the number, Letter paper.
CHANGES: dict[str, dict[str, Any]] = {
    "default": {},
    "smallest-module": {"module_mm": 0.5, "width_mm": 6, "height_mm": 12},
    "tightest-width": {"width_mm": 14.4},
    "large-module": {"module_mm": 2.0, "width_mm": 25, "height_mm": 45},
    "code-only": {"max_lines": 0, "show_number": False, "height_mm": 14.4, "width_mm": 14.4},
    "no-frame-with-number": {"caption_box": False, "show_number": True},
    "no-number": {"show_number": False},
    "letter-no-gap": {"page": PageSize.LETTER, "gap_mm": 0, "cut_lines": False},
    "tightest-gap": {"width_mm": 14.4, "gap_mm": 0.1, "cut_lines": True},
}
VARIANTS = [
    pytest.param(layout(key, **changes), id=f"{key}-{name}")
    for key in TEMPLATES
    for name, changes in CHANGES.items()
]


def decode(image: Image.Image) -> list[tuple[str, float, float]]:
    """Every Data Matrix found on a page: its text and its centre in millimetres."""
    found = []
    for result in zxingcpp.read_barcodes(image, formats=DATA_MATRIX):
        corners = [
            result.position.top_left,
            result.position.top_right,
            result.position.bottom_right,
            result.position.bottom_left,
        ]
        x = sum(point.x for point in corners) / 4 / PX_PER_MM
        y = sum(point.y for point in corners) / 4 / PX_PER_MM
        found.append((result.text, x, y))
    return found


def rasterize_svg(page: Page) -> Image.Image:
    png = resvg_py.svg_to_bytes(
        svg_string=to_svg(page, "labels").decode(),
        dpi=DPI,
        background="#ffffff",
    )
    return Image.open(io.BytesIO(png)).convert("L")


def rasterize_pdf(pages: list[Page]) -> list[Image.Image]:
    document = pypdfium2.PdfDocument(to_pdf(pages, "labels"))
    return [page.render(scale=DPI / 72).to_pil().convert("L") for page in document]


def assert_every_symbol_decodes(page: Page, image: Image.Image) -> None:
    found = decode(image)
    assert Counter(text for text, _, _ in found) == Counter(s.tag for s in page.symbols)
    # Each decoded symbol is the one drawn there, not a neighbour.
    for text, x, y in found:
        [symbol] = [
            s for s in page.symbols if s.symbol.contains(Rect(x, y, 0, 0)) and s.tag == text
        ]
        assert symbol.label.contains(symbol.quiet)


@pytest.mark.parametrize("variant", VARIANTS)
def test_golden_every_template_decodes_as_svg_and_pdf(variant: LabelLayout) -> None:
    # Enough labels for a second page, after a few skipped positions.
    pages = layout_pages(variant, items(40), skip=3)
    for page in pages:
        assert_every_symbol_decodes(page, rasterize_svg(page))
    for page, image in zip(pages, rasterize_pdf(pages), strict=True):
        assert_every_symbol_decodes(page, image)
    assert sum(len(page.symbols) for page in pages) == 40


@pytest.mark.parametrize("variant", VARIANTS)
def test_nothing_is_drawn_in_a_quiet_zone(variant: LabelLayout) -> None:
    [page] = layout_pages(variant, items(5))
    symbol_paths = [
        symbol_path(s.tag, s.symbol.x, s.symbol.y, variant.module_mm) for s in page.symbols
    ]
    for symbol in page.symbols:
        assert symbol.label.contains(symbol.quiet)
        assert symbol.quiet.width == pytest.approx(12 * variant.module_mm)
        quiet = symbol.quiet
        inside = Rect(quiet.x + 1e-6, quiet.y + 1e-6, quiet.width - 2e-6, quiet.height - 2e-6)
        for line in page.lines:
            half = line.width / 2
            extent = Rect(
                min(line.x1, line.x2) - half,
                min(line.y1, line.y2) - half,
                abs(line.x2 - line.x1) + line.width,
                abs(line.y2 - line.y1) + line.width,
            )
            assert not overlaps(extent, inside), (line, symbol)
        for path in page.paths:
            if path in symbol_paths:
                continue
            # A Bezier curve lies within its control points, so a contour's bounding box
            # holds all of its ink.
            for contour in contours(path):
                assert not overlaps(bounds(contour), inside), (contour[:2], symbol)


def contours(path: list[Command]) -> list[list[tuple[float, float]]]:
    result: list[list[tuple[float, float]]] = []
    for command in path:
        if command[0] == "M":
            result.append([])
        coordinates = command[1:]
        result[-1] += list(zip(coordinates[::2], coordinates[1::2], strict=True))
    return result


def bounds(points: list[tuple[float, float]]) -> Rect:
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def overlaps(a: Rect, b: Rect) -> bool:
    return (
        a.x < b.x + b.width
        and b.x < a.x + a.width
        and a.y < b.y + b.height
        and b.y < a.y + a.height
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"width_mm": 14.3}, "cannot hold a 12 mm code with its quiet zone"),
        ({"width_mm": 14.4, "height_mm": 14.3, "max_lines": 0}, "cannot hold"),
        ({"height_mm": 16}, "no room for a caption"),
        ({"width_mm": 200, "height_mm": 280}, "does not fit on a a4 page"),
        ({"width_mm": 14.4, "gap_mm": 0}, "Cut lines need a gap of at least 0.1 mm"),
        ({"gap_mm": 0.05}, "Cut lines need a gap"),
        ({"show_number": True, "max_lines": 0}, "set max_lines to 1"),
    ],
)
def test_a_layout_too_small_is_an_error_not_a_crop(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(LayoutError, match=message):
        layout_pages(layout("strip", **changes), items(1))


def test_the_smallest_label_that_holds_the_symbol_is_accepted() -> None:
    [page] = layout_pages(
        layout("strip", width_mm=14.4, height_mm=14.4, max_lines=0, show_number=False), items(1)
    )
    [symbol] = page.symbols
    assert symbol.quiet == pytest.approx(symbol.label)


def test_pages_hold_full_rows_and_columns() -> None:
    pages = layout_pages(layout("strip"), items(80))
    # A4 minus 10 mm margins: 11 columns of 15 + 2 mm, 7 rows of 35 + 2 mm.
    assert [len(page.symbols) for page in pages] == [77, 3]
    assert pages[1].symbols[0].label == Rect(10, 10, 15, 35)


def test_skipped_positions_stay_empty() -> None:
    [page] = layout_pages(layout("strip"), items(1), skip=12)
    assert page.symbols[0].label == Rect(10 + 17, 10 + 37, 15, 35)


def test_cut_lines_run_through_the_middle_of_the_gaps() -> None:
    [page] = layout_pages(layout("strip"), items(1))
    xs = sorted({line.x1 for line in page.lines if line.x1 == line.x2 and line.grey == CUT_GREY})
    assert xs[:2] == [pytest.approx(9), pytest.approx(26)]
    assert len(xs) == 12


def test_output_is_deterministic() -> None:
    pages = layout_pages(layout("strip"), items(10))
    assert to_pdf(pages, "x") == to_pdf(layout_pages(layout("strip"), items(10)), "x")
    assert to_svg(pages[0], "x") == to_svg(layout_pages(layout("strip"), items(10))[0], "x")


def test_svg_and_pdf_are_well_formed() -> None:
    pages = layout_pages(layout("compact"), items(200))
    svg = to_svg(pages[0], "Labels & more").decode()
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert 'width="210mm" height="297mm"' in svg
    assert "<title>Labels &amp; more</title>" in svg
    assert "<text" not in svg  # text is in outlines
    document = pypdfium2.PdfDocument(to_pdf(pages, "Labels"))
    assert len(document) == len(pages) == 2
    width, height = document[0].get_size()
    assert (width, height) == (pytest.approx(595.276, abs=0.01), pytest.approx(841.89, abs=0.01))
    assert b"/ViewerPreferences << /PrintScaling /None >>" in to_pdf(pages, "Labels")


def test_skip_is_less_than_a_page() -> None:
    layout_pages(layout("strip"), items(1), skip=76)
    with pytest.raises(LayoutError, match="A page holds 77 labels"):
        layout_pages(layout("strip"), items(1), skip=77)


def test_a_huge_word_is_wrapped_quickly() -> None:
    started = time.perf_counter()
    [page] = layout_pages(layout("strip"), [Item("004217", [[Run("x" * 2000)]])])
    assert time.perf_counter() - started < 2
    assert len(page.symbols) == 1


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


def test_a_long_caption_shrinks_then_is_cut_short() -> None:
    area = Rect(0, 0, 13, 7)
    size, lines = fit(caption(SCHEMA, LABEL, PLANTS[2]), area, max_lines=3)
    assert size == MIN_FONT
    assert len(lines) == 3
    assert text(lines[-1]).endswith(ELLIPSIS)


def test_words_are_kept_whole_when_a_smaller_size_allows() -> None:
    area = Rect(0, 0, 14, 20)
    _, lines = fit(caption(SCHEMA, LABEL, PLANTS[2]), area, max_lines=6)
    assert "Gymnocalycium" in [text(line).split(" ")[0] for line in lines]


# The API


def test_templates_are_listed(client: TestClient) -> None:
    body = client.get("/api/v1/labels/templates").json()
    assert [template["key"] for template in body] == ["strip", "compact"]
    assert body[0]["layout"]["module_mm"] == 1.2
    assert body[0]["layout"]["show_number"] is True
    assert body[0]["layout"]["margin_mm"] == 10


def test_labels_as_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/v1/labels", json={"plants": ["main:004218", "main:004217"], "skip": 76}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-page-count"] == "2"
    images = [
        page.render(scale=DPI / 72).to_pil().convert("L")
        for page in pypdfium2.PdfDocument(response.content)
    ]
    assert [[text for text, _, _ in decode(image)] for image in images] == [["004218"], ["004217"]]


def test_labels_as_svg_page_by_page(client: TestClient) -> None:
    request = {"plants": ["main:004217"] * 78, "format": "svg", "page": 2}
    response = client.post("/api/v1/labels", json=request)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["x-page-count"] == "2"
    png = resvg_py.svg_to_bytes(svg_string=response.text, dpi=DPI, background="#ffffff")
    assert [text for text, _, _ in decode(Image.open(io.BytesIO(png)))] == ["004217"]


def test_layout_overrides_apply(client: TestClient) -> None:
    request = {
        "plants": ["main:004217"],
        "template": "compact",
        "layout": {"page": "letter", "module_mm": 1.0, "width_mm": 12},
        "format": "svg",
    }
    response = client.post("/api/v1/labels", json=request)
    assert response.status_code == 200
    assert 'width="215.9mm" height="279.4mm"' in response.text


@pytest.mark.parametrize(
    ("request_body", "status", "message"),
    [
        ({"plants": ["main:nope"]}, 404, "No plant with the id main:nope."),
        ({"plants": ["main:004217"], "template": "huge"}, 422, "No label template 'huge'."),
        ({"plants": ["main:004217"], "preset": "nope"}, 422, "No preset 'nope'."),
        (
            {"plants": ["main:004217"], "layout": {"width_mm": 10}},
            422,
            "A 10x35 mm label cannot hold a 12 mm code with its quiet zone",
        ),
        ({"plants": ["main:004217"], "format": "svg", "page": 2}, 422, "There is no page 2"),
        ({"plants": []}, 422, "plants"),
        ({"plants": ["main:004217"], "layout": {"module_mm": 0.3}}, 422, "module_mm"),
        ({"plants": ["main:004217"], "layout": {"margin_mm": 4.9}}, 422, "margin_mm"),
    ],
)
def test_labels_errors(
    client: TestClient, request_body: dict[str, object], status: int, message: str
) -> None:
    response = client.post("/api/v1/labels", json=request_body)
    assert response.status_code == status
    body = response.json()
    assert body["code"] == ("not_found" if status == 404 else "invalid_request")
    assert message in body["message"]


def test_plants_without_a_number_cannot_be_labelled(client: TestClient) -> None:
    sync = client.get("/api/v1/sync").json()
    [untagged] = [plant["id"] for plant in sync["plants"] if plant["tag"] is None]
    response = client.post("/api/v1/labels", json={"plants": ["main:004217", untagged]})
    assert response.status_code == 422
    assert response.json()["message"] == f"These plants have no number to print: {untagged}."
