# tests/load_tests.md

---

## LAYER 6 — GOVERNANCE-SAFE ORCHESTRATION LOAD CERTIFICATION ARCHITECTURE

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governance-safe orchestration architecture established in `tests/test_scenarios.md` (the authoritative parent governance validation contract), `tests/edge_cases.md` (the authoritative parent governance edge-condition certification contract), `runtime/system_loop.md`, `runtime/scheduler_design.md`, `runtime/daily_outreach_flow.md`, `runtime/retry_cycle_flow.md`, `failure/failure_playbook.md`, `failure/scheduling_failures.md`, `failure/ghl_failures.md`, `failure/llm_failures.md`, all seven rewritten directive files, and `spec/01_requirements.md` through `spec/09_security_privacy.md`. The previous version described MVP-era performance and load validation: hardcoded concurrency limits ("50 concurrent executions"), simplistic throughput targets ("50 concurrent executions"), simplistic retry-load assumptions ("retry cycle runs"), simplistic scheduler load semantics ("1,000 eligible students"), simplistic queue saturation assumptions, and hardcoded worker behavior. Those patterns are incompatible with the governance-safe orchestration model. This file is now the **canonical governance-safe orchestration load certification architecture** for the Student Success Intelligence Platform.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

This file is the **governance-safe orchestration load certification architecture** for the Student Success Intelligence Platform. It defines:

* How governance conformance is validated under orchestration saturation, concurrent load, and replay-vs-LIVE stress
* What invariants must hold for orchestration to be considered governance-safe under peak load conditions
* How replay-safe concurrency is certified under scale
* How immutable lineage guarantees are preserved under bulk orchestration stress
* How Config V2 governance is validated under concurrent activation and load
* How provider-boundary governance is preserved under saturation and outage storms
* How AI advisory-only governance is preserved under inference backlog and stale conditions
* How deterministic degradation is validated under simultaneous multi-domain failure at scale
* How attribution continuity is certified under saturation conditions
* How idempotent orchestration is validated under duplicate-storm and concurrent-loop conditions
* How scheduler-window isolation is preserved under drift, orphan-window, and saturation conditions
* How observability governance is preserved under log-pipeline saturation

This document is the authoritative load certification contract for all orchestration domains. It **inherits** from and **must not contradict** `tests/test_scenarios.md` or `tests/edge_cases.md`. Where a governance principle is stated in those parent contracts, this file validates that the principle holds under saturation and high-concurrency conditions.

---

### 1.2 What Load Certification Is NOT

Load certification in the governance-safe orchestration model is explicitly **NOT**:

* **Throughput benchmarking** — "the system processes N students per second" is not a governance load assertion; the governance load assertion is "orchestration governance conformance is preserved across all N students regardless of batch size"
* **Worker saturation testing** — assertions that a specific number of workers saturate at a fixed queue depth are specification violations; concurrency governance resolves dynamically from Config V2
* **Simplistic queue stress testing** — "events queued, processed eventually" is not a governance outcome; the governance outcome is "all queued events carry attribution, idempotency protections hold, and no duplicate LIVE effect is produced under saturation"
* **LIVE-effect load verification** — no load scenario may assert that LIVE outbound communications occurred at volume; load tests assert that governance-authorized orchestration paths were traversed with correct attribution at scale
* **Hardcoded concurrency expectations** — any assertion of the form "max 50 processed concurrently" is a specification violation; concurrency governance resolves dynamically from Config V2 Group A
* **Hardcoded throughput targets** — fixed latency or throughput targets that are not derived from Config V2 governance are specification violations
* **Direct provider execution assertions** — no load test may assert that a provider API was called directly at volume; load tests assert that `ProviderOrchestrationAssessment` records were produced with correct `governance_scope` values
* **Replay-triggered LIVE load assertions** — no load test may assert that a replay-mode execution at scale produced LIVE effects; replay must suppress all LIVE outputs under all volume conditions
* **Mutable FINALIZED_COPY load assertions** — no load test may assert that `warehouse.snapshot_ai_narratives` records were modified or overwritten under bulk finalization or AI refresh load
* **Silent fallback load validation** — "fallback logic applied at scale" is not a valid governance load outcome; every degraded execution path under load must be observable and attributable

---

### 1.3 Inheritance from Parent Contracts

This file inherits the following governance contracts in full from `tests/test_scenarios.md` and `tests/edge_cases.md`:

| Inherited governance contract | Parent document | Section |
|---|---|---|
| Prohibited validation semantics | `tests/test_scenarios.md` | §2 |
| Governance preconditions | `tests/test_scenarios.md` | §3 (GPC-1 through GPC-5) |
| Orchestration Intent governance | `tests/test_scenarios.md` | §4 (OIG-1 through OIG-5) |
| Config V2 threshold resolution | `tests/test_scenarios.md` | §5 (CV2-1 through CV2-4) |
| SHADOW-vs-LIVE behavior boundaries | `tests/test_scenarios.md` | §6 (SVL-1 through SVL-3) |
| Replay orchestration governance | `tests/test_scenarios.md` | §7 (ROS-1 through ROS-5) |
| Retry orchestration governance | `tests/test_scenarios.md` | §8 (ROG-1 through ROG-5) |
| AI governance | `tests/test_scenarios.md` | §9 (AIG-1 through AIG-5) |
| Provider boundary governance | `tests/test_scenarios.md` | §10 (PBG-1 through PBG-5) |
| State transition governance | `tests/test_scenarios.md` | §11 (STG-1 through STG-4) |
| Resilience governance | `tests/test_scenarios.md` | §12 (RGS-1 through RGS-5) |
| Concurrency and idempotency | `tests/test_scenarios.md` | §13 (CID-1 through CID-4) |
| Attribution continuity | `tests/test_scenarios.md` | §14 (ATT-1 through ATT-5) |
| Degradation validation | `tests/test_scenarios.md` | §15 (DEG-1 through DEG-5) |
| Immutable lineage | `tests/test_scenarios.md` | §16 (IML-1 through IML-4) |
| Governance invariants | `tests/test_scenarios.md` | §17 (INV-1 through INV-7) |
| Replay edge conditions | `tests/edge_cases.md` | §4 (ECR-1 through ECR-5) |
| Regeneration integrity conditions | `tests/edge_cases.md` | §5 (ECRG-1 through ECRG-3) |
| Attribution-loss conditions | `tests/edge_cases.md` | §6 (ECA-1 through ECA-5) |
| Stale AI conditions | `tests/edge_cases.md` | §7 (ECAI-1 through ECAI-4) |
| Duplicate orchestration conditions | `tests/edge_cases.md` | §8 (ECDO-1 through ECDO-4) |
| Config V2 activation race conditions | `tests/edge_cases.md` | §9 (ECCV-1 through ECCV-4) |
| Scheduler orphan-window conditions | `tests/edge_cases.md` | §10 (ECSO-1 through ECSO-4) |
| Provider sync lag conditions | `tests/edge_cases.md` | §11 (ECPL-1 through ECPL-3) |
| Degradation escalation conditions | `tests/edge_cases.md` | §12 (ECDE-1 through ECDE-5) |
| Immutable lineage protection conditions | `tests/edge_cases.md` | §13 (ECIL-1 through ECIL-4) |
| Governance invariant stress tests | `tests/edge_cases.md` | §14 (ECINV-1 through ECINV-FAD3) |

The parent contracts define governance behavior under nominal and edge-condition inputs. This file defines governance certification under saturation, peak-volume, and concurrent-storm conditions. All governance invariants from both parent contracts must hold under the saturation conditions defined here.

---

### 1.4 Load Certification Principles

---

#### 1.4.1 Governance Conformance Under Saturation

Every load certification scenario validates that the governance contract defined in the canonical source documents was honored at volume. Same inputs under the same execution mode and the same ACTIVE config version must produce the same governance-conformant outputs regardless of batch size or concurrent load.

---

#### 1.4.2 Attribution Completeness Under Load

Every load certification scenario that validates orchestration output at scale must include an attribution assertion. An orchestration record without `correlation_id`, `execution_mode`, `execution_type`, and `config_version_id` is a governance defect regardless of whether it was produced in a batch of 1 or a batch of 10,000.

---

#### 1.4.3 Deterministic Degradation Under Saturation

When orchestration domains degrade under load (provider unavailability, AI backlog, sync lag overflow, observability pipeline saturation), the degradation path must be deterministic and observable. Non-deterministic degradation under load is a governance defect regardless of functional throughput.

---

#### 1.4.4 Config V2 Governed Load Semantics

All load-relevant thresholds — batch sizes, concurrency windows, retry windows, scheduler cadence, sync lag governance thresholds, AI TTL windows — resolve dynamically from the ACTIVE Config V2 version. No load certification scenario may assert a hardcoded threshold as the governance authority.

---

#### 1.4.5 Replay-LIVE Isolation Under Scale

Replay execution at scale must never produce LIVE effects regardless of volume, concurrency, or degradation state. The replay-LIVE isolation guarantee (AP-RT2) is load-invariant: it holds for a single replay record and for a bulk replay sweep of 10,000 records identically.

---

## 2. PROHIBITED LOAD CERTIFICATION SEMANTICS

---

The following validation patterns are **prohibited** in all load certification scenarios in this document. Their presence is a governance contract violation equivalent to the prohibitions in `tests/test_scenarios.md` §2 and `tests/edge_cases.md` §2.

| Prohibited load pattern | Governance violation | Required replacement |
|---|---|---|
| `50 concurrent executions` | Hardcoded concurrency limit | Config V2 Group A concurrency variable resolution — no hardcoded limit in any load scenario |
| `system throttles to 50 concurrent` | Hardcoded throttle assumption | Concurrency governance resolves from Config V2; throttle is dynamically governed |
| `batch processing applied` | Underspecified batch assertion | `OrchestrationIntent` records produced with correct `config_version_id` and `correlation_id` for each student in the batch |
| `queue handles overflow` | Silent queue overflow assertion | Overflow records must carry idempotency keys, attribution fields, and observable dead-letter entries |
| `events processed eventually` | Non-attributable eventual processing | Each event record carries `correlation_id`, `execution_type`, and governance-compliant `outcome` |
| `retry processed correctly` | Underspecified retry load assertion | `RetryPolicyAssessment` records with `config_version_id`, `retry_authorized`, and `causation_id` linkage |
| `system throttles requests / retries appropriately` | Silent provider throttle assertion | `RATE_LIMIT_ENCOUNTERED` event + `error_class = RateLimitError` + governed retry schedule with Config V2 backoff |
| `no duplicate processing` | Underspecified deduplication load assertion | `processed_events` idempotency gate + `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit records for each suppressed duplicate |
| `no crashes` | Non-observability load outcome | All failure classes produce structured log records; no exception is silently swallowed |
| `no failure cascade` | Vague cascade prevention assertion | Domain-isolated degradation with independent structured `error_class` events per failure domain |
| `load distributed / no duplicate execution` | Underspecified horizontal-scale assertion | Shared idempotency store enforces exactly-one-execution across distributed instances; `DUPLICATE_ORCHESTRATION_SUPPRESSED` per duplicate |
| `performance maintained` | Non-governance throughput assertion | Governance conformance preserved: `correlation_id` non-null, `config_version_id` non-null, degradation observable |
| Replay producing LIVE effects at scale | Replay governance violation | All replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` regardless of volume |
| `FINALIZED_COPY` mutated under bulk load | Immutable lineage violation under load | Bulk operations must produce `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` or `IMMUTABLE_RECORD_MUTATION_BLOCKED` events for each suppressed mutation attempt |
| `fallback logic applied` at scale | Silent bulk fallback assertion | Specific degradation event class + `DEGRADED` annotation + structured log per affected record |

