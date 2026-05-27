# ux/operator_workflows.md

---

## LAYER 12 — USER EXPERIENCE (GOVERNANCE-SAFE OPERATOR WORKFLOW ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-27 to reflect the finalized governed historical intelligence platform architecture. The previous version described MVP-era operational workflow guidance: direct execution semantics ("retry executed", "trigger manual outreach"), simplistic recovery procedures ("Retry immediately once"), direct escalation semantics without governance authorization, weak SHADOW containment ("no real sends" without containment governance), no replay visibility, no immutable-lineage operator constraints, no attribution continuity requirements, no governance invariant visibility, and MVP/STANDARD/PRODUCTION scope tiers that implied incremental governance maturity rather than non-negotiable baseline guarantees. That architecture is incompatible with the governance-safe orchestration model. Operator workflows are no longer operational execution procedures or direct intervention guides. They are governance-safe orchestration observation workflows — governed authorization workflows aligned with immutable lineage guarantees, SHADOW/LIVE isolation, provider-boundary governance, and attribution continuity guarantees.
>
> **Canonical parent:** This document is governed by `ux/user_experience.md` (the canonical UX governance contract). Where this document conflicts with that contract, `ux/user_experience.md` governs.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Operator Workflow Architecture** defines:

* What operator workflows are permitted to observe, investigate, and invoke — and what is explicitly prohibited
* How operators interact with governance state without influencing orchestration logic
* How SHADOW containment and replay isolation are visible within operator workflows
* How immutable lineage artifacts are reviewed without implying mutability
* How attribution continuity is maintained across every operator workflow step
* How degradation, provider-boundary, synchronization, scheduler, and AI governance states are investigated
* What governed API invocations are permitted per operator role and under what conditions
* How operator authorization is traced, audited, and remains attributable

This document is a **child UX governance contract** for:

* `ux/admin_dashboard.md` — dashboard surfaces used in all workflows
* All operator-facing governed API endpoints defined in `spec/07_api_contracts.md`

This document is **governed by**:

* `ux/user_experience.md` — canonical UX governance contract; §4, §5, §6, §8 apply directly to all workflows in this document

---

### 1.2 What Operator Workflows Are NOT

In the governance-safe interaction model, operator workflows are explicitly **NOT**:

* **Operational execution procedures** — workflows do not guide operators through steps that directly trigger provider dispatch, state transitions, or orchestration loops; those belong to the backend governance orchestration layer
* **Direct intervention procedures** — operators do not directly manipulate student state, override config thresholds, or bypass orchestration governance; all interaction is through governed API endpoints
* **Manual override procedures** — overriding backend governance logic, eligibility decisions, retry policy assessments, or Config V2-resolved thresholds is prohibited; operator actions are governed API invocations, not overrides
* **Replay-triggered LIVE authorization pathways** — operators may investigate replay outputs for visibility only; replay records may not be used to authorize LIVE actions; replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`
* **FINALIZED artifact mutation pathways** — operators may review FINALIZED snapshots, published reports, and archived AI insights in read-only mode; no workflow step implies mutability of immutable artifacts

---

### 1.3 Workflow Governance Layer

Operator workflows sit at the observation and governed-authorization boundary. They do not own orchestration decisions.

| Workflow category | Permitted actions | Prohibited actions |
|---|---|---|
| Orchestration observation | View governance state, mode badges, alert classifications, execution history | Derive or cache governance state independently of API |
| Student case investigation | Review lineage, attribution, state transitions, outreach history via read endpoints | Modify records, correct attribution gaps retroactively, access compliance-restricted records without authorization |
| Governed operator actions | Invoke `POST /actions/manual`, `POST /outreach/trigger`, `POST /sync/mssql`, `POST /quick-actions/log` with operator identity | Bypass API layer; construct provider payloads; trigger state transitions directly |
| SHADOW/Replay visibility | Observe SHADOW containment indicators, replay execution type, causation lineage | Treat SHADOW outputs as LIVE; initiate SHADOW→LIVE from non-Governance-Administrator role; treat replay outputs as authorization |
| Immutable artifact review | View FINALIZED snapshots, fingerprint components, AI narratives in read-only mode | Render edit controls; attempt mutations; suppress immutability indicators |

---

## 2. OPERATOR ROLES AND WORKFLOW AUTHORIZATION

---

### 2.1 Governance Administrator

Authorized workflows: all Operational Administrator workflows + SHADOW→LIVE transition authorization.

* Only role permitted to initiate SHADOW→LIVE execution mode transition (AP-RT7, CV2-4)
* SHADOW→LIVE workflow defined in §10.6 — not an operational workflow; a governance-authorization event

---

### 2.2 Operational Administrator / Operator

Authorized workflows: orchestration observation, student case investigation, governed operator actions, failure investigation, synchronization investigation, observability investigation.

* May invoke: `POST /actions/manual`, `POST /outreach/trigger`, `POST /sync/mssql`, `POST /quick-actions/log`
* May view: all dashboard read surfaces, governance alert classifications, student lineage views, execution mode badges
* May NOT: initiate SHADOW→LIVE transitions; mutate FINALIZED artifacts; access compliance-restricted audit telemetry

---

### 2.3 Program Manager / Viewer

Authorized workflows: read-only orchestration observation and student lifecycle review.

* May view: all read-only dashboard surfaces, lifecycle tab data, student profile views, cohort metrics
* May NOT: invoke any write endpoints; access governance transition controls; view audit-restricted compliance telemetry

---

## 3. CORE WORKFLOW GOVERNANCE PRINCIPLES

---

### 3.1 Orchestration-Observation Principle

> Operators observe governance state outputs and invoke governed API endpoints.
> Operators do not make orchestration decisions.
> Orchestration decisions originate exclusively in the backend directive layer.

---

### 3.2 API-First Interaction

* All actions invoke backend governed API endpoints — never bypass the API layer
* No direct database access from any operator workflow
* The dashboard and lifecycle surfaces are the observation surface only; they do not compute governance state

---

### 3.3 Attribution Continuity in Workflows

* Every operator action produces an audit record: `correlation_id`, `operator_identity`, `action_type`, `execution_mode`, `timestamp`
* Operator workflows must confirm that audit records were created — not proceed silently if audit record creation fails
* No operator action is complete until its audit record is confirmed visible

---

### 3.4 Governance Invariant Enforcement in Workflows

Operator workflows must honor all governance invariants from `ux/user_experience.md` §9. Specific workflow-layer enforcement:

* No workflow step guides an operator to mutate a FINALIZED artifact (INV-1, INV-6)
* No workflow step presents Config V2 resolved thresholds as editable (INV-7)
* No workflow step renders SHADOW outputs as LIVE (§9.4)
* No workflow step treats replay outputs as authorizing LIVE actions (INV-4)
* No workflow step proceeds with a broken attribution chain without surfacing `ATTRIBUTION_INCOMPLETE` (INV-5)

---

## 4. DAILY ORCHESTRATION OBSERVATION WORKFLOW

---

### 4.1 Daily Monitoring

**Actor:** Operational Administrator

**Purpose:** Verify orchestration health across all governance domains; confirm execution mode; review governance alert classifications; confirm no CRITICAL states require immediate investigation.

**Steps:**

1. Open dashboard at `http://host/`
2. Observe **execution mode badge** in header — confirms `SHADOW` / `LIVE` / `DEGRADED` / `MAINTENANCE`; execution mode is not optional context; it governs every subsequent action
3. If `execution_mode = DEGRADED`: read `degradation_cause` and `affected_domains` before reviewing any other card — degradation is a governance state that must be understood before taking any action
4. Scan card badges: `CRITICAL` on System Health card → investigate immediately; `CRITICAL` or `WARNING` on Operational Alerts card → click for alert detail
5. Click **Operational Alerts** card → review each alert with `severity`, `error_class` (never generic), `affected_domains`, and `recovery_path` where available
6. Click **System Health** card → confirm: PostgreSQL connected, SQL Server configured, scheduler last-ran timestamp, execution mode, provider availability
7. Confirm `SHADOW MODE` badge present if `execution_mode = SHADOW` — a missing SHADOW badge while in SHADOW mode is a UX governance defect; do not proceed without it
8. Note Config V2 version indicator (read-only) — confirms current ACTIVE config version governing orchestration decisions
9. Dashboard auto-refreshes every 60 seconds; click "↺ Refresh" in header for immediate update

