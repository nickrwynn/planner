# Linux Beta WIP Triage

Date (UTC): 2026-09-08
Scope: classify uncommitted work for solo Linux beta ASAP

## Classification summary

| Bucket | Purpose | Action for Linux beta |
|---|---|---|
| `core stability` | Upload/index reliability, contracts, CI e2e parity | Keep and verify |
| `optional beta UX` | Desktop/responsive/PWA polish that improves Linux use | Keep for beta comfort |
| `defer` | iOS/TestFlight packaging and Apple owner artifacts | Do not block Linux beta |

## Core stability (must land for beta)

- [`apps/api/alembic/versions/0018_allow_queued_lifecycle_state.py`](../../apps/api/alembic/versions/0018_allow_queued_lifecycle_state.py) — DB check constraint must allow `queued` (API already transitions to it).
- [`apps/api/app/api/routes/resources.py`](../../apps/api/app/api/routes/resources.py) — MIME fallback via filename when upload `content_type` is missing (Playwright/e2e and some browsers).
- [`apps/web/lib/types.ts`](../../apps/web/lib/types.ts) — Resource contract fields aligned with API (`user_id`, lifecycle error fields).
- [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — `AUTH_MODE=dev` for e2e compose stack.
- [`apps/web/e2e/full-flow.spec.ts`](../../apps/web/e2e/full-flow.spec.ts), [`apps/web/e2e/upload-search.spec.ts`](../../apps/web/e2e/upload-search.spec.ts) — richer upload failure diagnostics.
- Restore [`data/uploads/.gitkeep`](../../data/uploads/.gitkeep) so upload dir remains tracked empty.

## Optional beta UX (include if low risk)

- [`apps/web/app/globals.css`](../../apps/web/app/globals.css) — responsive breakpoints / safe-area / `100dvh` (helps smaller Linux windows).
- [`apps/web/app/layout.tsx`](../../apps/web/app/layout.tsx) — metadata/viewport polish.
- [`apps/web/app/manifest.ts`](../../apps/web/app/manifest.ts), [`apps/web/app/icon.tsx`](../../apps/web/app/icon.tsx), [`apps/web/app/apple-icon.tsx`](../../apps/web/app/apple-icon.tsx) — PWA manifest/icons (usable as installable web app on Linux).

## Defer (post Linux beta / iOS track)

- [`apps/web/capacitor.config.ts`](../../apps/web/capacitor.config.ts)
- [`apps/web/ios/`](../../apps/web/ios/) generated Capacitor project
- [`apps/web/e2e/ipad-web-smoke.spec.ts`](../../apps/web/e2e/ipad-web-smoke.spec.ts)
- Capacitor deps / `cap:*` scripts / `engines.node >=22` in [`apps/web/package.json`](../../apps/web/package.json) (CI web job uses Node 20)
- TestFlight / Apple signing checklist updates under `docs/product/ipad-*` and `github-actions-testflight-secrets-checklist.md`
- Architecture ship-gate evidence population (production NO-SHIP remains separate from solo Linux beta)
- Empty placeholder [`scripts/setup-desktop-stability.sh`](../../scripts/setup-desktop-stability.sh)
- Local-only [`.venv-ci/`](../../.venv-ci/) (gitignore; never commit)

## Notes

- Production ship-gate candidate docs remain bound to SHA `13caf46...` and are **out of scope** for solo Linux beta acceptance.
- iPad candidate SHA `8054bee...` and secret-gate failures are tracked but deferred until after Linux product validation.
