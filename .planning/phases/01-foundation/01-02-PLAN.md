---
phase: "01-foundation"
plan: "02"
type: execute
wave: 2
depends_on:
  - "01-01"
files_modified:
  - src/filter/config_loader.py
  - src/filter/eligibility.py
  - src/filter/dedup.py
  - tests/unit/test_eligibility.py
  - tests/unit/test_config_loader.py
  - tests/integration/test_dedup.py
autonomous: true
requirements:
  - INGEST-04
  - FILTER-01
  - FILTER-02

must_haves:
  truths:
    - "check_eligibility() returns FilterResult(passed=True) for a matching title + valid location"
    - "check_eligibility() returns FilterResult(passed=False, reason='title_mismatch') for a non-matching title"
    - "check_eligibility() returns FilterResult(passed=False, reason='location_mismatch') when location is blocked and allow_remote=false"
    - "check_eligibility() returns FilterResult(passed=False, reason='keyword_blocklist') when JD contains a blocked phrase"
    - "is_duplicate() returns True when the same url_hash already exists in the DB"
    - "is_duplicate() returns True when company+title+location fuzzy score >= 85 even with a different URL"
    - "load_eligibility_config() raises FileNotFoundError on missing file and ValidationError on invalid YAML schema"
  artifacts:
    - path: "src/filter/config_loader.py"
      provides: "load_eligibility_config() returning EligibilityConfig Pydantic model"
      exports: ["load_eligibility_config", "EligibilityConfig"]
    - path: "src/filter/eligibility.py"
      provides: "check_eligibility() pure function returning FilterResult"
      exports: ["check_eligibility", "FilterResult"]
    - path: "src/filter/dedup.py"
      provides: "is_duplicate() async function + hash_url() utility"
      exports: ["is_duplicate", "hash_url", "DEDUP_THRESHOLD"]
  key_links:
    - from: "src/filter/eligibility.py"
      to: "src/filter/config_loader.py"
      via: "EligibilityConfig parameter type"
      pattern: "from src\\.filter\\.config_loader import EligibilityConfig"
    - from: "src/filter/dedup.py"
      to: "src/queue/models.py"
      via: "Job model for DB query"
      pattern: "from src\\.queue\\.models import Job"
    - from: "src/filter/config_loader.py"
      to: "config/eligibility.yaml"
      via: "yaml.safe_load() + Pydantic model_validate()"
      pattern: "yaml\\.safe_load"
---

<objective>
Implement the eligibility filter engine — the three modules that decide whether a job lead is QUEUED or REJECTED, and whether it is a duplicate.

Purpose: This is the core decision logic of the entire system. FILTER-01 (title keywords), FILTER-02 (location), and INGEST-04 (cross-source deduplication) are all implemented here. These functions are called by main.py in Plan 03 to produce the dry-run output.

Output: Three fully-tested modules: config_loader.py (YAML→Pydantic), eligibility.py (pure filter function), dedup.py (async duplicate detector). All three are covered by unit and integration tests that pass before this plan is done.
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
</context>

<interfaces>
From Plan 01 — contracts the executor MUST use without re-reading the source files:

src/queue/models.py:
  class Job(Base):
    url_hash: Column(String(64), unique=True)
    company_normalized: Column(Text)
    title_normalized: Column(Text)
    location_normalized: Column(Text)

src/queue/db.py:
  get_session_factory(db_path: str) -> sessionmaker  # returns AsyncSession factory
  async def init_db(db_path: str) -> None

src/filter/config_loader.py (to be created in this plan):
  class EligibilityConfig(BaseModel):
    roles: RolesConfig        # .include: list[str], .exclude: list[str]
    location: LocationConfig  # .allow_remote: bool, .allowed_locations: list[str], .blocked_phrases: list[str]
    salary: SalaryConfig      # .skip_if_no_data: bool, .min_annual_usd: int
    keywords: KeywordsConfig  # .blocklist: list[str]

