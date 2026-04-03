from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.models._mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AIConversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        CheckConstraint("(mode IS NULL) OR (mode IN ('ask','study'))", name="ck_ai_conversations_mode"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(30), nullable=True)

    messages = relationship("AIMessage", back_populates="conversation", cascade="all,delete-orphan")

