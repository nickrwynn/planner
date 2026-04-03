from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.schemas.course import CourseCreate, CourseGradeSummary, CourseRead, CourseUpdate
from app.services import courses as course_service

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseRead])
def list_courses(db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    return course_service.list_courses(db, user=user)


@router.post("", response_model=CourseRead)
def create_course(payload: CourseCreate, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    return course_service.create_course(db, user=user, data=payload)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course_service.update_course(db, course=course, data=payload)


@router.delete("/{course_id}")
def delete_course(course_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    db.delete(course)
    db.commit()
    return {"ok": True}


@router.get("/{course_id}/grade-summary", response_model=CourseGradeSummary)
def course_grade_summary(course_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    pct, done, total = course_service.grade_summary(db, user=user, course=course)
    return CourseGradeSummary(course_id=course.id, weighted_completion_pct=round(pct, 2), done_tasks=done, total_tasks=total)