src/filter/eligibility.py (to be created in this plan):
  @dataclass
  class FilterResult:
    passed: bool
    reason: str | None  # "title_mismatch" | "location_mismatch" | "keyword_blocklist" | None

  def check_eligibility(title: str, location: str | None, jd_text: str | None, config: EligibilityConfig) -> FilterResult
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Config loader + eligibility filter (config_loader.py, eligibility.py) with unit tests</name>
  <files>
    src/filter/config_loader.py,
    src/filter/eligibility.py,
    tests/unit/test_eligibility.py,
    tests/unit/test_config_loader.py
  </files>
  <read_first>
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md (sections: src/filter/config_loader.py pattern, src/filter/eligibility.py pattern — read the full pattern blocks)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-CONTEXT.md (decisions D-03, D-07 for rejection reason format and config behavior)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/config/eligibility.yaml (the actual file to validate against)
  </read_first>
  <action>
    Write tests first (RED), then implement until tests pass (GREEN).

    tests/unit/test_config_loader.py — write these test cases before implementing config_loader.py:
    - test_loads_valid_yaml: create a temp eligibility.yaml with roles.include=["Product Manager"], call load_eligibility_config(), assert result.roles.include == ["Product Manager"]
    - test_raises_on_missing_file: call load_eligibility_config("nonexistent.yaml"), assert FileNotFoundError is raised
    - test_raises_on_empty_roles_include: create a temp yaml with roles.include=[], call load_eligibility_config(), assert pydantic.ValidationError is raised (the model_validator checks at least one role)
    - test_raises_on_missing_roles_key: create a temp yaml with only location: {allow_remote: true}, assert pydantic.ValidationError is raised

    tests/unit/test_eligibility.py — write these test cases before implementing eligibility.py:
    - test_pass_matching_title_remote: title="Senior Product Manager", location="Remote", jd_text="", config with roles.include=["Product Manager"], allow_remote=True → FilterResult(passed=True)
    - test_reject_title_mismatch: title="Software Engineer", location="Remote", jd_text="", config with roles.include=["Product Manager"] → FilterResult(passed=False, reason="title_mismatch")
    - test_reject_excluded_keyword_in_title: title="Product Manager Internship", location="Remote", jd_text="", config with roles.include=["Product Manager"], roles.exclude=["Internship"] → FilterResult(passed=False, reason="title_mismatch")
    - test_reject_jd_keyword_blocklist: title="Senior Product Manager", location="Remote", jd_text="Clearance required for this role", config with keywords.blocklist=["Clearance required"] → FilterResult(passed=False, reason="keyword_blocklist")
    - test_reject_location_mismatch: title="Senior Product Manager", location="New York", jd_text="", config with allow_remote=False, allowed_locations=["Philippines"] → FilterResult(passed=False, reason="location_mismatch")
    - test_reject_blocked_phrase_in_jd: title="Senior Product Manager", location="Remote", jd_text="Must be authorized to work in the US", config with location.blocked_phrases=["authorized to work in the US"] → FilterResult(passed=False, reason="location_mismatch")
    - test_first_failing_rule_short_circuits: title="Junior Developer Internship" with both title mismatch and blocklist conditions — assert reason == "title_mismatch" (first rule wins)

    src/filter/config_loader.py: Implement exactly per PATTERNS.md. RolesConfig, LocationConfig, SalaryConfig, KeywordsConfig, EligibilityConfig Pydantic v2 models. model_validator on EligibilityConfig checks roles.include is non-empty. load_eligibility_config() uses yaml.safe_load() (NOT yaml.load), Pydantic model_validate(). File path is passed as parameter — no env var reads inside this function.

    src/filter/eligibility.py: Implement exactly per PATTERNS.md. FilterResult dataclass with passed: bool, reason: str | None. _normalize() helper (lowercase + strip). check_eligibility() applies rules in this order: (1) title include check, (2) title exclude check, (3) JD keyword blocklist, (4) location blocked phrases in JD, (5) location allowed_locations check if not remote. First failure short-circuits — only one reason returned. Reason strings match DB column values: "title_mismatch", "location_mismatch", "keyword_blocklist". No I/O — pure function.
  </action>
  <behavior>
    - test_pass_matching_title_remote: FilterResult(passed=True, reason=None)
    - test_reject_title_mismatch: FilterResult(passed=False, reason="title_mismatch")
    - test_reject_excluded_keyword_in_title: FilterResult(passed=False, reason="title_mismatch")
    - test_reject_jd_keyword_blocklist: FilterResult(passed=False, reason="keyword_blocklist")
    - test_reject_location_mismatch: FilterResult(passed=False, reason="location_mismatch")
    - test_reject_blocked_phrase_in_jd: FilterResult(passed=False, reason="location_mismatch")
    - test_first_failing_rule_short_circuits: reason == "title_mismatch" (not "keyword_blocklist")
    - test_raises_on_missing_file: raises FileNotFoundError
    - test_raises_on_empty_roles_include: raises pydantic.ValidationError
  </behavior>
  <verify>
    <automated>cd "/Users/stefano/Documents/Workspaces/Job Application Automation" && uv run pytest tests/unit/test_eligibility.py tests/unit/test_config_loader.py -v</automated>
  </verify>
  <acceptance_criteria>
    - All 7 eligibility tests pass
    - All 4 config_loader tests pass (including the two error cases)
    - check_eligibility() has no import of aiosqlite, sqlalchemy, or any DB module (pure function — grep confirms)
    - config_loader.py uses yaml.safe_load (grep for "yaml.safe_load" in the file, NOT "yaml.load(")
    - FilterResult reason strings are exactly "title_mismatch", "location_mismatch", or "keyword_blocklist" (no spaces — underscore format)
  </acceptance_criteria>
  <done>Config loads and validates from YAML. Eligibility filter correctly QUEUES matching leads and REJECTS non-matching leads with a specific underscore-format reason.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Deduplication module (dedup.py) with integration test</name>
  <files>
    src/filter/dedup.py,
    tests/integration/test_dedup.py
  </files>
  <read_first>
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-PATTERNS.md (section: src/filter/dedup.py pattern — read the full pattern block including DEDUP_THRESHOLD constant and both fast and slow path)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-CONTEXT.md (decision D-08 for fuzzy match threshold and compound key)
    - /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/research/PITFALLS.md (Pitfall 2: Duplicate Applications — read the "How to avoid" section for the 30-day lookback consideration)
    - src/queue/models.py (Job model — read to confirm column names before writing DB queries)
  </read_first>
  <action>
    Write tests first (RED), then implement until tests pass (GREEN).

    tests/integration/test_dedup.py — write these test cases before implementing dedup.py. Use an in-memory SQLite DB (":memory:") with init_db() called in setup. Use the session factory to insert test Job rows.

    - test_hash_url_strips_tracking_params: hash_url("https://example.com/job?id=123&utm_source=linkedin") == hash_url("https://example.com/job?id=123&utm_campaign=spring") — tracking params stripped, so hashes match
    - test_hash_url_same_url_same_hash: call hash_url() twice with the same URL string → same result (deterministic)
    - test_is_duplicate_exact_url_hash: insert a Job with url_hash=X into DB; call is_duplicate(session, company, title, location, url_hash=X) → True
    - test_is_duplicate_new_url: with an empty DB, call is_duplicate(session, company, title, location, url_hash="newhash") → False
    - test_is_duplicate_fuzzy_cross_source: insert Job with company_normalized="acme corp", title_normalized="senior product manager", location_normalized="manila"; call is_duplicate(session, company="Acme Corp.", title="Senior Product Manager", location="Manila, Philippines", url_hash="different_hash") → True (fuzzy match >= 85)
    - test_is_not_duplicate_different_company: insert Job with company_normalized="acme corp"; call is_duplicate(session, company="Globex Corporation", title="Senior Product Manager", location="Manila", url_hash="different_hash") → False

    src/filter/dedup.py: Implement per PATTERNS.md. hash_url() uses hashlib.sha256 on the canonical URL (strip utm_source, utm_medium, utm_campaign, trk, refId tracking params via parse_qs/urlencode). _canonicalize_url() lowercases scheme+host and strips tracking params. _similarity_score() uses rapidfuzz.fuzz.token_sort_ratio (handles word order differences). DEDUP_THRESHOLD = 85 named constant. is_duplicate() async function: fast path (url_hash exact match via SQLAlchemy select), then slow path (load all company_normalized+title_normalized+location_normalized rows, compute weighted average: 0.4 company + 0.4 title + 0.2 location). Return True if combined >= DEDUP_THRESHOLD. Use AsyncSession parameter — never create a new engine inside this function.
  </action>
  <behavior>
    - test_hash_url_strips_tracking_params: two URLs with same id but different utm params → equal hashes
    - test_hash_url_same_url_same_hash: deterministic output
    - test_is_duplicate_exact_url_hash: → True
    - test_is_duplicate_new_url: → False
    - test_is_duplicate_fuzzy_cross_source: "Acme Corp." vs "acme corp" + slight location expansion → True (combined similarity >= 85)
    - test_is_not_duplicate_different_company: → False
  </behavior>
  <verify>
    <automated>cd "/Users/stefano/Documents/Workspaces/Job Application Automation" && uv run pytest tests/integration/test_dedup.py -v && uv run pytest tests/ -v 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - All 6 dedup integration tests pass
    - Full pytest suite (tests/) exits 0 — no regressions from Task 1
    - DEDUP_THRESHOLD = 85 is defined as a named constant in dedup.py (grep confirms: `grep "DEDUP_THRESHOLD" src/filter/dedup.py` returns a line with `= 85`)
    - dedup.py uses `rapidfuzz.fuzz.token_sort_ratio` (not `fuzz.ratio` or `thefuzz`) — grep confirms
    - is_duplicate() signature: `async def is_duplicate(session: AsyncSession, company: str, title: str, location: str | None, url_hash: str) -> bool`
  </acceptance_criteria>
  <done>Cross-source deduplication works: exact URL match and fuzzy company+title+location match both prevent duplicate job entries. INGEST-04 requirement satisfied.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| YAML config file → Pydantic model | eligibility.yaml is parsed; malformed or injected content must not execute |
