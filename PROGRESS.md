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

## Phase 8 — Architecture Harmonization & Pre-Warehouse Specification Finalization

- [x] Architecture harmonization analysis — spec consistency review across 5 impact areas
  - Date: 2026-05-25
  - What changed: design-level analysis only; no code or schema changes; produced 5 new required abstraction layers, 6 unresolved design decisions (D-1 through D-6), 8 specification sections requiring revision, dependency sequencing, and readiness assessment
  - Verification: analysis documented in session context; spec not yet updated (analysis phase only)

- [x] Finalize architecture-blocking design decisions — 6 FADs
  - Date: 2026-05-25
  - What changed: `spec/01_requirements.md` — integrated all 6 Finalized Architecture Decisions (FAD-1 through FAD-6); updated Sections 3.15, 3.17, 3.18, 3.19, 4.7, 4.8, 6, 7, 9.4, 11.1, 11.2; added Sections 12.8, 13, 14
  - Verification: spec file updated; all 5 D-decisions resolved (D-1/3/4/5/6 via FAD-3/5/1/4/2 respectively); D-2 classified as open Implementation concern; warehouse schema design unblocked
  - Notes: Section 13 records all 6 FADs as authoritative and binding; Section 14 provides readiness assessment with authoritative dependency sequencing; warehouse schema Alembic migration (`0002_warehouse_schema.py`) is now unblocked

- [x] State transition model evolution — extend from outreach-only to all 6 lifecycle domains
  - Date: 2026-05-25
  - What changed: `spec/03_state_transition_rules.md` — Section 1 (PURPOSE) expanded to multi-domain scope with domain overview table; Section 2 (SOURCE OF TRUTH) updated with new file references; appended Sections 14–45 covering: Domain 2 Snapshot Lifecycle (states, transitions, freezing points, compliance override path, retry semantics, invariants); Domain 3 Monthly Report Lifecycle (async generation, publication boundary, historical regeneration, operator review); Domain 4 AI Insight Lifecycle (force-refresh semantics, versioning, snapshot isolation, attribution guarantees); Domain 5 Configuration Version Governance (activation boundary, prospective-only enforcement, atomic activation, rollback prohibition); Domain 6 Compliance Governance (authorization gating, audit requirements, interaction with snapshot/report immutability); Section 39 Event Attribution Standard (origin_source, origin_authority, execution_mode, attribution fields per domain); Section 40 Cross-Domain Invariants (7 platform-wide invariants covering append-only reporting, reproducibility, AI snapshot isolation, auditability, source attribution, SQL Server authority, compliance override restriction); Section 41 Failure & Recovery Modeling per domain; Section 42 Scope-Specific Behavior (all domains × MVP/STANDARD/PRODUCTION); Section 43 Acceptance Criteria for new domains; Section 44 Combined Invariants; Section 45 Updated References
  - Verification: specification document only (no code); consistent with FAD-1 through FAD-6; preserves all existing outreach lifecycle content unchanged

