# ux/user_experience.md

---

## LAYER 12 — USER EXPERIENCE (GOVERNANCE-SAFE INTERACTION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-27 to reflect the finalized governed historical intelligence platform architecture. The previous version described MVP-era dashboard interaction guidance: simplistic user journeys ("System executes decisions", "Trigger manual action → System validates and executes"), generic UX constraints with no replay semantics, no SHADOW/LIVE isolation visibility, no immutable-lineage UX constraints, no governance invariant visibility, no attribution continuity requirements, and MVP/STANDARD/PRODUCTION scope tiers that implied incremental governance maturity rather than non-negotiable baseline guarantees. That architecture is incompatible with the governance-safe interaction model. UX is no longer workflow interaction guidance or dashboard rendering guidance. UX is governance-safe orchestration visibility architecture.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe UX Interaction Architecture** defines:

* What the UX layer is allowed to display, trigger, and surface — and what it is explicitly prohibited from doing
* How operators observe governance state without influencing orchestration logic
* How SHADOW containment and replay isolation are visible to operators
* How immutable lineage artifacts are displayed without implying mutability
* How attribution continuity is surfaced throughout every interaction
* How degradation states remain observable and never silently hidden
* What operator actions are governed API invocations vs what is prohibited
* How access control enforces governance boundaries across role tiers

This document is the **canonical UX governance contract** for:

* `ux/admin_dashboard.md` — governed by §3, §5, §6, §10, §12
* `ux/operator_workflows.md` — governed by §4, §5, §6, §8

Where child UX documents conflict with this document, this document governs.

---

### 1.2 What UX Is NOT

In the governance-safe interaction model, UX is explicitly **NOT**:

* **Workflow execution guidance** — UX does not guide operators through decision-making steps that produce orchestration outputs; that authority belongs to the backend directive layer
* **A business logic surface** — no validation, calculation, threshold evaluation, or decision logic lives in the UI; UI reflects backend state, it does not compute it
* **A direct execution surface** — operators cannot directly trigger provider dispatch, state transitions, or AI inference from the UI; all such interactions pass through governed API endpoints
* **A mutable interface for immutable artifacts** — FINALIZED snapshots, REPORT_PUBLISHED reports, and archived AI insights are read-only surfaces; the UI must never render a control implying these artifacts can be modified
* **A replay execution surface** — replay and regeneration modes are backend orchestration modes; the UI surfaces replay state for visibility only; it cannot trigger live effects through replay pathways
* **A SHADOW-to-LIVE transition surface for non-Governance-Administrators** — the SHADOW→LIVE transition is a governance-authorization event; the UI must enforce role restrictions before surfacing transition controls

---

### 1.3 UX Governance Layer Definition

The UX layer sits above the governance-authorized API boundary. It has:

* **Read access** to governance state, operational metrics, lineage artifacts, and alert records via governed read endpoints
* **Control access** to operator-authorized API invocations (governed manual actions, sync triggers, batch triggers) via governed write endpoints
* **No direct access** to database state, orchestration services, provider systems, or directive evaluation

| UX surface | Permitted operations | Prohibited operations |
|---|---|---|
| Dashboard read views | Display governance state, mode badges, alert classifications, lineage attribution | Derive, compute, or cache governance state independently |
| Operator action controls | Invoke governed API endpoints with operator identity | Bypass API layer; construct outbound payloads; modify records directly |
| Replay visibility views | Display replay execution metadata, containment badges, causation lineage | Initiate live execution from replay context; display replay outputs as LIVE |
| SHADOW mode views | Display containment badges, suppressed-provider indicators, shadow intent metadata | Display SHADOW outputs as LIVE; initiate SHADOW→LIVE from non-Governance-Administrator role |
| Immutable artifact views | Display FINALIZED snapshots, published reports, AI narratives as read-only | Render edit controls; imply mutability; suppress immutability indicators |

---

## 2. INTERACTION MODEL

---

### 2.1 Governance-Safe Interaction Principle

> UI is a **read + control surface only**.
> All orchestration decisions originate in the backend directive layer.
> Operators observe and authorize governed actions — they do not make orchestration decisions.

The interaction model is:

```
Backend Orchestration  →  Governance State  →  API Endpoints  →  UX Display / Control
                                                     ↑
                                         Operator-authorized API invocations only
```

Operators never own a step in this chain. They observe state and invoke governed API endpoints. The backend validates, authorizes, and executes.

---

