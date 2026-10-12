# SPDX-License-Identifier: AGPL-3.0-or-later
"""Label templates, and labels laid out on pages.

The one rule that is never bent: every symbol is printed whole, with a white
quiet zone of at least one module on the label around it. A label too small
for that is an error, never a crop; only the caption gives way, by shrinking
and then being cut short.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise

from squarepot_server.api.models import Label, LabelLayout, LabelTemplate, PageSize
from squarepot_server.labels import datamatrix
from squarepot_server.labels.text import Command, Run, font, truncate, width, words, wrap

PAGE_SIZES = {PageSize.A4: (210.0, 297.0), PageSize.LETTER: (215.9, 279.4)}
QUIET_MODULES = 1
# Caption: font sizes in millimetres per em, line height, and insets from the label edge.
MAX_FONT = 3.0
MIN_FONT = 1.8
FONT_STEP = 0.1
LINE_HEIGHT = 1.15
BASELINE = 0.9
EDGE = 0.4
TEXT_PAD = 0.4
BOX_LINE = 0.15
CUT_LINE = 0.1
CUT_GREY = 0.6
# Tolerance for lengths given in decimal millimetres.
EPSILON = 1e-9

TEMPLATES = {
    template.key: template
    for template in [
        LabelTemplate(
            key="strip",
            label=Label(en="Strip", ru="Полоска"),
            description="An upright strip for a pot: the code on top, the caption under it.",
            layout=LabelLayout(
                width_mm=15,
                height_mm=35,
                module_mm=1.2,
                max_lines=6,
                caption_box=True,
                show_number=False,
                page=PageSize.A4,
                margin_mm=10,
                gap_mm=2,
                cut_lines=True,
            ),
        ),
        LabelTemplate(
            key="compact",
            label=Label(en="Compact", ru="Компактная"),
            description="The code and one line of caption, for the smallest pots.",
            layout=LabelLayout(
                width_mm=15,
                height_mm=20,
                module_mm=1.2,
                max_lines=1,
                caption_box=True,
                show_number=False,
                page=PageSize.A4,
                margin_mm=10,
                gap_mm=2,
                cut_lines=True,
            ),
        ),
    ]
}


class LayoutError(ValueError):
    """The layout cannot hold whole symbols; the message says what to change."""


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def contains(self, other: Rect) -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and other.x + other.width <= self.x + self.width
            and other.y + other.height <= self.y + self.height
        )


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    grey: float


@dataclass(frozen=True)
class Symbol:
    tag: str
    label: Rect
    symbol: Rect
    quiet: Rect


@dataclass
class Page:
    """One page in millimetres, y down: filled black paths and stroked lines."""

    width: float
    height: float
    paths: list[list[Command]] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)


@dataclass(frozen=True)
class Item:
    """One label to print: its number and caption items."""

    tag: str
    caption: list[list[Run]]


@dataclass(frozen=True)
class Geometry:
    symbol_top: float
    symbol_left: float
    symbol_size: float
    caption_top: float


def geometry(layout: LabelLayout) -> Geometry:
    """Where the symbol goes on a label; raises LayoutError when it cannot go whole."""
    module = layout.module_mm
    size = datamatrix.SIZE * module
    needed = size + 2 * QUIET_MODULES * module
    side = (layout.width_mm - size) / 2
    top = min(side, 2 * QUIET_MODULES * module)
    if (
        layout.width_mm < needed - EPSILON
        or layout.height_mm < top + size + QUIET_MODULES * module - EPSILON
    ):
        raise LayoutError(
            f"A {layout.width_mm:g}x{layout.height_mm:g} mm label cannot hold a "
            f"{size:g} mm code with its quiet zone: it needs at least "
            f"{needed:g}x{needed:g} mm, or a smaller module_mm."
        )
    caption_top = top + size + QUIET_MODULES * module
    if (
        layout.max_lines
        and caption_area(layout, caption_top).height < MIN_FONT * LINE_HEIGHT - EPSILON
    ):
        raise LayoutError(
            f"A {layout.width_mm:g}x{layout.height_mm:g} mm label has no room for a caption "
            f"under the code: make it taller, or set max_lines to 0."
        )
    if layout.show_number and not layout.max_lines:
        raise LayoutError(
            "The number is printed as the caption's first line: set max_lines to 1 or more, "
            "or show_number to false."
        )
    if layout.cut_lines and layout.gap_mm < CUT_LINE - EPSILON:
        raise LayoutError(
            f"Cut lines need a gap of at least {CUT_LINE:g} mm between labels, or they would "
            f"run over the labels: widen gap_mm, or set cut_lines to false."
        )
    return Geometry(top, side, size, caption_top)


def caption_area(layout: LabelLayout, caption_top: float) -> Rect:
    """The text area of the caption, relative to the label's top left corner."""
    inset = EDGE + (TEXT_PAD if layout.caption_box else 0)
    top = caption_top + (TEXT_PAD if layout.caption_box else 0)
    bottom = layout.height_mm - inset
    return Rect(inset, top, layout.width_mm - 2 * inset, max(bottom - top, 0))