- [x] Idempotency and concurrency model evolution — extend from outreach-only to all 6 lifecycle domains
  - Date: 2026-05-25
  - What changed: `spec/04_idempotency_concurrency.md` — expanded from 463 to 1,315 lines; Section 1 (PURPOSE) expanded with multi-domain overview table and 6-domain idempotency concern summary; Section 2 (CORE PRINCIPLES) expanded with Platform Concurrency Philosophy (2.4: 6-workflow-class concurrency model, append-only philosophy, replay safety, determinism requirement) and Irreversible Operation Definitions (2.5: 7 explicitly irreversible operations); Section 4 (IDEMPOTENCY KEYS) expanded from outreach-only to 6 domain-specific key structures (Sections 4.1–4.7) covering snapshot (student_id, snapshot_month), report (cohort_id, report_month, template_version, lineage_version), AI insight (student_id, insight_type, date_period, prompt_version, version_number), config version, and compliance keys; appended Sections 15–26 covering: Section 15 Snapshot Finalization Idempotency (duplicate generation protection, concurrent finalization serialization, regeneration race protection, fingerprint drift prevention, stale update protection, compliance action dedup, idempotency classification table); Section 16 Report Generation Concurrency (duplicate job prevention, publication serialization, regeneration conflict prevention, stale rendering protection, artifact deduplication); Section 17 AI Generation Idempotency (duplicate request prevention, concurrent force-refresh handling, prompt version capture, model version attribution, partial failure recovery, serving state semantics, snapshot isolation boundary); Section 18 Config Version Governance Concurrency (simultaneous activation prevention, atomic swap invariant, duplicate promotion prevention, race condition at snapshot finalization, prospective-only enforcement, rollback prohibition); Section 19 Compliance-Governed Concurrency (duplicate request prevention, concurrent action prevention, stale approval handling, conflicting governance action prevention, partial execution recovery, audit survivability); Section 20 Event Idempotency & Attribution (communication events, access history, AI lifecycle, report lifecycle, compliance events, transition log dedup, correlation ID propagation, mirrored-source conflict handling); Section 21 Cross-Domain Concurrency Invariants (7 invariants: append-only finalized records, reproducibility under replay, AI snapshot isolation, config version consistency, compliance workflow serialization, historical regeneration read-only source, audit trail atomicity); Section 22 Failure & Recovery Model (cross-domain tables covering partial snapshot finalization, duplicate report publication, stale AI generations, orphaned regeneration jobs, fingerprint mismatch, failed compliance execution, concurrent config activation conflicts, failure classification summary); Section 23 Execution Mode Interactions (SHADOW mode for snapshots, compliance workflows in SHADOW, AI experimental context, auditability by mode); Section 24 Acceptance Criteria for new domains; Section 25 Downstream Implications for data model, API, warehouse schema, and orchestration; Section 26 Updated References
  - Verification: specification document only (no code); consistent with FAD-1 through FAD-6; consistent with spec/03_state_transition_rules.md Sections 14–45; preserves all existing outreach idempotency content unchanged

- [x] Physical warehouse architecture plan — translate conceptual data model into physical storage architecture
  - Date: 2026-05-25
  - What changed: `spec/09_warehouse_physical_architecture.md` (NEW, ~700 lines) — 12-section physical architecture specification covering: (1) three-schema physical boundary map with ASCII diagram, append-only and immutable-history enforcement strategies, regeneration and publication lineage strategies; (2) nine storage domain definitions (SQL Server mirror, outreach state machine, communication telemetry, monthly snapshots, report publication, AI insight lineage, config version registry, event timeline, compliance audit) with mutability, retention, and access profiles per domain; (3) snapshot storage strategy — two-table design recommendation (`warehouse.student_snapshots` + `warehouse.snapshot_ai_narratives` 1:1 companion) with FAD-1 compliance rationale, pre-migration benchmarking requirement, full column groupings for both tables (identity/lifecycle, SQL Server metric physical copies, derived metrics, communication summary, fingerprint components, metadata), reproducibility invariant table; (4) report artifact storage strategy — `warehouse.monthly_reports` and `warehouse.report_audit_log` column groupings, JSONB inline content recommendation with future object storage evolution path, report immutability under regeneration table; (5) event timeline storage strategy — hybrid approach (unified `public.student_timeline_events` for operational events, `warehouse.report_audit_log` for report lifecycle, `compliance_audit.deletion_log` for compliance events), top-level vs. JSONB column classification, SQL Server distinguishability enforcement, replay safety via idempotency keys, correlation ID propagation; (6) configuration version storage strategy — full column strategy for `config_version_registry` including all 22 configurable rule columns from spec/01 Sections 12.1–12.7, exactly-one-ACTIVE partial unique index enforcement, activation lineage query pattern, snapshot config version reference as logical (not physical FK) binding; (7) compliance audit storage strategy — schema isolation architecture, `compliance_audit.deletion_log` and `compliance_audit.scope_manifests` column strategies, survivability guarantees table, audit exportability requirements; (8) indexing and query strategy — expected query pattern categories with frequency/performance requirements, index strategy categories (PK, business key unique, idempotency key, state filtering, timeline, warehouse analytics), partitioning candidates, archival candidates; (9) storage evolution strategy — horizontal scaling path (read replicas, logical replication, schema-level archival separation), archive strategy per domain, long-term retention with partition-ready design, AI artifact growth management, event volume growth management; (10) data flow and synchronization — SQL Server→PostgreSQL sync boundary (with idempotency and partial-sync-safe properties), snapshot generation 3-step flow (DRAFT→VALIDATING→FINALIZED with invariants), report generation flow (with FAD-2 compliance), historical regeneration flow (POTENTIALLY_DIVERGENT logic), AI enrichment flow (with snapshot isolation boundary), compliance annotation flow (with pre-action hard gate); (11) migration planning readiness assessment — 0002 READY/0003 READY/0004 subsumed-by-0002 with FAD-4 inconsistency resolution, pre-migration benchmarking requirement, remaining blockers table (schema vs. go-live blockers distinguished), implementation-sensitive areas (permission GRANT statements in migration, config V1 seed, partial unique indexes, transaction safety), recommended migration sequencing (0001→0002+0003→0004+0005→0006); (12) output summary — physical architecture decision table, schema boundary recommendation table, recommended implementation sequence (8 steps: benchmark → 0002 → 0003 → deploy → 0004+0005 → service design), service layer sequencing (5 services with dependencies), open items for migration authors
  - Verification: specification document only (no code); consistent with FAD-1 through FAD-6; consistent with spec/08_data_model.md Sections 13–26; resolves spec/08 Section 8 inconsistency between 0004 and FAD-4 with explicit reconciliation recommendation; preserves all existing table structures and governance boundaries

