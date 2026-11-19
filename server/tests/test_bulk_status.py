# SPDX-License-Identifier: AGPL-3.0-or-later
"""One status for many plants at once (ADR 0009), against a writable fake store."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from squarepot_server.fields import Cell
from tests.conftest import FakeStore

HEADER: list[Cell] = ["tag", "genus", "species", "status", "status_date", "status_comment"]
DAY = datetime.now(UTC).date().isoformat()


@pytest.fixture
def store() -> FakeStore:
    fake = FakeStore()
    fake.put(
        "main",
        [
            HEADER,
            ["004217", "Lithops", "lesliei"],
            ["004218", "Conophytum", "bilobum"],
            ["004219", "Lithops", "dorotheae", "0", "2026-01-05", "frozen"],
            [None, "Lithops", "aucampiae"],
        ],
    )
    return fake


def set_status(client: TestClient, body: dict[str, Any], collection: str = "main") -> Any:
    return client.post(f"/api/v1/collections/{collection}/status", json=body)


def seen(plant_id: str, status: str | None = None) -> dict[str, str | None]:
    return {"id": plant_id, "seen": status}


def statuses(store: FakeStore) -> list[tuple[Cell, ...]]:
    return [tuple((row + [None] * 6)[3:6]) for row in store.tabs["main"][1:]]


def untagged_id(client: TestClient) -> str:
    plants = client.get("/api/v1/sync").json()["plants"]
    [plant] = [plant for plant in plants if plant["tag"] is None]
    return str(plant["id"])


def test_many_plants_are_written_in_one_write(client: TestClient, store: FakeStore) -> None:
    body = {
        "status": "gone",
        "status_date": "2026-10-26",
        "comment": "sold",
        "plants": [seen("main:004217"), seen("main:004218"), seen(untagged_id(client))],
    }
    response = set_status(client, body)
    assert response.status_code == 200
    assert [result["result"] for result in response.json()] == ["written"] * 3
    assert store.batches == 1
    assert statuses(store) == [
        ("0", "2026-10-26", "sold"),
        ("0", "2026-10-26", "sold"),
        ("0", "2026-01-05", "frozen"),
        ("0", "2026-10-26", "sold"),
    ]
    [main] = client.get("/api/v1/collections").json()
    assert (main["plant_count"], main["former_count"]) == (0, 4)
    plant = client.get("/api/v1/plants/by-tag/004217").json()["plants"][0]
    assert plant["status"] == "gone"
    assert plant["status_since"] == "2026-10-26"
    assert plant["status_comment"] == "sold"
    assert "status" not in plant["fields"]


def test_each_plant_is_answered_on_its_own(client: TestClient, store: FakeStore) -> None:
    body = {
        "status": "gone",
        "plants": [seen("main:004217"), seen("main:004219"), seen("main:999999")],
    }
    response = set_status(client, body)
    assert [(result["id"], result["result"]) for result in response.json()] == [
        ("main:004217", "written"),
        ("main:004219", "changed_in_sheet"),
        ("main:999999", "not_found"),
    ]
    assert statuses(store)[:3] == [
        ("0", DAY, None),
        (None, None, None),
        ("0", "2026-01-05", "frozen"),
    ]


def test_the_sheet_wins_and_the_copy_keeps_its_status(client: TestClient, store: FakeStore) -> None:
    response = set_status(client, {"status": "gone", "plants": [seen("main:004219")]})
    assert [result["result"] for result in response.json()] == ["changed_in_sheet"]
    assert store.batches == 0
    plant = client.get("/api/v1/plants/by-tag/004219").json()["plants"][0]
    assert plant["status"] == "gone"
    assert plant["status_since"] == "2026-01-05"
    assert plant["status_comment"] == "frozen"


def test_a_return_writes_1_and_clears_the_comment(client: TestClient, store: FakeStore) -> None:
    response = set_status(
        client,
        {"status": None, "comment": " ", "plants": [seen("main:004219", "gone")]},
    )
    assert [result["result"] for result in response.json()] == ["written"]
    assert statuses(store)[2] == ("1", DAY, None)
    [main] = client.get("/api/v1/collections").json()
    assert (main["plant_count"], main["former_count"]) == (4, 0)
    plant = client.get("/api/v1/plants/by-tag/004219").json()["plants"][0]
    assert plant["status"] is None
    assert plant["status_comment"] is None


def test_a_row_gone_from_the_sheet_is_not_found(client: TestClient, store: FakeStore) -> None:
    store.put("main", store.tabs["main"][:2])
    response = set_status(client, {"status": "gone", "plants": [seen("main:004218")]})
    assert [result["result"] for result in response.json()] == ["not_found"]
    assert store.batches == 0


@pytest.mark.parametrize(
    "body",
    [
        {"status": "dead", "plants": [seen("main:004217")]},
        {"status": "0", "plants": [seen("main:004217")]},
        {"status": "gone", "comment": "x" * 1001, "plants": [seen("main:004217")]},
        {"status": "gone", "plants": [seen("main:004217"), seen("main:004217")]},
        {"status": "gone", "plants": []},
        {"status": "gone", "plants": [seen("main:004217")] * 501},
    ],
)
def test_bad_requests_write_nothing(client: TestClient, store: FakeStore, body: Any) -> None:
    assert set_status(client, body).status_code == 422
    assert store.batches == 0


@pytest.mark.parametrize(
    "header",
    [
        ["tag", "genus", "species"],
        ["tag", "genus", "species", "status"],
        ["tag", "genus", "species", "status", "status_date"],
        ["tag", "genus", "species", "status", "status_comment"],
    ],
)
def test_a_sheet_without_the_status_columns_is_refused(
    client: TestClient, store: FakeStore, header: list[Cell]
) -> None:
    width = len(header)
    store.put("main", [header] + [list(row[:width]) for row in store.tabs["main"][1:]])
    response = set_status(client, {"status": "gone", "plants": [seen("main:004217")]})
    assert response.status_code == 422
    message = response.json()["message"]
    for key in ("status", "status_date", "status_comment"):
        if key not in header:
            assert f"'{key}' column" in message


def test_unknown_collections_and_read_only_sheets(client: TestClient, store: FakeStore) -> None:
    body = {"status": "gone", "plants": [seen("main:004217")]}
    assert set_status(client, body, "nope").status_code == 404
    store.read_only.add("main")
    response = set_status(client, body)
    assert response.status_code == 409
    assert response.json()["code"] == "not_editable"
