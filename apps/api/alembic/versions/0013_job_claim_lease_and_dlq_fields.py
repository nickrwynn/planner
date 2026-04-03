"""add claim/lease fields for jobs and deterministic dlq fields

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("background_jobs", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("background_jobs", sa.Column("claim_token", sa.String(length=64), nullable=True))
    op.add_column("background_jobs", sa.Column("claimed_by", sa.String(length=120), nullable=True))
    op.add_column("background_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("background_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_background_jobs_available_at", "background_jobs", ["available_at"], unique=False)
    op.create_index("ix_background_jobs_claim_token", "background_jobs", ["claim_token"], unique=False)
    op.create_index("ix_background_jobs_lease_expires_at", "background_jobs", ["lease_expires_at"], unique=False)

    op.add_column("dead_letter_jobs", sa.Column("reason_code", sa.String(length=80), nullable=True))
    op.add_column("dead_letter_jobs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("dead_letter_jobs", sa.Column("replay_key", sa.String(length=120), nullable=True))
    op.create_index("ix_dead_letter_jobs_reason_code", "dead_letter_jobs", ["reason_code"], unique=False)
    op.create_index("ix_dead_letter_jobs_replay_key", "dead_letter_jobs", ["replay_key"], unique=False)
    op.alter_column("dead_letter_jobs", "attempts", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_dead_letter_jobs_replay_key", table_name="dead_letter_jobs")
    op.drop_index("ix_dead_letter_jobs_reason_code", table_name="dead_letter_jobs")
    op.drop_column("dead_letter_jobs", "replay_key")
    op.drop_column("dead_letter_jobs", "attempts")
    op.drop_column("dead_letter_jobs", "reason_code")

    op.drop_index("ix_background_jobs_lease_expires_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_claim_token", table_name="background_jobs")
    op.drop_index("ix_background_jobs_available_at", table_name="background_jobs")
    op.drop_column("background_jobs", "lease_expires_at")
    op.drop_column("background_jobs", "claimed_at")
    op.drop_column("background_jobs", "claimed_by")
    op.drop_column("background_jobs", "claim_token")
    op.drop_column("background_jobs", "available_at")
