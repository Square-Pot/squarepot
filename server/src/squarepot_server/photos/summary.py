# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a plant shows of its photos: how many, the newest, and the main one (ADR 0007)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from squarepot_server.db import MainPhoto, PhotoRow, PlantRow, next_seq


@dataclass(frozen=True)
class PhotoSummary:
    count: int
    # When the newest photo was taken.
    last: datetime
    main_id: str


def summaries(session: Session, tags: Iterable[str]) -> dict[str, PhotoSummary]:
    """The summary of every number in `tags` that has photos not deleted."""
    wanted = sorted(set(tags))
    if not wanted:
        return {}
    rows = session.execute(
        select(PhotoRow.id, PhotoRow.tag, PhotoRow.taken_at)
        .where(PhotoRow.tag.in_(wanted), PhotoRow.deleted_at.is_(None))
        .order_by(PhotoRow.tag, PhotoRow.taken_at, PhotoRow.id)
    ).all()
    chosen = dict(
        session.execute(
            select(MainPhoto.tag, MainPhoto.photo_id).where(MainPhoto.tag.in_(wanted))
        ).all()
    )
    by_tag: dict[str, list[tuple[str, datetime]]] = {}
    for photo_id, tag, taken_at in rows:
        by_tag.setdefault(tag, []).append((photo_id, taken_at))
    result = {}
    for tag, photos in by_tag.items():
        ids = {photo_id for photo_id, _ in photos}
        newest_id, newest_at = photos[-1]
        main_id = chosen[tag] if chosen.get(tag) in ids else newest_id
        result[tag] = PhotoSummary(len(photos), newest_at, main_id)
    return result


def touch_plants(session: Session, tag: str) -> None:
    """Send the plants with this number again in the next sync: their photos changed."""
    session.execute(
        update(PlantRow).where(PlantRow.tag == tag, ~PlantRow.removed).values(seq=next_seq(session))
    )
