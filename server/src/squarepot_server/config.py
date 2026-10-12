# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configuration, read from environment variables only (see deploy/.env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# In a source checkout and in the container, schema/ sits next to server/.
DEFAULT_SCHEMA_FILE = Path(__file__).resolve().parents[3] / "schema" / "fields.yaml"


class CollectionConfig(BaseModel):
    """One collection: a tab of a spreadsheet shared with the service account."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    spreadsheet_id: str = Field(min_length=1)
    sheet: str = Field(min_length=1, description="Tab name.")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SQUAREPOT_", extra="ignore")

    api_token: SecretStr = Field(min_length=16)
    database_url: str = "sqlite:///data/squarepot.db"
    google_credentials_file: Path | None = None
    collections: list[CollectionConfig] = []
    sync_interval_seconds: float = Field(default=60, ge=0)
    schema_file: Path = DEFAULT_SCHEMA_FILE


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
