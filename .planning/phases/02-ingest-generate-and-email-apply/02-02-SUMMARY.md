---
phase: 02-ingest-generate-and-email-apply
plan: "02"
subsystem: ingestion
tags: [gmail, oauth2, history-id, fastapi, polling, ingest]
dependency_graph:
  requires:
    - src/api/app.py (FastAPI app + get_session dependency — from plan 02-01)
    - src/api/schemas.py (PollGmailOut, FetchEmailBodyIn, FetchEmailBodyOut — from plan 02-01)
    - src/queue/models.py (AgentConfig model — from plan 02-01)
  provides:
    - src/ingestion/gmail_client.py (get_gmail_service, poll_gmail_since, fetch_message_body)
    - src/api/routes/gmail.py (POST /gmail/poll-gmail, POST /gmail/fetch-email-body)
    - scripts/gmail_oauth.py (one-time OAuth2 token acquisition)
  affects:
    - n8n gmail-ingest workflow (calls /gmail/poll-gmail hourly, then /gmail/fetch-email-body per message)
    - agent_config table (gmail_history_id key persisted across restarts)
tech_stack:
  added:
    - google-api-python-client>=2.100 (already installed in plan 02-01 — used here for Gmail API)
    - google-auth-oauthlib>=1.0 (already installed — used in gmail_oauth.py script)
    - google-auth>=2.20 (already installed — Credentials + Request token refresh)
    - tenacity>=8.0 (already installed — retry wrapper on token refresh)
  patterns:
    - historyId checkpoint pattern (Gmail API partial sync per Google docs)
    - 404 fallback pattern (reset baseline on expired historyId per RESEARCH.md Pitfall 1)
    - OPS-01 challenge detection (Gmail OAuth 401 → HTTP 503 challenge_detected)
    - AgentConfig key-value store for persistent checkpoint (session.merge upsert pattern)
key_files:
  created:
    - src/ingestion/gmail_client.py
    - src/api/routes/gmail.py (replaced stub)
    - scripts/__init__.py
    - scripts/gmail_oauth.py
    - tests/unit/test_gmail_client.py
    - tests/integration/test_gmail_endpoints.py
  modified:
    - src/api/routes/gmail.py (stub → full implementation)
    - src/ingestion/gmail_client.py (ruff format applied after creation)
decisions:
  - "_OAUTH_CHALLENGE_DETAIL constant extracted to avoid repeated long string and E501 lint errors — consistent OPS-01 message across all 401/auth error paths"
  - "get_gmail_service raises HttpError/Exception which the routes catch — keeps client logic clean and routes own HTTP error mapping"
  - "_refresh_credentials wrapped as separate function so tenacity @retry decorator applies without wrapping get_gmail_service entirely"
  - "poll_gmail_since uses recursive call on 404 rather than goto-style loop — cleaner reset semantics, max 1 level of recursion"
  - "Routes read historyId in one session.begin() block and write in a second — avoids holding a write lock during Gmail API calls"
metrics:
  duration: "18 minutes"
  completed: "2026-05-27T18:05:26Z"
  tasks_completed: 2
  files_created: 6
  files_modified: 1
---

# Phase 2 Plan 02: Gmail Ingestion Client and Endpoints Summary

**One-liner:** Gmail API OAuth2 client with historyId-based polling, 404 fallback, and two FastAPI endpoints (/poll-gmail, /fetch-email-body) that persist the historyId checkpoint in SQLite and return OPS-01 challenge signals on auth failure.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Gmail API client with OAuth2, historyId polling, and unit tests | c5a8796 | src/ingestion/gmail_client.py, scripts/gmail_oauth.py, tests/unit/test_gmail_client.py |
| 2 | Gmail route endpoints (/poll-gmail, /fetch-email-body) with integration tests | 931f2f5 | src/api/routes/gmail.py, tests/integration/test_gmail_endpoints.py |

## What Was Built

### Task 1: Gmail API client module and OAuth script

**src/ingestion/gmail_client.py** — Three exported functions:

