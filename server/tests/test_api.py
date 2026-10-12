# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from squarepot_server import __version__
from squarepot_server.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


@pytest.mark.parametrize("tag", ["42a", "1234567", "-1", "0", "000000"])
def test_invalid_tag_is_rejected_with_the_error_body(client: TestClient, tag: str) -> None:
    response = client.get(f"/api/v1/plants/by-tag/{tag}")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_unknown_path_uses_the_error_body(client: TestClient) -> None:
    response = client.get("/api/v1/nowhere")
    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not Found"}


def test_large_responses_are_gzipped(client: TestClient) -> None:
    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"


def test_unexpected_error_uses_the_error_body() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "message": "Internal server error."}
