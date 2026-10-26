# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sightings and the inventory filters (ADR 0008)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from squarepot_server.config import PhotoStoreKind, Settings
from squarepot_server.fields import Cell
from tests.conftest import FakeStore
from tests.test_photo_images import photo

FIRST = "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"
SECOND = "0b7e6a3c-1111-4222-8333-944455566677"
THIRD = "2c3d4e5f-6a7b-4c8d-9e0f-a1b2c3d4e5f6"
HEADER: list[Cell] = ["tag", "genus", "species", "status"]


@pytest.fixture
def store() -> FakeStore:
    fake = FakeStore()
    fake.put(
        "main",
        [
            HEADER,
            ["004217", "Lithops", "lesliei"],
            ["004218", "Conophytum", "bilobum"],
            ["004219", "Lithops", "dorotheae", "dead"],
            [None, "Lithops", "aucampiae"],
        ],
    )
    return fake


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={"photos": PhotoStoreKind.DISK, "photos_dir": tmp_path / "photos"}
    )


def sighting(sighting_id: str, tag: str, seen_at: str, kind: str = "seen") -> dict[str, str]:
    return {"id": sighting_id, "tag": tag, "seen_at": seen_at, "kind": kind}


def send(client: TestClient, *sightings: dict[str, str]) -> list[str]:
    response = client.post("/api/v1/sightings", json={"sightings": list(sightings)})
    assert response.status_code == 200
    return [result["result"] for result in response.json()]


def last_seen(client: TestClient, tag: str) -> Any:
    return client.get(f"/api/v1/plants/by-tag/{tag}").json()["plants"][0]["last_seen"]


def test_sightings_are_recorded_once(client: TestClient, tmp_path: Path) -> None:
    first = sighting(FIRST, "004217", "2026-10-26T10:00:00+03:00")
    assert send(client, first, sighting(SECOND, "009999", "2026-10-26T10:00:00Z")) == [
        "recorded",
        "unknown_number",
    ]
    assert send(client, first) == ["already_recorded"]
    assert last_seen(client, "004217").startswith("2026-10-26T07:00:00")
    assert last_seen(client, "004218") is None
    [copy] = (tmp_path / "photos/sightings/004217").iterdir()
    assert copy.name == f"2026-10-26T07-00-00Z_{FIRST}.json"


def test_the_same_id_twice_in_one_batch_is_one_sighting(client: TestClient) -> None:
    again = sighting(FIRST, "004217", "2026-10-26T10:00:00Z")
    assert send(client, again, again) == ["recorded", "already_recorded"]


def test_a_time_in_the_future_counts_as_the_time_received(client: TestClient) -> None:
    later = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    send(client, sighting(FIRST, "004217", later))
    seen = datetime.fromisoformat(last_seen(client, "004217"))
    assert seen <= datetime.now(UTC)


def test_last_seen_is_the_later_of_a_sighting_and_a_photo(client: TestClient) -> None:
    # The photo was taken on 2025-06-01 at 07:00 UTC.
    client.put(f"/api/v1/photos/{THIRD}", params={"tag": "004217"}, content=photo())
    assert last_seen(client, "004217").startswith("2025-06-01T07:00:00")
    send(client, sighting(FIRST, "004217", "2025-01-01T00:00:00Z"))
    assert last_seen(client, "004217").startswith("2025-06-01T07:00:00")
    send(client, sighting(SECOND, "004217", "2026-01-01T00:00:00Z", "status"))
    assert last_seen(client, "004217").startswith("2026-01-01T00:00:00")


def test_a_sighting_sends_the_plant_again_in_the_sync(client: TestClient) -> None:
    cursor = client.get("/api/v1/sync").json()["cursor"]
    send(client, sighting(FIRST, "004218", "2026-10-26T10:00:00Z"))
    plants = client.get("/api/v1/sync", params={"cursor": cursor}).json()["plants"]
    assert [plant["tag"] for plant in plants] == ["004218"]


def test_a_batch_holds_at_most_500(client: TestClient) -> None:
    many = [sighting(FIRST, "004217", "2026-10-26T10:00:00Z")] * 501
    assert client.post("/api/v1/sightings", json={"sightings": many}).status_code == 422


def listed(client: TestClient, **query: str) -> list[str | None]:
    response = client.get("/api/v1/collections/main/plants", params=query)
    assert response.status_code == 200
    return [plant["tag"] for plant in response.json()]


def test_the_inventory_filters(client: TestClient) -> None:
    client.put(f"/api/v1/photos/{THIRD}", params={"tag": "004218"}, content=photo())
    send(client, sighting(FIRST, "004217", "2026-10-26T10:00:00Z"))
    assert listed(client) == ["004217", "004218", None]
    assert listed(client, former="true") == ["004217", "004218", "004219", None]
    assert listed(client, seen_before="2026-10-01") == ["004218", None]
    assert listed(client, seen_before="2025-01-01") == [None]
    assert listed(client, photo_before="2026-01-01") == ["004217", "004218", None]
    assert listed(client, photo_before="2025-01-01") == ["004217", None]
    assert listed(client, has_photo="true") == ["004218"]
    assert listed(client, has_photo="false", former="true") == ["004217", "004219", None]


def test_an_unknown_collection_has_no_plants(client: TestClient) -> None:
    assert client.get("/api/v1/collections/nope/plants").status_code == 404
