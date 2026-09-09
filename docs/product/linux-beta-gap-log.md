# Linux Beta Gap Log

Date (UTC): 2026-09-08
Operator: solo Linux beta
Environment: Docker Compose Linux (`AUTH_MODE=dev`)

## Session evidence summary

Automated:
- `make test-api` → **98 passed**, 7 skipped
- Release-critical e2e → **15 passed** (`full-flow`, `upload-search`, `a11y`)

Manual/API smoke:
- Stack health OK (`postgres`/`redis` ok)
- Web routes `/`, `/courses`, `/tasks`, `/resources`, `/search`, `/study-lab`, `/notebooks`, `/notes` → HTTP 200
- PWA endpoints `/manifest.webmanifest`, `/icon`, `/apple-icon` → HTTP 200
- Course/task create OK
- Upload `.txt` → indexed `done` / lifecycle `searchable` in ~1s
- Search for `beta` returned uploaded resource hit
- AI ask with `{ "message": ... }` returned grounded fallback snippets without OpenAI key
- Notes create/update works when using schema field `text` (maps to `extracted_text`)

## Gaps

### B1 — Upload enqueue raced lifecycle (FIXED this beta)
- Severity: **blocker** (was)
- Status: **fixed**
- Repro (pre-fix): upload enqueued Redis job before `queued` lifecycle commit → worker/API competed for lifecycle seq → UniqueViolation → lease wait ~90s → e2e timeout
- Fix: defer Redis enqueue until after queued lifecycle commit; lock resource row for event seq; worker `db.rollback()` before fail/retry
- Evidence: full-flow e2e now ~1.4s; API tests green

### B2 — Web container broken by host `node_modules` bind mount (FIXED this beta)
- Severity: **blocker** (was)
- Status: **fixed**
- Repro: compose bind-mounted `./apps/web` including host pnpm peer hash symlinks that do not exist in image
- Fix: anonymous volumes for `/app/apps/web/node_modules` and `/app/apps/web/.next`; root `.dockerignore` excludes `ios`/`.next`/`node_modules`
- Evidence: web Ready; routes return 200

### Q1 — AI ask request field is `message`, not `question`
- Severity: **quality**
- Status: open (docs/ergonomics)
- Repro: `POST /ai/ask` with `{ "question": "..." }` → 422 missing `message`
- Expected: README/examples or alias both fields
- Actual: schema requires `message`
- Notes: once correct, ask works and returns citations even without `OPENAI_API_KEY` (snippet fallback)

### Q2 — LLM answers require `OPENAI_API_KEY`
- Severity: **quality** (expected for local beta)
- Status: open / env-config
- Repro: ask without key returns “LLM is not configured…” plus snippets
- Expected for full study UX: configured key or clearer UI banner
- Actual: functional fallback, not full LLM answer

### Q3 — Note page write field is `text`, not `extracted_text`
- Severity: **quality**
- Status: open (docs/ergonomics)
- Repro: create/patch with `extracted_text` silently ignored; `text` works
- Expected: dual accept or clearer OpenAPI/README examples
- Actual: `NotePageCreate`/`NotePageUpdate` use `text`

### Q4 — Seeded DB accumulates e2e/courses noise
- Severity: **quality**
- Status: open
- Repro: long-lived postgres volume retains many “E2E Course” / “Full Flow Course” rows
- Expected: easy reset guidance for solo beta
- Actual: `down -v` works but is destructive; no soft cleanup UI

### Q5 — Root-owned `data/uploads` and `.next` artifacts after Docker runs
- Severity: **quality**
- Status: open
- Repro: host cannot delete some upload/build files without Docker-as-root cleanup
- Expected: container user matches host uid or documented cleanup command
- Actual: requires `docker run ... alpine rm/chown`

### E1 — StudyFlows not present
- Severity: **enhancement**
- Status: planned post-beta
- Notes: capture → explain highlight → recall scoring → flashcards is the next signature feature after Linux stability

### E2 — iOS/TestFlight still blocked on Apple secrets
- Severity: **enhancement** / deferred
- Status: deferred
- Notes: keep Linux-first until product feel is validated

### E3 — Chunk API returns preview only
- Severity: **enhancement**
- Status: open
- Notes: `/resources/{id}/chunks` returns `text_preview`; fine for MVP, thinner for StudyFlows highlight spans later

## Severity counts

| Severity | Open | Fixed this session |
|---|---|---|
| blocker | 0 | 2 |
| quality | 5 | 0 |
| enhancement | 3 | 0 |
