from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse
from uuid import UUID

import httpx
import jwt

from app.core.config import get_settings
from app.services.canvas_client import CanvasAPIError, normalize_canvas_base_url


def utcnow() -> datetime:
    return datetime.now(UTC)


def oauth_configured() -> bool:
    settings = get_settings()
    return bool(str(settings.canvas_oauth_client_id or "").strip() and str(settings.canvas_oauth_client_secret or "").strip())


def _state_secret() -> str:
    settings = get_settings()
    raw = (settings.integrations_secret or settings.auth_jwt_secret or "dev-integrations-secret").strip()
    return raw


def create_oauth_state(*, user_id: UUID, base_url: str) -> str:
    payload = {
        "purpose": "canvas_oauth",
        "sub": str(user_id),
        "base_url": normalize_canvas_base_url(base_url),
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
        raise CanvasAPIError("Invalid or expired OAuth state") from exc
    if claims.get("purpose") != "canvas_oauth":
        raise CanvasAPIError("Invalid OAuth state purpose")
    if not claims.get("base_url"):
        raise CanvasAPIError("OAuth state missing base_url")
    return claims


def build_authorize_url(*, base_url: str, state: str) -> str:
    settings = get_settings()
    if not oauth_configured():
        raise CanvasAPIError(
            "Canvas OAuth is not configured. Set CANVAS_OAUTH_CLIENT_ID and CANVAS_OAUTH_CLIENT_SECRET.",
            status_code=400,
        )
    root = normalize_canvas_base_url(base_url)
    params = {
        "client_id": settings.canvas_oauth_client_id.strip(),
        "response_type": "code",
        "redirect_uri": settings.canvas_oauth_redirect_uri.strip(),
        "state": state,
        "purpose": "StudyFlows",
    }
    scopes = str(settings.canvas_oauth_scopes or "").strip()
    if scopes:
        params["scope"] = scopes
    return f"{root}/login/oauth2/auth?{urlencode(params)}"


def exchange_authorization_code(*, base_url: str, code: str) -> dict[str, Any]:
    settings = get_settings()
    if not oauth_configured():
        raise CanvasAPIError("Canvas OAuth is not configured", status_code=400)
    root = normalize_canvas_base_url(base_url)
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.canvas_oauth_client_id.strip(),
        "client_secret": settings.canvas_oauth_client_secret.strip(),
        "redirect_uri": settings.canvas_oauth_redirect_uri.strip(),
        "code": code,
    }
    return _token_request(root, payload)


def refresh_access_token(*, base_url: str, refresh_token: str, client_id: str | None = None, client_secret: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    cid = (client_id or settings.canvas_oauth_client_id or "").strip()
    csec = (client_secret or settings.canvas_oauth_client_secret or "").strip()
    if not cid or not csec:
        raise CanvasAPIError("Canvas OAuth client credentials missing for refresh", status_code=400)
    root = normalize_canvas_base_url(base_url)
    payload = {
        "grant_type": "refresh_token",
        "client_id": cid,
        "client_secret": csec,
        "refresh_token": refresh_token,
    }
    return _token_request(root, payload)


def _token_request(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /login/oauth2/token — Canvas accepts form encoding (preferred) or JSON."""
    url = f"{base_url}/login/oauth2/token"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            res = client.post(
                url,
                data=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
    except httpx.HTTPError as exc:
        raise CanvasAPIError(f"Canvas OAuth token request failed: {exc}") from exc
    if res.status_code >= 400:
        detail = (res.text or res.reason_phrase)[:300]
        raise CanvasAPIError(f"Canvas OAuth token error ({res.status_code}): {detail}", status_code=res.status_code)
    data = res.json()
    if not isinstance(data, dict) or not data.get("access_token"):
        raise CanvasAPIError("Canvas OAuth token response missing access_token")
    return data


def safe_redirect_target(url: str, *, fallback: str) -> str:
    try:
        parsed = urlparse(url)
        fb = urlparse(fallback)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            # Prefer same host as configured success URL for open-redirect safety.
            if not fb.netloc or parsed.netloc == fb.netloc:
                return url
    except Exception:  # noqa: BLE001
        pass
    return fallback
