from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ResourceChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resource_chunks"
    __table_args__ = (
        UniqueConstraint("resource_id", "chunk_index", name="uq_resource_chunks_resource_id_chunk_index"),
        CheckConstraint("chunk_index >= 0", name="ck_resource_chunks_chunk_index_nonnegative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Phase 3+ (optional) fields
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

