from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.models.note_document import NoteDocument
from app.models.resource import Resource
from app.schemas.notes import (
    NoteDocumentCreate,
    NoteDocumentRead,
    NoteDocumentUpdate,
    NotePageCreate,
    NotePageRead,
    NotePageUpdate,
)
from app.services import notes as notes_service

router = APIRouter(tags=["notes"])


@router.get("/notebooks/{notebook_id}/note-documents", response_model=list[NoteDocumentRead])
def list_documents(
    notebook_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    return notes_service.list_note_documents(db, user=user, notebook_id=notebook_id)


@router.post("/note-documents", response_model=NoteDocumentRead)
def create_document(
    payload: NoteDocumentCreate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        return notes_service.create_note_document(
            db, user=user, notebook_id=payload.notebook_id, title=payload.title, note_type=payload.note_type
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/note-documents/{doc_id}", response_model=NoteDocumentRead)
def get_document(
    doc_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    doc = notes_service.get_note_document(db, user=user, doc_id=doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Note document not found")
    return doc


@router.patch("/note-documents/{doc_id}", response_model=NoteDocumentRead)
def update_document(
    doc_id: UUID,
    payload: NoteDocumentUpdate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    doc = notes_service.update_note_document(db, user=user, doc_id=doc_id, title=payload.title, note_type=payload.note_type)
    if not doc:
        raise HTTPException(status_code=404, detail="Note document not found")
    return doc


@router.get("/note-documents/{doc_id}/pages", response_model=list[NotePageRead])
def list_pages(
    doc_id: UUID,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    return notes_service.list_note_pages(db, user=user, doc_id=doc_id)


@router.post("/note-pages", response_model=NotePageRead)
def create_page(
    payload: NotePageCreate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    try:
        return notes_service.create_note_page(
            db, user=user, doc_id=payload.note_document_id, page_index=payload.page_index, text=payload.text
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/note-pages/{page_id}", response_model=NotePageRead)
def update_page(
    page_id: UUID,
    payload: NotePageUpdate,
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    page = notes_service.update_note_page(
        db, user=user, page_id=page_id, text=payload.text, page_data_json=payload.page_data_json
    )
    if not page:
        raise HTTPException(status_code=404, detail="Note page not found")
    return page


@router.get("/note-pages/{page_id}", response_model=NotePageRead)
def get_page(page_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    page = notes_service.get_note_page(db, user=user, page_id=page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Note page not found")
    doc = notes_service.get_note_document(db, user=user, doc_id=page.note_document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Note page not found")
    return page


@router.delete("/note-pages/{page_id}")
def delete_page(page_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    page = notes_service.get_note_page(db, user=user, page_id=page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Note page not found")
    doc = notes_service.get_note_document(db, user=user, doc_id=page.note_document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Note page not found")

    # Delete linked resource (chunks cascade)
    if page.resource_id:
        res = db.get(Resource, page.resource_id)
        if res and res.user_id == user.id:
            db.delete(res)

    db.delete(page)
    db.commit()
    return {"ok": True}


@router.delete("/note-documents/{doc_id}")
def delete_document(doc_id: UUID, db: Session = Depends(get_db_from_request), user=Depends(get_current_user)):
    doc = notes_service.get_note_document(db, user=user, doc_id=doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Note document not found")

    pages = notes_service.list_note_pages(db, user=user, doc_id=doc_id)
    for p in pages:
        if p.resource_id:
            res = db.get(Resource, p.resource_id)
            if res and res.user_id == user.id:
                db.delete(res)
        db.delete(p)

    db.delete(doc)
    db.commit()
    return {"ok": True}