---

## 3. LOAD CERTIFICATION DOMAINS

---

This file defines ten governance-oriented load certification domains. Each domain corresponds to a governance boundary that must hold not only under nominal and edge-condition inputs (validated in the parent contracts) but also under the high-volume, concurrent, and saturation conditions defined below.

| Domain | Code prefix | Governance boundary stressed under load |
|---|---|---|
| Orchestration concurrency saturation | LCS | AP-RT10, CID-1, CID-2, INV-5 |
| Replay-vs-LIVE isolation under load | LCR | AP-RT2, ROS-1, CID-3, INV-4 |
| Scheduler-window saturation | LCSCH | AP-SCH3, ECSO-1, ECSO-2, ATT-3 |
| Retry-storm governance | LCRSG | ROG-1 through ROG-5, CV2-1, CV2-2 |
| Duplicate orchestration storms | LCDO | CID-2, ECDO-1, ROG-5, PBG-3 |
| Provider synchronization backlog | LCPB | PBG-5, ECPL-1, ECPL-3, DEG-4 |
| AI inference backlog | LCAI | AIG-1 through AIG-5, ECAI-3, DEG-2 |
| Attribution continuity under stress | LCAT | ATT-1 through ATT-5, INV-5, ECA-1 |
| Degradation escalation under saturation | LCDE | RGS-1 through RGS-5, ECDE-1, DEG-1 |
| Observability saturation governance | LCOS | RGS-5, ECDE-2, AC-SCH10 |

Each domain section defines the saturation conditions, the load certification scenarios, and the prohibited assertions specific to that domain.

---

## 4. ORCHESTRATION CONCURRENCY SATURATION

---

### LCS-1 — Batch Orchestration: Config V2 Governed Concurrency, Zero Null attribution

**Governance contract:** `runtime/system_loop.md` §5.2, CV2-3, INV-5, INV-7

**Saturation condition:** A large evaluation batch is processed under full concurrency governed by Config V2 Group A. Every record produced must carry non-null `correlation_id` and `config_version_id`.

**Given:**

* Config V2 Group A concurrency variable is present and ACTIVE
* A large evaluation batch (volume governed by Config V2 Group A batch-size variable) is submitted for orchestration
* `execution_mode = LIVE`
* `correlation_id` is generated at loop start

**When:**

* Orchestration Evaluation Loop processes the full batch under Config V2 governed concurrency

**Then:**

* Concurrency limit applied is resolved from Config V2 Group A — no hardcoded limit governs batch execution
* Every `OrchestrationIntent` record in the batch carries `correlation_id` matching the cycle `correlation_id`
* Every `OrchestrationIntent` record carries `config_version_id` matching the ACTIVE config version
* No record in `student_timeline_events`, `processed_events`, or `state_transition_log` for this cycle has `correlation_id IS NULL`
* No record has `config_version_id IS NULL`
* Idempotency gate fires for every student before intent production — no student receives two `OrchestrationIntent` records in the same cycle
* Cycle completion record documents total batch size, total succeeded, total skipped, `correlation_id`

**Prohibited assertions:**

* Concurrency limit was derived from a hardcoded constant (e.g., `50 concurrent`)
* Any record in the batch has `correlation_id IS NULL` (INV-5)
* Any record in the batch has `config_version_id IS NULL` (INV-7)
* A student received two `OrchestrationIntent` records in the same cycle

---

### LCS-2 — Concurrent Loop Instances: Duplicate LIVE Orchestration Prevention Under Scale

**Governance contract:** `runtime/system_loop.md` AP-RT10, `spec/04_idempotency_concurrency.md` §2.2, CID-2, ECDO-1

**Saturation condition:** Multiple concurrent Orchestration Evaluation Loop instances run against the same student candidate set. The idempotency gate must prevent duplicate `OrchestrationIntent` records regardless of the number of concurrent instances.

**Given:**

* Multiple concurrent Orchestration Evaluation Loop instances select an overlapping student candidate set
* All instances have access to the shared `processed_events` idempotency store
* `execution_mode = LIVE`

**When:**

* All concurrent instances race to produce `OrchestrationIntent` records for overlapping students

**Then:**

* For each student, exactly one `OrchestrationIntent` record is produced — the first INSERT to `processed_events` wins (database-level unique constraint)
* All losing concurrent instances produce `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit records with `suppressed_by = IDEMPOTENCY_KEY_CONFLICT`
* No student receives duplicate LIVE outbound dispatch across concurrent instances
* Total `OrchestrationIntent` count across all instances equals the count of unique students — not the count of instances × students
* Each suppression event is observable and carries `correlation_id`

**Prohibited assertions:**

* Any student received more than one `OrchestrationIntent` record in the same cycle across concurrent instances
* Duplicate suppression was silent without `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit records
* Two concurrent instances produced duplicate `ghl_messages` records for the same student

---

### LCS-3 — Orphaned Cycle Prevention Under Concurrent Saturation

**Governance contract:** `runtime/system_loop.md` AP-RT15, OIG-5

**Saturation condition:** Under high concurrent load, a runtime loop cycle encounters a fatal error mid-execution. The orphan prevention guarantee must hold regardless of concurrent instance count.

**Given:**

* Orchestration Evaluation Loop cycle begins — `correlation_id` generated and recorded
* Concurrent load is at Config V2-governed maximum concurrency
* A fatal error is encountered mid-batch

**When:**

* The loop encounters the fatal error under saturation conditions

**Then:**

* A structured completion log is emitted with `outcome = failure` and the stable `error_class`
* A dead-letter record is written for every unprocessed student candidate remaining in the batch
* `correlation_id` is present in all failure records and all dead-letter records
* The cycle does not terminate silently (AP-RT15)
* Observability Heartbeat Loop detects no orphaned `cycle_id` for this cycle
* Other concurrent loop instances are not blocked by this instance's failure

**Prohibited assertions:**

* Cycle terminated without emitting a completion log under saturation
* Dead-letter records were missing `correlation_id`
* One loop instance's fatal failure silently blocked other concurrent instances

---

### LCS-4 — Compliance Hold: Per-Student Block Does Not Propagate Under Bulk Load

**Governance contract:** `runtime/system_loop.md` §10.2, CID-4, `spec/04_idempotency_concurrency.md` Domain 6

**Saturation condition:** Under a large evaluation batch, one or more students have active compliance holds. Per-student compliance blocks must not suppress orchestration evaluation globally at any batch size.

**Given:**

* A large evaluation batch contains students with and without active compliance holds
* `execution_mode = LIVE`
* Compliance hold count is a subset of the full batch

**When:**

* Orchestration Evaluation Loop evaluates the full batch

**Then:**

* For each compliance-held student: `COMPLIANCE_HOLD_DISPATCH_BLOCKED` event emitted with `correlation_id`
* All non-held students are evaluated and delegated without interference from the compliance-held students
* Compliance hold suppression does not cascade to non-held students under any batch size
* Total `OrchestrationIntent` count for non-held students matches expectation derived from eligibility governance
* Per-compliance-hold block is individually attributable

**Prohibited assertions:**

* Compliance hold for any student blocked orchestration evaluation globally across the batch
* Per-student compliance suppression was silent without an observable event

---

## 5. REPLAY-VS-LIVE ISOLATION UNDER LOAD

---

### LCR-1 — Bulk Replay Under Load: Zero LIVE Effects

**Governance contract:** `runtime/system_loop.md` §7.2, AP-RT2, AC-RT2, ROS-1, INV-4

**Saturation condition:** A bulk replay sweep covering a large historical student population runs concurrently with an active LIVE orchestration cycle. Replay must suppress all LIVE outputs regardless of replay volume.

**Given:**

* `execution_type = replay` — bulk replay sweep covering a large historical population
* LIVE batch cycle is running concurrently
* `historical_config_version_id` provided for all replayed students

**When:**

* Bulk replay sweep executes alongside the active LIVE cycle

**Then:**

* Zero LIVE outbound dispatches are produced by the replay sweep — `ProviderOrchestrationAssessment.outbound_suppressed = true` for every replayed student
* Zero LIVE state transitions are produced by the replay sweep
* Zero LIVE AI inferences are triggered by the replay sweep — `AIAssessment.ai_blocked = true` for every replayed student
* All replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`
* LIVE cycle outputs carry `governance_scope = AUTHORIZED` — they are not tagged `REPLAY_ONLY` by replay activity
* Query `ghl_messages` for `execution_type = replay` after sweep completion — expected: zero records
* Query `state_transition_log` for transitions produced by `execution_type = replay` — expected: zero records

**Prohibited assertions:**

* Any LIVE effect was produced by any replayed student regardless of replay volume
* LIVE cycle outputs were contaminated with `REPLAY_ONLY` scope tags
* Replay sweep volume affected LIVE cycle concurrency governance

---

### LCR-2 — Replay Idempotency Under Concurrent Bulk Replay Triggers

**Governance contract:** `runtime/system_loop.md` §4.8, §11.5, ROS-4, ECRG-2

**Saturation condition:** Multiple concurrent replay triggers arrive for the same `(source_artifact_id, replay_cycle_id)` tuple — simulating scheduler drift or double-submission under load.

**Given:**

* Multiple concurrent replay triggers with identical `(source_artifact_id = SA1, replay_cycle_id = RC1)` tuple
* Replay Orchestration Scheduler evaluates all concurrent triggers

**When:**

* All concurrent triggers race to initiate the same replay cycle

**Then:**

* First replay trigger wins — idempotency gate on `(source_artifact_id, replay_cycle_id)` fires
* All subsequent triggers for the same tuple are suppressed
* `TRIGGER_SUPPRESSED` records emitted with `suppression_reason = DUPLICATE_REPLAY_KEY` for each suppressed trigger
* Only one replay cycle is initiated for `(SA1, RC1)`
* No LIVE effects are produced by any instance of the replay cycle

**Prohibited assertions:**

* Multiple replay cycles executed for the same `(source_artifact_id, replay_cycle_id)` tuple
* Duplicate replay suppression was silent without `TRIGGER_SUPPRESSED` records

---

### LCR-3 — Replay Concurrency Isolation From LIVE Batch Under Saturation

**Governance contract:** `runtime/scheduler_design.md` §5.3, CID-3, ECR-3

**Saturation condition:** Both a LIVE batch cycle and a bulk replay sweep operate at high concurrency simultaneously. The two execution namespaces must remain isolated at any concurrent volume.

**Given:**

* LIVE batch cycle with `execution_type = original`, `correlation_id = COR-LIVE-BULK` running at Config V2 governed concurrency
* Bulk replay sweep with `execution_type = replay`, multiple `replay_cycle_id` values running concurrently
* Both cycles process some of the same student population (historical context vs. current context)

**When:**

* Both cycles run concurrently at peak saturation

**Then:**

* Replay cycle uses separate idempotency namespace `(source_artifact_id, replay_cycle_id)` — does not acquire LIVE window idempotency keys
* LIVE batch idempotency namespace `(scheduler_domain, cycle_date)` is not acquired by any replay cycle
* Replay outputs carry `governance_scope = REPLAY_ONLY` — they are not consumed as LIVE orchestration results
* LIVE outputs carry `governance_scope = AUTHORIZED` — they are not affected by concurrent replay volume
* Both cycles emit independent completion records with distinct `correlation_id` values

**Prohibited assertions:**

* Replay cycle acquired any LIVE window idempotency key
* LIVE cycle throughput or governance conformance was affected by concurrent replay volume
* Replay outputs were consumed as LIVE orchestration results under saturation

---

### LCR-4 — Bulk Regeneration Under Load: Zero External Calls

**Governance contract:** `spec/01_requirements.md` FAD-2, IML-2, ROS-5, ECRG-1, ECINV-FAD2

**Saturation condition:** A bulk report regeneration sweep runs for a large historical cohort population. The absolute prohibition on external API calls during regeneration (FAD-2) must hold at any regeneration volume.

**Given:**

* Report Generation Scheduler fires in `execution_type = regeneration` for a large historical cohort population
* `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` are accessible for all cohort records

**When:**

* Report Generation Loop executes bulk regeneration

**Then:**

* Zero SQL Server reads are made during regeneration — all data sourced from warehouse
* Zero AI provider calls are made during regeneration
* Zero GHL API calls are made during regeneration
* All regenerated reports are produced from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` exclusively (FAD-2)
* Each regeneration job record carries `execution_type = regeneration`, `output_identical` flag, `correlation_id`
* Bulk regeneration run produces one regeneration job record per `(cohort_id, report_month)` — not duplicates (idempotency gate active)

