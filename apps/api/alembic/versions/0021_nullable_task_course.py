"""allow personal tasks without a course

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tasks",
        "course_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM tasks WHERE course_id IS NULL")
    op.alter_column(
        "tasks",
        "course_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
