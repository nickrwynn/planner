from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo','in_progress','done')", name="ck_tasks_status"),
        CheckConstraint(
            "(task_type IS NULL) OR (task_type IN ('assignment','exam','reading','project','other'))",
            name="ck_tasks_task_type",
        ),
        CheckConstraint("(weight IS NULL) OR (weight >= 0)", name="ck_tasks_weight_nonnegative"),
        CheckConstraint(
            "(estimated_minutes IS NULL) OR (estimated_minutes >= 0)",
            name="ck_tasks_estimated_minutes_nonnegative",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    weight: Mapped[float | None] = mapped_column(nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="todo")
    estimated_minutes: Mapped[int | None] = mapped_column(nullable=True)
    priority_score: Mapped[float | None] = mapped_column(nullable=True)

    user = relationship("User")
    course = relationship("Course", back_populates="tasks")

