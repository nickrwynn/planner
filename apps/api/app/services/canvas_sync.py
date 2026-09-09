from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from uuid import UUID

from redis import Redis
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.course import Course
from app.models.integration_credential import IntegrationCredential
from app.models.resource import Resource
from app.models.task import Task
from app.models.user import User
from app.schemas.canvas import CanvasConnectRequest, CanvasStatusRead, CanvasSyncResult
from app.services.canvas_client import CanvasAPIError, CanvasClient, normalize_canvas_base_url
from app.services import canvas_oauth
from app.services import jobs as job_service
from app.services.resource_lifecycle import record_resource_event, transition_resource_lifecycle
from app.services.secret_crypto import decrypt_secret, encrypt_secret
from app.services.section_notebooks import ensure_section_notebook
from app.services.storage import get_storage_service

PROVIDER = "canvas"
_TAG_RE = re.compile(r"<[^>]+>")
_FILE_ID_RE = re.compile(
    r"""(?:/api/v1/(?:courses/\d+/)?files/|/files/|/media_attachments_iframe/)(\d+)""",
    re.IGNORECASE,
)
_DATA_API_FILE_RE = re.compile(
    r"""data-api-endpoint\s*=\s*["'][^"']*/files/(\d+)""",
    re.IGNORECASE,
)
_THIN_PAGE_MAX_CHARS = 220


def utcnow() -> datetime:
    return datetime.now(UTC)


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = _TAG_RE.sub(" ", unescape(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def extract_canvas_file_ids_from_html(html: str | None) -> list[str]:
    """Pull Canvas file IDs from page HTML (file links, previews, iframes, data-api-endpoint)."""
    if not html:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (_FILE_ID_RE, _DATA_API_FILE_RE):
        for match in pattern.finditer(html):
            fid = match.group(1)
            if fid not in seen:
                seen.add(fid)
                found.append(fid)
    return found


def _is_thin_page_text(text: str | None) -> bool:
    """True when page body is basically a filename / empty after stripping embeds."""
    if not text:
        return True
    cleaned = text.strip()
    if len(cleaned) <= _THIN_PAGE_MAX_CHARS:
        # Single token like CSCE_314_Fall_2026_Week_2_Narrative or a short link label
        if " " not in cleaned and len(cleaned) < 120:
            return True
        words = cleaned.split()
        if len(words) <= 8:
            return True
    return False


def _parse_canvas_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_credential(db: Session, *, user: User) -> IntegrationCredential | None:
    return (
        db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.user_id == user.id,
                IntegrationCredential.provider == PROVIDER,
            )
        )
        .scalars()
        .first()
    )


def status_for_user(db: Session, *, user: User) -> CanvasStatusRead:
    cred = get_credential(db, user=user)
    settings = get_settings()
    oauth_ready = canvas_oauth.oauth_configured()
    if not cred:
        return CanvasStatusRead(
            connected=False,
            oauth_configured=oauth_ready,
            default_base_url=settings.canvas_default_base_url or None,
        )
    meta = cred.metadata_json or {}
    return CanvasStatusRead(
        connected=True,
        base_url=cred.base_url,
        last_validated_at=cred.last_validated_at,
        last_synced_at=cred.last_synced_at,
        last_sync_status=cred.last_sync_status,
        last_sync_error=cred.last_sync_error,
        canvas_user_name=meta.get("canvas_user_name"),
        auth_mode=meta.get("auth_mode"),
        oauth_configured=oauth_ready,
        default_base_url=settings.canvas_default_base_url or None,
    )


def _persist_tokens(
    db: Session,
    *,
    user: User,
    base_url: str,
    access_token: str,
    refresh_token: str | None = None,
    auth_mode: str,
    canvas_user: dict | None = None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
    expires_in: int | None = None,
) -> IntegrationCredential:
    encrypted = encrypt_secret(access_token)
    cred = get_credential(db, user=user)
    if cred is None:
        cred = IntegrationCredential(
            user_id=user.id,
            provider=PROVIDER,
            base_url=base_url,
            token_encrypted=encrypted,
        )
        db.add(cred)
    else:
        cred.base_url = base_url
        cred.token_encrypted = encrypted

    cred.last_validated_at = utcnow()
    cred.last_sync_error = None
    meta = dict(cred.metadata_json or {})
    meta["auth_mode"] = auth_mode
    if refresh_token:
        meta["refresh_token_encrypted"] = encrypt_secret(refresh_token)
    if oauth_client_id:
        meta["oauth_client_id"] = oauth_client_id
    if oauth_client_secret:
        meta["oauth_client_secret_encrypted"] = encrypt_secret(oauth_client_secret)
    if expires_in is not None:
        try:
            meta["access_token_expires_at"] = (utcnow().timestamp() + int(expires_in) - 60)
        except (TypeError, ValueError):
            pass
    if canvas_user:
        meta["canvas_user_id"] = canvas_user.get("id")
        meta["canvas_user_name"] = canvas_user.get("name") or canvas_user.get("short_name") or meta.get(
            "canvas_user_name"
        )
    cred.metadata_json = meta
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def connect_canvas(db: Session, *, user: User, data: CanvasConnectRequest) -> CanvasStatusRead:
    base_url = normalize_canvas_base_url(data.base_url)
    client = CanvasClient(base_url=base_url, access_token=data.access_token)
    self_user = client.get_self()
    _persist_tokens(
        db,
        user=user,
        base_url=base_url,
        access_token=data.access_token,
        auth_mode="pat",
        canvas_user=self_user,
    )
    return status_for_user(db, user=user)


def connect_canvas_session(
    db: Session,
    *,
    user: User,
    base_url: str | None,
    session_cookie: str,
) -> CanvasStatusRead:
    from app.services.canvas_client import normalize_session_cookie

    settings = get_settings()
    root = normalize_canvas_base_url(base_url or settings.canvas_default_base_url)
    cookie = normalize_session_cookie(session_cookie)
    client = CanvasClient(base_url=root, session_cookie=cookie)
    self_user = client.get_self()
    _persist_tokens(
        db,
        user=user,
        base_url=root,
        access_token=cookie,  # stored encrypted; used as session cookie when auth_mode=session
        auth_mode="session",
        canvas_user=self_user,
    )
    return status_for_user(db, user=user)


def connect_canvas_oauth_tokens(
    db: Session,
    *,
    user: User,
    base_url: str,
    access_token: str,
    refresh_token: str | None,
    auth_mode: str = "oauth",
    canvas_user: dict | None = None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
    expires_in: int | None = None,
) -> CanvasStatusRead:
    root = normalize_canvas_base_url(base_url)
    if not canvas_user:
        client = CanvasClient(base_url=root, access_token=access_token)
        canvas_user = client.get_self()
    _persist_tokens(
        db,
        user=user,
        base_url=root,
        access_token=access_token,
        refresh_token=refresh_token,
        auth_mode=auth_mode,
        canvas_user=canvas_user,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
        expires_in=expires_in,
    )
    return status_for_user(db, user=user)


def _client_from_credential(db: Session, *, cred: IntegrationCredential) -> CanvasClient:
    secret = decrypt_secret(cred.token_encrypted)
    meta = dict(cred.metadata_json or {})
    auth_mode = meta.get("auth_mode") or "pat"

    if auth_mode == "session":
        return CanvasClient(base_url=cred.base_url, session_cookie=secret)

    token = secret
    expires_at = meta.get("access_token_expires_at")
    needs_refresh = False
    if auth_mode in {"oauth", "oauth_qr"} and meta.get("refresh_token_encrypted"):
        # Access tokens expire in ~1 hour; refresh a bit early or when expiry unknown.
        if expires_at is None:
            needs_refresh = True
        else:
            try:
                needs_refresh = float(expires_at) <= (utcnow().timestamp() + 120)
            except (TypeError, ValueError):
                needs_refresh = True

    if needs_refresh:
        refresh_token = decrypt_secret(meta["refresh_token_encrypted"])
        client_id = meta.get("oauth_client_id")
        client_secret = None
        if meta.get("oauth_client_secret_encrypted"):
            client_secret = decrypt_secret(meta["oauth_client_secret_encrypted"])
        tokens = canvas_oauth.refresh_access_token(
            base_url=cred.base_url,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        token = tokens["access_token"]
        cred.token_encrypted = encrypt_secret(token)
        # Same refresh_token is reused (Canvas does not rotate it on refresh).
        if tokens.get("expires_in") is not None:
            meta["access_token_expires_at"] = utcnow().timestamp() + int(tokens["expires_in"]) - 60
        if tokens.get("user"):
            meta["canvas_user_id"] = tokens["user"].get("id")
            meta["canvas_user_name"] = tokens["user"].get("name") or meta.get("canvas_user_name")
        cred.metadata_json = meta
        cred.last_validated_at = utcnow()
        db.add(cred)
        db.commit()
        db.refresh(cred)

    return CanvasClient(base_url=cred.base_url, access_token=token)


def _upsert_course(db: Session, *, user: User, canvas_course: dict) -> Course:
    source_ref = str(canvas_course.get("id"))
    existing = (
        db.execute(
            select(Course).where(
                Course.user_id == user.id,
                Course.source_type == PROVIDER,
                Course.source_ref == source_ref,
            )
        )
        .scalars()
        .first()
    )
    name = (canvas_course.get("name") or canvas_course.get("course_code") or f"Canvas course {source_ref}").strip()
    code = canvas_course.get("course_code")
    term = None
    term_obj = canvas_course.get("term")
    if isinstance(term_obj, dict):
        term = term_obj.get("name")

    if existing:
        existing.name = name
        existing.code = code
        existing.term = term
        db.add(existing)
        return existing

    # Adopt a manual course with the same code/name so re-sync does not create a twin.
    adopt = None
    manual_filter = or_(Course.source_type == "manual", Course.source_type.is_(None))
    if code:
        adopt = (
            db.execute(
                select(Course).where(
                    Course.user_id == user.id,
                    manual_filter,
                    Course.code == code,
                )
            )
            .scalars()
            .first()
        )
    if adopt is None:
        adopt = (
            db.execute(
                select(Course).where(
                    Course.user_id == user.id,
                    manual_filter,
                    Course.name == name,
                )
            )
            .scalars()
            .first()
        )
    if adopt is not None:
        adopt.source_type = PROVIDER
        adopt.source_ref = source_ref
        adopt.name = name
        adopt.code = code
        adopt.term = term
        db.add(adopt)
        return adopt

    course = Course(
        user_id=user.id,
        name=name,
        code=code,
        term=term,
        source_type=PROVIDER,
        source_ref=source_ref,
    )
    db.add(course)
    return course


def _collapse_duplicate_canvas_courses(db: Session, *, user: User) -> int:
    """Keep one course per Canvas id; re-point children and delete extras."""
    from app.models.notebook import Notebook
    from app.models.resource import Resource
    from app.models.study_flow import StudyFlow

    rows = (
        db.execute(
            select(Course).where(
                Course.user_id == user.id,
                Course.source_type == PROVIDER,
                Course.source_ref.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    by_ref: dict[str, list[Course]] = {}
    for course in rows:
        by_ref.setdefault(str(course.source_ref), []).append(course)

    removed = 0
    for group in by_ref.values():
        if len(group) < 2:
            continue
        keep = sorted(group, key=lambda c: (c.created_at is None, c.created_at or utcnow(), str(c.id)))[0]
        for dup in group:
            if dup.id == keep.id:
                continue
            for model in (Resource, Task, Notebook, StudyFlow):
                kids = (
                    db.execute(select(model).where(model.user_id == user.id, model.course_id == dup.id))
                    .scalars()
                    .all()
                )
                for kid in kids:
                    kid.course_id = keep.id
                    db.add(kid)
            db.delete(dup)
            removed += 1
    if removed:
        db.flush()
    return removed


def _apply_canvas_module_meta(
    resource: Resource,
    *,
    module_name: str | None,
    module_position: int | None,
    module_id: str | int | None = None,
    module_item: dict | None = None,
) -> None:
    if not module_name:
        return
    meta = dict(resource.metadata_json or {})
    meta["canvas_module_name"] = module_name
    if module_position is not None:
        meta["canvas_module_position"] = module_position
    if module_id is not None:
        meta["canvas_module_id"] = str(module_id)
    if module_item:
        item_id = module_item.get("id")
        if item_id is not None:
            meta["canvas_module_item_id"] = str(item_id)
        item_pos = module_item.get("position")
        try:
            if item_pos is not None:
                meta["canvas_module_item_position"] = int(item_pos)
        except (TypeError, ValueError):
            pass
        item_type = str(module_item.get("type") or "").strip()
        if item_type:
            meta["canvas_module_item_type"] = item_type
        html_url = module_item.get("html_url")
        if html_url:
            meta["canvas_html_url"] = str(html_url)
        external_url = module_item.get("external_url")
        if external_url:
            meta["canvas_external_url"] = str(external_url)
        content_id = module_item.get("content_id")
        if content_id is not None:
            meta["canvas_content_id"] = str(content_id)
    resource.metadata_json = meta


def _merge_canvas_module_meta(keep: Resource, donor: Resource) -> None:
    keep_meta = dict(keep.metadata_json or {})
    donor_meta = dict(donor.metadata_json or {})
    for key in (
        "canvas_module_name",
        "canvas_module_position",
        "canvas_module_id",
        "canvas_module_item_id",
        "canvas_module_item_position",
        "canvas_module_item_type",
        "canvas_html_url",
        "canvas_external_url",
        "canvas_content_id",
        "points_possible",
        "due_at",
    ):
        if donor_meta.get(key) not in (None, "") and keep_meta.get(key) in (None, ""):
            keep_meta[key] = donor_meta[key]
    keep.metadata_json = keep_meta


def _dedupe_course_resources_by_content(db: Session, *, user: User, course_id) -> int:
    """Collapse same-bytes Canvas imports (page stub + file twin, repeated sync leftovers)."""
    from app.models.resource import Resource

    rows = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.course_id == course_id,
                Resource.content_sha256.is_not(None),
                Resource.source_type.in_(
                    ("canvas_file", "canvas_page", "canvas_syllabus", "canvas_module_item")
                ),
            )
        )
        .scalars()
        .all()
    )
    by_hash: dict[str, list[Resource]] = {}
    for row in rows:
        sha = (row.content_sha256 or "").strip()
        if len(sha) < 16:
            continue
        by_hash.setdefault(sha, []).append(row)

    def rank(r: Resource) -> tuple:
        mime = r.mime_type or ""
        is_pdf = 0 if mime == "application/pdf" else 1
        is_file = 0 if r.source_type == "canvas_file" else 1
        is_plain = 0 if mime not in {"text/plain", "text/html"} else 1
        has_module = 0 if (r.metadata_json or {}).get("canvas_module_name") else 1
        return (is_pdf, is_plain, is_file, has_module, str(r.created_at or ""), str(r.id))

    removed = 0
    for group in by_hash.values():
        if len(group) < 2:
            continue
        keep = sorted(group, key=rank)[0]
        for dup in group:
            if dup.id == keep.id:
                continue
            _merge_canvas_module_meta(keep, dup)
            db.delete(dup)
            removed += 1
        db.add(keep)
    if removed:
        db.flush()
    return removed


def _dedupe_course_resources_by_module_item(db: Session, *, user: User, course_id) -> int:
    """One resource per Canvas module item id (or module+title fallback)."""
    from app.models.resource import Resource

    rows = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.course_id == course_id,
                Resource.source_type.in_(
                    ("canvas_file", "canvas_page", "canvas_syllabus", "canvas_module_item")
                ),
            )
        )
        .scalars()
        .all()
    )
    by_key: dict[str, list[Resource]] = {}
    for row in rows:
        meta = row.metadata_json or {}
        item_id = str(meta.get("canvas_module_item_id") or "").strip()
        module_name = str(meta.get("canvas_module_name") or "").strip().lower()
        title = (row.title or "").strip().lower()
        if item_id:
            key = f"item:{item_id}"
        elif module_name and title:
            key = f"title:{module_name}:{title}"
        else:
            continue
        by_key.setdefault(key, []).append(row)

    def rank(r: Resource) -> tuple:
        mime = r.mime_type or ""
        is_pdf = 0 if mime == "application/pdf" else 1
        is_file = 0 if r.source_type == "canvas_file" else 1
        return (is_pdf, is_file, str(r.created_at or ""), str(r.id))

    removed = 0
    for group in by_key.values():
        if len(group) < 2:
            continue
        keep = sorted(group, key=rank)[0]
        for dup in group:
            if dup.id == keep.id:
                continue
            _merge_canvas_module_meta(keep, dup)
            db.delete(dup)
            removed += 1
        db.add(keep)
    if removed:
        db.flush()
    return removed


