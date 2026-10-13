# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a running server holds: settings, schema, database and the sync worker."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.api.models import FieldSchema
from squarepot_server.config import CollectionConfig, Settings, StoreKind
from squarepot_server.db import make_engine
from squarepot_server.fields import Cell, load_schema
from squarepot_server.store import CollectionStore, CsvFileStore, GoogleSheetsStore, StoreError
from squarepot_server.sync import Syncer, SyncWorker, migrate

log = logging.getLogger(__name__)


class UnavailableStore:
    """Stands in for Google Sheets while the key is missing or unusable.

    The server still starts and serves its last copy, and every collection
    reports the reason as its sync error.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def version(self, collection: CollectionConfig) -> str:
        raise StoreError(self.reason)

    def read(self, collection: CollectionConfig) -> list[list[Cell]]:
        raise StoreError(self.reason)


def google_store(credentials_file: Path | None) -> CollectionStore:
    if credentials_file is None:
        return UnavailableStore("SQUAREPOT_GOOGLE_CREDENTIALS_FILE is not set")
    try:
        return GoogleSheetsStore.from_key_file(credentials_file)
    except (OSError, ValueError) as error:
        log.error("cannot use the service account key %s: %s", credentials_file, error)
        return UnavailableStore(f"the service account key cannot be used: {error}")


@dataclass
class Runtime:
    settings: Settings
    schema: FieldSchema
    engine: Engine
    sessions: sessionmaker[Session]
    syncer: Syncer
    worker: SyncWorker | None

    @classmethod
    def start(cls, settings: Settings, store: CollectionStore | None = None) -> Runtime:
        url = make_url(settings.database_url)
        if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = make_engine(settings.database_url)
        migrate(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        schema = load_schema(settings.schema_file)
        if store is None and settings.store == StoreKind.FILE:
            store = CsvFileStore()
        elif store is None:
            store = google_store(settings.google_credentials_file)
        syncer = Syncer(sessions, store, schema, settings.collections)
        syncer.prepare()
        worker = None
        if settings.sync_interval_seconds > 0:
            worker = SyncWorker(syncer, settings.sync_interval_seconds)
            worker.start()
        return cls(settings, schema, engine, sessions, syncer, worker)

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.engine.dispose()
