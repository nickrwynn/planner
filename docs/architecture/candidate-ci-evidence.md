# Candidate CI Evidence (Final Ship-Gate)

Date (UTC): 2026-04-03
Scope: candidate-bound CI proof for release-critical jobs

## Candidate Binding

- Candidate SHA: `BLOCKED`
- Candidate branch/tag: `BLOCKED`
- Environment: `production`

## CI Run Evidence

- CI run URL: `BLOCKED`
- CI provider: `GitHub Actions`
- Workflow file: `.github/workflows/ci.yml`

## Required Job Statuses

- `migrations`: `BLOCKED`
- `api_tests`: `BLOCKED`
- `api_tests_postgres`: `BLOCKED`
- `worker_smoke`: `BLOCKED`
- `e2e`: `BLOCKED`

## Validation Notes

- Do not mark pass unless job status is green in the candidate-bound run URL.
- Candidate SHA here must exactly match the release ticket/checklist and final audit.

## Status

Current state: `BLOCKED`
Blocker reason: candidate SHA and candidate-bound CI run evidence not provided.
