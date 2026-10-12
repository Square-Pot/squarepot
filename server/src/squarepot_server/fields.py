# SPDX-License-Identifier: AGPL-3.0-or-later
"""The field schema (schema/fields.yaml) and reading sheet rows by it.

The rules are those of docs/sheet-format.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from squarepot_server.api.models import FieldDefinition, FieldSchema, FieldType

Cell = str | int | float | bool | None

# Day 0 of the serial numbers that the Sheets API returns for dates.
SERIAL_EPOCH = date(1899, 12, 30)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEGACY_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
TAG = "tag"


def load_schema(path: Path) -> FieldSchema:
    return FieldSchema.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class TabError(Exception):
    """The tab cannot be imported at all (docs/sheet-format.md, "Validation and errors")."""


@dataclass(frozen=True)
class Issue:
    row: int
    column: str
    message: str


@dataclass(frozen=True)
class Row:
    row: int
    tag: str | None
    fields: dict[str, str]


@dataclass
class ParsedTab:
    rows: list[Row] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    # Numbers of skipped rows: they stay registered, so they are not issued again.
    skipped_tags: list[str] = field(default_factory=list)


class InvalidValue(ValueError):
    pass


def number_text(value: int | float) -> str:
    """A number cell as text, without a spurious ".0"."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def read_tag(cell: Cell) -> str:
    if isinstance(cell, bool):
        raise InvalidValue("not a number")
    text = number_text(cell) if isinstance(cell, int | float) else str(cell).strip()
    if not text.isascii() or not text.isdigit() or len(text) > 6:
        raise InvalidValue("not a six-digit number")
    tag = text.zfill(6)
    if tag == "000000":
        raise InvalidValue("000000 is reserved")
    return tag


def read_date(cell: Cell) -> str:
    if isinstance(cell, int | float) and not isinstance(cell, bool):
        try:
            return (SERIAL_EPOCH + timedelta(days=int(cell))).isoformat()
        except (ValueError, OverflowError) as error:
            # A number typed into a date cell, such as 20240315, or NaN.
            raise InvalidValue("not a date (YYYY-MM-DD)") from error
    text = str(cell).strip()
    try:
        if match := LEGACY_DATE.match(text):
            day, month, year = (int(part) for part in match.groups())
            return date(year, month, day).isoformat()
        if ISO_DATE.match(text):
            return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    raise InvalidValue("not a date (YYYY-MM-DD)")


def read_decimal(cell: Cell) -> str:
    if isinstance(cell, bool):
        raise InvalidValue("not a number")
    try:
        value = Decimal(repr(cell) if isinstance(cell, float) else str(cell).strip())
    except InvalidOperation as error:
        raise InvalidValue("not a number") from error
    if not value.is_finite():
        raise InvalidValue("not a number")
    return format(value, "f")


def read_text(definition: FieldDefinition, cell: Cell) -> str:
    text = number_text(cell) if isinstance(cell, int | float) else str(cell).strip()
    if definition.key == "currency":
        text = text.upper()
    if definition.pattern and not re.fullmatch(definition.pattern, text):
        raise InvalidValue(f"does not match {definition.pattern}")
    return text


def read_value(definition: FieldDefinition, cell: Cell) -> str:
    match definition.type:
        case FieldType.DATE:
            return read_date(cell)
        case FieldType.DECIMAL:
            return read_decimal(cell)
        case FieldType.TEXT:
            return read_text(definition, cell)


def is_empty(cell: Cell) -> bool:
    return cell is None or (isinstance(cell, str) and not cell.strip())


def map_header(schema: FieldSchema, header: list[Cell]) -> dict[int, FieldDefinition]:
    """Column index to field; raises TabError for a missing required or duplicate column."""
    by_name: dict[str, FieldDefinition] = {}
    for definition in schema.fields:
        for name in [definition.key, *definition.aliases]:
            by_name[name] = definition

    columns: dict[int, FieldDefinition] = {}
    seen: dict[str, int] = {}
    for index, cell in enumerate(header):
        match = by_name.get(str(cell).strip().lower()) if not is_empty(cell) else None
        if match is None:
            continue
        if match.key in seen:
            raise TabError(
                f"columns {column_name(seen[match.key])} and {column_name(index)} "
                f"both hold '{match.key}'"
            )
        seen[match.key] = index
        columns[index] = match

    for definition in schema.fields:
        if definition.required and definition.key not in seen:
            raise TabError(f"no '{definition.key}' column")
    return columns


def column_name(index: int) -> str:
    """Spreadsheet column letters for a zero-based index: 0 is A, 26 is AA."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def parse_tab(schema: FieldSchema, values: list[list[Cell]]) -> ParsedTab:
    """Read a tab's values, header first, into plant rows and per-cell issues."""
    if not values:
        raise TabError("the tab is empty")
    columns = map_header(schema, values[0])
    required = [d.key for d in schema.fields if d.required]
    result = ParsedTab()

    for offset, cells in enumerate(values[1:]):
        number = offset + 2
        if all(is_empty(cell) for cell in cells):
            continue
        tag: str | None = None
        fields: dict[str, str] = {}
        for index, definition in columns.items():
            cell = cells[index] if index < len(cells) else None
            if is_empty(cell):
                continue
            try:
                if definition.key == TAG:
                    tag = read_tag(cell)
                else:
                    fields[definition.key] = read_value(definition, cell)
            except InvalidValue as error:
                result.issues.append(Issue(number, column_name(index), str(error)))
        if missing := [key for key in required if key not in fields]:
            result.issues.append(Issue(number, "", f"skipped: no valid {', '.join(missing)}"))
            if tag is not None:
                result.skipped_tags.append(tag)
            continue
        result.rows.append(Row(number, tag, fields))
    return result
