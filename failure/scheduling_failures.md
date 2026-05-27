# failure/scheduling_failures.md

---

## LAYER 8 — FAILURE HANDLING (GOVERNANCE-SAFE SCHEDULER RESILIENCE ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture. The previous version described MVP-era scheduler recovery documentation: a hardcoded "6 PM CST" specification value, a simplistic five-type failure taxonomy (Missed/Duplicate/Partial/Crash/Drift), a "Trigger recovery execution immediately" instruction as a first-class recovery step, a direct "restart scheduler service" crash recovery instruction, "normalize system time to CST" as a time-drift correction, three-tier scope behavior (MVP/STANDARD/PRODUCTION), and generic five-field log requirements. That architecture is incompatible with the governance-safe orchestration model. Scheduler failure handling is no longer operational recovery documentation. It is governance-safe scheduler resilience orchestration — deterministic orchestration-window recovery coordination with replay-safe scheduler failure governance and observable scheduler degradation management. This document is governed by and must not conflict with `failure/failure_playbook.md` (the canonical parent resilience contract) and `runtime/scheduler_design.md` (the authoritative scheduler orchestration contract).

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Scheduler Resilience Architecture** defines:

* How scheduler failure governance domains are categorized, governed, and made historically explainable
* What execution modes govern scheduler resilience behavior — and what is permitted in each mode
* How deterministic scheduler degradation is coordinated without silent fallback execution
* How Config V2 governs scheduler recovery cadences, timing thresholds, and degradation escalation — not hardcoded timing values
* How replay-safe scheduler recovery semantics prevent historical simulation from generating LIVE recovery effects
* How orchestration-window governance prevents duplicate LIVE cycles, orphaned cycles, and replay corruption
* How scheduler recovery attribution lineage enables forensic reconstruction of every recovery action
* How scheduler failure state governance preserves immutable lineage and externalized state authority
* What authority boundaries constrain the scheduler resilience layer vs what it must not own

This document is a **child resilience contract** governed by:

* `failure/failure_playbook.md` §2.4 (Scheduler Failures), §4.4 (Scheduler Outage Degradation), §7.1 (Governed Recovery Coordination Model), §12 (AP-FP rules), §13 (Acceptance Criteria)
* `runtime/scheduler_design.md` §5 (Orchestration Window Governance), §6 (Config V2 Scheduling Governance), §7 (Replay & Regeneration Scheduling), §8 (Recovery & Degradation Governance), §9 (Attribution & Observability), §10 (Authority Boundaries)

Where this document conflicts with `failure/failure_playbook.md`, `failure/failure_playbook.md` governs. Where this document conflicts with `runtime/scheduler_design.md`, `runtime/scheduler_design.md` governs.

---

### 1.2 What Scheduler Failure Handling Is NOT

In the governance-safe orchestration model, scheduler failure handling is explicitly **NOT**:

* **"Trigger recovery execution immediately"** — this V1 instruction is replaced by governed scheduler recovery orchestration coordination (AP-SF3); no scheduler failure domain authorizes direct recovery execution as a resilience step
* **"Restart scheduler service"** — infrastructure process restart is not a scheduler resilience governance action; crash recovery is governed by orphan detection, recovery cycle attribution, and Operational Administrator authorization (AP-SF1)
* **"Normalize system time to CST"** — system time governance is not a resilience layer responsibility; scheduler timing is governed by Config V2 Group A `outreach_daily_trigger_hour_cst`; drift detection produces a structured event and escalation candidacy, not a direct normalization instruction (AP-SF4)
* **"Block second execution"** — duplicate trigger blocking is not a resilience-layer action; it is enforced by the orchestration-window idempotency gate in `runtime/scheduler_design.md` §5; the resilience layer observes and logs duplicate suppression events (AP-SF6)
* **Silent scheduler recovery** — scheduler recovery that does not produce an observable record is a specification violation (AP-SF8)
* **Replay-triggered LIVE scheduler recovery** — a replay-mode scheduling simulation may not generate LIVE recovery cycles (AP-SF2)
* **Hardcoded timing semantics** — no scheduler failure domain references a hardcoded trigger time, drift tolerance, or window duration; all timing values are governed by Config V2 (AP-SF4)

Explicitly prohibited in scheduler resilience orchestration:

* Direct scheduler process restart as a resilience step (AP-SF1)
* Replay-triggered LIVE recovery cycles (AP-SF2)
* "Trigger recovery execution immediately" semantics (AP-SF3)
* Hardcoded timing values in failure handling paths (AP-SF4)
* Orphaned execution windows without dead-letter documentation (AP-SF5)
* Duplicate recovery cycles for the same window (AP-SF6)
* Immutable record mutation during scheduler recovery (AP-SF7)
* Silent scheduler degradation (AP-SF8)

---

### 1.3 Authoritative Parent Contract Inheritance

This document inherits the following governance model from its parent contracts:

| Parent contract | Governing sections inherited |
|---|---|
| `failure/failure_playbook.md` | §2.4 Scheduler Failures; §4.4 Scheduler Outage Degradation; §7.1 Governed Recovery Coordination Model; §7.2 Config V2 Thresholds; §8 Attribution & Observability; §9 Idempotency; §12 AP-FP1 through AP-FP15; §13 AC-FP1 through AC-FP12 |
| `runtime/scheduler_design.md` | §3 Scheduler Modes; §4 Canonical Scheduler Domains; §5 Orchestration Window Governance; §6 Config V2 Scheduling Governance; §8 Recovery & Degradation Governance; §9.1–9.4 Attribution & Observability; §10 Authority Boundaries; AP-SCH1 through AP-SCH13 |
| `runtime/system_loop.md` | §10.1 Deterministic Degradation Principles; §10.5 Scheduler Lag Governance; §11 Runtime Attribution & Observability |

AP-FP rules from `failure/failure_playbook.md` and AP-SCH rules from `runtime/scheduler_design.md` are binding on this document. Where this document defines AP-SF rules, they are scheduler-resilience-specific extensions of the parent AP rules.

---

## 2. SCHEDULER FAILURE GOVERNANCE DOMAINS

---

### 2.1 Missed-Window Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | A governed execution window for any scheduler domain passed without a trigger record being emitted within the Config V2-governed timing window (governed by `outreach_daily_trigger_hour_cst` for the Orchestration Evaluation Scheduler; Config V2 Group I for other domains) |
| **Recovery philosophy** | Missed-window failures are detected by comparing expected trigger time (Config V2 Group A `outreach_daily_trigger_hour_cst`) against last recorded cycle completion timestamp; missed window triggers a governed recovery orchestration cycle with `execution_type = recovery` and full attribution; "trigger recovery execution immediately" is not a permitted semantic |
| **Replay behavior** | Missed-window records are preserved in scheduler trigger history; replay may simulate the missed window diagnostic; no LIVE recovery effects produced from replay |
| **SHADOW behavior** | Missed-window recovery evaluated in SHADOW mode; recovery cycle carries `execution_mode = SHADOW`; no LIVE outbound dispatch from recovery cycle |
| **LIVE behavior** | Lag detection triggers governed recovery coordination; recovery cycle carries `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`; already-processed students skipped via `processed_events` idempotency gate |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = missed_window`, `expected_trigger_time` (from Config V2), `last_cycle_completion_timestamp`, `lag_duration_ms`, `recovery_cycle_id` |
| **Attribution requirements** | `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by` in all recovery records; `cycle_id` linking recovery cycle to missed window |
| **Idempotency guarantees** | Recovery cycle uses same idempotency key as missed cycle `(scheduler_domain, cycle_date, execution_mode)`; duplicate recovery cycle → no-op |

**Prohibited patterns in missed-window handling:**
* "Trigger recovery execution immediately" as a direct execution instruction (AP-SF3)
* Recovery cycle without `recovery_of_cycle_date` attribution (AP-SF12)
* Duplicate recovery cycles for the same missed window (AP-SF6)

---

### 2.2 Duplicate-Window Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Two or more trigger attempts for the same `(scheduler_domain, cycle_date, execution_mode)` orchestration window within the idempotency gate window |
| **Recovery philosophy** | Duplicate triggers are absorbed by the orchestration-window idempotency gate in `runtime/scheduler_design.md` §5.1; the second trigger is a no-op; a `DUPLICATE_TRIGGER_SUPPRESSED` event is emitted; no resilience-layer recovery action is required; the resilience layer observes and logs the suppression |
| **Replay behavior** | Duplicate suppression records are preserved; replay may simulate the duplicate storm; no LIVE recovery effects |
| **SHADOW behavior** | `DUPLICATE_TRIGGER_SUPPRESSED` logged with `execution_mode = SHADOW`; loop continues |
| **LIVE behavior** | `DUPLICATE_TRIGGER_SUPPRESSED` event emitted with `scheduler_domain`, `cycle_id_duplicate`, `cycle_id_original`, `trigger_count`; no second cycle initiated; escalation candidacy generated if storm threshold exceeded |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = duplicate_window`, `scheduler_domain`, `trigger_count`, `idempotency_check_outcome = duplicate_suppressed` |
| **Attribution requirements** | `cycle_id_original` (the winning trigger) and `cycle_id_duplicate` (the suppressed trigger) both logged |
| **Idempotency guarantees** | Orchestration-window idempotency gate enforces at-most-once execution per window; no business state changes from suppressed trigger |

