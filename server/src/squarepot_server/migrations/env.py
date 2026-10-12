# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alembic environment: migrates the connection the server passes, or SQUAREPOT_DATABASE_URL."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy.engine import Connection

from squarepot_server.db import Base, make_engine


def run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with make_engine(os.environ["SQUAREPOT_DATABASE_URL"]).connect() as connection:
        run(connection)
