from __future__ import annotations

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.rate_limit import RedisRateLimiter, make_rate_limit_middleware


def _build_test_app(shared_redis, *, window_seconds: int = 60, max_requests: int = 2) -> FastAPI:
    app = FastAPI()
    limiter = RedisRateLimiter(
        redis=shared_redis,
        window_seconds=window_seconds,
        max_requests=max_requests,
    )
    app.middleware("http")(make_rate_limit_middleware(limiter))

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def test_rate_limit_blocks_after_max_requests():
    shared_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    app = _build_test_app(shared_redis, max_requests=2)
    client = TestClient(app)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_rate_limit_is_shared_across_instances():
    shared_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    app_a = _build_test_app(shared_redis, max_requests=2)
    app_b = _build_test_app(shared_redis, max_requests=2)
    client_a = TestClient(app_a)
    client_b = TestClient(app_b)

    assert client_a.get("/ping", headers={"X-User-Id": "shared-user"}).status_code == 200
    assert client_b.get("/ping", headers={"X-User-Id": "shared-user"}).status_code == 200
    assert client_a.get("/ping", headers={"X-User-Id": "shared-user"}).status_code == 429


def test_rate_limit_skips_health_checks():
    shared_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    app = _build_test_app(shared_redis, max_requests=1)
    client = TestClient(app)

    for _ in range(5):
        assert client.get("/health").status_code == 200
