# runtime/scheduler_design.md

---

## LAYER 7 — RUNTIME (GOVERNANCE-SAFE SCHEDULER ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture. The previous version described MVP-era scheduler timing documentation: a time-based trigger with a hardcoded "6:00 PM CST" specification value, a single-execution-per-window lock with no governance context, a simplistic "trigger recovery run" on missed detection, a hardcoded concurrency limit of 50 concurrent executions, and no runtime mode semantics, no replay-safe scheduling, no Config V2 governance, and no attribution or observability requirements. That architecture is incompatible with the governance-safe orchestration model. Scheduling orchestration is no longer timing infrastructure. It is governance-safe orchestration coordination — deterministic runtime-cycle sequencing with replay-safe execution-window governance and observable orchestration timing control. This document is governed by and must not conflict with `runtime/system_loop.md`.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Scheduler Orchestration Architecture** defines:

* How scheduler orchestration coordinates governance-safe runtime-cycle sequencing for each of the ten canonical orchestration domains
* What scheduler domains exist, what their execution cadences are, and how execution cadences are governed by Config V2 — not by hardcoded timing values
* What runtime mode restrictions apply to each scheduler domain and how mode transitions affect scheduling authority
* How orchestration window control prevents duplicate LIVE cycles, orphaned cycles, and replay corruption
* How replay and regeneration scheduling semantics differ from LIVE scheduling, and what LIVE effects are suppressed in each
* How recovery and degradation governance responds deterministically when scheduler lag, scheduler crash, provider outage, AI outage, or sync backlog occurs
* How scheduler attribution lineage propagates into every orchestration cycle it coordinates
* What authority boundaries constrain scheduler domains from acquiring provider authority, AI authority, or governance-transition authority

This document is governed by:

* `runtime/system_loop.md` — the authoritative parent runtime contract (§4.1–4.10 trigger conditions, §10.5, §3.2)

This document governs:

* `runtime/daily_outreach_flow.md` — scheduling trigger semantics referenced in §4.1 apply
* `runtime/retry_cycle_flow.md` — retry scheduling cadence from §4.2 applies; hardcoded MAX_ATTEMPTS timing is prohibited

Where this document conflicts with V1 child-document semantics, this document governs.

---

### 1.2 What Scheduler Orchestration Is NOT

In the governance-safe orchestration model, scheduler orchestration is explicitly **NOT**:

* **Direct operational execution** — schedulers do not execute outreach, send communications, or invoke provider APIs; they coordinate governance-safe cycle sequencing and delegate to orchestration loops
* **Generic timing infrastructure** — scheduler domains are not generic cron jobs; each domain is a governed orchestration coordinator with explicit mode behavior, attribution requirements, and replay restrictions
* **A governance definition layer** — schedulers inherit governance boundaries from Config V2, directives, and system_loop.md; they do not define thresholds, evaluate eligibility, or make orchestration decisions
* **Hardcoded timing logic** — no scheduler domain embeds a hardcoded trigger time, retry interval, concurrency limit, or window duration; all timing values are governed by Config V2 variables
* **A silent execution layer** — every scheduler-triggered cycle is attributed, observable, and historically explainable; schedulers that fire without producing observable records are specification violations

---

### 1.3 Scheduler Governance Layer Definition

Scheduler orchestration sits at the coordination boundary between:

* **Config V2 governance** (trigger cadences, timing windows, threshold values) — consumed but not defined by schedulers
* **Runtime orchestration loops** (§4.1–4.10 of `runtime/system_loop.md`) — coordinated and triggered by scheduler domains
* **Attribution and observability layer** (correlation_id propagation, structured cycle records) — initiated at scheduler trigger

| Layer | Scheduler relationship |
|---|---|
| Config V2 | Governs all trigger timing; schedulers consume Config V2 variables; schedulers do not own timing values |
| Runtime orchestration loops | Triggered and sequenced by scheduler domains; loops own evaluation logic; schedulers own timing coordination |
| Directive layer | Scheduler domains do not evaluate directives; directives are evaluated within orchestration loops |
| Provider layer | Scheduler domains never interact with provider APIs |
| Attribution layer | Scheduler domains generate `cycle_id` and `triggered_at` attribution; orchestration loops generate `correlation_id` |

---

## 2. SCHEDULER ORCHESTRATION MODEL

---

### 2.1 Governance-Safe Scheduling Principle

Every scheduler-triggered orchestration cycle must satisfy the following invariants before the cycle begins:

1. **Config V2-governed timing** — the trigger time or cadence for every scheduler domain is governed by a Config V2 variable; hardcoded values are specification violations (AP-SCH6)
2. **Mode-aware trigger** — scheduler domains check the current execution mode before triggering a cycle; prohibited triggers in the current mode are not fired
3. **Attribution-initiated** — a `cycle_id` is generated at the scheduler trigger and passed to the orchestration loop as the attribution anchor for that cycle
4. **Idempotency-gated** — the scheduler checks whether an execution record for the current window already exists before triggering; duplicate triggers for the same window are no-ops
5. **Observable** — every scheduler trigger event produces a structured log record, whether or not the triggered loop succeeds

---

### 2.2 Scheduler Role in the Three-Tier Runtime Architecture

```
Config V2 Group A / H / I / K  →  Trigger timing governance
             ↓
Scheduler Orchestration Layer  →  Governance-safe cycle sequencing
             ↓
Runtime Orchestration Loops  →  Candidate evaluation and intent production
             ↓
Provider Layer  →  Operational delivery (never owned by schedulers)
```

Schedulers coordinate the hand-off between Config V2-governed timing and runtime orchestration loops. They do not collapse tiers. A scheduler that evaluates eligibility, constructs a provider payload, or reads student data is a specification violation (AP-SCH1).

---

### 2.3 Scheduler Attribution Definition

| Attribution field | Generated by | Consumed by |
|---|---|---|
| `cycle_id` | Scheduler domain at trigger | Passed to orchestration loop as session context |
| `triggered_at` | Scheduler domain | Scheduler trigger record; loop completion record |
| `scheduler_domain` | Scheduler domain | Trigger record; all loop records within this cycle |
| `execution_mode` | Config V2 / mode governance | All records emitted within the triggered cycle |
| `config_version_id` | Resolved at trigger time | All records emitted within the triggered cycle |

The scheduler does not generate `correlation_id`. `correlation_id` is generated within the runtime orchestration loop (per `system_loop.md` §11.1). The scheduler's `cycle_id` is the attribution anchor that links the scheduling event to the loop's `correlation_id`.

---

## 3. SCHEDULER MODES

---

### 3.1 Canonical Scheduler Mode Definitions

Six scheduler modes govern all scheduling behavior. Mode is set at the environment level and applies to every scheduler domain.

---

#### LIVE

| Aspect | Behavior |
|---|---|
| Allowed triggers | All 10 scheduler domains may trigger (subject to Config V2 cadence) |
| Prohibited triggers | Replay Scheduler domain may not trigger LIVE orchestration cycles (AP-SCH3) |
| Provider restrictions | Scheduler coordinates orchestration cycles that may produce LIVE provider dispatch; scheduler itself never calls providers |
| Replay restrictions | Replay scheduling produces SHADOW-only outputs; replay triggers carry `governance_scope = REPLAY_ONLY` |
| AI restrictions | AI Refresh Scheduler coordinates refresh requests; advisory-only constraint enforced within orchestration loops (system_loop.md §9.1) |
| Escalation restrictions | None — full escalation routing active within triggered orchestration loops |
| Observability | Full scheduler trigger records required for all domains |

---

#### SHADOW

| Aspect | Behavior |
|---|---|
| Allowed triggers | All 10 scheduler domains may trigger; orchestration loops produce SHADOW-only outputs |
| Prohibited triggers | Scheduler domains may not trigger cycles that produce LIVE outbound dispatch |
| Provider restrictions | All outbound dispatch suppressed within triggered orchestration loops; inbound webhooks ingested and tagged `execution_mode = SHADOW` |
| Replay restrictions | Replay scheduling SHADOW-only within SHADOW mode |
| AI restrictions | AI refresh requests authorized; advisory outputs tagged `outcome = shadow_only` |
| Escalation restrictions | Escalation candidacy assessed and logged; no live operator routing |
| Observability | Full scheduler trigger records required; all cycle outcomes tagged `execution_mode = SHADOW` |

