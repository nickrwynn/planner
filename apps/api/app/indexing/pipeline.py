from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.parsing.ocr import OcrEnvironmentError, OcrParseError, classify_ocr_error, ocr_image
from app.parsing.pdf import PdfParseError, extract_pdf_pages
from app.indexing.chunk_embeddings import embed_resource_chunks_if_configured
from app.indexing.chunking import chunk_text
from app.services.resource_lifecycle import merge_event_details, record_resource_event, transition_resource_lifecycle


def _classify_index_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if isinstance(exc, OcrEnvironmentError):
        return "ocr_environment_error"
    if isinstance(exc, OcrParseError):
        return "ocr_parse_error"
    if isinstance(exc, PdfParseError):
        return exc.code
    if "pdf" in msg:
        return "pdf_parse_error"
    if "unsupported" in msg or "mime" in msg:
        return "unsupported_media_error"
    if "embedding" in msg:
        return "embedding_error"
    if "no such file" in msg or "cannot read" in msg:
        return "storage_read_error"
    return "indexing_error"


def _stage_for_error_code(code: str) -> str:
    if code in {
        "missing_storage_path",
        "storage_read_error",
        "pdf_parse_error",
        "ocr_environment_error",
        "ocr_parse_error",
        "unsupported_media_error",
    }:
        return "parsing"
    if code == "embedding_error":
        return "embedding"
    return "indexing"


