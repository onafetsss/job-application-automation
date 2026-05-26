---
phase: "01-foundation"
plan: "03"
type: execute
wave: 3
depends_on:
  - "01-01"
  - "01-02"
files_modified:
  - main.py
  - src/audit_log.py
  - tests/integration/test_dry_run_pipeline.py
autonomous: true
requirements:
  - FILTER-03
  - OPS-03

must_haves:
  truths:
    - "python main.py --dry-run prints QUEUED or REJECTED: <category> for each sample lead — one scannable line per job"
    - "python main.py --dry-run writes audit_log rows to the DB atomically — no submission rows created"
    - "python main.py (without --dry-run) also processes leads and writes DB rows but emits no stdout dry-run output"
    - "Duplicate sample leads are skipped with DEDUP_SKIP logged to audit_log (not printed to terminal)"
    - "After any run, the audit_log table contains job_id, source, event, reason, and timestamp for every processed lead"
    - "Editing eligibility.yaml and rerunning produces updated QUEUED/REJECTED decisions with no code changes"
  artifacts:
    - path: "main.py"
      provides: "CLI entry point with full filter pipeline — dedup + eligibility + audit + dry-run output"
      contains: "print_dry_run_row"
    - path: "src/audit_log.py"
      provides: "write_audit() async function + AuditLogEntry ORM model (complete implementation)"
      exports: ["write_audit", "AuditEvent", "AuditLogEntry"]
    - path: "tests/integration/test_dry_run_pipeline.py"
      provides: "End-to-end pipeline test covering QUEUED, REJECTED, and DEDUP_SKIP paths"
      contains: "test_dry_run_queues_eligible_lead"
  key_links:
    - from: "main.py"
      to: "src/filter/eligibility.py"
      via: "check_eligibility() call in run() async function"
      pattern: "from src\\.filter\\.eligibility import check_eligibility"
    - from: "main.py"
      to: "src/filter/dedup.py"
      via: "is_duplicate() + hash_url() calls before eligibility check"
      pattern: "from src\\.filter\\.dedup import is_duplicate, hash_url"
    - from: "main.py"
      to: "src/audit_log.py"
      via: "write_audit() call for every filter decision"
      pattern: "from src\\.audit_log import write_audit, AuditEvent"
    - from: "src/audit_log.py"
      to: "src/queue/models.py"
      via: "Base inheritance for AuditLogEntry"
      pattern: "from src\\.queue\\.models import Base"
---

<objective>
Wire the complete dry-run pipeline: main.py processes sample leads through dedup + eligibility + audit logging, prints scannable terminal output, and proves the system end-to-end without any submission path.

Purpose: This is the phase's final deliverable. FILTER-03 (dry-run mode) and OPS-03 (full audit trail) are completed here. After this plan, running `python main.py --dry-run` against any batch of sample leads produces the exact output described in the phase success criteria: QUEUED/REJECTED rows in the DB, audit_log entries, and scannable terminal output.

Output: A complete, working dry-run pipeline. write_audit() is fully implemented (Plan 01 created the stub model; this plan adds the async write function). main.py is upgraded from its Plan 01 stub to a real pipeline that processes sample leads. End-to-end integration test confirms all success criteria.
</objective>

<execution_context>
@/Users/stefano/.claude/get-shit-done/workflows/execute-plan.md
@/Users/stefano/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/ROADMAP.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-CONTEXT.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-01-SUMMARY.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-02-SUMMARY.md
</context>

<interfaces>
From Plans 01 and 02 — contracts the executor MUST use without re-reading the source files:

src/filter/eligibility.py:
  def check_eligibility(title: str, location: str | None, jd_text: str | None, config: EligibilityConfig) -> FilterResult
  # FilterResult.passed: bool
  # FilterResult.reason: str | None  — "title_mismatch" | "location_mismatch" | "keyword_blocklist" | None