### 2.2 Orchestration-Intent Interaction Governance

All UX-accessible controls that trigger backend behavior must:

1. Invoke a governed API endpoint — never call a provider API, write to a database, or trigger an orchestration service directly
2. Carry the invoking operator's identity — every API invocation is attributed
3. Accept the backend's governance validation response — the UI must surface rejection reasons (e.g., `MAX_ATTEMPTS_REACHED`, `STATE_TRANSITION_NOT_ALLOWED`, `COMPLIANCE_HOLD_ACTIVE`) without suppressing them
4. Reflect the backend's resulting state change — post-action refreshes must show actual system state, not optimistic local state

Prohibited UX interaction patterns:

* Optimistic state mutation — updating UI state before API response confirms
* Silent action failure — suppressing backend rejection without surfacing a governance reason
* Retry-on-failure without user acknowledgement — auto-retrying API invocations without displaying the failure reason
* Direct orchestration bypass — any frontend pathway that reaches provider systems without a governed API call

---

## 3. USER PERSONAS AND ROLE GOVERNANCE

---

### 3.1 Governance Administrator

Authority: Authorize SHADOW→LIVE execution mode transitions.

Interaction boundaries:

* Is the **only role** permitted to initiate a SHADOW→LIVE mode transition (AP-RT7, CV2-4)
* Must confirm an `activation_record_present` acknowledgement before the transition API is called
* Cannot trigger mode transitions via automated pathways — every transition is operator-initiated with explicit acknowledgement
* Transition confirmation UI must display: `from_mode = SHADOW`, `to_mode = LIVE`, required activation record ID, and explicit confirmation prompt

---

### 3.2 Operational Administrator / Operator

Authority: Trigger governed manual actions; monitor orchestration health; investigate student cases.

Interaction boundaries:

* May invoke: `POST /actions/manual`, `POST /outreach/trigger`, `POST /sync/mssql`, `POST /quick-actions/log`
* May view: all dashboard read surfaces, all governance alert classifications, student lineage views, execution mode badges
* May NOT: initiate SHADOW→LIVE transitions; mutate FINALIZED artifacts; access audit-restricted governance telemetry
* Every action must produce an audit record with: `operator_identity`, `action_type`, `student_id` (where applicable), `correlation_id`, `execution_mode`, `timestamp`

---

### 3.3 Program Manager / Viewer

Authority: Read-only access to operational dashboards and student lifecycle views.

Interaction boundaries:

* May view: all read-only dashboard surfaces, lifecycle tab data, student profile views, cohort metrics
* May NOT: invoke any write endpoints; access governance transition controls; view audit-restricted compliance telemetry; export compliance-governed records without authorized access

---

### 3.4 System (Automated Actor — NOT a UX Persona)

The system is not a UX persona. "System executes decisions" and "System validates and executes" are prohibited UX semantics. The system is the backend orchestration engine. It does not appear as a UX actor.

UX-visible system outputs are governance state records — they are displayed as attribution-attributed backend outputs, not as operator actions.

---

## 4. SHADOW AND REPLAY UX GOVERNANCE

---

### 4.1 SHADOW Mode Visibility

Every UX surface that renders data produced in SHADOW mode must:

* Display a persistent `SHADOW MODE` containment badge — never omit, never suppress
* Label all outreach history, state transitions, and action logs produced in SHADOW mode with `execution_mode = SHADOW` indicators
* Visually distinguish SHADOW outputs from LIVE outputs — SHADOW records must never appear identical to LIVE records in display
* Display suppressed-provider indicators: providers (GHL, SMS, email, Synthflow) show as `SUPPRESSED` in SHADOW mode; operator must not interpret these as failed or unavailable

SHADOW mode UX invariants:

* `governance_scope = SHADOW_ONLY` must be visible on every SHADOW orchestration intent displayed
* Provider records in SHADOW mode display `outbound_suppressed = true` — this is the expected state, not an error
* AI advisory outputs in SHADOW mode display `outcome = shadow_only` — not a failure state
* No UX surface may display a SHADOW execution as a LIVE execution

---

### 4.2 SHADOW→LIVE Transition UX Governance

The SHADOW→LIVE transition is a governance-authorization event, not an operational workflow step.

UX behavior for SHADOW→LIVE transition:

1. Transition controls are visible **only to Governance Administrator** role
2. Before surfacing the transition control, the UI must confirm via API that `activation_record_present` is validatable
3. The transition confirmation dialog must display:
   * `from_mode: SHADOW` and `to_mode: LIVE` explicitly
   * Activation record ID (required — UI must not allow submission without this)
   * Operator acknowledgement checkbox confirming the activation record is present
4. The transition is submitted via governed API endpoint with operator identity — automated submission is prohibited (AP-RT7)
5. If the backend rejects the transition, the rejection reason must be surfaced — no silent failure

---

### 4.3 Replay Mode Visibility

Replay execution is a backend orchestration mode. The UX must surface replay state for visibility without implying that replay outputs are LIVE.

Every replay-mode output displayed in the UX must:

* Display `execution_type = replay` or `execution_type = regeneration` prominently — never render replay outputs in the same style as `execution_type = original` outputs
* Show `governance_scope = REPLAY_ONLY` — replay outputs are never authorized for LIVE consumption
* Display a `new correlation_id` with a visible `causation_id → original correlation_id` lineage link
* Show `historical_config_version_id` — replay uses historical config, not the current ACTIVE config version
* Display `live_effects_produced = 0` — this is the expected invariant; a non-zero value is a governance defect that must surface as a CRITICAL alert

Replay mode UX invariants:

* Replay outputs must never appear alongside LIVE outputs without explicit mode differentiation
* Replay outputs must never render as actionable for LIVE execution
* Regeneration outputs (re-rendered reports) must be labeled as regenerated artifacts — not as newly generated reports
* A replay with `replay_partial = true` must display a `PARTIAL REPLAY` warning — operators must be aware the replay scope was incomplete

---

### 4.4 Replay Attribution Visibility

Every replay record displayed in the UX must surface lineage attribution:

* `causation_id` → original cycle's correlation_id — displayed as a clickable lineage link where supported
* `historical_config_version_id` — the config version that governed the historical execution
* `fingerprint_comparison_outcome` — `IDENTICAL`, `POTENTIALLY_DIVERGENT`, or `COMPARISON_UNAVAILABLE`
* If `fingerprint_comparison_outcome = POTENTIALLY_DIVERGENT`, a visible warning badge must be rendered — divergence is not an error but it must not be hidden

---

## 5. IMMUTABLE LINEAGE UX CONSTRAINTS

---

### 5.1 FINALIZED Artifact Display Rules

UX surfaces that display FINALIZED snapshots or REPORT_PUBLISHED reports must:

* Render them as **read-only** — no edit controls, no delete controls, no update affordances
* Display `lifecycle_state = FINALIZED` or `lifecycle_state = REPORT_PUBLISHED` as a badge — the immutability state is always visible
* Never render a FINALIZED artifact with controls that imply `allows_update = true` or `allows_delete = true`
* Surface `sourced_from_warehouse = true` for regeneration outputs — confirming the source is the append-only warehouse

If the backend returns a mutation attempt on a FINALIZED artifact, the UI must display a governance rejection error — not a generic error.

---

### 5.2 Append-Only Historical Visibility

The UX must surface the append-only nature of historical records:

* State transition logs are displayed in chronological order — they cannot be reordered, filtered to hide entries, or presented as editable
* Outreach history records are append-only audit artifacts — the UI must not offer delete or edit affordances
* AI insights, once archived, display `lifecycle_state = ARCHIVED` and offer no modification path

---

### 5.3 Attribution Continuity Visibility

Every orchestration record displayed in the UX must show attribution fields:

* `correlation_id` — present on every record; a missing correlation_id is a governance defect, not a display gap
* `execution_mode` — present on every record; never hidden
* `execution_type` — `original | replay | regeneration | recovery` — distinguishes record provenance
* `causation_id` — present on derived events (replay, recovery); renders as a lineage link to the parent event
* `config_version_id` — present on all orchestration intent records

If any of these fields is null on a displayed record, the UI must surface an `ATTRIBUTION_INCOMPLETE` indicator — not silently suppress the missing field.

---

### 5.4 Fingerprint Visibility

When displaying finalized snapshot records:

* The five fingerprint components must be accessible in the detail view: `schema_version`, `config_registry_version`, `ai_prompt_version`, `ai_model_version`, `report_template_version`
* Any component with value `UNKNOWN_V0` must display a visible audit-gap indicator — this is a known limitation, not an error
* Fingerprint mismatch between a stored snapshot and the current system fingerprint must surface as a `MEDIUM` severity governance alert in the UI

---

## 6. OPERATOR INTERACTION SEMANTICS

