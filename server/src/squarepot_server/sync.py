# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keeping the server's copy in step with the sheets (ADR 0003)."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.api.models import FieldSchema
from squarepot_server.config import CollectionConfig
from squarepot_server.db import (
    CollectionRow,
    PlantRow,
    RegisteredTag,
    get_meta,
    next_seq,
    set_meta,
)
from squarepot_server.fields import Issue, ParsedTab, Row, TabError, parse_tab
from squarepot_server.store import CollectionStore, StoreError

log = logging.getLogger(__name__)
MIGRATIONS = Path(__file__).with_name("migrations")
UNEXPECTED_ERROR = "unexpected error while syncing; see the server log"


def migrate(engine: Engine) -> None:
    """Bring the database schema up to date."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def plant_ids(collection_id: str, rows: list[Row]) -> list[str]:
    """Ids that stay the same across syncs as long as a row can be matched.

    A row with a number is matched by it, wherever it moves in the sheet. A row
    without one is matched by its contents, so editing it gives it a new id.
    """
    tags = Counter(row.tag for row in rows if row.tag)
    taken: Counter[str] = Counter()
    ids = []
    for row in rows:
        if row.tag and tags[row.tag] == 1:
            base = f"{collection_id}:{row.tag}"
        elif row.tag:
            base = f"{collection_id}:{row.tag}:row{row.row}"
        else:
            content = json.dumps(row.fields, sort_keys=True).encode()
            base = f"{collection_id}:h{hashlib.sha256(content).hexdigest()[:16]}"
        taken[base] += 1
        ids.append(base if taken[base] == 1 else f"{base}:{taken[base]}")
    return ids


def fields_fingerprint(schema: FieldSchema) -> str:
    """Changes whenever the way rows are read changes, even within one schema version."""
    fields = [field.model_dump(mode="json") for field in schema.fields]
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


class Syncer:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        store: CollectionStore,
        schema: FieldSchema,
        collections: list[CollectionConfig],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.store = store
        self.schema = schema
        self.collections = collections
        self.clock = clock

    def prepare(self) -> None:
        """Set up server-wide state, and drop collections no longer configured."""
        with self.sessions.begin() as session:
            if get_meta(session, "epoch") is None:
                set_meta(session, "epoch", secrets.token_hex(8))
            if get_meta(session, "schema_version") != str(self.schema.version):
                # Field keys may have changed: re-read every sheet, and clients get a full copy.
                set_meta(session, "schema_version", str(self.schema.version))
                session.execute(update(CollectionRow).values(store_version=None))
            fields = fields_fingerprint(self.schema)
            if get_meta(session, "schema_fields") != fields:
                # A field was added or its rules changed: re-read every sheet, and
                # clients get the differences as usual.
                set_meta(session, "schema_fields", fields)
                session.execute(update(CollectionRow).values(store_version=None))
            configured = {collection.id for collection in self.collections}
            for row in session.scalars(select(CollectionRow).where(~CollectionRow.removed)):
                if row.id not in configured:
                    self.remove_collection(session, row)

    def run_once(self) -> None:
        self.prepare()
        for collection in self.collections:
            try:
                self.sync_collection(collection)
            except Exception:
                # One collection's bug must not stop the others from syncing.
                log.exception("collection %s: sync failed", collection.id)
                self.record_failure(collection)

    def record_failure(self, collection: CollectionConfig) -> None:
        with self.sessions.begin() as session:
            row = session.get(CollectionRow, collection.id)
            if row is None:
                row = CollectionRow(id=collection.id, name=collection.name, seq=0, issues=[])
                session.add(row)
            if row.error != UNEXPECTED_ERROR or row.removed:
                row.removed = False
                row.error = UNEXPECTED_ERROR
                row.seq = next_seq(session)

    def sync_collection(self, collection: CollectionConfig) -> None:
        with self.sessions.begin() as session:
            row = session.get(CollectionRow, collection.id)
            if row is None:
                row = CollectionRow(id=collection.id, name=collection.name, seq=0, issues=[])
                session.add(row)
            row.removed = False
            row.name = collection.name
            try:
                version = self.store.version(collection)
                if version != row.store_version or row.error is not None:
                    parsed = parse_tab(self.schema, self.store.read(collection))
                    self.apply(session, collection.id, parsed)
                    row.store_version = version
                    row.plant_count = len(parsed.rows)
                    row.issues = [issue_json(issue) for issue in parsed.issues]
                    row.custom_columns = parsed.custom_columns
                row.error = None
                row.synced_at = self.clock()
            except (StoreError, TabError) as error:
                log.warning("collection %s: %s", collection.id, error)
                row.error = str(error)
            if session.is_modified(row):
                row.seq = next_seq(session)

    def apply(self, session: Session, collection_id: str, parsed: ParsedTab) -> None:
        existing = {
            plant.id: plant
            for plant in session.scalars(
                select(PlantRow).where(PlantRow.collection_id == collection_id)
            )
        }
        seen = set()
        for plant_id, row in zip(plant_ids(collection_id, parsed.rows), parsed.rows, strict=True):
            seen.add(plant_id)
            plant = existing.get(plant_id)
            if plant is None:
                session.add(
                    PlantRow(
                        id=plant_id,
                        collection_id=collection_id,
                        seq=next_seq(session),
                        tag=row.tag,
                        row=row.row,
                        fields=row.fields,
                        custom=row.custom,
                    )
                )
                continue
            if not plant.removed and (plant.tag, plant.row, plant.fields, plant.custom) == (
                row.tag,
                row.row,
                row.fields,
                row.custom,
            ):
                continue
            plant.tag, plant.row, plant.fields, plant.custom = (
                row.tag,
                row.row,
                row.fields,
                row.custom,
            )
            plant.removed = False
            plant.seq = next_seq(session)
        for plant_id, plant in existing.items():
            if plant_id not in seen and not plant.removed:
                plant.removed = True
                plant.seq = next_seq(session)

        tags = [row.tag for row in parsed.rows if row.tag] + parsed.skipped_tags
        self.register(session, collection_id, tags, parsed)

    def register(
        self, session: Session, collection_id: str, tags: list[str], parsed: ParsedTab
    ) -> None:
        """Record the collection's numbers, and report collisions (ADR 0002)."""
        for tag, count in Counter(tags).items():
            if count > 1:
                parsed.issues.append(Issue(0, "", f"number {tag} is used by {count} rows"))
            registered = session.get(RegisteredTag, tag)
            if registered is None:
                session.add(
                    RegisteredTag(tag=tag, collection_id=collection_id, registered_at=self.clock())
                )
            elif registered.collection_id != collection_id:
                owner = session.get(CollectionRow, registered.collection_id)
                if owner is not None and not owner.removed:
                    parsed.issues.append(
                        Issue(0, "", f"number {tag} is also used in collection {owner.id}")
                    )

    def remove_collection(self, session: Session, row: CollectionRow) -> None:
        row.removed = True
        # If it is configured again, its tab is read afresh to bring its plants back.
        row.store_version = None
        row.seq = next_seq(session)
        plants = select(PlantRow).where(PlantRow.collection_id == row.id, ~PlantRow.removed)
        for plant in session.scalars(plants):
            plant.removed = True
            plant.seq = next_seq(session)


def issue_json(issue: Issue) -> dict[str, Any]:
    return {"row": issue.row, "column": issue.column, "message": issue.message}


class SyncWorker:
    """Runs the syncer in a background thread, every `interval` seconds."""

    def __init__(self, syncer: Syncer, interval: float) -> None:
        self.syncer = syncer
        self.interval = interval
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="sync", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()
        self.thread.join()

    def loop(self) -> None:
        while not self.stopped.is_set():
            try:
                self.syncer.run_once()
            except Exception:
                log.exception("sync failed")
            self.stopped.wait(self.interval)
