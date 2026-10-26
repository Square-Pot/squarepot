# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from squarepot_server.app import create_app
from squarepot_server.config import PhotoStoreKind, Settings
from squarepot_server.web import origin, security_headers
from tests.conftest import TOKEN, FakeStore

INDEX = '<!doctype html><div id="root"></div>'


@pytest.fixture
def web_dir(tmp_path: Path) -> Path:
    root = tmp_path / "web"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "favicon.svg").write_text("<svg/>")
    (root / "assets" / "app-1a2b3c.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("not served")
    return root


@pytest.fixture
def web(settings: Settings, store: FakeStore, web_dir: Path) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"web_dir": web_dir}), store)
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/c/main", "/c/main/p/main:004217?genus=Lithops"])
def test_app_pages_get_the_index(web: TestClient, path: str) -> None:
    response = web.get(path)
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["cache-control"] == "no-cache"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"


def test_hashed_assets_are_cached_for_good(web: TestClient) -> None:
    response = web.get("/assets/app-1a2b3c.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert web.get("/favicon.svg").headers["cache-control"] == "no-cache"


def test_images_come_only_from_the_page_without_a_bucket(web: TestClient) -> None:
    policy = web.get("/").headers["content-security-policy"]
    assert "img-src 'self' blob: data:;" in policy


def test_images_may_come_from_the_photo_bucket(settings: Settings, tmp_path: Path) -> None:
    s3 = settings.model_copy(
        update={
            "photos": PhotoStoreKind.S3,
            "s3_endpoint": "https://storage.yandexcloud.net/",
            "s3_bucket": "square-pot",
            "s3_key_file": tmp_path / "key",
        }
    )
    policy = security_headers(s3)["Content-Security-Policy"]
    assert "img-src 'self' blob: data: https://storage.yandexcloud.net;" in policy
    assert "default-src 'self';" in policy


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://storage.yandexcloud.net/", "https://storage.yandexcloud.net"),
        ("https://user:secret@s3.example.org:9000/x", "https://s3.example.org:9000"),
        ("http://[::1]:9000", "http://[::1]:9000"),
    ],
)
def test_the_bucket_origin_has_no_credentials(endpoint: str, expected: str) -> None:
    assert origin(endpoint) == expected


@pytest.mark.parametrize(
    "path", ["/assets/gone.js", "/robots.txt", "/%2e%2e/secret.txt", "/%00", "/assets/%00.js"]
)
def test_a_missing_file_is_not_the_index(web: TestClient, path: str) -> None:
    assert web.get(path).status_code == 404


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unknown_api_paths_stay_api_errors(web: TestClient, method: str) -> None:
    response = web.request(method, "/api/v1/nowhere")
    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not Found"}


def test_the_api_still_answers(web: TestClient) -> None:
    response = web.get("/api/v1/collections", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


def test_only_reads_of_pages(web: TestClient) -> None:
    assert web.post("/c/main").status_code == 405


def test_a_websocket_is_closed(web: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), web.websocket_connect("/c/main"):
        pass


def test_without_a_build_only_the_api_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
