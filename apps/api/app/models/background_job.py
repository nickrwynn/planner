from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BackgroundJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','failed')",
            name="ck_background_jobs_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_background_jobs_attempts_non_negative",
        ),
        CheckConstraint(
            "(status != 'running') OR "
            "(claim_token IS NOT NULL AND claimed_by IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_background_jobs_running_claim_fields_present",
        ),
        CheckConstraint(
            "(status = 'running') OR "
            "(claim_token IS NULL AND claimed_by IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL)",
            name="ck_background_jobs_non_running_claim_fields_cleared",
        ),
        UniqueConstraint(
            "user_id",
            "resource_id",
            "job_type",
            "idempotency_key",
            name="uq_background_jobs_idempotency_scope",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    @property
    def lease_recovery_detected(self) -> bool:
        """True when the last transition indicates a lease-expiration requeue recovery."""
        err = (self.last_error or "").lower()
        return "lease expired while running" in err and "re-queued for crash recovery" in err
