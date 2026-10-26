# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plant photos: the index of the files in the photo storage, and each number's main photo.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from squarepot_server.db import UTCDateTime

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tag", sa.String(6), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("thumbnail_key", sa.Text(), nullable=False),
        sa.Column("meta_key", sa.Text(), nullable=False),
        sa.Column("taken_at", UTCDateTime(), nullable=False),
        sa.Column("taken_from", sa.String(16), nullable=False),
        sa.Column("uploaded_at", UTCDateTime(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("deleted_at", UTCDateTime(), nullable=True),
    )
    op.create_index("ix_photos_tag", "photos", ["tag"])
    op.create_index("ix_photos_seq", "photos", ["seq"])
    op.create_table(
        "main_photos",
        sa.Column("tag", sa.String(6), primary_key=True),
        sa.Column("photo_id", sa.String(36), sa.ForeignKey("photos.id"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("main_photos")
    op.drop_index("ix_photos_seq", table_name="photos")
    op.drop_index("ix_photos_tag", table_name="photos")
    op.drop_table("photos")
