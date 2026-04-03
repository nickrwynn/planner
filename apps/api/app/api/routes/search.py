from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.models.course import Course
from app.models.resource import Resource
from app.models.resource_chunk import ResourceChunk
from app.schemas.search import SearchHit
from app.indexing.embeddings import get_embeddings_provider
from app.search.hybrid import select_chunks_hybrid

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[SearchHit])
def search(
    q: str = Query(min_length=1, max_length=200),
    course_id: UUID | None = Query(default=None),
    resource_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db_from_request),
    user=Depends(get_current_user),
):
    """
    Phase 3 MVP search endpoint.

    - Initially keyword-based (`ILIKE`) over stored chunks.
    - Phase 3.5 will add embeddings + pgvector similarity search.
    """

    # Ownership is primarily via resources.user_id (course_id can be NULL, e.g. ad-hoc docs or note pages).
    owned_resource_ids = select(Resource.id).where(
        Resource.user_id == user.id,
        Resource.index_status == "done",
        Resource.lifecycle_state == "searchable",
    )
    stmt = select(ResourceChunk).where(
        ResourceChunk.user_id == user.id,
        ResourceChunk.resource_id.in_(owned_resource_ids),
    )

    if course_id is not None:
        owned_course = (
            db.execute(select(Course.id).where(Course.id == course_id, Course.user_id == user.id))
            .scalars()
            .first()
        )
        if not owned_course:
            return []
        course_resource_ids = select(Resource.id).where(
            Resource.user_id == user.id,
            Resource.course_id == course_id,
            Resource.index_status == "done",
            Resource.lifecycle_state == "searchable",
        )
        stmt = stmt.where(ResourceChunk.resource_id.in_(course_resource_ids))

    if resource_id is not None:
        owned_resource = (
            db.execute(select(Resource.id).where(Resource.id == resource_id, Resource.user_id == user.id))
            .scalars()
            .first()
        )
        if not owned_resource:
            return []
        stmt = stmt.where(ResourceChunk.resource_id == resource_id)

    # Collect title/metadata matches for optional fallback enrichment.
    title_meta_resource_ids = set(
        db.execute(
            select(Resource.id).where(
                Resource.user_id == user.id,
                or_(
                    Resource.title.ilike(f"%{q}%"),
                    cast(Resource.metadata_json, String).ilike(f"%{q}%"),
                ),
            )
        )
        .scalars()
        .all()
    )

    embedder = get_embeddings_provider()
    ranked = select_chunks_hybrid(db, stmt, q, embedder, limit, candidate_limit=200)

    hits: list[SearchHit] = []
    resource_ids = list({ch.resource_id for ch, _ in ranked})
    resources = (
        db.execute(select(Resource).where(Resource.user_id == user.id, Resource.id.in_(resource_ids)))
        .scalars()
        .all()
    )
    by_id = {r.id: r for r in resources}
    for ch, score in ranked:
        snippet = ch.text[:400]
        r = by_id.get(ch.resource_id)
        hits.append(
            SearchHit(
                resource_id=ch.resource_id,
                resource_title=(r.title if r else "Unknown resource"),
                resource_type=(r.resource_type if r else None),
                chunk_id=ch.id,
                chunk_index=ch.chunk_index,
                page_number=ch.page_number,
                snippet=snippet,
                score=score,
            )
        )

    if len(hits) < limit and title_meta_resource_ids:
        seen = {h.resource_id for h in hits}
        missing = [rid for rid in title_meta_resource_ids if rid not in seen]
        if missing:
            extra_chunks = (
                db.execute(
                    select(ResourceChunk)
                    .where(ResourceChunk.resource_id.in_(missing))
                    .order_by(ResourceChunk.updated_at.desc())
                    .limit(limit - len(hits))
                )
                .scalars()
                .all()
            )
            for ch in extra_chunks:
                r = by_id.get(ch.resource_id)
                hits.append(
                    SearchHit(
                        resource_id=ch.resource_id,
                        resource_title=(r.title if r else "Unknown resource"),
                        resource_type=(r.resource_type if r else None),
                        chunk_id=ch.id,
                        chunk_index=ch.chunk_index,
                        page_number=ch.page_number,
                        snippet=ch.text[:400],
                        score=None,
                    )
                )
    return hits

