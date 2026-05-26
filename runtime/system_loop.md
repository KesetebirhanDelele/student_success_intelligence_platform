# runtime/system_loop.md

---

## LAYER 7 — RUNTIME (GOVERNANCE-SAFE ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `spec/01_requirements.md` through `spec/09_warehouse_physical_architecture.md` and all seven governance-safe directives. The previous version described MVP-era execution flow: a direct execution sequence, hardcoded action dispatch semantics (SEND_SMS, SEND_EMAIL, BOOK_MEETING, GHL payload dispatch), hardcoded retry counts (MAX_ATTEMPTS), hardcoded channel progression (CALL→SMS→EMAIL), hardcoded concurrency limits (50 concurrent), and mutable operational sequencing with no replay semantics, no Config V2 governance, no SHADOW/LIVE distinction, and no attribution requirements. That architecture is incompatible with the governance-safe orchestration model. Runtime orchestration is no longer execution logic. It is governance-safe orchestration lifecycle coordination.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Runtime Orchestration Architecture** defines:

* How orchestration evaluation cycles are sequenced, governed, and made historically explainable
* What runtime modes exist, what is permitted in each, and how mode transitions are governed
* What canonical runtime orchestration domains exist and how each domain's idempotency, attribution, and replay safety are guaranteed
* How retry orchestration is governed by Config V2 — not by hardcoded thresholds
* How SHADOW-vs-LIVE execution mode restrictions apply to every orchestration domain
* How replay orchestration simulates historical decisions without generating LIVE effects
* How provider governance boundaries are maintained at runtime
* How AI advisory governance applies during runtime evaluation
* How degradation is deterministic, observable, and never silently swallowed

This document is the **authoritative parent runtime contract** for:

* `runtime/daily_outreach_flow.md` — governed by §4.1, §5, §6
* `runtime/retry_cycle_flow.md` — governed by §4.2, §6
* `runtime/scheduler_design.md` — governed by §3, §4.1–4.10, §10.5

Child runtime documents describe operational sequencing detail. This document establishes the governance model all such sequencing must conform to. Where child documents conflict with this document, this document governs.

---

### 1.2 What Runtime Orchestration Is NOT

In the governance-safe orchestration model, runtime is explicitly **NOT**:

* **Direct execution sequencing** — "Execute Action (GHL / Internal)" is not a runtime responsibility; runtime coordinates governance-safe intent delegation, not direct dispatch
* **A workflow execution engine** — runtime loops coordinate orchestration cycles; they do not own or invoke provider APIs
* **A provider dispatch layer** — no runtime loop directly sends SMS, email, GHL triggers, or meeting bookings; all dispatch is delegated to provider orchestration services under governance authorization
* **A mutable orchestration flow** — runtime sequencing is deterministic; hidden runtime mutations, silent fallbacks, and undocumented state changes are specification violations
* **Hardcoded threshold logic** — retry attempt counts, timing windows, concurrency limits, and channel progression are all Config V2-governed; no hardcoded values are permitted in runtime orchestration governance

---

### 1.3 Runtime Governance Layer Definition

Runtime orchestration sits at the coordination boundary between:

* The **directive layer** (intent and advisory generation) — `directives/`
* The **execution layer** (deterministic service execution) — `backend/src/services/`
* The **provider layer** (operational delivery) — GHL and other external systems

Runtime loops **coordinate** this boundary. They do not own business logic, they do not dispatch to providers directly, and they do not bypass directive governance.

| Layer | Runtime relationship |
|---|---|
| Directives | Generate advisories, intents, candidacy signals — runtime loops consume these outputs |
| Orchestration services | Validate and execute under governance authorization — runtime loops delegate to them |
| Provider systems | Execute operational delivery — runtime loops never own this path |
| Warehousing layer | Append-only persistence — runtime loops may trigger writes via designated service accounts, never directly |

---

## 2. RUNTIME ORCHESTRATION MODEL

---

### 2.1 Governance-Safe Sequencing Principle

Every runtime orchestration cycle must satisfy the following invariants:

1. **Preconditioned** — a valid ACTIVE config version, a valid execution_mode, and a valid correlation_id must exist before any orchestration loop evaluates candidates
2. **Intent-delegated** — runtime loops produce or receive orchestration intents; they do not execute actions directly
3. **Attribution-continuous** — a correlation_id generated at the start of a runtime cycle propagates through every directive evaluation, execution service call, provider interaction, and log record within that cycle
4. **Replay-safe** — every orchestration cycle must be historically reproducible; no runtime action may depend on mutable in-process state that is unavailable in replay context
5. **Idempotent** — re-running the same runtime cycle for the same inputs must produce the same end state, with no duplicate side effects

---

### 2.2 Three-Tier Runtime Architecture

```
Directive Layer  →  Intent / Advisory Generation
      ↓
Orchestration Services  →  Governance-Authorized Execution
      ↓
Provider Layer  →  Operational Delivery
```

Runtime loops coordinate this sequence. They do not collapse tiers. A runtime loop that calls a provider API directly is a specification violation (AP-RT1).

---

### 2.3 Orchestration Assessment Outputs Consumed by Runtime

Directives produce structured governance outputs. Runtime loops receive these outputs and coordinate the delegation path:

| Directive | Structured output consumed |
|---|---|
| `outreach_eligibility_rules.md` | `EligibilityAssessment` — ELIGIBLE/INELIGIBLE/BLOCKED/SHADOW_ONLY |
| `outreach_retry_policy.md` | `RetryPolicyAssessment` — RETRY_AUTHORIZED/RETRY_BLOCKED/RETRY_EXHAUSTED/RETRY_PENDING |
| `core_decision_engine.md` | `OrchestrationIntent` — INITIATE_OUTREACH/RETRY_OUTREACH/DEFER_PENDING_AI/ESCALATE/CLOSE/HOLD |
| `channel_selection_rules.md` | `ChannelSelectionAssessment` — CALL/SMS/EMAIL/NO_CHANNEL_ELIGIBLE |
| `escalation_rules.md` | `EscalationOrchestrationAssessment` — escalation_candidate, escalation_type, escalation_severity |
| `llm_processing_contract.md` | `AIAssessment` — ai_governance_tier, advisory_scope, advisory_content |
| `ghl_integration_contract.md` | `ProviderOrchestrationAssessment` — governance_scope, provider_event_type |

Runtime loops consume these outputs in governance-defined sequencing order. They do not re-implement directive logic (AP-RT12).

---

### 2.4 Runtime Layer Responsibilities

| Responsibility | Runtime layer owns | Runtime layer does NOT own |
|---|---|---|
| Triggering orchestration cycle start | Yes | Defining trigger-frequency thresholds (Config V2 owns those) |
| Validating governance preconditions | Yes | Evaluating eligibility logic (directives own this) |
| Propagating correlation_id | Yes | Generating idempotency keys for directive evaluations |
| Coordinating intent delegation to services | Yes | Executing outreach dispatch (orchestration services own this) |
| Consuming provider orchestration assessments | Yes | Making provider API calls (provider orchestration services own this) |
| Coordinating replay cycle execution | Yes | Generating live inferences during replay (AP-RT2) |
| Emitting runtime observability records | Yes | Implementing AI confidence scoring |

---

## 3. RUNTIME MODES

---

### 3.1 Canonical Runtime Mode Definitions

Six runtime modes govern all orchestration behavior. Mode is set at the environment level and applies to every loop in every orchestration domain.

---

#### LIVE

| Aspect | Behavior |
|---|---|
| Permitted operations | Full orchestration evaluation; full outbound dispatch delegation; AI inference; escalation routing; webhook ingestion |
| Prohibited operations | None within governance authorization |
| Provider restrictions | GHL dispatch authorized when `ProviderOrchestrationAssessment.governance_scope = AUTHORIZED` |
| AI restrictions | STALE AI may not independently drive LIVE escalation (AP-AI11); FINALIZED_COPY is immutable |
| Replay restrictions | No replay-mode calls may produce LIVE effects |
| Escalation restrictions | Full escalation routing active |
| Observability | Full telemetry required for all loops |

---

#### SHADOW

| Aspect | Behavior |
|---|---|
| Permitted operations | Full orchestration evaluation; AI inference (advisory only); inbound webhook ingestion (tagged `execution_mode = SHADOW`); replay diagnostics |
| Prohibited operations | LIVE outbound dispatch; LIVE state transitions; LIVE escalation routing |
| Provider restrictions | All outbound dispatch suppressed; `governance_scope = SHADOW_ONLY`; inbound webhooks ingested and tagged `execution_mode = SHADOW` |
| AI restrictions | AI advisory evaluated; outputs tagged `outcome = shadow_only`; FINALIZED_COPY semantics apply normally |
| Replay restrictions | Replay orchestration remains SHADOW-only within SHADOW mode |
| Escalation restrictions | Escalation candidacy assessed and logged; no live operator routing |
| Observability | Full telemetry required; all outcomes tagged `execution_mode = SHADOW` |

---

#### REPLAY

| Aspect | Behavior |
|---|---|
| Permitted operations | Historical orchestration simulation; SHADOW-only outputs; historical record reads; replay diagnostic emission |
| Prohibited operations | LIVE dispatch; LIVE state transitions; LIVE AI inference; LIVE provider calls; live escalation routing |
| Provider restrictions | All provider interactions return historical records from `processed_events` / `ghl_messages` only; no live GHL API calls |
| AI restrictions | Live AI inference suppressed; FINALIZED_COPY sourced exclusively from `warehouse.snapshot_ai_narratives`; stale AI in replay returns historical advisory or UNAVAILABLE |
| Replay restrictions | All outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; no output may be consumed as LIVE |
| Escalation restrictions | Escalation outputs carry `REPLAY_ESCALATION_CANDIDATE` scope; no live escalation acknowledgement or closure |
| Observability | Full replay diagnostic set: `source_artifact_id`, `historical_config_version_id`, `fingerprint_comparison_outcome`, `replay_partial` |

---

#### REGENERATION

| Aspect | Behavior |
|---|---|
| Permitted operations | Re-render published reports from FINALIZED snapshot data; read `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` exclusively (FAD-2) |
| Prohibited operations | SQL Server reads; AI provider calls; GHL calls; any warehouse mutation; state transitions |
| Provider restrictions | No external calls of any kind |
| AI restrictions | No live inference; FINALIZED_COPY sourced from warehouse exclusively |
| Replay restrictions | Regeneration does not simulate orchestration decisions; it re-renders report content; it is not replay |
| Escalation restrictions | No escalation actions |
| Observability | Regeneration job record with `source_artifact_id`, `lineage_version`, `regeneration_timestamp`, `output_identical` flag |

---

#### DEGRADED

| Aspect | Behavior |
|---|---|
| Permitted operations | Governance precondition validation; eligibility and retry assessment (read-only); inbound webhook ingestion; observability emission; escalation candidacy assessment |
| Prohibited operations | Outbound dispatch when provider is UNAVAILABLE; AI inference when AI provider is unavailable; snapshot finalization when warehouse is unreachable |
| Provider restrictions | Outbound dispatch blocked when circuit breaker OPEN or provider outage active; inbound continues |
| AI restrictions | AI inference blocked if AI provider unavailable; orchestration proceeds with rule-based evaluation only; STALE AI served if within TTL |
| Replay restrictions | Replay permitted if warehouse accessible and historical config resolvable |
| Escalation restrictions | Escalation candidacy assessed and routed; provider failure escalation candidacy generated |
| Observability | Degradation structured log required: `degradation_cause`, `affected_domains`, `degradation_onset_timestamp` |

---

#### MAINTENANCE

| Aspect | Behavior |
|---|---|
| Permitted operations | Migration execution; schema validation; config version promotion (governance-authorized); read-only diagnostic queries |
| Prohibited operations | All outreach orchestration evaluation loops; scheduled batch runs; AI inference for operational purposes |
| Provider restrictions | All provider calls suspended |
| AI restrictions | All AI inference suspended |
| Replay restrictions | Replay permitted if purely diagnostic and warehouse is not under migration |
| Escalation restrictions | Escalation routing suspended; candidacy assessment permitted for pre-existing cases |
| Observability | Maintenance start/end structured log with `maintenance_actor`, `maintenance_reason`, `maintenance_scope` |

---

### 3.2 Mode Transition Governance

| Transition | Permitted by | Audit required |
|---|---|---|
| SHADOW → LIVE | Governance Administrator | Yes — config version activation record |
| LIVE → SHADOW | Governance Administrator or Operational Administrator | Yes |
| LIVE → DEGRADED | Automatic (provider/AI outage detection) | Yes — degradation onset record |
| DEGRADED → LIVE | Automatic (recovery detection) OR Operational Administrator | Yes — recovery record |
| Any mode → REPLAY | Replay Services (SHADOW-only outputs) | Yes — replay diagnostic record |
| Any mode → MAINTENANCE | Governance Administrator | Yes |
| MAINTENANCE → previous mode | Governance Administrator | Yes |

No automation service may transition from SHADOW to LIVE without Governance Administrator authorization (AP-RT7).

---

### 3.3 Mode-Aware Sequencing

Every runtime loop checks execution mode as its second precondition (after config version validation). Mode determines which downstream paths are authorized. A loop that does not check execution mode before producing outputs is a specification violation.

---

## 4. CANONICAL RUNTIME ORCHESTRATION DOMAINS

---

The platform's runtime is organized into ten canonical orchestration domains. Each domain maps to a defined loop. Runtime loops do not share mutable state or directly invoke each other; they coordinate via governance-authorized intent records and shared append-only persistence.

---

### 4.1 Orchestration Evaluation Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Evaluate all students against eligibility, retry, and decision directives; produce governance-authorized `OrchestrationIntent` records for eligible students |
| **Trigger conditions** | Config V2 Group A `outreach_daily_trigger_hour_cst` (time-based); or operator-initiated batch trigger under governance authorization |
| **Replay behavior** | Full replay supported; all directive evaluations use `historical_config_version_id`; no LIVE dispatch produced |
| **SHADOW behavior** | Full evaluation proceeds; intents produced with `governance_scope = SHADOW_ONLY`; no outbound dispatch delegated |
| **LIVE behavior** | Intents produced with `governance_scope = AUTHORIZED`; delegation to outreach orchestration service proceeds |
| **Attribution** | `correlation_id` generated at loop start; propagated to every directive evaluation and every persisted intent record |
| **Observability** | Structured log per cycle: `loop_name`, `cycle_id`, `execution_mode`, `config_version_id`, `candidates_evaluated`, `intents_produced`, `duration_ms`, `outcome` |
| **Idempotency** | Keyed on `(cycle_date, execution_type, config_version_id)`; duplicate cycle key is a no-op; existing intents not re-produced |

---

### 4.2 Retry Orchestration Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Identify students in `NO_RESPONSE` state whose retry window has elapsed; coordinate retry orchestration via `outreach_retry_policy.md` assessment |
| **Trigger conditions** | Governed by Config V2 Group A retry timing variables; co-triggered with Orchestration Evaluation Loop |
| **Replay behavior** | Full replay supported; retry eligibility assessed against `historical_config_version_id` thresholds; no LIVE retry dispatch |
| **SHADOW behavior** | Retry candidacy assessed and logged; no LIVE dispatch produced |
| **LIVE behavior** | Retry intents produced; delegation to outreach orchestration service proceeds when `RetryPolicyAssessment.retry_authorized = true` |
| **Attribution** | `causation_id` linked to prior `OrchestrationIntent` for the student; `correlation_id` propagated |
| **Observability** | Structured log per cycle: `retry_candidates_evaluated`, `retry_authorized_count`, `retry_blocked_count`, `retry_exhausted_count`, `duration_ms` |
| **Idempotency** | Retry idempotency key per spec/04 §4.2; duplicate key → no-op |

---

### 4.3 Escalation Polling Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Evaluate students against `escalation_rules.md` to produce `EscalationOrchestrationAssessment` records; route candidacy signals to escalation routing service for human operator delivery |
| **Trigger conditions** | Triggered after Orchestration Evaluation Loop cycle completes; may also be triggered by retry exhaustion signals |
| **Replay behavior** | Escalation candidacy assessed under `historical_config_version_id`; outputs carry `REPLAY_ESCALATION_CANDIDATE` scope; no live routing |
| **SHADOW behavior** | Escalation candidacy assessed and logged; no live operator routing |
| **LIVE behavior** | `EscalationOrchestrationAssessment` records with `escalation_candidate = true` delegated to escalation routing service; routing is advisory — human acknowledgement required |
| **Attribution** | `causation_id` linked to originating orchestration cycle `correlation_id` |
| **Observability** | Structured log: `escalation_candidates_evaluated`, `candidacy_produced_count`, `replay_escalation_count`, `escalation_types_distribution`, `duration_ms` |
| **Idempotency** | Keyed on `(student_id, escalation_type, cycle_date)`; duplicate candidacy signal for same key within same cycle is suppressed |

