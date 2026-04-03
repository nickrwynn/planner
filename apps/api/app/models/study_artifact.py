from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class StudyArtifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "study_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('summary','flashcards','quiz','sample_problems')",
            name="ck_study_artifacts_artifact_type",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_resource_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user = relationship("User")

