# Worker Queue Evaluation

## Current state

- Queue: Redis list via `BLPOP` (`queue:parse_resource`)
- Retry: handled in worker code by re-enqueueing payload
- Gaps: no dead-letter queue, no native visibility timeout, limited observability

## Options compared

1. **Redis Streams**
   - Pros: consumer groups, pending entries list, replay support, no extra service.
   - Cons: more complex worker state handling than list-based queue.
2. **RQ**
   - Pros: simple Python API, retries, failed job registries, dashboard ecosystem.
   - Cons: framework migration and worker refactor required.
3. **Celery**
   - Pros: mature, robust retries/routing/scheduling.
   - Cons: higher complexity and operational overhead for current scope.

## Recommendation (next step)

- Move from Redis list to **Redis Streams** first.
- Keep one queue topic (`parse_resource`) and add:
  - consumer group for workers,
  - dead-letter stream after max retries,
  - queue depth + lag metrics.

## Exit criteria for migration

- No lost jobs during worker restart.
- Failed jobs land in DLQ with error reason.
- Job latency and retry counts available in metrics/logs.
