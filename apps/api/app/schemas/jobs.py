from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BackgroundJobRead(BaseModel):
    id: UUID
    user_id: UUID
    resource_id: UUID
    job_type: str
    status: str
    attempts: int
    last_error: str | None
    idempotency_key: str | None
    started_at: datetime | None
    finished_at: datetime | None
    available_at: datetime | None
    claimed_by: str | None
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    lease_recovery_detected: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResourceChunkPreview(BaseModel):
    id: UUID
    chunk_index: int
    page_number: int | None
    text_preview: str

    model_config = {"from_attributes": True}


class DeadLetterJobRead(BaseModel):
    id: UUID
    user_id: UUID | None
    resource_id: UUID | None
    background_job_id: UUID | None
    queue_name: str
    reason: str
    reason_code: str | None
    attempts: int
    replay_key: str | None
    payload_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobLifecycleRead(BaseModel):
    current_status: str
    claim_state: str
    lease_state: str
    lease_valid_now: bool | None
    next_action: str
    recovery_detected: bool
    replay_eligible: bool
    replay_block_reason: str | None
    attempts: int
    dead_letter_attempts: int | None
    dead_lettered: bool


class JobOperatorSummaryRead(BaseModel):
    correlation_id: str
    job_id: str
    resource_id: str
    dead_letter_id: str | None
    status: str
    is_running: bool
    lease_expired: bool
    retry_scheduled: bool
    dead_lettered: bool
    recovered_from_expiration: bool
    replayed: bool
    replay_eligible: bool
    attempts: int
    dead_letter_attempts: int | None
    available_at: datetime | None
    lease_expires_at: datetime | None
    last_error: str | None
    dead_letter_reason: str | None
    dead_letter_reason_code: str | None
    operator_explanation: str
    next_operator_action: str


class JobDiagnosticsRead(BaseModel):
    job: BackgroundJobRead
    dead_letter: DeadLetterJobRead | None
    lifecycle: JobLifecycleRead
    summary: JobOperatorSummaryRead


class ReplayDeadLetterResponse(BaseModel):
    replayed: bool
    replayed_dead_letter_id: UUID
    previous_attempts: int
    current_attempts: int
    job: BackgroundJobRead