---

#### REPLAY

| Aspect | Behavior |
|---|---|
| Allowed triggers | Replay Orchestration Scheduler (§4.8) only; operator-initiated and governance-authorized |
| Prohibited triggers | All outreach orchestration batch triggers (§4.1, §4.2) are suppressed; automated batch scheduling suspended |
| Provider restrictions | All provider interactions in replay use historical records; no live provider calls |
| Replay restrictions | All scheduled replay cycles carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` |
| AI restrictions | No live AI inference; FINALIZED_COPY sourced from `warehouse.snapshot_ai_narratives` exclusively |
| Escalation restrictions | Escalation outputs carry `REPLAY_ESCALATION_CANDIDATE` scope; no live routing |
| Observability | Full replay diagnostic set required per replay trigger record |

---

#### REGENERATION

| Aspect | Behavior |
|---|---|
| Allowed triggers | Report Generation Scheduler (§4.6) in regeneration mode only; operator-initiated |
| Prohibited triggers | All other outreach orchestration triggers suspended |
| Provider restrictions | No external calls of any kind; Report Generation Loop reads warehouse exclusively (FAD-2) |
| Replay restrictions | Regeneration is not replay; does not simulate orchestration decisions |
| AI restrictions | No live AI inference; report content sourced from `warehouse.snapshot_ai_narratives` |
| Escalation restrictions | No escalation actions |
| Observability | Regeneration cycle record required: `source_artifact_id`, `lineage_version`, `regeneration_timestamp` |

---

#### DEGRADED

| Aspect | Behavior |
|---|---|
| Allowed triggers | Orchestration Evaluation Scheduler, Retry Orchestration Scheduler, Escalation Polling Scheduler, Provider Synchronization Scheduler, Observability Heartbeat Scheduler may trigger (annotated DEGRADED) |
| Prohibited triggers | Triggers that require unavailable provider or AI are suppressed; snapshot and report triggers blocked if warehouse unreachable |
| Provider restrictions | Outbound dispatch blocked when provider unavailable; inbound webhooks continue |
| Replay restrictions | Replay scheduling permitted if warehouse accessible and historical config resolvable |
| AI restrictions | AI Refresh Scheduler trigger suppressed if AI provider unavailable; orchestration proceeds rule-based |
| Escalation restrictions | Escalation candidacy assessed and routed; provider failure escalation candidacy generated |
| Observability | Degradation structured log required: `degradation_cause`, `affected_domains`, `degradation_onset_timestamp` per trigger record |

---

#### MAINTENANCE

| Aspect | Behavior |
|---|---|
| Allowed triggers | No outreach orchestration triggers; config promotion trigger permitted (governance-authorized); read-only diagnostic scheduling permitted |
| Prohibited triggers | All batch orchestration triggers; all outbound scheduling; all AI refresh scheduling for operational purposes |
| Provider restrictions | All provider calls suspended |
| Replay restrictions | Replay scheduling permitted if purely diagnostic and warehouse not under migration |
| AI restrictions | All AI refresh scheduling suspended |
| Escalation restrictions | Escalation routing suspended; candidacy assessment for pre-existing cases permitted |
| Observability | Maintenance start/end structured log with `maintenance_actor`, `maintenance_reason`, `maintenance_scope` |

---

### 3.2 Mode Transition and Scheduling Impact

When execution mode transitions, the following scheduling impacts take effect immediately:

| Transition | Scheduling impact |
|---|---|
| SHADOW → LIVE | All 10 scheduler domains activate in LIVE configuration; outbound dispatch now authorized within triggered loops |
| LIVE → SHADOW | All outbound dispatch suppressed in triggered loops; scheduling continues with SHADOW-only outputs |
| LIVE → DEGRADED | Affected scheduler domains annotate triggers DEGRADED; triggers for unavailable resources suppressed |
| DEGRADED → LIVE | Scheduler domains resume normal trigger behavior; degradation annotation removed on next cycle |
| Any → REPLAY | Only Replay Orchestration Scheduler active; all batch scheduling suspended |
| Any → MAINTENANCE | All scheduling suspended except governance-authorized maintenance triggers |

No automation service may coordinate a SHADOW-to-LIVE mode transition through a scheduler trigger or scheduled event (AP-SCH2).

---

### 3.3 Scheduler Mode Check Requirement

Every scheduler domain must check the current execution mode as its first action before evaluating whether a trigger is due. A scheduler domain that fires a trigger without first checking execution mode is a specification violation.

---

## 4. CANONICAL SCHEDULER DOMAINS

---

The platform's scheduling architecture is organized into ten canonical scheduler domains. Each domain maps to one of the ten canonical runtime orchestration loops defined in `runtime/system_loop.md` §4. Scheduler domains do not share mutable state, do not directly invoke each other, and do not call provider APIs.

---

### 4.1 Orchestration Evaluation Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe daily batch trigger for the Orchestration Evaluation Loop (`system_loop.md` §4.1); ensure eligible-student evaluation occurs within Config V2-governed execution windows |
| **Execution cadence** | Governed by Config V2 Group A `outreach_daily_trigger_hour_cst`; no hardcoded timing value (AP-SCH6) |
| **Runtime mode behavior** | LIVE: triggers Orchestration Evaluation Loop with `governance_scope = AUTHORIZED`; SHADOW: triggers loop with `governance_scope = SHADOW_ONLY`; REPLAY: trigger suppressed; MAINTENANCE: trigger suppressed |
| **Replay restrictions** | Batch scheduling trigger suppressed in REPLAY mode; Replay Orchestration Scheduler owns historical simulation (§4.8) |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `config_version_id`, `trigger_window_start`, `trigger_window_end`, `idempotency_key` |
| **Idempotency guarantees** | Trigger idempotency key: `(scheduler_domain = orchestration_evaluation, cycle_date, execution_mode)`; duplicate trigger within same window is a no-op; prior execution record blocks re-trigger |

---

### 4.2 Retry Orchestration Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe retry batch trigger for the Retry Orchestration Loop (`system_loop.md` §4.2); retry scheduling cadence governed by Config V2 Group A retry timing variables |
| **Execution cadence** | Governed by Config V2 Group A `outreach_retry_window_days` and co-trigger timing with Orchestration Evaluation Scheduler; retry timing window is not hardcoded |
| **Runtime mode behavior** | LIVE: triggers Retry Orchestration Loop when retry-eligible students exist per Config V2 timing; SHADOW: triggers loop with SHADOW-only outputs; REPLAY: trigger suppressed; MAINTENANCE: trigger suppressed |
| **Replay restrictions** | Retry batch trigger suppressed in REPLAY mode; historical retry behavior is simulated by the Replay Orchestration Scheduler reading `processed_events` |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `config_version_id`, `retry_eligible_count_at_trigger` |
| **Idempotency guarantees** | Trigger idempotency key: `(scheduler_domain = retry_orchestration, cycle_date, execution_mode)`; retry scheduling trigger per window is a no-op if prior trigger record exists for same window |

---

### 4.3 Escalation Polling Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe polling trigger for the Escalation Polling Loop (`system_loop.md` §4.3); ensures escalation candidacy assessment runs after each Orchestration Evaluation cycle |
| **Execution cadence** | Governed by Config V2 Group I system timing variables; triggered after Orchestration Evaluation Scheduler cycle completion; may also be triggered by retry exhaustion signals |
| **Runtime mode behavior** | LIVE: triggers Escalation Polling Loop with full routing authorization; SHADOW: triggers loop; escalation candidacy assessed, logged, no live routing; REPLAY: trigger carries `REPLAY_ESCALATION_CANDIDATE` scope; MAINTENANCE: suspended |
| **Replay restrictions** | In REPLAY mode, escalation polling produces candidacy records with `REPLAY_ESCALATION_CANDIDATE` scope only; no live escalation routing |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `causation_cycle_id` (linked to Orchestration Evaluation cycle) |
| **Idempotency guarantees** | Trigger idempotency key: `(scheduler_domain = escalation_polling, cycle_date)`; duplicate escalation polling triggers within same window suppressed |

---

### 4.4 AI Refresh Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe AI refresh trigger for the AI Refresh Orchestration Loop (`system_loop.md` §4.4); ensures AI advisories are within TTL before the Orchestration Evaluation cycle requires them |
| **Execution cadence** | Governed by Config V2 Group H `ai_insight_ttl_hours`; AI Refresh Scheduler triggers when students requiring refresh exceed a governance-defined threshold; triggered before Orchestration Evaluation Scheduler for the cycle |
| **Runtime mode behavior** | LIVE: triggers AI Refresh Loop; refresh authorized; advisory outputs tagged with `ai_governance_tier`; SHADOW: triggers loop; advisory outputs tagged `outcome = shadow_only`; REPLAY: live AI inference suppressed; historical content sourced from warehouse; MAINTENANCE: trigger suspended |
| **Replay restrictions** | In REPLAY mode, AI Refresh Scheduler does not invoke live AI inference; FINALIZED_COPY sourced from `warehouse.snapshot_ai_narratives`; non-finalized sourced from `ai_insights` table |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `stale_count_at_trigger`, `missing_count_at_trigger` |
| **Idempotency guarantees** | AI refresh trigger idempotency key: `(scheduler_domain = ai_refresh, cycle_date)`; within-cycle re-triggers are no-ops; per-student refresh idempotency governed by `system_loop.md` §11.5 |

---

### 4.5 Snapshot Finalization Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe finalization trigger for the Snapshot Finalization Loop (`system_loop.md` §4.5); triggered when all validation gates pass for a given `(student_id, snapshot_month)` |
| **Execution cadence** | Event-driven — triggered by snapshot orchestration service signals when validation completes; not time-based; no Config V2 cadence variable applies to this domain's trigger timing |
| **Runtime mode behavior** | LIVE: triggers Snapshot Finalization Loop; finalization proceeds; FINALIZED state and AI physical copy (FAD-1) produced; SHADOW: finalization proceeds normally — finalization is not an outbound action; records tagged `execution_mode` at finalization; REPLAY: no re-triggering of finalization; reads existing finalized records; MAINTENANCE: suspended |
| **Replay restrictions** | In REPLAY mode, Snapshot Finalization Scheduler does not re-trigger finalization; existing finalized snapshot records are the authoritative source |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `student_id` (opaque), `snapshot_month`, `validation_gate_outcome` |
| **Idempotency guarantees** | Finalization trigger idempotency key: `(student_id, snapshot_month)` per `system_loop.md` §11.5; second trigger for same key is a no-op |

---

### 4.6 Report Generation Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe report generation trigger for the Report Generation Loop (`system_loop.md` §4.6); triggered after cohort snapshot finalization completeness gate passes |
| **Execution cadence** | Governance-authorized trigger; cohort finalization completeness gate must pass before report generation schedule fires; not time-based in the simple sense — completeness gate is the precondition |
| **Runtime mode behavior** | LIVE: triggers Report Generation Loop; report generated and published; SHADOW: generation proceeds; publication may be operator-suppressed; REGENERATION: triggers loop in regeneration mode; reads warehouse exclusively (FAD-2); no AI calls, no SQL Server reads; MAINTENANCE: suspended |
| **Replay restrictions** | In REGENERATION mode, report scheduling reads `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` exclusively; no external API calls; output must be identical for identical inputs (FAD-2) |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `cohort_id`, `report_month`, `completeness_gate_outcome` |
| **Idempotency guarantees** | Report generation trigger idempotency key: `(cohort_id, report_month, lineage_version)` per `system_loop.md` §11.5; duplicate publication for same key creates `POTENTIALLY_DIVERGENT` annotation |

---

### 4.7 Provider Synchronization Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe synchronization trigger for the Provider Synchronization Loop (`system_loop.md` §4.7); ensures SQL Server → PostgreSQL sync completes before Orchestration Evaluation Scheduler fires |
| **Execution cadence** | Governed by Config V2 Group I system timing variables; must complete before Orchestration Evaluation Scheduler cycle begins; sync lag assessed against Config V2 Group K `sql_server_max_sync_age_hours` |
| **Runtime mode behavior** | LIVE/SHADOW: sync proceeds in all non-MAINTENANCE modes; SQL Server is read-only; REPLAY: no SQL Server re-sync; stored `student_trigger_data` snapshot used; MAINTENANCE: suspended |
| **Replay restrictions** | In REPLAY mode, Provider Synchronization Scheduler does not re-sync from SQL Server; `sync_lag_hours` annotation preserved in replay context from original cycle records |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `expected_completion_before_cycle_id`, `sql_server_connection_outcome`, `sync_lag_hours` |
| **Idempotency guarantees** | SQL Server sync is always idempotent (upsert by `user_id`); re-running produces same PostgreSQL state as SQL Server source at time of run |

---

### 4.8 Replay Orchestration Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe replay trigger for the Replay Orchestration Loop (`system_loop.md` §4.8); operator-initiated and compliance-initiated only; produces SHADOW-only diagnostic outputs |
| **Execution cadence** | Operator-initiated or compliance-initiated; no automated cadence; governance authorization required; `source_artifact_id` and `historical_config_version_id` required as trigger inputs |
| **Runtime mode behavior** | REPLAY: Replay Orchestration Scheduler active; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; LIVE/SHADOW: replay may be triggered as a concurrent diagnostic cycle without disrupting batch scheduling; MAINTENANCE: permitted if purely diagnostic and warehouse not under migration |
| **Replay restrictions** | Replay Orchestration Scheduler is always SHADOW-only regardless of system execution mode (AP-RT2, AP-SCH3); replay triggers may never produce LIVE effects |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `operator_identity`, `source_artifact_id`, `historical_config_version_id`, `governance_authorization_record_id` |
| **Idempotency guarantees** | Replay trigger idempotency key: `(source_artifact_id, replay_cycle_id)`; duplicate replay triggers for same key are suppressed |

---

### 4.9 Compliance Orchestration Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate governance-safe compliance workflow trigger for the Compliance Orchestration Loop (`system_loop.md` §4.9); compliance authority operator-initiated only |
| **Execution cadence** | Compliance Operator-initiated; no automated cadence; compliance workflow authorization and pre-action audit entry required before trigger fires (spec/04 §19.4) |
| **Runtime mode behavior** | LIVE: compliance actions execute under compliance pathway service account; SHADOW: compliance workflow intake and authorization proceed; execution deferred; MAINTENANCE: suspended |
| **Replay restrictions** | Compliance execution is not replayed; compliance audit records are read in replay for historical explainability only; Compliance Orchestration Scheduler does not fire in REPLAY mode |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `compliance_actor_identity`, `action_type`, `pre_action_audit_entry_id`, `authorization_timestamp` |
| **Idempotency guarantees** | Compliance trigger idempotency key: `(student_id, action_type, scope_manifest_id)` per spec/04 §19.1; duplicate compliance request for same key is blocked |

---

### 4.10 Observability Heartbeat Scheduler

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate periodic health record emission trigger for the Observability Heartbeat Loop (`system_loop.md` §4.10); runs independently of outreach orchestration cycles |
| **Execution cadence** | Governed by Config V2 Group I system timing variables; runs on a fixed cadence independent of batch scheduling; cadence value is not hardcoded (AP-SCH6) |
| **Runtime mode behavior** | All modes: Observability Heartbeat Scheduler triggers in all execution modes including MAINTENANCE and REPLAY; observability heartbeat is mode-independent |
| **Replay restrictions** | Heartbeat Scheduler does not replay; historical heartbeat records are queryable for diagnostic purposes only |
| **Observability requirements** | Structured trigger record: `scheduler_domain`, `cycle_id`, `triggered_at`, `execution_mode`, `config_version_id`, `heartbeat_sequence_number` |
| **Idempotency guarantees** | Heartbeat records are append-only; idempotency not required for heartbeat triggers |

---

## 5. ORCHESTRATION WINDOW GOVERNANCE

---

### 5.1 Orchestration Window Definition

An **orchestration window** is the governance-defined execution period within which a scheduler domain may produce at most one cycle trigger. Orchestration windows are:

* Defined by the Config V2 trigger cadence for the scheduler domain
* Identified by a `(scheduler_domain, cycle_date, execution_mode)` tuple
* Protected by an idempotency gate that prevents duplicate triggers within the same window
* Closed when the triggered orchestration loop emits its completion record

A window is considered **open** from the time a trigger fires until the triggered loop emits its `loop_cycle_complete` record. An open window may not be re-triggered (AP-SCH4).

---

### 5.2 Runtime-Cycle Ownership

Every scheduler trigger produces one runtime cycle. That cycle is uniquely identified by the combination of:

* `cycle_id` — generated by the scheduler domain at trigger time
* `scheduler_domain` — the domain that owns this cycle
* `correlation_id` — generated by the orchestration loop when it begins evaluation

Ownership rules:

* A scheduler domain owns the timing coordination of a cycle
* The orchestration loop owns the evaluation authority within the cycle
* No other scheduler domain may claim ownership of a cycle it did not trigger
* Orphaned cycles (correlation_id generated, no completion record emitted) are specification violations (AP-SCH12)

---

### 5.3 Replay-Safe Locking

Replay-triggered cycles must not interfere with LIVE batch cycles:

* Replay Orchestration Scheduler triggers produce cycles with `execution_type = replay`; these cycles operate in a separate execution context from LIVE batch cycles
* A LIVE batch window and a replay cycle may run concurrently; they do not share mutable state
* Replay cycles may not acquire write locks that block LIVE cycle progress (AP-SCH3)
* Replay trigger records carry `governance_scope = REPLAY_ONLY`; they do not satisfy the idempotency gate for LIVE cycle windows

---

### 5.4 Distributed Scheduling Considerations

In distributed deployments:

* Distributed lock coordination uses an idempotency record in `processed_events` or a designated scheduling lock table as the canonical authority; advisory in-memory locks are not sufficient
* The idempotency gate for a scheduler domain checks for an existing execution record before acquiring a lock; the record is the lock
* If two scheduler processes attempt to trigger the same `(scheduler_domain, cycle_date, execution_mode)` window simultaneously, one succeeds in creating the idempotency record (INSERT wins); the other reads the existing record and treats the trigger as a no-op
* Clock skew between distributed scheduler processes is governed by Config V2 Group I timing tolerance variables; no hardcoded tolerance value is permitted (AP-SCH6)

---

### 5.5 Orphaned-Cycle Prevention

An orphaned cycle is a cycle where the scheduler trigger fired, a `cycle_id` was generated and recorded, but no completion record was ever emitted from the triggered orchestration loop.

Governance requirements:

* Every scheduler trigger record must be linked to a loop completion record; a trigger without a completion record after the governance-defined window is an orphan candidate
* Orphan detection runs as part of the Observability Heartbeat Loop (§4.10); any `cycle_id` without a linked `loop_cycle_complete` record beyond the timeout threshold produces a `CYCLE_ORPHAN_DETECTED` alert
* Orphaned cycles are not silently discarded; they are documented in a dead-letter record for manual triage
* Recovery cycles (§8.2) initiated for orphaned cycles carry `execution_type = recovery` and `orphaned_cycle_id` attribution

---

### 5.6 Stale-Lock Governance

If an orchestration window idempotency record exists but the corresponding loop completion record never arrived:

* The window is considered **locked-stale** after the governance-defined timeout governed by Config V2 Group I timing variables
* A locked-stale window may be force-unlocked only by an Operational Administrator with an explicit audit record
* Force-unlock produces a structured log entry: `STALE_LOCK_FORCE_UNLOCKED`, `scheduler_domain`, `cycle_id`, `lock_age_seconds`, `operator_identity`
* After force-unlock, the scheduler domain is eligible to trigger a recovery cycle for the missed window (§8.3)
* No automation may silently expire a stale lock without producing an observable record (AP-SCH9)

---

### 5.7 Deterministic Recovery Semantics

Recovery cycles are triggered when a scheduler domain detects that a governed execution window was missed or produced an orphaned cycle:

* Recovery cycle carries `execution_type = recovery`; it is identifiable and distinguishable from original cycles in all records
* Recovery cycle idempotency key matches the missed cycle: `(scheduler_domain, cycle_date, execution_mode)`; if the original cycle partially succeeded, the recovery cycle produces no duplicate records for already-processed students (idempotency gate in `processed_events`)
* Recovery cycle attribution includes: `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`, `orphaned_cycle_id` if applicable
* Recovery cycles require Operational Administrator authorization before running unless the governance model authorizes automated recovery (UE-SCH2 — open concern)

---

## 6. CONFIG V2 SCHEDULING GOVERNANCE

---

### 6.1 Config V2 Scheduler Timing Variables

All scheduler timing values are governed by Config V2. No scheduler domain embeds a hardcoded timing value.

| Timing parameter | Config V2 variable | Group | Classification |
|---|---|---|---|
| Daily outreach trigger hour (CST) | `outreach_daily_trigger_hour_cst` | A | OPERATIONAL_TUNING |
| Retry evaluation co-trigger timing | `outreach_retry_window_days` | A | OPERATIONAL_TUNING |
| AI refresh trigger threshold | `ai_insight_ttl_hours` | H | AI_GOVERNANCE |
| Provider sync cadence | (Group I system timing variable) | I | SYSTEM_TIMING |
| Observability heartbeat cadence | (Group I system timing variable) | I | SYSTEM_TIMING |
| Sync lag alert threshold | `sql_server_max_sync_age_hours` | K | DATA_FRESHNESS |
| Stale lock timeout | (Group I system timing variable) | I | SYSTEM_TIMING |
| Distributed clock skew tolerance | (Group I system timing variable) | I | SYSTEM_TIMING |
| Orphan detection window | (Group I system timing variable) | I | SYSTEM_TIMING |
| Recovery cycle authorization window | (Group I system timing variable) | I | SYSTEM_TIMING |

---

### 6.2 Config V2 Threshold Resolution Behavior

When any Config V2 scheduler timing variable is missing from the ACTIVE config version:

* `UNKNOWN_V0` is substituted for the missing variable
* `CONFIG_THRESHOLD_MISSING_{KEY}` warning is emitted in the scheduler trigger record
* The scheduler domain does not fire a trigger using a hardcoded fallback value (AP-SCH6)
* The scheduler domain enters a `SCHEDULER_DEGRADED` state for the affected domain and emits a `SCHEDULER_DEGRADED` structured log entry
* The `SCHEDULER_DEGRADED` state generates an escalation candidacy signal for operator awareness
* No silent skip behavior is permitted when Config V2 timing is unavailable

---

## 7. REPLAY & REGENERATION SCHEDULING

---

### 7.1 Replay Scheduling Semantics

A replay cycle is triggered by the Replay Orchestration Scheduler (§4.8) with operator or compliance authorization. The scheduling semantics are:

```
GOVERNANCE AUTHORIZATION REQUEST
  ↓
