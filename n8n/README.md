# n8n Workflows — Job Application Automation

Six n8n workflow JSON files that orchestrate the full autonomous application pipeline.

---

## Prerequisites

Before importing workflows, ensure:

1. **Docker Compose running** — `docker compose up -d` from the project root
2. **Both containers healthy** — `docker compose ps` shows `api` and `n8n` as Up
3. **Gmail OAuth token** — run `python scripts/gmail_oauth.py` and complete the OAuth flow; token saved to `.google_token.json`
4. **Resume files placed** — `.pdf` or `.docx` resumes in the `resumes/` directory
5. **Profile configured** — `config/profile.yaml` edited with your real name, target roles, skills, projects, etc.
6. **Telegram bot created** — via @BotFather: `/newbot`, send `/start` to your new bot to initialize the chat

---

## Environment Variables

Add these to `.env` (alongside the existing vars from `.env.example`):

| Variable | Description | How to get |
|---|---|---|
| `N8N_ENCRYPTION_KEY` | n8n credential encryption key — generate ONCE and never regenerate | `openssl rand -hex 32` |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token | Telegram → @BotFather → `/newbot` |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | Send `/start` to your bot, visit `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | console.anthropic.com → API Keys |
| `APPLY_TO_EMAIL` | Email address where applications are sent (MVP: use your own email to review before forwarding) | Your email or `stefano.dsilva@gmail.com` |

**Also add `TELEGRAM_CHAT_ID` to the n8n service in `docker-compose.yml`** so n8n workflows can read it via `$env.TELEGRAM_CHAT_ID`:

```yaml
services:
  n8n:
    environment:
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - APPLY_TO_EMAIL=${APPLY_TO_EMAIL}
```

---

## Credential Setup in n8n UI

Open n8n at `http://localhost:5678`.

**1. FastAPI Key** (Header Auth — for routes that require API key)

Settings → Credentials → Add Credential → Header Auth
- Name: `FastAPI Key`
- Header Name: `X-API-Key`
- Header Value: value from `API_KEY` in your `.env` (leave blank if `API_KEY` is not set — auth is skipped in dev mode)

**2. Anthropic API** (Header Auth — for Claude calls)

Settings → Credentials → Add Credential → Header Auth
- Name: `anthropicApi`
- Header Name: `x-api-key`
- Header Value: your `ANTHROPIC_API_KEY`

**3. Telegram Bot**

Settings → Credentials → Add Credential → Telegram
- Name: `Telegram Bot`
- Bot Token: your `TELEGRAM_BOT_TOKEN`

**4. Gmail OAuth2** (for sending application emails)

Settings → Credentials → Add Credential → Gmail OAuth2
- Name: `Gmail OAuth2`
- Complete the OAuth2 flow using your Google account

---

## Workflow Import Order

Import in this order so the Error Handler is active before other workflows run:

1. `error-handler.json` — import and **activate immediately** (catches errors from all other workflows)
2. `heartbeat.json`
3. `gmail-ingest.json`
4. `jobspy-scrape.json`
5. `kalibrr-scrape.json`
6. `ai-apply-pipeline.json`

**To import:** n8n UI → Workflows → ⋮ menu → Import from File → select the JSON file

After importing each workflow, open it and verify the credential assignments under each HTTP Request / Telegram / Gmail node.

---

## Workflow Descriptions

| File | Trigger | What it does |
|---|---|---|
| `gmail-ingest.json` | Every 1 hour | Polls Gmail for job alert emails, extracts job listings with Claude Haiku, ingests leads with `apply_type=email` |
| `jobspy-scrape.json` | Every 4 hours | Scrapes Indeed via JobSpy, ingests leads |
| `kalibrr-scrape.json` | Every 4 hours | Scrapes Kalibrr, ingests leads |
| `ai-apply-pipeline.json` | Every 15 minutes | Picks up QUEUED email-apply jobs, fetches profile, selects resume, optionally generates screening answers, writes cover letter via Claude Sonnet, sends email, marks submitted, notifies via Telegram |
| `error-handler.json` | On any workflow error | Sends error details to Telegram |
| `heartbeat.json` | Every 30 minutes | Sends a Telegram ping to confirm the system is alive |

---

## Configuration Notes

**Changing search terms** — open `jobspy-scrape.json` or `kalibrr-scrape.json` in n8n UI and edit the `search_term` parameter in the scrape node.

**Changing schedule intervals** — open any workflow and click the Schedule Trigger node to adjust.

**Profile data** — edit `config/profile.yaml` directly. The `ai-apply-pipeline` calls `GET /profile` once per run, so changes take effect immediately on the next run. You do not need to edit any n8n workflow when your profile changes.

**Apply email destination** — in MVP mode, `APPLY_TO_EMAIL` is set to your own email so you can review generated cover letters and forward manually. To send directly to companies, you would need to extract company apply emails from job listings (future phase).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ECONNREFUSED` or `getaddrinfo ENOTFOUND api` | Workflow using `localhost` instead of Docker service name | All URLs must use `http://api:8000` — verify in each HTTP Request node |
| Credential errors on execute | Credential not configured or wrong name | Re-enter credentials in n8n UI; ensure names match exactly (`anthropicApi`, `FastAPI Key`, `Telegram Bot`, `Gmail OAuth2`) |
| JobSpy/Kalibrr returns 0 results | Possible IP block by job board | Check `warning` field in response; Telegram alert fires automatically |
| Gmail ingest finds no new messages | Gmail token expired | Re-run `python scripts/gmail_oauth.py` to refresh token |
| Cover letter generation fails | Anthropic API key wrong or rate limited | Check `ANTHROPIC_API_KEY` in credentials; check Anthropic console for errors |
| Heartbeat not arriving | n8n container not running or Telegram creds wrong | `docker compose ps` to check n8n status; verify bot token and chat ID |

---

## API Endpoint Reference

All FastAPI URLs use the Docker service name `api` on port 8000.

| Method | Path | Auth | Used by |
|---|---|---|---|
| GET | `/profile` | None | ai-apply-pipeline |
| POST | `/gmail/poll-gmail` | X-API-Key | gmail-ingest |
| POST | `/gmail/fetch-email-body` | X-API-Key | gmail-ingest |
| POST | `/ingest/ingest-lead` | X-API-Key | gmail-ingest, jobspy-scrape, kalibrr-scrape |
| POST | `/scrape/scrape-jobspy` | X-API-Key | jobspy-scrape |
| POST | `/scrape/scrape-kalibrr` | X-API-Key | kalibrr-scrape |
| GET | `/application/queued-email-jobs` | None | ai-apply-pipeline |
| POST | `/resume/select-resume` | None | ai-apply-pipeline |
| GET | `/resume/resume-file/{name}` | None | ai-apply-pipeline |
| POST | `/application/generate-screening-answers` | None | ai-apply-pipeline |
| POST | `/application/write-application` | None | ai-apply-pipeline |
| POST | `/application/mark-submitted` | None | ai-apply-pipeline |
