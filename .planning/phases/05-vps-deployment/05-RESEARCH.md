# Phase 05: VPS Deployment (24/7) - Research

**Researched:** 2026-05-29
**Domain:** Docker deployment on a shared Hostinger VPS — headful anti-detect browser (Camoufox/Firefox) under a virtual display made viewable via noVNC, coexisting with an existing Traefik-proxied n8n, secure secret/session transfer, restart-survivable reliability.
**Confidence:** MEDIUM-HIGH (recipe components HIGH; the *exact* live Hostinger box config is UNKNOWN and must be discovered at execution — Question 7).

## Summary

The deployment is feasible with the existing container assets plus a noVNC-capable browser container. The single biggest technical correction this research surfaces: **`headless="virtual"` (what the applier currently uses) cannot be viewed via VNC** — Camoufox spawns its own Xvfb hardcoded to a **1x1 pixel screen** (`camoufox/virtdisplay.py:33`, issue #458), so the display is unwatchable and unclickable. To meet the locked noVNC reCAPTCHA-solving requirement, the plan must **manually start an Xvfb display at a real resolution (1920x1080x24), set `DISPLAY=:1`, run a window manager (fluxbox), x11vnc, and noVNC/websockify, and launch Camoufox with `headless=False`** so it attaches to that controlled display. This is a known, well-documented pattern (Xvfb + fluxbox + x11vnc + noVNC under supervisor).

The Hostinger n8n one-click template runs n8n behind **Traefik** on ports 80/443, with services attached to an **external Docker network named `traefik-proxy`** and routed by `Host()` rules + Let's Encrypt (`certresolver=letsencrypt`). The agent stack adds itself as new compose services on that same external network with its own Traefik labels — n8n is never touched. The noVNC endpoint is secured at the proxy with a Traefik **basicauth** middleware (plus optional **ipallowlist**), served over the existing HTTPS. Secrets and the Firefox/Camoufox profile transfer via `rsync` over SSH into a host directory that is **bind-mounted** into the container; the SQLite DB and the LinkedIn profile must live on the **host's local ext4 filesystem** (not overlayfs/NFS) for WAL `fcntl` locking to work. Gmail stays on the **already-built historyId polling path** — no Pub/Sub endpoint needed.

**Primary recommendation:** Build a dedicated `browser` service (Xvfb+fluxbox+x11vnc+noVNC, Camoufox `headless=False` on `DISPLAY=:1`), attach all agent services to the external `traefik-proxy` network, route a `recaptcha.<domain>` subdomain to noVNC behind basicauth, bind-mount secrets + DB + profile from host ext4 with `restart: unless-stopped`, and keep Gmail on polling. **Do not assume the Hostinger config — discover it first (Question 7 commands) before editing anything.**

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTPS termination, TLS certs, routing, auth | Existing Traefik proxy | — | Already owns 80/443 on the box; reuse per locked decision. Never run a second proxy. |
| reCAPTCHA remote solving (live browser view) | `browser` container (Xvfb+x11vnc+noVNC) | Traefik (HTTPS + basicauth) | Display + VNC encode live in-container; Traefik only fronts it securely. |
| LinkedIn Easy Apply automation | `browser`/`api` container (Camoufox `headless=False`) | — | Camoufox must attach to the controlled X display in the same container as Xvfb. |
| Email/external-form autonomous apply | `api` container (FastAPI + scheduler) | — | Headless-safe; no display needed. |
| Job state, audit log | SQLite file on host ext4 bind-mount | `api` container (aiosqlite) | WAL needs real fcntl locking → host local FS, single writer. |
| Scheduling (apply window, polling) | In-container scheduler (APScheduler) or n8n cron | n8n on existing instance | Locked: reuse existing n8n; APScheduler optional in-process. |
| Gmail ingestion | `api` container (historyId polling) | — | Already built as polling; no public webhook required. |
| Secret/session storage | Host dir bind-mount (chmod 600) | — | Out of git; writable + persisted across restarts. |

## Standard Stack

### Core (OS-level packages added to the browser container)
| Package | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `xvfb` | Debian stable | Virtual X framebuffer — gives headful Firefox a display | The canonical headless-display tool; already in `Dockerfile.api`. [CITED: camoufox.com/python/virtual-display] |
| `x11vnc` | Debian stable | Exposes the running Xvfb display over the VNC protocol (port 5900) | Standard bridge from a live X display to VNC. [VERIFIED: web recipe, multiple sources] |
| `novnc` + `websockify` | Debian stable | HTML5 VNC client + WS→VNC bridge (port 6080) → view in any browser | The "view in browser" half of the locked noVNC decision. [VERIFIED: noVNC official repos] |
| `fluxbox` | Debian stable | Minimal window manager so the Firefox window maps/focuses and modal clicks land | Without a WM, the modal/reCAPTCHA window may not receive focus/clicks reliably. [VERIFIED: web recipe] |
| `supervisor` | Debian stable | Process manager to run Xvfb + x11vnc + fluxbox + noVNC + app together in one container | Standard pattern for multi-process display containers. [VERIFIED: web recipe] |

### Supporting (already pinned — do NOT change)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `camoufox` | >=0.4.11 | Anti-detect Firefox | Launch with `headless=False` on controlled `DISPLAY` (NOT `"virtual"`) for the VNC path. |
| `playwright` | ==1.58.0 | Camoufox engine | **Pinned exactly** — 1.60.0 crashes (camoufox#617, per 03-SDUI-FINDINGS). Keep pin. |
| `aiosqlite` | >=0.20 | Async SQLite | DB file on host ext4 bind-mount, WAL mode. |
| `fastapi` | >=0.100 | HTTP service | Existing `api` service. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `headless=False` on manual Xvfb | `headless="virtual"` | **Rejected for VNC path** — 1x1px display, unwatchable/unclickable (camoufox#458). Fine only for fully-headless runs with no human interaction. |
| Traefik basicauth | Tailscale / WireGuard tunnel to noVNC | More setup; phone access requires VPN client. Basicauth+HTTPS is simpler and meets "one tap from phone." |
| In-container APScheduler | Existing n8n cron | n8n already runs; locked decision allows reusing it. APScheduler avoids cross-container HTTP. Either is acceptable (Claude's discretion). |
| supervisor | docker-compose multi-container (separate Xvfb) | X display can't be shared across containers cleanly; co-locating display+app+vnc in one container via supervisor is the standard. |

**Installation (browser container Dockerfile additions):**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify fluxbox supervisor \
    && rm -rf /var/lib/apt/lists/*
```

**Version verification:** All five are standard Debian/Ubuntu apt packages (long-maintained, in main). `novnc` + `websockify` are the official noVNC project packages. No new PyPI/npm dependency is introduced by the deployment recipe itself — verify against the box's distro with `apt-cache policy xvfb x11vnc novnc websockify fluxbox supervisor` at execution.

## Package Legitimacy Audit

> The deployment recipe adds **OS apt packages only** — no new PyPI/npm packages. slopcheck targets language registries; apt packages from Debian `main` are distro-curated and not a hallucination vector. Audit below documents provenance.

| Package | Registry | Age | Source | slopcheck | Disposition |
|---------|----------|-----|--------|-----------|-------------|
| xvfb | Debian apt (main) | 20+ yrs (xorg) | x.org | n/a (apt) | Approved |
| x11vnc | Debian apt (main) | 18+ yrs | github.com/LibVNC/x11vnc | n/a (apt) | Approved |
| novnc | Debian apt (main) | 10+ yrs | github.com/novnc/noVNC | n/a (apt) | Approved |
| websockify | Debian apt (main) | 10+ yrs | github.com/novnc/websockify | n/a (apt) | Approved |
| fluxbox | Debian apt (main) | 20+ yrs | fluxbox.org | n/a (apt) | Approved |
| supervisor | Debian apt (main) | 15+ yrs | github.com/Supervisor/supervisor | n/a (apt) | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.
**Note:** If a plan task chooses to install noVNC from git (alpine path in some recipes) instead of apt, pin to a tagged release of `github.com/novnc/noVNC` + `github.com/novnc/websockify` — do not clone unpinned `master`.

## Architecture Patterns

### System Architecture Diagram
```
            Internet (phone / laptop)
                    │  HTTPS :443
                    ▼
        ┌───────────────────────────┐
        │   Traefik (existing)      │  ports 80/443, certresolver=letsencrypt
        │   external net:           │
        │   traefik-proxy           │
        └─────┬───────────┬─────────┘
              │           │
   Host(n8n.<d>)   Host(recaptcha.<d>)  ── basicauth + (opt) ipallowlist middleware
              │           │
              ▼           ▼
     ┌──────────┐   ┌──────────────────────────────────────┐
     │  n8n     │   │  browser container (NEW)              │
     │ (UNTOUCHED)│  │  supervisor:                         │
     └──────────┘   │   ├ Xvfb :1  1920x1080x24             │
                    │   ├ fluxbox  (DISPLAY=:1)             │
                    │   ├ x11vnc   :5900  (-rfbauth)        │
                    │   ├ noVNC    :6080  (websockify)──────┼─→ Traefik loadbalancer.port=6080
                    │   └ Camoufox headless=False DISPLAY=:1│
                    │        │ persistent_context           │
                    └────────┼──────────────────────────────┘
                             │  reads/writes
                    ┌────────▼───────────────────────────┐
                    │ host bind-mounts (ext4, chmod 600)  │
                    │  data/linkedin_profile/  (writable) │
                    │  data/jobs.db (WAL, single writer)  │
                    │  .google_token.json / creds         │
                    └─────────────────────────────────────┘

  api container (FastAPI + Gmail historyId polling + scheduler) ── Telegram out (httpx) ──→ sends noVNC URL on RecaptchaDetected
```
On reCAPTCHA: applier raises `RecaptchaDetected` → job → NEEDS_HUMAN → Telegram message embeds `https://recaptcha.<domain>/vnc.html` → Stefano opens it, solves on the live session.

### Recommended Project Structure (deltas only)
```
docker/
├── Dockerfile.browser      # NEW: api image + xvfb/x11vnc/novnc/fluxbox/supervisor + Camoufox
│                           #      (or fold into Dockerfile.api if api+browser share one container)
└── supervisord.conf        # NEW: Xvfb, x11vnc, fluxbox, noVNC, uvicorn programs
docker-compose.yml          # EDIT: add traefik-proxy external network + labels; restart policies
.gitignore                  # EDIT: add the secret/profile files (see Pitfall 4)
```

### Pattern 1: Manual Xvfb + noVNC for a viewable Camoufox
**What:** Run the display stack under supervisor; launch Camoufox `headless=False` against `DISPLAY=:1`.
**When to use:** Any browser run that may pause for a human (reCAPTCHA). This is THE locked path.
**supervisord.conf (verified recipe):**
```ini
# Source: dev.to/danielcristho/running-firefox-in-docker (adapted: Debian apt, uvicorn app)
[supervisord]
nodaemon=true

[program:xvfb]
command=/usr/bin/Xvfb :1 -screen 0 1920x1080x24
autorestart=true
priority=10

[program:fluxbox]
command=/usr/bin/fluxbox
environment=DISPLAY=":1"
autorestart=true
priority=20

[program:x11vnc]
command=/usr/bin/x11vnc -display :1 -rfbauth /root/.vnc/passwd -forever -shared -rfbport 5900
autorestart=true
priority=30

[program:novnc]
command=/usr/bin/websockify --web=/usr/share/novnc 6080 localhost:5900
autorestart=true
priority=40

[program:app]
command=uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000
environment=DISPLAY=":1"
autorestart=true
priority=50
```
**Camoufox launch change (in `linkedin_applier.py` apply()):**
```python
# CHANGE for VPS noVNC path: headless=False on the controlled display, NOT "virtual".
# DISPLAY=:1 is set in the app's environment (supervisor). Keep persistent_context + humanize.
async with AsyncCamoufox(
    headless=False,                 # attaches to the real Xvfb :1 — viewable via noVNC
    persistent_context=True,
    user_data_dir=self.user_data_dir,
    humanize=True,
    os="windows",
) as context:
    ...
```
> Make this controllable by env (e.g. `CAMOUFOX_HEADLESS`) so local dev can still use `"virtual"` while the VPS uses `False`. x11vnc with `-shared` allows the same display to be both automated and watched simultaneously — Stefano sees exactly the modal the applier is on.

### Pattern 2: Attach to the existing Traefik proxy (Hostinger model)
**What:** Add services to the **external** `traefik-proxy` network; route by Host() + Let's Encrypt; bind no host ports.
**Compose snippet (DISCOVER actual network/cert names first — Question 7):**
```yaml
# Source: hostinger.com/support — Connecting multiple Docker Compose projects using Traefik
services:
  browser:
    build: { context: ., dockerfile: docker/Dockerfile.browser }
    restart: unless-stopped
    networks: [traefik-proxy, agent-network]
    volumes:
      - ./data:/data
      - ./config:/app/config
      - ./resumes:/app/resumes
      - ./.google_token.json:/app/.google_token.json
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.recaptcha.rule=Host(`recaptcha.${TRAEFIK_HOST}`)"
      - "traefik.http.routers.recaptcha.entrypoints=websecure"
      - "traefik.http.routers.recaptcha.tls.certresolver=letsencrypt"
      - "traefik.http.services.recaptcha.loadbalancer.server.port=6080"
      # security middleware — Pattern 3
      - "traefik.http.routers.recaptcha.middlewares=recaptcha-auth"
      - "traefik.http.middlewares.recaptcha-auth.basicauth.users=${RECAPTCHA_HTPASSWD}"
networks:
  traefik-proxy:
    external: true        # DISCOVER exact name: docker network ls
  agent-network:
    driver: bridge
```
> **Verify the proxy is actually Traefik on the live box.** Hostinger's *default n8n template* uses Traefik, but Stefano may have a custom/older setup (nginx-proxy, Caddy, or Caddy from a different tutorial). Run the Question-7 discovery commands FIRST; the labels above only apply if Traefik is confirmed.

### Anti-Patterns to Avoid
- **`headless="virtual"` when a human must view/click:** 1x1px display (camoufox#458) — invisible and unclickable via VNC. Use manual Xvfb + `headless=False`.
- **Binding host ports 80/443 in the agent compose:** collides with Traefik. Let Traefik own them; expose only via labels.
- **Editing Hostinger's `/root/docker-compose.yml` (n8n's file):** keep the agent stack in its OWN compose project/dir; only join the shared external network. Never restart n8n's stack.
- **SQLite DB or Firefox profile on overlayfs / a Docker named volume backed by a non-local FS:** WAL needs real `fcntl` locking; overlay/NFS → silent corruption. Bind-mount from host local ext4.
- **No window manager:** Firefox window may not focus; modal clicks (reCAPTCHA checkbox) can miss. Run fluxbox.
- **Committing secrets:** `.google_credentials.json` / `.google_token.json` are currently NOT in `.gitignore` (see Pitfall 4).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Live browser view in web page | Custom screenshot-streaming endpoint | x11vnc + noVNC | Real interactive session; clicks/keys flow back. Screenshots are read-only. |
| Multi-process container startup | Bash `&` background hacks | supervisor | Restart-on-crash per program, ordered priority, log routing. |
| HTTPS + auth on the endpoint | Self-signed certs + custom auth | Existing Traefik basicauth + Let's Encrypt | Proxy already terminates TLS; htpasswd is one label. |
| Gmail real-time push | New Pub/Sub topic + public webhook + 7-day watch renewal | Existing historyId polling (`gmail_client.poll_gmail_since`) | Already built and working; push adds GCP infra + a renew cron for a single-user agent. |
| Virtual display sizing | Camoufox `"virtual"` | Manual `Xvfb :1 -screen 0 1920x1080x24` | Camoufox virtual is hardcoded 1x1 (#458). |

**Key insight:** Every piece of this deployment is a solved, packaged problem (Traefik labels, supervisor, noVNC). The only *code* change is the Camoufox `headless` flag and embedding the noVNC URL in the Telegram alert.

## Runtime State Inventory

> This phase relocates a running agent + its authenticated session/secrets to a new host. Not a rename — but session/secret/state transfer is the crux, so inventoried here.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `data/jobs.db` (SQLite, gitignored). `data/linkedin_profile/` (Firefox profile, authenticated LinkedIn session, gitignored). | Transfer profile dir to VPS via rsync; let DB initialize fresh OR transfer if history matters. Both on host ext4 bind-mount, writable + persisted. |
| Live service config | Existing n8n workflows live in `n8n_storage` volume on the VPS (not in this repo's git unless re-imported). Agent's n8n workflow JSONs exist in `n8n/workflows/` — must be imported into the EXISTING n8n instance, not a new one. | Import workflow JSONs into existing n8n via its UI/API; do not stand up a second n8n. |
| OS-registered state | None on the VPS yet (fresh deploy). Docker `restart: unless-stopped` + a running dockerd is the only OS registration needed for reboot survival. | Confirm `docker info` shows restart policy honored; verify by `reboot`. |
| Secrets/env vars | `.google_credentials.json`, `.google_token.json` (present, NOT gitignored), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`, `N8N_ENCRYPTION_KEY`, new `RECAPTCHA_HTPASSWD`, `TRAEFIK_HOST`. | rsync secret files to host (chmod 600); put env vars in a `.env` on the VPS (gitignored). Add credential JSONs to `.gitignore` THIS phase. |
| Build artifacts | Camoufox Firefox binary (~100MB) fetched at image build via `python -m camoufox fetch`. | Rebuilt in image on VPS; no transfer needed. Ensure build step runs on the VPS (or push image to a registry). |

**The canonical question — after files are deployed, what runtime state must move?** The **authenticated LinkedIn Firefox profile** (`data/linkedin_profile/`) and the **Gmail OAuth token** (`.google_token.json`). Re-authenticating LinkedIn headlessly on the VPS would itself trigger a challenge — so the *working, logged-in profile must be copied over intact*, not re-created.

## Common Pitfalls

### Pitfall 1: noVNC shows a black/blank or unclickable browser
**What goes wrong:** Using `headless="virtual"` → 1x1px Xvfb; or no window manager → Firefox window unmanaged/unfocused.
**Why it happens:** camoufox#458 hardcodes the virtual screen to 1x1; X without a WM doesn't give windows focus/decoration.
**How to avoid:** Manual `Xvfb :1 -screen 0 1920x1080x24` + fluxbox + Camoufox `headless=False` on `DISPLAY=:1`.
**Warning signs:** noVNC connects but shows tiny/black area; clicks in noVNC don't register on the modal.

### Pitfall 2: SQLite corruption / "database is locked" / "disk I/O error"
**What goes wrong:** WAL file locking fails on overlayfs or a network-backed volume.
**Why it happens:** WAL needs real POSIX `fcntl` locks + shared memory; overlayfs/NFS/CIFS don't honor them → corruption or I/O errors.
**How to avoid:** Bind-mount `data/` from the host's **local ext4** filesystem; single container is the only writer; keep WAL mode. Confirm `df -T` shows ext4 (not overlay/nfs) for the mount source.
**Warning signs:** `disk I/O error`, `database is locked`, `unable to open database file (14)`.

### Pitfall 3: Disrupting the running n8n while adding services
**What goes wrong:** Re-`docker compose up` on n8n's own file, port 80/443 collision, or wrong network attach restarts/breaks n8n.
**Why it happens:** Assuming a clean box; editing the shared compose file; binding the proxy ports.
**How to avoid:** Keep the agent in a separate compose project/dir; join only the external `traefik-proxy` network; never bind 80/443; discover the live config before any `up`. Take a snapshot of n8n's compose + `docker ps` output first.
**Warning signs:** `port is already allocated`; n8n becomes unreachable after deploy; Traefik 404/502 on the n8n host.

### Pitfall 4: Secrets committed to git
**What goes wrong:** `.google_credentials.json` and `.google_token.json` are present in the repo and **not in `.gitignore`** (current `.gitignore` covers only `data/`, `.env`, `*.db`, etc.). A `git add .` would commit live OAuth creds.
**Why it happens:** Gitignore predates these files.
**How to avoid:** As an explicit task this phase, add to `.gitignore`: `.google_credentials.json`, `.google_token.json`, and any `*token*.json`. Verify with `git status --ignored`. (Locked decision §Secrets requires this.)
**Warning signs:** `git status` lists the credential JSONs as untracked-and-stageable.

### Pitfall 5: reCAPTCHA appears mid-flow but the applier already submitted
**What goes wrong:** A single pre-loop reCAPTCHA check misses a challenge that appears on a later modal step.
**Why it happens / handled:** Already mitigated — `_navigate_modal` re-checks `detect_recaptcha(page)` at the TOP of every iteration (03-SDUI-FINDINGS §4). Preserve this when changing `headless`.
**Validation note:** The Phase 03 UNVERIFIED caveat — live field-fill against the SDUI custom/shadow-DOM controls — should be validated here during a real supervised apply (which will pause at reCAPTCHA anyway, giving Stefano the noVNC view to observe). Worst case is graceful `UnknownFormField` → SKIPPED, not a crash.

### Pitfall 6: Telegram noVNC link is unauthenticated or wrong host
**What goes wrong:** The link exposes a live logged-in LinkedIn browser to the open internet.
**How to avoid:** Route via HTTPS Traefik host behind basicauth (Pattern 3). Embed `https://recaptcha.<domain>/vnc.html` in `send_telegram`; browser prompts for the basicauth creds before showing the session.

## Code Examples

### Securing the noVNC endpoint (Traefik basicauth + optional IP allowlist)
```yaml
# Source: doc.traefik.io basicauth + ipallowlist middleware docs
# Generate hash on the VPS:  htpasswd -nB stefano   (then escape every $ as $$ in compose)
labels:
  - "traefik.http.middlewares.recaptcha-auth.basicauth.users=stefano:$$apr1$$xxxx$$yyyy"
  # optional second layer — only Stefano's home/mobile ranges:
  - "traefik.http.middlewares.recaptcha-ip.ipallowlist.sourcerange=1.2.3.0/24,127.0.0.1/32"
  - "traefik.http.routers.recaptcha.middlewares=recaptcha-ip,recaptcha-auth"
```
> **Recommended simplest-robust option:** basicauth + HTTPS (existing certresolver). Add `ipallowlist` only if Stefano has a stable IP — mobile carrier IPs rotate, so an allowlist can lock him out from his phone. Basicauth alone over HTTPS satisfies "must not be open."

### Secret + session transfer (rsync over SSH)
```bash
# From the MacBook — push profile + secrets to the VPS app dir (NOT into git).
# Stop the local agent first so the Firefox profile isn't mid-write.
rsync -avz --delete \
  "data/linkedin_profile/" \
  root@<vps>:/opt/job-agent/data/linkedin_profile/
rsync -avz .google_credentials.json .google_token.json \
  root@<vps>:/opt/job-agent/
ssh root@<vps> 'chmod 600 /opt/job-agent/.google_*.json && \
  chmod -R u+rwX /opt/job-agent/data/linkedin_profile'
# .env on the VPS holds TELEGRAM_*, ANTHROPIC_API_KEY, N8N_ENCRYPTION_KEY,
# RECAPTCHA_HTPASSWD, TRAEFIK_HOST — created on the box, gitignored.
```
> The Firefox profile must stay **writable** and **persisted** (bind-mount, not copied into the image) — Camoufox writes session/cookie updates on every run.

### Reliability / restart survival
```yaml
services:
  browser:
    restart: unless-stopped   # survives crash + VPS reboot (dockerd starts on boot)
  api:
    restart: unless-stopped
```
```bash
# Verify reboot survival (locked decision requires this):
sudo reboot
# after reconnect:
docker ps                      # browser + api + n8n all Up
docker logs job-agent-browser  # supervisor started Xvfb/x11vnc/novnc/uvicorn
curl -k https://recaptcha.<domain>/vnc.html   # 401 (basicauth) = endpoint live + secured
```

### Telegram noVNC link embed (in the RecaptchaDetected handler)
```python
# In the apply route's RecaptchaDetected branch (src/api/routes/apply/linkedin_apply.py):
novnc_url = os.environ.get("NOVNC_URL", "https://recaptcha.example.com/vnc.html")
await send_telegram(
    f"\U0001F6A8 reCAPTCHA on job <b>{job.title}</b>.\n"
    f"Solve it here (login required): {novnc_url}"
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `headless="virtual"` everywhere | Manual Xvfb+VNC for human-in-loop; `"virtual"` only for pure-headless | camoufox#458 (open) | Must split the two run modes by env flag. |
| Gmail polling everywhere | Push/watch is "best practice" generally | — | For a single-user agent, polling (already built) is simpler and reliable; push adds GCP Pub/Sub + a 7-day watch-renew cron for negligible gain. Stay on polling. |
| Per-app reverse proxy | Shared Traefik on external network (Hostinger model) | n8n template default | New services attach to `traefik-proxy`; no new proxy. |

**Deprecated/outdated:**
- `playwright==1.60.0`: crashes Camoufox (camoufox#617). Keep `==1.58.0` pin.
- Treating `headless="virtual"` as VNC-viewable: false (1x1px).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The VPS uses the **Hostinger default n8n template with Traefik** on `traefik-proxy` external network, `certresolver=letsencrypt` | Pattern 2 | HIGH — wrong proxy/network name → labels don't route; n8n could be disrupted. **MUST discover live (Q7) before editing.** |
| A2 | The VPS `data/` mount sits on **local ext4** (not a network/overlay volume) | Pitfall 2 | HIGH — SQLite/WAL corruption. Verify `df -T` on the mount. |
| A3 | x11vnc `-shared` lets Camoufox automate AND Stefano watch the same display simultaneously | Pattern 1 | MEDIUM — if not, switch to watch-only during the pause; automation already halted at reCAPTCHA so concurrent control is moot. |
| A4 | Stefano controls a DNS subdomain (e.g. `recaptcha.<his-domain>`) he can point at the VPS for Let's Encrypt | Pattern 2/3 | MEDIUM — without a domain, fall back to the n8n host's existing domain + a path prefix, or a Tailscale URL. |
| A5 | The existing authenticated `data/linkedin_profile/` transfers and remains valid on the VPS (no IP-based re-challenge) | Runtime State | MEDIUM — LinkedIn may challenge on new IP/geo; first supervised apply via noVNC is the validation, and the reCAPTCHA pause path already handles a challenge. |
| A6 | noVNC/websockify launched via `websockify --web=/usr/share/novnc 6080 localhost:5900` matches the Debian package layout | Pattern 1 | LOW — path may differ by distro; some packages ship `novnc_proxy`. Verify the launcher name/path on the box. |

## Open Questions

1. **One container or two?** Camoufox needs the X display, so the browser must live in the same container as Xvfb. Does the FastAPI `api` process also run there (single container, simplest — supervisor runs uvicorn too), or stay separate with the browser spawned as a sub-service?
   - Recommendation: **Single browser+api container** for the apply path simplicity; APScheduler/Gmail polling can live in it. Keep n8n separate.
2. **Domain/subdomain for noVNC?** (A4) — confirm Stefano has a domain pointed at the VPS.
   - Recommendation: reuse his existing domain with a `recaptcha.` subdomain; if none, Tailscale Funnel/Serve is the fallback for a secure URL.
3. **Build on VPS vs push image?** Camoufox fetch + apt install is a ~minutes build. Building on the box is simplest; a registry push avoids rebuilding on a low-RAM VPS.
   - Recommendation: build on the box if RAM allows (check Q7); else build locally and push to a private registry.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + docker compose on VPS | All services | ✓ (n8n already runs via it) | discover | — |
| Traefik reverse proxy on VPS | noVNC HTTPS + auth | UNKNOWN — assume default template | discover | nginx-proxy/Caddy → adjust labels |
| External `traefik-proxy` network | Service routing | UNKNOWN | discover | create + attach Traefik manually |
| DNS subdomain → VPS | Let's Encrypt cert | UNKNOWN (A4) | — | Tailscale Funnel URL |
| Sufficient RAM for Firefox+Xvfb | browser container | UNKNOWN | discover | swap; or build image off-box |
| SSH access to VPS | rsync transfer | assume ✓ | — | — |

**Missing dependencies with no fallback:** SSH to the VPS (assumed available — required for everything).
**Missing dependencies with fallback:** Traefik (→ adapt to actual proxy); DNS subdomain (→ Tailscale); on-box build RAM (→ registry push).

## Question 7 — Live Discovery Commands (RUN BEFORE EDITING ANYTHING)

> The plan MUST start with a read-only discovery task. Do not assume the Hostinger config.

```bash
# OS + resources
cat /etc/os-release; uname -a
free -h; nproc; df -hT            # RAM/CPU + filesystem TYPE of the data dir (ext4 vs overlay/nfs)

# Docker landscape
docker --version; docker compose version
docker ps -a                       # what's running (n8n? traefik? proxy name?)
docker network ls                  # find the external proxy network name (expect 'traefik-proxy')
docker network inspect traefik-proxy 2>/dev/null   # confirm n8n is attached + subnet

# Reverse proxy identification
docker inspect $(docker ps -q) --format '{{.Name}} {{.Config.Image}}' | grep -iE 'traefik|caddy|nginx'
ss -tlnp | grep -E ':80|:443'      # which container owns 80/443

# n8n install method + its compose file (DO NOT edit it)
ls -la /root/docker-compose.yml /opt/*/docker-compose.yml 2>/dev/null
docker inspect <n8n_container> --format '{{json .Config.Labels}}' | tr ',' '\n' | grep traefik
                                   # → reveals exact router/entrypoint/certresolver naming to mirror

# Traefik dynamic config / certresolver name
docker inspect <traefik_container> --format '{{json .Args}}'   # look for certificatesresolvers.<name>

# Existing domains in use (avoid collisions)
docker inspect <n8n_container> --format '{{json .Config.Labels}}' | grep -o 'Host(`[^`]*`)'
```
**Blocking checks:** filesystem type of `data/` mount (A2), exact proxy + network name (A1), certresolver name, available RAM (build feasibility). Capture this output into the plan before writing any compose labels.

## Project Constraints (from CLAUDE.md)
- **GSD workflow:** No direct repo edits outside a GSD command — execution must go through `/gsd-execute-phase`.
- **Camoufox is mandatory** (anti-detection) — do not substitute Playwright/Chromium for LinkedIn.
- **`--restart unless-stopped`** is the prescribed 24/7 pattern (Stack Patterns by Variant).
- **SQLite as a volume-mounted file** for persistence (Stack Patterns by Variant) — aligns with Pitfall 2 guidance.
- **Secrets never hardcoded / never in git** (python-dotenv; STACK + locked decision).
- **`playwright==1.58.0` pin** must be preserved (03-SDUI-FINDINGS, camoufox#617).

## Sources

### Primary (HIGH confidence)
- [Camoufox Virtual Display](https://camoufox.com/python/virtual-display/) — `headless="virtual"` requires Xvfb; spawns own display.
- [camoufox#458 — virtual display is 1x1px](https://github.com/daijro/camoufox/issues/458) — root cause for NOT using "virtual" for VNC; hardcoded `1x1x24` in `virtdisplay.py:33`.
- [Hostinger — Connecting multiple Docker Compose projects using Traefik](https://www.hostinger.com/support/connecting-multiple-docker-compose-projects-using-traefik-in-hostinger-docker-manager/) — external network `traefik-proxy`, exact labels, `certresolver=letsencrypt`.
- [Hostinger — How to Use the N8N VPS Template](https://www.hostinger.com/support/10473267-how-to-use-the-n8n-vps-template-at-hostinger/) — template uses Traefik on 80/443; n8n env in `/root/docker-compose.yml`.
- [Traefik BasicAuth middleware](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/basicauth/) — htpasswd label, `$$` escaping.
- [Gmail API — Configure push notifications](https://developers.google.com/workspace/gmail/api/guides/push) — watch needs Pub/Sub + 7-day renewal (why polling is simpler here).

### Secondary (MEDIUM confidence)
- [Running Firefox in Docker with GUI and noVNC — dev.to/danielcristho](https://dev.to/danielcristho/running-firefox-in-docker-yes-with-a-gui-and-novnc-5fk) — full Xvfb+fluxbox+x11vnc+noVNC supervisor recipe (adapted to Debian apt + uvicorn).
- [Research: SQLite WAL Mode Across Docker Containers — Simon Willison](https://simonwillison.net/2026/Apr/7/sqlite-wal-docker-containers/) — WAL needs real fcntl locking; local FS single-writer is safe.
- [How to Run SQLite in Docker — OneUptime](https://oneuptime.com/blog/post/2026-02-08-how-to-run-sqlite-in-docker-when-and-how/view) — named/bind volume guidance; avoid overlay/network FS.
- [PyVirtualDisplay](https://github.com/ponty/PyVirtualDisplay) — alternative Python Xvfb wrapper with `use_xauth`/VNC option (fallback to manual Xvfb).

### Tertiary (LOW confidence — verify on the box)
- [silentz/vnc-containers](https://github.com/silentz/vnc-containers), [zaoqi/x11-novnc-docker](https://github.com/zaoqi/x11-novnc-docker) — reference noVNC container layouts; exact launcher path (`websockify` vs `novnc_proxy`) varies by distro (A6).

## Metadata

**Confidence breakdown:**
- Standard stack (Xvfb/x11vnc/noVNC/fluxbox/supervisor): HIGH — long-standing apt packages, multiple consistent recipes.
- Camoufox `headless` correction: HIGH — confirmed via official docs + tracked issue #458.
- Traefik/Hostinger integration: MEDIUM — default template confirmed, but the *specific* live box must be discovered (A1).
- SQLite/WAL on Docker volumes: HIGH — consistent across SQLite forum + multiple writeups.
- Gmail polling-vs-push: HIGH — official docs + already-built polling in `gmail_client.py`.
- Secrets/session transfer: HIGH — standard rsync/bind-mount; gitignore gap verified in-repo.

**Research date:** 2026-05-29
**Valid until:** ~2026-06-28 (30 days; Hostinger template + Camoufox issue status may change — re-verify A1 and #458 if later).