AUTHORIZATION RECORD WRITTEN (replay_authorization_id)
  ↓
REPLAY SCHEDULER TRIGGER (source_artifact_id + historical_config_version_id as inputs)
  ↓
CYCLE_ID GENERATED (replay context)
  ↓
REPLAY ORCHESTRATION LOOP TRIGGERED (system_loop.md §4.8)
  ↓
SHADOW-ONLY OUTPUTS PRODUCED (governance_scope = REPLAY_ONLY)
  ↓
REPLAY DIAGNOSTIC RECORD EMITTED
  ↓
NO LIVE EFFECTS PRODUCED
```

---

### 7.2 Regeneration Scheduling Semantics

Report regeneration is triggered by the Report Generation Scheduler (§4.6) in REGENERATION mode. Regeneration and replay are architecturally distinct:

| Characteristic | Replay scheduling | Regeneration scheduling |
|---|---|---|
| Trigger | Replay Orchestration Scheduler (§4.8) | Report Generation Scheduler (§4.6) in REGENERATION mode |
| Authorization | Operator or compliance-initiated; governance auth record required | Operator-initiated; report lineage governance required |
| Input requirement | `source_artifact_id` + `historical_config_version_id` | `cohort_id` + `report_month` + `lineage_version` |
| Purpose | Simulate historical orchestration decisions | Re-render historical report from immutable snapshot |
| Source data | Historical state + historical config | `warehouse.student_snapshots` + `warehouse.snapshot_ai_narratives` exclusively (FAD-2) |
| External calls | None | None — absolute prohibition |
| Warehouse mutation | None | None |

---

### 7.3 Historical Scheduling Replay

When replay scheduling is active, the scheduler resolves the historically-accurate trigger timing:

* The `historical_config_version_id` is used to resolve what the `outreach_daily_trigger_hour_cst` value was at the time of the original cycle
* If the historical trigger timing cannot be resolved from the config version record, the replay cycle is annotated `replay_partial = true` with `HISTORY_INCOMPLETE` on the timing field
* The resolved historical trigger time is emitted in the replay diagnostic record for explainability
* Historical scheduling replay does not re-trigger any live scheduling domain

---

### 7.4 Replay Suppression Rules

The following scheduling behaviors are suppressed in all replay contexts:

| Suppressed behavior | Suppression mechanism | Reference |
|---|---|---|
| Batch outreach trigger | Orchestration Evaluation Scheduler suppressed in REPLAY mode | AP-SCH3 |
| Retry batch trigger | Retry Orchestration Scheduler suppressed in REPLAY mode | AP-SCH3 |
| Live AI refresh trigger | AI Refresh Scheduler does not invoke live inference in REPLAY | AP-AI5; system_loop.md §7.2 |
| Live provider sync trigger | Provider Synchronization Scheduler reads stored snapshot data in REPLAY | system_loop.md §4.8 |
| Compliance workflow execution | Compliance Orchestration Scheduler does not fire in REPLAY | agent_ownership_matrix.md §6 |
| SHADOW-to-LIVE mode transition | No scheduler trigger may produce a mode transition | AP-SCH2 |

---

### 7.5 Replay Observability

Every replay cycle triggered by the Replay Orchestration Scheduler emits the full diagnostic record:

| Field | Required |
|---|---|
| `scheduler_domain` | `replay_orchestration` |
| `cycle_id` | UUID v4 generated at trigger |
| `triggered_at` | ISO-8601 trigger timestamp |
| `operator_identity` | Identity of the operator who initiated replay |
| `governance_authorization_record_id` | Record of the replay authorization |
| `source_artifact_id` | The artifact being replayed |
| `historical_config_version_id` | Config version resolved for the replay |
| `historical_trigger_time_resolved` | Resolved historical trigger timing (or `HISTORY_INCOMPLETE`) |
| `replay_partial` | True if any timing or threshold was `UNKNOWN_V0` |
| `replay_suppression_applied` | All suppression categories active during this replay trigger |

---

## 8. RECOVERY & DEGRADATION GOVERNANCE

---

### 8.1 Deterministic Recovery Principles

Recovery scheduling is observable, attributable, and deterministic. Every recovery cycle must satisfy:

1. **Attributable** — recovery cycles carry `execution_type = recovery`; `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by` are required in all records
2. **Non-duplicating** — recovery cycles check `processed_events` idempotency records from the original missed window; previously-processed students are skipped
3. **Observable** — recovery cycles emit the same structured completion records as original cycles; a recovery cycle that completes without emitting a completion record is a specification violation
4. **Governance-gated** — recovery cycles require Operational Administrator authorization unless Config V2-governed automated recovery is explicitly defined (UE-SCH2)
5. **Non-silent** — there is no such thing as a hidden recovery execution; every recovery trigger and completion is a first-class observable event (AP-SCH10)

---

### 8.2 Recovery Condition Table

| Recovery trigger | Detection mechanism | Recovery cycle behavior | Authorization required | Observability |
|---|---|---|---|---|
| Scheduler crash (process-level) | No trigger record emitted within Config V2-governed window | Orphan detection flags missed window; recovery cycle triggered with `execution_type = recovery` | Yes — Operational Administrator | `SCHEDULER_CRASH_DETECTED` event; recovery trigger record; recovery completion record |
| Partial orchestration execution | Trigger record exists; loop completion record absent after timeout | Orphan detection flags cycle; recovery cycle uses same idempotency keys; already-processed students skipped | Yes | `PARTIAL_EXECUTION_DETECTED` event; `orphaned_cycle_id` annotation |
| Provider outage during scheduling | `governance_scope = UNAVAILABLE` on outbound dispatch | No recovery cycle needed for scheduling itself; orchestration continues without dispatch; escalation candidacy generated | No | `PROVIDER_OUTAGE` event; degradation onset record |
| AI provider outage during scheduling | AI refresh trigger suppressed | No recovery cycle; next scheduled AI refresh trigger resumes when AI provider available | No | `AI_PROVIDER_UNAVAILABLE` event; stale AI annotation on next cycle |
| Distributed timing drift | Scheduler instances disagree on current window | First INSERT to idempotency record wins; all other instances treat trigger as no-op; no duplicate cycle | No — idempotency gate resolves | `DISTRIBUTED_TIMING_DRIFT_DETECTED` event if drift exceeds Config V2 Group I tolerance |
| Sync backlog at trigger time | `sync_lag_hours > sql_server_max_sync_age_hours` | Orchestration cycle proceeds with `STALE_SQL_SERVER_DATA` annotation; no recovery cycle for scheduling itself | No | `SYNC_LAG_EXCEEDED` event; annotation in all cycle records |
| Degraded mode entry | Provider or AI outage detection | Affected scheduler domains annotate triggers DEGRADED; available domains continue; recovery cycle triggered when degraded condition resolves | No — automatic | `SCHEDULER_DEGRADED` event per domain; `SCHEDULER_RECOVERY` event on resolution |

---

### 8.3 Recovery Attribution

All recovery cycles must carry the following attribution fields in addition to standard cycle attribution:

| Field | Required value |
|---|---|
| `execution_type` | `recovery` |
| `recovery_of_cycle_date` | ISO-8601 date of the missed window |
| `lag_detected_at` | ISO-8601 timestamp when lag or orphan was detected |
| `recovery_initiated_by` | Operator identity or `system_orphan_detector` |
| `orphaned_cycle_id` | `cycle_id` of the orphaned or missed cycle, if available |
| `recovery_authorization_record_id` | Reference to operator authorization record |

Recovery cycles may not omit these fields. A recovery cycle without full attribution is a specification violation (AP-SCH11).

---

### 8.4 Degradation Governance for Scheduler Domains

When a scheduler domain enters a degraded state:

* The domain emits a `SCHEDULER_DEGRADED` structured log entry with: `scheduler_domain`, `degradation_cause`, `first_affected_window`, `degradation_onset_timestamp`
* The domain does not silently skip trigger cycles; if a trigger cannot be safely fired, it is documented as a `TRIGGER_SUPPRESSED` record with `suppression_reason`
* An escalation candidacy signal is generated for any scheduler domain that remains degraded beyond the Config V2 Group I governance-defined threshold
* When the degradation condition resolves, the domain emits a `SCHEDULER_RECOVERY` structured log and resumes normal trigger behavior
* Recovery from degradation does not automatically trigger missed windows; missed windows require explicit Operational Administrator authorization for recovery cycles (UE-SCH2)

---

## 9. ATTRIBUTION & OBSERVABILITY

---

### 9.1 Scheduler Attribution Lineage

The full attribution chain from scheduling trigger to provider delivery:

```
Config V2 trigger timing  →  outreach_daily_trigger_hour_cst (Group A)
  ↓
