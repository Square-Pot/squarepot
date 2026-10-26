# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import worker: reads the label numbers in staged photos, one at a time (ADR 0008).

It runs beside the server, in a container of its own with half a core and
512 MB (deploy/compose.import.yaml), and only decodes: it never files a photo
or takes a change number, so the server stays the one writer of the change
sequence (db.py). Each change of state here is conditional, so the owner
filing or discarding a photo meanwhile wins.

Usage, with the server's settings:
    python -m squarepot_server.importer
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from types import FrameType

from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.config import get_settings
from squarepot_server.db import ImportRow, make_engine
from squarepot_server.photos.codes import read_numbers
from squarepot_server.photos.images import UnsupportedImage
from squarepot_server.photos.imports import ImportState
from squarepot_server.photos.storage import PhotoStorage, PhotoStorageError
from squarepot_server.runtime import photo_storage

log = logging.getLogger(__name__)
IDLE_SECONDS = 5.0


class Importer:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: PhotoStorage,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.clock = clock

    def move(self, import_id: str, old: ImportState, new: ImportState, **values: object) -> bool:
        """Change the state only if it is still `old`; whether it was."""
        with self.sessions.begin() as session:
            result = session.execute(
                update(ImportRow)
                .where(ImportRow.id == import_id, ImportRow.state == old.value)
                .values(state=new.value, **values)
            )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def recover(self) -> None:
        """Queue again what a stopped worker left half done."""
        with self.sessions.begin() as session:
            session.execute(
                update(ImportRow)
                .where(ImportRow.state == ImportState.DECODING.value)
                .values(state=ImportState.QUEUED.value)
            )

    def claim(self) -> ImportRow | None:
        """The oldest queued photo, now marked as being decoded."""
        while True:
            with self.sessions.begin() as session:
                row = session.scalars(
                    select(ImportRow)
                    .where(ImportRow.state == ImportState.QUEUED.value)
                    .order_by(ImportRow.uploaded_at, ImportRow.id)
                    .limit(1)
                ).first()
            if row is None:
                return None
            if self.move(row.id, ImportState.QUEUED, ImportState.DECODING):
                return row

    def run_once(self) -> bool:
        """Decode one queued photo; whether there was one."""
        row = self.claim()
        if row is None:
            return False
        try:
            numbers = read_numbers(self.storage.get(row.staged_key))
        except UnsupportedImage:
            self.move(row.id, ImportState.DECODING, ImportState.REVIEW, reason="unreadable")
        except PhotoStorageError as error:
            log.warning("import %s: not read from the storage: %s", row.id, error)
            self.move(row.id, ImportState.DECODING, ImportState.QUEUED)
            return False
        else:
            self.move(
                row.id,
                ImportState.DECODING,
                ImportState.DECODED,
                numbers=numbers,
                decoded_at=self.clock(),
            )
            log.info("import %s: %d numbers read", row.id, len(numbers))
        return True

    def run(self, stopped: threading.Event) -> None:
        self.recover()
        while not stopped.is_set():
            try:
                busy = self.run_once()
            except Exception:
                log.exception("import worker failed")
                busy = False
            if not busy:
                stopped.wait(IDLE_SECONDS)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = get_settings()
    storage = photo_storage(settings)
    if storage is None:
        print("Photos are not set up on this server: nothing to import into.", file=sys.stderr)
        return 1
    engine = make_engine(settings.database_url)
    stopped = threading.Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # The server migrates the database; wait for it rather than race it.
    while not stopped.is_set() and not inspect(engine).has_table("imports"):
        log.info("waiting for the server to create the imports table")
        stopped.wait(IDLE_SECONDS)
    Importer(sessionmaker(engine, expire_on_commit=False), storage).run(stopped)
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
