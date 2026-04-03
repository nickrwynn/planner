from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class NoteDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "note_documents"
    __table_args__ = (
        CheckConstraint(
            "(note_type IS NULL) OR (note_type IN ('typed','handwritten','mixed'))",
            name="ck_note_documents_note_type",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    notebook_id: Mapped[UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    note_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    notebook = relationship("Notebook", back_populates="note_documents")
    pages = relationship("NotePage", back_populates="note_document", cascade="all,delete-orphan")

