# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Google Sheets store, with the HTTP session stubbed out."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
import requests

from squarepot_server.config import CollectionConfig
from squarepot_server.store import GoogleSheetsStore, StoreError

CONFIG = CollectionConfig(id="main", name="Main", spreadsheet_id="abc/123?x", sheet="It's a tab/1")


def response(status: int, body: Any = None, reason: str = "") -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.reason = reason
    result._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return result


@dataclass
class StubSession:
    answer: requests.Response | Exception
    calls: list[tuple[str, dict[str, str], float]] = field(default_factory=list)

    def get(self, url: str, params: dict[str, str], timeout: float) -> requests.Response:
        self.calls.append((url, params, timeout))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def store(answer: requests.Response | Exception) -> tuple[GoogleSheetsStore, StubSession]:
    session = StubSession(answer)
    return GoogleSheetsStore(cast(requests.Session, session)), session


def test_version_is_the_drive_modified_time() -> None:
    sheets, session = store(response(200, {"modifiedTime": "2026-10-12T10:00:00.000Z"}))
    assert sheets.version(CONFIG) == "2026-10-12T10:00:00.000Z"
    [(url, params, timeout)] = session.calls
    assert url == "https://www.googleapis.com/drive/v3/files/abc/123%3Fx"
    assert params == {"fields": "modifiedTime", "supportsAllDrives": "true"}
    assert timeout > 0


def test_read_quotes_the_tab_name_and_asks_for_unformatted_values() -> None:
    sheets, session = store(response(200, {"values": [["tag", "genus"], [4217, "Lithops"]]}))
    assert sheets.read(CONFIG) == [["tag", "genus"], [4217, "Lithops"]]
    [(url, params, _)] = session.calls
    assert url == (
        "https://sheets.googleapis.com/v4/spreadsheets/abc/123%3Fx"
        "/values/%27It%27%27s%20a%20tab%2F1%27"
    )
    assert params == {
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
        "majorDimension": "ROWS",
    }


def test_an_empty_tab_has_no_values() -> None:
    sheets, _ = store(response(200, {"range": "'Plants'!A1:Z1000"}))
    assert sheets.read(CONFIG) == []


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (
            response(
                403, {"error": {"code": 403, "message": "The caller does not have permission"}}
            ),
            "Google answered 403: The caller does not have permission",
        ),
        (
            response(502, b"<html>Bad Gateway</html>", "Bad Gateway"),
            "Google answered 502: Bad Gateway",
        ),
        (response(404, {"error": "not an object"}, "Not Found"), "Google answered 404: Not Found"),
        (requests.ConnectionError("no route to host"), "Google is unreachable: no route to host"),
        (requests.Timeout("timed out"), "Google is unreachable: timed out"),
    ],
)
def test_failures_become_store_errors(answer: requests.Response | Exception, message: str) -> None:
    sheets, _ = store(answer)
    with pytest.raises(StoreError, match=f"^{message}$"):
        sheets.version(CONFIG)
    with pytest.raises(StoreError, match=f"^{message}$"):
        sheets.read(CONFIG)
