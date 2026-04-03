from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    term: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=20)
    grading_schema_json: dict | None = None


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    term: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=20)
    grading_schema_json: dict | None = None


class CourseRead(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    code: str | None
    term: str | None
    color: str | None
    grading_schema_json: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CourseGradeSummary(BaseModel):
    course_id: UUID
    weighted_completion_pct: float
    done_tasks: int
    total_tasks: int

