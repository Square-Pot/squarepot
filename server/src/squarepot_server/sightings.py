# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sightings: when each plant was last seen (ADR 0008).

They are kept in the database and, when photos are stored, also as small
JSON files next to them, so that losing the server loses none of them.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.api.models import Sighting, SightingOutcome
from squarepot_server.db import PlantRow, SightingRow
from squarepot_server.photos.storage import PhotoStorage
from squarepot_server.photos.summary import touch_plants

log = logging.getLogger(__name__)


class Sightings:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: PhotoStorage | None,
        # The syncer's lock: it guards the change sequence (see db.py).
        lock: threading.RLock,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.lock = lock
        self.clock = clock

    def record(self, sightings: list[Sighting]) -> list[SightingOutcome]:
        """Record each sighting of a plant that exists; the same id again changes nothing."""
        now = self.clock()
        outcomes = []
        added: list[SightingRow] = []
        with self.lock, self.sessions.begin() as session:
            numbers = set(
                session.scalars(
                    select(PlantRow.tag).where(
                        PlantRow.tag.in_({sighting.tag for sighting in sightings}),
                        ~PlantRow.removed,
                    )
                )
            )
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
            for tag in {row.tag for row in added}:
                touch_plants(session, tag)
        for row in added:
            self.copy(row)
        log.info("recorded %d sightings", len(added))
        return outcomes

    def copy(self, row: SightingRow) -> None:
        """Keep the sighting in the storage too; a failure only costs the copy."""
        if self.storage is None:
            return
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
