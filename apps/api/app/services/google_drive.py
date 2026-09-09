from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.integration_credential import IntegrationCredential
from app.models.resource import Resource
from app.models.user import User
from app.schemas.google_drive import (
    GoogleDriveFileItem,
    GoogleDriveImportResult,
    GoogleDriveStatusRead,
)
from app.schemas.resource import ResourceRead
from app.services import courses as course_service
from app.services import google_oauth
from app.services import jobs as job_service
from app.services.google_oauth import GoogleAPIError
from app.services.resource_lifecycle import record_resource_event
from app.services.secret_crypto import decrypt_secret, encrypt_secret
from app.services.storage import get_storage_service

PROVIDER = "google_drive"
GOOGLE_API_BASE = "https://www.googleapis.com"
_MAX_BYTES = 20 * 1024 * 1024

_ALLOWED_EXACT = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}

# Google Workspace docs → export as PDF for indexing
_EXPORT_AS_PDF = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.drawing",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _guess_mime(name: str | None, mime: str | None) -> str | None:
    if mime and mime.lower().strip() in _ALLOWED_EXACT:
        return mime.lower().strip()
    if mime and mime in _EXPORT_AS_PDF:
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(name or "")
    if guessed and guessed.lower() in _ALLOWED_EXACT:
        return guessed.lower()
    if mime and mime.startswith("text/"):
        return "text/plain"
    return None


def _is_listable_mime(mime: str | None) -> bool:
    if not mime:
        return False
    if mime in _EXPORT_AS_PDF:
        return True
    return mime.lower() in _ALLOWED_EXACT or mime.startswith("text/")


def status_for_user(db: Session, *, user: User) -> GoogleDriveStatusRead:
    settings = get_settings()
    cred = (
        db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.user_id == user.id,
                IntegrationCredential.provider == PROVIDER,
            )
        )
        .scalars()
        .first()
    )
    meta = dict(cred.metadata_json or {}) if cred else {}
    return GoogleDriveStatusRead(
        connected=bool(cred),
        oauth_configured=google_oauth.oauth_configured(),
        account_email=meta.get("account_email"),
        account_name=meta.get("account_name"),
        last_validated_at=cred.last_validated_at.isoformat() if cred and cred.last_validated_at else None,
        last_sync_error=cred.last_sync_error if cred else None,
        redirect_uri=settings.google_oauth_redirect_uri,
    )


def connect_oauth_tokens(
    db: Session,
    *,
    user: User,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None = None,
    account: dict | None = None,
) -> GoogleDriveStatusRead:
    cred = (
        db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.user_id == user.id,
                IntegrationCredential.provider == PROVIDER,
            )
        )
        .scalars()
        .first()
    )
    meta: dict = {}
    if cred and isinstance(cred.metadata_json, dict):
        meta = dict(cred.metadata_json)
    meta["auth_mode"] = "oauth"
    if refresh_token:
        meta["refresh_token_encrypted"] = encrypt_secret(refresh_token)
    if expires_in:
        meta["access_token_expires_at"] = (utcnow() + timedelta(seconds=int(expires_in) - 60)).isoformat()
    if account:
        meta["account_email"] = account.get("email")
        meta["account_name"] = account.get("name")
        meta["account_id"] = account.get("id")

    if cred is None:
        cred = IntegrationCredential(
            user_id=user.id,
            provider=PROVIDER,
            base_url=GOOGLE_API_BASE,
            token_encrypted=encrypt_secret(access_token),
            metadata_json=meta,
            last_validated_at=utcnow(),
            last_sync_error=None,
        )
        db.add(cred)
    else:
        cred.token_encrypted = encrypt_secret(access_token)
        cred.base_url = GOOGLE_API_BASE
        cred.metadata_json = meta
        cred.last_validated_at = utcnow()
        cred.last_sync_error = None
        db.add(cred)
    db.commit()
    return status_for_user(db, user=user)


def disconnect(db: Session, *, user: User) -> GoogleDriveStatusRead:
    cred = (
        db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.user_id == user.id,
                IntegrationCredential.provider == PROVIDER,
            )
        )
        .scalars()
        .first()
    )
    if cred:
        db.delete(cred)
        db.commit()
    return status_for_user(db, user=user)


