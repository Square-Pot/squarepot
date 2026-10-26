# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Google Sheets stores, with the HTTP session stubbed out."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
import requests

from squarepot_server.config import CollectionConfig
from squarepot_server.store import (
    MAX_DOWNLOAD_BYTES,
    CellWrite,
    GoogleSheetsStore,
    SheetLinkStore,
    StoreError,
)

CONFIG = CollectionConfig(id="main", name="Main", spreadsheet_id="abc/123?x", sheet="It's a tab/1")


def response(
    status: int, body: Any = None, reason: str = "", content_type: str = "application/json"
) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.reason = reason
    result.headers["Content-Type"] = content_type
    result._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    result._content_consumed = True  # type: ignore[attr-defined]  # the body is all there
    return result


@dataclass
class StubSession:
    answer: requests.Response | Exception
    calls: list[tuple[str, dict[str, str], float]] = field(default_factory=list)

    def get(
        self, url: str, params: dict[str, str], timeout: float, stream: bool = False
    ) -> requests.Response:
        self.calls.append((url, params, timeout))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def request(
        self, method: str, url: str, params: dict[str, str], json: Any, timeout: float
    ) -> requests.Response:
        assert (method, json) == ("GET", None)
        return self.get(url, params, timeout)


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
        (
            requests.ConnectionError("no route to host"),
            r"Google is unreachable \(ConnectionError\)",
        ),
        (requests.Timeout("timed out"), r"Google is unreachable \(Timeout\)"),
    ],
)
def test_failures_become_store_errors(answer: requests.Response | Exception, message: str) -> None:
    sheets, _ = store(answer)
    with pytest.raises(StoreError, match=f"^{message}$"):
        sheets.version(CONFIG)
    with pytest.raises(StoreError, match=f"^{message}$"):
        sheets.read(CONFIG)


CSV = "text/csv; charset=utf-8"
LINKED = CollectionConfig(id="main", name="Main", spreadsheet_id="abc/123?x")


def link_store(answer: requests.Response | Exception) -> tuple[SheetLinkStore, StubSession]:
    session = StubSession(answer)
    return SheetLinkStore(cast(requests.Session, session)), session


@pytest.mark.parametrize("error", [requests.ConnectionError, requests.ConnectTimeout])
def test_connection_errors_do_not_reveal_the_sheet_id(
    error: type[requests.RequestException],
) -> None:
    # As requests words it, with the URL in the text.
    answer = error(
        "HTTPSConnectionPool(host='docs.google.com', port=443): Max retries exceeded with url: "
        "/spreadsheets/d/abc%2F123%3Fx/export?format=csv"
    )
    stores: list[tuple[SheetLinkStore | GoogleSheetsStore, CollectionConfig]] = [
        (link_store(answer)[0], LINKED),
        (store(answer)[0], CONFIG),
    ]
    for sheets, collection in stores:
        with pytest.raises(StoreError) as caught:
            sheets.read(collection)
        assert "abc" not in str(caught.value)
        assert str(caught.value) == f"Google is unreachable ({error.__name__})"


def test_a_linked_sheet_is_downloaded_as_csv_from_its_first_tab() -> None:
    sheets, session = link_store(response(200, b"tag,genus\n4217,Lithops\n", content_type=CSV))
    assert sheets.read(LINKED) == [["tag", "genus"], ["4217", "Lithops"]]
    [(url, params, timeout)] = session.calls
    assert url == "https://docs.google.com/spreadsheets/d/abc%2F123%3Fx/export"
    assert params == {"format": "csv"}
    assert timeout > 0


def test_a_gid_chooses_the_tab() -> None:
    sheets, session = link_store(response(200, b"genus\n", content_type=CSV))
    sheets.read(LINKED.model_copy(update={"gid": 0}))
    assert session.calls[0][1] == {"format": "csv", "gid": "0"}


def test_the_version_is_a_hash_and_the_read_after_it_reuses_the_download() -> None:
    sheets, session = link_store(response(200, b"\xef\xbb\xbfgenus\nLithops\n", content_type=CSV))
    version = sheets.version(LINKED)
    assert len(version) == 64
    assert sheets.read(LINKED) == [["genus"], ["Lithops"]]
    assert len(session.calls) == 1
    assert sheets.version(LINKED) == version
    assert len(session.calls) == 2


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (
            response(404, b"<html></html>", "Not Found", "text/html"),
            "Google answered 404: no such sheet or tab, or the sheet is not shared by link",
        ),
        (
            response(200, b"<html>Sign in</html>", content_type="text/html; charset=utf-8"),
            'Google did not send CSV: share the sheet as "anyone with the link can view"',
        ),
        (
            response(500, b"", "Internal Server Error", "text/html"),
            "Google answered 500: Internal Server Error",
        ),
        (
            requests.ConnectionError("no route to host"),
            r"Google is unreachable \(ConnectionError\)",
        ),
        (response(200, b"genus\nD\xe9moa\n", content_type=CSV), "the sheet is not UTF-8: .*"),
        (
            response(200, b"x" * (MAX_DOWNLOAD_BYTES + 1), content_type=CSV),
            "the sheet is larger than 20 MB",
        ),
    ],
)
def test_link_failures_become_store_errors(
    answer: requests.Response | Exception, message: str
) -> None:
    sheets, _ = link_store(answer)
    with pytest.raises(StoreError, match=f"^{message}$"):
        sheets.read(LINKED)


