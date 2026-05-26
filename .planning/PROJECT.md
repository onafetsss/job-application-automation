# Autonomous Job Application Agent

## What This Is

An agentic system that monitors Stefano's job lead sources 24/7, filters opportunities against a configurable eligibility profile, and autonomously applies on his behalf — selecting the right resume template, generating a tailored cover letter, completing forms, and notifying him via Telegram/WhatsApp after each submission. Zero human intervention required once running.

## Core Value

Apply to every eligible job faster than any human could — at scale, around the clock, without Stefano lifting a finger.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Monitor LinkedIn job alert emails for new job leads
- [ ] Monitor Kalibrr job platform for new job leads
- [ ] Monitor other job boards (Indeed, etc.) for new job leads
- [ ] Filter leads against a configurable eligibility profile (role titles, salary range, location, keywords)
- [ ] Select best-fit resume template from library per job
- [ ] Generate AI-tailored cover letter and custom screening question answers per application
- [ ] Apply via LinkedIn Easy Apply
- [ ] Apply via full form applications (company-specific)
- [ ] Apply via email (resume + cover letter)
- [ ] Apply via platform-native flows (Kalibrr, etc.)
- [ ] Log all submitted applications with full audit trail
- [ ] Send Telegram/WhatsApp notification after each submission

### Out of Scope

- Human review step before submission — fully autonomous, no approval queue
- Building a job board or sourcing new job leads from scratch (relies on existing sources)

## Context

- Stefano has multiple resume templates and wants the system to match the best one per job description
- Sources vary: email-parsed (LinkedIn job alert digests), platform-scraped (Kalibrr, other boards)
- Eligibility criteria not yet defined — system needs a config layer (role titles, salary, location, keywords) Stefano can tune without touching code
- Applications span all formats: one-click Easy Apply, multi-field forms, plain email, platform native flows
- AI generates cover letters and screening question answers from the job description + Stefano's profile
- Post-application: full log entry + Telegram or WhatsApp push notification

## Constraints

- **Autonomy**: Must operate 24/7 without requiring Stefano to approve individual applications
- **Anti-bot detection**: Platforms like LinkedIn actively block automation — browser automation must handle fingerprinting, rate limits, and form detection gracefully
- **Email access**: Needs access to Gmail/email to parse LinkedIn job alert digests
- **Resume library**: Must ingest and version Stefano's resume templates as structured data for AI matching

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Configurable eligibility filters (not pure AI scoring) | User wants to tune hard rules — role, salary, location, keywords — without unpredictable AI drift | — Pending |
| AI-generated cover letters + screening answers | Tailored applications outperform templated ones; fully autonomous requires AI generation | — Pending |
| Telegram/WhatsApp for notifications | Mobile-first, instant delivery, no inbox noise | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-26 after initialization*
