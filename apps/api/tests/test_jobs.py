from __future__ import annotations

import importlib
import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import fakeredis
import pytest
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.dead_letter_job import DeadLetterJob
from app.models.resource import Resource
from app.models.user import User
from app.services import jobs as job_service
from app.workers.queue import QUEUE_PARSE_RESOURCE, enqueue_parse_wake

def test_upload_creates_background_job_and_listing(client):
    res = client.post("/courses", json={"name": "Course J"})
    assert res.status_code == 200
    course_id = res.json()["id"]

    res = client.post(
        "/resources/upload",
        data={"course_id": course_id, "title": "Text doc"},
        files={"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert res.status_code == 200
    resource = res.json()
    rid = resource["id"]

    res = client.get(f"/resources/{rid}/jobs")
    assert res.status_code == 200
    jobs = res.json()
    assert len(jobs) >= 1
    assert jobs[0]["job_type"] == "parse_resource"
    assert jobs[0]["resource_id"] == rid
    assert "started_at" in jobs[0]
    assert "finished_at" in jobs[0]
    jid = jobs[0]["id"]

    res = client.get(f"/jobs/{jid}")
    assert res.status_code == 200
    assert res.json()["id"] == jid

    res = client.get(f"/resources/{rid}/chunks")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_ai_conversations_and_messages(client):
    res = client.get("/ai/conversations")
    assert res.status_code == 200
    assert res.json() == []

    res = client.post("/ai/ask", json={"message": "Hello assistant"})
    assert res.status_code == 200
    data = res.json()
    cid = data["conversation_id"]

    res = client.get("/ai/conversations")
    assert res.status_code == 200
    convs = res.json()
    assert any(c["id"] == cid for c in convs)

    res = client.get(f"/ai/conversations/{cid}/messages")
    assert res.status_code == 200
    msgs = res.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def _mk_user_resource(db_session):
    user = User(email=f"jobs-{datetime.now(UTC).timestamp()}@test.dev", name="Jobs")
    db_session.add(user)
    db_session.commit()
    resource = Resource(
        user_id=user.id,
        course_id=None,
        title="R",
        resource_type="file",
        original_filename="r.txt",
        mime_type="text/plain",
        storage_path="/tmp/r.txt",
        parse_status="uploaded",
        ocr_status="pending",
        index_status="queued",
        lifecycle_state="uploaded",
    )
    db_session.add(resource)
    db_session.commit()
    db_session.refresh(resource)
    return user, resource


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_job_claim_lease_and_ack_flow(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(db_session, user=user, resource=resource, idempotency_key="claim-ack")
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    claimed_job, claim_token = claimed
    assert claimed_job.id == job.id
    assert claimed_job.status == "running"
    assert claimed_job.attempts == 1
    assert claimed_job.lease_expires_at is not None
    done = job_service.ack_parse_job_success(db_session, job_id=job.id, claim_token=claim_token)
    assert done is not None
    assert done.status == "done"
    assert done.lease_expires_at is None


def test_ack_parse_job_success_is_atomic_by_claim_token(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="ack-atomic-token",
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _claimed_job, token = claimed

    assert (
        job_service.ack_parse_job_success(
            db_session,
            job_id=job.id,
            claim_token=f"{token}-wrong",
        )
        is None
    )
    done = job_service.ack_parse_job_success(
        db_session,
        job_id=job.id,
        claim_token=token,
    )
    assert done is not None
    assert done.status == "done"
    assert job_service.ack_parse_job_success(db_session, job_id=job.id, claim_token=token) is None


def test_job_claim_is_deterministic_single_owner(db_session, engine):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="single-owner"
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db_a = SessionLocal()
    db_b = SessionLocal()
    try:
        claimed_a = job_service.claim_parse_job(
            db_a,
            job_id=job.id,
            worker_id="worker-a",
            lease_seconds=60,
        )
        claimed_b = job_service.claim_parse_job(
            db_b,
            job_id=job.id,
            worker_id="worker-b",
            lease_seconds=60,
        )
        assert claimed_a is not None
        assert claimed_b is None
    finally:
        db_a.close()
        db_b.close()


def test_job_crash_recovery_requeues_expired_running(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="recover-expired"
    )
    now = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=now,
    )
    assert claimed is not None
    count = job_service.recover_expired_running_jobs(db_session, now=now + timedelta(seconds=2))
    assert count == 1
    db_session.refresh(job)
    assert job.status == "queued"
    assert job.claim_token is None
    assert job.available_at is not None


def test_ack_is_rejected_after_lease_recovery(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="ack-stale-after-recovery"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=t0,
    )
    assert claimed is not None
    _, token = claimed
    recovered_ids = job_service.recover_expired_running_job_ids(db_session, now=t0 + timedelta(seconds=2))
    assert job.id in recovered_ids

    done = job_service.ack_parse_job_success(
        db_session,
        job_id=job.id,
        claim_token=token,
        now=t0 + timedelta(seconds=3),
    )
    assert done is None
    db_session.refresh(job)
    assert job.status == "queued"
    assert job.claim_token is None


def test_renew_parse_job_lease_extends_expiration_and_blocks_recovery(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="renew-lease"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=5,
        now=t0,
    )
    assert claimed is not None
    _claimed_job, token = claimed
    renewed = job_service.renew_parse_job_lease(
        db_session,
        job_id=job.id,
        claim_token=token,
        lease_seconds=5,
        now=t0 + timedelta(seconds=4),
    )
    assert renewed is not None
    assert _as_aware_utc(renewed.lease_expires_at) == t0 + timedelta(seconds=9)

    recovered = job_service.recover_expired_running_jobs(db_session, now=t0 + timedelta(seconds=6))
    assert recovered == 0
    db_session.refresh(job)
    assert job.status == "running"
    done = job_service.ack_parse_job_success(
        db_session,
        job_id=job.id,
        claim_token=token,
        now=t0 + timedelta(seconds=7),
    )
    assert done is not None
    assert done.status == "done"


def test_recovered_job_can_be_reclaimed_and_old_ack_is_rejected(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="recover-reclaim"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=t0,
    )
    assert claimed is not None
    _job, stale_token = claimed
    recovered_ids = job_service.recover_expired_running_job_ids(db_session, now=t0 + timedelta(seconds=2))
    assert job.id in recovered_ids

    re_claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-b",
        lease_seconds=60,
        now=t0 + timedelta(seconds=2),
    )
    assert re_claimed is not None
    reclaimed_job, new_token = re_claimed
    assert reclaimed_job.status == "running"
    assert reclaimed_job.claimed_by == "worker-b"

    stale_ack = job_service.ack_parse_job_success(
        db_session,
        job_id=job.id,
        claim_token=stale_token,
        now=t0 + timedelta(seconds=3),
    )
    assert stale_ack is None
    done = job_service.ack_parse_job_success(
        db_session,
        job_id=job.id,
        claim_token=new_token,
        now=t0 + timedelta(seconds=3),
    )
    assert done is not None
    assert done.status == "done"


def test_job_retry_and_dlq_are_deterministic(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="retry-dlq"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=t0,
    )
    assert claimed is not None
    _, token1 = claimed
    action, retried = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token1,
        error="failure injection 1",
        max_attempts=2,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
        now=t0,
    )
    assert action == "retried"
    assert retried is not None
    assert retried.status == "queued"
    assert _as_aware_utc(retried.available_at) == t0 + timedelta(seconds=1)

    claimed2 = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=t0 + timedelta(seconds=1),
    )
    assert claimed2 is not None
    _, token2 = claimed2
    action2, failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token2,
        error="failure injection 2",
        max_attempts=2,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
        now=t0 + timedelta(seconds=2),
    )
    assert action2 == "failed"
    assert failed is not None
    assert failed.status == "failed"
    dlq = db_session.query(DeadLetterJob).filter(DeadLetterJob.background_job_id == job.id).one()
    assert dlq.attempts == 2
    assert dlq.replay_key == f"{job.id}:2"
    assert dlq.reason_code == "job_error"


