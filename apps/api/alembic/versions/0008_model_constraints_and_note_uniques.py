"""add model constraints and note page uniqueness

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_resources_parse_status",
        "resources",
        "parse_status IN ('uploaded','parsing','parsed','skipped','failed')",
    )
    op.create_check_constraint(
        "ck_resources_ocr_status",
        "resources",
        "ocr_status IN ('pending','running','done','skipped','failed')",
    )
    op.create_check_constraint(
        "ck_resources_index_status",
        "resources",
        "index_status IN ('pending','queued','done','skipped','failed')",
    )

    op.create_check_constraint("ck_tasks_status", "tasks", "status IN ('todo','in_progress','done')")
    op.create_check_constraint(
        "ck_tasks_task_type",
        "tasks",
        "(task_type IS NULL) OR (task_type IN ('assignment','exam','reading','project','other'))",
    )
    op.create_check_constraint("ck_tasks_weight_nonnegative", "tasks", "(weight IS NULL) OR (weight >= 0)")
    op.create_check_constraint(
        "ck_tasks_estimated_minutes_nonnegative",
        "tasks",
        "(estimated_minutes IS NULL) OR (estimated_minutes >= 0)",
    )

    op.create_check_constraint(
        "ck_note_documents_note_type",
        "note_documents",
        "(note_type IS NULL) OR (note_type IN ('typed','handwritten','mixed'))",
    )
    op.create_check_constraint("ck_note_pages_page_index_nonnegative", "note_pages", "page_index >= 0")
    op.create_unique_constraint(
        "uq_note_pages_document_page_index",
        "note_pages",
        ["note_document_id", "page_index"],
    )

    op.create_check_constraint(
        "ck_ai_conversations_mode",
        "ai_conversations",
        "(mode IS NULL) OR (mode IN ('ask','study'))",
    )
    op.create_check_constraint("ck_ai_messages_role", "ai_messages", "role IN ('system','user','assistant')")

    op.create_check_constraint(
        "ck_study_artifacts_artifact_type",
        "study_artifacts",
        "artifact_type IN ('summary','flashcards','quiz','sample_problems')",
    )
    op.create_check_constraint(
        "ck_resource_chunks_chunk_index_nonnegative",
        "resource_chunks",
        "chunk_index >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_resource_chunks_chunk_index_nonnegative", "resource_chunks", type_="check")
    op.drop_constraint("ck_study_artifacts_artifact_type", "study_artifacts", type_="check")
    op.drop_constraint("ck_ai_messages_role", "ai_messages", type_="check")
    op.drop_constraint("ck_ai_conversations_mode", "ai_conversations", type_="check")
    op.drop_constraint("uq_note_pages_document_page_index", "note_pages", type_="unique")
    op.drop_constraint("ck_note_pages_page_index_nonnegative", "note_pages", type_="check")
    op.drop_constraint("ck_note_documents_note_type", "note_documents", type_="check")
    op.drop_constraint("ck_tasks_estimated_minutes_nonnegative", "tasks", type_="check")
    op.drop_constraint("ck_tasks_weight_nonnegative", "tasks", type_="check")
    op.drop_constraint("ck_tasks_task_type", "tasks", type_="check")
    op.drop_constraint("ck_tasks_status", "tasks", type_="check")
    op.drop_constraint("ck_resources_index_status", "resources", type_="check")
    op.drop_constraint("ck_resources_ocr_status", "resources", type_="check")
    op.drop_constraint("ck_resources_parse_status", "resources", type_="check")
