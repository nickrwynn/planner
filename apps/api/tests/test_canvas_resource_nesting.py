"""Canvas pages own their embedded attachments instead of flooding the course list.

A resource-hub page such as "Canvas Resources for Students" embeds a dozen
screenshots. Before nesting, each one became its own top-level resource, so
five Canvas items produced roughly thirty rows.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import select

from app.models.course import Course
from app.models.resource import Resource
from app.models.user import User
from app.schemas.canvas import CanvasConnectRequest
from app.services import canvas_sync as canvas_sync_service

PAGE_HTML = """
<p>Everything you need:</p>
<a href="/courses/101/files/9001">Syllabus.pdf</a>
<img src="/courses/101/files/9002/preview" alt="calendar">
<img src="/courses/101/files/9003/preview" alt="quizzes">
<img src="/courses/101/files/9004/preview" alt="settings">
"""

CANVAS_FILES = {
    "9001": {
        "id": 9001,
        "display_name": "Syllabus.pdf",
        "content-type": "application/pdf",
        "url": "https://example.instructure.com/files/9001/download",
        "uuid": "u9001",
        "size": 2048,
    },
    "9002": {
        "id": 9002,
        "display_name": "Canvas_Resources_Calendar.png",
        "content-type": "image/png",
        "url": "https://example.instructure.com/files/9002/download",
        "uuid": "u9002",
        "size": 1024,
    },
    "9003": {
        "id": 9003,
        "display_name": "Canvas_Resources_Quizzes.png",
        "content-type": "image/png",
        "url": "https://example.instructure.com/files/9003/download",
        "uuid": "u9003",
        "size": 1024,
    },
    "9004": {
        "id": 9004,
        "display_name": "Canvas_Resources_User Settings.png",
        "content-type": "image/png",
        "url": "https://example.instructure.com/files/9004/download",
        "uuid": "u9004",
        "size": 1024,
    },
}


class FakeCanvas:
    """Minimal Canvas with one module holding one page that embeds four files."""

    def __init__(self, *args, **kwargs):
        pass

    def get_self(self):
        return {"id": 1, "name": "Ada"}

    def list_active_courses(self):
        return [{"id": 101, "name": "CSCE 314", "course_code": "CSCE314", "syllabus_body": ""}]

    def list_assignments(self, course_id):
        return []

    def list_modules(self, course_id):
        return [
            {
                "id": 7,
                "name": "Student Resources",
                "position": 1,
                "items": [
                    {
                        "id": 71,
                        "type": "Page",
                        "title": "Syllabus",
                        "page_url": "syllabus",
                        "position": 1,
                    }
                ],
            }
        ]

    def get_page(self, course_id, page_url):
        return {"page_id": 555, "title": "Syllabus", "body": PAGE_HTML}

    def get_file(self, file_id):
        return CANVAS_FILES[str(file_id)]

    def download_bytes(self, url):
        # Distinct bytes per file so content hashes differ.
        return f"payload for {url}".encode()


def _sync(db_session, monkeypatch, client_cls=FakeCanvas) -> tuple[User, Course]:
    user = User(email="canvas-nesting@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-integrations-unit")
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.services.canvas_sync.CanvasClient", client_cls)
    monkeypatch.setattr("app.services.canvas_sync._upsert_syllabus_resource", lambda **kwargs: None)

    canvas_sync_service.connect_canvas(
        db_session,
        user=user,
        data=CanvasConnectRequest(
            base_url="https://example.instructure.com", access_token="secret-token"
        ),
    )
    canvas_sync_service.sync_canvas(db_session, user=user, redis=MagicMock())
    course = (
        db_session.execute(select(Course).where(Course.user_id == user.id)).scalars().first()
    )
    get_settings.cache_clear()
    return user, course


def _resources(db_session, user) -> list[Resource]:
    return list(
        db_session.execute(select(Resource).where(Resource.user_id == user.id)).scalars().all()
    )


def test_page_embeds_nest_under_the_page(db_session, monkeypatch):
    user, _course = _sync(db_session, monkeypatch)
    resources = _resources(db_session, user)

    top_level = [r for r in resources if r.parent_resource_id is None]
    children = [r for r in resources if r.parent_resource_id is not None]

    # One Canvas page must produce exactly one top-level entry, not four.
    assert len(top_level) == 1, [r.title for r in top_level]
    page = top_level[0]
    assert page.title == "Syllabus"

    # The three images hang off it rather than cluttering the course list.
    assert len(children) == 3
    assert all(c.parent_resource_id == page.id for c in children)
    assert {c.original_filename for c in children} == {
        "Canvas_Resources_Calendar.png",
        "Canvas_Resources_Quizzes.png",
        "Canvas_Resources_User Settings.png",
    }


def test_page_serves_the_embedded_pdf(db_session, monkeypatch):
    """Student Resources -> Syllabus should open the syllabus PDF itself."""
    user, _course = _sync(db_session, monkeypatch)
    page = next(r for r in _resources(db_session, user) if r.parent_resource_id is None)

    assert page.source_type == "canvas_page"
    assert page.mime_type == "application/pdf"
    assert (page.original_filename or "").endswith(".pdf")
    assert page.storage_path


def test_nesting_is_stable_across_repeat_syncs(db_session, monkeypatch):
    user, _course = _sync(db_session, monkeypatch)
    canvas_sync_service.sync_canvas(db_session, user=user, redis=MagicMock())

    resources = _resources(db_session, user)
    top_level = [r for r in resources if r.parent_resource_id is None]

    # Re-syncing must not re-promote the attachments to top level or duplicate them.
    assert len(top_level) == 1
    assert len(resources) == 4


def test_resync_adopts_resources_left_flat_by_older_syncs(db_session, monkeypatch):
    """The migration path for data already in the database.

    Existing rows were imported before nesting existed, so they all sit at top
    level. Re-syncing has to adopt them rather than requiring a wipe.
    """
    user, _course = _sync(db_session, monkeypatch)

    # Simulate the pre-nesting state: everything flat.
    for row in _resources(db_session, user):
        row.parent_resource_id = None
        db_session.add(row)
    db_session.flush()
    assert all(r.parent_resource_id is None for r in _resources(db_session, user))

    canvas_sync_service.sync_canvas(db_session, user=user, redis=MagicMock())

    resources = _resources(db_session, user)
    top_level = [r for r in resources if r.parent_resource_id is None]
    assert len(top_level) == 1
    assert len(resources) == 4


IMAGE_ONLY_HTML = """
<p>Office hours are Tuesday and Thursday, 2-4pm in HRBB 328.</p>
<img src="/courses/101/files/9002/preview" alt="calendar">
<img src="/courses/101/files/9003/preview" alt="map">
"""


class ImageOnlyCanvas(FakeCanvas):
    """A page whose only embeds are screenshots, like the Office Hours page."""

    def list_modules(self, course_id):
        return [
            {
                "id": 7,
                "name": "Student Resources",
                "position": 1,
                "items": [
                    {
                        "id": 72,
                        "type": "Page",
                        "title": "Office Hours",
                        "page_url": "office-hours",
                        "position": 1,
                    }
                ],
            }
        ]

    def get_page(self, course_id, page_url):
        return {"page_id": 556, "title": "Office Hours", "body": IMAGE_ONLY_HTML}


def test_screenshots_never_stand_in_for_the_page(db_session, monkeypatch):
    """A decorative image must not replace the page it was embedded in.

    This is what turned "Office Hours" into a PNG named after the page.
    """
    user, _course = _sync(db_session, monkeypatch, client_cls=ImageOnlyCanvas)

    resources = _resources(db_session, user)
    top_level = [r for r in resources if r.parent_resource_id is None]
    assert len(top_level) == 1
    page = top_level[0]

    assert page.title == "Office Hours"
    assert page.source_type == "canvas_page"
    # The page keeps its own prose rather than becoming one of the screenshots.
    assert page.mime_type == "text/plain"
    assert len([r for r in resources if r.parent_resource_id == page.id]) == 2


def test_module_metadata_still_groups_the_page(db_session, monkeypatch):
    """The UI groups by module name, so the page must keep carrying it."""
    user, _course = _sync(db_session, monkeypatch)
    page = next(r for r in _resources(db_session, user) if r.parent_resource_id is None)

    assert (page.metadata_json or {}).get("canvas_module_name") == "Student Resources"