- [x] Pre-migration storage validation — formal validation of physical warehouse architecture before migration authoring
  - Date: 2026-05-25
  - What changed: `spec/10_pre_migration_storage_validation.md` (NEW, ~900 lines) — 11-section pre-migration validation covering: (1) AI narrative storage validation — TOAST behavior analysis per design choice, two-table vs single-table comparison on analytical query performance, row bloat risk, buffer pool efficiency, append-only growth, historical reporting and regeneration-read performance, FAD-1 compliance confirmation, FK-to-ai_insights prohibition rationale, frozen-copy operational importance; (2) AI payload benchmarking plan — four benchmark queries (per-type distribution, per-student total, coverage, temporal trend), decision boundary thresholds (P95 per-field < 512 bytes for single-table viable; > 2048 bytes mandates two-table), growth projections (10–40% per year), row-width danger zones, analytical scan inflection points; (3) snapshot table physicalization review — fingerprint scalar column validation (3 scalar TEXT + 1 JSONB confirmed correct), JSONB usage review, lineage FK under compliance deletion confirmed safe, regeneration lineage semantics (snapshot regeneration re-reads stored metric columns, does NOT re-sync SQL Server), append-only gap identified (compliance pathway needs UPDATE (status) grant on warehouse.student_snapshots), partition-ready design confirmed (no blocking constructs), storage density estimates; (4) event storage validation — hybrid architecture structural validation, event volume scalability estimate (1.7–4.4M rows at full scale), timeline query efficiency, SQL Server distinguishability three-column strategy validated, unified table appropriateness confirmed, partition-ready design confirmed; (5) config version physical guarantee review — partial unique index operational correctness, concurrency race safety analysis (two-transaction scenario traced end-to-end), advisory locking not needed, application-level atomic swap still required alongside DB index; (6) compliance storage review — schema isolation validated, deletion-log survivability matrix confirmed, CRITICAL DEFECT IDENTIFIED AND FIXED: scope_manifests.is_current column violates INSERT-only invariant (compliance pathway cannot UPDATE) — removed from spec/09 Section 7.3 and replaced with MAX(manifest_version) query pattern, governance audit persistence (PRE/POST/CHECKPOINT pattern) validated, MVP/STANDARD sufficiency confirmed, compliance pathway UPDATE (status) grant gap confirmed; (7) migration 0002 readiness assessment — formal classification per area: warehouse.student_snapshots READY WITH VALIDATION, snapshot_ai_narratives READY, monthly_reports READY, report_audit_log READY, deletion_log READY, scope_manifests READY WITH MODIFICATION (is_current removed), permission grants READY WITH MODIFICATION (UPDATE grant added); (8) migration sequencing validation — compliance_audit in 0002 per FAD-4 re-confirmed, prior spec/08 inconsistency fully resolved, validated sequencing (0002 → 0003 concurrent → 0004 after 0002 → 0005 after 0002 → 0006 deferred), dangerous coupling concerns (GRANTs must be in migration, V1 seed transactional, 0002+0003 both required before snapshot service, compliance service needs schema check at startup); (9) implementation risk review — HIGH risks: missing UPDATE grant, is_current defect, GRANT omission, non-transactional atomic swap, missing V1 seed; MEDIUM risks: report_content_json payload growth, unbounded lineage depth; LOW risks: fingerprint JSONB evolution; scaling bottleneck projections (timeline events ~10M rows at 10K students triggers partitioning; snapshot table ~500K rows at that scale); (10) output — AI storage recommendation (two-table confirmed), benchmark strategy, finalized snapshot recommendation, migration readiness matrix, implementation risk matrix, migration sequencing recommendation, physical and operational scalability assessments, final pre-authoring checklist with 10 items all confirmed; (11) specification corrections to propagate — 4 corrections identified for spec/09; two critical corrections applied immediately (is_current removal, UPDATE grant addition); `spec/09_warehouse_physical_architecture.md` updated in Sections 7.3 and 11.4 with both corrections
  - Verification: specification document only (no code or migrations); consistent with FAD-1 through FAD-6; spec/09 Sections 7.3 and 11.4 corrected in place; all 10 pre-authoring checklist items confirmed; 0002 and 0003 authoring is unblocked

