from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.user import User
from app.schemas.course import CourseCreate, CourseUpdate
from app.services import tasks as task_service


def list_courses(db: Session, *, user: User) -> list[Course]:
    return db.execute(select(Course).where(Course.user_id == user.id).order_by(Course.created_at.desc())).scalars().all()


def get_course(db: Session, *, user: User, course_id: UUID) -> Course | None:
    return (
        db.execute(select(Course).where(Course.user_id == user.id, Course.id == course_id))
        .scalars()
        .first()
    )


def create_course(db: Session, *, user: User, data: CourseCreate) -> Course:
    course = Course(user_id=user.id, **data.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def update_course(db: Session, *, course: Course, data: CourseUpdate) -> Course:
    patch = data.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(course, k, v)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def grade_summary(db: Session, *, user: User, course: Course) -> tuple[float, int, int]:
    tasks = task_service.list_tasks(db, user=user, course_id=course.id, limit=500, offset=0)
    total = len(tasks)
    if total == 0:
        return 0.0, 0, 0
    weighted_total = 0.0
    weighted_done = 0.0
    done = 0
    for t in tasks:
        w = float(t.weight) if t.weight is not None else 1.0
        weighted_total += w
        if (t.status or "").lower() == "done":
            done += 1
            weighted_done += w
    pct = (weighted_done / weighted_total) * 100.0 if weighted_total > 0 else 0.0
    return pct, done, total

