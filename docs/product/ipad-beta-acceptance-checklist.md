# iPad Beta Acceptance Checklist

Use this checklist before promoting builds beyond internal TestFlight testers.

## Run metadata (required evidence header)

- Candidate SHA: `41e0a62d103169f2bd8d7ad0df3c15f2f96d3f55`
- GitHub Actions run URL (`ios-testflight.yml`): `https://github.com/nickrwynn/planner/actions/runs/23972118129` (failed at required secrets gate)
- TestFlight build number: `BLOCKED - no successful upload run yet`
- App Store Connect app version/build: `BLOCKED - no successful upload run yet`
- Tester name(s): `BLOCKED - pending internal TestFlight distribution`
- iPad model(s): `BLOCKED - pending internal TestFlight distribution`
- iPadOS version(s): `BLOCKED - pending internal TestFlight distribution`
- Test date (UTC): `2026-04-04T05:19:29Z`

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
- `gh secret list` returned no configured repository secrets for iOS TestFlight.
