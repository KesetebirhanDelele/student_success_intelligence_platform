# ux/admin_dashboard.md

---

## LAYER 12 — USER EXPERIENCE (GOVERNANCE-SAFE OPERATIONAL VISIBILITY ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-27 to reflect the finalized governed historical intelligence platform architecture. The previous version described MVP-era dashboard guidance: execution-console semantics, hardcoded `MAX_ATTEMPTS` references, "system processes" wording as a UX-visible actor, direct retry execution assumptions, weak replay visibility (none), missing immutable-lineage display constraints, missing Config V2 lineage visibility, missing governance-state guarantees, and MVP/STANDARD/PRODUCTION scope tiers implying incremental governance maturity rather than non-negotiable baseline guarantees. That architecture is incompatible with the governance-safe visibility model. The dashboard is no longer an operational execution console. It is a governance-safe orchestration visibility surface — replay-safe, immutable-lineage-preserving, SHADOW/LIVE isolated, and attribution-continuous.
>
> **Canonical parents:** This document is governed by `ux/user_experience.md` (§3, §5, §6, §10, §12) and `ux/operator_workflows.md`. Where this document conflicts with those contracts, those contracts govern.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Operational Visibility Architecture** defines:

* What the admin dashboard is permitted to display, surface, and trigger — and what it is explicitly prohibited from doing
* How governance state is surfaced across all 10 summary cards without computing, caching, or deriving state independently
* How SHADOW containment and replay isolation are visibly enforced across every dashboard component
* How immutable lineage artifacts are displayed without implying mutability
* How attribution continuity fields are surfaced on every orchestration record
* How degradation states remain permanently observable and never silently hidden
* How governed operator action surfaces invoke governed API endpoints only — never bypass the orchestration boundary
* How Config V2 lineage values are displayed read-only — never as editable overrides
* How access control enforces governance visibility boundaries across role tiers

This document is a **child governance contract** governed by:

* `ux/user_experience.md` — canonical UX governance contract; §3, §5, §6, §10, §12 govern all dashboard surfaces
* `ux/operator_workflows.md` — canonical operator governance workflow contract; all lifecycle tab workflows and manual action workflows are governed by it

---

### 1.2 What Dashboard Visibility Is NOT

In the governance-safe visibility model, the admin dashboard is explicitly **NOT**:

* **A workflow execution console** — the dashboard does not guide operators through orchestration decisions; it surfaces governance state produced by the backend directive layer
* **A business logic surface** — no eligibility evaluation, retry authorization, threshold comparison, or channel selection logic lives in the dashboard; the dashboard displays the output of backend governance evaluation only
* **A direct execution surface** — dashboard controls invoke governed API endpoints; they do not directly trigger provider dispatch, state transitions, or AI inference
* **A mutable interface for immutable artifacts** — FINALIZED snapshots, REPORT_PUBLISHED reports, and archived AI insights are read-only visibility surfaces; the dashboard must never render a control implying these artifacts can be modified
* **A replay execution surface** — replay outputs are displayed for visibility only; the dashboard cannot initiate live effects through replay pathways
* **A governance bypass surface** — no dashboard control bypasses the orchestration governance boundary, overrides Config V2 threshold values, or substitutes for governed API authorization

---

### 1.3 Dashboard Governance Layer Definition

The dashboard sits above the governance-authorized API boundary.

| Dashboard surface | Permitted operations | Prohibited operations |
|---|---|---|
| Read cards (System Health, Alerts, KPI, State Distribution) | Display governance state, mode badges, alert classifications, lineage attribution from API | Compute or cache governance state independently of API |
| Operator action cards (Manual Actions, Trigger Outreach Batch, SQL Server Sync) | Invoke governed API endpoints with operator identity; display API authorization results | Bypass API layer; construct outbound payloads; modify records directly |
| Channel Performance card | Display provider suppression state, attempt counts, shadow counts, mode labels | Label SUPPRESSED providers as failed; display SHADOW as LIVE |
| Recent Activity card | Display governance events with `execution_mode`, `correlation_id`, `execution_type` | Aggregate SHADOW and LIVE records into an unlabeled list |
| Student Cases card | Display student lineage fields, attribution continuity, state transitions via read endpoint | Render edit/delete controls; modify attribution fields; suppress `ATTRIBUTION_INCOMPLETE` indicators |
| Lifecycle tabs | Display student cohort data, action bars for governed API invocations | Compute eligibility; render threshold override controls; trigger direct provider actions |
| SHADOW→LIVE transition controls | Display transition form to Governance Administrator role only | Surface transition controls to non-Governance-Administrator roles |

---

## 2. DASHBOARD VISIBILITY MODEL

---

### 2.1 Governance-Safe Orchestration Visibility Principle

> The dashboard is a **read + controlled-invocation surface** only.
> All orchestration decisions originate in the backend directive layer.
> Operators observe governance state and invoke governed API endpoints — they do not make orchestration decisions.

The visibility model is:

```
Backend Orchestration  →  Governance State  →  API Endpoints  →  Dashboard Display / Invocation
                                                      ↑
                                          Operator-authorized API invocations only
```

---

### 2.2 Governance-Safe Dashboard Objectives

The dashboard MUST enable operators to answer:

* What is the current execution mode? (`SHADOW / LIVE / DEGRADED / MAINTENANCE` — always visible in header)
* What governance alerts are active, and what is their severity, error class, and recovery path?
* Which governance domains are degraded, and what is the recovery path?
* Which students have governance-notable states? (alerts referencing student_id, state distribution)
* What governed actions has the system produced? (Recent Activity with attribution continuity)
* What is the current Config V2 version governing orchestration? (visible read-only indicator)
* What governed actions can I invoke, and under what execution mode?

---

### 2.3 Mode-Aware Visibility Semantics

| Component | SHADOW mode behavior | LIVE mode behavior | DEGRADED mode behavior |
|---|---|---|---|
| Channel Performance | All providers labeled `SUPPRESSED` — expected state, not failure; `shadow_count = attempt_count` | Normal metrics | Affected channels labeled `UNAVAILABLE` with severity |
| Manual Actions card | Actions execute in SHADOW scope; audit record written; no outbound dispatch | Actions execute LIVE | Actions may be blocked if relevant domain degraded; degradation reason surfaced |
| Trigger Outreach Batch | Batch runs SHADOW — no outbound dispatch; result shows `governance_scope = SHADOW_ONLY` | Batch runs LIVE | Batch may be partially degraded; degraded domains labeled |
| SQL Server Sync | Sync proceeds (read-only pull — not outbound) | Sync proceeds | Sync blocked if SQL Server `UNAVAILABLE`; severity surfaced |
| AI Insights | Advisory tagged `outcome = shadow_only`; not a failure state | Full advisory with `ai_governance_tier` | STALE advisory served if AI provider UNAVAILABLE; `stale_ai_present = true` label |