---

### 4.4 AI Refresh Orchestration Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Identify students whose AI insight is STALE (beyond `ai_insight_ttl_hours` from Config V2 Group H) or MISSING; coordinate AI insight refresh via `llm_processing_contract.md` governance |
| **Trigger conditions** | Governed by Config V2 Group H `ai_insight_ttl_hours`; triggered before Orchestration Evaluation Loop when AI freshness is required for the cycle |
| **Replay behavior** | No live AI inference in replay; historical AI content sourced from `warehouse.snapshot_ai_narratives` (FINALIZED) or `ai_insights` table for non-finalized records |
| **SHADOW behavior** | AI refresh requests evaluated; AI provider calls authorized in SHADOW mode (advisory outputs tagged `outcome = shadow_only`) |
| **LIVE behavior** | AI refresh coordinated via AI advisory service; `AIAssessment.ai_governance_tier` updated in `ai_insights` table |
| **Attribution** | `ai_version_number`, `prompt_version`, `model_used`, `generated_at` captured in `ai_insights` record |
| **Observability** | Structured log: `stale_count`, `missing_count`, `refresh_requested_count`, `refresh_succeeded_count`, `provider_duration_ms_p95`, `provider_error_class_distribution` |
| **Idempotency** | AI refresh keyed on `(student_id, insight_type, date_period, prompt_version)` per spec/04 §4.4 |

---

### 4.5 Snapshot Finalization Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate transition of VALIDATING snapshots to FINALIZED state; physically copy AI narratives to `warehouse.snapshot_ai_narratives` (FAD-1) |
| **Trigger conditions** | Triggered by snapshot orchestration service when all validation gates pass for a given `(student_id, snapshot_month)` |
| **Replay behavior** | Replay reads finalized snapshot records; does not re-trigger finalization |
| **SHADOW behavior** | Snapshot finalization proceeds normally — finalization is not an outbound action; records tagged with `execution_mode` at time of finalization |
| **LIVE behavior** | Finalization produces FINALIZED state; AI narratives physically copied to warehouse; all finalized records are immutable (FAD-1) |
| **Attribution** | `finalization_actor`, `finalization_timestamp`, `config_version_id_at_finalization`, `ai_version_id_at_finalization` required |
| **Observability** | Structured log: `finalization_cycle_id`, `snapshots_finalized`, `finalization_failed_count`, `ai_copy_duration_ms`, `duplicate_finalization_attempts_blocked` |
| **Idempotency** | Keyed on `(student_id, snapshot_month)` per spec/04 §15.1; second attempt on same key is a no-op |

---

### 4.6 Report Generation Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate generation and publication of monthly cohort reports from FINALIZED snapshot data (FAD-2) |
| **Trigger conditions** | Governance-authorized trigger; cohort snapshot finalization completeness gate must pass before report generation begins |
| **Replay behavior** | Historical report regeneration reads FINALIZED warehouse data exclusively; no SQL Server reads, no AI calls, no GHL calls (FAD-2) |
| **SHADOW behavior** | Report generation proceeds normally; publication may be suppressed at operator discretion |
| **LIVE behavior** | Report generated and published; `warehouse.monthly_reports` record inserted; `report_audit_log` appended |
| **Attribution** | `report_generation_actor`, `lineage_version`, `template_version`, `config_version_id`, `snapshot_ids_included` required |
| **Observability** | Structured log: `report_cycle_id`, `cohort_id`, `report_month`, `generation_duration_ms`, `snapshot_count_used`, `publication_outcome` |
| **Idempotency** | Keyed on `(cohort_id, report_month, lineage_version)` per spec/04 §16.1; duplicate publication for same key creates `POTENTIALLY_DIVERGENT` annotation |

---

### 4.7 Provider Synchronization Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate SQL Server → PostgreSQL synchronization; update `student_trigger_data` from SQL Server read-only source; assess sync lag against `sql_server_max_sync_age_hours` from Config V2 Group K |
| **Trigger conditions** | Governed by Config V2 Group I system timing variables; must complete before Orchestration Evaluation Loop to ensure SQL Server-authoritative data is current |
| **Replay behavior** | Replay uses stored `student_trigger_data` snapshot; no SQL Server re-sync during replay; `sync_lag_hours` annotation preserved in replay context |
| **SHADOW behavior** | Sync proceeds normally in all execution modes — sync is read-only from SQL Server and is not an outbound action |
| **LIVE behavior** | `student_trigger_data` upserted from SQL Server; sync completion record written; sync lag assessed |
| **Attribution** | `sync_cycle_id`, `sync_source = sql_server`, `sync_record_count`, `sync_lag_hours`, `sync_timestamp` required |
| **Observability** | Structured log: `sync_cycle_id`, `records_synced`, `sync_duration_ms`, `sync_lag_hours`, `sql_server_connection_outcome`, `stale_threshold_exceeded` flag |
| **Idempotency** | SQL Server sync is always idempotent (upsert by `user_id`); re-running produces same PostgreSQL state as SQL Server source at time of run |

---

### 4.8 Replay Orchestration Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Simulate historical orchestration decisions using historical config version, historical student state, and FINALIZED warehouse records; produce replay diagnostic outputs without generating LIVE effects |
| **Trigger conditions** | Operator-initiated or compliance-initiated; governance authorization required; `source_artifact_id` and `historical_config_version_id` required as inputs |
| **Replay behavior** | This loop IS the replay loop; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` |
| **SHADOW behavior** | Replay is always SHADOW-only regardless of system execution mode (AP-RT2) |
| **LIVE behavior** | Explicitly prohibited (AP-OWN2, AP-RT2) |
| **Attribution** | `replay_cycle_id`, `source_artifact_id`, `historical_config_version_id`, `fingerprint_comparison_outcome`, `replay_partial` required |
| **Observability** | Full replay diagnostic set per `directives/agent_ownership_matrix.md` §6.4 and §11.4 |
| **Idempotency** | Idempotency key is `(source_artifact_id, replay_cycle_id)`; duplicate replay keys are suppressed |

---

### 4.9 Compliance Orchestration Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate compliance workflow execution (data access scope manifest, deletion scope execution, hold lifecycle management) under Compliance Authority governance |
| **Trigger conditions** | Compliance Operator initiated; compliance workflow authorization must be pre-obtained; pre-action audit entry required before execution begins (spec/04 §19.4) |
| **Replay behavior** | Compliance execution is not replayed; compliance audit records are read in replay for historical explainability only |
| **SHADOW behavior** | Compliance workflow intake and authorization proceed; execution deferred to PRODUCTION scope |
| **LIVE behavior** | Compliance actions executed under compliance pathway service account; all writes to `compliance_audit` schema |
| **Attribution** | `compliance_actor_identity`, `compliance_action_type`, `pre_action_audit_entry_id`, `authorization_timestamp`, `scope_manifest_id` required |
| **Observability** | Full compliance audit trail in `compliance_audit` schema; structured log per action |
| **Idempotency** | Compliance actions keyed per spec/04 §19.1; duplicate compliance request for same `(student_id, action_type, scope_manifest_id)` is blocked |

---

### 4.10 Observability Heartbeat Loop

| Attribute | Specification |
|---|---|
| **Purpose** | Emit periodic structured health records covering all active orchestration loops, provider connectivity, AI advisory freshness, sync lag state, and escalation backlog |
| **Trigger conditions** | Governed by Config V2 Group I system timing variables; runs independently of outreach orchestration cycles |
| **Replay behavior** | Heartbeat loops do not replay; historical heartbeat records are queryable for diagnostic purposes |
| **SHADOW behavior** | Heartbeat proceeds normally in all modes |
| **LIVE behavior** | Heartbeat emits structured log with all operational health metrics |
| **Attribution** | `heartbeat_id`, `execution_mode`, `config_version_id`, `emitted_at` required |
| **Observability** | Structured log covering: provider circuit breaker state, AI insight freshness distribution, sync lag hours, escalation backlog count, active compliance holds count, loop last-completion timestamps |
| **Idempotency** | Heartbeat records are append-only observability records; idempotency not required |

---

## 5. ORCHESTRATION GOVERNANCE SEQUENCING

---

### 5.1 Sequencing Principles

The canonical runtime governance sequencing applies to the Orchestration Evaluation Loop (§4.1). All other loops follow the same precondition model.

1. **Precondition gate** — config version, execution mode, attribution context validated before any evaluation begins
2. **SQL Server sync completion** — Provider Synchronization Loop (§4.7) must complete successfully before Orchestration Evaluation Loop consumes student data
3. **AI freshness assessment** — AI Refresh Orchestration Loop (§4.4) runs before Orchestration Evaluation Loop if AI advisory freshness is required for the cycle
4. **Directive evaluation** — eligibility, retry, decision, channel directives evaluated in governance-defined order; outputs are structured assessment objects, not action strings
5. **Intent record persistence** — `OrchestrationIntent` records written to `student_timeline_events` before any execution delegation; write failure is a loop failure
6. **Execution delegation** — intents delegated to orchestration services; runtime loop does not own execution
7. **Observability emission** — structured log emitted at loop completion; never omitted (AP-RT15)

---

### 5.2 Governance Precondition Gate

Before any loop evaluates candidates, the following preconditions must be satisfied:

| Precondition | Required value | Failure behavior |
|---|---|---|
| `config_version_id` | Non-null ACTIVE config version | Loop does not start; structured error log emitted; escalation candidacy generated |
| `execution_mode` | `SHADOW` or `LIVE` | Loop does not start; structured error log emitted |
| `correlation_id` | UUID v4 generated for this loop cycle | Loop does not start |
| Config V2 threshold resolution | All required Group variables resolvable | `UNKNOWN_V0` substituted for missing keys; `CONFIG_THRESHOLD_MISSING_{KEY}` warning emitted; loop continues with DEGRADED annotation |
| SQL Server data age | `sync_lag_hours ≤ sql_server_max_sync_age_hours` (Config V2 Group K) | Loop continues with `STALE_SQL_SERVER_DATA` annotation; not blocking |

---

### 5.3 Canonical Orchestration Evaluation Sequence

The governed runtime sequencing for the Orchestration Evaluation Loop is:

```
PRECONDITION GATE (§5.2)
  ↓
