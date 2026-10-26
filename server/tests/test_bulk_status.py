# SPDX-License-Identifier: AGPL-3.0-or-later
"""One status for many plants at once (ADR 0008), against a writable fake store."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from squarepot_server.fields import Cell
from tests.conftest import FakeStore

HEADER: list[Cell] = ["tag", "genus", "species", "status", "status_date"]


@pytest.fixture
def store() -> FakeStore:
    fake = FakeStore()
    fake.put(
        "main",
        [
            HEADER,
            ["004217", "Lithops", "lesliei"],
            ["004218", "Conophytum", "bilobum"],
            ["004219", "Lithops", "dorotheae", "dead", "2026-01-05"],
            [None, "Lithops", "aucampiae"],
        ],
    )
    return fake


def set_status(client: TestClient, body: dict[str, Any], collection: str = "main") -> Any:
    return client.post(f"/api/v1/collections/{collection}/status", json=body)


def seen(plant_id: str, status: str | None = None) -> dict[str, str | None]:
    return {"id": plant_id, "seen": status}


def statuses(store: FakeStore) -> list[tuple[Cell, ...]]:
    return [tuple((row + [None] * 5)[3:5]) for row in store.tabs["main"][1:]]


def untagged_id(client: TestClient) -> str:
    plants = client.get("/api/v1/sync").json()["plants"]
    [plant] = [plant for plant in plants if plant["tag"] is None]
    return str(plant["id"])


def test_many_plants_are_written_in_one_write(client: TestClient, store: FakeStore) -> None:
    body = {
        "status": "lost",
        "status_date": "2026-10-26",
        "plants": [seen("main:004217"), seen("main:004218"), seen(untagged_id(client))],
    }
    response = set_status(client, body)
    assert response.status_code == 200
    assert [result["result"] for result in response.json()] == ["written"] * 3
    assert store.batches == 1
    assert statuses(store) == [
        ("lost", "2026-10-26"),
        ("lost", "2026-10-26"),
        ("dead", "2026-01-05"),
        ("lost", "2026-10-26"),
    ]
    [main] = client.get("/api/v1/collections").json()
    assert (main["plant_count"], main["former_count"]) == (0, 4)


def test_each_plant_is_answered_on_its_own(client: TestClient, store: FakeStore) -> None:
    body = {
        "status": "sold",
        "plants": [seen("main:004217"), seen("main:004219"), seen("main:999999")],
    }
    response = set_status(client, body)
    assert [(result["id"], result["result"]) for result in response.json()] == [
        ("main:004217", "written"),
        ("main:004219", "changed_in_sheet"),
        ("main:999999", "not_found"),
    ]
    assert statuses(store)[:3] == [("sold", None), (None, None), ("dead", "2026-01-05")]


def test_an_empty_status_clears_it_and_its_date(client: TestClient, store: FakeStore) -> None:
    response = set_status(client, {"status": "", "plants": [seen("main:004219", "dead")]})
    assert [result["result"] for result in response.json()] == ["written"]
    assert statuses(store)[2] == (None, None)


def test_a_row_gone_from_the_sheet_is_not_found(client: TestClient, store: FakeStore) -> None:
    store.put("main", store.tabs["main"][:2])
    response = set_status(client, {"status": "dead", "plants": [seen("main:004218")]})
    assert [result["result"] for result in response.json()] == ["not_found"]
    assert store.batches == 0


@pytest.mark.parametrize(
    "body",
    [
        {"status": "Dead", "plants": [seen("main:004217")]},
        {"status": "eaten", "plants": [seen("main:004217")]},
        {"status": "dead", "plants": [seen("main:004217"), seen("main:004217")]},
        {"status": "dead", "plants": []},
        {"status": "dead", "plants": [seen("main:004217")] * 501},
    ],
)
def test_bad_requests_write_nothing(client: TestClient, store: FakeStore, body: Any) -> None:
    assert set_status(client, body).status_code == 422
    assert store.batches == 0


def test_a_sheet_without_a_status_column_is_refused(client: TestClient, store: FakeStore) -> None:
    store.put("main", [row[:3] for row in store.tabs["main"]])
    response = set_status(client, {"status": "dead", "plants": [seen("main:004217")]})
    assert response.status_code == 422
    assert "'status' column" in response.json()["message"]


def test_a_date_needs_a_status_date_column(client: TestClient, store: FakeStore) -> None:
    store.put("main", [row[:4] for row in store.tabs["main"]])
    body = {"status": "dead", "plants": [seen("main:004217")]}
    assert set_status(client, {**body, "status_date": "2026-10-26"}).status_code == 422
    assert set_status(client, body).status_code == 200
    assert store.tabs["main"][1][3] == "dead"


def test_unknown_collections_and_read_only_sheets(client: TestClient, store: FakeStore) -> None:
    body = {"status": "dead", "plants": [seen("main:004217")]}
    assert set_status(client, body, "nope").status_code == 404
    store.read_only.add("main")
    response = set_status(client, body)
    assert response.status_code == 409
    assert response.json()["code"] == "not_editable"