---

## 3. DASHBOARD STRUCTURE

---

### 3.1 Layout: Command Center with Governance Header + 10 Summary Cards

The dashboard has two visible layers:

**Governance Header** (persistent, always visible):

```
[ Execution Mode Badge ]  [ Config V2 Version: read-only ]  [ Last Run Correlation ID ]  [ Alert Severity Summary ]  [ ↺ Refresh ]
```

**10 Summary Card Grid** below the header. Each card shows:

* Title
* Status badge: `OK | INFO | WARNING | CRITICAL | SHADOW | DEGRADED`
* Short governance summary line
* Key metric (where applicable)
* "View details →" affordance

Clicking any card opens a **full-screen modal overlay** with the complete detail view for that section. The modal closes via the ✕ button, backdrop click, or Escape key.

---

### 3.2 Card Sections

Cards are grouped into three labeled rows:

```
── System Status ─────────────────────────────────────
  [ System Health ]  [ Operational Alerts ]  [ KPI Summary ]

── Pipeline ──────────────────────────────────────────
  [ State Distribution ]  [ Channel Performance ]  [ Recent Activity ]

── Actions ───────────────────────────────────────────
  [ Student Cases ]  [ Manual Actions ]  [ Trigger Outreach Batch ]
  [ SQL Server Sync ]  ← full-width
```

---

### 3.3 Card Inventory

| # | Card | Badge source | Key metric | Governance additions |
|---|------|-------------|------------|---------------------|
| 1 | System Health | DB + scheduler + MSSQL + execution mode | Execution mode pill | Execution mode, Config V2 version, degradation_cause if DEGRADED, scheduler last-run correlation_id |
| 2 | Operational Alerts | Highest severity in list | Alert count | `severity`, `error_class` (never generic), `affected_domains`, `recovery_path` |
| 3 | KPI Summary | INFO | Tracked count | 8-metric grid + 3 conversion pills; Config V2 version visible read-only |
| 4 | State Distribution | INFO | Active state count | Full state-by-state count with governance state labels |
| 5 | Channel Performance | SHADOW or OK | Total attempts | SUPPRESSED vs UNAVAILABLE distinction; `execution_mode` label per record |
| 6 | Recent Activity | INFO | Event count | Structured table: `execution_mode`, `execution_type`, `correlation_id` per row |
| 7 | Student Cases | INFO | — | Student lineage; `ATTRIBUTION_INCOMPLETE` surfacing; attribution fields on every record |
| 8 | Manual Actions | SHADOW or OK | — | Governed API invocation only; Config V2 ceiling surfaced; rejection reasons surfaced |
| 9 | Trigger Outreach Batch | SHADOW or OK | — | Governance scope label; SHADOW containment confirmation in result |
| 10 | SQL Server Sync | OK or WARNING | — | `origin_authority = sql_server_authoritative`; scanned/added/updated/failed counts |

---

### 3.4 Auto-Refresh

* `loadAll()` runs on page load and every **60 seconds** via `setInterval`
* All data-loading functions execute in parallel via `Promise.allSettled`
* Last refresh timestamp shown in governance header
* Refresh triggered manually via "↺ Refresh" header button
* Post-action refreshes show actual system state — not optimistic local state

---

## 4. GOVERNANCE STATE VISIBILITY (HEADER-LEVEL)

---

### 4.1 Execution Mode Badge

* Always visible in dashboard header — never hidden, never optional
* Displays: `SHADOW | LIVE | REPLAY | DEGRADED | MAINTENANCE`
* In `SHADOW` mode: persistent `SHADOW MODE` containment badge rendered alongside the mode pill — never omit
* In `DEGRADED` mode: `DEGRADED MODE` badge plus `degradation_cause` visible in header
* In `MAINTENANCE` mode: explicit "orchestration loops paused" notice visible

---

### 4.2 Config Version Indicator

* Current ACTIVE config version ID displayed read-only in header
* Not an editable control — Config V2 governance is backend territory
* Any operator action confirmation modal displays this same version ID to confirm which version governs the action

---

### 4.3 Last Orchestration Run Correlation ID

* Most recent orchestration cycle's `correlation_id` visible in header
* Provides a starting point for lineage tracing without requiring student-case navigation
* Links to full execution mode and attribution fields when clicked (read-only view)

---

### 4.4 Alert Severity Summary

* Highest severity active alert displayed in header with badge: `CRITICAL | HIGH | MEDIUM | LOW`
* Clickable — opens Operational Alerts card detail
* If `silent_swallow = true` appears on any governance record: CRITICAL alert surfaced in header immediately

---

## 5. SYSTEM HEALTH CARD — DETAIL VIEW

---

**Backend:** `GET /dashboard/health`

**Displays:**

* Execution Mode — `SHADOW / LIVE / DEGRADED / MAINTENANCE` badge
* PostgreSQL — connected / disconnected with dot indicator
* SQL Server — configured with host, or not configured
* Scheduler — active / idle; last successful run ISO timestamp or `Never ran` (WARNING)
* Last Orchestration Run — `correlation_id` of most recent cycle
* Config V2 — current ACTIVE config version ID (read-only)
* Outbound Channels — `CALL / SMS / EMAIL` availability flags; `SUPPRESSED` label in SHADOW mode; `UNAVAILABLE` label in DEGRADED mode
* Degradation detail (when `execution_mode = DEGRADED`): `degradation_cause`, `affected_domains`, `recovery_path` if available

**Badge Logic:**

| Condition | Badge |
|-----------|-------|
| PostgreSQL disconnected | CRITICAL |
| MSSQL not configured | WARNING |
| Scheduler never ran | WARNING |
| `execution_mode = DEGRADED` | DEGRADED |
| `silent_swallow = true` on any degradation record | CRITICAL |
| All healthy | OK |

**Governance invariant:** If `execution_mode = DEGRADED`, the card must display `degradation_cause` and `affected_domains` — a generic "system degraded" message without these fields is a governance display defect.

---

## 6. OPERATIONAL ALERTS CARD — DETAIL VIEW

---

**Backend:** `GET /dashboard/alerts`

**Displays:**

Flat list of alert rows. Each alert row shows:

* `severity` badge: `CRITICAL / HIGH / MEDIUM / LOW` (never custom or generic)
* `error_class`: specific governance classification — never generic "error"; examples: `TimeoutError`, `RateLimitError`, `AuthError`, `ValidationError`, `ReplayContainmentViolation`, `AttributionIncomplete`, `SilentSwallowDetected`
* `affected_domains`: which orchestration domains are impacted
* `message`: human-readable description in plain language
* `recommended_action`: governance-safe operator action if applicable (read — do not execute directly)
* `recovery_path`: what recovery orchestration has been or will be initiated (if available)
* `student_id`: when student-specific (clickable link to Student Cases lookup)

**Governance Alert Sources:**

| Severity | Source condition |
|----------|-----------------|
| CRITICAL | PostgreSQL disconnected |
| CRITICAL | `silent_swallow = true` on any governance record |
| CRITICAL | `live_effects_produced ≠ 0` on a replay record (replay containment violation) |
| CRITICAL | SHADOW containment failure (SHADOW outputs rendered or dispatched as LIVE) |
| HIGH | `execution_mode = DEGRADED` with `affected_domains` populated |
| HIGH | Attribution incomplete on student record with governance consequence |
| MEDIUM | SQL Server not configured or sync failed |
| MEDIUM | Fingerprint mismatch on current snapshot vs stored FINALIZED record |
| WARNING | Student in `CONTACTED` state > 48 hours |
| WARNING | Student in `NO_RESPONSE` with missed retry window (Config V2-governed) |
| WARNING | Scheduler has never run |
| WARNING | `ATTRIBUTION_INCOMPLETE` record surfaced for a student |
| INFO | `execution_mode = SHADOW` — expected governance state |
| INFO | Synthflow or GHL API key missing (outbound SUPPRESSED in SHADOW mode) |

**Governance distinction:** `SHADOW` containment indicators are **not** failure alerts — they are expected governance state indicators. In SHADOW mode, providers show `SUPPRESSED`, which is correct governance behavior. Do not surface these as failure conditions.

---

## 7. KPI SUMMARY CARD — DETAIL VIEW

---

**Backend:** `GET /dashboard/summary`

**Displays:**

* Tracked, Ever Contacted, Responded, No Response, Intervention Required, Resolved, Closed, Shadow Executions
* Conversion pills: Contacted Rate, Response Rate, Resolution Rate
* Config V2 version (read-only) confirming which version governed the current metrics window

---

## 8. STATE DISTRIBUTION CARD — DETAIL VIEW

---

**Backend:** `GET /dashboard/summary` (`by_state` field)

**Displays:**

State pill + count for each active state in lifecycle order:

`ELIGIBLE → QUEUED → CONTACTED → NO_RESPONSE → RETRY → RESPONDED → ANALYZED → INTERVENTION_REQUIRED → RESOLVED → CLOSED`

Each state pill includes:
* Count of students currently in that state
* `execution_mode` filter toggle (show SHADOW vs LIVE vs All records)

**Governance note:** `CLOSED` is a terminal state. Students in `CLOSED` will not progress to further states — this is governance behavior, not a data gap.

---

## 9. CHANNEL PERFORMANCE CARD — DETAIL VIEW

---

**Backend:** `GET /dashboard/channel-performance`

**Displays:**

Table with one row per channel (CALL, SMS, EMAIL):

* Attempts, Shadow Count, Responses, No Response, Success %
* `execution_mode` label per channel record

**SHADOW/LIVE distinction (required):**

| Condition | Channel display |
|-----------|----------------|
| `execution_mode = SHADOW` | All providers labeled `SUPPRESSED` — expected governance state, not failure |
| `execution_mode = LIVE` | Normal metrics; `SUPPRESSED` label absent |
| `execution_mode = DEGRADED` | Affected channels labeled `UNAVAILABLE` with severity classification |

**Governance invariant:** In SHADOW mode, `shadow_count = attempt_count` is the expected invariant. If `shadow_count < attempt_count` while in SHADOW mode, this is a containment anomaly and must surface as a governance alert.

---

## 10. RECENT ACTIVITY CARD — DETAIL VIEW

---

**Backend:** `GET /dashboard/recent-activity?limit=20`

**Displays:**

Structured table: Time, Student ID, Checkpoint, Channel, Action, `execution_mode` badge, `execution_type`, `correlation_id` (abbreviated), State Change (From → To pill)

* `execution_mode` badge is mandatory on every row — never blank
* `execution_type` distinguishes `original | replay | regeneration | recovery`
* SHADOW rows display `SHADOW` mode indicator — never rendered as neutral/unlabeled
* Replay rows display `execution_type = replay` label and are visually distinguishable from LIVE rows
* Reload button re-fetches without closing the modal

**Governance invariant:** Mixed-mode views (records spanning a SHADOW→LIVE transition) display both execution modes distinctly per record — they are never aggregated into an unlabeled list.

---

## 11. STUDENT CASES CARD — DETAIL VIEW

---

**Backend:** `GET /students/{id}/profile`, `GET /students/{id}/outreach-history`, `GET /students/{id}/state-transitions`

**Interaction:**

1. Operator enters Student ID in lookup input
2. Invokes lookup via governed read endpoint ("Look Up")
3. Profile card appears showing: name, risk badge, program path, email, phone, HWs behind, avg effort, inactive days, current lifecycle state pill, checkpoint, attempt count (with `config_version_id` that governed the attempt count limit), last contact `correlation_id`, last contact date, next retry date

**Outreach History table (required columns):**

| Column | Governance requirement |
|--------|------------------------|
| Date | Required |
| Attempt # | Required |
| Channel | Required |
| Action | Required |
| `execution_mode` | Required — SHADOW / LIVE; never blank |
| `execution_type` | Required — original / replay / regeneration / recovery |
| `correlation_id` | Required — missing = `ATTRIBUTION_INCOMPLETE` indicator |
| `config_version_id` | Required on orchestration intent records |
| From State → To State | Required |

**State Transitions table (required columns):**

| Column | Governance requirement |
|--------|------------------------|
| Date | Required |
| From | Required |
| To | Required |
| Trigger | Required |
| Actor | Required — `system` indicates backend orchestration; operator_id indicates operator-initiated |
| `correlation_id` | Required — missing = `ATTRIBUTION_INCOMPLETE` indicator |
| `execution_mode` | Required |

**Attribution continuity:** If any record in Outreach History or State Transitions has a null `correlation_id`, `execution_mode`, or `execution_type`, the table must surface an `ATTRIBUTION_INCOMPLETE` indicator on that row. This indicator must not be dismissed and must not be suppressed.

**Not Found:** Clear error message displayed inside modal: "Student not found: No record for ID N" — no crash, no blank state.

---

## 12. MANUAL ACTIONS CARD — DETAIL VIEW

---

**Backend:** `POST /actions/manual`

**Inputs:**

* Student ID (required)
* Notes (optional free text)

**Execution Mode Gate:**

