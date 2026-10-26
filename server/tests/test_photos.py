# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plant photos through the API, kept in a folder on the server (ADR 0007)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from squarepot_server.app import create_app
from squarepot_server.config import PhotoStoreKind, Settings
from tests.conftest import TOKEN, FakeStore, runtime
from tests.test_photo_images import photo

FIRST = "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"
SECOND = "0b7e6a3c-1111-4222-8333-944455566677"


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={"photos": PhotoStoreKind.DISK, "photos_dir": tmp_path / "photos"}
    )


def upload(client: TestClient, photo_id: str, tag: str = "004217", **query: str) -> Any:
    return client.put(
        f"/api/v1/photos/{photo_id}",
        params={"tag": tag, **query},
        content=photo(),
        headers={"Content-Type": "image/jpeg"},
    )


def photos(client: TestClient, tag: str = "004217", **query: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/v1/plants/by-tag/{tag}/photos", params=query)
    assert response.status_code == 200
    result: list[dict[str, Any]] = response.json()
    return result


def test_a_photo_is_uploaded_and_served_at_its_address(client: TestClient, tmp_path: Path) -> None:
    response = upload(client, FIRST)
    assert response.status_code == 201
    body = response.json()
    assert (body["id"], body["tag"], body["main"], body["comment"]) == (FIRST, "004217", True, "")
    assert body["taken_from"] == "camera"
    assert body["taken_at"].startswith("2025-06-01T07:00:00")
    assert (body["width"], body["height"]) == (300, 400)
    files = sorted(path.name for path in (tmp_path / "photos/photos/004217").iterdir())
    assert files == [
        f"2025-06-01T07-00-00Z_{FIRST}.jpg",
        f"2025-06-01T07-00-00Z_{FIRST}.json",
        f"2025-06-01T07-00-00Z_{FIRST}.thumb.jpg",
    ]
    image = client.get(body["url"], headers={"Authorization": ""})
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(image.content)) as opened:
        assert opened.size == (300, 400)
    assert client.get(body["thumbnail_url"], headers={"Authorization": ""}).status_code == 200
    assert client.get(body["url"].replace("signature=", "signature=0")).status_code == 404


def test_the_same_upload_again_changes_nothing(client: TestClient) -> None:
    first = upload(client, FIRST).json()
    again = upload(client, FIRST)
    assert again.status_code == 201
    assert again.json()["uploaded_at"] == first["uploaded_at"]
    assert len(photos(client)) == 1


def test_an_id_is_one_photo_of_one_plant(client: TestClient) -> None:
    upload(client, FIRST)
    response = upload(client, FIRST, tag="004218")
    assert response.status_code == 422
    assert "another plant" in response.json()["message"]


def test_only_a_plant_with_a_number_can_have_photos(client: TestClient) -> None:
    response = upload(client, FIRST, tag="009999")
    assert response.status_code == 404
    assert client.get("/api/v1/plants/by-tag/009999/photos").status_code == 404


def test_a_photo_must_be_an_image(client: TestClient) -> None:
    response = client.put(
        f"/api/v1/photos/{FIRST}", params={"tag": "004217"}, content=b"not an image"
    )
    assert response.status_code == 422
    assert response.json()["message"] == "not a JPEG, PNG or WebP image."


def test_a_photo_over_30_mb_is_refused(client: TestClient) -> None:
    response = client.put(
        f"/api/v1/photos/{FIRST}", params={"tag": "004217"}, content=b"\0" * (30 * 1024 * 1024 + 1)
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"


def test_photos_are_in_the_order_taken_and_the_newest_is_main(client: TestClient) -> None:
    upload(client, FIRST)
    later = client.put(
        f"/api/v1/photos/{SECOND}",
        params={"tag": "004217", "taken_at": "2026-01-01T12:00:00+03:00"},
        content=photo(taken=None, offset=None),
    )
    assert later.json()["taken_from"] == "client"
    listed = photos(client)
    assert [p["id"] for p in listed] == [FIRST, SECOND]
    assert [p["main"] for p in listed] == [False, True]


def test_the_owner_chooses_the_main_photo(client: TestClient) -> None:
    upload(client, FIRST)
    client.put(f"/api/v1/photos/{SECOND}", params={"tag": "004217"}, content=photo(taken=None))
    url = "/api/v1/plants/by-tag/004217/main-photo"
    assert client.put(url, json={"photo_id": FIRST}).status_code == 204
    assert [p["main"] for p in photos(client)] == [True, False]
    assert client.put(url, json={"photo_id": None}).status_code == 204
    assert [p["main"] for p in photos(client)] == [False, True]
    assert client.put(url.replace("004217", "004218"), json={"photo_id": FIRST}).status_code == 404


def test_a_comment_and_the_time_taken_can_be_changed(client: TestClient, tmp_path: Path) -> None:
    upload(client, FIRST)
    body = {"comment": " первый цветок ", "taken_at": "2025-05-01T09:00:00+00:00"}
    response = client.patch(f"/api/v1/photos/{FIRST}", json=body)
    assert response.status_code == 200
    assert response.json()["comment"] == "первый цветок"
    assert response.json()["taken_from"] == "owner"
    [meta] = (tmp_path / "photos/photos/004217").glob("*.json")
    assert "первый цветок" in meta.read_text(encoding="utf-8")
    assert client.patch(f"/api/v1/photos/{SECOND}", json={"comment": "x"}).status_code == 404


def test_a_deleted_photo_can_be_restored(client: TestClient) -> None:
    upload(client, FIRST)
    deleted = client.delete(f"/api/v1/photos/{FIRST}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None
    assert photos(client) == []
    assert [p["id"] for p in photos(client, deleted="true")] == [FIRST]
    restored = client.post(f"/api/v1/photos/{FIRST}/restore")
    assert restored.json()["deleted_at"] is None
    assert [p["id"] for p in photos(client)] == [FIRST]


def test_a_photo_deleted_30_days_ago_is_purged(client: TestClient, tmp_path: Path) -> None:
    upload(client, FIRST)
    client.delete(f"/api/v1/photos/{FIRST}")
    service = runtime(client).photos
    assert service is not None
    assert service.purge() == 0
    service.clock = lambda: datetime.now(UTC) + timedelta(days=31)
    assert service.purge() == 1
    assert list((tmp_path / "photos/photos/004217").iterdir()) == []
    assert photos(client, deleted="true") == []


def test_photos_need_a_storage(settings: Settings, store: FakeStore) -> None:
    off = settings.model_copy(update={"photos": PhotoStoreKind.NONE})
    with TestClient(create_app(off, store), headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        response = c.get("/api/v1/plants/by-tag/004217/photos")
    assert response.status_code == 503
    assert response.json()["message"] == "Photos are not set up on this server."
