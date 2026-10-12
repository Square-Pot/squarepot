# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from squarepot_server.runtime import UnavailableStore, google_store
from squarepot_server.store import StoreError
from tests.conftest import collection


def test_without_a_key_collections_report_it() -> None:
    store = google_store(None)
    assert isinstance(store, UnavailableStore)
    with pytest.raises(StoreError, match="SQUAREPOT_GOOGLE_CREDENTIALS_FILE is not set"):
        store.version(collection("main"))


@pytest.mark.parametrize("content", [None, "{}", "not json"])
def test_an_unusable_key_does_not_stop_the_server(tmp_path: Path, content: str | None) -> None:
    key = tmp_path / "service-account.json"
    if content is not None:
        key.write_text(content)
    store = google_store(key)
    assert isinstance(store, UnavailableStore)
    assert store.reason.startswith("the service account key cannot be used")
