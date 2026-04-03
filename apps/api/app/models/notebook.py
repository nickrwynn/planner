from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Notebook(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notebooks"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("notebooks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    user = relationship("User")
    course = relationship("Course", back_populates="notebooks")
    note_documents = relationship("NoteDocument", back_populates="notebook", cascade="all,delete-orphan")
    parent = relationship("Notebook", remote_side="Notebook.id", backref="children")

