from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from redis import Redis
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.core.config import get_settings
from app.core.telemetry import emit_diagnostic
from app.schemas.jobs import (
    BackgroundJobRead,
    DeadLetterJobRead,
    JobDiagnosticsRead,
    JobLifecycleRead,
    JobOperatorSummaryRead,
    ReplayDeadLetterResponse,
)
from app.services import jobs as job_service
from app.services.jobs import DeadLetterReplayBlockedError, DeadLetterReplayInvalidStateError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _as_aware_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _derive_job_lifecycle(job, dead_letter) -> JobLifecycleRead:
    now = datetime.now(UTC)
    is_running = job.status == "running"
    lease_expires_at = _as_aware_utc(job.lease_expires_at)
    available_at = _as_aware_utc(job.available_at)
    lease_active = bool(lease_expires_at and lease_expires_at > now)
    replay_eligible = bool(job.status == "failed" and dead_letter is not None)
    replay_block_reason = None
    if dead_letter is None and job.status == "failed":
        replay_block_reason = "missing_dead_letter"
    elif dead_letter is not None and job.status == "running":
        replay_block_reason = "job_running"
    elif dead_letter is not None and job.status != "failed":
        replay_block_reason = f"job_status_{job.status}"
    if is_running:
        claim_state = "claimed" if job.claim_token and job.claimed_by else "inconsistent_running_claim"
        lease_state = "active" if lease_active else "expired_or_missing"
        next_action = "worker_in_progress" if lease_active else "awaiting_recovery"
    elif job.status == "queued":
        claim_state = "cleared"
        lease_state = "none"
        next_action = "retry_scheduled" if available_at and available_at > now else "awaiting_worker_claim"
    elif job.status == "done":
        claim_state = "cleared"
        lease_state = "none"
        next_action = "terminal_success"
    else:
        claim_state = "cleared"
        lease_state = "none"
        next_action = "terminal_dead_letter" if dead_letter else "terminal_failed_no_dead_letter"
    return JobLifecycleRead(
        current_status=job.status,
        claim_state=claim_state,
        lease_state=lease_state,
        lease_valid_now=lease_active if is_running else None,
        next_action=next_action,
        recovery_detected=job.lease_recovery_detected,
        replay_eligible=replay_eligible,
        replay_block_reason=replay_block_reason,
        attempts=job.attempts,
        dead_letter_attempts=dead_letter.attempts if dead_letter else None,
        dead_lettered=dead_letter is not None,
    )


def _derive_job_operator_summary(job, dead_letter, *, lifecycle: JobLifecycleRead) -> JobOperatorSummaryRead:
    now = datetime.now(UTC)
    lease_expires_at = _as_aware_utc(job.lease_expires_at)
    available_at = _as_aware_utc(job.available_at)
    is_running = job.status == "running"
    lease_expired = bool(is_running and (lease_expires_at is None or lease_expires_at <= now))
    retry_scheduled = bool(job.status == "queued" and available_at and available_at > now and job.attempts > 0)
    recovered_from_expiration = bool(job.lease_recovery_detected)
    replayed = bool(
        job.status == "queued"
        and job.attempts == 0
        and dead_letter is None
        and job.started_at is None
        and job.finished_at is None
        and available_at is not None
        and available_at > _as_aware_utc(job.created_at)
    )
    if job.status == "running" and lease_expired:
        explanation = "Job is running with an expired or missing lease and is awaiting recovery."
        next_operator_action = "Check worker health and lease-recovery loop."
    elif recovered_from_expiration:
        explanation = "Job lease expiration was recovered and the job has been re-queued."
        next_operator_action = "Verify worker stability and monitor for duplicate expirations."
    elif retry_scheduled:
        explanation = "Job failed previously and is queued for retry."
        next_operator_action = "Wait for next available_at or inspect recent worker failures."
    elif dead_letter is not None:
        explanation = "Job is dead-lettered after terminal failure."
        next_operator_action = "Inspect dead-letter reason and replay when safe."
    elif replayed:
        explanation = "Job was replayed from dead letter and is queued as a fresh attempt."
        next_operator_action = "Monitor worker claim and follow resource lifecycle progress."
    elif job.status == "done":
        explanation = "Job completed successfully."
        next_operator_action = "No action required."
    elif job.status == "failed":
        explanation = "Job failed and requires dead-letter or replay handling."
        next_operator_action = "Review failure reason and decide on replay."
    else:
        explanation = "Job is queued and waiting for worker claim."
        next_operator_action = "Ensure workers are healthy and queue throughput is normal."
    return JobOperatorSummaryRead(
        correlation_id=f"job:{job.id}",
        job_id=str(job.id),
        resource_id=str(job.resource_id),
        dead_letter_id=str(dead_letter.id) if dead_letter else None,
        status=job.status,
        is_running=is_running,
        lease_expired=lease_expired,
        retry_scheduled=retry_scheduled,
        dead_lettered=dead_letter is not None,
        recovered_from_expiration=recovered_from_expiration,
        replayed=replayed,
        replay_eligible=lifecycle.replay_eligible,
        attempts=job.attempts,
        dead_letter_attempts=dead_letter.attempts if dead_letter else None,
        available_at=available_at,
        lease_expires_at=lease_expires_at,
        last_error=job.last_error,
        dead_letter_reason=dead_letter.reason if dead_letter else None,
        dead_letter_reason_code=dead_letter.reason_code if dead_letter else None,
        operator_explanation=explanation,
        next_operator_action=next_operator_action,
    )


