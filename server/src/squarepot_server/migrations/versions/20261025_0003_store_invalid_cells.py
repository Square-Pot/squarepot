# SPDX-License-Identifier: AGPL-3.0-or-later
"""Store the cells the import rejected, per plant.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.add_column(sa.Column("invalid", sa.JSON(), nullable=False, server_default="{}"))
    # Every tab is read again, so that the cells already rejected are recorded.
    op.execute("UPDATE collections SET store_version = NULL")


def downgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.drop_column("invalid")