def test_job_failure_injection_rejects_stale_claim(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="stale-claim"
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    action, _ = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token="wrong-token",
        error="injected stale claim",
        max_attempts=3,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "stale_claim"
    db_session.refresh(job)
    assert job.status == "running"


def test_dead_letter_route_is_reachable(client, db_session):
    user, resource = _mk_user_resource(db_session)
    dlq = DeadLetterJob(
        user_id=user.id,
        resource_id=resource.id,
        background_job_id=None,
        queue_name="queue:parse_resource",
        reason="boom",
        reason_code="job_error",
        attempts=3,
        replay_key="rk",
        payload_json={"x": 1},
    )
    db_session.add(dlq)
    db_session.commit()
    res = client.get("/jobs/dead-letter")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_dead_letter_route_filters_null_user_rows(client, db_session):
    _, resource = _mk_user_resource(db_session)
    dlq = DeadLetterJob(
        user_id=None,
        resource_id=resource.id,
        background_job_id=None,
        queue_name="queue:parse_resource",
        reason="system row",
        reason_code="job_error",
        attempts=1,
        replay_key="system-rk",
        payload_json={},
    )
    db_session.add(dlq)
    db_session.commit()
    res = client.get("/jobs/dead-letter")
    assert res.status_code == 200
    assert all(item["id"] != str(dlq.id) for item in res.json())


def test_job_diagnostics_route_returns_job_payload(client):
    res = client.post("/courses", json={"name": "Course J2"})
    assert res.status_code == 200
    course_id = res.json()["id"]
    up = client.post(
        "/resources/upload",
        data={"course_id": course_id, "title": "Diag doc"},
        files={"file": ("diag.txt", io.BytesIO(b"diag"), "text/plain")},
    )
    assert up.status_code == 200
    rid = up.json()["id"]
    jobs = client.get(f"/resources/{rid}/jobs")
    assert jobs.status_code == 200
    jid = jobs.json()[0]["id"]
    diag = client.get(f"/jobs/{jid}/diagnostics")
    assert diag.status_code == 200
    body = diag.json()
    assert body["job"]["id"] == jid
    assert "status" in body["job"]
    assert "claim_token" not in body["job"]
    assert isinstance(body["job"]["lease_recovery_detected"], bool)
    assert body["lifecycle"]["current_status"] == body["job"]["status"]
    assert body["lifecycle"]["dead_lettered"] is False
    assert body["lifecycle"]["next_action"] in {"awaiting_worker_claim", "retry_scheduled"}
    assert body["lifecycle"]["lease_valid_now"] is None
    assert body["lifecycle"]["replay_eligible"] is False
    assert body["lifecycle"]["replay_block_reason"] is None
    assert body["summary"]["correlation_id"] == f"job:{jid}"
    assert body["summary"]["status"] == body["job"]["status"]
    assert body["summary"]["operator_explanation"]
    assert body["summary"]["next_operator_action"]
    assert body["summary"]["dead_lettered"] is False


def test_dead_letter_replay_requeues_job(client, db_session, monkeypatch):
    # Use a fake redis client for replay enqueue side-effect.
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake_redis)

    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="replay-flow",
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _, claim_token = claimed
    action, failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=claim_token,
        error="deterministic final failure",
        max_attempts=1,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "failed"
    assert failed is not None
    dlq = db_session.query(DeadLetterJob).filter(DeadLetterJob.background_job_id == job.id).one()

    headers = {"x-user-id": str(user.id)}
    replay = client.post(f"/jobs/dead-letter/{dlq.id}/replay", headers=headers)
    assert replay.status_code == 200
    payload = replay.json()
    assert payload["replayed"] is True
    assert payload["replayed_dead_letter_id"] == str(dlq.id)
    assert payload["previous_attempts"] == 1
    assert payload["current_attempts"] == 0
    assert payload["job"]["id"] == str(job.id)
    assert payload["job"]["status"] == "queued"

    db_session.refresh(job)
    assert job.status == "queued"
    assert job.attempts == 0
    assert db_session.query(DeadLetterJob).filter(DeadLetterJob.id == dlq.id).first() is None


