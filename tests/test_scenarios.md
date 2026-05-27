# tests/test_scenarios.md

---

## LAYER 6 — GOVERNANCE VALIDATION CONTRACT

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governance-safe orchestration architecture established in `runtime/system_loop.md`, `runtime/scheduler_design.md`, `runtime/daily_outreach_flow.md`, `runtime/retry_cycle_flow.md`, `failure/failure_playbook.md`, `failure/scheduling_failures.md`, `failure/ghl_failures.md`, `failure/llm_failures.md`, all seven rewritten directive files, and `spec/01_requirements.md` through `spec/09_security_privacy.md`. The previous version described MVP-era execution validation scenarios: direct action dispatch assertions (`action = TRIGGER_OUTREACH`, `action = BOOK_MEETING`, `action = SEND_SMS_OR_EMAIL`), hardcoded retry count assumptions (`contact_attempt < MAX_ATTEMPTS`, `attempts < MAX_ATTEMPTS`), simplistic fallback validation ("fallback logic applied"), simplistic concurrency assumptions ("max 50 processed concurrently"), direct LLM override assertions ("system overrides LLM"), and "retry executed" semantics. Those patterns are incompatible with the governance-safe orchestration model. This file is now the **canonical governance validation contract** for all orchestration behavior, not a feature test specification.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

This file is the **canonical governance validation contract** for the Student Success Intelligence Platform. It defines:

* How governance conformance is validated across all orchestration domains
* What invariants must hold for orchestration to be considered governance-safe
* How replay-safe orchestration is validated and certified
* How immutable lineage guarantees are validated
* How Config V2 governance is validated at runtime
* How provider-boundary governance is validated
* How AI advisory-only governance is validated
* How deterministic degradation is validated
* How attribution continuity is validated
* How idempotent orchestration is validated
* How SHADOW-vs-LIVE behavior boundaries are validated

This document is the authoritative governance validation contract for:

* Runtime orchestration — governed by `runtime/system_loop.md`
* Scheduler orchestration — governed by `runtime/scheduler_design.md`
* Retry orchestration — governed by `runtime/retry_cycle_flow.md`
* Daily outreach orchestration — governed by `runtime/daily_outreach_flow.md`
* Resilience orchestration — governed by `failure/failure_playbook.md`
* Directive governance — governed by all directives in `directives/`
* Specification contracts — governed by `spec/01_requirements.md` through `spec/09_security_privacy.md`

---

### 1.2 What Testing Is NOT in This Document

In the governance-safe orchestration model, testing is explicitly **NOT**:

* **Feature execution validation** — "the system sends an outreach message" is not a governance assertion; the governance assertion is "an `OrchestrationIntent` with the correct governance attributes was produced and delegated"
* **LIVE-effect verification** — tests do not assert that LIVE outbound communications occurred; tests assert that governance-authorized orchestration paths were traversed with correct attribution
* **Hardcoded retry expectations** — assertions that assume a specific `MAX_ATTEMPTS` value are specification violations; retry governance resolves dynamically from Config V2
* **Direct execution semantics** — assertions of the form `action = TRIGGER_OUTREACH` (string dispatch) are replaced by structured governance assertions (`OrchestrationIntent.intent_type`, `governance_scope`, `config_version_id`)
* **Silent fallback verification** — "fallback logic applied" is not a valid test outcome; every degraded execution path must be observable and explicitly attributable
* **Replay-triggered LIVE assertions** — no test may assert that a replay-mode execution produced LIVE effects; replay must suppress all LIVE outputs
* **Mutable FINALIZED_COPY assertions** — no test may assert that `warehouse.snapshot_ai_narratives` records were modified or overwritten after FINALIZED state

---

### 1.3 Testing Principles

---

#### 1.3.1 Governance Conformance

Every test scenario validates that the governance contract defined in the canonical source documents was honored. Same inputs under the same execution mode and the same ACTIVE config version must produce the same governance-conformant outputs.

---

#### 1.3.2 Attribution Completeness

Every test scenario that validates orchestration output must include an attribution assertion. An orchestration record without `correlation_id`, `execution_mode`, `execution_type`, and `config_version_id` is a governance defect, not a partially-valid record.

---

#### 1.3.3 Isolation

Each test validates one governance invariant or one orchestration behavior boundary. No test may simultaneously validate eligibility governance and provider dispatch governance; these are separate isolation boundaries.

---

#### 1.3.4 Determinism

Same execution-mode, same ACTIVE config version, same student state inputs → same governance-conformant orchestration outputs. Non-deterministic governance outputs are specification defects regardless of functional correctness.

---

#### 1.3.5 Observability Completeness

A test scenario is not complete unless it includes an observability assertion. If the governance path was traversed but no structured log record was emitted, the scenario has a governance defect in its observability gate.

---

## 2. PROHIBITED VALIDATION SEMANTICS

---

The following validation patterns are **prohibited** in all test scenarios in this document. Their presence is a governance contract violation.

