from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.schemas.planner import (
    PlannerLabelCreate,
    PlannerLabelRead,
    PlannerNextResponse,
    PlannerUpcomingResponse,
)
from app.schemas.task import TaskRead
from app.services import planner as planner_service
from app.services import planner_labels as label_service

router = APIRouter(prefix="/planner", tags=["planner"])


def _label_read(label) -> PlannerLabelRead:
    return PlannerLabelRead(
        id=str(label.id),
        name=label.name,
        created_at=label.created_at.isoformat(),
        updated_at=label.updated_at.isoformat(),
    )


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


@router.get("/labels", response_model=list[PlannerLabelRead])
def list_planner_labels(db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    return [_label_read(label) for label in label_service.list_labels(db, user=user)]


@router.post("/labels", response_model=PlannerLabelRead)
def create_planner_label(
    payload: PlannerLabelCreate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    name = " ".join(payload.name.split()).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    label = label_service.create_label(db, user=user, name=name)
    return _label_read(label)


@router.delete("/labels/{label_id}")
def delete_planner_label(
    label_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    label = label_service.get_label_for_user(db, user=user, label_id=label_id)
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    label_service.delete_label(db, label=label)
    return {"ok": True}
