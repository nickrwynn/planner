from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
import app.main as app_main
from app.main import create_app


def _set_valid_prod_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_RUNTIME_PROFILE", "prod")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "bearer")
    monkeypatch.setenv("AUTH_JWT_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")


def test_create_app_rejects_insecure_prod_profile(monkeypatch):
    monkeypatch.setenv("APP_RUNTIME_PROFILE", "prod")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("AUTH_JWT_SECRET", "change-me")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="Invalid production configuration"):
        create_app()


def test_create_app_accepts_valid_prod_profile(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    get_settings.cache_clear()

    app = create_app()
    assert app.title == "Academic OS API"


def test_create_app_rejects_non_bearer_auth_mode_in_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "dev")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="AUTH_MODE must be 'bearer'"):
        create_app()


def test_create_app_rejects_weak_jwt_secret_in_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("AUTH_JWT_SECRET", "change-me")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET must be a strong secret"):
        create_app()


def test_create_app_rejects_short_jwt_secret_in_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("AUTH_JWT_SECRET", "a" * 31)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET must be a strong secret"):
        create_app()


def test_create_app_rejects_wildcard_cors_in_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="CORS_ORIGINS must be an explicit non-empty allowlist"):
        create_app()


def test_create_app_rejects_empty_cors_allowlist_in_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", " , ")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="CORS_ORIGINS must be an explicit non-empty allowlist"):
        create_app()


def test_create_app_rejects_rate_limit_disabled_in_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="RATE_LIMIT_ENABLED must be true"):
        create_app()


def test_create_app_accepts_prod_runtime_profile_with_dev_app_env(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()

    app = create_app()
    assert app.title == "Academic OS API"


def test_create_app_accepts_prod_app_env_without_runtime_prod(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setenv("APP_RUNTIME_PROFILE", "dev")
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()

    app = create_app()
    assert app.title == "Academic OS API"


def test_health_returns_503_when_dependency_check_degraded(monkeypatch):
    get_settings.cache_clear()

    class _FailingRedis:
        def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(app_main, "check_db", lambda _engine: None)
    monkeypatch.setattr(app_main.Redis, "from_url", lambda *args, **kwargs: _FailingRedis())

    app = create_app()
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["postgres"]["ok"] is True
    assert body["redis"]["ok"] is False
