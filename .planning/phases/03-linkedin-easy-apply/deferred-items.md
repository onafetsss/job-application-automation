# Deferred Items — Phase 03

Out-of-scope discoveries logged during execution (not fixed — outside the current task's blast radius).

## 11 pre-existing integration test failures (discovered during plan 03-05, Task 2 verification)

**Status:** Pre-existing — confirmed failing at commit `36d5e5b` (before any 03-05 work).
**Root cause:** Eligibility config (`config/eligibility.yaml`) now rejects the integration
fixtures' "Senior Product Manager" job title with `reason=title_mismatch`, so helper
`_create_queued_job` asserts `status == "queued"` but gets `rejected`. This cascades into
the application/screening/ingest endpoint tests that depend on a successfully-queued job.

**Affected tests:**
- tests/integration/test_application_endpoints.py::test_write_application_success
- tests/integration/test_application_endpoints.py::test_write_application_not_queued
- tests/integration/test_application_endpoints.py::test_mark_submitted_success
- tests/integration/test_application_endpoints.py::test_mark_submitted_not_applying
- tests/integration/test_cli.py::test_dry_run_prints_queued_line
- tests/integration/test_dry_run_pipeline.py::test_dry_run_catches_within_batch_duplicate
- tests/integration/test_ingest_endpoint.py::test_ingest_lead_queued
- tests/integration/test_ingest_endpoint.py::test_ingest_lead_duplicate
- tests/integration/test_screening_answers.py::test_generate_screening_answers_success
- tests/integration/test_screening_answers.py::test_generate_screening_answers_empty_questions
- tests/integration/test_screening_answers.py::test_generate_screening_answers_anthropic_failure

**Why not fixed here:** Out of scope for plan 03-05 (LinkedIn SDUI applier rework). The
fixtures/eligibility-config drift belongs to the ingestion/filter subsystem (Phase 02), not
the Easy Apply path. None of the 03-05 changed files (models.py, audit_log.py, notify.py,
linkedin_applier.py, linkedin_apply.py) touch these code paths.

**Suggested owner:** A Phase 02 follow-up — either update the eligibility fixtures to a title
that passes the current `eligibility.yaml`, or relax the test config. Recommend `/gsd:debug`.