- `get_gmail_service(token_path)`: Loads OAuth2 credentials from token JSON file. If expired with a refresh_token, calls `_refresh_credentials(creds)` (tenacity @retry with 3 attempts, exponential backoff 1–10s) and writes the refreshed token back to disk. Returns a Gmail API resource via `build("gmail", "v1", credentials=creds)`.

- `poll_gmail_since(service, start_history_id, sender_filter)`: First-run path (start_history_id=None) calls `messages.list()` to establish a baseline historyId and returns `([], historyId)`. Normal poll path calls `history.list()` with `historyTypes=["messageAdded"]` and pagination. For each message ID collected, fetches metadata headers and filters to only those where `sender_filter` appears in the `From` header. On HTTP 404, logs `gmail_history_id_expired` warning and recurses with `start_history_id=None` to reset baseline (RESEARCH.md Pitfall 1).

- `fetch_message_body(service, message_id)`: Calls `messages.get()` with `format="full"`, recursively searches MIME parts for `text/plain`, base64url-decodes the body, and extracts Subject and From headers. Returns `{"body_text", "subject", "sender"}`.

**scripts/gmail_oauth.py** — Standalone one-time script using `InstalledAppFlow.from_client_secrets_file()` with `access_type="offline", prompt="consent"` to obtain an offline refresh token. Writes token JSON to `GOOGLE_TOKEN_PATH` (default `.google_token.json`). Includes setup instructions and exit code 1 if credentials file is missing.

**tests/unit/test_gmail_client.py** — 5 unit tests, all passing:
1. `test_poll_gmail_first_run_baseline` — first run returns `([], "12345")`
2. `test_poll_gmail_history_returns_matching_messages` — sender filter correctly excludes non-LinkedIn senders
3. `test_poll_gmail_history_404_fallback` — 404 from history.list triggers baseline reset
4. `test_get_gmail_service_refreshes_expired_token` — expired creds trigger refresh + file write
5. `test_fetch_message_body_extracts_plain_text` — multipart message, text/plain extracted and base64url-decoded

### Task 2: Gmail FastAPI endpoints

**src/api/routes/gmail.py** — Replaces the stub with two POST endpoints:

- `POST /gmail/poll-gmail`: Reads `gmail_history_id` from `AgentConfig` (None on first run), calls `get_gmail_service()` then `poll_gmail_since()`, writes the new historyId back via `session.merge(AgentConfig(...))`, returns `PollGmailOut(message_ids, history_id)`. Gmail OAuth 401 → HTTP 503 `{"status": "challenge_detected"}` (OPS-01). Other HttpError → HTTP 502. Both endpoints protected by `verify_api_key` dependency (dev-mode bypass when `API_KEY` unset).

- `POST /gmail/fetch-email-body`: Calls `get_gmail_service()` then `fetch_message_body()`, returns `FetchEmailBodyOut(body_text, subject, sender)`. HTTP 404 on message-not-found. HTTP 503 on 401 auth challenge.

**tests/integration/test_gmail_endpoints.py** — 4 integration tests, all passing:
1. `test_poll_gmail_first_run` — first run passes `start_history_id=None` to `poll_gmail_since`
2. `test_poll_gmail_with_existing_history` — seeded `AgentConfig` row passed through to poll function
3. `test_fetch_email_body_success` — returns body_text, subject, sender from mocked service
4. `test_poll_gmail_auth_failure` — 401 from `get_gmail_service` returns HTTP 503 `challenge_detected`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused `os` import in gmail_client.py**
- **Found during:** Task 1 ruff check
- **Issue:** `import os` was included in the initial file but never used
- **Fix:** Removed the unused import
- **Files modified:** `src/ingestion/gmail_client.py`
- **Commit:** 931f2f5

