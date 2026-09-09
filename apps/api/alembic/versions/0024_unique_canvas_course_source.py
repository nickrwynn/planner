"""Unique Canvas course identity per user (prevents duplicate sync inserts).

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-09
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_courses_user_canvas_source
        ON courses (user_id, source_type, source_ref)
        WHERE source_ref IS NOT NULL AND source_type IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_courses_user_canvas_source")
