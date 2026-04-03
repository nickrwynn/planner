from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.schemas.planner import PlannerNextResponse, PlannerUpcomingResponse
from app.schemas.task import TaskRead
from app.services import planner as planner_service

router = APIRouter(prefix="/planner", tags=["planner"])


@router.get("/next", response_model=PlannerNextResponse)
def planner_next(db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    task, reasons = planner_service.next_open_task(db, user=user)
    return PlannerNextResponse(task=TaskRead.model_validate(task) if task else None, reasons=reasons)


@router.get("/upcoming", response_model=PlannerUpcomingResponse)
def planner_upcoming(
    limit: int = Query(default=8, ge=1, le=50),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    tasks = planner_service.upcoming_open_tasks(db, user=user, limit=limit)
    return PlannerUpcomingResponse(tasks=[TaskRead.model_validate(t) for t in tasks])
