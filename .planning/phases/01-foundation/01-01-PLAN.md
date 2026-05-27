---
phase: "01-foundation"
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - .env.example
  - .gitignore
  - Dockerfile
  - main.py
  - src/__init__.py
  - src/queue/__init__.py
  - src/queue/db.py
  - src/queue/models.py
  - src/filter/__init__.py
  - src/audit_log.py
  - tests/__init__.py
  - tests/unit/__init__.py
  - tests/integration/__init__.py
  - config/eligibility.yaml
autonomous: true
requirements:
  - OPS-03

must_haves:
  truths:
    - "uv run python main.py --dry-run exits without error after this plan (no filter logic yet — just boots)"
    - "data/jobs.db is created with all three tables: jobs, applications, audit_log"
    - "WAL mode is active on the database (PRAGMA journal_mode returns WAL)"
    - "All src/__init__.py and package __init__.py files exist so imports resolve"
    - "pyproject.toml declares all Phase 1 dependencies and ruff/mypy/pytest tool config"
  artifacts:
    - path: "pyproject.toml"
      provides: "dependency declarations and tool config"
      contains: "[project]"
    - path: "src/queue/db.py"
      provides: "SQLite engine, WAL mode, init_db(), get_session_factory()"
      exports: ["get_engine", "init_db", "get_session_factory"]
    - path: "src/queue/models.py"
      provides: "Job, Application, EligibilityConfigSnapshot ORM models + JobStatus enum"
      contains: "class Job(Base)"
    - path: "src/audit_log.py"
      provides: "AuditLogEntry ORM model + AuditEvent enum (table creation only in this plan)"
      contains: "class AuditLogEntry(Base)"
    - path: "config/eligibility.yaml"
      provides: "stub eligibility config with roles.include, location, salary, keywords sections"
      contains: "roles:"
  key_links:
    - from: "src/queue/db.py"
      to: "src/queue/models.py"
      via: "Base.metadata.create_all import"
      pattern: "from src\\.queue\\.models import Base"
    - from: "src/audit_log.py"
      to: "src/queue/models.py"
      via: "Base inheritance"
      pattern: "class AuditLogEntry\\(Base\\)"
---

<objective>
Scaffold the entire project structure and implement the database layer — the foundation every downstream plan, phase, and service depends on.

Purpose: Phase 1 cannot proceed without the ORM models, DB engine, and package structure in place. This plan is the only plan that creates pyproject.toml, the directory tree, and the core DB module. All other plans import from these files.

Output: A bootable Python project with all directories, pyproject.toml, SQLite engine (WAL mode), three ORM models (Job, Application, AuditLogEntry), and a stub eligibility.yaml. Running `uv run python main.py --dry-run` succeeds after this plan (with a stub main.py that just boots the DB and exits).
</objective>