def _assignment_logistics(assignment: dict) -> dict:
    return {
        "points_possible": assignment.get("points_possible"),
        "submission_types": assignment.get("submission_types"),
        "unlock_at": assignment.get("unlock_at"),
        "lock_at": assignment.get("lock_at"),
        "html_url": assignment.get("html_url"),
        "allowed_attempts": assignment.get("allowed_attempts"),
        "omit_from_final_grade": assignment.get("omit_from_final_grade"),
        "due_at_raw": assignment.get("due_at"),
        "has_overrides": bool(assignment.get("has_overrides")),
    }


def _upsert_assignment(db: Session, *, user: User, course: Course, assignment: dict) -> Task:
    source_ref = str(assignment.get("id"))
    existing = (
        db.execute(
            select(Task).where(
                Task.user_id == user.id,
                Task.source_type == PROVIDER,
                Task.source_ref == source_ref,
            )
        )
        .scalars()
        .first()
    )
    title = (assignment.get("name") or f"Assignment {source_ref}").strip()
    description = _strip_html(assignment.get("description"))
    purpose = None
    if description and len(description) > 40:
        # Soft "why": first sentence if present.
        purpose = description.split(".")[0].strip()[:500] or None
    due_at = _parse_canvas_dt(assignment.get("due_at"))
    weight = assignment.get("points_possible")
    try:
        weight_f = float(weight) if weight is not None else None
    except (TypeError, ValueError):
        weight_f = None
    logistics = _assignment_logistics(assignment)

    if existing:
        existing.course_id = course.id
        existing.title = title
        existing.description = description
        existing.purpose = purpose
        existing.logistics_json = logistics
        existing.due_at = due_at
        existing.weight = weight_f
        existing.task_type = existing.task_type or "assignment"
        db.add(existing)
        return existing

    task = Task(
        user_id=user.id,
        course_id=course.id,
        title=title,
        description=description,
        purpose=purpose,
        logistics_json=logistics,
        task_type="assignment",
        due_at=due_at,
        weight=weight_f,
        source_type=PROVIDER,
        source_ref=source_ref,
        status="todo",
    )
    db.add(task)
    return task


