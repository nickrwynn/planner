## Academic OS (MVP)

This monorepo is a **usable MVP** for an academic organizer with a resource ingestion pipeline, search, AI ask pane, study lab, and notes.

- **Web**: Next.js (TypeScript) App Router — dashboard, courses, tasks, resources, search, study lab, notebooks, notes, 3-column layout with agent pane
- **API**: FastAPI (Python) with SQLAlchemy models + Alembic migrations
- **Worker**: Python worker consuming Redis queue `queue:parse_resource` (JSON payloads with `job_id` + `resource_id`)
- **Infra**: Docker Compose with Postgres + Redis + API + Web + Worker

Auth supports **bearer mode** (`AUTH_MODE=bearer`): the API expects `Authorization: Bearer <jwt>` where the JWT includes `sub=<user_uuid>` and is signed with `AUTH_JWT_SECRET`.
The default local template uses **dev mode** (`AUTH_MODE=dev`) so you can bootstrap quickly; production deployments should run bearer mode.

### Local dev auth (multi-user testing)

The Next.js app sends `X-User-Id` when you set the same UUID in both places so the dashboard (server-rendered) and browser pages hit the API as the same user:

- **Browser / client components:** `NEXT_PUBLIC_DEV_USER_ID` or `NEXT_PUBLIC_API_USER_ID` (UUID string).
- **Server components (e.g. dashboard):** `DEV_USER_ID` or `API_USER_ID` (same UUID as above).

After `make seed`, inspect the `users` table or use the API to list users and copy an `id`. If these variables are unset, the API falls back to the first user (single-user dev).

## Repo layout

- `apps/web` — Next.js frontend
- `apps/api` — FastAPI backend
- `apps/worker` — worker process (imports `app` from `apps/api`)
- `packages/*` — reserved for shared packages later
- `docs/*` — architecture/product notes (placeholders for now)

## Prerequisites

- Docker Engine + Docker Compose plugin (recommended)

Optional (for running without Docker):

- Node.js LTS + pnpm
- Python 3.11+ and pip

## Quick start (Docker)

1. (Optional) Copy env template:

```bash
cp env.example .env
```

The Makefile uses `env.example` when no override is needed. The stack reads env via `docker compose --env-file env.example ...`. [`.env.example`](.env.example) is a symlink to [`env.example`](env.example) for tools that expect the dotfile name.

2. Start the stack:

```bash
make up
```

By default `env.example` runs a development runtime profile (`APP_RUNTIME_PROFILE=dev`).
To smoke-test production startup behavior locally, run:

```bash
APP_RUNTIME_PROFILE=prod docker compose --env-file env.example up --build -d
```

3. Open:

- Web: `http://localhost:3000`
- API: `http://localhost:8000/health`

4. Run migrations + seed dev data:

```bash
make migrate
make seed
```

See [`env.example`](env.example) for `OPENAI_API_KEY`, `EMBEDDINGS_PROVIDER`, and related AI settings.

### AI and retrieval environment matrix

| Mode | Required env | Behavior |
|---|---|---|
| Keyword-only retrieval (default) | none | `GET /search` and `POST /ai/ask` use keyword ranking only. |
| Semantic retrieval via OpenAI embeddings | `EMBEDDINGS_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_EMBEDDINGS_MODEL` (optional) | Chunk embeddings are generated during indexing; hybrid ranker uses vectors + keyword. |
| Semantic retrieval via sentence-transformers | `EMBEDDINGS_PROVIDER=sentence-transformers`, `SENTENCE_TRANSFORMERS_MODEL` (optional) + local ML deps | Local embeddings in-process; useful without OpenAI keys but heavier runtime deps. |
| Ask endpoint with LLM answer | `OPENAI_API_KEY` (and optional `OPENAI_CHAT_MODEL`) | `POST /ai/ask` returns model-generated answer with citations when chunks exist. |
| Study lab generation endpoints | `OPENAI_API_KEY` | `POST /ai/summaries`, `/flashcards`, `/quizzes`, `/sample-problems` require LLM config and fail otherwise. |

### CORS environment guidance

- `CORS_ORIGINS` should be a comma-separated allowlist per deployment environment.
- Dev example: `http://localhost:3000`
- Production example: `https://app.your-domain.com`
- Avoid wildcard origins in production.

## Smoke test checklist

- `make ps` shows `web`, `api`, `worker`, `postgres`, `redis` running.
- `curl http://localhost:8000/health` returns JSON with `status: ok` and `postgres.ok=true`, `redis.ok=true`.
- Dashboard at `http://localhost:3000` loads (tasks, resources, indexing failures if any).
- **Ingestion:** Create a course, upload a small PDF via Resources → confirm `GET /resources/{id}` shows `index_status=done` (after worker runs), `GET /resources/{id}/jobs` shows a job with `status=done`, and `GET /resources/{id}/chunks` returns rows. Unsupported file types should show `index_status=skipped` (not `done`) with no chunks; `.txt` / `text/*` should index like plain text.
- **Search / Ask:** `GET /search?q=...` returns hits; agent pane `POST /ai/ask` returns an answer (with citations when chunks exist).
- **Conversations:** `GET /ai/conversations` and `GET /ai/conversations/{id}/messages` after a successful ask.
- **Planner:** `GET /planner/next` returns a suggested task when open tasks exist.

