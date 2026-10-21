# SPDX-License-Identifier: AGPL-3.0-or-later
"""The two symbols under test, both holding a six-digit label number.

The 10x10 symbol is what the labels print today (ADR 0001): three data
codewords, one per digit pair, fill it, and five Reed-Solomon codewords
correct two errors. The 12x12 symbol has the same three codewords, then two
padding codewords, and seven Reed-Solomon codewords correct three errors.

The codewords, Reed-Solomon code and module placement are the server's own
(`squarepot_server.labels.datamatrix`), so the 10x10 symbol is exactly the one
printed on a label. `check.py` verifies both sizes against libdmtx.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

# The module alone: it needs nothing else from the server, which is not installed here.
SOURCE = Path(__file__).resolve().parents[2] / "server/src/squarepot_server/labels/datamatrix.py"
_spec = importlib.util.spec_from_file_location("datamatrix", SOURCE)
assert _spec is not None and _spec.loader is not None
datamatrix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(datamatrix)

# Symbol side -> (data codewords, error correction codewords), ISO/IEC 16022 Table 7.
CAPACITY = {10: (3, 5), 12: (5, 7)}
SIZES = tuple(CAPACITY)
PAD = 129


def pad(position: int) -> int:
    """The padding codeword at a 1-based position after the first (the 253-state algorithm)."""
    value = PAD + (149 * position) % 253 + 1
    return value - 254 if value > 254 else value


def codewords(tag: str, size: int) -> list[int]:
    data_count, ecc_count = CAPACITY[size]
    data = [130 + int(tag[index : index + 2]) for index in range(0, 6, 2)]
    if len(data) < data_count:
        data.append(PAD)
    while len(data) < data_count:
        data.append(pad(len(data) + 1))
    return data + datamatrix.error_correction(data, ecc_count)


def encode(tag: str, size: int) -> np.ndarray:
    """The symbol's modules as a boolean array, True dark, without a quiet zone."""
    if not datamatrix.TAG.match(tag):
        raise ValueError(f"not a label number: {tag!r}")
    words = codewords(tag, size)
    inner = size - 2
    placement = datamatrix.Placement(inner, inner)
    matrix = np.zeros((size, size), bool)
    matrix[:, 0] = True
    matrix[size - 1, :] = True
    matrix[0, :] = np.arange(size) % 2 == 0
    matrix[:, size - 1] = np.arange(size) % 2 == 1
    for row in range(inner):
        for column in range(inner):
            cell = placement.cells[row][column]
            if cell is None:
                # The unused 2x2 corner of a 12x12 data region: dark on its diagonal.
                dark = (row, column) in ((inner - 1, inner - 1), (inner - 2, inner - 2))
            else:
                word, bit = cell
                dark = bool(words[word] & (0x80 >> bit))
            matrix[row + 1, column + 1] = dark
    return matrix