**Prohibited assertions:**

* Any external API call occurred during any regeneration cycle regardless of cohort population size
* `output_identical` flag was absent from any regeneration job record
* Duplicate regeneration job records were produced for the same `(cohort_id, report_month)` under concurrent load

---

## 6. SCHEDULER-WINDOW SATURATION

---

### LCSCH-1 — Scheduler Drift Under High Trigger Frequency: Idempotency Gate Holds

**Governance contract:** `runtime/scheduler_design.md` §5.2, ECSO-2, AP-SCH3, CID-1

**Saturation condition:** Scheduler clock drift or rapid re-trigger causes the same `cycle_date` to be fired multiple times in rapid succession. The idempotency gate must prevent multiple orchestration loops from starting for the same window.

**Given:**

* Orchestration Evaluation Scheduler fires for `cycle_date = CURRENT` — trigger record written with `cycle_id = SCH-N`
* Scheduler drift causes multiple rapid re-fires for the same `cycle_date`
* Each re-fire generates a new candidate `cycle_id`

**When:**

* All re-fire triggers are evaluated by the scheduler idempotency gate

**Then:**

* Idempotency gate on `(scheduler_domain = orchestration_evaluation, cycle_date)` detects the existing trigger record for each re-fire
* Each duplicate trigger is suppressed with `TRIGGER_SUPPRESSED` record carrying `suppression_reason = DUPLICATE_CYCLE_DATE_WINDOW` and `duplicate_of = SCH-N`
* Exactly one Orchestration Evaluation Loop is initiated per `cycle_date`
* `SCHEDULER_DRIFT_DETECTED` event emitted with `drift_magnitude` for each drift episode
* Suppression records are individually attributable — suppression is never silent

**Prohibited assertions:**

* More than one Orchestration Evaluation Loop executed for the same `cycle_date`
* Any duplicate trigger suppression was silent without a `TRIGGER_SUPPRESSED` record

---

### LCSCH-2 — Scheduler Orphan Detection Under Multi-Domain Load

**Governance contract:** `runtime/scheduler_design.md` §8.2, RGS-2, ECSO-1

**Saturation condition:** Under high multi-domain scheduler load, orphan window detection must identify missed cycles accurately without producing false positives for cycles that are still in-flight.

**Given:**

* Multiple scheduler domains are active simultaneously (orchestration evaluation, retry, AI refresh, snapshot finalization, SQL Server sync, report generation, observability heartbeat)
* One or more scheduler domains miss a trigger window due to process crash under load
* Orphan detection runs in the next cycle window

**When:**

* Orphan detection scans for missed windows across all scheduler domains

**Then:**

* For each missed window: `SCHEDULER_ORPHAN_WINDOW_DETECTED` event emitted with `orphaned_cycle_date`, `scheduler_domain`, `detection_cycle_date`, `lag_hours`
* Recovery candidacy records are created for missed windows — recovery cycles are NOT automatically triggered (Operational Administrator authorization required)
* Active in-flight cycles are not identified as orphans — orphan detection correctly distinguishes in-flight from missed
* Scheduler domains with successful triggers are not affected by orphan detection for other domains
* The current trigger cycle for each domain proceeds normally — orphan detection does not block active processing

**Prohibited assertions:**

* Recovery cycles were automatically triggered without Operational Administrator authorization
* Orphan detection produced false positives for in-flight cycles
* Orphan detection was silent for genuinely missed windows

---

### LCSCH-3 — Scheduler Attribution Continuity Under Multi-Domain Saturation

**Governance contract:** `runtime/scheduler_design.md` §9.1, ATT-3, AC-SCH8

**Saturation condition:** Under multi-domain scheduler saturation, all triggered orchestration loops must propagate scheduler `cycle_id` to their loop start records regardless of concurrent scheduler load.

**Given:**

* Multiple scheduler domains fire near-simultaneously
* Each scheduler domain generates a `cycle_id` in its trigger record
* Each triggered orchestration loop begins independently

**When:**

* All triggered orchestration loops run concurrently

**Then:**

* Each loop start record includes the `cycle_id` from its scheduler trigger record
* Each loop generates its own `correlation_id` for downstream attribution
* Scheduler completion records for each domain include both `cycle_id` and `correlation_id`
* Cross-domain `cycle_id` mixing does not occur — each loop's attribution lineage is traceable to its own scheduler trigger
* Forensic chain is intact for each domain: `SCH-N → COR-N → OrchestrationIntents → processed_events`

**Prohibited assertions:**

* Any loop start record was missing `cycle_id` under multi-domain saturation
* Cross-domain `cycle_id` values were mixed in any loop record
* Attribution discontinuity was silent without observable events

---

### LCSCH-4 — Observability Heartbeat Continues Under Maintenance-Mode Saturation

**Governance contract:** `runtime/scheduler_design.md` §3.3, GPC-3, ECSO-4

**Saturation condition:** Under `execution_mode = MAINTENANCE` with all orchestration scheduler domains suppressed, the Observability Heartbeat Scheduler must continue firing at its governance-governed cadence.

**Given:**

* `execution_mode = MAINTENANCE`
* All orchestration-domain triggers are suppressed with `TRIGGER_SUPPRESSED` records
* Observability Heartbeat Scheduler evaluates in every window

**When:**

* Observability Heartbeat Scheduler fires during MAINTENANCE mode saturation

**Then:**

* Heartbeat trigger is NOT suppressed — it is the governance-defined exception to MAINTENANCE mode suppression
* Heartbeat trigger record carries `execution_mode = MAINTENANCE`, `scheduler_domain = observability_heartbeat`, `trigger_status = ACTIVE`
* `MAINTENANCE_MODE_EXCEPTION_HEARTBEAT_ACTIVE` annotation present in each heartbeat trigger record
* System health monitoring continues without interruption regardless of MAINTENANCE duration
* Heartbeat cadence is governed by Config V2 — no hardcoded interval

**Prohibited assertions:**

* Observability Heartbeat Scheduler was suppressed during MAINTENANCE mode at any load level
* Heartbeat trigger records were missing `execution_mode = MAINTENANCE` annotation

---

## 7. RETRY-STORM GOVERNANCE

---

### LCRSG-1 — Retry Storm: Config V2 Governed Threshold Protection Holds at Scale

**Governance contract:** `runtime/system_loop.md` §6.1, §6.2, CV2-1, CV2-2, ROG-1, ROG-2

**Saturation condition:** A large population of students in `NO_RESPONSE` state becomes eligible for retry simultaneously. Config V2 retry governance must hold for every student in the storm.

**Given:**

* A large population of students all have state = `NO_RESPONSE`
* Config V2 Group A `outreach_retry_window_days` has elapsed for all students
* Config V2 Group A `outreach_max_retry_attempts` has NOT been reached for any student
* `execution_mode = LIVE`

**When:**

* Retry Orchestration Loop evaluates the full retry-eligible population

**Then:**

* For each student: `RetryPolicyAssessment.retry_authorized = true` with `config_version_id` matching the ACTIVE config version
* No `RetryPolicyAssessment` record uses a hardcoded threshold value — all reference Config V2 Group A
* `OrchestrationIntent.intent_type = RETRY_OUTREACH` produced for each authorized student
* Each `RETRY_OUTREACH` intent carries `causation_id` linking to the prior `OrchestrationIntent` for that student
* Each intent is persisted to `student_timeline_events` before execution delegation
* Idempotency gate prevents duplicate `RETRY_OUTREACH` records for any student

**Prohibited assertions:**

* Any `RetryPolicyAssessment` was evaluated against a hardcoded `MAX_ATTEMPTS` constant
* Any `RETRY_OUTREACH` intent was produced without `causation_id`
* Any `RetryPolicyAssessment` was produced without `config_version_id`

---

### LCRSG-2 — Retry Exhaustion Storm: Escalation Candidacy at Scale

**Governance contract:** `runtime/system_loop.md` §6.5, ROG-3, `failure/failure_playbook.md`

**Saturation condition:** A large population of students simultaneously reaches retry exhaustion. Escalation candidacy signals must be produced for every exhausted student without governance shortcuts.

**Given:**

* A large population of students all have `contact_attempt ≥ outreach_max_retry_attempts` (Config V2 Group A)
* `RetryPolicyAssessment.retry_authorized = false` with `reason = RETRY_EXHAUSTED` for each
* `execution_mode = LIVE`

**When:**

* Retry Orchestration Loop processes the exhausted population

**Then:**

* For each student: `RETRY_EXHAUSTED` orchestration record produced and persisted
* For each student: escalation candidacy signal produced with `escalation_type = RETRY_EXHAUSTED` and `correlation_id`
* No further `RETRY_OUTREACH` intent is produced for any exhausted student
* Exhaustion records carry `config_version_id` matching the ACTIVE config version
* Exhaustion is observable for every student — no silent termination
* Total escalation candidacy signal count matches the exhausted population count

**Prohibited assertions:**

* Any exhausted student's state was silently transitioned to CLOSED without an escalation candidacy signal
* Any retry dispatch was produced for a student after `RETRY_EXHAUSTED`
* Escalation candidacy signals were produced without `correlation_id`

---

### LCRSG-3 — Retry Budget Protection Storm: Provider Outage, Full Retry Population Unaffected

**Governance contract:** `runtime/system_loop.md` §10.3, PBG-1, RGS-3, ECDE-4

**Saturation condition:** A large retry-eligible population is evaluated while the GHL provider circuit breaker is OPEN. The retry budget must not be consumed for any student whose dispatch was blocked by provider outage.

**Given:**

* GHL provider circuit breaker state = OPEN
* A large population of students with state = `NO_RESPONSE` are evaluated by Retry Orchestration Loop
* All students have elapsed `outreach_retry_window_days` (Config V2 Group A)
* All students have `contact_attempt < outreach_max_retry_attempts` (Config V2 Group A)

**When:**

* Retry Orchestration Loop evaluates the full retry-eligible population under provider outage

**Then:**

