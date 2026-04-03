# Release Ticket / Checklist (Final Ship-Gate)

Date (UTC): 2026-04-03
Scope: production release closeout

## Candidate Binding

- Candidate SHA: `BLOCKED`
- Candidate branch/tag: `BLOCKED`
- Environment: `production`

Validation rule: this candidate identifier must exactly match
`final-ship-gate-gap-audit.md`, `candidate-ci-evidence.md`, and
`restore-drill-evidence.md`.

## Ticket Metadata

- Ticket URL or ID: `BLOCKED`
- Release owner: `BLOCKED`
- On-call approver: `BLOCKED`
- Approval timestamp (UTC): `BLOCKED`

## Deploy Image Tags (Exact Candidate)

- API image tag: `BLOCKED`
- Web image tag: `BLOCKED`
- Worker image tag: `BLOCKED`

## Rollback Command Contract

- App rollback command:
  - `APP_RUNTIME_PROFILE=prod APP_ENV=production docker compose --env-file env.example up -d api worker web`
- Schema check command:
  - `docker compose --env-file env.example run --rm api python scripts/check_migrations.py`
- Emergency downgrade command (pre-approved only):
  - `docker compose --env-file env.example run --rm api alembic -c alembic.ini downgrade 0008`

## Release Checklist

- [ ] Candidate SHA is immutable and recorded.
- [ ] CI evidence URL for this candidate is attached.
- [ ] Required CI jobs are green for this candidate.
- [ ] Image tags map exactly to this candidate.
- [ ] Rollback plan reviewed by release owner and on-call approver.
- [ ] Restore-drill evidence (<=30 days) is linked.
- [ ] Health and upload/index/search smoke evidence attached.

## Status

Current state: `BLOCKED`
Blocker reason: candidate-bound operational fields are not yet populated.
