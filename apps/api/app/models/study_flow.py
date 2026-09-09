from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class StudyFlow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "study_flows"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "template_key", name="uq_study_flows_user_course_template"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False, default="default_retrieval")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    runs = relationship("StudyFlowRun", back_populates="flow", cascade="all,delete-orphan")


class StudyFlowRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "study_flow_runs"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    flow_id: Mapped[UUID] = mapped_column(ForeignKey("study_flows.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[UUID | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    current_step_key: Mapped[str] = mapped_column(String(50), nullable=False, default="read")
    progress_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flow = relationship("StudyFlow", back_populates="runs")
    steps = relationship("StudyFlowStep", back_populates="run", cascade="all,delete-orphan")


class StudyFlowStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "study_flow_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_key", name="uq_study_flow_steps_run_key"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("study_flow_runs.id", ondelete="CASCADE"), index=True)
    step_key: Mapped[str] = mapped_column(String(50), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run = relationship("StudyFlowRun", back_populates="steps")
