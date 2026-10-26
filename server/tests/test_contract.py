# SPDX-License-Identifier: AGPL-3.0-or-later
"""The committed openapi.json must match the API the code serves."""

from __future__ import annotations

from pathlib import Path

import yaml

from squarepot_server import openapi
from squarepot_server.api.models import FieldSchema

COMMITTED = Path(__file__).resolve().parents[1] / "openapi.json"


def test_committed_openapi_is_up_to_date() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == openapi.render(), (
        "server/openapi.json is out of date; regenerate it with "
        "`uv run python -m squarepot_server.openapi > openapi.json` in server/"
    )


def test_every_error_response_uses_the_error_body() -> None:
    document = openapi.document()
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if not status.startswith(("4", "5")):
                    continue
                expected = "Error"
                edits = ("create_plant", "edit_plant", "set_status")
                if status == "409" and operation["operationId"] in edits:
                    # An edit's conflict also carries the plant as it now is (or null).
                    expected = "EditConflict"
                schema = response["content"]["application/json"]["schema"]
                assert schema == {"$ref": f"#/components/schemas/{expected}"}, (
                    method,
                    path,
                    status,
                )
    conflict = document["components"]["schemas"]["EditConflict"]["properties"]
    assert set(document["components"]["schemas"]["Error"]["properties"]) <= set(conflict)


def test_field_schema_model_reads_fields_yaml() -> None:
    # The models forbid unknown keys, so nothing in the file can be silently dropped.
    path = Path(__file__).resolve().parents[2] / "schema" / "fields.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema = FieldSchema.model_validate(data)
    assert [field.key for field in schema.fields] == [field["key"] for field in data["fields"]]
    assert schema.model_dump(mode="json")["computed"][0]["from"] == data["computed"][0]["from"]
