from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.models.user import User


def test_bearer_auth_requires_valid_jwt(client, db_session, monkeypatch):
    user = User(email="bearer@test.dev", name="Bearer")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    monkeypatch.setenv("AUTH_MODE", "bearer")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-012345678901234567890123")
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("AUTH_JWT_ISSUER", "planner-api")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "planner-web")
    get_settings.cache_clear()

    no_token = client.get("/courses")
    assert no_token.status_code == 401

    bad_token = client.get("/courses", headers={"Authorization": "Bearer invalid"})
    assert bad_token.status_code == 401

    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": "planner-api",
        "aud": "planner-web",
    }
    token = jwt.encode(claims, "test-secret-012345678901234567890123", algorithm="HS256")
    ok = client.get("/courses", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200

    expired = dict(claims)
    expired["exp"] = int((now - timedelta(minutes=1)).timestamp())
    expired_token = jwt.encode(
        expired,
        "test-secret-012345678901234567890123",
        algorithm="HS256",
    )
    expired_res = client.get("/courses", headers={"Authorization": f"Bearer {expired_token}"})
    assert expired_res.status_code == 401

    wrong_aud = dict(claims)
    wrong_aud["aud"] = "other-client"
    wrong_aud_token = jwt.encode(
        wrong_aud,
        "test-secret-012345678901234567890123",
        algorithm="HS256",
    )
    wrong_aud_res = client.get("/courses", headers={"Authorization": f"Bearer {wrong_aud_token}"})
    assert wrong_aud_res.status_code == 401

    monkeypatch.setenv("AUTH_MODE", "dev")
    get_settings.cache_clear()
