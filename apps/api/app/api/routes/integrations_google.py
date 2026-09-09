from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from redis import Redis
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.core.config import get_settings
from app.models.user import User
from app.schemas.google_drive import (
    GoogleDriveFileItem,
    GoogleDriveImportRequest,
    GoogleDriveImportResult,
    GoogleDriveStatusRead,
    GoogleOAuthStartRead,
    GoogleOAuthStartRequest,
)
from app.services import google_drive as drive_service
from app.services import google_oauth
from app.services.google_oauth import GoogleAPIError

router = APIRouter(prefix="/integrations/google", tags=["integrations"])


def _http_status(exc: GoogleAPIError) -> int:
    return exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 400


def _append_query(url: str, **params: str) -> str:
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value is not None and value != "":
            q[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


@router.get("/status", response_model=GoogleDriveStatusRead)
def google_status(db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    return drive_service.status_for_user(db, user=user)


@router.post("/oauth/start", response_model=GoogleOAuthStartRead)
def oauth_start(
    payload: GoogleOAuthStartRequest = GoogleOAuthStartRequest(),
    user=Depends(get_current_user),
):
    try:
        state = google_oauth.create_oauth_state(user_id=user.id, return_to=payload.return_to)
        authorize_url = google_oauth.build_authorize_url(state=state)
        return GoogleOAuthStartRead(authorize_url=authorize_url, state=state)
    except GoogleAPIError as exc:
        raise HTTPException(status_code=_http_status(exc), detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db_from_request),
):
    settings = get_settings()
    fail = settings.google_oauth_failure_url
    ok = settings.google_oauth_success_url
    if error:
        return RedirectResponse(url=_append_query(fail, google="error", reason=error), status_code=302)
    if not code or not state:
        return RedirectResponse(url=_append_query(fail, google="error", reason="missing_code"), status_code=302)
    try:
        claims = google_oauth.parse_oauth_state(state)
        user_id = UUID(str(claims["sub"]))
        user = db.get(User, user_id)
        if not user:
            return RedirectResponse(url=_append_query(fail, google="error", reason="unknown_user"), status_code=302)
        tokens = google_oauth.exchange_authorization_code(code=code)
        account = drive_service.fetch_account_profile(tokens["access_token"])
        drive_service.connect_oauth_tokens(
            db,
            user=user,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_in=tokens.get("expires_in"),
            account=account,
        )
        # Always land on the public /oauth/done page (never the authenticated app UI).
        # The main app already has the user session and will close the in-app browser.
        return_to = str(claims.get("return_to") or "").strip()
        dest = _append_query(ok, google="connected")
        if return_to.startswith("/") and not return_to.startswith("//"):
            dest = _append_query(dest, return_to=return_to)
        return RedirectResponse(url=dest, status_code=302)
    except GoogleAPIError:
        return RedirectResponse(url=_append_query(fail, google="error", reason="oauth_failed"), status_code=302)
    except Exception:  # noqa: BLE001
        return RedirectResponse(url=_append_query(fail, google="error", reason="oauth_failed"), status_code=302)


@router.delete("/disconnect", response_model=GoogleDriveStatusRead)
def disconnect(db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    return drive_service.disconnect(db, user=user)


@router.get("/files", response_model=list[GoogleDriveFileItem])
def list_files(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        return drive_service.list_files(db, user=user, q=q, page_size=limit)
    except GoogleAPIError as exc:
        raise HTTPException(status_code=_http_status(exc), detail=str(exc)) from exc


@router.post("/import", response_model=GoogleDriveImportResult)
def import_file(
    payload: GoogleDriveImportRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    try:
        return drive_service.import_file(
            db,
            redis=redis,
            user=user,
            course_id=payload.course_id,
            file_id=payload.file_id,
            title=payload.title,
        )
    except (GoogleAPIError, ValueError) as exc:
        status = _http_status(exc) if isinstance(exc, GoogleAPIError) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
