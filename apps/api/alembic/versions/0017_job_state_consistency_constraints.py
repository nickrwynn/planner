"""enforce job state consistency constraints

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE background_jobs
            SET
                status = 'queued',
                available_at = COALESCE(available_at, NOW()),
                finished_at = NULL,
                claim_token = NULL,
                claimed_by = NULL,
                claimed_at = NULL,
                lease_expires_at = NULL,
                last_error = COALESCE(
                    last_error,
                    'running job missing claim/lease fields; re-queued by migration'
                )
            WHERE status = 'running'
              AND (
                claim_token IS NULL
                OR claimed_by IS NULL
                OR claimed_at IS NULL
                OR lease_expires_at IS NULL
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE background_jobs
            SET
                claim_token = NULL,
                claimed_by = NULL,
                claimed_at = NULL,
                lease_expires_at = NULL
            WHERE status <> 'running'
              AND (
                claim_token IS NOT NULL
                OR claimed_by IS NOT NULL
                OR claimed_at IS NOT NULL
                OR lease_expires_at IS NOT NULL
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE dead_letter_jobs
            SET replay_key = background_job_id::text || ':' || attempts::text
            WHERE background_job_id IS NOT NULL
              AND replay_key IS NULL
            """
        )
    )

    op.create_check_constraint(
        "ck_background_jobs_attempts_non_negative",
        "background_jobs",
        "attempts >= 0",
    )
    op.create_check_constraint(
        "ck_background_jobs_running_claim_fields_present",
        "background_jobs",
        "(status != 'running') OR "
        "(claim_token IS NOT NULL AND claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_background_jobs_non_running_claim_fields_cleared",
        "background_jobs",
        "(status = 'running') OR "
        "(claim_token IS NULL AND claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_dead_letter_jobs_replay_key_for_linked_job",
        "dead_letter_jobs",
        "(background_job_id IS NULL) OR (replay_key IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_dead_letter_jobs_replay_key_for_linked_job",
        "dead_letter_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_background_jobs_non_running_claim_fields_cleared",
        "background_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_background_jobs_running_claim_fields_present",
        "background_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_background_jobs_attempts_non_negative",
        "background_jobs",
        type_="check",
    )
