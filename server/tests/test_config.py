# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings: each store gets the collection fields it can use."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from squarepot_server.config import CollectionConfig, Settings, StoreKind


def settings(store: StoreKind, **fields: Any) -> Settings:
    return Settings(
        api_token=SecretStr("test-token-0123456789"),
        store=store,
        collections=[CollectionConfig(id="main", name="Main", **fields)],
    )


def test_the_link_store_takes_a_gid() -> None:
    [collection] = settings(StoreKind.LINK, spreadsheet_id="abc", gid=7).collections
    assert collection.gid == 7


@pytest.mark.parametrize(
    ("store", "fields", "message"),
    [
        (StoreKind.LINK, {}, "needs a spreadsheet_id with the link store"),
        (StoreKind.LINK, {"spreadsheet_id": "abc", "sheet": "Plants"}, "give the tab's gid"),
        (StoreKind.GOOGLE, {"spreadsheet_id": "abc"}, "needs a spreadsheet_id and a sheet"),
        (
            StoreKind.GOOGLE,
            {"spreadsheet_id": "abc", "sheet": "Plants", "gid": 7},
            "name the tab with sheet instead",
        ),
        (StoreKind.FILE, {}, "needs a file with the file store"),
    ],
)
def test_a_collection_that_its_store_cannot_read_is_rejected(
    store: StoreKind, fields: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        settings(store, **fields)
