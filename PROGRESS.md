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

---

## Phase 4 — Production-Grade Student Success Operations Platform

- [x] Expand StudentTriggerData model — 10 new optional fields
  - Date: 2026-05-15
  - What changed: app/models.py — added AttendancePercentage, CurrentSection, IPBCStartDate, Past10DaysLogon, Total_Payments, Total_Credits, PaymentBalance, ClassValue, FeePaid, ClassFeesPaid to StudentTriggerData; added 4 new models: StudentInterviewPrep (JSONB stub), StudentNote, AIInsight, GHLMessage
  - Verification: TypeScript N/A (Python); column migration runs automatically at startup via ALTER TABLE...ADD COLUMN IF NOT EXISTS in init_db()

- [x] Expand SQL Server sync to include new fields + InterviewPrep table
  - Date: 2026-05-15
  - What changed: app/database.py — expanded SELECT to 19 columns; added _fetch_interview_prep_sync() (SELECT *); app/services/sync.py — added _coerce_row() for date→datetime conversion, _serialize_for_jsonb() for JSONB safe types, sync_interview_prep() service; app/routers/sync.py — added POST /sync/interview-prep endpoint
  - Verification: _validate_row() unchanged (only required NOT NULL fields); new columns all Optional; shadow mode unaffected

- [x] Segmentation service + router
  - Date: 2026-05-15
  - What changed: app/services/segmentation.py — NEWCOMERS (≤90 days), HYPER_ACTIVE (logins≥7 AND eff>90), CAP_HOPEFULS (att>30 AND IPBC), LAUNCH_HOPEFULS (att>55 AND CAP), PLACEMENT_HOPEFULS (att>70 AND Launch); filter_by_role() for frontend role filtering; app/routers/segments.py — GET /segments/summary and GET /segments/{segment_name}
  - Verification: classify_student() pure function; no I/O

- [x] GHL message sync service + router (read-only, shadow-safe)
  - Date: 2026-05-15
  - What changed: app/services/ghl_sync.py — phone-based lookup (E.164 normalize → GET /v1/contacts/?phone= → conversation search → message fetch); sync_by_phone(), sync_student_by_user_id(), sync_all_students(); idempotent on ghl_message_id; all calls logged with duration_ms/status/outcome; app/routers/ghl_sync.py — GET /ghl-sync/status, POST /ghl-sync/student (user_id only, phone auto-loaded), POST /ghl-sync/batch (batch all); frontend — "Sync All GHL Messages" button on Overview card; per-student "Sync GHL" button in drawer Outreach tab with live result display
  - Notes: GHL reads are always allowed — shadow mode gates WRITES only; reads are non-destructive; contact_id is never required — phone number lookup is the only supported path

- [x] AI insight generation service + router
  - Date: 2026-05-15
  - What changed: app/services/ai_insights.py — OUTREACH_DRAFT, INTERVENTION, RISK_EXPLANATION, INTERVIEW_COACHING; 24-hour PostgreSQL cache; OpenAI GPT-4o; app/routers/ai_insights.py — GET /ai-insights/{user_id}/{insight_type}, GET /ai-insights/{user_id}
  - Verification: degrades gracefully if LLM_API_KEY not set; shadow mode unaffected (no outbound comm)

- [x] Unified timeline service + router
  - Date: 2026-05-15
  - What changed: app/services/timeline.py — merges OutreachHistory, StateTransitionLog, StudentNote, AIInsight, GHLMessage into chronological event stream; app/routers/student_timeline.py — GET /timeline/{user_id}
  - Verification: pure aggregation; no writes; no shadow gate needed

- [x] Payment reconciliation router with Bundle Deal fix
  - Date: 2026-05-15
  - What changed: app/routers/payment.py — GET /payment/reconciliation, GET /payment/student/{user_id}; bundle detection: Total_Credits>0 AND PaymentBalance==0 AND ClassValue>0 → actual_balance = ClassValue−Total_Payments−Total_Credits; payment_risk field: HIGH/MEDIUM/CLEAR
  - Verification: actual_balance field surfaced alongside stored PaymentBalance; is_bundle_deal flag makes fix auditable

