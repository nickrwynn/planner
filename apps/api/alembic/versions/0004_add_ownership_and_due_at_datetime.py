"""add ownership columns + tasks.due_at datetime

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-03
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Ensure at least one user exists (dev-mode safety for backfills) ---
    conn = op.get_bind()
    user_count = conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar() or 0
    if int(user_count) == 0:
        dev_id = str(uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO users (id, email, name, created_at, updated_at)
                VALUES (:id, :email, :name, now(), now())
                """
            ),
            {"id": dev_id, "email": "dev@example.com", "name": "Dev User"},
        )

    # --- resources.user_id ---
    op.add_column("resources", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_resources_user_id", "resources", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_resources_user_id_users",
        "resources",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Backfill from course ownership when possible; fallback to oldest user
    conn.execute(
        sa.text(
            """
            UPDATE resources r
            SET user_id = c.user_id
            FROM courses c
            WHERE r.course_id = c.id AND r.user_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE resources
            SET user_id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)
            WHERE user_id IS NULL
            """
        )
    )
    op.alter_column("resources", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    # --- notebooks.user_id ---
    op.add_column("notebooks", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_notebooks_user_id", "notebooks", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_notebooks_user_id_users",
        "notebooks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    conn.execute(
        sa.text(
            """
            UPDATE notebooks n
            SET user_id = c.user_id
            FROM courses c
            WHERE n.course_id = c.id AND n.user_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE notebooks
            SET user_id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)
            WHERE user_id IS NULL
            """
        )
    )
    op.alter_column("notebooks", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    # --- study_artifacts.user_id ---
    op.add_column("study_artifacts", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_study_artifacts_user_id", "study_artifacts", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_study_artifacts_user_id_users",
        "study_artifacts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Backfill: derive via course ownership when course_id present, else fallback to oldest user
    conn.execute(
        sa.text(
            """
            UPDATE study_artifacts a
            SET user_id = c.user_id
            FROM courses c
            WHERE a.course_id = c.id AND a.user_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE study_artifacts
            SET user_id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)
            WHERE user_id IS NULL
            """
        )
    )
    op.alter_column("study_artifacts", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    # --- tasks.due_at: string -> timestamptz ---
    # Existing schema: due_at is a string (nullable). Convert to timestamptz when possible.
    # For invalid values, set NULL.
    op.execute(
        sa.text(
            """
            ALTER TABLE tasks
            ALTER COLUMN due_at TYPE timestamptz
            USING NULLIF(due_at, '')::timestamptz
            """
        )
    )


def downgrade() -> None:
    # tasks.due_at: timestamptz -> string
    op.execute(
        sa.text(
            """
            ALTER TABLE tasks
            ALTER COLUMN due_at TYPE varchar(64)
            USING CASE
              WHEN due_at IS NULL THEN NULL
              ELSE to_char(due_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')
            END
            """
        )
    )

    op.drop_constraint("fk_study_artifacts_user_id_users", "study_artifacts", type_="foreignkey")
    op.drop_index("ix_study_artifacts_user_id", table_name="study_artifacts")
    op.drop_column("study_artifacts", "user_id")

    op.drop_constraint("fk_notebooks_user_id_users", "notebooks", type_="foreignkey")
    op.drop_index("ix_notebooks_user_id", table_name="notebooks")
    op.drop_column("notebooks", "user_id")

    op.drop_constraint("fk_resources_user_id_users", "resources", type_="foreignkey")
    op.drop_index("ix_resources_user_id", table_name="resources")
    op.drop_column("resources", "user_id")

