# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding and editing plants through the API, against a writable fake store (ADR 0006)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from squarepot_server.app import create_app
from squarepot_server.config import CollectionConfig, Settings
from squarepot_server.db import RegisteredTag
from squarepot_server.fields import SERIAL_EPOCH, Cell
from squarepot_server.store import CellWrite
from tests.conftest import TOKEN, FakeStore, runtime

HEADER: list[Cell] = ["tag", "genus", "species", "seeding_date", "price", "status", "Shelf"]


def rows() -> list[list[Cell]]:
    return [
        HEADER,
        [4217, "Lithops", "lesliei", (date(2024, 3, 15) - SERIAL_EPOCH).days, 12.5, None, "A1"],
        [None, "Lithops", "aucampiae", None, None, None, "B2"],
        ["004218", "Conophytum", "bilobum", "March 2024"],
    ]


@pytest.fixture
def store() -> FakeStore:
    fake = FakeStore()
    fake.put("main", rows())
    return fake


def edit(client: TestClient, plant_id: str, body: dict[str, Any]) -> Any:
    return client.patch(f"/api/v1/plants/{plant_id}", json=body)


def change(seen: str | None, value: str | None) -> dict[str, str | None]:
    return {"seen": seen, "value": value}


def untagged(client: TestClient) -> dict[str, Any]:
    plants = client.get("/api/v1/sync").json()["plants"]
    [plant] = [plant for plant in plants if plant["tag"] is None]
    return dict(plant)


def test_an_edit_writes_only_its_cells_and_returns_the_plant_as_read_back(
    client: TestClient, store: FakeStore
) -> None:
    response = edit(client, "main:004217", {"fields": {"species": change("lesliei", "hallii")}})
    assert response.status_code == 200
    assert response.json()["fields"]["species"] == "hallii"
    assert store.writes == [(2, [CellWrite(2, "hallii")])]
    lookup = client.get("/api/v1/plants/by-tag/004217").json()
    assert lookup["plants"][0]["fields"]["species"] == "hallii"


def test_dates_and_decimals_are_written_as_such(client: TestClient, store: FakeStore) -> None:
    body = {
        "fields": {
            "seeding_date": change("2024-03-15", "2025-01-02"),
            "price": change("12.5", "13.50"),
            "status": change(None, "dead"),
        }
    }
    response = edit(client, "main:004217", body)
    assert response.status_code == 200
    assert store.writes == [
        (2, [CellWrite(3, date(2025, 1, 2)), CellWrite(4, Decimal("13.50")), CellWrite(5, "dead")])
    ]
    fields = response.json()["fields"]
    assert (fields["seeding_date"], fields["price"], fields["status"]) == (
        "2025-01-02",
        "13.50",
        "dead",
    )


def test_a_cell_changed_in_the_sheet_wins(client: TestClient, store: FakeStore) -> None:
    changed = rows()
    changed[1][2] = "dorotheae"
    store.put("main", changed)
    response = edit(client, "main:004217", {"fields": {"species": change("lesliei", "hallii")}})
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "changed_in_sheet"
    assert "species" in body["message"]
    assert body["plant"]["fields"]["species"] == "dorotheae"
    assert store.writes == []


def test_hand_edits_to_other_cells_of_the_row_are_kept(
    client: TestClient, store: FakeStore
) -> None:
    store.tabs["main"][1][6] = "C3"
    response = edit(client, "main:004217", {"fields": {"species": change("lesliei", "hallii")}})
    assert response.status_code == 200
    assert response.json()["custom"] == {"Shelf": "C3"}


def test_a_custom_column_can_be_edited(client: TestClient, store: FakeStore) -> None:
    response = edit(client, "main:004217", {"custom": {"Shelf": change("A1", "D4")}})
    assert response.status_code == 200
    assert response.json()["custom"] == {"Shelf": "D4"}
    assert store.writes == [(2, [CellWrite(6, "D4")])]


def test_a_rejected_cell_is_seen_as_its_rejected_value(client: TestClient) -> None:
    body = {"fields": {"seeding_date": change("March 2024", "2024-03-01")}}
    response = edit(client, "main:004218", body)
    assert response.status_code == 200
    assert response.json()["fields"]["seeding_date"] == "2024-03-01"
    assert response.json()["invalid"] == {}


