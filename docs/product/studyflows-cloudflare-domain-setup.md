# StudyFlows domain + Cloudflare Tunnel walkthrough

Goal: stable **`https://app.mystudyflow.app`** pointing at your Linux Docker stack, then use that as **`CAP_SERVER_URL`** for TestFlight.

Stack stays on this machine:

- Web: `http://127.0.0.1:3000`
- API: reached via Next `/backend` rewrite

---

## 0. Check the name is free

1. Open [https://www.cloudflare.com/products/registrar/](https://www.cloudflare.com/products/registrar/) (or any registrar).
2. Search **`studyflows.app`**.
3. If taken, pick an alternative now (examples: `getstudyflows.app`, `studyflows.io`) and use that everywhere below instead of `studyflows.app`.

---

## 1. Create / sign in to Cloudflare

1. Go to [https://dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up).
2. Use the same email you’ll manage the product with.
3. Complete email verification.

**Tip:** Buying the domain **through Cloudflare Registrar** is the simplest path (DNS is already on Cloudflare). You can also buy elsewhere and change nameservers — both work; Cloudflare-buy is fewer steps.

---

## 2. Purchase `studyflows.app`

### Option A — Buy on Cloudflare (recommended)

1. Dashboard → **Domain Registration** → **Register Domains**.
2. Search `studyflows.app` → **Purchase**.
3. Choose registration length (1 year is fine).
4. Enter registrant contact info accurately (ICANN requires real contact data).
5. Pay.
6. When done, the domain should appear under **Websites** with Cloudflare DNS already attached.

### Option B — Buy elsewhere (Namecheap, Google Domains/Squarespace, Porkbun, …)

1. Purchase `studyflows.app` at that registrar.
2. In Cloudflare: **Add a site** → enter `studyflows.app` → choose Free plan.
3. Cloudflare shows two **nameservers** (e.g. `ada.ns.cloudflare.com`, `bob.ns.cloudflare.com`).
4. At your registrar → DNS / Nameservers → switch from “default” to **Custom** → paste Cloudflare’s two nameservers → Save.
5. Wait until Cloudflare dashboard shows the zone as **Active** (often 5–30 minutes; can take up to 24–48h).

Do **not** continue to tunnel DNS routes until the zone is **Active**.

---

## 3. Decide hostnames

Use:

| Hostname | Purpose |
|---|---|
| `app.studyflows.app` | StudyFlows web app (PWA + TestFlight `CAP_SERVER_URL`) |
| `studyflows.app` | Optional later (marketing / redirect to `app.`) |

For beta you only need **`app.studyflows.app`**.

---

## 4. Install `cloudflared` on the Linux box

If you don’t already have a permanent binary:

```bash
curl -fsSL -o ~/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x ~/bin/cloudflared
mkdir -p ~/bin
# if curl wrote before mkdir, move:
mkdir -p ~/bin && mv -n ./cloudflared ~/bin/cloudflared 2>/dev/null || true
export PATH="$HOME/bin:$PATH"
cloudflared --version
```

(Or reuse `/tmp/cloudflared` if that binary still works.)

---

## 5. Log cloudflared into Cloudflare

On the Linux machine:

```bash
cloudflared tunnel login
```

- A URL prints / a browser opens.
- Log into Cloudflare → select the **`studyflows.app`** zone → Authorize.
- Credentials land in `~/.cloudflared/cert.pem`.

---

## 6. Create a named tunnel

```bash
cloudflared tunnel create studyflows
cloudflared tunnel list
```

Copy the **tunnel UUID** (looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).

This also creates `~/.cloudflared/<UUID>.json`.

---

## 7. Point DNS at the tunnel

```bash
cloudflared tunnel route dns studyflows app.studyflows.app
```

In Cloudflare → **DNS** → **Records** you should see a CNAME:

- **Name:** `app`
- **Target:** `<UUID>.cfargotunnel.com`
- **Proxy:** Proxied (orange cloud) is fine

---

## 8. Write tunnel config

Create `~/.cloudflared/config.yml` (replace `TUNNEL_UUID`):

```yaml
tunnel: TUNNEL_UUID
credentials-file: /home/hpc1/.cloudflared/TUNNEL_UUID.json

ingress:
  - hostname: app.studyflows.app
    service: http://127.0.0.1:3000
  - service: http_status:404
```

---

## 9. Make sure StudyFlows is running locally

```bash
cd ~/Documents/planner
docker compose --env-file .env ps
# web must be up on :3000 with:
#   NEXT_PUBLIC_API_BASE_URL=/backend
#   NEXT_PUBLIC_API_AUTH_MODE=bearer
curl -fsS -o /dev/null -w 'web:%{http_code} backend:%{http_code}\n' \
  http://127.0.0.1:3000/ http://127.0.0.1:3000/backend/health
```

Expect `200` for both.

---

## 10. Run the tunnel

Foreground (good for first test):

```bash
cloudflared tunnel run studyflows
```

Leave that terminal open. For a longer-lived beta later, install a user systemd service; not required for first bring-up.

---

## 11. Verify HTTPS

From any machine:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' https://app.studyflows.app/
curl -fsS -o /dev/null -w '%{http_code}\n' https://app.studyflows.app/backend/health
curl -fsS -o /dev/null -w '%{http_code}\n' https://app.studyflows.app/manifest.webmanifest
```

Expect `200`. In a browser: open `https://app.studyflows.app/login` → create account / sign in.

**iPad:** Safari → that URL → Share → Add to Home Screen.

---

## 12. Wire TestFlight `CAP_SERVER_URL`

Once step 11 passes, tell the agent (or set yourself):

```text
CAP_SERVER_URL=https://app.studyflows.app
```

Then run the one-shot GitHub secrets + `ios-testflight.yml` upload (signing files already in `~/studyflows-signing/`).

---

## Checklist (tick as you go)

- [ ] Domain purchased (`studyflows.app` or alternate)
- [ ] Cloudflare zone **Active**
- [ ] `cloudflared tunnel login` done
- [ ] Tunnel `studyflows` created
- [ ] DNS route `app.studyflows.app` created
- [ ] `~/.cloudflared/config.yml` written
- [ ] Docker web/API healthy on localhost
- [ ] `cloudflared tunnel run studyflows` running
- [ ] `https://app.studyflows.app` returns 200
- [ ] `https://app.studyflows.app/backend/health` returns 200
- [ ] Ready for `CAP_SERVER_URL` + TestFlight secrets upload

---

## Common failures

| Symptom | Fix |
|---|---|
| Domain not Active in Cloudflare | Nameservers still on old registrar — wait or re-check NS |
| `tunnel login` fails | Use a browser on any device; paste the URL from the terminal |
| HTTPS 502 | Docker web not on `127.0.0.1:3000`, or wrong `service:` in config |
| UI loads, API 401/fail | Confirm `NEXT_PUBLIC_API_BASE_URL=/backend` and bearer login |
| Works then dies later | Tunnel process stopped — start `tunnel run` again (or add systemd) |

---

## Security note

You are exposing a real login-capable app on the public internet. Keep **`AUTH_MODE=bearer`**, use strong passwords, and share the URL only with intended beta testers.
