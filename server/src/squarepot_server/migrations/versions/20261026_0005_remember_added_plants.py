# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plants added through the API, by the client's request id, so a retry adds no second row.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from squarepot_server.db import UTCDateTime

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "added_plants",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("collection_id", sa.String(64), nullable=False),
        sa.Column("tag", sa.String(6), nullable=True),
        sa.Column("row", sa.Integer(), nullable=False),
        sa.Column("added_at", UTCDateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("added_plants")
