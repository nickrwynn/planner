from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ResourceLifecycleEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resource_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("resource_id", "seq", name="uq_resource_lifecycle_events_resource_seq"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    resource = relationship("Resource", back_populates="lifecycle_events")

    @property
    def is_warning(self) -> bool:
        return self.event_type == "embedding.warning"
