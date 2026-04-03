from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ResourceCreate(BaseModel):
    course_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    resource_type: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    storage_path: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    parse_status: str = "uploaded"
    ocr_status: str = "pending"
    index_status: str = "pending"
    lifecycle_state: str = "uploaded"
    metadata_json: dict | None = None
    content_sha256: str | None = None
    parse_pipeline_version: str = "v1"
    chunking_version: str = "char-v1"


class ResourceUpdate(BaseModel):
    course_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    resource_type: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    storage_path: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    parse_status: str | None = None
    ocr_status: str | None = None
    index_status: str | None = None
    lifecycle_state: str | None = None
    metadata_json: dict | None = None
    content_sha256: str | None = None
    parse_pipeline_version: str | None = None
    chunking_version: str | None = None


class ResourceRead(BaseModel):
    id: UUID
    user_id: UUID
    course_id: UUID | None
    title: str
    resource_type: str | None
    original_filename: str | None
    mime_type: str | None
    storage_path: str | None
    source_type: str | None
    source_ref: str | None
    parse_status: str
    ocr_status: str
    index_status: str
    lifecycle_state: str
    metadata_json: dict | None
    parse_error_code: str | None
    index_error_code: str | None
    content_sha256: str | None
    parse_pipeline_version: str
    chunking_version: str
    indexed_at: datetime | None
    last_lifecycle_event_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResourceBatchUploadResult(BaseModel):
    filename: str
    mime_type: str | None = None
    status: str
    reason: str | None = None
    resource: ResourceRead | None = None


class ResourceLifecycleEventRead(BaseModel):
    id: UUID
    resource_id: UUID
    user_id: UUID
    seq: int
    from_state: str | None
    to_state: str
    event_type: str
    error_code: str | None
    details_json: dict | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResourceDiagnosticsSummary(BaseModel):
    correlation_id: str
    resource_id: str
    parse_error_code: str | None
    index_error_code: str | None
    skip_reason: str | None
    skip_stage: str | None
    lifecycle_state: str
    current_stage: str | None
    current_explanation: str
    latest_stage: str | None
    latest_parser: str | None
    latest_failure_stage: str | None
    latest_failure_message: str | None
    latest_event_type: str | None
    latest_error_event_type: str | None
    latest_error_code: str | None
    latest_warning_event_type: str | None
    latest_warning_code: str | None
    latest_warning_message: str | None
    latest_successful_stage: str | None
    latest_successful_event_type: str | None
    latest_job_id: str | None
    latest_index_run_id: str | None
    latest_worker_id: str | None
    metadata_errors: dict[str, str | None]
    event_count: int


class ResourceDiagnosticsRead(BaseModel):
    resource: ResourceRead
    events: list[ResourceLifecycleEventRead]
    summary: ResourceDiagnosticsSummary