Scheduler Trigger  →  cycle_id + triggered_at + scheduler_domain
  ↓
Orchestration Loop  →  correlation_id + config_version_id + execution_mode
  ↓
OrchestrationIntent  →  intent_id + causation_id + correlation_id
  ↓
ProviderOrchestrationAssessment  →  governance_scope + correlation_id
  ↓
processed_events  →  idempotency_key + correlation_id
  ↓
ghl_messages  →  ghl_message_id + correlation_id
```

Every step in this chain is traceable from the initial scheduler trigger. A failure at any step that cannot be traced back to its `cycle_id` is an observability defect.

---

### 9.2 Orchestration-Cycle Correlation

The `cycle_id` generated by the scheduler domain serves as the session context that links:

* The scheduler trigger record
* The runtime orchestration loop's `correlation_id` (the loop generates its own `correlation_id`; the `cycle_id` is passed as session context)
* All orchestration records within the cycle

The linkage between `cycle_id` (scheduler) and `correlation_id` (loop) must be persisted in the loop's start record. A loop that does not record its `cycle_id` session context is unattributable to its scheduler trigger.

---

### 9.3 Runtime Traceability Requirements

| Traceability requirement | Implementation |
|---|---|
| Scheduler trigger to loop start | `cycle_id` in loop start record |
| Loop start to intent production | `correlation_id` in all `OrchestrationIntent` records |
| Intent production to execution | `correlation_id` in `processed_events` |
| Execution to provider delivery | `correlation_id` in `ghl_messages` |
| Recovery cycle to original missed window | `orphaned_cycle_id` in recovery trigger record |
| Replay cycle to governance authorization | `governance_authorization_record_id` in replay trigger record |
| Degradation event to escalation | `degradation_onset_timestamp` + escalation candidacy record |

If any link in this chain is missing, the orchestration event is not fully traceable and represents an observability defect (spec/06).

---

### 9.4 Required Scheduler Observability Fields

Every scheduler domain trigger emits a structured JSON record at trigger time:

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "scheduler_orchestration",
  "event": "scheduler_trigger_fired",
  "scheduler_domain": "string",
  "cycle_id": "uuid",
  "triggered_at": "ISO-8601",
  "execution_mode": "SHADOW | LIVE | REPLAY | REGENERATION | DEGRADED | MAINTENANCE",
  "config_version_id": "string | null",
  "trigger_window_start": "ISO-8601",
  "trigger_window_end": "ISO-8601",
  "idempotency_key": "string",
  "idempotency_check_outcome": "new | duplicate_suppressed",
  "trigger_outcome": "fired | suppressed_duplicate | suppressed_mode | suppressed_degraded | suppressed_maintenance",
  "degradation_flags": [],
  "config_threshold_missing_keys": []
}
```