_ALLOWED_CANVAS_FILE_MIME = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_MAX_CANVAS_FILES_PER_COURSE = 30


def _guess_mime(filename: str | None, content_type: str | None) -> str | None:
    mime = (content_type or "").split(";")[0].strip().lower() or None
    if mime in _ALLOWED_CANVAS_FILE_MIME:
        return mime
    if filename:
        guessed, _ = __import__("mimetypes").guess_type(filename)
        if guessed and guessed.lower() in _ALLOWED_CANVAS_FILE_MIME:
            return guessed.lower()
        if filename.lower().endswith(".pdf"):
            return "application/pdf"
    return mime if mime and mime.startswith("text/") else None


def _enqueue_resource_index(
    db: Session,
    *,
    redis: Redis,
    user: User,
    resource: Resource,
    idempotency_key: str,
    source: str,
) -> None:
    job = job_service.create_and_enqueue_parse(
        db,
        redis=redis,
        user=user,
        resource=resource,
        idempotency_key=idempotency_key,
        enqueue=False,
    )
    resource.index_status = "queued"
    meta = dict(resource.metadata_json or {})
    meta["latest_job_id"] = str(job.id)
    resource.metadata_json = meta
    transition_resource_lifecycle(
        resource,
        "queued",
        db=db,
        event_type="index.queued",
        details={"job_id": str(job.id), "source": source, "stage": "queue"},
    )
    db.flush()
    job_service.enqueue_job(redis, job)


def _upsert_canvas_file_resource(
    db: Session,
    *,
    redis: Redis,
    user: User,
    course: Course,
    client: CanvasClient,
    canvas_file: dict,
    title_override: str | None = None,
) -> Resource | None:
    file_id = canvas_file.get("id")
    if file_id is None:
        return None
    filename = canvas_file.get("display_name") or canvas_file.get("filename") or f"file-{file_id}"
    mime = _guess_mime(filename, canvas_file.get("content-type") or canvas_file.get("content_type"))
    if not mime:
        return None
    size = canvas_file.get("size") or 0
    try:
        if int(size) > 20 * 1024 * 1024:
            return None
    except (TypeError, ValueError):
        pass

    source_ref = str(file_id)
    display_title = (title_override or "").strip() or str(filename)
    existing = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.source_type == "canvas_file",
                Resource.source_ref == source_ref,
            )
        )
        .scalars()
        .first()
    )
    remote_hash = str(canvas_file.get("uuid") or canvas_file.get("md5") or canvas_file.get("updated_at") or "")
    if (
        existing
        and existing.storage_path
        and (existing.metadata_json or {}).get("canvas_fingerprint") == remote_hash
        and (not title_override or existing.title == display_title)
    ):
        return existing

    url = canvas_file.get("url")
    if not url:
        return None
    data = client.download_bytes(str(url))
    content_hash = hashlib.sha256(data).hexdigest()
    settings = get_settings()
    storage = get_storage_service(settings)
    safe_name = Path(str(filename)).name or f"canvas-{source_ref}.bin"

    if existing is None:
        resource = Resource(
            user_id=user.id,
            course_id=course.id,
            title=display_title,
            resource_type="file",
            original_filename=safe_name,
            mime_type=mime,
            source_type="canvas_file",
            source_ref=source_ref,
            parse_status="uploaded",
            ocr_status="pending",
            index_status="pending",
            lifecycle_state="uploaded",
            content_sha256=content_hash,
            metadata_json={"canvas_fingerprint": remote_hash},
        )
        db.add(resource)
        db.flush()
        record_resource_event(
            db,
            resource=resource,
            event_type="resource.uploaded",
            to_state=resource.lifecycle_state,
            details={"source": "canvas_file"},
        )
    else:
        resource = existing
        resource.course_id = course.id
        resource.title = display_title
        resource.original_filename = safe_name
        resource.mime_type = mime
        resource.content_sha256 = content_hash
        resource.parse_status = "uploaded"
        resource.index_status = "pending"
        resource.lifecycle_state = "uploaded"
        meta = dict(resource.metadata_json or {})
        meta["canvas_fingerprint"] = remote_hash
        resource.metadata_json = meta
        db.add(resource)
        db.flush()

    stored = storage.put_bytes(relative_path=f"{resource.id}/{safe_name}", data=data)
    resource.storage_path = stored.storage_path
    db.add(resource)
    db.flush()
    _enqueue_resource_index(
        db,
        redis=redis,
        user=user,
        resource=resource,
        idempotency_key=f"canvas-file:{resource.id}:{content_hash[:12]}",
        source="canvas_file",
    )
    return resource


def _upsert_syllabus_resource(
    db: Session,
    *,
    redis: Redis,
    user: User,
    course: Course,
    canvas_course: dict,
) -> Resource | None:
    body = canvas_course.get("syllabus_body")
    text = _strip_html(body) if isinstance(body, str) else None
    if not text:
        return None

    source_ref = str(canvas_course.get("id"))
    existing = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.source_type == "canvas_syllabus",
                Resource.source_ref == source_ref,
            )
        )
        .scalars()
        .first()
    )

    settings = get_settings()
    storage = get_storage_service(settings)
    data = text.encode("utf-8")
    content_hash = hashlib.sha256(data).hexdigest()
    filename = "syllabus.txt"

    if existing and existing.content_sha256 == content_hash and existing.storage_path:
        return existing

    if existing is None:
        resource = Resource(
            user_id=user.id,
            course_id=course.id,
            title=f"{course.name} Syllabus",
            resource_type="syllabus",
            original_filename=filename,
            mime_type="text/plain",
            source_type="canvas_syllabus",
            source_ref=source_ref,
            parse_status="uploaded",
            ocr_status="pending",
            index_status="pending",
            lifecycle_state="uploaded",
            content_sha256=content_hash,
        )
        db.add(resource)
        db.flush()
        record_resource_event(
            db,
            resource=resource,
            event_type="resource.uploaded",
            to_state=resource.lifecycle_state,
            details={"source": "canvas_syllabus"},
        )
    else:
        resource = existing
        resource.course_id = course.id
        resource.title = f"{course.name} Syllabus"
        resource.content_sha256 = content_hash
        resource.parse_status = "uploaded"
        resource.index_status = "pending"
        resource.lifecycle_state = "uploaded"
        db.add(resource)

    rel_path = f"{resource.id}/{filename}"
    stored = storage.put_bytes(relative_path=rel_path, data=data)
    resource.storage_path = stored.storage_path
    db.add(resource)
    db.flush()

    job = job_service.create_and_enqueue_parse(
        db,
        redis=redis,
        user=user,
        resource=resource,
        idempotency_key=f"canvas-syllabus:{resource.id}:{content_hash[:12]}",
        enqueue=False,
    )
    resource.index_status = "queued"
    meta = dict(resource.metadata_json or {})
    meta["latest_job_id"] = str(job.id)
    resource.metadata_json = meta
    transition_resource_lifecycle(
        resource,
        "queued",
        db=db,
        event_type="index.queued",
        details={"job_id": str(job.id), "source": "canvas_syllabus", "stage": "queue"},
    )
    db.flush()
    job_service.enqueue_job(redis, job)
    return resource


