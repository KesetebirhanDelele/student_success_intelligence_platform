# ux/operator_workflows.md

---

## LAYER 12 — USER EXPERIENCE (OPERATOR WORKFLOWS)

---

## 1. PURPOSE

This file defines:

* Step-by-step workflows for system operators
* How users interact with the system during daily operations
* Decision-support processes (NOT decision-making logic)
* Standard operating procedures (SOPs)

The goal is to ensure:

* Consistent operations
* Fast issue resolution
* Clear interaction boundaries
* No ambiguity in user actions

---

## 2. CORE PRINCIPLES

---

### 2.1 System-Driven Decisions

* Operators DO NOT make system decisions
* Operators only:

  * Observe
  * Trigger approved actions
  * Investigate anomalies

---

### 2.2 API-First Interaction

* All actions must go through backend APIs
* No direct database access
* UI acts as control surface only

---

### 2.3 Auditability

* Every operator action MUST be logged
* Include:

  * user_id
  * action
  * timestamp
  * reason

---

---

## 3. DAILY OPERATION WORKFLOW

---

### 3.1 Daily Monitoring

---

**Steps:**

1. Open dashboard at `http://host/` (served by FastAPI static mount)
2. Wait for auto-load — all 10 summary cards populate within 1–2 seconds
3. Scan card badges across the grid:
   * `CRITICAL` on System Health → investigate immediately (database or MSSQL issue)
   * `CRITICAL` or `WARNING` on Operational Alerts → click card for alert list
   * Metric values on KPI Summary → check tracked vs contacted rate
4. Click **Operational Alerts** card → review each alert with its recommended action
5. Click **System Health** card → confirm PostgreSQL connected, scheduler ran, execution mode is SHADOW
6. Dashboard auto-refreshes every 60 seconds; click "↺ Refresh" in header for immediate update

---

### Expected Outcome

* System health verified across all 10 cards
* No CRITICAL or WARNING alerts missed
* Execution mode confirmed (SHADOW = no real sends)

---

---

## 4. STUDENT CASE REVIEW WORKFLOW

---

### 4.1 Investigate Student

---

**Steps:**

1. Click the **Student Cases** card on the dashboard home page
2. Modal opens with a Student ID input
3. Enter the student's numeric ID and click "Look Up"
4. Review the profile card:
   * Name, risk badge (HIGH / MEDIUM / LOW), path, email, phone
   * Academic metrics: HWs Behind, Avg Effort Rating, Inactive Days
   * Current state pill, checkpoint, attempt count, last contact date, next retry date
5. Review **Outreach History** table below the profile: date, attempt #, channel, action, execution mode, from/to states
6. Review **State Transitions** table: date, from, to, trigger, actor

---

### Decision Support

Operator may determine:

* If system behaved correctly (state transitions are valid and ordered)
* If the student is stuck (same state for too long — also surfaced by Alerts card)
* If manual intervention is needed (use Manual Actions card)

---

### Not Found

If the student ID has no tracking record:

* Clear error message appears inside the modal
* No crash or blank state

---

---

## 5. FAILURE INVESTIGATION WORKFLOW

---

### 5.1 Identify Failure

---

**Steps:**

1. Open Failure Dashboard
2. Filter by failure type:

   * GHL failure
   * LLM failure
   * Scheduler issue
3. Select failure case

---

---

### 5.2 Investigate Details

---

**Steps:**

1. Review logs
2. Check:

   * Last action attempted
   * Recovery action taken
3. Confirm system behavior

---

---

### 5.3 Take Action (if needed)

---

Allowed actions:

* Retry outreach
* Trigger manual outreach
* Escalate issue

---

---

## 6. MANUAL INTERVENTION WORKFLOW

---

All manual actions share the same entry point:

1. Click the **Manual Actions** card on the dashboard home page
2. Modal opens with: Student ID input, Notes input, and 4 action buttons
3. Enter Student ID (required) and optional notes
4. Click the desired action button

---

### 6.1 Force Retry

---

**Steps:**

1. Open Manual Actions modal
2. Enter Student ID
3. Click “Force Retry”

**Guard:** If `current_attempt ≥ MAX_ATTEMPTS`, the API returns `MAX_ATTEMPTS_REACHED` and the action is blocked. The error message is shown inline.