**Governance invariants enforced in this workflow:**

* Execution mode always visible — not optional context
* SHADOW containment badge non-removable when `execution_mode = SHADOW`
* DEGRADED MODE badge surfaces `degradation_cause` — never silently displays system as fully operational
* No governance state may be hidden from this view

---

### 4.2 Governance Alert Review

**Actor:** Operational Administrator

**Purpose:** Review active governance alert classifications; understand severity, affected domains, and recovery paths; do not confuse SHADOW/REPLAY containment indicators with failure states.

**Steps:**

1. Click **Operational Alerts** card
2. Each alert displays:
   * `severity`: CRITICAL / HIGH / MEDIUM / LOW
   * `error_class`: specific classification — never generic "error"
   * `affected_domains`: which orchestration domains are impacted
   * `recommended_action`: governance-safe operator action if applicable
   * `recovery_path`: what recovery orchestration has been or will be initiated (if available)
3. SHADOW containment failures surface as CRITICAL — do not downgrade severity
4. Replay containment violations (`live_effects_produced ≠ 0` on a replay record) surface as CRITICAL
5. Attribution incomplete records surface as governance defect alerts — correlate to student ID where visible
6. Provider SUPPRESSED state in SHADOW mode: display as expected operational state — **not** as a failure requiring investigation

**Governance distinction:** In SHADOW mode, providers display `SUPPRESSED`. This is expected governance behavior, not a failure. Do not investigate SUPPRESSED provider state as an error in SHADOW mode.

---

## 5. STUDENT CASE INVESTIGATION WORKFLOW

---

### 5.1 Governance-Safe Student Investigation

**Actor:** Operational Administrator or Program Manager

**Purpose:** Investigate a student's orchestration history with full lineage visibility; review attribution continuity; identify governance defects (attribution incomplete, state machine violations, stale data annotations).

**Steps:**

1. Click **Student Cases** card on dashboard home page
2. Modal opens with Student ID input; enter student's numeric ID and invoke lookup via governed read endpoint
3. Review profile card: current lifecycle state, checkpoint, attempt count (with `config_version_id` that governed the attempt count limit), last contact `correlation_id`, last contact date, next retry date
4. Confirm profile card shows: `execution_mode` badge on the most recent outreach history record — not just the student state
5. Review **Outreach History** table:
   * Each entry must show: `execution_mode`, `execution_type`, `correlation_id`, `config_version_id`, channel, date, from/to states
   * If any entry shows `ATTRIBUTION_INCOMPLETE`: surface as a visibility defect — do not suppress or scroll past it
   * SHADOW entries show `execution_mode = SHADOW` label — they are governance records, not operational failures
   * Replay entries show `execution_type = replay`, `causation_id` → original `correlation_id` lineage link — not LIVE records
6. Review **State Transitions** table:
   * Each entry shows: `actor`, `trigger`, `correlation_id`, `execution_mode`
   * `actor = system` indicates a backend orchestration-sourced transition — not an operator action
   * Missing `correlation_id` on a state transition is a governance defect, not a display gap
7. If student ID has no tracking record: error message appears inside modal; no crash or blank state

**Investigation scope:**

* Operators review lineage to understand what orchestration decided and why — they do not make the orchestration decision
* Operators may identify that a student is stuck (same state for too long — surfaced by Alerts card) and then invoke a governed API action
* Operators may NOT modify state transition records, correct attribution gaps in historical records, or access compliance-restricted case data without authorization

---

### 5.2 Lineage Review with Attribution Continuity

**Actor:** Operational Administrator

**Purpose:** Verify attribution continuity for a student's orchestration record; confirm causation chain for replay or recovery events; identify `ATTRIBUTION_INCOMPLETE` conditions.

**Steps:**

1. Open student case in Student Cases modal
2. In Outreach History, expand a record's detail view to see full lineage fields:
   * `correlation_id` — every record
   * `execution_mode` — every record
   * `execution_type` — `original | replay | regeneration | recovery`
   * `causation_id` — derived events (replay, recovery); renders as lineage link to parent event
   * `config_version_id` — every orchestration intent record
   * `origin_source` — every sync-derived record
   * `origin_authority` — every sync-derived record