- [x] Notes router
  - Date: 2026-05-15
  - What changed: app/routers/notes.py — POST /notes, GET /notes/{user_id}; StudentNote model; author attribution; AI-generated flag
  - Verification: content/author validated; shadow mode unaffected

- [x] Expanded students router — drawer endpoint + interview prep
  - Date: 2026-05-15
  - What changed: app/routers/students.py — GET /students/{user_id}/drawer (combined profile+payment+segments+outreach+interview_prep), GET /students/{user_id}/interview-prep
  - Verification: bundle-aware balance computed in drawer; segment classification included

- [x] Extended KPI dashboard endpoint
  - Date: 2026-05-15
  - What changed: app/routers/dashboard.py — GET /dashboard/kpi-extended returns avg attendance, efficiency, hw_behind, engagement counts, payment risk, segment counts, section distribution
  - Verification: gracefully returns note when no students synced

- [x] Config expanded with GHL field vars
  - Date: 2026-05-15
  - What changed: app/config.py — GHL_TIMEOUT_SECONDS, GHL_RETRY_MAX, GHL_FIELD_MESSAGE, GHL_TASK_TITLE, GHL_TASK_DESCRIPTION, GHL_TASK_DUE_DATE, GHL_FIELD_VM_EMAIL_HTML, GHL_FIELD_VM_EMAIL_SUBJECT
  - Verification: all have safe defaults; no breaking change to existing .env

- [x] Update main.py — register 6 new routers
  - Date: 2026-05-15
  - What changed: app/main.py — registered segments, payment, student_timeline, ai_insights, notes, ghl_sync routers; version bumped to 2.0.0
  - Verification: all imports verified; startup runs init_db() with column migrations

- [x] Frontend complete rewrite — multi-dashboard SPA
  - Date: 2026-05-15
  - What changed: frontend/index.html — 11 tab navigation (Overview, KPI, Newcomers, Engagement, HW Risk, CAP Hopefuls, Launch Hopefuls, Placement Hopefuls, Payment, Outreach Activity, AI Intervention); Bootstrap 5 Offcanvas right drawer with 10 tabs (Info, Mentor, Instructor, Super Mentor, Timeline, Outreach, AI Insights, Interview Prep, Payment, Notes); Chart.js 4 charts (segments doughnut, HW risk bar, sections bar, outreach funnel); generic DataTable engine with search/sort/paginate/CSV export; role picker in navbar persisted to sessionStorage; auto-refresh every 10 min (600000ms); bundle deal payment risk visualization; conditional row formatting
  - Verification: all API endpoints wired; SHADOW mode badge preserved; GHL read-only indicator on sync card; role picker wired to API role params; CSV export works on filtered rows

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

- [x] SQL Server sync partial-sync tolerance + structured error surfacing
  - Date: 2026-05-12
  - What changed: app/services/sync.py — added _validate_row() guard on UserID/HWsBehind/AvgEffRating; invalid rows are skipped with reason logged and returned in failures[]; valid rows always commit; db.commit() wrapped in try/except so a late DB-level failure returns structured error instead of 500; structured response adds status/rows_scanned/rows_successful/rows_failed/failures fields; frontend/index.html — _renderSyncResult() helper, syncMssqlInline() and syncMssql() rewritten to show scanned/inserted/updated/skipped counts, per-failure UserID+reason table, WARNING badge on partial_success; tests/test_sync.py — 12 new tests (5 unit _validate_row, 7 integration sync_from_mssql) all passing
  - Verification: pytest tests/ → 45 passed, 0 failed (was 33)
  - Notes: model NOT NULL constraints preserved; no silently-defaulted NULL values; shadow mode unaffected; data_quality_issues table deferred as follow-up

