"""add direct ownership columns for tasks/chunks/messages

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column("tasks", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_tasks_user_id_users",
        "tasks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    conn.execute(
        sa.text(
            """
            UPDATE tasks t
            SET user_id = c.user_id
            FROM courses c
            WHERE t.course_id = c.id
              AND t.user_id IS NULL
            """
        )
    )
    op.alter_column("tasks", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    op.add_column("resource_chunks", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_resource_chunks_user_id", "resource_chunks", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_resource_chunks_user_id_users",
        "resource_chunks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    conn.execute(
        sa.text(
            """
            UPDATE resource_chunks rc
            SET user_id = r.user_id
            FROM resources r
            WHERE rc.resource_id = r.id
              AND rc.user_id IS NULL
            """
        )
    )
    op.alter_column("resource_chunks", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    op.add_column("ai_messages", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_ai_messages_user_id", "ai_messages", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_ai_messages_user_id_users",
        "ai_messages",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    conn.execute(
        sa.text(
            """
            UPDATE ai_messages m
            SET user_id = c.user_id
            FROM ai_conversations c
            WHERE m.conversation_id = c.id
              AND m.user_id IS NULL
            """
        )
    )
    op.alter_column("ai_messages", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_ai_messages_user_id_users", "ai_messages", type_="foreignkey")
    op.drop_index("ix_ai_messages_user_id", table_name="ai_messages")
    op.drop_column("ai_messages", "user_id")

    op.drop_constraint("fk_resource_chunks_user_id_users", "resource_chunks", type_="foreignkey")
    op.drop_index("ix_resource_chunks_user_id", table_name="resource_chunks")
    op.drop_column("resource_chunks", "user_id")

    op.drop_constraint("fk_tasks_user_id_users", "tasks", type_="foreignkey")
    op.drop_index("ix_tasks_user_id", table_name="tasks")
    op.drop_column("tasks", "user_id")
