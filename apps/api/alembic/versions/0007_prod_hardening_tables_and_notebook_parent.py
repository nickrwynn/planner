"""add notebook parent_id, dead letter jobs, ai usage logs

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notebooks", sa.Column("parent_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_notebooks_parent_id_notebooks",
        "notebooks",
        "notebooks",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_notebooks_parent_id", "notebooks", ["parent_id"], unique=False)

    op.create_table(
        "dead_letter_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), sa.ForeignKey("resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("background_job_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("queue_name", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dead_letter_jobs_user_id", "dead_letter_jobs", ["user_id"], unique=False)
    op.create_index("ix_dead_letter_jobs_resource_id", "dead_letter_jobs", ["resource_id"], unique=False)
    op.create_index("ix_dead_letter_jobs_background_job_id", "dead_letter_jobs", ["background_job_id"], unique=False)

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_usage_logs_user_id", "ai_usage_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_user_id", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")

    op.drop_index("ix_dead_letter_jobs_background_job_id", table_name="dead_letter_jobs")
    op.drop_index("ix_dead_letter_jobs_resource_id", table_name="dead_letter_jobs")
    op.drop_index("ix_dead_letter_jobs_user_id", table_name="dead_letter_jobs")
    op.drop_table("dead_letter_jobs")

    op.drop_index("ix_notebooks_parent_id", table_name="notebooks")
    op.drop_constraint("fk_notebooks_parent_id_notebooks", "notebooks", type_="foreignkey")
    op.drop_column("notebooks", "parent_id")
