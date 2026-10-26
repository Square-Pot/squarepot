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
from squarepot_server.store import CellWrite, StoreError, StoreRefused

TOKEN = "test-token-0123456789"
HEADER: list[Cell] = ["tag", "genus", "species", "field_number"]


@dataclass
class FakeStore:
    """Tabs by collection id. Bump `versions` (or use `put`) when a tab changes.

    It can be written to, as the service account's store can: written values
    land in the tab as text, and `writes` records each write.
    """

    tabs: dict[str, list[list[Cell]]] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)
    failing: set[str] = field(default_factory=set)
    buggy: set[str] = field(default_factory=set)
    reads: int = 0
    writes: list[tuple[int, list[CellWrite]]] = field(default_factory=list)
    # Calls of write_rows, each of which writes many rows at once.
    batches: int = 0
    # Collections shared with the service account as Viewer, and those whose sharing
    # was changed to Viewer since the last sync.
    read_only: set[str] = field(default_factory=set)
    refusing: set[str] = field(default_factory=set)

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

    def can_edit(self, collection: CollectionConfig) -> bool:
        return collection.id not in self.read_only

    def write(self, collection: CollectionConfig, row: int, cells: list[CellWrite]) -> None:
        if collection.id in self.failing:
            raise StoreError("Google is unreachable: test")
        if collection.id in self.refusing:
            raise StoreRefused("Google answered 403: The caller does not have permission")
        self.writes.append((row, cells))
        values = self.tabs[collection.id]
        while len(values) < row:
            values.append([])
        for cell in cells:
            line = values[row - 1]
            line.extend([None] * (cell.column + 1 - len(line)))
            line[cell.column] = None if cell.value is None else str(cell.value)
        self.versions[collection.id] += 1

    def write_rows(self, collection: CollectionConfig, rows: dict[int, list[CellWrite]]) -> None:
        self.batches += 1
        for row, cells in rows.items():
            self.write(collection, row, cells)

    def append(self, collection: CollectionConfig, cells: list[CellWrite]) -> int:
        row = len(self.tabs[collection.id]) + 1
        self.write(collection, row, cells)
        return row


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
