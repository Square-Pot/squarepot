# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pages as SVG (one page) and PDF (every page), with text already in outlines.

Both are written directly: the pages hold only filled paths and lines, and the
output is the same bytes for the same input.
"""

from __future__ import annotations

import zlib
from xml.sax.saxutils import escape, quoteattr

from squarepot_server.labels.layout import Page
from squarepot_server.labels.text import Command

POINTS_PER_MM = 72 / 25.4


def number(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def svg_path_data(commands: list[Command]) -> str:
    return "".join(
        command[0] + " ".join(number(value) for value in command[1:]) for command in commands
    )


def to_svg(page: Page, title: str) -> bytes:
    width, height = number(page.width), number(page.height)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
        f'viewBox="0 0 {width} {height}">\n',
        f"<title>{escape(title)}</title>\n" if title else "",
    ]
    for line in page.lines:
        grey = round(line.grey * 255)
        parts.append(
            f'<line x1="{number(line.x1)}" y1="{number(line.y1)}" x2="{number(line.x2)}" '
            f'y2="{number(line.y2)}" stroke="rgb({grey},{grey},{grey})" '
            f'stroke-width="{number(line.width)}" stroke-linecap="square"/>\n'
        )
    for path in page.paths:
        parts.append(f'<path d={quoteattr(svg_path_data(path))} fill="#000"/>\n')
    parts.append("</svg>\n")
    return "".join(parts).encode()


def pdf_content(page: Page) -> bytes:
    # Millimetres with y down, as on the page model, to points with y up.
    scale = number(POINTS_PER_MM)
    ops = [f"{scale} 0 0 -{scale} 0 {number(page.height * POINTS_PER_MM)} cm", "2 J"]
    for line in page.lines:
        ops.append(
            f"{number(line.width)} w {number(line.grey)} G {number(line.x1)} {number(line.y1)} m "
            f"{number(line.x2)} {number(line.y2)} l S"
        )
    ops.append("0 g")
    for path in page.paths:
        for command in path:
            values = " ".join(number(value) for value in command[1:])
            match command[0]:
                case "M":
                    ops.append(f"{values} m")
                case "L":
                    ops.append(f"{values} l")
                case "C":
                    ops.append(f"{values} c")
                case "Z":
                    ops.append("h")
        ops.append("f")
    return "\n".join(ops).encode()


def to_pdf(pages: list[Page], title: str) -> bytes:
    """A PDF 1.6 file: the catalog, the page tree, then a page and its content per page."""
    objects: list[bytes] = []
    page_ids = [3 + 2 * index for index in range(len(pages))]
    info_id = 3 + 2 * len(pages)
    # Printed at actual size: a viewer's "fit to page" would shrink the modules.
    objects.append(
        b"<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /PrintScaling /None >> >>"
    )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for page_id, page in zip(page_ids, pages, strict=True):
        width = number(page.width * POINTS_PER_MM)
        height = number(page.height * POINTS_PER_MM)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << >> /Contents {page_id + 1} 0 R >>".encode()
        )
        stream = zlib.compress(pdf_content(page), 9)
        objects.append(
            f"<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )
    objects.append(f"<< /Title {pdf_string(title)} /Producer (Square-Pot) >>".encode())

    output = bytearray(b"%PDF-1.6\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info_id} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def pdf_string(text: str) -> str:
    """A PDF text string: UTF-16 with a byte order mark, as hex."""
    return "<FEFF" + text.encode("utf-16-be").hex().upper() + ">"