* For each student: `RetryPolicyAssessment.retry_authorized = true` (policy allows retry)
* For each student: `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE` (dispatch blocked by outage)
* For each student: `contact_attempt` is NOT incremented
* For each student: retry budget is NOT consumed
* For each student: `RETRY_BUDGET_PROTECTED_PROVIDER_UNAVAILABLE` event emitted
* `PROVIDER_OUTAGE` structured log event emitted once per cycle — not once per student
* Provider failure escalation candidacy generated once per cycle

**Prohibited assertions:**

* Any student's `contact_attempt` was incremented when the provider was unavailable
* Retry budget was consumed for any student during the provider outage
* `PROVIDER_OUTAGE` event was emitted once per student rather than once per cycle

---

### LCRSG-4 — Retry Window Enforcement Under Rapid Re-trigger: No Early Retry at Scale

**Governance contract:** `runtime/system_loop.md` §6.2, ROG-2, CV2-2

**Saturation condition:** Scheduler drift or rapid re-trigger causes the Retry Orchestration Loop to evaluate the same retry-eligible population before the Config V2 Group A retry window has elapsed.

**Given:**

* A large population of students all have state = `NO_RESPONSE`
* `outreach_retry_window_days` has NOT elapsed since last contact (Config V2 Group A)
* Scheduler drift causes a rapid re-trigger of the Retry Orchestration Loop

**When:**

* Retry Orchestration Loop evaluates the full population on rapid re-trigger

**Then:**

* For each student: `RetryPolicyAssessment.retry_authorized = false` with `reason = RETRY_WINDOW_NOT_ELAPSED` and `config_version_id`
* No `RETRY_OUTREACH` intent is produced for any student in this cycle
* Skip records emitted for each student with `skip_reason = RETRY_WINDOW_NOT_ELAPSED`
* Retry timing assertion references the Config V2 variable — no hardcoded `24h` constant used for any student

**Prohibited assertions:**

* Any retry was authorized based on a hardcoded timing constant
* Any `RETRY_OUTREACH` intent was produced for a student whose retry window had not elapsed
* Skip records were absent for any student whose retry was blocked

---

## 8. DUPLICATE ORCHESTRATION STORMS

---

### LCDO-1 — Webhook Storm: Duplicate Event Suppression at Scale

**Governance contract:** `runtime/system_loop.md` §10.6, PBG-3, `spec/04_idempotency_concurrency.md`, ECDO-2

**Saturation condition:** GHL delivers a large volume of duplicate webhook events simultaneously — simulating a provider retry storm or webhook replay event. The deduplication gate must suppress all duplicates without state management service calls.

**Given:**

* GHL delivers a large volume of webhook events, many of which are duplicates of previously processed events
* Processed `event_id` values are present in `processed_events` for all prior events
* Concurrent duplicate deliveries arrive for many of the same `event_id` values

**When:**

* Webhook ingestion service processes the full webhook storm

**Then:**

* For each previously processed `event_id`: `processed_events` dedup lookup fires before any state management service call
* Duplicate events are detected and suppressed — `DUPLICATE_EVENT_SUPPRESSED` audit log entry produced for each duplicate
* Zero state management service calls are made for duplicate events
* No duplicate state transitions are produced
* Non-duplicate events are processed normally
* Total `DUPLICATE_EVENT_SUPPRESSED` count matches the duplicate event count in the storm
* All suppression records carry `correlation_id`

**Prohibited assertions:**

* Any duplicate webhook triggered a state management service call
* Duplicate suppression was silent for any event in the storm
* Non-duplicate events were affected by duplicate suppression storm volume

---

### LCDO-2 — Concurrent Finalization Storm: Exactly-One-FINALIZED Under Concurrent Load

**Governance contract:** `spec/03_state_transition_rules.md` Domain 2, STG-3, ECINV-1, ECINV-FAD1

**Saturation condition:** A bulk finalization sweep runs concurrently with multiple finalization trigger sources, some of which duplicate the same `(student_id, snapshot_month)` key. Exactly one finalization must succeed per key.

**Given:**

* A large student population awaits snapshot finalization
* Bulk finalization sweep runs while individual finalization triggers also arrive concurrently
* Some `(student_id, snapshot_month)` keys are targeted by multiple concurrent finalization attempts

**When:**

* All concurrent finalization attempts race against the idempotency gate

**Then:**

* For each `(student_id, snapshot_month)` key: exactly one finalization succeeds — database-level unique constraint ensures only one writer succeeds
* All competing attempts for already-FINALIZED keys produce `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` records
* No `warehouse.student_snapshots` record is written more than once for any `(student_id, snapshot_month)` key
* No `warehouse.snapshot_ai_narratives` record is written more than once for any key
* All blocked attempts are individually observable
* Bulk finalization sweep completion record documents: total candidates, total finalized, total blocked, `correlation_id`

**Prohibited assertions:**

* More than one FINALIZED record was produced for any `(student_id, snapshot_month)` key
* Any duplicate finalization attempt was silent without a `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` record

---

### LCDO-3 — Duplicate Replay Storm: Bulk Replay Idempotency at Scale

**Governance contract:** `runtime/system_loop.md` §4.8, ROS-4, ECRG-2

**Saturation condition:** A bulk replay trigger submission contains duplicate `(source_artifact_id, replay_cycle_id)` entries — simulating a replay orchestration re-submission storm.

**Given:**

* A bulk replay trigger submission contains multiple entries with duplicate `(source_artifact_id, replay_cycle_id)` tuples
* Replay Orchestration Scheduler evaluates all submitted triggers

**When:**

* Scheduler processes the full bulk replay submission

**Then:**

* Idempotency gate fires on `(source_artifact_id, replay_cycle_id)` for each entry
* Duplicate tuples are suppressed — `TRIGGER_SUPPRESSED` records emitted with `suppression_reason = DUPLICATE_REPLAY_KEY`
* Only one replay cycle is initiated per unique `(source_artifact_id, replay_cycle_id)` tuple
* Non-duplicate entries are processed normally
* No LIVE effects are produced by any replay cycle in the storm

**Prohibited assertions:**

* Multiple replay cycles executed for any duplicate `(source_artifact_id, replay_cycle_id)` tuple
* Any LIVE effect was produced by any replay cycle in the storm
* Duplicate suppression was silent for any entry in the bulk submission

---

## 9. PROVIDER SYNCHRONIZATION BACKLOG

---

### LCPB-1 — SQL Server Sync Backlog: Non-Blocking Annotation at Scale

**Governance contract:** `runtime/system_loop.md` §10.7, §8.2, PBG-5, DEG-4, ECPL-1, ECPL-3

**Saturation condition:** SQL Server sync lag accumulates across multiple consecutive failed sync cycles. All affected student records must carry `STALE_SQL_SERVER_DATA` annotations. Orchestration evaluation must not be blocked regardless of sync backlog magnitude.

**Given:**

* SQL Server sync has failed for multiple consecutive cycles
* `sync_lag_hours` exceeds the primary governance threshold (Config V2 Group K primary variable)
* `sync_lag_hours` additionally exceeds the secondary escalation threshold (Config V2 Group K secondary variable)
* Orchestration Evaluation Loop evaluates the full student population

**When:**

* Orchestration Evaluation Loop evaluates all students whose trigger data is stale

**Then:**

* `SYNC_LAG_EXCEEDED` event emitted for primary threshold violation with `sync_lag_hours`, `threshold_hours`, `affected_student_count`, `correlation_id`
* `SYNC_BACKLOG_ESCALATION_THRESHOLD_EXCEEDED` event emitted for secondary threshold violation
* Escalation candidacy signal produced: `escalation_type = SYNC_BACKLOG_CRITICAL`, `escalation_severity = HIGH`
* All affected student `OrchestrationIntent` records carry `STALE_SQL_SERVER_DATA` annotation
* Orchestration evaluation proceeds for all students — sync backlog is non-blocking at any backlog magnitude
* No student is silently skipped due to stale trigger data
* Both threshold values resolved from Config V2 Group K — no hardcoded hour constants

**Prohibited assertions:**

* Orchestration evaluation was blocked by sync backlog at any magnitude
* Any student was silently skipped due to stale trigger data
* Either threshold was derived from a hardcoded constant rather than Config V2 Group K

---

### LCPB-2 — Provider Outage: Outbound Suppression, Inbound Processing Continues

**Governance contract:** `runtime/system_loop.md` §8.3, §10.2, PBG-1, DEG-1, RGS-3

**Saturation condition:** GHL provider outage is active during a large orchestration cycle. Outbound dispatch must be suppressed for all students; inbound webhook processing must continue unaffected.

**Given:**

* GHL provider circuit breaker state = OPEN
* `PROVIDER_OUTAGE` event has been emitted
* A large outreach orchestration cycle is active
* GHL continues to deliver inbound webhooks during the outage

**When:**

* Orchestration Evaluation Loop and Webhook Ingestion Service both run during the provider outage

**Then:**

* All outbound dispatch delegations produce `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`
* `CIRCUIT_BREAKER_OPEN` structured log event emitted with `correlation_id`
* Retry budget is NOT consumed for any student whose dispatch was blocked by the outage
* Inbound webhook processing continues normally — no inbound suppression from outbound outage
* SQL Server sync loop continues unaffected
* AI evaluation loop continues unaffected
* Provider failure escalation candidacy generated once for the cycle, not per student
* `degradation_cause = PROVIDER_OUTAGE`, `affected_domains = ["ghl_outbound"]` in cycle completion record

**Prohibited assertions:**

* Any outbound dispatch was produced when the circuit breaker was OPEN
* Retry budget was consumed for any student during the provider outage
* Inbound webhook processing was suppressed by outbound provider outage
* Provider outage caused silent dispatch failures without observable events

---

### LCPB-3 — Provider AUTH_FAILURE Under Load: Terminal Classification, No Bulk Retry

**Governance contract:** `runtime/system_loop.md` §8.3, PBG-2, `failure/ghl_failures.md`

**Saturation condition:** GHL provider returns `AUTH_FAILURE` during an active high-volume orchestration cycle. AUTH_FAILURE is a TERMINAL class — no retry must be produced for any student, and all subsequent provider interactions must be blocked.

**Given:**

* GHL provider returns `AUTH_FAILURE` response during an active orchestration cycle
* `execution_mode = LIVE`
* Multiple students have pending dispatch delegations

**When:**

* Provider orchestration service processes the AUTH_FAILURE response

**Then:**

* Failure classified as `error_class = AUTH_FAILURE` (TERMINAL class)
* No retry is produced for any student — TERMINAL class carries no retry semantics
* `AUTH_FAILURE` structured log emitted with `provider = ghl`, `correlation_id`
* Alert escalation candidacy generated
* All subsequent provider interactions blocked until key rotation is confirmed
* Students with pending dispatch delegations receive `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE` — not retry scheduled
* AUTH_FAILURE is never classified as a transient error regardless of volume

**Prohibited assertions:**

* AUTH_FAILURE triggered a retry attempt for any student
* AUTH_FAILURE was classified as a transient error class
* Subsequent provider interactions proceeded without key rotation confirmation

---

## 10. AI INFERENCE BACKLOG

---

### LCAI-1 — AI Advisory Backlog: Rule-Based Orchestration Continues at Scale

**Governance contract:** `runtime/system_loop.md` §10.4, §9.1, AIG-1, AIG-4, DEG-2

**Saturation condition:** AI provider is unavailable or circuit breaker is OPEN during a large-scale orchestration cycle. Rule-based orchestration must proceed for all students regardless of AI advisory backlog.

