from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.task import TaskRead


class PlannerNextResponse(BaseModel):
    task: TaskRead | None = None
    reasons: list[str] = Field(default_factory=list)


class PlannerUpcomingResponse(BaseModel):
    tasks: list[TaskRead] = Field(default_factory=list)