@dataclass
class RecordingSession:
    """Answers each request with the next of `answers`, and records it."""

    answers: list[requests.Response]
    calls: list[tuple[str, str, dict[str, str], Any]] = field(default_factory=list)

    def request(
        self, method: str, url: str, params: dict[str, str], json: Any, timeout: float
    ) -> requests.Response:
        self.calls.append((method, url, params, json))
        return self.answers.pop(0)


def writing_store(*answers: requests.Response) -> tuple[GoogleSheetsStore, RecordingSession]:
    session = RecordingSession(list(answers))
    return GoogleSheetsStore(cast(requests.Session, session)), session


SHEETS = "https://sheets.googleapis.com/v4/spreadsheets/abc/123%3Fx"
TABS = {
    "sheets": [
        {"properties": {"sheetId": 0, "title": "Other"}},
        {"properties": {"sheetId": 7, "title": "It's a tab/1"}},
    ]
}


def test_cells_are_written_as_if_typed_and_keep_their_format() -> None:
    sheets, session = writing_store(response(200, {}))
    cells = [
        CellWrite(1, "=1+1"),
        CellWrite(3, date(2025, 1, 2)),
        CellWrite(4, Decimal("12.50")),
        CellWrite(5, Decimal("3")),
        CellWrite(27, None),
    ]
    sheets.write(CONFIG, 12, cells)
    [(method, url, params, body)] = session.calls
    assert (method, url, params) == ("POST", f"{SHEETS}/values:batchUpdate", {})
    assert body == {
        "valueInputOption": "USER_ENTERED",
        "data": [
            {"range": "'It''s a tab/1'!B12", "values": [["'=1+1"]]},
            {"range": "'It''s a tab/1'!D12", "values": [["2025-01-02"]]},
            {"range": "'It''s a tab/1'!E12", "values": [[12.5]]},
            {"range": "'It''s a tab/1'!F12", "values": [[3]]},
            {"range": "'It''s a tab/1'!AB12", "values": [[""]]},
        ],
    }


def test_a_number_cell_is_set_to_plain_text() -> None:
    sheets, session = writing_store(response(200, {}), response(200, TABS), response(200, {}))
    sheets.write(CONFIG, 12, [CellWrite(0, "004219", number=True)])
    write, tabs, format_ = session.calls
    assert write[3]["data"] == [{"range": "'It''s a tab/1'!A12", "values": [["'004219"]]}]
    assert tabs[:3] == ("GET", SHEETS, {"fields": "sheets.properties(sheetId,title)"})
    assert format_[:2] == ("POST", f"{SHEETS}:batchUpdate")
    assert format_[3] == {
        "requests": [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": 7,
                        "startRowIndex": 11,
                        "endRowIndex": 12,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
                    "fields": "userEnteredFormat.numberFormat",
                }
            }
        ]
    }


def test_a_row_is_appended_after_the_last_and_its_number_is_returned() -> None:
    appended = {"updates": {"updatedRange": "'It''s a tab/1'!A528:C528"}}
    sheets, session = writing_store(response(200, appended), response(200, TABS), response(200, {}))
    row = sheets.append(CONFIG, [CellWrite(2, "cooperi"), CellWrite(0, "004219", number=True)])
    assert row == 528
    method, url, params, body = session.calls[0]
    assert (method, url) == ("POST", f"{SHEETS}/values/%27It%27%27s%20a%20tab%2F1%27:append")
    assert params == {"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
    assert body == {"majorDimension": "ROWS", "values": [["'004219", "", "'cooperi"]]}
    assert session.calls[2][3]["requests"][0]["repeatCell"]["range"]["startRowIndex"] == 527


def test_an_append_without_a_row_in_the_answer_is_an_error() -> None:
    sheets, _ = writing_store(response(200, {"updates": {}}))
    with pytest.raises(StoreError, match="did not say which row"):
        sheets.append(CONFIG, [CellWrite(1, "Haworthia")])


def test_a_missing_tab_stops_formatting() -> None:
    sheets, _ = writing_store(response(200, {}), response(200, {"sheets": []}))
    with pytest.raises(StoreError, match="no tab"):
        sheets.write(CONFIG, 2, [CellWrite(0, "004219", number=True)])


def test_write_failures_become_store_errors() -> None:
    answer = response(403, {"error": {"message": "The caller does not have permission"}})
    sheets, _ = writing_store(answer)
    with pytest.raises(StoreError, match="^Google answered 403: The caller does not have"):
        sheets.write(CONFIG, 2, [CellWrite(1, "Lithops")])
