# runtime/retry_cycle_flow.md

---

## LAYER 7 — RUNTIME (GOVERNANCE-SAFE RETRY ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `spec/01_requirements.md` through `spec/09_warehouse_physical_architecture.md` and all seven governance-safe directives. The previous version described MVP-era hardcoded retry execution documentation: a direct execution sequence with `contact_attempt < MAX_ATTEMPTS` entry condition, hardcoded CALL→SMS→EMAIL channel progression ("Attempt 1 → CALL / Attempt 2 → SMS / Attempt 3 → EMAIL"), hardcoded retry timeline ("Day 1 (6 PM) → Attempt 1 / Day 2 (6 PM) → Attempt 2 / Day 3 (6 PM) → Attempt 3"), "Trigger GHL with updated attempt count" in Step 7, `contact_attempt += 1` direct state mutation, and generic "Retry immediately once" fallback failure handling. That architecture is incompatible with the governance-safe orchestration model. Retry orchestration flow is no longer direct retry execution. It is governance-safe retry orchestration lifecycle coordination — deterministic retry-cycle sequencing with replay-safe retry governance and observable retry attribution continuity. This document is governed by `runtime/system_loop.md`, `runtime/scheduler_design.md`, and `runtime/daily_outreach_flow.md`.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Retry Orchestration Architecture** defines:

* How retry orchestration evaluation cycles are sequenced, governed, and made historically explainable
* What retry orchestration execution domains exist and how each domain coordinates governance-safe retry candidacy assessment, retry intent production, and execution delegation
* How SHADOW-vs-LIVE execution mode restrictions apply to every domain within the retry orchestration flow
* How replay orchestration simulates historical retry decisions without generating LIVE effects
* How provider governance boundaries are maintained during retry orchestration
* How AI advisory governance applies during retry candidate evaluation
* How degradation is deterministic, observable, and never silently swallowed within a retry cycle
* How the full retry orchestration lineage chain enables forensic reconstruction of any retry decision
* How retry thresholds, cadences, and termination conditions are governed by Config V2 — not by hardcoded values

This document is a **child runtime contract** governed by:

* `runtime/system_loop.md` — the authoritative parent runtime contract (§4.2, §6, §8.3, §3.1)
* `runtime/scheduler_design.md` — retry scheduler trigger semantics in §4.2 govern when retry cycles are coordinated
* `runtime/daily_outreach_flow.md` — retry orchestration coordination (§4.4 of daily flow) is the daily-cycle entry point; this document describes the operational sequencing detail within the Retry Orchestration Loop (`system_loop.md` §4.2)

Where this document conflicts with parent contract semantics, the parent contracts govern.

---

### 1.2 What Retry Orchestration Flow Is NOT

In the governance-safe orchestration model, retry orchestration flow is explicitly **NOT**:

* **Direct retry execution flow** — retry orchestration does not trigger GHL, does not send SMS or email, does not increment attempt counts; it coordinates governance-safe retry intent generation and execution delegation
* **Hardcoded retry progression** — the channel sequence CALL→SMS→EMAIL is not a fixed retry progression; channel selection is a fresh assessment per attempt governed by `channel_selection_rules.md`; no hardcoded channel advancement is permitted (AP-RF2)
* **Hardcoded attempt counter** — `MAX_ATTEMPTS` is not a hardcoded constant; retry exhaustion is governed by Config V2 Group A `outreach_max_retry_attempts`; no hardcoded count is embedded in retry orchestration governance (AP-RF3)
* **Direct state mutation flow** — `contact_attempt += 1` is not a retry orchestration responsibility; state write authority is externalized to the state management service (AP-RF7)
* **Provider dispatch flow** — no step in retry orchestration constructs a GHL API payload, an SMS message body, an email template, or a meeting booking request; all provider dispatch is delegated to provider orchestration services under governance authorization (AP-RF1)
* **Silent fallback execution** — "Retry immediately once" is not a permitted failure response; every failure path is deterministic, observable, and governed (AP-RF4)
* **A replay-unaware flow** — retry orchestration must be historically reproducible; every retry decision must be traceable through an immutable attribution chain linked to the prior orchestration intent

Explicitly prohibited in retry orchestration flow:

* Direct provider execution (AP-RF1)
* Direct GHL dispatch (AP-RF1, AP-RF2)
* Hardcoded channel progression (AP-RF2)
* Hardcoded retry attempt thresholds (AP-RF3)
* Replay-triggered LIVE retry effects (AP-RF4 by reference to AP-RT2)
* Hidden retry fallback execution (AP-RF5)
* Non-attributable retry orchestration actions (AP-RF6)
* Direct state mutation by the retry orchestration loop (AP-RF7)

---

### 1.3 Retry Orchestration Governance Layer Definition

Retry orchestration coordination sits at the sequencing boundary between:

* The **scheduler orchestration layer** (`runtime/scheduler_design.md` §4.2) — provides the governance-safe trigger, `cycle_id`, and `execution_mode` that initiate each retry cycle
* The **daily orchestration flow** (`runtime/daily_outreach_flow.md` §4.4) — the Retry Orchestration Coordination domain coordinates retry policy assessment within the daily cycle; retry_cycle_flow.md describes the detailed sequencing this coordination entails
* The **directive layer** (`directives/outreach_retry_policy.md`, `directives/channel_selection_rules.md`, and others) — produces advisory assessments, retry candidacy signals, and governance constraints consumed by the retry orchestration sequence
* The **execution layer** (orchestration services in `backend/src/services/`) — validates and executes under governance authorization; receives retry intents delegated by the retry orchestration loop
* The **provider layer** (GHL and other external systems) — executes operational delivery under provider orchestration assessment governance; never owned by retry orchestration

| Layer | Retry orchestration relationship |
|---|---|
| Scheduler layer | Provides `cycle_id`, `triggered_at`, `execution_mode`, `config_version_id`; retry flow inherits all attribution from scheduler trigger |
| Daily flow | Coordinates retry candidacy assessment in §4.4; retry_cycle_flow.md describes the governed detail |
| Directive layer | Produces `RetryPolicyAssessment`, `EligibilityAssessment`, `OrchestrationIntent`, `ChannelSelectionAssessment`, `EscalationOrchestrationAssessment`, `AIAssessment`, `ProviderOrchestrationAssessment`; retry flow consumes these in governance-defined order |
| Orchestration services | Receive delegated retry intents; own execution authorization; retry flow never owns execution path |
| Provider layer | Execute delivery; governed by `ghl_integration_contract.md`; retry flow never owns this path |
| Warehousing layer | Append-only persistence; retry flow triggers writes via designated service accounts only |

---

## 2. RETRY ORCHESTRATION MODEL

---

### 2.1 Governance-Safe Retry Sequencing Principle

Every retry orchestration cycle must satisfy the following invariants before candidate evaluation begins:

1. **Scheduler-triggered** — the retry cycle is initiated by the Retry Orchestration Scheduler (`scheduler_design.md` §4.2) with a governance-authorized `cycle_id` and `execution_mode`; no ad-hoc self-triggering by the retry flow
2. **Config V2-governed** — retry timing windows, maximum attempt counts, and channel cadences are governed by Config V2 Group A variables; no hardcoded threshold exists in this document (AP-RF3, AP-RF8)
3. **Preconditioned** — a valid ACTIVE config version, a valid `execution_mode`, and a valid `correlation_id` must exist before any retry candidate is evaluated (inherited from `system_loop.md` §5.2)
4. **Intent-delegated** — the retry orchestration flow produces `OrchestrationIntent` records with `intent_type = RETRY_OUTREACH`; it does not execute retry actions directly (AP-RF1)
5. **Attribution-continuous** — a `correlation_id` propagated from the scheduler trigger flows through every directive evaluation, execution service call, provider interaction, and log record within the retry cycle; a `causation_id` links each retry intent to the prior `OrchestrationIntent` for that student (AP-RF6)
6. **Replay-safe** — every retry decision must be historically reproducible; no retry orchestration action may depend on mutable in-process state unavailable in replay context
7. **Idempotent** — re-running the same retry cycle for the same inputs must produce the same end state, with no duplicate retry dispatch

---

### 2.2 Three-Tier Retry Orchestration Architecture

```
Scheduler Trigger (cycle_id, execution_mode, config_version_id)
  ↓
Directive Layer  →  Retry Candidacy / Advisory Assessment Generation
  ↓
Orchestration Services  →  Governance-Authorized Retry Execution Delegation
  ↓
Provider Layer  →  Operational Delivery (never owned by retry flow)
```

