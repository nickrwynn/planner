"""Nest Canvas attachments under the page they came from.

A Canvas page such as "Canvas Resources for Students" embeds a dozen images,
and the sync turned each one into its own top-level resource. Giving resources
a parent lets the list mirror Canvas — module -> page -> attachment — without
deleting anything that already exists.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column("parent_resource_id", sa.UUID(), nullable=True),
    )
    # SET NULL rather than CASCADE: losing a page must not silently delete the
    # attachment bytes and their indexed chunks.
    op.create_foreign_key(
        "fk_resources_parent_resource_id",
        "resources",
        "resources",
        ["parent_resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_resources_parent_resource_id",
        "resources",
        ["parent_resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_resources_parent_resource_id", table_name="resources")
    op.drop_constraint("fk_resources_parent_resource_id", "resources", type_="foreignkey")
    op.drop_column("resources", "parent_resource_id")
