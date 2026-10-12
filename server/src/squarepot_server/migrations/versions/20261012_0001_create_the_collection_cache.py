# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create the collection cache.

Revision ID: 0001
Revises:
Create Date: 2026-10-12 13:38:08.421202
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from squarepot_server.db import UTCDateTime

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.Column("store_version", sa.Text(), nullable=True),
        sa.Column("synced_at", UTCDateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("plant_count", sa.Integer(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("collections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_collections_seq"), ["seq"], unique=False)

    op.create_table(
        "meta",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "registered_tags",
        sa.Column("tag", sa.String(length=6), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("registered_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tag"),
    )
    op.create_table(
        "plants",
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.Column("tag", sa.String(length=6), nullable=True),
        sa.Column("row", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_plants_collection_id"), ["collection_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_plants_seq"), ["seq"], unique=False)
        batch_op.create_index(batch_op.f("ix_plants_tag"), ["tag"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("plants", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plants_tag"))
        batch_op.drop_index(batch_op.f("ix_plants_seq"))
        batch_op.drop_index(batch_op.f("ix_plants_collection_id"))

    op.drop_table("plants")
    op.drop_table("registered_tags")
    op.drop_table("meta")
    with op.batch_alter_table("collections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collections_seq"))

    op.drop_table("collections")
