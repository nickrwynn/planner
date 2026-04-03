# Production Deployment Runbook

## Scope

Single-node private beta deployment for web, API, worker, Postgres, and Redis.

## Ownership and change control

- Release owner approves deploy window and rollback plan.
- On-call engineer executes deployment checklist.
- Any failed safety check blocks release until resolved.

## Preconditions

- `AUTH_MODE=bearer`
- `AUTH_JWT_SECRET` is set to a strong secret
- `RATE_LIMIT_ENABLED=true`
- `TELEMETRY_ENABLED=true`
- Backups are configured and verified

## Startup

1. Validate environment variables from `env.example` against production secrets.
   - `APP_RUNTIME_PROFILE=prod`
   - `APP_ENV=production`
2. Start dependencies: Postgres and Redis.
3. Run migrations:
   - `docker compose --env-file env.example run --rm api alembic -c alembic.ini upgrade head`
   - `docker compose --env-file env.example run --rm api python scripts/check_migrations.py`
4. Start API, worker, and web:
   - `APP_RUNTIME_PROFILE=prod APP_ENV=production docker compose --env-file env.example up -d api worker web`
5. Verify:
   - `GET /health` returns `postgres.ok=true`, `redis.ok=true`
   - Upload -> index -> search smoke flow succeeds

## Shutdown

1. Stop web traffic ingress.
2. Stop web and API.
3. Wait for worker queue drain; then stop worker.
4. Keep Postgres/Redis up until backup checkpoint completes.
5. Stop remaining services.

## Recovery

1. Restore Postgres from latest healthy backup.
2. Restore object storage/files snapshot for the same recovery point.
3. Run migrations to head.
4. Start services and run smoke checks.
5. Validate key user journeys and monitor error/latency for 30 minutes.

## Rollback decision flow

Use this decision flow immediately when a deploy fails:

1. **Application-only regression** (API/web/worker behavior bad, schema compatible):
   - Redeploy last known-good image tags for `api`, `web`, `worker`.
   - Keep database at current schema version.
   - Re-run `/health` and upload/index/search smoke.
2. **Migration failure before completion**:
   - Stop rollout.
   - Resolve migration issue and rerun `alembic upgrade head` only after fix.
   - Do not serve traffic until migration checker passes.
3. **Migration completed but release is incompatible with new schema**:
   - Preferred: deploy a hotfix build compatible with current head schema.
   - If emergency downgrade is approved and verified for this revision set:
     - `docker compose --env-file env.example run --rm api alembic -c alembic.ini downgrade 0008`
     - Redeploy last known-good application images.
   - If downgrade is unsafe or fails, execute full restore procedure from backup runbook.
4. **Data integrity risk or unknown state**:
   - Declare incident.
   - Execute full restore using [`backup-restore-runbook.md`](backup-restore-runbook.md).
   - Keep release in no-ship state until recovery evidence is complete.

## Rollback command contract

Record these concrete commands in the deploy ticket before release starts:

- Last known-good image tags:
  - `api=<tag>`
  - `web=<tag>`
  - `worker=<tag>`
- App rollback command:
  - `APP_RUNTIME_PROFILE=prod APP_ENV=production docker compose --env-file env.example up -d api worker web`
- Schema check command:
  - `docker compose --env-file env.example run --rm api python scripts/check_migrations.py`
- Emergency downgrade command (only if pre-approved for current migration graph):
  - `docker compose --env-file env.example run --rm api alembic -c alembic.ini downgrade 0008`

## Safety Checks

- Never skip migrations.
- Never deploy with `AUTH_MODE=dev`.
- Never deploy without backup restore drill completed in last 30 days.
- Never deploy with `RATE_LIMIT_ENABLED=false`.

## Release gate (ship criteria)

A release is ship-ready only when all are true:

- CI is green for migration, API, Postgres-backed API, worker smoke, and E2E gates in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).
- Startup env safety constraints are verified by tests in [`apps/api/tests/test_startup_config.py`](../../apps/api/tests/test_startup_config.py).
- Deploy ticket includes rollback command contract above with image tags filled.
- Latest restore drill evidence (<=30 days) is attached per [`backup-restore-runbook.md`](backup-restore-runbook.md).
- Health and upload/index/search smoke outputs are attached for the release candidate environment.

## Release evidence (required)

Attach release evidence to the deploy ticket:

- Commit SHA and environment
- Migration output (`upgrade head` and migration checker)
- Health check output
- Smoke flow output (upload/index/search)
- Rollback command and confirmation that rollback plan was reviewed