3. If `execution_type = replay`: confirm `causation_id` → original `correlation_id` is visible; confirm `governance_scope = REPLAY_ONLY` is shown; confirm `live_effects_produced = 0`
4. If any attribution field is null: `ATTRIBUTION_INCOMPLETE` indicator surfaced — this is a governance defect to note, not to dismiss
5. If `origin_authority = sql_server_authoritative` on a sync-derived record: SQL Server won on conflict — this is expected governance behavior, not a data error

---

## 6. LIFECYCLE TAB INVESTIGATION WORKFLOWS

---

### 6.1 Navigating Lifecycle Tabs

**Actor:** Operational Administrator or Program Manager

**Steps:**

1. Open dashboard at `http://host/`
2. Scroll below the 10 summary cards to the tab bar: Newcomers | Engagement | HW Risk | CAP Hopefuls | Launch Hopefuls | Placement Hopefuls
3. Click the desired tab; tab data loads automatically from the lifecycle read endpoint
4. Use search box to filter by name, email, or column value; use pagination controls; use column header sort
5. Click **Export CSV** to download the current filtered view (read-only governance record)

---

### 6.2 Student Row Selection and Governance Drawer

**Steps:**

1. Click any row in a lifecycle tab table; row highlights — this is the **selected student**
2. Action bar activates; right-side drawer opens showing: Profile, Timeline, Notes, Outreach, AI Insights tabs
3. **Profile tab**: contact info, program path, academic metrics, risk badge
4. **Timeline tab**: unified governance activity log (outreach history, GHL messages, notes, AI insights, state transitions), newest first; each entry carries `execution_mode` and `correlation_id`
5. **Notes tab**: internal notes; operator may add a new note
6. **AI Insights tab**: `ai_governance_tier` visible (FINALIZED_COPY / AI_GENERATED / STALE / UNAVAILABLE); advisory output labeled as advisory — not as authorization
7. Drawer closes via the ✕ button or Escape

---

### 6.3 Triggering a Governed Operator Action from Lifecycle Tab

**Actor:** Operational Administrator

**Steps:**

1. Select a student row (action buttons activate)
2. **Confirm execution mode badge before acting** — SHADOW mode label must be visible if `execution_mode = SHADOW`; LIVE mode label must be visible if `execution_mode = LIVE`; operator must be aware of execution mode before any action invocation
3. Click the desired action button; action invokes a governed API endpoint — it does not bypass the backend orchestration boundary
4. Review inline result from API:
   * Governance authorization confirmation: `correlation_id` displayed; action logged
   * Governance rejection: rejection reason surfaced in full — `MAX_ATTEMPTS_REACHED`, `STATE_TRANSITION_NOT_ALLOWED`, `COMPLIANCE_HOLD_ACTIVE`, etc.
5. If rejection: read the governance reason; do not attempt to work around it; the rejection is a backend governance enforcement, not a UI bug
6. Confirm action appears in student's Timeline (Timeline tab in drawer → newest entry) — confirms audit record was written

---

### 6.4 Syncing Student Data Before Using Tabs

**Steps:**

1. If tabs are empty or showing stale data annotations (`STALE_SQL_SERVER_DATA` badge visible on records):
2. On the dashboard Overview tab, click **Sync Students** (or **Sync All** on the SQL Server Sync card)
3. Invoke `POST /sync/mssql` — pulls latest rows from SQL Server `AI_ChatBot_TriggerData`; this is a read-only sync from SQL Server (not an outbound action)
4. Result shows: scanned / added / updated / failed counts; `origin_authority = sql_server_authoritative` confirmed
5. Return to the lifecycle tab and reload — data now reflects the latest sync; `STALE_SQL_SERVER_DATA` annotations should clear for synced records

**Provider boundary note:** SQL Server is `origin_authority = sql_server_authoritative`. When sync-derived data conflicts with GHL-supplemented data, SQL Server wins. This is expected governance behavior — not a data error.

---

## 7. GOVERNED MANUAL ACTION WORKFLOWS

---

All manual actions share the same governed interaction model:

1. Click the **Manual Actions** card on the dashboard home page
2. Modal opens with: Student ID input, Notes input, and action buttons
3. Enter Student ID (required) — notes field is optional context
4. Confirm execution mode badge before acting
5. Click the desired action button — each invokes `POST /actions/manual` with the corresponding action type
6. Review inline API result for governance authorization confirmation or rejection reason
7. Confirm audit record visible in student's Timeline

---

### 7.1 Force Retry

**Actor:** Operational Administrator

**Governed by:** `outreach_retry_policy.md` (RetryPolicyAssessment); Config V2 Group A `outreach_max_retry_attempts`

**Steps:**

1. Open Manual Actions modal; enter Student ID
2. Confirm execution mode badge visible
3. Click "Force Retry" — invokes `POST /actions/manual` with `action_type = FORCE_RETRY`

**Backend governance guard:** If `current_attempt ≥ outreach_max_retry_attempts` (Config V2 Group A), the API returns `MAX_ATTEMPTS_REACHED` and the action is blocked. The rejection reason is surfaced inline — do not suppress it. The retry ceiling is Config V2-governed; no operator action can override it.

**Governance note:** This action produces an orchestration intent (`RETRY_OUTREACH`) in the governed backend orchestration layer. It does not directly execute outreach. In SHADOW mode, the intent carries `governance_scope = SHADOW_ONLY`; no outbound dispatch occurs.

---

### 7.2 Mark Resolved

**Actor:** Operational Administrator

**Steps:**

1. Open Manual Actions modal; enter Student ID and optional notes
2. Click "Mark Resolved" — invokes `POST /actions/manual` with `action_type = MARK_RESOLVED`

**Effect:** Student transitions to `RESOLVED` via the governed state management service. No further automated outreach. Case treated as successfully concluded.

**Governance note:** `RESOLVED` is not a terminal state in the same sense as `CLOSED`. Do not treat it as such unless confirmed by the API response.

---

### 7.3 Close Case

**Actor:** Operational Administrator

