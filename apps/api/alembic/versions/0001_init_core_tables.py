"""init core tables

Revision ID: 0001
Revises: 
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("term", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("grading_schema_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_courses_user_id", "courses", ["user_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=True),
        sa.Column("due_at", sa.String(length=64), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tasks_course_id", "tasks", ["course_id"], unique=False)

    op.create_table(
        "resources",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("original_filename", sa.String(length=300), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("ocr_status", sa.String(length=30), nullable=False),
        sa.Column("index_status", sa.String(length=30), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resources_course_id", "resources", ["course_id"], unique=False)

    op.create_table(
        "notebooks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notebooks_course_id", "notebooks", ["course_id"], unique=False)

    # Notes + AI tables (no routes yet, but schema exists)
    op.create_table(
        "note_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "notebook_id", sa.Uuid(as_uuid=True), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("note_type", sa.String(length=50), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_note_documents_notebook_id", "note_documents", ["notebook_id"], unique=False)

    op.create_table(
        "note_pages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "note_document_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("note_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("page_data_json", sa.JSON(), nullable=True),
        sa.Column("extracted_text", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_note_pages_note_document_id", "note_pages", ["note_document_id"], unique=False)

    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("mode", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"], unique=False)
    op.create_index("ix_ai_conversations_course_id", "ai_conversations", ["course_id"], unique=False)

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_messages_conversation_id", "ai_messages", ["conversation_id"], unique=False)

    op.create_table(
        "study_artifacts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_resource_ids_json", sa.JSON(), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_study_artifacts_course_id", "study_artifacts", ["course_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_study_artifacts_course_id", table_name="study_artifacts")
    op.drop_table("study_artifacts")

    op.drop_index("ix_ai_messages_conversation_id", table_name="ai_messages")
    op.drop_table("ai_messages")

    op.drop_index("ix_ai_conversations_course_id", table_name="ai_conversations")
    op.drop_index("ix_ai_conversations_user_id", table_name="ai_conversations")
    op.drop_table("ai_conversations")

    op.drop_index("ix_note_pages_note_document_id", table_name="note_pages")
    op.drop_table("note_pages")

    op.drop_index("ix_note_documents_notebook_id", table_name="note_documents")
    op.drop_table("note_documents")

    op.drop_index("ix_notebooks_course_id", table_name="notebooks")
    op.drop_table("notebooks")

    op.drop_index("ix_resources_course_id", table_name="resources")
    op.drop_table("resources")

    op.drop_index("ix_tasks_course_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_courses_user_id", table_name="courses")
    op.drop_table("courses")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

