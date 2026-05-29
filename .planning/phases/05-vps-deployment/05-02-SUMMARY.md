---
phase: 05-vps-deployment
plan: 02
subsystem: vps-display-stack
tags: [docker, supervisor, camoufox, novnc, gitignore, security]
requires: [05-01]
provides:
  - "docker/Dockerfile.browser (browser+API container image)"
  - "docker/supervisord.conf (5-process supervisor config)"
  - "CAMOUFOX_DISPLAY_MODE env gate in linkedin_applier"
  - "NOVNC_URL injection in reCAPTCHA Telegram alert"
  - "gitignored Gmail OAuth credential files"
affects:
  - "Wave 3 compose deploy (depends on these files)"
tech-stack:
  added: [xvfb, x11vnc, novnc, websockify, fluxbox, supervisor]
  patterns: ["env-gated headless mode", "build-arg VNC password via x11vnc -storepasswd"]
key-files:
  created:
    - docker/Dockerfile.browser
    - docker/supervisord.conf
  modified:
    - .gitignore
    - src/browser/linkedin_applier.py
    - src/api/routes/apply/linkedin_apply.py
decisions:
  - "headless gated on CAMOUFOX_DISPLAY_MODE==xvfb (False on VPS, 'virtual' locally)"
  - ".google_token.json matched via *token*.json glob (explicit line also present)"
metrics:
  tasks: 3
  files: 5
  completed: 2026-05-29
---

# Phase 05 Plan 02: VPS Display Stack Code Changes Summary

Env-gated Camoufox headless mode, noVNC URL in reCAPTCHA Telegram alerts, a new single browser+API container (Xvfb + fluxbox + x11vnc + noVNC + uvicorn under supervisor), and gitignored Gmail OAuth credentials — all done on the MacBook before any VPS work.

## What Was Built

### Task 1 — gitignore credential files (commit 57edfbd)
Appended `.google_credentials.json`, `.google_token.json`, and `*token*.json` to `.gitignore`. Verified `data/` already covers `data/linkedin_profile/`. The previously-untracked credential files now no longer appear in `git status`. Mitigates threat T-05-02-T.

### Task 2 — env-gate headless + noVNC URL (commit aae1d50)
- `src/browser/linkedin_applier.py`: resolves `_headless = False if CAMOUFOX_DISPLAY_MODE=="xvfb" else "virtual"` immediately before the `AsyncCamoufox` block; passes `headless=_headless`. Other args (`persistent_context`, `user_data_dir`, `humanize`, `os`) unchanged. Updated the T-03-05 docstring.
- `src/api/routes/apply/linkedin_apply.py`: the `RecaptchaDetected` branch reads `NOVNC_URL` from env; when set, the Telegram message includes an HTML `<a href>` clickable link; when empty, it degrades to the original plain-text message. The DB status transition and audit write are unchanged.

### Task 3 — Dockerfile.browser + supervisord.conf (commit b9f2364)
- `docker/supervisord.conf`: five programs in priority order xvfb(10) → fluxbox(20) → x11vnc(30) → novnc(40) → app(50). The `app` program sets `DISPLAY=:1` and `CAMOUFOX_DISPLAY_MODE=xvfb`.
- `docker/Dockerfile.browser`: `python:3.11-slim` base replicating Dockerfile.api, adds the display-stack apt packages, fetches Camoufox, bakes the VNC password from build-arg `VNC_PASSWD` via `x11vnc -storepasswd` (T-05-02-I mitigation), copies `supervisord.conf` to `/etc/supervisor/conf.d/app.conf`, exposes 8000 + 6080, CMD `supervisord -c /etc/supervisor/supervisord.conf`.

## Verification Results

| # | Check | Result |
|---|-------|--------|
| 1 | `git check-ignore -v .google_credentials.json` | match (`.gitignore:15`) |
| 2 | `git check-ignore -v .google_token.json` | match (`.gitignore:17` via `*token*.json`) |
| 3 | `grep CAMOUFOX_DISPLAY_MODE src/browser/linkedin_applier.py` | 3 matches |
| 4 | `grep NOVNC_URL src/api/routes/apply/linkedin_apply.py` | 3 matches |
| 5 | `docker/Dockerfile.browser` + `docker/supervisord.conf` exist | both present |

Additional checks:
- Both Python files parse clean (AST).
- Headless gate logic matrix verified: unset/empty/other → `"virtual"`; `xvfb` → `False`. Local macOS behavior unchanged.
- No credential files tracked by git (`git ls-files | grep google_*` → empty).

## Deviations from Plan

None functionally. Two minor notes:
- **`.google_token.json` matched via the `*token*.json` glob (line 17) rather than its own explicit line 16.** Both lines were added exactly as the plan specified; `git check-ignore` reports whichever rule matches first. The file is correctly ignored. Not a deviation — expected behavior of glob precedence.
- Plan line numbers (AsyncCamoufox ~591, Telegram ~214) matched the actual files exactly; no adaptation needed.

## Supervisor config note (for Wave 3)

The Dockerfile copies `supervisord.conf` to `/etc/supervisor/conf.d/app.conf` (an include), while CMD references `/etc/supervisor/supervisord.conf` (Debian's package default, which has `[include] files = /etc/supervisor/conf.d/*.conf`). Program definitions load via the include. The `[supervisord]` section inside `app.conf` is redundant-but-harmless. Written exactly as planned. Pitfall A6 (noVNC web-asset path `/usr/share/novnc`) is unverifiable on the Mac and will surface at `docker build` time on the VPS as the plan notes.

## Out of Scope (left untouched)

Unrelated working-tree changes were deliberately not staged: n8n workflow edits, `.continue-here.md` deletions, `.DS_Store`, `resumes/`, `.planning/graphs/`. No VPS/docker build or deploy was attempted (Wave 3).

## Self-Check: PASSED

- docker/Dockerfile.browser — FOUND
- docker/supervisord.conf — FOUND
- Commit 57edfbd — FOUND
- Commit aae1d50 — FOUND
- Commit b9f2364 — FOUND
