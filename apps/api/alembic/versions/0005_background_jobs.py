"""background_jobs table

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), sa.ForeignKey("resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_background_jobs_user_id", "background_jobs", ["user_id"], unique=False)
    op.create_index("ix_background_jobs_resource_id", "background_jobs", ["resource_id"], unique=False)
    op.create_index("ix_background_jobs_idempotency_key", "background_jobs", ["idempotency_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_background_jobs_idempotency_key", table_name="background_jobs")
    op.drop_index("ix_background_jobs_resource_id", table_name="background_jobs")
    op.drop_index("ix_background_jobs_user_id", table_name="background_jobs")
    op.drop_table("background_jobs")
