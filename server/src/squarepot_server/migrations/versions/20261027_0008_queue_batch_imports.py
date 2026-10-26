# SPDX-License-Identifier: AGPL-3.0-or-later
"""Batch imports: photos staged until their codes are read and they are filed (ADR 0008).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-27 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from squarepot_server.db import UTCDateTime

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("staged_key", sa.Text(), nullable=False),
        sa.Column("file_time", UTCDateTime(), nullable=True),
        sa.Column("uploaded_at", UTCDateTime(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("numbers", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("tag", sa.String(6), nullable=True),
        sa.Column("decoded_at", UTCDateTime(), nullable=True),
    )
    op.create_index("ix_imports_state", "imports", ["state"])


def downgrade() -> None:
    op.drop_index("ix_imports_state", table_name="imports")
    op.drop_table("imports")
