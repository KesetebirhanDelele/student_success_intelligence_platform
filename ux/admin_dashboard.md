# ux/admin_dashboard.md

---

## LAYER 12 — USER EXPERIENCE (ADMIN DASHBOARD)

---

## 1. PURPOSE

This file defines:

* Admin dashboard structure
* Key views and components
* Data visualization requirements
* Operator controls and workflows

The goal is to provide:

* Full system visibility
* Actionable insights
* Efficient monitoring and intervention

---

## 2. DASHBOARD OBJECTIVES

---

The dashboard MUST enable operators to answer:

* What is happening right now? (System Health, Alerts)
* Which students need attention? (Alerts, KPI Summary, State Distribution)
* What is the system producing? (Channel Performance, Recent Activity)
* What safe actions can I take? (Student Cases, Manual Actions, Trigger Outreach)

---

## 3. DASHBOARD STRUCTURE — IMPLEMENTED

---

### 3.1 Layout: Command Center with 10 Summary Cards

The dashboard home page is a grid of **10 summary cards**, each showing:

* Title
* Status badge: `OK | INFO | WARNING | CRITICAL | SHADOW`
* Short summary line
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

| # | Card | Badge source | Key metric | Detail view |
|---|------|-------------|------------|-------------|
| 1 | System Health | DB + scheduler + MSSQL state | Execution mode pill | hcard grid: Postgres, SQL Server, Scheduler, mode, last run, channels |
| 2 | Operational Alerts | Highest severity in list | Alert count | Full alert list with severity, message, recommended action, student_id |
| 3 | KPI Summary | INFO | Tracked count | 8-metric kgrid + 3 conversion pills |
| 4 | State Distribution | INFO | Active state count | Full state-by-state count list |
| 5 | Channel Performance | SHADOW | Total attempts | CALL/SMS/EMAIL table: attempts, shadow, responses, success % |
| 6 | Recent Activity | INFO | Event count | Structured table of last 20 events with Reload button |
| 7 | Student Cases | INFO | — | Student ID lookup + profile + outreach history + state transitions |
| 8 | Manual Actions | SHADOW | — | Student ID + notes + 4 action buttons + action log console |
| 9 | Trigger Outreach Batch | SHADOW | — | Checkpoint selector + Run Batch button + result |
| 10 | SQL Server Sync | OK or WARNING (from health) | — | Sync Now button + status text |

---

## 4. AUTO-REFRESH

---

* `loadAll()` runs on page load and every **60 seconds** via `setInterval`
* All 5 data-loading functions execute in parallel via `Promise.allSettled`
* Last refresh timestamp shown in header
* Refresh can be triggered manually via "↺ Refresh" header button

---

## 5. SYSTEM HEALTH CARD — DETAIL VIEW

---

### Backend: `GET /dashboard/health`

### Displays

* Execution Mode — SHADOW or LIVE badge
* PostgreSQL — connected / disconnected (green / red dot)
* SQL Server — configured with host, or not configured (red)
* Scheduler — active / idle status
* Last Scheduler Run — ISO timestamp or "Never ran"
* Outbound Channels — CALL / SMS / EMAIL enabled flags

### Badge Logic

| Condition | Badge |
|-----------|-------|
| PostgreSQL disconnected | CRITICAL |
| MSSQL not configured | WARNING |
| All healthy | OK |

---

## 6. OPERATIONAL ALERTS CARD — DETAIL VIEW

---

### Backend: `GET /dashboard/alerts`

### Displays

Flat list of alert rows, each showing:

* Severity badge (CRITICAL / WARNING / INFO)
* Message
* Recommended action
* Student ID (when student-specific)

### Alert Sources

| Severity | Trigger condition |
|----------|------------------|
| CRITICAL | MSSQL_HOST not configured |
| WARNING  | Student in CONTACTED state > 48 hours |
| WARNING  | Student in NO_RESPONSE with missed retry window |
| WARNING  | Scheduler has never run |
| INFO     | System in SHADOW mode |
| INFO     | Synthflow or GHL API key missing |