---

### 2.3 Orphaned-Window Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | A scheduler trigger fired, a `cycle_id` was generated and recorded, but no `loop_cycle_complete` record was emitted within the Config V2 Group I governance-defined orphan-detection window (governed by `runtime/scheduler_design.md` §5.5) |
| **Recovery philosophy** | Orphan detection runs within the Observability Heartbeat Loop (§4.10 of `scheduler_design.md`); any `cycle_id` without a linked completion record beyond the timeout threshold produces a `CYCLE_ORPHAN_DETECTED` alert; orphaned cycles are not silently discarded; they are documented in a dead-letter record with `orphaned_cycle_id` attribution; recovery requires Operational Administrator authorization (UE-SCH2) |
| **Replay behavior** | Orphaned cycle records preserved; replay may simulate the orphaned-window diagnostic with `source_artifact_id = orphaned_cycle_id`; no LIVE recovery |
| **SHADOW behavior** | Orphan detection emits `CYCLE_ORPHAN_DETECTED` in SHADOW mode; dead-letter record created; no LIVE recovery |
| **LIVE behavior** | `CYCLE_ORPHAN_DETECTED` event emitted; dead-letter record created with full attribution; escalation candidacy generated; recovery cycle triggered with `execution_type = recovery` and `orphaned_cycle_id` annotation after Operational Administrator authorization |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = orphaned_window`, `orphaned_cycle_id`, `orphan_detection_timestamp`, `time_since_trigger_ms` |
| **Attribution requirements** | `orphaned_cycle_id`, `orphan_detection_timestamp` in dead-letter and recovery records |
| **Idempotency guarantees** | Recovery cycle for orphaned window uses same idempotency key as orphaned cycle; already-processed records skipped |

---

### 2.4 Scheduler Crash Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Scheduler process-level failure where no trigger record was emitted within the Config V2-governed window for an expected domain; detected by absence of trigger record (not by process monitoring — the trigger record is the authoritative signal) |
| **Recovery philosophy** | Crash detection is trigger-record-absence-based; orphan detection flags missed windows; crash recovery is not "restart scheduler service" — it is governed recovery coordination with Operational Administrator authorization; recovery cycle carries `execution_type = recovery` and `scheduler_crash_detected = true` attribution |
| **Replay behavior** | Crash event records preserved; replay may simulate crash window diagnostic; `SCHEDULER_CRASH_DETECTED` event visible in replay context |
| **SHADOW behavior** | Crash detection emits `SCHEDULER_CRASH_DETECTED` in SHADOW mode; recovery coordination deferred until LIVE mode for outbound effects |
| **LIVE behavior** | `SCHEDULER_CRASH_DETECTED` event emitted; affected scheduler domain enters SCHEDULER_DEGRADED state; escalation candidacy generated; recovery cycle authorized by Operational Administrator; full attribution carried in recovery records |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = scheduler_crash`, `scheduler_domain`, `expected_trigger_time`, `crash_detection_timestamp`, `first_missing_window` |
| **Attribution requirements** | `recovery_authorization_record_id` (Operational Administrator authorization) in recovery trigger record |
| **Idempotency guarantees** | Recovery cycle for crash-missed window uses same idempotency key as missed cycle |

**Prohibited patterns in crash handling:**
* "Restart scheduler service" as a resilience governance instruction (AP-SF1)
* Triggering recovery before Operational Administrator authorization when automation is not Config V2-defined (AP-SF9)

---

### 2.5 Distributed Timing Drift Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Multiple scheduler instances disagree on the current execution window due to clock skew between distributed processes; governed by Config V2 Group I distributed clock skew tolerance variable |
| **Recovery philosophy** | Clock skew is resolved deterministically by the orchestration-window idempotency gate: the first INSERT to the idempotency record wins; all other scheduler instances read the existing record and treat the trigger as a no-op; timing drift does not require a recovery cycle; it produces a structured event when drift exceeds Config V2 Group I tolerance |
| **Replay behavior** | Timing drift records preserved; replay uses historical `triggered_at` from winning trigger record |
| **SHADOW behavior** | `DISTRIBUTED_TIMING_DRIFT_DETECTED` emitted if drift exceeds Config V2 tolerance; idempotency gate resolves winner; no LIVE effects |
| **LIVE behavior** | `DISTRIBUTED_TIMING_DRIFT_DETECTED` emitted with `scheduler_domain`, `drift_ms`, `winning_instance`, `config_v2_tolerance_ms`; orchestration continues with winning trigger record; no recovery cycle required |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = distributed_timing_drift`, `drift_ms`, `config_v2_clock_skew_tolerance_applied`, `winning_instance` |
| **Attribution requirements** | `winning_cycle_id` from winning trigger; `drift_detected_at` in structured event |
| **Idempotency guarantees** | Idempotency gate enforces single-cycle execution regardless of drift severity |

**Prohibited patterns in drift handling:**
* "Normalize system time to CST" as a resilience governance instruction (AP-SF4)
* Hardcoded drift tolerance values in failure handling logic (AP-SF4)

---

### 2.6 Replay Scheduling Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Replay Orchestration Scheduler (§4.8 of `scheduler_design.md`) authorization failures, historical config resolution failures, historical trigger timing resolution failures, partial replay scheduling due to incomplete historical records |
| **Recovery philosophy** | Replay scheduling failures emit SHADOW-only diagnostics; no LIVE recovery effects; replay failure annotates `replay_partial = true` when historical trigger timing cannot be resolved from config version record; replay scheduling failure does not block LIVE orchestration |
| **Replay behavior** | Replay scheduling failure is itself a replay diagnostic; `fingerprint_comparison_outcome = UNKNOWN` when historical state is incomplete |
| **SHADOW behavior** | All replay scheduling is SHADOW-mode by definition; failure scoped to `execution_type = replay` |
| **LIVE behavior** | No LIVE behavior during replay scheduling failure; LIVE mode may not be entered from replay scheduling failure context |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = replay_scheduling_failure`, `source_artifact_id`, `historical_config_version_id`, `historical_trigger_time_resolved` (or `HISTORY_INCOMPLETE`), `replay_partial` |
| **Attribution requirements** | `source_artifact_id`, `governance_authorization_record_id`, `historical_config_version_id` or null |
| **Idempotency guarantees** | Replay scheduling is inherently read-only; no idempotency key consumption during replay scheduling failure |

---

### 2.7 Regeneration Scheduling Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Report Generation Scheduler (§4.6 of `scheduler_design.md`) failure in REGENERATION mode: report lineage resolution failures, `warehouse.student_snapshots` read failures during regeneration scheduling, cohort finalization completeness gate failures |
| **Recovery philosophy** | Regeneration scheduling failure emits structured log and stops for the affected regeneration request; no retry within regeneration mode without operator re-authorization; no warehouse mutation on failure; failed regeneration scheduling does not corrupt existing REPORT_PUBLISHED state |
| **Replay behavior** | Regeneration is not replay; regeneration scheduling failure does not produce replay diagnostics |
| **SHADOW behavior** | Regeneration may be scheduled in any mode; failure tagged `execution_type = regeneration`; no LIVE dispatch from regeneration |
| **LIVE behavior** | Regeneration scheduling failure emits structured event; no state transitions; no provider calls; recovery requires operator re-authorization of new regeneration request |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = regeneration_scheduling_failure`, `cohort_id`, `report_month`, `lineage_version`, `failure_cause` |
| **Attribution requirements** | `lineage_version`, `source_artifact_id` (cohort snapshot) required |
| **Idempotency guarantees** | Regeneration creates new version lineage on success; failed scheduling does not produce a partial lineage record (AP-SF7) |

---

### 2.8 Degraded Scheduler Coordination

| Attribute | Specification |
|---|---|
| **Governance scope** | A scheduler domain enters a SCHEDULER_DEGRADED state due to: Config V2 timing variable unavailable, provider outage blocking triggered loop dispatch, AI provider outage suppressing AI Refresh Scheduler trigger, SQL Server connection failure at sync trigger time, or stale-lock on current window |
| **Recovery philosophy** | Degraded scheduler domains emit `SCHEDULER_DEGRADED` structured log; degradation is observable, not silent; affected domain does not silently skip trigger cycles — if a trigger cannot safely fire, it is documented as `TRIGGER_SUPPRESSED` with `suppression_reason`; escalation candidacy generated if domain remains degraded beyond Config V2 Group I threshold; domain emits `SCHEDULER_RECOVERY` event when degradation resolves |
| **Replay behavior** | Historical `SCHEDULER_DEGRADED` events preserved; replay reads degradation onset from trigger history at historical timestamp |
| **SHADOW behavior** | Degraded scheduler triggers in SHADOW mode carry degradation annotation; outputs tagged `execution_mode = SHADOW` and `degradation_flags` |
| **LIVE behavior** | `SCHEDULER_DEGRADED` event emitted per domain; `TRIGGER_SUPPRESSED` record per suppressed trigger window; escalation candidacy when persistence threshold exceeded; `SCHEDULER_RECOVERY` event on resolution |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = degraded_coordination`, `scheduler_domain`, `degradation_cause`, `first_affected_window`, `degradation_onset_timestamp` |
| **Attribution requirements** | `scheduler_domain`, `degradation_onset_timestamp`, `config_version_id` (to identify which version was missing the threshold, if applicable) |
| **Idempotency guarantees** | Degraded-mode triggers that produce `TRIGGER_SUPPRESSED` records do not consume window idempotency keys; the window remains available for recovery after degradation resolves |