| Prohibited pattern | Governance violation | Required replacement |
|---|---|---|
| `action = TRIGGER_OUTREACH` | Direct execution dispatch assertion | `OrchestrationIntent.intent_type = INITIATE_OUTREACH` + `governance_scope` assertion |
| `action = BOOK_MEETING` | Direct provider execution assertion | No meeting booking action exists in the governance model; escalation candidacy is the governed path |
| `action = SEND_SMS_OR_EMAIL` | Direct channel dispatch assertion | `ChannelSelectionAssessment.selected_channel` + `ProviderOrchestrationAssessment.governance_scope = AUTHORIZED` |
| `retry_allowed = false` | Hardcoded retry state assertion | `RetryPolicyAssessment.retry_authorized = false` with `reason` and `config_version_id` |
| `retry executed` | Direct retry execution assertion | `OrchestrationIntent.intent_type = RETRY_OUTREACH` + `causation_id` linkage |
| `scheduled retry` | Ambiguous scheduler assertion | `RetryOrchestrationScheduler` trigger record + `execution_type` |
| `fallback logic applied` | Silent fallback assertion | Specific degradation event + `DEGRADED` annotation + observability record |
| `max 50 processed concurrently` | Hardcoded concurrency limit | Config V2 Group A concurrency variable resolution assertion |
| `LLM overrides` / `system overrides LLM` | AI override direction inversion | AI is advisory-only; `OrchestrationIntent` must be produced from rule-based directive evaluation; AI informs but does not authorize |
| `FINALIZED_COPY` mutated | Immutable lineage violation | `warehouse.snapshot_ai_narratives` is append-only after FINALIZED; no mutation may be asserted |
| Replay mode producing LIVE effects | Replay governance violation | All replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` |

---

## 3. GOVERNANCE PRECONDITION SCENARIOS

---

### GPC-1 — ACTIVE Config Version Required Before Evaluation

**Governance contract:** `runtime/system_loop.md` §5.2, AP-RT3

**Given:**

* No ACTIVE config version exists in `config_version_registry`
* `execution_mode = LIVE`

**When:**

* Any runtime orchestration loop attempts to begin candidate evaluation

**Then:**

* Loop does not start
* Zero candidates are evaluated
* Zero `OrchestrationIntent` records are produced
* Structured error log is emitted with `event = PRECONDITION_FAILED_NO_ACTIVE_CONFIG`
* `correlation_id` is present in the error log
* Escalation candidacy signal is produced

**Prohibited assertions:**

* Loop partially evaluated candidates before failing
* Any `OrchestrationIntent` record exists without a valid `config_version_id`

---

### GPC-2 — Config V2 Threshold Missing — UNKNOWN_V0 Substitution

**Governance contract:** `runtime/system_loop.md` §6.1, AP-RT9, `runtime/scheduler_design.md` §6.2

**Given:**

* ACTIVE config version exists
* Required threshold key (e.g., `outreach_max_retry_attempts`) is absent from the ACTIVE config version
* `execution_mode = LIVE`

**When:**

* The runtime loop evaluates a candidate requiring that threshold

**Then:**

* `UNKNOWN_V0` is substituted for the missing threshold
* `CONFIG_THRESHOLD_MISSING_outreach_max_retry_attempts` warning is emitted in the structured log
* The loop continues with `DEGRADED` annotation
* No hardcoded fallback value is used
* The `OrchestrationIntent` record carries `degradation_flags = ["CONFIG_THRESHOLD_MISSING_outreach_max_retry_attempts"]`

**Prohibited assertions:**

* Loop used a hardcoded default value (e.g., `max_retry_attempts = 3`) when the config key was missing
* Loop failed silently without emitting a warning

---

### GPC-3 — Execution Mode Check Before Any Evaluation

**Governance contract:** `runtime/system_loop.md` §3.3, `runtime/scheduler_design.md` §3.3

**Given:**

* ACTIVE config version exists
* `execution_mode = MAINTENANCE`

**When:**

* Orchestration Evaluation Scheduler evaluates whether a trigger is due

**Then:**

* Trigger is suppressed
* `TRIGGER_SUPPRESSED` record is emitted with `suppression_reason = MAINTENANCE_MODE`
* No orchestration cycle begins
* Observability Heartbeat Scheduler continues to trigger (exception applies)

**Prohibited assertions:**

* Any outreach orchestration evaluation proceeded in MAINTENANCE mode
* Trigger suppression was silent (no `TRIGGER_SUPPRESSED` record)

---

### GPC-4 — Config V2 Exactly-One-ACTIVE Enforcement (INVARIANT-5)

**Governance contract:** `spec/03_state_transition_rules.md` Domain 5, `spec/01_requirements.md` FAD-3

**Given:**

* One ACTIVE config version exists
* A second config version is promoted to ACTIVE via governance-authorized activation

**Then:**

* The previously ACTIVE version transitions to SUPERSEDED
* At no point do two versions hold ACTIVE status simultaneously
* Config version activation record is written with `activation_actor`, `activation_timestamp`, `superseded_version_id`
* The new ACTIVE version applies prospectively only — no retroactive re-evaluation of historical decisions using the new config version (FAD-3)

**Prohibited assertions:**

* Two ACTIVE config versions exist at the same time
* New config version retroactively re-categorized historical orchestration decisions
* Rollback of a SUPERSEDED config version to ACTIVE

---

### GPC-5 — Prospective-Only Activation Behavior (FAD-3)

**Governance contract:** `spec/01_requirements.md` FAD-3, `runtime/system_loop.md` §5.2

**Given:**

* Config version V1 was ACTIVE for cycle dated 2026-06-01
* Config version V2 is activated on 2026-06-02

**When:**

* Replay Orchestration Loop evaluates the 2026-06-01 cycle for a student

**Then:**

* The replay uses `historical_config_version_id = V1` to evaluate the 2026-06-01 cycle
* V2 is not applied to the 2026-06-01 replay context
* `fingerprint_comparison_outcome` reflects re-evaluation under V1, not V2
* `replay_partial = false` if V1 is fully resolvable

**Prohibited assertions:**

* Replay applied V2 to a historical cycle governed by V1
* V2 retroactively changed the classification of V1-governed orchestration decisions

---

## 4. ORCHESTRATION INTENT GOVERNANCE SCENARIOS

---

### OIG-1 — Orchestration Intent Generation — ELIGIBLE Student

**Governance contract:** `runtime/system_loop.md` §4.1, §5.3

**Given:**

* `EligibilityAssessment.eligibility_status = ELIGIBLE` (from `directives/outreach_eligibility_rules.md`)
* `execution_mode = SHADOW`
* ACTIVE config version present
* `correlation_id` generated for this cycle

**When:**

* Core decision engine evaluates the student and produces `OrchestrationIntent`

**Then:**

* `OrchestrationIntent.intent_type = INITIATE_OUTREACH`
* `OrchestrationIntent.governance_scope = SHADOW_ONLY`
* `OrchestrationIntent.correlation_id` matches the cycle `correlation_id`
* `OrchestrationIntent.config_version_id` matches the ACTIVE config version
* `OrchestrationIntent.execution_mode = SHADOW`
* Intent record is persisted to `student_timeline_events` before any execution delegation
* No LIVE outbound dispatch is delegated

**Prohibited assertions:**

* `action = TRIGGER_OUTREACH` (string dispatch — not a governance assertion)
* `OrchestrationIntent` record exists without `correlation_id`
* LIVE dispatch occurred in SHADOW mode

---

### OIG-2 — Orchestration Intent Generation — INELIGIBLE Student (Terminal State)

**Governance contract:** `spec/03_state_transition_rules.md` Domain 1, `runtime/system_loop.md` §5.3

**Given:**

* Student state = `CLOSED`
* `execution_mode = LIVE`

**When:**

* Orchestration Evaluation Loop evaluates the student

**Then:**

* `EligibilityAssessment.eligibility_status = BLOCKED` (terminal state)
* No `OrchestrationIntent` is produced for this student
* Student skip is logged with `skip_reason = TERMINAL_STATE_CLOSED`, `student_id` (opaque), `correlation_id`
* State remains `CLOSED` — no transition is attempted
* Structured skip record is emitted — skip is never silent (AP-RT5)

**Prohibited assertions:**

* Any `OrchestrationIntent` was produced for a `CLOSED` student
* Skip was silent (no structured log record)
* State transitioned out of `CLOSED` without a compliance-governed action

---

### OIG-3 — Orchestration Intent Persistence Before Delegation

**Governance contract:** `runtime/system_loop.md` §5.3 step 5, AP-RT4

**Given:**

* `OrchestrationIntent.intent_type = INITIATE_OUTREACH` produced
* `execution_mode = LIVE`
* `governance_scope = AUTHORIZED`

**When:**

* Runtime loop attempts execution delegation

**Then:**

* `student_timeline_events` write for the `OrchestrationIntent` record completes before any execution delegation call is made
* If the `student_timeline_events` write fails, no execution delegation occurs
* A `WAREHOUSE_WRITE_FAILURE` event is emitted
* Loop cycle completes with `outcome = failure` for this student

**Prohibited assertions:**

* Execution delegation occurred before `student_timeline_events` write confirmed
* Write failure was silently swallowed

---

### OIG-4 — No Direct Provider Dispatch From Runtime Loop

**Governance contract:** `runtime/system_loop.md` AP-RT1

**Given:**

* `OrchestrationIntent.intent_type = INITIATE_OUTREACH` produced
* `governance_scope = AUTHORIZED`

**When:**

* Runtime loop processes the intent

**Then:**

* Intent is delegated to outreach orchestration service
* Runtime loop does not construct a GHL API payload
* Runtime loop does not construct an SMS message body
* Runtime loop does not construct an email body
* Runtime loop does not invoke a meeting booking request
* `ProviderOrchestrationAssessment` is produced by the outreach orchestration service, not by the runtime loop

**Prohibited assertions:**

* Runtime loop called a GHL API endpoint directly
* Runtime loop constructed any provider-bound payload

---

### OIG-5 — Orphaned Cycle Prevention (AP-RT15)

**Governance contract:** `runtime/system_loop.md` AP-RT15, `runtime/scheduler_design.md` §5.5

**Given:**

* A runtime loop cycle begins — `correlation_id` is generated and recorded
* A fatal error is encountered mid-execution

**When:**

* The loop encounters the fatal error

**Then:**

* A structured completion log is emitted with `outcome = failure`
* The failure is classified with a stable `error_class`
* A dead-letter record is written for any unprocessed candidates
* `correlation_id` is present in all failure records
* The cycle does not terminate silently (AP-RT15)
* Observability Heartbeat Loop will not detect an orphaned `cycle_id` for this cycle

**Prohibited assertions:**

* Cycle terminated without emitting a completion log
* `correlation_id` was generated but no completion record was produced

---

## 5. CONFIG V2 GOVERNANCE SCENARIOS

---

### CV2-1 — Retry Threshold Resolution from Config V2

**Governance contract:** `runtime/system_loop.md` §6.1, AC-RT3

**Given:**

* `outreach_max_retry_attempts = 3` is present in the ACTIVE config version (Config V2 Group A)
* Student `contact_attempt = 3`
* `RetryPolicyAssessment` is produced by `directives/outreach_retry_policy.md`

**When:**

* Retry Orchestration Loop evaluates the student

**Then:**

* `RetryPolicyAssessment.retry_authorized = false`
* `RetryPolicyAssessment.reason = RETRY_EXHAUSTED`
* `RetryPolicyAssessment.config_version_id` matches the ACTIVE config version
* No hardcoded threshold value was used
* Escalation candidacy signal is produced with `escalation_type = RETRY_EXHAUSTED`

**Prohibited assertions:**

* Retry threshold was evaluated against a hardcoded `MAX_ATTEMPTS` constant
* `RetryPolicyAssessment` was produced without `config_version_id`

---

### CV2-2 — Retry Timing Window Resolution from Config V2

**Governance contract:** `runtime/system_loop.md` §6.1, `runtime/scheduler_design.md` §4.2

**Given:**

* `outreach_retry_window_days = 2` is present in the ACTIVE config version (Config V2 Group A)
* Student last outreach attempt was 1 day ago
* Student state = `NO_RESPONSE`

**When:**

* Retry Orchestration Loop evaluates the student

**Then:**

* `RetryPolicyAssessment.retry_authorized = false`
* `RetryPolicyAssessment.reason = RETRY_WINDOW_NOT_ELAPSED`
* `RetryPolicyAssessment.config_version_id` matches the ACTIVE config version
* No LIVE retry dispatch is produced
* Retry timing assertion references the Config V2 variable, not a hardcoded `24h` constant

**Prohibited assertions:**

* Retry was blocked based on a hardcoded `last_contact_time < 24h` assertion
* `RetryPolicyAssessment` produced without `config_version_id`

---

### CV2-3 — Concurrency Limit Resolution from Config V2

**Governance contract:** `runtime/system_loop.md` §5.2, `runtime/scheduler_design.md` §2.1

**Given:**

* Config V2 Group A concurrency variable is present in the ACTIVE config version
* 100 eligible students exist in the evaluation batch
* `execution_mode = LIVE`

**When:**

* Orchestration Evaluation Loop processes the batch

**Then:**

* Concurrency limit applied to the batch is resolved from Config V2 Group A
* No hardcoded concurrency limit (e.g., `max 50 concurrent`) is used
* Idempotency gate prevents duplicate processing of any student within the same cycle
* `OrchestrationIntent` records are produced for each authorized student with correct `config_version_id`

**Prohibited assertions:**

* Concurrency limit was `50` from a hardcoded value rather than Config V2
* Two `OrchestrationIntent` records were produced for the same student in the same cycle

---

### CV2-4 — Config Activation Record Required for SHADOW-to-LIVE

**Governance contract:** `runtime/system_loop.md` §3.2, AP-RT7, `runtime/scheduler_design.md` AP-SCH2

**Given:**

* Current `execution_mode = SHADOW`
* A Governance Administrator initiates a SHADOW-to-LIVE transition

**Then:**

* A config version activation record is written before LIVE mode takes effect
* The activation record includes `activation_actor`, `activation_timestamp`, `previous_execution_mode = SHADOW`, `new_execution_mode = LIVE`
* No automation service coordinates the SHADOW-to-LIVE transition (AP-RT7)
* First cycle in LIVE mode carries the new `execution_mode = LIVE` and valid `config_version_id` in all records

**Prohibited assertions:**

* SHADOW-to-LIVE transition occurred without a Governance Administrator authorization record
* An automated scheduler triggered the mode transition

---

## 6. SHADOW-VS-LIVE BEHAVIOR SCENARIOS

---

### SVL-1 — SHADOW Mode: No LIVE Outbound Dispatch

**Governance contract:** `runtime/system_loop.md` §3.1 (SHADOW mode), AC-RT7

**Given:**

* `execution_mode = SHADOW`
* `EligibilityAssessment.eligibility_status = ELIGIBLE`
* `OrchestrationIntent.intent_type = INITIATE_OUTREACH` produced

**When:**

* Orchestration Evaluation Loop produces and delegates the intent

**Then:**

* `OrchestrationIntent.governance_scope = SHADOW_ONLY`
* No LIVE outbound dispatch is delegated
* All outputs are tagged `outcome = shadow_only`
* `ProviderOrchestrationAssessment.outbound_suppressed = true`
* Structured log emitted with `execution_mode = SHADOW`, `outcome = shadow_only`
* Inbound webhook ingestion continues normally, tagged `execution_mode = SHADOW`

**Prohibited assertions:**

* Any LIVE GHL dispatch was produced in SHADOW mode
* Any LIVE SMS or email was sent in SHADOW mode
* Outputs were tagged with `outcome = success` without SHADOW qualifier

---

### SVL-2 — SHADOW Mode: AI Advisory Evaluated — Tagged Shadow-Only

**Governance contract:** `runtime/system_loop.md` §3.1 (SHADOW mode), §9.1

**Given:**

* `execution_mode = SHADOW`
* AI Refresh Orchestration Loop evaluates a student with stale AI insight

**When:**

* AI provider call is made for advisory refresh

**Then:**

* AI advisory outputs are tagged `outcome = shadow_only`
* `AIAssessment.advisory_content` is produced normally
* `AIAssessment.ai_governance_tier` is set correctly
* Advisory output does not authorize LIVE orchestration
* No LIVE escalation routing occurs from AI advisory output in SHADOW mode

**Prohibited assertions:**

* AI advisory output was blocked entirely in SHADOW mode
* AI output caused LIVE escalation routing in SHADOW mode

---

### SVL-3 — LIVE Mode: AUTHORIZED Intent Delegates to Orchestration Service

**Governance contract:** `runtime/system_loop.md` §3.1 (LIVE mode), §5.4

**Given:**

* `execution_mode = LIVE`
* `OrchestrationIntent.intent_type = INITIATE_OUTREACH`
* `governance_scope = AUTHORIZED`

**When:**

* Runtime loop processes the intent

**Then:**

* Intent is delegated to outreach orchestration service
* `ProviderOrchestrationAssessment` is produced by the outreach orchestration service
* `ProviderOrchestrationAssessment.governance_scope = AUTHORIZED` (if provider available)
* Execution proceeds under governance authorization
* `correlation_id` propagates through all downstream records

**Prohibited assertions:**

* Runtime loop produced the provider payload directly
* Delegation occurred without `ProviderOrchestrationAssessment`

---

## 7. REPLAY ORCHESTRATION SCENARIOS

---

### ROS-1 — Replay: LIVE Effects Suppressed (AP-RT2)

**Governance contract:** `runtime/system_loop.md` §7.2, AP-RT2, AC-RT2

**Given:**

* `execution_type = replay`
* Replay Orchestration Loop evaluates a student's historical orchestration context with `source_artifact_id` and `historical_config_version_id`

**When:**

* Replay cycle executes directive evaluations

**Then:**

* No LIVE outbound dispatch is produced
* No LIVE AI inference is triggered
* No student state transitions are produced
* No escalation routing occurs (outputs carry `REPLAY_ESCALATION_CANDIDATE` scope)
* All outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`
* A replay diagnostic record is emitted with all required fields (§7.4 of `runtime/system_loop.md`)
* `ProviderOrchestrationAssessment.outbound_suppressed = true`
* `AIAssessment.ai_blocked = true` (FINALIZED_COPY sourced from warehouse)

