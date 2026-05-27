# tests/edge_cases.md

---

## LAYER 6 — GOVERNANCE EDGE-CONDITION CERTIFICATION ARCHITECTURE

---

> **Version note:** This file was completely rewritten on 2026-05-26 to align with the governance-safe orchestration architecture established in `tests/test_scenarios.md` (the authoritative parent governance validation contract), `runtime/system_loop.md`, `runtime/scheduler_design.md`, `runtime/daily_outreach_flow.md`, `runtime/retry_cycle_flow.md`, `failure/failure_playbook.md`, `failure/scheduling_failures.md`, `failure/ghl_failures.md`, `failure/llm_failures.md`, all seven rewritten directive files, and `spec/01_requirements.md` through `spec/09_security_privacy.md`. The previous version described MVP-era workflow exception testing: missing contact info handling, hardcoded `MAX_ATTEMPTS` retry assumptions, simplistic fallback validation ("system falls back to safe state"), hardcoded concurrency limits ("more than 50 concurrent executions"), direct execution assumptions, and simplistic NO_ACTION semantics. Those patterns are incompatible with the governance-safe orchestration model and are replaced in this file by governance-boundary certification under boundary-stress and race-condition inputs.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

This file is the **governance edge-condition certification architecture** for the Student Success Intelligence Platform. It extends `tests/test_scenarios.md` — the authoritative parent governance validation contract — by defining:

* How governance invariants behave under boundary-stress, timing-race, and degradation-cascade conditions
* How replay-safe orchestration holds under adversarial and partial-failure edge inputs
* How immutable lineage guarantees are preserved when idempotency windows overlap, history is incomplete, or attribution chains are interrupted
* How Config V2 governance handles activation races, missing thresholds, and prospective-only enforcement under stress
* How provider-boundary governance holds when duplicate webhooks, outage storms, and synchronization lag accumulate
* How AI advisory-only governance holds when AI content is stale, unavailable, or fingerprint-divergent
* How attribution continuity holds when `correlation_id`, `causation_id`, or lineage records are at risk of loss
* How deterministic degradation holds when multiple failure domains degrade simultaneously
* How idempotency protections hold under concurrent replay-vs-LIVE execution and scheduler drift scenarios

This document **inherits** from and **must not contradict** `tests/test_scenarios.md`. Where a governance principle is stated in the parent contract, this file validates that principle holds under stress. Where this file defines a new edge-condition scenario, the edge condition must be traceable to a governance invariant in the parent contract.

---

### 1.2 What Edge-Condition Validation Is NOT

In the governance-safe orchestration model, edge-condition validation is explicitly **NOT**:

* **Workflow exception testing** — "what happens when email fails" is not a governance edge assertion; the governance assertion is "what governance records are produced, what attribution is preserved, and what observable degradation signals are emitted when the provider boundary is unavailable"
* **Operational fallback testing** — "system falls back to safe state" is not a valid edge-condition outcome; every degraded execution path must be specifically observable and explicitly attributable
* **Simplistic failure-edge testing** — testing that a retry stops at a hardcoded threshold is a specification violation; the edge condition tests that retry governance resolves dynamically from Config V2 and that exhaustion produces an escalation candidacy signal with full attribution
* **LIVE-effect assumption testing** — no edge-condition test may assert that a LIVE outbound communication occurred; tests assert governance-authorized orchestration paths with correct attribution
* **Replay-triggered LIVE assertions** — no edge-condition scenario may assert that a replay-mode execution produced LIVE effects under any condition, including partial failure or degraded warehouse access
* **Mutable FINALIZED_COPY assertions** — no edge-condition scenario may assert or accept that `warehouse.snapshot_ai_narratives` records were modified, overwritten, or re-evaluated after FINALIZED state
* **Silent fallback certification** — "fallback logic applied" is never a governance-safe edge-condition outcome; every fallback path must emit a specific degradation event with attribution

---

### 1.3 Inheritance from Parent Contract

This file inherits the following governance contracts in full from `tests/test_scenarios.md`:

| Inherited contract | Section in parent |
|---|---|
| Prohibited validation semantics | §2 |
| Config V2 governance preconditions | §3 (GPC-1 through GPC-5) |
| Orchestration Intent governance | §4 (OIG-1 through OIG-5) |
| Config V2 threshold resolution | §5 (CV2-1 through CV2-4) |
| SHADOW-vs-LIVE behavior boundaries | §6 (SVL-1 through SVL-3) |
| Replay orchestration governance | §7 (ROS-1 through ROS-5) |
| Retry orchestration governance | §8 (ROG-1 through ROG-5) |
| AI governance | §9 (AIG-1 through AIG-5) |
| Provider boundary governance | §10 (PBG-1 through PBG-5) |
| State transition governance | §11 (STG-1 through STG-4) |
| Resilience governance | §12 (RGS-1 through RGS-5) |
| Concurrency and idempotency | §13 (CID-1 through CID-4) |
| Attribution continuity | §14 (ATT-1 through ATT-5) |
| Degradation validation | §15 (DEG-1 through DEG-5) |
| Immutable lineage | §16 (IML-1 through IML-4) |
| Governance invariants | §17 (INV-1 through INV-7) |
| Acceptance criteria | §18 (AC-GOV-1 through AC-GOV-8) |

The parent contract defines the nominal governance behavior. This file defines the edge-condition stress behavior. All governance invariants from the parent must hold under the stress conditions defined here.

---

## 2. PROHIBITED EDGE-CASE VALIDATION SEMANTICS

---

The following patterns are **prohibited** in all edge-condition scenarios in this document. Their presence is a governance contract violation equivalent to the prohibitions in `tests/test_scenarios.md` §2.

| Prohibited edge-case pattern | Governance violation | Required replacement |
|---|---|---|
| `contact_attempt > MAX_ATTEMPTS` | Hardcoded threshold edge assertion | `RetryPolicyAssessment.retry_authorized = false` with `reason = RETRY_EXHAUSTED` and `config_version_id` — threshold resolves from Config V2 |
| `last_contact_time < retry interval` | Hardcoded timing edge assertion | `RetryPolicyAssessment.reason = RETRY_WINDOW_NOT_ELAPSED` with `config_version_id` — window resolves from Config V2 Group A |
| `stop retry / trigger fallback or escalation` | Silent fallback edge assertion | Specific `RETRY_EXHAUSTED` record + escalation candidacy signal + observable structured log |
| `second attempt ignored` | Underspecified idempotency assertion | Explicit `TRIGGER_SUPPRESSED` or `DUPLICATE_IDEMPOTENCY_KEY` record with `suppression_reason` and `correlation_id` |
| `more than 50 concurrent executions` | Hardcoded concurrency edge assertion | Config V2 Group A concurrency variable resolution — no hardcoded limit in any edge scenario |
| `system falls back to safe state` | Silent fallback edge outcome | Specific degradation event class + `DEGRADED` annotation + structured log with `degradation_cause` |
| `process once / ignore duplicates` | Underspecified deduplication assertion | `DUPLICATE_EVENT_SUPPRESSED` or `DUPLICATE_REPLAY_KEY` audit record with full attribution fields |
| `treat as NO_RESPONSE after timeout` | Silent inferred state transition | Governance-authorized state assessment with `correlation_id` and observable event record |
| `skip LLM processing / proceed with fallback` | Silent fallback edge assertion | `AIAssessment.advisory_scope = UNAVAILABLE` + `TRANSCRIPT_UNAVAILABLE` event + structured log |
| `retry or discard` (contradictory AI output) | Ambiguous disposition without governance record | Specific `AI_OUTPUT_INVALID` classification + structured log + directive evaluation proceeds rule-based |
| `truncate or summarize / then process` | Silent transformation assumption | `AI_INPUT_TRUNCATED` annotation + `AIAssessment` record with truncation flag + rule-based evaluation continues |
| `normalize time / execute at correct CST equivalent` | Operational description not a governance assertion | Scheduler `cycle_id` record with normalized `scheduled_at` (ISO-8601 UTC) + `execution_type = original` |
| `lock prevents duplicate execution` | Underspecified concurrency assertion | `processed_events` idempotency record + `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit record |
| `resume from last successful step` | Silent partial recovery assertion | `execution_type = recovery` trigger with full attribution including `orphaned_cycle_id` and `recovery_authorization_record_id` |
| Replay mode produces LIVE effects under degradation | Replay governance violation under stress | All replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` regardless of degradation state |
| `FINALIZED_COPY` mutated after provider failure | Immutable lineage violation | `IMMUTABLE_RECORD_MUTATION_BLOCKED` event; mutation attempt is auditable and non-destructive |

---

## 3. EDGE-CONDITION DOMAINS

---

This file defines ten governance-oriented edge-condition domains. Each domain corresponds to a governance boundary that must hold not only under nominal conditions (validated in the parent contract) but also under the adversarial, concurrent, and degraded conditions defined below.

| Domain | Code prefix | Governance boundary stressed |
|---|---|---|
| Replay edge conditions | ECR | AP-RT2, ROS-1, ROS-2, ROS-4 |
| Regeneration integrity conditions | ECRG | FAD-2, IML-2, ROS-5 |
| Attribution-loss conditions | ECA | ATT-1 through ATT-5, INV-5 |
| Stale AI conditions | ECAI | AIG-2, AIG-3, AIG-4, AIG-5 |
| Duplicate orchestration conditions | ECDO | CID-1, CID-2, ROG-5, PBG-3 |
| Config V2 activation race conditions | ECCV | GPC-1, GPC-4, CV2-4, INV-2, INV-3 |
| Scheduler orphan-window conditions | ECSO | RGS-2, DEG-3, OIG-5, ATT-4 |
| Provider synchronization lag conditions | ECPL | PBG-5, DEG-4, DEG-1 |
| Degradation escalation conditions | ECDE | RGS-1 through RGS-5, DEG-1 through DEG-5 |
| Immutable lineage protection conditions | ECIL | IML-1 through IML-4, INV-1, INV-6, FAD-1, FAD-6 |

Each domain section defines the stress conditions, the edge-condition scenarios, and the prohibited assertions specific to that domain.

---

## 4. REPLAY EDGE CONDITIONS

---

### ECR-1 — Replay Against Partially Incomplete Warehouse Record

**Governance contract:** `runtime/system_loop.md` §7.3, §6.3, ROS-3

**Edge condition:** Historical warehouse record is partially populated — some governance fields are present, some are absent (e.g., `config_version_id` is present but `prompt_version` is null).

**Given:**

* `execution_type = replay`
* `historical_config_version_id` resolves to V1
* `warehouse.snapshot_ai_narratives` record exists but `prompt_version IS NULL`

**When:**

* Replay Orchestration Loop evaluates AI advisory content for the replay context

**Then:**

* `AIAssessment.ai_governance_tier = FINALIZED_COPY` is preserved (warehouse sourced)
* `replay_partial = true` is set in the replay diagnostic record
* `AI_ATTRIBUTION_FIELD_MISSING_prompt_version` warning is emitted
* No live AI inference is triggered to fill the gap
* `governance_scope = REPLAY_ONLY` is maintained — the missing field does not unlock LIVE inference

**Prohibited assertions:**

* Live AI inference was triggered because a warehouse attribution field was null
* `replay_partial` remained `false` when attribution fields were missing
* `governance_scope` changed from `REPLAY_ONLY` due to the incomplete record