---

### 2.9 Synchronization Backlog at Scheduler Trigger

| Attribute | Specification |
|---|---|
| **Governance scope** | SQL Server sync lag exceeds `sql_server_max_sync_age_hours` from Config V2 Group K at the time the Orchestration Evaluation Scheduler or Retry Orchestration Scheduler fires |
| **Recovery philosophy** | Sync backlog at trigger time does not block the scheduler trigger; orchestration cycle proceeds with `STALE_SQL_SERVER_DATA` annotation on affected student records; the Provider Synchronization Scheduler (§4.7) recovers sync independently; no recovery cycle is triggered for scheduling itself |
| **Replay behavior** | Sync lag annotation at trigger time is preserved in scheduler trigger records; replay reads historical `sync_lag_hours` value from original trigger record |
| **SHADOW behavior** | `SYNC_LAG_EXCEEDED` event emitted; scheduler trigger proceeds with annotation |
| **LIVE behavior** | `SYNC_LAG_EXCEEDED` event emitted; scheduler trigger fires with `stale_sql_server_data = true` annotation; orchestration loop receives annotated data; persistent sync backlog generates escalation candidacy |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = sync_backlog_at_trigger`, `scheduler_domain`, `sync_lag_hours`, `sql_server_max_sync_age_hours_applied` (Config V2 Group K value used) |
| **Attribution requirements** | `sync_lag_hours` annotation in all orchestration records produced during stale-data cycle |
| **Idempotency guarantees** | Sync operations are read-only for SQL Server; no idempotency concern for annotated trigger cycles |

---

### 2.10 Attribution-Loss Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Scheduler trigger record missing `cycle_id`, orchestration loop start record missing `cycle_id` session context linkage, recovery cycle missing `recovery_of_cycle_date`, broken chain between `cycle_id` (scheduler) and `correlation_id` (orchestration loop) |
| **Recovery philosophy** | Attribution failure in the scheduler layer is a specification defect; affected records are flagged `attribution_incomplete = true`; no silent continuation with broken scheduler attribution; escalation candidacy generated; recovery cycle requires full attribution before initiating |
| **Replay behavior** | Attribution failure produces `fingerprint_comparison_outcome = UNKNOWN` with `attribution_incomplete = true`; replay simulation cannot proceed without `source_artifact_id` |
| **SHADOW behavior** | Attribution failure logged with SHADOW scope; flagged for review |
| **LIVE behavior** | `SCHEDULER_ATTRIBUTION_FAILURE` event emitted; affected cycle annotated; escalation candidacy generated; cycle not aborted unless precondition gate fails |
| **Observability requirements** | `failure_domain = scheduler`, `scheduler_failure_type = attribution_loss`, `missing_field`, `affected_cycle_id`, `attribution_incomplete = true` |
| **Attribution requirements** | Attribution failure record must itself carry `cycle_id` from the scheduler trigger event, even if downstream loop records are missing it |
| **Idempotency guarantees** | Attribution failure records are append-only; no retroactive lineage repair that mutates existing records (AP-SF7) |

---

## 3. SCHEDULER FAILURE AUTHORITY BOUNDARIES

---

### 3.1 What the Scheduler Resilience Layer Coordinates

| Responsibility | Scheduler resilience layer owns | Scheduler resilience layer does NOT own |
|---|---|---|
| Scheduler failure domain classification and routing | Yes | Defining scheduler timing governance (Config V2 owns timing) |
| Recovery cycle attribution coordination | Yes | Executing the recovery cycle orchestration (orchestration loops own this) |
| Degraded scheduler domain coordination | Yes | Mode transition authority (Governance/Operational Administrator owns this) |
| Observability emission for scheduler failure events | Yes | Implementing scheduler monitoring infrastructure |
| Orchestration-window idempotency record governance | Yes (observing) | Writing idempotency records (scheduler domain owns this per `scheduler_design.md` §5.1) |
| Escalation candidacy generation for scheduler failures | Yes | Escalation routing to human operators (escalation routing service owns this) |
| Dead-letter record coordination for orphaned windows | Yes | Dead-letter infrastructure implementation |
| Stale-lock detection and force-unlock request | Yes (detection) | Force-unlock execution (Operational Administrator owns this per `scheduler_design.md` §5.6) |

---

### 3.2 Mode Transition Authority Restrictions

The scheduler resilience layer never coordinates mode transitions:

* No scheduler failure handling path may initiate a SHADOW-to-LIVE transition (AP-SCH2; AP-SF9)
* Degraded-mode entry from scheduler failure is annotated and observed — not orchestrated by the resilience layer
* Recovery from DEGRADED to LIVE is Governance Administrator authority; resilience layer emits `SCHEDULER_RECOVERY` event when conditions resolve
* Mode transition decisions require human operator authorization; no recovery cycle trigger may encode a mode transition as a recovery step

---

### 3.3 Provider Authority Restrictions During Scheduler Failures

The scheduler resilience layer never escalates provider authority during failures:

* Providers remain `platform_supplementary` during scheduler failures — failure does not grant providers additional governance scope
* Provider outage at scheduler trigger time blocks dispatch within the triggered orchestration loop; it does not authorize alternative dispatch from the scheduler resilience layer (AP-FP1; AP-SF1)
* Recovery cycles are subject to the same provider governance boundaries as original cycles (AP-FP8)
* No scheduler failure handling path directly calls a GHL API, constructs a webhook, or initiates a communication dispatch

---

### 3.4 AI Authority Restrictions During Scheduler Failures

The scheduler resilience layer never expands AI advisory authority during failures:

* AI provider outage at AI Refresh Scheduler trigger time suppresses the AI refresh trigger; it does not elevate AI to decision-making authority (AP-FP9)
* AI advisory absence during degraded scheduler evaluation is annotated; rule-based evaluation proceeds
* FINALIZED_COPY records are never re-evaluated by scheduler recovery — they remain immutable (AP-SF7)
* No scheduler failure handling path initiates live AI inference

---

### 3.5 Replay Authority Restrictions During Scheduler Failures

The scheduler resilience layer does not grant LIVE authority to replay scheduling:

* A scheduler failure detected during replay simulation produces no LIVE recovery cycle (AP-SF2)
* Replay scheduling failure outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`
* No mode transition from REPLAY to LIVE is permitted within a scheduler resilience sequence (AP-SF9)
* Replay scheduling simulation reads historical trigger records from scheduler audit history; it does not re-trigger historical scheduling domains

---

## 4. DETERMINISTIC SCHEDULER DEGRADATION GOVERNANCE

---

### 4.1 Scheduler Degradation Principles

Scheduler degradation is observable, not silent. Inherited from `runtime/system_loop.md` §10.1 and extended for the scheduler layer:

Every degraded scheduler state must:
* Emit a `SCHEDULER_DEGRADED` structured log entry with `scheduler_domain`, `degradation_cause`, `first_affected_window`, `degradation_onset_timestamp`
* Produce a `TRIGGER_SUPPRESSED` record for each window that cannot safely fire
* Generate an observable escalation candidacy signal when persistence threshold is exceeded
* Emit a `SCHEDULER_RECOVERY` structured log when the degradation condition resolves
* Never silently skip a trigger window without a `TRIGGER_SUPPRESSED` record

