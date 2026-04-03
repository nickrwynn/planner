from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import UTC
from datetime import datetime
from threading import Event, Thread
from time import sleep
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import create_engine, text


QUEUE_PARSE_RESOURCE = "queue:parse_resource"
logger = logging.getLogger("worker")
logging.basicConfig(level=os.getenv("WORKER_LOG_LEVEL", "INFO").upper())


def _log_event(event: str, *, level: str = "info", **fields) -> None:
    service_name = str(fields.get("service") or fields.get("service_name") or "worker")
    normalized_level = str(level or "info").lower().strip() or "info"
    if normalized_level == "warn":
        normalized_level = "warning"
    normalized_fields = {
        key: value
        for key, value in fields.items()
        if key not in {"service", "service_name"} and value is not None
    }
    if not normalized_fields.get("correlation_id"):
        if normalized_fields.get("job_id"):
            normalized_fields["correlation_id"] = f"job:{normalized_fields['job_id']}"
        elif normalized_fields.get("resource_id"):
            normalized_fields["correlation_id"] = f"resource:{normalized_fields['resource_id']}"
        elif normalized_fields.get("dead_letter_id"):
            normalized_fields["correlation_id"] = f"dead_letter:{normalized_fields['dead_letter_id']}"
    payload = {
        "event": event,
        "level": normalized_level,
        "ts": datetime.now(UTC).isoformat(),
        "event_version": 1,
        "service": service_name,
        **normalized_fields,
    }
    line = json.dumps(payload, default=str)
    if normalized_level in {"error", "critical"}:
        logger.error(line)
    elif normalized_level in {"warning"}:
        logger.warning(line)
    else:
        logger.info(line)


def _notify_webhook(*, event: str, payload: dict) -> bool:
    url = os.getenv("JOB_WEBHOOK_URL", "").strip()
    if not url:
        return False
    body = json.dumps({"event": event, **payload}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=3)  # noqa: S310
        return True
    except (urllib.error.URLError, TimeoutError):
        _log_event(
            "job_webhook_notify_failed",
            level="warning",
            webhook_event=event,
            job_id=str(payload.get("job_id", "")),
            resource_id=str(payload.get("resource_id", "")),
        )
        return False


def _max_parse_attempts() -> int:
    return max(1, int(os.getenv("WORKER_MAX_PARSE_ATTEMPTS", "3")))


def _lease_seconds() -> int:
    return max(5, int(os.getenv("WORKER_LEASE_SECONDS", "90")))


def _failure_injection_resource_ids() -> set[str]:
    raw = os.getenv("WORKER_FAILURE_INJECTION_RESOURCE_IDS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _should_inject_failure(resource_id: str, configured: set[str]) -> bool:
    return bool(configured) and resource_id in configured


def check_postgres(database_url: str) -> tuple[bool, str | None]:
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def check_redis(redis_url: str) -> tuple[bool, str | None]:
    try:
        r = Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        r.ping()
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _parse_queue_payload(raw: bytes) -> tuple[UUID | None, str | None, bool, str | None]:
    try:
        payload = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Redis wake payload is advisory only; undecodable bytes are ignored.
        return None, None, False, "<non_utf8_payload>"
    if not payload.strip():
        return None, None, False, "<empty_payload>"
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict) and obj.get("wake") is True:
            return None, None, True, None
        if (
            isinstance(obj, dict)
            and "job_id" in obj
            and "resource_id" in obj
            and obj["job_id"] is not None
            and obj["resource_id"] is not None
        ):
            return UUID(str(obj["job_id"])), str(obj["resource_id"]), False, None
    except (json.JSONDecodeError, ValueError):
        pass
    return None, None, False, payload


def _read_wake_signal(redis_client: Redis):
    try:
        return redis_client.blpop(QUEUE_PARSE_RESOURCE, timeout=1)
    except RedisError as e:
        _log_event(
            "queue_wake_unavailable",
            level="warning",
            error=str(e),
        )
        return None