**Effect:** Student transitions to `RETRY` state. The scheduler will move them to `CONTACTED` on the next cycle.

---

### 6.2 Mark Resolved

---

**Steps:**

1. Open Manual Actions modal
2. Enter Student ID and optional notes
3. Click “Mark Resolved”

**Effect:** Student transitions to `RESOLVED`. No further automated outreach. Case is treated as successfully concluded.

---

### 6.3 Close Case

---

**Steps:**

1. Open Manual Actions modal
2. Enter Student ID and reason in Notes (recommended)
3. Click “Close Case”

**Guard:** Blocked if student is already `CLOSED`.

**Effect:** Student transitions to `CLOSED` (terminal). No further actions possible.

---

### 6.4 Batch Outreach Trigger

---

**Steps:**

1. Click the **Trigger Outreach Batch** card
2. Select checkpoint from dropdown: SQL, SSRS, SSIS, Post Completion
3. Click “Run Batch”

**Effect:** `POST /outreach/trigger` fires. Result line shows triggered / retried / skipped / error counts. KPI Summary, Alerts, and Recent Activity cards auto-refresh.

---

---

## 7. ESCALATION WORKFLOW

---

### 7.1 Identify Cases Requiring Escalation

---

**Sources:**

* **Operational Alerts card** — WARNING or CRITICAL alerts include student_id where relevant
* **Student Cases card** — risk badge (HIGH / MEDIUM) visible in profile card
* **State Distribution card** — high counts in INTERVENTION_REQUIRED signal backlog

---

### 7.2 Operator-Initiated Escalation (ESCALATE action)

---

**Steps:**

1. Note the student ID from the alert or Student Cases lookup
2. Click the **Manual Actions** card
3. Enter the student ID in the Student ID field
4. Optionally enter reason in Notes (e.g., "HIGH risk metrics, no response after 3 days")
5. Click "Escalate"

**Valid from:** CONTACTED, NO_RESPONSE, RETRY, RESPONDED

**Effect:** Student transitions to `INTERVENTION_REQUIRED`. Audit record written. Program manager must handle the case outside the automated system.

**Blocked from:** CLOSED, ELIGIBLE, QUEUED, ANALYZED, INTERVENTION_REQUIRED, RESOLVED

---

### 7.3 Automated Escalation

The scheduler also reaches `INTERVENTION_REQUIRED` automatically from `ANALYZED` when the LLM analysis determines intervention is needed. This is distinct from the operator ESCALATE action and requires no dashboard interaction.

---

---

## 8. MEETING MANAGEMENT WORKFLOW

---

### 8.1 Review Scheduled Meetings

---

**Steps:**

1. Open meeting dashboard
2. View upcoming meetings
3. Verify scheduling

---

---

### 8.2 Manual Booking (Override)

---

**Steps:**

1. Select student
2. Click “Book Meeting”
3. Choose time
4. Confirm

---

---

## 9. SYSTEM VALIDATION WORKFLOW

---

### 9.1 Validate Daily Execution

---

**Steps:**

1. Confirm scheduler ran
2. Verify:

   * Outreach triggered
   * States updated
3. Check logs

---

---

### 9.2 Validate Retry Cycle

---

**Steps:**

1. Identify retry-eligible students
2. Confirm retry executed
3. Verify state transitions

---

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal workflows
* Manual monitoring
* Limited intervention options

---

---

### STANDARD

* Structured workflows
* Basic failure handling
* Limited escalation

---

---

### PRODUCTION

* Full workflows
* Complete failure handling
* Escalation + monitoring
* Strict auditability

---

---

## 11. CONSTRAINTS

---

* No direct DB edits
* No bypassing API
* No manual override of core decision logic

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Daily Monitoring

**Given** operator opens dashboard
**When** reviewing metrics
**Then** system health is visible

---

---

### Case 2 — Failure Handling

**Given** failure occurs
**When** operator investigates
**Then** correct recovery action identified

---

---

### Case 3 — Manual Action

**Given** operator triggers action
**When** executed
**Then** system processes and logs action

---

---

## 13. REFERENCES

---

Depends on:

* ux/admin_dashboard.md
* spec/07_api_contracts.md
* runtime/system_loop.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