**2. [Rule 1 - Bug] Line-length violations in gmail.py (E501)**
- **Found during:** Task 2 ruff check
- **Issue:** Six lines exceeded 100-char limit due to repeated `"Gmail OAuth token expired or revoked"` inline in `HTTPException` detail dicts
- **Fix:** Extracted the repeated string as `_OAUTH_CHALLENGE_DETAIL` module constant; applied to all six call sites
- **Files modified:** `src/api/routes/gmail.py`
- **Commit:** 931f2f5

## Human Verification Required

**The following checkpoint requires manual action before the Gmail ingestion vertical slice is operational:**

### What Was Built

The Gmail OAuth2 token acquisition script (`scripts/gmail_oauth.py`) and the Gmail API polling endpoints (`POST /gmail/poll-gmail`, `POST /gmail/fetch-email-body`) are fully implemented and unit/integration tested with mocked services. However, real Gmail API calls require a valid OAuth token, which must be obtained through a one-time browser-based consent flow.

### How to Verify

1. **Create a GCP project and enable Gmail API:**
   - Go to `console.cloud.google.com` → New Project (or use existing)
   - APIs & Services → Library → Search "Gmail API" → Enable

2. **Create OAuth 2.0 Client ID (Desktop app type):**
   - GCP Console → APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: Desktop app
   - Download the credentials JSON file

3. **Configure environment:**
   - Set `GOOGLE_CREDENTIALS_PATH=path/to/downloaded-credentials.json` in `.env`
   - Optionally set `GOOGLE_TOKEN_PATH=.google_token.json` (this is the default)

4. **Run the OAuth flow (one-time, local):**
   ```
   uv run python scripts/gmail_oauth.py
   ```
   - A browser window opens — select your Gmail account
   - Approve the `gmail.readonly` scope
   - Verify `.google_token.json` was created in the project root

5. **Start the API server:**
   ```
   uv run uvicorn src.api.app:app --port 8000
   ```

6. **Test `/poll-gmail`:**
   ```
   curl -X POST http://localhost:8000/gmail/poll-gmail
   ```
   **Expected:** JSON response with `message_ids` (possibly empty array on first run) and a `history_id` string.

   **First-run example:**
   ```json
   {"message_ids": [], "history_id": "123456789"}
   ```

7. **Test `/fetch-email-body` with a real message ID** (optional if `message_ids` was non-empty):
   ```
   curl -X POST http://localhost:8000/gmail/fetch-email-body \
     -H "Content-Type: application/json" \
     -d '{"message_id": "<id_from_poll_response>"}'
   ```
   **Expected:** JSON with `body_text`, `subject`, and `sender` fields.

### Resume Signal

Type **"approved"** if the Gmail OAuth flow works and `/poll-gmail` returns valid data (including `history_id` string in the response), or describe any issues encountered.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| T-02-06 (mitigated) | scripts/gmail_oauth.py | `.google_token.json` path written to GOOGLE_TOKEN_PATH env var; script instructs user to add to .gitignore; never logged |
| T-02-07 (mitigated) | src/ingestion/gmail_client.py | Offline refresh token used; token auto-refreshed on expiry via tenacity retry; 401 detection fires OPS-01 HTTP 503 |
| T-02-09 (mitigated) | src/api/routes/gmail.py + src/queue/models.py | historyId written via ORM parameterized query (session.merge); 404 fallback recovers from corrupted/expired historyId |

No new threat surface beyond plan's threat model.

## Self-Check: PASSED

- `src/ingestion/gmail_client.py` exists: FOUND
- `src/api/routes/gmail.py` exists: FOUND (stub replaced with full implementation)
- `scripts/gmail_oauth.py` exists: FOUND
- `scripts/__init__.py` exists: FOUND
- `tests/unit/test_gmail_client.py` exists: FOUND
- `tests/integration/test_gmail_endpoints.py` exists: FOUND
- commit c5a8796: FOUND (Task 1)
- commit 931f2f5: FOUND (Task 2)
- 5/5 unit tests passing: CONFIRMED
- 4/4 integration tests passing: CONFIRMED
- ruff check src/api/routes/gmail.py src/ingestion/gmail_client.py: PASSED
- ruff format --check: PASSED
