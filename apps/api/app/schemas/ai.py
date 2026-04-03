from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Citation(BaseModel):
    resource_id: UUID
    page_number: int | None = None
    chunk_id: UUID
    chunk_index: int
    snippet: str


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None
    course_id: UUID | None = None
    resource_ids: list[UUID] | None = None
    top_k: int = Field(default=8, ge=1, le=20)


class AskResponse(BaseModel):
    conversation_id: UUID
    answer: str
    citations: list[Citation]


class MessageRead(BaseModel):
    id: UUID
    user_id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations_json: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationRead(BaseModel):
    id: UUID
    user_id: UUID
    course_id: UUID | None
    title: str | None
    mode: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

