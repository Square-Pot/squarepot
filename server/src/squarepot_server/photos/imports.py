# SPDX-License-Identifier: AGPL-3.0-or-later
"""Batch imports, on the server's side (ADR 0008).

An upload is staged in the photo storage and queued. The import worker, a
process of its own, reads the label numbers (see importer.py). The server
then files each decoded photo through the same steps as an upload, under the
syncer's lock, so the change sequence keeps one writer (db.py). A photo with
no code, a number no plant has, or several numbers waits for the owner.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.db import ImportRow, PlantRow
from squarepot_server.photos.images import UnsupportedImage
from squarepot_server.photos.service import PhotoNotFound, Photos
from squarepot_server.photos.storage import PhotoStorage

log = logging.getLogger(__name__)
# Staged files are removed after this, filed or not.
STAGED_LAST = timedelta(days=30)


class ImportState(StrEnum):
    QUEUED = "queued"
    DECODING = "decoding"
    DECODED = "decoded"
    REVIEW = "review"
    FILED = "filed"
    DISCARDED = "discarded"


WAITING = (ImportState.QUEUED, ImportState.DECODING, ImportState.DECODED, ImportState.REVIEW)


class ImportNotFound(Exception):
    pass


class ImportClosed(Exception):
    """The photo was already filed or discarded."""


class Imports:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: PhotoStorage,
        photos: Photos,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.photos = photos
        self.clock = clock
        # Filing by the owner and by the chore take turns.
        self.filing = threading.Lock()

    def stage(self, import_id: UUID, data: bytes, file_time: datetime | None) -> ImportRow:
        """Keep the file and queue it; the same id again changes nothing."""
        with self.sessions.begin() as session:
            existing = session.get(ImportRow, str(import_id))
        if existing is not None:
            return existing
        key = f"staging/{import_id}"
        self.storage.put(key, data, "application/octet-stream")
        row = ImportRow(
            id=str(import_id),
            staged_key=key,
            file_time=file_time,
            uploaded_at=self.clock(),
            state=ImportState.QUEUED.value,
            numbers=[],
            reason=None,
            tag=None,
            decoded_at=None,
        )
        with self.sessions.begin() as session:
            session.add(row)
        return row

    def get(self, import_id: UUID) -> ImportRow:
        with self.sessions.begin() as session:
            row = session.get(ImportRow, str(import_id))
        if row is None:
            raise ImportNotFound(f"No imported photo {import_id}.")
        return row

    def waiting(self, state: ImportState | None = None) -> list[ImportRow]:
        """Photos not yet filed or discarded, oldest first; or those in one state."""
        states = [state] if state is not None else list(WAITING)
        with self.sessions.begin() as session:
            return list(
                session.scalars(
                    select(ImportRow)
                    .where(ImportRow.state.in_([state.value for state in states]))
                    .order_by(ImportRow.uploaded_at, ImportRow.id)
                )
            )

    def set_state(self, import_id: str, state: ImportState, **values: object) -> ImportRow:
        with self.sessions.begin() as session:
            row = session.get(ImportRow, import_id)
            assert row is not None
            row.state = state.value
            for name, value in values.items():
                setattr(row, name, value)
        return row

    def place(self, row: ImportRow, tag: str) -> ImportRow:
        """File the staged photo into the plant with this number, as an upload is."""
        data = self.storage.get(row.staged_key)
        self.photos.add(UUID(row.id), tag, data, row.file_time)
        self.storage.delete(row.staged_key)
        log.info("import %s: filed into %s", row.id, tag)
        return self.set_state(row.id, ImportState.FILED, tag=tag, reason=None)

    def file(self, import_id: UUID, tag: str) -> ImportRow:
        """The owner's choice of plant for a photo, whatever its codes said."""
        with self.filing:
            row = self.get(import_id)
            if row.state in (ImportState.FILED, ImportState.DISCARDED):
                raise ImportClosed(f"Imported photo {import_id} is already {row.state}.")
            return self.place(row, tag)

    def discard(self, import_id: UUID) -> ImportRow:
        with self.filing:
            row = self.get(import_id)
            if row.state == ImportState.FILED:
                raise ImportClosed(f"Imported photo {import_id} is already filed.")
            self.storage.delete(row.staged_key)
            return self.set_state(row.id, ImportState.DISCARDED)

    def file_decoded(self) -> int:
        """File each decoded photo with one known number; send the others to review."""
        filed = 0
        with self.filing:
            for row in self.waiting(ImportState.DECODED):
                with self.sessions.begin() as session:
                    known = set(
                        session.scalars(
                            select(PlantRow.tag).where(
                                PlantRow.tag.in_(row.numbers), ~PlantRow.removed
                            )
                        )
                    )
                if not row.numbers:
                    reason = "no_code"
                elif len(row.numbers) > 1:
                    reason = "several_numbers"
                elif row.numbers[0] not in known:
                    reason = "unknown_number"
                else:
                    try:
                        self.place(row, row.numbers[0])
                    except UnsupportedImage:
                        reason = "unreadable"
                    except PhotoNotFound:
                        # The plant left the sheet since the check above.
                        reason = "unknown_number"
                    else:
                        filed += 1
                        continue
                self.set_state(row.id, ImportState.REVIEW, reason=reason)
        return filed

    def purge(self) -> int:
        """Remove staged files older than STAGED_LAST; their photos are discarded."""
        cutoff = self.clock() - STAGED_LAST
        old = [row for row in self.waiting() if row.uploaded_at < cutoff]
        for row in old:
            self.storage.delete(row.staged_key)
            self.set_state(row.id, ImportState.DISCARDED, reason="expired")
        return len(old)