def _get_cred(db: Session, *, user: User) -> IntegrationCredential:
    cred = (
        db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.user_id == user.id,
                IntegrationCredential.provider == PROVIDER,
            )
        )
        .scalars()
        .first()
    )
    if not cred:
        raise GoogleAPIError("Google Drive is not connected", status_code=400)
    return cred


def _access_token(db: Session, *, user: User) -> str:
    cred = _get_cred(db, user=user)
    meta = dict(cred.metadata_json or {})
    expires_at = meta.get("access_token_expires_at")
    needs_refresh = False
    if expires_at:
        try:
            needs_refresh = datetime.fromisoformat(str(expires_at)) <= utcnow()
        except ValueError:
            needs_refresh = True
    if needs_refresh and meta.get("refresh_token_encrypted"):
        refresh = decrypt_secret(str(meta["refresh_token_encrypted"]))
        tokens = google_oauth.refresh_access_token(refresh_token=refresh)
        cred.token_encrypted = encrypt_secret(tokens["access_token"])
        if tokens.get("expires_in"):
            meta["access_token_expires_at"] = (
                utcnow() + timedelta(seconds=int(tokens["expires_in"]) - 60)
            ).isoformat()
        if tokens.get("refresh_token"):
            meta["refresh_token_encrypted"] = encrypt_secret(tokens["refresh_token"])
        cred.metadata_json = meta
        cred.last_validated_at = utcnow()
        db.add(cred)
        db.commit()
    return decrypt_secret(cred.token_encrypted)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def fetch_account_profile(access_token: str) -> dict:
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers=_auth_headers(access_token),
            )
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Google profile request failed: {exc}", status_code=502) from exc
    if res.status_code >= 400:
        return {}
    return res.json()


