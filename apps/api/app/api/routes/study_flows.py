from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.models.study_flow import StudyFlowRun
from app.schemas.study_flow import (
    StudyFlowAdvanceRequest,
    StudyFlowAttachResourceRequest,
    StudyFlowEnsureRequest,
    StudyFlowInProgressItem,
    StudyFlowRead,
    StudyFlowRunRead,
    StudyFlowSaveNoteRequest,
    StudyFlowSaveNoteResponse,
    StudyFlowScoreRead,
    StudyFlowScoreRequest,
)
from app.services import courses as course_service
from app.services import resources as resource_service
from app.services import study_flows as study_flow_service
from app.services.studyflow_notes import append_studyflow_note

router = APIRouter(prefix="/study-flows", tags=["study-flows"])


@router.get("/in-progress", response_model=list[StudyFlowInProgressItem])
def list_in_progress_study_flows(
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    return study_flow_service.list_in_progress(db, user=user)


@router.post("/ensure", response_model=StudyFlowRead)
def ensure_study_flow(
    payload: StudyFlowEnsureRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    course = course_service.get_course(db, user=user, course_id=payload.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return study_flow_service.ensure_flow(db, user=user, course=course, data=payload)


@router.get("/by-course/{course_id}", response_model=StudyFlowRead)
def get_study_flow_for_course(
    course_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    course = course_service.get_course(db, user=user, course_id=course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return study_flow_service.ensure_flow(
        db,
        user=user,
        course=course,
        data=StudyFlowEnsureRequest(course_id=course_id),
    )


@router.post("/runs/{run_id}/attach-resource", response_model=StudyFlowRunRead)
def attach_resource(
    run_id: UUID,
    payload: StudyFlowAttachResourceRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        return study_flow_service.attach_resource(
            db, user=user, run_id=run_id, resource_id=payload.resource_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/advance", response_model=StudyFlowRunRead)
def advance_step(
    run_id: UUID,
    payload: StudyFlowAdvanceRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        return study_flow_service.advance_step(db, user=user, run_id=run_id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/score", response_model=StudyFlowScoreRead)
def score_attempt(
    payload: StudyFlowScoreRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    _ = db, user
    return study_flow_service.score_summary(
        source_text=payload.source_text, student_text=payload.student_text
    )


@router.post("/runs/{run_id}/save-note", response_model=StudyFlowSaveNoteResponse)
def save_note(
    run_id: UUID,
    payload: StudyFlowSaveNoteRequest,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    run = (
        db.execute(select(StudyFlowRun).where(StudyFlowRun.id == run_id, StudyFlowRun.user_id == user.id))
        .scalars()
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="StudyFlow run not found")
    if not run.resource_id:
        raise HTTPException(status_code=400, detail="Attach a resource before saving notes")
    resource = resource_service.get_resource_for_user(db, user=user, resource_id=run.resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        result = append_studyflow_note(
            db,
            user=user,
            resource=resource,
            highlight=payload.highlight,
            student_text=payload.student_text,
            step_key=payload.step_key,
            kind=payload.kind,
            latex=payload.latex,
            page_number=payload.page_number,
            section_hint=payload.section_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid opaque browser "Failed to fetch" when the worker dumps an unhandled DB error.
        raise HTTPException(status_code=500, detail=f"Could not save note: {exc}") from exc
    return StudyFlowSaveNoteResponse(**result)
