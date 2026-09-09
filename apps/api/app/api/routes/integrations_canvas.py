from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from redis import Redis
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.core.config import get_settings
from app.models.user import User
from app.schemas.canvas import (
    CanvasConnectRequest,
    CanvasOAuthStartRead,
    CanvasOAuthStartRequest,
    CanvasQrConnectRequest,
    CanvasSessionConnectRequest,
    CanvasStatusRead,
    CanvasSyncResult,
)
from app.services.canvas_client import CanvasAPIError
from app.services import canvas_oauth
from app.services import canvas_qr_login
from app.services import canvas_sync as canvas_sync_service

router = APIRouter(prefix="/integrations/canvas", tags=["integrations"])


@router.get("/status", response_model=CanvasStatusRead)
def canvas_status(db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    return canvas_sync_service.status_for_user(db, user=user)


@router.put("", response_model=CanvasStatusRead)
def connect_canvas(
    payload: CanvasConnectRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        return canvas_sync_service.connect_canvas(db, user=user, data=payload)
    except CanvasAPIError as exc:
        status = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/session", response_model=CanvasStatusRead)
def connect_canvas_session(
    payload: CanvasSessionConnectRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    """Temp workaround: reuse a logged-in browser `canvas_session` cookie."""
    try:
        return canvas_sync_service.connect_canvas_session(
            db,
            user=user,
            base_url=payload.base_url,
            session_cookie=payload.session_cookie,
        )
    except CanvasAPIError as exc:
        status = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/oauth/start", response_model=CanvasOAuthStartRead)
def oauth_start(
    payload: CanvasOAuthStartRequest = CanvasOAuthStartRequest(),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    settings = get_settings()
    base_url = payload.base_url or settings.canvas_default_base_url
    try:
        state = canvas_oauth.create_oauth_state(user_id=user.id, base_url=base_url)
        authorize_url = canvas_oauth.build_authorize_url(base_url=base_url, state=state)
        return CanvasOAuthStartRead(authorize_url=authorize_url, state=state)
    except CanvasAPIError as exc:
        status = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db_from_request),
):
    settings = get_settings()
    fail = settings.canvas_oauth_failure_url
    ok = settings.canvas_oauth_success_url
    if error:
        return RedirectResponse(url=f"{fail}&reason={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{fail}&reason=missing_code", status_code=302)
    try:
        claims = canvas_oauth.parse_oauth_state(state)
        user_id = UUID(str(claims["sub"]))
        user = db.get(User, user_id)
        if not user:
            return RedirectResponse(url=f"{fail}&reason=unknown_user", status_code=302)
        tokens = canvas_oauth.exchange_authorization_code(base_url=str(claims["base_url"]), code=code)
        canvas_sync_service.connect_canvas_oauth_tokens(
            db,
            user=user,
            base_url=str(claims["base_url"]),
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            auth_mode="oauth",
            canvas_user=tokens.get("user"),
            oauth_client_id=settings.canvas_oauth_client_id.strip() or None,
            oauth_client_secret=settings.canvas_oauth_client_secret.strip() or None,
            expires_in=tokens.get("expires_in"),
        )
        return RedirectResponse(url=ok, status_code=302)
    except CanvasAPIError:
        return RedirectResponse(url=f"{fail}&reason=oauth_failed", status_code=302)
    except Exception:  # noqa: BLE001
        return RedirectResponse(url=f"{fail}&reason=oauth_failed", status_code=302)


@router.post("/oauth/qr", response_model=CanvasStatusRead)
def oauth_qr_connect(
    payload: CanvasQrConnectRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        result = canvas_qr_login.login_with_qr_url(payload.qr_url)
        return canvas_sync_service.connect_canvas_oauth_tokens(
            db,
            user=user,
            base_url=result["base_url"],
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            auth_mode="oauth_qr",
            canvas_user=result.get("user"),
            oauth_client_id=result.get("client_id"),
            oauth_client_secret=result.get("client_secret"),
            expires_in=result.get("expires_in"),
        )
    except CanvasAPIError as exc:
        status = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/sync", response_model=CanvasSyncResult)
def sync_canvas(
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        return canvas_sync_service.sync_canvas(db, user=user, redis=redis)
    except CanvasAPIError as exc:
        status = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