PROVIDER SYNC VALIDATION (sql_server_max_sync_age_hours check)
  ↓
AI FRESHNESS GATE (ai_insight_ttl_hours check per student)
  ↓
ELIGIBILITY ASSESSMENT (outreach_eligibility_rules.md → EligibilityAssessment)
  ↓
RETRY POLICY ASSESSMENT (outreach_retry_policy.md → RetryPolicyAssessment, for retry candidates)
  ↓
CORE DECISION ENGINE (core_decision_engine.md → OrchestrationIntent)
  ↓
CHANNEL SELECTION (channel_selection_rules.md → ChannelSelectionAssessment)
  ↓
ESCALATION CANDIDACY ASSESSMENT (escalation_rules.md → EscalationOrchestrationAssessment)
  ↓
INTENT RECORD PERSISTENCE (student_timeline_events append)
  ↓
EXECUTION DELEGATION (orchestration services, under governance authorization)
  ↓
PROVIDER ORCHESTRATION ASSESSMENT (ghl_integration_contract.md → ProviderOrchestrationAssessment)
  ↓
OBSERVABILITY EMISSION
```

This sequence is deterministic. No step may be skipped. No step may produce direct execution output that bypasses the next step.

---

### 5.4 Intent Delegation Boundaries

| Stage | Owner | Runtime loop responsibility |
|---|---|---|
| Advisory generation | Directive layer | Invoke directive evaluation; receive assessment objects |
| Intent validation | Runtime loop | Validate `OrchestrationIntent` is governance-authorized for dispatch |
| Execution delegation | Orchestration services | Runtime loop delegates; does not own execution path |
| Provider dispatch | Provider orchestration services | Runtime loop coordinates; does not call GHL directly |
| State persistence | State management service | Runtime loop does not write state transitions directly |
| Observability | Runtime loop | Loop emits structured cycle-level log |

---

## 6. RETRY ORCHESTRATION GOVERNANCE

---

### 6.1 Config V2 Retry Governance

All retry orchestration thresholds are governed by Config V2. No retry threshold is hardcoded in runtime architecture.

| Threshold | Config V2 variable | Group | Classification |
|---|---|---|---|
| Retry timing window | `outreach_retry_window_days` | A | OPERATIONAL_TUNING |
| Maximum retry attempts | `outreach_max_retry_attempts` | A | OPERATIONAL_TUNING |
| Provider failure retry attempts | `provider_failure_max_retry_attempts` | F | PROVIDER_FAILURE_THRESHOLD |
| Provider circuit breaker threshold | `provider_failure_circuit_breaker_threshold` | F | PROVIDER_FAILURE_THRESHOLD |
| Provider retry backoff | `provider_failure_retry_backoff_base_seconds` | F | PROVIDER_FAILURE_THRESHOLD |

When any threshold key resolves as missing from the ACTIVE config version, `UNKNOWN_V0` is substituted and `CONFIG_THRESHOLD_MISSING_{KEY}` is emitted. The retry orchestration loop continues in DEGRADED annotation state; it does not fail silently or assume a hardcoded fallback value (AP-RT9).

---

### 6.2 Runtime-Safe Retry Sequencing

Retry orchestration proceeds through the same governance sequencing as the primary Orchestration Evaluation Loop (§5.3), with the following additional preconditions:

1. Student state must be `NO_RESPONSE` or `CONTACTED` (time-window elapsed) — state validation is performed by the state management service, not by the runtime loop
2. `RetryPolicyAssessment.retry_authorized = true` — produced by `outreach_retry_policy.md`; runtime loop does not re-implement retry logic
3. Retry idempotency key must not already exist in `processed_events` for this `(student_id, checkpoint_type, contact_attempt)` combination
4. Compliance hold must not be active — checked in governance precondition gate

---

### 6.3 Replay-Safe Retry Semantics

Retry orchestration in REPLAY mode:
* Evaluates `outreach_retry_policy.md` using the `historical_config_version_id` resolved for the replay context
* Produces `RetryPolicyAssessment` with `governance_scope = REPLAY_ONLY`
* Does not produce LIVE retry dispatch
* `UNKNOWN_V0` substituted for any threshold missing from historical config version — `replay_partial = true` annotation added to replay diagnostic record
* Historical retry records from `processed_events` are the authoritative source for what retries occurred; live retry policy evaluation in replay is diagnostic only

---

### 6.4 Provider-Governed Execution Boundaries

Retry dispatch is governed by `ghl_integration_contract.md`. The runtime retry loop:
* Produces `OrchestrationIntent` with `intent_type = RETRY_OUTREACH`
* Delegates to outreach orchestration service
* Outreach orchestration service evaluates `ProviderOrchestrationAssessment` before any dispatch
* `ProviderOrchestrationAssessment.governance_scope` must be `AUTHORIZED` before dispatch proceeds
* If `governance_scope = UNAVAILABLE`, retry dispatch is blocked; `RETRY_EXHAUSTED` escalation candidacy is generated; runtime loop does not silently skip (AP-RT6)

---

### 6.5 Retry Termination Governance

Retry orchestration terminates for a student when any of the following governed conditions are met:

| Termination condition | Governed by | Runtime loop behavior |
|---|---|---|
| `contact_attempt ≥ outreach_max_retry_attempts` (Config V2 Group A) | `outreach_retry_policy.md` | Delegate to escalation candidacy assessment |
| `RetryPolicyAssessment.retry_authorized = false` with `reason = RETRY_EXHAUSTED` | `outreach_retry_policy.md` | Produce `RETRY_EXHAUSTED` orchestration record; delegate to escalation |
| Student state is `RESPONDED`, `CLOSED`, or `INTERVENTION_REQUIRED` | State management service | Loop skips student on next cycle via precondition check |
| Compliance hold activated | `ghl_integration_contract.md` RULE 5 | Dispatch blocked; compliance hold record annotation |
| Provider circuit breaker OPEN | `ghl_integration_contract.md` RULE 4 | Outbound blocked; provider failure escalation candidacy |

Retry termination never results in a silent close. Every termination condition produces an observable record.

---

## 7. REPLAY & REGENERATION RUNTIME SEMANTICS

---

### 7.1 Replay Orchestration Lifecycle

A replay cycle proceeds through the following governed phases:

```
GOVERNANCE AUTHORIZATION (operator-initiated; authorization record written)
  ↓
