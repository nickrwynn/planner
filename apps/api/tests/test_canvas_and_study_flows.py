from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import select

from app.models.course import Course
from app.models.integration_credential import IntegrationCredential
from app.models.task import Task
from app.models.user import User
from app.schemas.canvas import CanvasConnectRequest
from app.services.canvas_client import CanvasClient, normalize_canvas_base_url
from app.services import canvas_sync as canvas_sync_service
from app.services.secret_crypto import decrypt_secret, encrypt_secret


def test_normalize_canvas_base_url():
    assert normalize_canvas_base_url("myschool.instructure.com") == "https://myschool.instructure.com"
    assert normalize_canvas_base_url("https://myschool.instructure.com/") == "https://myschool.instructure.com"


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-integrations-unit")
    from app.core.config import get_settings

    get_settings.cache_clear()
    token = "canvas-pat-abc"
    enc = encrypt_secret(token)
    assert enc != token
    assert decrypt_secret(enc) == token
    get_settings.cache_clear()


def test_canvas_client_get_self(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer tok"
        assert request.url.path.endswith("/api/v1/users/self")
        return httpx.Response(200, json={"id": 9, "name": "Ada"})

    transport = httpx.MockTransport(handler)

    class PatchedClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.services.canvas_client.httpx.Client", PatchedClient)
    client = CanvasClient(base_url="https://example.instructure.com", access_token="tok")
    assert client.get_self()["name"] == "Ada"


def test_canvas_sync_upsert_idempotent(db_session, monkeypatch):
    user = User(email="canvas@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-integrations-unit")
    from app.core.config import get_settings

    get_settings.cache_clear()

    courses_payload = [
        {
            "id": 101,
            "name": "Calc I",
            "course_code": "MATH101",
            "term": {"name": "Fall 2026"},
            "syllabus_body": "<p>Welcome to Calc</p>",
        }
    ]
    assignments_payload = [
        {
            "id": 501,
            "name": "HW 1",
            "description": "<p>Do problems 1-10. Practice derivatives.</p>",
            "due_at": "2026-09-15T23:59:00Z",
            "points_possible": 10,
            "submission_types": ["online_upload"],
            "html_url": "https://example.instructure.com/courses/101/assignments/501",
            "unlock_at": None,
            "lock_at": None,
        }
    ]

    class FakeCanvas:
        def __init__(self, *args, **kwargs):
            pass

        def get_self(self):
            return {"id": 1, "name": "Ada"}

        def list_active_courses(self):
            return courses_payload

        def list_assignments(self, course_id):
            assert str(course_id) == "101"
            return assignments_payload

    monkeypatch.setattr("app.services.canvas_sync.CanvasClient", FakeCanvas)
    monkeypatch.setattr(
        "app.services.canvas_sync._upsert_syllabus_resource",
        lambda **kwargs: None,
    )

    canvas_sync_service.connect_canvas(
        db_session,
        user=user,
        data=CanvasConnectRequest(base_url="https://example.instructure.com", access_token="secret-token"),
    )
    cred = db_session.execute(select(IntegrationCredential)).scalars().first()
    assert cred is not None
    assert decrypt_secret(cred.token_encrypted) == "secret-token"

    fake_redis = MagicMock()
    result1 = canvas_sync_service.sync_canvas(db_session, user=user, redis=fake_redis)
    result2 = canvas_sync_service.sync_canvas(db_session, user=user, redis=fake_redis)

    assert result1.courses_upserted == 1
    assert result1.assignments_upserted == 1
    assert result2.courses_upserted == 1
    assert result2.assignments_upserted == 1

    courses = db_session.execute(select(Course).where(Course.user_id == user.id)).scalars().all()
    tasks = db_session.execute(select(Task).where(Task.user_id == user.id)).scalars().all()
    assert len(courses) == 1
    assert courses[0].source_type == "canvas"
    assert courses[0].source_ref == "101"
    assert len(tasks) == 1
    assert tasks[0].source_ref == "501"
    assert tasks[0].due_at is not None
    due = tasks[0].due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    assert due == datetime(2026, 9, 15, 23, 59, tzinfo=UTC)
    assert tasks[0].logistics_json["points_possible"] == 10
    assert tasks[0].description and "problems" in tasks[0].description.lower()
    get_settings.cache_clear()


def test_canvas_status_endpoint(client, db_session):
    res = client.get("/integrations/canvas/status")
    assert res.status_code == 200
    assert res.json()["connected"] is False


def test_study_flow_ensure_and_advance(client):
    course = client.post("/courses", json={"name": "Physics"}).json()
    flow = client.get(f"/study-flows/by-course/{course['id']}").json()
    assert flow["active_run"]["current_step_key"] == "read"
    assert len(flow["active_run"]["steps"]) == 4

    run_id = flow["active_run"]["id"]
    advanced = client.post(
        f"/study-flows/runs/{run_id}/advance",
        json={"step_key": "read", "complete": True, "payload_json": {"ok": True}},
    ).json()
    assert advanced["current_step_key"] == "highlight_ask"

    again = client.get(f"/study-flows/by-course/{course['id']}").json()
    assert again["active_run"]["id"] == run_id
    assert again["active_run"]["current_step_key"] == "highlight_ask"


def test_study_flow_score(client):
    res = client.post(
        "/study-flows/score",
        json={
            "source_text": "Derivatives measure instantaneous rate of change of a function.",
            "student_text": "A derivative is the instantaneous rate of change.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["score"] > 0.2
    assert "feedback" in body


def test_oauth_start_requires_config(client, monkeypatch):
    monkeypatch.setenv("CANVAS_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("CANVAS_OAUTH_CLIENT_SECRET", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    res = client.post("/integrations/canvas/oauth/start", json={"base_url": "https://canvas.tamu.edu"})
    assert res.status_code == 400
    get_settings.cache_clear()


def test_oauth_start_and_callback(client, monkeypatch):
    monkeypatch.setenv("CANVAS_OAUTH_CLIENT_ID", "cid-123")
    monkeypatch.setenv("CANVAS_OAUTH_CLIENT_SECRET", "csec-456")
    monkeypatch.setenv("CANVAS_OAUTH_REDIRECT_URI", "http://localhost:8000/integrations/canvas/oauth/callback")
    monkeypatch.setenv("CANVAS_OAUTH_SUCCESS_URL", "http://localhost:3000/courses?canvas=connected")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-integrations-unit")
    from app.core.config import get_settings

    get_settings.cache_clear()

    start = client.post("/integrations/canvas/oauth/start", json={"base_url": "https://canvas.tamu.edu"})
    assert start.status_code == 200
    body = start.json()
    assert "login/oauth2/auth" in body["authorize_url"]
    assert "client_id=cid-123" in body["authorize_url"]
    assert "state=" in body["authorize_url"]
    state = body["state"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login/oauth2/token"):
            assert request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded")
            return httpx.Response(
                200,
                json={
                    "access_token": "access-abc",
                    "refresh_token": "refresh-xyz",
                    "expires_in": 3600,
                    "user": {"id": 42, "name": "Jimi"},
                    "token_type": "Bearer",
                },
            )
        if request.url.path.endswith("/api/v1/users/self"):
            return httpx.Response(200, json={"id": 42, "name": "Jimi"})
        return httpx.Response(404, json={"error": "missing"})

    transport = httpx.MockTransport(handler)

    class PatchedClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.services.canvas_oauth.httpx.Client", PatchedClient)
    monkeypatch.setattr("app.services.canvas_client.httpx.Client", PatchedClient)

    cb = client.get(
        "/integrations/canvas/oauth/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert cb.status_code == 302
    assert "canvas=connected" in cb.headers["location"]

    status = client.get("/integrations/canvas/status").json()
    assert status["connected"] is True
    assert status["auth_mode"] == "oauth"
    assert status["canvas_user_name"] == "Jimi"
    assert status["oauth_configured"] is True
    get_settings.cache_clear()


def test_parse_qr_login_url():
    from app.services.canvas_qr_login import parse_qr_login_url

    parsed = parse_qr_login_url(
        "https://sso.canvaslms.com/canvas/login?domain=canvas.tamu.edu&code=abc123"
    )
    assert parsed["domain"] == "canvas.tamu.edu"
    assert parsed["code"] == "abc123"


def test_normalize_session_cookie():
    from app.services.canvas_client import normalize_session_cookie

    assert normalize_session_cookie("rawvalue") == "rawvalue"
    assert normalize_session_cookie("canvas_session=abc123") == "abc123"
    assert normalize_session_cookie("foo=1; canvas_session=xyz; bar=2") == "xyz"


def test_extract_section_key():
    from app.services.section_notebooks import extract_section_key

    assert extract_section_key("Reading 1.1 Limits") == "1.1"
    assert extract_section_key("Section 2.3") == "2.3"
    assert extract_section_key("Homework set A") is None


def test_extract_canvas_file_ids_from_html():
    from app.services.canvas_sync import extract_canvas_file_ids_from_html, _is_thin_page_text

    html = """
    <p><a class="instructure_file_link"
       data-api-endpoint="https://canvas.tamu.edu/api/v1/courses/1/files/998877"
       href="/courses/1/files/998877/download?download_frd=1">CSCE_314_Fall_2026_Week_2_Narrative</a></p>
    <iframe src="/media_attachments_iframe/112233"></iframe>
    """
    ids = extract_canvas_file_ids_from_html(html)
    assert ids[0] == "998877"
    assert "112233" in ids
    assert _is_thin_page_text("CSCE_314_Fall_2026_Week_2_Narrative")
    assert _is_thin_page_text(None)
    assert not _is_thin_page_text(
        "Functional Foundations: From Paradigms to Practice. This week we shift from process to meaning "
        "and explore why another paradigm matters for how we think about code."
    )


def test_normalize_match_key_and_repairable_stub_flags():
    from types import SimpleNamespace

    from app.services.canvas_sync import _is_repairable_canvas_page_stub, _normalize_match_key

    assert _normalize_match_key("CSCE_314_Fall_2026_Week_2_Narrative") == "csce314fall2026week2narrative"
    stub = SimpleNamespace(
        source_type="canvas_page",
        source_ref="482349:9583901",
        mime_type="application/pdf",
        metadata_json={"upgraded_from_canvas_page_stub": True},
    )
    assert _is_repairable_canvas_page_stub(stub)
    plain = SimpleNamespace(
        source_type="canvas_page",
        source_ref="482349:9583901",
        mime_type="text/plain",
        metadata_json={},
    )
    assert _is_repairable_canvas_page_stub(plain)
    other = SimpleNamespace(
        source_type="canvas_file",
        source_ref="99",
        mime_type="application/pdf",
        metadata_json={},
    )
    assert not _is_repairable_canvas_page_stub(other)


def test_collect_student_files_ignores_403(monkeypatch):
    from app.services import canvas_sync as sync
    from app.services.canvas_client import CanvasAPIError

    class FakeClient:
        def list_course_files(self, course_id):
            raise CanvasAPIError("nope", status_code=403)

        def list_modules(self, course_id):
            return [
                {
                    "items": [
                        {"type": "File", "content_id": 99, "title": "Reading 1.1.pdf"},
                        {"type": "Page", "page_url": "week-1", "title": "Week 1"},
                    ]
                }
            ]

        def get_file(self, file_id):
            assert str(file_id) == "99"
            return {"id": 99, "display_name": "Reading 1.1.pdf", "url": "https://example/f", "content-type": "application/pdf"}

    files, notes = sync._collect_student_accessible_files(FakeClient(), course_id=1)
    assert notes == []
    assert len(files) == 1
    assert files[0]["id"] == 99


def test_session_connect(client, monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-integrations-unit")
    monkeypatch.setenv("CANVAS_DEFAULT_BASE_URL", "https://canvas.tamu.edu")
    from app.core.config import get_settings

    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "canvas_session=sess-cookie" in (request.headers.get("cookie") or "")
        assert request.url.path.endswith("/api/v1/users/self")
        return httpx.Response(200, json={"id": 7, "name": "Session User"})

    transport = httpx.MockTransport(handler)

    class PatchedClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.services.canvas_client.httpx.Client", PatchedClient)
    res = client.post(
        "/integrations/canvas/session",
        json={"session_cookie": "canvas_session=sess-cookie", "base_url": "https://canvas.tamu.edu"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is True
    assert body["auth_mode"] == "session"
    assert body["canvas_user_name"] == "Session User"
    get_settings.cache_clear()
