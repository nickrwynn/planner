# Linux Beta Verification Runbook

Repeatable commands for the solo Linux beta. Prefer these over ad-hoc steps.

## 0) One-time hygiene

```bash
# Keep host bind mounts from breaking Next in the web container
# (compose isolates container node_modules/.next; still keep host install healthy)
pnpm install
```

## 1) Start stack

```bash
AUTH_MODE=dev docker compose --env-file env.example up --build -d
make migrate
make seed
make smoke
curl -fsS -o /dev/null -w 'web:%{http_code}\n' http://localhost:3000/
curl -fsS -o /dev/null -w 'manifest:%{http_code}\n' http://localhost:3000/manifest.webmanifest
```

## 2) Automated gates

```bash
make test-api
AUTH_MODE=dev pnpm --filter @planner/web test:e2e \
  e2e/full-flow.spec.ts e2e/upload-search.spec.ts e2e/a11y.spec.ts
```

## 3) Manual smoke (5–10 minutes)

1. Open `http://localhost:3000`.
2. Create a course named `Linux Beta`.
3. Create a task on that course.
4. Upload a small `.txt` file via Resources.
5. Wait until resource detail shows indexed/searchable.
6. Search for a unique token from the file.
7. Ask the agent a question about that content.
8. Create a notebook + note page and type a short note.

## 4) Log gaps

Record every friction item in [`linux-beta-gap-log.md`](linux-beta-gap-log.md) with:

- severity: `blocker` | `quality` | `enhancement`
- reproduction steps
- expected vs actual
- optional screenshot / log snippet

## 5) Stop / reset (optional)

```bash
docker compose --env-file env.example down
# destructive reset of DB/volumes:
# docker compose --env-file env.example down -v
```

## Related docs

- Triage: [`linux-beta-wip-triage.md`](linux-beta-wip-triage.md)
- Acceptance: [`linux-beta-acceptance-checklist.md`](linux-beta-acceptance-checklist.md)
- Product index: [`README.md`](README.md)