| user job data → filter functions | job title, company, JD text come from external sources (scrapers, emails in Phase 2); must not be treated as executable |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | Tampering | eligibility.yaml YAML parsing | mitigate | yaml.safe_load() only — enforced in config_loader.py; never yaml.load(raw, Loader=yaml.Loader) which allows arbitrary Python object instantiation |
| T-02-02 | Information Disclosure | filter rejection reasons in audit log | accept | Rejection reasons are category labels only ("title_mismatch", not the failing value per D-03); no PII or sensitive config values leaked in reason strings |
| T-02-03 | Denial of Service | dedup slow path O(N) scan | accept | Phase 1 has at most hundreds of jobs; scan is acceptable. Mitigate in Phase 2+ by adding a DB index on company_normalized+title_normalized if slow path becomes bottleneck |
| T-02-04 | Tampering | SQL injection via job field values | mitigate | All DB queries use SQLAlchemy ORM (parameterized) — no raw string interpolation into SQL; dedup.py uses `select(Job.company_normalized, ...)` with no f-strings in query |
| T-02-SC | Tampering | rapidfuzz package legitimacy | mitigate | rapidfuzz is a well-established PyPI package (2M+ weekly downloads, C extension, maintained); executor verifies on npmjs/pypi before install |
</threat_model>

