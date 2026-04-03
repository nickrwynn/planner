from __future__ import annotations

from sqlalchemy import inspect


def test_schema_contains_required_ownership_and_determinism_columns(db_session):
    inspector = inspect(db_session.bind)

    note_document_cols = {c["name"] for c in inspector.get_columns("note_documents")}
    note_page_cols = {c["name"] for c in inspector.get_columns("note_pages")}
    resource_cols = {c["name"] for c in inspector.get_columns("resources")}
    task_cols = {c["name"] for c in inspector.get_columns("tasks")}
    chunk_cols = {c["name"] for c in inspector.get_columns("resource_chunks")}
    ai_message_cols = {c["name"] for c in inspector.get_columns("ai_messages")}
    job_cols = {c["name"] for c in inspector.get_columns("background_jobs")}

    assert "user_id" in note_document_cols
    assert "user_id" in note_page_cols
    assert "content_sha256" in resource_cols
    assert "parse_pipeline_version" in resource_cols
    assert "chunking_version" in resource_cols
    assert "indexed_at" in resource_cols
    assert "lifecycle_state" in resource_cols
    assert "user_id" in task_cols
    assert "user_id" in chunk_cols
    assert "user_id" in ai_message_cols
    assert "started_at" in job_cols
    assert "finished_at" in job_cols
