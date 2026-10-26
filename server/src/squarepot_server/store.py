# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where collections are stored: the CollectionStore interface (ADR 0003), Sheets and CSV files."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable
from urllib.parse import quote

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from squarepot_server.config import CollectionConfig
from squarepot_server.fields import Cell, column_name

log = logging.getLogger(__name__)
SCOPES = [
    # Writing too (ADR 0006); the sheet's sharing decides whether the account may.
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]
TIMEOUT_SECONDS = 30
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{}/export"
# A tab of plants is about 100 bytes a row; more than this is not a collection.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets/{}"
# The first row of a range such as A528:F528, the part after the tab name's last "!".
RANGE_ROW = re.compile(r"[A-Z]+([0-9]+)")


class StoreError(Exception):
    """The store could not be reached or refused the request."""


class StoreRefused(StoreError):
    """The store refused a request for lack of permission, such as a write to a shared sheet."""


class CollectionStore(Protocol):
    def version(self, collection: CollectionConfig) -> str:
        """A value that changes whenever the collection's data may have changed; cheap to get."""
        ...

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        """Every row of the collection's tab, header first."""
        ...


@dataclass(frozen=True)
class CellWrite:
    """A value to write into one cell of a row, by zero-based column index.

    Text is written as typed text, never as a formula or a number. A decimal is
    written as a number and a date as a date, so the cell keeps its format.
    None empties the cell. A plant number is text, and its cell is also set to
    the plain text format (docs/sheet-format.md, "The plant number").
    """

    column: int
    value: str | Decimal | date | None
    number: bool = False


@runtime_checkable
class EditableStore(CollectionStore, Protocol):
    """A store that can write the cells of a collection (ADR 0006)."""

    def can_edit(self, collection: CollectionConfig) -> bool:
        """Whether writing to the collection is allowed, as of its last version check."""
        ...

    def write(self, collection: CollectionConfig, row: int, cells: list[CellWrite]) -> None:
        """Write cells of one row, by its sheet row number; leaves every other cell alone."""
        ...

    def write_rows(self, collection: CollectionConfig, rows: dict[int, list[CellWrite]]) -> None:
        """Write cells of many rows in one call, as `write` does for one."""
        ...

    def append(self, collection: CollectionConfig, cells: list[CellWrite]) -> int:
        """Add a row after the last row of the tab, and return its row number."""
        ...


