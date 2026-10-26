# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a running server holds: settings, schema, database and the sync worker."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import requests
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from squarepot_server.api.models import FieldSchema
from squarepot_server.backoff import Backoff
from squarepot_server.config import CollectionConfig, PhotoStoreKind, Settings, StoreKind
from squarepot_server.db import make_engine
from squarepot_server.fields import Cell, load_schema
from squarepot_server.photos.service import Photos
from squarepot_server.photos.storage import (
    DiskStorage,
    PhotoStorage,
    S3Storage,
    Signer,
    read_key_file,
)
from squarepot_server.sightings import Sightings
from squarepot_server.store import (
    CollectionStore,
    CsvFileStore,
    GoogleSheetsStore,
    SheetLinkStore,
    StoreError,
)
from squarepot_server.sync import Syncer, SyncWorker, migrate

log = logging.getLogger(__name__)
PHOTO_FILES_ROUTE = "/api/v1/photo-files"


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


def photo_storage(settings: Settings) -> PhotoStorage | None:
    """The configured photo storage, or None when photos are off or cannot be stored."""
    if settings.photos == PhotoStoreKind.DISK:
        token = settings.api_token.get_secret_value().encode()
        secret = hashlib.sha256(b"squarepot photo files\n" + token).digest()
        return DiskStorage(settings.photos_dir, secret, PHOTO_FILES_ROUTE)
    if settings.photos == PhotoStoreKind.S3 and settings.s3_key_file and settings.s3_bucket:
        try:
            key_id, secret_key = read_key_file(settings.s3_key_file)
        except (OSError, ValueError) as error:
            # The message names the file, never its contents.
            log.error("photos are off: cannot use the key file %s: %s", settings.s3_key_file, error)
            return None
        signer = Signer(key_id, secret_key, settings.s3_region)
        base_url = f"{settings.s3_endpoint.rstrip('/')}/{settings.s3_bucket}"
        return S3Storage(requests.Session(), base_url, signer)
    return None


@dataclass
class Runtime:
    settings: Settings
    schema: FieldSchema
    engine: Engine
    sessions: sessionmaker[Session]
    syncer: Syncer
    worker: SyncWorker | None
    photos: Photos | None = None
    sightings: Sightings | None = None
    backoff: Backoff = field(default_factory=Backoff)

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
        elif store is None and settings.store == StoreKind.LINK:
            store = SheetLinkStore(requests.Session())
        elif store is None:
            store = google_store(settings.google_credentials_file)
        syncer = Syncer(sessions, store, schema, settings.collections)
        syncer.prepare()
        storage = photo_storage(settings)
        photos = Photos(sessions, storage, syncer.lock) if storage is not None else None
        worker = None
        if settings.sync_interval_seconds > 0:
            chores = [photos.purge] if photos is not None else []
            worker = SyncWorker(syncer, settings.sync_interval_seconds, chores)
            worker.start()
        sightings = Sightings(sessions, storage, syncer.lock)
        return cls(settings, schema, engine, sessions, syncer, worker, photos, sightings)

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.engine.dispose()