---

### ECR-2 — Replay Against a Student Whose Historical Config Version Is SUPERSEDED

**Governance contract:** `runtime/system_loop.md` §7.3, GPC-5, ROS-2

**Edge condition:** The `historical_config_version_id` for the replay context is a SUPERSEDED version; the current ACTIVE version is V3 (V1 and V2 are SUPERSEDED).

**Given:**

* `execution_type = replay`
* `historical_config_version_id = V1` (V1 is SUPERSEDED, V3 is now ACTIVE)
* Replay cycle is initiated for a `cycle_date` governed by V1

**When:**

* Replay Orchestration Loop resolves thresholds for directive evaluation

**Then:**

* Thresholds are resolved from V1 (SUPERSEDED) — not from the current ACTIVE version V3
* `RetryPolicyAssessment.config_version_id = V1`
* `EligibilityAssessment.config_version_id = V1`
* `SUPERSEDED_CONFIG_USED_FOR_REPLAY` annotation is emitted in the replay diagnostic record
* LIVE orchestration is not influenced — `governance_scope = REPLAY_ONLY` is preserved

**Prohibited assertions:**

* Replay applied the current ACTIVE config version (V3) to a context governed by V1
* SUPERSEDED status of V1 blocked the replay from resolving thresholds

---

### ECR-3 — Replay Triggered Concurrently With an Ongoing LIVE Cycle for the Same Student

**Governance contract:** `runtime/system_loop.md` AP-RT2, `runtime/scheduler_design.md` §5.3, CID-3

**Edge condition:** A LIVE orchestration cycle is in progress for student S1 at the same time a replay cycle is initiated for the same student's historical context.

**Given:**

* LIVE cycle with `execution_type = original`, `correlation_id = COR-LIVE-01` is in progress for student S1
* Replay cycle with `execution_type = replay`, `replay_cycle_id = RC-01` is initiated for student S1's historical context

**When:**

* Both cycles run concurrently

**Then:**

* Replay cycle uses separate idempotency namespace `(source_artifact_id, replay_cycle_id)` — not the LIVE cycle idempotency namespace
* Replay outputs carry `governance_scope = REPLAY_ONLY` — they do not interfere with LIVE cycle records
* LIVE cycle outputs carry `governance_scope = AUTHORIZED` — they are not tagged `REPLAY_ONLY`
* No replay record is consumed as a LIVE orchestration result
* Both cycles emit independent completion records

**Prohibited assertions:**

* Replay cycle acquired the LIVE idempotency window for student S1
* Replay outputs were consumed as part of the LIVE cycle for student S1
* LIVE cycle was blocked or delayed by the concurrent replay

---

### ECR-4 — Replay Initiated When Historical FINALIZED_COPY Record Has a Fingerprint Mismatch

**Governance contract:** `runtime/system_loop.md` §7.4, §9.3, AIG-3

**Edge condition:** The AI narrative stored in `warehouse.snapshot_ai_narratives` for the replayed student has a `content_fingerprint` that does not match the fingerprint recorded in the original finalization audit record.

**Given:**

* `execution_type = replay`
* `warehouse.snapshot_ai_narratives` record exists for `(student_id = S1, snapshot_month = 2026-05)`
* Fingerprint of stored content does not match `expected_fingerprint` in the finalization audit record

**When:**

* Replay Orchestration Loop reads the AI narrative from warehouse

**Then:**

* `FINALIZED_COPY_FINGERPRINT_MISMATCH` event is emitted with: `student_id` (opaque), `snapshot_month`, `expected_fingerprint`, `observed_fingerprint`, `correlation_id`
* `replay_partial = true` is set
* `fingerprint_comparison_outcome = DIVERGENT` is recorded in the replay diagnostic record
* No live AI inference is triggered to regenerate the narrative
* Replay continues with `AIAssessment.ai_governance_tier = FINALIZED_COPY_DIVERGENT` annotation
* The divergence is observable and attributable — not silently accepted or silently rejected

**Prohibited assertions:**

* Live AI inference was triggered because the fingerprint mismatched
* The mismatch was silently accepted without an observable event
* The replay was blocked entirely by a fingerprint mismatch

---

### ECR-5 — Replay of a Cycle Where the Scheduler Record Was Never Written

**Governance contract:** `runtime/scheduler_design.md` §8.2, RGS-2, OIG-5

**Edge condition:** The historical `cycle_id` referenced by the replay request does not exist in the scheduler records (the original cycle crashed before writing its trigger record).

**Given:**

* `execution_type = replay`
* `source_artifact_id = SA-ORPHAN` references an `orphaned_cycle_id` for which no scheduler trigger record exists
* Replay is initiated by an Operational Administrator

**When:**

* Replay Orchestration Scheduler evaluates the replay trigger

**Then:**

* `REPLAY_SOURCE_SCHEDULER_RECORD_MISSING` event is emitted with `orphaned_cycle_id`, `replay_initiated_by`, `correlation_id`
* `replay_partial = true` is set
* Replay proceeds using available student state records and warehouse data as the historical context
* `fingerprint_comparison_outcome = PARTIAL` reflects that the scheduler source context is unavailable
* Replay diagnostic record documents the missing source record as a governance limitation

**Prohibited assertions:**

* Replay was blocked entirely because the scheduler trigger record was missing
* Replay proceeded without emitting a `REPLAY_SOURCE_SCHEDULER_RECORD_MISSING` event

---

## 5. REGENERATION INTEGRITY EDGE CONDITIONS

---

### ECRG-1 — Regeneration When Warehouse Is Partially Available (One Table Accessible, One Inaccessible)

**Governance contract:** `spec/01_requirements.md` FAD-2, `runtime/system_loop.md` §7.5, IML-2

**Edge condition:** `warehouse.student_snapshots` is accessible but `warehouse.snapshot_ai_narratives` is unavailable due to a transient database partition.

**Given:**

* Report Generation Scheduler fires in `execution_type = regeneration`
* `warehouse.student_snapshots` is accessible
* `warehouse.snapshot_ai_narratives` is unavailable (timeout or connection error)

**When:**

* Report Generation Loop attempts regeneration

**Then:**

* Regeneration is not silently completed with partial data
* `REGENERATION_WAREHOUSE_PARTIAL` event is emitted with: `accessible = ["student_snapshots"]`, `inaccessible = ["snapshot_ai_narratives"]`, `correlation_id`
* Regeneration cycle completes with `outcome = partial_failure`
* No external API calls are made to compensate for the missing warehouse data (FAD-2 is absolute)
* `output_identical = false` flag is set — regenerated and original reports cannot be verified as identical

**Prohibited assertions:**

* Regeneration silently completed using only `student_snapshots` without flagging the missing AI narrative data
* An AI provider call was made to fill the gap in the absence of warehouse data

---

### ECRG-2 — Regeneration Triggered Twice Concurrently for the Same Report

**Governance contract:** `spec/04_idempotency_concurrency.md` Domain 3, STG-3

**Edge condition:** Two concurrent regeneration triggers arrive for the same `(cohort_id, report_month)`.

**Given:**

* `(cohort_id = C1, report_month = 2026-05)` snapshot data exists in warehouse
* Two Report Generation Scheduler instances simultaneously fire in `execution_type = regeneration`

**When:**

* Both instances attempt to write a regeneration job record for `(C1, 2026-05)`

**Then:**

* First write wins — idempotency gate on `(cohort_id, report_month, execution_type = regeneration)` fires
* Second trigger is a no-op
* `DUPLICATE_REGENERATION_SUPPRESSED` audit record is produced for the second trigger
* Only one regenerated report is produced
* No external API calls are made by either trigger (FAD-2 is absolute)

**Prohibited assertions:**

* Two regenerated reports were produced for the same `(cohort_id, report_month)`
* Duplicate suppression was silent without an audit record

---

### ECRG-3 — Regeneration Produces Output That Differs From Original

**Governance contract:** `spec/01_requirements.md` FAD-2, IML-2, ROS-5

**Edge condition:** Regenerated report output differs from the original despite identical warehouse inputs — indicating a non-deterministic regeneration path.

**Given:**

* `(cohort_id = C1, report_month = 2026-05)` FINALIZED snapshot data exists in warehouse
* Original report `content_fingerprint = ORIG-FP-001`
* Report Generation Loop executes regeneration

**When:**

* Regenerated report is produced and its fingerprint is computed

**Then:**

* `output_identical` is evaluated by comparing `regenerated_content_fingerprint` against `ORIG-FP-001`
* If fingerprints diverge: `REGENERATION_NON_DETERMINISM_DETECTED` event is emitted with both fingerprints and `correlation_id`
* `output_identical = false` is set in the regeneration job record
* Escalation candidacy signal is produced: `escalation_type = REGENERATION_NON_DETERMINISM`
* Non-determinism is observable — never silently accepted as valid

**Prohibited assertions:**

* Non-deterministic regeneration output was silently accepted as a valid regenerated report
* `output_identical` flag was set to `true` when fingerprints diverged

---

## 6. ATTRIBUTION-LOSS EDGE CONDITIONS

---

### ECA-1 — Correlation ID Lost at Provider Delivery Boundary

**Governance contract:** `runtime/system_loop.md` §11.1, §11.3, ATT-1, INV-5

**Edge condition:** The `correlation_id` propagated through the orchestration chain is absent from the `ghl_messages` provider delivery record due to a provider delivery service bug or payload serialization error.

**Given:**

* Orchestration cycle with `correlation_id = COR-001` produces `OrchestrationIntent` and delegates to outreach orchestration service
* Provider delivery service creates a `ghl_messages` record without `correlation_id`

**When:**

* Governance observability layer audits the delivery record

**Then:**

* `ATTRIBUTION_FIELD_MISSING_correlation_id` event is emitted with `ghl_messages.id`, `attempted_correlation_id = COR-001`
* The delivery record is flagged as a governance defect — not silently accepted
* Escalation candidacy signal produced: `escalation_type = ATTRIBUTION_CONTINUITY_FAILURE`
* All downstream forensic queries for `COR-001` will identify the gap in the `ghl_messages` table
* The `OrchestrationIntent` and `processed_events` records remain valid — only the `ghl_messages` record is defective

**Prohibited assertions:**

* Attribution loss at the provider delivery boundary was silently accepted
* A delivery record without `correlation_id` was treated as a valid governance record

---

### ECA-2 — Causation ID Absent From a RETRY_OUTREACH Intent

**Governance contract:** `runtime/system_loop.md` §4.2, §11.2, ATT-2

**Edge condition:** Retry Orchestration Loop produces a `RETRY_OUTREACH` intent without a `causation_id` — breaking the lineage chain from the originating intent.

**Given:**

* `OrchestrationIntent.intent_id = INT-001` was produced for initial outreach
* Retry Orchestration Loop evaluates the student and attempts to produce `RETRY_OUTREACH` intent
* `causation_id` field is null or absent in the retry intent record

**When:**

* Governance observability layer audits the retry intent record

**Then:**

* `ATTRIBUTION_FIELD_MISSING_causation_id` event is emitted with `retry_intent_id`, `expected_causation_id_source = INT-001`, `correlation_id`
* The retry intent is flagged as a governance defect — it is persisted with the defect annotation, not silently dropped
* `CAUSATION_LINEAGE_BROKEN` flag is set on the retry intent record
* Escalation candidacy signal produced: `escalation_type = ATTRIBUTION_CONTINUITY_FAILURE`
* The retry dispatch proceeds under the `CAUSATION_LINEAGE_BROKEN` annotation — the defect does not block execution but is observable

