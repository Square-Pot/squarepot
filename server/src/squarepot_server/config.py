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
    GOOGLE = "google"
    FILE = "file"


class CollectionConfig(BaseModel):
    """One collection: a tab of a spreadsheet shared with the service account, or a CSV file."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    spreadsheet_id: str | None = Field(default=None, min_length=1)
    sheet: str | None = Field(default=None, min_length=1, description="Tab name.")
    file: Path | None = Field(default=None, description="CSV file, laid out as a tab.")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SQUAREPOT_", extra="ignore")

    api_token: SecretStr = Field(min_length=16)
    database_url: str = "sqlite:///data/squarepot.db"
    store: StoreKind = StoreKind.GOOGLE
    google_credentials_file: Path | None = None
    collections: list[CollectionConfig] = []
    sync_interval_seconds: float = Field(default=60, ge=0)
    schema_file: Path = DEFAULT_SCHEMA_FILE

    @model_validator(mode="after")
    def collections_match_the_store(self) -> Settings:
        for collection in self.collections:
            if self.store == StoreKind.GOOGLE and not (
                collection.spreadsheet_id and collection.sheet
            ):
                raise ValueError(
                    f"collection {collection.id!r} needs a spreadsheet_id and a sheet "
                    "with the google store"
                )
            if self.store == StoreKind.FILE and collection.file is None:
                raise ValueError(f"collection {collection.id!r} needs a file with the file store")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
