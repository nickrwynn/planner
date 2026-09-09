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
    # Hybrid by default: use course sources when present, otherwise general knowledge / web notes.
    allow_general_knowledge: bool = True
    allow_web_lookup: bool = True


class AskResponse(BaseModel):
    conversation_id: UUID
    answer: str
    citations: list[Citation]


class AiStatusResponse(BaseModel):
    configured: bool
    provider: str | None = None
    model: str | None = None
    message: str


class HandwritingRequest(BaseModel):
    image_base64: str = Field(min_length=8)
    mode: str = Field(default="text", pattern="^(text|math)$")


class HandwritingResponse(BaseModel):
    text: str
    latex: str | None = None
    provider: str
    model_name: str | None = None


class CompleteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    course_id: UUID | None = None


class CompleteResponse(BaseModel):
    completion: str
    provider: str | None = None


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

