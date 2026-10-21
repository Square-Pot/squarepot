# SPDX-License-Identifier: AGPL-3.0-or-later
"""The caption printed under the code, from a preset and the schema's display rules."""

from __future__ import annotations

from squarepot_server.api.models import Display, FieldSchema, LabelLanguage, Preset
from squarepot_server.labels.text import Run, Style

NAME = "name"


def apply_case(value: str, case: str) -> str:
    match case:
        case "lower":
            return value.lower()
        case "upper":
            return value.upper()
        case "title":
            return " ".join(word[:1].upper() + word[1:].lower() for word in value.split(" "))
        case _:
            return value


def styled(value: str, display: Display) -> list[Run]:
    """One field value with its prefix, case, italics and quotes (schema/fields.yaml)."""
    text = apply_case(value.strip(), display.case)
    if display.quote:
        text = f"\u2018{text}\u2019"  # curly single quotes
    runs = [Run(f"{display.prefix} ")] if display.prefix else []
    runs.append(Run(text, Style.ITALIC if display.italic else Style.REGULAR))
    return runs


def caption(schema: FieldSchema, preset: Preset, fields: dict[str, str]) -> list[list[Run]]:
    """One item per non-empty preset entry, in preset order.

    The first item is set in bold unless it has italics, as a name does: on
    the default preset, that is the field number.

    Computed fields other than the name (such as age) change over time and are
    not printed.
    """
    displays = {definition.key: definition.display for definition in schema.fields}
    computed = {field.key: field.from_ for field in schema.computed}
    items: list[list[Run]] = []
    for key in preset.fields:
        if key == NAME:
            runs: list[Run] = []
            for part in computed.get(NAME, []):
                if fields.get(part, "").strip():
                    runs.extend([Run(" ")] if runs else [])
                    runs.extend(styled(fields[part], displays[part]))
        elif key in displays and fields.get(key, "").strip():
            runs = styled(fields[key], displays[key])
        else:
            continue
        if runs:
            items.append(runs)
    if items and all(run.style == Style.REGULAR for run in items[0]):
        items[0] = [
            Run(run.text, Style.BOLD) if run.style == Style.REGULAR else run for run in items[0]
        ]
    return items


def burial_text(
    schema: FieldSchema, preset: Preset, fields: dict[str, str], language: LabelLanguage
) -> list[list[Run]]:
    """One item per non-empty preset field: its label in bold, then its value.

    Computed fields are left out: the name is on the visible part, and age changes over time.
    """
    definitions = {definition.key: definition for definition in schema.fields}
    items: list[list[Run]] = []
    for key in preset.fields:
        definition = definitions.get(key)
        if definition is None or not fields.get(key, "").strip():
            continue
        label = getattr(definition.label, language.value)
        items.append([Run(f"{label}: ", Style.BOLD), *styled(fields[key], definition.display)])
    return items