**Given:**

* AI provider is unavailable
* AI circuit breaker state = OPEN
* A large orchestration evaluation cycle is active requiring AI advisory for many students

**When:**

* Orchestration Evaluation Loop evaluates all students requiring AI advisory

**Then:**

* `AI_PROVIDER_UNAVAILABLE` event emitted with `correlation_id`
* For each affected student: `AIAssessment.advisory_scope = UNAVAILABLE`
* Orchestration proceeds with rule-based evaluation only for all students — not blocked by AI unavailability
* Snapshot finalization is not blocked for any student
* `ai_content_stale = true` flag set on all affected orchestration records
* Escalation candidacy assessment proceeds with rule-based severity for all students
* Total affected student count documented in cycle completion record

**Prohibited assertions:**

* Orchestration evaluation was blocked for any student by AI provider unavailability
* AI provider unavailability was silent without structured log events
* Snapshot finalization was blocked by AI provider unavailability

---

### LCAI-2 — FINALIZED_COPY Immutability Under Bulk AI Refresh Sweep

**Governance contract:** `runtime/system_loop.md` §9.3, AP-OWN15, AIG-3, IML-1, INV-6, ECINV-6

**Saturation condition:** AI Refresh Orchestration Loop runs a bulk sweep that includes students with `FINALIZED_COPY` narratives in its candidate set. Every `FINALIZED_COPY` student must be skipped — no AI provider call, no warehouse write.

**Given:**

* AI Refresh Orchestration Loop bulk sweep candidate set includes students with `ai_governance_tier = FINALIZED_COPY`
* The `FINALIZED_COPY` population is a subset of the full candidate set

**When:**

* AI Refresh Loop executes the bulk sweep

**Then:**

* For each `FINALIZED_COPY` student: `ai_governance_tier = FINALIZED_COPY` check fires immediately
* For each `FINALIZED_COPY` student: no AI provider call is made
* For each `FINALIZED_COPY` student: no `ai_insights` record mutation is attempted
* For each `FINALIZED_COPY` student: skip record emitted with `skip_reason = FINALIZED_COPY_SKIP`, `student_id` (opaque), `correlation_id`
* `warehouse.snapshot_ai_narratives` row count and content checksums are identical before and after the bulk sweep for all pre-existing records
* Non-`FINALIZED_COPY` students in the candidate set are evaluated normally

**Prohibited assertions:**

* AI Refresh Loop made an AI provider call for any `FINALIZED_COPY` student
* `warehouse.snapshot_ai_narratives` content was modified for any record during the bulk sweep
* Skip records were absent for any `FINALIZED_COPY` student

---

### LCAI-3 — STALE AI Advisory: Governance Advisory-Only at Scale

**Governance contract:** `runtime/system_loop.md` §9.2, AIG-2, ECAI-1, AC-RT11

**Saturation condition:** A large population of students has STALE AI advisory content. STALE status must restrict advisory scope but not block orchestration for any student at any volume.

**Given:**

* A large population of students all have `AIAssessment.ai_governance_tier = STALE` (beyond `ai_insight_ttl_hours` from Config V2 Group H)
* Some students in the population meet rule-based escalation candidacy criteria
* `execution_mode = LIVE`

**When:**

* Orchestration Evaluation Loop and Escalation Polling Loop evaluate the full population

**Then:**

* For each student: orchestration proceeds — STALE AI does not block evaluation
* For each student meeting escalation criteria: `EscalationOrchestrationAssessment.severity` is governed by rule-based assessment, not STALE AI advisory
* STALE AI does not independently elevate escalation severity for any student (AP-AI11)
* `STALE` annotation is present in every escalation candidacy record where applicable
* `STALE_AI_SEVERITY_ELEVATION_BLOCKED` annotation applied where STALE AI advisory severity exceeds rule-based severity
* No student's orchestration is blocked by STALE AI status

**Prohibited assertions:**

* STALE AI advisory elevated escalation severity for any student in LIVE mode (AP-AI11)
* STALE AI blocked orchestration evaluation for any student

---

### LCAI-4 — AI Lineage Drift Prevention Under Bulk AI Generation

**Governance contract:** `spec/01_requirements.md` FAD-6, ATT-5, IML-3, ECINV-FAD1

**Saturation condition:** AI Refresh Loop generates advisory content for a large population simultaneously. AI attribution metadata must be captured correctly for every generated record — no lineage drift under bulk generation load.

**Given:**

* AI Refresh Orchestration Loop generates `ai_insights` records for a large student population
* AI provider returns complete attribution metadata (`ai_version_number`, `prompt_version`, `model_used`, `generated_at`) for each call

**When:**

* Bulk AI generation completes and `ai_insights` records are persisted

**Then:**

* Every `ai_insights` record carries: `ai_version_number`, `prompt_version`, `model_used`, `generated_at`, `correlation_id`
* Attribution metadata is immutable after `AI_GENERATED` state for every record
* No record has null `model_used`, null `prompt_version`, or null `ai_version_number`
* Any record where attribution fields could not be extracted produces `AI_ATTRIBUTION_FIELD_MISSING` event (ECA-5 pattern) — `model_used = UNKNOWN` explicit marker, not null
* Query `ai_insights` for `model_used IS NULL` after bulk generation — expected: zero records

**Prohibited assertions:**

* Any `ai_insights` record was persisted with null attribution fields without an observable event
* Attribution metadata was mutated on any record after `AI_GENERATED` state

---

## 11. ATTRIBUTION CONTINUITY UNDER STRESS

---

### LCAT-1 — Correlation ID Continuity: Zero Null Records Across Full Cycle at Scale

**Governance contract:** `runtime/system_loop.md` §11.1, §11.3, ATT-1, INV-5, ECINV-5

**Saturation condition:** A large-scale orchestration cycle produces a high volume of records across all tables. The invariant that every record carries a non-null `correlation_id` must hold for every record regardless of volume.

**Given:**

* Orchestration Evaluation Loop executes for a large student population
* `correlation_id` is generated at loop start and propagated to all downstream operations
* `execution_mode = LIVE`

**When:**

* Cycle completes and all records are written to `student_timeline_events`, `processed_events`, `state_transition_log`, and `ghl_messages`

**Then:**

* Query each table for records from this cycle: `SELECT COUNT(*) WHERE correlation_id IS NULL AND cycle_date = [cycle_date]` — expected: zero for all tables
* `correlation_id` is present in:
  * Every orchestration loop structured log record
  * Every `OrchestrationIntent` record in `student_timeline_events`
  * Every `ProviderOrchestrationAssessment` record
  * Every `processed_events` idempotency record
  * Every `ghl_messages` provider delivery record
* Any record with `correlation_id IS NULL`: `ATTRIBUTION_INVARIANT_VIOLATED` event emitted per null record; escalation candidacy generated

**Prohibited assertions:**

* Any record in any audited table has `correlation_id IS NULL` regardless of cycle volume
* Attribution invariant violations were silent without observable events

---

### LCAT-2 — Causation ID Linkage: Retry Chain Integrity at Scale

**Governance contract:** `runtime/system_loop.md` §4.2, §11.2, ATT-2, ECA-2

**Saturation condition:** A large retry orchestration cycle produces `RETRY_OUTREACH` intents for many students. Every retry intent must carry `causation_id` linking to the originating intent — no causation drift under bulk retry load.

**Given:**

* Retry Orchestration Loop produces `RETRY_OUTREACH` intents for a large retry-eligible population
* Each student has a prior `OrchestrationIntent` record in `student_timeline_events`

**When:**

* Bulk retry cycle completes

**Then:**

* Every `RETRY_OUTREACH` intent carries `causation_id` linking to the `intent_id` of the prior `OrchestrationIntent` for that student
* Query `student_timeline_events` for `RETRY_OUTREACH` records with `causation_id IS NULL` — expected: zero records
* Any `RETRY_OUTREACH` record with null `causation_id`: `ATTRIBUTION_FIELD_MISSING_causation_id` event emitted (ECA-2 pattern); `CAUSATION_LINEAGE_BROKEN` flag set; the defect does not block execution but is observable
* Attribution lineage chain is traceable from each retry intent back to its originating intent

**Prohibited assertions:**

* Any `RETRY_OUTREACH` intent was persisted without `causation_id` without an observable governance defect event
* Causation linkage drift was silent under bulk retry load

---

### LCAT-3 — Recovery Attribution: Full Attribution Required Before Recovery Begins

**Governance contract:** `runtime/scheduler_design.md` §8.3, AP-SCH11, ATT-4, ECA-4

**Saturation condition:** Under high-load scheduler saturation, orphan windows are detected across multiple domains. Recovery cycles for missed windows must carry full attribution before any recovery orchestration begins.

**Given:**

* Orphan detection identifies missed windows across multiple scheduler domains under saturation
* Operational Administrator authorizes recovery cycles for each missed domain
* Recovery cycle trigger records are written for each domain

**When:**

* Recovery Orchestration Loops attempt to begin recovery evaluation

**Then:**

* Each recovery cycle trigger record includes ALL required attribution fields: `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`, `orphaned_cycle_id`, `recovery_authorization_record_id`
* Any recovery trigger record missing a required field: `RECOVERY_ATTRIBUTION_INCOMPLETE` event emitted and recovery cycle does NOT proceed (ECA-4 pattern)
* All recovery cycles that proceed are forensically distinguishable from original cycles
* Recovery cycles check `processed_events` idempotency records — already-processed students are skipped

**Prohibited assertions:**

* Any recovery cycle proceeded without a complete `recovery_authorization_record_id`
* Attribution incompleteness was silently accepted under load

---

### LCAT-4 — Scheduler Attribution Continuity: cycle_id Propagation Under Multi-Domain Load

**Governance contract:** `runtime/scheduler_design.md` §9.1, ATT-3, ECA-3

**Saturation condition:** Under multi-domain scheduler saturation, all triggered orchestration loops must propagate the scheduler `cycle_id` to their loop start records. Missing `cycle_id` propagation under concurrent load must be detected and escalated.

**Given:**

* Multiple scheduler domains fire near-simultaneously under saturation
* Each produces a trigger record with a distinct `cycle_id`
* All triggered orchestration loops begin under concurrent load

**When:**

* Governance observability layer audits loop start records for all concurrent loops

**Then:**

* Each loop start record includes the `cycle_id` from its corresponding scheduler trigger record
* Any loop start record with `cycle_id IS NULL`: `ATTRIBUTION_FIELD_MISSING_cycle_id` event emitted; `SCHEDULER_ATTRIBUTION_DISCONTINUITY` event emitted with `expected_cycle_id`; escalation candidacy generated
* The forensic chain `SCH-N → COR-N → OrchestrationIntents` is intact for each domain
* Cross-domain `cycle_id` mixing is absent — no loop carries a `cycle_id` from a different domain's trigger

**Prohibited assertions:**

* `cycle_id` absence from any loop start record was silent under multi-domain saturation
* Cross-domain `cycle_id` mixing occurred in any loop record

---

## 12. DEGRADATION ESCALATION UNDER SATURATION

---

### LCDE-1 — Multi-Domain Outage Storm: Deterministic Degradation, Independent Domain Events

**Governance contract:** `runtime/system_loop.md` §10.2, §10.4, `failure/failure_playbook.md`, DEG-1, DEG-2, ECDE-1