def parse_csv(data: bytes, where: object) -> list[list[Cell]]:
    """Rows of a CSV file in UTF-8, with or without a byte order mark; every cell is text."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise StoreError(f"{where} is not UTF-8: {error}") from error
    return [list[Cell](row) for row in csv.reader(io.StringIO(text, newline=""))]


class SheetLinkStore:
    """Downloads tabs of sheets shared as "anyone with the link can view", as CSV.

    The export link needs no credentials and no Google Cloud project, but
    gives no modification time: the version is a hash of the download. Each
    check therefore downloads the tab, and a read right after it reuses that
    download.
    """

    def __init__(self, session: requests.Session) -> None:
        self.session = session
        self.downloads: dict[str, bytes] = {}

    def download(self, collection: CollectionConfig) -> bytes:
        # Settings make sure of it with this store.
        if not collection.spreadsheet_id:
            raise StoreError(f"collection {collection.id!r} has no spreadsheet_id")
        params = {"format": "csv"}
        if collection.gid is not None:
            params["gid"] = str(collection.gid)
        url = EXPORT_URL.format(quote(collection.spreadsheet_id, safe=""))
        try:
            response = self.session.get(url, params=params, timeout=TIMEOUT_SECONDS, stream=True)
        except Exception as error:
            # The class name only: requests puts the URL, and so the sheet id, in the text.
            raise StoreError(f"Google is unreachable ({type(error).__name__})") from error
        with response:
            return self.body(response)

    @staticmethod
    def body(response: requests.Response) -> bytes:
        if response.status_code in (401, 403, 404):
            raise StoreError(
                f"Google answered {response.status_code}: no such sheet or tab, "
                "or the sheet is not shared by link"
            )
        if not response.ok:
            raise StoreError(f"Google answered {response.status_code}: {response.reason}")
        if not response.headers.get("Content-Type", "").startswith("text/csv"):
            # A private sheet sends the browser to a sign-in page instead.
            raise StoreError(
                'Google did not send CSV: share the sheet as "anyone with the link can view"'
            )
        data = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                data += chunk
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise StoreError(
                        f"the sheet is larger than {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB"
                    )
        except requests.RequestException as error:
            raise StoreError(f"Google is unreachable ({type(error).__name__})") from error
        return bytes(data)

    def version(self, collection: CollectionConfig) -> str:
        data = self.download(collection)
        self.downloads[collection.id] = data
        return hashlib.sha256(data).hexdigest()

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        data = self.downloads.pop(collection.id, None)
        if data is None:
            data = self.download(collection)
        return parse_csv(data, "the sheet")


class GoogleSheetsStore:
    """Reads tabs with a service account that the owner shared the spreadsheet with."""

    def __init__(self, session: requests.Session) -> None:
        self.session = session
        # Whether the service account may edit each collection's spreadsheet, by id.
        self.editable: dict[str, bool] = {}

    @classmethod
    def from_key_file(cls, credentials_file: Path) -> GoogleSheetsStore:
        load = service_account.Credentials.from_service_account_file
        credentials = load(str(credentials_file), scopes=SCOPES)  # type: ignore[no-untyped-call]
        return cls(AuthorizedSession(credentials))  # type: ignore[no-untyped-call]

    def get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        return self.call("GET", url, params)

    def call(
        self, method: str, url: str, params: dict[str, str], body: Any = None
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method, url, params=params, json=body, timeout=TIMEOUT_SECONDS
            )
        except Exception as error:
            # The class name only: requests puts the URL, and so the sheet id, in the text.
            raise StoreError(f"Google is unreachable ({type(error).__name__})") from error
        if not response.ok:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.reason
            error_type = StoreRefused if response.status_code == 403 else StoreError
            raise error_type(f"Google answered {response.status_code}: {message}")
        return cast(dict[str, Any], response.json())

    @staticmethod
    def tab(collection: CollectionConfig) -> tuple[str, str]:
        # Settings make sure of both with this store.
        if not (collection.spreadsheet_id and collection.sheet):
            raise StoreError(f"collection {collection.id!r} has no spreadsheet_id and sheet")
        return collection.spreadsheet_id, collection.sheet

    def version(self, collection: CollectionConfig) -> str:
        spreadsheet_id, _ = self.tab(collection)
        body = self.get(
            f"https://www.googleapis.com/drive/v3/files/{quote(spreadsheet_id)}",
            {"fields": "modifiedTime,capabilities/canEdit", "supportsAllDrives": "true"},
        )
        self.editable[collection.id] = body.get("capabilities", {}).get("canEdit") is True
        return str(body["modifiedTime"])

    def can_edit(self, collection: CollectionConfig) -> bool:
        return self.editable.get(collection.id, False)

    @staticmethod
    def quoted(sheet: str) -> str:
        """A tab name as the start of a range: 'It''s a tab'."""
        return "'{}'".format(sheet.replace("'", "''"))

    def values_url(self, collection: CollectionConfig) -> str:
        """The address of the collection's whole tab in the Sheets values API."""
        spreadsheet_id, sheet = self.tab(collection)
        tab = quote(self.quoted(sheet), safe="")
        return f"{SHEETS_URL.format(quote(spreadsheet_id))}/values/{tab}"

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        body = self.get(
            self.values_url(collection),
            {
                "valueRenderOption": "UNFORMATTED_VALUE",
                "dateTimeRenderOption": "SERIAL_NUMBER",
                "majorDimension": "ROWS",
            },
        )
        return cast(list[list[Cell]], body.get("values", []))

    @staticmethod
    def entered(cell: CellWrite) -> str | int | float:
        """A value as if typed into the cell, which then keeps its format."""
        match cell.value:
            case None:
                return ""
            case Decimal():
                return (
                    int(cell.value) if cell.value == cell.value.to_integral() else float(cell.value)
                )
            case date():
                # Read as a date whatever the sheet's locale.
                return cell.value.isoformat()
            case str():
                # The apostrophe keeps text as text: never a formula, number or date.
                return "'" + cell.value

    def write(self, collection: CollectionConfig, row: int, cells: list[CellWrite]) -> None:
        self.write_rows(collection, {row: cells})

    def write_rows(self, collection: CollectionConfig, rows: dict[int, list[CellWrite]]) -> None:
        spreadsheet_id, sheet = self.tab(collection)
        data = [
            {
                "range": f"{self.quoted(sheet)}!{column_name(cell.column)}{row}",
                "values": [[self.entered(cell)]],
            }
            for row, cells in rows.items()
            for cell in cells
        ]
        self.call(
            "POST",
            f"{SHEETS_URL.format(quote(spreadsheet_id))}/values:batchUpdate",
            {},
            {"valueInputOption": "USER_ENTERED", "data": data},
        )
        for row, cells in rows.items():
            self.format_numbers(collection, row, cells)

    def append(self, collection: CollectionConfig, cells: list[CellWrite]) -> int:
        by_column = {cell.column: cell for cell in cells}
        values = [
            self.entered(by_column.get(column, CellWrite(column, None)))
            for column in range(max(by_column, default=0) + 1)
        ]
        body = self.call(
            "POST",
            f"{self.values_url(collection)}:append",
            {"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            {"majorDimension": "ROWS", "values": [values]},
        )
        try:
            match = RANGE_ROW.match(str(body["updates"]["updatedRange"]).rsplit("!", 1)[-1])
        except (KeyError, TypeError):
            match = None
        if match is None:
            raise StoreError("Google did not say which row it added")
        row = int(match.group(1))
        self.format_numbers(collection, row, cells)
        return row

    def format_numbers(
        self, collection: CollectionConfig, row: int, cells: list[CellWrite]
    ) -> None:
        """Set the plain text format on the cells of plant numbers just written.

        The numbers are already written as text, so a failure here is logged, not
        raised: the write itself succeeded, and a retry must not write again.
        """
        numbers = [cell for cell in cells if cell.number and cell.value is not None]
        if not numbers:
            return
        try:
            self.set_text_format(collection, row, numbers)
        except StoreError as error:
            log.warning(
                "collection %s: row %d: number cell not formatted: %s", collection.id, row, error
            )

    def set_text_format(
        self, collection: CollectionConfig, row: int, numbers: list[CellWrite]
    ) -> None:
        spreadsheet_id, sheet = self.tab(collection)
        url = SHEETS_URL.format(quote(spreadsheet_id))
        body = self.get(url, {"fields": "sheets.properties(sheetId,title)"})
        sheet_ids = [
            tab["properties"]["sheetId"]
            for tab in body.get("sheets", [])
            if tab.get("properties", {}).get("title") == sheet
        ]
        if not sheet_ids:
            raise StoreError(f"the spreadsheet has no tab {sheet!r}")
        formats = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_ids[0],
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": cell.column,
                        "endColumnIndex": cell.column + 1,
                    },
                    "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
                    "fields": "userEnteredFormat.numberFormat",
                }
            }
            for cell in numbers
        ]
        self.call("POST", f"{url}:batchUpdate", {}, {"requests": formats})


class CsvFileStore:
    """Reads each collection from a CSV file laid out as a tab: a header row, then a plant per row.

    For the demo and for trying Square-Pot without a Google account. Every cell is
    text, as typed into a sheet; the file is read as UTF-8, with or without a
    byte order mark, and fields are separated by commas only. Editing the file
    is editing the sheet: the next sync sees it.
    """

    @staticmethod
    def load(collection: CollectionConfig) -> bytes:
        if collection.file is None:
            raise StoreError(f"collection {collection.id!r} has no file")
        try:
            return collection.file.read_bytes()
        except OSError as error:
            raise StoreError(f"cannot read {collection.file}: {error.strerror}") from error

    def version(self, collection: CollectionConfig) -> str:
        return hashlib.sha256(self.load(collection)).hexdigest()

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        return parse_csv(self.load(collection), collection.file)
