# SPDX-License-Identifier: AGPL-3.0-or-later
"""The CSV file store and the demo collection: the server without a Google account."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from squarepot_server.app import create_app
from squarepot_server.config import CollectionConfig, Settings, StoreKind
from squarepot_server.fields import load_schema, parse_tab
from squarepot_server.labels.caption import caption, entries
from squarepot_server.store import CsvFileStore, StoreError
from tests.conftest import TOKEN, runtime
from tests.test_sync import ids, sync

DEMO = Path(__file__).resolve().parents[1] / "demo" / "plants.csv"
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema" / "fields.yaml"
# The tags of the A4 sample sheet of labels.
SAMPLE_TAGS = [f"{n:06d}" for n in range(1, 78)]


def file_collection(path: Path) -> CollectionConfig:
    return CollectionConfig(id="demo", name="Demo plants", file=path)


def test_a_csv_file_reads_as_a_tab_of_text(tmp_path: Path) -> None:
    path = tmp_path / "plants.csv"
    path.write_bytes('\ufefftag,genus,notes\n004217,Demoa,"one, two"\n\n,Fictilia,\n'.encode())
    assert CsvFileStore().read(file_collection(path)) == [
        ["tag", "genus", "notes"],
        ["004217", "Demoa", "one, two"],
        [],
        ["", "Fictilia", ""],
    ]


def test_the_version_follows_the_content(tmp_path: Path) -> None:
    path = tmp_path / "plants.csv"
    store, collection = CsvFileStore(), file_collection(path)
    path.write_text("tag,genus\n")
    first = store.version(collection)
    path.write_text("tag,genus\n")
    assert store.version(collection) == first
    path.write_text("tag,genus\n000001,Demoa\n")
    assert store.version(collection) != first


def test_an_unreadable_file_is_a_store_error(tmp_path: Path) -> None:
    store = CsvFileStore()
    with pytest.raises(StoreError, match="cannot read"):
        store.version(file_collection(tmp_path / "missing.csv"))
    (tmp_path / "latin1.csv").write_bytes(b"tag,genus\n,D\xe9moa\n")
    with pytest.raises(StoreError, match="not UTF-8"):
        store.read(file_collection(tmp_path / "latin1.csv"))


@pytest.mark.parametrize(
    ("store", "collection", "message"),
    [
        (StoreKind.FILE, {"id": "demo", "name": "Demo"}, "needs a file"),
        (StoreKind.GOOGLE, {"id": "demo", "name": "Demo", "file": "a.csv"}, "spreadsheet_id"),
        (StoreKind.LINK, {"id": "demo", "name": "Demo", "file": "a.csv"}, "spreadsheet_id"),
    ],
)
def test_collections_must_suit_the_store(
    store: StoreKind, collection: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            api_token=SecretStr(TOKEN),
            store=store,
            collections=[CollectionConfig.model_validate(collection)],
        )


def test_the_demo_collection_is_valid_and_matches_the_sample_sheet() -> None:
    parsed = parse_tab(load_schema(SCHEMA_FILE), CsvFileStore().read(file_collection(DEMO)))
    assert parsed.issues == []
    assert [row.tag for row in parsed.rows if row.tag] == SAMPLE_TAGS
    assert len(parsed.rows) > len(SAMPLE_TAGS)  # and some plants without a label yet


def test_demo_names_follow_the_display_rules() -> None:
    # The schema adds "aff." to an affinity itself, so the sheet holds only the epithet.
    schema = load_schema(SCHEMA_FILE)
    label = entries(next(preset for preset in schema.presets if preset.key == "label"))
    parsed = parse_tab(schema, CsvFileStore().read(file_collection(DEMO)))
    texts = [
        " ".join("".join(run.text for run in item) for item in caption(schema, label, row.fields))
        for row in parsed.rows
    ]
    assert not any("aff. aff." in text for text in texts)
    assert sum(" aff. " in text for text in texts) > 0


@pytest.fixture
def demo(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    path = tmp_path / "plants.csv"
    shutil.copy(DEMO, path)
    settings = Settings(
        api_token=SecretStr(TOKEN),
        database_url=f"sqlite:///{tmp_path / 'squarepot.db'}",
        store=StoreKind.FILE,
        collections=[file_collection(path)],
        sync_interval_seconds=0,
    )
    with TestClient(create_app(settings), headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        runtime(client).syncer.run_once()
        yield client, path


def test_the_demo_syncs_and_numbers_are_found(demo: tuple[TestClient, Path]) -> None:
    client, _ = demo
    body = sync(client)
    assert body["kind"] == "full"
    assert body["collections"][0]["error"] is None
    assert sorted(plant["tag"] for plant in body["plants"] if plant["tag"]) == SAMPLE_TAGS
    found = client.get("/api/v1/plants/by-tag/000042")
    assert found.status_code == 200
    assert ids(found.json()["plants"]) == ["demo:000042"]


def test_an_edit_of_the_file_reaches_the_delta(demo: tuple[TestClient, Path]) -> None:
    client, path = demo
    first = sync(client)
    last = first["plants"][-1]["id"]
    lines = path.read_text().splitlines()
    edited = lines[1].replace(",alba,", ",nivea,")
    assert edited != lines[1]
    # Edit the first plant, remove the last one, and add one with a new number in its place.
    path.write_text("\n".join([lines[0], edited, *lines[2:-1], "000078,,Demoa,,nova"]) + "\n")
    runtime(client).syncer.run_once()
    body = sync(client, first["cursor"])
    assert body["kind"] == "delta"
    assert ids(body["plants"]) == ["demo:000001", "demo:000078"]
    assert body["plants"][0]["fields"]["species"] == "nivea"
    assert body["removed_plants"] == [last]
    assert client.get("/api/v1/plants/by-tag/000078").status_code == 200
