# PROGRESS.md — Student Success Intelligence Platform (SSIP)

## Current State (as of 2026-05-06)

**Stack:** Python 3.11 · FastAPI · SQLAlchemy async (PostgreSQL) · pyodbc (SQL Server read-only) · APScheduler · Anthropic Claude API · Docker Compose  
**Execution mode:** `SHADOW` (no real outbound communication until `.env` credentials are filled and mode is flipped to `LIVE`)  
**Note on CLAUDE.md folder refs:** CLAUDE.md was written for a Node.js/Express/React stack. The actual layer mapping is `/app/` → backend, `/frontend/index.html` → frontend, `/app/services/` → business logic. Governance rules, escalation model, and PROGRESS.md gate all apply as written.

---

## Phase 1 — MVP Core Platform

- [x] Initial project scaffold
  - Date: 2026-05-05
  - What changed: repo created, FastAPI skeleton, requirements.txt, pytest.ini, seed_data.py
  - Verification: commit a6f58cb

- [x] MVP backend — core services and routers
  - Date: 2026-05-05
  - What changed: Full FastAPI app with routers (health, outreach, students, metrics, actions, webhook, sync, dashboard), SQLAlchemy models (StudentTriggerData, StudentOutreachTracking, OutreachHistory, StateTransitionLog, ProcessedEvents), state machine, eligibility engine, decision engine, channel selector, scheduler (APScheduler daily batch), outreach orchestration, all integration stubs (GHL, Synthflow, SMS, email, LLM)
  - Verification: commit e334fd8; `tsc --noEmit` N/A (Python); app boots in Docker

- [x] Port moved to 8080
  - Date: 2026-05-05
  - What changed: SSIP service bound to port 8080 in Docker Compose
  - Verification: commit a76ed07

- [x] MVP dashboard fixes
  - Date: 2026-05-05
  - What changed: frontend/index.html corrections post-MVP
  - Verification: commit f23f97a

- [x] Testing and UX documentation
  - Date: 2026-05-05
  - What changed: tests/test_scenarios.md, tests/edge_cases.md, tests/load_tests.md, tests/test_dashboard.py, tests/test_actions.py, tests/test_shadow_safety.py added
  - Verification: commit 19320e4; test files confirmed present

---

## Phase 2 — Production System with Shadow Write

- [x] Production-grade backend rewrite
  - Date: 2026-05-05
  - What changed: 32 files touched — config.py (mssql_dsn builder, is_shadow property), database.py (SQL Server pyodbc sync reader), models.py (5 ORM models finalized), all routers hardened, services split into integrations/ subpackage (ghl.py, synthflow.py, sms.py, email.py, llm.py), sync.py (SQL Server → PostgreSQL upsert), outreach.py rewritten for shadow-safe execution, state_machine.py tightened, docker-compose.yml added, .env.example expanded
  - Verification: commit 0183797; SHADOW mode validated — all outbound calls are no-ops when `EXECUTION_MODE=SHADOW`

- [x] Shadow safety test suite
  - Date: 2026-05-05
  - What changed: tests/test_shadow_safety.py — 6 tests covering GHL, Synthflow, SMS, email no-HTTP in shadow mode; OutreachHistory shadow field invariants; CLOSED state transition lock
  - Verification: commit 19320e4 / 0183797; tests cover shadow gate for all 4 channels

---

## Phase 3 — Dashboard UI

- [x] Full ops dashboard (8-section rewrite)
  - Date: 2026-05-06
  - What changed: frontend/index.html rewritten — System Health panel, Operational Alerts, Funnel KPIs + conversion pills, State Distribution + Channel Performance table, Student Lookup (profile, risk badge, dual timelines), Outreach trigger, SQL Server sync control, Manual Actions (Close/Retry/Resolve/Escalate with SHADOW badge), Recent Activity table; auto-refreshes every 60 seconds
  - Verification: commit c1a41fb

- [x] Collapsible cards
  - Date: 2026-05-06
  - What changed: dashboard cards made collapsible
  - Verification: commit 089c1d5

