# GitHub Actions TestFlight Secrets Checklist

Use this checklist to verify every secret required by `.github/workflows/ios-testflight.yml`.

## Ownership and run metadata

- Candidate SHA: `8054bee8f3a931b2dc1e6c9d4b22773d2c5fa358`
- Repo admin owner: `nickrwynn`
- Date (UTC): `2026-04-09T09:41:25Z`

## Phase execution status

- [x] PHASE A complete: remote workflow discoverable and dispatch revalidated (`iOS TestFlight`, run `23972234629`).
- [ ] PHASE C blocked: required repository secrets are still absent (`gh secret list` returned empty output).
- [ ] PHASE C recheck: no new secrets detected as of `2026-04-09T09:10:16Z`.

## Required repository secrets

| Secret | Required format | Source artifact | Status |
|---|---|---|---|
| `APPLE_TEAM_ID` | Apple Team ID string | Apple Developer account | MISSING (not present in repo secrets) |
| `APPSTORE_CONNECT_KEY_ID` | Key ID string | ASC API key | MISSING (not present in repo secrets) |
| `APPSTORE_CONNECT_ISSUER_ID` | Issuer UUID | ASC API key | MISSING (not present in repo secrets) |
| `APPSTORE_CONNECT_API_KEY_BASE64` | base64 of `.p8` content | ASC API key file | MISSING (not present in repo secrets) |
| `IOS_CERTIFICATE_P12_BASE64` | base64 of `.p12` file | iOS distribution cert export | MISSING (not present in repo secrets) |
| `IOS_CERTIFICATE_PASSWORD` | plaintext secret | cert export password | MISSING (not present in repo secrets) |
| `IOS_PROVISIONING_PROFILE_BASE64` | base64 of `.mobileprovision` file | App Store provisioning profile | MISSING (not present in repo secrets) |
| `CAP_SERVER_URL` | HTTPS URL (not placeholder) | deployed web environment | MISSING (not present in repo secrets) |

## Local format verification commands

Run these checks before dispatching `ios-testflight.yml`:

```bash
# API key decodes and parses as a private key
echo "$APPSTORE_CONNECT_API_KEY_BASE64" | base64 --decode > /tmp/AuthKey.p8
openssl pkey -in /tmp/AuthKey.p8 -noout

# Certificate decodes into a readable PKCS#12 structure
echo "$IOS_CERTIFICATE_P12_BASE64" | base64 --decode > /tmp/dist-cert.p12
openssl pkcs12 -in /tmp/dist-cert.p12 -info -noout -passin pass:"$IOS_CERTIFICATE_PASSWORD"

# Provisioning profile decodes
echo "$IOS_PROVISIONING_PROFILE_BASE64" | base64 --decode > /tmp/profile.mobileprovision
file /tmp/profile.mobileprovision

# Hosted web URL is HTTPS and not placeholder
[[ "$CAP_SERVER_URL" == https://* ]] && [[ "$CAP_SERVER_URL" != "https://planner.example.com" ]]
```

## CI gate alignment checks

- [x] Secret names exactly match workflow `Validate required secrets` keys. (verified against `.github/workflows/ios-testflight.yml`)
- [ ] `CAP_SERVER_URL` is reachable and serves the web app. (BLOCKED: secret missing)
- [ ] Secrets are stored at repository or environment scope used by workflow. (BLOCKED: `gh secret list` returned no configured secrets)
- [ ] Last rotation date is recorded. (BLOCKED: secrets absent)

## Evidence log

| Check | Result | Evidence reference |
|---|---|---|
| Secret presence complete | FAIL | `gh secret list` output empty at `2026-04-09T09:10:16Z` |
| Base64 decode checks pass | BLOCKED | Required secret values unavailable for local decode checks |
| CAP_SERVER_URL reachable | BLOCKED | `CAP_SERVER_URL` secret missing |
| First signed upload run | BLOCKED | Latest run `23972405379` failed at `Validate required secrets` (`Missing required secret: APPLE_TEAM_ID`; all 8 required secret env vars empty) |

## Execution recheck notes (PHASE C)

