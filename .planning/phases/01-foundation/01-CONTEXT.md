# Phase 1: Foundation - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the data contract every downstream phase depends on: SQLite schema (jobs table with full state machine), eligibility filter engine driven by a YAML config, cross-source deduplication logic, dry-run mode (CLI flag), and audit logging. No ingestion sources, no AI generation, no submission paths — pure infrastructure that must be in place before anything else can be built.

**Requirements in scope:** INGEST-04, FILTER-01, FILTER-02, FILTER-03, OPS-03

</domain>

<decisions>
## Implementation Decisions

### Dry-run Mode
- **D-01:** Dry-run is triggered via a CLI flag — `python main.py --dry-run`. Not a config file setting. Stays off by default; explicitly toggled per run.
- **D-02:** Output is terminal-only (no file, no Telegram). Print each job: title, company, and either QUEUED or REJECTED + reason (e.g. `REJECTED: title mismatch`).
- **D-03:** Rejection reason shows just the category (e.g. `REJECTED: location mismatch`) — not the failing value. Keep it scannable.

### Job Data Model
- **D-04:** Store full JD text per job lead (raw + cleaned). Required by Phase 2 AI cover letter generation. Do not rely on re-fetching at generation time.
- **D-05:** Job state machine uses simple states: `DISCOVERED → QUEUED | REJECTED → APPLYING → SUBMITTED | FAILED`. No intermediate PREPARING state.
- **D-06:** Jobs table stores the selected resume template name AND the full generated cover letter text AND screening answers. This populates the Phase 4 dashboard detail view without extra lookups.

### Eligibility Config
- **D-07:** Eligibility config is a YAML file (`eligibility.yaml`) — editable without code changes. Changes take effect on the next run. (Config UX not deeply discussed — planner has flexibility on exact schema shape, but it must cover title keywords include/exclude lists and location/remote flag.)

### Deduplication
- **D-08:** Dedup key is company + normalized title + location fuzzy match. (Dedup threshold not discussed — planner decides threshold using research guidance: fuzzy match on company + title + location with ~85% similarity floor.)

### Claude's Discretion
- Config YAML schema design (exact field names, nesting structure for include/exclude keyword lists)
- Fuzzy match library and similarity threshold (research recommended thefuzz or rapidfuzz)
- SQLite WAL mode and aiosqlite vs synchronous access pattern
- Audit log schema columns (beyond the success criteria requirements: job ID, source, timestamp, filter decision, reason)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` — Phase 1 requirements: INGEST-04, FILTER-01, FILTER-02, FILTER-03, OPS-03

### Research (critical for stack and architecture decisions)
- `.planning/research/STACK.md` — Stack decisions: SQLite + aiosqlite, fuzzy match library, Python 3.11
- `.planning/research/ARCHITECTURE.md` — State machine design, job lifecycle, SQLite-as-queue pattern, build order constraints
- `.planning/research/PITFALLS.md` — Deduplication cross-source problem (company+title+location key), silent failure modes

### Roadmap
- `.planning/ROADMAP.md` Phase 1 — Success criteria (5 observable behaviors that define done)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project. No existing code to reuse.

### Established Patterns
- None yet. Phase 1 establishes the patterns all later phases follow.

### Integration Points
- Phase 1 creates the SQLite DB and schema that every subsequent phase reads from and writes to.
- The `eligibility.yaml` config file path and structure must be documented clearly so Phase 2 ingestion code can locate and reload it.

</code_context>

<specifics>
## Specific Ideas

- The CLI entry point should accept `--dry-run` as a flag cleanly alongside other future flags (e.g., `--source gmail`, `--limit 10`)
- Terminal dry-run output should be scannable at a glance — one line per job, fixed-width formatting preferred

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Foundation*
*Context gathered: 2026-05-26*
