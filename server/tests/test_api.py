# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from squarepot_server import __version__, openapi
from squarepot_server.app import create_app
from squarepot_server.config import Settings
from squarepot_server.db import CollectionRow
from squarepot_server.fields import load_schema
from tests.conftest import HEADER, TOKEN, FakeStore, collection, runtime

PROTECTED = [
    path.replace("{tag}", "004217")
    for path, operations in openapi.document()["paths"].items()
    if any(operation.get("security") for operation in operations.values())
]


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Authorization": ""})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_every_route_but_health_is_protected() -> None:
    assert sorted(PROTECTED) == [
        "/api/v1/collections",
        "/api/v1/plants/by-tag/004217",
        "/api/v1/schema",
        "/api/v1/sync",
    ]


@pytest.mark.parametrize("path", PROTECTED)
@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token", "Basic dGVzdA=="])
def test_a_missing_or_wrong_token_is_refused(
    client: TestClient, path: str, authorization: str | None
) -> None:
    headers = {"Authorization": authorization or ""}
    response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "unauthorized"


def test_lookup_by_tag(client: TestClient) -> None:
    response = client.get("/api/v1/plants/by-tag/4217")
    assert response.status_code == 200
    body = response.json()
    assert body["tag"] == "004217"
    [plant] = body["plants"]
    assert plant == {
        "id": "main:004217",
        "collection_id": "main",
        "tag": "004217",
        "row": 2,
        "fields": {"genus": "Lithops", "species": "lesliei", "field_number": "SB 1234"},
    }


def test_lookup_of_an_unknown_tag(client: TestClient) -> None:
    response = client.get("/api/v1/plants/by-tag/999999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize("tag", ["42a", "1234567", "-1", "0", "000000"])
def test_invalid_tag_is_rejected_with_the_error_body(client: TestClient, tag: str) -> None:
    response = client.get(f"/api/v1/plants/by-tag/{tag}")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_a_colliding_number_finds_every_plant(settings: Settings, store: FakeStore) -> None:
    store.put("other", [HEADER, ["4217", "Haworthia", "cooperi"]])
    settings.collections.append(collection("other"))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings, store), headers=headers) as client:
        runtime(client).syncer.run_once()
        plants = client.get("/api/v1/plants/by-tag/004217").json()["plants"]
        with runtime(client).sessions() as session:
            issues = session.get_one(CollectionRow, "other").issues
    assert [plant["collection_id"] for plant in plants] == ["main", "other"]
    assert issues == [
        {"row": 0, "column": "", "message": "number 004217 is also used in collection main"}
    ]


def test_collections(client: TestClient) -> None:
    [main] = client.get("/api/v1/collections").json()
    assert main["id"] == "main"
    assert main["name"] == "Main"
    assert main["plant_count"] == 3
    assert main["error"] is None
    assert main["synced_at"].endswith("Z") or main["synced_at"].endswith("+00:00")


def test_schema_is_fields_yaml(client: TestClient, settings: Settings) -> None:
    body: dict[str, Any] = client.get("/api/v1/schema").json()
    assert body == load_schema(settings.schema_file).model_dump(mode="json")
    assert body["computed"][0]["from"][0] == "genus"


def test_unknown_path_uses_the_error_body(client: TestClient) -> None:
    response = client.get("/api/v1/nowhere")
    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not Found"}


def test_large_responses_are_gzipped(client: TestClient) -> None:
    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"


def test_unexpected_error_uses_the_error_body(settings: Settings, store: FakeStore) -> None:
    app = create_app(settings, store)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "message": "Internal server error."}
