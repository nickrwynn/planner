from __future__ import annotations

import io
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.indexing.pipeline import index_resource
from app.indexing.pipeline import _classify_index_error
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.models.resource_lifecycle_event import ResourceLifecycleEvent
from app.services.resource_lifecycle import transition_resource_lifecycle
from app.models.user import User
from app.parsing.ocr import OcrEnvironmentError
from app.parsing.ocr import OcrParseError
from app.parsing.pdf import PdfParseError


def test_index_resource_unsupported_mime_skipped(db_session, tmp_path):
    user = User(email="pipe@test.dev", name="Pipe")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01unsupported")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Bin",
        resource_type="file",
        original_filename="data.bin",
        mime_type="application/octet-stream",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.parse_status == "skipped"
    assert res.index_status == "skipped"
    assert res.lifecycle_state == "skipped"
    assert res.parse_error_code == "unsupported_media_error"
    assert res.index_error_code == "unsupported_media_error"
    assert (res.metadata_json or {}).get("skip_reason") == "unsupported_mime"
    n = db_session.scalar(
        select(func.count()).select_from(ResourceChunk).where(ResourceChunk.resource_id == res.id)
    )
    assert n == 0


def test_index_resource_plain_text(db_session, tmp_path):
    user = User(email="txt@test.dev", name="Txt")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "note.txt"
    f.write_text("Hello world unique_plaintext_token_for_search", encoding="utf-8")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Note",
        resource_type="file",
        original_filename="note.txt",
        mime_type="text/plain",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.parse_status == "parsed"
    assert res.index_status == "done"
    chunks = list(
        db_session.execute(
            select(ResourceChunk)
            .where(ResourceChunk.resource_id == res.id)
            .order_by(ResourceChunk.chunk_index.asc())
        ).scalars().all()
    )
    assert len(chunks) >= 1
    assert "unique_plaintext_token_for_search" in chunks[0].text


def test_index_resource_embedding_failure_still_persists_chunks(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.pipeline.embed_resource_chunks_if_configured",
        lambda _chunks: "embedding service unavailable",
    )

    user = User(email="embedfail@test.dev", name="EmbedFail")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "note2.txt"
    f.write_text("unique_embed_fail_token_xyz", encoding="utf-8")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Note",
        resource_type="file",
        original_filename="note2.txt",
        mime_type="text/plain",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
    )
    db_session.add(res)
    db_session.commit()

    from app.indexing.pipeline import index_resource

    index_resource(
        db_session,
        resource_id=str(res.id),
        trace_context={"job_id": "job-embed-test", "worker_id": "worker-test"},
    )
    db_session.refresh(res)
    assert res.parse_status == "parsed"
    assert res.index_status == "done"
    assert res.index_error_code == "embedding_error"
    assert (res.metadata_json or {}).get("embedding_error") == "embedding service unavailable"
    assert (res.metadata_json or {}).get("latest_job_id") == "job-embed-test"
    assert (res.metadata_json or {}).get("latest_index_run_id")
    chunks = list(
        db_session.execute(
            select(ResourceChunk).where(ResourceChunk.resource_id == res.id)
        ).scalars().all()
    )
    assert len(chunks) >= 1
    assert all(c.embedding is None for c in chunks)


def test_index_resource_image_ocr_environment_error_sets_metadata(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.pipeline.ocr_image",
        lambda _path: (_ for _ in ()).throw(OcrEnvironmentError("tesseract missing")),
    )

    user = User(email="ocrfail@test.dev", name="OcrFail")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "scan.png"
    f.write_bytes(b"not_a_real_png_but_pipeline_calls_ocr_function")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Scan",
        resource_type="scan",
        original_filename="scan.png",
        mime_type="image/png",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.index_status == "failed"
    assert res.ocr_status == "failed"
    assert (res.metadata_json or {}).get("ocr_error") == "tesseract missing"
    assert (res.metadata_json or {}).get("ocr_error_code") == "ocr_environment_error"
    assert res.parse_error_code == "ocr_environment_error"
    assert res.index_error_code == "ocr_environment_error"


