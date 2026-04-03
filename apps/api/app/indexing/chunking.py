from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    page_number: int | None
    text: str


def chunk_text(*, text: str, page_number: int | None, chunk_size: int = 1200, overlap: int = 200) -> list[Chunk]:
    """
    Simple stable chunking for MVP: character-based with overlap.
    Page number is carried through for citations.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    chunks: list[Chunk] = []
    start = 0
    idx = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(Chunk(chunk_index=idx, page_number=page_number, text=chunk))
            idx += 1
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks

