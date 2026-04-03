from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.models.note_document import NoteDocument
from app.models.note_page import NotePage
from app.models.resource import Resource
from app.schemas.notebook import NotebookCreate, NotebookRead, NotebookUpdate
from app.services import courses as course_service
from app.services import notebooks as notebook_service

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


@router.get("", response_model=list[NotebookRead])
def list_notebooks(
    course_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    if course_id is not None:
        course = course_service.get_course(db, user=user, course_id=course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return notebook_service.list_notebooks(db, user=user, course_id=course_id)


@router.post("", response_model=NotebookRead)
def create_notebook(payload: NotebookCreate, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    if payload.course_id is not None:
        course = course_service.get_course(db, user=user, course_id=payload.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    try:
        return notebook_service.create_notebook(db, user=user, data=payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{notebook_id}", response_model=NotebookRead)
def get_notebook(notebook_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    notebook = notebook_service.get_notebook_for_user(db, user=user, notebook_id=notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if notebook.course_id is not None:
        course = course_service.get_course(db, user=user, course_id=notebook.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    return notebook


@router.patch("/{notebook_id}", response_model=NotebookRead)
def update_notebook(
    notebook_id: UUID,
    payload: NotebookUpdate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    notebook = notebook_service.get_notebook_for_user(db, user=user, notebook_id=notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    target_course_id = payload.course_id if payload.course_id is not None else notebook.course_id
    if target_course_id is not None:
        course = course_service.get_course(db, user=user, course_id=target_course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
    try:
        return notebook_service.update_notebook(db, notebook=notebook, data=payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/{notebook_id}")
def delete_notebook(notebook_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    notebook = notebook_service.get_notebook_for_user(db, user=user, notebook_id=notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Best-effort: delete resources created for note pages in this notebook.
    doc_ids = select(NoteDocument.id).where(NoteDocument.notebook_id == notebook_id)
    page_resource_ids = (
        db.execute(select(NotePage.resource_id).where(NotePage.note_document_id.in_(doc_ids)))
        .scalars()
        .all()
    )
    for rid in [r for r in page_resource_ids if r is not None]:
        res = db.get(Resource, rid)
        if res and res.user_id == user.id:
            db.delete(res)

    db.delete(notebook)
    db.commit()
    return {"ok": True}