def test_job_diagnostics_includes_dead_letter_lifecycle(client, db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="diag-dead-letter-lifecycle",
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _, token = claimed
    action, _failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="terminal diagnostics failure",
        max_attempts=1,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "failed"
    headers = {"x-user-id": str(user.id)}
    diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert diag.status_code == 200
    body = diag.json()
    assert body["lifecycle"]["current_status"] == "failed"
    assert body["lifecycle"]["dead_lettered"] is True
    assert body["lifecycle"]["next_action"] == "terminal_dead_letter"
    assert body["lifecycle"]["replay_eligible"] is True
    assert body["lifecycle"]["replay_block_reason"] is None
    assert body["summary"]["dead_lettered"] is True
    assert body["summary"]["dead_letter_reason_code"] == "job_error"
    assert "dead-lettered" in body["summary"]["operator_explanation"]


def test_dead_letter_replay_resets_attempt_budget(db_session):
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="replay-reset-attempts",
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _, token = claimed
    action, _failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="terminal failure before replay",
        max_attempts=1,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "failed"
    dlq = db_session.query(DeadLetterJob).filter(DeadLetterJob.background_job_id == job.id).one()

    replayed = job_service.replay_dead_letter_job_for_user(
        db_session,
        redis=fake_redis,
        user=user,
        dead_letter_id=dlq.id,
    )
    assert replayed is not None
    _old_dlq, replayed_job = replayed
    assert replayed_job.attempts == 0
    assert replayed_job.status == "queued"

    claimed_after_replay = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed_after_replay is not None
    _, replay_token = claimed_after_replay
    # With reset attempts and max_attempts=2, first post-replay failure must retry.
    replay_action, replay_retry = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=replay_token,
        error="first post-replay failure",
        max_attempts=2,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert replay_action == "retried"
    assert replay_retry is not None
    assert replay_retry.status == "queued"


def test_claim_next_parse_job_skips_already_claimed_head(db_session, engine):
    user, resource = _mk_user_resource(db_session)
    job_1 = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="claim-next-1"
    )
    job_2 = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="claim-next-2"
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db_a = SessionLocal()
    db_b = SessionLocal()
    try:
        head = job_service.claim_parse_job(
            db_a,
            job_id=job_1.id,
            worker_id="worker-head",
            lease_seconds=60,
        )
        assert head is not None
        next_claim = job_service.claim_next_parse_job(
            db_b,
            worker_id="worker-next",
            lease_seconds=60,
        )
        assert next_claim is not None
        claimed_job, _ = next_claim
        assert claimed_job.id != job_1.id
        assert claimed_job.status == "running"
    finally:
        db_a.close()
        db_b.close()