**Prohibited assertions:**

* `RETRY_OUTREACH` intent was persisted without a `causation_id` without emitting a governance defect event
* Attribution defect silently blocked or silently permitted the retry without an observable record

---

### ECA-3 — Scheduler Attribution Discontinuity: cycle_id Not Propagated to Loop Start Record

**Governance contract:** `runtime/scheduler_design.md` §9.1, ATT-3, AC-SCH8

**Edge condition:** Orchestration Evaluation Scheduler fires and generates `cycle_id = SCH-001`, but the triggered orchestration loop does not receive or record the `cycle_id` in its loop start record.

**Given:**

* Orchestration Evaluation Scheduler fires and writes a trigger record with `cycle_id = SCH-001`
* Orchestration loop begins but its loop start record has `cycle_id IS NULL`

**When:**

* Governance observability layer audits the loop start record

**Then:**

* `ATTRIBUTION_FIELD_MISSING_cycle_id` event is emitted for the loop start record
* `cycle_id = SCH-001` cannot be resolved from the loop start record
* The forensic chain `SCH-001 → COR-002 → OrchestrationIntent` is broken at the loop start
* `SCHEDULER_ATTRIBUTION_DISCONTINUITY` event is emitted with `expected_cycle_id = SCH-001`, `loop_correlation_id = COR-002`
* Escalation candidacy signal produced: `escalation_type = ATTRIBUTION_CONTINUITY_FAILURE`

**Prohibited assertions:**

* `cycle_id` absence from the loop start record was silently accepted as a valid loop record
* Attribution discontinuity was not observable in structured logs

---

### ECA-4 — Recovery Attribution Incomplete: Missing Required Field

**Governance contract:** `runtime/scheduler_design.md` §8.3, AP-SCH11, ATT-4

**Edge condition:** A recovery cycle trigger record is written but one of the required attribution fields is absent (e.g., `recovery_authorization_record_id` is null).

**Given:**

* Orphaned cycle detected for `cycle_date = 2026-06-01`
* Recovery cycle trigger record is written with `execution_type = recovery`, `orphaned_cycle_id = SCH-ORPHAN-01`
* `recovery_authorization_record_id IS NULL`

**When:**

* Recovery Orchestration Loop attempts to begin the recovery cycle

**Then:**

* `RECOVERY_ATTRIBUTION_INCOMPLETE` event is emitted with the missing field name and `orphaned_cycle_id`
* Recovery cycle does NOT proceed until `recovery_authorization_record_id` is provided
* This is a hard gate — recovery without authorization attribution is prohibited (AP-SCH11)
* No recovery orchestration evaluation begins
* Escalation candidacy signal produced: `escalation_type = RECOVERY_AUTHORIZATION_MISSING`

**Prohibited assertions:**

* Recovery cycle proceeded without a `recovery_authorization_record_id`
* Attribution incompleteness was silently accepted and the recovery cycle started anyway

---

### ECA-5 — AI Attribution Metadata Missing From ai_insights Record

**Governance contract:** `spec/01_requirements.md` FAD-6, ATT-5, IML-3

**Edge condition:** AI Refresh Orchestration Loop produces a new `ai_insights` record but `model_used` or `prompt_version` is null due to a provider response deserialization error.

**Given:**

* AI Refresh Orchestration Loop completes an AI advisory call
* Provider response is received but `model_used` cannot be extracted from the response (field absent or malformed)

**When:**

* `ai_insights` record is persisted

**Then:**

* `AI_ATTRIBUTION_FIELD_MISSING_model_used` event is emitted with `insight_id`, `correlation_id`
* `ai_insights` record is persisted with `model_used = UNKNOWN` (explicit unknown marker, not null)
* `ai_governance_tier = AI_GENERATED_ATTRIBUTION_INCOMPLETE` annotation is applied
* Record is flagged for forensic review — not silently accepted as a complete attribution record
* Attribution metadata is immutable after persistence — `model_used = UNKNOWN` cannot be updated retroactively (FAD-6)

**Prohibited assertions:**

* `ai_insights` record was persisted with `model_used IS NULL` without an observable event
* Attribution incomplete record was retroactively updated after `AI_GENERATED` state

---

## 7. STALE AI EDGE CONDITIONS

---

### ECAI-1 — STALE AI Advisory Remains Advisory-Only When Student Enters Escalation Candidacy

**Governance contract:** `runtime/system_loop.md` §9.2, AIG-2, AC-RT11

**Edge condition:** A student meets rule-based escalation candidacy criteria simultaneously with having a STALE AI advisory. The stale advisory recommends a higher escalation severity than the rule-based assessment.

**Given:**

* `AIAssessment.ai_governance_tier = STALE` (beyond `ai_insight_ttl_hours` from Config V2 Group H)
* `AIAssessment.advisory_content.recommended_escalation_severity = CRITICAL`
* Rule-based escalation assessment produces `EscalationOrchestrationAssessment.severity = MEDIUM`
* `execution_mode = LIVE`

**When:**

* Escalation Polling Loop evaluates escalation candidacy

**Then:**

* `EscalationOrchestrationAssessment.severity = MEDIUM` — governed by rule-based assessment
* STALE AI advisory does not elevate severity to CRITICAL (AP-AI11)
* `STALE_AI_SEVERITY_ELEVATION_BLOCKED` annotation is applied to the escalation candidacy record
* STALE AI advisory content is present as advisory context — it informs but does not authorize escalation severity
* `STALE` annotation is present in the escalation candidacy record

**Prohibited assertions:**

* STALE AI advisory elevated escalation severity to CRITICAL in LIVE mode (AP-AI11)
* STALE AI annotation blocked the escalation candidacy assessment entirely

---

### ECAI-2 — STALE AI Advisory During Replay: No Live Refresh

**Governance contract:** `runtime/system_loop.md` §7.2, AP-AI5, AIG-5

**Edge condition:** Replay context requires AI advisory evaluation. The `warehouse.snapshot_ai_narratives` record exists but is marked STALE relative to the original cycle's TTL at the time of the original execution.

**Given:**

* `execution_type = replay`
* `warehouse.snapshot_ai_narratives` record exists for the replayed student
* Record was marked STALE (beyond `ai_insight_ttl_hours`) at original cycle time
* Current ACTIVE config `ai_insight_ttl_hours` is different from historical config V1 value

**When:**

* Replay Orchestration Loop evaluates AI advisory content

**Then:**

* AI advisory content is sourced from `warehouse.snapshot_ai_narratives` — no live AI inference is triggered (AP-AI5)
* `ai_governance_tier = FINALIZED_COPY` — FINALIZED_COPY takes precedence over STALE classification
* Staleness annotation is propagated from the historical record into the replay diagnostic record
* `fingerprint_comparison_outcome` reflects the original STALE classification
* No live AI inference is triggered to refresh stale content during replay — this is an absolute prohibition

**Prohibited assertions:**

* Live AI inference was triggered during replay to refresh a STALE advisory
* STALE classification during replay caused the advisory to be excluded from the diagnostic record

---

### ECAI-3 — AI Provider Unavailable During Snapshot Finalization

**Governance contract:** `runtime/system_loop.md` §10.4, `failure/llm_failures.md`, AIG-4

**Edge condition:** AI provider becomes unavailable precisely when Snapshot Finalization Loop is evaluating whether to finalize a student whose `ai_insights` record is in `AI_GENERATED` state (not yet FINALIZED_COPY).

**Given:**

* Snapshot Finalization Loop evaluates `(student_id = S1, snapshot_month = 2026-05)`
* `ai_insights` record for S1 is in `AI_GENERATED` state
* AI provider becomes unavailable mid-finalization evaluation
* AI circuit breaker state transitions to OPEN

**When:**

* Snapshot Finalization Loop attempts to read the AI narrative for inclusion in the finalization record

**Then:**

* `AI_PROVIDER_UNAVAILABLE` event emitted with `correlation_id`
* Finalization proceeds with `ai_content_stale = true` flag
* `ai_governance_tier = UNAVAILABLE` is annotated on the finalization record
* Snapshot finalization is NOT blocked (governed by AIG-4)
* The finalization record is written without the AI narrative — it carries `AI_NARRATIVE_UNAVAILABLE_AT_FINALIZATION` annotation
* Physical copy to `warehouse.snapshot_ai_narratives` is not attempted when AI narrative is unavailable — no null record is written to the warehouse

**Prohibited assertions:**

* Snapshot finalization was blocked entirely by AI provider unavailability
* A null or empty AI narrative was physically copied to `warehouse.snapshot_ai_narratives`

---

### ECAI-4 — FINALIZED_COPY Read Attempted by AI Refresh Loop

**Governance contract:** `runtime/system_loop.md` §9.3, AP-OWN15, AIG-3, IML-1

**Edge condition:** AI Refresh Orchestration Loop evaluates a student whose `ai_governance_tier = FINALIZED_COPY`. The loop should skip the student without attempting any evaluation or write.

**Given:**

* `ai_insights` record for `(student_id = S1, insight_type = MONTHLY_NARRATIVE)` has `ai_governance_tier = FINALIZED_COPY`
* AI Refresh Orchestration Loop evaluates S1 as a candidate for advisory refresh

**When:**

* AI Refresh Loop evaluates whether to trigger an AI advisory refresh for S1

**Then:**

* `ai_governance_tier = FINALIZED_COPY` check fires — skip is immediate
* No AI provider call is made for S1
* No `ai_insights` record mutation is attempted
* Skip record emitted: `skip_reason = FINALIZED_COPY_SKIP`, `student_id` (opaque), `correlation_id`
* Skip is observable — never silent

**Prohibited assertions:**

* AI Refresh Loop made an AI provider call for a `FINALIZED_COPY` student
* `warehouse.snapshot_ai_narratives` record was evaluated for overwrite potential
* Skip was silent without a structured skip record

---

## 8. DUPLICATE ORCHESTRATION EDGE CONDITIONS

---

### ECDO-1 — Duplicate LIVE Orchestration Triggered by Concurrent Loop Instances

**Governance contract:** `runtime/system_loop.md` AP-RT10, `spec/04_idempotency_concurrency.md` §2.2, CID-2

**Edge condition:** Config V2 Group A concurrency variable is set to a value that permits multiple loop instances. Both instances select the same student in the same window and race to write the idempotency record.

**Given:**

* Two concurrent Orchestration Evaluation Loop instances both select student S1 for evaluation
* Both instances attempt to write idempotency record `(student_id = S1, cycle_date = 2026-06-01, checkpoint_type = INITIATE_OUTREACH)` to `processed_events`

**When:**

* Both instances race to INSERT the idempotency record

**Then:**

