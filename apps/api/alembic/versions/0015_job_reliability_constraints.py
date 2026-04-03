"""harden job reliability constraints

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_background_jobs_status",
        "background_jobs",
        "status IN ('queued','running','done','failed')",
    )
    op.create_unique_constraint(
        "uq_background_jobs_idempotency_scope",
        "background_jobs",
        ["user_id", "resource_id", "job_type", "idempotency_key"],
    )

    op.create_check_constraint(
        "ck_dead_letter_jobs_attempts_non_negative",
        "dead_letter_jobs",
        "attempts >= 0",
    )
    op.create_unique_constraint(
        "uq_dead_letter_jobs_background_job_id",
        "dead_letter_jobs",
        ["background_job_id"],
    )
    op.create_foreign_key(
        "fk_dead_letter_jobs_background_job_id_background_jobs",
        "dead_letter_jobs",
        "background_jobs",
        ["background_job_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dead_letter_jobs_background_job_id_background_jobs",
        "dead_letter_jobs",
        type_="foreignkey",
    )
    op.drop_constraint("uq_dead_letter_jobs_background_job_id", "dead_letter_jobs", type_="unique")
    op.drop_constraint("ck_dead_letter_jobs_attempts_non_negative", "dead_letter_jobs", type_="check")
    op.drop_constraint("uq_background_jobs_idempotency_scope", "background_jobs", type_="unique")
    op.drop_constraint("ck_background_jobs_status", "background_jobs", type_="check")