def _collect_student_accessible_files(
    client: CanvasClient,
    *,
    course_id: str | int,
) -> tuple[list[dict], list[str]]:
    """Students often cannot GET /courses/:id/files (403). Prefer modules + per-file fetch."""
    soft_notes: list[str] = []
    by_id: dict[str, dict] = {}

    # Best-effort course file index (works for teachers/TAs; usually 403 for students).
    try:
        for canvas_file in client.list_course_files(course_id)[:_MAX_CANVAS_FILES_PER_COURSE]:
            fid = canvas_file.get("id")
            if fid is not None:
                by_id[str(fid)] = canvas_file
    except CanvasAPIError as exc:
        if exc.status_code != 403:
            soft_notes.append(f"files course={course_id}: {exc}")
        # 403 is expected for many student enrollments — fall through to modules.

    # Module File items are the student-visible path.
    try:
        for module in client.list_modules(course_id):
            for item in module.get("items") or []:
                if str(item.get("type") or "").lower() != "file":
                    continue
                content_id = item.get("content_id")
                if content_id is None:
                    continue
                key = str(content_id)
                if key in by_id:
                    continue
                try:
                    by_id[key] = client.get_file(content_id)
                except CanvasAPIError as exc:
                    if exc.status_code != 403:
                        soft_notes.append(f"module file course={course_id} id={content_id}: {exc}")
    except CanvasAPIError as exc:
        if exc.status_code != 403:
            soft_notes.append(f"modules course={course_id}: {exc}")

    return list(by_id.values())[:_MAX_CANVAS_FILES_PER_COURSE], soft_notes


def _delete_canvas_module_item_text_stub(
    db: Session,
    *,
    user: User,
    course_id_db,
    course_id: str | int,
    item_id,
) -> None:
    """Remove parsed-text mirrors of module items (assignments/quizzes/links)."""
    source_ref = f"{course_id}:item:{item_id}"
    stubs = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.course_id == course_id_db,
                Resource.source_type == "canvas_module_item",
                Resource.source_ref == source_ref,
            )
        )
        .scalars()
        .all()
    )
    for stub in stubs:
        db.delete(stub)
    if stubs:
        db.flush()


def _upsert_files_from_html(
    db: Session,
    *,
    redis: Redis,
    user: User,
    course: Course,
    client: CanvasClient,
    html: str | None,
    title_override: str | None,
    module_name: str | None,
    module_position: int | None,
    module_id: str | int | None,
    module_item: dict | None,
    seen_file_ids: set[str] | None,
    meta_extra: dict | None = None,
) -> list[Resource]:
    """Download Canvas file embeds/links from HTML; return successfully stored resources."""
    embedded: list[Resource] = []
    file_ids = extract_canvas_file_ids_from_html(html)
    for idx, file_id in enumerate(file_ids[:8]):
        key = str(file_id)
        if seen_file_ids is not None and key in seen_file_ids:
            existing_file = (
                db.execute(
                    select(Resource).where(
                        Resource.user_id == user.id,
                        Resource.source_type == "canvas_file",
                        Resource.source_ref == key,
                    )
                )
                .scalars()
                .first()
            )
            if existing_file:
                _apply_canvas_module_meta(
                    existing_file,
                    module_name=module_name,
                    module_position=module_position,
                    module_id=module_id,
                    module_item=module_item,
                )
                if meta_extra:
                    meta = dict(existing_file.metadata_json or {})
                    meta.update({k: v for k, v in meta_extra.items() if v is not None})
                    existing_file.metadata_json = meta
                db.add(existing_file)
                embedded.append(existing_file)
            continue
        try:
            canvas_file = client.get_file(file_id)
        except CanvasAPIError:
            continue
        override = title_override if idx == 0 else None
        try:
            res = _upsert_canvas_file_resource(
                db,
                redis=redis,
                user=user,
                course=course,
                client=client,
                canvas_file=canvas_file,
                title_override=override,
            )
        except Exception:  # noqa: BLE001
            continue
        if not res:
            continue
        if seen_file_ids is not None:
            seen_file_ids.add(key)
        _apply_canvas_module_meta(
            res,
            module_name=module_name,
            module_position=module_position,
            module_id=module_id,
            module_item=module_item,
        )
        if meta_extra:
            meta = dict(res.metadata_json or {})
            meta.update({k: v for k, v in meta_extra.items() if v is not None})
            res.metadata_json = meta
        db.add(res)
        embedded.append(res)
    return embedded


def _upsert_canvas_module_item_resource(
    db: Session,
    *,
    redis: Redis,
    user: User,
    course: Course,
    client: CanvasClient,
    course_id: str | int,
    module_item: dict,
    module_name: str | None,
    module_position: int | None,
    module_id: str | int | None,
    assignment: dict | None = None,
    seen_file_ids: set[str] | None = None,
) -> Resource | None:
    """
    For Assignment/Quiz/Discussion/External* module items: download attached/embedded files
    (PDFs etc). Do not create parsed text/plain stubs — those already live as Tasks when needed.
    """
    item_type = str(module_item.get("type") or "").strip()
    title = str(module_item.get("title") or item_type or "Canvas item").strip()
    item_id = module_item.get("id")
    if item_id is None:
        return None
    if item_type.lower() == "subheader":
        return None

    body_html = ""
    due_at = None
    points = None
    if assignment:
        body_html = assignment.get("description") if isinstance(assignment.get("description"), str) else ""
        due_at = assignment.get("due_at")
        points = assignment.get("points_possible")

    meta_extra = {
        "points_possible": points,
        "due_at": due_at,
    }
    embedded = _upsert_files_from_html(
        db,
        redis=redis,
        user=user,
        course=course,
        client=client,
        html=body_html,
        title_override=title,
        module_name=module_name,
        module_position=module_position,
        module_id=module_id,
        module_item=module_item,
        seen_file_ids=seen_file_ids,
        meta_extra=meta_extra,
    )
    # Drop any earlier text/plain mirrors of this module row.
    _delete_canvas_module_item_text_stub(
        db, user=user, course_id_db=course.id, course_id=course_id, item_id=item_id
    )
    if not embedded:
        return None
    # Prefer a PDF when the assignment embeds several files.
    pdfs = [r for r in embedded if (r.mime_type or "").lower().endswith("pdf") or "pdf" in (r.mime_type or "").lower()]
    return (pdfs or embedded)[0]