---

## 7. KPI SUMMARY CARD — DETAIL VIEW

---

### Backend: `GET /dashboard/summary`

### Displays

* Tracked, Ever Contacted, Responded, No Response, Intervention Required, Resolved, Closed, Shadow Executions
* Conversion pills: Contacted Rate, Response Rate, Resolution Rate

---

## 8. STATE DISTRIBUTION CARD — DETAIL VIEW

---

### Backend: `GET /dashboard/summary` (by_state field)

### Displays

State pill + count for each active state in pipeline order:
`ELIGIBLE → QUEUED → CONTACTED → NO_RESPONSE → RETRY → RESPONDED → ANALYZED → INTERVENTION_REQUIRED → RESOLVED → CLOSED`

---

## 9. CHANNEL PERFORMANCE CARD — DETAIL VIEW

---

### Backend: `GET /dashboard/channel-performance`

### Displays

Table with one row per channel (CALL, SMS, EMAIL):

* Attempts, Shadow Count, Responses, No Response, Success %
* SHADOW mode note when all sends are simulated

---

## 10. RECENT ACTIVITY CARD — DETAIL VIEW

---

### Backend: `GET /dashboard/recent-activity?limit=20`

### Displays

Structured table: Time, Student ID, Checkpoint, Channel, Action, Mode badge, State Change (From → To pill)

* Reload button re-fetches without closing the modal

---

## 11. STUDENT CASES CARD — DETAIL VIEW

---

### Interaction

1. Operator enters Student ID in lookup input
2. Clicks "Look Up"
3. Profile card appears showing: name, risk badge, path, email, phone, HWs behind, avg effort, inactive days, current state pill, checkpoint, attempts, last contact, next retry
4. Outreach History table: date, attempt #, channel, action, mode, from state, to state
5. State Transitions table: date, from, to, trigger, actor

### Not Found

* Clear error message: "Student not found: No record for ID N"

---

## 12. MANUAL ACTIONS CARD — DETAIL VIEW

---

### Inputs

* Student ID (required)
* Notes (optional free text)

### Available Actions

| Button | action_type | Transitions to | Guard |
|--------|-------------|---------------|-------|
| Close Case | CLOSE_CASE | CLOSED | Blocked if CLOSED |
| Force Retry | FORCE_RETRY | RETRY | Blocked at MAX_ATTEMPTS |
| Mark Resolved | BOOK_MEETING | RESOLVED | State machine must allow |
| Escalate | ESCALATE | INTERVENTION_REQUIRED | Only from active outreach states |

### Feedback

* Result shown inline below buttons
* Action log console shows timestamped entries (SHADOW mode label on Force Retry)
* On success: `loadSummary()`, `loadAlerts()`, `loadActivity()` auto-refresh

### Constraints

* No action executes without a Student ID
* All actions go through `POST /actions/manual`
* Every action produces OutreachHistory + StateTransitionLog records

---

## 13. TRIGGER OUTREACH BATCH CARD — DETAIL VIEW

---

### Inputs

Checkpoint selector: `SQL | SSRS | SSIS | POST_COMPLETION`

### Action

`POST /outreach/trigger { "checkpoint_type": "SQL" }`

### Result

* Displays: `Done — triggered:N retried:N skipped:N errors:N`
* On success: `loadSummary()`, `loadAlerts()`, `loadActivity()` auto-refresh

---

## 14. SQL SERVER SYNC CARD — DETAIL VIEW

---

### Action

`POST /sync/mssql`

### Result

* Connected: `Sync done — added:N updated:N`
* Not configured: `SQL Server not configured (credentials pending)`

### Badge

Set by `GET /dashboard/health` MSSQL configured field — WARNING if not configured, OK if configured.

---

## 15. MANUAL ACTIONS

---

### Allowed Actions