Additionally, every scheduler domain emits a completion record when the triggered loop returns its completion event:

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "scheduler_orchestration",
  "event": "scheduler_cycle_complete",
  "scheduler_domain": "string",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "string",
  "execution_type": "original | recovery | replay | regeneration",
  "trigger_to_completion_ms": 0,
  "loop_outcome": "success | failure | partial | shadow_only",
  "orphan_detected": false
}
```

PII (student name, email, phone) must not appear in scheduler observability records (AP-SCH13).

---

## 10. AUTHORITY BOUNDARIES

---

### 10.1 Scheduler Authority Definition

Scheduler domains hold **orchestration timing authority only**. The boundaries are:

| Authority type | Held by schedulers | Not held by schedulers |
|---|---|---|
| Trigger timing coordination | Yes — governed by Config V2 | No — hardcoded timing values are prohibited |
| Cycle attribution initiation | Yes — `cycle_id` generated at trigger | No — `correlation_id` generated within the loop |
| Mode check (before trigger) | Yes — all domains check execution mode | No — mode transitions are Governance Administrator authority |
| Idempotency gate check | Yes — before each trigger | No — student-level idempotency governed within loops |
| Governance definition | No — Config V2 owns timing governance | N/A |
| Eligibility evaluation | No — directives own this | N/A |
| Provider API calls | No — provider layer owns this | N/A |
| State transitions | No — state management service owns this | N/A |
| AI inference | No — AI advisory service owns this | N/A |

---

### 10.2 Replay Scheduler Authority Restrictions

The Replay Orchestration Scheduler (§4.8) holds the most restricted authority profile:

* May only trigger cycles with `governance_scope = REPLAY_ONLY`
* May never produce a cycle that results in LIVE outbound dispatch (AP-SCH3)
* May not acquire a LIVE window idempotency key — replay triggers use a separate namespace `(source_artifact_id, replay_cycle_id)`
* May not trigger a mode transition from SHADOW to LIVE
* May not write to `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives` (AP-SCH8)
* May not initiate compliance workflow execution
* Authorization record from a Governance Administrator or Compliance Operator is required before a replay trigger fires

---

### 10.3 Provider Authority Boundaries at Scheduling Layer

Scheduler domains are explicitly prohibited from:

* Constructing GHL API payloads
* Constructing SMS, email, or meeting booking requests
* Calling any external API (GHL, AI provider, SQL Server at runtime — SQL Server reads are within the Provider Synchronization domain's execution scope, not the scheduler's)
* Accessing student PII for scheduling decisions (student counts at aggregate level are permitted in observability records; individual student data is never accessed at the scheduling layer)

Provider authority remains with the provider orchestration services governed by `directives/ghl_integration_contract.md`. Scheduler domains coordinate timing only.

---

### 10.4 AI Authority at Scheduling Layer

AI advisory outputs are consumed by runtime orchestration loops, not by scheduler domains. At the scheduling layer:

* The AI Refresh Scheduler (§4.4) coordinates the timing of AI refresh requests; it does not evaluate AI outputs
* No scheduler domain may interpret an AI advisory output to make scheduling decisions
* No scheduler domain may produce an `OrchestrationIntent` — intent production is within the orchestration loop boundary
* No scheduler domain may modify the `ai_insight_ttl_hours` threshold from Config V2 based on AI advisory output; the threshold is Config V2-governed and AI-immutable at the scheduling layer

---

## 11. ARCHITECTURE PRESERVATION RULES

---

The following rules are MUST NOT prohibitions. Violation of any rule is a specification defect.

| Rule | Prohibition |
|---|---|
| **AP-SCH1** | MUST NOT allow any scheduler domain to evaluate student eligibility, access student trigger data, or produce orchestration intents; scheduler domains coordinate timing, not evaluation |
| **AP-SCH2** | MUST NOT allow any scheduler domain to trigger or coordinate a mode transition from SHADOW to LIVE; SHADOW-to-LIVE transition requires Governance Administrator authorization and a config version activation record |
| **AP-SCH3** | MUST NOT allow the Replay Orchestration Scheduler to produce LIVE effects or acquire a LIVE window idempotency key; all replay triggers carry `governance_scope = REPLAY_ONLY`; live dispatch and live state transitions in replay context are specification violations |
| **AP-SCH4** | MUST NOT allow duplicate LIVE scheduling triggers for the same `(scheduler_domain, cycle_date, execution_mode)` window; the idempotency gate must fire before any trigger is emitted; a duplicate window trigger is a no-op, not a second cycle |
| **AP-SCH5** | MUST NOT allow any scheduler domain to silently skip a trigger window; all trigger suppressions must produce a `TRIGGER_SUPPRESSED` structured record with `suppression_reason`; no silent skips |
| **AP-SCH6** | MUST NOT allow any scheduler domain to embed a hardcoded timing value (trigger hour, retry interval, concurrency limit, heartbeat cadence, or window duration); all timing values are governed by Config V2 Group A, H, I, or K variables; `UNKNOWN_V0` substituted for missing keys; no silent default assumptions |
| **AP-SCH7** | MUST NOT allow a recovery cycle to be triggered without full attribution fields (`execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`); unattributed recovery cycles are specification violations |
| **AP-SCH8** | MUST NOT allow any scheduler domain (including the Replay Orchestration Scheduler) to write to `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, or `compliance_audit` schema; warehouse writes are within the designated service account paths only (AP-OWN15) |
| **AP-SCH9** | MUST NOT allow stale orchestration window locks to be silently expired; stale lock force-unlock requires Operational Administrator authorization with an audit record; automated silent expiry is prohibited |
| **AP-SCH10** | MUST NOT allow hidden recovery execution; every recovery cycle trigger and every recovery cycle completion is a first-class observable event; recovery cycles that execute without producing scheduler trigger and completion records are specification violations |
| **AP-SCH11** | MUST NOT allow a recovery cycle to omit recovery attribution fields; specifically `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by` are mandatory; omission makes the recovery cycle forensically unresolvable |
| **AP-SCH12** | MUST NOT allow an orphaned scheduler cycle — a cycle where `cycle_id` was generated and the trigger record was written but no loop completion record was ever linked; orphaned cycles must be detected by the Observability Heartbeat Loop and documented in a dead-letter record |
| **AP-SCH13** | MUST NOT log raw PII (student name, email, phone, transcript content, payment details) in scheduler observability records; aggregate counts and opaque `cycle_id` / `scheduler_domain` fields only |
| **AP-SCH14** | MUST NOT allow any scheduler domain to fire in MAINTENANCE mode unless explicitly authorized as a governance-approved maintenance trigger (config promotion, diagnostic read); all outreach orchestration scheduling is suspended in MAINTENANCE mode |
| **AP-SCH15** | MUST NOT allow any scheduler domain to re-implement the governance precondition gate defined in `runtime/system_loop.md` §5.2; the precondition gate is owned by the orchestration loop; the scheduler's responsibility is to pass the `cycle_id` and `config_version_id` as session context so the loop can execute the gate |