def index_resource(
    db: Session,
    *,
    resource_id: str,
    trace_context: dict | None = None,
) -> None:
    rid: UUID | None
    try:
        rid = UUID(str(resource_id))
    except Exception:  # noqa: BLE001
        rid = None
    if rid is None:
        return

    resource = db.get(Resource, rid)
    if not resource:
        return
    trace = {"index_run_id": str(uuid4())}
    if trace_context:
        for key, value in trace_context.items():
            if value is not None:
                trace[key] = value

    # Reset chunks
    db.execute(
        delete(ResourceChunk).where(
            ResourceChunk.resource_id == resource.id,
            ResourceChunk.user_id == resource.user_id,
        )
    )
    db.commit()

    if not resource.storage_path:
        resource.parse_status = "failed"
        resource.index_status = "failed"
        resource.parse_error_code = "missing_storage_path"
        resource.index_error_code = "missing_storage_path"
        transition_resource_lifecycle(
            resource,
            "failed",
            db=db,
            event_type="parse.failed",
            error_code="missing_storage_path",
            details=merge_event_details(
                {"stage": "storage", "reason": "resource has no storage_path", "outcome": "failed"},
                trace=trace,
            ),
        )
        db.add(resource)
        db.commit()
        return

    mime = (resource.mime_type or "").lower()
    meta = dict(resource.metadata_json or {})
    for key in (
        "skip_reason",
        "index_error",
        "index_error_code",
        "ocr_error",
        "ocr_error_code",
        "embedding_error",
    ):
        meta.pop(key, None)
    meta["latest_index_run_id"] = trace["index_run_id"]
    if "job_id" in trace:
        meta["latest_job_id"] = trace["job_id"]
    resource.metadata_json = meta
    resource.parse_pipeline_version = "v1"
    resource.chunking_version = "char-v1"
    if resource.storage_path and Path(resource.storage_path).exists():
        try:
            resource.content_sha256 = hashlib.sha256(Path(resource.storage_path).read_bytes()).hexdigest()
        except Exception:
            pass

    try:
        resource.parse_status = "parsing"
        transition_resource_lifecycle(
            resource,
            "parsing",
            db=db,
            event_type="parse.started",
            details=merge_event_details({"parser": "auto", "stage": "parsing"}, trace=trace),
        )
        db.add(resource)
        db.commit()

        chunks_to_insert: list[ResourceChunk] = []

        if mime == "application/pdf" or resource.storage_path.lower().endswith(".pdf"):
            pages = extract_pdf_pages(resource.storage_path)
            for page in pages:
                for ch in chunk_text(text=page.text, page_number=page.page_number):
                    chunks_to_insert.append(
                        ResourceChunk(
                            user_id=resource.user_id,
                            resource_id=resource.id,
                            chunk_index=ch.chunk_index,
                            page_number=ch.page_number,
                            text=ch.text,
                        )
                    )
            resource.parse_status = "parsed"
            resource.ocr_status = "skipped"
            resource.parse_error_code = None
            resource.index_error_code = None
            transition_resource_lifecycle(
                resource,
                "parsed",
                db=db,
                event_type="parse.succeeded",
                details=merge_event_details(
                    {"parser": "pdf", "pages": len(pages), "stage": "parsing", "outcome": "parsed"},
                    trace=trace,
                ),
            )

        elif mime.startswith("image/"):
            # OCR fallback for images
            resource.parse_status = "parsing"
            resource.ocr_status = "running"
            record_resource_event(
                db=db,
                resource=resource,
                event_type="parse.ocr_started",
                from_state=resource.lifecycle_state,
                to_state=resource.lifecycle_state,
                details=merge_event_details({"parser": "ocr", "stage": "parsing"}, trace=trace),
            )
            db.add(resource)
            db.commit()

            try:
                ocr = ocr_image(resource.storage_path)
            except OcrEnvironmentError as e:
                code = classify_ocr_error(e)
                meta = dict(resource.metadata_json or {})
                meta["ocr_error"] = str(e)
                meta["ocr_error_code"] = code
                resource.metadata_json = meta
                resource.parse_status = "failed"
                resource.ocr_status = "failed"
                resource.index_status = "failed"
                resource.parse_error_code = code
                resource.index_error_code = code
                transition_resource_lifecycle(
                    resource,
                    "failed",
                    db=db,
                    event_type="parse.failed",
                    error_code=code,
                    details=merge_event_details(
                        {
                            "parser": "ocr",
                            "stage": "parsing",
                            "message": str(e),
                            "outcome": "failed",
                        },
                        trace=trace,
                    ),
                )
                db.add(resource)
                db.commit()
                return
            except OcrParseError as e:
                code = classify_ocr_error(e)
                meta = dict(resource.metadata_json or {})
                meta["ocr_error"] = str(e)
                meta["ocr_error_code"] = code
                resource.metadata_json = meta
                resource.parse_status = "failed"
                resource.ocr_status = "failed"
                resource.index_status = "failed"
                resource.parse_error_code = code
                resource.index_error_code = code
                transition_resource_lifecycle(
                    resource,
                    "failed",
                    db=db,
                    event_type="parse.failed",
                    error_code=code,
                    details=merge_event_details(
                        {
                            "parser": "ocr",
                            "stage": "parsing",
                            "message": str(e),
                            "outcome": "failed",
                        },
                        trace=trace,
                    ),
                )
                db.add(resource)
                db.commit()
                return
            for ch in chunk_text(text=ocr.text, page_number=None):
                chunks_to_insert.append(
                    ResourceChunk(
                        user_id=resource.user_id,
                        resource_id=resource.id,
                        chunk_index=ch.chunk_index,
                        page_number=None,
                        text=ch.text,
                    )
                )
            resource.ocr_status = "done"
            resource.parse_status = "parsed"
            resource.parse_error_code = None
            resource.index_error_code = None
            transition_resource_lifecycle(
                resource,
                "parsed",
                db=db,
                event_type="parse.succeeded",
                details=merge_event_details(
                    {"parser": "ocr", "stage": "parsing", "outcome": "parsed"},
                    trace=trace,
                ),
            )
            record_resource_event(
                db=db,
                resource=resource,
                event_type="parse.ocr_completed",
                from_state=resource.lifecycle_state,
                to_state=resource.lifecycle_state,
                details=merge_event_details({"parser": "ocr", "stage": "parsing"}, trace=trace),
            )

        elif mime.startswith("text/") or resource.storage_path.lower().endswith(".txt"):
            raw_text = Path(resource.storage_path).read_text(encoding="utf-8", errors="replace")
            for ch in chunk_text(text=raw_text, page_number=None):
                chunks_to_insert.append(
                    ResourceChunk(
                        user_id=resource.user_id,
                        resource_id=resource.id,
                        chunk_index=ch.chunk_index,
                        page_number=None,
                        text=ch.text,
                    )
                )
            resource.parse_status = "parsed"
            resource.ocr_status = "skipped"
            resource.parse_error_code = None
            resource.index_error_code = None
            transition_resource_lifecycle(
                resource,
                "parsed",
                db=db,
                event_type="parse.succeeded",
                details=merge_event_details(
                    {"parser": "text", "stage": "parsing", "outcome": "parsed"},
                    trace=trace,
                ),
            )

        else:
            # Unknown type: no parsing
            resource.parse_status = "skipped"
            resource.ocr_status = "skipped"
            resource.index_status = "skipped"
            resource.parse_error_code = "unsupported_media_error"
            resource.index_error_code = "unsupported_media_error"
            transition_resource_lifecycle(
                resource,
                "skipped",
                db=db,
                event_type="parse.skipped",
                error_code="unsupported_media_error",
                details=merge_event_details(
                    {
                        "stage": "parsing",
                        "reason": "unsupported_mime",
                        "outcome": "skipped",
                        "intentional_skip": True,
                    },
                    trace=trace,
                ),
            )
            meta = dict(resource.metadata_json or {})
            meta["skip_reason"] = "unsupported_mime"
            resource.metadata_json = meta

        if chunks_to_insert:
            transition_resource_lifecycle(
                resource,
                "chunked",
                db=db,
                event_type="chunking.completed",
                details=merge_event_details(
                    {"stage": "chunking", "chunk_count": len(chunks_to_insert)},
                    trace=trace,
                ),
            )

        embed_error = embed_resource_chunks_if_configured(chunks_to_insert)
        if embed_error:
            meta = dict(resource.metadata_json or {})
            meta["embedding_error"] = embed_error
            resource.metadata_json = meta
            resource.index_error_code = "embedding_error"
            record_resource_event(
                db,
                resource=resource,
                event_type="embedding.warning",
                error_code="embedding_error",
                details=merge_event_details(
                    {"stage": "embedding", "message": embed_error},
                    trace=trace,
                ),
            )

        db.add_all(chunks_to_insert)
        if chunks_to_insert:
            transition_resource_lifecycle(
                resource,
                "indexed",
                db=db,
                event_type="index.completed",
                details=merge_event_details(
                    {"stage": "indexing", "chunk_count": len(chunks_to_insert)},
                    trace=trace,
                ),
            )
            resource.index_status = "done"
            if not embed_error:
                resource.index_error_code = None
            resource.indexed_at = datetime.now(timezone.utc)
            transition_resource_lifecycle(
                resource,
                "searchable",
                db=db,
                event_type="searchable.ready",
                details=merge_event_details({"stage": "searchable"}, trace=trace),
            )
        else:
            resource.index_status = "skipped"
            resource.indexed_at = None
            meta = dict(resource.metadata_json or {})
            if resource.parse_status == "skipped":
                meta.setdefault("skip_reason", "unsupported_mime")
                resource.index_error_code = resource.index_error_code or "unsupported_media_error"
            else:
                meta.setdefault("skip_reason", "no_text_extracted")
                resource.index_error_code = "no_text_extracted"
            resource.metadata_json = meta
            transition_resource_lifecycle(
                resource,
                "skipped",
                db=db,
                event_type="index.skipped",
                error_code=resource.index_error_code,
                details=merge_event_details(
                    {
                        "stage": "indexing",
                        "reason": meta.get("skip_reason"),
                        "outcome": "skipped",
                        "intentional_skip": True,
                    },
                    trace=trace,
                ),
            )

        db.add(resource)
        db.commit()
    except Exception as e:  # noqa: BLE001
        # Preserve error in metadata_json without expanding schema
        code = _classify_index_error(e)
        stage = _stage_for_error_code(code)
        meta = dict(resource.metadata_json or {})
        meta["index_error"] = str(e)
        meta["index_error_code"] = code
        resource.metadata_json = meta
        resource.index_status = "failed"
        resource.index_error_code = code
        if stage == "parsing":
            resource.parse_status = "failed"
            resource.ocr_status = "failed"
            resource.parse_error_code = code
        else:
            if resource.parse_status == "parsing":
                resource.parse_status = "parsed"
            if resource.ocr_status == "running":
                resource.ocr_status = "done"
        transition_resource_lifecycle(
            resource,
            "failed",
            db=db,
            event_type="parse.failed" if stage == "parsing" else "index.failed",
            error_code=code,
            details=merge_event_details(
                {"stage": stage, "message": str(e), "outcome": "failed"},
                trace=trace,
            ),
        )
        resource.indexed_at = None
        db.add(resource)
        db.commit()