* First INSERT wins (database-level unique constraint)
* Second INSERT detects a conflict and treats the trigger as a no-op
* `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit record is produced for the second attempt with `suppressed_by = IDEMPOTENCY_KEY_CONFLICT`
* Only one `OrchestrationIntent` is produced for student S1 in this cycle
* The concurrent conflict does not produce a duplicate `ghl_messages` record

**Prohibited assertions:**

* Two `OrchestrationIntent` records were produced for the same student in the same cycle
* Idempotency conflict was silent without a `DUPLICATE_ORCHESTRATION_SUPPRESSED` record

---

### ECDO-2 — Duplicate Webhook Delivery: Second Delivery Arrives After State Transition Completes

**Governance contract:** `runtime/system_loop.md` §10.6, PBG-3, `spec/04_idempotency_concurrency.md`

**Edge condition:** GHL delivers the same webhook `event_id = EVT-123` twice. The first delivery was processed and resulted in a state transition. The second delivery arrives after the state transition is complete.

**Given:**

* GHL webhook `event_id = EVT-123` was processed: state transition from `QUEUED` to `CONTACTED` is complete
* `processed_events` record for `EVT-123` exists with `outcome = processed`
* GHL delivers `EVT-123` a second time

**When:**

* Webhook ingestion service processes the second `EVT-123` delivery

**Then:**

* `processed_events` dedup lookup detects the existing `EVT-123` record before any state management call
* No second state management service call is made
* `DUPLICATE_EVENT_SUPPRESSED` audit log entry is produced with `event_id = EVT-123`, `suppression_reason = PROCESSED_EVENT_DUPLICATE`, `correlation_id`
* Student state remains `CONTACTED` — no duplicate transition is attempted
* Suppression is observable — never silent

**Prohibited assertions:**

* Second webhook delivery triggered a second state transition
* Duplicate suppression was silent without an audit log entry

---

### ECDO-3 — Idempotency Key Collision Between Retry and Initial Outreach in the Same Cycle

**Governance contract:** `runtime/system_loop.md` §4.2, §4.8, ROG-5, `spec/04_idempotency_concurrency.md` Domain 1

**Edge condition:** A scheduler mis-fire triggers both the Orchestration Evaluation Loop and the Retry Orchestration Loop in the same window for the same student. Both attempt to write overlapping idempotency keys.

**Given:**

* Orchestration Evaluation Loop produces `(student_id = S1, cycle_date = 2026-06-01, checkpoint_type = INITIATE_OUTREACH)` idempotency record
* Retry Orchestration Loop concurrently attempts to write `(student_id = S1, cycle_date = 2026-06-01, checkpoint_type = RETRY_OUTREACH, contact_attempt = 1)` idempotency record

**When:**

* Both loops write to `processed_events` in the same window

**Then:**

* The two records have different `checkpoint_type` values — they do NOT collide (distinct idempotency keys)
* If the Retry Orchestration Loop correctly checks `RetryPolicyAssessment` before producing a retry intent, it should find `retry_authorized = false` (student was just initiated, not in `NO_RESPONSE` state)
* If the retry check fails and a duplicate `RETRY_OUTREACH` intent is produced anyway: `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit record is produced
* `IDEMPOTENCY_NAMESPACE_COLLISION_RISK` event is emitted if both loops target the same student in the same window outside their expected cadence

**Prohibited assertions:**

* Both `INITIATE_OUTREACH` and `RETRY_OUTREACH` intents were produced for the same student in the same cycle window without a governance authorization path for both
* Idempotency key overlap was silent without an observable event

---

### ECDO-4 — Duplicate Finalization Trigger: FINALIZED State Already Written

**Governance contract:** `spec/03_state_transition_rules.md` Domain 2, STG-3, `spec/04_idempotency_concurrency.md` Domain 2

**Edge condition:** Snapshot Finalization Scheduler fires a duplicate trigger for a snapshot that is already FINALIZED. The finalization service must detect this without attempting any warehouse write.

**Given:**

* `(student_id = S1, snapshot_month = 2026-05)` snapshot state = `FINALIZED`
* Snapshot Finalization Scheduler fires a second trigger for the same key

**When:**

* Snapshot Finalization Loop receives the second trigger

**Then:**

* Idempotency gate fires on `(student_id, snapshot_month)` key before any warehouse evaluation
* `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` audit record is produced with: `student_id` (opaque), `snapshot_month`, `correlation_id`, `suppression_reason = ALREADY_FINALIZED`
* No mutation of `warehouse.student_snapshots` occurs
* No mutation of `warehouse.snapshot_ai_narratives` occurs
* No AI provider call is made
* Second trigger is a complete no-op — observable and attributable

**Prohibited assertions:**

* Any warehouse record was evaluated for mutation after FINALIZED state
* Duplicate finalization suppression was silent without a `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` record

---

## 9. CONFIG V2 ACTIVATION RACE CONDITIONS

---

### ECCV-1 — Config Version Activation While Evaluation Cycle Is In Progress

**Governance contract:** `spec/03_state_transition_rules.md` Domain 5, GPC-4, CV2-4, INV-2

**Edge condition:** A Governance Administrator activates a new config version (V1 → SUPERSEDED, V2 → ACTIVE) while an ongoing Orchestration Evaluation Loop cycle is mid-execution.

**Given:**

* Orchestration Evaluation Loop cycle began with `config_version_id = V1` (ACTIVE)
* Mid-cycle: V1 is transitioned to SUPERSEDED and V2 is activated by a Governance Administrator
* The loop has processed 50 students under V1 and has 50 remaining

**When:**

* Loop continues processing remaining students

**Then:**

* Students processed before activation used V1 thresholds — their records carry `config_version_id = V1`
* Students processed after activation: the loop resolves the ACTIVE config version at evaluation time — they carry `config_version_id = V2` for their assessments
* No student is evaluated with a null `config_version_id`
* `CONFIG_VERSION_MID_CYCLE_TRANSITION` event is emitted with: `cycle_correlation_id`, `v1_id`, `v2_id`, `transition_at`, `students_processed_under_v1`, `students_processed_under_v2`
* The cycle completion record documents the mid-cycle transition

**Prohibited assertions:**

* Any student's assessment record carries `config_version_id IS NULL` after the mid-cycle transition
* Mid-cycle activation was silent without an observable transition event

---

### ECCV-2 — Simultaneous ACTIVE Assertion During Config Activation (INV-2 Under Stress)

**Governance contract:** `spec/03_state_transition_rules.md` Domain 5, INV-2

**Edge condition:** A race condition at the database level causes both V1 and V2 to briefly appear as ACTIVE simultaneously during a non-atomic activation transaction.

**Given:**

* Config version V1 is ACTIVE
* A governance-authorized config activation transaction begins: `UPDATE config_version_registry SET status = SUPERSEDED WHERE id = V1; UPDATE config_version_registry SET status = ACTIVE WHERE id = V2;`
* Between the two UPDATE statements, a concurrent reader queries `config_version_registry` for `status = ACTIVE`

**When:**

* Concurrent reader receives a result set

**Then:**

* The two UPDATEs are wrapped in a single database transaction — the concurrent reader either sees the pre-transaction state (V1 = ACTIVE, V2 = DRAFT) or the post-transaction state (V1 = SUPERSEDED, V2 = ACTIVE)
* No read-committed window exists where both V1 and V2 are ACTIVE simultaneously
* `CONFIG_VERSION_ACTIVATION_ATOMIC` constraint is validated by querying `count(*) WHERE status = ACTIVE` both before and after the transaction — count must equal 1 at both points
* If a race produces a count of 2: `CONFIG_VERSION_INVARIANT_VIOLATED` alert event is emitted and escalation candidacy is generated immediately

**Prohibited assertions:**

* `count(*) WHERE status = ACTIVE > 1` was ever valid (INV-2)
* The activation transaction allowed a concurrent reader to observe a non-atomic state

---

### ECCV-3 — Config Version Rollback Attempted After Activation (STG-4 Under Stress)

**Governance contract:** `spec/03_state_transition_rules.md` Domain 5, STG-4

**Edge condition:** A Governance Administrator or automated service attempts to restore V1 to ACTIVE after V2 has been successfully activated and V1 is SUPERSEDED. This might occur as a "rollback" in response to a production issue.

**Given:**

* V2 is ACTIVE; V1 is SUPERSEDED
* An attempt is made to set `config_version_registry SET status = ACTIVE WHERE id = V1`

**When:**

* The rollback attempt is evaluated by the config version governance service

**Then:**

* The rollback is blocked — SUPERSEDED → ACTIVE is a forbidden transition
* `CONFIG_VERSION_ROLLBACK_BLOCKED` event is emitted with: `attempted_version_id = V1`, `current_status = SUPERSEDED`, `blocking_rule = ROLLBACK_FORBIDDEN`, `correlation_id`
* V1 remains SUPERSEDED; V2 remains ACTIVE
* A new config version V3 must be created if the intent is to revert to V1's thresholds
* Escalation candidacy signal produced: `escalation_type = CONFIG_VERSION_GOVERNANCE_VIOLATION`

**Prohibited assertions:**

* A SUPERSEDED config version was restored to ACTIVE
* Rollback attempt was silent without a `CONFIG_VERSION_ROLLBACK_BLOCKED` event

---

### ECCV-4 — Prospective-Only Enforcement: No Retroactive Re-Evaluation After Activation (INV-3 Under Stress)

**Governance contract:** `spec/01_requirements.md` FAD-3, INV-3, GPC-5

**Edge condition:** After V2 is activated, an automated process attempts to re-evaluate all historical `OrchestrationIntent` records from prior cycles using V2 thresholds (e.g., a "backfill" job).

**Given:**

* V2 activated on 2026-06-02
* A backfill process queries `OrchestrationIntent` records with `cycle_date < 2026-06-02` and attempts to update their `config_version_id` to V2

**When:**

* Backfill process attempts the update

**Then:**

* Update is blocked — `student_timeline_events` is append-only; in-place updates are prohibited (IML-4)
* `RETROACTIVE_CONFIG_UPDATE_BLOCKED` event is emitted for each blocked update attempt
* No historical record's `config_version_id` is changed to V2
* `APPEND_ONLY_MUTATION_BLOCKED` events are emitted for each attempted in-place mutation
* Escalation candidacy signal produced: `escalation_type = RETROACTIVE_CONFIG_APPLICATION_ATTEMPT`

**Prohibited assertions:**

* Any `OrchestrationIntent` record with `cycle_date < 2026-06-02` had its `config_version_id` changed to V2
* The backfill attempt was silent without observable blocking events

---

## 10. SCHEDULER ORPHAN-WINDOW EDGE CONDITIONS

---

### ECSO-1 — Scheduler Orphan-Window Detection: Missed Trigger Not Detected Until Next Cycle

**Governance contract:** `runtime/scheduler_design.md` §8.2, RGS-2, OIG-5

**Edge condition:** Orchestration Evaluation Scheduler crashes and its missed trigger is not detected until the next scheduled cycle fires. The orphan window spans one full cycle date.

**Given:**

* Orchestration Evaluation Scheduler was expected to trigger for `cycle_date = 2026-06-01`
* Scheduler process crashed — no trigger record was written for `cycle_date = 2026-06-01`
* Scheduler recovers and triggers for `cycle_date = 2026-06-02`
* During the `2026-06-02` trigger, orphan detection scans for missed windows

**When:**

* Orphan detection identifies `cycle_date = 2026-06-01` as a missed window

**Then:**

* `SCHEDULER_ORPHAN_WINDOW_DETECTED` event is emitted with: `orphaned_cycle_date = 2026-06-01`, `detection_cycle_date = 2026-06-02`, `lag_hours` (computed)
* Recovery candidacy record is created — recovery cycle is NOT automatically triggered
* Operational Administrator authorization is required before recovery cycle fires
* The `2026-06-02` cycle proceeds normally — orphan detection does not block it