src/filter/dedup.py:
  DEDUP_THRESHOLD = 85
  def hash_url(url: str) -> str
  async def is_duplicate(session: AsyncSession, company: str, title: str, location: str | None, url_hash: str) -> bool

src/filter/config_loader.py:
  def load_eligibility_config(path: str | Path) -> EligibilityConfig

src/queue/db.py:
  async def init_db(db_path: str) -> None
  def get_session_factory(db_path: str) -> sessionmaker  # returns AsyncSession factory

src/audit_log.py (Plan 01 stub — this plan completes it):
  class AuditEvent(str, Enum):
    DISCOVERED, FILTERED_PASS, FILTERED_REJECT, DEDUP_SKIP, QUEUED,
    DRY_RUN_WOULD_QUEUE, DRY_RUN_WOULD_REJECT
  class AuditLogEntry(Base): ...  # table already defined; write_audit() to be implemented here

main.py (Plan 01 stub — this plan upgrades it):
  # Currently: init_db() + print("DB initialised.") + return
  # Target: full pipeline with sample leads + dedup + eligibility + audit + dry-run output

Sample lead dict shape (used in main.py and tests):
  {
    "url": str,          # canonical apply URL
    "title": str,        # job title
    "company": str,      # company name
    "location": str | None,
    "source": str,       # e.g. "sample" or "linkedin_email"
    "clean_jd": str | None,  # plain-text job description
  }
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Complete write_audit() in audit_log.py and write the integration test</name>
  <files>
    src/audit_log.py,
    tests/integration/test_dry_run_pipeline.py
  </files>
  <read_first>
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md (section: src/audit_log.py pattern — read the full pattern block for write_audit() implementation)
    - src/audit_log.py (current state from Plan 01 — read to see what exists: AuditEvent enum, AuditLogEntry model; write_audit() function may or may not be present — check before writing)
    - src/queue/db.py (read to confirm get_session_factory() signature and AsyncSession import path)
  </read_first>
  <action>
    Write the integration test first (RED), then complete write_audit() (GREEN).

    tests/integration/test_dry_run_pipeline.py — write these end-to-end test cases using an in-memory DB:

    - test_dry_run_queues_eligible_lead: create an EligibilityConfig with roles.include=["Product Manager"], allow_remote=True. Run the full pipeline for one lead: title="Senior Product Manager", company="Acme Corp", location="Remote", source="sample", clean_jd="", url="https://example.com/job1". Provide mock dry_run=True. Assert: (1) audit_log table has one row with event="DRY_RUN_WOULD_QUEUE" and source="sample", (2) no row in jobs table (dry-run does not insert jobs).

    - test_dry_run_rejects_ineligible_lead: same setup but title="Junior Developer". Assert: audit_log has event="DRY_RUN_WOULD_REJECT" and reason="title_mismatch".

    - test_dedup_skip_logged: insert a Job row manually with url_hash matching the sample lead. Run pipeline for the same lead. Assert: audit_log has event="DEDUP_SKIP" for that lead; jobs table still has only one row (no duplicate inserted).

    - test_audit_log_has_required_fields: after running pipeline for any lead, query audit_log and assert every row has non-null: source, event, timestamp. Assert that rows for filter decisions have non-null reason or reason is None only when event is QUEUED/DRY_RUN_WOULD_QUEUE.

    NOTE: these tests exercise the full pipeline — they call the same functions main.py will call (is_duplicate, check_eligibility, write_audit) directly, not through subprocess. This is an integration test, not a CLI test.

    src/audit_log.py — complete the write_audit() async function if it is not already implemented:
    write_audit(session: AsyncSession, *, source: str, event: AuditEvent, job_id: str | None = None, reason: str | None = None, details: str | None = None) -> None.
    Creates AuditLogEntry row, calls session.add(entry). Also emits structlog log.info("audit", job_id=job_id, source=source, event=event.value, reason=reason). Does NOT call session.commit() — caller manages the transaction (per the async pattern from PATTERNS.md). Note: all calls to write_audit() must be inside the same session.begin() context as any job insert/update.
  </action>
  <behavior>
    - test_dry_run_queues_eligible_lead: audit_log has 1 row, event="DRY_RUN_WOULD_QUEUE", jobs table has 0 rows
    - test_dry_run_rejects_ineligible_lead: audit_log has 1 row, event="DRY_RUN_WOULD_REJECT", reason="title_mismatch"
    - test_dedup_skip_logged: audit_log has event="DEDUP_SKIP", jobs table count unchanged
    - test_audit_log_has_required_fields: every audit_log row has source, event, timestamp populated
  </behavior>
  <verify>
    <automated>cd "/Users/stefano/Documents/Workspaces/Job Application Automation" && uv run pytest tests/integration/test_dry_run_pipeline.py -v</automated>
  </verify>
  <acceptance_criteria>
    - All 4 pipeline integration tests pass
    - write_audit() does NOT call session.commit() (grep confirms: `grep "session.commit" src/audit_log.py` returns no matches)
    - write_audit() calls both session.add(entry) AND log.info("audit", ...) (grep confirms both)
    - AuditLogEntry rows always have source, event, timestamp set (enforced by nullable=False in model — grep confirms these columns are nullable=False)
  </acceptance_criteria>
  <done>Audit logging is fully functional: every filter decision produces a DB row and a structlog event. write_audit() is atomically committed with its parent transaction.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Complete main.py pipeline — dedup + eligibility + audit + dry-run terminal output</name>
  <files>
    main.py,
    tests/integration/test_cli.py
  </files>
  <read_first>
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md (section: main.py pattern — read the full pattern block for run() implementation, print_dry_run_row() format, and sample_leads list)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-CONTEXT.md (decisions D-01, D-02, D-03 for dry-run flag name, terminal output format, reason display format)
    - main.py (current state from Plan 01 stub — read to see what already exists before overwriting)
  </read_first>
  <action>
    Write CLI test first (RED), then complete main.py (GREEN).

    tests/integration/test_cli.py — write these subprocess-based CLI tests:

    - test_help_shows_dry_run_flag: subprocess.run(["uv", "run", "python", "main.py", "--help"], capture_output=True). Assert stdout contains "--dry-run".
    - test_dry_run_prints_queued_line: subprocess.run(["uv", "run", "python", "main.py", "--dry-run"], capture_output=True, cwd=project_root). Assert stdout contains "QUEUED" and "Senior Product Manager" (or whatever the first matching sample lead is).
    - test_dry_run_prints_rejected_line: same command. Assert stdout contains "REJECTED:" for at least one non-matching sample lead.
    - test_no_dry_run_no_terminal_output: subprocess.run(["uv", "run", "python", "main.py"], ...). Assert stdout does NOT contain "QUEUED" or "REJECTED:" — no dry-run output in non-dry-run mode (DB writes happen but no terminal output per D-02).

    main.py — upgrade from the Plan 01 stub to the full pipeline. Replace the stub run() body with the real implementation per PATTERNS.md:

    1. load_dotenv() at module top; structlog.configure() with JSONRenderer at module top (once).
    2. build_arg_parser(): --dry-run (store_true), --source (default "all"), --limit (type=int, default=0).
    3. print_dry_run_row(title, company, status, reason): format per D-02/D-03 — label is "QUEUED" or "REJECTED: {reason.replace('_', ' ')}" (underscore→space for display). Left-aligned to 30 chars, then "{title} @ {company}".
    4. run() async: (a) load DB_PATH, ELIGIBILITY_CONFIG_PATH from env; (b) await init_db(db_path); (c) load_eligibility_config(config_path); (d) session_factory = get_session_factory(db_path); (e) iterate over sample_leads (hardcoded list of 5-6 diverse leads: 2 that pass filter, 2 that fail on different reasons, 1 duplicate); (f) for each lead: compute url_hash, call is_duplicate() inside session.begin(), if duplicate → write_audit(DEDUP_SKIP) and continue; (g) call check_eligibility(); (h) if dry_run → print_dry_run_row() AND write_audit(DRY_RUN_WOULD_QUEUE or DRY_RUN_WOULD_REJECT); (i) if NOT dry_run AND passed → insert Job row with status=QUEUED and write_audit(QUEUED); if NOT dry_run AND failed → insert Job row with status=REJECTED and write_audit(FILTERED_REJECT). All DB operations inside same session.begin() per async pattern.

    Sample leads must include: at least one "Senior Product Manager" (passes), one "Software Engineer" (fails title), one "Product Manager" with "must be authorized to work in the US" in JD (fails location), and one duplicate of the first lead (same URL).

    The 5 phase success criteria from ROADMAP.md must all be satisfiable by running this pipeline against the hardcoded sample leads:
    - Success criterion 1: jobs table has QUEUED and REJECTED rows after non-dry-run
    - Success criterion 2: duplicate appears once, not twice
    - Success criterion 3: dry-run processes and logs without submitting
    - Success criterion 4: editing eligibility.yaml changes decisions on next run
    - Success criterion 5: every job has audit_log entry with job_id, source, timestamp, event, reason
  </action>
  <behavior>
    - test_help_shows_dry_run_flag: stdout contains "--dry-run"
    - test_dry_run_prints_queued_line: stdout has at least one line with "QUEUED" and a job title
    - test_dry_run_prints_rejected_line: stdout has at least one line with "REJECTED:"
    - test_no_dry_run_no_terminal_output: stdout contains neither "QUEUED" nor "REJECTED:"
    - python main.py --dry-run exits 0
    - python main.py (no flag) exits 0 and creates data/jobs.db with QUEUED and REJECTED rows
  </behavior>
  <verify>
    <automated>cd "/Users/stefano/Documents/Workspaces/Job Application Automation" && uv run pytest tests/integration/test_cli.py -v && uv run python main.py --dry-run && echo "--- DB check ---" && uv run python -c "import asyncio, aiosqlite; asyncio.run((lambda: asyncio.get_event_loop().run_until_complete(__import__('asyncio').sleep(0)))())" ; uv run python -c "import sqlite3; db=sqlite3.connect('data/jobs.db'); print('jobs:', db.execute('SELECT status, COUNT(*) FROM jobs GROUP BY status').fetchall()); print('audit:', db.execute('SELECT event, COUNT(*) FROM audit_log GROUP BY event').fetchall())"</automated>
  </verify>
  <acceptance_criteria>
    - All 4 CLI tests pass
    - Full pytest suite exits 0 (no regressions across all three test files)
    - python main.py --dry-run stdout contains at least one "QUEUED" line and at least one "REJECTED:" line
    - python main.py --dry-run stdout does NOT write any rows to the jobs table (dry-run = audit only)
    - python main.py (no flag) writes QUEUED and REJECTED rows to jobs table (confirmed by SQLite query)
    - audit_log table has rows for every lead processed (DRY_RUN_WOULD_QUEUE, DRY_RUN_WOULD_REJECT, and DEDUP_SKIP events present after one run with the duplicate sample lead)
    - REJECTED: reason display uses spaces not underscores (e.g. "REJECTED: title mismatch" not "REJECTED: title_mismatch")
    - Duplicate sample lead appears once in jobs table (not twice) after non-dry-run
  </acceptance_criteria>
  <done>The complete dry-run pipeline works end-to-end: sample leads flow through dedup, eligibility filter, audit logging, and either terminal output (dry-run) or DB insertion (live). All 5 phase success criteria are demonstrable.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| terminal stdout ← filter results | Dry-run output is user-facing; reason display must not leak raw config values or internal state |
