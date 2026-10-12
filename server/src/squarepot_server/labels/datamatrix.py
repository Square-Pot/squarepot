# SPDX-License-Identifier: AGPL-3.0-or-later
"""The label code: a six-digit number in a 10x10 Data Matrix ECC200 symbol (ADR 0001).

Only this one symbol size is needed, so the encoder is written for it: three
data codewords (one per digit pair), five Reed-Solomon codewords, and the
module placement of ISO/IEC 16022, Annex F.
"""

from __future__ import annotations

import re

SIZE = 10
DATA_SIZE = SIZE - 2
ECC_CODEWORDS = 5
TAG = re.compile(r"^(?!000000)[0-9]{6}$")

# GF(256) with the Data Matrix field polynomial x^8 + x^5 + x^3 + x^2 + 1.
EXP = [0] * 255
LOG = [0] * 256
_value = 1
for _power in range(255):
    EXP[_power] = _value
    LOG[_value] = _power
    _value <<= 1
    if _value & 0x100:
        _value ^= 0x12D


def multiply(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return EXP[(LOG[a] + LOG[b]) % 255]


def generator(degree: int) -> list[int]:
    """Coefficients of (x + a^1)(x + a^2)...(x + a^degree), a = 2, highest power first."""
    polynomial = [1]
    for power in range(1, degree + 1):
        root = EXP[power]
        polynomial = [
            high ^ multiply(low, root)
            for high, low in zip([*polynomial, 0], [0, *polynomial], strict=True)
        ]
    return polynomial


def error_correction(data: list[int], degree: int = ECC_CODEWORDS) -> list[int]:
    polynomial = generator(degree)
    remainder = [0] * degree
    for codeword in data:
        factor = codeword ^ remainder[0]
        remainder = [*remainder[1:], 0]
        for index in range(degree):
            remainder[index] ^= multiply(polynomial[index + 1], factor)
    return remainder


def codewords(tag: str) -> list[int]:
    """Data codewords: digit pairs 00-99 are encoded as 130-229, which fills the symbol."""
    data = [130 + int(tag[index : index + 2]) for index in range(0, 6, 2)]
    return data + error_correction(data)


class Placement:
    """Where each bit of each codeword goes in the data region (ISO/IEC 16022, Annex F)."""

    def __init__(self, rows: int, columns: int) -> None:
        self.rows = rows
        self.columns = columns
        # (codeword index, bit index with 0 as the most significant), or None until placed.
        self.cells: list[list[tuple[int, int] | None]] = [[None] * columns for _ in range(rows)]
        self.place()

    def module(self, row: int, column: int, codeword: int, bit: int) -> None:
        if row < 0:
            row += self.rows
            column += 4 - ((self.rows + 4) % 8)
        if column < 0:
            column += self.columns
            row += 4 - ((self.columns + 4) % 8)
        self.cells[row][column] = (codeword, bit)

    def utah(self, row: int, column: int, codeword: int) -> None:
        for bit, (dr, dc) in enumerate(
            [(-2, -2), (-2, -1), (-1, -2), (-1, -1), (-1, 0), (0, -2), (0, -1), (0, 0)]
        ):
            self.module(row + dr, column + dc, codeword, bit)

    def corner(self, codeword: int, positions: list[tuple[int, int]]) -> None:
        for bit, (row, column) in enumerate(positions):
            self.module(row, column, codeword, bit)

    def place(self) -> None:
        rows, columns = self.rows, self.columns
        codeword, row, column = 0, 4, 0
        while True:
            if row == rows and column == 0:
                self.corner(
                    codeword,
                    [
                        (rows - 1, 0),
                        (rows - 1, 1),
                        (rows - 1, 2),
                        (0, columns - 2),
                        (0, columns - 1),
                        (1, columns - 1),
                        (2, columns - 1),
                        (3, columns - 1),
                    ],
                )
                codeword += 1
            if row == rows - 2 and column == 0 and columns % 4:
                self.corner(
                    codeword,
                    [
                        (rows - 3, 0),
                        (rows - 2, 0),
                        (rows - 1, 0),
                        (0, columns - 4),
                        (0, columns - 3),
                        (0, columns - 2),
                        (0, columns - 1),
                        (1, columns - 1),
                    ],
                )
                codeword += 1
            if row == rows - 2 and column == 0 and columns % 8 == 4:
                self.corner(
                    codeword,
                    [
                        (rows - 3, 0),
                        (rows - 2, 0),
                        (rows - 1, 0),
                        (0, columns - 2),
                        (0, columns - 1),
                        (1, columns - 1),
                        (2, columns - 1),
                        (3, columns - 1),
                    ],
                )
                codeword += 1
            if row == rows + 4 and column == 2 and not columns % 8:
                self.corner(
                    codeword,
                    [
                        (rows - 1, 0),
                        (rows - 1, columns - 1),
                        (0, columns - 3),
                        (0, columns - 2),
                        (0, columns - 1),
                        (1, columns - 3),
                        (1, columns - 2),
                        (1, columns - 1),
                    ],
                )
                codeword += 1
            # Sweep up and to the right, then down and to the left.
            while True:
                if row < rows and column >= 0 and self.cells[row][column] is None:
                    self.utah(row, column, codeword)
                    codeword += 1
                row -= 2
                column += 2
                if not (row >= 0 and column < columns):
                    break
            row += 1
            column += 3
            while True:
                if row >= 0 and column < columns and self.cells[row][column] is None:
                    self.utah(row, column, codeword)
                    codeword += 1
                row += 2
                column -= 2
                if not (row < rows and column >= 0):
                    break
            row += 3
            column += 1
            if not (row < rows or column < columns):
                break


PLACEMENT = Placement(DATA_SIZE, DATA_SIZE)


def encode(tag: str) -> list[list[bool]]:
    """The symbol's modules, row by row from the top; True is dark.

    The finder pattern is the solid left column and bottom row; the timing
    pattern alternates along the top row and the right column.
    """
    if not TAG.match(tag):
        raise ValueError(f"not a label number: {tag!r}")
    words = codewords(tag)
    matrix = [[False] * SIZE for _ in range(SIZE)]
    for row in range(SIZE):
        matrix[row][0] = True
        matrix[row][SIZE - 1] = row % 2 == 1
    for column in range(SIZE):
        matrix[SIZE - 1][column] = True
        matrix[0][column] = column % 2 == 0
    for row in range(DATA_SIZE):
        for column in range(DATA_SIZE):
            cell = PLACEMENT.cells[row][column]
            # Every module of a 10x10 symbol's data region carries a codeword bit.
            assert cell is not None
            codeword, bit = cell
            dark = bool(words[codeword] & (0x80 >> bit))
            matrix[row + 1][column + 1] = dark
    return matrix
