# iOS Client Readiness (Deferred)

Status: deferred until production API contract is stable.

## Readiness criteria before native client

- Auth/token lifecycle finalized.
- API versioning strategy documented.
- Error contract standardized across endpoints.
- E2E and contract tests green in CI.

## Proposed scope (phase 1)

- Read-only dashboard, courses, tasks, resources.
- Ask agent over existing resources.
- No upload/scan on first iOS iteration.

## API requirements

- Stable pagination patterns.
- Mobile-friendly typed response schemas.
- Rate limits and retry headers.
