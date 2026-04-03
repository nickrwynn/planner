from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate


def list_tasks(
    db: Session,
    *,
    user: User,
    course_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Task]:
    q = select(Task).where(Task.user_id == user.id).order_by(Task.created_at.desc())
    if course_id is not None:
        q = q.where(Task.course_id == course_id)
    q = q.limit(limit).offset(offset)
    return db.execute(q).scalars().all()


def get_task(db: Session, *, task_id: UUID) -> Task | None:
    return db.get(Task, task_id)


def get_task_for_user(db: Session, *, user: User, task_id: UUID) -> Task | None:
    return (
        db.execute(
            select(Task)
            .where(
                Task.id == task_id,
                Task.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )


def create_task(db: Session, *, course: Course, data: TaskCreate) -> Task:
    task = Task(user_id=course.user_id, course_id=course.id, **data.model_dump(exclude={"course_id"}))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, *, task: Task, data: TaskUpdate) -> Task:
    patch = data.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(task, k, v)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

