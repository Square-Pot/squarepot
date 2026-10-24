# SPDX-License-Identifier: AGPL-3.0-or-later
"""Store custom columns: their names per collection and their values per plant.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("collections") as batch:
        batch.add_column(
            sa.Column("custom_columns", sa.JSON(), nullable=False, server_default="[]")
        )
    with op.batch_alter_table("plants") as batch:
        batch.add_column(sa.Column("custom", sa.JSON(), nullable=False, server_default="{}"))
    # Every tab is read again, so that the custom columns already in it come in.
    op.execute("UPDATE collections SET store_version = NULL")


def downgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.drop_column("custom")
    with op.batch_alter_table("collections") as batch:
        batch.drop_column("custom_columns")
