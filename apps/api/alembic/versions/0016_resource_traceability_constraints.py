"""add resource traceability constraints

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalize historical duplicates before enforcing uniqueness.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY resource_id
                        ORDER BY seq ASC, occurred_at ASC, created_at ASC, id ASC
                    ) AS new_seq
                FROM resource_lifecycle_events
            )
            UPDATE resource_lifecycle_events AS e
            SET seq = ranked.new_seq
            FROM ranked
            WHERE e.id = ranked.id
            """
        )
    )
    op.create_check_constraint(
        "ck_resources_parse_error_code",
        "resources",
        "parse_error_code IS NULL OR parse_error_code IN "
        "('missing_storage_path','pdf_parse_error','ocr_environment_error','ocr_parse_error',"
        "'storage_read_error','unsupported_media_error','indexing_error')",
    )
    op.create_check_constraint(
        "ck_resources_index_error_code",
        "resources",
        "index_error_code IS NULL OR index_error_code IN "
        "('missing_storage_path','pdf_parse_error','ocr_environment_error','ocr_parse_error',"
        "'storage_read_error','unsupported_media_error','embedding_error','indexing_error')",
    )
    op.create_unique_constraint(
        "uq_resource_lifecycle_events_resource_seq",
        "resource_lifecycle_events",
        ["resource_id", "seq"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_resource_lifecycle_events_resource_seq",
        "resource_lifecycle_events",
        type_="unique",
    )
    op.drop_constraint("ck_resources_index_error_code", "resources", type_="check")
    op.drop_constraint("ck_resources_parse_error_code", "resources", type_="check")
