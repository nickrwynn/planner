from __future__ import annotations

from uuid import UUID

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.indexing.embeddings import EmbeddingsProvider
from app.models.resource_chunk import ResourceChunk
from app.search.keyword import chunk_text_keyword_clause


def _page_key(ch: ResourceChunk) -> int:
    if ch.page_number is not None:
        return int(ch.page_number)
    return int(ch.chunk_index)


def _diversify_by_page(
    scored: list[tuple[ResourceChunk, float | None]],
    *,
    limit: int,
) -> list[tuple[ResourceChunk, float | None]]:
    """Prefer page diversity so top-k is not all preface/TOC pages."""
    if limit < 1 or not scored:
        return []
    picked: list[tuple[ResourceChunk, float | None]] = []
    used_pages: set[int] = set()
    # First pass: at most one chunk per page
    for item in scored:
        page = _page_key(item[0])
        if page in used_pages:
            continue
        picked.append(item)
        used_pages.add(page)
        if len(picked) >= limit:
            return picked
    # Second pass: fill remaining slots
    picked_ids = {ch.id for ch, _ in picked}
    for item in scored:
        if item[0].id in picked_ids:
            continue
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def select_chunks_hybrid(
    db: Session,
    base_stmt,
    query: str,
    embedder: EmbeddingsProvider | None,
    limit: int,
    *,
    candidate_limit: int = 300,
) -> list[tuple[ResourceChunk, float | None]]:
    """
    Keyword-only when no embedder. With embedder: prefer keyword-matched candidates (then backfill by
    chunk recency), rank chunks that have embeddings by dot product vs the query vector, then fill
    remaining slots with keyword matches. The float is the semantic score when the hit came from the
    vector ranker; None for keyword-only hits.
    """
    if limit < 1:
        return []
    if not embedder:
        chunks = list(
            db.execute(
                base_stmt.where(chunk_text_keyword_clause(query))
                .order_by(desc(ResourceChunk.updated_at), asc(ResourceChunk.chunk_index), asc(ResourceChunk.id))
                .limit(max(limit * 8, 40))
            )
            .scalars()
            .all()
        )
        # Soft demote very early front-matter-ish chunks when later matches exist.
        mid = [c for c in chunks if int(c.chunk_index) >= 8]
        early = [c for c in chunks if int(c.chunk_index) < 8]
        ordered = mid + early if mid else early
        return _diversify_by_page([(c, None) for c in ordered], limit=limit)

    qvec = embedder.embed_query(query)
    kw_clause = chunk_text_keyword_clause(query)

    keyword_hits = list(
        db.execute(
            base_stmt.where(kw_clause)
            .order_by(desc(ResourceChunk.updated_at), asc(ResourceChunk.chunk_index), asc(ResourceChunk.id))
            .limit(candidate_limit)
        )
        .scalars()
        .all()
    )
    seen: set[UUID] = {c.id for c in keyword_hits}

    if len(keyword_hits) < candidate_limit:
        overflow = min(candidate_limit * 3, 2000)
        rest = list(
            db.execute(base_stmt.order_by(desc(ResourceChunk.updated_at)).limit(overflow)).scalars().all()
        )
        for ch in rest:
            if ch.id in seen:
                continue
            keyword_hits.append(ch)
            seen.add(ch.id)
            if len(keyword_hits) >= candidate_limit:
                break

    candidates = keyword_hits[:candidate_limit]
    scored: list[tuple[float, ResourceChunk]] = []
    for ch in candidates:
        if not ch.embedding:
            continue
        dot = sum(a * b for a, b in zip(qvec, ch.embedding, strict=False))
        # Mild penalty for early book front matter so chapter body can win ties.
        penalty = 0.02 if int(ch.chunk_index) < 8 else 0.0
        scored.append((dot - penalty, ch))
    scored.sort(
        key=lambda x: (
            -x[0],
            str(x[1].resource_id),
            int(x[1].chunk_index),
            str(x[1].id),
        )
    )

    ranked: list[tuple[ResourceChunk, float | None]] = [(ch, float(s)) for s, ch in scored]
    diversified = _diversify_by_page(ranked, limit=limit)
    merged_ids: set[UUID] = {ch.id for ch, _ in diversified}

    if len(diversified) >= limit:
        return diversified

    kw_cap = max(limit * 6, 50)
    kw_pool: list[tuple[ResourceChunk, float | None]] = []
    for ch in (
        db.execute(
            base_stmt.where(kw_clause)
            .order_by(desc(ResourceChunk.updated_at), asc(ResourceChunk.chunk_index), asc(ResourceChunk.id))
            .limit(kw_cap)
        )
        .scalars()
        .all()
    ):
        if ch.id in merged_ids:
            continue
        kw_pool.append((ch, None))
    fill = _diversify_by_page(kw_pool, limit=limit - len(diversified))
    return diversified + fill