## Implemented API routes (current)

- **health**: `GET /health`
- **planner**: `GET /planner/next`
- **courses**: `GET /courses`, `POST /courses`, `GET /courses/{id}`, `PATCH /courses/{id}`, `DELETE /courses/{id}`
- **tasks**: `GET /tasks` (pagination: `limit`, `offset`), `GET /courses/{course_id}/tasks`, `POST /tasks`, `PATCH /tasks/{id}`, `GET /tasks/{id}`, `DELETE /tasks/{id}`
- **resources**: `GET /resources` (pagination: `limit`, `offset`), `POST /resources`, `GET /resources/{id}`, `PATCH /resources/{id}`, `DELETE /resources/{id}`, `POST /resources/upload`, `POST /resources/{id}/reindex`, `GET /resources/{id}/jobs`, `GET /resources/{id}/chunks`
- **jobs**: `GET /jobs/{job_id}`
- **notebooks**: `GET /notebooks`, `POST /notebooks`, `GET /notebooks/{id}`, `PATCH /notebooks/{id}`, `DELETE /notebooks/{id}`
- **notes**: `GET /notebooks/{id}/note-documents`, `POST /note-documents`, `GET /note-documents/{id}`, `PATCH /note-documents/{id}`, `DELETE /note-documents/{id}`, `GET /note-documents/{id}/pages`, `POST /note-pages`, `PATCH /note-pages/{id}`, `GET /note-pages/{id}`, `DELETE /note-pages/{id}`
- **search**: `GET /search`
- **ai**: `POST /ai/ask`, `GET /ai/conversations`, `GET /ai/conversations/{id}/messages`, `GET /ai/artifacts` (pagination: `limit`, `offset`), `GET /ai/artifacts/{id}`, `POST /ai/summaries`, `POST /ai/flashcards`, `POST /ai/quizzes`, `POST /ai/sample-problems`

## Resource ingestion pipeline

Redis queue payload (preferred): JSON string `{"job_id":"<uuid>","resource_id":"<uuid>"}`. Legacy: raw `resource_id` UUID string only.

```mermaid
flowchart TD
  upload[POST_/resources/upload] --> store[LocalFilesystemStorage_put_bytes]
  store --> jobRow[background_jobs_queued]
  jobRow --> enqueue[Redis_rpush_JSON]
  enqueue --> worker[worker_blpop]
  worker --> index[index_resource]
  index --> parse[PDF_or_OCR]
  parse --> chunk[chunk_text]
  chunk --> chunks[resource_chunks]
  chunks --> done[job_done_or_retry]
```

Worker may **retry** failed indexing up to `WORKER_MAX_PARSE_ATTEMPTS` (default 3) with backoff before marking the job failed.

## Local run (without Docker) (optional)

Ubuntu prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
```

Web:

```bash
pnpm install
pnpm --filter @planner/web dev
```

API:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r apps/api/requirements.txt
export DATABASE_URL="postgresql+psycopg://planner:planner@localhost:5432/planner"
export REDIS_URL="redis://localhost:6379/0"
uvicorn app.main:create_app --factory --reload --port 8000 --app-dir apps/api
```

Worker (requires Redis):

```bash
python3 -m venv .venv-worker
. .venv-worker/bin/activate
pip install -r apps/worker/requirements.txt
export DATABASE_URL="postgresql+psycopg://planner:planner@localhost:5432/planner"
export REDIS_URL="redis://localhost:6379/0"
export PYTHONPATH="apps/worker:apps/api"
python -m worker.main
```

## Common commands

```bash
make up
make logs
make down
make migrate
make seed
make test-api
```

Production operations runbook: [`docs/architecture/production-runbook.md`](docs/architecture/production-runbook.md)

## Testing (API)

With the stack running (or at least a build of the `api` image), run the full suite inside the container so imports and `PYTHONPATH` match production:

```bash
make test-api
# equivalent:
docker compose --env-file env.example exec -e PYTHONPATH=/app api pytest -q
```

The API image sets `PYTHONPATH=/app` so the `app` package resolves. Tests use a file-backed SQLite database via the `client` and `db_session` fixtures (see [`apps/api/tests/conftest.py`](apps/api/tests/conftest.py)); they do not require Postgres on the host. The `client` fixture patches Redis with `fakeredis` so upload/job tests run without a real Redis broker.

`app.main` does not instantiate the FastAPI app at import time; use `uvicorn app.main:create_app --factory`. That way test collection does not open a DB connection before `DATABASE_URL` is overridden.