The retry orchestration flow coordinates the first two tiers and delegates to the third. It does not collapse tiers. A retry flow step that calls a provider API directly is a specification violation (AP-RF1). A retry flow step that re-implements directive logic is a specification violation (AP-RF9).

---

### 2.3 Directive Assessment Outputs Consumed by Retry Orchestration

| Directive | Structured output consumed | Consumed at step |
|---|---|---|
| `outreach_retry_policy.md` | `RetryPolicyAssessment` — RETRY_AUTHORIZED/RETRY_BLOCKED/RETRY_EXHAUSTED/RETRY_PENDING | §4.3 Retry Eligibility Coordination |
| `outreach_eligibility_rules.md` | `EligibilityAssessment` — eligibility re-check for retry window candidates | §4.3 Retry Eligibility Coordination |
| `channel_selection_rules.md` | `ChannelSelectionAssessment` — fresh channel assessment per retry attempt; not a progression lookup | §5.3 Canonical Sequence (Channel Selection step) |
| `core_decision_engine.md` | `OrchestrationIntent` — RETRY_OUTREACH/ESCALATE/CLOSE/HOLD | §5.3 Canonical Sequence (Decision Engine step) |
| `escalation_rules.md` | `EscalationOrchestrationAssessment` — escalation_candidate, escalation_type, escalation_severity | §4.5 Escalation Coordination |
| `llm_processing_contract.md` | `AIAssessment` — ai_governance_tier, advisory_scope, advisory_content | §4.6 AI Enrichment Coordination |
| `ghl_integration_contract.md` | `ProviderOrchestrationAssessment` — governance_scope, provider_event_type | §5.3 Canonical Sequence (Provider Assessment step) |

Retry orchestration consumes these outputs in governance-defined order (§5.3). It does not re-implement directive logic (AP-RF9).

---

### 2.4 Retry Orchestration Layer Responsibilities

| Responsibility | Retry orchestration owns | Retry orchestration does NOT own |
|---|---|---|
| Consuming scheduler trigger attribution | Yes | Defining retry trigger cadence (Config V2 owns) |
| Validating governance preconditions | Yes | Evaluating retry eligibility logic (directives own) |
| Propagating `correlation_id` and `causation_id` | Yes | Generating idempotency keys for directive evaluations |
| Coordinating retry intent delegation to services | Yes | Executing retry dispatch (orchestration services own) |
| Consuming provider orchestration assessments | Yes | Making provider API calls (provider orchestration services own) |
| Coordinating replay retry cycle sequencing | Yes | Generating live inferences during replay (AP-RT2) |
| Emitting retry cycle-level observability records | Yes | Implementing AI confidence scoring |
| Identifying retry-window-elapsed candidates | Yes | Writing state transitions for those candidates (state management service owns) |

---

## 3. RUNTIME MODES GOVERNING RETRY ORCHESTRATION

---

### 3.1 Mode Inheritance from Parent Contract

Retry orchestration inherits all six runtime mode definitions from `system_loop.md` §3.1. This section summarizes mode behavior as it applies to the retry orchestration flow. For authoritative mode definitions, see `system_loop.md` §3.