---

## 12. ACCEPTANCE CRITERIA

---

### AC-SCH1 — Config V2-Governed Trigger Timing

**Given** `outreach_daily_trigger_hour_cst` is present in the ACTIVE config version  
**When** the Orchestration Evaluation Scheduler evaluates whether a trigger is due  
**Then** the trigger timing is resolved from the Config V2 variable; no hardcoded hour is used; the `config_version_id` is recorded in the trigger record

---

### AC-SCH2 — Missing Config V2 Timing Variable

**Given** `outreach_daily_trigger_hour_cst` is absent from the ACTIVE config version  
**When** the Orchestration Evaluation Scheduler evaluates whether a trigger is due  
**Then** `UNKNOWN_V0` is substituted; `CONFIG_THRESHOLD_MISSING_outreach_daily_trigger_hour_cst` warning is emitted; the scheduler domain enters `SCHEDULER_DEGRADED` state; no trigger fires using a hardcoded fallback; an escalation candidacy signal is generated

---

### AC-SCH3 — Duplicate Window Prevention

**Given** the Orchestration Evaluation Scheduler has already fired for `(orchestration_evaluation, 2026-06-01, LIVE)`  
**When** the scheduler evaluates again within the same window  
**Then** the idempotency gate reads the existing trigger record; the duplicate trigger is suppressed; a `TRIGGER_SUPPRESSED` record is emitted with `suppression_reason = DUPLICATE_WINDOW`; no second cycle is triggered