- [x] Expand All cards feature
  - Date: 2026-05-06
  - What changed: frontend/index.html — each card gains a ▼ chevron toggle button (stops propagation, doesn't open modal); inline Bootstrap collapse panel renders compact live data below card body; "⊞ Expand All / ⊟ Collapse All" button added to navbar; auto-refreshes open panels every 60 s; static panels (Student Cases, Manual Actions, Trigger, Sync) render interactive forms inline; async panels (Health, Alerts, KPI, States, Channels, Activity) fetch and render on expand
  - Verification: user confirmed

- [x] PROGRESS.md created
  - Date: 2026-05-06
  - What changed: this file created to satisfy CLAUDE.md hard gate; documents full project state through commit 22802e3

## Phase 5 — Lifecycle Tab Reformat (6 tabs, per-spec column schemas)

- [x] Expand StudentTriggerData — 10 additional SQL Server source columns
  - Date: 2026-05-15
  - What changed: app/models.py — added ClassName, ClassSignupsID, ActiveStatus, StatusI, StatusII, StudentStartDate, ClassStartDate, LastActivitySection, LastLoginDays, LastSubmitted to StudentTriggerData; added StudentCampaignActivity and StudentQuickActionLog models; expanded StudentNote with note_type and visibility fields
  - Verification: migration-lite in init_db() adds all new columns via ALTER TABLE IF NOT EXISTS on container restart — safe to run repeatedly

- [x] Migration-lite for Phase 5 columns
  - Date: 2026-05-15
  - What changed: app/database.py — _NEW_TRIGGER_COLS extended with 10 new columns; student_notes ALTER TABLE adds note_type and visibility

- [x] Segmentation service — fix section field and thresholds
  - Date: 2026-05-15
  - What changed: app/services/segmentation.py — replaced CurrentSection references with LastActivitySection (via _section() helper falling back to PathName); CAP_HOPEFULS threshold corrected to attendance > 50 (was > 30); LAUNCH_HOPEFULS filter changed to 'CAP Project' in section (was 'CAP'); rules dict updated to match spec
  - Notes: CurrentSection was always NULL because it does not exist in SQL Server — LastActivitySection is the correct source column

- [x] Sync coerce — generalize date column handling
  - Date: 2026-05-15
  - What changed: app/services/sync.py — _coerce_row() now handles StudentStartDate and ClassStartDate date→datetime conversion alongside IPBCStartDate; LastSubmitted coerced to ISO string for VARCHAR storage

- [x] Lifecycle router — 6 dedicated tab endpoints
  - Date: 2026-05-15
  - What changed: app/routers/lifecycle.py (NEW) — GET /lifecycle/newcomers (IPBCStartDate within 90d), /engagement (all), /hw-risk (IPBCStartDate not null), /cap-hopefuls (attendance>50), /launch-hopefuls (attendance>70 AND 'CAP Project' in section), /placement-hopefuls (attendance>70 AND 'Launch' in section); each endpoint merges latest campaign activity and latest note per student; _compute_common() derives row_id, student_name, weeks_in_program, last_hw_submitted_days, active_student; all null-safe with graceful fallbacks
  - Verification: SHADOW mode unaffected (read-only endpoints)

- [x] Quick actions router — operator button log + campaign activity query
  - Date: 2026-05-15
  - What changed: app/routers/quick_actions.py (NEW) — POST /quick-actions/log (logs StudentQuickActionLog + companion StudentCampaignActivity); GET /campaign-activity/{user_id}; GET /quick-actions/{user_id}; execution_mode stamped on every record; no external communication triggered
  - Verification: SHADOW mode enforced — shadow_only=True on all campaign activity records when in shadow mode

- [x] Register new routers in app/main.py
  - Date: 2026-05-15
  - What changed: lifecycle_router and quick_actions_router registered with Lifecycle and QuickActions tags

- [x] Frontend — 6 lifecycle tabs with per-spec column schemas and action bars
  - Date: 2026-05-15
  - What changed: frontend/index.html — CSS added for .dt-row-selected and .action-bar-wrap; 6 tab pane HTML replaced with structured layout (section label + action bar + table container); buildTable() updated with onSelect callback and selectedId row highlighting via .dt-row-selected class; TAB_ACTIONS and handleAction() implement button click → POST /quick-actions/log flow; 6 dedicated loaders: loadNewcomersTab() (17 cols), loadEngagementTab() (18 cols), loadHwRiskTab() (20 cols), loadCapTab() (20 cols), loadLaunchTab() (20 cols), loadPlacementTab() (28 cols); loadTab() updated to call per-tab loaders; action buttons disabled until row selected; SHADOW badge visible on each action bar
  - Verification: column order matches spec exactly for each tab; campaign/notes columns present but blank until activity logged; Launch and Placement Hopefuls show empty table with descriptive note when filter returns no rows
  - Verification: user confirmed

---

## Phase 6 — Lifecycle Tab Data Fix (Newcomers / HW Risk / CAP Hopefuls empty)

- [x] Diagnose empty lifecycle tabs
  - Date: 2026-05-15
  - What changed: investigation only — no code changed during diagnosis
  - Verification: confirmed `IPBCStartDate` is NULL for all 76 SQL Server students; `AttendancePercentage` was NULL in PostgreSQL despite being populated in SQL Server (scale mismatch + stale sync); 39/76 students skipped by sync validation (HWsBehind/AvgEffRating NULL); PostgreSQL had 10 seed rows + 80 partially-synced real rows

- [x] Fix sync validation — allow students without homework data
  - Date: 2026-05-15
  - What changed: app/services/sync.py — `_REQUIRED_FIELDS` narrowed to `("UserID",)` only; `_coerce_row()` now defaults `HWsBehind → 0` and `AvgEffRating → 0.0` when NULL (students before first HW submission); `AttendancePercentage` normalized from SQL Server's 0–1 fraction to 0–100 scale (×100); `ClassSignupsID` cast to `str` (SQL Server int → PostgreSQL VARCHAR); `Total_Credits`/`ClassValue`/`PaymentBalance`/`ClassFeesPaid` explicitly cast to `float`
  - Verification: sync ran 76/76 scanned, 76 successful, 0 failures; `AttendancePercentage` now 92.3 (was NULL) for sample student

- [x] Fix lifecycle tab filters — remove IPBC gate
  - Date: 2026-05-15
  - What changed: app/routers/lifecycle.py — **Newcomers**: filter changed to `COALESCE(IPBCStartDate, StudentStartDate) within 90 days` via SQLAlchemy `or_/and_`; **HW Risk**: removed `IPBCStartDate IS NOT NULL` gate entirely (shows all 94 students); **CAP Hopefuls**: removed `IPBCStartDate IS NOT NULL`, kept `AttendancePercentage > 50` (now 59 students qualify); `_compute_common()` falls back to `StudentStartDate` for `weeks_in_program` when `IPBCStartDate` is NULL; added `and_` / `or_` to imports
  - Verification: Newcomers=17, HW Risk=94, CAP Hopefuls=59 rows returned after fix

- [x] Fix segmentation service — mirror same logic
  - Date: 2026-05-15
  - What changed: app/services/segmentation.py — NEWCOMERS segment uses `IPBCStartDate or StudentStartDate` for date check; CAP_HOPEFULS removes `has_ipbc_start` gate, classifies on attendance alone; SEGMENT_RULES strings updated to document new logic
  - Verification: consistent with lifecycle endpoint behaviour

- [x] Fix action buttons — row click handler unreachable due to hyphen in containerId
  - Date: 2026-05-15
  - What changed: frontend/index.html — `buildTable()` generated four inline onclick strings using bare identifiers (`__dtRowClick_dt-newcomers(...)`) which JavaScript parses as subtraction; fixed all four generators (row click, prev pager, next pager, sort header) to use `window['__dtXxx_${containerId}'](...)` bracket notation so the hyphenated key is reachable
  - Verification: `onSelect` callback now fires on row click → action buttons un-disable; pager Prev/Next and column sort also unblocked by same fix

- [x] Make ODBC driver configurable — MSSQL_DRIVER env var
  - Date: 2026-05-15
  - What changed: app/config.py — added `MSSQL_DRIVER: str = "ODBC Driver 17 for SQL Server"` setting; `mssql_dsn` property uses `{self.MSSQL_DRIVER}` instead of hardcoded v18; production can override with `MSSQL_DRIVER=ODBC Driver 18 for SQL Server` in `.env`
  - Verification: sync succeeded using Driver 17 locally

---

## Documentation Update — Phase 5 Sync

- [x] Spec, UX, and implementation plan docs updated to reflect Phases 4 & 5
  - Date: 2026-05-15
  - What changed: spec/08_data_model.md — complete rewrite: dual-DB architecture (SQL Server read-only + PostgreSQL app DB), full student_trigger_data column list, new tables (student_campaign_activity, student_quick_action_log), updated student_notes schema, migration-lite strategy documented; spec/07_api_contracts.md — added sections 3.7–3.14 covering sync, lifecycle tabs, quick actions, GHL sync, timeline, notes, AI insights, segments endpoints; ux/admin_dashboard.md — new Section 15 documenting 6 lifecycle tabs, action bar behavior, per-tab column schemas, empty-state messaging; ux/operator_workflows.md — new Section 5 covering all lifecycle tab workflows (navigation, row selection, action button flow, data sync, drawer usage); execution/implementation_plan.md — Phase overview updated to show actual delivered phases alongside original plan
  - Verification: user requested; all docs reflect current codebase state

---

---

## Phase 7 — Architecture Hardening (Pre-Warehouse)

- [x] Add Alembic migration support
  - Date: 2026-05-24
  - What changed: `requirements.txt` — added `alembic>=1.13.0`; `alembic.ini` created with placeholder URL overridden at runtime; `alembic/env.py` — async-compatible env using `create_async_engine` + `NullPool`, offline mode strips `+asyncpg` prefix for SQL script generation; `alembic/script.py.mako` — standard template; `alembic/versions/0001_baseline.py` — full baseline migration for all 11 tables and all indexes as-at Phase 5
  - Verification: alembic.ini and env.py created; migration file covers all ORM models and indexes
  - Notes: Existing deployments must run `alembic stamp head` before running `alembic upgrade` to skip DDL already applied by init_db(). `init_db()` kept intact for now — future schema changes use Alembic only.

- [x] Add warehouse-preparation indexes
  - Date: 2026-05-24
  - What changed: `app/models.py` — added `ix_stl_created_at` to `StateTransitionLog` (was missing), `ix_sot_updated_at` to `StudentOutreachTracking`, `ix_oh_checkpoint` to `OutreachHistory`, `ix_sca_created_at` to `StudentCampaignActivity`; `app/database.py` — added four `CREATE INDEX IF NOT EXISTS` statements in `init_db()` to apply indexes to existing deployments on next restart
  - Verification: indexes defined in model `__table_args__`; migration-lite guards in `init_db()` are idempotent

- [x] Add `risk_level_for_display()` to priority service — consolidate risk scoring
  - Date: 2026-05-24
  - What changed: `app/services/priority.py` — added `risk_level_for_display(profile)`: accepts any object with priority fields (duck-typed, no ORM import), calls `score_student()`, maps URGENT→HIGH, returns HIGH/MEDIUM/LOW/UNKNOWN
  - Verification: removed duplicate `_risk_level()` from `app/routers/students.py`; all three callers (students, work_queue, segments) now use canonical score via priority service

- [x] Extract payment logic to `app/services/payment.py`
  - Date: 2026-05-24
  - What changed: `app/services/payment.py` (NEW) — `compute_balance(student_dict)` (bundle-fix), `payment_risk_label(balance)` (HIGH/MEDIUM/CLEAR), `build_payment_row(orm_row)` (full reconciliation row); `app/routers/payment.py` — removed `_compute_balance()` and `_payment_row()`, delegates to service; `app/routers/students.py` — drawer endpoint replaced inline bundle calculation with `compute_balance()` + `payment_risk_label()`
  - Verification: API response shape unchanged; all payment fields still present

- [x] Extract alert logic to `app/services/alerts.py`
  - Date: 2026-05-24
  - What changed: `app/services/alerts.py` (NEW) — `gather_alerts(db, *, is_shadow, mssql_configured, last_run)` — all five alert categories (CRITICAL: no MSSQL, WARNING: stuck CONTACTED, missed retry, scheduler stale, INFO: shadow mode); `app/routers/dashboard.py` — `dashboard_alerts()` replaced 50-line inline block with single `gather_alerts()` call; removed now-unused `timedelta` and `StudentOutreachTracking` imports from router
  - Verification: API response shape unchanged; all alert severities and messages preserved

- [x] Extract date utilities to `app/utils/date_utils.py`
  - Date: 2026-05-24
  - What changed: `app/utils/__init__.py` (NEW); `app/utils/date_utils.py` (NEW) — `to_isostr`, `weeks_in_program`, `hw_submitted_days`, `active_student_flag`, `serialize_datetime_fields` extracted from `lifecycle.py` private helpers; `app/routers/lifecycle.py` — removed 5 private `_*` functions, imports from `app.utils.date_utils`; `typing.Any` import removed (no longer needed)
  - Verification: all lifecycle tab endpoints retain identical behavior; function logic unchanged during extraction

---

## Phase 4 — Operational Outreach Command Center

- [x] Priority scoring engine
  - Date: 2026-05-06
  - What changed: app/services/priority.py — additive numeric score 0–135 mapping to URGENT/HIGH/MEDIUM/LOW; recommended action derived from score + tracking state; reason codes per student
  - Verification: pytest tests/ → 33 passed, 0 failed (7 new priority tests in test_work_queue.py)

- [x] Remove hardcoded PathName/checkpoint validators
  - Date: 2026-05-06
  - What changed: removed VALID_CHECKPOINTS set from schemas.py (TriggerOutreachRequest no longer rejects unknown PathNames); removed CHECKPOINTS set from outreach.py; simplified path filter from POST_COMPLETION special-case to generic `path != checkpoint_type`
  - Verification: test_trigger_outreach_request_accepts_arbitrary_path passes; existing batch logic unchanged

- [x] Source analysis router
  - Date: 2026-05-06
  - What changed: app/routers/source.py — GET /source/paths (distinct PathNames from mirror), GET /source/summary (per-path totals, tracked vs untracked, URGENT/HIGH/MEDIUM/LOW risk distribution)
  - Verification: pytest tests/ → 33 passed; endpoints live at localhost:8080/source/paths and /source/summary

- [x] Work queue router
  - Date: 2026-05-06
  - What changed: app/routers/work_queue.py — GET /work-queue/summary (counts for 7 named queues), GET /work-queue/{queue_name} (paginated, priority-sorted student list with PathName filter); queues: all_source, untracked, eligible, contacted, intervention, retry_due, resolved_closed
  - Verification: pytest tests/ → 33 passed; invalid queue name returns APIResponse.fail

- [x] Batch preview and run router
  - Date: 2026-05-06
  - What changed: app/routers/batch.py — GET /batch/preview (dry-run: per-student decision + priority without executing), POST /batch/run (shadow-safe delegation to outreach service); both carry execution_mode + shadow flags
  - Verification: pytest tests/ → 33 passed

- [x] Register new routers in main.py
  - Date: 2026-05-06
  - What changed: app/main.py imports and registers source_router, work_queue_router, batch_router with tags Source/WorkQueue/Batch
  - Verification: container running; all new endpoints return 200 OK at startup

- [x] Test suite expanded to 33 tests
  - Date: 2026-05-06
  - What changed: tests/test_work_queue.py — 14 new tests covering priority engine (7), source router (2), work queue summary structure (1), invalid queue name (1), batch preview keys (1), schema accepts arbitrary path (2)
  - Verification: pytest tests/ → 33 passed, 0 failed

- [x] Dashboard operational upgrade — Source Analysis + Work Queue + Batch Preview
  - Date: 2026-05-06
  - What changed: frontend/index.html — Operations section added with Source Analysis card (per-path tracked/untracked/risk breakdown) and Work Queue card (7-queue browser with priority-sorted table); Batch Preview modal (decision summary + per-student preview before running); dynamic PathName dropdown in Trigger Outreach (fetches /source/paths, falls back to static list); priority badge component (URGENT/HIGH/MEDIUM/LOW); updated loadAll to call loadSourceSummary + loadWorkQueueSummary; updated toggleAllCards to include new panels
  - Verification: pytest tests/ → 33 passed, 0 failed; container running at localhost:8080
