from __future__ import annotations

from app.indexing import embeddings as embeddings_mod
from app.models.resource_chunk import ResourceChunk


def embed_resource_chunks_if_configured(chunks: list[ResourceChunk]) -> str | None:
    """
    When an embeddings provider is configured, set chunk.embedding on each chunk in place.

    Returns None if skipped (no provider or no chunks) or on success.
    Returns an error string if embedding was attempted but failed (chunks stay without vectors).
    """
    if not chunks:
        return None
    embedder = embeddings_mod.get_embeddings_provider()
    if not embedder:
        return None
    try:
        vectors = embedder.embed_documents([c.text for c in chunks])
        for c, v in zip(chunks, vectors, strict=False):
            c.embedding = v
    except Exception as e:  # noqa: BLE001
        return str(e)
    return None