| Mode | Retry orchestration behavior |
|---|---|
| **LIVE** | Full retry candidate evaluation; retry intents produced with `governance_scope = AUTHORIZED`; delegation to outreach orchestration service when `ProviderOrchestrationAssessment.governance_scope = AUTHORIZED`; all retry domains active |
| **SHADOW** | Full retry candidate evaluation; all retry intents produced with `governance_scope = SHADOW_ONLY`; no LIVE outbound dispatch delegated; all outcomes tagged `execution_mode = SHADOW` |
| **REPLAY** | Historical retry simulation only; SHADOW-only outputs; no LIVE dispatch, no LIVE AI inference, no state transitions; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` |
| **REGENERATION** | Not applicable to retry orchestration flow; regeneration is a Report Generation Loop concern (`system_loop.md` §4.6) |
| **DEGRADED** | Non-dispatch retry domains continue; retry dispatch blocked when provider unavailable; AI scope restricted when AI unavailable; all degradation states observable |
| **MAINTENANCE** | All retry orchestration evaluation suspended; no retry candidate evaluation; no retry intent production |

---

### 3.2 Mode Enforcement in Retry Orchestration

Every step in the retry orchestration flow checks execution mode before producing outputs. A step that produces LIVE outputs without checking execution mode is a specification violation. Mode checking is not optional or deferred — it is the second precondition after config version validation.

* **LIVE mode** — `OrchestrationIntent.governance_scope = AUTHORIZED`; full delegation path active
* **SHADOW mode** — `OrchestrationIntent.governance_scope = SHADOW_ONLY`; delegation produces no outbound dispatch
* **REPLAY mode** — all outputs carry `execution_type = replay`; no LIVE path is reachable (AP-RF4, AP-RT2)
* **DEGRADED mode** — outputs carry `DEGRADED` annotation; blocked domains depend on degradation cause (§10.2)
* **MAINTENANCE mode** — retry cycle does not start; scheduler trigger is suppressed (`scheduler_design.md` §3.1)

---

## 4. RETRY ORCHESTRATION EXECUTION DOMAINS

---

The retry orchestration flow is organized into ten coordination domains. Each domain maps to a specific governance responsibility within the retry evaluation cycle. Domains are sequenced deterministically (§5.3). No domain may be skipped. No domain may produce direct provider execution output.

---

### 4.1 Retry Candidate Loading Orchestration

| Attribute | Specification |
|---|---|
| **Purpose** | Identify students in `NO_RESPONSE` state whose retry window has elapsed per `outreach_retry_window_days` from Config V2 Group A; load candidate records from `student_trigger_data` annotated with `contact_attempt` count; apply pre-evaluation filter to exclude structurally invalid records |
| **Replay behavior** | Sources candidate records from stored `student_trigger_data` snapshot at historical timestamp; no SQL Server re-sync occurs during replay; historical `contact_attempt` count sourced from `state_transition_log` |
| **SHADOW behavior** | Candidate loading proceeds normally; loaded retry candidates evaluated with SHADOW-only output restriction |
| **LIVE behavior** | Retry candidate records loaded from current `student_trigger_data`; `NO_RESPONSE` state verified with state management service; retry window elapsed check uses `outreach_retry_window_days` from ACTIVE config version |
| **Attribution requirements** | `sync_cycle_id` annotated on each candidate record; `contact_attempt` count annotated per candidate from `state_transition_log` (read-only) |
| **Observability requirements** | Structured log: `retry_candidates_loaded`, `pre_filter_exclusions`, `load_duration_ms`, `window_elapsed_count` |
| **Idempotency guarantees** | Candidate loading is read-only; re-running produces the same candidate set given the same `student_trigger_data` and `state_transition_log` state |

---

### 4.2 Governance Precondition Validation

| Attribute | Specification |
|---|---|
| **Purpose** | Validate all governance preconditions required before any retry candidate evaluation begins; inherited from `system_loop.md` §5.2; this domain is the gate that must pass before proceeding to §4.3 |
| **Replay behavior** | Precondition validation uses `historical_config_version_id`; execution mode check validates `execution_type = replay` |
| **SHADOW behavior** | Full precondition validation applies; SHADOW mode does not relax preconditions |
| **LIVE behavior** | All preconditions must be satisfied; failure at any precondition stops the retry cycle with structured error emission |
| **Attribution requirements** | `config_version_id`, `execution_mode`, `correlation_id` all validated; their values propagated to every subsequent domain |
| **Observability requirements** | Precondition failure produces structured log: `PRECONDITION_FAILED_{CAUSE}`, `failed_precondition_field`, `correlation_id` |
| **Idempotency guarantees** | Precondition validation is stateless; re-running produces same outcome given same system state |

Preconditions required (inherited from `system_loop.md` §5.2):

| Precondition | Required value | Failure behavior |
|---|---|---|
| `config_version_id` | Non-null ACTIVE config version | Retry cycle stops; `PRECONDITION_FAILED_NO_ACTIVE_CONFIG` emitted; escalation candidacy generated |
| `execution_mode` | `SHADOW` or `LIVE` (or `REPLAY` for replay context) | Retry cycle stops; structured error emitted |
| `correlation_id` | UUID v4 generated for this retry cycle | Retry cycle stops |
| Config V2 threshold resolution | `outreach_max_retry_attempts`, `outreach_retry_window_days` from Group A resolvable | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning; cycle continues with DEGRADED annotation |
| SQL Server data age | `sync_lag_hours ≤ sql_server_max_sync_age_hours` (Config V2 Group K) | Cycle continues with `STALE_SQL_SERVER_DATA` annotation; not blocking |

---

### 4.3 Retry Eligibility Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate retry policy assessment for each loaded candidate via `outreach_retry_policy.md`; produce `RetryPolicyAssessment` records; apply eligibility re-check via `outreach_eligibility_rules.md`; exclude ineligible or retry-exhausted students from further evaluation |
| **Replay behavior** | Retry policy evaluated under `historical_config_version_id`; thresholds (`outreach_max_retry_attempts`, `outreach_retry_window_days`) resolved from historical config version; `RetryPolicyAssessment` produced with `governance_scope = REPLAY_ONLY` |
| **SHADOW behavior** | Full retry eligibility evaluation; `RetryPolicyAssessment.governance_scope = SHADOW_ONLY` |
| **LIVE behavior** | Full retry eligibility evaluation; `RETRY_AUTHORIZED` students advance to decision engine; `RETRY_BLOCKED` students produce skip records; `RETRY_EXHAUSTED` students produce escalation candidacy |
| **Attribution requirements** | `correlation_id` propagated to every `RetryPolicyAssessment` record; `config_version_id` recorded in each assessment; `contact_attempt` annotated on assessment |
| **Observability requirements** | Per-cycle log: `retry_candidates_evaluated`, `retry_authorized_count`, `retry_blocked_count`, `retry_exhausted_count`, `retry_pending_count`, `skip_reason_distribution` |
| **Idempotency guarantees** | Retry eligibility assessment keyed on `(student_id, checkpoint_type, contact_attempt)` per `system_loop.md` §11.5; re-evaluating same student in same cycle with same config produces same assessment |

---

### 4.4 Retry Cadence Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Validate that the retry cadence for each candidate conforms to `outreach_retry_window_days` from Config V2 Group A; ensure the elapsed-window check uses the Config V2-governed threshold; prohibit premature retry dispatch |
| **Replay behavior** | Cadence validation uses `outreach_retry_window_days` from `historical_config_version_id`; produces cadence annotation in replay diagnostic record |
| **SHADOW behavior** | Full cadence validation applies; premature retry suppressed in SHADOW mode as in LIVE mode |
| **LIVE behavior** | `last_contact_at` sourced from `state_transition_log`; elapsed duration compared to `outreach_retry_window_days`; students not yet past window produce `RETRY_PENDING` assessment and are excluded from this cycle |
| **Attribution requirements** | `retry_window_days_applied` (from ACTIVE config version) annotated on each assessment; `last_contact_at` timestamp annotated |
| **Observability requirements** | Per-cycle log: `retry_window_not_elapsed_count`, `retry_window_elapsed_count`, `retry_window_days_config_value` |
| **Idempotency guarantees** | Cadence validation is read-only; no side effects; re-running produces same outcome given same state |

---

### 4.5 Escalation Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate escalation candidacy assessment for retry-exhausted students and students meeting escalation criteria per `escalation_rules.md`; produce `EscalationOrchestrationAssessment` records; route candidacy signals to escalation routing service |
| **Replay behavior** | Escalation candidacy assessed under `historical_config_version_id`; outputs carry `REPLAY_ESCALATION_CANDIDATE` scope; no live routing |
| **SHADOW behavior** | Escalation candidacy assessed and logged; no live operator routing |
| **LIVE behavior** | `EscalationOrchestrationAssessment` records with `escalation_candidate = true` delegated to escalation routing service; routing is advisory — human acknowledgement required |
| **Attribution requirements** | `causation_id` linked to the `OrchestrationIntent` that triggered the retry sequence; escalation record contains originating `intent_id` and `contact_attempt` count |
| **Observability requirements** | Per-cycle log: `escalation_candidates_evaluated`, `retry_exhausted_escalations`, `candidacy_produced_count`, `escalation_types_distribution` |
| **Idempotency guarantees** | Keyed on `(student_id, escalation_type, cycle_date)` per `system_loop.md` §11.5; duplicate signal within same cycle suppressed |

---

### 4.6 AI Enrichment Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate AI advisory enrichment for retry candidates; verify AI advisory freshness against `ai_insight_ttl_hours` from Config V2 Group H; consume `AIAssessment` outputs; restrict AI advisory scope based on governance tier |
| **Replay behavior** | No live AI inference; AI content sourced from `warehouse.snapshot_ai_narratives` (FINALIZED) or `ai_insights` table (non-finalized); stale AI in replay returns historical advisory or `UNAVAILABLE` |
| **SHADOW behavior** | AI advisory evaluated; outputs tagged `outcome = shadow_only`; FINALIZED_COPY semantics apply normally |
| **LIVE behavior** | `AIAssessment.advisory_content` informs but does not authorize `OrchestrationIntent` (AP-RF10, AP-RT11); `ai_governance_tier` governs advisory scope |
| **Attribution requirements** | `ai_version_number`, `prompt_version`, `model_used`, `generated_at` captured in assessment record; `correlation_id` propagated |
| **Observability requirements** | Per-cycle log: `stale_ai_count`, `missing_ai_count`, `finalized_copy_count`, `ai_governance_tier_distribution` |
| **Idempotency guarantees** | AI advisory consumption is read-only; enrichment does not mutate `ai_insights` table (AI Refresh Orchestration Loop owns mutations, `system_loop.md` §4.4) |

---

### 4.7 Provider Synchronization Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Validate that Provider Synchronization Loop (`system_loop.md` §4.7) has completed successfully before retry candidate evaluation consumes `student_trigger_data`; assess sync lag against `sql_server_max_sync_age_hours` from Config V2 Group K |
| **Replay behavior** | Replay uses stored `student_trigger_data` snapshot; no SQL Server re-sync validation during replay; `sync_lag_hours` annotation preserved from original cycle records |
| **SHADOW behavior** | Sync validation proceeds normally in all execution modes |
| **LIVE behavior** | Sync completion record verified; `sync_lag_hours` assessed; `STALE_SQL_SERVER_DATA` annotation applied to affected candidates if lag threshold exceeded |
| **Attribution requirements** | `sync_cycle_id` from Provider Synchronization Loop linked to retry orchestration cycle |
| **Observability requirements** | Per-cycle log: `sync_lag_hours`, `stale_threshold_exceeded`, `sync_validation_outcome` |
| **Idempotency guarantees** | Sync validation is read-only; retry flow does not invoke sync directly |

---

### 4.8 Observability Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Emit structured observability records throughout the retry orchestration cycle; ensure every domain completion, every skip, every failure, and every degradation state is observable; never suppress observability even under failure conditions |
| **Replay behavior** | Replay cycles emit full replay diagnostic records in addition to standard observability; all outputs carry `execution_type = replay` tag |
| **SHADOW behavior** | Full observability records required; all outcomes tagged `execution_mode = SHADOW` |
| **LIVE behavior** | Full observability records emitted at cycle completion; PII-free structured logs per AP-RF13 |
| **Attribution requirements** | Every observability record carries `correlation_id`, `cycle_id`, `execution_mode`, `config_version_id` |
| **Observability requirements** | See §11.3 for the full required retry orchestration observability field set |
| **Idempotency guarantees** | Observability records are append-only; idempotency not required for structured log emission |

---

### 4.9 Replay Retry Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate replay mode behavior when the retry orchestration flow runs as a historical simulation; ensure all LIVE retry effects are suppressed; ensure replay diagnostic records are complete |
| **Replay behavior** | This domain IS the active governance domain when `execution_type = replay`; all other domains subordinate to replay suppression rules (§7) |
| **SHADOW behavior** | Replay within SHADOW mode produces SHADOW-only diagnostic outputs; no LIVE effects |
| **LIVE behavior** | Replay Orchestration Scheduler never triggers LIVE retry cycles with `execution_type = replay`; this domain is inactive in normal LIVE operation (AP-RF4, AP-SCH3) |
| **Attribution requirements** | `replay_cycle_id`, `source_artifact_id`, `historical_config_version_id`, `fingerprint_comparison_outcome`, `replay_partial` required |
| **Observability requirements** | Full replay diagnostic set per `system_loop.md` §7.4 |
| **Idempotency guarantees** | Replay idempotency key: `(source_artifact_id, replay_cycle_id)` per `system_loop.md` §11.5 |

---

### 4.10 Degradation Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Govern the retry orchestration flow's behavior when one or more operational components are degraded; ensure degradation is deterministic, observable, and produces escalation candidacy; ensure no domain silently absorbs a degraded state |
| **Replay behavior** | Replay permitted if warehouse accessible and historical config resolvable; replay partial annotation applied when any threshold is UNKNOWN_V0 |
| **SHADOW behavior** | Degradation behavior applies normally in SHADOW mode |
| **LIVE behavior** | Degradation condition table (§10.2) governs which domains continue and which are blocked; every degraded state produces a structured observability record |
| **Attribution requirements** | Degradation records carry `degradation_cause`, `affected_domains`, `degradation_onset_timestamp`, `correlation_id` |
| **Observability requirements** | Degradation structured log required: `degradation_cause`, `affected_domains`, `degradation_onset_timestamp` |
| **Idempotency guarantees** | Degradation coordination does not produce side effects; degradation records are append-only observability records |

---

## 5. CANONICAL RETRY ORCHESTRATION SEQUENCING

---

### 5.1 Sequencing Principles

The canonical retry orchestration governance sequencing is deterministic. The following principles govern its execution:

1. **Precondition gate is mandatory** — config version, execution mode, attribution context validated before any retry candidate evaluation begins (`system_loop.md` §5.2)
2. **Sync completion precedes evaluation** — Provider Synchronization Loop must complete successfully before retry candidate evaluation consumes `student_trigger_data` (`system_loop.md` §5.1)
3. **Retry window check precedes directive evaluation** — cadence validation must precede full directive evaluation; premature retry candidates are excluded before eligibility and policy assessment
4. **Directive evaluation is ordered** — retry policy, eligibility re-check, decision engine, channel selection, escalation directives evaluated in governance-defined order; outputs are structured assessment objects, not action strings
5. **Intent persistence precedes delegation** — `OrchestrationIntent` records written to `student_timeline_events` before any execution delegation; write failure is a cycle failure for that record
6. **Execution delegation is not execution** — retry flow delegates to orchestration services; it does not own the execution path
7. **Observability emission is mandatory** — structured log emitted at cycle completion; never omitted (AP-RT15, AP-RF15)

---

### 5.2 Governance Precondition Gate

Inherited verbatim from `system_loop.md` §5.2. Before any retry candidate evaluation:

| Precondition | Required value | Failure behavior |
|---|---|---|
| `config_version_id` | Non-null ACTIVE config version | Retry cycle does not start; structured error log emitted; escalation candidacy generated |
| `execution_mode` | `SHADOW` or `LIVE` | Retry cycle does not start; structured error log emitted |
| `correlation_id` | UUID v4 generated for this retry cycle | Retry cycle does not start |
| Config V2 threshold resolution | `outreach_max_retry_attempts` and `outreach_retry_window_days` from Group A resolvable | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning; cycle continues with DEGRADED annotation |
| SQL Server data age | `sync_lag_hours ≤ sql_server_max_sync_age_hours` (Config V2 Group K) | Cycle continues with `STALE_SQL_SERVER_DATA` annotation; not blocking |

---

### 5.3 Canonical Retry Orchestration Evaluation Sequence

The governed retry runtime sequencing is:

```
PRECONDITION GATE (§5.2 — config_version_id, execution_mode, correlation_id)
  ↓