The following patterns are prohibited (AP-SF3, AP-SF4, AP-SF8):
* Direct scheduler process restart as a recovery instruction
* Falling back to a hardcoded timing value when a Config V2 variable is missing
* Silently expiring a stale orchestration-window lock without producing `STALE_LOCK_FORCE_UNLOCKED` record (AP-SCH9)

---

### 4.2 Scheduler Crash Degradation

When scheduler crash is detected (absence of trigger record within Config V2-governed window):

* Affected scheduler domain emits `SCHEDULER_CRASH_DETECTED` event with `scheduler_domain`, `expected_trigger_time`, `crash_detection_timestamp`, `first_missing_window`
* Domain enters SCHEDULER_DEGRADED state; `SCHEDULER_DEGRADED` structured log emitted
* Escalation candidacy generated for Operational Administrator awareness
* Recovery cycle triggered after Operational Administrator authorization (UE-SCH2) with `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`, `scheduler_crash_detected = true`
* Missed windows are not automatically recovered; each missed window requires explicit authorization

---

### 4.3 Missed-Window Degradation

When scheduler lag is detected for a missed execution window:

* Lag detection compares expected trigger time from Config V2 Group A `outreach_daily_trigger_hour_cst` against last recorded cycle completion timestamp
* `SCHEDULER_LAG_DETECTED` event emitted with `scheduler_domain`, `expected_trigger_time`, `lag_duration_ms`
* Missed cycle triggers governed recovery coordination (§7.1 of this document); recovery cycle carries `execution_type = recovery` and full attribution
* Recovery cycle is idempotent — same idempotency key as missed cycle; duplicate processing blocked via `processed_events`
* Scheduler lag persisting beyond Config V2 Group I governance-defined bounds generates escalation candidacy

---

### 4.4 Duplicate Trigger Storm Degradation

When duplicate trigger attempts exceed a governance-defined threshold within a single window:

* Each duplicate trigger is absorbed by the orchestration-window idempotency gate (first INSERT wins)
* All suppressed duplicates produce `DUPLICATE_TRIGGER_SUPPRESSED` records
* When storm count exceeds threshold: `DUPLICATE_TRIGGER_STORM` event emitted with `scheduler_domain`, `duplicate_count`, `window_start`, `window_end`
* Escalation candidacy generated for operator awareness
* Outbound orchestration is unaffected — storm absorbed without impacting the valid cycle

---

### 4.5 Distributed Timing Drift Degradation

When clock skew between distributed scheduler instances is detected:

* Orchestration-window idempotency gate resolves the winner deterministically (first INSERT to idempotency record wins)
* All non-winning instances treat the trigger as a no-op
* If drift exceeds Config V2 Group I clock skew tolerance: `DISTRIBUTED_TIMING_DRIFT_DETECTED` event emitted with `drift_ms`, `config_v2_tolerance_ms`, `winning_instance`
* No recovery cycle required for timing drift — idempotency gate has already ensured at-most-once execution
* Persistent drift beyond tolerance generates escalation candidacy

---

### 4.6 Orphaned-Window Degradation

When an orchestration window is orphaned (trigger record exists, no completion record after Config V2 Group I orphan-detection window):

* `CYCLE_ORPHAN_DETECTED` event emitted by Observability Heartbeat Loop with `orphaned_cycle_id`, `scheduler_domain`, `trigger_timestamp`, `detection_timestamp`, `time_since_trigger_ms`
* Dead-letter record created with full attribution
* Escalation candidacy generated for Operational Administrator triage
* Stale-lock evaluation: if window idempotency record exists without completion, stale-lock governance applies (§4.9)
* Recovery cycle authorized by Operational Administrator carries `orphaned_cycle_id` attribution

---

### 4.7 Observability Degradation in Scheduler Context

When the scheduler observability pipeline degrades:

* Scheduler domains continue triggering; observability failure does not block trigger evaluation
* Structured trigger records that fail to be written are directed to stderr with `OBSERVABILITY_DEGRADED` flag
* `OBSERVABILITY_DEGRADED` event directed to stderr; escalation candidacy generated for persistent degradation
* Scheduler attribution (at minimum `cycle_id`, `scheduler_domain`, `triggered_at`) is preserved in stderr even when observability pipeline is degraded

---

### 4.8 Config Threshold Missing in Scheduler Context

When a required Config V2 scheduler timing variable is missing from the ACTIVE config version:

* `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning emitted in scheduler trigger record
* Affected scheduler domain enters SCHEDULER_DEGRADED state for that domain
* Scheduler domain does not fire a trigger using a hardcoded fallback timing value (AP-SF4)
* `TRIGGER_SUPPRESSED` record produced with `suppression_reason = CONFIG_THRESHOLD_MISSING_{KEY}`
* Escalation candidacy generated for missing threshold
* When threshold is restored in a new Config V2 ACTIVE version, scheduler domain resumes and emits `SCHEDULER_RECOVERY` event

---

### 4.9 Stale-Lock Governance

When an orchestration-window idempotency record exists but the corresponding loop completion record never arrived:

* Window is considered locked-stale after Config V2 Group I governed timeout
* Stale-lock cannot be silently expired by automation (AP-SCH9; AP-SF8)
* Force-unlock requires Operational Administrator authorization with explicit `STALE_LOCK_FORCE_UNLOCKED` audit record containing `scheduler_domain`, `cycle_id`, `lock_age_seconds`, `operator_identity`
* After force-unlock, scheduler domain is eligible to trigger a recovery cycle for the missed window
* Recovery cycle for a force-unlocked window carries `stale_lock_resolved = true` attribution

---

## 5. REPLAY & REGENERATION SCHEDULING FAILURE SEMANTICS

---

### 5.1 Replay Scheduling Failure Governance

When the scheduler resilience layer processes failures in REPLAY mode (`execution_type = replay`):

* Replay may simulate historical scheduling failures from `scheduler_trigger_history` and `processed_events` records
* Replay may not generate LIVE recovery cycles from historical scheduling failure simulation
* Historical scheduling failure records are read-only reference points; replay does not re-trigger historical scheduler domains
* Replay scheduling failure diagnostics carry `governance_scope = REPLAY_ONLY`; they may not be consumed as LIVE recovery signals (AP-SF2)
* `fingerprint_comparison_outcome = MATCH | DIVERGENT | UNKNOWN` emitted for simulated vs historical scheduling failure behavior

---

### 5.2 Replay Suppression Rules

The following scheduler behaviors are suppressed in all replay contexts:

| Suppressed scheduler behavior | Suppression mechanism | Reference |
|---|---|---|
| Batch outreach trigger in replay context | Orchestration Evaluation Scheduler suppressed in REPLAY mode | AP-SCH3; `scheduler_design.md` §7.4 |
| Retry batch trigger in replay context | Retry Orchestration Scheduler suppressed in REPLAY mode | AP-SCH3; `scheduler_design.md` §7.4 |
| Live AI Refresh Scheduler trigger in replay | AI Refresh Scheduler does not invoke live AI inference | AP-AI5; `system_loop.md` §7.2 |
| Live provider sync trigger in replay | Provider Synchronization Scheduler reads stored snapshot data | `scheduler_design.md` §4.7 |
| Compliance workflow scheduling in replay | Compliance Orchestration Scheduler does not fire in REPLAY | `scheduler_design.md` §4.9 |
| SHADOW-to-LIVE mode transition via scheduler failure | No failure path may produce a mode transition | AP-SCH2; AP-SF9 |
| Recovery cycle from replay-detected scheduler failure | Replay scheduling failure produces SHADOW-only diagnostics; no LIVE recovery | AP-SF2 |

---

### 5.3 Historical Scheduling Visibility

In REPLAY mode, historical scheduling state is sourced from governance records — not from live scheduler evaluation:

* Historical trigger timing resolved from `historical_config_version_id` at time of original cycle — specifically `outreach_daily_trigger_hour_cst` (Group A) and relevant Group I timing variables
* If historical trigger timing cannot be resolved: annotated `replay_partial = true` with `HISTORY_INCOMPLETE` on the timing field
* Historical trigger records sourced from scheduler audit tables at historical `triggered_at` timestamp
* Historical idempotency records sourced from `processed_events` at historical timestamp
* Replay may not generate new trigger records to substitute for historically incomplete trigger data
* All replay scheduling visibility records carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`

---

### 5.4 Regeneration Scheduling Failure Semantics

Regeneration scheduling failures are distinct from replay scheduling failures:

* Regeneration creates new version lineage when successful — it does not overwrite the original published report (AP-SF7)
* Regeneration scheduling failure does not corrupt existing REPORT_PUBLISHED state
* No live inference, no state transitions, no provider calls during regeneration scheduling failure recovery
* Failed regeneration scheduling is documented as append-only records; recovery requires operator re-authorization of a new governed regeneration request
* Report Generation Scheduler in REGENERATION mode reads `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` exclusively (FAD-2); regeneration scheduling failure does not trigger live SQL Server re-sync