- [x] spec/07_api_contracts.md — full evolution to governed historical intelligence API spec
  - Date: 2026-05-25
  - What changed: `spec/07_api_contracts.md` rewritten from 1,138 lines (operational-only) to ~1,000-line governed historical intelligence spec. Preserved all existing §8 operational endpoints (3.1–3.15) unchanged. Added: §2 expanded API Architecture Philosophy (mutable vs immutable surfaces, operational vs historical endpoints, lineage-aware patterns, append-only historical workflows, reproducibility visibility, SQL Server read-only boundary); §3 error handling with HTTP status codes and full error code table including governance-specific codes (`GOVERNANCE_BOUNDARY`, `FINALIZED_IMMUTABLE`, `PUBLISHED_IMMUTABLE`, `CONFIG_ROLLBACK_FORBIDDEN`, `AUDIT_ENTRY_MISSING`); §4 idempotency rules with domain-specific keys and `Idempotency-Key` header semantics; §5 role-based visibility model (mentor/super_mentor/instructor/operator/compliance_reviewer/config_admin/admin) with super-mentor transitive visibility rule and governance boundary authorization table; §6 async operation model with job pattern, polling expectations, and failure visibility including `stale_insight_available`; §7 filtering/query semantics (time-window, config version, fingerprint, timeline event attribution); §9 Snapshot APIs (draft creation, lifecycle transitions, finalized retrieval, historical lookup, fingerprint inspection, lineage traversal, historical comparison); §10 Report APIs (generation, published retrieval, version lookup, publication history, publish, regeneration, source fingerprint); §11 AI Insight APIs (active retrieval with stale flag, version history, specific version, generation with force-refresh idempotency, PRODUCTION review gate, provenance inspection, snapshot isolation behavior guarantee); §12 Config Version Registry APIs (active version, historical lookup, version list, proposal with rollback prohibition, lifecycle transitions with atomic APPROVED→ACTIVE, lineage traversal, snapshots-referencing-version); §13 Compliance APIs (workflow request, status, lifecycle transitions with BEGIN_EXECUTION hard gate, audit log visibility, audit export survivability guarantee); §14 Timeline and Lineage APIs (extended timeline with origin_source/authority/is_authoritative, generic lineage traversal, fingerprint divergence inspection, regeneration history); §15 extended acceptance criteria (10 cases covering immutable retrieval, lineage correctness, reproducibility visibility, governance isolation, attribution consistency, append-only behavior, config lineage); §16 unresolved API concerns (U-1 through U-11); §17 downstream implications (service layer, repositories, frontend dashboards, report rendering, orchestration); §18 references
  - Verification: specification document only (no implementation code); consistent with spec/01 §12.1–12.7 threshold field names; consistent with spec/03 state enums for all 6 domains; consistent with spec/08 access control matrix and data invariants §22; consistent with 0002/0003 migration table names and column names; super-mentor transitive visibility preserved per CLAUDE.md; all 13 output requirements from the task satisfied; PROGRESS.md hard gate satisfied

