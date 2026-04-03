from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DeadLetterJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "dead_letter_jobs"
    __table_args__ = (
        UniqueConstraint("background_job_id", name="uq_dead_letter_jobs_background_job_id"),
        CheckConstraint("attempts >= 0", name="ck_dead_letter_jobs_attempts_non_negative"),
        CheckConstraint(
            "(background_job_id IS NULL) OR (replay_key IS NOT NULL)",
            name="ck_dead_letter_jobs_replay_key_for_linked_job",
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("resources.id", ondelete="SET NULL"), index=True, nullable=True
    )
    background_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    replay_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