**Saturation condition:** GHL provider outage and AI provider outage occur simultaneously during a large-scale orchestration cycle. Each domain's degradation must be independently observable and must not block other domains.

**Given:**

* GHL provider circuit breaker state = OPEN (`PROVIDER_OUTAGE` event)
* AI provider circuit breaker state = OPEN (`AI_PROVIDER_UNAVAILABLE` event)
* `execution_mode = LIVE`
* Large-scale orchestration cycle is active

**When:**

* Orchestration Evaluation Loop evaluates the full population under multi-domain outage

**Then:**

* `PROVIDER_OUTAGE` event emitted with `provider = ghl`, `correlation_id` — once per cycle, not per student
* `AI_PROVIDER_UNAVAILABLE` event emitted with `correlation_id` — once per cycle
* All outbound dispatches blocked: `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`
* AI advisory scope degraded for all students: `AIAssessment.advisory_scope = UNAVAILABLE`
* Rule-based orchestration evaluation proceeds for all students
* Inbound webhook ingestion continues normally — not blocked by outbound outage
* SQL Server sync continues unaffected
* `degradation_cause = MULTI_DOMAIN_OUTAGE`, `affected_domains = ["ghl", "ai"]` in cycle completion record
* Two separate escalation candidacy signals — one per domain
* Retry budget is NOT consumed for any student during the outage storm

**Prohibited assertions:**

* Multi-domain outage caused either failure to be silently swallowed
* Inbound webhook ingestion was blocked by GHL outbound outage under saturation
* Rule-based orchestration evaluation was blocked by AI outage
* Retry budget was consumed for any student during the outage storm

---

### LCDE-2 — Cascading Observability Saturation: Orchestration Loops Continue

**Governance contract:** `runtime/system_loop.md` §10.8, RGS-5, ECDE-2

**Saturation condition:** Observability pipeline (structured log destination) becomes unavailable during a high-volume orchestration cycle. Orchestration loops must continue without blocking on observability failure.

**Given:**

* Orchestration loops are mid-execution under high volume
* Observability pipeline (log destination) becomes unavailable
* Multiple failure events are ready to be emitted but cannot reach the primary destination

**When:**

* Orchestration loops continue evaluation while the observability pipeline is degraded

**Then:**

* Orchestration loops continue — observability failure does not block execution under any volume
* Structured log entries that fail primary destination are redirected to stderr with `OBSERVABILITY_DEGRADED` flag
* `OBSERVABILITY_DEGRADED` flag appears in the next successful log record when pipeline recovers
* All `PROVIDER_OUTAGE` and governance events that could not be written to primary destination are replayed when observability recovers
* `MULTI_DOMAIN_DEGRADATION` annotation documents `affected_domains` when observability and another domain degrade simultaneously
* No governance events are silently lost — stderr serves as the fallback stream

**Prohibited assertions:**

* Orchestration loops were blocked by observability pipeline failure under any volume
* Any governance events were silently lost because the observability pipeline was unavailable

---

### LCDE-3 — Multiple Simultaneous Failure Classes: Independent Classification at Scale

**Governance contract:** `failure/failure_playbook.md` §2, AP-FP3, AP-FP4, RGS-1, ECDE-5

**Saturation condition:** During a large orchestration cycle, multiple distinct failure classes occur for different students and domain boundaries simultaneously. Each failure class must be independently classified and handled.

**Given:**

* Large orchestration cycle active
* A subset of students encounter `TimeoutError` on SQL Server sync read
* A subset of students encounter `ValidationError` on eligibility assessment input
* Provider boundary returns `AUTH_FAILURE`
* Observability pipeline briefly degrades

**When:**

* Orchestration loop catches each exception across all concurrent failure events

**Then:**

* Each failure class produces its own structured log record with stable `error_class` string
* `TimeoutError` students: retry candidacy record produced; dead-letter record written with recovery instructions
* `ValidationError` students: skipped with `skip_reason = VALIDATION_ERROR`; no retry attempt (validation errors are not retryable)
* `AUTH_FAILURE`: classified as TERMINAL; no retry produced; all subsequent provider interactions blocked; alert escalation generated
* No generic `Error` class is used for any of the failure classifications
* Cycle completion record documents all failure classes with counts and `affected_student_ids` (opaque)
* Failures are not aggregated silently — each class produces independent observable records

**Prohibited assertions:**

* Any exception was caught with a generic `Error` class in any production code path under load
* Any exception was silently swallowed under saturation conditions
* `ValidationError` triggered a retry attempt for any student

---

### LCDE-4 — Degraded Replay Under Load: Warehouse-Accessible, No LIVE Effects

**Governance contract:** `runtime/system_loop.md` §3.1 (DEGRADED), ECDE-3, DEG-5, INV-4

**Saturation condition:** Bulk replay is executed under `execution_mode = DEGRADED` (provider outage active). Warehouse is accessible. Replay must be permitted and must produce zero LIVE effects regardless of replay volume under DEGRADED mode.

**Given:**

* `execution_mode = DEGRADED` (GHL provider outage active)
* Warehouse is accessible for all replayed students
* `historical_config_version_id` is resolvable for all replayed students
* Bulk replay sweep for a large historical population is triggered

**When:**

* Bulk Replay Orchestration Loop executes under DEGRADED mode

**Then:**

* Replay is permitted — warehouse accessible and historical config resolvable
* All replay outputs carry `execution_type = replay`, `governance_scope = REPLAY_ONLY`, `execution_mode = DEGRADED`
* Zero LIVE effects produced by any replayed student
* `ProviderOrchestrationAssessment.outbound_suppressed = true` for all replayed students
* `degradation_cause = PROVIDER_OUTAGE_DEGRADED_MODE` in replay diagnostic records
* Query `ghl_messages` for `execution_type = replay` after sweep — expected: zero records
* Query `state_transition_log` for transitions produced by `execution_type = replay` — expected: zero records

**Prohibited assertions:**

* Replay was blocked under DEGRADED mode when warehouse and historical config were accessible
* Any LIVE effect was produced under DEGRADED-mode bulk replay regardless of volume
* DEGRADED execution mode annotation was absent from any replay record

---

## 13. OBSERVABILITY SATURATION GOVERNANCE

---

### LCOS-1 — Structured Log Completeness Under High-Volume Cycle

**Governance contract:** `spec/06_observability_operations.md`, `runtime/system_loop.md` §11.1, AC-RT8

**Saturation condition:** Under a high-volume orchestration cycle, every structured log record must include the required governance fields. Log field omission under load is a governance defect.

**Given:**

* High-volume orchestration cycle active
* Observability pipeline is functioning normally
* Multiple concurrent loop instances are emitting structured log records

**When:**

* Structured log records are emitted across all orchestration loops

**Then:**

* Every structured log record includes: `timestamp` (ISO-8601), `level`, `service`, `event`, `correlation_id`, `duration_ms`, `outcome`
* No structured log record uses `console.log` of unstructured strings in any production code path
* All failure records include `error_class` — generic `Error` is absent from all production log records
* PII is absent from all structured log records (`spec/09_security_privacy.md` — PII prohibition in observability records)
* Log volume at saturation does not cause field omission — governance fields are not optional under load

**Prohibited assertions:**

* Any structured log record was missing `correlation_id` under high volume
* Generic `Error` appeared as `error_class` in any production log record
* PII appeared in any structured log record under saturation

---

### LCOS-2 — Observability Heartbeat: Attribution and Continuity Under All Modes

**Governance contract:** `runtime/scheduler_design.md` §3.3, ECSO-4, `spec/06_observability_operations.md`

**Saturation condition:** Under all execution modes and saturation conditions, the Observability Heartbeat Scheduler must emit complete heartbeat records including governance attribution fields.

**Given:**

* Observability Heartbeat Scheduler fires at Config V2 governed cadence
* System may be in any execution mode: SHADOW, LIVE, DEGRADED, or MAINTENANCE

**When:**

* Heartbeat record is emitted in each window

**Then:**

* Every heartbeat record carries: `scheduler_domain = observability_heartbeat`, `execution_mode`, `trigger_status = ACTIVE`, `correlation_id`, `config_version_id`
* Heartbeat emits in MAINTENANCE mode with `MAINTENANCE_MODE_EXCEPTION_HEARTBEAT_ACTIVE` annotation
* Heartbeat continues in DEGRADED mode — provider outage does not suppress heartbeat
* Heartbeat cadence resolves from Config V2 — no hardcoded interval governs heartbeat timing
* Missed heartbeat window is itself detectable via orphan detection

**Prohibited assertions:**

* Heartbeat was suppressed in any execution mode including MAINTENANCE and DEGRADED
* Heartbeat records were missing governance attribution fields under any mode

---

## 14. GOVERNANCE INVARIANT LOAD TESTS

---

These scenarios validate that INVARIANT-1 through INVARIANT-7 (from `tests/test_scenarios.md` §17) and FAD-1 through FAD-6 hold under saturation, concurrent load, and multi-domain degradation conditions. Each scenario is prefixed `LCI` and references the parent invariant.

---

### LCI-INV1 — INVARIANT-1 Under Saturation: FINALIZED Snapshot Inviolable Under Concurrent Bulk Mutation Attempts

**Parent invariant:** INV-1 — A FINALIZED snapshot record is inviolable (from `tests/test_scenarios.md` §17)

**Saturation condition:** A bulk finalization sweep runs concurrently with multiple mutation attempts against already-FINALIZED records.

**Governance load verification:**

* Record `content_checksum` for all `warehouse.student_snapshots` records in FINALIZED state before any bulk operation
* Execute bulk finalization sweep including already-FINALIZED students
* Execute concurrent mutation attempts against FINALIZED records
* After all operations complete:
  * `content_checksum` for all pre-existing FINALIZED records must be identical — no mutation succeeded
  * `IMMUTABLE_RECORD_MUTATION_BLOCKED` event count must equal the attempted mutation count
  * `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` count must equal the repeated finalization trigger count
* If any FINALIZED record shows content change: `IMMUTABLE_RECORD_MUTATION_DETECTED` governance defect event emitted; escalation candidacy generated

**Prohibited assertions:**

* Any FINALIZED `warehouse.student_snapshots` record was mutated under saturation
* Any mutation attempt was silent without an observable blocking event

---

### LCI-INV2 — INVARIANT-2 Under Saturation: Exactly-One-ACTIVE Config Version Under Concurrent Readers

**Parent invariant:** INV-2 — At all times, exactly one config version holds ACTIVE status (from `tests/test_scenarios.md` §17)

**Saturation condition:** Config version activation runs while multiple concurrent orchestration loops read `config_version_registry` simultaneously.

**Governance load verification:**

* Query `SELECT COUNT(*) FROM config_version_registry WHERE status = 'ACTIVE'` repeatedly across concurrent readers during and after config activation
* Expected: count = 1 at every observable point — before, during (post-atomic transaction), and after activation
* Config activation transaction is atomic — two-step UPDATE (V1 → SUPERSEDED, V2 → ACTIVE) is wrapped in a single transaction
* If at any point `count ≠ 1`: `CONFIG_VERSION_INVARIANT_VIOLATED` alert event emitted; escalation candidacy generated immediately
* `CONFIG_VERSION_MID_CYCLE_TRANSITION` event emitted if activation occurs during an active evaluation cycle — documents split counts

**Prohibited assertions:**

* `count(*) WHERE status = ACTIVE = 0` ever observable
* `count(*) WHERE status = ACTIVE = 2` ever observable
* Concurrent readers observed a non-atomic activation state