def fit(items: list[list[Run]], area: Rect, max_lines: int) -> tuple[float, list[list[Run]]]:
    """The largest font size at which the caption fits, and its lines; cut short if none does."""

    def lines_at(size: float) -> list[list[Run]]:
        # One line more than allowed is enough to know that the caption does not fit.
        lines: list[list[Run]] = []
        for item in items:
            lines += wrap(item, size, area.width, limit=max_lines + 1 - len(lines))
            if len(lines) > max_lines:
                break
        return lines

    # Words are broken only when no size keeps them whole.
    for whole_words in (True, False):
        size = MAX_FONT
        while size >= MIN_FONT - EPSILON:
            lines = lines_at(size)
            fits = (
                len(lines) <= max_lines and len(lines) * size * LINE_HEIGHT <= area.height + EPSILON
            )
            if fits and (
                not whole_words
                or all(width(word, size) <= area.width for item in items for word in words(item))
            ):
                return size, lines
            size = round(size - FONT_STEP, 6)
    size = MIN_FONT
    lines = lines_at(size)
    room = min(max_lines, math.floor(area.height / (size * LINE_HEIGHT) + EPSILON))
    if len(lines) > room:
        lines = [*lines[: room - 1], truncate(lines[room - 1], size, area.width)]
    return size, lines


def symbol_path(tag: str, x: float, y: float, module: float) -> list[Command]:
    """The dark modules as one path, with each row's runs merged into rectangles."""
    commands: list[Command] = []
    for row, cells in enumerate(datamatrix.encode(tag)):
        column = 0
        while column < datamatrix.SIZE:
            if not cells[column]:
                column += 1
                continue
            start = column
            while column < datamatrix.SIZE and cells[column]:
                column += 1
            left, right = x + start * module, x + column * module
            top, bottom = y + row * module, y + (row + 1) * module
            commands += [("M", left, top), ("L", right, top), ("L", right, bottom)]
            commands += [("L", left, bottom), ("Z",)]
    return commands