@router.get("/dead-letter", response_model=list[DeadLetterJobRead])
def list_dead_letter_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    rows = job_service.list_dead_letter_jobs_for_user(db, user=user, limit=limit)
    emit_diagnostic("jobs_dead_letter_listed", user_id=str(user.id), count=len(rows), limit=limit)
    return rows


@router.get("/{job_id}", response_model=BackgroundJobRead)
def get_job(job_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    job = job_service.get_job_for_user(db, user=user, job_id=job_id)
    if not job:
        emit_diagnostic("job_lookup_not_found", job_id=str(job_id), user_id=str(user.id))
        raise HTTPException(status_code=404, detail="Job not found")
    emit_diagnostic(
        "job_lookup_ok",
        job_id=str(job.id),
        resource_id=str(job.resource_id),
        correlation_id=f"job:{job.id}",
        user_id=str(user.id),
        status=job.status,
        attempts=job.attempts,
        lease_recovery_detected=job.lease_recovery_detected,
    )
    return job


@router.get("/{job_id}/diagnostics", response_model=JobDiagnosticsRead)
def get_job_diagnostics(job_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    details = job_service.get_job_diagnostics_for_user(db, user=user, job_id=job_id)
    if not details:
        emit_diagnostic("job_diagnostics_not_found", job_id=str(job_id), user_id=str(user.id))
        raise HTTPException(status_code=404, detail="Job not found")
    job, dead_letter = details
    emit_diagnostic(
        "job_diagnostics_read",
        job_id=str(job.id),
        resource_id=str(job.resource_id),
        correlation_id=f"job:{job.id}",
        user_id=str(user.id),
        has_dead_letter=dead_letter is not None,
        job_status=job.status,
        lease_recovery_detected=job.lease_recovery_detected,
        dead_letter_reason_code=dead_letter.reason_code if dead_letter else None,
        dead_letter_attempts=dead_letter.attempts if dead_letter else None,
    )
    lifecycle = _derive_job_lifecycle(job, dead_letter)
    return JobDiagnosticsRead(
        job=BackgroundJobRead.model_validate(job),
        dead_letter=DeadLetterJobRead.model_validate(dead_letter) if dead_letter else None,
        lifecycle=lifecycle,
        summary=_derive_job_operator_summary(job, dead_letter, lifecycle=lifecycle),
    )


@router.post("/dead-letter/{dead_letter_id}/replay", response_model=ReplayDeadLetterResponse)
def replay_dead_letter_job(
    dead_letter_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        replayed = job_service.replay_dead_letter_job_for_user(
            db,
            redis=redis,
            user=user,
            dead_letter_id=dead_letter_id,
        )
    except DeadLetterReplayBlockedError as exc:
        emit_diagnostic(
            "job_replay_blocked_running",
            dead_letter_id=str(dead_letter_id),
            correlation_id=f"dead_letter:{dead_letter_id}",
            user_id=str(user.id),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeadLetterReplayInvalidStateError as exc:
        emit_diagnostic(
            "job_replay_blocked_invalid_state",
            dead_letter_id=str(dead_letter_id),
            correlation_id=f"dead_letter:{dead_letter_id}",
            user_id=str(user.id),
            reason=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replayed is None:
        emit_diagnostic(
            "job_replay_not_found",
            dead_letter_id=str(dead_letter_id),
            correlation_id=f"dead_letter:{dead_letter_id}",
            user_id=str(user.id),
        )
        raise HTTPException(status_code=404, detail="Dead-letter job not found")
    dead_letter, job = replayed
    emit_diagnostic(
        "job_replayed",
        dead_letter_id=str(dead_letter.id),
        job_id=str(job.id),
        resource_id=str(job.resource_id),
        correlation_id=f"job:{job.id}",
        user_id=str(user.id),
        previous_attempts=dead_letter.attempts,
        current_attempts=job.attempts,
    )
    emit_diagnostic(
        "dead_letter_replayed",
        dead_letter_id=str(dead_letter.id),
        job_id=str(job.id),
        resource_id=str(job.resource_id),
        correlation_id=f"job:{job.id}",
        user_id=str(user.id),
        previous_attempts=dead_letter.attempts,
        current_attempts=job.attempts,
    )
    return ReplayDeadLetterResponse(
        replayed=True,
        replayed_dead_letter_id=dead_letter.id,
        previous_attempts=dead_letter.attempts,
        current_attempts=job.attempts,
        job=BackgroundJobRead.model_validate(job),
    )