def _upsert_canvas_page_resource(
    db: Session,
    *,
    redis: Redis,
    user: User,
    course: Course,
    client: CanvasClient,
    course_id: str | int,
    module_item: dict,
    module_name: str | None = None,
    module_position: int | None = None,
    seen_file_ids: set[str] | None = None,
) -> Resource | None:
    """Import Canvas pages: pull embedded PDF/media files, keep HTML text only when substantive."""
    page_url = module_item.get("page_url")
    title = module_item.get("title") or "Canvas page"
    if not page_url:
        return None
    try:
        page = client.get_page(course_id, str(page_url))
    except CanvasAPIError:
        return None

    body = page.get("body") if isinstance(page.get("body"), str) else ""
    page_title = str(page.get("title") or title)
    source_ref = f"{course_id}:{page.get('page_id') or page_url}"
    existing = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.source_type == "canvas_page",
                Resource.source_ref == source_ref,
            )
        )
        .scalars()
        .first()
    )

    # 1) Download any files embedded/linked in the page HTML (common for PDF viewers).
    file_ids = extract_canvas_file_ids_from_html(body)
    embedded_resources = _upsert_files_from_html(
        db,
        redis=redis,
        user=user,
        course=course,
        client=client,
        html=body,
        title_override=page_title,
        module_name=module_name,
        module_position=module_position,
        module_id=None,
        module_item=module_item,
        seen_file_ids=seen_file_ids,
    )

    text = _strip_html(body)
    # Always prefer real PDF/file bytes when the page embeds them — never keep page.txt
    # alongside (or instead of) the duplicate of the module PDF.
    if embedded_resources:
        pdfs = [
            r
            for r in embedded_resources
            if "pdf" in (r.mime_type or "").lower() or (r.original_filename or "").lower().endswith(".pdf")
        ]
        primary = (pdfs or embedded_resources)[0]
        _apply_canvas_module_meta(primary, module_name=module_name, module_position=module_position)
        db.add(primary)
        if existing is not None and existing.id != primary.id:
            _copy_storage_onto_page_resource(
                db,
                redis=redis,
                user=user,
                page_resource=existing,
                file_resource=primary,
                page_title=page_title,
                embedded_file_ids=file_ids,
            )
            _apply_canvas_module_meta(existing, module_name=module_name, module_position=module_position)
            db.add(existing)
            # Drop the duplicate canvas_file row created for the same bytes.
            db.delete(primary)
            db.flush()
            return existing
        return primary

    if not text:
        return None

    data = text.encode("utf-8")
    content_hash = hashlib.sha256(data).hexdigest()
    if existing and existing.content_sha256 == content_hash and existing.storage_path and existing.mime_type == "text/plain":
        _apply_canvas_module_meta(existing, module_name=module_name, module_position=module_position)
        db.add(existing)
        return existing

    settings = get_settings()
    storage = get_storage_service(settings)
    filename = "page.txt"

    if existing is None:
        resource = Resource(
            user_id=user.id,
            course_id=course.id,
            title=page_title,
            resource_type="page",
            original_filename=filename,
            mime_type="text/plain",
            source_type="canvas_page",
            source_ref=source_ref,
            parse_status="uploaded",
            ocr_status="pending",
            index_status="pending",
            lifecycle_state="uploaded",
            content_sha256=content_hash,
            metadata_json={
                "page_url": str(page_url),
                "embedded_file_ids": file_ids,
            },
        )
        db.add(resource)
        db.flush()
        record_resource_event(
            db,
            resource=resource,
            event_type="resource.uploaded",
            to_state=resource.lifecycle_state,
            details={"source": "canvas_page"},
        )
    else:
        resource = existing
        resource.course_id = course.id
        resource.title = page_title
        resource.resource_type = "page"
        resource.original_filename = filename
        resource.mime_type = "text/plain"
        resource.content_sha256 = content_hash
        resource.parse_status = "uploaded"
        resource.index_status = "pending"
        resource.lifecycle_state = "uploaded"
        meta = dict(resource.metadata_json or {})
        meta["page_url"] = str(page_url)
        meta["embedded_file_ids"] = file_ids
        resource.metadata_json = meta
        db.add(resource)
        db.flush()

    _apply_canvas_module_meta(resource, module_name=module_name, module_position=module_position)
    stored = storage.put_bytes(relative_path=f"{resource.id}/{filename}", data=data)
    resource.storage_path = stored.storage_path
    db.add(resource)
    db.flush()
    _enqueue_resource_index(
        db,
        redis=redis,
        user=user,
        resource=resource,
        idempotency_key=f"canvas-page:{resource.id}:{content_hash[:12]}",
        source="canvas_page",
    )
    return resource


def _is_repairable_canvas_page_stub(resource: Resource) -> bool:
    """Thin page.txt stubs, or page rows previously filled from a guessed/linked PDF."""
    if resource.source_type != "canvas_page" or not resource.source_ref:
        return False
    if resource.mime_type in {None, "text/plain", "text/html"}:
        return True
    meta = dict(resource.metadata_json or {})
    return bool(meta.get("upgraded_from_canvas_page_stub") or meta.get("linked_canvas_file_resource_id"))


