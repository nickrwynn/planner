"""add resource lifecycle audit events and error code columns

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("parse_error_code", sa.String(length=80), nullable=True))
    op.add_column("resources", sa.Column("index_error_code", sa.String(length=80), nullable=True))
    op.add_column("resources", sa.Column("last_lifecycle_event_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_resources_parse_error_code", "resources", ["parse_error_code"], unique=False)
    op.create_index("ix_resources_index_error_code", "resources", ["index_error_code"], unique=False)

    op.create_table(
        "resource_lifecycle_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "resource_id", sa.Uuid(as_uuid=True), sa.ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(length=30), nullable=True),
        sa.Column("to_state", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resource_lifecycle_events_user_id", "resource_lifecycle_events", ["user_id"], unique=False)
    op.create_index(
        "ix_resource_lifecycle_events_resource_id", "resource_lifecycle_events", ["resource_id"], unique=False
    )
    op.create_index(
        "ix_resource_lifecycle_events_error_code", "resource_lifecycle_events", ["error_code"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_resource_lifecycle_events_error_code", table_name="resource_lifecycle_events")
    op.drop_index("ix_resource_lifecycle_events_resource_id", table_name="resource_lifecycle_events")
    op.drop_index("ix_resource_lifecycle_events_user_id", table_name="resource_lifecycle_events")
    op.drop_table("resource_lifecycle_events")

    op.drop_index("ix_resources_index_error_code", table_name="resources")
    op.drop_index("ix_resources_parse_error_code", table_name="resources")
    op.drop_column("resources", "last_lifecycle_event_at")
    op.drop_column("resources", "index_error_code")
    op.drop_column("resources", "parse_error_code")
