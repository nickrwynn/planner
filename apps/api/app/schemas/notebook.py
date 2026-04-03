from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotebookCreate(BaseModel):
    course_id: UUID | None = None
    parent_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)


class NotebookUpdate(BaseModel):
    course_id: UUID | None = None
    parent_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


class NotebookRead(BaseModel):
    id: UUID
    course_id: UUID | None
    parent_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