def test_claim_parse_job_respects_available_at_window(db_session):
    user, resource = _mk_user_resource(db_session)
    t0 = datetime.now(UTC)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="claim-next-window",
    )
    job.available_at = t0 + timedelta(seconds=30)
    db_session.add(job)
    db_session.commit()

    not_ready = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=t0,
    )
    assert not_ready is None

    ready = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=t0 + timedelta(seconds=31),
    )
    assert ready is not None
    claimed, _token = ready
    assert claimed.id == job.id
    assert claimed.status == "running"


def test_recover_expired_running_job_ids_returns_exact_ids(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="recover-id-list",
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
    )
    assert claimed is not None
    ids = job_service.recover_expired_running_job_ids(db_session, now=t0 + timedelta(seconds=2))
    assert ids == [job.id]
    db_session.refresh(job)
    assert job.status == "queued"


def test_replay_dead_letter_running_job_is_blocked(client, db_session, monkeypatch):
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake_redis)

    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="replay-running"
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    dlq = DeadLetterJob(
        user_id=user.id,
        resource_id=resource.id,
        background_job_id=job.id,
        queue_name="queue:parse_resource",
        reason="failed previously",
        reason_code="job_error",
        attempts=1,
        replay_key=f"{job.id}:1",
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    db_session.add(dlq)
    db_session.commit()

    headers = {"x-user-id": str(user.id)}
    replay = client.post(f"/jobs/dead-letter/{dlq.id}/replay", headers=headers)
    assert replay.status_code == 409
    assert replay.json()["detail"] == "Job is currently running and cannot be replayed"


def test_classify_error_code_is_deterministic():
    assert job_service.classify_error_code("lease expired while running") == "lease_expired"
    assert job_service.classify_error_code("timeout waiting for parser") == "timeout"
    assert job_service.classify_error_code("OCR output unreadable") == "ocr_error"
    assert job_service.classify_error_code("PDF parser failed") == "pdf_error"
    assert job_service.classify_error_code("unexpected") == "job_error"


def test_fail_or_retry_handles_dlq_integrity_race(db_session, monkeypatch):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="dlq-race"
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _, token = claimed
    existing = DeadLetterJob(
        user_id=user.id,
        resource_id=resource.id,
        background_job_id=job.id,
        queue_name="queue:parse_resource",
        reason="old reason",
        reason_code="job_error",
        attempts=1,
        replay_key=f"{job.id}:1",
        payload_json={"stale": True},
    )
    db_session.add(existing)
    db_session.commit()

    original_commit = db_session.commit
    state = {"raised": False}

    def flaky_commit():
        if not state["raised"]:
            state["raised"] = True
            raise IntegrityError(statement=None, params=None, orig=Exception("duplicate"))
        return original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)
    action, failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="final failure with race",
        max_attempts=1,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "failed"
    assert failed is not None
    assert failed.status == "failed"
    refreshed = db_session.query(DeadLetterJob).filter(DeadLetterJob.background_job_id == job.id).one()
    assert refreshed.reason == "final failure with race"