<verification>
After both tasks complete:

1. pytest tests/unit/test_eligibility.py -v → all 7 tests pass
2. pytest tests/unit/test_config_loader.py -v → all 4 tests pass
3. pytest tests/integration/test_dedup.py -v → all 6 tests pass
4. pytest tests/ -v → full suite passes (no regressions)
5. grep "yaml.safe_load" src/filter/config_loader.py returns a match
6. grep "DEDUP_THRESHOLD" src/filter/dedup.py returns "DEDUP_THRESHOLD = 85"
7. grep "token_sort_ratio" src/filter/dedup.py returns a match
</verification>

<success_criteria>
- FILTER-01: Title include/exclude keyword filtering works with case-insensitive matching
- FILTER-02: Location filtering works — allow_remote flag, allowed_locations allowlist, and blocked_phrases in JD all function correctly
- INGEST-04: Deduplication prevents the same job from being inserted twice, both via exact URL hash and via fuzzy compound key (85% threshold)
- All filter functions are covered by passing tests
- No I/O in eligibility.py (grep confirms no `import aiosqlite` or `import sqlalchemy`)
- Config loader fails loudly on invalid YAML (ValidationError) and missing file (FileNotFoundError)
</success_criteria>

<output>
Create /Users/stefano/Documents/Workspaces/Job\ Application\ Automation/.planning/phases/01-foundation/01-02-SUMMARY.md when done
</output>