REPLAY PRECONDITION GATE (source_artifact_id, historical_config_version_id validated)
  ↓
HISTORICAL STATE RESOLUTION (student state from warehouse/processed_events at historical timestamp)
  ↓
HISTORICAL CONFIG VERSION RESOLUTION (config version at original execution time)
  ↓
DIRECTIVE EVALUATION (all directives evaluated under historical config; SHADOW-only outputs)
  ↓
FINGERPRINT COMPARISON (current re-evaluation vs stored historical outcome)
  ↓
REPLAY DIAGNOSTIC EMISSION (source_artifact_id, fingerprint_comparison_outcome, replay_partial)
  ↓
NO LIVE EFFECTS PRODUCED
```

---

### 7.2 Replay Suppression Behavior

The following categories of LIVE effects are suppressed in all replay contexts:

| Effect category | Suppression mechanism | Reference |
|---|---|---|
| Outbound GHL dispatch | `ProviderOrchestrationAssessment.outbound_suppressed = true` | AP-GHL5; ghl_integration_contract.md RULE 1 |
| Live AI inference | `AIAssessment.ai_blocked = true`; FINALIZED_COPY sourced from warehouse | AP-AI5; llm_processing_contract.md RULE 2 |
| Student state transitions | Replay Services hold no state write authority | AP-OWN2 |
| Escalation routing | Escalation outputs carry `REPLAY_ESCALATION_CANDIDATE` scope | escalation_rules.md §6 |
| Compliance workflow execution | No compliance actions in replay context | agent_ownership_matrix.md §6 |
| Warehouse mutations | Replay loop reads warehouse; does not write | AP-OWN15 |

---

### 7.3 Historical Resolution Semantics

When replay is executing, the following resolution rules apply:

| Resource | Historical source | Fallback if unavailable |
|---|---|---|
| Student state at replay timestamp | `state_transition_log` at `historical_timestamp` | `HISTORY_INCOMPLETE` annotation; `replay_partial = true` |
| Config version at original execution | `config_version_registry` by `config_version_id` | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING` emitted |
| AI advisory content | `warehouse.snapshot_ai_narratives` (FINALIZED) or `ai_insights` (non-finalized) | `ai_governance_tier = UNAVAILABLE` |
| Provider delivery state | `ghl_messages` + `processed_events` at historical timestamp | `delivery_state = UNKNOWN`; provider lineage incomplete annotation |

---

### 7.4 Replay Observability

Every replay cycle emits the full diagnostic record:

| Field | Required |
|---|---|
| `replay_cycle_id` | UUID v4 |
| `source_artifact_id` | The artifact being replayed |
| `historical_config_version_id` | Config version resolved for the replay |
| `historical_execution_timestamp` | When the original orchestration occurred |
| `fingerprint_comparison_outcome` | `MATCH`, `DIVERGENT`, or `UNKNOWN` |
| `replay_partial` | True if any threshold was UNKNOWN_V0 |
| `divergence_fields` | List of fields that differed between historical and re-evaluated outcome |
| `replay_suppression_applied` | All suppression categories active during replay |

---

### 7.5 Regeneration Restrictions

Report regeneration is NOT replay. The distinction is architecturally enforced:

| Characteristic | Replay | Regeneration |
|---|---|---|
| Purpose | Simulate historical orchestration decisions | Re-render historical report from immutable snapshot |
| Source | Historical state + historical config | `warehouse.student_snapshots` + `warehouse.snapshot_ai_narratives` exclusively (FAD-2) |
| External calls | None | None — absolute prohibition |
| Output | Replay diagnostic records | Re-rendered report artifact |
| Warehouse mutation | None | None |
| Config version required | Yes (historical) | No — regeneration reads stored snapshot values |

---

## 8. PROVIDER GOVERNANCE AT RUNTIME

---

### 8.1 Provider Boundary Principles

Runtime loops never own provider governance. The provider boundary is governed exclusively by `directives/ghl_integration_contract.md`.

* Runtime loops produce `OrchestrationIntent` records
* Orchestration services evaluate `ProviderOrchestrationAssessment` before delegating to GHL
* If `governance_scope ≠ AUTHORIZED`, no outbound dispatch occurs
* No runtime loop may construct a GHL API call, an SMS payload, an email payload, or a meeting booking request
* Provider selection, channel sequencing, and delivery telemetry are governed by `ghl_integration_contract.md` and `channel_selection_rules.md` — not by runtime loops

---

### 8.2 Provider Synchronization Governance

The Provider Synchronization Loop (§4.7) is the only runtime domain that interacts with SQL Server directly:
* SQL Server is read-only — no writes, no mutations from any runtime loop
* Sync lag is assessed against `sql_server_max_sync_age_hours` from Config V2 Group K
* Sync backlog annotates student records but does not block orchestration evaluation
* GHL webhook ingestion occurs independently of sync orchestration — webhooks are ingested and attributed by the platform's ingestion service, not by runtime loops

---

### 8.3 Provider Failure Runtime Behavior

| Provider failure state | Runtime loop behavior |
|---|---|
| Circuit breaker OPEN | Outbound dispatch blocked; `governance_scope = UNAVAILABLE`; provider failure escalation candidacy generated; loop continues for non-dispatch domains |
| Provider outage active | Same as circuit breaker OPEN |
| Retry budget exhausted | `RETRY_EXHAUSTED` annotation; escalation candidacy generated; no further retry dispatch |
| Sync lag exceeds threshold | `STALE_SQL_SERVER_DATA` annotation; loop continues; orchestration proceeds with annotated data |
| `AUTH_FAILURE` | TERMINAL class; no retry; alert escalation generated; all subsequent provider interactions blocked until key rotation confirmed |

---

## 9. AI GOVERNANCE AT RUNTIME

---

### 9.1 Advisory-Only Runtime Principle

AI advisory outputs are consumed by runtime loops, not obeyed. At runtime:
* `AIAssessment.advisory_content.recommended_intervention` informs but does not authorize `OrchestrationIntent`
* `AIAssessment.confidence_metadata.confidence_score` governs advisory scope (FULL/LIMITED/UNAVAILABLE) but does not override rule-based eligibility
* No runtime loop may produce an `OrchestrationIntent` from AI advisory output alone (AP-RT11)

---

### 9.2 Stale AI Runtime Restrictions

| AI governance tier | Runtime behavior |
|---|---|
| CONFIDENT (≥ 0.70, within TTL) | Full advisory scope; may elevate escalation severity in LIVE mode |
| ADVISORY (< 0.70 or approaching TTL) | Limited advisory scope; may not independently drive LIVE escalation |
| STALE (beyond `ai_insight_ttl_hours`) | Advisory scope limited; LIVE escalation from AI advisory blocked; orchestration proceeds with rule-based evaluation only |
| IN_FLIGHT | Prior version served if available; DEFERRED advisory scope; loop proceeds without waiting |
| UNAVAILABLE (null insight) | Rule-based evaluation only; orchestration not blocked |

Stale AI does not block orchestration. It restricts advisory scope and escalation authority only.

---

### 9.3 FINALIZED_COPY Runtime Semantics

Once AI text is physically copied to `warehouse.snapshot_ai_narratives` at FINALIZED state (FAD-1):
* The AI Refresh Orchestration Loop does not re-evaluate or overwrite this content
* Replay reads this content directly — no live AI inference is triggered even if the content appears stale
* No runtime loop has authority to mutate `warehouse.snapshot_ai_narratives` (AP-OWN15)
* `ai_governance_tier = FINALIZED_COPY` is the highest precedence tier; it overrides all staleness assessments

---

### 9.4 AI Refresh Governance

The AI Refresh Orchestration Loop (§4.4):
* Identifies students requiring refresh based on `ai_insight_ttl_hours` threshold
* Delegates refresh to AI advisory service
* Does not own the AI provider call (AP-RT1)
* Failed AI refresh does not block snapshot finalization — `ai_content_stale = true` flag is set; finalization proceeds

---

## 10. DEGRADATION & FAILURE GOVERNANCE

---

### 10.1 Deterministic Degradation Principles

Degradation is observable, not silent. Every degraded runtime state must:
* Emit a structured log entry with `degradation_cause`, `affected_domains`, and `outcome = partial` or `outcome = failure`
* Produce an observable escalation candidacy signal for human awareness
* Describe what operations continued and what operations were blocked
* Never silently swallow a failure or substitute a silent default

