# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuilding the photo index and the sightings from the photo storage."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from squarepot_server.config import PhotoStoreKind, Settings
from squarepot_server.db import MainPhoto, PhotoRow, SightingRow
from squarepot_server.rebuild import rebuild
from tests.conftest import runtime
from tests.test_photo_images import photo

FIRST = "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"
SECOND = "0b7e6a3c-1111-4222-8333-944455566677"


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={"photos": PhotoStoreKind.DISK, "photos_dir": tmp_path / "photos"}
    )


def test_a_lost_index_is_rebuilt_from_the_storage(client: TestClient, tmp_path: Path) -> None:
    upload = client.put(
        f"/api/v1/photos/{FIRST}", params={"tag": "004217", "comment": "цветёт"}, content=photo()
    )
    assert upload.status_code == 201
    sighting = {"id": SECOND, "tag": "004217", "seen_at": "2026-10-26T10:00:00Z", "kind": "seen"}
    client.post("/api/v1/sightings", json={"sightings": [sighting]})
    (tmp_path / "photos/photos/004217/stray.json").write_text("not json")
    before = client.get("/api/v1/plants/by-tag/004217/photos").json()
    seen = client.get("/api/v1/plants/by-tag/004217").json()["plants"][0]["last_seen"]
    state = runtime(client)
    with state.sessions.begin() as session:
        for table in (MainPhoto, PhotoRow, SightingRow):
            session.execute(delete(table))
    assert client.get("/api/v1/plants/by-tag/004217/photos").json() == []
    cursor = client.get("/api/v1/sync").json()["cursor"]

    assert state.photos is not None
    photos, sightings = rebuild(state.sessions, state.photos.storage)
    assert (photos.added, photos.present, photos.unreadable) == (1, 0, 1)
    assert (sightings.added, sightings.present, sightings.unreadable) == (1, 0, 0)

    after = client.get("/api/v1/plants/by-tag/004217/photos").json()
    drop = ("url", "thumbnail_url", "urls_expire_at")
    assert [{k: v for k, v in p.items() if k not in drop} for p in after] == [
        {k: v for k, v in p.items() if k not in drop} for p in before
    ]
    assert client.get("/api/v1/plants/by-tag/004217").json()["plants"][0]["last_seen"] == seen
    changed = client.get("/api/v1/sync", params={"cursor": cursor}).json()["plants"]
    assert [plant["tag"] for plant in changed] == ["004217"]

    again = rebuild(state.sessions, state.photos.storage)
    assert [(c.added, c.present) for c in again] == [(0, 1), (0, 1)]
