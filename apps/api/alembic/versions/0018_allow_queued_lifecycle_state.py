"""allow queued resource lifecycle state

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-03
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_resources_lifecycle_state", "resources", type_="check")
    op.create_check_constraint(
        "ck_resources_lifecycle_state",
        "resources",
        "lifecycle_state IN ('uploaded','queued','parsing','parsed','chunked','indexed','searchable','skipped','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_resources_lifecycle_state", "resources", type_="check")
    op.create_check_constraint(
        "ck_resources_lifecycle_state",
        "resources",
        "lifecycle_state IN ('uploaded','parsing','parsed','chunked','indexed','searchable','skipped','failed')",
    )
