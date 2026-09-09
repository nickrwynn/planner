from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.note_page import NotePage
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.models.user import User
from app.schemas.notebook import NotebookCreate
from app.services import notebooks as notebook_service
from app.services import notes as notes_service


def send_resource_to_notes(
    db: Session,
    *,
    user: User,
    resource: Resource,
    max_pages: int = 40,
) -> dict:
    """Ensure a course notebook + note document, then create pages from resource chunks."""
    if not resource.course_id:
        raise ValueError("Resource must belong to a course")

    notebooks = notebook_service.list_notebooks(db, user=user, course_id=resource.course_id)
    notebook = next((n for n in notebooks if n.title.lower().startswith("course notes")), None)
    if notebook is None and notebooks:
        notebook = notebooks[0]
    if notebook is None:
        notebook = notebook_service.create_notebook(
            db,
            user=user,
            data=NotebookCreate(course_id=resource.course_id, title="Course notes", parent_id=None),
        )

    docs = notes_service.list_note_documents(db, user=user, notebook_id=notebook.id)
    title = f"From: {resource.title}"
    doc = next((d for d in docs if d.title == title), None)
    if doc is None:
        doc = notes_service.create_note_document(
            db, user=user, notebook_id=notebook.id, title=title, note_type="typed"
        )

    chunks = (
        db.execute(
            select(ResourceChunk)
            .where(
                ResourceChunk.resource_id == resource.id,
                ResourceChunk.user_id == user.id,
            )
            .order_by(ResourceChunk.chunk_index.asc())
            .limit(max_pages)
        )
        .scalars()
        .all()
    )
    if not chunks:
        raise ValueError("Resource has no indexed text yet. Wait for indexing to finish.")

    # Replace existing pages for this document when re-sending.
    existing_pages = notes_service.list_note_pages(db, user=user, doc_id=doc.id)
    for page in existing_pages:
        db.delete(page)
    db.commit()

    created: list[NotePage] = []
    for idx, chunk in enumerate(chunks):
        page = notes_service.create_note_page(
            db, user=user, doc_id=doc.id, page_index=idx, text=chunk.text
        )
        # Prefer linking original resource for provenance.
        page.resource_id = resource.id
        page.page_data_json = {
            "source_resource_id": str(resource.id),
            "source_chunk_id": str(chunk.id),
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
        }
        db.add(page)
        created.append(page)
    db.commit()

    return {
        "notebook_id": str(notebook.id),
        "note_document_id": str(doc.id),
        "pages_created": len(created),
        "resource_id": str(resource.id),
    }
