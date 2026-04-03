from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.indexing.chunk_embeddings import embed_resource_chunks_if_configured
from app.indexing.chunking import chunk_text
from app.models.course import Course
from app.models.notebook import Notebook
from app.models.note_document import NoteDocument
from app.models.note_page import NotePage
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.models.user import User


def _ensure_notebook_owned(db: Session, *, user: User, notebook_id: UUID) -> Notebook | None:
    # Ownership is via notebooks.user_id (course_id is optional).
    nb = db.get(Notebook, notebook_id)
    if not nb:
        return None
    if nb.user_id != user.id:
        return None
    # If course_id is set, ensure it is still owned by the user (defense-in-depth).
    if nb.course_id:
        owned = (
            db.execute(select(Course).where(Course.id == nb.course_id, Course.user_id == user.id))
            .scalars()
            .first()
        )
        if not owned:
            return None
    return nb


def create_note_document(db: Session, *, user: User, notebook_id: UUID, title: str, note_type: str | None) -> NoteDocument:
    nb = _ensure_notebook_owned(db, user=user, notebook_id=notebook_id)
    if not nb:
        raise ValueError("Notebook not found")
    doc = NoteDocument(
        user_id=user.id,
        notebook_id=notebook_id,
        title=title,
        note_type=note_type,
        metadata_json=None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def update_note_document(
    db: Session, *, user: User, doc_id: UUID, title: str | None, note_type: str | None
) -> NoteDocument | None:
    doc = get_note_document(db, user=user, doc_id=doc_id)
    if not doc:
        return None
    if title is not None:
        doc.title = title
    if note_type is not None:
        doc.note_type = note_type
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_note_documents(db: Session, *, user: User, notebook_id: UUID) -> list[NoteDocument]:
    nb = _ensure_notebook_owned(db, user=user, notebook_id=notebook_id)
    if not nb:
        return []
    return (
        db.execute(
            select(NoteDocument).where(
                NoteDocument.notebook_id == notebook_id,
                NoteDocument.user_id == user.id,
            )
        )
        .scalars()
        .all()
    )


def get_note_document(db: Session, *, user: User, doc_id: UUID) -> NoteDocument | None:
    doc = db.get(NoteDocument, doc_id)
    if not doc:
        return None
    if doc.user_id != user.id:
        return None
    nb = _ensure_notebook_owned(db, user=user, notebook_id=doc.notebook_id)
    return doc if nb else None


def create_note_page(db: Session, *, user: User, doc_id: UUID, page_index: int, text: str) -> NotePage:
    doc = get_note_document(db, user=user, doc_id=doc_id)
    if not doc:
        raise ValueError("Note document not found")

    # Create a Resource row to unify indexing/search/agent.
    nb = db.get(Notebook, doc.notebook_id)
    course_id = nb.course_id if nb else None
    res = Resource(
        user_id=user.id,
        course_id=course_id,
        title=f"Note: {doc.title} (p{page_index + 1})",
        resource_type="note_page",
        original_filename=None,
        mime_type="text/plain",
        storage_path=None,
        parse_status="parsed",
        ocr_status="skipped",
        index_status="done",
        lifecycle_state="searchable",
    )
    db.add(res)
    db.commit()
    db.refresh(res)

    page_data = {
        "version": 1,
        "elements": [{"id": "text1", "type": "text", "content": text}],
    }
    page = NotePage(
        user_id=user.id,
        note_document_id=doc.id,
        resource_id=res.id,
        page_index=page_index,
        page_data_json=page_data,
        extracted_text=text,
    )
    db.add(page)
    db.commit()
    db.refresh(page)

    # Index into ResourceChunks (synchronously for MVP)
    db.execute(delete(ResourceChunk).where(ResourceChunk.resource_id == res.id, ResourceChunk.user_id == user.id))
    chunks: list[ResourceChunk] = []
    for ch in chunk_text(text=text, page_number=None):
        chunks.append(
            ResourceChunk(
                user_id=user.id,
                resource_id=res.id,
                chunk_index=ch.chunk_index,
                page_number=None,
                text=ch.text,
            )
        )
    embed_err = embed_resource_chunks_if_configured(chunks)
    if embed_err:
        meta = dict(res.metadata_json or {})
        meta["embedding_error"] = embed_err
        res.metadata_json = meta
        db.add(res)
    db.add_all(chunks)
    db.commit()

    return page


def list_note_pages(db: Session, *, user: User, doc_id: UUID) -> list[NotePage]:
    doc = get_note_document(db, user=user, doc_id=doc_id)
    if not doc:
        return []
    return (
        db.execute(
            select(NotePage)
            .where(
                NotePage.note_document_id == doc_id,
                NotePage.user_id == user.id,
            )
            .order_by(NotePage.page_index.asc())
        )
        .scalars()
        .all()
    )


def update_note_page(
    db: Session,
    *,
    user: User,
    page_id: UUID,
    text: str | None,
    page_data_json: dict | None,
) -> NotePage | None:
    page = db.get(NotePage, page_id)
    if not page:
        return None
    if page.user_id != user.id:
        return None
    doc = get_note_document(db, user=user, doc_id=page.note_document_id)
    if not doc:
        return None

    if page_data_json is not None:
        page.page_data_json = page_data_json
    if text is not None:
        page.extracted_text = text
        # Update the canonical text element if present
        if isinstance(page.page_data_json, dict):
            elements = page.page_data_json.get("elements")
            if isinstance(elements, list) and elements:
                if isinstance(elements[0], dict) and elements[0].get("type") == "text":
                    elements[0]["content"] = text

    db.add(page)
    db.commit()
    db.refresh(page)

    # Re-index linked resource chunks
    if page.resource_id and page.extracted_text is not None:
        db.execute(
            delete(ResourceChunk).where(
                ResourceChunk.resource_id == page.resource_id,
                ResourceChunk.user_id == user.id,
            )
        )
        chunks: list[ResourceChunk] = []
        for ch in chunk_text(text=page.extracted_text, page_number=None):
            chunks.append(
                ResourceChunk(
                    user_id=user.id,
                    resource_id=page.resource_id,
                    chunk_index=ch.chunk_index,
                    page_number=None,
                    text=ch.text,
                )
            )
        embed_err = embed_resource_chunks_if_configured(chunks)
        if embed_err:
            r = db.get(Resource, page.resource_id)
            if r:
                meta = dict(r.metadata_json or {})
                meta["embedding_error"] = embed_err
                r.metadata_json = meta
                db.add(r)
        db.add_all(chunks)
        db.commit()

    return page


def get_note_page(db: Session, *, user: User, page_id: UUID) -> NotePage | None:
    page = db.get(NotePage, page_id)
    if not page:
        return None
    if page.user_id != user.id:
        return None
    return page