Before any action button is rendered active, the current execution mode badge must be visible. In SHADOW mode, all actions execute within SHADOW scope — no outbound dispatch occurs. The SHADOW containment badge must be visible before any action is invoked.

**Available Actions:**

| Button | `action_type` | Backend guard | Governance note |
|--------|---------------|---------------|-----------------|
| Force Retry | `FORCE_RETRY` | Blocked if `current_attempt ≥ outreach_max_retry_attempts` (Config V2 Group A); rejection: `MAX_ATTEMPTS_REACHED` | Config V2-governed ceiling; no operator override |
| Mark Resolved | `MARK_RESOLVED` | State machine must allow; blocked from `CLOSED` | `RESOLVED` is not terminal — do not treat as such |
| Close Case | `CLOSE_CASE` | Blocked if already `CLOSED`; rejection: `STATE_TRANSITION_NOT_ALLOWED` | `CLOSED` is terminal per `spec/03_state_transition_rules.md` |
| Escalate | `ESCALATE` | Valid from: `CONTACTED`, `NO_RESPONSE`, `RETRY`, `RESPONDED`; blocked from `CLOSED`, `ELIGIBLE`, `QUEUED`, `ANALYZED`, `INTERVENTION_REQUIRED`, `RESOLVED` | Produces `INTERVENTION_REQUIRED` transition; audit record written with `operator_identity` and `correlation_id` |

**Feedback:**

* Result shown inline below buttons with: governance authorization confirmation or rejection reason
* Rejection reasons surfaced verbatim — `MAX_ATTEMPTS_REACHED`, `STATE_TRANSITION_NOT_ALLOWED`, `COMPLIANCE_HOLD_ACTIVE` — never coerced to generic errors
* Audit confirmation receipt displayed: `correlation_id`, `execution_mode`, `timestamp` — confirms audit record was written
* Action log console shows timestamped entries with `execution_mode` label per entry
* On success: `loadSummary()`, `loadAlerts()`, `loadActivity()` auto-refresh to reflect actual system state

**Governance invariants enforced in this surface:**

* No action executes without a Student ID
* All actions invoke `POST /actions/manual` — no direct provider calls
* Every action produces `OutreachHistory` + `StateTransitionLog` records
* Config V2-governed thresholds are displayed read-only — no override control is rendered

---

## 13. TRIGGER OUTREACH BATCH CARD — DETAIL VIEW

---

**Backend:** `POST /outreach/trigger`

**Inputs:**

Checkpoint selector: `SQL | SSRS | SSIS | POST_COMPLETION`

**Execution Mode Gate:**

Execution mode badge visible before "Run Batch" button is active. In SHADOW mode, batch runs SHADOW — no outbound dispatch.

**Result:**

Displays: `Done — triggered:N retried:N skipped:N errors:N`

In SHADOW mode, result additionally shows: `governance_scope = SHADOW_ONLY — no outbound dispatch occurred`

On success: `loadSummary()`, `loadAlerts()`, `loadActivity()` auto-refresh

**Governance note:** "triggered:N" in SHADOW mode means N orchestration intents were produced and logged with `execution_mode = SHADOW`. It does not mean N outbound dispatches. The result display must not imply outbound activity in SHADOW mode.

---

## 14. SQL SERVER SYNC CARD — DETAIL VIEW

---

**Backend:** `POST /sync/mssql`

**Action:**

Pulls latest rows from SQL Server `AI_ChatBot_TriggerData`. This is a **read-only pull** from SQL Server — it is not an outbound action and is not affected by SHADOW mode.

**Result:**

* Connected: `Sync done — scanned:N added:N updated:N failed:N`
  * `origin_source = mirrored_sql_server`, `origin_authority = sql_server_authoritative` confirmed
  * Dedup gate result displayed when duplicate detected: `duplicate_detected`, `dedup_gate_applied`
  * Conflict attribution when SQL Server overrides a GHL record: winning source visible
* Not configured: `SQL Server not configured (credentials pending)`

**Badge:**

Set by `GET /dashboard/health` MSSQL configured field — WARNING if not configured, OK if configured.

**Provider boundary note:** `origin_authority = sql_server_authoritative` means SQL Server wins on conflict with GHL-supplemented data. This is expected governance behavior — not a data error.

---

## 15. STUDENT LIFECYCLE TABS

---

### 15.1 Tab Overview

The dashboard home page includes six tabbed views below the 10-card summary grid. Each tab is a governance-visible data table driven by a dedicated lifecycle read endpoint.

| Tab Name | Endpoint | Filter Criteria |
|----------|----------|-----------------|
| Newcomers | `GET /lifecycle/newcomers` | IPBCStartDate within last 90 days |
| Engagement | `GET /lifecycle/engagement` | All students |
| HW Risk | `GET /lifecycle/hw-risk` | IPBCStartDate not null |
| CAP Hopefuls | `GET /lifecycle/cap-hopefuls` | IPBCStartDate not null AND AttendancePercentage > 50 |
| Launch Hopefuls | `GET /lifecycle/launch-hopefuls` | Attendance > 70% AND section contains "CAP Project" |
| Placement Hopefuls | `GET /lifecycle/placement-hopefuls` | Attendance > 70% AND section contains "Launch" |

---

### 15.2 Tab Features (All Tabs)

* Search across all columns (client-side)
* Sort by any column header
* Pagination (50 rows/page default)
* CSV export (read-only governance record)
* Row click → right-side detail drawer opens for that student
* Row selection highlights selected row — activates action bar
* **SHADOW MODE badge always visible** next to action bar when `execution_mode = SHADOW`

---

### 15.3 Action Bar (Governance-Safe)

Each tab has an action bar above the table. Buttons are **disabled by default** and **enabled only after row selection**. Selected student's name is shown in the label next to the buttons.

On button click:

1. Current execution mode badge must be visible before button is active
2. `POST /quick-actions/log` is called with: `student_user_id`, `action_key`, `action_label`, `tab_name`, `operator_identity`
3. Inline result shows: governance authorization confirmation with `correlation_id`, or rejection with reason
4. Action recorded in both `student_quick_action_log` (audit) and `student_campaign_activity` (populates "Last Campaign Activity" columns)
5. In SHADOW mode: no real outbound communication; `execution_mode = SHADOW` label shown in result

**Governance note:** The action bar invokes governed API endpoints. It does not construct outbound payloads, trigger provider APIs, or bypass the orchestration boundary. The audit record for every button click carries `operator_identity` and `correlation_id`.

---

### 15.4 Per-Tab Column Schemas