def draw_label(page: Page, x: float, y: float, layout: LabelLayout, item: Item) -> None:
    shape = geometry(layout)
    module = layout.module_mm
    symbol = Rect(x + shape.symbol_left, y + shape.symbol_top, shape.symbol_size, shape.symbol_size)
    quiet = QUIET_MODULES * module
    page.symbols.append(
        Symbol(
            tag=item.tag,
            label=Rect(x, y, layout.width_mm, layout.height_mm),
            symbol=symbol,
            quiet=Rect(
                symbol.x - quiet,
                symbol.y - quiet,
                symbol.width + 2 * quiet,
                symbol.height + 2 * quiet,
            ),
        )
    )
    page.paths.append(symbol_path(item.tag, symbol.x, symbol.y, module))

    items = ([[Run(item.tag)]] if layout.show_number else []) + item.caption
    if not layout.max_lines or not items:
        return
    area = caption_area(layout, shape.caption_top)
    size, lines = fit(items, area, layout.max_lines)
    if layout.caption_box:
        top = y + shape.caption_top + BOX_LINE / 2
        left = x + EDGE + BOX_LINE / 2
        right = x + layout.width_mm - EDGE - BOX_LINE / 2
        bottom = y + layout.height_mm - EDGE - BOX_LINE / 2
        corners = [(left, top), (right, top), (right, bottom), (left, bottom), (left, top)]
        for (x1, y1), (x2, y2) in pairwise(corners):
            page.lines.append(Line(x1, y1, x2, y2, BOX_LINE, 0.0))
    commands: list[Command] = []
    for index, line in enumerate(lines):
        baseline = y + area.y + index * size * LINE_HEIGHT + size * BASELINE
        cursor = x + area.x + (area.width - width(line, size)) / 2
        for run in line:
            commands += font(run.style).outline(run.text, size, cursor, baseline)
            cursor += font(run.style).width(run.text, size)
    if commands:
        page.paths.append(commands)


def grid(layout: LabelLayout) -> tuple[int, int]:
    """Columns and rows of labels on a page."""
    page_width, page_height = PAGE_SIZES[layout.page]
    columns = math.floor(
        (page_width - 2 * layout.margin_mm + layout.gap_mm) / (layout.width_mm + layout.gap_mm)
        + EPSILON
    )
    rows = math.floor(
        (page_height - 2 * layout.margin_mm + layout.gap_mm) / (layout.height_mm + layout.gap_mm)
        + EPSILON
    )
    if columns < 1 or rows < 1:
        raise LayoutError(
            f"A {layout.width_mm:g}x{layout.height_mm:g} mm label does not fit on a "
            f"{layout.page.value} page with {layout.margin_mm:g} mm margins."
        )
    return columns, rows


def cut_lines(page: Page, layout: LabelLayout, columns: int, rows: int) -> None:
    """Lines through the middle of every gap, so that a cut never reaches a label."""
    left, top = layout.margin_mm, layout.margin_mm
    pitch_x, pitch_y = layout.width_mm + layout.gap_mm, layout.height_mm + layout.gap_mm
    half = layout.gap_mm / 2
    x_end = left + columns * pitch_x - half
    y_end = top + rows * pitch_y - half
    for column in range(columns + 1):
        x = left + column * pitch_x - half
        page.lines.append(Line(x, top - half, x, y_end, CUT_LINE, CUT_GREY))
    for row in range(rows + 1):
        y = top + row * pitch_y - half
        page.lines.append(Line(left - half, y, x_end, y, CUT_LINE, CUT_GREY))


def layout_pages(layout: LabelLayout, items: list[Item], skip: int = 0) -> list[Page]:
    """Lay labels out in rows, page after page, after `skip` empty positions."""
    geometry(layout)
    columns, rows = grid(layout)
    per_page = columns * rows
    if skip >= per_page:
        raise LayoutError(f"A page holds {per_page} labels, so skip must be less than that.")
    slots = skip + len(items)
    page_width, page_height = PAGE_SIZES[layout.page]
    pages: list[Page] = []
    for number in range(max(1, math.ceil(slots / per_page))):
        page = Page(page_width, page_height)
        if layout.cut_lines:
            cut_lines(page, layout, columns, rows)
        pages.append(page)
        for slot in range(number * per_page, min(slots, (number + 1) * per_page)):
            if slot < skip:
                continue
            position = slot - number * per_page
            row, column = divmod(position, columns)
            x = layout.margin_mm + column * (layout.width_mm + layout.gap_mm)
            y = layout.margin_mm + row * (layout.height_mm + layout.gap_mm)
            draw_label(page, x, y, layout, items[slot - skip])
    return pages