- [x] Home page summary card rows
  - Date: 2026-05-06
  - What changed: Three labeled rows of summary cards (System Status, Pipeline, Actions) with title, status badge, short summary, key metric, and "View details →" footer; hover highlights border in blue
  - Verification: commit 0ddd455

- [x] CLAUDE.md and documentation update
  - Date: 2026-05-06
  - What changed: CLAUDE.md governance contract updated; supporting docs refreshed
  - Verification: commit 22802e3

---

## Pending / Blockers

- [x] SQL Server credentials set and deployment running in SHADOW mode
  - Date: 2026-05-06
  - What changed: MSSQL_USER + MSSQL_PASS filled in .env; Dockerfile fixed (apt-key → gpg --dearmor, msodbcsql17 → msodbcsql18, python:3.11 → python:3.12 for CVE fix); config.py DSN updated to ODBC Driver 18 + TrustServerCertificate=yes; containers running at localhost:8080
  - Verification: `docker compose logs api` shows all dashboard endpoints returning 200 OK; mode=SHADOW confirmed in startup log

- [x] Switch LLM integration from Anthropic to OpenAI GPT-4o
  - Date: 2026-05-06
  - What changed: app/services/integrations/llm.py rewritten to use `openai.AsyncOpenAI` + `chat.completions.create`; requirements.txt swapped `anthropic>=0.34.0` → `openai>=1.0.0`; config.py default model updated to `gpt-4o`; .env.example updated
  - Verification: pytest tests/ → 19 passed, 0 failed

- [x] Fix sync error messaging — show real SQL Server error instead of generic "not configured"
  - Date: 2026-05-06
  - What changed: database.py _fetch_students_sync now returns (rows, error) tuple; sync.py propagates error field in response; frontend displays actual error string (e.g. permission denied) instead of hardcoded "SQL Server not configured"
  - Verification: container rebuilt and running; error message now reflects actual SQL Server exception

- [x] Bootstrap 5 enterprise UX redesign
  - Date: 2026-05-06
  - What changed: frontend/index.html rewritten from custom dark theme to Bootstrap 5 CDN + navy/white enterprise design matching CLAUDE.md spec — CSS custom properties, card border-0 shadow-sm pattern, table-hover, Bootstrap modal, WCAG 2.1 AA focus indicators, reduced-motion and high-contrast media queries; all API calls and interactions preserved
  - Verification: docker compose up -d --build api succeeded; container running at localhost:8080

- [ ] GHL, Synthflow, LLM (OpenAI) API keys — fill in `.env`
  - Blocker: all outbound integrations are stubbed in shadow mode; real execution requires credentials and `EXECUTION_MODE=LIVE` (strategic decision — requires explicit approval before flip)

- [x] Pytest suite — all 19 tests green
  - Date: 2026-05-06
  - What changed: tests/test_shadow_safety.py had 4 tests passing wrong flat payloads to integration functions that expect builder-constructed nested payloads; fixed tests to use `build_ghl_payload`, `build_call_payload`, `build_sms_payload`, `build_email_payload` helpers
  - Verification: `pytest tests/ -v` → 19 passed, 0 failed (test_shadow_safety.py 6/6, test_actions.py 8/8, test_dashboard.py 5/5)

- [x] Expand All cards feature
  - Date: 2026-05-06
  - What changed: frontend/index.html — each card gains a ▼ chevron toggle button (stops propagation, doesn't open modal); inline Bootstrap collapse panel renders compact live data below card body; "⊞ Expand All / ⊟ Collapse All" button added to navbar; auto-refreshes open panels every 60 s; static panels (Student Cases, Manual Actions, Trigger, Sync) render interactive forms inline; async panels (Health, Alerts, KPI, States, Channels, Activity) fetch and render on expand
  - Verification: user confirmed

- [ ] PROGRESS.md created
  - Date: 2026-05-06
  - What changed: this file created to satisfy CLAUDE.md hard gate; documents full project state through commit 22802e3
  - Verification: user confirmed
