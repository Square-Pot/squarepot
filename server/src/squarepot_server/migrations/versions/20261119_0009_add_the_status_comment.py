# SPDX-License-Identifier: AGPL-3.0-or-later
"""The status comment, and a re-read of every tab under the two-state status (ADR 0009).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.add_column(sa.Column("status_comment", sa.Text(), nullable=True))
    # Every tab is read again: statuses become the two states "0"/"1", the date
    # is resolved into status_since, and the comment is cached.
    op.execute("UPDATE collections SET store_version = NULL")


def downgrade() -> None:
    with op.batch_alter_table("plants") as batch:
        batch.drop_column("status_comment")
