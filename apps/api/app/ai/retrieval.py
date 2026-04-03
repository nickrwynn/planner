from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indexing.embeddings import get_embeddings_provider
from app.search.hybrid import select_chunks_hybrid
from app.models.course import Course
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    resource_id: UUID
    chunk_index: int
    page_number: int | None
    text: str


def retrieve_chunks(
    db: Session,
    *,
    user_id: UUID,
    query: str,
    course_id: UUID | None = None,
    resource_ids: list[UUID] | None = None,
    k: int = 8,
) -> list[RetrievedChunk]:
    owned_resource_ids = select(Resource.id).where(
        Resource.user_id == user_id,
        Resource.index_status == "done",
        Resource.lifecycle_state == "searchable",
    )
    stmt = select(ResourceChunk).where(
        ResourceChunk.user_id == user_id,
        ResourceChunk.resource_id.in_(owned_resource_ids),
    )

    if course_id is not None:
        owned_course = (
            db.execute(select(Course.id).where(Course.id == course_id, Course.user_id == user_id))
            .scalars()
            .first()
        )
        if not owned_course:
            return []
        stmt = stmt.where(
            ResourceChunk.resource_id.in_(
                select(Resource.id).where(
                    Resource.user_id == user_id,
                    Resource.course_id == course_id,
                    Resource.index_status == "done",
                    Resource.lifecycle_state == "searchable",
                )
            )
        )

    if resource_ids:
        stmt = stmt.where(
            ResourceChunk.resource_id.in_(
                select(Resource.id).where(
                    Resource.user_id == user_id,
                    Resource.id.in_(resource_ids),
                    Resource.index_status == "done",
                    Resource.lifecycle_state == "searchable",
                )
            )
        )

    embedder = get_embeddings_provider()
    ranked = select_chunks_hybrid(db, stmt, query, embedder, k, candidate_limit=300)

    return [
        RetrievedChunk(
            chunk_id=ch.id,
            resource_id=ch.resource_id,
            chunk_index=ch.chunk_index,
            page_number=ch.page_number,
            text=ch.text,
        )
        for ch, _score in ranked
    ]

