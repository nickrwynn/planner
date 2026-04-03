"""note_pages resource link

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("note_pages", sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_note_pages_resource_id_resources",
        "note_pages",
        "resources",
        ["resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_note_pages_resource_id", "note_pages", ["resource_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_note_pages_resource_id", table_name="note_pages")
    op.drop_constraint("fk_note_pages_resource_id_resources", "note_pages", type_="foreignkey")
    op.drop_column("note_pages", "resource_id")

