# SPDX-License-Identifier: Apache-2.0
"""Check the cross-references in schema/fields.yaml.

JSON Schema validates the shape of the file; this script checks what JSON
Schema cannot: that keys are unique, that aliases do not collide with keys,
and that computed fields and presets refer only to keys that exist.

Usage:
    python schema/check_fields.py [PATH]   check a schema file (default: schema/fields.yaml)
    python schema/check_fields.py --self-test
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).with_name("fields.yaml")


def check(schema: dict[str, Any]) -> list[str]:
    """Return a list of problems; empty when the schema is consistent."""
    errors: list[str] = []
    seen: dict[str, str] = {}

    def claim(name: str, owner: str) -> None:
        if name in seen:
            errors.append(f"{owner}: '{name}' is already used by {seen[name]}")
        else:
            seen[name] = owner

    fields: list[dict[str, Any]] = schema.get("fields", [])
    computed: list[dict[str, Any]] = schema.get("computed", [])
    presets: list[dict[str, Any]] = schema.get("presets", [])

    for field in fields:
        claim(field["key"], f"field '{field['key']}'")
    for item in computed:
        claim(item["key"], f"computed field '{item['key']}'")
    for field in fields:
        for alias in field.get("aliases", []):
            claim(alias, f"alias of field '{field['key']}'")

    field_keys = {field["key"] for field in fields}
    for item in computed:
        for ref in item["from"]:
            if ref not in field_keys:
                errors.append(f"computed field '{item['key']}': unknown field '{ref}'")

    displayable = field_keys | {item["key"] for item in computed}
    preset_keys: set[str] = set()
    for preset in presets:
        if preset["key"] in preset_keys:
            errors.append(f"preset '{preset['key']}' is defined twice")
        preset_keys.add(preset["key"])
        for ref in preset["fields"]:
            if ref not in displayable:
                errors.append(f"preset '{preset['key']}': unknown field '{ref}'")

    return errors


def self_test(schema: dict[str, Any]) -> list[str]:
    """Break a valid schema in each way check() must catch; return the ways it missed."""
    if check(schema):
        return ["the schema under test is not valid to begin with"]

    def set_preset_ref(s: dict[str, Any]) -> None:
        s["presets"][0]["fields"].append("nmae")

    def set_computed_ref(s: dict[str, Any]) -> None:
        s["computed"][0]["from"].append("genuss")

    def set_duplicate_key(s: dict[str, Any]) -> None:
        s["fields"].append(copy.deepcopy(s["fields"][0]))

    def set_alias_collision(s: dict[str, Any]) -> None:
        s["fields"][0].setdefault("aliases", []).append(s["fields"][1]["key"])

    def set_computed_collision(s: dict[str, Any]) -> None:
        s["computed"][0]["key"] = s["fields"][0]["key"]

    def set_duplicate_preset(s: dict[str, Any]) -> None:
        s["presets"].append(copy.deepcopy(s["presets"][0]))

    breakages = [
        set_preset_ref,
        set_computed_ref,
        set_duplicate_key,
        set_alias_collision,
        set_computed_collision,
        set_duplicate_preset,
    ]
    missed: list[str] = []
    for breakage in breakages:
        broken = copy.deepcopy(schema)
        breakage(broken)
        if not check(broken):
            missed.append(breakage.__name__)
    return missed


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        schema = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
        missed = self_test(schema)
        for name in missed:
            print(f"self-test: {name} was not detected", file=sys.stderr)
        return 1 if missed else 0

    status = 0
    for path in [Path(arg) for arg in argv] or [DEFAULT_PATH]:
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        for error in check(schema):
            print(f"{path}: {error}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
