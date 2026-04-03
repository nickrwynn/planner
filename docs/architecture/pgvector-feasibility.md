# pgvector Feasibility

## Current baseline

- Embeddings are stored in `resource_chunks.embedding` as JSON.
- Ranking uses in-process dot product over candidate chunks.

## Why change

- JSON vectors do not scale well for large corpora.
- No ANN index support.

## Proposed migration sketch

1. Enable `pgvector` extension.
2. Add `embedding_vec vector(1536)` (or model-specific dim) to `resource_chunks`.
3. Backfill vectors from existing JSON embeddings.
4. Add ivfflat/hnsw index.
5. Switch hybrid ranker to SQL vector similarity for semantic step.

## Decision gate

- Move to pgvector when:
  - corpus > 100k chunks,
  - semantic query latency > 500ms p95,
  - memory usage for in-process scoring becomes unstable.
