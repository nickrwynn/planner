from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.resource import ResourceRead


class GoogleDriveStatusRead(BaseModel):
    connected: bool
    oauth_configured: bool = False
    account_email: str | None = None
    account_name: str | None = None
    last_validated_at: str | None = None
    last_sync_error: str | None = None
    redirect_uri: str | None = None


class GoogleOAuthStartRequest(BaseModel):
    return_to: str | None = Field(default=None, max_length=500)


class GoogleOAuthStartRead(BaseModel):
    authorize_url: str
    state: str


class GoogleDriveFileItem(BaseModel):
    id: str
    name: str
    mime_type: str | None = None
    modified_time: str | None = None
    size: int | None = None
    web_view_link: str | None = None
    icon_link: str | None = None


class GoogleDriveImportRequest(BaseModel):
    file_id: str = Field(min_length=1, max_length=200)
    course_id: UUID
    title: str | None = Field(default=None, max_length=300)


class GoogleDriveImportResult(BaseModel):
    resource: ResourceRead
    created: bool
    message: str
