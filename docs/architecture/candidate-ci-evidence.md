# Candidate CI Evidence (Final Ship-Gate)

Date (UTC): 2026-04-03
Scope: candidate-bound CI proof for release-critical jobs

## Candidate Binding

- Candidate SHA: `13caf46a39c53d1ba0725ed77f8a4c4eec838e9b`
- Candidate branch/tag: `main`
- Environment: `production`

## CI Run Evidence

- CI run URL: `https://github.com/nickrwynn/planner/actions/runs/23961441564`
- CI provider: `GitHub Actions`
- Workflow file: `.github/workflows/ci.yml`
- Workflow conclusion: `failure`

## Required Job Statuses

- `migrations`: `success`
- `api_tests`: `failure`
- `api_tests_postgres`: `success`
- `worker_smoke`: `success`
- `e2e`: `failure`

## Validation Notes

- Do not mark pass unless job status is green in the candidate-bound run URL.
- Candidate SHA here must exactly match the release ticket/checklist and final audit.
- Candidate run binding check: run head SHA matches `13caf46a39c53d1ba0725ed77f8a4c4eec838e9b`.

## Status

Current state: `BLOCKED`
Blocker reason: required release-critical jobs are not all green for this candidate (`api_tests`, `e2e` failed).