**Prohibited assertions:**

* Recovery cycle was automatically triggered without Operational Administrator authorization
* Orphan window detection was silent without a `SCHEDULER_ORPHAN_WINDOW_DETECTED` event
* The `2026-06-02` cycle was blocked by detection of the `2026-06-01` orphan window

---

### ECSO-2 — Scheduler Drift: Same Cycle Triggered Multiple Times Within a Single Window

**Governance contract:** `runtime/scheduler_design.md` §5.2, CID-1, AP-SCH3

**Edge condition:** Scheduler drift (clock skew or process restart) causes the same `cycle_date` to be triggered more than once within the window.

**Given:**

* Orchestration Evaluation Scheduler fires for `cycle_date = 2026-06-01` — trigger record written with `cycle_id = SCH-001`
* Scheduler drift causes a second fire for `cycle_date = 2026-06-01` — trigger record `cycle_id = SCH-002` is generated

**When:**

* Second trigger `SCH-002` is evaluated

**Then:**

* Idempotency gate on `(scheduler_domain = orchestration_evaluation, cycle_date = 2026-06-01)` detects the existing `SCH-001` record
* `SCH-002` trigger is suppressed — `TRIGGER_SUPPRESSED` record emitted with `suppression_reason = DUPLICATE_CYCLE_DATE_WINDOW`, `duplicate_of = SCH-001`
* No second orchestration loop is initiated for `cycle_date = 2026-06-01`
* Scheduler drift event is logged: `SCHEDULER_DRIFT_DETECTED` with `drift_magnitude` (time between SCH-001 and SCH-002 fires)

**Prohibited assertions:**

* A second orchestration loop executed for `cycle_date = 2026-06-01` from `SCH-002`
* Duplicate trigger suppression was silent without a `TRIGGER_SUPPRESSED` record

---

### ECSO-3 — Scheduler Degradation Cascade: One Domain's Failure Suppresses Another Domain's Trigger

**Governance contract:** `runtime/scheduler_design.md` §8.4, DEG-3, AC-SCH10

**Edge condition:** AI Refresh Scheduler degrades due to AI provider outage. The `SCHEDULER_DEGRADED` event for the AI domain incorrectly suppresses the Orchestration Evaluation Scheduler's trigger (cross-domain contamination).

**Given:**

* AI Refresh Scheduler receives `AI_PROVIDER_UNAVAILABLE` signal — correctly emits `SCHEDULER_DEGRADED` for `scheduler_domain = ai_refresh`
* Orchestration Evaluation Scheduler evaluates whether to fire
* A bug or misconfiguration causes the Orchestration Evaluation Scheduler to read the AI domain's `SCHEDULER_DEGRADED` state and suppress its own trigger

**When:**

* Governance observability layer audits the suppressed Orchestration Evaluation trigger

**Then:**

* `SCHEDULER_CROSS_DOMAIN_SUPPRESSION_DETECTED` event is emitted — this is a governance defect
* The suppressed Orchestration Evaluation trigger is logged as a governance defect, not a valid suppression
* Escalation candidacy signal produced: `escalation_type = SCHEDULER_CROSS_DOMAIN_CONTAMINATION`
* Orphan detection will identify the missing Orchestration Evaluation window and produce a recovery candidacy record

**Prohibited assertions:**

* Cross-domain scheduler suppression was silently accepted as a valid degradation behavior
* One domain's `SCHEDULER_DEGRADED` state was propagated to suppress other scheduler domains

---

### ECSO-4 — Observability Heartbeat Scheduler Continues During Maintenance Mode

**Governance contract:** `runtime/scheduler_design.md` §3.3, GPC-3, `runtime/system_loop.md` §3.3

**Edge condition:** `execution_mode = MAINTENANCE` suppresses all outreach orchestration triggers. The Observability Heartbeat Scheduler must continue firing — it is the exception to MAINTENANCE mode suppression.

**Given:**

* `execution_mode = MAINTENANCE`
* Orchestration Evaluation Scheduler evaluates — trigger is suppressed (`TRIGGER_SUPPRESSED` with `suppression_reason = MAINTENANCE_MODE`)
* Observability Heartbeat Scheduler evaluates in the same window

**When:**

* Observability Heartbeat Scheduler fires

**Then:**

* Observability Heartbeat trigger is NOT suppressed in MAINTENANCE mode
* Heartbeat trigger record emitted with `execution_mode = MAINTENANCE`, `scheduler_domain = observability_heartbeat`, `trigger_status = ACTIVE`
* System health monitoring continues during MAINTENANCE mode
* `MAINTENANCE_MODE_EXCEPTION_HEARTBEAT_ACTIVE` annotation is present in the heartbeat trigger record

**Prohibited assertions:**

* Observability Heartbeat Scheduler was suppressed during MAINTENANCE mode
* Heartbeat trigger was emitted without the `execution_mode = MAINTENANCE` annotation

---

## 11. PROVIDER SYNCHRONIZATION LAG EDGE CONDITIONS

---

### ECPL-1 — Synchronization Lag Exceeds Governance Threshold During Active Outreach Cycle

**Governance contract:** `runtime/system_loop.md` §10.7, §8.2, PBG-5, DEG-4

**Edge condition:** SQL Server sync lag exceeds `sql_server_max_sync_age_hours` (Config V2 Group K) during an active outreach orchestration cycle. Students whose trigger data is stale must be annotated, not silently skipped or blocked.

**Given:**

* `sync_lag_hours > sql_server_max_sync_age_hours` (Config V2 Group K) — sync is overdue
* 30 students are candidates for eligibility evaluation
* 20 of the 30 students have `student_trigger_data` records older than `sql_server_max_sync_age_hours`

**When:**

* Orchestration Evaluation Loop evaluates the 30-student batch

**Then:**

* `SYNC_LAG_EXCEEDED` event emitted with: `sync_lag_hours`, `threshold_hours`, `affected_student_count = 20`, `correlation_id`
* All 20 affected students' `OrchestrationIntent` records carry `STALE_SQL_SERVER_DATA` annotation
* Orchestration evaluation proceeds for all 30 students — sync lag is non-blocking
* No student is silently skipped due to stale trigger data
* Persistent sync backlog beyond secondary threshold generates escalation candidacy: `escalation_type = SYNC_LAG_GOVERNANCE_THRESHOLD_EXCEEDED`

**Prohibited assertions:**

* Any student was silently skipped due to stale trigger data without a `STALE_SQL_SERVER_DATA` annotation
* Sync lag blocked orchestration evaluation for any student
* `STALE_SQL_SERVER_DATA` annotation was absent from affected student records

---

### ECPL-2 — Provider Synchronization Lag: Inbound Webhook Received Before Sync Cycle Reflects New State

**Governance contract:** `runtime/system_loop.md` §8.2, §10.6, PBG-3, `spec/04_idempotency_concurrency.md`

**Edge condition:** GHL delivers a webhook for a student whose SQL Server sync has not yet propagated the latest academic data. The student's `student_trigger_data` record is stale relative to the webhook event timestamp.

**Given:**

* GHL webhook `event_id = EVT-200` arrives for student S1 indicating `call_outcome = CONNECTED`
* S1's `student_trigger_data` record has `last_synced_at = 6 hours ago` (within sync lag threshold)
* SQL Server has newer academic data for S1 that has not yet been synced

**When:**

* Webhook ingestion service processes `EVT-200`

**Then:**

* Webhook is processed and state transition occurs based on the current `student_trigger_data` record (source of truth at time of event processing)
* `STALE_TRIGGER_DATA_AT_WEBHOOK_PROCESSING` annotation is applied to the state transition record
* `sync_lag_hours` is recorded in the webhook processing record
* State transition proceeds — webhook processing is not blocked by sync lag
* Next sync cycle will update `student_trigger_data` — this does not retroactively change the webhook-driven state transition

**Prohibited assertions:**

* Webhook processing was blocked pending sync completion
* State transition record did not include the `STALE_TRIGGER_DATA_AT_WEBHOOK_PROCESSING` annotation when sync lag was present

---

### ECPL-3 — Synchronization Backlog Overflow: Escalation Candidacy Before Governance Threshold

**Governance contract:** `runtime/system_loop.md` §10.7, `runtime/scheduler_design.md` §4.7

**Edge condition:** SQL Server sync has failed for multiple consecutive cycles, causing `sync_lag_hours` to accumulate beyond the secondary escalation threshold (Config V2 Group K secondary variable).

**Given:**

* Primary `sql_server_max_sync_age_hours` threshold (Config V2 Group K): 4 hours
* Secondary escalation threshold (Config V2 Group K): 8 hours
* Current `sync_lag_hours = 12` — exceeds both thresholds

**When:**

* Orchestration Evaluation Loop evaluates the current batch

**Then:**

* `SYNC_LAG_EXCEEDED` event emitted for primary threshold violation (as in ECPL-1)
* `SYNC_BACKLOG_ESCALATION_THRESHOLD_EXCEEDED` event emitted for secondary threshold violation with `sync_lag_hours = 12`, `secondary_threshold_hours = 8`
* Escalation candidacy signal produced: `escalation_type = SYNC_BACKLOG_CRITICAL`, `escalation_severity = HIGH`
* All student records carry `STALE_SQL_SERVER_DATA` annotation
* Orchestration evaluation proceeds with stale data — escalation candidacy does not block evaluation
* Both threshold violations are resolved from Config V2 Group K — no hardcoded thresholds

**Prohibited assertions:**

* Escalation candidacy was not generated despite sync lag exceeding the secondary threshold
* Either threshold was derived from a hardcoded constant rather than Config V2 Group K

---

## 12. DEGRADATION ESCALATION EDGE CONDITIONS

---

### ECDE-1 — Simultaneous Provider Outage and AI Outage: Deterministic Multi-Domain Degradation

**Governance contract:** `runtime/system_loop.md` §10.2, §10.4, `failure/failure_playbook.md`, DEG-1, DEG-2

**Edge condition:** GHL provider outage and AI provider outage occur simultaneously. Both domains degrade at the same time during an active orchestration cycle.

**Given:**

* GHL provider circuit breaker state = OPEN (`PROVIDER_OUTAGE` event)
* AI provider circuit breaker state = OPEN (`AI_PROVIDER_UNAVAILABLE` event)
* `execution_mode = LIVE`

**When:**

* Orchestration Evaluation Loop evaluates candidates

**Then:**

* `PROVIDER_OUTAGE` structured log event emitted with `provider = ghl`, `correlation_id`
* `AI_PROVIDER_UNAVAILABLE` structured log event emitted with `correlation_id`
* Outbound dispatch blocked for all students: `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`
* AI advisory scope degraded: `AIAssessment.advisory_scope = UNAVAILABLE`
* Orchestration evaluation proceeds with rule-based evaluation only
* Inbound webhook ingestion continues normally
* SQL Server sync loop continues unaffected
* `degradation_cause = MULTI_DOMAIN_OUTAGE`, `affected_domains = ["ghl", "ai"]` documented in cycle completion record
* Two separate escalation candidacy signals produced — one per domain
* Retry budget is NOT consumed for provider-unavailable students

**Prohibited assertions:**

