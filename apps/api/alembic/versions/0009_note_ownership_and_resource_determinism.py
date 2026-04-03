"""note ownership and deterministic resource metadata

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column("note_documents", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_note_documents_user_id", "note_documents", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_note_documents_user_id_users",
        "note_documents",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    conn.execute(
        sa.text(
            """
            UPDATE note_documents d
            SET user_id = n.user_id
            FROM notebooks n
            WHERE d.notebook_id = n.id
              AND d.user_id IS NULL
            """
        )
    )
    op.alter_column("note_documents", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    op.add_column("note_pages", sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_note_pages_user_id", "note_pages", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_note_pages_user_id_users",
        "note_pages",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    conn.execute(
        sa.text(
            """
            UPDATE note_pages p
            SET user_id = d.user_id
            FROM note_documents d
            WHERE p.note_document_id = d.id
              AND p.user_id IS NULL
            """
        )
    )
    op.alter_column("note_pages", "user_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)

    op.add_column("resources", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "resources",
        sa.Column("parse_pipeline_version", sa.String(length=32), nullable=False, server_default="v1"),
    )
    op.add_column(
        "resources",
        sa.Column("chunking_version", sa.String(length=32), nullable=False, server_default="char-v1"),
    )
    op.add_column("resources", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_resources_content_sha256", "resources", ["content_sha256"], unique=False)
    op.create_check_constraint(
        "ck_resources_content_sha256_len",
        "resources",
        "(content_sha256 IS NULL) OR (char_length(content_sha256) = 64)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_resources_content_sha256_len", "resources", type_="check")
    op.drop_index("ix_resources_content_sha256", table_name="resources")
    op.drop_column("resources", "indexed_at")
    op.drop_column("resources", "chunking_version")
    op.drop_column("resources", "parse_pipeline_version")
    op.drop_column("resources", "content_sha256")

    op.drop_constraint("fk_note_pages_user_id_users", "note_pages", type_="foreignkey")
    op.drop_index("ix_note_pages_user_id", table_name="note_pages")
    op.drop_column("note_pages", "user_id")

    op.drop_constraint("fk_note_documents_user_id_users", "note_documents", type_="foreignkey")
    op.drop_index("ix_note_documents_user_id", table_name="note_documents")
    op.drop_column("note_documents", "user_id")