| sample_leads list → DB insert | Lead data (title, company, JD) is treated as untrusted text input; must not be used in raw SQL |
| audit_log ← all events | Audit log must be append-only; no UPDATE/DELETE should ever target audit_log rows |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | Information Disclosure | dry-run terminal output | mitigate | print_dry_run_row() shows category only ("title mismatch", not the failing keyword from config) — per D-03; no raw config values or JD content echoed to terminal |
| T-03-02 | Tampering | audit_log append-only guarantee | mitigate | write_audit() only calls session.add() — never UPDATE or DELETE on audit_log; enforced in code; add a comment "# audit_log is append-only — never update or delete rows" in write_audit() |
| T-03-03 | Tampering | Job row insertion via sample data | mitigate | All Job field values inserted via SQLAlchemy ORM keyword args (no f-string SQL); company, title, location are stored as-is, never eval'd or executed |
| T-03-04 | Denial of Service | sample_leads hardcoded list size | accept | Phase 1 sample list is 5-6 items; O(N) scan is negligible; production ingestion (Phase 2) will use DB-backed lists with LIMIT |
| T-03-05 | Information Disclosure | structlog JSON output to stdout | accept | Phase 1 logs contain no PII beyond job title and company name (both are public information from job boards); no credentials, tokens, or personal data in log events |
| T-03-SC | Tampering | No new package installs in this plan | accept | Plan 03 adds no new dependencies to pyproject.toml; all imports are from Plan 01/02 packages |
</threat_model>