PROVIDER SYNC VALIDATION (sql_server_max_sync_age_hours check — §4.7)
  ↓
RETRY CANDIDATE LOADING (NO_RESPONSE candidates from student_trigger_data — §4.1)
  ↓
RETRY WINDOW CADENCE CHECK (outreach_retry_window_days check per candidate — §4.4)
  ↓
RETRY POLICY ASSESSMENT (outreach_retry_policy.md → RetryPolicyAssessment — §4.3)
  ↓
ELIGIBILITY RE-CHECK (outreach_eligibility_rules.md → EligibilityAssessment — §4.3)
  ↓
AI ENRICHMENT COORDINATION (ai_insight_ttl_hours freshness check — §4.6)
  ↓
CORE DECISION ENGINE (core_decision_engine.md → OrchestrationIntent with intent_type = RETRY_OUTREACH — system_loop.md §5.3)
  ↓
CHANNEL SELECTION (channel_selection_rules.md → ChannelSelectionAssessment; fresh per-attempt assessment — system_loop.md §5.3)
  ↓
ESCALATION CANDIDACY ASSESSMENT (escalation_rules.md → EscalationOrchestrationAssessment — §4.5)
  ↓
INTENT RECORD PERSISTENCE (student_timeline_events append with causation_id → prior intent_id — system_loop.md §5.1)
  ↓
EXECUTION DELEGATION (orchestration services, under governance authorization — §5.4)
  ↓
PROVIDER ORCHESTRATION ASSESSMENT (ghl_integration_contract.md → ProviderOrchestrationAssessment)
  ↓
OBSERVABILITY EMISSION (§4.8 — cycle completion record)
```

This sequence is deterministic. No step may be skipped. No step may produce direct execution output that bypasses the next step. No step may produce LIVE output when `execution_mode` is SHADOW or REPLAY. Channel selection at this step is a fresh assessment — not a fixed CALL→SMS→EMAIL advancement (AP-RF2).

---

### 5.4 Intent Delegation Boundaries

| Stage | Owner | Retry flow responsibility |
|---|---|---|
| Advisory generation | Directive layer | Invoke directive evaluation; receive assessment objects |
| Intent validation | Retry orchestration flow | Validate `OrchestrationIntent` carries `intent_type = RETRY_OUTREACH`, is governance-authorized, and `execution_mode` is checked |
| `causation_id` linkage | Retry orchestration flow | Link retry intent to prior `OrchestrationIntent.intent_id` for the student |
| Execution delegation | Orchestration services | Retry flow delegates; does not own execution path |
| Provider dispatch | Provider orchestration services | Retry flow coordinates; does not call GHL directly (AP-RF1, AP-RF2) |
| State persistence | State management service | Retry flow does not write `contact_attempt` increments or state transitions directly (AP-RF7) |
| Observability | Retry orchestration flow | Loop emits structured cycle-level log |

---

## 6. RETRY STATE TRANSITION GOVERNANCE

---

### 6.1 Governance-Safe Retry State Coordination

Retry orchestration does not own state transitions. The V1 pattern:

> `QUEUED → CONTACTED` triggered by "Trigger GHL with updated attempt count" and `contact_attempt += 1`

is replaced with:

> `OrchestrationIntent` with `intent_type = RETRY_OUTREACH` produced by decision engine → delegated to orchestration services → `ProviderOrchestrationAssessment` authorizes dispatch → state management service records transition and increments attempt count

Retry orchestration's role: **coordinate the sequence that produces retry intents; link each intent to its causation lineage; delegate execution; never write state or increment attempt counts directly.**

---

### 6.2 State Transition Authority

| State transition | Authority | Retry flow role |
|---|---|---|
| `NO_RESPONSE` → RETRY candidacy | Retry flow identifies; does not write | Loads candidates; produces `RetryPolicyAssessment` |
| `NO_RESPONSE` → CONTACTED (on retry) | State management service (after confirmed dispatch) | Produces retry intent; does not write transition |
| `CONTACTED` → `NO_RESPONSE` | State management service (after timeout or GHL webhook) | Does not own; retry flow evaluates next cycle |
| `contact_attempt` increment | State management service (after state transition) | Does not write `contact_attempt += 1` directly (AP-RF7) |
| Any state → `INTERVENTION_REQUIRED` (retry exhausted) | State management service (after escalation routing) | Escalation domain (§4.5) produces candidacy signal |
| Any state → `CLOSED` (retry exhausted, no escalation path) | State management service (via decision engine close intent) | Produces close intent only |
| `NO_RESPONSE` → `RESPONDED` | State management service (after inbound GHL webhook) | Does not own; inbound webhook handled by ingestion service |

State transitions are always initiated by governance-authorized intents, never by direct retry loop writes (AP-RF7). Every state transition produces an observable record with `correlation_id` and `causation_id`.

---

### 6.3 Replay-Safe Retry State Semantics

In REPLAY mode:

* Retry orchestration flow produces no state transitions
* Historical state records from `state_transition_log` are the authoritative source for what transitions occurred
* Historical `contact_attempt` count sourced from `state_transition_log` — not from a live counter
* Re-evaluating a historical retry cycle produces a fingerprint comparison between the historical retry decision and the current re-evaluation result
* `fingerprint_comparison_outcome = MATCH | DIVERGENT | UNKNOWN` emitted in replay diagnostic record
* No state write authority exists in replay context (AP-OWN2, AP-RF7)

---

## 7. REPLAY & REGENERATION SEMANTICS

---

### 7.1 Retry Replay Orchestration

When the retry orchestration flow runs in REPLAY mode (`execution_type = replay`), it follows the governed replay lifecycle from `system_loop.md` §7.1:

```
GOVERNANCE AUTHORIZATION (operator-initiated; authorization record written)
  ↓
