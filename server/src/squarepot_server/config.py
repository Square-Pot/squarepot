# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuration, read from environment variables only (see deploy/.env.example)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# In a source checkout and in the container, schema/ sits next to server/.
DEFAULT_SCHEMA_FILE = Path(__file__).resolve().parents[3] / "schema" / "fields.yaml"


class StoreKind(StrEnum):
    LINK = "link"
    GOOGLE = "google"
    FILE = "file"


class PhotoStoreKind(StrEnum):
    """Where plant photos are kept (ADR 0007)."""

    NONE = "none"
    DISK = "disk"
    S3 = "s3"


class CollectionConfig(BaseModel):
    """One collection: a tab of a Google Sheet, or a CSV file laid out as one."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    spreadsheet_id: str | None = Field(default=None, min_length=1)
    sheet: str | None = Field(
        default=None, min_length=1, description="Tab name, for the google store."
    )
    gid: int | None = Field(default=None, ge=0, description="Tab id, for a sheet read by link.")
    file: Path | None = Field(default=None, description="CSV file, laid out as a tab.")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SQUAREPOT_", extra="ignore")

    api_token: SecretStr = Field(min_length=16)
    database_url: str = "sqlite:///data/squarepot.db"
    store: StoreKind = StoreKind.LINK
    google_credentials_file: Path | None = None
    collections: list[CollectionConfig] = []
    sync_interval_seconds: float = Field(default=60, ge=0)
    schema_file: Path = DEFAULT_SCHEMA_FILE
    web_dir: Path | None = Field(
        default=None, description="The built web app, served at /; none serves only the API."
    )
    api_docs: bool = Field(
        default=False, description="Serve /docs, /redoc and /openapi.json, for development."
    )
    photos: PhotoStoreKind = PhotoStoreKind.NONE
    photos_dir: Path = Path("data/photos")
    s3_endpoint: str = "https://storage.yandexcloud.net"
    s3_region: str = "ru-central1"
    s3_bucket: str | None = Field(default=None, min_length=3)
    s3_key_file: Path | None = Field(
        default=None,
        description="A file holding the key id on its first line, the secret on its second.",
    )

    @model_validator(mode="after")
    def collections_match_the_store(self) -> Settings:
        for collection in self.collections:
            if self.store == StoreKind.LINK and not collection.spreadsheet_id:
                raise ValueError(
                    f"collection {collection.id!r} needs a spreadsheet_id with the link store"
                )
            if self.store == StoreKind.LINK and collection.sheet is not None:
                raise ValueError(
                    f"collection {collection.id!r} names a sheet, which the link store cannot "
                    "choose by name: give the tab's gid (the number after #gid= in its URL) "
                    "instead, or neither for the first tab"
                )
            if self.store == StoreKind.GOOGLE and collection.gid is not None:
                raise ValueError(
                    f"collection {collection.id!r} has a gid, which the google store does not "
                    "use: name the tab with sheet instead"
                )
            if self.store == StoreKind.GOOGLE and not (
                collection.spreadsheet_id and collection.sheet
            ):
                raise ValueError(
                    f"collection {collection.id!r} needs a spreadsheet_id and a sheet "
                    "with the google store"
                )
            if self.store == StoreKind.FILE and collection.file is None:
                raise ValueError(f"collection {collection.id!r} needs a file with the file store")
        if self.photos == PhotoStoreKind.S3 and not (self.s3_bucket and self.s3_key_file):
            raise ValueError("photos in s3 need SQUAREPOT_S3_BUCKET and SQUAREPOT_S3_KEY_FILE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