**Steps:**

1. Open Manual Actions modal; enter Student ID; enter reason in Notes (recommended)
2. Click "Close Case" — invokes `POST /actions/manual` with `action_type = CLOSE_CASE`

**Backend governance guard:** Blocked if student is already `CLOSED` — `CLOSED` is terminal; the API will reject the request with `STATE_TRANSITION_NOT_ALLOWED`.

**Governance note:** `CLOSED` is a terminal lifecycle state governed by `spec/03_state_transition_rules.md`. No further state transitions are possible from `CLOSED`. The terminal state governance is irreversible.

---

### 7.4 Escalate (Governed)

**Actor:** Operational Administrator

**Valid from states:** `CONTACTED`, `NO_RESPONSE`, `RETRY`, `RESPONDED`

**Steps:**

1. Note the student ID from an alert or Student Cases lookup
2. Open Manual Actions modal; enter the student ID and reason in Notes
3. Click "Escalate" — invokes `POST /actions/manual` with `action_type = ESCALATE`

**Effect via governed API:** Student transitions to `INTERVENTION_REQUIRED`. Audit record written with `operator_identity` and `correlation_id`. Program manager handles the case outside the automated outreach system.

**Blocked from:** `CLOSED`, `ELIGIBLE`, `QUEUED`, `ANALYZED`, `INTERVENTION_REQUIRED`, `RESOLVED`

**Governance note:** Escalation candidacy is also assessed automatically by the Escalation Polling Loop (§4.3 of `runtime/system_loop.md`) after the Orchestration Evaluation Loop completes. The automated escalation from `ANALYZED` state is distinct from this operator-initiated action. Both produce audit records with their respective `actor_identity`.

---

### 7.5 Batch Outreach Trigger

**Actor:** Operational Administrator

**Steps:**

1. Click the **Trigger Outreach Batch** card
2. Select checkpoint from dropdown: SQL, SSRS, SSIS, Post Completion
3. Confirm execution mode badge — in SHADOW mode, no outbound dispatch will occur
4. Click "Run Batch" — invokes `POST /outreach/trigger`
5. Result line shows: triggered / retried / skipped / error counts; KPI Summary, Alerts, and Recent Activity cards auto-refresh

**Governance note:** Batch outreach trigger coordinates an Orchestration Evaluation Loop cycle. In SHADOW mode, the cycle produces `governance_scope = SHADOW_ONLY` intents — no outbound dispatch is delegated. In LIVE mode, the cycle proceeds through the full governed orchestration sequence.

---

## 8. SHADOW MODE OPERATOR WORKFLOWS

---

### 8.1 Understanding SHADOW Mode in Operator Workflows

SHADOW mode is a governance execution mode, not a test or preview mode. When `execution_mode = SHADOW`:

* All orchestration evaluation proceeds normally — eligibility assessed, retry assessed, decisions made
* All outbound dispatch is suppressed — no GHL API calls, no SMS, no email, no voice
* All provider interactions display `outbound_suppressed = true` — this is expected governance behavior, not a failure
* All operator actions (Force Retry, Mark Resolved, Close Case, Escalate, Batch Trigger) execute in SHADOW mode semantics — they produce audit records and orchestration intents; no LIVE outbound occurs
* AI advisory outputs are tagged `outcome = shadow_only` — not a failure state

**Operator workflow constraint:** In SHADOW mode, do not interpret suppressed providers as unavailable. A provider labeled `SUPPRESSED` is functioning correctly within governance constraints.

---

### 8.2 Verifying SHADOW Containment

**Actor:** Operational Administrator

**Purpose:** Confirm SHADOW mode is active and containment is operating correctly before any operator action.

**Steps:**

1. Open dashboard; confirm `SHADOW MODE` persistent badge in header
2. Click Channel Performance card — confirm all channel counts show `SUPPRESSED` state; shadow count = attempt count
3. Check Operational Alerts — confirm no SHADOW containment failures are surfaced as CRITICAL alerts
4. If any outreach history record shows `execution_mode = LIVE` while system is in SHADOW: this is a CRITICAL containment violation — surface immediately; do not proceed with other actions

---

### 8.3 SHADOW→LIVE Transition Authorization

**Actor:** Governance Administrator only

This workflow is a governance-authorization event, not an operational workflow step. Non-Governance-Administrators must not attempt this workflow; the transition control is not rendered for non-authorized roles (see `ux/user_experience.md` §4.2 and §10.5).

**Steps:**

1. Navigate to execution mode transition control (visible to Governance Administrator only)
2. Confirm current mode: `SHADOW` — form will not submit if already in LIVE
3. Enter or confirm activation record ID (required — form submission is blocked without this; the activation record ID confirms that an authorized governance decision has been recorded)
4. Read and confirm explicit acknowledgement checkbox: "I confirm an activation record is present authorizing this SHADOW→LIVE transition"
5. Submit via governed API endpoint — backend validates `actor_type`, `activation_record_present`, and ensures no automated service triggered this transition (AP-RT7)
6. On success: execution mode badge updates to `LIVE`; audit record of transition visible with `correlation_id`
7. On rejection: rejection reason surfaced — do not retry automatically; address the rejection reason before re-attempting

**Non-negotiable constraints:**

* Automated SHADOW→LIVE transitions are prohibited (AP-RT7)
* `activation_record_present` gate is a hard requirement — the API blocks submission without it
* Only Governance Administrator role may render this transition control

---

## 9. REPLAY OPERATOR WORKFLOWS

---

### 9.1 Understanding Replay in Operator Context

Replay execution is a backend orchestration mode (`execution_type = replay`). Operator-visible replay outputs are governance records with these invariants:

* `execution_type = replay` — always visible on replay records
* `governance_scope = REPLAY_ONLY` — replay outputs are not authorized for LIVE consumption
* `causation_id` → original `correlation_id` — lineage link to the original execution event
* `historical_config_version_id` — replay used historical config, not the current ACTIVE config version
* `live_effects_produced = 0` — the expected invariant; non-zero triggers a CRITICAL governance alert

**Operator workflow constraint:** Replay records may be reviewed for lineage investigation. They may not be treated as authorizing LIVE actions. Replay is not a "test run before going live."

---

