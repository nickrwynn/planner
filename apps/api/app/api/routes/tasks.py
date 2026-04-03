from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.models.course import Course
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import courses as course_service
from app.services import tasks as task_service

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    course_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    # If scoping to a course, ensure the user owns it.
    if course_id is not None:
        course = course_service.get_course(db, user=user, course_id=course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return task_service.list_tasks(db, user=user, course_id=course_id, limit=limit, offset=offset)


@router.get("/courses/{course_id}/tasks", response_model=list[TaskRead])
def list_tasks_for_course(
    course_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return task_service.list_tasks(db, user=user, course_id=course_id, limit=limit, offset=offset)


@router.post("/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    course: Course | None = course_service.get_course(db, user=user, course_id=payload.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return task_service.create_task(db, course=course, data=payload)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: UUID, payload: TaskUpdate, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    task = task_service.get_task_for_user(db, user=user, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_service.update_task(db, task=task, data=payload)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    task = task_service.get_task_for_user(db, user=user, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/tasks/{task_id}")
def delete_task(task_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    task = task_service.get_task_for_user(db, user=user, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"ok": True}

