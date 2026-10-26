# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plant photos: files in the photo storage, indexed in the database (ADR 0007).

Next to each photo the storage keeps a small JSON file that repeats what the
index holds, so that the index can be rebuilt from the storage alone.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.api.models import Photo, PhotoChange, TakenFrom
from squarepot_server.db import MainPhoto, PhotoRow, PlantRow, next_seq
from squarepot_server.photos.images import process, resolve_time
from squarepot_server.photos.storage import PhotoStorage
from squarepot_server.photos.summary import touch_plants

log = logging.getLogger(__name__)
URLS_LAST = timedelta(hours=6)
KEPT_AFTER_DELETE = timedelta(days=30)


class PhotoNotFound(Exception):
    pass


class PhotoIdTaken(Exception):
    """The id is already the id of a photo of another plant."""


class Photos:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: PhotoStorage,
        # The syncer's lock: it guards the change sequence (see db.py).
        lock: threading.RLock,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.lock = lock
        self.clock = clock
        # One photo is processed at a time, to keep memory low on a small host.
        self.processing = threading.Lock()

    def has_plant(self, session: Session, tag: str) -> bool:
        query = select(PlantRow.id).where(PlantRow.tag == tag, ~PlantRow.removed).limit(1)
        return session.scalar(query) is not None

    def add(self, photo_id: UUID, tag: str, data: bytes, client_time: datetime | None) -> PhotoRow:
        """Store a photo of the plant with this number; the same id again changes nothing."""
        with self.sessions.begin() as session:
            existing = session.get(PhotoRow, str(photo_id))
            plant = self.has_plant(session, tag)
        if existing is not None:
            if existing.tag != tag:
                raise PhotoIdTaken(f"Photo {photo_id} is a photo of another plant.")
            return existing
        if not plant:
            raise PhotoNotFound(f"No plant has the number {tag}.")
        with self.processing:
            processed = process(data)
        now = self.clock()
        taken_at, taken_from = resolve_time(processed.taken_at, client_time, now)
        stem = f"photos/{tag}/{taken_at:%Y-%m-%dT%H-%M-%SZ}_{photo_id}"
        row = PhotoRow(
            id=str(photo_id),
            tag=tag,
            seq=0,
            key=f"{stem}.jpg",
            thumbnail_key=f"{stem}.thumb.jpg",
            meta_key=f"{stem}.json",
            taken_at=taken_at,
            taken_from=taken_from,
            uploaded_at=now,
            width=processed.width,
            height=processed.height,
            size=len(processed.large),
            comment="",
            deleted_at=None,
        )
        self.storage.put(row.key, processed.large, "image/jpeg")
        self.storage.put(row.thumbnail_key, processed.thumbnail, "image/jpeg")
        self.write_meta(row)
        with self.lock, self.sessions.begin() as session:
            row.seq = next_seq(session)
            session.add(row)
            touch_plants(session, tag)
        log.info("plant %s: photo %s added", tag, photo_id)
        return row

    def write_meta(self, row: PhotoRow) -> None:
        meta = {
            "id": row.id,
            "tag": row.tag,
            "taken_at": row.taken_at.isoformat(),
            "taken_from": row.taken_from,
            "uploaded_at": row.uploaded_at.isoformat(),
            "width": row.width,
            "height": row.height,
            "size": row.size,
            "comment": row.comment,
            "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        }
        data = json.dumps(meta, ensure_ascii=False, indent=2).encode()
        self.storage.put(row.meta_key, data, "application/json")

    def get(self, photo_id: UUID) -> PhotoRow:
        with self.sessions.begin() as session:
            row = session.get(PhotoRow, str(photo_id))
        if row is None:
            raise PhotoNotFound(f"No photo {photo_id}.")
        return row

    def update(self, photo_id: UUID, apply: Callable[[PhotoRow], None]) -> PhotoRow:
        """Change a photo in the index and in its JSON file in the storage."""
        with self.lock, self.sessions.begin() as session:
            row = session.get(PhotoRow, str(photo_id))
            if row is None:
                raise PhotoNotFound(f"No photo {photo_id}.")
            apply(row)
            if session.is_modified(row):
                row.seq = next_seq(session)
                touch_plants(session, row.tag)
                self.write_meta(row)
        return row

    def change(self, photo_id: UUID, change: PhotoChange) -> PhotoRow:
        def apply(row: PhotoRow) -> None:
            if change.comment is not None:
                row.comment = change.comment.strip()
            if change.taken_at is not None:
                row.taken_at = change.taken_at.astimezone(UTC)
                row.taken_from = TakenFrom.OWNER

        return self.update(photo_id, apply)

    def delete(self, photo_id: UUID) -> PhotoRow:
        now = self.clock()

        def apply(row: PhotoRow) -> None:
            if row.deleted_at is None:
                row.deleted_at = now

        return self.update(photo_id, apply)

    def restore(self, photo_id: UUID) -> PhotoRow:
        def apply(row: PhotoRow) -> None:
            row.deleted_at = None

        return self.update(photo_id, apply)

    def of_plant(self, tag: str, deleted: bool = False) -> tuple[list[PhotoRow], str | None]:
        """A plant's photos in the order they were taken, and the id of its main photo."""
        query = select(PhotoRow).where(PhotoRow.tag == tag).order_by(PhotoRow.taken_at, PhotoRow.id)
        if not deleted:
            query = query.where(PhotoRow.deleted_at.is_(None))
        with self.sessions.begin() as session:
            rows = list(session.scalars(query))
            plant = self.has_plant(session, tag)
            chosen = session.get(MainPhoto, tag)
        if not plant and not rows:
            raise PhotoNotFound(f"No plant has the number {tag}.")
        shown = [row for row in rows if row.deleted_at is None]
        ids = {row.id for row in shown}
        main = chosen.photo_id if chosen is not None and chosen.photo_id in ids else None
        if main is None and shown:
            main = shown[-1].id
        return rows, main

    def choose_main(self, tag: str, photo_id: UUID | None) -> None:
        with self.lock, self.sessions.begin() as session:
            chosen = session.get(MainPhoto, tag)
            touch_plants(session, tag)
            if photo_id is None:
                if chosen is not None:
                    session.delete(chosen)
                return
            row = session.get(PhotoRow, str(photo_id))
            if row is None or row.tag != tag or row.deleted_at is not None:
                raise PhotoNotFound(f"Plant {tag} has no photo {photo_id}.")
            if chosen is None:
                session.add(MainPhoto(tag=tag, photo_id=row.id))
            else:
                chosen.photo_id = row.id

    def to_api(self, row: PhotoRow, main: str | None) -> Photo:
        expires_at = self.clock() + URLS_LAST
        return Photo(
            id=UUID(row.id),
            tag=row.tag,
            taken_at=row.taken_at,
            taken_from=TakenFrom(row.taken_from),
            uploaded_at=row.uploaded_at,
            width=row.width,
            height=row.height,
            comment=row.comment,
            main=row.id == main,
            deleted_at=row.deleted_at,
            url=self.storage.url(row.key, expires_at),
            thumbnail_url=self.storage.url(row.thumbnail_key, expires_at),
            urls_expire_at=expires_at,
        )

    def purge(self) -> int:
        """Remove the files and the index entry of photos deleted more than 30 days ago."""
        cutoff = self.clock() - KEPT_AFTER_DELETE
        with self.sessions.begin() as session:
            rows = list(session.scalars(select(PhotoRow).where(PhotoRow.deleted_at < cutoff)))
        for row in rows:
            for key in (row.key, row.thumbnail_key, row.meta_key):
                self.storage.delete(key)
            with self.lock, self.sessions.begin() as session:
                chosen = session.get(MainPhoto, row.tag)
                if chosen is not None and chosen.photo_id == row.id:
                    session.delete(chosen)
                session.execute(delete(PhotoRow).where(PhotoRow.id == row.id))
        return len(rows)