---

### LCI-INV3 — INVARIANT-3 Under Saturation: Prospective-Only Activation, Multiple Config Versions

**Parent invariant:** INV-3 — Config activation applies only to new cycles; historical records not retroactively re-evaluated (from `tests/test_scenarios.md` §17)

**Saturation condition:** Multiple config version activations (V1 → V2 → V3) have occurred. Concurrent replay cycles for V1-era and V2-era cycles run simultaneously. No replay applies a non-historical config version.

**Governance load verification:**

* Replay for V1-era `cycle_date`: all directive evaluations resolve from V1 — `SELECT DISTINCT config_version_id FROM processed_events WHERE execution_type = 'replay' AND cycle_date < v2_activation_date` must equal `{V1}`
* Replay for V2-era `cycle_date`: all directive evaluations resolve from V2 — result set must equal `{V2}`
* No replay record carries `config_version_id = V3` (current ACTIVE) for any historical context
* Mid-replay config activation (ECINV-FAD3 pattern): in-progress replay context anchored to `historical_config_version_id` — V3 activation does not contaminate it

**Prohibited assertions:**

* Any historical replay applied a non-historical config version at any volume
* Mid-replay config activation silently contaminated any in-progress replay context

---

### LCI-INV4 — INVARIANT-4 Under Saturation: Zero LIVE Effects From Bulk Replay Under All Conditions

**Parent invariant:** INV-4 — The Replay Orchestration Loop may produce diagnostic records only; no LIVE effects (from `tests/test_scenarios.md` §17)

**Saturation condition:** Bulk replay sweep for a large historical population runs in all execution modes including DEGRADED. Zero LIVE effects must be produced at any replay volume.

**Governance load verification:**

