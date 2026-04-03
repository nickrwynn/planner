from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class NotePage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "note_pages"
    __table_args__ = (
        UniqueConstraint("note_document_id", "page_index", name="uq_note_pages_document_page_index"),
        CheckConstraint("page_index >= 0", name="ck_note_pages_page_index_nonnegative"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    note_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("note_documents.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resources.id", ondelete="SET NULL"), index=True, nullable=True
    )
    page_index: Mapped[int] = mapped_column(nullable=False)
    page_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(String, nullable=True)

    note_document = relationship("NoteDocument", back_populates="pages")
    resource = relationship("Resource")