#### Newcomers (17 columns)
Student Name, UserID, Email, Phone, Program Path, IPBC Start Date, Weeks in Program, HW Submitted (days ago), Attendance %, Active, Status I, Status II, Last Campaign Activity Date, Last Campaign Activity Type, Last Campaign Activity, Campaign Notes, Notes

#### Engagement (18 columns)
Student Name, UserID, Email, Phone, Program Path, IPBC Start Date, Weeks in Program, Class Name, Last Activity Section, HW Submitted (days ago), Last Login Days, Attendance %, Active, Last Campaign Activity Date, Last Campaign Activity Type, Last Campaign Activity, Campaign Notes, Notes

#### HW Risk (20 columns)
Student Name, UserID, Email, Phone, Program Path, IPBC Start Date, Weeks in Program, HWs Behind, Avg Effort Rating, Last Activity Days, HW Submitted (days ago), Last Login Days, Attendance %, Active, Status I, Status II, Last Campaign Activity Date, Last Campaign Activity Type, Last Campaign Activity, Notes

#### CAP Hopefuls (20 columns)
Student Name, UserID, Email, Phone, Program Path, IPBC Start Date, Weeks in Program, Class Name, Last Activity Section, HW Submitted (days ago), Attendance %, Active, Status I, Status II, Total Payments, Payment Balance, Fee Paid, Last Campaign Activity Date, Last Campaign Activity, Notes

#### Launch Hopefuls (20 columns)
Same as CAP Hopefuls columns (students within CAP Project section, higher attendance threshold).

#### Placement Hopefuls (28 columns)
All prior columns plus: Last Interview, Last Interview Days Ago, Recruiter Interview Count, Technical Interview Count, Recruiter:Technical Ratio, Avg Interview Prep Score, Avg Interview Score, ChatGPT Prompt. (Interview fields are currently null until placement data source is integrated.)

---

### 15.5 Governance Drawer (Lifecycle Tabs)

Row click opens a right-side detail drawer with five tabs:

| Drawer tab | Contents | Governance requirement |
|------------|----------|----------------------|
| **Profile** | Contact info, program path, academic metrics, risk badge | Read-only display; no edit controls |
| **Timeline** | Unified governance activity log (outreach history, GHL messages, notes, AI insights, state transitions) newest first | Each entry carries `execution_mode` and `correlation_id` — required; missing = `ATTRIBUTION_INCOMPLETE` |
| **Notes** | Internal notes; operator may add a new note | Note creation invokes governed API — not a direct DB write |
| **Outreach** | Outreach history with full attribution fields | `execution_mode`, `execution_type`, `correlation_id`, `config_version_id` on every entry |
| **AI Insights** | `ai_governance_tier` visible (`FINALIZED_COPY / AI_GENERATED / STALE / UNAVAILABLE`); advisory labeled as advisory | No AI output rendered as decision or authorization; FINALIZED narratives are read-only |

**FINALIZED AI Insights:** Narratives in `lifecycle_state = FINALIZED` are read-only in the AI Insights tab. No edit path is rendered. `allows_update = false` is confirmed by the API response and the UI reflects this without offering a modification control.

---

### 15.6 Empty-State Messaging

* Launch Hopefuls and Placement Hopefuls tabs show a descriptive empty-state note explaining their filter criteria when no rows match — not a generic "No records found"
* All tabs show `Sync students from SQL Server first` guidance if `student_trigger_data` is empty
* Tabs with `STALE_SQL_SERVER_DATA` badge visible instruct: "Use SQL Server Sync card to pull latest data"

---

## 16. SHADOW AND REPLAY DASHBOARD GOVERNANCE

---

### 16.1 SHADOW Mode Visibility Semantics

Every dashboard component that renders data produced in SHADOW mode must:

* Display a persistent `SHADOW MODE` containment badge — never omit, never suppress
* Label all outreach history, state transitions, and action log entries produced in SHADOW mode with `execution_mode = SHADOW` indicator
* Visually distinguish SHADOW outputs from LIVE outputs — SHADOW records must never appear identical to LIVE records

SHADOW mode dashboard invariants:

* `governance_scope = SHADOW_ONLY` visible on every SHADOW orchestration intent displayed
* Provider records in SHADOW mode display `outbound_suppressed = true` — expected governance state, not error
* AI advisory outputs in SHADOW mode display `outcome = shadow_only` — not a failure state
* No dashboard component may display a SHADOW execution as a LIVE execution
* `SUPPRESSED` ≠ `UNAVAILABLE` — SUPPRESSED is expected SHADOW governance behavior; UNAVAILABLE is a degradation condition

---

### 16.2 Replay Mode Visibility Semantics

Every replay-mode output displayed in the dashboard must:

* Display `execution_type = replay` or `execution_type = regeneration` — never render replay outputs in the same visual style as `execution_type = original` outputs
* Show `governance_scope = REPLAY_ONLY` — replay outputs are never authorized for LIVE consumption
* Display a new `correlation_id` with a visible `causation_id → original correlation_id` lineage link
* Show `historical_config_version_id` — replay uses historical config, not the current ACTIVE config version
* Display `live_effects_produced = 0` — the expected invariant; non-zero = CRITICAL governance alert

Replay mode dashboard invariants:

* Replay outputs must never appear alongside LIVE outputs without explicit mode differentiation per record
* Replay outputs must never render as actionable for LIVE execution
* A replay with `replay_partial = true` must display a `PARTIAL REPLAY` warning badge
* `POTENTIALLY_DIVERGENT` fingerprint comparison outcome must display a visible warning badge — divergence is not suppressed

---

### 16.3 SHADOW→LIVE Transition Visibility

The SHADOW→LIVE transition is a governance-authorization event surfaced in the dashboard for the Governance Administrator role only.

**Visibility governance:**

* Transition control is rendered **only when `execution_mode = SHADOW` AND operator role = `Governance Administrator`**
* Non-Governance-Administrator roles: transition control is not rendered, or is visibly disabled with access restriction indicator
* Transition form must display: `from_mode: SHADOW`, `to_mode: LIVE`, activation record ID field (required), explicit acknowledgement checkbox
* Submission blocked until both activation record ID and acknowledgement checkbox are confirmed
* Backend rejection reason surfaced verbatim — no silent failure

**Governed by:** `ux/user_experience.md` §4.2, AP-RT7, CV2-4

---

### 16.4 Replay Attribution Visibility

Every replay record displayed must surface lineage attribution:

* `causation_id` → original cycle's `correlation_id` — displayed as a lineage link
* `historical_config_version_id` — the config version that governed the historical execution
* `fingerprint_comparison_outcome` — `IDENTICAL`, `POTENTIALLY_DIVERGENT`, or `COMPARISON_UNAVAILABLE`
* If `fingerprint_comparison_outcome = POTENTIALLY_DIVERGENT`: visible warning badge rendered — not hidden

