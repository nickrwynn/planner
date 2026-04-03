from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ALLOWED_TASK_TYPES = {"assignment", "exam", "reading", "project", "other"}


def _normalize_task_type(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip().lower()
    if not s:
        return None
    if s not in ALLOWED_TASK_TYPES:
        raise ValueError(f"task_type must be one of {sorted(ALLOWED_TASK_TYPES)}")
    return s


class TaskCreate(BaseModel):
    course_id: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    task_type: str | None = None
    due_at: datetime | None = None
    weight: float | None = None
    source_type: str | None = None
    source_ref: str | None = None
    status: str = "todo"
    estimated_minutes: int | None = None
    priority_score: float | None = None

    _task_type_validator = field_validator("task_type", mode="before")(_normalize_task_type)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    task_type: str | None = None
    due_at: datetime | None = None
    weight: float | None = None
    source_type: str | None = None
    source_ref: str | None = None
    status: str | None = None
    estimated_minutes: int | None = None
    priority_score: float | None = None

    _task_type_validator = field_validator("task_type", mode="before")(_normalize_task_type)


class TaskRead(BaseModel):
    id: UUID
    user_id: UUID
    course_id: UUID
    title: str
    description: str | None
    task_type: str | None
    due_at: datetime | None
    weight: float | None
    source_type: str | None
    source_ref: str | None
    status: str
    estimated_minutes: int | None
    priority_score: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