def list_files(db: Session, *, user: User, q: str | None = None, page_size: int = 25) -> list[GoogleDriveFileItem]:
    token = _access_token(db, user=user)
    clauses = [
        "trashed = false",
        "("
        + " or ".join(
            [f"mimeType = '{m}'" for m in sorted(_ALLOWED_EXACT)]
            + [f"mimeType = '{m}'" for m in sorted(_EXPORT_AS_PDF)]
        )
        + ")",
    ]
    if q and q.strip():
        safe = q.strip().replace("\\", "\\\\").replace("'", "\\'")
        clauses.append(f"name contains '{safe}'")
    params = {
        "pageSize": min(max(page_size, 1), 50),
        "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink,iconLink)",
        "q": " and ".join(clauses),
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.get(
                f"{GOOGLE_API_BASE}/drive/v3/files",
                headers=_auth_headers(token),
                params=params,
            )
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Google Drive list failed: {exc}", status_code=502) from exc
    if res.status_code >= 400:
        raise GoogleAPIError(f"Google Drive list error ({res.status_code}): {res.text[:300]}", status_code=400)
    files = res.json().get("files") or []
    items: list[GoogleDriveFileItem] = []
    for f in files:
        mime = f.get("mimeType")
        if not _is_listable_mime(mime):
            continue
        size_raw = f.get("size")
        try:
            size = int(size_raw) if size_raw is not None else None
        except (TypeError, ValueError):
            size = None
        items.append(
            GoogleDriveFileItem(
                id=str(f.get("id")),
                name=str(f.get("name") or "Untitled"),
                mime_type=mime,
                modified_time=f.get("modifiedTime"),
                size=size,
                web_view_link=f.get("webViewLink"),
                icon_link=f.get("iconLink"),
            )
        )
    return items


def _download_file_bytes(*, token: str, file_id: str, mime_type: str | None) -> tuple[bytes, str, str]:
    """Returns (data, resolved_mime, filename_suffix_hint)."""
    headers = _auth_headers(token)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        if mime_type in _EXPORT_AS_PDF:
            res = client.get(
                f"{GOOGLE_API_BASE}/drive/v3/files/{file_id}/export",
                headers=headers,
                params={"mimeType": "application/pdf"},
            )
            if res.status_code >= 400:
                raise GoogleAPIError(f"Google export failed ({res.status_code}): {res.text[:300]}", status_code=400)
            return res.content, "application/pdf", ".pdf"
        res = client.get(
            f"{GOOGLE_API_BASE}/drive/v3/files/{file_id}",
            headers=headers,
            params={"alt": "media"},
        )
        if res.status_code >= 400:
            raise GoogleAPIError(f"Google download failed ({res.status_code}): {res.text[:300]}", status_code=400)
        return res.content, (mime_type or "application/octet-stream"), ""


def import_file(
    db: Session,
    *,
    redis: Redis,
    user: User,
    course_id: UUID,
    file_id: str,
    title: str | None = None,
) -> GoogleDriveImportResult:
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise GoogleAPIError("Course not found", status_code=404)

    token = _access_token(db, user=user)
    # Fetch metadata
    with httpx.Client(timeout=30.0) as client:
        meta_res = client.get(
            f"{GOOGLE_API_BASE}/drive/v3/files/{file_id}",
            headers=_auth_headers(token),
            params={"fields": "id,name,mimeType,modifiedTime,size,md5Checksum"},
        )
    if meta_res.status_code >= 400:
        raise GoogleAPIError(f"Google file metadata error ({meta_res.status_code})", status_code=400)
    meta = meta_res.json()
    name = title or str(meta.get("name") or f"drive-{file_id}")
    remote_mime = meta.get("mimeType")
    if not _is_listable_mime(remote_mime):
        raise GoogleAPIError(f"Unsupported Google Drive file type: {remote_mime}", status_code=415)

    size_raw = meta.get("size")
    try:
        if size_raw is not None and int(size_raw) > _MAX_BYTES:
            raise GoogleAPIError(f"File too large (max {_MAX_BYTES} bytes)", status_code=413)
    except (TypeError, ValueError):
        pass

    existing = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.source_type == "google_drive",
                Resource.source_ref == file_id,
            )
        )
        .scalars()
        .first()
    )
    fingerprint = str(meta.get("md5Checksum") or meta.get("modifiedTime") or "")
    if existing and existing.storage_path and (existing.metadata_json or {}).get("drive_fingerprint") == fingerprint:
        return GoogleDriveImportResult(
            resource=ResourceRead.model_validate(existing),
            created=False,
            message="Already imported",
        )

    data, resolved_mime, suffix = _download_file_bytes(token=token, file_id=file_id, mime_type=remote_mime)
    if len(data) > _MAX_BYTES:
        raise GoogleAPIError(f"File too large (max {_MAX_BYTES} bytes)", status_code=413)
    resolved_mime = _guess_mime(name + suffix, resolved_mime) or resolved_mime
    if resolved_mime not in _ALLOWED_EXACT and not str(resolved_mime).startswith("text/"):
        raise GoogleAPIError(f"Unsupported file type after download: {resolved_mime}", status_code=415)

    content_hash = hashlib.sha256(data).hexdigest()
    settings = get_settings()
    storage = get_storage_service(settings)
    safe_name = Path(name).name or f"drive-{file_id}"
    if suffix and not safe_name.lower().endswith(suffix):
        safe_name = f"{safe_name}{suffix}"

    if existing is None:
        resource = Resource(
            user_id=user.id,
            course_id=course.id,
            title=name,
            resource_type="file",
            original_filename=safe_name,
            mime_type=resolved_mime,
            source_type="google_drive",
            source_ref=file_id,
            parse_status="uploaded",
            ocr_status="pending",
            index_status="pending",
            lifecycle_state="uploaded",
            content_sha256=content_hash,
            metadata_json={"drive_fingerprint": fingerprint, "drive_mime": remote_mime},
        )
        db.add(resource)
        db.flush()
        record_resource_event(
            db,
            resource=resource,
            event_type="resource.uploaded",
            to_state=resource.lifecycle_state,
            details={"source": "google_drive"},
        )
        created = True
    else:
        resource = existing
        resource.title = name
        resource.course_id = course.id
        resource.mime_type = resolved_mime
        resource.original_filename = safe_name
        resource.content_sha256 = content_hash
        resource.metadata_json = {**(resource.metadata_json or {}), "drive_fingerprint": fingerprint, "drive_mime": remote_mime}
        db.add(resource)
        created = False

    stored = storage.put_bytes(relative_path=f"{resource.id}/{safe_name}", data=data)
    resource.storage_path = stored.storage_path
    db.add(resource)
    db.commit()
    db.refresh(resource)

    job = job_service.create_and_enqueue_parse(
        db,
        redis=redis,
        user=user,
        resource=resource,
        idempotency_key=f"google_drive:{resource.id}:{fingerprint or content_hash}",
    )
    _ = job
    return GoogleDriveImportResult(
        resource=ResourceRead.model_validate(resource),
        created=created,
        message="Imported from Google Drive",
    )
