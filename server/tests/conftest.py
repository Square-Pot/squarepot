# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fixtures: a server on a temporary SQLite database, reading an in-memory fake store."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from squarepot_server.app import create_app
from squarepot_server.config import CollectionConfig, Settings
from squarepot_server.fields import Cell
from squarepot_server.runtime import Runtime
from squarepot_server.store import StoreError

TOKEN = "test-token-0123456789"
HEADER: list[Cell] = ["tag", "genus", "species", "field_number"]


@dataclass
class FakeStore:
    """Tabs by collection id. Bump `versions` (or use `put`) when a tab changes."""

    tabs: dict[str, list[list[Cell]]] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)
    failing: set[str] = field(default_factory=set)
    buggy: set[str] = field(default_factory=set)
    reads: int = 0

    def put(self, collection_id: str, values: list[list[Cell]]) -> None:
        self.tabs[collection_id] = values
        self.versions[collection_id] = self.versions.get(collection_id, 0) + 1

    def version(self, collection: CollectionConfig) -> str:
        if collection.id in self.failing:
            raise StoreError("Google is unreachable: test")
        return str(self.versions[collection.id])

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        self.reads += 1
        if collection.id in self.buggy:
            raise RuntimeError("a bug")
        return self.tabs[collection.id]


def collection(collection_id: str) -> CollectionConfig:
    return CollectionConfig(id=collection_id, name=collection_id.title(), spreadsheet_id="sheet")


@pytest.fixture
def store() -> FakeStore:
    fake = FakeStore()
    fake.put(
        "main",
        [
            HEADER,
            [4217, "Lithops", "lesliei", "SB 1234"],
            ["004218", "Conophytum", "bilobum"],
            [None, "Lithops", "aucampiae"],
        ],
    )
    return fake


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_token=SecretStr(TOKEN),
        database_url=f"sqlite:///{tmp_path / 'data' / 'squarepot.db'}",
        collections=[collection("main")],
        sync_interval_seconds=0,
    )


@pytest.fixture
def client(settings: Settings, store: FakeStore) -> Iterator[TestClient]:
    with TestClient(create_app(settings, store), headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        runtime(c).syncer.run_once()
        yield c


def runtime(client: TestClient) -> Runtime:
    app = client.app
    assert hasattr(app, "state")
    result: Runtime = app.state.runtime
    return result
