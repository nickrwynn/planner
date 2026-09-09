#!/usr/bin/env bash
# Expose local StudyFlows over HTTPS for iPad "Add to Home Screen" beta.
# Requires: stack up on :3000, cloudflared installed, web using /backend API proxy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_PORT="${WEB_PORT:-3000}"
WEB_URL="${WEB_URL:-http://127.0.0.1:${WEB_PORT}}"

echo "== StudyFlows PWA / homescreen tunnel =="
echo "Root: $ROOT"
echo "Web:  $WEB_URL"
echo

if ! curl -fsS -o /dev/null --max-time 3 "$WEB_URL" 2>/dev/null; then
  echo "ERROR: web is not reachable at $WEB_URL"
  echo "Start the stack first:  make up"
  echo "For same-origin API (required on iPad), set in .env then recreate web:"
  echo "  NEXT_PUBLIC_API_BASE_URL=/backend"
  echo "  API_INTERNAL_BASE_URL=http://api:8000"
  echo "  docker compose --env-file .env up -d --force-recreate web"
  exit 1
fi

if ! curl -fsS -o /dev/null --max-time 3 "$WEB_URL/manifest.webmanifest" 2>/dev/null; then
  echo "WARN: /manifest.webmanifest not OK — PWA install may be limited"
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found."
  echo "Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
  echo "  # Debian/Ubuntu example:"
  echo "  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null"
  echo "  # or download the linux amd64 binary from GitHub releases"
  echo
  echo "Alternate: ngrok http ${WEB_PORT}"
  exit 1
fi

PUBLIC_API="$(curl -fsS --max-time 3 "$WEB_URL" 2>/dev/null | head -c 0 || true)"
# Soft check that browser API base is same-origin (baked at next build).
if docker compose -f "$ROOT/docker-compose.yml" exec -T web printenv NEXT_PUBLIC_API_BASE_URL 2>/dev/null | grep -q '^/backend$'; then
  echo "OK: NEXT_PUBLIC_API_BASE_URL=/backend (same-origin proxy)"
else
  echo "WARN: web container NEXT_PUBLIC_API_BASE_URL is not /backend"
  echo "      iPad Safari cannot reach localhost:8000. Recreate web with:"
  echo "      NEXT_PUBLIC_API_BASE_URL=/backend"
  echo "      API_INTERNAL_BASE_URL=http://api:8000"
  echo "      (rebuild web image if the public env is compile-time baked)"
fi

echo
echo "Starting Cloudflare quick tunnel → $WEB_URL"
echo "Share the https://*.trycloudflare.com URL with testers."
echo "On iPad Safari: open link → Share → Add to Home Screen."
echo "Ctrl+C stops the tunnel."
echo

exec cloudflared tunnel --url "$WEB_URL"