def test_fail_or_retry_rejects_expired_lease_before_recovery(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="expired-before-recover"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=t0,
    )
    assert claimed is not None
    _, token = claimed
    action, _updated = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="late worker failure after lease timeout",
        max_attempts=3,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
        now=t0 + timedelta(seconds=2),
    )
    assert action == "stale_claim"
    db_session.refresh(job)
    assert job.status == "running"


def test_stale_claim_reason_is_explicit_in_detailed_fail_path(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="stale-reason-detailed-fail"
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    action, _updated, reason = job_service.fail_or_retry_parse_job_detailed(
        db_session,
        job_id=job.id,
        claim_token="wrong-token",
        error="stale mismatch",
        max_attempts=3,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "stale_claim"
    assert reason == "claim_token_mismatch"


def test_renew_parse_job_lease_rejects_expired_claim(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="renew-expired"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=t0,
    )
    assert claimed is not None
    _, token = claimed
    renewed = job_service.renew_parse_job_lease(
        db_session,
        job_id=job.id,
        claim_token=token,
        lease_seconds=30,
        now=t0 + timedelta(seconds=2),
    )
    assert renewed is None
    renewed2, reason = job_service.renew_parse_job_lease_detailed(
        db_session,
        job_id=job.id,
        claim_token=token,
        lease_seconds=30,
        now=t0 + timedelta(seconds=2),
    )
    assert renewed2 is None
    assert reason == "lease_expired"
    db_session.refresh(job)
    assert job.status == "running"
    assert _as_aware_utc(job.lease_expires_at) == t0 + timedelta(seconds=1)


def test_ack_parse_job_success_detailed_returns_token_mismatch_reason(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="ack-detailed-reason"
    )
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _claimed_job, token = claimed
    done, reason = job_service.ack_parse_job_success_detailed(
        db_session,
        job_id=job.id,
        claim_token=f"{token}-bad",
    )
    assert done is None
    assert reason == "claim_token_mismatch"


def _load_worker_main_module():
    file_path = Path(__file__).resolve()
    worker_app_path = None
    for parent in [*file_path.parents, Path.cwd(), *Path.cwd().parents]:
        candidate = parent / "apps" / "worker"
        if candidate.exists():
            worker_app_path = candidate
            break
    if worker_app_path is None:
        pytest.skip("worker module path unavailable in current test runtime")
    if str(worker_app_path) not in sys.path:
        sys.path.insert(0, str(worker_app_path))
    return importlib.import_module("worker.main")


def test_worker_parse_queue_payload_wake_and_job_shapes():
    module = _load_worker_main_module()
    wake = module._parse_queue_payload(b'{"wake": true}')
    assert wake == (None, None, True, None)

    job_id = uuid4()
    resource_id = uuid4()
    targeted = module._parse_queue_payload(
        json.dumps({"job_id": str(job_id), "resource_id": str(resource_id)}).encode("utf-8")
    )
    assert targeted == (job_id, str(resource_id), False, None)

    invalid = module._parse_queue_payload(b'{"job_id":"nope"}')
    assert invalid[0] is None
    assert invalid[2] is False
    assert invalid[3] is not None


def test_worker_read_wake_signal_handles_redis_error(monkeypatch):
    module = _load_worker_main_module()
    events: list[tuple[str, dict]] = []

    def fake_log(event: str, **fields):
        events.append((event, fields))

    class BrokenRedis:
        def blpop(self, *_args, **_kwargs):
            raise module.RedisError("redis unavailable")

    monkeypatch.setattr(module, "_log_event", fake_log)
    wake = module._read_wake_signal(BrokenRedis())
    assert wake is None
    assert events
    assert events[0][0] == "queue_wake_unavailable"


def test_worker_log_event_normalizes_warning_and_correlation(monkeypatch):
    module = _load_worker_main_module()
    lines: list[str] = []

    class FakeLogger:
        def info(self, message):
            lines.append(message)

        def warning(self, message):
            lines.append(message)

        def error(self, message):
            lines.append(message)

    monkeypatch.setattr(module, "logger", FakeLogger())
    module._log_event("worker_test", level="warn", job_id="job-99", service_name="worker-custom")
    assert lines
    payload = json.loads(lines[-1])
    assert payload["level"] == "warning"
    assert payload["service"] == "worker-custom"
    assert payload["correlation_id"] == "job:job-99"


def test_db_claim_path_is_safe_when_wake_signal_unavailable(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session,
        user=user,
        resource=resource,
        idempotency_key="db-claim-without-wake",
    )
    module = _load_worker_main_module()

    class BrokenRedis:
        def blpop(self, *_args, **_kwargs):
            raise module.RedisError("redis unavailable")

    wake = module._read_wake_signal(BrokenRedis())
    assert wake is None
    claimed = job_service.claim_next_parse_job(
        db_session,
        worker_id="worker-db-fallback",
        lease_seconds=60,
    )
    assert claimed is not None
    claimed_job, _token = claimed
    assert claimed_job.status == "running"


def test_enqueue_parse_wake_writes_explicit_wake_payload():
    fake = fakeredis.FakeStrictRedis(decode_responses=False)
    enqueue_parse_wake(fake)
    raw = fake.lpop(QUEUE_PARSE_RESOURCE)
    assert raw is not None
    payload = json.loads(raw.decode("utf-8"))
    assert payload == {"wake": True}


def test_replay_dead_letter_rejects_non_failed_job_state(client, db_session, monkeypatch):
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake_redis)

    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="replay-invalid-state"
    )
    dlq = DeadLetterJob(
        user_id=user.id,
        resource_id=resource.id,
        background_job_id=job.id,
        queue_name="queue:parse_resource",
        reason="manual injection",
        reason_code="job_error",
        attempts=1,
        replay_key=f"{job.id}:1",
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    db_session.add(dlq)
    db_session.commit()

    headers = {"x-user-id": str(user.id)}
    replay = client.post(f"/jobs/dead-letter/{dlq.id}/replay", headers=headers)
    assert replay.status_code == 409
    assert replay.json()["detail"] == "Job status 'queued' cannot be replayed; expected failed"


def test_duplicate_targeted_wake_does_not_duplicate_execution_claim(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="duplicate-wake-single-claim"
    )
    module = _load_worker_main_module()
    payload = json.dumps({"job_id": str(job.id), "resource_id": str(resource.id)}).encode("utf-8")

    parsed_1 = module._parse_queue_payload(payload)
    parsed_2 = module._parse_queue_payload(payload)
    assert parsed_1[0] == job.id
    assert parsed_2[0] == job.id

    claimed_1 = job_service.claim_parse_job(
        db_session,
        job_id=parsed_1[0],
        worker_id="worker-a",
        lease_seconds=60,
    )
    claimed_2 = job_service.claim_parse_job(
        db_session,
        job_id=parsed_2[0],
        worker_id="worker-b",
        lease_seconds=60,
    )
    assert claimed_1 is not None
    assert claimed_2 is None
    db_session.refresh(job)
    assert job.status == "running"
    assert job.attempts == 1


def test_empty_wake_payload_falls_back_to_db_claim_path(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="empty-wake-fallback"
    )
    module = _load_worker_main_module()
    parsed = module._parse_queue_payload(b"")
    assert parsed == (None, None, False, "<empty_payload>")

    claimed = job_service.claim_next_parse_job(
        db_session,
        worker_id="worker-db-fallback-empty",
        lease_seconds=60,
    )
    assert claimed is not None
    claimed_job, _token = claimed
    assert claimed_job.id == job.id
    assert claimed_job.status == "running"


def test_malformed_non_utf8_wake_payload_is_ignored_and_db_claim_still_works(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="non-utf8-wake-fallback"
    )
    module = _load_worker_main_module()
    parsed = module._parse_queue_payload(b"\xff\xfe\xfd")
    assert parsed == (None, None, False, "<non_utf8_payload>")

    claimed = job_service.claim_next_parse_job(
        db_session,
        worker_id="worker-db-fallback-non-utf8",
        lease_seconds=60,
    )
    assert claimed is not None
    claimed_job, _token = claimed
    assert claimed_job.id == job.id
    assert claimed_job.status == "running"


def test_lost_wake_enqueue_failure_does_not_block_db_source_of_truth(db_session, monkeypatch):
    user, resource = _mk_user_resource(db_session)
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)

    def fail_enqueue(_redis, _payload):
        raise RedisError("redis unavailable during enqueue")

    monkeypatch.setattr("app.services.jobs.enqueue_parse_payload", fail_enqueue)
    created = job_service.create_and_enqueue_parse(
        db_session,
        redis=fake_redis,
        user=user,
        resource=resource,
        idempotency_key="lost-wake-safe",
    )
    assert created.status == "queued"
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=created.id,
        worker_id="worker-lost-wake-targeted",
        lease_seconds=60,
    )
    assert claimed is not None
    claimed_job, _token = claimed
    assert claimed_job.id == created.id


