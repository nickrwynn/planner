from __future__ import annotations

from sqlalchemy import ColumnElement, and_, or_

from app.models.resource_chunk import ResourceChunk

# Tokens that match almost every textbook / English prose chunk when OR'd.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "i",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
        # Study-lab meta prompts / instructional words
        "key",
        "concepts",
        "summarize",
        "summary",
        "flashcards",
        "facts",
        "quiz",
        "questions",
        "sample",
        "problems",
        "create",
        "generate",
        "return",
        "json",
        "regarding",
        "passage",
        "discuss",
        "define",
        "explain",
    }
)


def query_tokens(query: str, *, limit: int = 12) -> list[str]:
    """Extract useful keyword tokens from a free-text query."""
    raw = [w.strip(".,;:!?\"'()[]{}").lower() for w in query.split() if w.strip()]
    words: list[str] = []
    seen: set[str] = set()
    for w in raw:
        if len(w) < 3 or w in _STOPWORDS or w in seen:
            continue
        seen.add(w)
        words.append(w)
        if len(words) >= limit:
            break
    return words


def chunk_text_keyword_clause(query: str) -> ColumnElement[bool]:
    """
    Multi-token keyword match.

    - 1 token: substring match
    - 2–3 tokens: require ALL (AND) so loose OR no longer floods with front matter
    - 4+ tokens: AND the first 3 only (extra tokens are too restrictive for PDF OCR text)
    - If every token is a stopword, fall back to OR on the raw first few words
    """
    words = query_tokens(query, limit=8)
    if not words:
        fallback = [w.strip() for w in query.split() if len(w.strip()) >= 3][:4]
        if not fallback:
            return ResourceChunk.text.ilike("%%")
        return or_(*[ResourceChunk.text.ilike(f"%{w}%") for w in fallback])

    must = words[:3]
    clauses = [ResourceChunk.text.ilike(f"%{w}%") for w in must]
    if len(clauses) == 1:
        return clauses[0]
    return and_(*clauses)