The following patterns are prohibited (AP-RT14):
* `try { ... } catch (e) {}` semantics — swallowing an error without logging
* Falling back to a hardcoded default when a Config V2 threshold is missing
* Retrying indefinitely without an upper bound from Config V2

---

### 10.2 Deterministic Degradation Condition Table

| Condition | Affected domains | Runtime behavior | Orchestration continues | Observability |
|---|---|---|---|---|
| Provider circuit breaker OPEN | §4.1, §4.2 | Outbound dispatch blocked; `governance_scope = UNAVAILABLE` | Yes (inbound, AI, sync, escalation continue) | `CIRCUIT_BREAKER_OPEN` event; provider failure escalation candidacy |
| Provider outage active | §4.1, §4.2 | Same as circuit open | Yes | `PROVIDER_OUTAGE` event; degradation onset record |
| AI provider unavailable | §4.4 | AI refresh blocked; rule-based evaluation only | Yes | `AI_PROVIDER_UNAVAILABLE` event; stale AI annotation |
| SQL Server sync lag exceeded | §4.7 | `STALE_SQL_SERVER_DATA` annotation; orchestration continues | Yes | `SYNC_LAG_EXCEEDED` event |
| SQL Server connection failed | §4.7 | Sync blocked for this cycle; last successful sync data used | Yes (with stale annotation) | `SQL_SERVER_UNAVAILABLE` event; escalation candidacy |
| Scheduler lag detected | §4.1, §4.2 | Missed cycle detection; recovery cycle triggered | Yes (recovery) | `SCHEDULER_LAG_DETECTED` event; recovery cycle attribution |
| Duplicate event storm | §4.7 inbound webhooks | Deduplication gate absorbs duplicates; `DUPLICATE_SUPPRESSED` scope | Yes | `DUPLICATE_EVENT_STORM` event; dedup count emitted |
| Config threshold missing | All loops | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning; loop annotated DEGRADED | Yes (annotated) | `CONFIG_THRESHOLD_MISSING` warning per key |
| Observability pipeline degraded | All loops | Loops continue; `OBSERVABILITY_DEGRADED` flag emitted to stderr | Yes | Direct stderr alert |
| Compliance hold active (batch) | §4.1, §4.2 for affected student | Outbound dispatch blocked for that student; other students unaffected | Yes | `COMPLIANCE_HOLD_DISPATCH_BLOCKED` per student |
| Warehouse write failure | §4.5, §4.6 | Loop fails for affected record; structured failure log; dead-letter for retry | No (for that record) | `WAREHOUSE_WRITE_FAILURE` event; recovery path documented |

---

### 10.3 Provider Outage Runtime Behavior

When a provider outage is detected:
* **Outbound dispatch** — blocked for all students in the current cycle; `governance_scope = UNAVAILABLE`; escalation candidacy generated for provider failure
* **Inbound webhook ingestion** — continues normally; webhooks received during provider outage are ingested and attributed; no state transitions produced from webhooks without governance authorization
* **SQL Server platform reads** — unaffected; sync loop continues
* **AI evaluation** — unaffected
* **Retry budget protection** — retry attempts during a provider outage are not consumed from the student's retry budget if the provider was unavailable (governed by `outreach_retry_policy.md`)

---

### 10.4 AI Outage Runtime Behavior

When the AI provider is unavailable:
* **AI refresh orchestration** — blocked for new requests; circuit breaker state updated
* **Orchestration evaluation** — proceeds with rule-based evaluation only; AI advisory scope = UNAVAILABLE
* **Snapshot finalization** — not blocked; `ai_content_stale = true` flag set
* **Escalation candidacy** — rule-based severity assessment applies; AI may not elevate without advisory content
* **FINALIZED_COPY records** — unaffected; sourced from warehouse regardless of AI provider state

---

### 10.5 Scheduler Lag Governance

Scheduler lag is detected when an expected cycle has no corresponding completion record within the governed window:
* Lag detection compares expected trigger time (governed by Config V2 Group A `outreach_daily_trigger_hour_cst`) against last recorded cycle completion timestamp
* Missed cycle triggers a recovery orchestration cycle with `execution_type = recovery`
* Recovery cycle carries full attribution: `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`
* Recovery cycle is idempotent — same idempotency key as the missed cycle; duplicate processing is blocked
* Scheduler lag persisting beyond governance-defined bounds generates an escalation candidacy signal

---

### 10.6 Duplicate Event Storm Handling

Inbound webhook duplicate events are absorbed by the deduplication gate in `ghl_integration_contract.md` RULE 6:
* `processed_events` dedup lookup occurs before any state management service call
* All duplicate detections produce an audit log entry — no silent drops
* Duplicate event storms do not degrade outbound orchestration domains

---

### 10.7 Sync Backlog Governance

SQL Server sync backlog (sync lag exceeding `sql_server_max_sync_age_hours` from Config V2 Group K):
* Annotates affected student records with `stale_sql_server_data = true`
* Does not block orchestration evaluation — governance model allows orchestration to proceed with annotated data
* Annotated decisions carry `STALE_SQL_SERVER_DATA` annotation in orchestration intent records
* Persistent sync backlog generates escalation candidacy if lag exceeds governance-defined threshold

---

### 10.8 Observability Degradation

If the observability pipeline degrades:
* Orchestration loops continue — observability failure does not block execution
* Structured log entries that fail to be written are directed to stderr with `OBSERVABILITY_DEGRADED` flag
* The failure is itself observable — it does not disappear silently

---

## 11. RUNTIME ATTRIBUTION & OBSERVABILITY

---

### 11.1 Runtime Correlation ID Propagation

A `correlation_id` (UUID v4) is generated at the start of every orchestration loop cycle. This ID:
* Propagates through every directive evaluation within the cycle
* Propagates through every execution service call within the cycle
* Propagates through every provider orchestration assessment within the cycle
* Is persisted in every `OrchestrationIntent` record, every `state_transition_log` record, every `processed_events` record, and every structured log entry within the cycle

A failure that cannot be traced from symptom to root cause using a single `correlation_id` is an observability defect (spec/06).

---

### 11.2 Runtime Attribution Requirements

Every runtime orchestration record must carry:

| Field | Required in |
|---|---|
| `correlation_id` | All records in every loop |
| `causation_id` | All records derived from a prior orchestration record |
| `config_version_id` | All orchestration evaluation records |
| `execution_mode` | All records |
| `execution_type` | All records (`original`, `replay`, `regeneration`, `recovery`) |
| `loop_name` | Structured log entries |
| `actor_identity` | All human-initiated actions; `system` for automated loops |
| `attribution_timestamp` | All records (when the action occurred, not when logged) |

---

### 11.3 Orchestration Lineage

The full orchestration lineage chain for any outreach event:

```
sync_cycle_id  →  SQL Server source record
  ↓
correlation_id  →  Orchestration Evaluation Loop cycle
  ↓
OrchestrationIntent.intent_id  →  Intent record
  ↓
ProviderOrchestrationAssessment.correlation_id  →  Provider assessment
  ↓
processed_events.idempotency_key  →  Execution dedup record
  ↓
ghl_messages.ghl_message_id  →  Provider delivery record
```

This chain enables forensic reconstruction of any outreach decision from SQL Server source through provider delivery confirmation.

---

### 11.4 Required Runtime Observability Fields

