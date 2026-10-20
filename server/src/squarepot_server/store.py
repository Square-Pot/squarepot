# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where collections are stored: the CollectionStore interface (ADR 0003), Sheets and CSV files."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import quote

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from squarepot_server.config import CollectionConfig
from squarepot_server.fields import Cell

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]
TIMEOUT_SECONDS = 30
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{}/export"
# A tab of plants is about 100 bytes a row; more than this is not a collection.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


class StoreError(Exception):
    """The store could not be reached or refused the request."""


class CollectionStore(Protocol):
    def version(self, collection: CollectionConfig) -> str:
        """A value that changes whenever the collection's data may have changed; cheap to get."""
        ...

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        """Every row of the collection's tab, header first."""
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

    @classmethod
    def from_key_file(cls, credentials_file: Path) -> GoogleSheetsStore:
        load = service_account.Credentials.from_service_account_file
        credentials = load(str(credentials_file), scopes=SCOPES)  # type: ignore[no-untyped-call]
        return cls(AuthorizedSession(credentials))  # type: ignore[no-untyped-call]

    def get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self.session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except Exception as error:
            # The class name only: requests puts the URL, and so the sheet id, in the text.
            raise StoreError(f"Google is unreachable ({type(error).__name__})") from error
        if not response.ok:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.reason
            raise StoreError(f"Google answered {response.status_code}: {message}")
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
            {"fields": "modifiedTime", "supportsAllDrives": "true"},
        )
        return str(body["modifiedTime"])

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        spreadsheet_id, sheet = self.tab(collection)
        sheet = sheet.replace("'", "''")
        body = self.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}"
            f"/values/{quote(f"'{sheet}'", safe='')}",
            {
                "valueRenderOption": "UNFORMATTED_VALUE",
                "dateTimeRenderOption": "SERIAL_NUMBER",
                "majorDimension": "ROWS",
            },
        )
        return cast(list[list[Cell]], body.get("values", []))


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