* Execute bulk replay sweep (multiple execution modes: SHADOW, LIVE, DEGRADED)
* Query `ghl_messages` for `execution_type = replay` — expected: zero records
* Query `state_transition_log` for transitions produced by `execution_type = replay` — expected: zero records
* Query `processed_events` for `execution_type = replay` records — all carry `governance_scope = REPLAY_ONLY`
* All replay records carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` regardless of volume and execution mode

**Prohibited assertions:**

* Any LIVE effect was produced by any replay-mode execution at any volume or under any execution mode

---

### LCI-INV5 — INVARIANT-5 Under Saturation: Zero Null correlation_id Across Large Population Cycle

**Parent invariant:** INV-5 — Every orchestration record carries a non-null `correlation_id` (from `tests/test_scenarios.md` §17)

**Saturation condition:** A large-scale orchestration cycle (volume governed by Config V2 Group A batch-size variable) produces a high record volume. Zero null `correlation_id` values must appear across all audited tables.

**Governance load verification:**

* Execute large-scale orchestration cycle with `correlation_id` generated at loop start
* After cycle completion, query ALL audited tables:
  * `SELECT COUNT(*) FROM student_timeline_events WHERE correlation_id IS NULL AND cycle_date = [cycle_date]` — expected: zero
  * `SELECT COUNT(*) FROM state_transition_log WHERE correlation_id IS NULL AND cycle_date = [cycle_date]` — expected: zero
  * `SELECT COUNT(*) FROM processed_events WHERE correlation_id IS NULL AND cycle_date = [cycle_date]` — expected: zero
  * `SELECT COUNT(*) FROM ghl_messages WHERE correlation_id IS NULL` — expected: zero (for this cycle's records)
* Any null found: `ATTRIBUTION_INVARIANT_VIOLATED` event emitted per null record; escalation candidacy generated

**Prohibited assertions:**

* Any record in any audited table has `correlation_id IS NULL` regardless of cycle population size

---

### LCI-INV6 — INVARIANT-6 Under Saturation: FINALIZED_COPY Immutability Under Bulk AI Refresh

**Parent invariant:** INV-6 — `warehouse.snapshot_ai_narratives` records are immutable after insertion (from `tests/test_scenarios.md` §17)

**Saturation condition:** AI Refresh Orchestration Loop bulk sweep includes FINALIZED_COPY students at high volume. No content mutation must occur to any existing record.

**Governance load verification:**

* Record `row_count` and `content_checksum` for all `warehouse.snapshot_ai_narratives` records before the bulk sweep
* Execute bulk AI Refresh Loop sweep including FINALIZED_COPY students
* After sweep completion:
  * `row_count` — must have increased only by newly generated non-FINALIZED records (not FINALIZED ones)
  * `content_checksum` — identical for all pre-existing records
* Any delta in pre-existing records: `IMMUTABLE_RECORD_MUTATION_DETECTED` governance defect event emitted

**Prohibited assertions:**

* Any `warehouse.snapshot_ai_narratives` record had content modified by the bulk AI refresh sweep at any sweep volume

---

### LCI-INV7 — INVARIANT-7 Under Saturation: All Governance Decision Records Carry config_version_id After Mid-Cycle Transition

**Parent invariant:** INV-7 — Every `OrchestrationIntent`, `RetryPolicyAssessment`, and `EligibilityAssessment` record must carry `config_version_id` (from `tests/test_scenarios.md` §17)

**Saturation condition:** A config version transition (V1 → V2) occurs mid-cycle during a large evaluation batch. All records produced before and after the transition must carry non-null `config_version_id`.

**Governance load verification:**

* Query `student_timeline_events` for records produced during the transition cycle
* `SELECT COUNT(*) FROM student_timeline_events WHERE config_version_id IS NULL AND cycle_date = [transition_cycle_date]` — expected: zero
* Records produced before transition: `config_version_id = V1`
* Records produced after transition: `config_version_id = V2`
* `CONFIG_VERSION_MID_CYCLE_TRANSITION` event emitted with `students_processed_under_v1`, `students_processed_under_v2`

**Prohibited assertions:**

* Any governance decision record produced during a config transition has `config_version_id IS NULL`

---

### LCI-FAD1 — FAD-1 Under Load: AI Physical Copy Immutability Under Bulk Finalization

**Parent invariant:** FAD-1 — Physical copy AI immutability; `warehouse.snapshot_ai_narratives` is append-only after FINALIZED (from `spec/01_requirements.md`)

**Saturation condition:** Bulk Snapshot Finalization Loop runs for a large student population simultaneously. For already-FINALIZED students, the loop must skip them with zero warehouse write attempts.

**Governance load verification:**

* Record initial `row_count` for `warehouse.snapshot_ai_narratives`
* Execute bulk finalization sweep (mix of new and already-FINALIZED students)
* After sweep: `row_count` must have increased by exactly the count of newly finalized students (not the count of already-FINALIZED students)
* All already-FINALIZED students: `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` records must exist for each
* No FINALIZED narrative was overwritten

**Prohibited assertions:**

* `row_count` for `warehouse.snapshot_ai_narratives` increased by more than the count of newly finalized students
* Any `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` record was absent for any already-FINALIZED student

---

### LCI-FAD2 — FAD-2 Under Load: Regeneration Produces Zero External Calls Under Concurrent Access

**Parent invariant:** FAD-2 — Historical report reproducibility; no external calls in regeneration (from `spec/01_requirements.md`)

**Saturation condition:** Bulk report regeneration runs while concurrent processes attempt external access for the same cohorts. FAD-2 is absolute at any regeneration volume.

**Governance load verification:**

* During bulk report regeneration cycle: intercept any outbound HTTP call (SQL Server, AI provider, GHL) across all regeneration instances
* Expected: zero outbound HTTP calls during any regeneration cycle instance
* Any outbound call attempt during regeneration produces: `REGENERATION_EXTERNAL_CALL_BLOCKED` event with `correlation_id`
* `output_identical` evaluation proceeds using warehouse-only data for all regenerated reports

**Prohibited assertions:**

* Any outbound call succeeded during any regeneration cycle instance regardless of concurrent access pressure
* External call attempt during regeneration was silent without a `REGENERATION_EXTERNAL_CALL_BLOCKED` event

---

### LCI-FAD3 — FAD-3 Under Load: No Retroactive Re-Evaluation Under Concurrent Config Activation and Replay

**Parent invariant:** FAD-3 — Prospective-only config activation; historical records not retroactively re-evaluated (from `spec/01_requirements.md`)

**Saturation condition:** A new config version (V3) is activated while concurrent replay and LIVE cycles are running. No in-progress replay context may be contaminated by V3 activation.

**Governance load verification:**

* Replay for V1-era cycles running concurrently with V3 activation: all replay assessment records carry `config_version_id = V1` — before and after V3 activation mid-replay
* `V3_ACTIVATION_DURING_REPLAY` annotation applied to replay diagnostic records for in-progress replays during V3 activation
* `CONFIG_VERSION_MID_REPLAY_TRANSITION` event emitted
* LIVE cycles started after V3 activation: all carry `config_version_id = V3`
* No historical replay assessment record carries `config_version_id = V3`

**Prohibited assertions:**

* Any replay assessment record carried a config version ID from a config activated after the replay's `historical_config_version_id`
* V3 activation silently contaminated any in-progress replay context

---

## 15. ACCEPTANCE CRITERIA

---

Acceptance criteria for governance load certification are organized by domain. They extend and do not replace the governance acceptance criteria in `tests/test_scenarios.md` §18 and `tests/edge_cases.md` §15.

---

### AC-LOAD-1 — Governance Conformance Under Saturation Certification

A system passes governance conformance under saturation certification when:

* Config V2 governed concurrency resolves dynamically for all batch executions — no hardcoded limit governs any batch (LCS-1)
* Concurrent loop instances prevent duplicate LIVE orchestration via idempotency gate with observable suppression records (LCS-2)
* Orphaned cycle prevention holds under concurrent saturation with dead-letter records for unprocessed candidates (LCS-3)
* Per-student compliance holds do not cascade to global batch suppression at any batch size (LCS-4)

---

### AC-LOAD-2 — Replay-Safe Orchestration Under Load Certification

A system passes replay-safe orchestration under load certification when:

* Bulk replay sweep at any volume produces zero LIVE effects — verified by querying `ghl_messages` and `state_transition_log` (LCR-1)
* Concurrent duplicate replay triggers are suppressed by idempotency gate with `TRIGGER_SUPPRESSED` records (LCR-2)
* Replay and LIVE namespaces remain isolated under concurrent saturation — no namespace contamination (LCR-3)
* Bulk regeneration at any cohort volume produces zero external API calls (LCR-4, LCI-FAD2)

---

### AC-LOAD-3 — Scheduler Governance Under Saturation Certification

A system passes scheduler governance under saturation certification when:

* Scheduler drift at high trigger frequency produces `TRIGGER_SUPPRESSED` records and `SCHEDULER_DRIFT_DETECTED` events — exactly one loop per `cycle_date` (LCSCH-1)
* Multi-domain orphan detection identifies missed cycles without producing false positives for in-flight cycles (LCSCH-2)
* Scheduler attribution continuity holds under multi-domain saturation — no `cycle_id` mixing or null propagation (LCSCH-3)
* Observability Heartbeat Scheduler continues uninterrupted in MAINTENANCE mode under any load (LCSCH-4)

---

### AC-LOAD-4 — Deterministic Degradation Under Saturation Certification

A system passes deterministic degradation under saturation certification when:

* Multi-domain outage storm produces independent observable events per domain without cross-domain blocking (LCDE-1)
* Observability pipeline saturation redirects to stderr without blocking orchestration loops (LCDE-2)
* Multiple simultaneous failure classes are independently classified with stable `error_class` values — no generic `Error` (LCDE-3)
* DEGRADED-mode bulk replay produces zero LIVE effects — verified by table queries (LCDE-4)

---

### AC-LOAD-5 — Immutable Lineage Under Stress Certification

A system passes immutable lineage under stress certification when:

* FINALIZED snapshot records are inviolable under concurrent bulk mutation attempts — content checksums unchanged (LCI-INV1, LCI-FAD1)
* `warehouse.snapshot_ai_narratives` content is identical before and after bulk AI refresh sweeps (LCI-INV6)
* Bulk regeneration produces no external calls and `output_identical` flags are present on all records (LCI-FAD2)
* Bulk finalization sweep increases warehouse row count by exactly the count of newly finalized students (LCI-FAD1)

---

### AC-LOAD-6 — Attribution Continuity Under Load Certification

A system passes attribution continuity under load certification when:

* Zero null `correlation_id` records exist in all audited tables after any scale cycle (LCAT-1, LCI-INV5)
* Zero null `causation_id` records exist for `RETRY_OUTREACH` intents after bulk retry cycles (LCAT-2)
* All recovery cycle trigger records carry complete attribution before recovery begins (LCAT-3)
* Scheduler `cycle_id` propagation holds under multi-domain saturation — no null or mixed values (LCAT-4)

---

### AC-LOAD-7 — Provider-Boundary Preservation Under Load Certification

A system passes provider-boundary preservation under load certification when:

* Duplicate webhook storms are suppressed with `DUPLICATE_EVENT_SUPPRESSED` records — zero duplicate state transitions (LCDO-1)
* Concurrent finalization storms produce exactly one FINALIZED record per `(student_id, snapshot_month)` key (LCDO-2)
* GHL provider outage suppresses all outbound dispatch without affecting inbound webhook processing (LCPB-2)
* AUTH_FAILURE is classified TERMINAL with no retry produced for any student (LCPB-3)
* Retry budget is protected for all retry-eligible students during provider outage storms (LCRSG-3)

---

### AC-LOAD-8 — AI Governance Preservation Under Load Certification

A system passes AI governance preservation under load certification when:

* AI provider unavailability allows rule-based orchestration to proceed for all students at scale (LCAI-1)
* Bulk AI refresh sweeps leave all FINALIZED_COPY narratives immutable — zero content mutations (LCAI-2)
* STALE AI advisory never elevates escalation severity for any student in LIVE mode at any population size (LCAI-3)
* Bulk AI generation produces zero null attribution fields — `model_used IS NULL` count = zero (LCAI-4)

---

### AC-LOAD-9 — Idempotent Orchestration Under Concurrency Certification

A system passes idempotent orchestration under concurrency certification when:

* Config V2 governed concurrency prevents duplicate LIVE orchestration across concurrent instances at any scale (LCS-2)
* Bulk replay idempotency gate prevents multiple replay cycles for identical `(source_artifact_id, replay_cycle_id)` tuples (LCR-2)
* Retry storm governance enforces Config V2 thresholds without hardcoded limits for any population size (LCRSG-1)
* Retry window enforcement blocks early retry for all students under rapid re-trigger (LCRSG-4)

---

### AC-LOAD-10 — Governance Invariant Preservation Under Saturation Certification

A system passes governance invariant preservation under saturation certification when all of the following hold under concurrent and high-volume conditions:

* INVARIANT-1: FINALIZED snapshots inviolable under concurrent bulk mutation attempts (LCI-INV1)
* INVARIANT-2: Exactly-one-ACTIVE config version at all observable points during concurrent activation (LCI-INV2)
* INVARIANT-3: All replays consistently apply historical config across multiple prior activations (LCI-INV3)
* INVARIANT-4: Zero LIVE effects from bulk replay at any volume under any execution mode (LCI-INV4)
* INVARIANT-5: Zero null `correlation_id` records across any scale orchestration cycle (LCI-INV5)
* INVARIANT-6: Bulk AI refresh sweep leaves all FINALIZED_COPY narratives immutable (LCI-INV6)
* INVARIANT-7: Zero null `config_version_id` records during mid-transition config batches (LCI-INV7)
* FAD-1: Bulk finalization produces exactly the expected new warehouse row count (LCI-FAD1)
* FAD-2: Zero outbound calls during bulk regeneration under concurrent access pressure (LCI-FAD2)
* FAD-3: In-progress replay contexts not contaminated by concurrent config activation (LCI-FAD3)

---

## 16. SCOPE-SPECIFIC LOAD COVERAGE

---

### MVP

* LCS-1 (batch orchestration: Config V2 concurrency, zero null attribution)
* LCS-3 (orphaned cycle prevention under saturation)
* LCR-1 (bulk replay: zero LIVE effects)
* LCSCH-1 (scheduler drift: idempotency gate holds)
* LCSCH-4 (heartbeat continues in MAINTENANCE)
* LCRSG-1 (retry storm: Config V2 threshold protection)
* LCDO-1 (webhook storm: duplicate suppression)
* LCAI-1 (AI backlog: rule-based orchestration continues)
* LCAT-1 (zero null correlation_id at scale)
* LCDE-2 (observability saturation: loops continue)
* LCI-INV2 (exactly-one-ACTIVE under concurrent load)
* LCI-INV5 (zero null correlation_id, large population)

---

### STANDARD

All MVP scenarios plus:

* LCS-2 (concurrent duplicate LIVE prevention)
* LCS-4 (compliance hold: no cascade under bulk load)
* LCR-2 (replay idempotency under concurrent triggers)
* LCR-3 (replay-vs-LIVE isolation under saturation)
* LCSCH-2 (orphan detection under multi-domain load)
* LCSCH-3 (scheduler attribution continuity under saturation)
* LCRSG-2 (retry exhaustion storm: escalation candidacy)
* LCRSG-3 (retry budget protection during outage)
* LCRSG-4 (retry window enforcement under rapid re-trigger)
* LCDO-2 (concurrent finalization storm: exactly-one-FINALIZED)
* LCDO-3 (duplicate replay storm: bulk idempotency)
* LCPB-1 (sync backlog: non-blocking at scale)
* LCPB-2 (provider outage: outbound suppressed, inbound continues)
* LCAI-2 (FINALIZED_COPY immutability under bulk AI refresh)
* LCAI-3 (STALE AI governance at scale)
* LCAT-2 (causation_id linkage: retry chain integrity)
* LCAT-3 (recovery attribution: full attribution before recovery)
* LCDE-1 (multi-domain outage storm)
* LCDE-3 (multiple failure classes: independent classification)
* LCOS-1 (structured log completeness under high volume)
* LCI-INV1, LCI-INV3, LCI-INV4, LCI-INV6, LCI-INV7
* LCI-FAD1, LCI-FAD3

---

### PRODUCTION

All MVP and STANDARD scenarios plus:

* LCR-4 (bulk regeneration: zero external calls)
* LCPB-3 (AUTH_FAILURE: terminal under load)
* LCAI-4 (AI lineage drift prevention under bulk generation)
* LCAT-4 (scheduler attribution under multi-domain saturation)
* LCDE-4 (degraded replay under load)
* LCOS-2 (observability heartbeat: attribution under all modes)
* LCI-INV2 (exactly-one-ACTIVE: concurrent readers stress)
* LCI-FAD2 (regeneration: zero external calls under concurrent pressure)
* Full governance invariant preservation suite (LCI-INV1 through LCI-FAD3)
* Full attribution continuity suite (LCAT-1 through LCAT-4) under peak volume
* Full provider-boundary load suite (LCPB-1 through LCPB-3, LCRSG-3)
* Full scheduler saturation suite (LCSCH-1 through LCSCH-4)

---

## 17. REFERENCES

---

### Parent Governance Contracts

* `tests/test_scenarios.md` — **authoritative parent governance validation contract**; this file inherits all governance invariants, prohibited validation semantics, and acceptance criteria from §2 through §18
* `tests/edge_cases.md` — **authoritative parent governance edge-condition certification contract**; this file inherits all edge-condition domains, stress scenarios, and acceptance criteria from §2 through §15

### Runtime Contracts

* `runtime/system_loop.md` — authoritative parent runtime contract; AP-RT1 through AP-RT15; replay governance; Config V2 integration; observability framework
* `runtime/scheduler_design.md` — governance-safe scheduler orchestration; AP-SCH1 through AP-SCH15; orphan detection; attribution lineage
* `runtime/daily_outreach_flow.md` — daily orchestration flow governance
* `runtime/retry_cycle_flow.md` — retry orchestration governance; retry budget protection

### Resilience Contracts

* `failure/failure_playbook.md` — canonical parent resilience contract; AP-FP1 through AP-FP8; deterministic degradation; failure classification
* `failure/scheduling_failures.md` — scheduler-domain resilience governance
* `failure/ghl_failures.md` — provider-domain resilience governance; circuit breaker patterns; AUTH_FAILURE terminal classification
* `failure/llm_failures.md` — AI-domain resilience governance; advisory-only degradation; stale AI governance

### Directive Contracts

* `directives/outreach_eligibility_rules.md` — EligibilityAssessment governance
* `directives/outreach_retry_policy.md` — RetryPolicyAssessment governance; Config V2 threshold resolution
* `directives/core_decision_engine.md` — OrchestrationIntent governance; rule-based evaluation primacy
* `directives/channel_selection_rules.md` — ChannelSelectionAssessment governance
* `directives/escalation_rules.md` — EscalationOrchestrationAssessment governance
* `directives/llm_processing_contract.md` — AIAssessment governance; advisory-only guarantees
* `directives/ghl_integration_contract.md` — ProviderOrchestrationAssessment governance; provider-boundary rules
* `directives/agent_ownership_matrix.md` — authority domain definitions; write authority restrictions

### Specification Contracts

* `spec/01_requirements.md` — FAD-1 through FAD-6; Config V2 Governance Catalog §12
* `spec/03_state_transition_rules.md` — state transition authority for all lifecycle domains
* `spec/04_idempotency_concurrency.md` — idempotency keys, concurrency controls, Domains 1–6
* `spec/05_external_integrations.md` — provider integration governance; read-only SQL Server constraints
* `spec/06_observability_operations.md` — structured log requirements; metrics requirements; observability governance
* `spec/07_api_contracts.md` — API boundary contracts
* `spec/08_data_model.md` — entity definitions; append-only constraints; immutability requirements
* `spec/09_security_privacy.md` — security governance; PII prohibition in observability records

### Architecture Decisions Referenced

* FAD-1 — Physical copy AI immutability (`warehouse.snapshot_ai_narratives`)
* FAD-2 — Historical report reproducibility (no external calls in regeneration)
* FAD-3 — Prospective-only config activation
* FAD-6 — AI attribution metadata immutability after AI_GENERATED

### Architecture Preservation Rules Referenced

* AP-RT1 through AP-RT15 — runtime loop governance prohibitions
* AP-SCH1 through AP-SCH15 — scheduler domain governance prohibitions
* AP-FP1 through AP-FP8 — resilience orchestration governance prohibitions
* AP-AI5, AP-AI11 — AI advisory-only and STALE AI governance prohibitions
* AP-OWN15 — warehouse write authority restrictions

### Governance Invariants Referenced

* INV-1 through INV-7 — from `tests/test_scenarios.md` §17
* FAD-1 through FAD-6 — from `spec/01_requirements.md`

---

## END OF FILE