---

### AC-SCH4 — Replay Scheduler LIVE Suppression

**Given** `execution_mode = LIVE` and the Replay Orchestration Scheduler is triggered with a valid `source_artifact_id`  
**When** the replay cycle executes  
**Then** all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; no LIVE outbound dispatch is delegated; no LIVE window idempotency key is acquired; the replay trigger record is emitted with `replay_suppression_applied` documented

---

### AC-SCH5 — SHADOW Mode Enforcement

**Given** `execution_mode = SHADOW`  
**When** the Orchestration Evaluation Scheduler triggers a cycle  
**Then** the triggered loop receives `governance_scope = SHADOW_ONLY`; all outputs are tagged `outcome = shadow_only`; no LIVE dispatch is delegated; the trigger record shows `execution_mode = SHADOW`

---

### AC-SCH6 — Recovery Cycle Attribution

**Given** the Observability Heartbeat Loop detects an orphaned cycle with `cycle_id = ABC123`  
**When** a recovery cycle is triggered  
**Then** the recovery cycle trigger record includes `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `orphaned_cycle_id = ABC123`, `recovery_initiated_by`; no recovery cycle fires without these fields

---

### AC-SCH7 — Stale Lock Governance

**Given** an orchestration window lock has been open longer than the Config V2 Group I stale-lock timeout  
**When** the Observability Heartbeat Loop detects the stale lock  
**Then** a `STALE_LOCK_DETECTED` structured log is emitted; no automated silent expiry occurs; an escalation candidacy signal is generated; force-unlock requires Operational Administrator authorization with an audit record

---

### AC-SCH8 — Scheduler Attribution Lineage

**Given** a scheduler trigger fires for the Orchestration Evaluation domain  
**When** the triggered cycle completes  
**Then** the scheduler completion record includes both `cycle_id` (from scheduler trigger) and `correlation_id` (from the loop); the link between scheduler trigger and loop evaluation is present in the completion record; all downstream records (intents, processed_events, ghl_messages) carry the `correlation_id`

---

### AC-SCH9 — Maintenance Mode Suspension

**Given** `execution_mode = MAINTENANCE`  
**When** the Orchestration Evaluation Scheduler evaluates whether a trigger is due  
**Then** the trigger is suppressed; a `TRIGGER_SUPPRESSED` record is emitted with `suppression_reason = MAINTENANCE_MODE`; no cycle is triggered; the Observability Heartbeat Scheduler continues to trigger as an exception

---

### AC-SCH10 — Degradation Observability

**Given** the AI provider becomes unavailable during active operation  
**When** the AI Refresh Scheduler evaluates whether to fire  
**Then** the AI Refresh domain emits a `SCHEDULER_DEGRADED` record with `degradation_cause = AI_PROVIDER_UNAVAILABLE`; the trigger is suppressed for this domain; all other scheduler domains continue normally; an escalation candidacy signal is generated; when the AI provider recovers, a `SCHEDULER_RECOVERY` record is emitted

---

### AC-SCH11 — Regeneration External Call Prohibition

**Given** the Report Generation Scheduler fires in REGENERATION mode  
**When** the triggered Report Generation Loop executes  
**Then** no SQL Server read occurs; no AI provider call is made; no GHL API call is made; report content is derived exclusively from warehouse data; the scheduler completion record shows `execution_type = regeneration`; the report is identical for identical inputs (FAD-2)

---

### AC-SCH12 — Orphaned Cycle Detection

**Given** a scheduler trigger fired for `cycle_id = XYZ789`  
**When** no loop completion record is received within the Config V2 Group I orphan detection window  
**Then** the Observability Heartbeat Loop emits `CYCLE_ORPHAN_DETECTED` with `orphaned_cycle_id = XYZ789`; a dead-letter record is written for the orphaned cycle; an escalation candidacy signal is generated; no silent discard occurs

---

## 13. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Orchestration Evaluation Scheduler (§4.1) and Provider Synchronization Scheduler (§4.7) active
* Retry Orchestration Scheduler: deferred — single attempt per student per cycle
* Escalation Polling Scheduler: escalation candidacy assessed and logged; live routing deferred
* AI Refresh Scheduler: deferred; rule-based evaluation only
* Snapshot Finalization Scheduler: deferred
* Report Generation Scheduler: deferred
* Replay Orchestration Scheduler: deferred
* Compliance Orchestration Scheduler: deferred
* Observability Heartbeat Scheduler: minimal — trigger and completion records only
* SHADOW mode enforcement on all scheduler domains
* Config V2 Group A trigger timing required; remaining groups deferred
* No hardcoded timing values even in MVP; Config V2 Group A must be seeded before any scheduler domain fires

---

### STANDARD

* Orchestration Evaluation Scheduler, Retry Orchestration Scheduler, Escalation Polling Scheduler, AI Refresh Scheduler, Provider Synchronization Scheduler active
* Snapshot Finalization Scheduler active
* Report Generation Scheduler: generation trigger active; publication governance deferred to PRODUCTION
* Replay Orchestration Scheduler: diagnostic mode; operator-initiated only
* Compliance Orchestration Scheduler: intake and authorization active; execution trigger deferred
* Observability Heartbeat Scheduler: full health record emission active
* All 10 Config V2 timing groups active
* Full idempotency enforcement across all active scheduler domains
* Orphaned-cycle detection active via Observability Heartbeat Scheduler

---

### PRODUCTION

* All 10 canonical scheduler domains active
* Full governance precondition enforcement delegated to orchestration loops
* Compliance Orchestration Scheduler execution trigger active (pre-action audit entry hard gate enforced)
* Recovery cycle governance active per §8.3; Operational Administrator authorization required
* Full distributed scheduling coordination via idempotency record arbitration
* Config V2 threshold monitoring active; `SCHEDULER_DEGRADED` alerts propagated to escalation routing
* Full attribution lineage chain verified end-to-end: scheduler trigger → correlation_id → ghl_message_id

---

## 14. UNRESOLVED CONCERNS

---

### UE-SCH1 — Inter-Domain Scheduling Conflict Resolution (OPERATIONAL DECISION)

**Problem:** When multiple scheduler domains are eligible to trigger in the same time window (e.g., Provider Synchronization Scheduler, AI Refresh Scheduler, and Orchestration Evaluation Scheduler all targeting the same execution window), no sequencing arbitration protocol is defined.

**Impact:** If all three domains trigger simultaneously in a constrained environment, the Orchestration Evaluation Loop may begin before the sync and AI refresh are complete, producing stale-data or stale-AI annotations that could have been avoided.

**Classification:** Operational decision. Requires defining inter-domain trigger sequencing: whether Provider Synchronization and AI Refresh must emit completion signals before Orchestration Evaluation Scheduler fires, and whether this sequencing is Config V2-governed or hard-coded as a scheduling invariant.

---

### UE-SCH2 — Recovery Cycle Automated vs Manual Authorization (GOVERNANCE DECISION)

**Problem:** §8.2 states that recovery cycles require Operational Administrator authorization, but the governance protocol for when recovery cycles may proceed automatically has not been finalized.

**Impact:** A scheduler crash in the early morning that is detected at 6:05 AM may need a recovery cycle fired before the next day's window; requiring manual authorization introduces delay that could affect outreach for an entire cohort.

**Classification:** Governance decision. Mirrors UE-RT2 from `runtime/system_loop.md`. Resolution must define: which recovery scenarios allow automated recovery without manual authorization, what Config V2 variables govern the automated-recovery window, and what audit record is required when automated recovery proceeds.

---

### UE-SCH3 — Distributed Scheduler Lock Coordination Mechanism (OPERATIONAL DECISION)

**Problem:** §5.4 defines that distributed scheduling uses the idempotency record in `processed_events` or a designated scheduling lock table as the canonical authority. The specific table and lock record schema have not been defined.

**Impact:** Without a specified lock table schema, distributed deployments cannot implement the idempotency gate consistently.

**Classification:** Operational decision. Requires defining: the scheduling lock table name and schema (`scheduler_execution_windows`?), the INSERT-wins arbitration behavior, and what happens when the lock table is unavailable (fail-safe or fail-open?).

---

### UE-SCH4 — Heartbeat Failure Escalation Threshold for Scheduler Domains (OPERATIONAL DECISION)

**Problem:** The threshold at which a missing scheduler heartbeat or a `SCHEDULER_DEGRADED` event triggers human-visible escalation has not been defined by a Config V2 variable.

**Impact:** Extended scheduler degradation could mask operational failures without generating operator alerts.

**Classification:** Operational decision. Requires a Config V2 variable (likely Group I) governing the escalation threshold for scheduler domain degradation duration.

---

### UE-SCH5 — Scheduler Identity in Compliance Attribution (GOVERNANCE DECISION)

**Problem:** The Compliance Orchestration Scheduler (§4.9) carries `compliance_actor_identity` in its trigger record, but the governance protocol for how the scheduler's identity is distinct from the operator who initiated the compliance workflow has not been defined.

**Impact:** Forensic attribution of compliance actions could be ambiguous if the scheduler's identity and the operator's identity are conflated in the trigger record.

**Classification:** Governance decision. Requires defining whether the compliance trigger record carries both `scheduler_identity` (the scheduling service) and `operator_identity` (the human who requested the compliance action), or whether a combined `delegated_by` field is the appropriate model.

---

## 15. DOWNSTREAM GOVERNANCE

---

### 15.1 Child Document Governance

`runtime/scheduler_design.md` governs scheduling semantics for the following child runtime documents. Where child documents contain scheduling semantics that contradict this document, this document governs:

| Child document | Governed scheduling aspects | Required updates |
|---|---|---|
| `runtime/daily_outreach_flow.md` | Scheduler trigger semantics in §STEP 1; timing values in flow overview; batch concurrency limits | Must remove hardcoded "6:00 PM CST" trigger reference (or update to reference Config V2 `outreach_daily_trigger_hour_cst`); must remove hardcoded "Max 50 concurrent" batch limit; trigger timing governed by §4.1 of this document |
| `runtime/retry_cycle_flow.md` | Retry timing semantics in §STEP 3; retry timeline hardcoded example; termination condition `contact_attempt ≥ MAX_ATTEMPTS` | Must remove hardcoded retry timeline (Day 1 CALL → Day 2 SMS → Day 3 EMAIL); must reference Config V2 Group A retry timing; `MAX_ATTEMPTS` must reference `outreach_max_retry_attempts` from Config V2 Group A per §6.1 of `runtime/system_loop.md`; retry scheduling governed by §4.2 of this document |

---

### 15.2 Parent Contract Reference

This document is governed by and must not conflict with:

* `runtime/system_loop.md` §4.1–4.10 (trigger conditions for each canonical orchestration domain)
* `runtime/system_loop.md` §10.5 (Scheduler Lag Governance — defines lag detection, recovery cycle attribution requirements)
* `runtime/system_loop.md` §3.2 (Mode Transition Governance — defines which transitions require which authorization levels)

Where this document adds scheduling-specific governance detail not present in `runtime/system_loop.md`, this document governs those scheduling-specific aspects. Where this document is silent on a governance question already answered by `runtime/system_loop.md`, `runtime/system_loop.md` governs.

---

## 16. REFERENCES

---

**Parent contract (this document is governed by):**
* `runtime/system_loop.md`

**Child documents (this document governs scheduling aspects of):**
* `runtime/daily_outreach_flow.md`
* `runtime/retry_cycle_flow.md`

**Directive contracts (consumed by triggered orchestration loops):**
* `directives/outreach_eligibility_rules.md`
* `directives/outreach_retry_policy.md`
* `directives/core_decision_engine.md`
* `directives/channel_selection_rules.md`
* `directives/escalation_rules.md`
* `directives/llm_processing_contract.md`
* `directives/ghl_integration_contract.md`
* `directives/agent_ownership_matrix.md`

**Specification contracts:**
* `spec/01_requirements.md` (Config V2 Governance Catalog §12 — trigger timing variables Groups A, H, I, K)
* `spec/03_state_transition_rules.md`
* `spec/04_idempotency_concurrency.md` (idempotency keys per loop)
* `spec/05_external_integrations.md`
* `spec/06_observability_operations.md`
* `spec/07_api_contracts.md`
* `spec/08_data_model.md`
* `spec/09_warehouse_physical_architecture.md`

**Architecture decisions:**
* FAD-1 (Physical copy AI immutability — `warehouse.snapshot_ai_narratives`)
* FAD-2 (Historical report reproducibility — no SQL Server re-reads in regeneration)
* FAD-3 (Prospective-only config activation)

---

## END OF FILE