<verification>
After both tasks complete, verify the five phase success criteria from ROADMAP.md:

1. **Success criterion 1** — QUEUED and REJECTED rows in jobs table:
   `uv run python main.py && uv run python -c "import sqlite3; db=sqlite3.connect('data/jobs.db'); print(db.execute('SELECT status, COUNT(*) FROM jobs GROUP BY status').fetchall())"` → output includes ("QUEUED", N) and ("REJECTED", M).

2. **Success criterion 2** — Duplicate appears once:
   `uv run python -c "import sqlite3; db=sqlite3.connect('data/jobs.db'); rows=db.execute('SELECT company, title, COUNT(*) FROM jobs GROUP BY company, title HAVING COUNT(*) > 1').fetchall(); print('Duplicates:', rows)"` → empty list.

3. **Success criterion 3** — Dry-run processes without submitting:
   Run `uv run python main.py --dry-run` → stdout has QUEUED/REJECTED lines; jobs table has 0 rows (or same count as before dry-run).

4. **Success criterion 4** — Config changes take effect:
   Edit config/eligibility.yaml to add "Software Engineer" to roles.include; rerun `python main.py --dry-run`; observe the previously-rejected "Software Engineer" lead now shows QUEUED.

5. **Success criterion 5** — Full audit trail:
   `uv run python -c "import sqlite3; db=sqlite3.connect('data/jobs.db'); print(db.execute('SELECT job_id, source, event, reason, timestamp FROM audit_log LIMIT 5').fetchall())"` → each row has source, event, timestamp populated; reason is non-null for REJECT events.

Full pytest suite:
`uv run pytest tests/ -v` → all tests pass.
</verification>

<success_criteria>
- FILTER-03: `python main.py --dry-run` processes all sample leads through eligibility + dedup and prints one scannable line per lead, without creating any rows in the jobs table
- OPS-03: Every lead processed (queued, rejected, or dedup-skipped) produces an audit_log row with job_id (or null for dedup skips), source, event, reason, and timestamp
- Phase success criterion 2 (dedup): duplicate sample lead appears once in jobs table after non-dry-run
- Phase success criterion 4 (config hot-reload): editing eligibility.yaml and rerunning changes decisions without code changes
- All integration and CLI tests pass
- mypy and ruff pass with no errors: `uv run mypy src/ main.py` and `uv run ruff check src/ main.py tests/`
</success_criteria>

<output>
Create /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-03-SUMMARY.md when done
</output>
