from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import and_, desc, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.background_job import BackgroundJob
from app.models.dead_letter_job import DeadLetterJob
from app.models.resource import Resource
from app.models.user import User
from app.workers.queue import enqueue_parse_payload

JOB_TYPE_PARSE_RESOURCE = "parse_resource"
QUEUE_PARSE_RESOURCE = "queue:parse_resource"
CLAIM_CANDIDATE_BATCH = 20


class DeadLetterReplayBlockedError(RuntimeError):
    pass


class DeadLetterReplayInvalidStateError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def retry_delay_seconds(attempt: int) -> int:
    # Deterministic exponential backoff by attempt number.
    return min(2 ** max(0, attempt - 1), 30)


def classify_error_code(error: str) -> str:
    msg = (error or "").lower()
    if "lease" in msg and "expire" in msg:
        return "lease_expired"
    if "timeout" in msg:
        return "timeout"
    if "ocr" in msg:
        return "ocr_error"
    if "pdf" in msg:
        return "pdf_error"
    return "job_error"


def _stale_claim_reason(job: BackgroundJob, *, claim_token: str, now: datetime) -> str:
    if job.status != "running":
        return "not_running"
    if job.claim_token != claim_token:
        return "claim_token_mismatch"
    lease_expires_at = job.lease_expires_at
    if lease_expires_at is None:
        return "lease_missing"
    if _ensure_aware_utc(lease_expires_at) <= now:
        return "lease_expired"
    return "active"


