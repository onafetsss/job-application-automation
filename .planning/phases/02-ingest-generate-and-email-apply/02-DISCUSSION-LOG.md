# Phase 2: Ingest, Generate, and Email Apply - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 2-Ingest-Generate-and-Email-Apply
**Areas discussed:** Gmail ingestion model, Run model & scheduling, Resume library & AI selection, LinkedIn alert email parsing

---

## Gmail Ingestion Model

| Option | Description | Selected |
|--------|-------------|----------|
| Poll Gmail API | Check every N minutes via `users.messages.list`. Simple, no GCP/public endpoint needed. | ✓ |
| Pub/Sub push | Real-time via GCP Pub/Sub + Gmail watch. Requires GCP project, public HTTPS endpoint, 7-day watch renewal. | |

**Interval:** Every hour (user chose; lower API quota usage, fine for a job agent)

**Email identification:**

| Option | Description | Selected |
|--------|-------------|----------|
| Sender filter (`jobalerts-noreply@linkedin.com`) | Precise, no label setup required | ✓ |
| Gmail label | Requires manual Gmail filter rule setup | |
| Subject line keyword | Fragile to subject format changes | |

**State tracking:**

| Option | Description | Selected |
|--------|-------------|----------|
| Store last-seen historyId | Efficient — fetches only new messages since checkpoint | ✓ |
| Mark emails as read | Invasive — mutates inbox state | |
| Store processed message IDs | Fetches all matching emails every poll | |

**OAuth:** Offline refresh token in `.env` (user confirmed; service account requires Google Workspace).

**Jobs per email:** Claude decides (handle 1-to-many, safe default).

---

## Run Model & Scheduling

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent APScheduler daemon | In-process Python scheduler, one Docker container | |
| Docker + external cron | Per-run containers triggered by VPS cron | |
| n8n | Visual workflow orchestrator — user-initiated via freeform answer | ✓ |

**Notes:** User asked about n8n after initial options were presented. Discussion covered n8n Cloud vs self-hosted and role split.

**n8n hosting:**

| Option | Description | Selected |
|--------|-------------|----------|
| n8n Cloud | Hosted by n8n, always-on, no server management | |
| Self-hosted on VPS | Runs alongside Python service on same VPS | ✓ |

**Python role:**

| Option | Description | Selected |
|--------|-------------|----------|
| Python webhook service | n8n calls Python endpoints for filter/dedup/DB | |
| n8n owns everything it can | n8n handles all it can natively; Python handles DB + Camoufox | ✓ |

**Phase 1 bridge:**

| Option | Description | Selected |
|--------|-------------|----------|
| Expose Phase 1 as FastAPI service | Add FastAPI layer, n8n calls endpoints | ✓ |
| Replicate in n8n Code nodes (JavaScript) | Rewrite filter/dedup in JS; Phase 1 code unused | |

**Resume access for n8n:**

| Option | Description | Selected |
|--------|-------------|----------|
| Python endpoint serves resume content | `POST /select-resume` returns name + text | ✓ |
| n8n reads resume files directly | n8n reads from filesystem volume | |

**Claude API caller:**

| Option | Description | Selected |
|--------|-------------|----------|
| n8n via HTTP Request node | n8n builds prompts and calls Anthropic API | ✓ |
| Python handles all Claude API calls | Python service owns all AI logic | |

---

## Resume Library & AI Selection

| Format | Selected |
|--------|----------|
| 1–3 resumes, .docx | |
| 4+ resumes, .docx | |
| Mix of .docx and PDF | ✓ |

**Differentiation:**

| Option | Selected |
|--------|----------|
| Role type / industry focus | ✓ |
| Highlighted skills / keywords | |
| Claude decides | |

**Selection approach:**

| Option | Description | Selected |
|--------|-------------|----------|
| LLM prompt comparison | Send JD + resume summaries to Haiku, ask which fits | ✓ |
| Embedding similarity | Embed resumes + JD, cosine similarity | |

**Storage:**

| Option | Selected |
|--------|----------|
| Mounted volume path | |
| Git repo (committed) | ✓ |

**Notes:** User confirmed private repo — safe to commit resume files.

---

## LinkedIn Alert Email Parsing

| Option | Description | Selected |
|--------|-------------|----------|
| AI-assisted extraction | n8n strips to plain text → Haiku → structured JSON | ✓ |
| HTML scraper (BeautifulSoup4) | Fast but brittle to HTML template changes | |
| Hybrid: scraper with AI fallback | More code to maintain | |

**Fields extracted:** `title`, `company`, `location`, `url` (4 fields — sufficient for Phase 1 dedup + filter)

**URL handling:**

| Option | Selected |
|--------|----------|
| Store as-is; Phase 1 dedup canonicalizes | ✓ |
| Follow redirects to canonical URL | |

**Who calls Claude for parsing:**

| Option | Selected |
|--------|----------|
| n8n calls Claude API (HTTP Request node) | ✓ |
| Python handles email parsing | |

---

## Model Selection (emerged during discussion)

User asked for cost estimates at 1,000 applications. Discussion covered Haiku vs Sonnet vs GPT-4o.

| Task | Model | Cost/1,000 |
|------|-------|-----------|
| Email parsing | Haiku 3.5 | ~$1 |
| Resume selection | Haiku 3.5 | ~$1 |
| Cover letter | Sonnet 4.x | ~$15 |
| Screening answers | Haiku 3.5 | ~$3 |
| **Total** | | **~$20** |

User confirmed: **Sonnet for cover letters, Haiku for everything else.**

---

## Claude's Discretion

- FastAPI endpoint schema (request/response shapes)
- Stefano's profile format for AI prompts
- `apply_type` detection during ingestion
- OPS-01/OPS-02 implementation placement
- n8n workflow structure (one vs multiple workflows)
- Gmail `historyId` storage location
- Kalibrr scraper details

## Deferred Ideas

None — discussion stayed within phase scope.