REPLAY PRECONDITION GATE (source_artifact_id, historical_config_version_id validated)
  ↓
HISTORICAL RETRY CANDIDATE STATE RESOLUTION (NO_RESPONSE state from state_transition_log at historical timestamp)
  ↓
HISTORICAL CONTACT ATTEMPT COUNT RESOLUTION (contact_attempt from state_transition_log)
  ↓
HISTORICAL CONFIG VERSION RESOLUTION (config version at original retry execution time; outreach_max_retry_attempts and outreach_retry_window_days resolved from historical config)
  ↓
DIRECTIVE EVALUATION (retry policy, eligibility, decision, channel directives evaluated under historical config; SHADOW-only outputs)
  ↓
FINGERPRINT COMPARISON (current re-evaluation vs stored historical retry outcome)
  ↓
REPLAY DIAGNOSTIC EMISSION (source_artifact_id, fingerprint_comparison_outcome, replay_partial)
  ↓
NO LIVE EFFECTS PRODUCED
```

---

### 7.2 Replay Suppression Behavior

The following LIVE effects are suppressed in all retry orchestration replay contexts:

| Effect category | Suppression mechanism | Reference |
|---|---|---|
| Outbound GHL retry dispatch | `ProviderOrchestrationAssessment.outbound_suppressed = true` | AP-GHL5; AP-RF4 |
| Live AI inference | `AIAssessment.ai_blocked = true`; FINALIZED_COPY sourced from warehouse | AP-AI5; AP-RF11 |
| Student state transitions (including contact_attempt increment) | Replay Services hold no state write authority | AP-OWN2; AP-RF7 |
| Escalation routing | Escalation outputs carry `REPLAY_ESCALATION_CANDIDATE` scope | AP-RF4 |
| Warehouse mutations | Replay loop reads warehouse; does not write | AP-OWN15 |

---

### 7.3 Regeneration Restrictions

Retry orchestration flow is not involved in report regeneration. Regeneration is a Report Generation Loop concern (`system_loop.md` §4.6, FAD-2). The retry orchestration flow:

* Does not execute in REGENERATION mode
* Does not re-evaluate retry candidates during a regeneration cycle
* Does not access `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives` directly

---

## 8. PROVIDER GOVERNANCE

---

### 8.1 Provider Boundary Principles

Retry orchestration flow never owns provider governance. Inherited from `system_loop.md` §8.1:

* Retry orchestration flow produces `OrchestrationIntent` records with `intent_type = RETRY_OUTREACH`
* Orchestration services evaluate `ProviderOrchestrationAssessment` before delegating to GHL
* If `governance_scope ≠ AUTHORIZED`, no outbound retry dispatch occurs
* No step in retry orchestration may construct a GHL API call, an SMS payload, an email body, or a meeting booking request (AP-RF1, AP-RF2)
* Channel assignment for each retry attempt is produced by `channel_selection_rules.md` assessment — not by a hardcoded CALL→SMS→EMAIL advancement rule (AP-RF2)

---

### 8.2 GHL Retry Integration Governance

The `ghl_integration_contract.md` governs all provider interactions. Retry orchestration flow consumes `ProviderOrchestrationAssessment` and delegates; it does not own:

* GHL API endpoint routing for retry events
* SMS/email/call payload construction for retry attempts
* Outbound retry within provider layer (provider-level retries are distinct from orchestration-level retry cycles)
* Provider circuit breaker state
* Provider delivery confirmation telemetry

All of the above are governed by `ghl_integration_contract.md` RULE 1–6 and consumed by the retry flow as assessment outputs only.

---

### 8.3 Provider Failure Retry Behavior

| Provider failure state | Retry orchestration behavior |
|---|---|
| Circuit breaker OPEN | Outbound retry dispatch blocked; `governance_scope = UNAVAILABLE`; provider failure escalation candidacy generated; non-dispatch domains continue |
| Provider outage active | Same as circuit breaker OPEN |
| Retry budget exhausted via provider outage | Retry attempts blocked by provider outage are not consumed from student retry budget (governed by `outreach_retry_policy.md`); budget protection emitted as annotation |
| Sync lag exceeds threshold | `STALE_SQL_SERVER_DATA` annotation; retry evaluation continues with annotated data |
| `AUTH_FAILURE` | TERMINAL class; no retry; alert escalation; all subsequent provider interactions blocked until key rotation confirmed |

No provider failure results in silent absorption (AP-RF12). Every failure produces an observable audit record and an escalation candidacy signal (AP-RT6).

---

## 9. AI GOVERNANCE

---

### 9.1 Advisory-Only Retry Principle

AI advisory outputs are consumed by the retry orchestration flow, not obeyed. Inherited from `system_loop.md` §9.1:

* `AIAssessment.advisory_content.recommended_intervention` informs but does not authorize `OrchestrationIntent` with `intent_type = RETRY_OUTREACH`
* `AIAssessment.confidence_metadata.confidence_score` governs advisory scope (FULL/LIMITED/UNAVAILABLE) but does not override rule-based retry eligibility
* No step in the retry orchestration flow may produce an `OrchestrationIntent` from AI advisory output alone (AP-RF10, AP-RT11)

---

### 9.2 Stale AI Retry Restrictions

| AI governance tier | Retry orchestration behavior |
|---|---|
| CONFIDENT (≥ 0.70, within TTL) | Full advisory scope; may elevate escalation severity in LIVE retry mode |
| ADVISORY (< 0.70 or approaching TTL) | Limited advisory scope; may not independently drive LIVE escalation from retry |
| STALE (beyond `ai_insight_ttl_hours`) | Advisory scope limited; LIVE escalation from AI advisory blocked for retry candidates; rule-based evaluation only |
| IN_FLIGHT | Prior version served if available; DEFERRED advisory scope; retry cycle proceeds without waiting |
| UNAVAILABLE (null insight) | Rule-based evaluation only; retry cycle not blocked |

Stale AI does not block the retry orchestration cycle. It restricts advisory scope and escalation authority only.

---

### 9.3 FINALIZED_COPY Retry Semantics

Once AI text is physically copied to `warehouse.snapshot_ai_narratives` at FINALIZED state (FAD-1):

* The retry orchestration flow does not re-request AI evaluation for this content
* Replay reads this content directly — no live AI inference triggered
* `ai_governance_tier = FINALIZED_COPY` overrides all staleness assessments in retry evaluation
* No step in retry orchestration may trigger mutation of `warehouse.snapshot_ai_narratives` (AP-OWN15, AP-RF11)

---

## 10. FAILURE & DEGRADATION GOVERNANCE

---

### 10.1 Deterministic Degradation Principles

Degradation in retry orchestration is observable, not silent. Inherited from `system_loop.md` §10.1:

Every degraded retry orchestration state must:

* Emit a structured log entry with `degradation_cause`, `affected_domains`, and `outcome = partial` or `outcome = failure`
* Produce an escalation candidacy signal for human awareness
* Describe what domains continued and what domains were blocked
* Never silently swallow a failure or substitute a silent default (AP-RF12)

Explicitly prohibited patterns:

* Generic "Retry immediately once" failure response without observable cause classification (replaces V1 §8 fallback)
* Silent skip of a failed retry candidate without structured error record (AP-RT5)
* Swallowing provider failure without audit record (AP-RT6)
* Retrying without an upper bound from Config V2 `outreach_max_retry_attempts` (AP-RF3)
* Assuming a hardcoded fallback when Config V2 threshold is missing (AP-RF8)

---

### 10.2 Retry Degradation Condition Table

| Condition | Affected retry domains | Retry flow behavior | Orchestration continues | Observability required |
|---|---|---|---|---|
| Provider circuit breaker OPEN | §4.1 (dispatch delegation), §5.3 (execution delegation) | Outbound retry dispatch blocked; `governance_scope = UNAVAILABLE` | Yes (eligibility, AI, cadence check, escalation) | `CIRCUIT_BREAKER_OPEN` event; provider failure escalation candidacy |
| Provider outage active | §4.1, §5.3 | Same as circuit open | Yes | `PROVIDER_OUTAGE` event; degradation onset record |
| AI provider unavailable | §4.6 | AI enrichment blocked; rule-based retry evaluation only | Yes | `AI_PROVIDER_UNAVAILABLE` event; stale AI annotation |
| SQL Server sync lag exceeded | §4.7, §4.1 | `STALE_SQL_SERVER_DATA` annotation; retry evaluation continues | Yes | `SYNC_LAG_EXCEEDED` event |
| SQL Server connection failed | §4.7 | Sync validation blocked; last successful sync data used | Yes (with stale annotation) | `SQL_SERVER_UNAVAILABLE` event; escalation candidacy |
| Config threshold missing (`outreach_max_retry_attempts`) | §4.3 | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_OUTREACH_MAX_RETRY_ATTEMPTS` warning; DEGRADED annotation | Yes (annotated) | `CONFIG_THRESHOLD_MISSING` warning |
| Config threshold missing (`outreach_retry_window_days`) | §4.4 | `UNKNOWN_V0` substituted; cadence check uses UNKNOWN_V0; DEGRADED annotation | Yes (annotated) | `CONFIG_THRESHOLD_MISSING` warning |
| Duplicate retry event storm | Inbound webhook coordination | Deduplication gate absorbs; `DUPLICATE_SUPPRESSED` scope | Yes | `DUPLICATE_EVENT_STORM` event; dedup count emitted |
| Compliance hold (individual student) | §4.3, §5.3 dispatch | Retry dispatch blocked for that student; others unaffected | Yes | `COMPLIANCE_HOLD_DISPATCH_BLOCKED` per student |
| Warehouse write failure | Intent persistence (§5.3) | Cycle fails for affected record; structured failure log; dead-letter for retry | No (for that record) | `WAREHOUSE_WRITE_FAILURE` event; recovery path documented |
| Retry starvation (all candidates `RETRY_PENDING`) | §4.4 | No dispatch produced this cycle; structured log emitted; escalation candidacy if starvation persists | Yes | `RETRY_STARVATION_DETECTED` event; starvation count emitted |

