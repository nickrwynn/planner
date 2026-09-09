from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.user import User
from app.schemas.notebook import NotebookCreate
from app.services import notebooks as notebook_service
_SECTION_RE = re.compile(
    r"(?:(?:section|sec\.?|reading|ch(?:apter)?\.?)\s*)?(\d+\.\d+)\b",
    re.IGNORECASE,
)
# Prefer numbered section headings like "1.2 Random sampling" near line starts.
_HEADING_SECTION_RE = re.compile(
    r"(?m)^\s*(?:section|sec\.?|reading|ch(?:apter)?\.?)?\s*(\d+\.\d+)\s+[A-Za-z]",
    re.IGNORECASE,
)


def extract_section_key(title: str | None) -> str | None:
    if not title:
        return None
    m = _SECTION_RE.search(title.strip())
    if not m:
        return None
    return m.group(1)


def extract_section_key_from_text(*texts: str | None) -> str | None:
    """Find a section number from highlight / page body (not PDF filename)."""
    for text in texts:
        if not text or not text.strip():
            continue
        # Prefer heading-like matches first.
        m = _HEADING_SECTION_RE.search(text)
        if m:
            return m.group(1)
        m = _SECTION_RE.search(text)
        if m:
            return m.group(1)
    return None


def ensure_section_notebook(
    db: Session,
    *,
    user: User,
    course_id: UUID,
    title: str | None,
    section_key: str | None = None,
) -> tuple[Notebook | None, bool]:
    """If title/section looks like a section reading (e.g. 1.1), ensure a matching course notebook.

    Returns (notebook, created).
    """
    section = section_key or extract_section_key(title)
    if not section:
        return None, False

    desired = f"Section {section}"
    existing = notebook_service.list_notebooks(db, user=user, course_id=course_id)
    for nb in existing:
        key = extract_section_key(nb.title)
        if key == section or nb.title.strip().lower() in {desired.lower(), section.lower()}:
            return nb, False

    nb = notebook_service.create_notebook(
        db,
        user=user,
        data=NotebookCreate(course_id=course_id, title=desired, parent_id=None),
    )
    return nb, True