---

### 6.1 Governed API-Only Interaction

Operators may only interact with the system through governed API endpoints. The UX must enforce this boundary:

* All action controls (manual actions, batch triggers, sync triggers) invoke backend API endpoints — never bypass
* The UX must display the governance authorization result of every API invocation — approval or rejection, with reason
* Rejected invocations (e.g., compliance hold active, state machine violation, max attempts reached) must surface the backend's governance reason — suppression is prohibited

---

### 6.2 Operator Interaction Prohibitions

Operators cannot:

* Bypass the orchestration governance layer — no direct provider calls, no direct database writes from the UI
* Mutate FINALIZED artifacts — the UI must not surface controls that imply FINALIZED records can be modified
* Override Config V2 governance — threshold values, retry counts, and channel progression rules are Config V2 territory; the UI may display current config values as read-only; it may not override them
* Trigger a SHADOW→LIVE transition without a confirmed activation record — the UI enforces this at the presentation layer before the API call is made
* Initiate automated SHADOW→LIVE transitions — the UX has no automated pathway for this transition

---

### 6.3 Audit Attribution Requirements

Every operator action must produce a visible audit trail:

* The UX must confirm that every action invocation produced an audit record: `correlation_id`, `operator_identity`, `action_type`, `execution_mode`, `timestamp`
* If audit record creation fails, the UX must surface the failure — not proceed silently
* Audit confirmation receipts are displayed inline after every action (action log entries visible in the Manual Actions card)

---

## 7. OBSERVABILITY UX GOVERNANCE

---

### 7.1 Governance State Must Always Be Visible

The following governance states must always be visible in the dashboard and never hidden:

| State | Display requirement |
|---|---|
| `execution_mode` | Always visible in dashboard header — SHADOW / LIVE / REPLAY / DEGRADED / MAINTENANCE |
| `SHADOW containment` | Persistent SHADOW MODE badge when `execution_mode = SHADOW` |
| `DEGRADED` | DEGRADED MODE badge with `degradation_cause` visible |
| `MAINTENANCE` | MAINTENANCE MODE badge with explicit "orchestration loops paused" notice |
| `compliance_hold_active` | Visible compliance hold indicator on any student record subject to a hold |
| `FINALIZED` | Immutability badge on every FINALIZED artifact |
| `REPORT_PUBLISHED` | Immutability badge on every published report |

---

### 7.2 Degradation Visibility

Degradation is a governance state, not an error to be hidden. The UX must:

* Display degradation type and severity: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
* Surface `degradation_cause` in plain language — not a generic "system error"
* Display `affected_domains` — which orchestration domains are operating in degraded state
* Never display a degraded system as fully operational
* Surface `recovery_path` when available — operators must be able to see what recovery action is pending

Degradation containment rule: if `silent_swallow = true` appears on any degradation record, this is a governance defect and must be surfaced as a CRITICAL alert.

---

### 7.3 Provider Boundary Visibility

All provider interactions must be visible with their governance scope:

* GHL interactions: display `origin_authority = platform_supplementary` — GHL is supplementary, not authoritative
* SQL Server sync: display `origin_authority = sql_server_authoritative` — SQL Server wins on conflict
* Provider suppressed state (SHADOW/REPLAY): display `outbound_suppressed = true` as expected state — not error
* Provider unavailable state (DEGRADED): display `UNAVAILABLE` with severity classification — not silently blank

---

### 7.4 Synchronization Visibility

SQL Server sync events must surface:

* `origin_source = mirrored_sql_server`, `origin_authority = sql_server_authoritative`
* Dedup gate result when duplicate detected: `duplicate_detected`, `dedup_gate_applied`
* Sync outcome: scanned / added / updated / failed counts
* Conflict attribution when SQL Server overrides a GHL record — winning source visible

---

### 7.5 Scheduler Visibility

Scheduler state must be visible:

* Last successful run timestamp — `Never ran` surfaced as WARNING
* Next scheduled run window
* Current execution mode at time of last run
* Scheduler idle vs active state
* Any orchestration loops paused in MAINTENANCE mode

---

### 7.6 AI Governance Visibility

AI outputs must be visibly attributed:

* `ai_governance_tier`: `FINALIZED_COPY | AI_GENERATED | STALE | UNAVAILABLE`
* `advisory_scope`: `AVAILABLE | UNAVAILABLE | STALE | SHADOW_ONLY`
* Stale AI served in degraded state: display `stale_ai_present = true`, `stale_ai_version` visible
* SHADOW mode AI: display `outcome = shadow_only` — not failure
* AI is advisory-only: no AI output may be displayed as a decision or authorization — only as advisory input

