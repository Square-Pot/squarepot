# SPDX-License-Identifier: AGPL-3.0-or-later
"""Label templates, and labels laid out on pages.

The one rule that is never bent: every symbol is printed whole, with a white
quiet zone of at least one module on the label around it. A label too small
for that is an error, never a crop; only the caption gives way, by shrinking
and then being cut short.

A label has a visible part, which holds the code and the caption, and may
have a white burial zone under it that goes into the substrate, blank or
with more about the plant. A blank band between the two can lift the code
clear of the soil.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise

from squarepot_server.api.models import (
    Label,
    LabelLayout,
    LabelOrientation,
    LabelTemplate,
    PageSize,
)
from squarepot_server.labels import datamatrix
from squarepot_server.labels.text import Command, Run, Style, font, truncate, width, words, wrap

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
SOIL_DASH = 1.0
# The number is a backup for the code, set small next to it in a strip as deep as its font
# size: under the code on a vertical label, down its side on a horizontal one.
NUMBER_FONT = MIN_FONT
# Extra room inside the caption's frame, left and right, that a caption gets when it costs no
# font size: more on the left of a horizontal label's caption, which starts there, the same on
# both sides of a vertical one's, which is centred. It shrinks in steps, both sides together,
# down to none, as a longer caption needs the room.
COMFORT = {LabelOrientation.HORIZONTAL: (2.0, 1.0), LabelOrientation.VERTICAL: (1.0, 1.0)}
COMFORT_STEPS = 4
# Burial text: at most this font size, and its box's inset from the cut corners at the sides
# and from the soil line and the bottom edge.
BURIAL_MAX_FONT = 2.5
BURIAL_SIDE = 1.0
BURIAL_TOP = 0.5
# Tolerance for lengths given in decimal millimetres.
EPSILON = 1e-9

TEMPLATES = {
    template.key: template
    for template in [
        LabelTemplate(
            key="vertical",
            label=Label(en="Vertical", ru="Вертикальная"),
            description=(
                "An upright label for a pot: the code on top, the caption under it, and a "
                "white zone at the bottom that goes into the substrate."
            ),
            layout=LabelLayout(
                orientation=LabelOrientation.VERTICAL,
                width_mm=15,
                height_mm=60,
                burial_mm=25,
                band_mm=0,
                chamfer_mm=0,
                burial_text=False,
                module_mm=1.2,
                max_lines=8,
                caption_box=True,
                show_number=True,
                page=PageSize.A4,
                margin_mm=10,
                gap_mm=2,
                cut_lines=True,
            ),
        ),
        LabelTemplate(
            key="horizontal",
            label=Label(en="Horizontal", ru="Горизонтальная"),
            description=(
                "A wide, low label for low plants: the caption and the code side by side, a "
                "blank band under them that lifts them clear of the soil, and a white zone with "
                "cut corners that goes into the substrate."
            ),
            layout=LabelLayout(
                orientation=LabelOrientation.HORIZONTAL,
                width_mm=76,
                height_mm=33,
                burial_mm=15,
                band_mm=3,
                chamfer_mm=5,
                burial_text=True,
                module_mm=1.2,
                max_lines=4,
                caption_box=True,
                show_number=True,
                page=PageSize.A4,
                # 9 mm, not 10, keeps eight rows of 33 mm on an A4 page.
                margin_mm=9,
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
        # Within EPSILON: positions on a page carry float error from adding lengths.
        return (
            self.x <= other.x + EPSILON
            and self.y <= other.y + EPSILON
            and other.x + other.width <= self.x + self.width + EPSILON
            and other.y + other.height <= self.y + self.height + EPSILON
        )


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    grey: float
    # Length of each dash and of each space between them; 0 draws a solid line.
    dash: float = 0


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
    # Plants whose caption or burial text was cut short, by `Item.plant_id`.
    cut: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Item:
    """One label to print: its number, caption items and burial text items."""

    tag: str
    caption: list[list[Run]]
    burial: list[list[Run]] = field(default_factory=list)
    # The plant's id, to report a cut caption by; the tag when empty.
    plant_id: str = ""


@dataclass(frozen=True)
class Geometry:
    """Where things go on a label, relative to its top left corner."""

    symbol: Rect
    # Outer edge of the caption's frame; the text sits inside it.
    frame: Rect
    text: Rect
    # Height of the visible part, which holds the code and the caption.
    visible: float
    # Where the burial zone starts: the visible part and the band above it.
    soil: float
    # The strip next to the code that holds the number, when it is shown.
    number: Rect | None = None
    # The box in the burial zone for its text, when it has one.
    burial: Rect | None = None


def geometry(layout: LabelLayout) -> Geometry:
    """Where the symbol goes on a label; raises LayoutError when it cannot go whole."""
    module = layout.module_mm
    size = datamatrix.SIZE * module
    quiet = QUIET_MODULES * module
    needed = size + 2 * quiet
    soil = layout.height_mm - layout.burial_mm
    visible = soil - layout.band_mm
    horizontal = layout.orientation == LabelOrientation.HORIZONTAL
    name = f"A {layout.width_mm:g}x{layout.height_mm:g} mm label"
    number = None
    if layout.band_mm and not layout.burial_mm:
        raise LayoutError("Only a burial zone has a band above it: set burial_mm, or band_mm to 0.")
    if layout.burial_mm and visible <= EPSILON:
        band = f" and {layout.band_mm:g} mm band" if layout.band_mm else ""
        raise LayoutError(
            f"{name} has no visible part above its {layout.burial_mm:g} mm burial{band}."
        )
    if horizontal:
        top = (visible - size) / 2
        side = min(top, 2 * quiet)
        symbol = Rect(layout.width_mm - side - size, top, size, size)
        fits = visible >= needed - EPSILON and layout.width_mm >= needed - EPSILON
        right = symbol.x - quiet
        if layout.show_number:
            number = Rect(right - NUMBER_FONT, symbol.y, NUMBER_FONT, size)
            right = number.x - TEXT_PAD
        frame = Rect(EDGE, EDGE, max(right - EDGE, 0), visible - 2 * EDGE)
    else:
        side = (layout.width_mm - size) / 2
        top = min(side, 2 * quiet)
        symbol = Rect(side, top, size, size)
        fits = layout.width_mm >= needed - EPSILON and visible >= top + size + quiet - EPSILON
        caption_top = top + size + quiet
        if layout.show_number:
            number = Rect(symbol.x, caption_top, size, NUMBER_FONT)
            caption_top = number.y + number.height
        frame = Rect(EDGE, caption_top, layout.width_mm - 2 * EDGE, visible - EDGE - caption_top)
    if not fits:
        burial = f" above a {layout.burial_mm:g} mm burial" if layout.burial_mm else ""
        raise LayoutError(
            f"{name} cannot hold a {size:g} mm code with its quiet zone{burial}: it needs "
            f"at least {needed:g}x{needed:g} mm visible, or a smaller module_mm."
        )
    pad = TEXT_PAD if layout.caption_box else 0
    text = Rect(
        frame.x + pad,
        frame.y + pad,
        max(frame.width - 2 * pad, 0),
        max(frame.height - 2 * pad, 0),
    )
    if layout.max_lines and (
        text.height < MIN_FONT * LINE_HEIGHT - EPSILON or text.width < MIN_FONT - EPSILON
    ):
        where = "beside" if horizontal else "under"
        raise LayoutError(
            f"{name} has no room for a caption {where} the code: make it "
            f"{'wider' if horizontal else 'taller'}, or set max_lines to 0."
        )
    if number is not None and (
        number.x < EDGE - EPSILON or number.y + number.height > visible - EDGE + EPSILON
    ):
        where = "beside" if horizontal else "under"
        raise LayoutError(
            f"{name} has no room for the number {where} the code: make it "
            f"{'wider' if horizontal else 'taller'}, or set show_number to false."
        )
    if layout.cut_lines and layout.gap_mm < CUT_LINE - EPSILON:
        raise LayoutError(
            f"Cut lines need a gap of at least {CUT_LINE:g} mm between labels, or they would "
            f"run over the labels: widen gap_mm, or set cut_lines to false."
        )
    if layout.chamfer_mm and not layout.burial_mm:
        raise LayoutError(
            "Only a burial zone has corners to cut: set burial_mm, or chamfer_mm to 0."
        )
    if 2 * layout.chamfer_mm > layout.width_mm + EPSILON:
        raise LayoutError(
            f"A {layout.chamfer_mm:g} mm chamfer on each corner is wider than the "
            f"{layout.width_mm:g} mm label: make chamfer_mm smaller."
        )
    box = None
    if layout.burial_text:
        inset = layout.chamfer_mm + BURIAL_SIDE
        box = Rect(
            inset,
            soil + BURIAL_TOP,
            layout.width_mm - 2 * inset,
            layout.burial_mm - 2 * BURIAL_TOP,
        )
        if box.width < MIN_FONT - EPSILON or box.height < MIN_FONT * LINE_HEIGHT - EPSILON:
            raise LayoutError(
                f"{name} has no room for text in its burial zone: make burial_mm larger or "
                f"chamfer_mm smaller, or set burial_text to false."
            )
    return Geometry(symbol, frame, text, visible, soil, number, box)


def fit(
    items: list[list[Run]], area: Rect, max_lines: int, largest: float = MAX_FONT
) -> tuple[float, list[list[Run]], bool]:
    """The largest font size at which the caption fits, and its lines; cut short if none does.

    The last value says whether the lines were cut short.
    """

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
        size = largest
        while size >= MIN_FONT - EPSILON:
            lines = lines_at(size)
            fits = (
                len(lines) <= max_lines and len(lines) * size * LINE_HEIGHT <= area.height + EPSILON
            )
            if fits and (
                not whole_words
                or all(width(word, size) <= area.width for item in items for word in words(item))
            ):
                return size, lines, False
            size = round(size - FONT_STEP, 6)
    size = MIN_FONT
    lines = lines_at(size)
    room = min(max_lines, math.floor(area.height / (size * LINE_HEIGHT) + EPSILON))
    if len(lines) <= room:
        return size, lines, False
    return size, [*lines[: room - 1], truncate(lines[room - 1], size, area.width)], True


def comfortable_fit(
    items: list[list[Run]], text: Rect, max_lines: int, orientation: LabelOrientation
) -> tuple[Rect, float, list[list[Run]], bool]:
    """The caption's area, font size and lines, with the most extra room that costs no size.

    When even the smallest size does not fit, the caption gets all of the room, so that as
    little as possible is cut.
    """
    left, right = COMFORT[orientation]
    # Never so much that not even one character fits.
    scale = min(1.0, max(text.width - MIN_FONT, 0) / (left + right))
    best: tuple[Rect, float, list[list[Run]], bool] | None = None
    for step in range(COMFORT_STEPS, -1, -1):
        share = scale * step / COMFORT_STEPS
        area = Rect(text.x + left * share, text.y, text.width - (left + right) * share, text.height)
        size, lines, cut = fit(items, area, max_lines)
        # Ties keep the larger inset, met first, except at the smallest size.
        if best is None or size > best[1] + EPSILON or (size <= MIN_FONT + EPSILON and step == 0):
            best = (area, size, lines, cut)
    assert best is not None
    return best


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
    symbol = Rect(x + shape.symbol.x, y + shape.symbol.y, shape.symbol.width, shape.symbol.height)
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
    if layout.burial_mm:
        draw_burial(page, x, y, layout, shape.soil)
    if shape.number is not None:
        draw_number(page, x + shape.number.x, y + shape.number.y, shape.number, item.tag)
    cut = False
    if layout.max_lines and item.caption:
        cut |= draw_caption(page, x, y, layout, shape, item.caption)
    if shape.burial is not None and item.burial:
        cut |= draw_burial_text(page, x, y, shape.burial, item.burial)
    if cut:
        page.cut.append(item.plant_id or item.tag)


def draw_caption(
    page: Page, x: float, y: float, layout: LabelLayout, shape: Geometry, items: list[list[Run]]
) -> bool:
    """Draw the caption; whether it was cut short."""
    area, size, lines, cut = comfortable_fit(
        items, shape.text, layout.max_lines, layout.orientation
    )
    horizontal = layout.orientation == LabelOrientation.HORIZONTAL
    if layout.caption_box:
        frame = shape.frame
        top = y + frame.y + BOX_LINE / 2
        left = x + frame.x + BOX_LINE / 2
        right = x + frame.x + frame.width - BOX_LINE / 2
        bottom = y + frame.y + frame.height - BOX_LINE / 2
        corners = [(left, top), (right, top), (right, bottom), (left, bottom), (left, top)]
        for (x1, y1), (x2, y2) in pairwise(corners):
            page.lines.append(Line(x1, y1, x2, y2, BOX_LINE, 0.0))
    # Beside the code, the lines are centred in the height and start on the left.
    first = (area.height - len(lines) * size * LINE_HEIGHT) / 2 if horizontal else 0
    draw_lines(
        page, x + area.x, y + area.y + first, area.width, size, lines, centred=not horizontal
    )
    return cut


def draw_lines(
    page: Page,
    x: float,
    y: float,
    available: float,
    size: float,
    lines: list[list[Run]],
    centred: bool,
) -> None:
    """Lines of text from (x, y), their top left, each started on the left or centred."""
    commands: list[Command] = []
    for index, line in enumerate(lines):
        baseline = y + index * size * LINE_HEIGHT + size * BASELINE
        cursor = x + ((available - width(line, size)) / 2 if centred else 0)
        for run in line:
            commands += font(run.style).outline(run.text, size, cursor, baseline)
            cursor += font(run.style).width(run.text, size)
    if commands:
        page.paths.append(commands)


def draw_burial_text(page: Page, x: float, y: float, box: Rect, items: list[list[Run]]) -> bool:
    """The burial text at the top left of its box, as large as fits, then cut short.

    Returns whether it was cut short.
    """
    room = math.floor(box.height / (MIN_FONT * LINE_HEIGHT) + EPSILON)
    size, lines, cut = fit(items, box, room, BURIAL_MAX_FONT)
    draw_lines(page, x + box.x, y + box.y, box.width, size, lines, centred=False)
    return cut


def draw_number(page: Page, x: float, y: float, strip: Rect, tag: str) -> None:
    """The number in its strip, centred across it.

    Under the code it ends at the code's right edge. Down the side of the code it is centred
    and turned a quarter clockwise, with its top to the code.
    """
    regular = font(Style.REGULAR)
    length = regular.width(tag, NUMBER_FONT)
    if strip.width > strip.height:
        baseline = y + (strip.height + regular.digit_height(NUMBER_FONT)) / 2
        page.paths.append(regular.outline(tag, NUMBER_FONT, x + strip.width - length, baseline))
        return
    baseline = x + (strip.width - regular.digit_height(NUMBER_FONT)) / 2
    start = y + (strip.height - length) / 2
    commands: list[Command] = []
    # Set on a baseline at the origin, then (along, down) becomes (baseline - down, start + along).
    for command in regular.outline(tag, NUMBER_FONT, 0, 0):
        points = command[1:]
        turned: list[float] = []
        for along, down in zip(points[::2], points[1::2], strict=True):
            turned += [baseline - down, start + along]
        commands.append((command[0], *turned))
    page.paths.append(commands)


def draw_burial(page: Page, x: float, y: float, layout: LabelLayout, soil: float) -> None:
    """The soil line, just inside the burial zone, and the cut corners under it."""
    line = y + soil + CUT_LINE / 2
    page.lines.append(Line(x, line, x + layout.width_mm, line, CUT_LINE, CUT_GREY, dash=SOIL_DASH))
    if layout.chamfer_mm:
        # Started a line's width down, so that the stroke stays out of the quiet zone.
        top, bottom = y + soil + CUT_LINE, y + layout.height_mm
        right = x + layout.width_mm
        page.lines.append(Line(x, top, x + layout.chamfer_mm, bottom, CUT_LINE, CUT_GREY))
        page.lines.append(Line(right, top, right - layout.chamfer_mm, bottom, CUT_LINE, CUT_GREY))


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
