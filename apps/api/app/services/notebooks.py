from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.notebook import Notebook
from app.models.user import User
from app.schemas.notebook import NotebookCreate, NotebookUpdate


def list_notebooks(db: Session, *, user: User, course_id: UUID | None = None) -> list[Notebook]:
    q = select(Notebook).where(Notebook.user_id == user.id).order_by(Notebook.created_at.desc())
    if course_id is not None:
        q = q.where(Notebook.course_id == course_id)
    return db.execute(q).scalars().all()


def get_notebook(db: Session, *, notebook_id: UUID) -> Notebook | None:
    return db.get(Notebook, notebook_id)


def get_notebook_for_user(db: Session, *, user: User, notebook_id: UUID) -> Notebook | None:
    return (
        db.execute(
            select(Notebook).where(
                Notebook.id == notebook_id,
                Notebook.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )


def create_notebook(db: Session, *, user: User, data: NotebookCreate) -> Notebook:
    if data.parent_id:
        parent = db.get(Notebook, data.parent_id)
        if not parent or parent.user_id != user.id:
            raise ValueError("Parent notebook not found")
    notebook = Notebook(user_id=user.id, **data.model_dump())
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook


def update_notebook(db: Session, *, notebook: Notebook, data: NotebookUpdate) -> Notebook:
    patch = data.model_dump(exclude_unset=True)
    if "parent_id" in patch and patch["parent_id"] is not None:
        parent = db.get(Notebook, patch["parent_id"])
        if not parent or parent.user_id != notebook.user_id:
            raise ValueError("Parent notebook not found")
        if parent.id == notebook.id:
            raise ValueError("Notebook cannot be its own parent")
    for k, v in patch.items():
        setattr(notebook, k, v)
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook

