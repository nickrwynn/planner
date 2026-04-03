from __future__ import annotations

import hashlib
import time

from fastapi import Request
from redis import Redis
from starlette.responses import JSONResponse


class RedisRateLimiter:
    """Distributed fixed-window rate limiter backed by Redis."""

    def __init__(self, *, redis: Redis, window_seconds: int, max_requests: int):
        self.redis = redis
        self.window_seconds = max(1, int(window_seconds))
        self.max_requests = max(1, int(max_requests))
        self._namespace = "rate-limit:v1"

    def _key(self, request: Request) -> str:
        token = request.headers.get("Authorization", "").strip()
        if token:
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
            principal = f"token:{token_hash}"
        else:
            user = request.headers.get("X-User-Id", "").strip()
            if user:
                principal = f"user:{user}"
            else:
                host = request.client.host if request.client else "unknown"
                principal = f"ip:{host}"
        bucket = int(time.time() // self.window_seconds)
        return f"{self._namespace}:{principal}:{request.url.path}:{bucket}"

    def allow(self, request: Request) -> bool:
        key = self._key(request)
        try:
            count = int(self.redis.incr(key))
            if count == 1:
                # First hit in this window; set expiry once.
                self.redis.expire(key, self.window_seconds + 1)
            return count <= self.max_requests
        except Exception:
            # Fail-open to avoid cascading outages if Redis is unavailable.
            return True


def make_rate_limit_middleware(limiter: RedisRateLimiter):
    async def middleware(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if not limiter.allow(request):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        return await call_next(request)

    return middleware