def test_index_resource_lifecycle_reaches_searchable(db_session, tmp_path):
    user = User(email="lifecycle@test.dev", name="Lifecycle")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "lifecycle.txt"
    f.write_text("lifecycle token text", encoding="utf-8")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Lifecycle",
        resource_type="file",
        original_filename="lifecycle.txt",
        mime_type="text/plain",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.lifecycle_state == "searchable"
    assert res.index_status == "done"
    assert res.indexed_at is not None
    assert res.last_lifecycle_event_at is not None
    events = list(
        db_session.execute(
            select(ResourceLifecycleEvent)
            .where(ResourceLifecycleEvent.resource_id == res.id)
            .order_by(ResourceLifecycleEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    assert len(events) >= 4
    assert events[0].to_state == "parsing"
    assert events[-1].to_state == "searchable"
    event_types = [event.event_type for event in events]
    assert event_types == [
        "parse.started",
        "parse.succeeded",
        "chunking.completed",
        "index.completed",
        "searchable.ready",
    ]


def test_index_resource_is_deterministic_for_same_input(db_session, tmp_path):
    user = User(email="deterministic@test.dev", name="Deterministic")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "deterministic.txt"
    f.write_text(("deterministic token " * 200).strip(), encoding="utf-8")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Deterministic",
        resource_type="file",
        original_filename="deterministic.txt",
        mime_type="text/plain",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    first = list(
        db_session.execute(
            select(ResourceChunk)
            .where(ResourceChunk.resource_id == res.id)
            .order_by(ResourceChunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    first_snapshot = [(c.chunk_index, c.page_number, c.text) for c in first]

    index_resource(db_session, resource_id=str(res.id))
    second = list(
        db_session.execute(
            select(ResourceChunk)
            .where(ResourceChunk.resource_id == res.id)
            .order_by(ResourceChunk.chunk_index.asc())
        )
        .scalars()
        .all()
    )
    second_snapshot = [(c.chunk_index, c.page_number, c.text) for c in second]
    assert first_snapshot == second_snapshot


def test_lifecycle_transition_guard_blocks_invalid_jump(db_session):
    user = User(email="lifeguard@test.dev", name="LifeGuard")
    db_session.add(user)
    db_session.commit()

    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Lifecycle Guard",
        resource_type="file",
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    transition_resource_lifecycle(res, "parsing")
    transition_resource_lifecycle(res, "parsed")

    with pytest.raises(ValueError):
        transition_resource_lifecycle(res, "searchable")


def test_classify_index_error_is_structured():
    assert _classify_index_error(OcrEnvironmentError("tesseract missing")) == "ocr_environment_error"
    assert _classify_index_error(OcrParseError("bad image")) == "ocr_parse_error"
    assert _classify_index_error(PdfParseError("pdf_parse_error", "bad pdf")) == "pdf_parse_error"
    assert _classify_index_error(FileNotFoundError("no such file")) == "storage_read_error"
    assert _classify_index_error(RuntimeError("something unknown")) == "indexing_error"


def test_ocr_success_records_completed_event(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.indexing.pipeline.ocr_image", lambda _path: type("OCR", (), {"text": "ocr text"})())
    user = User(email="ocr-success@test.dev", name="OCR Success")
    db_session.add(user)
    db_session.commit()
    f = tmp_path / "scan.png"
    f.write_bytes(b"fake")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Image",
        resource_type="scan",
        original_filename="scan.png",
        mime_type="image/png",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()
    index_resource(db_session, resource_id=str(res.id))
    events = list(
        db_session.execute(
            select(ResourceLifecycleEvent)
            .where(ResourceLifecycleEvent.resource_id == res.id)
            .order_by(ResourceLifecycleEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    parse_started_count = sum(1 for e in events if e.event_type == "parse.started")
    assert parse_started_count == 1
    assert any(e.event_type == "parse.ocr_started" for e in events)
    assert any(e.event_type == "parse.ocr_completed" for e in events)
    event_types = [e.event_type for e in events]
    assert event_types == [
        "parse.started",
        "parse.ocr_started",
        "parse.succeeded",
        "parse.ocr_completed",
        "chunking.completed",
        "index.completed",
        "searchable.ready",
    ]


def test_index_resource_empty_text_sets_skipped_lifecycle(db_session, tmp_path):
    user = User(email="empty-text@test.dev", name="EmptyText")
    db_session.add(user)
    db_session.commit()
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Empty",
        resource_type="file",
        original_filename="empty.txt",
        mime_type="text/plain",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.parse_status == "parsed"
    assert res.index_status == "skipped"
    assert res.lifecycle_state == "skipped"
    assert res.index_error_code == "no_text_extracted"
    assert (res.metadata_json or {}).get("skip_reason") == "no_text_extracted"


def test_index_resource_pdf_parse_error_is_classified(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.pipeline.extract_pdf_pages",
        lambda _path: (_ for _ in ()).throw(PdfParseError("pdf_parse_error", "broken pdf")),
    )
    user = User(email="pdf-fail@test.dev", name="PdfFail")
    db_session.add(user)
    db_session.commit()
    f = tmp_path / "broken.pdf"
    f.write_bytes(b"%PDF fake")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Broken PDF",
        resource_type="file",
        original_filename="broken.pdf",
        mime_type="application/pdf",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.parse_status == "failed"
    assert res.index_status == "failed"
    assert res.parse_error_code == "pdf_parse_error"
    assert res.index_error_code == "pdf_parse_error"


def test_resource_diagnostics_summary_contains_error_codes(client, db_session):
    course = client.post("/courses", json={"name": "Diag Summary Course"}).json()
    upload = client.post(
        "/resources/upload",
        data={"course_id": course["id"], "title": "diag"},
        files={"file": ("diag.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert upload.status_code == 200
    res_id = upload.json()["id"]
    response = client.get(f"/resources/{res_id}/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert "correlation_id" in body["summary"]
    assert "resource_id" in body["summary"]
    assert "parse_error_code" in body["summary"]
    assert "index_error_code" in body["summary"]
    assert "skip_reason" in body["summary"]
    assert "skip_stage" in body["summary"]
    assert "lifecycle_state" in body["summary"]
    assert "current_stage" in body["summary"]
    assert "current_explanation" in body["summary"]
    assert "latest_stage" in body["summary"]
    assert "latest_parser" in body["summary"]
    assert "latest_failure_stage" in body["summary"]
    assert "latest_failure_message" in body["summary"]
    assert "latest_event_type" in body["summary"]
    assert "latest_error_event_type" in body["summary"]
    assert "latest_error_code" in body["summary"]
    assert "latest_warning_event_type" in body["summary"]
    assert "latest_warning_code" in body["summary"]
    assert "latest_warning_message" in body["summary"]
    assert "latest_successful_stage" in body["summary"]
    assert "latest_successful_event_type" in body["summary"]
    assert "latest_job_id" in body["summary"]
    assert "latest_index_run_id" in body["summary"]
    assert "latest_worker_id" in body["summary"]
    assert body["summary"]["event_count"] >= 1


def test_resource_diagnostics_events_include_queue_enqueue_trace(client):
    course = client.post("/courses", json={"name": "Diag Queue Course"}).json()
    upload = client.post(
        "/resources/upload",
        data={"course_id": course["id"], "title": "queued-trace"},
        files={"file": ("diag-queue.txt", io.BytesIO(b"hello queue"), "text/plain")},
    )
    assert upload.status_code == 200
    res_id = upload.json()["id"]

    response = client.get(f"/resources/{res_id}/diagnostics")
    assert response.status_code == 200
    body = response.json()
    event_types = [event["event_type"] for event in body["events"]]
    assert "resource.uploaded" in event_types
    assert "index.queued" in event_types
    queued = next(event for event in body["events"] if event["event_type"] == "index.queued")
    assert queued["details_json"]["job_id"]


def test_index_resource_trace_context_is_attached_to_lifecycle_events(db_session, tmp_path):
    user = User(email="trace-context@test.dev", name="Trace")
    db_session.add(user)
    db_session.commit()
    f = tmp_path / "trace.txt"
    f.write_text("trace me", encoding="utf-8")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Trace resource",
        resource_type="file",
        original_filename="trace.txt",
        mime_type="text/plain",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(
        db_session,
        resource_id=str(res.id),
        trace_context={"job_id": "job-trace-1", "worker_id": "worker-x", "attempt": 2},
    )
    events = list(
        db_session.execute(
            select(ResourceLifecycleEvent)
            .where(ResourceLifecycleEvent.resource_id == res.id)
            .order_by(ResourceLifecycleEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    assert events
    assert all((event.details_json or {}).get("index_run_id") for event in events)
    assert all((event.details_json or {}).get("job_id") == "job-trace-1" for event in events)
    assert all((event.details_json or {}).get("worker_id") == "worker-x" for event in events)
    assert all((event.details_json or {}).get("attempt") == 2 for event in events)


def test_index_resource_failure_trace_context_is_attached(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.pipeline.extract_pdf_pages",
        lambda _path: (_ for _ in ()).throw(PdfParseError("pdf_parse_error", "trace pdf failure")),
    )
    user = User(email="trace-failure@test.dev", name="TraceFailure")
    db_session.add(user)
    db_session.commit()
    f = tmp_path / "trace-failure.pdf"
    f.write_bytes(b"%PDF trace fail")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Trace failure",
        resource_type="file",
        original_filename="trace-failure.pdf",
        mime_type="application/pdf",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(
        db_session,
        resource_id=str(res.id),
        trace_context={"job_id": "job-trace-fail", "worker_id": "worker-y", "attempt": 4},
    )
    events = list(
        db_session.execute(
            select(ResourceLifecycleEvent)
            .where(ResourceLifecycleEvent.resource_id == res.id)
            .order_by(ResourceLifecycleEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    assert events
    failed = events[-1]
    assert failed.event_type == "parse.failed"
    assert failed.error_code == "pdf_parse_error"
    assert (failed.details_json or {}).get("job_id") == "job-trace-fail"
    assert (failed.details_json or {}).get("index_run_id")


def test_index_resource_missing_storage_path_fails_with_structured_event(db_session):
    user = User(email="missing-storage@test.dev", name="MissingStorage")
    db_session.add(user)
    db_session.commit()

    res = Resource(
        user_id=user.id,
        course_id=None,
        title="No file",
        resource_type="file",
        original_filename="missing.txt",
        mime_type="text/plain",
        storage_path=None,
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.parse_status == "failed"
    assert res.index_status == "failed"
    assert res.lifecycle_state == "failed"
    assert res.parse_error_code == "missing_storage_path"
    assert res.index_error_code == "missing_storage_path"
    events = list(
        db_session.execute(
            select(ResourceLifecycleEvent)
            .where(ResourceLifecycleEvent.resource_id == res.id)
            .order_by(ResourceLifecycleEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    assert [event.event_type for event in events] == ["parse.failed"]
    assert (events[-1].details_json or {}).get("stage") == "storage"


def test_index_resource_image_ocr_parse_error_sets_failed_state(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.pipeline.ocr_image",
        lambda _path: (_ for _ in ()).throw(OcrParseError("corrupt image")),
    )
    user = User(email="ocr-parse@test.dev", name="OCR Parse")
    db_session.add(user)
    db_session.commit()

    f = tmp_path / "broken-image.png"
    f.write_bytes(b"broken")
    res = Resource(
        user_id=user.id,
        course_id=None,
        title="Broken image",
        resource_type="scan",
        original_filename="broken-image.png",
        mime_type="image/png",
        storage_path=str(f),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(res)
    db_session.commit()

    index_resource(db_session, resource_id=str(res.id))
    db_session.refresh(res)
    assert res.parse_status == "failed"
    assert res.ocr_status == "failed"
    assert res.index_status == "failed"
    assert res.parse_error_code == "ocr_parse_error"
    assert res.index_error_code == "ocr_parse_error"
    events = list(
        db_session.execute(
            select(ResourceLifecycleEvent)
            .where(ResourceLifecycleEvent.resource_id == res.id)
            .order_by(ResourceLifecycleEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    assert [event.event_type for event in events] == ["parse.started", "parse.ocr_started", "parse.failed"]
    assert (events[-1].details_json or {}).get("stage") == "parsing"
    assert (events[-1].details_json or {}).get("message") == "corrupt image"


def test_diagnostics_summary_is_sufficient_for_skipped_and_failed_resources(client, db_session, tmp_path, monkeypatch):
    user = User(email="diag-sufficient@test.dev", name="Diag Sufficient")
    db_session.add(user)
    db_session.commit()

    skipped_file = tmp_path / "unknown.bin"
    skipped_file.write_bytes(b"\x00\x01")
    skipped = Resource(
        user_id=user.id,
        course_id=None,
        title="Skipped",
        resource_type="file",
        original_filename="unknown.bin",
        mime_type="application/octet-stream",
        storage_path=str(skipped_file),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(skipped)
    db_session.commit()
    index_resource(db_session, resource_id=str(skipped.id), trace_context={"job_id": "job-skip"})
    db_session.refresh(skipped)

    monkeypatch.setattr(
        "app.indexing.pipeline.extract_pdf_pages",
        lambda _path: (_ for _ in ()).throw(PdfParseError("pdf_parse_error", "diagnostic pdf fail")),
    )
    failed_file = tmp_path / "failed.pdf"
    failed_file.write_bytes(b"%PDF bad")
    failed = Resource(
        user_id=user.id,
        course_id=None,
        title="Failed",
        resource_type="file",
        original_filename="failed.pdf",
        mime_type="application/pdf",
        storage_path=str(failed_file),
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
    )
    db_session.add(failed)
    db_session.commit()
    index_resource(db_session, resource_id=str(failed.id), trace_context={"job_id": "job-fail"})
    db_session.refresh(failed)

    skip_diag = client.get(
        f"/resources/{skipped.id}/diagnostics",
        headers={"X-User-Id": str(user.id)},
    )
    assert skip_diag.status_code == 200
    skip_summary = skip_diag.json()["summary"]
    assert skip_summary["lifecycle_state"] == "skipped"
    assert skip_summary["skip_reason"] == "unsupported_mime"
    assert skip_summary["skip_stage"] == "parsing"
    assert skip_summary["latest_stage"] == "parsing"
    assert skip_summary["latest_error_code"] == "unsupported_media_error"
    assert skip_summary["latest_job_id"] == "job-skip"

    fail_diag = client.get(
        f"/resources/{failed.id}/diagnostics",
        headers={"X-User-Id": str(user.id)},
    )
    assert fail_diag.status_code == 200
    fail_summary = fail_diag.json()["summary"]
    assert fail_summary["lifecycle_state"] == "failed"
    assert fail_summary["latest_failure_stage"] == "parsing"
    assert fail_summary["latest_failure_message"] == "diagnostic pdf fail"
    assert fail_summary["latest_error_event_type"] == "parse.failed"
    assert fail_summary["latest_error_code"] == "pdf_parse_error"
    assert fail_summary["latest_job_id"] == "job-fail"


def test_reindex_enqueues_queue_event_and_clears_stale_errors(client, db_session):
    course = client.post("/courses", json={"name": "Reindex Queue Course"}).json()
    upload = client.post(
        "/resources/upload",
        data={"course_id": course["id"], "title": "reindex-me"},
        files={"file": ("reindex.txt", io.BytesIO(b"hello reindex"), "text/plain")},
    )
    assert upload.status_code == 200
    resource = upload.json()
    resource_id = resource["id"]

    resource_row = db_session.get(Resource, UUID(resource_id))
    assert resource_row is not None
    resource_row.parse_error_code = "pdf_parse_error"
    resource_row.index_error_code = "indexing_error"
    resource_row.metadata_json = {"skip_reason": "old_reason", "index_error": "old error"}
    db_session.add(resource_row)
    db_session.commit()

    reindex = client.post(f"/resources/{resource_id}/reindex")
    assert reindex.status_code == 200
    body = reindex.json()
    assert body["lifecycle_state"] == "queued"
    assert body["index_status"] == "queued"
    assert body["parse_error_code"] is None
    assert body["index_error_code"] is None

    diag = client.get(f"/resources/{resource_id}/diagnostics")
    assert diag.status_code == 200
    payload = diag.json()
    assert payload["summary"]["latest_event_type"] == "index.queued"
    assert payload["summary"]["latest_job_id"]
    queued = payload["events"][-1]
    assert queued["event_type"] == "index.queued"
    assert queued["to_state"] == "queued"
    assert queued["details_json"]["source"] == "reindex"