**Prohibited assertions:**

* Any LIVE effect was produced during replay execution
* `governance_scope` was anything other than `REPLAY_ONLY`

---

### ROS-2 — Replay: Historical Config Version Used

**Governance contract:** `runtime/system_loop.md` §7.3, §6.3, FAD-3

**Given:**

* Original orchestration cycle used `config_version_id = V1`
* Current ACTIVE config version is V2
* Replay cycle is initiated with `historical_config_version_id = V1`

**When:**

* Replay Orchestration Loop evaluates directive outputs

**Then:**

* All directive evaluations use thresholds from config version V1
* `RetryPolicyAssessment.config_version_id = V1`
* `EligibilityAssessment.config_version_id = V1`
* V2 thresholds are not applied to the historical replay context
* `fingerprint_comparison_outcome` compares re-evaluation under V1 against stored historical outcome

**Prohibited assertions:**

* Replay applied current ACTIVE config version to a historical context
* Historical replay re-evaluated decisions using V2 while governed by V1

---

### ROS-3 — Replay: UNKNOWN_V0 Substituted for Missing Historical Threshold

**Governance contract:** `runtime/system_loop.md` §7.3, §6.3

**Given:**

* `historical_config_version_id = V1`
* V1 does not contain a value for `outreach_retry_window_days`

**When:**

* Replay Orchestration Loop evaluates retry policy under historical config V1

**Then:**

* `UNKNOWN_V0` is substituted for the missing threshold
* `CONFIG_THRESHOLD_MISSING_outreach_retry_window_days` is emitted in the replay diagnostic record
* `replay_partial = true` is set in the replay diagnostic record
* No hardcoded fallback threshold is applied

**Prohibited assertions:**

* Replay applied a hardcoded value when the historical config was incomplete
* `replay_partial` remained `false` when a threshold was unavailable

---

### ROS-4 — Replay: Idempotency Key Prevents Duplicate Replay Execution

**Governance contract:** `runtime/system_loop.md` §4.8, §11.5

**Given:**

* Replay cycle with `(source_artifact_id = SA1, replay_cycle_id = RC1)` was already executed
* A second replay trigger is submitted for the same `(SA1, RC1)` tuple

**When:**

* Replay Orchestration Scheduler evaluates the second trigger

**Then:**

* The idempotency gate reads the existing replay execution record
* Second trigger is a no-op
* `TRIGGER_SUPPRESSED` record is emitted with `suppression_reason = DUPLICATE_REPLAY_KEY`
* No second replay cycle is initiated

**Prohibited assertions:**

* A second replay cycle executed for the same `(source_artifact_id, replay_cycle_id)` tuple

---

### ROS-5 — Regeneration: External Calls Absolutely Prohibited (FAD-2)

**Governance contract:** `runtime/system_loop.md` §7.5, AC-RT12, `runtime/scheduler_design.md` AC-SCH11

**Given:**

* A report regeneration cycle is triggered from a FINALIZED snapshot
* Report Generation Scheduler fires in REGENERATION mode

**When:**

* Report Generation Loop executes regeneration

**Then:**

