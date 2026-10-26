# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sightings: the dated proofs that a plant is still there (ADR 0008).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from squarepot_server.db import UTCDateTime

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sightings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tag", sa.String(6), nullable=False),
        sa.Column("seen_at", UTCDateTime(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("received_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_sightings_tag", "sightings", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_sightings_tag", table_name="sightings")
    op.drop_table("sightings")
