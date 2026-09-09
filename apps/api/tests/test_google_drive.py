from __future__ import annotations

from uuid import uuid4

import pytest

from app.services import google_oauth
from app.services.google_drive import _guess_mime, _is_listable_mime


def test_google_oauth_state_roundtrip(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret-for-google-oauth-state-32chars")
    from app.core.config import get_settings

    get_settings.cache_clear()
    user_id = uuid4()
    state = google_oauth.create_oauth_state(user_id=user_id, return_to="/courses/x/resources")
    claims = google_oauth.parse_oauth_state(state)
    assert claims["sub"] == str(user_id)
    assert claims["purpose"] == "google_oauth"
    assert claims["return_to"] == "/courses/x/resources"
    get_settings.cache_clear()


def test_google_oauth_requires_config(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(google_oauth.GoogleAPIError):
        google_oauth.build_authorize_url(state="x")
    get_settings.cache_clear()


def test_drive_mime_helpers():
    assert _is_listable_mime("application/pdf")
    assert _is_listable_mime("application/vnd.google-apps.document")
    assert not _is_listable_mime("application/zip")
    assert _guess_mime("notes.pdf", "application/octet-stream") == "application/pdf"
    assert _guess_mime("doc", "application/vnd.google-apps.document") == "application/pdf"