---

## 17. IMMUTABLE-LINEAGE DASHBOARD CONSTRAINTS

---

### 17.1 FINALIZED Artifact Display Rules

Dashboard surfaces that display FINALIZED snapshots or REPORT_PUBLISHED reports must:

* Render them as **read-only** — no edit controls, no delete controls, no update affordances
* Display `lifecycle_state = FINALIZED` or `lifecycle_state = REPORT_PUBLISHED` as a badge — always visible
* Never render a FINALIZED artifact with controls implying `allows_update = true` or `allows_delete = true`
* Surface `sourced_from_warehouse = true` for regeneration outputs — confirming the source is the append-only warehouse

If the backend returns a mutation attempt on a FINALIZED artifact, the dashboard must display a governance rejection error:

```
GOVERNANCE REJECTION: This record is FINALIZED and immutable. No modifications are permitted.
```

---

### 17.2 Append-Only Historical Record Display

The dashboard must enforce append-only semantics visually:

* State transition logs are displayed in chronological order — not reorderable, not filterable to hide entries
* Outreach history records are append-only audit artifacts — no delete or edit affordances
* AI insights, once archived, display `lifecycle_state = ARCHIVED` with no modification path
* No delete or edit controls are ever rendered on records in: `state_transition_log`, `outreach_history`, `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `student_timeline_events`

---

### 17.3 Attribution Continuity Display

Every orchestration record displayed in the dashboard must show:

* `correlation_id` — present on every record; missing = `ATTRIBUTION_INCOMPLETE` indicator
* `execution_mode` — present on every record; never hidden
* `execution_type` — `original | replay | regeneration | recovery` — distinguishes record provenance
* `causation_id` — present on derived events (replay, recovery); renders as lineage link to parent event
* `config_version_id` — present on all orchestration intent records

If any of these fields is null on a displayed record, the dashboard must surface an `ATTRIBUTION_INCOMPLETE` indicator on that row — not silently blank the field.

---

### 17.4 Fingerprint Visibility

When displaying FINALIZED snapshot records:

* The five fingerprint components must be accessible in the detail view: `schema_version`, `config_registry_version`, `ai_prompt_version`, `ai_model_version`, `report_template_version`
* Any component with value `UNKNOWN_V0` must display a visible audit-gap indicator — known limitation, not an error
* Fingerprint mismatch between a stored snapshot and current system fingerprint surfaces as a `MEDIUM` severity governance alert

---

## 18. OPERATOR ACTION SURFACES

---

### 18.1 Governed API-Only Action Model

All action controls on the dashboard invoke backend API endpoints. The dashboard enforces this boundary:

* Manual Actions card → `POST /actions/manual`
* Trigger Outreach Batch card → `POST /outreach/trigger`
* SQL Server Sync card → `POST /sync/mssql`
* Lifecycle tab action bar → `POST /quick-actions/log`
* SHADOW→LIVE transition (Governance Administrator only) → governed mode transition endpoint

No dashboard control bypasses the API layer. No dashboard control constructs outbound provider payloads.

---

### 18.2 Action Authorization Visibility

The dashboard displays the governance authorization result of every API invocation:

* **Authorization confirmed:** `correlation_id` displayed inline; execution mode shown; action visible in Timeline tab
* **Rejected:** rejection reason surfaced verbatim — `MAX_ATTEMPTS_REACHED`, `STATE_TRANSITION_NOT_ALLOWED`, `COMPLIANCE_HOLD_ACTIVE`, `ATTRIBUTION_INCOMPLETE`, `IMMUTABLE_RECORD_MUTATION_REJECTED` — never suppressed, never coerced to generic error

---

### 18.3 Audit Attribution in Action Surfaces

Every operator action must produce a visible audit trail in the dashboard:

* Action log console (Manual Actions card) shows timestamped entries: `correlation_id`, `execution_mode`, `timestamp`, action type
* Audit confirmation receipt displayed inline after every action invocation
* If audit record creation fails: the dashboard must surface the failure — not proceed silently
* Timeline tab in Governance Drawer confirms audit record: newest entry shows `actor_identity = operator_id`

---

### 18.4 Config V2 Visibility in Action Surfaces

All Config V2-governed threshold values are displayed read-only in action confirmation dialogs:

* Force Retry confirmation: displays `outreach_max_retry_attempts` (current Config V2 Group A value) as read-only ceiling
* No action surface renders a threshold value as an editable field
* `MAX_ATTEMPTS_REACHED` rejection surfaces the Config V2-resolved limit value — operator must understand what governed the rejection

---

## 19. OBSERVABILITY DASHBOARD GOVERNANCE

---

### 19.1 Degradation Visibility

Degradation is a governance state — not an error to be hidden.

| Required visibility item | Location |
|--------------------------|----------|
| `DEGRADED MODE` badge | Header — persistent when `execution_mode = DEGRADED` |
| `degradation_cause` | System Health card detail AND header; plain language required |
| `affected_domains` | Operational Alerts card — which orchestration domains degraded |
| `recovery_path` | Operational Alerts card — what recovery is pending (if available) |
| `silent_swallow = true` | CRITICAL alert in Operational Alerts — governance defect |

A degraded system must never appear as fully operational. `UNAVAILABLE` providers must never display as `OK`.

---

### 19.2 Provider Boundary Visibility

All provider interactions are visible with their governance scope:

| Provider | Visibility requirement |
|----------|----------------------|
| GHL | `origin_authority = platform_supplementary` — supplementary, not authoritative |
| SQL Server | `origin_authority = sql_server_authoritative` — wins on conflict with GHL |
| Provider in SHADOW/REPLAY | `outbound_suppressed = true` — expected state, not error |
| Provider in DEGRADED | `UNAVAILABLE` with severity classification — not silently blank |

---

### 19.3 Synchronization Visibility

SQL Server sync events must surface (SQL Server Sync card detail):

* `origin_source = mirrored_sql_server`, `origin_authority = sql_server_authoritative`
* Dedup gate result when duplicate detected: `duplicate_detected`, `dedup_gate_applied`
* Sync outcome: scanned / added / updated / failed counts
* Conflict attribution when SQL Server overrides a GHL record: winning source visible

---

### 19.4 Scheduler Visibility

Scheduler state must be visible (System Health card detail):

* Last successful run timestamp — `Never ran` surfaced as WARNING
* Last orchestration cycle's `correlation_id`
* Current execution mode at time of last run
* Scheduler idle vs active state
* Any orchestration loops paused in MAINTENANCE mode

---

### 19.5 AI Governance Visibility

AI outputs must be visibly attributed (AI Insights tab in Governance Drawer):

* `ai_governance_tier`: `FINALIZED_COPY | AI_GENERATED | STALE | UNAVAILABLE`
* `advisory_scope`: `AVAILABLE | UNAVAILABLE | STALE | SHADOW_ONLY`
* Stale AI in degraded state: `stale_ai_present = true`, `stale_ai_version` visible
* SHADOW mode AI: `outcome = shadow_only` — not failure
* AI is advisory-only: no AI output may be labeled as a decision or authorization — advisory label required

---

### 19.6 Config V2 Lineage Visibility

Config V2 version lineage must be visible at multiple levels:

* Dashboard header: current ACTIVE config version ID (read-only)
* Every action confirmation: `config_version_id` of the version governing the action
* Every outreach history record: `config_version_id` that governed the orchestration cycle
* Manual Actions card: `outreach_max_retry_attempts` displayed read-only before Force Retry

No Config V2 value in the dashboard is editable. Config V2 governance is backend territory.

---

## 20. ACCESS CONTROL DASHBOARD GOVERNANCE

---

### 20.1 Role-Based Visibility Semantics

| Role | Permitted views | Prohibited views |
|------|----------------|-----------------|
| Governance Administrator | All views + SHADOW→LIVE transition controls | None |
| Operational Administrator | All operational views + manual action controls + lifecycle tab action bar | Governance transition controls; compliance-restricted audit records |
| Program Manager / Viewer | All read-only dashboard and lifecycle tab views | Manual action controls; governance transition controls; compliance records; audit-restricted governance telemetry |

---

### 20.2 Replay Access Restrictions

Replay execution metadata is visible to Operational Administrator and above:

* Viewer roles may see high-level replay status (replay in progress, replay complete) but not internal replay diagnostic fields
* Replay causation lineage (`causation_id` chains) is visible to Operator and above
* Replay divergence alerts (`POTENTIALLY_DIVERGENT`) must be visible to Operator and above — not hidden from view

---

### 20.3 Immutable Record Access Behavior

FINALIZED and REPORT_PUBLISHED records are accessible to all roles in read-only mode:

* No role may render modification controls on immutable records
* Compliance-governed deletion events visible only to `compliance_officer` and `auditor` roles
* Pre-action audit entries for compliance operations visible to authorized compliance roles only

---

### 20.4 Audit Visibility Guarantees

Governance telemetry is authoritative; operational telemetry is contextual. The dashboard must surface:

* Full audit trail of operator actions with `correlation_id` linkage
* Governance boundary crossing events: FINALIZED state changes, config version promotions, SHADOW→LIVE transitions
* Every audit entry displays: `actor_identity`, `action_type`, `execution_mode`, `timestamp`, `correlation_id`

---

## 21. DASHBOARD GOVERNANCE INVARIANTS

---

### 21.1 Cross-Domain Governance Invariants (INV-1 through INV-7)

| Invariant | Dashboard enforcement |
|-----------|----------------------|
| **INV-1** FINALIZED snapshot is immutable | No edit/delete controls rendered on FINALIZED artifacts; `lifecycle_state = FINALIZED` badge always visible |
| **INV-2** Exactly one config version ACTIVE | Dashboard header shows current ACTIVE version read-only; no multi-active state implied; `config_version_id` on every intent record |
| **INV-3** (FAD-3) Activation is prospective-only | SHADOW→LIVE transition form requires `activation_record_present` confirmation before submission; no backdated activation implied |
| **INV-4** (AP-RT2) No LIVE effects from replay | Replay outputs rendered with `REPLAY_ONLY` scope; `live_effects_produced = 0` shown as invariant; non-zero → CRITICAL governance alert |
| **INV-5** Attribution continuity | `correlation_id`, `execution_mode`, `execution_type` always displayed; null values surface `ATTRIBUTION_INCOMPLETE` indicator |
| **INV-6** (FAD-1) FINALIZED_COPY immutability | AI narratives in FINALIZED state rendered read-only in AI Insights tab; `allows_update = false` confirmed; no edit path |
| **INV-7** No hardcoded thresholds | Config V2 resolved values shown read-only; no dashboard control allows threshold override; `MAX_ATTEMPTS_REACHED` rejection surfaces Config V2-governed limit |

---

### 21.2 FAD Visibility in Dashboard (FAD-1 through FAD-6)

| FAD | Dashboard visibility behavior |
|-----|-------------------------------|
| **FAD-1** FINALIZED_COPY immutability | AI narratives in FINALIZED state: read-only view in AI Insights tab; no edit path rendered |
| **FAD-2** Regeneration reads warehouse exclusively | Regenerated reports labeled `sourced_from_warehouse = true`; no live inference indicator |
| **FAD-3** Prospective-only activation | SHADOW→LIVE transition form requires future-dated or current confirmation only; no backdated activation |
| **FAD-4** Append-only audit log | Audit records displayed with no delete/edit affordances; chronological only |
| **FAD-5** Config V2 governance | Threshold values in all action surfaces are read-only resolved values; no override controls rendered |
| **FAD-6** Snapshot fingerprint reproducibility | Fingerprint components always visible on FINALIZED record detail; `UNKNOWN_V0` surfaces audit-gap indicator |

---

### 21.3 Append-Only Visibility Guarantees

The dashboard must enforce append-only semantics visually:

* Historical records in Timeline, Outreach History, and State Transitions may not appear editable
* Audit log entries are displayed in append order only — no filter hides entries from the visible window
* Delete controls are never rendered on records in: `state_transition_log`, `outreach_history`, `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `student_timeline_events`