def test_retry_schedule_is_deterministic_and_capped():
    assert [job_service.retry_delay_seconds(i) for i in range(1, 9)] == [1, 2, 4, 8, 16, 30, 30, 30]


def test_dlq_upsert_is_deterministic_single_row(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="dlq-upsert-single-row"
    )
    existing = DeadLetterJob(
        user_id=user.id,
        resource_id=resource.id,
        background_job_id=job.id,
        queue_name="queue:parse_resource",
        reason="old reason",
        reason_code="job_error",
        attempts=0,
        replay_key=f"{job.id}:0",
        payload_json={"old": True},
    )
    db_session.add(existing)
    db_session.commit()

    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _, token = claimed
    action, failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="final deterministic failure",
        max_attempts=1,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "failed"
    assert failed is not None
    rows = db_session.query(DeadLetterJob).filter(DeadLetterJob.background_job_id == job.id).all()
    assert len(rows) == 1
    assert rows[0].reason == "final deterministic failure"
    assert rows[0].attempts == 1
    assert rows[0].replay_key == f"{job.id}:1"


def test_stale_claim_rejection_matrix_is_explicit(db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="stale-claim-matrix"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=t0,
    )
    assert claimed is not None
    _claimed_job, token = claimed

    wrong_done, wrong_reason = job_service.ack_parse_job_success_detailed(
        db_session,
        job_id=job.id,
        claim_token=f"{token}-wrong",
        now=t0,
    )
    assert wrong_done is None
    assert wrong_reason == "claim_token_mismatch"

    expired_done, expired_reason = job_service.ack_parse_job_success_detailed(
        db_session,
        job_id=job.id,
        claim_token=token,
        now=t0 + timedelta(seconds=2),
    )
    assert expired_done is None
    assert expired_reason == "lease_expired"

    action, _updated, stale_reason = job_service.fail_or_retry_parse_job_detailed(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="late failure",
        max_attempts=3,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
        now=t0 + timedelta(seconds=2),
    )
    assert action == "stale_claim"
    assert stale_reason == "lease_expired"


