from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.task import TaskRead


class PlannerNextResponse(BaseModel):
    task: TaskRead | None = None
    reasons: list[str] = Field(default_factory=list)


class PlannerUpcomingResponse(BaseModel):
    tasks: list[TaskRead] = Field(default_factory=list)


class PlannerLabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PlannerLabelRead(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
