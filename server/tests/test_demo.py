# SPDX-License-Identifier: AGPL-3.0-or-later
"""The CSV file store: the server without a Google account."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from squarepot_server.config import CollectionConfig, Settings, StoreKind
from squarepot_server.store import CsvFileStore, StoreError
from tests.conftest import TOKEN


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