### 9.2 Replay Investigation Workflow

**Actor:** Operational Administrator

**Purpose:** Investigate a replay execution to verify historical decision reproducibility; confirm replay containment; review fingerprint comparison outcomes; identify partial replay conditions.

**Steps:**

1. Open student case in Student Cases modal
2. In Outreach History, locate records with `execution_type = replay` badge
3. Review replay record metadata:
   * `execution_type = replay` — prominent label
   * `governance_scope = REPLAY_ONLY` — visible governance scope
   * `causation_id` → original `correlation_id` lineage link — click to navigate to original record (where supported)
   * `historical_config_version_id` — the config version used during replay; not the current ACTIVE config
   * `live_effects_produced = 0` — confirm this invariant; if non-zero, a CRITICAL governance alert must be visible
4. Review `fingerprint_comparison_outcome`:
   * `IDENTICAL` — re-evaluation produced same outcome as historical
   * `POTENTIALLY_DIVERGENT` — re-evaluation diverged from historical; `POTENTIALLY_DIVERGENT` badge visible; this is not an error but must not be hidden
   * `COMPARISON_UNAVAILABLE` — comparison could not be performed
5. If `replay_partial = true`: a `PARTIAL REPLAY` warning is displayed — the replay scope was incomplete; historical data was unavailable for some inputs
6. Replay records must never appear in the same visual style as LIVE records — they must be visually distinguishable

---

### 9.3 Replay Containment Verification

**Actor:** Operational Administrator

**Purpose:** Confirm that a completed replay cycle produced no LIVE effects.

**Steps:**

1. After replay is complete, check Operational Alerts for any `live_effects_produced ≠ 0` alerts
2. If no alert: replay contained — `live_effects_produced = 0` is confirmed
3. If alert present: CRITICAL governance defect — `live_effects_produced ≠ 0` on a replay record is a specification violation (INV-4, AP-RT2); do not dismiss the alert; escalate to Governance Administrator

---

## 10. FAILURE INVESTIGATION WORKFLOWS

---

### 10.1 Governance-Safe Failure Investigation

**Actor:** Operational Administrator

**Purpose:** Identify the governance root cause of an orchestration failure; confirm degradation classification; identify affected domains; review recovery path.

**Steps:**

1. Open Operational Alerts card — filter by `severity = CRITICAL` or `CRITICAL | HIGH`
2. Select failure alert; review alert detail:
   * `failure_domain`: one of `orchestration | provider | ai | scheduler | replay | regeneration | synchronization | observability | attribution | compliance`
   * `error_class`: specific classification — `TimeoutError | RateLimitError | AuthError | ValidationError | UpstreamUnavailable | ContractViolation | AttributionFailure` — never generic
   * `affected_domains`: which orchestration domains are impacted
   * `correlation_id`: trace the failure to its originating orchestration cycle
3. Do not use the `error_class` value "Error" or "Unknown" as acceptable classifications — if a failure surfaces without a specific `error_class`, this is itself a governance observability defect
4. Review recovery path in alert: confirm whether recovery orchestration has been initiated or is pending

**Governance note:** Recovery orchestration is coordinated by the backend resilience layer. Operators observe the recovery path — they do not trigger recovery directly. A recovery cycle carries `execution_type = recovery` and is visible in the orchestration audit trail.

---

### 10.2 Provider Failure Investigation

**Actor:** Operational Administrator

**Purpose:** Distinguish provider failures from governance-expected suppression; understand circuit breaker state; determine if escalation candidacy has been generated.

**Steps:**

1. Check Channel Performance card — review provider state per channel
2. In SHADOW mode: providers show `SUPPRESSED` — this is expected; do not investigate as failure
3. In DEGRADED mode (provider outage): providers show `UNAVAILABLE` with `error_class` and `severity` — this requires investigation
4. Review provider alert detail:
   * `provider_name`: which provider is affected
   * `circuit_breaker_state`: OPEN / CLOSED / HALF_OPEN
   * `http_status_code` from provider (if available)
   * `retry_count`: attempts before circuit opened
   * `governance_scope = UNAVAILABLE`: confirms outbound dispatch is blocked
5. Confirm that a provider failure escalation candidacy signal has been generated — if not, this is a resilience observability gap
6. Do not attempt direct provider API remediation — provider recovery is governed by the backend circuit breaker and recovery orchestration sequence

**Key distinction:** `SUPPRESSED` (SHADOW mode, expected) vs `UNAVAILABLE` (DEGRADED mode, failure) are two different governance states. They require different operator responses.

---

### 10.3 AI Governance Failure Investigation

**Actor:** Operational Administrator

**Purpose:** Confirm AI advisory governance tier; verify AI failure does not imply orchestration block; understand degraded-mode AI behavior.

**Steps:**

1. Check AI Insights card on dashboard (or AI Insights tab in student drawer)
2. Review `ai_governance_tier` label:
   * `FINALIZED_COPY` — sourced from warehouse; immutable; not re-evaluated; expected
   * `AI_GENERATED` — fresh advisory within TTL; normal
   * `STALE` — beyond `ai_insight_ttl_hours` threshold; advisory scope limited; orchestration continues with rule-based evaluation
   * `UNAVAILABLE` — AI provider unavailable; rule-based evaluation only; orchestration not blocked
3. In DEGRADED mode with AI provider unavailable:
   * `stale_ai_present = true` indicator — stale advisory served if within TTL
   * Confirm `ai_governance_tier` is visible — not blank
   * AI absence does not block orchestration; rule-based evaluation annotated
4. In SHADOW mode: AI advisory shows `outcome = shadow_only` — not a failure
5. AI advisory outputs are always labeled as advisory — **never as authorization**; if an AI output is labeled as authorizing an action, that is a UX governance defect

---

### 10.4 Scheduler Failure Investigation

**Actor:** Operational Administrator

**Purpose:** Confirm scheduler last-ran timestamp; identify missed cycle conditions; verify recovery cycle attribution.

**Steps:**

