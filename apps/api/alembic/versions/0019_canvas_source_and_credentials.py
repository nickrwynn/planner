"""canvas source fields, task logistics, integration credentials

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("source_type", sa.String(length=50), nullable=True))
    op.add_column("courses", sa.Column("source_ref", sa.String(length=200), nullable=True))
    op.create_index("ix_courses_user_source", "courses", ["user_id", "source_type", "source_ref"])

    op.add_column("tasks", sa.Column("purpose", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("logistics_json", sa.JSON(), nullable=True))
    op.create_index("ix_tasks_user_source", "tasks", ["user_id", "source_type", "source_ref"])

    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("token_encrypted", sa.String(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=50), nullable=True),
        sa.Column("last_sync_error", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_integration_credentials_user_provider"),
    )


def downgrade() -> None:
    op.drop_table("integration_credentials")
    op.drop_index("ix_tasks_user_source", table_name="tasks")
    op.drop_column("tasks", "logistics_json")
    op.drop_column("tasks", "purpose")
    op.drop_index("ix_courses_user_source", table_name="courses")
    op.drop_column("courses", "source_ref")
    op.drop_column("courses", "source_type")