def _normalize_match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _copy_storage_onto_page_resource(
    db: Session,
    *,
    redis: Redis,
    user: User,
    page_resource: Resource,
    file_resource: Resource,
    page_title: str,
    embedded_file_ids: list[str],
) -> Resource:
    """Replace a canvas_page stub with the bytes of an already-synced file, keeping page id/source_ref."""
    if not file_resource.storage_path or not Path(file_resource.storage_path).exists():
        return page_resource
    data = Path(file_resource.storage_path).read_bytes()
    settings = get_settings()
    storage = get_storage_service(settings)
    safe_name = Path(file_resource.original_filename or "embedded.pdf").name
    content_hash = hashlib.sha256(data).hexdigest()

    page_resource.title = page_title or page_resource.title
    page_resource.resource_type = "file"
    page_resource.mime_type = file_resource.mime_type or "application/pdf"
    page_resource.original_filename = safe_name
    page_resource.content_sha256 = content_hash
    page_resource.parse_status = "uploaded"
    page_resource.ocr_status = "pending"
    page_resource.index_status = "pending"
    page_resource.lifecycle_state = "uploaded"
    meta = dict(page_resource.metadata_json or {})
    meta["upgraded_from_canvas_page_stub"] = True
    meta["embedded_file_ids"] = embedded_file_ids
    meta["linked_canvas_file_source_ref"] = file_resource.source_ref
    meta.pop("linked_canvas_file_resource_id", None)
    page_resource.metadata_json = meta
    stored = storage.put_bytes(relative_path=f"{page_resource.id}/{safe_name}", data=data)
    page_resource.storage_path = stored.storage_path
    db.add(page_resource)
    db.flush()
    _enqueue_resource_index(
        db,
        redis=redis,
        user=user,
        resource=page_resource,
        idempotency_key=f"canvas-page-upgrade:{page_resource.id}:{content_hash[:12]}",
        source="canvas_page_upgrade",
    )
    return page_resource


def repair_thin_canvas_page(
    db: Session,
    *,
    redis: Redis,
    user: User,
    resource: Resource,
) -> Resource | None:
    """Re-fetch a canvas_page and replace filename-only stubs with embedded PDF/media files."""
    if not _is_repairable_canvas_page_stub(resource):
        return None

    cred = get_credential(db, user=user)
    if not cred or not resource.course_id:
        return _promote_stub_using_existing_course_pdf(db, redis=redis, user=user, resource=resource)

    parts = str(resource.source_ref).split(":", 1)
    if len(parts) != 2:
        return _promote_stub_using_existing_course_pdf(db, redis=redis, user=user, resource=resource)
    course_id, page_key = parts[0], parts[1]
    course = db.get(Course, resource.course_id)
    if not course:
        return None
    client = _client_from_credential(db, cred=cred)
    meta = dict(resource.metadata_json or {})
    page_url = str(meta.get("page_url") or page_key)
    try:
        repaired = _upsert_canvas_page_resource(
            db,
            redis=redis,
            user=user,
            course=course,
            client=client,
            course_id=course_id,
            module_item={"page_url": page_url, "title": resource.title},
        )
    except Exception:  # noqa: BLE001
        repaired = None
    if repaired is not None:
        return repaired
    return _promote_stub_using_existing_course_pdf(db, redis=redis, user=user, resource=resource)


def _promote_stub_using_existing_course_pdf(
    db: Session,
    *,
    redis: Redis,
    user: User,
    resource: Resource,
) -> Resource | None:
    """If page.txt is only a Canvas file label, attach a strongly matching PDF from the same course."""
    if not resource.course_id:
        return None
    label = (resource.title or "").strip()
    stub_name = ""
    try:
        if (
            resource.mime_type in {None, "text/plain", "text/html"}
            and resource.storage_path
            and Path(resource.storage_path).exists()
        ):
            stub_name = Path(resource.storage_path).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:  # noqa: BLE001
        stub_name = ""

    candidates = (
        db.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.course_id == resource.course_id,
                Resource.mime_type == "application/pdf",
                Resource.id != resource.id,
            )
        )
        .scalars()
        .all()
    )
    if not candidates:
        return None

    stub_key = _normalize_match_key(stub_name)
    label_key = _normalize_match_key(label)

    def score(r: Resource) -> int:
        title_key = _normalize_match_key(r.title or "")
        fname_key = _normalize_match_key(r.original_filename or "")
        s = 0
        # Strong: stub filename (e.g. CSCE_314_Fall_2026_Week_2_Narrative) appears in candidate.
        if stub_key and len(stub_key) >= 12:
            if stub_key in title_key or stub_key in fname_key:
                s += 20
            elif title_key and title_key in stub_key:
                s += 12
            elif fname_key and fname_key in stub_key:
                s += 12
        # Medium: title tokens that look like a specific week+topic pair.
        label_tokens = [t for t in re.split(r"[^a-z0-9]+", label.lower()) if len(t) >= 4]
        hit = sum(1 for t in label_tokens if t in (r.title or "").lower() or t in (r.original_filename or "").lower())
        if hit >= 2:
            s += 6
        elif hit == 1 and label_key and (label_key in title_key or label_key in fname_key):
            s += 3
        return s

    ranked = sorted(candidates, key=score, reverse=True)
    # Never promote on a weak "narrative"-only / single-PDF guess — that caused cross-topic mismatches.
    if not ranked or score(ranked[0]) < 12:
        return None
    best = ranked[0]
    if not best.storage_path or not Path(best.storage_path).exists():
        return None

    return _copy_storage_onto_page_resource(
        db,
        redis=redis,
        user=user,
        page_resource=resource,
        file_resource=best,
        page_title=resource.title or best.title,
        embedded_file_ids=list((resource.metadata_json or {}).get("embedded_file_ids") or []),
    )


