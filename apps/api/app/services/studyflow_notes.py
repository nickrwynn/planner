from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.note_page import NotePage
from app.models.resource import Resource
from app.models.user import User
from app.schemas.notebook import NotebookCreate
from app.services import notebooks as notebook_service
from app.services import notes as notes_service
from app.services.section_notebooks import (
    ensure_section_notebook,
    extract_section_key,
    extract_section_key_from_text,
)


def append_studyflow_note(
    db: Session,
    *,
    user: User,
    resource: Resource,
    highlight: str,
    student_text: str,
    step_key: str,
    kind: str = "comment",
    latex: str | None = None,
    page_number: int | None = None,
    section_hint: str | None = None,
) -> dict:
    """
    Append a StudyFlows highlight + student note into a course notebook page.

    Prefers a Section X.Y notebook when the resource title, highlight, or explicit
    section hint looks like a section reading; otherwise uses/creates a
    "StudyFlows notes" notebook + per-resource document.
    """
    if not resource.course_id:
        raise ValueError("Resource must belong to a course")

    course_id = resource.course_id
    section = (
        extract_section_key(section_hint)
        or extract_section_key(resource.title)
        or extract_section_key_from_text(highlight, student_text)
        or extract_section_key_from_text(section_hint)
    )
    section_nb, _created = ensure_section_notebook(
        db,
        user=user,
        course_id=course_id,
        title=resource.title,
        section_key=section,
    )
    if section_nb is not None:
        notebook = section_nb
        doc_title = "StudyFlows annotations"
    else:
        notebooks = notebook_service.list_notebooks(db, user=user, course_id=course_id)
        notebook = next((n for n in notebooks if n.title.lower() == "studyflows notes"), None)
        if notebook is None:
            notebook = notebook_service.create_notebook(
                db,
                user=user,
                data=NotebookCreate(course_id=course_id, title="StudyFlows notes", parent_id=None),
            )
        doc_title = f"StudyFlows: {resource.title}"[:200]

    docs = notes_service.list_note_documents(db, user=user, notebook_id=notebook.id)
    doc = next((d for d in docs if d.title == doc_title), None)
    if doc is None:
        # note_documents.note_type check allows only typed|handwritten|mixed|NULL
        doc_note_type = "handwritten" if kind == "ink" else "mixed"
        doc = notes_service.create_note_document(
            db,
            user=user,
            notebook_id=notebook.id,
            title=doc_title,
            note_type=doc_note_type,
        )

    current_max = db.scalar(
        select(func.max(NotePage.page_index)).where(
            NotePage.note_document_id == doc.id,
            NotePage.user_id == user.id,
        )
    )
    page_index = int(current_max if current_max is not None else -1) + 1

    ts = datetime.now(timezone.utc).isoformat()
    section_label = section or "general"
    page_label = f" · PDF p{page_number}" if page_number else ""
    body_parts = [
        f"## StudyFlows · {kind} · {step_key}",
        f"_Saved {ts}_ · section `{section_label}`{page_label} · resource `{resource.title}`",
        "",
        "### Highlight",
        f"> {highlight.strip()}" if highlight.strip() else "_(no highlight)_",
        "",
        "### Note",
        student_text.strip() or "_(empty)_",
    ]
    if latex and latex.strip():
        body_parts.extend(["", "### LaTeX", f"$$\n{latex.strip()}\n$$"])
    text = "\n".join(body_parts)

    page = notes_service.create_note_page(
        db, user=user, doc_id=doc.id, page_index=page_index, text=text
    )
    return {
        "notebook_id": str(notebook.id),
        "note_document_id": str(doc.id),
        "note_page_id": str(page.id),
        "page_index": page.page_index,
        "notebook_title": notebook.title,
        "document_title": doc.title,
    }
