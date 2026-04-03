from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.core.config import get_settings
from app.core.telemetry import emit_diagnostic
from app.models.resource import Resource
from app.models.resource_lifecycle_event import ResourceLifecycleEvent
from app.models.resource_chunk import ResourceChunk
from app.schemas.jobs import BackgroundJobRead, ResourceChunkPreview
from app.schemas.resource import (
    ResourceBatchUploadResult,
    ResourceCreate,
    ResourceDiagnosticsSummary,
    ResourceDiagnosticsRead,
    ResourceLifecycleEventRead,
    ResourceRead,
    ResourceUpdate,
)
from app.services import courses as course_service
from app.services import resources as resource_service
from app.services import jobs as job_service
from app.services.resource_lifecycle import record_resource_event, transition_resource_lifecycle
from app.services.storage import get_storage_service
router = APIRouter(prefix="/resources", tags=["resources"])

_CHUNK_PREVIEW_LEN = 500
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB baseline guardrail for MVP
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
_ALLOWED_EXACT_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


def _delete_resource_storage_tree(storage_root: str, storage_path: str | None) -> None:
    """Best-effort delete of resource file and its UUID parent folder."""
    if not storage_path:
        return
    path = Path(storage_path)
    root = Path(storage_root).resolve()

    try:
        abs_path = path.resolve()
    except Exception:
        return

    # Only allow deletes inside configured storage root.
    try:
        abs_path.relative_to(root)
    except Exception:
        return

    # Remove the file if it exists.
    try:
        abs_path.unlink(missing_ok=True)
    except Exception:
        pass

    # If parent under root is UUID-like, remove whole resource directory.
    parent = abs_path.parent
    if parent == root:
        return
    try:
        parent.relative_to(root)
    except Exception:
        return
    try:
        UUID(parent.name)
    except Exception:
        return
    try:
        shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        pass


def _is_allowed_upload_mime(mime: str | None) -> bool:
    if not mime:
        return False
    normalized = mime.lower().strip()
    if normalized in _ALLOWED_EXACT_MIME_TYPES:
        return True
    return normalized.startswith("text/")


