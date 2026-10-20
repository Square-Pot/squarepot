# SPDX-License-Identifier: AGPL-3.0-or-later
"""Syncing the server's copy with the store, and the phone's copy with the server."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from squarepot_server.api.models import FieldSchema
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
