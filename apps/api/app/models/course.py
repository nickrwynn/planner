from __future__ import annotations

from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Course(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "courses"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    term: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    grading_schema_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user = relationship("User", back_populates="courses")
    tasks = relationship("Task", back_populates="course", cascade="all,delete-orphan")
    resources = relationship("Resource", back_populates="course", cascade="all,delete-orphan")
    notebooks = relationship("Notebook", back_populates="course", cascade="all,delete-orphan")

