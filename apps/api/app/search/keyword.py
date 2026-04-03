from __future__ import annotations

from sqlalchemy import ColumnElement, or_

from app.models.resource_chunk import ResourceChunk


def chunk_text_keyword_clause(query: str) -> ColumnElement[bool]:
    """
    Multi-token keyword match: any token may appear (OR). Caps tokens for safety.
    """
    words = [w.strip() for w in query.split() if w.strip()][:12]
    if not words:
        return ResourceChunk.text.ilike("%%")
    if len(words) == 1:
        return ResourceChunk.text.ilike(f"%{words[0]}%")
    return or_(*[ResourceChunk.text.ilike(f"%{w}%") for w in words])
