from __future__ import annotations

import json

from redis import Redis


QUEUE_PARSE_RESOURCE = "queue:parse_resource"


def enqueue_parse_payload(redis: Redis, payload_json: str) -> None:
    """Push wake/target hints; DB remains source-of-truth for claims."""
    redis.rpush(QUEUE_PARSE_RESOURCE, payload_json)


def enqueue_parse_resource(redis: Redis, *, resource_id: str) -> None:
    """Legacy: enqueue resource_id only (tests / old callers). Prefer create_and_enqueue_parse + job row."""
    redis.rpush(QUEUE_PARSE_RESOURCE, resource_id)


def enqueue_parse_job_id(redis: Redis, *, job_id: str, resource_id: str) -> None:
    payload = json.dumps({"job_id": job_id, "resource_id": resource_id})
    enqueue_parse_payload(redis, payload)


def enqueue_parse_wake(redis: Redis) -> None:
    """Wake workers when DB state changed but no payload is needed."""
    enqueue_parse_payload(redis, json.dumps({"wake": True}))
