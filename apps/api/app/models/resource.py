from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin

RESOURCE_PARSE_ERROR_CODES = (
    "missing_storage_path",
    "no_text_extracted",
    "pdf_parse_error",
    "ocr_environment_error",
    "ocr_parse_error",
    "storage_read_error",
    "unsupported_media_error",
    "indexing_error",
)

RESOURCE_INDEX_ERROR_CODES = (
    "missing_storage_path",
    "no_text_extracted",
    "pdf_parse_error",
    "ocr_environment_error",
    "ocr_parse_error",
    "storage_read_error",
    "unsupported_media_error",
    "embedding_error",
    "indexing_error",
)


class Resource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('uploaded','parsing','parsed','skipped','failed')",
            name="ck_resources_parse_status",
        ),
        CheckConstraint(
            "ocr_status IN ('pending','running','done','skipped','failed')",
            name="ck_resources_ocr_status",
        ),
        CheckConstraint(
            "index_status IN ('pending','queued','done','skipped','failed')",
            name="ck_resources_index_status",
        ),
        CheckConstraint(
            "lifecycle_state IN ('uploaded','queued','parsing','parsed','chunked','indexed','searchable','skipped','failed')",
            name="ck_resources_lifecycle_state",
        ),
        CheckConstraint(
            "parse_error_code IS NULL OR parse_error_code IN "
            "('missing_storage_path','no_text_extracted','pdf_parse_error','ocr_environment_error','ocr_parse_error',"
            "'storage_read_error','unsupported_media_error','indexing_error')",
            name="ck_resources_parse_error_code",
        ),
        CheckConstraint(
            "index_error_code IS NULL OR index_error_code IN "
            "('missing_storage_path','no_text_extracted','pdf_parse_error','ocr_environment_error','ocr_parse_error',"
            "'storage_read_error','unsupported_media_error','embedding_error','indexing_error')",
            name="ck_resources_index_error_code",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True, nullable=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    ocr_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    index_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    lifecycle_state: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parse_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    index_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    parse_pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    chunking_version: Mapped[str] = mapped_column(String(32), nullable=False, default="char-v1")
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_lifecycle_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    course = relationship("Course", back_populates="resources")
    lifecycle_events = relationship(
        "ResourceLifecycleEvent",
        back_populates="resource",
        cascade="all, delete-orphan",
    )

    @property
    def diagnostics_trace_ready(self) -> bool:
        meta = self.metadata_json or {}
        return bool(meta.get("latest_index_run_id"))