def test_diagnostics_coherent_across_queued_running_retry_and_success(client, db_session):
    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="diag-transition-coherence"
    )
    headers = {"x-user-id": str(user.id)}

    queued_diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert queued_diag.status_code == 200
    queued_lifecycle = queued_diag.json()["lifecycle"]
    assert queued_lifecycle["current_status"] == "queued"
    assert queued_lifecycle["next_action"] == "awaiting_worker_claim"
    queued_summary = queued_diag.json()["summary"]
    assert queued_summary["is_running"] is False
    assert queued_summary["retry_scheduled"] is False

    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
    )
    assert claimed is not None
    _, token = claimed
    running_diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert running_diag.status_code == 200
    running_lifecycle = running_diag.json()["lifecycle"]
    assert running_lifecycle["current_status"] == "running"
    assert running_lifecycle["claim_state"] == "claimed"
    assert running_lifecycle["next_action"] == "worker_in_progress"
    assert running_lifecycle["lease_valid_now"] is True
    running_summary = running_diag.json()["summary"]
    assert running_summary["is_running"] is True
    assert running_summary["lease_expired"] is False

    action, retried = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token,
        error="transient retry error",
        max_attempts=2,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
    )
    assert action == "retried"
    assert retried is not None
    retry_diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert retry_diag.status_code == 200
    retry_lifecycle = retry_diag.json()["lifecycle"]
    assert retry_lifecycle["current_status"] == "queued"
    assert retry_lifecycle["next_action"] == "retry_scheduled"
    retry_summary = retry_diag.json()["summary"]
    assert retry_summary["retry_scheduled"] is True
    assert retry_summary["attempts"] == 1

    claimed_2 = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=_as_aware_utc(retried.available_at),
    )
    assert claimed_2 is not None
    _, token2 = claimed_2
    done = job_service.ack_parse_job_success(
        db_session,
        job_id=job.id,
        claim_token=token2,
    )
    assert done is not None
    success_diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert success_diag.status_code == 200
    success_lifecycle = success_diag.json()["lifecycle"]
    assert success_lifecycle["current_status"] == "done"
    assert success_lifecycle["next_action"] == "terminal_success"
    assert success_lifecycle["dead_lettered"] is False
    success_summary = success_diag.json()["summary"]
    assert success_summary["status"] == "done"
    assert "completed successfully" in success_summary["operator_explanation"]


