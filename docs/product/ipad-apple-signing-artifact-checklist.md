# iPad Apple Signing Artifact Checklist

Use this checklist to close Apple/App Store Connect/signing blockers before a real TestFlight upload.

## Ownership and run metadata

- Candidate SHA: `41e0a62d103169f2bd8d7ad0df3c15f2f96d3f55`
- Release owner: `nickrwynn` (GitHub)
- Apple account owner: `BLOCKED - not provided in repo evidence`
- Date (UTC): `2026-04-04T05:18:49Z`

## Phase execution status

- [x] PHASE A complete: `ios-testflight.yml` is active on remote (`gh workflow list` shows `iOS TestFlight`).
- [ ] PHASE B in progress: Apple signing artifacts must be populated manually by Apple account owner.
- [ ] PHASE B recheck: no new Apple artifact evidence captured in repository as of `2026-04-04T05:18:49Z`.

## Apple Developer + App Store Connect objects

- [ ] Apple Developer Program membership is active. (BLOCKED: no Apple evidence attached)
- [ ] Team ID captured (`APPLE_TEAM_ID`). (BLOCKED: no Team ID evidence)
- [x] Bundle ID created (`com.academicos.planner`) with matching capabilities. (verified in `apps/web/capacitor.config.ts`)
- [ ] App Store Connect app record exists for the same bundle ID. (BLOCKED: no ASC evidence attached)
- [ ] Internal TestFlight group exists. (BLOCKED: no ASC group evidence attached)

## App Store Connect API key artifacts

- [ ] API key created with app management permissions. (BLOCKED: no API key evidence)
- [ ] Key ID captured (`APPSTORE_CONNECT_KEY_ID`). (BLOCKED)
- [ ] Issuer ID captured (`APPSTORE_CONNECT_ISSUER_ID`). (BLOCKED)
- [ ] `.p8` key file exported and stored securely. (BLOCKED)
- [ ] `.p8` content base64-encoded for `APPSTORE_CONNECT_API_KEY_BASE64`. (BLOCKED)

## Signing certificate and provisioning profile artifacts

- [ ] iOS distribution certificate exists for the correct team. (BLOCKED: no cert evidence)
- [ ] Certificate exported as `.p12`. (BLOCKED)
- [ ] `.p12` password recorded in secure manager. (BLOCKED)
- [ ] `.p12` content base64-encoded for `IOS_CERTIFICATE_P12_BASE64`. (BLOCKED)
- [ ] Password mapped to `IOS_CERTIFICATE_PASSWORD`. (BLOCKED)
- [ ] App Store provisioning profile generated for `com.academicos.planner`. (BLOCKED)
- [ ] Provisioning profile base64-encoded for `IOS_PROVISIONING_PROFILE_BASE64`. (BLOCKED)

## Consistency checks (must pass)

- [ ] Team ID is identical across cert, profile, and App Store Connect. (BLOCKED)
- [ ] Bundle ID is identical across Capacitor config, profile, and App Store Connect app. (PARTIAL: Capacitor side verified only)
- [ ] Profile includes distribution signing for App Store/TestFlight upload. (BLOCKED)

## Evidence log

| Artifact | Status | Owner | Evidence reference |
|---|---|---|---|
| Team ID | BLOCKED | Apple account owner (TBD) | Missing from secrets and docs; `gh secret list` returned empty |
| Bundle ID | VERIFIED (repo) | Release owner | `apps/web/capacitor.config.ts` appId `com.academicos.planner` |
| ASC app record | BLOCKED | Apple account owner (TBD) | No App Store Connect evidence attached |
| API key (`.p8`) | BLOCKED | Apple account owner (TBD) | No artifact reference and no matching secret present |
| Distribution cert (`.p12`) | BLOCKED | Apple account owner (TBD) | No artifact reference and no matching secret present |
| Provisioning profile | BLOCKED | Apple account owner (TBD) | No artifact reference and no matching secret present |

## Required closure evidence for PHASE B

- Team ID value captured and matches cert/profile/ASC team.
- ASC app record URL or screenshot reference for `com.academicos.planner`.
- ASC internal TestFlight group reference.
- API key metadata captured (`APPSTORE_CONNECT_KEY_ID`, `APPSTORE_CONNECT_ISSUER_ID`) and `.p8` export confirmed.
- Distribution certificate export (`.p12`) confirmed with password owner reference.
- App Store provisioning profile reference for `com.academicos.planner`.

## Artifact preparation commands (owner-run)

```bash
# 1) Encode App Store Connect API key (.p8) for secret storage
base64 -w 0 AuthKey_<KEY_ID>.p8 > /tmp/APPSTORE_CONNECT_API_KEY_BASE64.txt

# 2) Encode distribution certificate (.p12)
base64 -w 0 dist-cert.p12 > /tmp/IOS_CERTIFICATE_P12_BASE64.txt

# 3) Encode App Store provisioning profile (.mobileprovision)
base64 -w 0 appstore.mobileprovision > /tmp/IOS_PROVISIONING_PROFILE_BASE64.txt
```