* Multi-domain outage caused either failure to be silently swallowed
* Inbound webhook ingestion was blocked by GHL outbound outage
* Rule-based orchestration evaluation was blocked by AI outage
* Retry budget was consumed during provider outage

---

### ECDE-2 — Cascading Degradation: Observability Pipeline Fails During Provider Outage

**Governance contract:** `runtime/system_loop.md` §10.8, RGS-5

**Edge condition:** GHL provider outage is active. During the outage, the observability pipeline (structured log destination) also becomes unavailable. Orchestration loops must continue and emit degradation signals to stderr.

**Given:**

* GHL provider circuit breaker state = OPEN
* Observability pipeline (log destination) becomes unavailable
* Orchestration loops are mid-execution

**Then:**

* Orchestration loops continue — observability failure does not block execution
* Structured log entries that fail to be written to the primary destination are redirected to stderr with `OBSERVABILITY_DEGRADED` flag
* `OBSERVABILITY_DEGRADED` flag appears in the next successful log record
* `MULTI_DOMAIN_DEGRADATION` annotation documents: `affected_domains = ["ghl", "observability"]`
* All `PROVIDER_OUTAGE` events that could not be written to the primary destination are replayed when observability recovers

**Prohibited assertions:**

* Orchestration loops were blocked by observability pipeline failure
* Provider outage events were silently lost because the observability pipeline was unavailable

---

### ECDE-3 — Degraded Replay: Provider Outage Active, Warehouse Accessible

**Governance contract:** `runtime/system_loop.md` §3.1 (DEGRADED), `runtime/scheduler_design.md` §3.1 (DEGRADED), DEG-5

**Edge condition:** Replay is triggered while `execution_mode = DEGRADED` (GHL provider outage active). Replay must be permitted because warehouse is accessible and historical config is resolvable. The DEGRADED execution mode does not restrict replay.

**Given:**

* `execution_mode = DEGRADED` (GHL provider outage active)
* Warehouse is accessible
* `historical_config_version_id = V1` is resolvable
* Replay Orchestration Scheduler is triggered for a historical diagnostic

**When:**

* Replay Orchestration Loop executes

**Then:**

* Replay is permitted — warehouse accessible and historical config resolvable
* All replay outputs carry `execution_type = replay`, `governance_scope = REPLAY_ONLY`, `execution_mode = DEGRADED`
* No LIVE effects are produced
* Degradation annotations are included in the replay diagnostic record: `degradation_cause = PROVIDER_OUTAGE_DEGRADED_MODE`
* `ProviderOrchestrationAssessment.outbound_suppressed = true` (replay suppresses LIVE dispatch regardless of mode)

**Prohibited assertions:**

* Replay was blocked in DEGRADED mode when warehouse and historical config were accessible
* Replay produced LIVE effects in DEGRADED mode
* DEGRADED execution mode annotation was absent from the replay diagnostic record

---

### ECDE-4 — Retry Budget Consumed During Provider Outage: Budget Protection Stress Test

**Governance contract:** `runtime/system_loop.md` §10.3, PBG-1, RGS-3

**Edge condition:** 10 retry-eligible students are evaluated while GHL provider circuit breaker is OPEN. None of their retry dispatches should consume retry budget.

**Given:**

* GHL provider circuit breaker state = OPEN
* 10 students with `state = NO_RESPONSE` are evaluated by Retry Orchestration Loop
* All 10 have elapsed `outreach_retry_window_days` (Config V2 Group A)
* All 10 have `contact_attempt < outreach_max_retry_attempts` (Config V2 Group A)

**When:**

* Retry Orchestration Loop evaluates all 10 students

**Then:**

* For each of the 10 students:
  * `RetryPolicyAssessment.retry_authorized = true` (policy allows retry)
  * `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE` (dispatch blocked by outage)
  * `contact_attempt` is NOT incremented
  * Retry budget is NOT consumed
  * `RETRY_BUDGET_PROTECTED_PROVIDER_UNAVAILABLE` event emitted per student
* `PROVIDER_OUTAGE` structured log event emitted for the cycle
* Provider failure escalation candidacy generated once per cycle, not 10 times

**Prohibited assertions:**

* Any student's `contact_attempt` was incremented when the provider was unavailable
* Retry budget was consumed for any of the 10 students during the provider outage

---

### ECDE-5 — Deterministic Degradation: Multiple Simultaneous Failure Classes

**Governance contract:** `failure/failure_playbook.md` §2, AP-FP3, AP-FP4, RGS-1

**Edge condition:** During a single orchestration cycle, multiple distinct failure classes are encountered: `TimeoutError` for student S1, `ValidationError` for student S2, and `AUTH_FAILURE` at the provider boundary. Each must be classified and handled independently.

**Given:**

* Orchestration evaluation cycle is active
* Student S1: `TimeoutError` on SQL Server sync read
* Student S2: `ValidationError` on eligibility assessment input
* Provider boundary: `AUTH_FAILURE` from GHL

**When:**

* Orchestration loop catches each exception

**Then:**

* S1: exception classified as `error_class = TimeoutError`; structured log emitted; retry candidacy record produced; dead-letter record for S1 with recovery instructions
* S2: exception classified as `error_class = ValidationError`; structured log emitted; student S2 skipped with `skip_reason = VALIDATION_ERROR`; no retry attempt for S2 (validation errors are not retryable)
* Provider AUTH_FAILURE: classified as `error_class = AUTH_FAILURE` (TERMINAL); no retry produced; alert escalation candidacy generated; all subsequent provider interactions blocked
* Each failure class produces its own structured log record — they are not aggregated silently
* Cycle completion record documents all three failure classes with counts and `affected_student_ids` (opaque)
* No generic `Error` class is used for any of the three failures

**Prohibited assertions:**

* Any exception was caught with a generic `Error` class in a production code path
* Any exception was silently swallowed without a structured log record
* S2's `ValidationError` triggered a retry attempt

---

## 13. IMMUTABLE LINEAGE PROTECTION EDGE CONDITIONS

---

### ECIL-1 — Direct UPDATE Attempt on student_timeline_events Record

**Governance contract:** `runtime/system_loop.md` §11.3, IML-4, `spec/08_data_model.md`

**Edge condition:** A direct SQL UPDATE is attempted against an existing `OrchestrationIntent` record in `student_timeline_events` — for example, to correct a field value after the fact.

**Given:**

* `student_timeline_events` record `intent_id = INT-001` exists with `governance_scope = AUTHORIZED`
* An operation attempts: `UPDATE student_timeline_events SET governance_scope = SHADOW_ONLY WHERE intent_id = INT-001`

**When:**

* Database receives the UPDATE statement

**Then:**

* UPDATE is rejected at the database constraint level
* `APPEND_ONLY_MUTATION_BLOCKED` event is emitted with: `table = student_timeline_events`, `record_id = INT-001`, `attempted_field = governance_scope`, `correlation_id`
* Historical record `INT-001` is preserved intact with `governance_scope = AUTHORIZED`
* The correction must be represented by a new record: `INSERT INTO student_timeline_events (..., correction_of = INT-001)` with the corrected values
* The correction record is append-only — it does not overwrite `INT-001`

**Prohibited assertions:**

* `student_timeline_events` record was updated in-place
* UPDATE was silently rejected without an observable event

---

### ECIL-2 — Direct UPDATE Attempt on warehouse.snapshot_ai_narratives After FINALIZED State

**Governance contract:** `spec/01_requirements.md` FAD-1, IML-1, INV-6

**Edge condition:** An operation attempts to update an existing `warehouse.snapshot_ai_narratives` record to correct a narrative content error.

**Given:**

* `warehouse.snapshot_ai_narratives` record for `(student_id = S1, snapshot_month = 2026-05)` exists in FINALIZED state
* An operation attempts: `UPDATE warehouse.snapshot_ai_narratives SET narrative_content = '<corrected text>' WHERE student_id = S1 AND snapshot_month = '2026-05'`

**When:**

* Database receives the UPDATE statement

**Then:**

* UPDATE is blocked at the database constraint level
* `IMMUTABLE_RECORD_MUTATION_BLOCKED` event emitted with: `table = warehouse.snapshot_ai_narratives`, `record_key = (S1, 2026-05)`, `correlation_id`
* Narrative content remains unchanged
* The correction path is: a governance-authorized compliance action, not an in-place UPDATE
* Escalation candidacy signal produced: `escalation_type = IMMUTABLE_RECORD_MUTATION_ATTEMPT`

**Prohibited assertions:**

* Narrative content was modified in-place in `warehouse.snapshot_ai_narratives`
* Mutation attempt was silent without an observable event

---

### ECIL-3 — AI Attribution Metadata Mutation Attempt After AI_GENERATED State (FAD-6 Under Stress)

**Governance contract:** `spec/01_requirements.md` FAD-6, IML-3, `spec/04_idempotency_concurrency.md` Domain 4

**Edge condition:** An AI model upgrade changes the `model_used` identifier. An automated migration script attempts to backfill `model_used` on all existing `ai_insights` records with `AI_GENERATED` state.

**Given:**

* Migration script attempts: `UPDATE ai_insights SET model_used = 'claude-opus-4-7' WHERE state = 'AI_GENERATED' AND model_used = 'claude-sonnet-4-6'`
* Multiple `ai_insights` records exist in `AI_GENERATED` state with `model_used = 'claude-sonnet-4-6'`

**When:**

* Migration script runs

**Then:**

* UPDATE is blocked for all `AI_GENERATED` state records at the database constraint level
* `AI_ATTRIBUTION_MUTATION_BLOCKED` event emitted for each blocked record
* All `ai_insights` records in `AI_GENERATED` state retain `model_used = 'claude-sonnet-4-6'` — the value reflects the model that actually generated the content
* Future AI generations will use `model_used = 'claude-opus-4-7'` — this applies only to new records
* Backfill mutation attempt is logged as a governance defect

**Prohibited assertions:**

* Any `ai_insights` record in `AI_GENERATED` state had its `model_used` field updated in-place
* Migration ran silently without blocking events

---

### ECIL-4 — Append-Only Lineage: processed_events Record Deletion Attempted

**Governance contract:** `spec/04_idempotency_concurrency.md` Domain 1, IML-4

**Edge condition:** An operational cleanup job attempts to delete `processed_events` records older than 30 days to manage database size. Deleting idempotency records would break the deduplication gate.

**Given:**

* `processed_events` records from `cycle_date = 2026-05-01` exist
* Cleanup job attempts: `DELETE FROM processed_events WHERE created_at < '2026-05-26'`

**When:**

* Cleanup job runs

**Then:**

* DELETE is blocked — `processed_events` is append-only for governance-active records
* `APPEND_ONLY_DELETE_BLOCKED` event emitted with: `table = processed_events`, `attempted_delete_count`, `correlation_id`
* All idempotency records are preserved intact
* The cleanup job logs a governance defect: `IDEMPOTENCY_RECORD_DELETION_ATTEMPT`
* Archival (not deletion) of aged `processed_events` records must follow a compliance-governed retention path — deletion of active idempotency keys is prohibited

**Prohibited assertions:**

* Any `processed_events` record was deleted without a compliance-governed archival process
* DELETE was silently blocked without an observable event

---

## 14. GOVERNANCE INVARIANT STRESS TESTS

---