* No SQL Server read occurs
* No AI provider call is made
* No GHL API call is made
* Report content is derived exclusively from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives`
* Regenerated report is identical to the original for identical inputs (FAD-2)
* Scheduler completion record shows `execution_type = regeneration`

**Prohibited assertions:**

* Any external API call occurred during regeneration
* Regenerated report content differed from the original for the same inputs

---

## 8. RETRY ORCHESTRATION GOVERNANCE SCENARIOS

---

### ROG-1 — Retry Authorization: Config V2-Governed Threshold

**Governance contract:** `runtime/system_loop.md` §6.1, §6.2, AC-RT3

**Given:**

* Student state = `NO_RESPONSE`
* `outreach_retry_window_days` elapsed (per Config V2 Group A)
* `contact_attempt < outreach_max_retry_attempts` (per Config V2 Group A)
* Compliance hold is NOT active
* `execution_mode = LIVE`

**When:**

* Retry Orchestration Loop evaluates the student

**Then:**

* `RetryPolicyAssessment.retry_authorized = true`
* `RetryPolicyAssessment.config_version_id` matches the ACTIVE config version
* `OrchestrationIntent.intent_type = RETRY_OUTREACH` produced
* `OrchestrationIntent.causation_id` is linked to the prior `OrchestrationIntent` for this student
* Intent is persisted to `student_timeline_events` before execution delegation

**Prohibited assertions:**

* Retry authorization was based on a hardcoded `last_contact_time ≥ 24h` assertion
* `RetryPolicyAssessment` was produced without `config_version_id`
* `causation_id` was absent from the `RETRY_OUTREACH` intent

---

### ROG-2 — Retry Window Not Elapsed: Deterministic Block

**Governance contract:** `runtime/system_loop.md` §6.2, `runtime/retry_cycle_flow.md`

**Given:**

* Student state = `NO_RESPONSE`
* `outreach_retry_window_days` has NOT elapsed (per Config V2 Group A)
* `execution_mode = LIVE`

**When:**

* Retry Orchestration Loop evaluates the student

**Then:**

* `RetryPolicyAssessment.retry_authorized = false`
* `RetryPolicyAssessment.reason = RETRY_WINDOW_NOT_ELAPSED`
* `RetryPolicyAssessment.config_version_id` matches the ACTIVE config version
* No `OrchestrationIntent` of type `RETRY_OUTREACH` is produced
* Skip record emitted with `skip_reason = RETRY_WINDOW_NOT_ELAPSED`

**Prohibited assertions:**

* Retry was blocked based on a hardcoded time window constant
* Skip was silent without a structured log record

---

### ROG-3 — Retry Exhausted: Escalation Candidacy Generated

**Governance contract:** `runtime/system_loop.md` §6.5, `failure/failure_playbook.md`

**Given:**

* `contact_attempt ≥ outreach_max_retry_attempts` (Config V2 Group A)
* `RetryPolicyAssessment.retry_authorized = false`
* `RetryPolicyAssessment.reason = RETRY_EXHAUSTED`
* `execution_mode = LIVE`

**When:**

* Retry Orchestration Loop evaluates the student

**Then:**

* `RETRY_EXHAUSTED` orchestration record is produced
* Escalation candidacy signal is produced with `escalation_type = RETRY_EXHAUSTED`
* No further `RETRY_OUTREACH` intent is produced for this student
* `RETRY_EXHAUSTED` record is persisted with full attribution
* Termination is observable — never silent

**Prohibited assertions:**

* Student state was silently transitioned to CLOSED without an escalation candidacy signal
* Any further retry dispatch was produced after `RETRY_EXHAUSTED`

---

### ROG-4 — Replay-Safe Retry Evaluation: No LIVE Dispatch

**Governance contract:** `runtime/system_loop.md` §6.3

**Given:**

* `execution_type = replay`
* `historical_config_version_id` provided
* Student historical state at replay timestamp = `NO_RESPONSE` with elapsed window

**When:**

* Replay Orchestration Loop evaluates retry policy under historical config

**Then:**

* `RetryPolicyAssessment` produced with `governance_scope = REPLAY_ONLY`
* No LIVE retry dispatch produced
* `UNKNOWN_V0` substituted for any threshold missing from historical config
* Historical `processed_events` records are the authoritative source for what retries actually occurred
* Replay diagnostic record emitted

**Prohibited assertions:**

* LIVE retry dispatch was produced from a replay-mode retry evaluation
* `governance_scope` was anything other than `REPLAY_ONLY`

---

### ROG-5 — Retry Idempotency: Duplicate Key Is a No-Op

**Governance contract:** `runtime/system_loop.md` §4.2, §11.5, `spec/04_idempotency_concurrency.md`

**Given:**

* Retry idempotency key `(student_id, checkpoint_type = RETRY_OUTREACH, contact_attempt = 2)` already exists in `processed_events`
* Retry Orchestration Loop evaluates the same student again

**When:**

* Retry loop checks `processed_events` before producing intent

**Then:**

* Duplicate idempotency key is detected
* No second `RETRY_OUTREACH` intent is produced
* No second execution delegation occurs
* Skip record emitted with `skip_reason = DUPLICATE_IDEMPOTENCY_KEY`

**Prohibited assertions:**

* A second `RETRY_OUTREACH` intent was produced for the same `(student_id, contact_attempt)` tuple

---

## 9. AI GOVERNANCE SCENARIOS

---

### AIG-1 — AI Is Advisory-Only: Deterministic Governance Overrides AI

**Governance contract:** `runtime/system_loop.md` §9.1, AP-RT11

**Given:**

* `AIAssessment.advisory_content.recommended_intervention = DEFER`
* `EligibilityAssessment.eligibility_status = ELIGIBLE` (from rule-based directive evaluation)
* `OrchestrationIntent` is being produced by `core_decision_engine.md`

**When:**

* Core decision engine evaluates the student

**Then:**

* `OrchestrationIntent` is produced from rule-based directive evaluation
* AI advisory output informs but does NOT authorize the `OrchestrationIntent`
* `OrchestrationIntent.intent_type` is governed by eligibility and decision directives, not by AI recommendation alone
* `AIAssessment.advisory_content` is present in the record as advisory context, not as the governance decision

**Prohibited assertions:**

* AI advisory output alone produced an `OrchestrationIntent` (AP-RT11)
* `OrchestrationIntent` was suppressed based on AI advisory without rule-based directive evaluation

---

### AIG-2 — Stale AI: Limited Advisory Scope, Orchestration Continues

**Governance contract:** `runtime/system_loop.md` §9.2, AC-RT11

**Given:**

* `AIAssessment.ai_governance_tier = STALE` (beyond `ai_insight_ttl_hours` from Config V2 Group H)
* Student is evaluated for escalation candidacy

**When:**

* Escalation Polling Loop evaluates escalation candidacy for the student

**Then:**

* STALE AI does not independently drive LIVE escalation
* Rule-based escalation assessment proceeds
* Escalation severity may not be elevated by STALE AI advisory
* `STALE` annotation is present in the escalation candidacy record
* Orchestration is not blocked — STALE AI restricts advisory scope only

**Prohibited assertions:**

* STALE AI blocked orchestration entirely
* STALE AI independently elevated escalation severity in LIVE mode (AP-AI11)

---

### AIG-3 — FINALIZED_COPY Is Immutable (FAD-1)

**Governance contract:** `runtime/system_loop.md` §9.3, `spec/01_requirements.md` FAD-1

**Given:**

* AI narrative for `(student_id, snapshot_month)` has been physically copied to `warehouse.snapshot_ai_narratives`
* Snapshot state = `FINALIZED`

**When:**

* AI Refresh Orchestration Loop evaluates whether to refresh the AI insight for this student

**Then:**

* `warehouse.snapshot_ai_narratives` record is NOT re-evaluated or overwritten
* `ai_governance_tier = FINALIZED_COPY` (highest precedence tier)
* Replay reads this content directly from warehouse — no live AI inference is triggered
* No runtime loop has authority to mutate `warehouse.snapshot_ai_narratives` (AP-OWN15)

**Prohibited assertions:**

* AI Refresh Loop overwrote a `FINALIZED_COPY` narrative
* `warehouse.snapshot_ai_narratives` record was mutated after FINALIZED state

---

### AIG-4 — AI Provider Unavailable: Rule-Based Evaluation Proceeds

**Governance contract:** `runtime/system_loop.md` §10.4, `failure/llm_failures.md`

**Given:**

* AI provider is unavailable
* AI circuit breaker state = OPEN
* Student requires orchestration evaluation

**When:**

* Orchestration Evaluation Loop evaluates the student

**Then:**

* `AIAssessment.advisory_scope = UNAVAILABLE`
* Orchestration proceeds with rule-based evaluation only
* `AI_PROVIDER_UNAVAILABLE` event is emitted in the structured log
* Stale AI annotation is applied to the orchestration record
* Snapshot finalization is not blocked
* `ai_content_stale = true` flag is set

**Prohibited assertions:**

* Orchestration evaluation was blocked entirely by AI provider unavailability
* AI provider unavailability was silent without a structured log record

---

### AIG-5 — Replay: No Live AI Inference

**Governance contract:** `runtime/system_loop.md` §7.2, AP-AI5

**Given:**

* `execution_type = replay`
* FINALIZED AI narrative exists in `warehouse.snapshot_ai_narratives` for the replayed student

**When:**

* Replay Orchestration Loop evaluates AI advisory content

**Then:**

* `AIAssessment.ai_blocked = true`
* AI advisory content is sourced from `warehouse.snapshot_ai_narratives` (FINALIZED)
* No live AI provider call is made
* `ai_governance_tier = FINALIZED_COPY`

**Prohibited assertions:**

* Live AI inference was triggered during replay execution
* AI provider was called during replay-mode orchestration

---

## 10. PROVIDER BOUNDARY GOVERNANCE SCENARIOS

---

### PBG-1 — Provider Circuit Breaker OPEN: Dispatch Blocked, Observability Required

**Governance contract:** `runtime/system_loop.md` §8.3, §10.2, AC-RT6, `failure/ghl_failures.md`

**Given:**

* GHL provider circuit breaker state = OPEN
* `OrchestrationIntent.intent_type = INITIATE_OUTREACH` produced
* `execution_mode = LIVE`

**When:**

* Outreach orchestration service evaluates `ProviderOrchestrationAssessment`

**Then:**

* `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`
* LIVE outbound dispatch is blocked
* `CIRCUIT_BREAKER_OPEN` structured log event is emitted
* Provider failure escalation candidacy signal is produced
* Runtime loop continues for non-dispatch domains (inbound webhooks, AI evaluation, sync)
* Student retry budget is NOT consumed when provider was unavailable (governed by `outreach_retry_policy.md`)

**Prohibited assertions:**

* Dispatch failure was silent (no structured log event)
* Retry budget was consumed when the provider circuit breaker was OPEN

---

### PBG-2 — Provider Auth Failure: Terminal Class, No Retry

**Governance contract:** `runtime/system_loop.md` §8.3, `failure/ghl_failures.md`

**Given:**

* GHL provider returns `AUTH_FAILURE` response
* `execution_mode = LIVE`

**When:**

* Provider orchestration service processes the GHL response

**Then:**

* Failure classified as `error_class = AUTH_FAILURE` (TERMINAL class)
* No retry is produced (TERMINAL — no retry semantics)
* Alert escalation candidacy generated
* All subsequent provider interactions blocked until key rotation is confirmed
* `AUTH_FAILURE` structured log emitted with `provider = ghl`, `correlation_id`

**Prohibited assertions:**

* AUTH_FAILURE triggered a retry attempt
* AUTH_FAILURE was classified as a transient error class

---

### PBG-3 — Inbound Webhook: Deduplication Gate Before State Management

**Governance contract:** `runtime/system_loop.md` §10.6, `failure/ghl_failures.md`, `spec/04_idempotency_concurrency.md`

**Given:**

* GHL webhook with `event_id = EVT-123` is received
* A prior record for `EVT-123` already exists in `processed_events`

**When:**

* Webhook ingestion service processes the event

**Then:**

* `processed_events` dedup lookup fires before any state management service call
* Duplicate `EVT-123` is detected
* No state management service call is made
* `DUPLICATE_EVENT_SUPPRESSED` audit log entry is produced
* Webhook is not silently dropped — suppression is observable

**Prohibited assertions:**

* Duplicate webhook was processed as a new event
* Duplicate suppression was silent without an audit log entry

---

### PBG-4 — SQL Server Sync: Read-Only Governance, All Modes

**Governance contract:** `runtime/system_loop.md` §8.2, `runtime/scheduler_design.md` §4.7

**Given:**

* `execution_mode = SHADOW`
* Provider Synchronization Loop evaluates SQL Server sync

**When:**

* SQL Server sync executes

**Then:**

* SQL Server is read-only — no writes, no mutations from any runtime loop
* Sync proceeds normally in SHADOW mode (sync is read-only and not an outbound action)
* `student_trigger_data` is upserted from SQL Server
* Sync completion record written with `sync_cycle_id`, `sync_source = sql_server`, `sync_lag_hours`

**Prohibited assertions:**

* SQL Server sync was suppressed in SHADOW mode
* SQL Server write was attempted from any runtime loop

---

### PBG-5 — Provider Sync Lag Annotation: Non-Blocking

**Governance contract:** `runtime/system_loop.md` §10.7, §8.2

**Given:**

* `sync_lag_hours > sql_server_max_sync_age_hours` (Config V2 Group K)
* Orchestration Evaluation Loop evaluates candidates

**When:**

* Orchestration Evaluation Loop processes student records

**Then:**

* `STALE_SQL_SERVER_DATA` annotation is applied to affected student records
* Orchestration evaluation proceeds (sync backlog is non-blocking)
* `OrchestrationIntent` records carry `STALE_SQL_SERVER_DATA` annotation
* `SYNC_LAG_EXCEEDED` event is emitted
* Persistent sync backlog generates escalation candidacy if beyond governance-defined threshold

**Prohibited assertions:**

* Orchestration was blocked by sync lag
* Sync lag annotation was silent

---

## 11. STATE TRANSITION GOVERNANCE SCENARIOS

---

### STG-1 — Valid State Transition: Attribution Required

**Governance contract:** `spec/03_state_transition_rules.md` Domain 1, `runtime/system_loop.md` §5.4

**Given:**

* Student state = `ELIGIBLE`
* `OrchestrationIntent.intent_type = INITIATE_OUTREACH` produced and delegated
* Execution authorization confirmed

**When:**

* State management service processes the state transition

**Then:**

* State transitions from `ELIGIBLE` to `QUEUED`
* `state_transition_log` record written with: `from_state = ELIGIBLE`, `to_state = QUEUED`, `correlation_id`, `causation_id`, `execution_mode`, `config_version_id`, `actor = system`
* Runtime loop did NOT write the state transition directly — state management service owns this path

**Prohibited assertions:**

* Runtime loop wrote the state transition directly
* State transition record exists without `correlation_id`

---

### STG-2 — Invalid Transition Blocked With Observable Record

**Governance contract:** `spec/03_state_transition_rules.md` Domain 1

**Given:**

* Student state = `CLOSED`
* An attempt is made to transition state to `QUEUED`

**When:**

* State management service evaluates the transition

**Then:**

* Transition is blocked — `CLOSED` is a terminal state
* `INVALID_STATE_TRANSITION_BLOCKED` event is emitted with: `attempted_from = CLOSED`, `attempted_to = QUEUED`, `correlation_id`, `student_id` (opaque)
* Student state remains `CLOSED`
* The blocking is observable — not silent

**Prohibited assertions:**

* State was silently rejected without a structured log record
* State transitioned out of `CLOSED` without a compliance-governed action

---

### STG-3 — FINALIZED Snapshot: Immutable After Finalization

**Governance contract:** `spec/03_state_transition_rules.md` Domain 2, `spec/04_idempotency_concurrency.md` Domain 2, FAD-1

**Given:**

* `(student_id, snapshot_month)` snapshot state = `FINALIZED`
* Snapshot Finalization Loop receives a second finalization trigger for the same key

**When:**

* Snapshot Finalization Scheduler evaluates the second trigger

**Then:**

* Idempotency gate fires on `(student_id, snapshot_month)` key
* Second finalization trigger is a no-op
* No mutation of `warehouse.student_snapshots` occurs
* No mutation of `warehouse.snapshot_ai_narratives` occurs
* `DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED` audit record is produced

**Prohibited assertions:**

* Second finalization trigger mutated any FINALIZED warehouse record
* Duplicate finalization was silent without an audit record

---

### STG-4 — Config Version: ACTIVE-to-SUPERSEDED Only, Rollback Forbidden

**Governance contract:** `spec/03_state_transition_rules.md` Domain 5

**Given:**

* Config version V1 is ACTIVE
* A governance-authorized activation promotes V2 to ACTIVE (V1 transitions to SUPERSEDED)
* An attempt is made to revert V2 to DRAFT or restore V1 to ACTIVE

**Then:**

* The revert attempt is blocked — rollback of config versions is forbidden
* `CONFIG_VERSION_ROLLBACK_BLOCKED` event is emitted
* V1 remains SUPERSEDED
* V2 remains ACTIVE
* Any new activation requires a new config version record (V3)

**Prohibited assertions:**

* A SUPERSEDED config version was restored to ACTIVE
* Config version state was mutated without a governance-authorized activation record

---

## 12. RESILIENCE GOVERNANCE SCENARIOS

---

### RGS-1 — Deterministic Degradation: No Silent Swallowing

**Governance contract:** `failure/failure_playbook.md` §2, AP-FP3, AP-FP4, `runtime/system_loop.md` §10.1

**Given:**

* A failure is encountered during orchestration evaluation (any failure class)

**When:**

* Orchestration loop catches the exception

**Then:**

* Exception is classified with a stable `error_class` string
* Full context (excluding PII) is logged
* Either a retry path or a dead-letter record with recovery instructions is produced
* `try { } catch(e) {}` silent swallow is absent (AP-RT14)
* "Fallback logic applied" is NOT a valid outcome description — specific degradation path is logged

**Prohibited assertions:**

* Any exception was caught and silently discarded
* Generic `Error` was used as the `error_class` in production code paths

---

### RGS-2 — Scheduler Crash Recovery: Observable, Attributed

**Governance contract:** `failure/failure_playbook.md` §4.4, `runtime/scheduler_design.md` §8.2

**Given:**

* Orchestration Evaluation Scheduler process crashed — no trigger record was emitted within the Config V2-governed window

**When:**

* Orphan detection identifies the missed window

**Then:**

* `SCHEDULER_CRASH_DETECTED` event is emitted
* Recovery cycle is produced with `execution_type = recovery`
* Recovery cycle carries full attribution: `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`, `orphaned_cycle_id`
* Recovery cycle checks `processed_events` idempotency records — already-processed students are skipped
* Operational Administrator authorization is required before recovery cycle fires (unless Config V2-governed automated recovery is defined)

**Prohibited assertions:**

* Recovery cycle executed without full attribution fields (AP-SCH11)
* Recovery cycle produced duplicate LIVE dispatch for already-processed students

---

### RGS-3 — Provider Outage: Retry Budget Protection

**Governance contract:** `runtime/system_loop.md` §10.3, `failure/ghl_failures.md`

**Given:**

* GHL provider outage is active (circuit breaker OPEN or `PROVIDER_OUTAGE` event)
* Retry Orchestration Loop processes retry-eligible students

**When:**

* Retry dispatch delegation is blocked due to provider outage

**Then:**

* `governance_scope = UNAVAILABLE` for all dispatch attempts
* Retry budget is NOT consumed for students whose dispatch was blocked by provider outage
* `PROVIDER_OUTAGE` event emitted
* Provider failure escalation candidacy generated
* `ProviderOrchestrationAssessment.outbound_suppressed = true`
* Inbound webhook ingestion continues normally during provider outage

**Prohibited assertions:**

* Retry budget was consumed when the provider was UNAVAILABLE
* Provider outage was silent without a structured log event

---

### RGS-4 — Missing Transcript / Missing Data: Deterministic Degradation Path

**Governance contract:** `failure/failure_playbook.md` §2, `failure/llm_failures.md`

**Given:**

* Student transcript is unavailable
* AI Refresh Orchestration Loop evaluates AI advisory for this student

**When:**

* AI advisory service receives transcript-unavailable signal

**Then:**

* `AIAssessment.advisory_scope = UNAVAILABLE`
* `ai_governance_tier = UNAVAILABLE`
* Orchestration proceeds with rule-based evaluation only
* `TRANSCRIPT_UNAVAILABLE` event emitted with `correlation_id`
* `ANALYZED` state is not required for orchestration progression — the path degrades deterministically without entering `ANALYZED`

**Prohibited assertions:**

* "Fallback logic applied" was logged as an outcome without a specific degradation event
* Orchestration was blocked entirely by transcript unavailability
* `ANALYZED` state was assigned based on absent data

---

### RGS-5 — Observability Pipeline Degradation: Loops Continue

**Governance contract:** `runtime/system_loop.md` §10.8

**Given:**

* Observability pipeline degrades (structured log destination unavailable)

**When:**

* Runtime orchestration loops continue evaluation

**Then:**

* Orchestration loops continue — observability failure does not block execution
* Structured log entries that fail to be written are directed to stderr with `OBSERVABILITY_DEGRADED` flag
* The failure is itself observable — it does not disappear silently
* Loops emit `OBSERVABILITY_DEGRADED` flag in their next successful log record

**Prohibited assertions:**

* Orchestration loops were blocked by observability pipeline failure
* Observability degradation was entirely silent

---

## 13. CONCURRENCY AND IDEMPOTENCY SCENARIOS

---

### CID-1 — Idempotent Orchestration Cycle

**Governance contract:** `runtime/system_loop.md` §2.1, §4.1, AC-RT5, `spec/04_idempotency_concurrency.md`

**Given:**

* Orchestration Evaluation Loop has already produced `OrchestrationIntent` for student with idempotency key `(cycle_date = 2026-06-01, execution_type = original, config_version_id = V1)`

**When:**

* Loop is re-triggered for the same cycle inputs

**Then:**

* `processed_events` dedup check fires
* Duplicate idempotency key detected
* No second `OrchestrationIntent` is produced
* No second execution delegation occurs
* Skip record emitted with `skip_reason = DUPLICATE_IDEMPOTENCY_KEY`

**Prohibited assertions:**

* A second `OrchestrationIntent` was produced for the same cycle idempotency key

---

### CID-2 — Concurrency: Duplicate LIVE Orchestration Prevented

**Governance contract:** `runtime/system_loop.md` AP-RT10, `spec/04_idempotency_concurrency.md` §2.2

**Given:**

* Two concurrent Orchestration Evaluation Loop instances both select the same student in the same window
* Both attempt to produce `OrchestrationIntent` for the student

**When:**

* Both instances attempt to write the idempotency record to `processed_events`

**Then:**

* First INSERT wins
* Second INSERT detects an existing record and treats the trigger as a no-op
* No duplicate LIVE intent is produced
* `DUPLICATE_ORCHESTRATION_SUPPRESSED` audit record is produced for the second attempt

**Prohibited assertions:**

* Two `OrchestrationIntent` records were produced for the same student in the same cycle
* Concurrency conflict was silent without an audit record

---

### CID-3 — Replay Concurrency: Isolated from LIVE Batch

**Governance contract:** `runtime/scheduler_design.md` §5.3

**Given:**

* LIVE batch cycle is running with window `(orchestration_evaluation, 2026-06-01, LIVE)`
* Replay cycle is triggered concurrently for `(source_artifact_id = SA1, replay_cycle_id = RC1)`

**When:**

* Both cycles run concurrently

**Then:**

* Replay cycle uses separate idempotency namespace `(source_artifact_id, replay_cycle_id)`
* LIVE batch window idempotency key is NOT acquired by the replay cycle (AP-SCH3)
* Replay cycle outputs carry `governance_scope = REPLAY_ONLY` and do not interfere with LIVE cycle outputs
* Both cycles emit their own completion records independently

**Prohibited assertions:**

* Replay cycle acquired a LIVE window idempotency key
* Replay cycle outputs were consumed as LIVE orchestration results

---

### CID-4 — Compliance Hold: Per-Student Block Without Global Impact

**Governance contract:** `runtime/system_loop.md` §10.2, `spec/04_idempotency_concurrency.md` Domain 6

**Given:**

* Student S1 has an active compliance hold
* 99 other students are eligible for outreach
* `execution_mode = LIVE`

**When:**

* Orchestration Evaluation Loop evaluates the 100-student batch

**Then:**

* Outbound dispatch for S1 is blocked — `COMPLIANCE_HOLD_DISPATCH_BLOCKED` emitted per S1
* The other 99 students are unaffected
* S1's `OrchestrationIntent` carries `compliance_hold_active = true` annotation
* Compliance hold does not suppress orchestration evaluation globally

**Prohibited assertions:**

* Compliance hold for one student blocked evaluation for all students
* S1's compliance hold suppression was silent

---

## 14. ATTRIBUTION CONTINUITY SCENARIOS

---

### ATT-1 — Correlation ID Propagation: End-to-End Chain

**Governance contract:** `runtime/system_loop.md` §11.1, §11.3, AC-RT8

**Given:**

* Orchestration cycle is triggered
* `correlation_id = COR-001` is generated at loop start

**When:**

* Cycle completes for one student with successful intent delegation

**Then:**

* `COR-001` is present in:
  * Orchestration loop cycle structured log
  * `OrchestrationIntent` record in `student_timeline_events`
  * `ProviderOrchestrationAssessment` record
  * `processed_events` idempotency record
  * `ghl_messages` provider delivery record (if dispatch completed)
* No orchestration record exists without `COR-001` for this cycle

**Prohibited assertions:**

* Any record in the lineage chain was missing `correlation_id`
* `correlation_id` was not propagated from scheduler trigger to provider delivery

---

### ATT-2 — Causation ID: Retry Linkage to Prior Intent

**Governance contract:** `runtime/system_loop.md` §4.2, §11.2

**Given:**

* `OrchestrationIntent.intent_id = INT-001` was produced for initial outreach
* Retry Orchestration Loop produces `OrchestrationIntent.intent_type = RETRY_OUTREACH` for the same student

**When:**

* `RETRY_OUTREACH` intent record is persisted

**Then:**

* `RETRY_OUTREACH` intent carries `causation_id = INT-001`
* `correlation_id` is propagated from the retry cycle
* `config_version_id` matches the ACTIVE config version at time of retry evaluation
* Attribution lineage chain is traceable: `INT-001 → RETRY intent → processed_events`

**Prohibited assertions:**

* `causation_id` was absent from a `RETRY_OUTREACH` intent
* Retry intent was not traceable back to the original `OrchestrationIntent`

---

### ATT-3 — Scheduler Attribution Lineage: cycle_id to correlation_id

**Governance contract:** `runtime/scheduler_design.md` §9.1, §9.2, AC-SCH8

**Given:**

* Orchestration Evaluation Scheduler fires for `cycle_date = 2026-06-01`
* `cycle_id = SCH-001` is generated at trigger time

**When:**

* Triggered orchestration loop begins evaluation

**Then:**

* Loop start record includes `cycle_id = SCH-001` as session context
* `correlation_id = COR-002` is generated within the loop
* Scheduler completion record includes both `cycle_id = SCH-001` and `correlation_id = COR-002`
* All downstream records (intents, processed_events, ghl_messages) carry `correlation_id = COR-002`
* Forensic chain is traceable: `SCH-001 → COR-002 → OrchestrationIntent → processed_events`

**Prohibited assertions:**

* Loop completion record was missing `cycle_id` from the scheduler trigger
* Downstream records were missing `correlation_id`

---

### ATT-4 — Recovery Cycle: Full Attribution Required

**Governance contract:** `runtime/scheduler_design.md` §8.3, AP-SCH7, AP-SCH11

**Given:**

* Orchestration Evaluation Loop orphaned cycle detected for `cycle_date = 2026-06-01`
* Operational Administrator authorizes recovery cycle

**When:**

* Recovery cycle trigger record is written

**Then:**

* Recovery trigger record includes ALL required attribution fields:
  * `execution_type = recovery`
  * `recovery_of_cycle_date = 2026-06-01`
  * `lag_detected_at` (ISO-8601)
  * `recovery_initiated_by` (Operational Administrator identity)
  * `orphaned_cycle_id` (original `cycle_id`)
  * `recovery_authorization_record_id`
* Recovery cycle is forensically distinguishable from original cycles in all records

**Prohibited assertions:**

* Recovery cycle trigger was missing any required attribution field (AP-SCH11)
* Recovery cycle was forensically indistinguishable from an original cycle

---

### ATT-5 — Provider Attribution: AI Lineage in AI_GENERATED Records

**Governance contract:** `runtime/system_loop.md` §4.4, `spec/08_data_model.md`

**Given:**

* AI Refresh Orchestration Loop produces a new `ai_insights` record

**When:**

* The `ai_insights` record is persisted

**Then:**

* Record includes: `ai_version_number`, `prompt_version`, `model_used`, `generated_at`, `correlation_id`
* Attribution metadata is immutable after `AI_GENERATED` state
* No mutation of `ai_version_number` or `prompt_version` occurs after generation

**Prohibited assertions:**

* AI attribution metadata was absent from the `ai_insights` record
* AI attribution metadata was mutated after `AI_GENERATED` state

---

## 15. DEGRADATION VALIDATION SCENARIOS

---

### DEG-1 — Provider Outage: Deterministic Degradation Path

**Governance contract:** `runtime/system_loop.md` §10.2, §10.3, `failure/failure_playbook.md`

**Given:**

* GHL provider outage is detected
* Orchestration Evaluation Loop begins a new cycle

**When:**

* Outbound dispatch delegation is attempted for any student

**Then:**

* `PROVIDER_OUTAGE` structured log event emitted
* Outbound dispatch blocked for all students in this cycle
* Inbound webhook ingestion continues normally
* SQL Server sync loop continues unaffected
* AI evaluation loop continues unaffected
* Provider failure escalation candidacy generated
* `degradation_cause = PROVIDER_OUTAGE`, `affected_domains` documented

**Prohibited assertions:**

* Provider outage caused silent dispatch failures without observable events
* Provider outage blocked non-dispatch domains (AI, sync, inbound webhooks)

---

### DEG-2 — AI Outage: Rule-Based Orchestration Continues

**Governance contract:** `runtime/system_loop.md` §10.4, `failure/llm_failures.md`

**Given:**

* AI provider is unavailable
* AI circuit breaker state = OPEN

**When:**

* Orchestration Evaluation Loop evaluates students requiring AI advisory

**Then:**

* `AI_PROVIDER_UNAVAILABLE` event is emitted
* Orchestration proceeds with rule-based evaluation only
* `AIAssessment.advisory_scope = UNAVAILABLE`
* Snapshot finalization is not blocked
* `ai_content_stale = true` flag is set on affected records
* Escalation candidacy assessment proceeds with rule-based severity

**Prohibited assertions:**

* Orchestration evaluation was entirely blocked by AI outage
* AI outage was silent without observable events

---

### DEG-3 — Scheduler Degradation: SCHEDULER_DEGRADED Event

**Governance contract:** `runtime/scheduler_design.md` §8.4, AC-SCH10

**Given:**

* AI provider becomes unavailable during active operation
* AI Refresh Scheduler evaluates whether to fire

**When:**

* AI Refresh Scheduler determines trigger cannot proceed due to AI provider outage

**Then:**

* `SCHEDULER_DEGRADED` structured log emitted with `scheduler_domain = ai_refresh`, `degradation_cause = AI_PROVIDER_UNAVAILABLE`
* Trigger is suppressed for this domain — `TRIGGER_SUPPRESSED` record with `suppression_reason = AI_PROVIDER_UNAVAILABLE`
* All other scheduler domains continue normally
* Escalation candidacy signal generated
* When AI provider recovers, `SCHEDULER_RECOVERY` record is emitted

**Prohibited assertions:**

* Scheduler degradation was silent without a `SCHEDULER_DEGRADED` record
* All scheduler domains were suppressed because one domain degraded

---

### DEG-4 — Synchronization Lag: Non-Blocking Annotation

**Governance contract:** `runtime/system_loop.md` §10.7, `runtime/scheduler_design.md` §4.7

**Given:**

* `sync_lag_hours > sql_server_max_sync_age_hours` (Config V2 Group K)
* Orchestration Evaluation Scheduler fires

**When:**

* Orchestration Evaluation Loop evaluates students

**Then:**

* `SYNC_LAG_EXCEEDED` event emitted
* `STALE_SQL_SERVER_DATA` annotation applied to affected records
* Orchestration evaluation proceeds — sync backlog is non-blocking
* Persistent sync backlog generates escalation candidacy if threshold is exceeded
* No student is silently skipped due to sync lag

**Prohibited assertions:**

* Orchestration was blocked by sync lag
* Sync lag annotation was absent from affected orchestration records

---

### DEG-5 — Replay in DEGRADED Mode: Permitted if Warehouse Accessible

**Governance contract:** `runtime/system_loop.md` §3.1 (DEGRADED), `runtime/scheduler_design.md` §3.1 (DEGRADED)

**Given:**

* `execution_mode = DEGRADED` (provider outage active)
* Warehouse is accessible
* Historical config version is resolvable

**When:**

* Replay Orchestration Scheduler is triggered for a historical diagnostic

**Then:**

* Replay is permitted — warehouse accessible and historical config resolvable
* All replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`
* No LIVE effects are produced
* Degradation annotations are included in the replay diagnostic record

