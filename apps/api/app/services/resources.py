from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.resource import Resource
from app.models.user import User
from app.schemas.resource import ResourceCreate, ResourceUpdate


def list_resources(
    db: Session,
    *,
    user: User,
    course_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Resource]:
    q = select(Resource).where(Resource.user_id == user.id).order_by(Resource.created_at.desc())
    if course_id is not None:
        q = q.where(Resource.course_id == course_id)
    q = q.limit(limit).offset(offset)
    return db.execute(q).scalars().all()


def get_resource(db: Session, *, resource_id: UUID) -> Resource | None:
    return db.get(Resource, resource_id)


def get_resource_for_user(db: Session, *, user: User, resource_id: UUID) -> Resource | None:
    return (
        db.execute(
            select(Resource).where(
                Resource.id == resource_id,
                Resource.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )


def create_resource(db: Session, *, user: User, data: ResourceCreate) -> Resource:
    resource = Resource(user_id=user.id, **data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def update_resource(db: Session, *, resource: Resource, data: ResourceUpdate) -> Resource:
    patch = data.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(resource, k, v)
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource

