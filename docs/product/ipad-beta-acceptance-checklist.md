# iPad Beta Acceptance Checklist

Use this checklist before promoting builds beyond internal TestFlight testers.

## Run metadata (required evidence header)

- Candidate SHA: `8054bee8f3a931b2dc1e6c9d4b22773d2c5fa358`
- GitHub Actions run URL (`ios-testflight.yml`): `https://github.com/nickrwynn/planner/actions/runs/23972405379` (failed at required secrets gate)
- TestFlight build number: `BLOCKED - no successful upload run yet`
- App Store Connect app version/build: `BLOCKED - no successful upload run yet`
- Tester name(s): `BLOCKED - pending internal TestFlight distribution`
- iPad model(s): `BLOCKED - pending internal TestFlight distribution`
- iPadOS version(s): `BLOCKED - pending internal TestFlight distribution`
- Test date (UTC): `2026-04-09T09:41:25Z`

## iPad web readiness

- [ ] App loads over HTTPS on iPad Safari.
- [ ] Layout is usable in portrait and landscape.
- [ ] Touch targets are usable for primary actions.
- [ ] Keyboard entry works for auth, notes, and search.
- [ ] File upload works from iPad Files picker.
- [ ] Search and AI ask flows return expected data.
- [ ] PWA manifest and icon endpoints resolve (`/manifest.webmanifest`, `/icon`, `/apple-icon`).

## iPad web smoke evidence log

| Flow | Result (pass/fail) | Evidence |
|---|---|---|
| Dashboard + nav | PARTIAL | Emulated iPad smoke spec exists: `apps/web/e2e/ipad-web-smoke.spec.ts` |
| Courses + tasks | PARTIAL | Emulated iPad smoke route coverage in `apps/web/e2e/ipad-web-smoke.spec.ts` |
| Resources upload/index/search | PARTIAL | Route-level coverage in smoke spec; real-device evidence pending |
| Search + AI ask | PARTIAL | Route-level coverage in smoke spec; real-device evidence pending |
| Notes/notebooks touch input | PARTIAL | Route-level coverage in smoke spec; real-device evidence pending |
| Portrait + landscape check | FAIL (pending) | Real iPad portrait/landscape evidence not yet recorded |

## iOS TestFlight build readiness

- [ ] `ios-testflight.yml` run is green.
- [ ] Build archive/export/upload completes.
- [ ] TestFlight build appears in App Store Connect.
- [ ] Build installs on at least one iPad test device.
- [ ] Required signing and GitHub secrets checklists are complete. (BLOCKED: both still open with missing artifacts/secrets)

## Core product smoke on iPad app

- [ ] Login/auth session is stable.
- [ ] Dashboard renders without blocking UI errors.
- [ ] Resource upload -> indexing -> search roundtrip succeeds.
- [ ] Notes/notebooks flows are usable with touch input.
- [ ] No blocker-level crashes in a 15-minute walkthrough.

## Internal rollout gate

- [ ] Internal testers signed off with evidence.
- [ ] CI run URL, TestFlight build number, and install proof are attached.
- [ ] External tester rollout approved (optional, after internal pass).

Current blocker evidence:
- `gh workflow list` shows `CI` and `iOS TestFlight` workflows on remote.
- `gh workflow run ios-testflight.yml --ref main` dispatch now succeeds.
- Run `https://github.com/nickrwynn/planner/actions/runs/23972013710` failed at `Validate required secrets` (`Missing required secret: APPLE_TEAM_ID`).
- Run `https://github.com/nickrwynn/planner/actions/runs/23972118129` failed at `Validate required secrets` (`Missing required secret: APPLE_TEAM_ID`).
- Run `https://github.com/nickrwynn/planner/actions/runs/23972234629` failed at `Validate required secrets` (`Missing required secret: APPLE_TEAM_ID`).
- Run `https://github.com/nickrwynn/planner/actions/runs/23972405379` failed at `Validate required secrets` (`Missing required secret: APPLE_TEAM_ID`; all 8 required secret env vars were empty).
- `2026-04-04T06:03:11Z`: `gh secret list` recheck returned no configured repository secrets for iOS TestFlight.
- `2026-04-04T06:03:11Z`: no owner-provided signing artifacts or secrets became available, so no new dispatch was triggered (would not produce new evidence).
- `2026-04-09T09:10:16Z`: fresh `gh secret list` recheck still returned no configured repository secrets for iOS TestFlight.
- `2026-04-09T09:10:16Z`: latest run remained `23972405379` (failed at `Validate required secrets` with `Missing required secret: APPLE_TEAM_ID`).
- `2026-04-09T09:10:16Z`: no owner-provided signing artifacts were detected in `/home/hpc1/Documents/planner`, `/home/hpc1/Documents`, or `/home/hpc1/Downloads`, so dispatch remained intentionally paused.
- `2026-04-09T09:11:27Z`: local PHASE C preflight confirmed required owner inputs remained unavailable (`APPLE_TEAM_ID`, `APPSTORE_CONNECT_KEY_ID`, `APPSTORE_CONNECT_ISSUER_ID`, `IOS_CERTIFICATE_PASSWORD`, `CAP_SERVER_URL` all missing), so signed upload remains blocked upstream of workflow dispatch.
- `2026-04-09T09:27:29Z`: recheck confirmed blocker state unchanged (no configured iOS/TestFlight secrets, no signing artifacts detected, latest failed run still `23972405379`), so PHASE D/E remain gated by PHASE C.
- `2026-04-09T09:36:36Z`: blocker state revalidated unchanged (`gh secret list` empty, latest failed run still `23972405379`, no signing artifacts detected), so PHASE C remains the only active gate before D/E.
- `2026-04-09T09:37:44Z`: blocker state remained unchanged (`gh secret list` empty, no newer run than failed `23972405379`, and no signing artifacts detected), so PHASE D/E remain gated by PHASE C.
- `2026-04-09T09:40:13Z`: blocker state remained unchanged (`gh secret list` empty, latest run still failed `23972405379`, and no signing artifacts detected), so PHASE D/E remain gated by PHASE C.
- `2026-04-09T09:41:25Z`: blocker state remained unchanged (`gh secret list` empty, latest run still failed `23972405379`, and no signing artifacts detected), so PHASE D/E remain gated by PHASE C.