Every runtime loop emits a structured JSON record to stdout upon cycle completion:

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "runtime_orchestration",
  "event": "loop_cycle_complete",
  "loop_name": "string",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | REPLAY | REGENERATION | DEGRADED | MAINTENANCE",
  "execution_type": "original | replay | regeneration | recovery",
  "config_version_id": "string | null",
  "duration_ms": 0,
  "outcome": "success | failure | partial | shadow_only",
  "candidates_evaluated": 0,
  "intents_produced": 0,
  "degradation_flags": [],
  "config_threshold_missing_keys": []
}
```

PII (student name, email, phone) must not appear in runtime observability records (AP-RT13).

---

### 11.5 Idempotency Key Requirements per Loop

| Loop | Idempotency key | Source |
|---|---|---|
| Orchestration Evaluation Loop | `(cycle_date, execution_type, config_version_id)` | Runtime loop |
| Retry Orchestration Loop | `(student_id, checkpoint_type, contact_attempt)` | spec/04 §4.2 |
| Escalation Polling Loop | `(student_id, escalation_type, cycle_date)` | escalation_rules.md |
| AI Refresh Orchestration Loop | `(student_id, insight_type, date_period, prompt_version)` | spec/04 §4.4 |
| Snapshot Finalization Loop | `(student_id, snapshot_month)` | spec/04 §15.1 |
| Report Generation Loop | `(cohort_id, report_month, lineage_version)` | spec/04 §16.1 |
| Provider Synchronization Loop | `(sync_cycle_id)` | Sync service |
| Replay Orchestration Loop | `(source_artifact_id, replay_cycle_id)` | Replay service |
| Compliance Orchestration Loop | `(student_id, action_type, scope_manifest_id)` | spec/04 §19.1 |
| Observability Heartbeat Loop | N/A — append-only observability records | — |

---

## 12. ARCHITECTURE PRESERVATION RULES

---

The following rules are MUST NOT prohibitions. Violation of any rule is a specification defect.

| Rule | Prohibition |
|---|---|
| **AP-RT1** | MUST NOT allow any runtime loop to directly call a provider API (GHL, AI provider, SMS, email, meeting booking); all provider interactions are delegated to governance-authorized orchestration services via the `ghl_integration_contract.md` and `llm_processing_contract.md` boundaries |
| **AP-RT2** | MUST NOT allow the Replay Orchestration Loop to produce LIVE effects; all replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; live dispatch, live state transitions, and live AI inference in replay context are specification violations |
| **AP-RT3** | MUST NOT allow any runtime loop to execute without a valid ACTIVE config version; the governance precondition gate (§5.2) must fire before any candidate evaluation begins |
| **AP-RT4** | MUST NOT allow any runtime loop to produce an `OrchestrationIntent` without propagating a `correlation_id` from the loop cycle into the intent record; unattributed intents are specification violations |
| **AP-RT5** | MUST NOT allow any runtime loop to silently skip a student candidate due to an error; all skips must produce a structured log entry with `skip_reason`, `student_id` (opaque), and `correlation_id` |
| **AP-RT6** | MUST NOT allow provider failure to silently absorb outbound dispatch failures; all `governance_scope = UNAVAILABLE` outcomes must produce an observable audit record and an escalation candidacy signal |
| **AP-RT7** | MUST NOT allow any automation service to transition execution mode from SHADOW to LIVE; SHADOW-to-LIVE transition requires Governance Administrator authorization and a config version activation record |
| **AP-RT8** | MUST NOT allow any runtime loop to perform a direct write to `warehouse` or `compliance_audit` schemas outside the designated service account paths (AP-OWN15) |
| **AP-RT9** | MUST NOT allow any runtime loop to substitute a hardcoded fallback value when a Config V2 threshold key is missing; `UNKNOWN_V0` must be substituted and `CONFIG_THRESHOLD_MISSING_{KEY}` emitted; no silent default assumption |
| **AP-RT10** | MUST NOT allow duplicate LIVE execution of the same `OrchestrationIntent`; the idempotency key in `processed_events` must be checked before any execution delegation; a duplicate key is a no-op, not a second execution |
| **AP-RT11** | MUST NOT allow an `OrchestrationIntent` to be produced from AI advisory output alone; AI advisory informs but does not authorize orchestration decisions; rule-based directive evaluation must produce the intent |
| **AP-RT12** | MUST NOT allow any runtime loop to re-implement directive logic; eligibility, retry policy, decision engine, channel selection, escalation, AI governance, and provider governance evaluations are delegated to their respective directives |
| **AP-RT13** | MUST NOT log raw PII (student name, email, phone, transcript content, payment details) in runtime orchestration observability records; opaque `student_id` and `correlation_id` only |
| **AP-RT14** | MUST NOT silently swallow runtime failures; every caught exception must be classified with a stable `error_class`, logged with full context (excluding PII), and produce either a retry path or a dead-letter record with recovery instructions |
| **AP-RT15** | MUST NOT allow an orphaned orchestration cycle — a cycle that began (correlation_id generated) but did not emit an observability record at completion; every cycle that starts must emit a structured completion log, even if the outcome is `failure` |

---

## 13. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Orchestration Evaluation Loop (§4.1) and Provider Synchronization Loop (§4.7) active
* Retry Orchestration Loop deferred — single attempt per student per cycle
* Escalation Polling Loop: escalation candidacy assessed and logged; no live routing
* AI Refresh Orchestration Loop: deferred; rule-based evaluation only
* Snapshot Finalization Loop: deferred
* Report Generation Loop: deferred
* Replay Orchestration Loop: deferred
* Compliance Orchestration Loop: deferred
* Observability Heartbeat Loop: minimal — cycle start/end records only
* SHADOW mode enforcement on all automation
* Config V2 Group A, F, K thresholds used; remaining groups deferred

---

### STANDARD

* Orchestration Evaluation Loop, Retry Orchestration Loop, Escalation Polling Loop, AI Refresh Orchestration Loop, Provider Synchronization Loop active
* Snapshot Finalization Loop active
* Report Generation Loop: generation active; publication governance deferred to PRODUCTION
* Replay Orchestration Loop: diagnostic mode; operator-initiated only
* Compliance Orchestration Loop: intake and authorization active; execution deferred
* Observability Heartbeat Loop: full health record emission
* All 10 Config V2 groups active
* Full idempotency enforcement across all active loops

---

### PRODUCTION

* All 10 canonical runtime orchestration domains active
* Full governance precondition enforcement on every loop
* Compliance Orchestration Loop execution active (pre-action audit entry hard gate enforced)
* Emergency recovery orchestration cycles governed (UE-RT5 resolved)
* Full provider degradation governance active (circuit breaker, retry collapse, provider outage)
* AI governance tier enforcement active for all orchestration decisions
* Full observability pipeline: correlation_id traceability end-to-end verified

---

## 14. ACCEPTANCE CRITERIA

---

### AC-RT1 — Governance Precondition Enforcement

**Given** no ACTIVE config version exists
**When** any runtime loop attempts to begin candidate evaluation
**Then** the loop does not start; a structured error log is emitted with `PRECONDITION_FAILED_NO_ACTIVE_CONFIG`; no candidate is evaluated; no intent is produced

---

### AC-RT2 — Replay LIVE Suppression

**Given** `execution_type = replay`
**When** the Replay Orchestration Loop evaluates a student's historical orchestration context
**Then** no LIVE outbound dispatch is generated; no LIVE AI inference is triggered; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; a replay diagnostic record is emitted

---

### AC-RT3 — Config V2 Retry Threshold Governance

**Given** `outreach_max_retry_attempts` is present in the ACTIVE config version
**When** the Retry Orchestration Loop evaluates a student
**Then** the retry termination check uses the config-governed threshold; `RetryPolicyAssessment.config_version_id` matches the ACTIVE config version; no hardcoded value is used

---

### AC-RT4 — Missing Config Threshold UNKNOWN_V0

**Given** a required Config V2 threshold key is absent from the ACTIVE config version
**When** any runtime loop evaluates a candidate requiring that threshold
**Then** `UNKNOWN_V0` is substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning is emitted; the loop continues with `DEGRADED` annotation; no hardcoded fallback value is used

---

### AC-RT5 — Idempotent Orchestration Cycle

**Given** the Orchestration Evaluation Loop has already produced an `OrchestrationIntent` for a student with a given idempotency key
**When** the loop is re-triggered for the same cycle inputs
**Then** the `processed_events` dedup check fires; the duplicate key is a no-op; no second intent is produced; no second dispatch is delegated

---

### AC-RT6 — Provider Failure Observability

**Given** the GHL provider circuit breaker opens during an orchestration cycle
**When** outbound dispatch delegation is attempted
**Then** `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`; a `CIRCUIT_BREAKER_OPEN` structured log is emitted; a provider failure escalation candidacy signal is produced; the runtime loop continues for non-dispatch domains

---

### AC-RT7 — SHADOW Mode Enforcement

**Given** `execution_mode = SHADOW`
**When** the Orchestration Evaluation Loop produces an `OrchestrationIntent` with `intent_type = INITIATE_OUTREACH`
**Then** the intent carries `governance_scope = SHADOW_ONLY`; no LIVE dispatch is delegated; all outputs are tagged `outcome = shadow_only`

---

### AC-RT8 — Attribution Continuity

**Given** an orchestration cycle is triggered
**When** the cycle completes
**Then** a single `correlation_id` is present in the cycle's structured log, in every `OrchestrationIntent` record produced, in every `processed_events` record written, and in every directive evaluation record within the cycle; no orchestration record exists without a `correlation_id`

---

### AC-RT9 — No Direct Provider Dispatch

**Given** an `OrchestrationIntent` with `intent_type = INITIATE_OUTREACH` is produced
**When** the runtime loop processes the intent
**Then** the intent is delegated to the outreach orchestration service; the runtime loop does not construct a GHL API payload, an SMS message, an email body, or a meeting booking request

---

### AC-RT10 — Orphaned Cycle Prevention

**Given** a runtime loop cycle begins (correlation_id generated)
**When** the cycle encounters a fatal error mid-execution
**Then** a structured completion log is emitted with `outcome = failure`; the failure is classified with a stable `error_class`; a dead-letter record is written for any unprocessed candidates; the cycle does not terminate silently

---

### AC-RT11 — Stale AI Restriction at Runtime

**Given** `AIAssessment.ai_governance_tier = STALE` for a student
**When** the Escalation Polling Loop evaluates escalation candidacy for that student
**Then** stale AI advisory does not independently drive LIVE escalation; rule-based escalation assessment proceeds; escalation severity may not be elevated by STALE AI; the stale AI annotation is present in the escalation candidacy record

---

### AC-RT12 — Regeneration External Call Prohibition

**Given** a report regeneration cycle is triggered from a FINALIZED snapshot
**When** the Report Generation Loop executes regeneration
**Then** no SQL Server read occurs; no AI provider call is made; no GHL API call is made; report content is derived exclusively from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives`; the regenerated report is identical to the original for identical inputs (FAD-2)

