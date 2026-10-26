# SPDX-License-Identifier: AGPL-3.0-or-later
"""Former plants: count them apart, and record since when each has its status.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("collections") as batch:
        batch.add_column(
            sa.Column("former_count", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("plants") as batch:
        batch.add_column(sa.Column("status_seen", sa.Text(), nullable=True))
        batch.add_column(sa.Column("status_since", sa.Date(), nullable=True))
    # Every tab is read again, so that both counts are taken and the statuses recorded.
    op.execute("UPDATE collections SET store_version = NULL")


def downgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.drop_column("status_since")
        batch.drop_column("status_seen")
    with op.batch_alter_table("collections") as batch:
        batch.drop_column("former_count")