---

### 10.3 Provider Outage Retry Behavior

When a provider outage is detected during a retry orchestration cycle:

* **Outbound dispatch** — blocked for all retry candidates in the cycle; `governance_scope = UNAVAILABLE`; escalation candidacy generated
* **Inbound webhook ingestion** — continues normally; webhooks ingested and attributed; no state transitions without governance authorization
* **SQL Server reads** — unaffected; sync loop continues
* **AI evaluation** — unaffected
* **Retry budget protection** — retry attempts blocked by provider outage are not consumed from student retry budget (governed by `outreach_retry_policy.md`); `provider_outage_exempted = true` annotation applied to the blocked attempt record

---

### 10.4 AI Outage Retry Behavior

When the AI provider is unavailable:

* **AI enrichment coordination** — blocked for new requests; circuit breaker state updated
* **Retry candidate evaluation** — proceeds with rule-based evaluation only; AI advisory scope = UNAVAILABLE
* **FINALIZED_COPY records** — unaffected; sourced from warehouse regardless of AI provider state
* **Escalation candidacy** — rule-based severity assessment applies; AI may not elevate without advisory content
* **Retry intent production** — not blocked; rule-based `RetryPolicyAssessment` governs retry authorization

---

### 10.5 Retry Starvation Governance

Retry starvation occurs when all retry candidates in a cycle have `RETRY_PENDING` status (retry window has not yet elapsed for any candidate). This is a normal state, not a failure:

* Retry orchestration cycle completes normally with zero dispatch authorized
* Structured completion log emitted: `outcome = shadow_only` (SHADOW) or `outcome = success` (LIVE with zero dispatch) with `retry_starvation_flag = true`
* Persistent starvation (multiple consecutive cycles with zero dispatch) generates an escalation candidacy signal after a governance-defined consecutive-cycle threshold (Config V2 Group A, UE-RF3)
* Starvation does not cause the retry cycle to skip its precondition gate or reduce observability

---

## 11. ATTRIBUTION & OBSERVABILITY

---

### 11.1 Retry Orchestration Attribution Lineage

The full attribution lineage chain for any retry outreach event:

```
Scheduler Trigger  →  cycle_id + triggered_at (scheduler_design.md §4.2)
  ↓
Config V2 Retry Governance  →  outreach_retry_window_days + outreach_max_retry_attempts (Group A)
  ↓
Retry Orchestration Loop  →  correlation_id + config_version_id + execution_mode
  ↓
Prior OrchestrationIntent  →  causation_id (prior intent_id from initial or previous retry)
  ↓
Retry OrchestrationIntent  →  intent_id + causation_id + contact_attempt + correlation_id
  ↓
ProviderOrchestrationAssessment  →  governance_scope + correlation_id
  ↓
processed_events  →  idempotency_key (student_id, checkpoint_type, contact_attempt) + correlation_id
  ↓
ghl_messages  →  ghl_message_id + correlation_id
```

Every link in this chain is required. A missing link is an attribution defect (AP-RF6, AP-RT4, spec/06). The `causation_id` linking each retry intent to its prior intent is what distinguishes retry orchestration attribution from initial outreach attribution.

---

### 11.2 Retry Attribution Requirements

Every retry orchestration record must carry (inherited from `system_loop.md` §11.2):

| Field | Required in |
|---|---|
| `correlation_id` | All records in every domain |
| `causation_id` | All retry intent records; links to prior `OrchestrationIntent.intent_id` for the student |
| `contact_attempt` | All retry intent records; sourced from `state_transition_log`; never written by retry flow |
| `config_version_id` | All orchestration evaluation records |
| `execution_mode` | All records |
| `execution_type` | All records (`original`, `replay`, `regeneration`, `recovery`) |
| `loop_name` | Structured log entries |
| `actor_identity` | Human-initiated actions; `system` for automated loops |
| `attribution_timestamp` | All records |

---

### 11.3 Retry Orchestration Observability Fields