These scenarios validate that INVARIANT-1 through INVARIANT-7 (from `tests/test_scenarios.md` §17) and FAD-1 through FAD-6 hold under stress, concurrent load, and multi-domain degradation conditions. Each scenario is prefixed `ECINV` and references the parent invariant.

---

### ECINV-1 — INVARIANT-1 Under Stress: Concurrent Finalization Attempts (INV-1)

**Parent invariant:** INV-1 — A FINALIZED snapshot record is inviolable.

**Stress condition:** 5 concurrent goroutines/processes attempt to finalize the same `(student_id = S1, snapshot_month = 2026-05)` simultaneously.

**Given:**

* `(S1, 2026-05)` snapshot is in `PENDING_FINALIZATION` state
* 5 concurrent requests attempt to finalize the snapshot

**When:**

* All 5 finalization attempts hit the idempotency gate simultaneously

**Then:**

* Exactly one finalization succeeds — database-level unique constraint on `(student_id, snapshot_month)` in FINALIZED state ensures only one writer succeeds
* The 4 losing requests each receive a `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` response
* No `warehouse.student_snapshots` record is written more than once for `(S1, 2026-05)`
* All 5 attempts produce observable records — 1 success, 4 blocked

**Prohibited assertions:**

* More than one FINALIZED record was produced for `(S1, 2026-05)`
* Any of the 4 blocked attempts was silent

---

### ECINV-2 — INVARIANT-2 Under Stress: Config Activation During Loop Mid-Execution (INV-2)

**Parent invariant:** INV-2 — At all times, exactly one config version holds ACTIVE status.

**Stress condition:** Config version activation transaction runs while a reader is querying `config_version_registry` in a loop.

**Governance verification:**

* Query `SELECT COUNT(*) FROM config_version_registry WHERE status = 'ACTIVE'` before activation transaction: count = 1
* Query during transaction (if readable): count = 1 (either pre-transaction state V1 or post-transaction state V2)
* Query after transaction completes: count = 1
* If at any point count ≠ 1: `CONFIG_VERSION_INVARIANT_VIOLATED` alert event is emitted and escalation candidacy is generated

**Prohibited assertions:**

* `count(*) WHERE status = ACTIVE = 0` ever (no ACTIVE version)
* `count(*) WHERE status = ACTIVE = 2` ever (two simultaneous ACTIVE versions)

---

### ECINV-3 — INVARIANT-3 Under Stress: Replay Uses Historical Config After Multiple Activations (INV-3)

**Parent invariant:** INV-3 — Config activation applies only to new cycles; historical records are not re-evaluated.

**Stress condition:** V1 → V2 → V3 activations have occurred. A replay is initiated for a cycle governed by V1. All three versions are in the registry.

**Governance verification:**

* Replay for `cycle_date = 2026-05-01` (V1 era): all directive evaluations resolve from V1
* Replay for `cycle_date = 2026-05-15` (V2 era): all directive evaluations resolve from V2
* No replay applies V3 (current ACTIVE) to any historical context
* Query: `SELECT DISTINCT config_version_id FROM processed_events WHERE execution_type = 'replay' AND cycle_date < v2_activation_date` — all records must have `config_version_id = V1`

**Prohibited assertions:**

* Any historical replay applied a non-historical config version to historical context

---

### ECINV-4 — INVARIANT-4 Under Stress: Replay in DEGRADED Mode Produces No LIVE Effects (INV-4)

**Parent invariant:** INV-4 — The Replay Orchestration Loop may produce diagnostic records only; no LIVE effects.

**Stress condition:** Replay is executed in `execution_mode = DEGRADED` with both GHL and AI providers unavailable.

**Governance verification:**

* Execute replay cycle in DEGRADED mode
* Query `ghl_messages` for `execution_type = replay` — expected: zero records
* Query `state_transition_log` for transitions produced by `execution_type = replay` — expected: zero records
* All replay outputs carry `governance_scope = REPLAY_ONLY` and `execution_type = replay`
* DEGRADED mode annotations are present in all replay records

**Prohibited assertions:**

* Any LIVE effect was produced during DEGRADED-mode replay

---

### ECINV-5 — INVARIANT-5 Under Stress: Batch of 1,000 — Zero Null correlation_id Records (INV-5)

**Parent invariant:** INV-5 — Every orchestration record carries a non-null `correlation_id`.

**Stress condition:** A large batch of 1,000 students is evaluated in a single cycle. The batch must produce zero records with `correlation_id IS NULL`.

**Governance verification:**

* Execute a 1,000-student evaluation cycle
* Query all tables: `OrchestrationIntent`, `state_transition_log`, `processed_events`, `student_timeline_events`
* `SELECT COUNT(*) FROM [table] WHERE correlation_id IS NULL AND cycle_date = [cycle_date]` — expected: zero for all tables
* If any null is found: `ATTRIBUTION_INVARIANT_VIOLATED` event emitted per null record; escalation candidacy generated

**Prohibited assertions:**

* Any record in any of the four audited tables has `correlation_id IS NULL`

---

### ECINV-6 — INVARIANT-6 Under Stress: FINALIZED_COPY Immutability Under Bulk AI Refresh Sweep (INV-6)

**Parent invariant:** INV-6 — `warehouse.snapshot_ai_narratives` records are immutable after insertion.

**Stress condition:** AI Refresh Orchestration Loop runs a bulk sweep that inadvertently includes students with FINALIZED_COPY narratives in its candidate set.

**Governance verification:**

* Record `row_count` and `content_checksum` for all `warehouse.snapshot_ai_narratives` records before the bulk sweep
* Execute AI Refresh Loop sweep including FINALIZED_COPY students
* After sweep: record `row_count` and `content_checksum` again
* Expected: row counts identical; content checksums identical for all pre-existing records
* Any delta is a governance defect — `IMMUTABLE_RECORD_MUTATION_DETECTED` event emitted

**Prohibited assertions:**

* Any `warehouse.snapshot_ai_narratives` record had its content modified by the bulk AI refresh sweep

---

### ECINV-7 — INVARIANT-7 Under Stress: All Governance Decision Records Carry config_version_id After Config Transition (INV-7)

**Parent invariant:** INV-7 — Every `OrchestrationIntent`, `RetryPolicyAssessment`, and `EligibilityAssessment` record must carry `config_version_id`.

**Stress condition:** A config version transition (V1 → V2) occurs during an active evaluation cycle. All records produced before and after the transition must carry a non-null `config_version_id` — either V1 or V2 depending on when they were produced.

**Governance verification:**

* Query `student_timeline_events` for records produced during the transition cycle
* `SELECT COUNT(*) FROM student_timeline_events WHERE config_version_id IS NULL AND cycle_date = [transition_cycle_date]` — expected: zero
* Records produced before transition: `config_version_id = V1`
* Records produced after transition: `config_version_id = V2`
* No record carries `config_version_id IS NULL` regardless of transition timing

**Prohibited assertions:**

* Any governance decision record produced during a config transition has `config_version_id IS NULL`

---

### ECINV-FAD1 — FAD-1 Under Stress: Bulk Finalization Sweep Preserves FINALIZED_COPY Immutability

**Parent invariant:** FAD-1 — AI physical copy immutability; `warehouse.snapshot_ai_narratives` is append-only after FINALIZED.

**Stress condition:** A bulk Snapshot Finalization Loop runs for 500 students simultaneously. For 100 students already finalized, the loop must skip them without any warehouse write attempt.

**Governance verification:**

* Record initial `row_count` for `warehouse.snapshot_ai_narratives`
* Execute bulk finalization sweep for 500 students (100 already FINALIZED, 400 new)
* After sweep: `row_count` should have increased by exactly 400
* All 100 already-FINALIZED students: `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` records must exist
* No FINALIZED narrative was overwritten

**Prohibited assertions:**

* `row_count` for `warehouse.snapshot_ai_narratives` increased by more than 400
* Any `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` record was absent for the 100 already-FINALIZED students

---

### ECINV-FAD2 — FAD-2 Under Stress: Regeneration Under Concurrent External Access Attempts

**Parent invariant:** FAD-2 — Historical report reproducibility; no external calls in regeneration.

**Stress condition:** While regeneration is running for `(cohort_id = C1, report_month = 2026-05)`, a concurrent process (a bug or misconfiguration) attempts to trigger an AI provider call for the same cohort.

**Governance verification:**

* During report regeneration cycle: intercept any outbound HTTP call (SQL Server, AI provider, GHL)
* Expected: zero outbound HTTP calls during regeneration
* Any outbound call attempt during regeneration produces: `REGENERATION_EXTERNAL_CALL_BLOCKED` event
* `output_identical` evaluation proceeds using warehouse-only data

**Prohibited assertions:**

* Any outbound call succeeded during a regeneration cycle
* External call attempt during regeneration was silent without a blocking event

---

### ECINV-FAD3 — FAD-3 Under Stress: No Retroactive Re-Evaluation After Config Transition During Replay

**Parent invariant:** FAD-3 — Prospective-only config activation; historical records not retroactively re-evaluated.

**Stress condition:** A replay is executed for a historical cycle. During the replay, a new config version (V3) is activated. The replay must continue using the historical config version (V1) — the in-progress replay must not be contaminated by V3 activation.

**Given:**

* Replay for `cycle_date = 2026-05-01` is running with `historical_config_version_id = V1`
* Mid-replay: V3 is activated (V2 transitions to SUPERSEDED, V3 to ACTIVE)

**When:**

* Replay continues evaluating remaining students

**Then:**

* All students evaluated before and after V3 activation carry `config_version_id = V1` in their replay assessment records
* `V3_ACTIVATION_DURING_REPLAY` annotation is applied to the replay diagnostic record
* V3 activation does not influence the historical replay context — the replay is anchored to `historical_config_version_id = V1`
* A `CONFIG_VERSION_MID_REPLAY_TRANSITION` event is emitted documenting the V3 activation timestamp and the replay's continued use of V1

**Prohibited assertions:**

* Any replay assessment record carried `config_version_id = V3` for a cycle governed by V1
* V3 activation silently contaminated the in-progress replay context

---

## 15. ACCEPTANCE CRITERIA

---

Acceptance criteria are organized by governance edge-condition domain. They extend and do not replace the governance acceptance criteria in `tests/test_scenarios.md` §18.

---

### AC-EDGE-1 — Replay-Safe Edge-Condition Certification

A system passes replay-safe edge-condition certification when:

* Replay against a partially incomplete warehouse record is observable with `replay_partial = true` and no live inference is triggered (ECR-1)
* Replay using a SUPERSEDED historical config version resolves correctly with `SUPERSEDED_CONFIG_USED_FOR_REPLAY` annotation (ECR-2)
* Concurrent replay and LIVE cycles are isolated with separate idempotency namespaces (ECR-3)
* Fingerprint mismatch during replay produces `FINALIZED_COPY_FINGERPRINT_MISMATCH` event and `fingerprint_comparison_outcome = DIVERGENT` (ECR-4)
* Replay against a missing scheduler source record produces `REPLAY_SOURCE_SCHEDULER_RECORD_MISSING` event and proceeds with available data (ECR-5)

---

### AC-EDGE-2 — Regeneration Integrity Edge-Condition Certification

A system passes regeneration integrity edge-condition certification when:

* Partial warehouse availability during regeneration produces `REGENERATION_WAREHOUSE_PARTIAL` event and `output_identical = false` without any external API calls (ECRG-1)
* Concurrent duplicate regeneration triggers are suppressed by idempotency gate with `DUPLICATE_REGENERATION_SUPPRESSED` audit record (ECRG-2)
* Non-deterministic regeneration output produces `REGENERATION_NON_DETERMINISM_DETECTED` event with fingerprint comparison (ECRG-3)

---

### AC-EDGE-3 — Attribution Continuity Under Failure Certification

A system passes attribution continuity under failure certification when:

* `correlation_id` loss at provider delivery boundary produces `ATTRIBUTION_FIELD_MISSING_correlation_id` event and escalation candidacy (ECA-1)
* Absent `causation_id` on `RETRY_OUTREACH` intent produces `ATTRIBUTION_FIELD_MISSING_causation_id` event and `CAUSATION_LINEAGE_BROKEN` flag (ECA-2)
* Scheduler attribution discontinuity produces `SCHEDULER_ATTRIBUTION_DISCONTINUITY` event (ECA-3)
* Recovery attribution incompleteness blocks recovery cycle execution with `RECOVERY_ATTRIBUTION_INCOMPLETE` event (ECA-4)
* AI attribution field absence produces `AI_ATTRIBUTION_FIELD_MISSING` event and persists `UNKNOWN` marker with immutability (ECA-5)

---

### AC-EDGE-4 — Provider-Boundary Edge-Condition Certification

A system passes provider-boundary edge-condition certification when:

* Duplicate webhook delivery after state transition is detected and suppressed with `DUPLICATE_EVENT_SUPPRESSED` audit record (ECDO-2)
* Retry budget is protected for all retry-eligible students during provider outage (ECDE-4)
* Synchronization lag exceeds governance thresholds and produces non-blocking `STALE_SQL_SERVER_DATA` annotations with escalation candidacy (ECPL-1, ECPL-3)
* Sync lag at webhook processing time is annotated without blocking webhook processing (ECPL-2)

---

### AC-EDGE-5 — AI Governance Edge-Condition Certification

A system passes AI governance edge-condition certification when:

* STALE AI advisory cannot elevate escalation severity in LIVE mode (ECAI-1)
* Replay never triggers live AI inference to refresh STALE advisory content (ECAI-2)
* AI provider unavailability during snapshot finalization does not block finalization and does not write a null/empty narrative to warehouse (ECAI-3)
* AI Refresh Loop immediately skips FINALIZED_COPY students with observable skip records (ECAI-4)

---

### AC-EDGE-6 — Config V2 Activation Race Protection Certification

A system passes Config V2 activation race protection certification when:

* Mid-cycle config activation produces a `CONFIG_VERSION_MID_CYCLE_TRANSITION` event documenting the split counts (ECCV-1)
* Simultaneous ACTIVE assertion is prevented by atomic activation transaction (ECCV-2)
* Config version rollback is blocked with `CONFIG_VERSION_ROLLBACK_BLOCKED` event (ECCV-3)
* Retroactive re-evaluation after activation is blocked for all historical records (ECCV-4)

---

### AC-EDGE-7 — Immutable Lineage Edge-Condition Certification

A system passes immutable lineage edge-condition certification when:

* Direct UPDATE on `student_timeline_events` is blocked with `APPEND_ONLY_MUTATION_BLOCKED` event (ECIL-1)
* Direct UPDATE on `warehouse.snapshot_ai_narratives` is blocked with `IMMUTABLE_RECORD_MUTATION_BLOCKED` event (ECIL-2)
* AI attribution metadata backfill is blocked for all `AI_GENERATED` records with `AI_ATTRIBUTION_MUTATION_BLOCKED` events (ECIL-3)
* `processed_events` deletion is blocked for governance-active records with `APPEND_ONLY_DELETE_BLOCKED` event (ECIL-4)

---

### AC-EDGE-8 — Deterministic Degradation Edge-Condition Certification

A system passes deterministic degradation edge-condition certification when:

* Simultaneous provider and AI outage produces independent observable events per domain without cross-domain blocking (ECDE-1)
* Observability pipeline failure during provider outage redirects to stderr without blocking loops (ECDE-2)
* Multiple simultaneous failure classes are classified and handled independently without generic `Error` classification (ECDE-5)

---

### AC-EDGE-9 — Scheduler Governance Edge-Condition Certification

A system passes scheduler governance edge-condition certification when:

* Orphan window detection produces `SCHEDULER_ORPHAN_WINDOW_DETECTED` event and recovery candidacy without auto-triggering recovery (ECSO-1)
* Scheduler drift produces `TRIGGER_SUPPRESSED` with `suppression_reason = DUPLICATE_CYCLE_DATE_WINDOW` and `SCHEDULER_DRIFT_DETECTED` event (ECSO-2)
* Cross-domain scheduler suppression produces `SCHEDULER_CROSS_DOMAIN_SUPPRESSION_DETECTED` governance defect event (ECSO-3)
* Observability Heartbeat Scheduler continues uninterrupted during MAINTENANCE mode (ECSO-4)

---

### AC-EDGE-10 — Governance Invariant Stress Certification

A system passes governance invariant stress certification when all of the following hold under concurrent and high-volume conditions:

* INVARIANT-1: Concurrent finalization produces exactly one FINALIZED record with 4 observable blocking events (ECINV-1)
* INVARIANT-2: Config activation transaction maintains exactly-one-ACTIVE at all observable points (ECINV-2)
* INVARIANT-3: Replay consistently applies historical config across multiple prior activations (ECINV-3)
* INVARIANT-4: Replay in DEGRADED mode produces zero LIVE effects (ECINV-4)
* INVARIANT-5: Batch of 1,000 produces zero null `correlation_id` records (ECINV-5)
* INVARIANT-6: Bulk AI refresh sweep leaves all FINALIZED_COPY narratives immutable (ECINV-6)
* INVARIANT-7: Mid-transition config batch produces zero null `config_version_id` records (ECINV-7)
* FAD-1: Bulk finalization sweep produces exactly the expected new row count with observable blocking for all already-FINALIZED records (ECINV-FAD1)
* FAD-2: Zero outbound calls during regeneration under concurrent external access pressure (ECINV-FAD2)
* FAD-3: In-progress replay context is not contaminated by concurrent config activation (ECINV-FAD3)

---

## 16. SCOPE-SPECIFIC EDGE COVERAGE

---

### MVP

* ECR-1 (partial warehouse replay), ECR-2 (SUPERSEDED config replay)
* ECA-1 (correlation_id loss), ECA-4 (recovery attribution incomplete)
* ECDO-2 (duplicate webhook after state transition), ECDO-4 (duplicate finalization suppression)
* ECCV-3 (config rollback blocked), ECCV-4 (retroactive config application blocked)
* ECSO-1 (orphan-window detection), ECSO-4 (heartbeat continues in MAINTENANCE)
* ECIL-1 (student_timeline_events UPDATE blocked), ECIL-2 (warehouse narrative UPDATE blocked)
* ECDE-5 (multiple simultaneous failure classes classified independently)
* ECINV-2 (exactly-one-ACTIVE under stress), ECINV-5 (zero null correlation_id in 1,000-student batch)

---

### STANDARD

All MVP scenarios plus:

* ECR-3 (concurrent replay vs LIVE isolation), ECR-4 (fingerprint mismatch), ECR-5 (missing scheduler source record)
* ECRG-1 (partial warehouse regeneration), ECRG-2 (concurrent regeneration suppression), ECRG-3 (non-deterministic regeneration)
* ECA-2 (causation_id absent), ECA-3 (scheduler attribution discontinuity), ECA-5 (AI attribution missing)
* ECAI-1 (STALE AI severity elevation blocked), ECAI-2 (STALE AI replay), ECAI-3 (AI unavailable during finalization), ECAI-4 (FINALIZED_COPY skip)
* ECDO-1 (concurrent duplicate LIVE orchestration), ECDO-3 (retry vs initial idempotency)
* ECCV-1 (mid-cycle config transition), ECCV-2 (simultaneous ACTIVE race)
* ECSO-2 (scheduler drift), ECSO-3 (cross-domain degradation contamination)
* ECPL-1 (sync lag during active cycle), ECPL-2 (sync lag at webhook), ECPL-3 (backlog overflow)
* ECDE-1 (multi-domain outage), ECDE-3 (degraded replay), ECDE-4 (retry budget protection)
* ECIL-3 (AI attribution backfill blocked), ECIL-4 (processed_events deletion blocked)
* ECINV-1, ECINV-3, ECINV-4, ECINV-6, ECINV-7, ECINV-FAD3

---

### PRODUCTION

All MVP and STANDARD scenarios plus:

* ECDE-2 (cascading observability degradation during provider outage)
* ECINV-FAD1 (bulk finalization sweep immutability), ECINV-FAD2 (regeneration under concurrent access)
* Full governance invariant stress suite (ECINV-1 through ECINV-FAD3)
* Full attribution continuity suite (ECA-1 through ECA-5) with load testing
* Full immutable lineage suite (ECIL-1 through ECIL-4) with bulk mutation attempts
* Full Config V2 activation race suite (ECCV-1 through ECCV-4) under concurrent load

---

## 17. REFERENCES

---

### Parent Governance Contract

* `tests/test_scenarios.md` — **authoritative parent governance validation contract**; this file inherits all governance invariants and prohibited validation semantics from §2 through §18

### Runtime Contracts

* `runtime/system_loop.md` — authoritative parent runtime contract; AP-RT1 through AP-RT15
* `runtime/scheduler_design.md` — governance-safe scheduler orchestration; AP-SCH1 through AP-SCH15
* `runtime/daily_outreach_flow.md` — daily orchestration flow governance
* `runtime/retry_cycle_flow.md` — retry orchestration governance

### Resilience Contracts

* `failure/failure_playbook.md` — canonical parent resilience contract; AP-FP1 through AP-FP8
* `failure/scheduling_failures.md` — scheduler-domain resilience governance
* `failure/ghl_failures.md` — provider-domain resilience governance
* `failure/llm_failures.md` — AI-domain resilience governance

### Directive Contracts

* `directives/outreach_eligibility_rules.md` — EligibilityAssessment governance
* `directives/outreach_retry_policy.md` — RetryPolicyAssessment governance
* `directives/core_decision_engine.md` — OrchestrationIntent governance
* `directives/channel_selection_rules.md` — ChannelSelectionAssessment governance
* `directives/escalation_rules.md` — EscalationOrchestrationAssessment governance
* `directives/llm_processing_contract.md` — AIAssessment governance
* `directives/ghl_integration_contract.md` — ProviderOrchestrationAssessment governance
* `directives/agent_ownership_matrix.md` — authority domain definitions

### Specification Contracts

* `spec/01_requirements.md` — FAD-1 through FAD-6; Config V2 Governance Catalog §12
* `spec/03_state_transition_rules.md` — state transition authority for all lifecycle domains
* `spec/04_idempotency_concurrency.md` — idempotency keys, concurrency controls, Domain 1–6
* `spec/05_external_integrations.md` — provider integration governance
* `spec/06_observability_operations.md` — observability requirements
* `spec/07_api_contracts.md` — API boundary contracts
* `spec/08_data_model.md` — entity definitions and immutability constraints
* `spec/09_security_privacy.md` — security governance (PII prohibition in observability records)

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

---

## END OF FILE
