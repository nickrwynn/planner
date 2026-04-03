from __future__ import annotations

from uuid import UUID

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.indexing.embeddings import EmbeddingsProvider
from app.models.resource_chunk import ResourceChunk
from app.search.keyword import chunk_text_keyword_clause


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
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [(c, None) for c in chunks]

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
        scored.append((dot, ch))
    scored.sort(
        key=lambda x: (
            -x[0],
            str(x[1].resource_id),
            int(x[1].chunk_index),
            str(x[1].id),
        )
    )

    merged: list[tuple[ResourceChunk, float | None]] = [(ch, float(s)) for s, ch in scored[:limit]]
    merged_ids: set[UUID] = {ch.id for ch, _ in merged}

    if len(merged) >= limit:
        return merged

    kw_cap = max(limit * 3, 50)
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
        merged.append((ch, None))
        merged_ids.add(ch.id)
        if len(merged) >= limit:
            break
    return merged