def sync_canvas(db: Session, *, user: User, redis: Redis) -> CanvasSyncResult:
    cred = get_credential(db, user=user)
    if not cred:
        raise CanvasAPIError("Canvas is not connected", status_code=400)

    client = _client_from_credential(db, cred=cred)
    errors: list[str] = []
    courses_upserted = 0
    assignments_upserted = 0
    syllabi_upserted = 0
    files_upserted = 0
    notebooks_upserted = 0

    try:
        canvas_courses = client.list_active_courses()
    except CanvasAPIError as exc:
        cred.last_sync_status = "failed"
        cred.last_sync_error = str(exc)
        cred.last_synced_at = utcnow()
        db.add(cred)
        db.commit()
        raise

    for canvas_course in canvas_courses:
        try:
            course = _upsert_course(db, user=user, canvas_course=canvas_course)
            db.flush()
            courses_upserted += 1
            course_id = canvas_course.get("id")
            if course_id is not None:
                assignments_by_id: dict[str, dict] = {}
                try:
                    for assignment in client.list_assignments(course_id):
                        aid = assignment.get("id")
                        if aid is not None:
                            assignments_by_id[str(aid)] = assignment
                        task = _upsert_assignment(db, user=user, course=course, assignment=assignment)
                        assignments_upserted += 1
                        _, created = ensure_section_notebook(
                            db, user=user, course_id=course.id, title=task.title
                        )
                        if created:
                            notebooks_upserted += 1
                except CanvasAPIError as exc:
                    errors.append(f"assignments course={course_id}: {exc}")

                # Mirror Canvas Modules — files, pages, and assignment/quiz/link items.
                seen_file_ids: set[str] = set()

                try:
                    for module in client.list_modules(course_id):
                        module_name = str(module.get("name") or "").strip() or None
                        module_id = module.get("id")
                        module_position = module.get("position")
                        try:
                            module_position = int(module_position) if module_position is not None else None
                        except (TypeError, ValueError):
                            module_position = None

                        items = list(module.get("items") or [])
                        if not items and module_id is not None:
                            try:
                                items = client.list_module_items(course_id, module_id)
                            except CanvasAPIError:
                                items = []

                        for item in items:
                            title = item.get("title")
                            item_type = str(item.get("type") or "").lower()
                            _, created = ensure_section_notebook(
                                db, user=user, course_id=course.id, title=title
                            )
                            if created:
                                notebooks_upserted += 1

                            if item_type == "file":
                                content_id = item.get("content_id")
                                if content_id is None:
                                    continue
                                key = str(content_id)
                                if key in seen_file_ids:
                                    existing_file = (
                                        db.execute(
                                            select(Resource).where(
                                                Resource.user_id == user.id,
                                                Resource.source_type == "canvas_file",
                                                Resource.source_ref == key,
                                            )
                                        )
                                        .scalars()
                                        .first()
                                    )
                                    if existing_file:
                                        _apply_canvas_module_meta(
                                            existing_file,
                                            module_name=module_name,
                                            module_position=module_position,
                                            module_id=module_id,
                                            module_item=item,
                                        )
                                        db.add(existing_file)
                                    continue
                                try:
                                    canvas_file = client.get_file(content_id)
                                    res = _upsert_canvas_file_resource(
                                        db,
                                        redis=redis,
                                        user=user,
                                        course=course,
                                        client=client,
                                        canvas_file=canvas_file,
                                        title_override=str(title) if title else None,
                                    )
                                    if res:
                                        seen_file_ids.add(key)
                                        _apply_canvas_module_meta(
                                            res,
                                            module_name=module_name,
                                            module_position=module_position,
                                            module_id=module_id,
                                            module_item=item,
                                        )
                                        db.add(res)
                                        files_upserted += 1
                                except Exception as exc:  # noqa: BLE001
                                    errors.append(f"file course={course_id} id={content_id}: {exc}")
                            elif item_type == "page":
                                try:
                                    page_res = _upsert_canvas_page_resource(
                                        db,
                                        redis=redis,
                                        user=user,
                                        course=course,
                                        client=client,
                                        course_id=course_id,
                                        module_item=item,
                                        module_name=module_name,
                                        module_position=module_position,
                                        seen_file_ids=seen_file_ids,
                                    )
                                    if page_res:
                                        _apply_canvas_module_meta(
                                            page_res,
                                            module_name=module_name,
                                            module_position=module_position,
                                            module_id=module_id,
                                            module_item=item,
                                        )
                                        db.add(page_res)
                                        files_upserted += 1
                                except Exception as exc:  # noqa: BLE001
                                    errors.append(f"page course={course_id}: {exc}")
                            elif item_type in {
                                "assignment",
                                "quiz",
                                "discussion",
                                "discussiontopic",
                                "externalurl",
                                "externaltool",
                            }:
                                try:
                                    content_id = item.get("content_id")
                                    asg = (
                                        assignments_by_id.get(str(content_id))
                                        if content_id is not None
                                        else None
                                    )
                                    item_res = _upsert_canvas_module_item_resource(
                                        db,
                                        redis=redis,
                                        user=user,
                                        course=course,
                                        client=client,
                                        course_id=course_id,
                                        module_item=item,
                                        module_name=module_name,
                                        module_position=module_position,
                                        module_id=module_id,
                                        assignment=asg,
                                        seen_file_ids=seen_file_ids,
                                    )
                                    if item_res:
                                        files_upserted += 1
                                except Exception as exc:  # noqa: BLE001
                                    errors.append(f"module item course={course_id}: {exc}")
                except CanvasAPIError as exc:
                    if exc.status_code != 403:
                        errors.append(f"modules course={course_id}: {exc}")

                try:
                    # Remove leftover assignment/quiz text stubs from older syncs.
                    stale_text = (
                        db.execute(
                            select(Resource).where(
                                Resource.user_id == user.id,
                                Resource.course_id == course.id,
                                Resource.source_type == "canvas_module_item",
                                Resource.mime_type == "text/plain",
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for stub in stale_text:
                        db.delete(stub)
                    if stale_text:
                        db.flush()
                    _dedupe_course_resources_by_content(db, user=user, course_id=course.id)
                    _dedupe_course_resources_by_module_item(db, user=user, course_id=course.id)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"dedupe course={course_id}: {exc}")

            try:
                syllabus = _upsert_syllabus_resource(
                    db, redis=redis, user=user, course=course, canvas_course=canvas_course
                )
                if syllabus:
                    syllabi_upserted += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"syllabus course={course_id}: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"course={canvas_course.get('id')}: {exc}")

    try:
        _collapse_duplicate_canvas_courses(db, user=user)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"collapse courses: {exc}")

    cred.last_synced_at = utcnow()
    cred.last_sync_status = "ok" if not errors else "partial"
    cred.last_sync_error = "; ".join(errors)[:2000] if errors else None
    db.add(cred)
    db.commit()

    return CanvasSyncResult(
        courses_upserted=courses_upserted,
        assignments_upserted=assignments_upserted,
        syllabi_upserted=syllabi_upserted,
        files_upserted=files_upserted,
        notebooks_upserted=notebooks_upserted,
        errors=errors,
    )
