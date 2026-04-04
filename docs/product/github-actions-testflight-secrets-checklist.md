# GitHub Actions TestFlight Secrets Checklist

Use this checklist to verify every secret required by `.github/workflows/ios-testflight.yml`.

## Ownership and run metadata

- Candidate SHA: `41e0a62d103169f2bd8d7ad0df3c15f2f96d3f55`
- Repo admin owner: `nickrwynn`
- Date (UTC): `2026-04-04T05:18:49Z`

## Phase execution status

- [x] PHASE A complete: remote workflow discoverable (`iOS TestFlight`).
- [ ] PHASE C blocked: required repository secrets are still absent (`gh secret list` returned empty output).
- [ ] PHASE C recheck: no new secrets detected as of `2026-04-04T05:18:49Z`.

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
| Secret presence complete | FAIL | `gh secret list` output empty at 2026-04-04T05:18:49Z |
| Base64 decode checks pass | BLOCKED | Required secret values unavailable for local decode checks |
| CAP_SERVER_URL reachable | BLOCKED | `CAP_SERVER_URL` secret missing |
| First signed upload run | BLOCKED | Cannot dispatch `ios-testflight.yml` successfully until secrets are present |

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
