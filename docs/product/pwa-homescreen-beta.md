# PWA / Add to Home Screen beta (while waiting on Apple)

Use this path until Apple Developer membership is approved and TestFlight secrets exist.

StudyFlows already ships a web manifest (`/manifest.webmanifest`), icons, and `appleWebApp` metadata. Testers open an **HTTPS** URL in **Safari**, then **Share → Add to Home Screen**.

## Why HTTPS + same-origin API

- iOS only offers a solid Home Screen install experience over **HTTPS**.
- The iPad cannot call `http://localhost:8000`. The web app must talk to the API via a **same-origin** path: `/backend/*` (Next rewrite → API).

## Owner steps (you)

1. **Stack up locally** (or on a VPS):

```bash
make up
```

2. **Point the browser API base at `/backend`** in `.env`:

```bash
NEXT_PUBLIC_API_BASE_URL=/backend
API_INTERNAL_BASE_URL=http://api:8000
```

3. **Recreate / rebuild web** so the public env is applied (Next bakes `NEXT_PUBLIC_*` at build time in Docker):

```bash
docker compose --env-file .env up -d --build --force-recreate web
```

4. **Expose HTTPS** with Cloudflare quick tunnel:

```bash
chmod +x scripts/pwa-homescreen-beta.sh
./scripts/pwa-homescreen-beta.sh
```

Copy the printed `https://….trycloudflare.com` URL.

5. **On each iPad**
   - Open the URL in **Safari** (not Chrome).
   - Tap **Share → Add to Home Screen → Add**.
   - Launch from the Home Screen icon (standalone chrome).
   - Dismiss the in-app install hint if shown.

6. **Share with other beta testers** — send them the same HTTPS link + the Share → Add to Home Screen steps. No Apple review required.

7. **Per-user accounts (required)** — use bearer auth so testers do not see your Canvas:

```bash
AUTH_MODE=bearer
API_AUTH_MODE=bearer
NEXT_PUBLIC_API_AUTH_MODE=bearer
AUTH_JWT_SECRET=<strong-secret-32+-chars>
NEXT_PUBLIC_API_BASE_URL=/backend
```

Then migrate + recreate:

```bash
docker compose --env-file .env exec api alembic -c alembic.ini upgrade head
docker compose --env-file .env up -d --build --force-recreate api web
```

- Testers: open URL → **Create account** → connect **their** Canvas.
- You (owner): **Create account** once with `dev@example.com` to claim your existing data, then sign in.

### Notes

- Quick tunnels die when you stop `cloudflared` or reboot; for a stable URL use a named Cloudflare Tunnel or a real VPS + domain (then set that host as future `CAP_SERVER_URL`).
- Keep the machine running while testers use the app.
- This is **not** the native Capacitor shell: Pencil/on-device Vision land with TestFlight later; cloud OCR / web Pencil UX still apply in the PWA.
- Prefer invite-only links. Never leave a public URL on `AUTH_MODE=dev` (everyone shares one user).

## Agent / product follow-ups (parallel)

- Pencil UX + fast handwriting OCR (see iPad Pencil planning doc).
- TestFlight after Apple membership + signing secrets (no secret-recheck loops).

## Verify

```bash
curl -fsS -o /dev/null -w 'manifest:%{http_code}\n' http://localhost:3000/manifest.webmanifest
curl -fsS -o /dev/null -w 'icon:%{http_code}\n' http://localhost:3000/icon
curl -fsS -o /dev/null -w 'apple-icon:%{http_code}\n' http://localhost:3000/apple-icon
curl -fsS -o /dev/null -w 'backend-health:%{http_code}\n' http://localhost:3000/backend/health
```