- [x] Alembic migration 0003 — config_version_registry initialization
  - Date: 2026-05-25
  - What changed: `alembic/versions/0003_config_version_registry.py` (NEW, ~270 lines) — creates `public.config_version_registry` with 24 configurable rule columns (spec/01 §12.1–12.7), governance lifecycle columns, self-referential lineage FKs, exactly-one-ACTIVE partial unique index on constant expression `(1) WHERE status = 'ACTIVE'`, column-level UPDATE grant for `config_admin_user` on governance metadata only (status, superseded_by_version_id, deactivated_at), and transactionally coupled V1 seed record at `status = 'ACTIVE'` with all spec/01 Section 12 defaults
  - Verification: Python syntax correct; revision chain `0002 → 0003` set; all 24 rule columns from spec/01 §12.1–12.7 present; exactly-one-ACTIVE invariant enforced via `uq_cvr_active_singleton` partial unique index on constant expression `(1)` (raw DDL, not op.create_index); FAD-3 compliant (prospective-only semantics; no retroactive recalculation possible); spec/10 §8.5 compliant (V1 seed in same upgrade() as CREATE TABLE, same Alembic transaction); CHECK constraint on status domain enforced; self-referential FKs on prior_version_id and superseded_by_version_id; downgrade drops table, cascading to all indexes
  - Notes: config_admin_user is a new role (not in 0002); all grants are pg_roles-guarded for dev/CI safety; payment_deviation_alert_threshold nullable per spec/01 §12.3 ("default TBD"); rule_set_snapshot_json is an inline JSONB object duplicating all 24 rule values for one-shot reproducibility audit without column joins

- [x] spec/05_external_integrations.md — full evolution to governed integration architecture spec
  - Date: 2026-05-25
  - What changed: `spec/05_external_integrations.md` rewritten from 444 lines (MVP-era GHL/LLM/Synthflow reliability doc) to ~900-line governed integration architecture specification. Existing §§1–16 replaced in full. Added: §2 Integration Philosophy (6 pillars: governed synchronization, append-only ingestion, lineage-preserving integration, replay-safe ingestion, authoritative-source boundaries, reproducibility-safe synchronization); §3 Authoritative Boundary Model (system authority classification table, authoritative vs derivative distinction, operational vs historical ownership, synchronization vs mutation semantics, mirrored vs platform-owned event semantics); §4 SQL Server Integration Architecture (6 extraction domain table, synchronization philosophy with idempotent upsert semantics, incremental extraction expectations per scope, attribution preservation rules, replay safety, conflict handling, mirrored-event semantics, historical snapshot isolation boundary); §5 GHL / Communication Provider Integration (provider ownership boundaries, communication event ingestion with deduplication keys, attribution preservation, timeline synchronization, deduplication expectations, replay handling, future provider extensibility contract); §6 AI Provider Integration (role boundary, integration scope, prompt version attribution immutability, model version attribution, refresh lineage, reproducibility expectations per FAD-1, retry semantics per scope, failure visibility with stale serving, frozen snapshot isolation per INVARIANT-3, provider independence); §7 Snapshot Generation Orchestration (conceptual orchestration sequence across 6 phases: preconditions, DRAFT assembly, content lock, AI enrichment, fingerprint freezing, finalization; AI enrichment boundary, fingerprint freezing, orchestration ownership, append-only guarantees, replay safety table, failure recovery table, historical regeneration boundary per FAD-2); §8 Configuration Registry Integration (how consumers read ACTIVE config, historical config reference for audit, prospective-only semantics for integration consumers, exactly-one-ACTIVE guarantee for integration consumers); §9 Event Ingestion and Timeline Integration (event ingestion architecture, timeline normalization with attribution_timestamp vs ingestion_timestamp, attribution propagation rules, replay-safe ingestion mechanisms, unified timeline expectations, event ordering, eventual consistency assumptions); §10 Compliance and Governance Integration (architecture overview, compliance export architecture, audit export content, deletion workflow integration boundaries with hard gate, survivability guarantees, governance isolation boundaries); §11 Failure and Retry Semantics (partial synchronization recovery, failure classification table across 17 failure types, duplicate ingestion handling table, stale AI at snapshot time, provider outage handling, reconciliation expectations, attribution preservation during retries); §12 Future Integration Extensibility (additional AI providers, CRM providers, communication providers, vector-search and RAG systems, analytics warehouses, compliance export systems); §13 Acceptance Criteria (7 cases: replay-safe ingestion, lineage preservation, attribution consistency, reproducibility preservation, append-only guarantees, authoritative-boundary preservation, governance isolation); §14 Downstream Implications (service layer table, scheduler jobs table, ETL jobs table, AI orchestration table, observability requirements table); §15 Unresolved Integration Concerns (UI-1 through UI-7); §16 Integration Invariants; §17 Scope-Specific Behavior Summary (MVP/STANDARD/PRODUCTION); §18 References
  - Verification: specification document only (no implementation code); consistent with spec/01 operational domains and cohort rules; consistent with spec/03 §39 Event Attribution Standard and §40 Cross-Domain Invariants; consistent with spec/04 idempotency keys per domain and CONC-INVARIANT-1 through CONC-INVARIANT-7; consistent with spec/07 API contracts for sync, snapshot, report, AI insights, config version, compliance endpoints; consistent with spec/08 dual-database architecture, three-schema separation, and data authority levels; consistent with spec/09 physical boundary map, append-only enforcement, access control profiles; consistent with 0002/0003 migration table names and permission model; FAD-1 (frozen AI copy), FAD-2 (snapshot-centric historical), FAD-3 (prospective-only config), FAD-4 (compliance isolation), FAD-5 (SQL Server read-only), FAD-6 (reproducibility fingerprint) all preserved; PROGRESS.md hard gate satisfied