---

### 21.4 SHADOW/LIVE Isolation Guarantees

The dashboard must never allow SHADOW and LIVE outputs to appear interchangeable:

* Every record carries an explicit `execution_mode` badge
* SHADOW records display `SHADOW` mode indicator — never blank
* LIVE records display `LIVE` mode indicator
* Mixed-mode views (records spanning a mode transition) display both execution modes distinctly per record — never aggregated into an unlabeled list
* Execution mode is permanent metadata — it does not update when the system transitions modes

---

## 22. PERFORMANCE CONSTRAINTS

---

* Dashboard load time ≤ 2 seconds
* API response ≤ 500 ms
* Pagination for large datasets (50 rows/page default)
* Auto-refresh every 60 seconds; manual refresh via "↺ Refresh" header button
* Post-action refreshes reflect actual system state — not optimistic local state

---

## 23. ERROR HANDLING (GOVERNANCE-AWARE)

---

### 23.1 Governance-Aware Error Display

Error messages must:

* Display the governance reason, not a generic message — `MAX_ATTEMPTS_REACHED`, `COMPLIANCE_HOLD_ACTIVE`, `STATE_TRANSITION_NOT_ALLOWED`, `ATTRIBUTION_INCOMPLETE`, `IMMUTABLE_RECORD_MUTATION_REJECTED`
* Never expose internal stack traces or secrets in error text
* Surface the `error_class` from the backend response — not coerced to "Something went wrong"