---

## 6. SCHEDULER FAILURE STATE GOVERNANCE

---

### 6.1 State Authority During Scheduler Failures

The scheduler resilience layer does not own state transitions. State write authority is externalized to the state management service in all scheduler failure scenarios:

| Scheduler failure scenario | State coordination | Scheduler resilience layer role |
|---|---|---|
| Missed execution window | No state change for students (processing deferred to recovery cycle) | Coordinates recovery cycle attribution; produces structured failure log |
| Duplicate trigger suppressed | No state change | `DUPLICATE_TRIGGER_SUPPRESSED` scope logged; idempotency gate enforces no-op |
| Orphaned window | No state change | `CYCLE_ORPHAN_DETECTED` event; dead-letter coordination |
| Scheduler crash | No state change for students | Recovery cycle coordination with full attribution after administrator authorization |
| Distributed timing drift | No state change (idempotency gate resolved) | `DISTRIBUTED_TIMING_DRIFT_DETECTED` event if tolerance exceeded |
| Stale lock | No state change | Stale-lock detection; escalation candidacy; force-unlock request to operator |
| Config threshold missing | No state change for students | SCHEDULER_DEGRADED annotation; `TRIGGER_SUPPRESSED` record |
| Replay scheduling failure | No state change | SHADOW-only diagnostic; `replay_partial = true` annotation |
| Sync backlog at trigger | No direct state change | Orchestration cycle proceeds with `STALE_SQL_SERVER_DATA` annotation |

---

### 6.2 Immutable Record Protections in Scheduler Recovery

Scheduler recovery orchestration must never mutate:

* `warehouse.student_snapshots` — FINALIZED state is irreversible; scheduler recovery does not re-trigger finalization (AP-OWN15; AP-SF7)
* `warehouse.snapshot_ai_narratives` — FINALIZED_COPY is immutable; scheduler recovery does not re-render AI narrative content
* `warehouse.monthly_reports` — REPORT_PUBLISHED is immutable; scheduler recovery does not overwrite published reports
* `state_transition_log` — append-only; recovery cycle produces new entries, not retroactive corrections
* `student_timeline_events` — append-only; recovery intent records are new entries with `execution_type = recovery`

---

### 6.3 Orchestration-Window State Coordination

The orchestration-window idempotency record (created by the scheduler domain in `processed_events` or scheduling lock table) is the authoritative window state:

* A window is open from trigger fire until loop completion record is emitted
* An open window may not be re-triggered (AP-SCH4)
* A window without a completion record after governance timeout is an orphan candidate
* A force-unlocked window is treated as having no prior execution record; a fresh recovery cycle may proceed
* Orchestration-window state is owned by the scheduler domain (via `scheduler_design.md` §5); the resilience layer observes and reports window state but does not write window state records directly

---

## 7. GOVERNED SCHEDULER RECOVERY COORDINATION

---

### 7.1 Governed Recovery Coordination Model

The V1 pattern:

> "Trigger recovery execution immediately" and "Restart scheduler service"

is replaced with:

> **Governed Scheduler Recovery Orchestration Coordination** — the scheduler resilience layer detects a missed or orphaned window, validates recovery governance prerequisites, coordinates the production of a `RecoveryOrchestrationRecord` with `execution_type = recovery` and full scheduler attribution, and delegates recovery through the same governance-authorized orchestration sequence as the original missed cycle

Recovery coordination model:

```
SCHEDULER FAILURE DETECTION  →  structured scheduler failure log emitted (§11.1)
  ↓
RECOVERY AUTHORIZATION GATE  →  execution_mode, config_version_id, and (if required) operator
                                  authorization validated; replay context: LIVE recovery blocked
  ↓
IDEMPOTENCY CHECK  →  same (scheduler_domain, cycle_date, execution_mode) key checked;
                       if already recovered, no-op; DUPLICATE_SUPPRESSED logged
  ↓
RECOVERY CYCLE ATTRIBUTION  →  recovery_of_cycle_date, lag_detected_at, recovery_initiated_by,
                                 orphaned_cycle_id (if applicable) annotated
  ↓
RECOVERY ORCHESTRATION DELEGATION  →  governed orchestration sequence (same as normal cycle);
                                        already-processed students skipped via processed_events
  ↓
OBSERVABILITY EMISSION  →  scheduler recovery cycle completion record (§11.2)
```

---

### 7.2 Config V2-Governed Scheduler Recovery Thresholds

Scheduler recovery behavior is governed by Config V2, not by hardcoded timing values:

| Scheduler recovery threshold | Config V2 source | Group |
|---|---|---|
| Daily trigger hour for recovery window determination | `outreach_daily_trigger_hour_cst` | A |
| Retry window cadence for missed-retry-window recovery | `outreach_retry_window_days` | A |
| Sync lag tolerance at recovery trigger time | `sql_server_max_sync_age_hours` | K |
| AI insight freshness assessment at recovery time | `ai_insight_ttl_hours` | H |
| Orphan detection window | (Config V2 Group I system timing variable) | I |
| Stale-lock timeout for window governance | (Config V2 Group I system timing variable) | I |
| Recovery cycle authorization window | (Config V2 Group I system timing variable) | I |
| Distributed clock skew tolerance | (Config V2 Group I system timing variable) | I |
| Escalation threshold for persistent degradation | (Config V2 Group I system timing variable) | I |

No hardcoded scheduler recovery thresholds are permitted. Substituting a literal timing value for any of these variables in scheduler failure handling logic is a specification defect (AP-SF4).

When a Config V2 threshold is missing, `UNKNOWN_V0` substitution applies with `CONFIG_THRESHOLD_MISSING_{KEY}` warning and SCHEDULER_DEGRADED annotation — not a hardcoded integer fallback.

---

### 7.3 Recovery Attribution Requirements

All scheduler recovery cycles must carry the following attribution fields in addition to standard scheduler trigger attribution:

| Field | Required value |
|---|---|
| `execution_type` | `recovery` |
| `recovery_of_cycle_date` | ISO-8601 date of the missed window |
| `lag_detected_at` | ISO-8601 timestamp when lag or orphan was detected |
| `recovery_initiated_by` | Operator identity or `system_orphan_detector` |
| `orphaned_cycle_id` | `cycle_id` of the orphaned or missed cycle, if available |
| `recovery_authorization_record_id` | Reference to Operational Administrator authorization record |
| `scheduler_crash_detected` | `true` if recovery is from a crash-miss event; `false` otherwise |
| `stale_lock_resolved` | `true` if recovery follows a stale-lock force-unlock; `false` otherwise |

Recovery cycles without these fields are specification violations (AP-SF12; `scheduler_design.md` §8.3).

---

### 7.4 Dead-Letter Governance for Scheduler Failures

Scheduler failure operations that cannot be recovered by normal governed recovery coordination are directed to dead-letter:

* Dead-letter record carries full attribution: `correlation_id` (or `cycle_id` if loop never started), `scheduler_domain`, `failure_domain`, `failure_cause`, `original_trigger_timestamp`, `attempt_count`
* Dead-letter records are append-only; no silent discard (AP-SF5)
* Dead-letter records produce escalation candidacy for human review
* Recovery from dead-letter requires a new governed cycle with `execution_type = recovery` and `orphaned_cycle_id` annotation — not a direct re-execution (AP-SF3)

---

## 8. SCHEDULER ATTRIBUTION & OBSERVABILITY

---

### 8.1 Scheduler Failure Attribution Lineage Chain

Every scheduler failure record must carry a complete attribution lineage. The full chain, extended from `runtime/scheduler_design.md` §9.1:

```
Config V2 trigger timing  →  outreach_daily_trigger_hour_cst (Group A) + Group I timing variables
  ↓
Scheduler Trigger  →  cycle_id + triggered_at + scheduler_domain + execution_mode + config_version_id
  ↓
Scheduler Failure Event  →  failure_domain + scheduler_failure_type + failure_cause
  ↓
Recovery Authorization Gate  →  config_version_id validated; operator_authorization (if required)
  ↓
Recovery Cycle Attribution  →  recovery_of_cycle_date + lag_detected_at + recovery_initiated_by
  ↓
Orchestration Loop  →  correlation_id + config_version_id (within recovery cycle)
  ↓
Dead-Letter or Escalation Candidacy  →  escalation_type + escalation_severity
```

A scheduler failure that cannot be traced from symptom back to root cause using a single `cycle_id` is an observability defect (`spec/06`).

---

### 8.2 Recovery Cycle Causation Propagation

Every scheduler recovery action must propagate causation lineage:

* Recovery cycle links to the missed cycle via `recovery_of_cycle_date` and `orphaned_cycle_id` (if available)
* Recovery orchestration records carry `causation_id` referencing the original `OrchestrationIntent` where applicable
* Recovery observability records carry `execution_type = recovery` and `cycle_id` from the recovery trigger
* Recovery records are not retroactively attributed to the original cycle's `correlation_id` — they carry the recovery cycle's own `correlation_id`
* The linkage between scheduler `cycle_id` and orchestration loop `correlation_id` must be persisted in the loop's start record

---

### 8.3 Replay Diagnostics

Replay scheduling failure diagnostics must carry:

| Field | Specification |
|---|---|
| `source_artifact_id` | ID of the original scheduler trigger record or cycle being replayed |
| `historical_config_version_id` | Config version at time of original scheduling trigger |
| `historical_trigger_time_resolved` | Resolved historical trigger timing or `HISTORY_INCOMPLETE` |
| `fingerprint_comparison_outcome` | `MATCH \| DIVERGENT \| UNKNOWN` |
| `replay_partial` | `true` if historical timing data was incomplete |
| `execution_type` | `replay` |
| `governance_scope` | `REPLAY_ONLY` |
| `replay_suppression_applied` | All suppression categories active during this replay trigger |

---

### 8.4 Scheduler Audit Continuity

All scheduler recovery actions produce observable, auditable records:

* Scheduler recovery trigger records are append-only — no retroactive updates to prior trigger records
* Every scheduler recovery action is attributable to an `actor_identity` (`system_orphan_detector` for automated; named operator identity for operator-initiated)
* Scheduler recovery cycle records are preserved in scheduler trigger history with `execution_type = recovery`
* The resilience layer does not produce scheduler audit records that contradict the append-only trigger history
* PII (student name, email, phone) must not appear in scheduler failure or recovery observability records (AP-SF13)

---

## 9. SCHEDULER FAILURE IDEMPOTENCY GUARANTEES

---

### 9.1 Core Idempotency Principle

Every scheduler recovery operation must satisfy the idempotency principle inherited from `spec/04_idempotency_concurrency.md` §2.1 and enforced by `runtime/scheduler_design.md` §2.1:

> Repeated operations MUST NOT create duplicate effects. Same request → same outcome. Same input + same state → same persisted result; no first-run/second-run divergence.

---

### 9.2 Domain-Specific Scheduler Idempotency Keys

| Scheduler failure domain | Idempotency key | Behavior on duplicate |
|---|---|---|
| Missed-window recovery | `(scheduler_domain, cycle_date, execution_mode, execution_type = recovery)` | Duplicate recovery trigger → no-op; `DUPLICATE_SUPPRESSED` logged |
| Duplicate-window detection | `(scheduler_domain, cycle_date, execution_mode)` in idempotency gate | Second trigger → no-op; `DUPLICATE_TRIGGER_SUPPRESSED` logged |
| Orphaned-window dead-letter | `(orphaned_cycle_id, failure_domain = scheduler)` | Duplicate dead-letter creation → no-op |
| Scheduler crash recovery | `(scheduler_domain, cycle_date, execution_type = recovery)` | Duplicate crash recovery trigger → no-op |
| Force-unlock audit record | `(cycle_id, operator_identity, stale_lock_force_unlock_timestamp)` | Duplicate force-unlock audit → idempotent confirmation |
| Escalation candidacy from scheduler failure | `(scheduler_domain, failure_type, onset_timestamp)` | Duplicate escalation candidacy → idempotent candidacy confirmation |

---

### 9.3 Idempotency Violations Are Production Defects

An operation that "works once but produces duplicate effects on the second run" is broken. Idempotency violations in scheduler recovery paths must be fixed before the change ships:

* Recovery cycle that re-processes already-processed students without checking `processed_events` idempotency key
* Orphaned-window dead-letter that creates a duplicate record without deduplication
* Force-unlock that produces duplicate `STALE_LOCK_FORCE_UNLOCKED` audit records
* Escalation candidacy generation that fires multiple candidacy signals for the same degradation onset without deduplication

---

## 10. DETERMINISTIC DEGRADATION CONDITION TABLE

---

### 10.1 Canonical Scheduler Degradation Conditions

Inherited from `runtime/system_loop.md` §10.2 and `runtime/scheduler_design.md` §8.2 with scheduler-resilience-specific annotations:

| Condition | Scheduler failure domain | Scheduler behavior | Scheduling continues | Resilience escalation |
|---|---|---|---|---|
| Scheduler lag detected (missed window) | Missed-window (§2.1) | Governed recovery coordination triggered; `SCHEDULER_LAG_DETECTED` event | Yes (recovery) | `SCHEDULER_LAG_DETECTED` + recovery attribution |
| Scheduler crash (no trigger record) | Crash (§2.4) | `SCHEDULER_CRASH_DETECTED`; domain enters SCHEDULER_DEGRADED; recovery requires admin authorization | No (affected domain) | `SCHEDULER_CRASH_DETECTED` + escalation candidacy |
| Duplicate trigger storm | Duplicate-window (§2.2) | Idempotency gate absorbs; `DUPLICATE_TRIGGER_STORM` when threshold exceeded | Yes | `DUPLICATE_TRIGGER_STORM` + dedup count |
| Orphaned window detected | Orphaned-window (§2.3) | `CYCLE_ORPHAN_DETECTED`; dead-letter created; admin authorization required for recovery | No (that cycle) | `CYCLE_ORPHAN_DETECTED` + dead-letter record |
| Distributed timing drift | Drift (§2.5) | Idempotency gate resolves winner; `DISTRIBUTED_TIMING_DRIFT_DETECTED` if exceeds tolerance | Yes | `DISTRIBUTED_TIMING_DRIFT_DETECTED` if beyond tolerance |
| Config timing threshold missing | Degraded coordination (§2.8) | SCHEDULER_DEGRADED; `TRIGGER_SUPPRESSED`; no hardcoded fallback | No (affected domain) | `CONFIG_THRESHOLD_MISSING_{KEY}` + escalation candidacy |
| Provider outage at trigger time | Degraded coordination (§2.8) | Trigger fires; dispatching loop receives `governance_scope = UNAVAILABLE`; retry budget protected | Yes (with annotation) | `PROVIDER_OUTAGE` event; degradation onset record |
| AI provider outage at AI Refresh Scheduler | Degraded coordination (§2.8) | AI Refresh Scheduler trigger suppressed; `TRIGGER_SUPPRESSED` record; next scheduled trigger resumes when AI available | No (AI Refresh domain) | `AI_PROVIDER_UNAVAILABLE` event; stale AI annotation |
| SQL Server sync backlog at trigger | Sync backlog (§2.9) | Trigger fires; orchestration proceeds with `STALE_SQL_SERVER_DATA` annotation | Yes (with annotation) | `SYNC_LAG_EXCEEDED` event |
| Stale lock on current window | Orphaned-window (§2.3) | Stale-lock detected after Config V2 Group I timeout; force-unlock requires admin; no silent expiry | No (that window) | Admin authorization request + `STALE_LOCK_FORCE_UNLOCKED` on resolution |
| Observability pipeline degraded | Degraded coordination (§2.8) | Scheduler triggers continue; `OBSERVABILITY_DEGRADED` to stderr; attribution preserved in stderr | Yes | Direct stderr alert |
| Replay scheduling failure | Replay scheduling (§2.6) | SHADOW-only diagnostic; `replay_partial = true`; no LIVE recovery | Yes (SHADOW scope) | `REPLAY_SCHEDULING_FAILURE` diagnostic; no LIVE escalation |
| Attribution-loss in trigger chain | Attribution-loss (§2.10) | Affected records flagged `attribution_incomplete = true`; escalation candidacy | No (that cycle) | `SCHEDULER_ATTRIBUTION_FAILURE` event |

---

## 11. SCHEDULER RESILIENCE OBSERVABILITY SCHEMA

---

### 11.1 Structured Scheduler Failure Log Record

Every scheduler failure event must emit a structured JSON record, extending the parent schema from `failure/failure_playbook.md` §11.1 with scheduler-specific fields:

```json
{
  "timestamp": "ISO-8601",
  "level": "warn | error",
  "service": "scheduler_resilience_orchestration",
  "event": "scheduler_failure_detected",
  "failure_domain": "scheduler",
  "scheduler_failure_type": "missed_window | duplicate_window | orphaned_window | scheduler_crash | distributed_timing_drift | replay_scheduling_failure | regeneration_scheduling_failure | degraded_coordination | sync_backlog_at_trigger | attribution_loss",
  "scheduler_domain": "orchestration_evaluation | retry_orchestration | escalation_polling | ai_refresh | snapshot_finalization | report_generation | provider_synchronization | replay_orchestration | compliance_orchestration | observability_heartbeat",
  "cycle_id": "uuid | null",
  "correlation_id": "uuid | null",
  "execution_mode": "SHADOW | LIVE | REPLAY | REGENERATION | DEGRADED | MAINTENANCE",
  "execution_type": "original | recovery | replay | regeneration",
  "config_version_id": "string | null",
  "expected_trigger_time": "ISO-8601 | null",
  "actual_trigger_time": "ISO-8601 | null",
  "lag_duration_ms": 0,
  "orphaned_cycle_id": "uuid | null",
  "recovery_of_cycle_date": "YYYY-MM-DD | null",
  "recovery_action": "governed_recovery_cycle | dead_letter | degraded_continuation | escalation_candidacy | no_op | trigger_suppressed",
  "failure_cause": "string",
  "error_class": "TimeoutError | MissingTriggerRecord | OrphanedCycle | DuplicateTrigger | DistributedDrift | StaleLock | ConfigThresholdMissing | AttributionFailure | IdempotencyViolation | string",
  "degradation_flags": [],
  "config_threshold_missing_keys": [],
  "attribution_incomplete": false,
  "outcome": "failure | partial | degraded"
}
```

No PII (student name, email, phone) may appear in scheduler failure log records (AP-SF13).

---

### 11.2 Scheduler Recovery Cycle Completion Record

A governed scheduler recovery cycle emits a completion record extending the parent recovery record from `failure/failure_playbook.md` §11.2 with scheduler-specific attribution:

```json
{
  "timestamp": "ISO-8601",
  "level": "info",
  "service": "scheduler_resilience_orchestration",
  "event": "scheduler_recovery_cycle_complete",
  "scheduler_domain": "string",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | DEGRADED",
  "execution_type": "recovery",
  "config_version_id": "string",
  "recovery_of_cycle_date": "YYYY-MM-DD",
  "lag_detected_at": "ISO-8601",
  "recovery_initiated_by": "system_orphan_detector | operator_id",
  "recovery_authorization_record_id": "uuid | null",
  "orphaned_cycle_id": "uuid | null",
  "scheduler_crash_detected": false,
  "stale_lock_resolved": false,
  "recovery_candidates_processed": 0,
  "recovery_skipped_already_processed": 0,
  "recovery_failed_count": 0,
  "trigger_to_completion_ms": 0,
  "outcome": "success | partial | failure"
}
```

---

## 12. ARCHITECTURE PRESERVATION RULES

---

### AP-SF1 — No Direct Scheduler Process Restart as Recovery

MUST NOT use "restart scheduler service" or any equivalent process-restart instruction as a scheduler resilience step. Scheduler crash recovery is governed recovery cycle coordination following orphan detection and Operational Administrator authorization, not infrastructure-level process management. Violation is a specification defect.

### AP-SF2 — No Replay-Triggered LIVE Scheduler Recovery

MUST NOT allow replay-mode scheduling failure simulation to generate LIVE recovery cycles. All outputs from replay-mode scheduler resilience evaluation carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`. No mode transition from REPLAY to LIVE occurs within a scheduler resilience sequence.

### AP-SF3 — No "Trigger Recovery Execution Immediately" Semantics

MUST NOT use "trigger recovery execution immediately" or equivalent as a scheduler recovery instruction. Recovery coordination follows the governed six-step model in §7.1: FAILURE DETECTION → RECOVERY AUTHORIZATION GATE → IDEMPOTENCY CHECK → RECOVERY CYCLE ATTRIBUTION → RECOVERY ORCHESTRATION DELEGATION → OBSERVABILITY EMISSION.

### AP-SF4 — No Hardcoded Scheduler Timing Values in Resilience Paths

MUST NOT embed a hardcoded trigger time (e.g., "6 PM CST"), drift tolerance, stale-lock timeout, orphan-detection window, or recovery window duration in any scheduler failure handling path. All timing values are governed by Config V2. When a Config V2 timing variable is missing, `UNKNOWN_V0` substitution with `CONFIG_THRESHOLD_MISSING_{KEY}` applies — not a hardcoded integer fallback.

### AP-SF5 — No Orphaned Execution Windows Without Dead-Letter

MUST NOT silently discard an orphaned orchestration window. Every orphaned cycle must produce a `CYCLE_ORPHAN_DETECTED` event and a dead-letter record with full attribution. Silent orphan expiry is a specification defect.

### AP-SF6 — No Duplicate Recovery Cycles for the Same Window

MUST NOT produce duplicate recovery cycles for the same missed execution window. Recovery cycle idempotency key `(scheduler_domain, cycle_date, execution_mode, execution_type = recovery)` must be checked before initiating recovery. Duplicate recovery cycle → no-op; `DUPLICATE_SUPPRESSED` logged.

### AP-SF7 — No Immutable Record Mutation During Scheduler Recovery

MUST NOT overwrite, backfill, or retroactively modify any record in `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `warehouse.monthly_reports`, `state_transition_log`, or `student_timeline_events` during scheduler recovery. All recovery actions produce new append-only records.

### AP-SF8 — No Silent Scheduler Degradation

MUST NOT allow a scheduler domain to silently enter a degraded state, skip a trigger window, or expire a stale lock without producing an observable structured log record. Every degradation has a `SCHEDULER_DEGRADED` event. Every suppressed trigger has a `TRIGGER_SUPPRESSED` record. Every stale-lock force-unlock has a `STALE_LOCK_FORCE_UNLOCKED` audit entry.

### AP-SF9 — No Governance Bypass During Scheduler Recovery

MUST NOT bypass Config V2 threshold validation, execution mode checks, Operational Administrator authorization requirements, or orchestration-window idempotency gates during scheduler recovery orchestration. Recovery cycles are subject to the same governance precondition gate as original cycles.

### AP-SF10 — No Scheduler Authority Escalation

MUST NOT use a scheduler failure or recovery event to acquire provider authority, AI decision-making authority, or mode-transition authority. Scheduler domains hold orchestration timing authority only (per `runtime/scheduler_design.md` §10.1). Failure does not expand scheduler authority scope.

### AP-SF11 — No Silent Stale-Lock Expiry

MUST NOT silently expire an orchestration-window stale lock without Operational Administrator authorization and a `STALE_LOCK_FORCE_UNLOCKED` audit record. Automated stale-lock expiry without governance authorization is a specification defect (inherits AP-SCH9).

### AP-SF12 — No Non-Attributable Scheduler Recovery Cycles

MUST NOT allow a scheduler recovery cycle to proceed without `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`, `execution_type = recovery`, and `config_version_id` in all recovery records. Recovery cycles without complete attribution are orphaned specification defects (inherits AP-FP6; `scheduler_design.md` §8.3).

### AP-SF13 — No PII in Scheduler Resilience Observability Records

MUST NOT log raw PII (student name, email, phone number, academic transcript content) in any scheduler failure or recovery structured log record. `student_id` (UUID, opaque reference) is the permitted student-level reference (inherits AP-FP13; AP-SCH13).

### AP-SF14 — No Silent Error Swallowing in Scheduler Resilience

MUST NOT use `try { ... } catch (e) {}` semantics anywhere in the scheduler resilience layer. Every caught exception is tagged with a stable `error_class` string and emitted as a structured log record before any fallback or continuation path is taken (inherits AP-FP14).

### AP-SF15 — No Orphaned Scheduler Recovery Execution

MUST NOT allow a scheduler recovery cycle to proceed without a completion record written — even on failure. Every scheduler recovery cycle has an observable start (`scheduler_trigger_fired` with `execution_type = recovery`) and an observable end (`scheduler_recovery_cycle_complete` or `scheduler_failure_detected` with recovery context). A scheduler recovery that starts but never ends is a new orphan candidate (inherits AP-FP15).

---

## 13. ACCEPTANCE CRITERIA

---

### AC-SF1 — Deterministic Scheduler Resilience Behavior

**Given** any scheduler failure condition defined in §10.1
**When** the scheduler resilience layer processes the failure
**Then** the outcome is deterministic: the same scheduler failure input produces the same structured failure log, the same recovery action classification, and the same escalation candidacy signal — with no undocumented variation between runs

---

### AC-SF2 — Replay-Safe Scheduler Recovery Behavior

**Given** a replay-mode evaluation of a historical scheduler failure
**When** the replay simulation completes
**Then** no LIVE recovery cycle is produced; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; `fingerprint_comparison_outcome` is emitted; historical trigger timing is resolved from `historical_config_version_id`

---

### AC-SF3 — Immutable Lineage Preservation