Every retry orchestration cycle emits a structured JSON record to stdout upon completion:

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "retry_orchestration",
  "event": "loop_cycle_complete",
  "loop_name": "retry_orchestration_loop",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | REPLAY | DEGRADED | MAINTENANCE",
  "execution_type": "original | replay | regeneration | recovery",
  "config_version_id": "string | null",
  "outreach_max_retry_attempts_applied": 0,
  "outreach_retry_window_days_applied": 0,
  "duration_ms": 0,
  "outcome": "success | failure | partial | shadow_only",
  "retry_candidates_loaded": 0,
  "retry_window_elapsed_count": 0,
  "retry_window_not_elapsed_count": 0,
  "retry_authorized_count": 0,
  "retry_blocked_count": 0,
  "retry_exhausted_count": 0,
  "retry_intents_produced": 0,
  "escalation_candidacy_produced": 0,
  "dispatch_authorized": 0,
  "dispatch_blocked_unavailable": 0,
  "retry_starvation_flag": false,
  "degradation_flags": [],
  "config_threshold_missing_keys": []
}
```

PII (student name, email, phone, transcript content) must not appear in retry orchestration observability records (AP-RF13, AP-RT13).

---

### 11.4 Correlation and Causation Propagation

`correlation_id` and `causation_id` propagation rules in retry orchestration:

* `correlation_id` generated at the start of every retry orchestration cycle (or inherited from the daily cycle if co-triggered)
* `correlation_id` propagates through every directive evaluation, execution service call, provider assessment, and log record within the retry cycle
* `causation_id` set to the prior `OrchestrationIntent.intent_id` for the student — the intent that resulted in the `NO_RESPONSE` state being evaluated for retry
* Both IDs persisted in every `OrchestrationIntent` record, every `state_transition_log` record, every `processed_events` record, and every structured log entry within the cycle

A retry failure that cannot be traced from symptom to root cause using `correlation_id` and then back to the original outreach decision using `causation_id` is an observability defect (spec/06).

---

## 12. ARCHITECTURE PRESERVATION RULES

---

The following rules are MUST NOT prohibitions. Violation of any rule is a specification defect.

| Rule | Prohibition |
|---|---|
| **AP-RF1** | MUST NOT allow any step in retry orchestration to directly call a provider API (GHL, AI provider, SMS, email, meeting booking); all provider interactions are delegated to governance-authorized orchestration services via `ghl_integration_contract.md` and `llm_processing_contract.md` boundaries |
| **AP-RF2** | MUST NOT allow retry orchestration to apply a hardcoded channel progression (CALL→SMS→EMAIL); channel selection for each retry attempt is a fresh assessment by `channel_selection_rules.md`; the progression is governed by directive logic, not by hardcoded advancement in the retry flow |
| **AP-RF3** | MUST NOT allow retry orchestration to apply a hardcoded maximum attempt threshold; `MAX_ATTEMPTS` is not a constant in retry orchestration governance; retry exhaustion check uses `outreach_max_retry_attempts` from the ACTIVE Config V2 Group A |
| **AP-RF4** | MUST NOT allow replay-triggered retry orchestration cycles to produce LIVE effects; all replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; replay cycles may not acquire LIVE window idempotency keys |
| **AP-RF5** | MUST NOT allow silent fallback execution in any retry orchestration domain; every failure path is deterministic and observable; generic "Retry immediately once" is not a permitted failure response specification |
| **AP-RF6** | MUST NOT allow any retry orchestration action to exist without a `correlation_id`, `causation_id`, `execution_mode`, and `config_version_id`; unattributed retry actions are specification violations; the `causation_id` linking to the prior intent is required on every retry intent record |
| **AP-RF7** | MUST NOT allow the retry orchestration flow to write state transitions directly or increment `contact_attempt` counts directly; state transitions and attempt count increments are produced as `OrchestrationIntent` records and delegated to the state management service |
| **AP-RF8** | MUST NOT allow retry orchestration to substitute a hardcoded fallback value when a Config V2 threshold key is missing; `UNKNOWN_V0` must be substituted and `CONFIG_THRESHOLD_MISSING_{KEY}` emitted; no silent default for `outreach_max_retry_attempts` or `outreach_retry_window_days` |
| **AP-RF9** | MUST NOT allow any retry orchestration domain to re-implement directive logic; retry policy, eligibility, decision engine, channel selection, escalation, AI governance, and provider governance evaluations are delegated to their respective directives (AP-RT12) |
| **AP-RF10** | MUST NOT allow an `OrchestrationIntent` with `intent_type = RETRY_OUTREACH` to be produced from AI advisory output alone; AI advisory informs but does not authorize retry orchestration decisions; rule-based `RetryPolicyAssessment` must authorize the retry (AP-RT11) |
| **AP-RF11** | MUST NOT allow live AI inference during replay retry orchestration; FINALIZED_COPY sourced exclusively from `warehouse.snapshot_ai_narratives` in replay; non-finalized AI sourced from `ai_insights` table historical records; no mutation of `warehouse.snapshot_ai_narratives` by any retry domain (AP-OWN15) |
| **AP-RF12** | MUST NOT silently swallow retry orchestration failures; every caught exception must be classified with a stable `error_class`, logged with full context (excluding PII), and produce either a retry path or a dead-letter record with recovery instructions (AP-RT14) |
| **AP-RF13** | MUST NOT log raw PII (student name, email, phone, transcript content, payment details) in retry orchestration observability records; opaque `student_id` and `correlation_id` only (AP-RT13) |
| **AP-RF14** | MUST NOT allow duplicate LIVE execution of the same retry intent; the idempotency key `(student_id, checkpoint_type, contact_attempt)` in `processed_events` must be checked before any execution delegation; a duplicate key is a no-op, not a second dispatch |
| **AP-RF15** | MUST NOT allow an orphaned retry orchestration cycle — a cycle that began (correlation_id generated) but did not emit a structured observability record at completion; every retry cycle that starts must emit a completion log, even if the outcome is `failure` (AP-RT15) |

---

## 13. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Retry Orchestration Loop deferred — single attempt per student per daily cycle
* When the Retry Orchestration Loop is active, SHADOW mode enforcement applies
* `outreach_max_retry_attempts` from Config V2 Group A governs; no hardcoded attempt ceiling
* `outreach_retry_window_days` from Config V2 Group A governs cadence; no hardcoded Day 1/Day 2/Day 3 timing
* Channel selection per attempt governed by `channel_selection_rules.md`; no hardcoded CALL→SMS→EMAIL progression
* Observability: cycle start/end records only
* Attribution: `correlation_id` and `causation_id` required on all records

---

### STANDARD

* Retry Orchestration Loop active
* Full retry eligibility and policy assessment
* Escalation coordination active with live routing for retry-exhausted students
* AI enrichment coordination active for retry candidates
* Full `causation_id` lineage from initial intent through all retry intents
* All retry-applicable Config V2 Group A variables active
* Full idempotency enforcement: `(student_id, checkpoint_type, contact_attempt)` keyed
* Full observability pipeline

---

### PRODUCTION

* All 10 retry orchestration execution domains fully active
* Full governance precondition enforcement before every retry cycle
* Compliance hold enforcement active per student at retry dispatch
* Retry starvation detection and escalation active
* Full provider degradation governance (circuit breaker, retry budget protection, provider outage)
* AI governance tier enforcement active for all retry orchestration decisions
* Full observability pipeline: `correlation_id` and `causation_id` traceability end-to-end verified
* Emergency recovery retry orchestration cycles governed (UE-RT5 resolution applies)

---

## 14. ACCEPTANCE CRITERIA

---

### AC-RF1 — Governance Precondition Enforcement

**Given** no ACTIVE config version exists
**When** the retry orchestration cycle is triggered
**Then** the cycle does not start; `PRECONDITION_FAILED_NO_ACTIVE_CONFIG` is emitted; no retry candidate is evaluated; no retry intent is produced; an escalation candidacy signal is generated

---

### AC-RF2 — No Hardcoded Channel Progression

**Given** a student is evaluated for a second retry attempt
**When** the retry orchestration flow coordinates channel selection
**Then** `channel_selection_rules.md` produces a fresh `ChannelSelectionAssessment` for this attempt; no hardcoded CALL→SMS→EMAIL progression is applied; the channel assigned is solely determined by directive assessment output

---

### AC-RF3 — Config V2 Retry Threshold Governance

**Given** `outreach_max_retry_attempts` is present in the ACTIVE config version
**When** the retry orchestration flow evaluates retry exhaustion
**Then** the retry exhaustion check uses the Config V2-governed threshold; `RetryPolicyAssessment.config_version_id` matches the ACTIVE config version; no hardcoded `MAX_ATTEMPTS` value is used

---

### AC-RF4 — Replay LIVE Suppression

**Given** `execution_type = replay`
**When** the retry orchestration flow evaluates a student's historical retry context
**Then** no LIVE outbound retry dispatch is generated; no LIVE AI inference is triggered; no `contact_attempt` increment is written; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; a replay diagnostic record is emitted

---

### AC-RF5 — Missing Config Threshold UNKNOWN_V0

**Given** `outreach_retry_window_days` is absent from the ACTIVE config version
**When** the retry orchestration cycle evaluates cadence for a candidate
**Then** `UNKNOWN_V0` is substituted; `CONFIG_THRESHOLD_MISSING_OUTREACH_RETRY_WINDOW_DAYS` warning is emitted; the cycle continues with `DEGRADED` annotation; no hardcoded fallback window is assumed

---

### AC-RF6 — Attribution Continuity (causation_id)

**Given** a retry orchestration cycle is triggered for a student who was previously contacted
**When** the retry intent is produced
**Then** `OrchestrationIntent.causation_id` links to the prior `OrchestrationIntent.intent_id` for that student; a single `correlation_id` is present in the cycle's structured log, in the retry intent record, in the `processed_events` record, and in the directive evaluation records within the cycle

---

### AC-RF7 — No Direct State Mutation

**Given** a retry orchestration cycle successfully delegates a retry intent
**When** the state management service records the dispatch confirmation
**Then** the retry orchestration flow has not written any `contact_attempt` increment or state transition directly; the `contact_attempt` value is owned by the state management service; the retry flow's `OrchestrationIntent` is the governance-authorized input to that transition

---

### AC-RF8 — SHADOW Mode Enforcement

**Given** `execution_mode = SHADOW`
**When** the retry orchestration flow produces a `RetryPolicyAssessment` with `retry_authorized = true`
**Then** the resulting `OrchestrationIntent` carries `governance_scope = SHADOW_ONLY`; no LIVE retry dispatch is delegated; all outputs are tagged `outcome = shadow_only`

---

### AC-RF9 — Provider Failure Observability

**Given** the GHL provider circuit breaker opens during a retry orchestration cycle
**When** outbound retry dispatch delegation is attempted
**Then** `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`; a `CIRCUIT_BREAKER_OPEN` structured log is emitted; a provider failure escalation candidacy signal is produced; non-dispatch retry domains continue; retry budget protection annotation applied for blocked attempts

---

### AC-RF10 — No Silent Failure Absorption

**Given** a retry candidate evaluation fails with an unexpected exception
**When** the retry orchestration flow handles the failure
**Then** the exception is classified with a stable `error_class`; a structured skip record is emitted with `skip_reason`, `contact_attempt`, and `correlation_id`; the failure is not silently swallowed; remaining candidates are evaluated

---

### AC-RF11 — Idempotent Retry Cycle

**Given** the retry orchestration cycle has already produced a `RETRY_OUTREACH` intent for a student with `contact_attempt = 2`
**When** the cycle is re-triggered for the same inputs
**Then** the `processed_events` dedup check on `(student_id, checkpoint_type, contact_attempt = 2)` fires; the duplicate key is a no-op; no second retry intent is produced; no second dispatch is delegated

---

### AC-RF12 — Orphaned Cycle Prevention

**Given** a retry orchestration cycle begins (correlation_id generated)
**When** the cycle encounters a fatal error mid-execution
**Then** a structured completion log is emitted with `outcome = failure`; the failure is classified; a dead-letter record is written for unprocessed retry candidates; the cycle does not terminate silently

---

## 15. UNRESOLVED CONCERNS

---

### UE-RF1 — Retry Window Tolerance vs. Missed Retry (OPERATIONAL DECISION)

**Problem:** The retry orchestration cycle is governed by `outreach_retry_window_days` from Config V2 Group A, but the governance protocol for when a retry candidate whose window elapsed "yesterday" (missed a cycle) is treated vs. a candidate whose window elapsed today has not been defined.

**Impact:** A missed retry cycle could cause a student to be treated as a "new window" candidate rather than a "window-elapsed-yesterday" candidate, which may affect escalation timing.

**Classification:** Operational decision. Mirrors UE-DF1 and UE-SCH1. Resolution requires a "missed retry window" tolerance variable or explicit catch-up behavior definition in Config V2 Group I.

---

### UE-RF2 — Per-Student Retry Intent Persistence Failure Recovery (GOVERNANCE DECISION)

**Problem:** When `OrchestrationIntent` persistence fails for one retry candidate mid-cycle, the governance protocol for whether to continue with remaining candidates or halt the retry cycle has not been defined.

**Impact:** Continuing creates a cycle where some retry intents were produced and some were not, with partial lineage. Halting abandons other eligible retry candidates.

**Classification:** Governance decision. Mirrors UE-DF4. Requires defining failure granularity (per-student rollback vs cycle-level rollback) and the recovery path for retry-specific intents.

---

### UE-RF3 — Retry Starvation Escalation Threshold (OPERATIONAL DECISION)

**Problem:** The retry degradation condition table (§10.2) includes `RETRY_STARVATION_DETECTED` for consecutive cycles with zero dispatch, but the governance-defined consecutive-cycle threshold at which starvation generates an escalation candidacy signal has not been specified.

**Impact:** Without a threshold, starvation detection cannot deterministically trigger escalation.

**Classification:** Operational decision. Requires a Config V2 Group A variable governing the consecutive-zero-dispatch threshold for escalation.

---

### UE-RF4 — Retry Budget Protection Scope on Provider Outage (GOVERNANCE DECISION)

**Problem:** When a provider outage blocks retry dispatch, the `outreach_retry_policy.md` governs whether the blocked attempt is counted against the student's retry budget. The specific mechanism by which the retry orchestration flow communicates "this attempt was blocked by provider outage, not consumed" to the state management service has not been defined.

**Impact:** Without a clear protocol, some implementations may consume the retry budget for outage-blocked attempts, prematurely exhausting a student's retry eligibility.

**Classification:** Governance decision. Requires defining the `provider_outage_exempted` flag protocol on `OrchestrationIntent` records and its handling by the state management service.

---

### UE-RF5 — AI Advisory Absence Escalation in DEGRADED Retry Mode (OPERATIONAL DECISION)

**Problem:** When the retry cycle runs in DEGRADED mode due to AI provider unavailability, the governance model for when rule-based-only retry evaluation requires human review has not been defined for retry candidates specifically.

**Impact:** Retry decisions made for high-escalation-risk students without AI advisory may proceed without any escalation path flagging this condition.

**Classification:** Operational decision. Mirrors UE-DF5. Requires an escalation candidacy type for AI-unavailable DEGRADED retry evaluation and a Config V2 threshold governing when this escalation fires.

---

## 16. DOWNSTREAM GOVERNANCE

---

### 16.1 Parent Contract Inheritance

This document is a child of:

| Parent contract | Governs this document via |
|---|---|
| `runtime/system_loop.md` | §4.2 (Retry Orchestration Loop), §6 (retry governance), §8.3 (provider failure behavior), §3.1 (mode definitions), §9 (AI governance), §10 (degradation governance), §11 (attribution and observability), §12 (AP-RT1–AP-RT15) |
| `runtime/scheduler_design.md` | §4.2 (Retry Orchestration Scheduler trigger semantics), §3 (scheduler mode restrictions), §5 (orchestration window governance), §6 (Config V2 retry timing variables) |
| `runtime/daily_outreach_flow.md` | §4.4 (Retry Orchestration Coordination within daily cycle); retry_cycle_flow.md describes the operational sequencing detail for the coordination declared there |

Where this document conflicts with parent contract semantics, the parent contracts govern.

---

### 16.2 Directive Dependencies

| Directive | Retry flow dependency |
|---|---|
| `directives/outreach_retry_policy.md` | `RetryPolicyAssessment` consumed by §4.3; retry exhaustion termination governed by §6.5 of `system_loop.md` |
| `directives/outreach_eligibility_rules.md` | `EligibilityAssessment` re-check consumed by §4.3 |
| `directives/core_decision_engine.md` | `OrchestrationIntent` with `intent_type = RETRY_OUTREACH` consumed by §5.3 |
| `directives/channel_selection_rules.md` | `ChannelSelectionAssessment` per-attempt fresh assessment consumed by §5.3 |
| `directives/escalation_rules.md` | `EscalationOrchestrationAssessment` for retry-exhausted candidates consumed by §4.5 |
| `directives/llm_processing_contract.md` | `AIAssessment` consumed by §4.6 |
| `directives/ghl_integration_contract.md` | `ProviderOrchestrationAssessment` consumed by §5.3; RULE 1–6 govern provider boundary |
| `directives/agent_ownership_matrix.md` | Authority domain definitions consumed by §6.2, §7.2 |

---

### 16.3 Upstream Spec Dependencies

| Specification | Retry sections governed |
|---|---|
| `spec/01_requirements.md` §12 (Config V2 Governance Catalog) | §5.2 (precondition gate), §4.4 (retry cadence), §4.3 (exhaustion threshold) |
| `spec/03_state_transition_rules.md` | §4.1 (NO_RESPONSE candidate filtering), §6.2 (state transition authority) |
| `spec/04_idempotency_concurrency.md` | §11.3 (idempotency key `student_id, checkpoint_type, contact_attempt`), §5.3 (retry dedup) |
| `spec/05_external_integrations.md` | §8 (provider governance), §7.2 (replay suppression) |
| `spec/06_observability_operations.md` | §11 (retry observability), §4.1–4.10 (observability requirements) |
| `spec/07_api_contracts.md` | §5.4 (retry intent delegation API boundaries) |
| `spec/08_data_model.md` | §4.1 (student_trigger_data, state_transition_log), §6.2 (processed_events) |
| `spec/09_warehouse_physical_architecture.md` | §9.3 (FINALIZED_COPY semantics), §7.3 (regeneration restrictions) |

---

## 17. REFERENCES

---

**Governing parent contracts (authoritative over this document):**
* `runtime/system_loop.md`
* `runtime/scheduler_design.md`
* `runtime/daily_outreach_flow.md`

**Directive contracts (consumed by this document):**
* `directives/outreach_retry_policy.md`
* `directives/outreach_eligibility_rules.md`
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
