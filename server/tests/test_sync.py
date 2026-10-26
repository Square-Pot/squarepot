# SPDX-License-Identifier: AGPL-3.0-or-later
"""Syncing the server's copy with the store, and the phone's copy with the server."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from squarepot_server.api.models import FieldSchema
from squarepot_server.config import Settings
from tests.conftest import HEADER, FakeStore, collection, runtime


def sync(client: TestClient, cursor: str | None = None) -> dict[str, Any]:
    params = {"cursor": cursor} if cursor is not None else {}
    response = client.get("/api/v1/sync", params=params)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def ids(items: list[dict[str, Any]]) -> list[str]:
    return [item["id"] for item in items]


def test_full_copy(client: TestClient) -> None:
    body = sync(client)
    assert body["kind"] == "full"
    assert body["schema_version"] == 1
    assert ids(body["collections"]) == ["main"]
    assert len(body["plants"]) == 3
    assert body["removed_collections"] == body["removed_plants"] == []


def test_nothing_changed_gives_an_empty_delta(client: TestClient) -> None:
    cursor = sync(client)["cursor"]
    body = sync(client, cursor)
    assert body["kind"] == "delta"
    assert body["collections"] == body["plants"] == []
    assert body["cursor"] == cursor


def test_a_poll_of_an_unchanged_sheet_refreshes_only_the_collection(
    client: TestClient, store: FakeStore
) -> None:
    first = sync(client)
    reads = store.reads
    runtime(client).syncer.run_once()
    body = sync(client, first["cursor"])
    assert store.reads == reads
    assert ids(body["collections"]) == ["main"]
    assert body["collections"][0]["synced_at"] >= first["collections"][0]["synced_at"]
    assert body["plants"] == []


def test_edits_additions_and_removals_reach_the_delta(client: TestClient, store: FakeStore) -> None:
    cursor = sync(client)["cursor"]
    store.put(
        "main",
        [
            HEADER,
            ["004218", "Conophytum", "bilobum", "PV 99"],  # edited, and moved up a row
            [4219, "Haworthia", "cooperi"],  # added
            # 004217 and the untagged row are gone
        ],
    )
    runtime(client).syncer.run_once()
    body = sync(client, cursor)
    assert body["kind"] == "delta"
    assert ids(body["plants"]) == ["main:004218", "main:004219"]
    assert body["plants"][0]["row"] == 2
    assert body["plants"][0]["fields"]["field_number"] == "PV 99"
    assert len(body["removed_plants"]) == 2
    assert "main:004217" in body["removed_plants"]
    assert client.get("/api/v1/plants/by-tag/004217").status_code == 404
    assert len(sync(client)["plants"]) == 2


def test_custom_columns_reach_the_phone_and_their_edits_the_delta(
    client: TestClient, store: FakeStore
) -> None:
    assert sync(client)["collections"][0]["custom_columns"] == []
    store.put("main", [[*HEADER, "Marathon"], [4217, "Lithops", "lesliei", "SB 1234", "yes"]])
    runtime(client).syncer.run_once()
    body = sync(client)
    assert body["collections"][0]["custom_columns"] == ["Marathon"]
    [plant] = body["plants"]
    assert plant["custom"] == {"Marathon": "yes"}
    store.put("main", [[*HEADER, "Marathon"], [4217, "Lithops", "lesliei", "SB 1234", "no"]])
    runtime(client).syncer.run_once()
    delta = sync(client, body["cursor"])
    assert [plant["custom"] for plant in delta["plants"]] == [{"Marathon": "no"}]


def test_rejected_cells_reach_the_phone_and_go_when_fixed(
    client: TestClient, store: FakeStore
) -> None:
    store.put("main", [["tag", "genus", "seeding_date"], [4217, "Lithops", "soon"]])
    runtime(client).syncer.run_once()
    body = sync(client)
    [plant] = body["plants"]
    assert plant["invalid"] == {
        "seeding_date": {"cell": "C2", "value": "soon", "reason": "not a date (YYYY-MM-DD)"}
    }
    store.put("main", [["tag", "genus", "seeding_date"], [4217, "Lithops", "2024-03-15"]])
    runtime(client).syncer.run_once()
    [fixed] = sync(client, body["cursor"])["plants"]
    assert fixed["invalid"] == {}
    assert fixed["fields"]["seeding_date"] == "2024-03-15"


def test_the_sheet_url_opens_the_tab_when_its_gid_is_known(
    client: TestClient, settings: Settings
) -> None:
    settings.collections[0] = settings.collections[0].model_copy(update={"gid": 1234})
    [main] = sync(client)["collections"]
    assert main["sheet_url"] == "https://docs.google.com/spreadsheets/d/sheet/edit#gid=1234"
    settings.collections[0] = settings.collections[0].model_copy(
        update={"spreadsheet_id": None, "file": "plants.csv"}
    )
    assert sync(client)["collections"][0]["sheet_url"] is None


def test_a_removed_row_that_comes_back_is_sent_again(client: TestClient, store: FakeStore) -> None:
    original = store.tabs["main"]
    store.put("main", original[:1] + original[2:])
    runtime(client).syncer.run_once()
    cursor = sync(client)["cursor"]
    store.put("main", original)
    runtime(client).syncer.run_once()
    body = sync(client, cursor)
    # The rows below it moved back down, so they changed too.
    assert "main:004217" in ids(body["plants"])
    assert body["removed_plants"] == []


def test_a_collection_no_longer_configured_is_removed_with_its_plants(
    client: TestClient,
) -> None:
    full = sync(client)
    runtime(client).syncer.collections = []
    runtime(client).syncer.run_once()
    body = sync(client, full["cursor"])
    assert body["removed_collections"] == ["main"]
    assert sorted(body["removed_plants"]) == sorted(ids(full["plants"]))
    assert client.get("/api/v1/collections").json() == []


def test_a_store_failure_keeps_the_copy_and_reports_it(
    client: TestClient, store: FakeStore
) -> None:
    cursor = sync(client)["cursor"]
    store.failing.add("main")
    runtime(client).syncer.run_once()
    body = sync(client, cursor)
    [main] = body["collections"]
    assert main["error"] == "Google is unreachable: test"
    assert main["plant_count"] == 3
    assert client.get("/api/v1/plants/by-tag/004217").status_code == 200

    store.failing.clear()
    runtime(client).syncer.run_once()
    assert sync(client, body["cursor"])["collections"][0]["error"] is None


def test_former_plants_are_counted_apart_and_still_served(
    client: TestClient, store: FakeStore
) -> None:
    store.put(
        "main",
        [
            ["tag", "genus", "status", "status_date"],
            [4217, "Lithops", "", ""],
            [4218, "Conophytum", "dead", "2025-06-14"],
            [4219, "Lithops", "sold", ""],
        ],
    )
    runtime(client).syncer.run_once()
    body = sync(client)
    [main] = body["collections"]
    assert (main["plant_count"], main["former_count"]) == (1, 2)
    assert len(body["plants"]) == 3
    plants = client.get("/api/v1/plants/by-tag/004218").json()["plants"]
    assert plants[0]["fields"]["status"] == "dead"
    assert plants[0]["status_since"] == "2025-06-14"


def test_the_server_records_since_when_a_plant_has_its_status(
    client: TestClient, store: FakeStore
) -> None:
    def since(tag: str) -> Any:
        return client.get(f"/api/v1/plants/by-tag/{tag}").json()["plants"][0]["status_since"]

    def put(status: str, notes: str = "", status_date: str = "") -> None:
        store.put(
            "main",
            [
                ["tag", "genus", "status", "notes", "status_date"],
                [4217, "Lithops", status, notes, status_date],
            ],
        )

    syncer = runtime(client).syncer
    syncer.clock = lambda: datetime(2026, 10, 25, 12, tzinfo=UTC)
    put("")
    syncer.run_once()
    assert since("004217") is None

    put("dead")
    syncer.run_once()
    assert since("004217") == "2026-10-25"

    # Another edit keeps the day; a different status starts a new one.
    syncer.clock = lambda: datetime(2026, 11, 2, 12, tzinfo=UTC)
    put("dead", notes="a pity")
    syncer.run_once()
    assert since("004217") == "2026-10-25"
    put("gifted")
    syncer.run_once()
    assert since("004217") == "2026-11-02"

    # A date in the sheet wins; without a status there is none.
    put("gifted", status_date="2026-10-30")
    syncer.run_once()
    assert since("004217") == "2026-10-30"
    put("")
    syncer.run_once()
    assert since("004217") is None


def test_a_broken_tab_keeps_the_copy_and_reports_it(client: TestClient, store: FakeStore) -> None:
    store.put("main", [["tag", "species"], [4217, "lesliei"]])
    runtime(client).syncer.run_once()
    [main] = client.get("/api/v1/collections").json()
    assert main["error"] == "no 'genus' column"
    assert client.get("/api/v1/plants/by-tag/004217").status_code == 200


def test_unusable_cursors_give_a_full_copy(client: TestClient) -> None:
    cursor = sync(client)["cursor"]
    epoch, schema_version, seq = cursor.split(".")
    for bad in [
        "",
        "garbage",
        "a.b.c",
        f"{epoch}.{schema_version}.-1",
        f"{epoch}.{schema_version}.{int(seq) + 1}",
        f"other.{schema_version}.{seq}",
        f"{epoch}.{int(schema_version) + 1}.{seq}",
    ]:
        assert sync(client, bad)["kind"] == "full", bad


def test_a_new_schema_version_rereads_sheets_and_resets_cursors(
    client: TestClient, store: FakeStore
) -> None:
    cursor = sync(client)["cursor"]
    syncer = runtime(client).syncer
    newer = FieldSchema.model_validate({**syncer.schema.model_dump(by_alias=True), "version": 2})
    syncer.schema = newer
    runtime(client).schema = newer
    reads = store.reads
    syncer.run_once()
    assert store.reads == reads + 1
    body = sync(client, cursor)
    assert body["kind"] == "full"
    assert body["schema_version"] == 2


def test_a_changed_field_rereads_sheets_without_resetting_cursors(
    client: TestClient, store: FakeStore
) -> None:
    cursor = sync(client)["cursor"]
    syncer = runtime(client).syncer
    schema = syncer.schema.model_dump(by_alias=True)
    for field in schema["fields"]:
        if field["key"] == "species":
            field["display"]["case"] = "as-is"
    syncer.schema = FieldSchema.model_validate(schema)
    reads = store.reads
    syncer.run_once()
    assert store.reads == reads + 1
    assert sync(client, cursor)["kind"] == "delta"
    syncer.run_once()
    assert store.reads == reads + 1


def test_untagged_rows_have_ids_too(client: TestClient) -> None:
    [untagged] = [plant for plant in sync(client)["plants"] if plant["tag"] is None]
    assert untagged["id"].startswith("main:h")
    assert untagged["fields"] == {"genus": "Lithops", "species": "aucampiae"}


def test_a_repeated_failure_is_not_sent_again(client: TestClient, store: FakeStore) -> None:
    store.failing.add("main")
    runtime(client).syncer.run_once()
    cursor = sync(client)["cursor"]
    runtime(client).syncer.run_once()
    assert sync(client, cursor)["collections"] == []


def test_cursors_that_are_not_plain_numbers_give_a_full_copy(client: TestClient) -> None:
    epoch, schema_version, _ = sync(client)["cursor"].split(".")
    for seq in ["²", "٣", "9" * 5000, " 1", "1 "]:
        assert sync(client, f"{epoch}.{schema_version}.{seq}")["kind"] == "full", seq


def test_a_failing_collection_does_not_stop_the_others(
    client: TestClient, store: FakeStore
) -> None:
    syncer = runtime(client).syncer
    syncer.collections = [collection("broken"), *syncer.collections]
    store.put("broken", [HEADER, [1, "Lithops"]])
    store.buggy.add("broken")
    store.put("main", [HEADER, [4217, "Lithops", "lesliei"], [4300, "Haworthia"]])
    syncer.run_once()
    by_id = {c["id"]: c for c in client.get("/api/v1/collections").json()}
    assert by_id["broken"]["error"] == "unexpected error while syncing; see the server log"
    assert by_id["main"]["error"] is None
    assert client.get("/api/v1/plants/by-tag/4300").status_code == 200


def test_a_number_typed_into_a_date_cell_is_only_a_cell_issue(
    client: TestClient, store: FakeStore
) -> None:
    store.put("main", [["tag", "genus", "seeding_date"], [4217, "Lithops", 20240315]])
    runtime(client).syncer.run_once()
    [main] = client.get("/api/v1/collections").json()
    assert main["error"] is None
    [plant] = client.get("/api/v1/plants/by-tag/4217").json()["plants"]
    assert plant["fields"] == {"genus": "Lithops"}


def test_a_collection_configured_again_gets_its_plants_back(client: TestClient) -> None:
    syncer = runtime(client).syncer
    configured = syncer.collections
    syncer.collections = []
    syncer.run_once()
    cursor = sync(client)["cursor"]
    syncer.collections = configured
    syncer.run_once()
    body = sync(client, cursor)
    assert ids(body["collections"]) == ["main"]
    assert len(body["plants"]) == 3
    assert client.get("/api/v1/plants/by-tag/4217").status_code == 200
