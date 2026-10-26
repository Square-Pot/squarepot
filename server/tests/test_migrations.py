# SPDX-License-Identifier: AGPL-3.0-or-later
"""The migrations build the database the models describe, and keep existing data."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text

from squarepot_server.db import Base, make_engine
from squarepot_server.sync import MIGRATIONS, migrate


def test_the_migrations_match_the_models(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    migrate(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_custom_columns_come_to_an_existing_database(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.execute(
            text(
                "INSERT INTO collections (id, name, seq, removed, store_version, plant_count, "
                "issues) VALUES ('main', 'Main', 1, 0, '7', 1, '[]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO plants (id, collection_id, seq, removed, tag, row, fields) "
                """VALUES ('main:004217', 'main', 2, 0, '004217', 2, '{"genus": "Lithops"}')"""
            )
        )
    migrate(engine)
    with engine.connect() as connection:
        collection = connection.execute(
            text("SELECT store_version, custom_columns FROM collections")
        ).one()
        plant = connection.execute(text("SELECT fields, custom FROM plants")).one()
    # The tab is read again on the next sync, which brings in its custom columns.
    assert tuple(collection) == (None, "[]")
    assert tuple(plant) == ('{"genus": "Lithops"}', "{}")


def test_former_plants_come_to_an_existing_database(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003")
        connection.execute(
            text(
                "INSERT INTO collections (id, name, seq, removed, store_version, plant_count, "
                "issues, custom_columns) VALUES ('main', 'Main', 1, 0, '7', 1, '[]', '[]')"
            )
        )
    migrate(engine)
    with engine.connect() as connection:
        collection = connection.execute(
            text("SELECT store_version, plant_count, former_count FROM collections")
        ).one()
    # The tab is read again on the next sync, which takes both counts.
    assert tuple(collection) == (None, 1, 0)