AI advisory prohibition in UX: the display of an AI advisory output must never imply the AI authorized an orchestration action. Advisory outputs are labeled as advisory; authorization labels belong only to governance-confirmed operator actions.

---

## 8. ACCESS CONTROL GOVERNANCE

---

### 8.1 Role-Based Visibility Semantics

| Role | Permitted views | Prohibited views |
|---|---|---|
| Governance Administrator | All views + SHADOW→LIVE transition controls | None |
| Operational Administrator | All operational views + manual action controls | Governance transition controls; compliance-restricted audit records |
| Program Manager / Viewer | All read-only dashboard and lifecycle views | Manual action controls; governance transition controls; compliance records |

---

### 8.2 Replay Access Restrictions

Replay execution metadata is visible to Operational Administrator and above.

* Viewer roles may see high-level replay status (replay in progress, replay complete) but not internal replay diagnostic fields
* Replay causation lineage (causation_id chains) is visible to Operator and above
* Replay divergence alerts (POTENTIALLY_DIVERGENT) must be visible to Operator and above — not hidden from view

---

### 8.3 Immutable Record Access Behavior

FINALIZED and REPORT_PUBLISHED records are accessible to all roles in read-only mode.

* No role may render modification controls on immutable records
* Compliance-governed deletion events are visible only to `compliance_officer` and `auditor` roles
* Pre-action audit entries for compliance operations are visible to authorized compliance roles only

---

### 8.4 Audit Visibility Guarantees

Governance telemetry is authoritative; operational telemetry is contextual. The UX must surface:

* Full audit trail of operator actions with `correlation_id` linkage
* Governance boundary crossing events: FINALIZED state changes, config version promotions, SHADOW→LIVE transitions
* Every audit entry must display: `actor_identity`, `action_type`, `execution_mode`, `timestamp`, `correlation_id`

---

## 9. UX GOVERNANCE INVARIANTS

---

### 9.1 Cross-Domain Governance Invariants (INV-1 through INV-7)

These invariants govern UX display behavior — they define what the UI must never misrepresent.

| Invariant | UX enforcement |
|---|---|
| **INV-1** FINALIZED snapshot is immutable | No edit/delete controls rendered on FINALIZED artifacts; immutability badge always visible |
| **INV-2** Exactly one config version ACTIVE | UI displays current ACTIVE version; no multi-active state implied; config version shown on every intent record |
| **INV-3** (FAD-3) Activation is prospective-only | SHADOW→LIVE activation UI requires activation_record_present confirmation before submission; no backdated activation implied |
| **INV-4** (AP-RT2) No LIVE effects from replay | Replay outputs rendered with REPLAY_ONLY scope; live_effects_produced = 0 shown as invariant; non-zero triggers CRITICAL alert |
| **INV-5** Attribution continuity | correlation_id, execution_mode, execution_type always displayed; null values surface ATTRIBUTION_INCOMPLETE indicator |
| **INV-6** (FAD-1) FINALIZED_COPY immutability | AI narratives in FINALIZED state rendered read-only; allows_update = false confirmed visually |
| **INV-7** No hardcoded thresholds | Config V2 resolved values shown as read-only; no UX control allows threshold override |

---

### 9.2 FAD Visibility Guarantees (FAD-1 through FAD-6)

| FAD | UX behavior |
|---|---|
| **FAD-1** FINALIZED_COPY immutability | All AI narratives in FINALIZED state: read-only view; no edit path |
| **FAD-2** Regeneration reads warehouse exclusively | Regenerated reports labeled `sourced_from_warehouse = true`; no live inference indicator |
| **FAD-3** Prospective-only activation | Activation form requires future-dated or current confirmation only |
| **FAD-4** Append-only audit log | Audit records display with no delete/edit affordances; chronological only |
| **FAD-5** Config V2 governance | Threshold values in UI are read-only resolved values; no override controls |
| **FAD-6** Snapshot fingerprint reproducibility | Fingerprint components always visible on FINALIZED records; UNKNOWN_V0 surfaces audit-gap indicator |

---

### 9.3 Append-Only Visibility Guarantees

The UX must enforce append-only semantics visually:

* Historical records may not appear editable regardless of user role
* Audit log entries are displayed in append order only — no filter that hides entries from the visible window is permitted
* Delete controls are never rendered on records in: `state_transition_log`, `outreach_history`, `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `student_timeline_events`

---

### 9.4 SHADOW/LIVE Isolation Guarantees

The UX must never allow SHADOW and LIVE outputs to appear interchangeable:

* Every record carries an explicit `execution_mode` badge
* SHADOW records display `SHADOW` mode indicator — never blank
* LIVE records display `LIVE` mode indicator
* Mixed-mode views (where both exist, e.g., outreach history spanning a mode transition) must display both execution modes distinctly per record — never aggregate them into an unlabeled list

---

## 10. OPERATOR USER JOURNEYS (GOVERNANCE-SAFE)

---

### 10.1 Monitor Orchestration Health

**Actor:** Operational Administrator

**Steps:**

1. Open dashboard
2. Observe execution mode badge in header — confirms SHADOW / LIVE / DEGRADED state
3. Scan governance alert classifications — CRITICAL / HIGH / MEDIUM / LOW
4. Click Operational Alerts card for governance alert detail with `error_class`, `affected_domains`, `recovery_path`
5. Confirm System Health card shows: Postgres connected, SQL Server configured, scheduler last ran, execution mode, provider availability
6. If `execution_mode = DEGRADED`, review degradation cause and affected domains before taking any action

**Governance invariant:** Operator visibility of governance state is non-optional. No state critical to governance may be hidden from this view.

---

### 10.2 Investigate Student Case with Lineage Visibility

**Actor:** Operational Administrator or Program Manager

**Steps:**

1. Open Student Cases card
2. Enter student ID and invoke lookup via API
3. Confirm profile card shows: current state, checkpoint, attempt count with config_version_id, last contact correlation_id
4. Review Outreach History: each entry shows `execution_mode`, `execution_type`, `correlation_id`, `config_version_id` — not just channel and date
5. Review State Transitions: each entry shows `actor`, `trigger`, `correlation_id`, `execution_mode`
6. If any record shows `ATTRIBUTION_INCOMPLETE`, surface it as a visibility defect — do not suppress

---

### 10.3 Review Governance Alerts

**Actor:** Operational Administrator

**Steps:**

1. Click Operational Alerts card
2. Each alert must show: `severity` (CRITICAL/HIGH/MEDIUM/LOW), `error_class` (never generic), `affected_domains`, `recommended_action`, `recovery_path` (if available)
3. For SHADOW containment failures: display as CRITICAL — never downgrade severity
4. For replay containment violations (live_effects_produced ≠ 0): display as CRITICAL
5. For attribution incomplete records: display as governance defect alert — correlate to student ID where available

---

### 10.4 Trigger Governed Operator Action

**Actor:** Operational Administrator

**Steps:**

1. Select student in lifecycle tab (row selection required)
2. Confirm SHADOW MODE badge is visible (or LIVE mode badge — operator must be aware of execution mode before acting)
3. Invoke action via governed API button
4. Review inline result from API: governance authorization confirmation or rejection with reason
5. Confirm audit record was created: `correlation_id` displayed in action confirmation
6. If rejection: surface the governance reason fully — MAX_ATTEMPTS_REACHED, STATE_TRANSITION_NOT_ALLOWED, COMPLIANCE_HOLD_ACTIVE, etc.

---

### 10.5 SHADOW→LIVE Transition Authorization

**Actor:** Governance Administrator only

**Steps:**

1. Navigate to execution mode transition control (visible to Governance Administrator only)
2. Confirm current mode: `SHADOW`
3. Enter or confirm activation record ID (required — form submission blocked without this)
4. Read and confirm explicit acknowledgement: "I confirm an activation record is present authorizing this transition"
5. Submit via governed API endpoint — backend validates actor_type, activation_record_present, automated_service_triggered
6. On success: execution mode badge updates to `LIVE`; audit record of transition visible
7. On rejection: surface rejection reason — do not retry automatically

---

## 11. DASHBOARD COMPONENTS (GOVERNANCE-SAFE)

---

### 11.1 Governance State Display Requirements

Every dashboard view must include:

* Execution mode badge (header-level): `SHADOW | LIVE | REPLAY | DEGRADED | MAINTENANCE`
* Alert severity summary: highest severity active alert class
* Config version indicator: current ACTIVE config version ID (read-only)
* Last orchestration run correlation_id (for lineage traceability)

---

### 11.2 Mode-Aware Component Behavior

| Component | SHADOW mode behavior | LIVE mode behavior | DEGRADED mode behavior |
|---|---|---|---|
| Channel Performance | All sends labeled SUPPRESSED; shadow count = attempt count | Normal metrics | Affected channels labeled UNAVAILABLE |
| Manual Actions | Actions execute in SHADOW mode; audit logged; no outbound | Actions execute LIVE | Actions may be blocked if relevant domain degraded |
| Trigger Outreach Batch | Batch runs SHADOW — no outbound dispatch | Batch runs LIVE | Batch may be partially degraded; degraded domains labeled |
| SQL Server Sync | Sync proceeds (read-only — not an outbound action) | Sync proceeds | Sync blocked if SQL Server UNAVAILABLE |
| AI Insights | Advisory tagged `outcome = shadow_only` | Full advisory | STALE served if AI provider UNAVAILABLE |

---

### 11.3 Lineage Visibility Components

The following lineage fields must be surfaceable in student detail views:

* `correlation_id` — every outreach history and state transition record
* `execution_mode` — every record
* `execution_type` — every record
* `causation_id` — derived events (replay, recovery)
* `config_version_id` — every orchestration intent record
* `origin_source` — every sync-derived record
* `origin_authority` — every sync-derived record

---

## 12. UX CONSTRAINTS (GOVERNANCE-SAFE)

---

### 12.1 No Business Logic in UI

* UI must not evaluate eligibility, retry authorization, threshold comparisons, or channel selection
* These are directive-layer responsibilities
* UI displays the output of backend directive evaluation only

---

### 12.2 No Direct Execution Semantics

* Controls that appear to directly execute provider actions (e.g., "Send SMS", "Trigger GHL") must invoke governed API endpoints
* No UI control bypasses the backend orchestration boundary
* API invocation is the only permitted execution pathway from the UI

---

### 12.3 Attribution Continuity Required

* No record may be displayed without `correlation_id`, `execution_mode`, `execution_type`
* Missing fields surface ATTRIBUTION_INCOMPLETE indicator — not blank display
* UI must not normalize attribution gaps by omitting the field from the display schema

---

### 12.4 Mode-Consistent Display

* Records produced in SHADOW mode must always render with SHADOW mode indicators — they may not be displayed as neutral/unlabeled after a mode transition
* Records produced in REPLAY mode must always render with REPLAY mode indicators — they may not be commingled with LIVE records in an unlabeled list
* Execution mode is permanent metadata on a record — it does not update when the system transitions modes

---

### 12.5 No Hidden Governance State

* All governance state transitions (FINALIZED, REPORT_PUBLISHED, SHADOW→LIVE, config version promotion) must be represented in the audit trail visible via the UI
* Governance-boundary crossings are never hidden from operators with appropriate access
* Silent governance state is a UX defect

---

### 12.6 Performance Constraints

* Dashboard load ≤ 2 seconds
* API response ≤ 500 ms
* Pagination for large datasets
* Auto-refresh every 60 seconds; manual refresh available

---

## 13. ERROR HANDLING (UX GOVERNANCE)

---

### 13.1 Governance-Aware Error Display

Error messages must:

* Display the governance reason, not a generic message — `MAX_ATTEMPTS_REACHED`, `COMPLIANCE_HOLD_ACTIVE`, `STATE_TRANSITION_NOT_ALLOWED`, `ATTRIBUTION_INCOMPLETE`, `IMMUTABLE_RECORD_MUTATION_REJECTED`
* Never expose internal stack traces or secrets in error text
* Surface the `error_class` from the backend response — not coerce to a generic "Something went wrong"

---

### 13.2 Mode-Aware Error Handling

* In SHADOW mode: errors from suppressed providers must display as `SUPPRESSED — expected in SHADOW mode`, not as provider failures
* In DEGRADED mode: errors from unavailable providers must display with `UNAVAILABLE` and `severity` classification — not as generic errors
* In REPLAY mode: any error that would generate a LIVE effect must be surfaced as a CRITICAL containment violation — not silently suppressed

---

### 13.3 FINALIZED Mutation Rejection

If the backend rejects a mutation attempt on a FINALIZED record:

* Display: `GOVERNANCE REJECTION: This record is FINALIZED and immutable. No modifications are permitted.`
* Do not retry the mutation
* Do not surface a "try again later" message that implies eventual mutability

---

## 14. ACCEPTANCE CRITERIA (GOVERNANCE-SAFE UX CERTIFICATION)

---

### Case 1 — SHADOW Containment Visibility

**Given** `execution_mode = SHADOW`
**When** dashboard loads
**Then** SHADOW MODE badge visible in header; all outreach history records labeled `execution_mode = SHADOW`; no SHADOW record rendered as LIVE

---

### Case 2 — Replay Isolation Visibility

**Given** replay execution records exist in audit trail
**When** operator views outreach history including replay records
**Then** replay records display `execution_type = replay`, `governance_scope = REPLAY_ONLY`; `causation_id` visible linking to original; live_effects_produced = 0 confirmed; replay records never rendered as LIVE

---

### Case 3 — Immutable Lineage Visibility

**Given** FINALIZED snapshot exists
**When** operator views snapshot detail
**Then** `lifecycle_state = FINALIZED` badge visible; no edit/delete controls rendered; fingerprint components visible; `allows_update = false` confirmed; any attempt to render modification controls is a test failure

---

### Case 4 — Attribution Continuity

**Given** any orchestration record displayed in student case view
**When** record detail is visible
**Then** `correlation_id`, `execution_mode`, `execution_type` are all non-null; missing fields surface `ATTRIBUTION_INCOMPLETE` indicator

---

### Case 5 — Degradation Visibility

**Given** `execution_mode = DEGRADED` with affected_domains
**When** dashboard loads
**Then** DEGRADED MODE badge visible; `degradation_cause` and `affected_domains` surfaced in alert; `recovery_path` shown where available; no degraded component appears as fully operational

---

### Case 6 — Provider Boundary Visibility

**Given** SHADOW mode active
**When** operator views Channel Performance card
**Then** all providers display `SUPPRESSED` state; shadow count = attempt count; SHADOW mode note visible; no provider labeled as "failed" when suppression is the expected governance state

---

### Case 7 — Governance Invariant Consistency

**Given** any live_effects_produced ≠ 0 on a replay record
**When** that record is surfaced in the dashboard
**Then** CRITICAL governance alert emitted; replay containment violation visible; record labeled as governance defect — not silently displayed as a normal replay record

---

### Case 8 — SHADOW→LIVE Transition Authorization Gate

**Given** Governance Administrator initiates SHADOW→LIVE transition
**When** transition form rendered
**Then** activation record ID field is required; confirmation checkbox required; submission blocked until both present; API rejection surfaces reason verbatim

---

### Case 9 — AI Advisory Visibility

**Given** AI insight displayed in student drawer
**When** operator views the insight
**Then** `ai_governance_tier` visible (FINALIZED_COPY / AI_GENERATED / STALE / UNAVAILABLE); advisory output labeled as advisory — not as authorization; in SHADOW mode, `outcome = shadow_only` label visible

---

### Case 10 — Non-Governance-Administrator Cannot Access Transition Control

**Given** Operational Administrator role (not Governance Administrator)
**When** dashboard renders
**Then** SHADOW→LIVE transition control is not rendered or is visibly disabled with access restriction indicator; no pathway to transition from this role

---

## 15. REFERENCES

---

Inherits from and is governed by:

* `spec/01_requirements.md` — platform purpose, operational domains, FAD governance model
* `spec/03_state_transition_rules.md` — INV-1 through INV-7, all lifecycle domain governance boundaries
* `spec/05_external_integrations.md` — lineage-preserving integration fields, SQL Server authority boundary
* `spec/06_observability_operations.md` — two-category telemetry model, governance-aware observability, lineage-aware telemetry
* `spec/07_api_contracts.md` — all API endpoint contracts governing operator interactions
* `runtime/system_loop.md` — six runtime modes, SHADOW→LIVE governance (§3.2), AP-RT7
* `runtime/scheduler_design.md` — scheduler visibility requirements
* `failure/failure_playbook.md` — resilience governance, degradation observability
* `ux/admin_dashboard.md` — dashboard structure and component definitions (child — governed by this file)
* `ux/operator_workflows.md` — operator workflow step definitions (child — governed by this file)
* `tests/test_shadow_safety.py` — executable SHADOW and replay containment certification (Phase 27)
* `tests/test_dashboard.py` — executable observability governance certification (Phase 26)
* `tests/test_sync.py` — executable synchronization governance certification
* `tests/test_actions.py` — executable operator action governance certification
* `tests/test_work_queue.py` — executable work queue governance certification

---

## END OF FILE