- `2026-04-04T06:03:11Z`: `gh secret list` returned no configured repository secrets.
- `2026-04-04T06:03:11Z`: all 8 required TestFlight secrets remain missing at repository scope (`APPLE_TEAM_ID`, `APPSTORE_CONNECT_KEY_ID`, `APPSTORE_CONNECT_ISSUER_ID`, `APPSTORE_CONNECT_API_KEY_BASE64`, `IOS_CERTIFICATE_P12_BASE64`, `IOS_CERTIFICATE_PASSWORD`, `IOS_PROVISIONING_PROFILE_BASE64`, `CAP_SERVER_URL`).
- `2026-04-04T06:03:11Z`: latest run evidence revalidated from `23972405379` failed in `Validate required secrets` before build/sign stages.
- `2026-04-04T06:03:11Z`: dispatch was intentionally not rerun because no new secrets/artifacts were available to produce different CI evidence.
- `2026-04-09T09:10:16Z`: `gh secret list` still returned no configured repository secrets.
- `2026-04-09T09:10:16Z`: latest workflow remains `23972405379` (failure at `Validate required secrets`, `Missing required secret: APPLE_TEAM_ID`).
- `2026-04-09T09:10:16Z`: no signing artifacts were detected in `/home/hpc1/Documents/planner`, `/home/hpc1/Documents`, or `/home/hpc1/Downloads` for `AuthKey_*.p8`, `*.p12`, or `*.mobileprovision`.
- `2026-04-09T09:10:16Z`: dispatch intentionally not rerun because evidence is unchanged and would repeat the same secret-gate failure.
- `2026-04-09T09:11:27Z`: local secret-population preflight confirmed owner-only inputs were still unavailable (`APPLE_TEAM_ID`, `APPSTORE_CONNECT_KEY_ID`, `APPSTORE_CONNECT_ISSUER_ID`, `IOS_CERTIFICATE_PASSWORD`, `CAP_SERVER_URL` all missing in local execution environment), so `gh secret set` could not proceed.
- `2026-04-09T09:27:29Z`: recheck confirmed no repository secrets configured (`gh secret list` empty), latest run still `23972405379` failed at required-secret gate, and no signing artifacts were present in `/home/hpc1/Documents/planner`, `/home/hpc1/Documents`, or `/home/hpc1/Downloads`.
- `2026-04-09T09:36:36Z`: recheck confirmed blocker unchanged (`gh secret list` still empty, latest run still `23972405379` failed at `Validate required secrets`, and no `.p8`/`.p12`/`.mobileprovision` artifacts detected in `/home/hpc1/Documents/planner`, `/home/hpc1/Documents`, or `/home/hpc1/Downloads`).
- `2026-04-09T09:37:44Z`: blocker recheck unchanged (`gh secret list` empty, latest run unchanged at `23972405379` failure, no signing artifacts detected in monitored paths), so PHASE C remains active and workflow rerun stayed intentionally paused.
- `2026-04-09T09:40:13Z`: blocker recheck unchanged (`gh secret list` empty, latest run still `23972405379` failed at secret validation, and no owner signing artifacts detected in monitored paths), so PHASE C remains hard-blocked.
- `2026-04-09T09:41:25Z`: blocker recheck unchanged (`gh secret list` empty, latest run still `23972405379` failed at `Validate required secrets`, no signing artifacts detected in monitored paths), so PHASE C remains hard-blocked.

## Required closure evidence for PHASE C

- `gh secret list` shows all 8 required keys.
- Local decode checks pass for API key, cert, and profile payloads.
- `CAP_SERVER_URL` value is HTTPS and not placeholder.

## Secret population commands (owner-run)

```bash
gh secret set APPLE_TEAM_ID --body "<TEAM_ID>"
gh secret set APPSTORE_CONNECT_KEY_ID --body "<KEY_ID>"
gh secret set APPSTORE_CONNECT_ISSUER_ID --body "<ISSUER_UUID>"
gh secret set APPSTORE_CONNECT_API_KEY_BASE64 --body "$(cat /tmp/APPSTORE_CONNECT_API_KEY_BASE64.txt)"
gh secret set IOS_CERTIFICATE_P12_BASE64 --body "$(cat /tmp/IOS_CERTIFICATE_P12_BASE64.txt)"
gh secret set IOS_CERTIFICATE_PASSWORD --body "<P12_PASSWORD>"
gh secret set IOS_PROVISIONING_PROFILE_BASE64 --body "$(cat /tmp/IOS_PROVISIONING_PROFILE_BASE64.txt)"
gh secret set CAP_SERVER_URL --body "https://<your-hosted-planner-url>"

# verify presence after set
gh secret list
```
