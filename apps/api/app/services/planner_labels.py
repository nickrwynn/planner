from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planner_label import PlannerLabel
from app.models.user import User


def list_labels(db: Session, *, user: User) -> list[PlannerLabel]:
    return list(
        db.execute(
            select(PlannerLabel).where(PlannerLabel.user_id == user.id).order_by(PlannerLabel.name.asc())
        )
        .scalars()
        .all()
    )


def get_label_for_user(db: Session, *, user: User, label_id: UUID) -> PlannerLabel | None:
    return (
        db.execute(
            select(PlannerLabel).where(PlannerLabel.id == label_id, PlannerLabel.user_id == user.id)
        )
        .scalars()
        .first()
    )


def create_label(db: Session, *, user: User, name: str) -> PlannerLabel:
    cleaned = " ".join(name.split()).strip()
    existing = (
        db.execute(
            select(PlannerLabel).where(
                PlannerLabel.user_id == user.id,
                PlannerLabel.name == cleaned,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return existing
    label = PlannerLabel(user_id=user.id, name=cleaned)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


def delete_label(db: Session, *, label: PlannerLabel) -> None:
    db.delete(label)
    db.commit()
