# Production Readiness Checklist

Last updated: 2026-04-03

## A. Release foundation / reproducible builds

- [x] API default container command switched to non-reload runtime (`apps/api/Dockerfile`).
- [x] Web default container command switched to production start (`apps/web/Dockerfile`).
- [x] Runtime profile switch (`APP_RUNTIME_PROFILE`) added to compose (`docker-compose.yml`).
- [x] Worker local dependency install path aligned (`apps/worker/requirements.txt`).
- [x] `make verify-release` target added for prod-profile smoke checks (`Makefile`).

Validation:
- `docker compose --env-file env.example config --quiet` passed.
- `make help` lists `verify-release`.

## B. Config and environment hardening

- [x] Production-profile startup guards added (`apps/api/app/main.py`).
- [x] Settings defaults hardened for API config (`apps/api/app/core/config.py`).
- [x] Env template updated with runtime/auth mode controls (`env.example`).

Validation:
- `pytest tests/test_startup_config.py` passed in API container.

## C. Auth, authorization, and tenancy safety

- [x] Bearer JWT validation hardened (`sub`, `exp`, `iat`, optional `iss`/`aud`) (`apps/api/app/api/deps.py`).
- [x] Non-dev unsupported auth modes now rejected (`apps/api/app/api/deps.py`).
- [x] Web API header mode split for dev vs bearer behavior (`apps/web/lib/api.ts`).

Validation:
- `pytest tests/test_auth_bearer.py` passed in API container.

## D. DB schema, migrations, and data integrity

- [x] CI job for Postgres-backed API tests added (`.github/workflows/ci.yml`).
- [x] Migration integrity checker added and wired into CI (`apps/api/scripts/check_migrations.py`, `.github/workflows/ci.yml`).

## E. Storage and resource lifecycle correctness

- [x] Upload read path now bounded chunked reads (`apps/api/app/api/routes/resources.py`).
- [x] Local storage traversal hardening via resolved root containment (`apps/api/app/services/storage/local_fs.py`).
- [x] Batch upload returns explicit accepted/rejected result rows (`apps/api/app/api/routes/resources.py`).

Validation:
- `pytest tests/test_resources.py tests/test_storage_paths.py` passed in API container.

## F. Queue and worker reliability

- [ ] Claim/ack/lease model and richer job telemetry.

## G. Parsing and indexing robustness

- [ ] Structured parser error taxonomy and lifecycle audit trails.

## H. Search and retrieval quality

- [x] Retrieval regression test added to assert exact keyword preference (`apps/api/tests/test_hybrid_retrieval.py`).
- [ ] Full benchmark suite and quality thresholds.

## I. AI ask and study-lab hardening

- [x] Citation reference validation now strips invalid source ids and preserves grounded fallback citations (`apps/api/app/api/routes/ai.py`).
- [x] Adversarial citation regression test added (`apps/api/tests/test_ai_citations.py`).

## J. Planner/domain logic trust

- [ ] Weighted deterministic planner scoring and test matrix.

## K. Web UX correctness and page integrity

- [x] Resource page surfaces batch upload accept/reject feedback (`apps/web/app/resources/page.tsx`).
- [ ] Remaining page-by-page hardening tasks.

## L. Web/API contract consistency

- [x] Contract drift check script added (`scripts/check_web_api_contracts.py`).
- [ ] Shared/generated contracts.

## M. Testing and CI confidence

- [x] Web typecheck script added (`apps/web/package.json`).
- [x] CI includes web typecheck/build and worker import smoke (`.github/workflows/ci.yml`).
- [ ] Worker reliability chaos tests.

## N. Observability, logging, and rate limiting

- [x] Redis-backed distributed rate limiter implemented (`apps/api/app/api/middleware/rate_limit.py`).
- [x] Middleware wired to API app runtime (`apps/api/app/main.py`).
- [ ] Telemetry depth expansion (worker/job traces and correlation IDs).

Validation:
- `pytest tests/test_rate_limit_middleware.py` passed in API container.

## O. Production operations, backup, restore, and deployment safety

- [ ] Backup/restore drill evidence and runbook proof.