def _start_lease_heartbeat(
    *,
    SessionLocal,
    job_service,
    job_id: UUID,
    claim_token: str,
    lease_seconds: int,
    worker_id: str,
) -> tuple[Event, Thread]:
    stop_event = Event()
    interval_seconds = max(1, lease_seconds // 3)

    def _heartbeat() -> None:
        while not stop_event.wait(interval_seconds):
            db = SessionLocal()
            try:
                renewed, stale_reason = job_service.renew_parse_job_lease_detailed(
                    db,
                    job_id=job_id,
                    claim_token=claim_token,
                    lease_seconds=lease_seconds,
                )
                if renewed is None:
                    _log_event(
                        "lease_heartbeat_stale_claim",
                        level="warning",
                        job_id=str(job_id),
                        worker_id=worker_id,
                        stale_reason=stale_reason,
                    )
                    return
            except Exception as e:  # noqa: BLE001
                _log_event(
                    "lease_heartbeat_error",
                    level="warning",
                    job_id=str(job_id),
                    worker_id=worker_id,
                    error=str(e),
                )
            finally:
                db.close()

    thread = Thread(target=_heartbeat, name=f"lease-heartbeat-{job_id}", daemon=True)
    thread.start()
    return stop_event, thread


def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://planner:planner@localhost:5432/planner"
    )
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    max_attempts = _max_parse_attempts()
    lease_seconds = _lease_seconds()
    fail_resource_ids = _failure_injection_resource_ids()
    worker_id = os.getenv("WORKER_ID", f"worker-{os.getpid()}")

    pg_ok, pg_err = check_postgres(database_url)
    r_ok, r_err = check_redis(redis_url)

    _log_event(
        "worker_startup",
        service="worker",
        correlation_id="service:worker",
        postgres={"ok": pg_ok, "error": pg_err},
        redis={"ok": r_ok, "error": r_err},
        max_parse_attempts=max_attempts,
        lease_seconds=lease_seconds,
        failure_injection_count=len(fail_resource_ids),
        worker_id=worker_id,
        wake_signal_mode="redis_wake_secondary_db_claim_primary",
    )

    r = Redis.from_url(redis_url)

    from app.db import base  # noqa: WPS433,F401
    from app.indexing.pipeline import index_resource  # noqa: WPS433
    from app.db.session import create_session_factory  # noqa: WPS433
    from app.models.background_job import BackgroundJob  # noqa: WPS433
    from app.models.resource import Resource  # noqa: WPS433
    from app.services import jobs as job_service  # noqa: WPS433

    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = create_session_factory(engine)

    while True:
        try:
            # Wake signal from enqueue path; processing claims work from DB.
            wake = _read_wake_signal(r)
            db = SessionLocal()
            try:
                recovered_ids = job_service.recover_expired_running_job_ids(db)
                if recovered_ids:
                    _log_event(
                        "expired_leases_recovered",
                        count=len(recovered_ids),
                        job_ids=[str(job_id) for job_id in recovered_ids],
                    )
                    for recovered_id in recovered_ids:
                        _log_event(
                            "job_lease_recovered",
                            level="warning",
                            job_id=str(recovered_id),
                            worker_id=worker_id,
                        )

                claimed = None
                if wake is not None and len(wake) == 2:
                    job_id, _resource_id, is_wake, invalid_payload = _parse_queue_payload(wake[1])
                    if job_id is not None:
                        claimed = job_service.claim_parse_job(
                            db,
                            job_id=job_id,
                            worker_id=worker_id,
                            lease_seconds=lease_seconds,
                        )
                        if claimed is None:
                            _log_event(
                                "queue_targeted_claim_miss_fallback_db_scan",
                                level="warning",
                                job_id=str(job_id),
                            )
                    elif is_wake:
                        _log_event("queue_wake_signal_received")
                    elif invalid_payload:
                        _log_event("queue_payload_ignored", level="warning", payload=invalid_payload)

                if claimed is None:
                    claimed = job_service.claim_next_parse_job(
                        db,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
                if claimed is None:
                    continue
                job, claim_token = claimed
                rid = UUID(str(job.resource_id))
                _log_event(
                    "parse_resource_claimed",
                    job_id=str(job.id),
                    resource_id=str(job.resource_id),
                    correlation_id=f"job:{job.id}",
                    attempt=job.attempts,
                )
                heartbeat_stop, heartbeat_thread = _start_lease_heartbeat(
                    SessionLocal=SessionLocal,
                    job_service=job_service,
                    job_id=job.id,
                    claim_token=claim_token,
                    lease_seconds=lease_seconds,
                    worker_id=worker_id,
                )
                try:
                    if _should_inject_failure(str(job.resource_id), fail_resource_ids):
                        raise RuntimeError("worker failure injection: configured resource failure")
                    index_resource(
                        db,
                        resource_id=str(rid),
                        trace_context={
                            "job_id": str(job.id),
                            "resource_id": str(job.resource_id),
                            "worker_id": worker_id,
                            "attempt": job.attempts,
                        },
                    )
                except Exception as e:  # noqa: BLE001
                    heartbeat_stop.set()
                    heartbeat_thread.join(timeout=2)
                    payload = {"job_id": str(job.id), "resource_id": str(job.resource_id)}
                    action, updated, stale_reason = job_service.fail_or_retry_parse_job_detailed(
                        db,
                        job_id=job.id,
                        claim_token=claim_token,
                        error=str(e),
                        max_attempts=max_attempts,
                        payload_json=payload,
                    )
                    if action == "retried":
                        _log_event(
                            "parse_resource_retry_scheduled",
                            level="warning",
                            job_id=str(job.id),
                            resource_id=str(job.resource_id),
                            correlation_id=f"job:{job.id}",
                            error=str(e),
                            reason_code=job_service.classify_error_code(str(e)),
                            next_available_at=updated.available_at if updated else None,
                            attempts=updated.attempts if updated else None,
                        )
                    else:
                        _log_event(
                            "parse_resource_failed",
                            action=action,
                            job_id=str(job.id),
                            resource_id=str(job.resource_id),
                            correlation_id=f"job:{job.id}",
                            error=str(e),
                            reason_code=job_service.classify_error_code(str(e)),
                            stale_reason=stale_reason,
                        )
                    if action == "failed" and updated:
                        _notify_webhook(
                            event="job.failed",
                            payload={
                                "job_id": str(updated.id),
                                "resource_id": str(updated.resource_id),
                                "status": "failed",
                                "error": str(e),
                            },
                        )
                    continue

                heartbeat_stop.set()
                heartbeat_thread.join(timeout=2)
                db.expire_all()
                res = db.get(Resource, rid)
                # "done" = indexed chunks; "skipped" = intentional no index (unsupported MIME, empty extract) — job succeeds.
                ok = res is not None and res.index_status in ("done", "skipped")
                err: str | None = None
                if not ok and res is not None:
                    meta = dict(res.metadata_json or {})
                    err = meta.get("index_error") or f"index_status={res.index_status}"
                    err_code = meta.get("index_error_code") or res.index_error_code
                elif not ok:
                    err = "resource missing after index"
                    err_code = "resource_missing"
                else:
                    err_code = None

                if ok:
                    done, stale_reason = job_service.ack_parse_job_success_detailed(
                        db,
                        job_id=job.id,
                        claim_token=claim_token,
                    )
                    if done:
                        _log_event(
                            "parse_resource_succeeded",
                            job_id=str(done.id),
                            resource_id=str(done.resource_id),
                            correlation_id=f"job:{done.id}",
                            status=done.status,
                            attempt=done.attempts,
                        )
                        _notify_webhook(
                            event="job.done",
                            payload={"job_id": str(done.id), "resource_id": str(done.resource_id), "status": "done"},
                        )
                    else:
                        _log_event(
                            "parse_resource_ack_stale_claim",
                            level="warning",
                            job_id=str(job.id),
                            resource_id=str(job.resource_id),
                            correlation_id=f"job:{job.id}",
                            stale_reason=stale_reason,
                        )
                else:
                    payload = {"job_id": str(job.id), "resource_id": str(job.resource_id)}
                    action, updated, stale_reason = job_service.fail_or_retry_parse_job_detailed(
                        db,
                        job_id=job.id,
                        claim_token=claim_token,
                        error=err or "index failed",
                        max_attempts=max_attempts,
                        payload_json=payload,
                    )
                    if action == "retried":
                        _log_event(
                            "parse_resource_retry_scheduled",
                            level="warning",
                            job_id=str(job.id),
                            resource_id=str(job.resource_id),
                            correlation_id=f"job:{job.id}",
                            error=err,
                            reason_code=err_code,
                            next_available_at=updated.available_at if updated else None,
                            attempts=updated.attempts if updated else None,
                        )
                    else:
                        _log_event(
                            "parse_resource_failed",
                            action=action,
                            job_id=str(job.id),
                            resource_id=str(job.resource_id),
                            correlation_id=f"job:{job.id}",
                            error=err,
                            reason_code=err_code,
                            stale_reason=stale_reason,
                        )
                    if action == "failed" and updated:
                        _notify_webhook(
                            event="job.failed",
                            payload={
                                "job_id": str(updated.id),
                                "resource_id": str(updated.resource_id),
                                "status": "failed",
                                "error": err,
                            },
                        )
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            _log_event("worker_error", level="error", error=str(e))


if __name__ == "__main__":
    main()