**Prohibited assertions:**

* Replay was blocked in DEGRADED mode when warehouse and historical config were accessible
* Replay produced LIVE effects in DEGRADED mode

---

## 16. IMMUTABLE LINEAGE SCENARIOS

---

### IML-1 — FAD-1: AI Physical Copy Immutability

**Governance contract:** `spec/01_requirements.md` FAD-1, `runtime/system_loop.md` §9.3

**Given:**

* Snapshot Finalization Loop completes finalization for `(student_id = S1, snapshot_month = 2026-05)`
* AI narrative is physically copied to `warehouse.snapshot_ai_narratives`

**When:**

* Any subsequent operation attempts to update the AI narrative for this record

**Then:**

* No update to `warehouse.snapshot_ai_narratives` is permitted
* `IMMUTABLE_RECORD_MUTATION_BLOCKED` event is emitted
* AI Refresh Loop does not evaluate or overwrite this record
* Replay reads this record directly — no live AI inference triggered
* `ai_governance_tier = FINALIZED_COPY`

**Prohibited assertions:**

* `warehouse.snapshot_ai_narratives` record was mutated after FINALIZED state
* AI Refresh Loop attempted to update a FINALIZED narrative

---

### IML-2 — FAD-2: Regeneration Uses Warehouse Exclusively