- [x] Alembic migration 0002 — warehouse and compliance_audit schema initialization
  - Date: 2026-05-25
  - What changed: `alembic/versions/0002_warehouse_schema.py` (NEW, ~370 lines) — full Alembic migration creating `warehouse` schema (4 tables) and `compliance_audit` schema (2 tables) in the same file per FAD-4. Tables created: `warehouse.student_snapshots` (identity/lifecycle, ss_-prefixed SQL Server metric copy columns, derived metrics, communication summary, 5-component reproducibility fingerprint, metadata); `warehouse.snapshot_ai_narratives` (1:1 AI text companion; FK to student_snapshots NOT to ai_insights per FAD-1; advisory ai_source_insight_id_hint INTEGER with no FK constraint); `warehouse.monthly_reports` (lineage-versioned with self-referential parent_report_id FK; JSONB report_content_json, aggregate_stats_json, source_snapshot_fingerprint_json; idempotency key); `warehouse.report_audit_log` (append-only lifecycle log; FK to monthly_reports); `compliance_audit.deletion_log` (permanent append-only audit trail; no FK to public or warehouse schemas; plain INTEGER student_id for survivability); `compliance_audit.scope_manifests` (append-only version lineage; is_current column OMITTED per spec/10 correction 1; manifest_version ordering pattern). Indexes created: partial unique `(student_id, snapshot_month) WHERE status='FINALIZED'` on student_snapshots; partial unique `(cohort_id, report_month, lineage_version) WHERE status='REPORT_PUBLISHED'` on monthly_reports; unique `report_idempotency_key` on monthly_reports; unique `snapshot_id` on snapshot_ai_narratives; fingerprint column indexes (config_registry_version, schema_version) for audit queries; timeline query indexes; compliance indexes. Permission grants implemented with pg_roles existence guards: `app_service_user` SELECT on both schemas; `finalization_service_user` INSERT on warehouse tables + sequence USAGE; `compliance_pathway_user` INSERT on compliance_audit tables + sequence USAGE + column-level UPDATE(status) on warehouse.student_snapshots (sole exception to INSERT-only model; spec/10 correction 2). Full downgrade path reverses grants, drops tables in FK dependency order, drops schemas. Module docstring documents both critical corrections, two-table rationale, service account naming, and future migration grant obligations.
  - Verification: Python syntax correct; revision chain `0001 → 0002` set; all spec/09 column groups implemented; both spec/10 corrections applied (no is_current, UPDATE grant present); FAD-1 compliant (snapshot_ai_narratives FK to student_snapshots, not ai_insights); FAD-4 compliant (both schemas in same migration); all partial unique indexes use `postgresql_where` clause; downgrade order respects FK dependencies