| action_type | Intended Use |
|-------------|--------------|
| CLOSE_CASE  | Archive a case permanently |
| FORCE_RETRY | Manually trigger a retry cycle |
| BOOK_MEETING | Mark the case as resolved (no further outreach) |
| ESCALATE    | Flag for immediate human intervention |

### Constraints

* All actions must go through `POST /actions/manual`
* Must validate state before execution (state machine enforced server-side)
* Must log all actions (OutreachHistory + StateTransitionLog)
* FORCE_RETRY is blocked when `current_attempt ≥ MAX_ATTEMPTS`

---

---

## 10. SETTINGS PANEL

---

### Configuration Options

* Feature flags (toggle)
* Scheduler time (view-only or configurable)
* Threshold values (future)

---

---

## 11. ROLE-BASED ACCESS

---

### MVP

* Single role (admin)

---

### STANDARD

* Basic roles:

  * Viewer
  * Operator

---

### PRODUCTION

* Full RBAC:

  * Viewer
  * Operator
  * Admin
  * Super Admin

---

---

## 12. PERFORMANCE REQUIREMENTS

---

* Dashboard load time ≤ 2 seconds
* API response ≤ 500 ms
* Pagination for large datasets

---

---

## 13. UX CONSTRAINTS

---

* No business logic in UI
* All decisions come from backend
* UI reflects real system state
* No hidden or derived UI-only data

---

---

## 14. ERROR HANDLING

---

### Rules

* Display user-friendly messages
* Hide technical details
* Provide retry options where safe

---

---

### Example

```plaintext id="qpvkn1"
"Unable to load data. Please try again."
```

---

---

## 15. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Basic dashboard
* Minimal views
* Limited filtering

---

---

### STANDARD

* Full dashboards
* Core analytics
* Basic filtering

---

---

### PRODUCTION

* Full analytics suite
* Advanced filtering
* Failure monitoring
* Real-time updates (if supported)

---

---

## 16. ACCEPTANCE CRITERIA

---

### Case 1 — Card Grid Loads

**Given** dashboard opened
**When** `loadAll()` completes
**Then** all 10 cards show non-loading summary text and appropriate badges

---

### Case 2 — Modal Opens on Click

**Given** operator clicks any card
**When** card is clicked
**Then** modal opens with correct title and detail content

---

### Case 3 — System Health Detail

**Given** System Health card clicked
**When** detail loads
**Then** shows PostgreSQL, SQL Server, Scheduler, mode, channels status

---

### Case 4 — Alert With Student ID

**Given** a student is stuck in CONTACTED > 48h
**When** Operational Alerts detail opens
**Then** WARNING alert shown with student_id visible

---

### Case 5 — Student Lookup Not Found

**Given** operator enters unknown student ID
**When** Look Up clicked
**Then** clear "not found" message shown — no crash

---

### Case 6 — FORCE_RETRY Blocked at Max Attempts

**Given** student has current_attempt = MAX_ATTEMPTS
**When** Force Retry clicked
**Then** error message shows MAX_ATTEMPTS_REACHED — no state change

---

### Case 7 — ESCALATE From CONTACTED

**Given** student in CONTACTED state
**When** ESCALATE clicked
**Then** student transitions to INTERVENTION_REQUIRED and audit log updated

---

### Case 8 — SHADOW Mode Alert

**Given** `settings.is_shadow = True`
**When** alerts load
**Then** INFO alert: "System is running in SHADOW mode"

---

### Case 9 — No Real Sends in SHADOW

**Given** any manual or batch action in SHADOW mode
**When** action executes
**Then** no HTTP call to GHL, Synthflow, or SMS provider — history written with `execution_mode = SHADOW`

---

### Case 10 — Auto Refresh

**Given** dashboard open
**When** 60 seconds elapse
**Then** all card summaries refresh without page reload

---

---

## 17. REFERENCES

---

Depends on:

* ux/user_experience.md
* spec/07_api_contracts.md
* runtime/system_loop.md
* state/system_state_model.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