**Governance contract:** `spec/01_requirements.md` FAD-2, `runtime/system_loop.md` §7.5

**Given:**

* `(cohort_id = C1, report_month = 2026-05)` FINALIZED snapshot data exists in warehouse
* Report Generation Scheduler fires in REGENERATION mode

**When:**

* Report Generation Loop executes regeneration

**Then:**

* Report data sourced exclusively from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives`
* No SQL Server reads
* No AI provider calls
* No GHL calls
* Regenerated report is identical to original for identical inputs
* `execution_type = regeneration` in completion record
* `output_identical` flag is present in the regeneration job record

**Prohibited assertions:**

* Any external API call occurred during regeneration
* Regenerated and original reports differed for identical inputs

---

### IML-3 — FAD-6: Attribution Metadata Immutability After AI_GENERATED

**Governance contract:** `spec/01_requirements.md` FAD-6, `spec/04_idempotency_concurrency.md` Domain 4

**Given:**

* `ai_insights` record for `(student_id = S1, insight_type = OUTREACH_DRAFT)` has been generated
* Record state = `AI_GENERATED`

**When:**

* Any operation attempts to modify `ai_version_number`, `prompt_version`, or `model_used` on the existing record

**Then:**

* Mutation is blocked
* `AI_ATTRIBUTION_MUTATION_BLOCKED` event is emitted
* A new `ai_insights` record is required for any updated advisory (new version lineage)
* Existing record remains immutable with original attribution metadata

**Prohibited assertions:**

* Attribution metadata was mutated on an `AI_GENERATED` record
* `prompt_version` or `model_used` was overwritten in-place

---

### IML-4 — Append-Only: student_timeline_events

**Governance contract:** `runtime/system_loop.md` §11.3, `spec/08_data_model.md`

**Given:**

* `OrchestrationIntent` record has been written to `student_timeline_events`

**When:**

* Any operation attempts to update or delete the existing `OrchestrationIntent` record

**Then:**

* Update and delete are prohibited — `student_timeline_events` is append-only
* `APPEND_ONLY_MUTATION_BLOCKED` event is emitted
* Historical record is preserved intact
* Corrections are represented by new records with `correction_of` lineage reference

**Prohibited assertions:**

* Existing `student_timeline_events` record was updated in-place
* Historical orchestration record was deleted

---

## 17. GOVERNANCE INVARIANT TESTS

---

### INV-1 — Immutable FINALIZED Snapshot

**Governance contract:** `spec/03_state_transition_rules.md` Domain 2, `spec/04_idempotency_concurrency.md` Domain 2

**Invariant:** A FINALIZED snapshot record is inviolable. No system, user, or automated process may modify a row in `warehouse.student_snapshots` once it reaches FINALIZED state. Compliance-governed deletion is the only lawful mutation path.

**Validation:**

* Attempt direct UPDATE on a FINALIZED `warehouse.student_snapshots` row
* Expected: database-level constraint blocks the update; `IMMUTABLE_RECORD_MUTATION_BLOCKED` event emitted
* No partial mutation succeeds

---

### INV-2 — Exactly-One-ACTIVE Config Version

**Governance contract:** `spec/03_state_transition_rules.md` Domain 5, `spec/01_requirements.md` §12

**Invariant:** At all times, exactly one config version in `config_version_registry` holds ACTIVE status. Two simultaneous ACTIVE versions are a specification defect.

**Validation:**

* Query `config_version_registry` where `status = ACTIVE` at any point during or after config activation
* Expected: count = exactly 1
* Config activation transaction is atomic — transition of V1 to SUPERSEDED and V2 to ACTIVE are in the same transaction

---

### INV-3 — Prospective-Only Activation (FAD-3)

**Governance contract:** `spec/01_requirements.md` FAD-3

**Invariant:** A new config version activation applies only to new orchestration cycles initiated after activation. Historical records resolved under the prior version are not retroactively re-evaluated under the new version.

**Validation:**

* Activate V2 on 2026-06-02
* Query all `OrchestrationIntent` records with `cycle_date = 2026-06-01` — all carry `config_version_id = V1`
* Query all `OrchestrationIntent` records with `cycle_date = 2026-06-02` (post-activation) — all carry `config_version_id = V2`
* No 2026-06-01 record has `config_version_id = V2`

---

### INV-4 — No LIVE Effects From Replay (AP-RT2)

**Governance contract:** `runtime/system_loop.md` AP-RT2

**Invariant:** The Replay Orchestration Loop may produce diagnostic records only. No LIVE outbound dispatch, no LIVE state transition, no LIVE AI inference, and no LIVE escalation routing may be produced by any replay-mode execution.

**Validation:**

* Execute a replay cycle
* Query `processed_events` for records with `execution_type = replay` — all carry `governance_scope = REPLAY_ONLY`
* Query `ghl_messages` — no records with `execution_type = replay` exist (no LIVE dispatch)
* Query `state_transition_log` — no transitions produced by `execution_type = replay`

---

### INV-5 — Correlation ID on Every Orchestration Record

**Governance contract:** `runtime/system_loop.md` §11.1, AP-RT4

**Invariant:** Every `OrchestrationIntent`, `state_transition_log`, `processed_events`, and `student_timeline_events` record produced during an orchestration cycle carries a non-null `correlation_id` matching the cycle's `correlation_id`.

**Validation:**

* Query any of the above tables for records with `correlation_id IS NULL`
* Expected: zero records
* Any null `correlation_id` is a governance defect

---

### INV-6 — FINALIZED_COPY Immutability (FAD-1)

**Governance contract:** `spec/01_requirements.md` FAD-1

**Invariant:** `warehouse.snapshot_ai_narratives` records are immutable after insertion. No UPDATE or DELETE is permitted. Historical report regeneration reads these records; it never mutates them.

**Validation:**

* Query `warehouse.snapshot_ai_narratives` update timestamp distribution — no records should show modification after initial insertion
* Attempt UPDATE on any `warehouse.snapshot_ai_narratives` record — expected: blocked at database constraint level

---

### INV-7 — No Hardcoded Threshold in Orchestration Records

**Governance contract:** `runtime/system_loop.md` §6.1, AP-RT9

**Invariant:** Every `OrchestrationIntent`, `RetryPolicyAssessment`, and `EligibilityAssessment` record must carry `config_version_id`. The absence of `config_version_id` on any governance decision record indicates that a hardcoded threshold was used.

**Validation:**

* Query `student_timeline_events` for orchestration intent records with `config_version_id IS NULL`
* Expected: zero records
* Any record without `config_version_id` is a governance defect

---

## 18. ACCEPTANCE CRITERIA

---

Acceptance criteria are organized by governance domain. Each criterion corresponds to a test scenario above.

---

### AC-GOV-1 — Replay-Safe Certification

A system is replay-safe when:

* All replay-mode executions suppress LIVE outbound dispatch (ROS-1)
* Historical config version is used for historical replay context (ROS-2)
* `UNKNOWN_V0` substitution is applied when historical config is incomplete (ROS-3)
* Duplicate replay execution is suppressed by idempotency gate (ROS-4)
* Regeneration reads warehouse exclusively and produces identical output (ROS-5)

---

### AC-GOV-2 — Deterministic Orchestration Certification

A system demonstrates deterministic orchestration when:

* Same execution-mode, config version, and student state inputs produce identical governance-conformant outputs
* No runtime loop re-implements directive logic (AP-RT12)
* OrchestrationIntent is produced from directive evaluation, not from AI advisory alone (AIG-1)
* Config V2 thresholds govern all retry, timing, and concurrency decisions (CV2-1, CV2-2, CV2-3)

---

### AC-GOV-3 — Immutable Lineage Certification

Immutable lineage is preserved when:

* FINALIZED snapshot records cannot be mutated (INV-1, IML-1)
* AI physical copy is immutable after FINALIZED state (AIG-3, INV-6)
* AI attribution metadata is immutable after AI_GENERATED state (IML-3, INV-7)
* `student_timeline_events` is append-only (IML-4)
* Regeneration produces identical output from identical warehouse inputs (IML-2)

---

### AC-GOV-4 — Attribution Continuity Certification

Attribution continuity is demonstrated when:

* `correlation_id` propagates from orchestration loop start to provider delivery record (ATT-1)
* `causation_id` links retry intents to their originating intent (ATT-2)
* Scheduler `cycle_id` links to loop `correlation_id` in completion records (ATT-3)
* Recovery cycles carry full attribution lineage (ATT-4)
* AI attribution metadata is captured at generation time (ATT-5)
* No orchestration record exists without `correlation_id` (INV-5)

---

### AC-GOV-5 — Degradation Observability Certification

Degradation is observable when:

* All provider outages produce structured `PROVIDER_OUTAGE` events (DEG-1)
* All AI outages produce structured `AI_PROVIDER_UNAVAILABLE` events (DEG-2)
* All scheduler degradations produce `SCHEDULER_DEGRADED` records (DEG-3)
* Sync lag produces non-blocking `STALE_SQL_SERVER_DATA` annotations (DEG-4)
* No failure is silently swallowed (RGS-1)

---

### AC-GOV-6 — Idempotent Orchestration Certification

Orchestration is idempotent when:

* Duplicate cycle triggers are suppressed by idempotency gate (CID-1)
* Concurrent duplicate LIVE orchestration is prevented (CID-2)
* Replay concurrency is isolated from LIVE batch (CID-3)
* FINALIZED snapshot finalization is idempotent (STG-3)
* Retry idempotency key prevents duplicate retry dispatch (ROG-5)

---

### AC-GOV-7 — Provider-Boundary Governance Certification

Provider boundary is maintained when:

* No runtime loop directly calls a provider API (OIG-4, PBG-4)
* Circuit breaker OPEN blocks dispatch with observable records (PBG-1)
* AUTH_FAILURE is classified TERMINAL with no retry (PBG-2)
* Inbound webhook deduplication fires before state management calls (PBG-3)
* Retry budget is not consumed during provider outages (RGS-3)

---

### AC-GOV-8 — AI Governance Preservation Certification

AI governance is preserved when:

* AI is advisory-only and does not authorize OrchestrationIntent alone (AIG-1)
* STALE AI restricts advisory scope without blocking orchestration (AIG-2)
* FINALIZED_COPY is never re-evaluated or overwritten (AIG-3)
* AI provider unavailability allows rule-based evaluation to proceed (AIG-4)
* No live AI inference occurs in replay mode (AIG-5)

---

## 19. SCOPE-SPECIFIC VALIDATION COVERAGE

---

### MVP

* GPC-1 (ACTIVE config required), GPC-2 (UNKNOWN_V0), GPC-3 (maintenance mode)
* OIG-1 (SHADOW intent), OIG-2 (CLOSED block), OIG-3 (persistence before delegation), OIG-5 (orphaned cycle)
* SVL-1 (SHADOW no dispatch), SVL-2 (SHADOW AI shadow-only)
* CV2-1 (retry threshold), CV2-2 (retry timing), CV2-4 (SHADOW-to-LIVE requires authorization)
* STG-1 (valid transition with attribution), STG-2 (invalid transition blocked)
* PBG-4 (SQL Server read-only)
* ATT-1 (correlation_id propagation), ATT-3 (scheduler attribution)
* RGS-1 (no silent swallowing)
* INV-2 (exactly-one-ACTIVE), INV-5 (correlation_id on every record)

---

### STANDARD

All MVP scenarios plus:

* ROG-1 through ROG-5 (retry governance)
* AIG-1 through AIG-4 (AI governance)
* PBG-1 through PBG-3, PBG-5 (provider governance)
* ROS-1 through ROS-5 (replay governance)
* CID-1 through CID-4 (concurrency and idempotency)
* DEG-1 through DEG-4 (degradation)
* ATT-2, ATT-4, ATT-5 (extended attribution)
* STG-3 (FINALIZED snapshot idempotency)
* INV-1, INV-3, INV-4, INV-6, INV-7 (governance invariants)

---

### PRODUCTION

All MVP and STANDARD scenarios plus:

* GPC-4, GPC-5 (Config V2 activation governance, prospective-only behavior)
* CV2-3 (concurrency from Config V2)
* STG-4 (config version rollback forbidden)
* IML-1 through IML-4 (full immutable lineage suite)
* DEG-5 (replay in DEGRADED mode)
* RGS-2 (scheduler crash recovery attribution)
* RGS-4 (missing transcript degradation path)
* RGS-5 (observability pipeline degradation)
* PBG-2 (AUTH_FAILURE terminal class)
* ATT-5 (AI lineage immutability)
* Full governance invariant suite (INV-1 through INV-7)

---

## 20. REFERENCES

---

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

* `spec/01_requirements.md` — FAD-1 through FAD-6, Config V2 Governance Catalog §12
* `spec/03_state_transition_rules.md` — state transition authority for all lifecycle domains
* `spec/04_idempotency_concurrency.md` — idempotency keys, concurrency controls
* `spec/05_external_integrations.md` — provider integration governance
* `spec/06_observability_operations.md` — observability requirements
* `spec/07_api_contracts.md` — API boundary contracts
* `spec/08_data_model.md` — entity definitions and immutability constraints
* `spec/09_security_privacy.md` — security governance (PII prohibition in observability records)

### Architecture Decisions

* FAD-1 — Physical copy AI immutability (`warehouse.snapshot_ai_narratives`)
* FAD-2 — Historical report reproducibility (no external calls in regeneration)
* FAD-3 — Prospective-only config activation
* FAD-6 — AI attribution metadata immutability after AI_GENERATED

### Architecture Preservation Rules Referenced

* AP-RT1 through AP-RT15 — runtime loop governance prohibitions
* AP-SCH1 through AP-SCH15 — scheduler domain governance prohibitions
* AP-FP1 through AP-FP8 — resilience orchestration governance prohibitions

---

## END OF FILE