---

## 15. UNRESOLVED CONCERNS

---

### UE-RT1 — Multi-Loop Scheduling Conflict (OPERATIONAL DECISION)

**Problem:** No conflict resolution protocol exists when multiple orchestration loops (e.g., Snapshot Finalization Loop and Report Generation Loop) are scheduled to run concurrently and both require access to the same `student_snapshots` data.

**Impact:** Report generation starting before snapshot finalization completes for all students in the cohort could produce incomplete reports.

**Classification:** Operational decision. Requires defining inter-loop dependency ordering, blocking behavior when dependencies are not met, and the escalation path for inter-loop conflicts.

---

### UE-RT2 — Recovery Cycle Authorization Governance (GOVERNANCE DECISION)

**Problem:** When a missed cycle is detected and a recovery cycle is triggered (§10.5), the governance protocol for when a recovery cycle requires human confirmation vs proceeds automatically has not been defined.

**Impact:** A recovery cycle running without human awareness could execute outreach for a missed day without operators knowing it was a recovery.

**Classification:** Governance decision. Requires defining whether recovery cycles require Operational Administrator authorization before running.

---

### UE-RT3 — Maintenance Mode Loop Quiescence (OPERATIONAL DECISION)

**Problem:** When the system transitions to MAINTENANCE mode, the protocol for gracefully quiescing in-progress orchestration loops has not been defined.

**Impact:** Partial execution during maintenance could produce incomplete intent records or orphaned attribution chains.

**Classification:** Operational decision. Requires defining the quiescence protocol for in-progress loops before maintenance mode takes effect.

---

### UE-RT4 — Observability Heartbeat Failure Escalation Threshold (OPERATIONAL DECISION)

**Problem:** The Observability Heartbeat Loop (§4.10) detects observability pipeline degradation, but the threshold at which a missing heartbeat triggers human-visible escalation has not been defined.

**Impact:** Extended observability outages could mask operational failures.

**Classification:** Operational decision. Requires a Config V2 variable (likely Group I) governing the heartbeat failure escalation threshold.

---

### UE-RT5 — Emergency Runtime Recovery Authority (GOVERNANCE DECISION)

**Problem:** No governance pathway exists for emergency runtime intervention when a governance-blocking failure (corrupted config version, inaccessible warehouse, compliance hold incorrectly blocking an entire cohort) prevents all orchestration loops from running.

**Impact:** A governance-blocking failure with no fast-path recovery could halt all student outreach indefinitely.

**Classification:** Governance decision. Mirrors UE-OWN1 (Emergency Override Authority) at the runtime level. Resolution of UE-OWN1 must also address the runtime recovery authority pathway.

---

## 16. DOWNSTREAM GOVERNANCE

---

### 16.1 Child Document Governance

`runtime/system_loop.md` is the authoritative parent runtime contract. The following child documents describe operational sequencing detail and must not conflict with this document:

| Child document | Governed by sections | Required updates |
|---|---|---|
| `runtime/daily_outreach_flow.md` | §4.1, §5, §6, §3.1 | Must remove direct execution semantics (GHL payload dispatch, "Send payload to GHL"); must replace with orchestration intent delegation model; parent contract governs |
| `runtime/retry_cycle_flow.md` | §4.2, §6, §8.3 | Must remove hardcoded MAX_ATTEMPTS, hardcoded CALL→SMS→EMAIL channel progression, and direct GHL dispatch semantics; must reference Config V2 Group A retry thresholds; parent contract governs |
| `runtime/scheduler_design.md` | §4.1–4.10 trigger conditions, §10.5, §3.2 | Must govern trigger timing via Config V2 Group A; must remove hardcoded "6:00 PM CST" as a specification value (reference Config V2 variable instead); parent contract governs |

Where child documents contain semantics that contradict this parent contract, this document governs.

---

### 16.2 Upstream Directive Dependencies

| Directive | Runtime dependency |
|---|---|
| `directives/outreach_eligibility_rules.md` | `EligibilityAssessment` consumed by §4.1, §5.3 |
| `directives/outreach_retry_policy.md` | `RetryPolicyAssessment` consumed by §4.2, §6 |
| `directives/core_decision_engine.md` | `OrchestrationIntent` consumed by §4.1, §5.3 |
| `directives/channel_selection_rules.md` | `ChannelSelectionAssessment` consumed by §4.1, §5.3 |
| `directives/escalation_rules.md` | `EscalationOrchestrationAssessment` consumed by §4.3 |
| `directives/llm_processing_contract.md` | `AIAssessment` consumed by §4.4, §9 |
| `directives/ghl_integration_contract.md` | `ProviderOrchestrationAssessment` consumed by §4.1, §4.2, §8 |
| `directives/agent_ownership_matrix.md` | Authority domain definitions consumed by §3.2, §7.2 |

---

### 16.3 Upstream Spec Dependencies

| Specification | Runtime sections governed |
|---|---|
| `spec/01_requirements.md` §12 (Config V2 Governance Catalog) | §6.1 (retry thresholds), §5.2 (precondition gate), §4.1–4.10 (trigger conditions) |
| `spec/03_state_transition_rules.md` | §4.1–4.2 (state-based candidate filtering), §6.2 (retry preconditions) |
| `spec/04_idempotency_concurrency.md` | §11.5 (idempotency keys per loop), §6.2 (retry dedup), §10.2 (duplicate handling) |
| `spec/05_external_integrations.md` | §8 (provider governance), §7.2 (replay suppression) |
| `spec/06_observability_operations.md` | §11 (runtime observability), §4.1–4.10 (observability requirements) |
| `spec/07_api_contracts.md` | §5.4 (intent delegation API boundaries) |
| `spec/08_data_model.md` | §4.5, §4.6 (warehouse domains), §4.7 (sync loop) |
| `spec/09_warehouse_physical_architecture.md` | §4.5, §4.6, §7 (warehouse write authority), §8.2 (sync governance) |

---

## 17. REFERENCES

---

**Parent contracts (this document governs):**
* `runtime/daily_outreach_flow.md`
* `runtime/retry_cycle_flow.md`
* `runtime/scheduler_design.md`

**Directive contracts (this document consumes):**
* `directives/outreach_eligibility_rules.md`
* `directives/outreach_retry_policy.md`
* `directives/core_decision_engine.md`
* `directives/channel_selection_rules.md`
* `directives/escalation_rules.md`
* `directives/llm_processing_contract.md`
* `directives/ghl_integration_contract.md`
* `directives/agent_ownership_matrix.md`

**Specification contracts:**
* `spec/01_requirements.md` (Config V2 Governance Catalog §12)
* `spec/03_state_transition_rules.md`
* `spec/04_idempotency_concurrency.md`
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