<execution_context>
@/Users/stefano/.claude/get-shit-done/workflows/execute-plan.md
@/Users/stefano/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/ROADMAP.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-CONTEXT.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md
@/Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-SKELETON.md
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Project scaffold — pyproject.toml, directories, .gitignore, .env.example</name>
  <files>
    pyproject.toml,
    .env.example,
    .gitignore,
    Dockerfile,
    src/__init__.py,
    src/queue/__init__.py,
    src/filter/__init__.py,
    tests/__init__.py,
    tests/unit/__init__.py,
    tests/integration/__init__.py
  </files>
  <read_first>
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md (sections: pyproject.toml pattern, .env.example pattern, directory structure)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/CLAUDE.md (Technology Stack table for exact versions)
  </read_first>
  <action>
    Create the project scaffold from scratch. No files exist yet — create all of them.

    pyproject.toml: Follow the pattern in PATTERNS.md exactly. Project name "job-agent", version "0.1.0", requires-python ">=3.11". Dependencies (core, not dev): aiosqlite>=0.20, sqlalchemy>=2.0, pydantic>=2.0, pyyaml>=6.0, rapidfuzz>=3.0, structlog>=24.0, python-dotenv>=1.0, tenacity>=8.0. Dev group: pytest>=8.0, pytest-asyncio>=0.23, ruff>=0.4, mypy>=1.10. Tool config: [tool.ruff] line-length=100, select=["E","F","I","UP"]; [tool.mypy] python_version="3.11", strict=true, ignore_missing_imports=true; [tool.pytest.ini_options] asyncio_mode="auto".

    .env.example: Exactly the pattern in PATTERNS.md — DB_PATH=data/jobs.db, ELIGIBILITY_CONFIG_PATH=config/eligibility.yaml, then commented-out Phase 2+ vars (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY, GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH).

    .gitignore: Include data/, .env, __pycache__/, *.db, .mypy_cache/, .ruff_cache/, browser_profiles/, *.pyc, dist/, .venv/.

    Dockerfile: Stub only — FROM python:3.11-slim, WORKDIR /app, COPY . ., RUN pip install uv, CMD ["python", "main.py"]. No multi-stage build needed yet.

    All __init__.py files: empty files to make packages importable.

    Do NOT use pip install — document that uv sync is the install command. Do NOT create a requirements.txt.

    After creating pyproject.toml, run: uv sync --group dev (this installs all deps and creates .venv).
  </action>
  <behavior>
    - uv sync --group dev exits 0 after pyproject.toml is written
    - python -c "import aiosqlite, sqlalchemy, pydantic, yaml, rapidfuzz, structlog, dotenv, tenacity" exits 0
    - .gitignore contains "data/" and ".env" as separate lines
    - pyproject.toml contains [tool.ruff], [tool.mypy], [tool.pytest.ini_options] sections
  </behavior>
  <verify>
    <automated>cd "/Users/stefano/Documents/Workspaces/Job Application Automation" && uv sync --group dev 2>&1 | tail -5 && uv run python -c "import aiosqlite, sqlalchemy, pydantic, yaml, rapidfuzz, structlog, dotenv, tenacity; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - uv sync --group dev exits 0 with no dependency errors
    - `python -c "import aiosqlite, sqlalchemy, pydantic, yaml, rapidfuzz, structlog, dotenv, tenacity"` exits 0
    - pyproject.toml contains `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` sections
    - .gitignore contains the lines `data/` and `.env` (verified with grep)
    - All __init__.py files exist: src/__init__.py, src/queue/__init__.py, src/filter/__init__.py, tests/__init__.py, tests/unit/__init__.py, tests/integration/__init__.py
  </acceptance_criteria>
  <done>Project installs cleanly with uv; all package structure exists; pyproject.toml is the single source of truth for deps and tool config.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: DB engine + ORM models — db.py, models.py, audit_log.py table definition, stub config + main.py boot check</name>
  <files>
    src/queue/db.py,
    src/queue/models.py,
    src/audit_log.py,
    config/eligibility.yaml,
    main.py,
    tests/integration/test_db_init.py
  </files>
  <read_first>
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md (sections: src/queue/db.py pattern, src/queue/models.py pattern, src/audit_log.py pattern, main.py pattern)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-CONTEXT.md (decisions D-04, D-05, D-06 for model field requirements)
  </read_first>
  <action>
    Implement four files following the PATTERNS.md specifications exactly.

    src/queue/models.py: Implement JobStatus enum (DISCOVERED, QUEUED, REJECTED, APPLYING, SUBMITTED, FAILED — per D-05), Job ORM model with all columns from PATTERNS.md including url_hash, title_normalized, company_normalized, location_normalized, raw_jd, clean_jd (per D-04), resume_template, cover_letter, screening_answers (per D-06, nullable), and the relationship to Application. Application ORM model with all columns. EligibilityConfigSnapshot ORM model for audit trail of config changes. All primary keys are UUID strings (str(uuid.uuid4()) default). UNIQUE constraint on url and url_hash columns of Job.

    src/queue/db.py: Implement get_engine() singleton, init_db() with WAL mode pragma and foreign_keys=ON pragma and Base.metadata.create_all, get_session_factory() returning AsyncSession factory with expire_on_commit=False. Follow the PATTERNS.md pattern exactly — module-level singleton _engine.

    src/audit_log.py: Implement AuditEvent enum (DISCOVERED, FILTERED_PASS, FILTERED_REJECT, DEDUP_SKIP, QUEUED, DRY_RUN_WOULD_QUEUE, DRY_RUN_WOULD_REJECT), AuditLogEntry ORM model extending Base (job_id nullable String, source String not-null, event String not-null, reason String nullable, timestamp DateTime not-null default utcnow, details Text nullable). Implement write_audit() async function with keyword-only args (source, event, job_id=None, reason=None, details=None) that adds to session AND emits structlog event. AuditLogEntry must use the same Base from src.queue.models so all tables are created together.

    config/eligibility.yaml: Full stub following the PATTERNS.md config pattern — roles.include with PM-related titles ("Product Manager", "Senior Product Manager", "Principal Product Manager", "Head of Product"), roles.exclude with junior-signal strings ("Internship", "Graduate Program", "Entry Level", "Junior", "0-2 years"), location section (allow_remote: true, allowed_locations: ["Philippines", "Manila", "Remote", "Worldwide"], blocked_phrases with US work authorization strings), salary section (skip_if_no_data: false, min_annual_usd: 0), keywords.blocklist (["Clearance required", "Security clearance"]).

    main.py: Stub entry point — imports argparse, asyncio, os, structlog, load_dotenv, init_db, get_session_factory, load_eligibility_config (from src.filter.config_loader — this module doesn't exist yet; handle ImportError gracefully or add a TODO comment). Implement build_arg_parser() with --dry-run, --source, --limit flags per PATTERNS.md. Implement run() async function that calls init_db() only (no filter logic yet — that comes in Plan 02). Implement main() calling asyncio.run(run(args)). DB_PATH and ELIGIBILITY_CONFIG_PATH read from env per PATTERNS.md. structlog configured with JSONRenderer at startup. For the Phase 1 stub: after init_db(), print "DB initialised." and return — no pipeline logic yet.

    tests/integration/test_db_init.py: Write one integration test: test_init_db_creates_tables — calls asyncio.run(init_db(":memory:")) (use in-memory DB for test isolation), then queries sqlite_master to assert tables "jobs", "applications", "audit_log" all exist. Also assert WAL mode is active by querying PRAGMA journal_mode.
  </action>
  <behavior>
    - tests/integration/test_db_init.py::test_init_db_creates_tables passes (jobs, applications, audit_log tables all created)
    - PRAGMA journal_mode returns "wal" after init_db()
    - python main.py --dry-run exits 0 and prints "DB initialised."
    - python main.py --help shows --dry-run, --source, --limit flags
    - Job model has url_hash column with unique=True
    - AuditLogEntry.__tablename__ == "audit_log"
  </behavior>
  <verify>
    <automated>cd "/Users/stefano/Documents/Workspaces/Job Application Automation" && uv run pytest tests/integration/test_db_init.py -v && uv run python main.py --dry-run && uv run python main.py --help | grep -E "dry-run|source|limit"</automated>
  </verify>
  <acceptance_criteria>
    - pytest tests/integration/test_db_init.py exits 0 — both table existence and WAL mode assertions pass
    - python main.py --dry-run exits 0 and prints exactly "DB initialised." to stdout
    - python main.py --help output contains "--dry-run", "--source", and "--limit"
    - src/queue/models.py contains `class Job(Base)`, `class Application(Base)`, `class EligibilityConfigSnapshot(Base)` and `class JobStatus(str, Enum)`
    - src/audit_log.py contains `class AuditLogEntry(Base)` and `class AuditEvent(str, Enum)` with DRY_RUN_WOULD_QUEUE and DRY_RUN_WOULD_REJECT members
    - config/eligibility.yaml contains `roles:` and `location:` top-level keys
  </acceptance_criteria>
  <done>Database initialises with all three tables in WAL mode. main.py boots cleanly. ORM models are the authoritative data contract for the entire system.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| filesystem → SQLite DB | DB file created on disk; must not be world-readable |
| environment → main.py | DB_PATH and config path read from env; must not allow path traversal |
| YAML file → Pydantic model | eligibility.yaml parsed; malformed input must surface errors, not silently use defaults |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | Information Disclosure | data/jobs.db | mitigate | Create data/ with 0700 permissions (mkdir with mode=0o700 in init_db); DB file inherits directory permissions; add data/ to .gitignore |
| T-01-02 | Tampering | config/eligibility.yaml YAML injection | mitigate | Use yaml.safe_load() (not yaml.load()); Pydantic model_validate() rejects unexpected fields; never exec() or eval() config values |
| T-01-03 | Elevation of Privilege | DB_PATH environment variable | mitigate | init_db() resolves path with pathlib.Path and calls mkdir(parents=True, exist_ok=True) — no shell expansion; never pass DB_PATH to a shell command |
| T-01-04 | Tampering | audit_log table | mitigate | No UPDATE or DELETE operations on audit_log anywhere in Phase 1 code; write_audit() only calls session.add() — append-only by convention enforced in code review |
| T-01-05 | Spoofing | CLI --dry-run argument | accept | argparse handles --dry-run as a boolean flag; no user-provided string data processed as code; low-value attack surface |
| T-01-SC | Tampering | uv/pip package installs | mitigate | All packages listed in pyproject.toml with minimum versions; executor runs slopcheck on new packages before install; rapidfuzz and structlog are well-established packages |
</threat_model>

<verification>
After both tasks complete:

1. uv sync --group dev installs cleanly (exit 0)
2. All package directories exist with __init__.py
3. pytest tests/integration/test_db_init.py -v passes
4. python main.py --dry-run exits 0, prints "DB initialised."
5. python main.py --help shows --dry-run, --source, --limit
6. data/ directory (or data/jobs.db) is created with restricted permissions (not world-readable)
7. config/eligibility.yaml is valid YAML (python -c "import yaml; yaml.safe_load(open('config/eligibility.yaml'))" exits 0)
</verification>

<success_criteria>
- Project installs from scratch with a single `uv sync --group dev` command
- SQLite DB is created on first run with jobs, applications, and audit_log tables
- WAL mode is confirmed active
- All ORM models match the canonical schema from PATTERNS.md
- AuditEvent enum includes all seven events including DRY_RUN_WOULD_QUEUE and DRY_RUN_WOULD_REJECT
- main.py CLI accepts --dry-run, --source, --limit without error
- config/eligibility.yaml is a valid, human-readable stub
</success_criteria>

<output>
Create /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-01-SUMMARY.md when done
</output>
