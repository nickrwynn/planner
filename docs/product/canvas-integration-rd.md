# Canvas Integration R&D (Deferred)

Status: deferred until core auth, storage, and ingestion are stable.

## Goal

Import courses, assignments, and due dates from Canvas into Academic OS.

## Prerequisites

- Production auth/authz complete.
- Per-user OAuth token storage with encryption-at-rest.
- Idempotent sync jobs and conflict resolution.

## Initial plan

1. OAuth app registration and callback flow.
2. Pull courses + assignments via Canvas API.
3. Map to internal `courses` and `tasks` with source refs.
4. Background sync schedule + manual sync trigger.

## Risks

- API quota and permission scopes.
- Duplicate task mapping and due date timezone drift.
