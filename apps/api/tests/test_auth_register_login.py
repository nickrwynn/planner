from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.models.user import User


def test_register_login_me_flow(client, db_session, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "bearer")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-012345678901234567890123")
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "HS256")
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    get_settings.cache_clear()

    reg = client.post(
        "/auth/register",
        json={"email": "beta@test.dev", "password": "password123", "name": "Beta"},
    )
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "beta@test.dev"
    token = body["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "beta@test.dev"

    courses = client.get("/courses", headers={"Authorization": f"Bearer {token}"})
    assert courses.status_code == 200
    assert courses.json() == []

    dup = client.post(
        "/auth/register",
        json={"email": "beta@test.dev", "password": "password123"},
    )
    assert dup.status_code == 409

    login = client.post(
        "/auth/login",
        json={"email": "beta@test.dev", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    bad = client.post(
        "/auth/login",
        json={"email": "beta@test.dev", "password": "wrong-password"},
    )
    assert bad.status_code == 401

    monkeypatch.setenv("AUTH_MODE", "dev")
    get_settings.cache_clear()


def test_register_claims_seed_user_without_password(client, db_session, monkeypatch):
    seed = User(email="dev@example.com", name="Dev User", password_hash=None)
    db_session.add(seed)
    db_session.commit()

    monkeypatch.setenv("AUTH_MODE", "bearer")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-012345678901234567890123")
    monkeypatch.delenv("AUTH_JWT_ISSUER", raising=False)
    monkeypatch.delenv("AUTH_JWT_AUDIENCE", raising=False)
    get_settings.cache_clear()

    reg = client.post(
        "/auth/register",
        json={"email": "dev@example.com", "password": "password123", "name": "Nick"},
    )
    assert reg.status_code == 200, reg.text
    assert reg.json()["user"]["email"] == "dev@example.com"

    monkeypatch.setenv("AUTH_MODE", "dev")
    get_settings.cache_clear()
