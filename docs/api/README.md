## API Conventions

- All authenticated endpoints must resolve user identity through `get_current_user`.
- Production profile requires bearer JWT auth with strict claim validation.
- Resource ingestion endpoints must return explicit failure reasons for rejected files.
- New endpoints must include:
  - ownership enforcement checks,
  - schema validation via `app.schemas.*`,
  - tests for success and failure paths.

## Route groups

- `/courses`, `/tasks`, `/planner`
- `/resources`, `/jobs`, `/search`
- `/notebooks`, `/note-documents`, `/note-pages`
- `/ai/*`

## Release-critical requirements

- No endpoint may implicitly create fallback identities in production profile.
- Any background-job-facing endpoint must expose sufficient diagnostics for retry/failure visibility.
- API changes require updating tests and CI checks.

