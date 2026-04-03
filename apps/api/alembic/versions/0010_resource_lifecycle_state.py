"""resource lifecycle state column

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    op.add_column(
        "resources",
        sa.Column("lifecycle_state", sa.String(length=30), nullable=False, server_default="uploaded"),
    )
    conn.execute(
        sa.text(
            """
            UPDATE resources
            SET lifecycle_state = CASE
                WHEN index_status = 'done' THEN 'searchable'
                WHEN index_status = 'skipped' THEN 'skipped'
                WHEN parse_status = 'failed' OR ocr_status = 'failed' OR index_status = 'failed' THEN 'failed'
                WHEN parse_status = 'parsing' OR ocr_status = 'running' THEN 'parsing'
                WHEN parse_status = 'parsed' THEN 'parsed'
                ELSE 'uploaded'
            END
            """
        )
    )
    op.create_check_constraint(
        "ck_resources_lifecycle_state",
        "resources",
        "lifecycle_state IN ('uploaded','parsing','parsed','chunked','indexed','searchable','skipped','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_resources_lifecycle_state", "resources", type_="check")
    op.drop_column("resources", "lifecycle_state")
