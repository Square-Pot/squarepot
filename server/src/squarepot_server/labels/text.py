# SPDX-License-Identifier: AGPL-3.0-or-later
"""Text as outlines, so that printed labels need no fonts and look the same everywhere."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from typing import Any

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

FONTS = Path(__file__).with_name("fonts")
ELLIPSIS = "…"

Point = tuple[float, float]
# Path commands in millimetres, y down:
# ("M", x, y), ("L", x, y), ("C", x1, y1, x2, y2, x, y), ("Z",)
Command = tuple[Any, ...]


class Style(StrEnum):
    REGULAR = "regular"
    ITALIC = "italic"
    BOLD = "bold"


FONT_FILES = {
    Style.REGULAR: "DejaVuSansCondensed.ttf",
    Style.ITALIC: "DejaVuSansCondensed-Oblique.ttf",
    Style.BOLD: "DejaVuSansCondensed-Bold.ttf",
}


@dataclass(frozen=True)
class Run:
    text: str
    style: Style = Style.REGULAR


class OutlinePen(BasePen):  # type: ignore[misc]
    """Records a glyph's outline as cubic path commands, scaled and placed."""

    def __init__(self, glyph_set: Any, scale: float, x: float, y: float) -> None:
        super().__init__(glyph_set)
        self.scale = scale
        self.x = x
        self.y = y
        self.commands: list[Command] = []
        self.current: Point = (0.0, 0.0)

    def point(self, point: Point) -> Point:
        # Font units, y up, to millimetres on the page, y down.
        return (self.x + point[0] * self.scale, self.y - point[1] * self.scale)

    def _moveTo(self, point: Point) -> None:
        self.commands.append(("M", *self.point(point)))
        self.current = point

    def _lineTo(self, point: Point) -> None:
        self.commands.append(("L", *self.point(point)))
        self.current = point

    def _curveToOne(self, first: Point, second: Point, end: Point) -> None:
        self.commands.append(("C", *self.point(first), *self.point(second), *self.point(end)))
        self.current = end

    def _qCurveToOne(self, control: Point, end: Point) -> None:
        # A quadratic Bézier is the cubic with controls two thirds of the way to its control point.
        start = self.current
        first = (
            start[0] + 2 / 3 * (control[0] - start[0]),
            start[1] + 2 / 3 * (control[1] - start[1]),
        )
        second = (end[0] + 2 / 3 * (control[0] - end[0]), end[1] + 2 / 3 * (control[1] - end[1]))
        self._curveToOne(first, second, end)

    def _closePath(self) -> None:
        self.commands.append(("Z",))

    def _endPath(self) -> None:
        self.commands.append(("Z",))


class Font:
    def __init__(self, path: Path) -> None:
        self.font = TTFont(path)
        self.units = self.font["head"].unitsPerEm
        self.cmap: dict[int, str] = self.font.getBestCmap()
        self.metrics: dict[str, tuple[int, int]] = self.font["hmtx"].metrics
        self.glyphs = self.font.getGlyphSet()

    def glyph(self, char: str) -> str:
        return self.cmap.get(ord(char)) or self.cmap.get(ord("?"), ".notdef")

    def width(self, text: str, size: float) -> float:
        """Advance width in millimetres of `text` set at `size` millimetres per em."""
        return float(sum(self.metrics[self.glyph(char)][0] for char in text) * size / self.units)

    def outline(self, text: str, size: float, x: float, baseline: float) -> list[Command]:
        scale = size / self.units
        commands: list[Command] = []
        for char in text:
            name = self.glyph(char)
            pen = OutlinePen(self.glyphs, scale, x, baseline)
            self.glyphs[name].draw(pen)
            commands.extend(pen.commands)
            x += self.metrics[name][0] * scale
        return commands


@cache
def font(style: Style) -> Font:
    return Font(FONTS / FONT_FILES[style])


def width(runs: list[Run], size: float) -> float:
    return sum(font(run.style).width(run.text, size) for run in runs)


def words(runs: list[Run]) -> list[list[Run]]:
    """Split runs at spaces into words, each a list of runs, keeping styles."""
    result: list[list[Run]] = [[]]
    for run in runs:
        parts = run.text.split(" ")
        for index, part in enumerate(parts):
            if index:
                result.append([])
            if part:
                result[-1].append(Run(part, run.style))
    return [word for word in result if word]


def split_word(word: list[Run], size: float, available: float) -> tuple[list[Run], list[Run]]:
    """The longest head of a word that fits `available`, at least one character, and the rest."""
    chars = [(char, run.style) for run in word for char in run.text]
    count = 1
    used = font(chars[0][1]).width(chars[0][0], size)
    while count < len(chars):
        used += font(chars[count][1]).width(chars[count][0], size)
        if used > available:
            break
        count += 1
    return join(chars[:count]), join(chars[count:])


def join(chars: list[tuple[str, Style]]) -> list[Run]:
    return [
        Run("".join(char for char, _ in group), style)
        for style, group in groupby(chars, key=itemgetter(1))
    ]


def wrap(
    runs: list[Run], size: float, available: float, limit: int | None = None
) -> list[list[Run]]:
    """Break runs into lines no wider than `available`; a word too long is broken by characters.

    With a `limit`, stops after that many lines.
    """
    lines: list[list[Run]] = []
    line: list[Run] = []
    pending = words(runs)
    while pending and (limit is None or len(lines) < limit):
        word = pending.pop(0)
        if not line and width(word, size) > available:
            head, rest = split_word(word, size, available)
            lines.append(head)
            if rest:
                pending.insert(0, rest)
            continue
        candidate = [*line, Run(" "), *word] if line else word
        if width(candidate, size) <= available or not line:
            line = candidate
            continue
        lines.append(line)
        line = []
        pending.insert(0, word)
    if line and (limit is None or len(lines) < limit):
        lines.append(line)
    return lines


def truncate(line: list[Run], size: float, available: float) -> list[Run]:
    """The line cut so that it ends with an ellipsis and fits `available`."""
    chars = [(char, run.style) for run in line for char in run.text]
    while chars:
        candidate = join([*chars, (ELLIPSIS, chars[-1][1])])
        if width(candidate, size) <= available:
            return candidate
        chars.pop()
    return [Run(ELLIPSIS)]