async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    size = 0
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=413, detail=f"File too large (max {max_bytes} bytes)")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("", response_model=list[ResourceRead])
def list_resources(
    course_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    if course_id is not None:
        course = course_service.get_course(db, user=user, course_id=course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return resource_service.list_resources(db, user=user, course_id=course_id, limit=limit, offset=offset)


@router.post("", response_model=ResourceRead)
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    if payload.course_id is not None:
        course = course_service.get_course(db, user=user, course_id=payload.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return resource_service.create_resource(db, user=user, data=payload)


@router.post("/upload", response_model=ResourceRead)
async def upload_resource(
    file: UploadFile = File(...),
    course_id: UUID | None = Form(default=None),
    title: str | None = Form(default=None),
    resource_type: str | None = Form(default=None),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    if course_id is not None:
        course = course_service.get_course(db, user=user, course_id=course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

    settings = get_settings()
    storage = get_storage_service(settings)

    data = await _read_upload_limited(file, _MAX_UPLOAD_BYTES)
    if not _is_allowed_upload_mime(file.content_type):
        emit_diagnostic(
            "resource_upload_rejected_mime",
            level="warning",
            user_id=str(user.id),
            mime_type=file.content_type or "unknown",
        )
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {file.content_type or 'unknown'}")
    safe_filename = Path(file.filename or "upload.bin").name or "upload.bin"

    # Store under uploads/<resource_id>/<original_filename>
    resource = Resource(
        user_id=user.id,
        course_id=course_id,
        title=title or safe_filename or "Untitled",
        resource_type=resource_type or "file",
        original_filename=safe_filename,
        mime_type=file.content_type,
        parse_status="uploaded",
        ocr_status="pending",
        index_status="pending",
        lifecycle_state="uploaded",
        content_sha256=hashlib.sha256(data).hexdigest(),
        parse_pipeline_version="v1",
        chunking_version="char-v1",
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    record_resource_event(
        db,
        resource=resource,
        event_type="resource.uploaded",
        to_state=resource.lifecycle_state,
        details={"filename": safe_filename, "mime_type": file.content_type},
    )
    db.commit()

    rel_path = f"{resource.id}/{safe_filename}"
    stored = storage.put_bytes(relative_path=rel_path, data=data)

    resource.storage_path = stored.storage_path
    db.add(resource)
    db.commit()
    db.refresh(resource)

    r = Redis.from_url(settings.redis_url)
    try:
        job = job_service.create_and_enqueue_parse(
            db,
            redis=r,
            user=user,
            resource=resource,
            idempotency_key=f"upload:{resource.id}",
        )
    except Exception as exc:  # noqa: BLE001
        emit_diagnostic(
            "resource_upload_enqueue_failed",
            level="error",
            user_id=str(user.id),
            resource_id=str(resource.id),
            correlation_id=f"resource:{resource.id}",
            error=str(exc),
        )
        raise

    resource.index_status = "queued"
    meta = dict(resource.metadata_json or {})
    meta["latest_job_id"] = str(job.id)
    resource.metadata_json = meta
    db.add(resource)
    transition_resource_lifecycle(
        resource,
        "queued",
        db=db,
        event_type="index.queued",
        details={"job_id": str(job.id), "source": "upload", "stage": "queue"},
    )
    db.commit()
    db.refresh(resource)
    emit_diagnostic(
        "resource_upload_enqueued",
        user_id=str(user.id),
        resource_id=str(resource.id),
        job_id=str(job.id),
        correlation_id=f"job:{job.id}",
        course_id=str(resource.course_id) if resource.course_id else None,
    )

    return resource


@router.post("/upload-batch", response_model=list[ResourceBatchUploadResult])
async def upload_resource_batch(
    files: list[UploadFile] = File(...),
    course_id: UUID | None = Form(default=None),
    resource_type: str | None = Form(default=None),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    if course_id is not None:
        course = course_service.get_course(db, user=user, course_id=course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    if len(files) == 0:
        raise HTTPException(status_code=422, detail="No files provided")

    settings = get_settings()
    storage = get_storage_service(settings)
    r = Redis.from_url(settings.redis_url)
    results: list[ResourceBatchUploadResult] = []

    for file in files:
        safe_filename = Path(file.filename or "upload.bin").name or "upload.bin"
        try:
            data = await _read_upload_limited(file, _MAX_UPLOAD_BYTES)
        except HTTPException:
            emit_diagnostic(
                "resource_batch_file_rejected_size",
                level="warning",
                user_id=str(user.id),
                filename=safe_filename,
            )
            results.append(
                ResourceBatchUploadResult(
                    filename=safe_filename,
                    mime_type=file.content_type,
                    status="rejected",
                    reason=f"file too large (max {_MAX_UPLOAD_BYTES} bytes)",
                )
            )
            continue
        if not _is_allowed_upload_mime(file.content_type):
            emit_diagnostic(
                "resource_batch_file_rejected_mime",
                level="warning",
                user_id=str(user.id),
                filename=safe_filename,
                mime_type=file.content_type or "unknown",
            )
            results.append(
                ResourceBatchUploadResult(
                    filename=safe_filename,
                    mime_type=file.content_type,
                    status="rejected",
                    reason=f"unsupported file type: {file.content_type or 'unknown'}",
                )
            )
            continue
        resource = Resource(
            user_id=user.id,
            course_id=course_id,
            title=safe_filename,
            resource_type=resource_type or "file",
            original_filename=safe_filename,
            mime_type=file.content_type,
            parse_status="uploaded",
            ocr_status="pending",
            index_status="pending",
            lifecycle_state="uploaded",
            content_sha256=hashlib.sha256(data).hexdigest(),
            parse_pipeline_version="v1",
            chunking_version="char-v1",
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
        record_resource_event(
            db,
            resource=resource,
            event_type="resource.uploaded",
            to_state=resource.lifecycle_state,
            details={"filename": safe_filename, "mime_type": file.content_type},
        )
        db.commit()

        rel_path = f"{resource.id}/{safe_filename}"
        stored = storage.put_bytes(relative_path=rel_path, data=data)
        resource.storage_path = stored.storage_path
        db.add(resource)
        db.commit()
        db.refresh(resource)

        try:
            job = job_service.create_and_enqueue_parse(
                db,
                redis=r,
                user=user,
                resource=resource,
                idempotency_key=f"upload:{resource.id}",
            )
        except Exception as exc:  # noqa: BLE001
            emit_diagnostic(
                "resource_batch_file_enqueue_failed",
                level="error",
                user_id=str(user.id),
                resource_id=str(resource.id),
                filename=safe_filename,
                correlation_id=f"resource:{resource.id}",
                error=str(exc),
            )
            results.append(
                ResourceBatchUploadResult(
                    filename=safe_filename,
                    mime_type=file.content_type,
                    status="rejected",
                    reason="enqueue failed",
                )
            )
            continue
        resource.index_status = "queued"
        meta = dict(resource.metadata_json or {})
        meta["latest_job_id"] = str(job.id)
        resource.metadata_json = meta
        transition_resource_lifecycle(
            resource,
            "queued",
            db=db,
            event_type="index.queued",
            details={"job_id": str(job.id), "source": "upload_batch", "stage": "queue"},
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
        results.append(
            ResourceBatchUploadResult(
                filename=safe_filename,
                mime_type=file.content_type,
                status="accepted",
                resource=ResourceRead.model_validate(resource),
            )
        )
        emit_diagnostic(
            "resource_batch_file_enqueued",
            user_id=str(user.id),
            resource_id=str(resource.id),
            job_id=str(job.id),
            correlation_id=f"job:{job.id}",
            filename=safe_filename,
        )

    return results


@router.get("/{resource_id}/jobs", response_model=list[BackgroundJobRead])
def list_resource_jobs(
    resource_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return job_service.list_jobs_for_resource(db, user=user, resource_id=resource_id)


@router.get("/{resource_id}/chunks", response_model=list[ResourceChunkPreview])
def list_resource_chunks(
    resource_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    rows = (
        db.execute(
            select(ResourceChunk)
            .where(
                ResourceChunk.resource_id == resource_id,
                ResourceChunk.user_id == user.id,
            )
            .order_by(ResourceChunk.chunk_index.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        ResourceChunkPreview(
            id=c.id,
            chunk_index=c.chunk_index,
            page_number=c.page_number,
            text_preview=(c.text[:_CHUNK_PREVIEW_LEN] + ("…" if len(c.text) > _CHUNK_PREVIEW_LEN else "")),
        )
        for c in rows
    ]


@router.get("/{resource_id}", response_model=ResourceRead)
def get_resource(resource_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.course_id is not None:
        course = course_service.get_course(db, user=user, course_id=resource.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return resource


@router.get("/{resource_id}/diagnostics", response_model=ResourceDiagnosticsRead)
def get_resource_diagnostics(
    resource_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        emit_diagnostic("resource_diagnostics_not_found", resource_id=str(resource_id), user_id=str(user.id))
        raise HTTPException(status_code=404, detail="Resource not found")
    events = (
        db.execute(
            select(ResourceLifecycleEvent)
            .where(
                ResourceLifecycleEvent.resource_id == resource_id,
                ResourceLifecycleEvent.user_id == user.id,
            )
            .order_by(ResourceLifecycleEvent.seq.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    emit_diagnostic(
        "resource_diagnostics_read",
        user_id=str(user.id),
        resource_id=str(resource.id),
        event_count=len(events),
        parse_status=resource.parse_status,
        index_status=resource.index_status,
        lifecycle_state=resource.lifecycle_state,
        latest_job_id=(resource.metadata_json or {}).get("latest_job_id"),
        latest_index_run_id=(resource.metadata_json or {}).get("latest_index_run_id"),
        parse_error_code=resource.parse_error_code,
        index_error_code=resource.index_error_code,
    )
    latest_error_event = next(
        (event for event in reversed(events) if event.error_code and event.event_type != "embedding.warning"),
        None,
    )
    latest_warning_event = next((event for event in reversed(events) if event.event_type == "embedding.warning"), None)
    latest_skip_event = next((event for event in reversed(events) if event.event_type.endswith(".skipped")), None)
    latest_stage_event = events[-1] if events else None
    latest_success_event = next(
        (
            event
            for event in reversed(events)
            if event.event_type in {"parse.succeeded", "chunking.completed", "index.completed", "searchable.ready"}
        ),
        None,
    )
    meta = resource.metadata_json or {}
    error_details = latest_error_event.details_json or {} if latest_error_event else {}
    warning_details = latest_warning_event.details_json or {} if latest_warning_event else {}
    skip_details = latest_skip_event.details_json or {} if latest_skip_event else {}
    latest_stage_details = latest_stage_event.details_json or {} if latest_stage_event else {}
    latest_success_details = latest_success_event.details_json or {} if latest_success_event else {}
    latest_parser = next(
        (
            (event.details_json or {}).get("parser")
            for event in reversed(events)
            if (event.details_json or {}).get("parser")
        ),
        None,
    )
    latest_worker_id = next(
        (
            (event.details_json or {}).get("worker_id")
            for event in reversed(events)
            if (event.details_json or {}).get("worker_id")
        ),
        None,
    )
    current_stage = (
        latest_stage_details.get("stage")
        or skip_details.get("stage")
        or error_details.get("stage")
        or resource.lifecycle_state
    )
    if resource.lifecycle_state == "failed":
        current_explanation = (
            f"Resource failed during {error_details.get('stage') or current_stage}: "
            f"{error_details.get('message') or latest_error_event.error_code if latest_error_event else 'unknown error'}"
        )
    elif resource.lifecycle_state == "skipped":
        current_explanation = (
            f"Resource indexing was skipped at {skip_details.get('stage') or current_stage}: "
            f"{skip_details.get('reason') or meta.get('skip_reason') or 'unspecified skip'}"
        )
    elif resource.lifecycle_state == "searchable":
        current_explanation = "Resource is searchable and indexing is complete."
    elif resource.lifecycle_state == "queued":
        current_explanation = "Resource is queued and waiting for worker processing."
    elif resource.lifecycle_state == "parsing":
        current_explanation = "Resource is currently in parsing."
    else:
        current_explanation = f"Resource is currently in state '{resource.lifecycle_state}'."
    correlation_id = (
        f"job:{meta.get('latest_job_id')}" if meta.get("latest_job_id") else f"resource:{resource.id}"
    )
    return ResourceDiagnosticsRead(
        resource=ResourceRead.model_validate(resource),
        events=[ResourceLifecycleEventRead.model_validate(e) for e in events],
        summary=ResourceDiagnosticsSummary(
            correlation_id=correlation_id,
            resource_id=str(resource.id),
            parse_error_code=resource.parse_error_code,
            index_error_code=resource.index_error_code,
            skip_reason=skip_details.get("reason") or meta.get("skip_reason"),
            skip_stage=skip_details.get("stage"),
            lifecycle_state=resource.lifecycle_state,
            current_stage=current_stage,
            current_explanation=current_explanation,
            latest_stage=latest_stage_details.get("stage"),
            latest_parser=latest_parser,
            latest_failure_stage=error_details.get("stage"),
            latest_failure_message=error_details.get("message"),
            latest_event_type=events[-1].event_type if events else None,
            latest_error_event_type=latest_error_event.event_type if latest_error_event else None,
            latest_error_code=latest_error_event.error_code if latest_error_event else None,
            latest_warning_event_type=latest_warning_event.event_type if latest_warning_event else None,
            latest_warning_code=latest_warning_event.error_code if latest_warning_event else None,
            latest_warning_message=warning_details.get("message"),
            latest_successful_stage=latest_success_details.get("stage"),
            latest_successful_event_type=latest_success_event.event_type if latest_success_event else None,
            latest_job_id=meta.get("latest_job_id"),
            latest_index_run_id=meta.get("latest_index_run_id"),
            latest_worker_id=latest_worker_id,
            metadata_errors={
                "index_error": meta.get("index_error"),
                "ocr_error": meta.get("ocr_error"),
                "embedding_error": meta.get("embedding_error"),
            },
            event_count=len(events),
        ),
    )


@router.patch("/{resource_id}", response_model=ResourceRead)
def update_resource(
    resource_id: UUID,
    payload: ResourceUpdate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        emit_diagnostic("resource_reindex_not_found", resource_id=str(resource_id), user_id=str(user.id))
        raise HTTPException(status_code=404, detail="Resource not found")
    target_course_id = payload.course_id if payload.course_id is not None else resource.course_id
    if target_course_id is not None:
        course = course_service.get_course(db, user=user, course_id=target_course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return resource_service.update_resource(db, resource=resource, data=payload)


@router.delete("/{resource_id}")
def delete_resource(resource_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Best-effort storage cleanup (chunks/jobs cascade via FK).
    settings = get_settings()
    if resource.storage_path and resource.storage_path.startswith("s3://"):
        try:
            # storage_path format: s3://bucket/key
            key = resource.storage_path.split("/", 3)[3]
            storage = get_storage_service(settings)
            storage.delete(relative_path=key)
        except Exception:
            pass
    else:
        _delete_resource_storage_tree(settings.storage_root, resource.storage_path)

    db.delete(resource)
    db.commit()
    return {"ok": True}


@router.post("/{resource_id}/reindex", response_model=ResourceRead)
def reindex_resource(resource_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not resource.storage_path:
        emit_diagnostic(
            "resource_reindex_blocked_missing_storage",
            level="warning",
            user_id=str(user.id),
            resource_id=str(resource.id),
            correlation_id=f"resource:{resource.id}",
        )
        raise HTTPException(status_code=409, detail="Resource has no storage_path and cannot be reindexed")

    settings = get_settings()
    r = Redis.from_url(settings.redis_url)
    try:
        job = job_service.create_and_enqueue_parse(
            db,
            redis=r,
            user=user,
            resource=resource,
            idempotency_key=f"reindex:{resource.id}",
        )
    except Exception as exc:  # noqa: BLE001
        emit_diagnostic(
            "resource_reindex_enqueue_failed",
            level="error",
            user_id=str(user.id),
            resource_id=str(resource.id),
            correlation_id=f"resource:{resource.id}",
            error=str(exc),
        )
        raise

    resource.index_status = "queued"
    resource.parse_status = "uploaded" if resource.storage_path else resource.parse_status
    resource.ocr_status = "pending"
    resource.parse_error_code = None
    resource.index_error_code = None
    meta = dict(resource.metadata_json or {})
    for key in ("skip_reason", "index_error", "index_error_code", "ocr_error", "ocr_error_code", "embedding_error"):
        meta.pop(key, None)
    meta["latest_job_id"] = str(job.id)
    resource.metadata_json = meta
    if resource.storage_path:
        transition_resource_lifecycle(
            resource,
            "uploaded",
            db=db,
            event_type="resource.reindex_requested",
            details={"source": "api"},
        )
    transition_resource_lifecycle(
        resource,
        "queued",
        db=db,
        event_type="index.queued",
        details={"job_id": str(job.id), "source": "reindex", "stage": "queue"},
    )
    resource.indexed_at = None
    db.add(resource)
    db.commit()
    db.refresh(resource)
    emit_diagnostic(
        "resource_reindex_requested",
        resource_id=str(resource.id),
        user_id=str(user.id),
        job_id=str(job.id),
        correlation_id=f"job:{job.id}",
    )
    return resource

