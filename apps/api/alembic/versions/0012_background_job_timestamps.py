"""add started_at/finished_at to background_jobs

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("background_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("background_jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("background_jobs", "finished_at")
    op.drop_column("background_jobs", "started_at")
