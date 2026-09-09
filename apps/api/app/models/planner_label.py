from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PlannerLabel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User-defined planner types/contexts (e.g. Gym, Personal, Club)."""

    __tablename__ = "planner_labels"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_planner_labels_user_name"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    user = relationship("User")