**Given** a scheduler recovery cycle completes
**When** any record is written
**Then** no existing record in `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `state_transition_log`, or `student_timeline_events` is modified; only new append-only records are produced with `execution_type = recovery`

---

### AC-SF4 — No Hardcoded Timing in Recovery Path

**Given** a missed scheduler window is detected
**When** the scheduler resilience layer determines the missed window timing
**Then** no hardcoded timing value (e.g., "6 PM CST") is used; the expected trigger time is resolved from Config V2 Group A `outreach_daily_trigger_hour_cst`; if the Config V2 variable is missing, `UNKNOWN_V0` substitution is applied with `CONFIG_THRESHOLD_MISSING_outreach_daily_trigger_hour_cst` warning; no hardcoded fallback is used

---

### AC-SF5 — Governed Recovery Coordination (Not Immediate Execution)

**Given** a missed or orphaned scheduler window is detected
**When** the scheduler resilience layer initiates recovery
**Then** the six-step governed recovery coordination model (§7.1) is followed: FAILURE DETECTION → RECOVERY AUTHORIZATION GATE → IDEMPOTENCY CHECK → RECOVERY CYCLE ATTRIBUTION → RECOVERY ORCHESTRATION DELEGATION → OBSERVABILITY EMISSION; "trigger recovery execution immediately" semantics are not applied

---

### AC-SF6 — Idempotent Scheduler Recovery

**Given** the same scheduler recovery cycle is triggered twice (e.g., duplicate lag detection events)
**When** the second recovery cycle is evaluated
**Then** the idempotency key check returns a match; the second recovery is a no-op; `DUPLICATE_SUPPRESSED` is logged; no duplicate state transitions or outreach dispatches are produced

---

### AC-SF7 — Orphaned Window Documentation

**Given** a scheduler trigger fires but no loop completion record is emitted within the Config V2 Group I governed orphan-detection window
**When** the Observability Heartbeat Loop detects the orphan
**Then** `CYCLE_ORPHAN_DETECTED` event is emitted with `orphaned_cycle_id`; a dead-letter record is created with full attribution; escalation candidacy is generated; the orphaned cycle is not silently discarded

---

### AC-SF8 — Silent Degradation Prohibition

**Given** any scheduler domain enters a degraded state (Config V2 timing missing, provider outage, stale lock, etc.)
**When** the degradation is detected
**Then** `SCHEDULER_DEGRADED` event is emitted with `scheduler_domain`, `degradation_cause`, `degradation_onset_timestamp`; a `TRIGGER_SUPPRESSED` record is produced for each window that cannot safely fire; no trigger window is silently skipped; escalation candidacy is generated when persistence threshold is exceeded

---

### AC-SF9 — Attribution Continuity in Scheduler Recovery

**Given** any scheduler recovery action is taken
**When** the recovery record is written
**Then** `cycle_id`, `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`, `execution_mode`, and `config_version_id` are present on every recovery record; a recovery failure that cannot be traced to root cause via a single `cycle_id` is an observability defect

---

### AC-SF10 — Stale-Lock Governance

**Given** an orchestration-window idempotency record exists without a loop completion record beyond Config V2 Group I timeout
**When** the stale lock is detected
**Then** the stale lock is not silently expired by automation; a `STALE_LOCK_FORCE_UNLOCKED` audit record is created only upon explicit Operational Administrator authorization containing `scheduler_domain`, `cycle_id`, `lock_age_seconds`, `operator_identity`; no recovery cycle fires before force-unlock is confirmed

---

### AC-SF11 — Config V2 Threshold Absence Governance

**Given** a Config V2 scheduler timing variable is missing from the ACTIVE config version during scheduler evaluation
**When** the scheduler resilience layer evaluates the failure
**Then** `UNKNOWN_V0` is substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning is emitted; no hardcoded timing integer is used; the affected domain enters SCHEDULER_DEGRADED state; a `TRIGGER_SUPPRESSED` record is produced; escalation candidacy is generated

---

### AC-SF12 — Distributed Timing Drift Resolution

**Given** multiple scheduler instances attempt to trigger the same `(scheduler_domain, cycle_date, execution_mode)` window due to clock skew
**When** both trigger attempts arrive
**Then** the first INSERT to the idempotency record wins; the second instance reads the existing record and produces no cycle; `DISTRIBUTED_TIMING_DRIFT_DETECTED` is emitted if drift exceeds Config V2 Group I tolerance; no duplicate cycle is produced

---

## 14. UNRESOLVED GOVERNANCE CONCERNS

---

The following governance decisions affecting scheduler resilience behavior are deferred. They are documented here for governance review and are not blocking. The system operates without them using governed approximations noted below.

**UE-SF1: Recovery cycle escalation persistence threshold** — How many consecutive missed scheduler windows generate escalation candidacy vs self-recovering no-op? Currently: any lag detection generates escalation candidacy. Governing decision: define a persistence threshold in Config V2 Group I. (OPERATIONAL DECISION — see `failure/failure_playbook.md` UE-FP1)

**UE-SF2: Orphaned cycle recovery authorization automation** — When is an orphaned window recovered automatically vs requiring explicit Operational Administrator authorization? Currently: Operational Administrator authorization required (UE-SCH2 in `runtime/scheduler_design.md`). Governing decision: define auto-recovery conditions in Config V2. (GOVERNANCE DECISION — see `runtime/scheduler_design.md` UE-SCH2)

**UE-SF3: Dead-letter retention window for scheduler failures** — How long are scheduler dead-letter records retained? Currently: indefinite retention assumed. Governing decision: define retention window in Config V2 Group K or equivalent. (OPERATIONAL DECISION — see `failure/failure_playbook.md` UE-FP2)

**UE-SF4: Stale-lock timeout duration** — How long before an open window is considered stale-locked? Currently: governed by Config V2 Group I system timing variable (value not yet defined). Governing decision: define specific duration. (OPERATIONAL DECISION)

**UE-SF5: DEGRADED-mode missed-window recovery authorization** — When a scheduler domain recovers from DEGRADED state, are missed windows during the degraded period automatically recovered or do they require explicit operator authorization? Currently: explicit Operational Administrator authorization required. Governing decision: may be automated under Config V2 governance. (GOVERNANCE DECISION)

---

## 15. DOWNSTREAM REFERENCES

---

### 15.1 Authoritative Parent Contracts

This document is governed by and must not conflict with:

| Parent contract | Governing sections |
|---|---|
| `failure/failure_playbook.md` | §2.4 (Scheduler Failures); §4.4 (Scheduler Outage Degradation); §7.1 (Governed Recovery Coordination); §7.2 (Config V2 Thresholds); §8 (Attribution & Observability); §9 (Idempotency); §12 (AP-FP1–AP-FP15); §13 (AC-FP1–AC-FP12) |
| `runtime/scheduler_design.md` | §3 (Scheduler Modes); §4 (Canonical Scheduler Domains); §5 (Orchestration Window Governance); §6 (Config V2 Scheduling Governance); §7 (Replay & Regeneration Scheduling); §8 (Recovery & Degradation Governance); §8.3 (Recovery Attribution); §9 (Attribution & Observability); §10 (Authority Boundaries); AP-SCH1–AP-SCH13 |
| `runtime/system_loop.md` | §10.1 (Deterministic Degradation Principles); §10.5 (Scheduler Lag Governance); §11.1 (Correlation ID Propagation); §11.2 (Runtime Attribution Requirements) |
| `spec/04_idempotency_concurrency.md` | §2 (Core Principles); §2.1 (Idempotency First) |
| `spec/06_observability_operations.md` | Structured log requirements; correlation ID propagation; governance telemetry vs operational telemetry |
| `spec/09_security_privacy.md` | PII protection in scheduler observability records |

---

### 15.2 Sibling Contracts

This document shares governance parentage with:

| Sibling contract | Shared parent governance |
|---|---|
| `failure/ghl_failures.md` | `failure/failure_playbook.md` §2.2 (Provider Failures); AP-FP1–AP-FP15 |
| `failure/llm_failures.md` | `failure/failure_playbook.md` §2.3 (AI Failures); AP-FP9; AP-FP10 |
| `runtime/daily_outreach_flow.md` | `runtime/system_loop.md`; `runtime/scheduler_design.md` §4.1 |
| `runtime/retry_cycle_flow.md` | `runtime/system_loop.md`; `runtime/scheduler_design.md` §4.2 |

---

### 15.3 Directive Dependencies

| Directive | Scheduler resilience dependency |
|---|---|
| `directives/outreach_retry_policy.md` | Retry authorization during recovery cycles; retry budget protection semantics |
| `directives/outreach_eligibility_rules.md` | Eligibility assessment during recovery cycle evaluation |
| `directives/ghl_integration_contract.md` | Circuit breaker governance affecting scheduler trigger authorization; provider outage detection |
| `directives/llm_processing_contract.md` | AI provider availability affecting AI Refresh Scheduler trigger decisions |
| `directives/escalation_rules.md` | Escalation candidacy generation on scheduler failure conditions |

---

## END OF FILE
