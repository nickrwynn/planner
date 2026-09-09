from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select
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


@dataclass(frozen=True)
class PageRange:
    start: int
    end: int


def retrieve_chunks(
    db: Session,
    *,
    user_id: UUID,
    query: str,
    course_id: UUID | None = None,
    resource_ids: list[UUID] | None = None,
    k: int = 8,
    page_start: int | None = None,
    page_end: int | None = None,
    page_ranges: list[PageRange] | None = None,
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

    ranges = list(page_ranges or [])
    if page_start is not None or page_end is not None:
        start = int(page_start or 1)
        end = int(page_end or page_start or start)
        if end < start:
            start, end = end, start
        ranges.append(PageRange(start=start, end=end))

    if ranges:
        clauses = []
        for r in ranges:
            clauses.append(
                and_(
                    ResourceChunk.page_number.is_not(None),
                    ResourceChunk.page_number >= r.start,
                    ResourceChunk.page_number <= r.end,
                )
            )
        stmt = stmt.where(or_(*clauses))
        # For explicit page scopes (Study Lab sections), load body chunks directly
        # instead of keyword-hybrid which often returns empty/front-matter.
        page_rows = list(
            db.execute(
                stmt.order_by(ResourceChunk.chunk_index.asc(), ResourceChunk.id.asc()).limit(max(k * 4, 40))
            )
            .scalars()
            .all()
        )
        if page_rows:
            # Prefer hybrid ranking within the page pool when embeddings exist; else take in order.
            embedder = get_embeddings_provider()
            if embedder and query.strip():
                ranked = select_chunks_hybrid(
                    db,
                    stmt,
                    query,
                    embedder,
                    k,
                    candidate_limit=min(300, max(len(page_rows) * 2, 50)),
                )
                if ranked:
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
            return [
                RetrievedChunk(
                    chunk_id=ch.id,
                    resource_id=ch.resource_id,
                    chunk_index=ch.chunk_index,
                    page_number=ch.page_number,
                    text=ch.text,
                )
                for ch in page_rows[:k]
            ]
        return []

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
