# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sightings: when each plant was last seen (ADR 0008).

They are kept in the database and also as small JSON files next to the
photos, so that losing the server loses none of them. Without a photo storage
none are recorded (ADR 0003: the server holds no data that exists nowhere else).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.api.models import Sighting, SightingOutcome
from squarepot_server.db import PlantRow, SightingRow
from squarepot_server.photos.storage import PhotoStorage
from squarepot_server.photos.summary import touch_plants

log = logging.getLogger(__name__)

# How often a sighting of a number not in the copy may make the server read the sheets.
REFRESH_EVERY = timedelta(minutes=1)


class Sightings:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: PhotoStorage,
        # The syncer's lock: it guards the change sequence (see db.py).
        lock: threading.RLock,
        # Reads the sheets again, for numbers added there since the last sync.
        refresh: Callable[[], None] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.lock = lock
        self.refresh = refresh
        self.clock = clock
        self.refreshed_at: datetime | None = None

    def record(self, sightings: list[Sighting]) -> list[SightingOutcome]:
        """Record each sighting of a plant that exists; the same id again changes nothing.

        A number not in the copy makes the server read the sheets first, at most once
        every REFRESH_EVERY, so a plant just added to the sheet is found.
        """
        now = self.clock()
        tags = {sighting.tag for sighting in sightings}
        outcomes: list[SightingOutcome] = []
        added: list[SightingRow] = []
        with self.lock:
            if tags - self.known(tags) and self.may_refresh(now):
                assert self.refresh is not None
                self.refresh()
            with self.sessions.begin() as session:
                numbers = known_numbers(session, tags)
                for tag in self.record_in(session, sightings, numbers, now, outcomes, added):
                    touch_plants(session, tag)
        for row in added:
            self.copy(row)
        log.info("recorded %d sightings", len(added))
        return outcomes

    def known(self, tags: set[str]) -> set[str]:
        with self.sessions() as session:
            return known_numbers(session, tags)

    def may_refresh(self, now: datetime) -> bool:
        if self.refresh is None:
            return False
        if self.refreshed_at is not None and now - self.refreshed_at < REFRESH_EVERY:
            return False
        self.refreshed_at = now
        return True

    def record_in(
        self,
        session: Session,
        sightings: list[Sighting],
        numbers: set[str],
        now: datetime,
        outcomes: list[SightingOutcome],
        added: list[SightingRow],
    ) -> set[str]:
        """Add the new sightings to the session; gives the numbers seen."""
        for sighting in sightings:
            if session.get(SightingRow, str(sighting.id)) is not None:
                outcomes.append(SightingOutcome.ALREADY_RECORDED)
            elif sighting.tag not in numbers:
                outcomes.append(SightingOutcome.UNKNOWN_NUMBER)
            else:
                row = SightingRow(
                    id=str(sighting.id),
                    tag=sighting.tag,
                    seen_at=min(sighting.seen_at, now).astimezone(UTC),
                    kind=sighting.kind.value,
                    received_at=now,
                )
                session.add(row)
                session.flush()
                added.append(row)
                outcomes.append(SightingOutcome.RECORDED)
        return {row.tag for row in added}

    def copy(self, row: SightingRow) -> None:
        """Keep the sighting in the storage too; a failure only costs the copy."""
        meta = {
            "id": row.id,
            "tag": row.tag,
            "seen_at": row.seen_at.isoformat(),
            "kind": row.kind,
            "received_at": row.received_at.isoformat(),
        }
        key = f"sightings/{row.tag}/{row.seen_at:%Y-%m-%dT%H-%M-%SZ}_{row.id}.json"
        try:
            self.storage.put(key, json.dumps(meta, indent=2).encode(), "application/json")
        except Exception:
            log.exception("sighting %s: not copied to the storage", row.id)


def known_numbers(session: Session, tags: set[str]) -> set[str]:
    """The numbers in `tags` that a plant in the copy has."""
    return set(
        session.scalars(select(PlantRow.tag).where(PlantRow.tag.in_(tags), ~PlantRow.removed))
    )


def last_sightings(session: Session, tags: Iterable[str]) -> dict[str, datetime]:
    """When each number in `tags` was last seen, by sightings alone."""
    wanted = sorted(set(tags))
    if not wanted:
        return {}
    rows = session.execute(
        select(SightingRow.tag, func.max(SightingRow.seen_at))
        .where(SightingRow.tag.in_(wanted))
        .group_by(SightingRow.tag)
    ).all()
    # max() keeps the column's type, which gives the time back in UTC.
    return {tag: seen_at for tag, seen_at in rows}
