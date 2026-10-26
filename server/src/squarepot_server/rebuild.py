# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild the photo index and the sightings from the photo storage (ADR 0007, ADR 0008).

Each photo and each sighting has a JSON file in the storage. This adds to the
database every one it lacks, for example after the database was lost; it never
changes or removes what the database already holds. The choice of a plant's
main photo is not in the storage, so it falls back to the newest photo.

Usage, with the server's own settings (it may keep running):
    docker compose exec server python -m squarepot_server.rebuild
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.config import get_settings
from squarepot_server.db import PhotoRow, SightingRow, make_engine, next_seq
from squarepot_server.photos.storage import PhotoStorage, PhotoStorageError
from squarepot_server.photos.summary import touch_plants
from squarepot_server.runtime import photo_storage
from squarepot_server.sync import migrate

log = logging.getLogger(__name__)


@dataclass
class Counts:
    added: int = 0
    present: int = 0
    unreadable: int = 0


def moment(value: Any) -> datetime:
    return datetime.fromisoformat(str(value))


def photo_row(key: str, meta: dict[str, Any]) -> PhotoRow:
    stem = key.removesuffix(".json")
    return PhotoRow(
        id=str(meta["id"]),
        tag=str(meta["tag"]),
        seq=0,
        key=f"{stem}.jpg",
        thumbnail_key=f"{stem}.thumb.jpg",
        meta_key=key,
        taken_at=moment(meta["taken_at"]),
        taken_from=str(meta["taken_from"]),
        uploaded_at=moment(meta["uploaded_at"]),
        width=int(meta["width"]),
        height=int(meta["height"]),
        size=int(meta["size"]),
        comment=str(meta.get("comment") or ""),
        deleted_at=moment(meta["deleted_at"]) if meta.get("deleted_at") else None,
    )


def sighting_row(meta: dict[str, Any]) -> SightingRow:
    return SightingRow(
        id=str(meta["id"]),
        tag=str(meta["tag"]),
        seen_at=moment(meta["seen_at"]),
        kind=str(meta["kind"]),
        received_at=moment(meta["received_at"]),
    )


def rebuild(sessions: sessionmaker[Session], storage: PhotoStorage) -> tuple[Counts, Counts]:
    """Add the photos and sightings the database lacks; gives the counts of each."""
    photos, sightings = Counts(), Counts()
    for prefix, counts in (("photos/", photos), ("sightings/", sightings)):
        for key in storage.keys(prefix):
            if not key.endswith(".json"):
                continue
            try:
                meta = json.loads(storage.get(key))
                row: PhotoRow | SightingRow = (
                    photo_row(key, meta) if prefix == "photos/" else sighting_row(meta)
                )
            except (PhotoStorageError, ValueError, KeyError, TypeError) as error:
                log.warning("%s: skipped, %s", key, type(error).__name__)
                counts.unreadable += 1
                continue
            with sessions.begin() as session:
                if session.get(type(row), row.id) is not None:
                    counts.present += 1
                    continue
                if isinstance(row, PhotoRow):
                    row.seq = next_seq(session)
                session.add(row)
                session.flush()
                touch_plants(session, row.tag)
                counts.added += 1
    return photos, sightings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    storage = photo_storage(settings)
    if storage is None:
        print("Photos are not set up on this server: nothing to rebuild from.", file=sys.stderr)
        return 1
    engine = make_engine(settings.database_url)
    migrate(engine)
    try:
        photos, sightings = rebuild(sessionmaker(engine, expire_on_commit=False), storage)
    except PhotoStorageError as error:
        print(f"The photo storage cannot be listed: {error}.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    for name, counts in (("photos", photos), ("sightings", sightings)):
        print(
            f"{name}: {counts.added} added, {counts.present} already there, "
            f"{counts.unreadable} unreadable"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
