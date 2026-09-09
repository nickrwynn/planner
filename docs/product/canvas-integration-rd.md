# Canvas Integration (OAuth2)

Status: **active** — OAuth2 is the primary connect path (Canvas API Policy requires OAuth for multi-user apps; PATs are optional/dev-only when schools still allow them).

## Goal

Import courses, assignments, due dates, and syllabi from Canvas into StudyFlows.

## Setup (developer key)

1. Ask your Canvas admin (e.g. TAMU IT) for an **API developer key**, or create one in Site Admin if you run open-source Canvas.
2. On the key, set **Redirect URI** to exactly:
   `http://localhost:8000/integrations/canvas/oauth/callback`
   (or your deployed API callback URL).
3. Put the key credentials in `env.example` / `.env`:

```bash
CANVAS_OAUTH_CLIENT_ID=...
CANVAS_OAUTH_CLIENT_SECRET=...
CANVAS_OAUTH_REDIRECT_URI=http://localhost:8000/integrations/canvas/oauth/callback
CANVAS_OAUTH_SUCCESS_URL=http://localhost:3000/courses?canvas=connected
CANVAS_OAUTH_FAILURE_URL=http://localhost:3000/courses?canvas=error
CANVAS_DEFAULT_BASE_URL=https://canvas.tamu.edu
# If the key requires scopes, list them space-separated:
# CANVAS_OAUTH_SCOPES=url:GET|/api/v1/courses url:GET|/api/v1/courses/:id/assignments ...
```

4. Restart the API (`make up` / compose recreate).
5. Open **Courses** → **Connect with Canvas OAuth** → approve → **Sync now**.

Tokens: access tokens expire in ~1 hour; we store the refresh token encrypted and refresh before sync.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/integrations/canvas/status` | connected?, oauth_configured?, last sync |
| `POST` | `/integrations/canvas/oauth/start` | `{ base_url? }` → authorize URL + state |
| `GET` | `/integrations/canvas/oauth/callback` | Canvas redirect; exchanges `code` for tokens |
| `POST` | `/integrations/canvas/oauth/qr` | Optional: paste mobile QR login URL → OAuth tokens |
| `PUT` | `/integrations/canvas` | Optional PAT fallback |
| `POST` | `/integrations/canvas/sync` | Upsert courses / assignments / syllabi |

OAuth follows Canvas’s documented flow: `GET /login/oauth2/auth` → callback with `code` → `POST /login/oauth2/token` (form-encoded) → refresh via `grant_type=refresh_token`.

## Mapping

| Canvas | StudyFlows |
|--------|-------------|
| Course | `courses` `source_type=canvas` |
| Assignment | `tasks` what/why/when + `logistics_json` |
| Syllabus body | `resources` `source_type=canvas_syllabus` |

## Notes for TAMU / SSO schools

- Self-serve **personal access tokens** are often disabled; use a school-issued developer key + OAuth.
- Mobile “QR for Mobile Login” is a one-time OAuth bootstrap for official apps; we expose it as an alternate connect path when `mobile_verify` authorizes your domain.
