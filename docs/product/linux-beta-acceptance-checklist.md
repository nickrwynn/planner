# Linux Beta Acceptance Checklist

Use this checklist for the **solo Linux beta** of the existing MVP.
Scope excludes StudyFlows and iOS/TestFlight packaging.

## Run metadata

- Candidate / local tree date (UTC): `2026-09-08T02:16:00Z`
- Operator: solo Linux beta owner
- Environment: Docker Compose on Linux (`AUTH_MODE=dev`, `APP_RUNTIME_PROFILE=dev`)
- Web: `http://localhost:3000`
- API health: `http://localhost:8000/health`

## Bootstrap reliability

- [x] `AUTH_MODE=dev docker compose --env-file env.example up --build -d` starts `postgres`, `redis`, `api`, `worker`, `web`
- [x] `make migrate` reaches Alembic head (includes `0018` queued lifecycle)
- [x] `make seed` completes
- [x] `curl -fsS http://localhost:8000/health` returns `status=ok` with postgres/redis ok
- [x] Web root returns HTTP 200
- [x] Optional PWA endpoints resolve: `/manifest.webmanifest`, `/icon`, `/apple-icon`

## Core product flows

- [x] Courses: create / rename / open detail
- [x] Tasks: create / mark done / list by course
- [x] Resources: upload `.txt` or PDF → `index_status` becomes `done` and `lifecycle_state=searchable`
- [x] Search: query finds uploaded content
- [x] AI ask: agent pane / API returns an answer (citations when chunks exist; graceful without OpenAI key)
- [x] Notes/notebooks: create notebook + note document + page; edit typed page text (`text` field)
- [x] Study lab page loads and lists resources for a course

## Automated verification

- [x] `make test-api` green (98 passed, 7 skipped)
- [x] Release-critical e2e green:
  - `pnpm --filter @planner/web test:e2e e2e/full-flow.spec.ts e2e/upload-search.spec.ts e2e/a11y.spec.ts` → 15 passed

## Outcome

- Result (`pass` / `fail`): `pass`
- Blockers found: none open; see [`linux-beta-gap-log.md`](linux-beta-gap-log.md) (2 blockers fixed during beta prep)
- Ready for daily solo use: `yes` (set `OPENAI_API_KEY` for full LLM answers)
