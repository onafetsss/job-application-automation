# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-26
**Phase:** 1-Foundation
**Areas discussed:** Dry-run output, Job data model

---

## Dry-run Output

### Q1: Output format

| Option | Description | Selected |
|--------|-------------|----------|
| Terminal summary | Print each job: title, company, QUEUED or REJECTED + reason. Easy to scroll. | ✓ |
| HTML/text report file | Write a report file you can open and read through at your own pace | |
| Telegram preview | Send a summary message to your Telegram so you see it on mobile | |
| All of the above | Terminal output + report file + Telegram summary | |

**User's choice:** Terminal summary
**Notes:** Wants to scroll through quickly in the terminal. No external outputs for dry-run.

---

### Q2: Rejection detail level

| Option | Description | Selected |
|--------|-------------|----------|
| Just the reason | e.g. 'REJECTED: title mismatch' | ✓ |
| Reason + the failing value | e.g. 'REJECTED: title mismatch — found "Customer Service", not in include list' | |
| You decide | Whatever level of detail makes the filter easiest to tune | |

**User's choice:** Just the reason
**Notes:** Keep output concise and scannable.

---

### Q3: Trigger mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| CLI flag | python main.py --dry-run (easy to switch on/off per run) | ✓ |
| Config setting | dry_run: true in a config file (survives restarts, must be manually toggled off) | |
| Environment variable | DRY_RUN=1 python main.py | |

**User's choice:** CLI flag
**Notes:** Explicit per-run control. Off by default.

---

## Job Data Model

### Q1: Store full JD text?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — full JD text | Needed by Phase 2 AI to generate a tailored cover letter. Store raw + cleaned text. | ✓ |
| URL only, fetch on demand | Lighter storage, but requires a live fetch at cover letter generation time (can fail) | |
| You decide | Whatever's most reliable for downstream AI generation | |

**User's choice:** Yes — full JD text (Recommended)
**Notes:** Accepted the recommendation without modification.

---

### Q2: State machine complexity

| Option | Description | Selected |
|--------|-------------|----------|
| Simple | DISCOVERED → QUEUED \| REJECTED → APPLYING → SUBMITTED \| FAILED | ✓ |
| Detailed | Add PREPARING as a distinct state between QUEUED and APPLYING | |
| You decide | Whatever maps cleanest to the pipeline steps | |

**User's choice:** Simple
**Notes:** Fewer states, less complexity.

---

### Q3: Store generated artifacts?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — store everything | Full record: resume used, cover letter text, screening answers. Needed for Phase 4 dashboard detail view. | ✓ |
| Reference only | Store the template name and a log file path, not the full text | |
| You decide | Whatever supports the Phase 4 dashboard requirements | |

**User's choice:** Yes — store everything (Recommended)
**Notes:** Accepted the recommendation. Needed for the CRM dashboard.

---

## Claude's Discretion

- YAML config schema shape (exact field names, nesting)
- Fuzzy match library and similarity threshold
- SQLite access pattern (aiosqlite vs synchronous)
- Audit log column set beyond minimum success criteria

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
