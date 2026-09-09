from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.services.canvas_client import CanvasAPIError, normalize_canvas_base_url

SSO_HOSTS = {"sso.canvaslms.com", "sso.beta.canvaslms.com", "sso.test.canvaslms.com"}


def parse_qr_login_url(qr_url: str) -> dict[str, str]:
    try:
        url = urlparse((qr_url or "").strip())
    except Exception as exc:  # noqa: BLE001
        raise CanvasAPIError("QR login value is not a valid URL") from exc
    if url.scheme != "https":
        raise CanvasAPIError("QR login URL must be https")
    if url.hostname not in SSO_HOSTS:
        raise CanvasAPIError(f"Unrecognized Canvas SSO host: {url.hostname}")
    if url.path.rstrip("/") != "/canvas/login":
        raise CanvasAPIError("QR login URL path must be /canvas/login")
    qs = parse_qs(url.query)
    domain = (qs.get("domain") or [None])[0]
    code = (qs.get("code") or [None])[0]
    if not domain or not code:
        raise CanvasAPIError("QR login URL must include domain and code")
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    return {"sso_host": url.hostname or "sso.canvaslms.com", "domain": domain, "code": code}


def fetch_mobile_client(*, domain: str, sso_host: str) -> dict[str, str]:
    url = f"https://{sso_host}/api/v1/mobile_verify.json?domain={domain}"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            res = client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Canvas/7.0 (iPhone; iOS 17.0; Scale/3.00)",
                },
            )
    except httpx.HTTPError as exc:
        raise CanvasAPIError(f"mobile_verify failed: {exc}") from exc
    if res.status_code >= 400:
        raise CanvasAPIError(f"mobile_verify error ({res.status_code})", status_code=res.status_code)
    data = res.json()
    if not isinstance(data, dict) or data.get("authorized") is not True:
        raise CanvasAPIError(
            "Canvas mobile_verify did not authorize this domain. "
            "Use a school-approved OAuth developer key instead.",
            status_code=400,
        )
    base_url = data.get("base_url")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    if not base_url or not client_id or not client_secret:
        raise CanvasAPIError("mobile_verify response missing client credentials")
    return {
        "base_url": normalize_canvas_base_url(str(base_url)),
        "client_id": str(client_id),
        "client_secret": str(client_secret),
    }


def exchange_mobile_auth_code(*, base_url: str, client_id: str, client_secret: str, code: str) -> dict[str, Any]:
    url = f"{normalize_canvas_base_url(base_url)}/login/oauth2/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            res = client.post(url, json=payload, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise CanvasAPIError(f"QR OAuth token exchange failed: {exc}") from exc
    if res.status_code >= 400:
        detail = (res.text or res.reason_phrase)[:300]
        raise CanvasAPIError(f"QR OAuth token error ({res.status_code}): {detail}", status_code=res.status_code)
    data = res.json()
    if not isinstance(data, dict) or not data.get("access_token"):
        raise CanvasAPIError("QR OAuth response missing access_token")
    if not data.get("refresh_token"):
        raise CanvasAPIError("QR OAuth response missing refresh_token (code may be expired)")
    return data


def login_with_qr_url(qr_url: str) -> dict[str, Any]:
    parsed = parse_qr_login_url(qr_url)
    mobile = fetch_mobile_client(domain=parsed["domain"], sso_host=parsed["sso_host"])
    tokens = exchange_mobile_auth_code(
        base_url=mobile["base_url"],
        client_id=mobile["client_id"],
        client_secret=mobile["client_secret"],
        code=parsed["code"],
    )
    return {
        **mobile,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens.get("expires_in"),
        "user": tokens.get("user") or {},
        "obtained_at": datetime.now(UTC).isoformat(),
    }