---

### 23.2 Mode-Aware Error Handling

* In SHADOW mode: errors from suppressed providers display `SUPPRESSED — expected in SHADOW mode`, not as provider failures
* In DEGRADED mode: errors from unavailable providers display with `UNAVAILABLE` and `severity` classification — not as generic errors
* In REPLAY mode: any error that would generate a LIVE effect surfaces as a CRITICAL containment violation — not silently suppressed

---

### 23.3 FINALIZED Mutation Rejection

If the backend rejects a mutation attempt on a FINALIZED record:

* Display: `GOVERNANCE REJECTION: This record is FINALIZED and immutable. No modifications are permitted.`
* Do not retry the mutation
* Do not surface "try again later" — this implies eventual mutability

---

## 24. ACCEPTANCE CRITERIA (GOVERNANCE-SAFE DASHBOARD CERTIFICATION)

---

### Case 1 — SHADOW Containment Visibility

**Given** `execution_mode = SHADOW`
**When** dashboard loads
**Then** `SHADOW MODE` badge visible in header; all outreach history records labeled `execution_mode = SHADOW`; Channel Performance shows all providers as `SUPPRESSED`; no SHADOW record rendered as LIVE

---

### Case 2 — Replay Isolation Visibility

**Given** replay execution records exist in audit trail
**When** operator views Recent Activity or Outreach History including replay records
**Then** replay records display `execution_type = replay`, `governance_scope = REPLAY_ONLY`; `causation_id` visible linking to original `correlation_id`; `live_effects_produced = 0` confirmed; replay records never rendered as LIVE

---

### Case 3 — Immutable Lineage Visibility

**Given** FINALIZED snapshot exists
**When** operator views snapshot detail via Student Cases
**Then** `lifecycle_state = FINALIZED` badge visible; no edit/delete controls rendered; five fingerprint components accessible; `allows_update = false` confirmed; any rendering of modification controls is a test failure

---

### Case 4 — Attribution Continuity Visibility

**Given** any orchestration record displayed in Student Cases Outreach History or State Transitions
**When** record detail is visible
**Then** `correlation_id`, `execution_mode`, `execution_type` are all non-null; missing fields surface `ATTRIBUTION_INCOMPLETE` indicator; indicator is not dismissed

---

### Case 5 — Degradation Visibility

**Given** `execution_mode = DEGRADED` with `affected_domains` populated
**When** dashboard loads
**Then** `DEGRADED MODE` badge visible in header; `degradation_cause` and `affected_domains` surfaced in Operational Alerts; `recovery_path` shown where available; no degraded component appears as fully operational

---

### Case 6 — Provider Boundary Visibility (SUPPRESSED vs UNAVAILABLE)

**Given** SHADOW mode active
**When** operator views Channel Performance card
**Then** all providers display `SUPPRESSED` — not `UNAVAILABLE`, not failed; `shadow_count = attempt_count`; SHADOW mode note visible; `SUPPRESSED` label clearly distinct from `UNAVAILABLE`

---

### Case 7 — Replay Containment Violation Surfacing

**Given** a replay record exists with `live_effects_produced ≠ 0`
**When** that record is surfaced in Recent Activity or Student Cases
**Then** CRITICAL governance alert emitted in Operational Alerts; replay containment violation visible on the record; record labeled as governance defect — not silently displayed as a normal replay record; operator cannot dismiss without acknowledgement

---

### Case 8 — SHADOW→LIVE Transition Authorization Gate

**Given** Governance Administrator initiates SHADOW→LIVE transition
**When** transition form rendered
**Then** `from_mode: SHADOW` and `to_mode: LIVE` displayed; activation record ID field is required; confirmation checkbox required; submission blocked until both present; API rejection surfaces reason verbatim; no automated submission pathway

---

### Case 9 — Config V2 Visibility in Manual Actions

**Given** operator attempts Force Retry on a student at Config V2-governed attempt ceiling
**When** Force Retry is clicked
**Then** `MAX_ATTEMPTS_REACHED` rejection surfaces inline; rejection message displays Config V2-resolved limit value read-only; no override control is rendered; operator cannot circumvent the Config V2 ceiling

---

### Case 10 — Governance Invariant Consistency (Non-Governance-Administrator Access Gate)

**Given** Operational Administrator role (not Governance Administrator)
**When** dashboard renders with `execution_mode = SHADOW`
**Then** SHADOW→LIVE transition control is not rendered, or is visibly disabled with access restriction indicator; no pathway to transition from this role is available in the dashboard

---

## 25. REFERENCES

---

Inherits from and is governed by:

* `ux/user_experience.md` — canonical UX governance contract; §3, §5, §6, §10, §12 govern all surfaces in this document
* `ux/operator_workflows.md` — canonical operator governance workflow contract; lifecycle tab workflows and manual action workflows governed by it
* `spec/01_requirements.md` — platform purpose, operational domains, FAD governance model
* `spec/03_state_transition_rules.md` — INV-1 through INV-7, terminal state governance, compliance deletion governance
* `spec/05_external_integrations.md` — lineage-preserving integration fields, SQL Server authority boundary
* `spec/06_observability_operations.md` — two-category telemetry model, governance-aware observability
* `spec/07_api_contracts.md` — all API endpoint contracts governing operator action surfaces
* `runtime/system_loop.md` — six runtime modes, AP-RT7, ten orchestration domains, degradation governance
* `runtime/scheduler_design.md` — scheduler visibility requirements, recovery cycle attribution
* `runtime/daily_outreach_flow.md` — daily cycle governance and SHADOW mode behavior
* `runtime/retry_cycle_flow.md` — retry policy governance, Config V2 Group A
* `failure/failure_playbook.md` — canonical resilience governance, AP-FP rules, degradation condition table
* `failure/scheduling_failures.md` — scheduler failure context
* `failure/ghl_failures.md` — provider failure context, SUPPRESSED vs UNAVAILABLE distinction
* `failure/llm_failures.md` — AI governance failure context
* `tests/test_shadow_safety.py` — executable SHADOW and replay containment certification
* `tests/test_dashboard.py` — executable observability governance certification
* `tests/test_sync.py` — executable synchronization governance certification
* `tests/test_actions.py` — executable operator action governance certification
* `tests/test_work_queue.py` — executable work queue governance certification

---

## END OF FILE