def create_parse_resource_job(
    db: Session,
    *,
    user: User,
    resource: Resource,
    idempotency_key: str | None = None,
) -> BackgroundJob:
    job = BackgroundJob(
        user_id=user.id,
        resource_id=resource.id,
        job_type=JOB_TYPE_PARSE_RESOURCE,
        status="queued",
        attempts=0,
        last_error=None,
        idempotency_key=idempotency_key,
        available_at=utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_job(redis: Redis, job: BackgroundJob) -> bool:
    payload = json.dumps({"job_id": str(job.id), "resource_id": str(job.resource_id)})
    try:
        enqueue_parse_payload(redis, payload)
        return True
    except RedisError:
        # Queue payloads are advisory wake hints; DB state remains source-of-truth.
        return False


def claim_next_parse_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> tuple[BackgroundJob, str] | None:
    now = _ensure_aware_utc(now or utcnow())
    while True:
        rows = list(
            db.execute(
                select(BackgroundJob.id)
                .where(
                    BackgroundJob.job_type == JOB_TYPE_PARSE_RESOURCE,
                    BackgroundJob.status == "queued",
                    or_(BackgroundJob.available_at.is_(None), BackgroundJob.available_at <= now),
                )
                .order_by(BackgroundJob.created_at.asc(), BackgroundJob.id.asc())
                .limit(CLAIM_CANDIDATE_BATCH)
            )
            .scalars()
            .all()
        )
        if not rows:
            return None
        for row_id in rows:
            claimed = claim_parse_job(
                db,
                job_id=row_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                now=now,
            )
            if claimed is not None:
                return claimed


def claim_parse_job(
    db: Session,
    *,
    job_id: UUID,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> tuple[BackgroundJob, str] | None:
    now = _ensure_aware_utc(now or utcnow())
    token = uuid4().hex
    result = db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "queued",
            or_(BackgroundJob.available_at.is_(None), BackgroundJob.available_at <= now),
        )
        .values(
            status="running",
            attempts=BackgroundJob.attempts + 1,
            last_error=None,
            started_at=now,
            finished_at=None,
            claim_token=token,
            claimed_by=worker_id,
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=max(1, lease_seconds)),
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        db.rollback()
        return None
    db.commit()
    db.expire_all()
    row = db.get(BackgroundJob, job_id)
    if row is None:
        return None
    return row, token


def renew_parse_job_lease_detailed(
    db: Session,
    *,
    job_id: UUID,
    claim_token: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> tuple[BackgroundJob | None, str]:
    now = _ensure_aware_utc(now or utcnow())
    job = db.get(BackgroundJob, job_id)
    if job is None:
        return None, "missing"
    reason = _stale_claim_reason(job, claim_token=claim_token, now=now)
    if reason != "active":
        return None, reason
    result = db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "running",
            BackgroundJob.claim_token == claim_token,
            BackgroundJob.lease_expires_at.is_not(None),
            BackgroundJob.lease_expires_at > now,
        )
        .values(
            lease_expires_at=now + timedelta(seconds=max(1, lease_seconds)),
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        db.rollback()
        return None, "state_race"
    db.commit()
    db.expire_all()
    renewed = db.get(BackgroundJob, job_id)
    if renewed is None:
        return None, "missing"
    return renewed, "active"


def renew_parse_job_lease(
    db: Session,
    *,
    job_id: UUID,
    claim_token: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> BackgroundJob | None:
    renewed, _reason = renew_parse_job_lease_detailed(
        db,
        job_id=job_id,
        claim_token=claim_token,
        lease_seconds=lease_seconds,
        now=now,
    )
    return renewed


def ack_parse_job_success_detailed(
    db: Session,
    *,
    job_id: UUID,
    claim_token: str,
    now: datetime | None = None,
) -> tuple[BackgroundJob | None, str]:
    now = _ensure_aware_utc(now or utcnow())
    job = db.get(BackgroundJob, job_id)
    if job is None:
        return None, "missing"
    reason = _stale_claim_reason(job, claim_token=claim_token, now=now)
    if reason != "active":
        return None, reason
    result = db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == "running",
            BackgroundJob.claim_token == claim_token,
            BackgroundJob.lease_expires_at.is_not(None),
            BackgroundJob.lease_expires_at > now,
        )
        .values(
            status="done",
            finished_at=now,
            last_error=None,
            claim_token=None,
            claimed_by=None,
            claimed_at=None,
            lease_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        db.rollback()
        return None, "state_race"
    db.commit()
    db.expire_all()
    done = db.get(BackgroundJob, job_id)
    if done is None:
        return None, "missing"
    return done, "active"


def ack_parse_job_success(
    db: Session,
    *,
    job_id: UUID,
    claim_token: str,
    now: datetime | None = None,
) -> BackgroundJob | None:
    done, _reason = ack_parse_job_success_detailed(
        db,
        job_id=job_id,
        claim_token=claim_token,
        now=now,
    )
    return done


def fail_or_retry_parse_job_detailed(
    db: Session,
    *,
    job_id: UUID,
    claim_token: str,
    error: str,
    max_attempts: int,
    payload_json: dict | None,
    queue_name: str = QUEUE_PARSE_RESOURCE,
    now: datetime | None = None,
) -> tuple[str, BackgroundJob | None, str | None]:
    now = _ensure_aware_utc(now or utcnow())
    job = db.get(BackgroundJob, job_id)
    if not job:
        return "missing", None, "missing"
    reason = _stale_claim_reason(job, claim_token=claim_token, now=now)
    if reason != "active":
        return "stale_claim", job, reason

    attempts = int(job.attempts or 0)
    if attempts < max_attempts:
        delay = retry_delay_seconds(attempts)
        job.status = "queued"
        job.finished_at = None
        job.available_at = now + timedelta(seconds=delay)
        job.last_error = f"{error} (retry_at={job.available_at.isoformat()}; attempt={attempts}/{max_attempts})"
        job.claim_token = None
        job.claimed_by = None
        job.claimed_at = None
        job.lease_expires_at = None
        db.add(job)
        db.commit()
        db.refresh(job)
        return "retried", job, None

    job.status = "failed"
    job.finished_at = now
    job.last_error = error
    job.claim_token = None
    job.claimed_by = None
    job.claimed_at = None
    job.lease_expires_at = None
    db.add(job)

    dlq = (
        db.execute(
            select(DeadLetterJob).where(DeadLetterJob.background_job_id == job.id).limit(1)
        )
        .scalars()
        .first()
    )
    if dlq is None:
        dlq = DeadLetterJob(
            user_id=job.user_id,
            resource_id=job.resource_id,
            background_job_id=job.id,
            queue_name=queue_name,
            reason=error,
            reason_code=classify_error_code(error),
            attempts=attempts,
            replay_key=f"{job.id}:{attempts}",
            payload_json=payload_json,
        )
    else:
        dlq.reason = error
        dlq.reason_code = classify_error_code(error)
        dlq.attempts = attempts
        dlq.replay_key = f"{job.id}:{attempts}"
        dlq.payload_json = payload_json
    db.add(dlq)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        persisted_job = db.get(BackgroundJob, job.id)
        if persisted_job is None:
            raise
        persisted_job.status = "failed"
        persisted_job.finished_at = now
        persisted_job.last_error = error
        persisted_job.claim_token = None
        persisted_job.claimed_by = None
        persisted_job.claimed_at = None
        persisted_job.lease_expires_at = None
        db.add(persisted_job)
        existing = (
            db.execute(
                select(DeadLetterJob).where(DeadLetterJob.background_job_id == job.id).limit(1)
            )
            .scalars()
            .first()
        )
        if existing is None:
            raise
        existing.reason = error
        existing.reason_code = classify_error_code(error)
        existing.attempts = attempts
        existing.replay_key = f"{job.id}:{attempts}"
        existing.payload_json = payload_json
        db.add(existing)
        db.commit()
    refreshed = db.get(BackgroundJob, job.id)
    if refreshed is None:
        return "failed", None, None
    return "failed", refreshed, None


def fail_or_retry_parse_job(
    db: Session,
    *,
    job_id: UUID,
    claim_token: str,
    error: str,
    max_attempts: int,
    payload_json: dict | None,
    queue_name: str = QUEUE_PARSE_RESOURCE,
    now: datetime | None = None,
) -> tuple[str, BackgroundJob | None]:
    action, updated, _reason = fail_or_retry_parse_job_detailed(
        db,
        job_id=job_id,
        claim_token=claim_token,
        error=error,
        max_attempts=max_attempts,
        payload_json=payload_json,
        queue_name=queue_name,
        now=now,
    )
    return action, updated


def recover_expired_running_job_ids(db: Session, *, now: datetime | None = None) -> list[UUID]:
    now = _ensure_aware_utc(now or utcnow())
    rows = list(
        db.execute(
            select(BackgroundJob.id, BackgroundJob.attempts).where(
                and_(
                    BackgroundJob.status == "running",
                    BackgroundJob.lease_expires_at.is_not(None),
                    BackgroundJob.lease_expires_at <= now,
                )
            )
        )
        .all()
    )
    if not rows:
        return []
    recovered_ids: list[UUID] = []
    for job_id, attempts_raw in rows:
        attempts = int(attempts_raw or 0)
        result = db.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == job_id,
                BackgroundJob.status == "running",
                BackgroundJob.lease_expires_at.is_not(None),
                BackgroundJob.lease_expires_at <= now,
            )
            .values(
                status="queued",
                available_at=now,
                finished_at=None,
                claim_token=None,
                claimed_by=None,
                claimed_at=None,
                lease_expires_at=None,
                last_error=(
            f"lease expired while running (attempt={attempts}); re-queued for crash recovery"
                ),
            )
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) == 1:
            recovered_ids.append(job_id)
    if recovered_ids:
        db.commit()
    else:
        db.rollback()
    return recovered_ids


def recover_expired_running_jobs(db: Session, *, now: datetime | None = None) -> int:
    return len(recover_expired_running_job_ids(db, now=now))


def create_and_enqueue_parse(
    db: Session,
    *,
    redis: Redis,
    user: User,
    resource: Resource,
    idempotency_key: str | None = None,
) -> BackgroundJob:
    if idempotency_key:
        existing = (
            db.execute(
                select(BackgroundJob)
                .where(
                    BackgroundJob.user_id == user.id,
                    BackgroundJob.resource_id == resource.id,
                    BackgroundJob.job_type == JOB_TYPE_PARSE_RESOURCE,
                    BackgroundJob.idempotency_key == idempotency_key,
                )
                .order_by(desc(BackgroundJob.created_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing and existing.status in {"queued", "running", "done"}:
            return existing

    try:
        job = create_parse_resource_job(db, user=user, resource=resource, idempotency_key=idempotency_key)
    except IntegrityError:
        db.rollback()
        existing = (
            db.execute(
                select(BackgroundJob)
                .where(
                    BackgroundJob.user_id == user.id,
                    BackgroundJob.resource_id == resource.id,
                    BackgroundJob.job_type == JOB_TYPE_PARSE_RESOURCE,
                    BackgroundJob.idempotency_key == idempotency_key,
                )
                .order_by(desc(BackgroundJob.created_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if existing is None:
            raise
        job = existing
    enqueue_job(redis, job)
    return job


def list_jobs_for_resource(
    db: Session, *, user: User, resource_id: UUID, limit: int = 20
) -> list[BackgroundJob]:
    res = db.get(Resource, resource_id)
    if not res or res.user_id != user.id:
        return []
    q = (
        select(BackgroundJob)
        .where(
            BackgroundJob.resource_id == resource_id,
            BackgroundJob.user_id == user.id,
        )
        .order_by(BackgroundJob.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(q).scalars().all())


def get_job_for_user(db: Session, *, user: User, job_id: UUID) -> BackgroundJob | None:
    job = db.get(BackgroundJob, job_id)
    if not job:
        return None
    if job.user_id != user.id:
        return None
    res = db.get(Resource, job.resource_id)
    if not res or res.user_id != user.id:
        return None
    return job


def list_dead_letter_jobs_for_user(db: Session, *, user: User, limit: int = 50) -> list[DeadLetterJob]:
    q = (
        select(DeadLetterJob)
        .where(DeadLetterJob.user_id == user.id)
        .order_by(DeadLetterJob.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(q).scalars().all())


def get_job_diagnostics_for_user(
    db: Session,
    *,
    user: User,
    job_id: UUID,
) -> tuple[BackgroundJob, DeadLetterJob | None] | None:
    job = get_job_for_user(db, user=user, job_id=job_id)
    if not job:
        return None
    dlq = (
        db.execute(
            select(DeadLetterJob)
            .where(
                DeadLetterJob.background_job_id == job_id,
                DeadLetterJob.user_id == user.id,
            )
            .order_by(DeadLetterJob.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return job, dlq


def replay_dead_letter_job_for_user(
    db: Session,
    *,
    redis: Redis,
    user: User,
    dead_letter_id: UUID,
    now: datetime | None = None,
) -> tuple[DeadLetterJob, BackgroundJob] | None:
    now = _ensure_aware_utc(now or utcnow())
    dlq = db.get(DeadLetterJob, dead_letter_id)
    if dlq is None or dlq.user_id != user.id:
        return None
    if dlq.background_job_id is None:
        return None
    job = db.get(BackgroundJob, dlq.background_job_id)
    if job is None or job.user_id != user.id:
        return None

    if job.status == "running":
        raise DeadLetterReplayBlockedError("Job is currently running and cannot be replayed")
    if job.status != "failed":
        raise DeadLetterReplayInvalidStateError(
            f"Job status '{job.status}' cannot be replayed; expected failed"
        )

    # Replay starts a fresh processing cycle with deterministic retry budget.
    job.status = "queued"
    job.attempts = 0
    job.started_at = None
    job.available_at = now
    job.last_error = None
    job.finished_at = None
    job.claim_token = None
    job.claimed_by = None
    job.claimed_at = None
    job.lease_expires_at = None
    db.add(job)
    db.delete(dlq)
    db.commit()
    db.refresh(job)
    enqueue_job(redis, job)
    return dlq, job