- [x] Conceptual data model evolution — extend from operational outreach storage to governed historical-intelligence architecture
  - Date: 2026-05-25
  - What changed: `spec/08_data_model.md` — evolved from 453 to 1,475 lines; Section 1 (PURPOSE) rewritten to define 7 platform capabilities and platform capability summary table with governance boundaries per capability; Section 2 (DATABASE OVERVIEW) rewritten to DATABASE ARCHITECTURE with PostgreSQL schema separation (public / warehouse / compliance_audit), schema-level access control matrix, expanded data sources table, and conceptual data class mutability table; Section 7 (STATE FIELD ENUMS) expanded from outreach-only to all 6 lifecycle domains (Domains 1–6) with state diagrams and governance boundary annotations; Section 8 (MIGRATION STRATEGY) updated from migration-lite to Alembic-primary with upcoming migration table (0002–0006) and rules; Section 9 (DATA CONSISTENCY RULES) expanded from 5 bullets to 7 subsections (universal, outreach, snapshot, report, AI, config, compliance, cross-schema); Section 10 (SCOPE-SPECIFIC BEHAVIOR) expanded from MVP/LIVE to MVP/STANDARD/PRODUCTION with per-domain behavior table; Section 11 (ACCEPTANCE CRITERIA) expanded from 4 cases to 12 cases covering all governance boundaries; Section 12 (DOWNSTREAM IMPLICATIONS) table mapping conceptual entities to downstream artifacts; appended Sections 13–26 covering: Section 13 Schema Ownership Architecture (public/warehouse/compliance_audit with access control matrix); Section 14 Snapshot-Centric Historical Architecture (StudentSnapshot, SnapshotReproducibilityFingerprint, FrozenAINarrativeCopy, SnapshotLineage conceptual entities; draft vs finalized behavior table; snapshot-to-report relationship diagrams); Section 15 Operational Intelligence Domain Model (7 intelligence sub-domains: coursework, attendance/progression, segment classification, financial, mentor visibility, communication telemetry, access history; operational vs historical responsibility table); Section 16 Unified Event and Timeline Model (7 event types: CommunicationEvent, AccessHistoryEvent, AILifecycleEvent, SnapshotLifecycleEvent, ReportLifecycleEvent, ComplianceLifecycleEvent, ConfigLifecycleEvent; event attribution standard; unified timeline rendering spec); Section 17 AI Insight and Reproducibility Model (AIInsightRecord, AIInsightVersionHistory, FrozenSnapshotNarrative, SnapshotAIIsolationBoundary; active vs archived version table; reproducibility semantics); Section 18 Configuration Version Registry Model (ConfigVersionRecord, ConfigActivationLineage, SnapshotConfigVersionReference; governance invariants; historical auditability); Section 19 Compliance Governance Model (ComplianceWorkflowRecord, ComplianceAuditEntry, ComplianceScopeManifest; governance isolation principles; data location deletion path table; reproducibility implications after deletion); Section 20 Report Artifact and Publication Model (MonthlyReportArtifact, ReportTemplateVersion, ReportLineage, ReportSourceBinding; publication vs regeneration semantics table); Section 21 Data Ownership and Source Authority (SQL Server authoritative domains; PostgreSQL authoritative domains; data mutability classification table; mirrored data expectations); Section 22 Cross-Domain Data Invariants (8 platform-wide invariants: DATA-INVARIANT-1 through DATA-INVARIANT-8 covering append-only finalized reporting, reproducibility, AI snapshot isolation, config version consistency, compliance audit survivability, SQL Server authority, historical regeneration read-only source, governance boundary irreversibility); Section 23 Future-Scale Considerations (large archives, AI provider evolution, report template evolution, vector search/RAG, enterprise compliance); Section 24 Acceptance Criteria Extended (Cases 13–18 covering config lineage, classification auditability, compliance schema independence, mirrored source attribution, warehouse permission enforcement, report artifact preservation); Section 25 Downstream Implications (API contracts, warehouse schema, compliance schema, config registry, observability per domain); Section 26 References (governing documents + legacy references)
  - Verification: specification document only (no code); consistent with FAD-1 through FAD-6; consistent with spec/03_state_transition_rules.md Sections 14–45; consistent with spec/04_idempotency_concurrency.md Sections 15–26; preserves all existing operational table descriptions (Sections 3–6) unchanged

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
