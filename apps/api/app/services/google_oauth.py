from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt

from app.core.config import get_settings


class GoogleAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def utcnow() -> datetime:
    return datetime.now(UTC)


def oauth_configured() -> bool:
    settings = get_settings()
    return bool(str(settings.google_oauth_client_id or "").strip() and str(settings.google_oauth_client_secret or "").strip())


def _state_secret() -> str:
    settings = get_settings()
    return (settings.integrations_secret or settings.auth_jwt_secret or "dev-integrations-secret").strip()


def create_oauth_state(*, user_id: UUID, return_to: str | None = None) -> str:
    payload = {
        "purpose": "google_oauth",
        "sub": str(user_id),
        "return_to": return_to or "",
        "iat": int(utcnow().timestamp()),
        "exp": int((utcnow() + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(payload, _state_secret(), algorithm="HS256")


def parse_oauth_state(state: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            state,
            _state_secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except Exception as exc:  # noqa: BLE001
        raise GoogleAPIError("Invalid or expired OAuth state") from exc
    if claims.get("purpose") != "google_oauth":
        raise GoogleAPIError("Invalid OAuth state purpose")
    return claims


def build_authorize_url(*, state: str) -> str:
    settings = get_settings()
    if not oauth_configured():
        raise GoogleAPIError(
            "Google Drive OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.",
            status_code=400,
        )
    scopes = str(settings.google_oauth_scopes or "").strip() or "https://www.googleapis.com/auth/drive.readonly"
    params = {
        "client_id": settings.google_oauth_client_id.strip(),
        "redirect_uri": settings.google_oauth_redirect_uri.strip(),
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_authorization_code(*, code: str) -> dict[str, Any]:
    settings = get_settings()
    if not oauth_configured():
        raise GoogleAPIError("Google Drive OAuth is not configured", status_code=400)
    payload = {
        "code": code,
        "client_id": settings.google_oauth_client_id.strip(),
        "client_secret": settings.google_oauth_client_secret.strip(),
        "redirect_uri": settings.google_oauth_redirect_uri.strip(),
        "grant_type": "authorization_code",
    }
    return _token_request(payload)


def refresh_access_token(*, refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    if not oauth_configured():
        raise GoogleAPIError("Google Drive OAuth is not configured", status_code=400)
    payload = {
        "client_id": settings.google_oauth_client_id.strip(),
        "client_secret": settings.google_oauth_client_secret.strip(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    return _token_request(payload)


def _token_request(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                "https://oauth2.googleapis.com/token",
                data=payload,
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Google token request failed: {exc}", status_code=502) from exc
    if res.status_code >= 400:
        detail = res.text[:300]
        raise GoogleAPIError(f"Google token error ({res.status_code}): {detail}", status_code=400)
    data = res.json()
    if not data.get("access_token"):
        raise GoogleAPIError("Google token response missing access_token", status_code=400)
    return data