@pytest.mark.parametrize(
    ("fields", "custom", "message"),
    [
        ({"seeding_date": "15.03.2024"}, {}, "seeding_date: write it as '2024-03-15'"),
        ({"seeding_date": "soon"}, {}, "seeding_date: not a date (YYYY-MM-DD)"),
        ({"price": "12,5"}, {}, "price: not a number"),
        ({"status": "Погиб"}, {}, "status: write it as 'dead'"),
        ({"genus": ""}, {}, "genus: is required"),
        ({"genus": " Lithops"}, {}, "genus: write it as 'Lithops'"),
        ({"tag": "004300"}, {}, "tag: numbers are issued by the server"),
        ({"colour": "red"}, {}, "colour: no such field"),
        ({"locality": "Springbok"}, {}, "locality: the sheet has no 'locality' column, add one"),
        ({}, {"Pot": "8 cm"}, "Pot: the sheet has no custom column of that name"),
    ],
)
def test_values_that_would_not_read_back_are_refused(
    client: TestClient,
    store: FakeStore,
    fields: dict[str, str],
    custom: dict[str, str],
    message: str,
) -> None:
    body = {
        "fields": {key: change(None, value) for key, value in fields.items()},
        "custom": {name: change(None, value) for name, value in custom.items()},
    }
    response = edit(client, "main:004217", body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert message in response.json()["message"]
    assert store.writes == []


def test_a_plant_without_a_number_gets_a_new_id_when_edited(client: TestClient) -> None:
    plant = untagged(client)
    body = {"fields": {"species": change("aucampiae", "aucampiae var. koelemanii")}}
    response = edit(client, plant["id"], body)
    assert response.status_code == 200
    assert response.json()["row"] == 3
    assert response.json()["id"] != plant["id"]
    assert edit(client, plant["id"], body).status_code == 404


def test_a_plant_without_a_number_changed_by_hand_is_a_conflict(
    client: TestClient, store: FakeStore
) -> None:
    plant = untagged(client)
    store.tabs["main"][2][6] = "C3"
    response = edit(client, plant["id"], {"fields": {"species": change("aucampiae", "x")}})
    assert response.status_code == 409
    assert response.json()["plant"]["custom"] == {"Shelf": "C3"}
    assert store.writes == []


def test_a_row_gone_from_the_sheet_is_a_conflict(client: TestClient, store: FakeStore) -> None:
    store.put("main", [row for row in rows() if row[0] != 4217])
    response = edit(client, "main:004217", {"fields": {"species": change("lesliei", "x")}})
    assert response.status_code == 409
    assert response.json() == {
        "code": "changed_in_sheet",
        "message": "The plant's row is no longer in the sheet as it was.",
        "plant": None,
    }


def registered(client: TestClient) -> list[str]:
    with runtime(client).sessions() as session:
        return list(session.scalars(select(RegisteredTag.tag).order_by(RegisteredTag.tag)))


def test_a_plant_gets_the_next_free_number(client: TestClient, store: FakeStore) -> None:
    response = edit(client, untagged(client)["id"], {"issue_number": True})
    assert response.status_code == 200
    assert response.json()["tag"] == "004219"
    assert response.json()["id"] == "main:004219"
    assert store.writes == [(3, [CellWrite(0, "004219", number=True)])]
    assert registered(client) == ["004217", "004218", "004219"]


def test_a_number_is_never_issued_twice_even_when_writing_it_fails(
    client: TestClient, store: FakeStore
) -> None:
    plant = untagged(client)
    store.failing.add("main")
    response = edit(client, plant["id"], {"issue_number": True})
    assert response.status_code == 503
    assert response.json()["code"] == "store_unavailable"
    store.failing.clear()
    assert edit(client, plant["id"], {"issue_number": True}).json()["tag"] == "004220"


def test_asking_a_number_for_a_numbered_plant_changes_nothing(
    client: TestClient, store: FakeStore
) -> None:
    response = edit(client, "main:004217", {"issue_number": True})
    assert response.status_code == 200
    assert response.json()["tag"] == "004217"
    assert store.writes == []


def test_a_new_plant_is_a_new_row_with_a_number(client: TestClient, store: FakeStore) -> None:
    body = {"fields": {"genus": "Haworthia", "species": "cooperi"}, "custom": {"Shelf": "D4"}}
    response = client.post("/api/v1/collections/main/plants", json=body)
    assert response.status_code == 201
    plant = response.json()
    assert (plant["tag"], plant["row"]) == ("004219", 5)
    assert plant["fields"] == {"genus": "Haworthia", "species": "cooperi"}
    assert plant["custom"] == {"Shelf": "D4"}
    assert store.tabs["main"][4] == ["004219", "Haworthia", "cooperi", None, None, None, "D4"]


def test_a_new_plant_may_go_without_a_number(client: TestClient) -> None:
    body = {"fields": {"genus": "Haworthia"}, "issue_number": False}
    response = client.post("/api/v1/collections/main/plants", json=body)
    assert response.status_code == 201
    assert (response.json()["tag"], response.json()["row"]) == (None, 5)


def test_a_new_plant_needs_its_required_fields(client: TestClient, store: FakeStore) -> None:
    response = client.post("/api/v1/collections/main/plants", json={"fields": {"species": "x"}})
    assert response.status_code == 422
    assert "genus: is required" in response.json()["message"]
    assert store.writes == []
    assert registered(client) == ["004217", "004218"]


def test_unknown_plants_and_collections_are_not_found(client: TestClient) -> None:
    assert edit(client, "main:999999", {}).status_code == 404
    response = client.post("/api/v1/collections/nope/plants", json={"fields": {"genus": "x"}})
    assert response.status_code == 404


@dataclass
class ReadOnlyStore:
    """A store that can only read, as a sheet read by link."""

    store: FakeStore

    def version(self, collection: CollectionConfig) -> str:
        return self.store.version(collection)

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        return self.store.read(collection)


@pytest.fixture
def read_only(settings: Settings, store: FakeStore) -> Iterator[TestClient]:
    app = create_app(settings, ReadOnlyStore(store))
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        runtime(client).syncer.run_once()
        yield client


def test_a_collection_read_by_link_cannot_be_edited(read_only: TestClient) -> None:
    [main] = read_only.get("/api/v1/collections").json()
    assert main["editable"] is False
    response = edit(read_only, "main:004217", {"fields": {"species": change("lesliei", "x")}})
    assert response.status_code == 409
    assert response.json()["code"] == "not_editable"
    response = read_only.post("/api/v1/collections/main/plants", json={"fields": {"genus": "x"}})
    assert response.status_code == 409


def test_a_retried_addition_adds_no_second_row(client: TestClient, store: FakeStore) -> None:
    body = {"request_id": "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b", "fields": {"genus": "Aloe"}}
    first = client.post("/api/v1/collections/main/plants", json=body)
    again = client.post("/api/v1/collections/main/plants", json=body)
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert len(store.writes) == 1
    assert registered(client) == ["004217", "004218", "004219"]
    other = {**body, "request_id": "0b7e6a3c-1111-4222-8333-944455566677"}
    assert client.post("/api/v1/collections/main/plants", json=other).json()["tag"] == "004220"