def test_job_diagnostics_summary_marks_recovered_and_replayed(client, db_session, monkeypatch):
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake_redis)

    user, resource = _mk_user_resource(db_session)
    job = job_service.create_parse_resource_job(
        db_session, user=user, resource=resource, idempotency_key="diag-recovered-replayed"
    )
    t0 = datetime.now(UTC)
    claimed = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=1,
        now=t0,
    )
    assert claimed is not None
    recovered_ids = job_service.recover_expired_running_job_ids(db_session, now=t0 + timedelta(seconds=2))
    assert job.id in recovered_ids

    headers = {"x-user-id": str(user.id)}
    recovered_diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert recovered_diag.status_code == 200
    recovered_summary = recovered_diag.json()["summary"]
    assert recovered_summary["recovered_from_expiration"] is True
    assert "lease expiration was recovered" in recovered_summary["operator_explanation"]

    claimed2 = job_service.claim_parse_job(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=t0 + timedelta(seconds=3),
    )
    assert claimed2 is not None
    _, token2 = claimed2
    action, _failed = job_service.fail_or_retry_parse_job(
        db_session,
        job_id=job.id,
        claim_token=token2,
        error="terminal replay test failure",
        max_attempts=1,
        payload_json={"job_id": str(job.id), "resource_id": str(resource.id)},
        now=t0 + timedelta(seconds=4),
    )
    assert action == "failed"
    dlq = db_session.query(DeadLetterJob).filter(DeadLetterJob.background_job_id == job.id).one()
    replay = client.post(f"/jobs/dead-letter/{dlq.id}/replay", headers=headers)
    assert replay.status_code == 200

    replay_diag = client.get(f"/jobs/{job.id}/diagnostics", headers=headers)
    assert replay_diag.status_code == 200
    replay_summary = replay_diag.json()["summary"]
    assert replay_summary["replayed"] is True
    assert replay_summary["attempts"] == 0
    assert "replayed from dead letter" in replay_summary["operator_explanation"]