1. Check System Health card — review scheduler last-ran timestamp
2. If scheduler timestamp shows `Never ran` or is stale: a `WARNING` or `CRITICAL` alert should be visible on the Operational Alerts card
3. Review alert detail:
   * `expected_trigger_time`: when the cycle should have run (governed by Config V2 Group A)
   * `actual_trigger_time`: when it actually ran (or null if missed)
   * `lag_duration_ms`: how late the scheduler ran
   * `recovery_cycle_id`: if a recovery cycle was initiated
4. Confirm recovery cycle attribution in Operational Alerts:
   * `execution_type = recovery`
   * `recovery_of_cycle_date` — which missed cycle the recovery addresses
   * `recovery_initiated_by`: `system` (automated) or operator identity
5. Recovery cycles carry the same idempotency key as the missed cycle — duplicate recovery processing is blocked; already-processed students are skipped

---

### 10.5 Synchronization Investigation

**Actor:** Operational Administrator

**Purpose:** Confirm SQL Server sync status; identify stale data conditions; initiate sync if needed.

**Steps:**

1. Check SQL Server Sync card on dashboard — review sync outcome and last sync timestamp
2. Sync state fields:
   * `origin_source = mirrored_sql_server`
   * `origin_authority = sql_server_authoritative`
   * Dedup gate result (if duplicate detected): `duplicate_detected`, `dedup_gate_applied`
   * Sync outcome counts: scanned / added / updated / failed
3. If sync lag indicator shows `STALE_SQL_SERVER_DATA`: student records affected are annotated; orchestration continues with annotation but decisions may reflect stale data
4. Click **Sync Students** (or **Sync All**) to trigger `POST /sync/mssql`:
   * This is a read-only sync from SQL Server — not an outbound action
   * Sync proceeds in all execution modes, including SHADOW
5. If sync fails with `SQL_SERVER_UNAVAILABLE`: this is a governance degradation event; an escalation candidacy signal should be visible in Operational Alerts; do not attempt manual SQL Server remediation from the dashboard

---

## 11. IMMUTABLE-LINEAGE OPERATOR CONSTRAINTS

---

### 11.1 FINALIZED Artifact Review (Read-Only)

**Actor:** Any authorized role

**Purpose:** Review a FINALIZED snapshot for historical explainability without implying mutability.

**Steps:**

1. Navigate to a FINALIZED snapshot record (via Student Cases → Outreach History → FINALIZED record)
2. Confirm `lifecycle_state = FINALIZED` badge is visible — immutability state is always shown
3. Review snapshot detail — all fields are read-only; no edit, no delete, no update affordances are present
4. Review fingerprint components:
   * `schema_version`
   * `config_registry_version`
   * `ai_prompt_version`
   * `ai_model_version`
   * `report_template_version`
5. If any component shows `UNKNOWN_V0`: audit-gap indicator is visible — this is a known limitation, not an error; it means the component was not versioned at the time of finalization
6. If a fingerprint mismatch exists between the stored snapshot and the current system fingerprint: a `MEDIUM` severity governance alert is visible

**Operator constraint:** If the UI renders any control implying a FINALIZED artifact can be modified, this is a UX governance defect (INV-1, INV-6). Do not use such a control.

---

### 11.2 Append-Only Historical Record Review

**Actor:** Any authorized role

**Purpose:** Confirm append-only record integrity for state transitions, outreach history, and timeline events.

**Constraints operators must observe:**

* State transition logs are displayed in chronological order — not editable, not reorderable, not filterable in ways that hide entries
* Outreach history records are append-only audit artifacts — no delete or edit affordances should be present
* AI insights, once archived, display `lifecycle_state = ARCHIVED` — no modification path exists
* Timeline entries appear in newest-first order; the order reflects the append sequence; it is not sortable in ways that would misrepresent the historical sequence

---

### 11.3 Attribution Continuity Review

**Actor:** Operational Administrator

**Purpose:** Verify that all orchestration records in a student case carry complete attribution.

**Steps:**

1. Open student case in Student Cases modal
2. In Outreach History, for each displayed record, verify:
   * `correlation_id` is present and non-null
   * `execution_mode` is present: `SHADOW | LIVE | REPLAY | DEGRADED`
   * `execution_type` is present: `original | replay | regeneration | recovery`
3. If any field is null: `ATTRIBUTION_INCOMPLETE` indicator is surfaced — this is a governance defect; note the `correlation_id` of the affected cycle and the missing field name; do not dismiss
4. `causation_id` is expected on derived events (replay, recovery); its absence on a derived event is an attribution defect
5. `config_version_id` is expected on every orchestration intent record; its absence is an attribution gap

---

## 12. OPERATOR AUTHORIZATION GOVERNANCE

---

### 12.1 Governed API Invocation Behavior

All operator actions in this document invoke governed backend API endpoints. The UX enforces this boundary:

* Every action control invokes a specific backend endpoint — no control bypasses the API layer
* Every invocation carries the operator's identity — attribution is non-negotiable
* Every invocation surfaces the backend's governance validation response — approval or rejection, with reason
* Rejected invocations surface the backend governance reason — suppression of rejection reasons is prohibited

---

### 12.2 Authorization Prohibitions

Operators cannot:

* Bypass the orchestration governance layer from any workflow step — no direct provider calls, no direct database writes
* Mutate FINALIZED artifacts — no workflow step implies FINALIZED records can be modified
* Override Config V2 governance — threshold values displayed in the UI are read-only resolved values; no workflow step offers an override control
* Trigger a SHADOW→LIVE transition without a confirmed activation record — the UI enforces this gate at the presentation layer before the API call is made
* Authorize AI advisory outputs as governance decisions — AI outputs are advisory; no operator workflow treats AI advisory as authorization

---

### 12.3 Operator Audit Attribution Requirements

Every operator action must produce a visible audit trail:

* Audit confirmation receipt is displayed inline after every action: `correlation_id`, `action_type`, `execution_mode`, `timestamp`
* If audit record creation fails, the UX surfaces the failure — it does not proceed silently
* All audit records are append-only — they are not editable by operators or by the system after creation
* Audit records are visible in the student's Timeline tab immediately after the action

---

### 12.4 Escalation Authorization Visibility

Escalation candidacy (operator-initiated or system-generated) must be visible:

* Operator-initiated escalation: audit record with `operator_identity`, `action_type = ESCALATE`, `correlation_id`
* System-generated escalation candidacy: audit record with `actor_identity = system`, `escalation_type`, `escalation_severity`
* Both sources produce visible governance records — operators may not assume escalation is "invisible" if generated by the system
* Escalation outputs from replay are always `REPLAY_ESCALATION_CANDIDATE` scope — they do not generate live operator routing

---

## 13. OPERATIONAL OBSERVABILITY WORKFLOWS

---

### 13.1 Governance State Observation Workflow

**Actor:** Operational Administrator

**Purpose:** Confirm all governance states are observable and no governance state is hidden.

**States that must always be visible:**

| Governance state | Dashboard location | Operator action if missing |
|---|---|---|
| `execution_mode` | Header badge | Refresh dashboard; if still missing, surface as CRITICAL UX defect |
| `SHADOW containment` | SHADOW MODE badge in header | If missing while mode = SHADOW, surface as UX governance defect |
| `DEGRADED` | DEGRADED MODE badge | If system is degraded but badge is absent, surface as CRITICAL defect |
| `MAINTENANCE` | MAINTENANCE MODE badge | Confirms orchestration loops paused |
| `compliance_hold_active` | Student record indicator | Visible on any student record subject to a hold |
| `FINALIZED` | Immutability badge on artifact | Must be visible on every FINALIZED artifact in the student record |
| Config V2 ACTIVE version | Config version indicator | Read-only; current ACTIVE version ID |

---

### 13.2 Degradation Investigation Workflow

**Actor:** Operational Administrator

**Purpose:** Understand degradation cause and affected domains; identify recovery path; confirm no silently degraded components.

**Steps:**

1. `DEGRADED MODE` badge visible in header — click to expand degradation detail
2. Review degradation detail:
   * `degradation_type`: specific type — never generic
   * `error_class`: specific error class — never generic
   * `affected_domains`: which orchestration domains are degraded
   * `recovery_path`: what recovery coordination is pending
3. Confirm no degraded component appears as fully operational — a degraded domain silently displaying as normal is a UX governance defect
4. `silent_swallow = true` on any degradation record: CRITICAL alert — this is a governance defect; surface immediately
5. Review Operational Alerts for recovery coordination status

---

### 13.3 Provider Boundary Visibility

All provider interactions display governance scope:

* GHL: `origin_authority = platform_supplementary` — visible in provider detail; GHL is supplementary authority, not final
* SQL Server sync: `origin_authority = sql_server_authoritative` — visible in sync detail; SQL Server wins on conflict
* Provider suppressed (SHADOW): `outbound_suppressed = true` — expected state; not labeled as failure
* Provider unavailable (DEGRADED): `UNAVAILABLE` with severity — not silently blank

---

### 13.4 Observability Heartbeat Review

**Actor:** Operational Administrator

**Purpose:** Confirm the observability heartbeat loop is active and all operational health metrics are current.

**Steps:**

1. Check System Health card — all metric timestamps should be recent
2. Heartbeat fields to verify:
   * Provider circuit breaker state (OPEN / CLOSED per provider)
   * AI insight freshness distribution
   * Sync lag hours
   * Escalation backlog count
   * Active compliance holds count
   * Loop last-completion timestamps
3. If heartbeat is stale (no recent completion): `SCHEDULER_LAG_DETECTED` or `OBSERVABILITY_DEGRADED` alert should be visible; investigate per §10.4

---

## 14. WORKFLOW GOVERNANCE INVARIANTS

---

### 14.1 Cross-Domain Governance Invariants Applied to Operator Workflows

Inherited from `ux/user_experience.md` §9.1. Operator workflow enforcement:

| Invariant | Operator workflow enforcement |
|---|---|
| **INV-1** FINALIZED snapshot is immutable | No workflow step guides an operator to edit or delete a FINALIZED record; FINALIZED badge always visible in review steps |
| **INV-2** Exactly one config version ACTIVE | Config version ID displayed as read-only in all operator action confirmations; no workflow step offers a config version override |
| **INV-3** (FAD-3) Activation is prospective-only | SHADOW→LIVE transition workflow (§8.3) requires activation_record_present confirmation; no backdated activation implied in any workflow step |
| **INV-4** (AP-RT2) No LIVE effects from replay | Replay investigation workflow (§9.2) confirms `live_effects_produced = 0`; non-zero value surfaces CRITICAL alert; replay records never treated as LIVE authorization |
| **INV-5** Attribution continuity | All investigation workflows surface `ATTRIBUTION_INCOMPLETE` when correlation_id, execution_mode, or execution_type is null; never dismiss |
| **INV-6** (FAD-1) FINALIZED_COPY immutability | AI Insights tab in student drawer: FINALIZED state = read-only; AI narrative review workflows confirm no edit path exists |
| **INV-7** No hardcoded thresholds | Manual action workflows surface Config V2-resolved values as read-only; `MAX_ATTEMPTS_REACHED` rejection surfaces the config-governed limit, not a hardcoded value |

---

### 14.2 FAD Visibility in Operator Workflows

| FAD | Operator workflow behavior |
|---|---|
| **FAD-1** FINALIZED_COPY immutability | AI narratives in FINALIZED state reviewed as read-only in AI Insights tab; no edit affordance |
| **FAD-2** Regeneration reads warehouse exclusively | Regenerated reports labeled `sourced_from_warehouse = true` in report detail view |
| **FAD-3** Prospective-only activation | SHADOW→LIVE transition form requires future or current-dated activation confirmation; no backdated submission |
| **FAD-4** Append-only audit log | State transition and outreach history records show chronological-only display; no filter that hides entries; no delete affordances |
| **FAD-5** Config V2 governance | All retry thresholds, timing values, channel progression rules displayed as read-only resolved values in alert and action contexts |
| **FAD-6** Snapshot fingerprint reproducibility | Fingerprint components accessible in §11.1 investigation workflow; `UNKNOWN_V0` shows audit-gap indicator; fingerprint mismatch → MEDIUM governance alert |

---

### 14.3 Append-Only Operational Visibility

All operator workflow steps must honor append-only semantics:

* Historical records may not appear editable in any workflow step regardless of user role
* Audit log entries are displayed in append order — no filter that hides entries from the visible window
* Delete controls are never presented on records in: `state_transition_log`, `outreach_history`, `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `student_timeline_events`

---

### 14.4 SHADOW/LIVE Isolation in Operator Workflows

All operator workflow steps must maintain SHADOW/LIVE isolation:

* SHADOW records display `execution_mode = SHADOW` badge — never appear as neutral/unlabeled
* LIVE records display `execution_mode = LIVE` badge
* Mixed-mode views (outreach history spanning a mode transition) display execution mode per record — never aggregate into an unlabeled list
* Execution mode is permanent metadata on a record — it does not update when the system transitions modes
* No workflow step allows an operator to reinterpret a SHADOW record as a LIVE record

---

## 15. ACCEPTANCE CRITERIA (GOVERNANCE-SAFE WORKFLOW CERTIFICATION)

---

### Case 1 — SHADOW Containment in Operator Workflows

**Given** `execution_mode = SHADOW`
**When** operator opens dashboard and reviews lifecycle tab
**Then** SHADOW MODE persistent badge visible in header; all action buttons confirm SHADOW mode before invocation; action confirmation inline result shows `execution_mode = SHADOW`; no SHADOW record rendered as LIVE; provider state shows `SUPPRESSED` — not `failed`

---

### Case 2 — Replay Investigation Containment

**Given** replay execution records exist in student outreach history
**When** operator reviews the student's outreach history including replay records
**Then** replay records display `execution_type = replay`, `governance_scope = REPLAY_ONLY`, `causation_id` linking to original; `live_effects_produced = 0` confirmed; replay records visually distinguishable from LIVE records; no replay record interpreted as authorizing a LIVE action

---

### Case 3 — Immutable Lineage Review

**Given** a FINALIZED snapshot exists in a student's record
**When** operator reviews the snapshot detail in the investigation workflow
**Then** `lifecycle_state = FINALIZED` badge visible; no edit/delete controls present; all five fingerprint components accessible; `allows_update = false` confirmed; any attempt to render a modification control is a test failure

---

### Case 4 — Attribution Continuity in Investigation

**Given** operator investigates a student case and reviews outreach history records
**When** any record detail is visible
**Then** `correlation_id`, `execution_mode`, `execution_type` are all non-null on every record; any null field surfaces `ATTRIBUTION_INCOMPLETE` indicator; null fields are not silently suppressed or displayed as blank

---

### Case 5 — Degradation Observation Workflow

**Given** `execution_mode = DEGRADED` with affected_domains
**When** operator opens dashboard
**Then** DEGRADED MODE badge visible; `degradation_cause` and `affected_domains` surfaced in alert; `recovery_path` shown where available; no degraded component appears as fully operational; `silent_swallow = true` on any degradation record → CRITICAL alert surfaced

---

### Case 6 — Provider Boundary Distinction

**Given** SHADOW mode active with provider suppression
**When** operator reviews Channel Performance card
**Then** all providers display `SUPPRESSED` state (not `UNAVAILABLE`, not `failed`); shadow count = attempt count; SHADOW mode note visible; no provider labeled as "failed" when suppression is the expected governance state

---

### Case 7 — Replay Containment Violation Surfacing

**Given** `live_effects_produced ≠ 0` exists on a replay record
**When** operator reviews operational alerts
**Then** CRITICAL governance alert visible; replay containment violation labeled explicitly; record labeled as governance defect (INV-4 violation); not displayed as a normal replay record; operator cannot dismiss without acknowledging the governance defect

---

### Case 8 — SHADOW→LIVE Transition Authorization Gate

**Given** Governance Administrator initiates SHADOW→LIVE transition workflow (§8.3)
**When** transition form is rendered
**Then** activation record ID field is required; confirmation checkbox required; submission blocked until both present; API rejection surfaces governance rejection reason verbatim; no automated submission pathway exists

---

### Case 9 — Non-Governance-Administrator Cannot Access Transition Workflow

**Given** Operational Administrator role (not Governance Administrator)
**When** dashboard renders
**Then** SHADOW→LIVE transition control is not rendered or is visibly disabled with access restriction indicator; no navigation path exists to the transition workflow from this role

---

### Case 10 — Governed Operator Action Audit Attribution

**Given** Operational Administrator triggers a Force Retry action from the Manual Actions card
**When** API responds with confirmation
**Then** `correlation_id` displayed inline in action confirmation; `execution_mode` shown; action visible in student Timeline tab within same session; `actor_identity = operator_id` in the audit record; action not considered complete without visible audit confirmation

---

## 16. REFERENCES

---

Governed by (parent contracts):

* `ux/user_experience.md` — canonical UX governance contract; §4, §5, §6, §8, §9 govern all workflows in this document
* `spec/03_state_transition_rules.md` — INV-1 through INV-7, terminal state governance, lifecycle domain boundaries
* `spec/05_external_integrations.md` — lineage-preserving integration fields, SQL Server authority boundary, provider governance
* `spec/06_observability_operations.md` — two-category telemetry model, governance-aware observability, lineage-aware telemetry
* `spec/07_api_contracts.md` — all API endpoint contracts governing operator invocations
* `runtime/system_loop.md` — six runtime modes, SHADOW→LIVE governance (§3.2), AP-RT7, ten canonical orchestration domains
* `runtime/scheduler_design.md` — scheduler visibility, recovery cycle attribution
* `runtime/daily_outreach_flow.md` — daily cycle governance, degradation sequencing
* `runtime/retry_cycle_flow.md` — retry policy governance, Config V2 Group A thresholds
* `failure/failure_playbook.md` — canonical resilience governance, AP-FP rules, deterministic degradation conditions
* `failure/scheduling_failures.md` — scheduler failure investigation context
* `failure/ghl_failures.md` — provider failure investigation context
* `failure/llm_failures.md` — AI governance failure context
* `ux/admin_dashboard.md` — dashboard card structure and component definitions (sibling document, co-governed by canonical UX contract)

Executable governance-safe test contracts:

* `tests/test_shadow_safety.py` — SHADOW and replay containment certification
* `tests/test_dashboard.py` — observability governance certification
* `tests/test_sync.py` — synchronization governance certification
* `tests/test_actions.py` — operator action governance certification
* `tests/test_work_queue.py` — work queue governance certification

---

## END OF FILE
