from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CanvasConnectRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=500)
    access_token: str = Field(min_length=8, max_length=2000)


class CanvasOAuthStartRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)


class CanvasOAuthStartRead(BaseModel):
    authorize_url: str
    state: str


class CanvasSessionConnectRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)
    session_cookie: str = Field(min_length=8, max_length=8000)


class CanvasQrConnectRequest(BaseModel):
    qr_url: str = Field(min_length=20, max_length=8000)


class CanvasStatusRead(BaseModel):
    connected: bool
    base_url: str | None = None
    last_validated_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    canvas_user_name: str | None = None
    auth_mode: str | None = None
    oauth_configured: bool = False
    default_base_url: str | None = None


class CanvasSyncResult(BaseModel):
    courses_upserted: int
    assignments_upserted: int
    syllabi_upserted: int
    files_upserted: int = 0
    notebooks_upserted: int = 0
    errors: list[str] = Field(default_factory=list)
