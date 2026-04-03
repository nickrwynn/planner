## Architecture Overview

Primary components:

- `apps/web` (Next.js UI and e2e tests)
- `apps/api` (FastAPI domain APIs, ingestion, search, AI)
- `apps/worker` (Redis-backed background indexing jobs)
- Postgres (state) and Redis (queue/rate limiting)

Core data and processing flow:

1. User uploads resource via API.
2. API stores metadata and enqueues parse/index job.
3. Worker parses/OCRs/chunks/indexes content and updates lifecycle/job status.
4. Search and AI routes retrieve indexed chunks under ownership constraints.

Operational docs:

- Production runbook: `docs/architecture/production-runbook.md`
- Backup/restore runbook: `docs/architecture/backup-restore-runbook.md`
- Live readiness checklist: `docs/architecture/production-readiness-checklist.md`

