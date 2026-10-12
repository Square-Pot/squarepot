# SPDX-License-Identifier: AGPL-3.0-or-later
"""The server's database: its copy of every collection, and server-only state.

Every change to a collection or plant takes the next value of a single change
sequence (`seq`). A sync cursor is a position in that sequence, so the changes
since a cursor are the rows with a greater `seq`. Removed rows are kept as
tombstones (`removed`), so that removals can be synced too.

The sequence is safe because there is one writer: the sync worker of a single
server process. Running several server processes on one database would need a
database sequence instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    Text,
    TypeDecorator,
    create_engine,
    event,
)
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class UTCDateTime(TypeDecorator[datetime]):
    """A timezone-aware UTC datetime, also on SQLite, which drops the zone."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UTCDateTime,
        dict[str, Any]: JSON,
        list[Any]: JSON,
    }


class Meta(Base):
    """Server-wide values: `epoch`, `seq` and `schema_version`."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class CollectionRow(Base):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(index=True)
    removed: Mapped[bool] = mapped_column(default=False)
    # The store's version of the data this copy was read from (ADR 0003).
    store_version: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)
    plant_count: Mapped[int] = mapped_column(default=0)
    # Per-cell problems of the last read, as {"row", "column", "message"} objects.
    issues: Mapped[list[Any]] = mapped_column(default=list)


class PlantRow(Base):
    __tablename__ = "plants"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    seq: Mapped[int] = mapped_column(index=True)
    removed: Mapped[bool] = mapped_column(default=False)
    tag: Mapped[str | None] = mapped_column(String(6), index=True)
    row: Mapped[int]
    fields: Mapped[dict[str, Any]]


class RegisteredTag(Base):
    """Every number issued or seen in a sheet; never reused (ADR 0002)."""

    __tablename__ = "registered_tags"

    tag: Mapped[str] = mapped_column(String(6), primary_key=True)
    collection_id: Mapped[str] = mapped_column(String(64))
    registered_at: Mapped[datetime]


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure(connection: Any, record: Any) -> None:
        # Readers do not block the sync worker's writes, and a busy database is waited for.
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_meta(session: Session, key: str) -> str | None:
    row = session.get(Meta, key)
    return row.value if row else None


def set_meta(session: Session, key: str, value: str) -> None:
    session.merge(Meta(key=key, value=value))


def current_seq(session: Session) -> int:
    return int(get_meta(session, "seq") or 0)


def next_seq(session: Session) -> int:
    seq = current_seq(session) + 1
    set_meta(session, "seq", str(seq))
    return seq
