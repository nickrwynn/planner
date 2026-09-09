from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings


_PBKDF2_ROUNDS = 260000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, rounds_s, salt, digest = stored.split("$", 3)
        rounds = int(rounds_s)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return hmac.compare_digest(dk.hex(), digest)


def mint_access_token(*, user_id: str, settings: Settings) -> str:
    secret = str(settings.auth_jwt_secret or "").strip()
    if not secret:
        raise RuntimeError("AUTH_JWT_SECRET is not configured")
    now = datetime.now(UTC)
    ttl_hours = max(1, int(getattr(settings, "auth_jwt_ttl_hours", None) or 720))
    claims: dict = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
    }
    if settings.auth_jwt_issuer:
        claims["iss"] = settings.auth_jwt_issuer
    if settings.auth_jwt_audience:
        claims["aud"] = settings.auth_jwt_audience
    return jwt.encode(claims, secret, algorithm=settings.auth_jwt_algorithm or "HS256")
