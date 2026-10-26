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
    (
        method.upper(),
        path.replace("{tag}", "004217")
        .replace("{plant_id}", "main:004217")
        .replace("{collection_id}", "main")
        .replace("{photo_id}", "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"),
    )
    for path, operations in openapi.document()["paths"].items()
    for method, operation in operations.items()
    if operation.get("security")
]


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Authorization": ""})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_every_route_but_health_is_protected() -> None:
    photo = "/api/v1/photos/6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"
    assert sorted(PROTECTED) == [
        ("DELETE", photo),
        ("GET", "/api/v1/collections"),
        ("GET", "/api/v1/collections/main/plants"),
        ("GET", "/api/v1/labels/templates"),
        ("GET", f"{photo}/image"),
        ("GET", f"{photo}/thumbnail"),
        ("GET", "/api/v1/plants/by-tag/004217"),
        ("GET", "/api/v1/plants/by-tag/004217/photos"),
        ("GET", "/api/v1/schema"),
        ("GET", "/api/v1/sync"),
        ("PATCH", photo),
        ("PATCH", "/api/v1/plants/main:004217"),
        ("POST", "/api/v1/collections/main/plants"),
        ("POST", "/api/v1/collections/main/status"),
        ("POST", "/api/v1/labels"),
        ("POST", f"{photo}/restore"),
        ("POST", "/api/v1/sightings"),
        ("PUT", photo),
        ("PUT", "/api/v1/plants/by-tag/004217/main-photo"),
    ]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token", "Basic dGVzdA=="])
def test_a_missing_or_wrong_token_is_refused(
    client: TestClient, method: str, path: str, authorization: str | None
) -> None:
    headers = {"Authorization": authorization or ""}
    response = client.request(method, path, headers=headers)
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
        "custom": {},
        "invalid": {},
        "status_since": None,
        "last_seen": None,
        "photo_count": 0,
        "last_photo": None,
        "main_photo_id": None,
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
    assert main["sheet_url"] == "https://docs.google.com/spreadsheets/d/sheet/edit"
    assert main["id"] == "main"
    assert main["name"] == "Main"
    assert main["plant_count"] == 3
    assert main["editable"] is True
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
    response = client.get("/api/v1/schema", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_docs_are_off_by_default(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_the_api_docs_can_be_turned_on(settings: Settings, store: FakeStore) -> None:
    with TestClient(create_app(settings.model_copy(update={"api_docs": True}), store)) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").json()["info"]["title"] == "Square-Pot API"


def test_the_api_docs_flag_is_read_before_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQUAREPOT_API_DOCS", "true")
    assert create_app().openapi_url == "/openapi.json"
    monkeypatch.delenv("SQUAREPOT_API_DOCS")
    assert create_app().openapi_url is None


def test_unexpected_error_uses_the_error_body(settings: Settings, store: FakeStore) -> None:
    app = create_app(settings, store)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "message": "Internal server error."}
