# SPDX-License-Identifier: AGPL-3.0-or-later
"""Batch photo imports: staging, the worker's decoding, filing and the review queue."""

from __future__ import annotations

import io
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker

from squarepot_server.config import PhotoStoreKind, Settings
from squarepot_server.db import make_engine
from squarepot_server.importer import Importer
from squarepot_server.labels.datamatrix import encode
from squarepot_server.photos.codes import read_numbers
from squarepot_server.photos.imports import Imports, ImportState
from squarepot_server.runtime import Runtime
from tests.conftest import runtime

FIRST = "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"
SECOND = "0b7e6a3c-1111-4222-8333-944455566677"


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={"photos": PhotoStoreKind.DISK, "photos_dir": tmp_path / "photos"}
    )


def labelled(*tags: str, size: tuple[int, int] = (1200, 900), module: int = 12) -> bytes:
    """A PNG photo with a Data Matrix of each number, side by side."""
    image = Image.new("L", size, 200)
    for index, tag in enumerate(tags):
        matrix = encode(tag)
        side = (len(matrix) + 4) * module
        code = Image.new("L", (side, side), 255)
        for row, line in enumerate(matrix):
            for column, dark in enumerate(line):
                if dark:
                    x, y = (column + 2) * module, (row + 2) * module
                    code.paste(0, (x, y, x + module, y + module))
        image.paste(code, (40 + index * (side + 60), 40))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def stage(client: TestClient, import_id: str, data: bytes, **query: str) -> Any:
    response = client.put(f"/api/v1/imports/{import_id}", params=query, content=data)
    assert response.status_code == 201
    return response.json()


def work(client: TestClient) -> Runtime:
    """Let the worker decode everything queued, then the server file it."""
    state = runtime(client)
    assert state.photos is not None and state.imports is not None
    importer = Importer(state.sessions, state.photos.storage)
    while importer.run_once():
        pass
    state.imports.file_decoded()
    return state


def imported(client: TestClient, import_id: str) -> Any:
    return client.get(f"/api/v1/imports/{import_id}").json()


def test_a_photo_with_one_known_number_is_filed(client: TestClient, tmp_path: Path) -> None:
    body = stage(client, FIRST, labelled("004217"), file_time="2025-05-01T09:00:00Z")
    assert (body["state"], body["numbers"], body["tag"]) == ("queued", [], None)
    assert client.get(body["url"], headers={"Authorization": ""}).status_code == 200
    work(client)
    body = imported(client, FIRST)
    assert (body["state"], body["numbers"], body["tag"]) == ("filed", ["004217"], "004217")
    assert body["url"] is None
    [photo] = client.get("/api/v1/plants/by-tag/004217/photos").json()
    assert photo["id"] == FIRST
    assert photo["taken_at"].startswith("2025-05-01T09:00:00")
    assert not list((tmp_path / "photos/staging").iterdir())
    assert stage(client, FIRST, labelled("004218"))["state"] == "filed"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (labelled(), "no_code"),
        (labelled("009999"), "unknown_number"),
        (labelled("004217", "004218"), "several_numbers"),
        (b"not a photo", "unreadable"),
    ],
)
def test_the_others_wait_for_the_owner(client: TestClient, data: bytes, reason: str) -> None:
    stage(client, FIRST, data)
    work(client)
    [waiting] = client.get("/api/v1/imports", params={"state": "review"}).json()
    assert (waiting["id"], waiting["reason"]) == (FIRST, reason)
    assert client.get("/api/v1/plants/by-tag/004217/photos").json() == []


def test_the_owner_files_or_discards(client: TestClient) -> None:
    stage(client, FIRST, labelled("004217", "004218"))
    stage(client, SECOND, labelled())
    work(client)
    response = client.post(f"/api/v1/imports/{FIRST}/file", json={"tag": "004218"})
    assert (response.json()["state"], response.json()["tag"]) == ("filed", "004218")
    assert client.post(f"/api/v1/imports/{SECOND}/discard").json()["state"] == "discarded"
    assert client.post(f"/api/v1/imports/{SECOND}/file", json={"tag": "004217"}).status_code == 409
    assert client.post(f"/api/v1/imports/{FIRST}/discard").status_code == 409
    assert client.get("/api/v1/imports").json() == []
    unknown = client.post(f"/api/v1/imports/{SECOND}x/discard")
    assert unknown.status_code == 422


def test_the_owner_wins_over_the_worker(client: TestClient) -> None:
    stage(client, FIRST, labelled("004217"))
    state = runtime(client)
    assert state.photos is not None
    importer = Importer(state.sessions, state.photos.storage)
    row = importer.claim()
    assert row is not None
    client.post(f"/api/v1/imports/{FIRST}/file", json={"tag": "004218"})
    assert not importer.move(row.id, ImportState.DECODING, ImportState.DECODED)
    assert imported(client, FIRST)["tag"] == "004218"


def test_two_processes_never_claim_the_same_photo(client: TestClient, settings: Settings) -> None:
    # Each worker has its own engine on the database file, as a second process would.
    ids = [f"6f1c2b9e-3d4a-4e8f-9b7c-{index:012d}" for index in range(40)]
    for import_id in ids:
        stage(client, import_id, b"x")
    state = runtime(client)
    assert state.photos is not None
    storage = state.photos.storage
    claimed: list[list[str]] = [[], []]
    engines = [make_engine(settings.database_url) for _ in claimed]

    def claim_all(found: list[str], engine: Any) -> None:
        importer = Importer(sessionmaker(engine, expire_on_commit=False), storage)
        while (row := importer.claim()) is not None:
            found.append(row.id)

    threads = [
        threading.Thread(target=claim_all, args=(found, engine))
        for found, engine in zip(claimed, engines, strict=True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for engine in engines:
        engine.dispose()
    assert sorted(claimed[0] + claimed[1]) == ids


def test_a_stopped_worker_leaves_nothing_half_done(client: TestClient) -> None:
    stage(client, FIRST, labelled("004217"))
    state = runtime(client)
    assert state.photos is not None
    importer = Importer(state.sessions, state.photos.storage)
    assert importer.claim() is not None
    assert importer.claim() is None
    importer.recover()
    assert imported(client, FIRST)["state"] == "queued"


def test_staged_files_go_after_30_days(client: TestClient, tmp_path: Path) -> None:
    stage(client, FIRST, labelled())
    imports = runtime(client).imports
    assert isinstance(imports, Imports)
    assert imports.purge() == 0
    imports.clock = lambda: datetime.now(UTC) + timedelta(days=31)
    assert imports.purge() == 1
    assert (imported(client, FIRST)["state"], imported(client, FIRST)["reason"]) == (
        "discarded",
        "expired",
    )
    assert not list((tmp_path / "photos/staging").iterdir())


def test_a_small_code_is_read_on_the_full_image() -> None:
    # 3 px modules: too small once the photo is shrunk to 2000 px for the first pass.
    data = labelled("004217", size=(4000, 3000), module=3)
    assert read_numbers(data) == ["004217"]
