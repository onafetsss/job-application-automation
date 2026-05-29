# Phase 05: VPS Deployment (24/7) - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning
**Source:** Interactive decision capture (main-context AskUserQuestion)

<domain>
## Phase Boundary

Deploy the existing, working agent stack to Stefano's always-on VPS so it runs 24/7 without his laptop. In scope: containerizing the FastAPI agent + Camoufox browser + APScheduler, deploying them onto the existing Hostinger VPS alongside its dockerized n8n, wiring headless Camoufox + noVNC for remote reCAPTCHA solving, secure transfer of the authenticated LinkedIn session and secrets, and confirming end-to-end autonomous operation with the laptop closed.

Out of scope: the Phase 4 dashboard CRM / Kalibrr / generic-form work; building new apply capabilities; CI/CD pipelines beyond a simple deploy/restart story.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Target environment
- Deploy to Stefano's **existing Hostinger VPS** — the same box already running his n8n automations.
- n8n there runs via **Docker / docker-compose**. The agent stack must be added as ADDITIONAL compose services that coexist with the existing n8n WITHOUT disrupting current automations. Reuse the existing reverse proxy where sensible.
- The agent's n8n workflows can run on the existing n8n instance (no second n8n).

### reCAPTCHA remote solving
- **noVNC in the browser.** Camoufox runs on a virtual display (Xvfb) inside its container; noVNC exposes that display over the web. When the LinkedIn applier hits reCAPTCHA → job goes NEEDS_HUMAN (already built in Phase 03) → Telegram message includes a noVNC link → Stefano opens it in any browser (phone/laptop) and solves the challenge on the live session. No native VNC client app.

### Deploy scope
- **Full stack now:** FastAPI agent + Camoufox + APScheduler + the n8n workflows. Email/external-form applies run fully autonomous 24/7; LinkedIn Easy Apply runs with the reCAPTCHA pause path.

### Reliability
- Containers use a restart policy so the stack survives VPS reboots and crashes. Verify by rebooting the box.

### Secrets & session
- Transfer the authenticated LinkedIn session (`data/linkedin_profile/`) and all secrets (Gmail OAuth `.google_credentials.json`/`.google_token.json`, Telegram token/chat id, Anthropic key) to the VPS via a secure channel. NEVER commit these to git (they are currently untracked + unignored — add to .gitignore as part of this phase).

### Claude's Discretion
- Exact docker-compose structure, Dockerfile changes for Xvfb/noVNC, reverse-proxy/auth for the noVNC endpoint (must be access-controlled — it exposes a live logged-in browser), how the Gmail public HTTPS endpoint is exposed (existing proxy vs poll-only), and the deploy/update procedure.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### LinkedIn applier / reCAPTCHA pause (already built — Phase 03)
- `src/browser/linkedin_applier.py` — Camoufox session, frame-aware modal, `detect_recaptcha`, `RecaptchaDetected`
- `src/api/routes/apply/linkedin_apply.py` — `paused_human` / NEEDS_HUMAN handling
- `src/notify.py` — Telegram `send_telegram` (the noVNC link will be sent through this)
- `.planning/phases/03-linkedin-easy-apply/03-SDUI-FINDINGS.md` — live SDUI findings + the UNVERIFIED field-fill caveat to validate on the VPS

### Existing container/stack assets
- `docker/Dockerfile` and `docker/Dockerfile.api` — current images
- `docker-compose.yml` — current compose (API + n8n services)
- `03-01-PLAN.md` notes — Camoufox already set up with xvfb in Docker during Phase 03 foundation

### Stack guidance
- `CLAUDE.md` "Stack Patterns by Variant" — VPS deploy pattern, `--restart unless-stopped`, SQLite as volume-mounted file, Gmail `users.watch` needs public HTTPS
</canonical_refs>

<specifics>
## Specific Ideas
- Telegram reCAPTCHA alert should embed the noVNC URL so solving is one tap from the phone.
- The noVNC endpoint exposes a live, logged-in LinkedIn browser — it MUST be access-controlled (auth / IP allowlist / token), not open to the internet.
- Validate the Phase 03 residual caveat here: confirm live field-fill against the SDUI modal's custom/shadow-DOM controls during a real supervised apply (which will pause at reCAPTCHA anyway).
</specifics>

<deferred>
## Deferred Ideas
- Phase 4 dashboard CRM, Kalibrr native apply, generic web-form apply.
- Any multi-user / horizontal scaling concerns (single-user agent).
</deferred>

---

*Phase: 05-vps-deployment*
*Context gathered: 2026-05-29 via interactive decision capture*
