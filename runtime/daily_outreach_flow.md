# runtime/daily_outreach_flow.md

---

## LAYER 7 — RUNTIME (GOVERNANCE-SAFE DAILY ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `spec/01_requirements.md` through `spec/09_warehouse_physical_architecture.md` and all seven governance-safe directives. The previous version described MVP-era operational outreach flow documentation: a direct execution sequence with hardcoded "6:00 PM CST" trigger timing, "Send payload to GHL" in Step 8, "Max 50 concurrent executions" batch limit, simplistic `QUEUED → CONTACTED` state transitions with no governance context, generic "fallback logic" for failure handling, no runtime mode semantics, no Config V2 governance, no replay semantics, no attribution requirements, and direct GHL dispatch assumptions. That architecture is incompatible with the governance-safe orchestration model. Daily orchestration flow is no longer direct outreach execution. It is governance-safe orchestration lifecycle coordination — deterministic runtime-cycle sequencing with replay-safe orchestration governance and observable attribution continuity. This document is governed by `runtime/system_loop.md` and `runtime/scheduler_design.md`.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Daily Orchestration Architecture** defines:

* How the daily orchestration evaluation cycle is sequenced, governed, and made historically explainable
* What daily orchestration execution domains exist and how each domain coordinates governance-safe evaluation, intent production, and execution delegation
* How SHADOW-vs-LIVE execution mode restrictions apply to every domain within the daily orchestration flow
* How replay orchestration simulates the historical daily cycle without generating LIVE effects
* How provider governance boundaries are maintained during daily orchestration
* How AI advisory governance applies during daily candidate evaluation
* How degradation is deterministic, observable, and never silently swallowed within a daily cycle
* How the full daily orchestration lineage chain enables forensic reconstruction of any outreach decision

This document is a **child runtime contract** governed by:

* `runtime/system_loop.md` — the authoritative parent runtime contract (§4.1, §5, §6, §3.1)
* `runtime/scheduler_design.md` — scheduler trigger semantics in §4.1 govern when this cycle begins

Where this document conflicts with parent contract semantics, the parent contracts govern.

This document describes the operational sequencing detail within the Orchestration Evaluation Loop (`system_loop.md` §4.1).

---

### 1.2 What Daily Orchestration Flow Is NOT

In the governance-safe orchestration model, daily orchestration flow is explicitly **NOT**:

* **Direct outreach execution flow** — daily orchestration does not send SMS, emails, or GHL triggers; it coordinates governance-safe intent generation and execution delegation
* **Provider dispatch flow** — no step in daily orchestration constructs a GHL API payload, an SMS message body, an email template, or a meeting booking request; all provider dispatch is delegated to provider orchestration services under governance authorization
* **Operational task execution flow** — daily orchestration is not a sequential task runner; it is an intent-production and governance-validation sequence
* **Hardcoded timing flow** — the daily trigger time is not "6:00 PM CST" hardcoded; it is governed by Config V2 Group A `outreach_daily_trigger_hour_cst`; all timing values are Config V2-governed (AP-DF6)
* **Silent fallback execution** — generic "fallback logic" is not a permitted failure response; every failure path is deterministic, observable, and governed
* **A replay-unaware flow** — daily orchestration must be historically reproducible; every orchestration decision must be traceable through an immutable attribution chain
* **Non-attributable orchestration** — no orchestration action produced by the daily cycle is permitted to exist without a `correlation_id`, `execution_mode`, and `config_version_id`

Explicitly prohibited in daily orchestration flow:

* Direct provider execution (AP-DF1)
* Direct GHL dispatch (AP-DF1, AP-DF2)
* Direct SMS or email execution semantics (AP-DF1)
* Replay-triggered LIVE effects (AP-DF3)
* Hidden fallback execution (AP-DF4)
* Non-attributable orchestration actions (AP-DF5)
* Hardcoded timing or concurrency values (AP-DF6)
* Direct state mutation by the orchestration loop (AP-DF7)

---

### 1.3 Daily Orchestration Governance Layer Definition

Daily orchestration coordination sits at the sequencing boundary between:

* The **scheduler orchestration layer** (`runtime/scheduler_design.md` §4.1) — provides the governance-safe trigger, `cycle_id`, and `execution_mode` that initiate the daily cycle
* The **directive layer** (all seven governance-safe directives) — produces advisory assessments, intent candidates, and governance constraints consumed by the orchestration sequence
* The **execution layer** (orchestration services in `backend/src/services/`) — validates and executes under governance authorization; receives intents delegated by the orchestration loop
* The **provider layer** (GHL and other external systems) — executes operational delivery under provider orchestration assessment governance; never owned by daily orchestration

| Layer | Daily orchestration relationship |
|---|---|
| Scheduler layer | Provides `cycle_id`, `triggered_at`, `execution_mode`, `config_version_id`; daily flow inherits all attribution from scheduler trigger |
| Directive layer | Produces `EligibilityAssessment`, `RetryPolicyAssessment`, `OrchestrationIntent`, `ChannelSelectionAssessment`, `EscalationOrchestrationAssessment`, `AIAssessment`, `ProviderOrchestrationAssessment`; daily flow consumes these in governance-defined order |
| Orchestration services | Receive delegated intents; own execution authorization; daily flow never owns execution path |
| Provider layer | Execute delivery; governed by `ghl_integration_contract.md`; daily flow never owns this path |
| Warehousing layer | Append-only persistence; daily flow triggers writes via designated service accounts only |

---

## 2. DAILY ORCHESTRATION MODEL

---

### 2.1 Governance-Safe Daily Sequencing Principle

Every daily orchestration cycle must satisfy the following invariants before candidate evaluation begins:

1. **Scheduler-triggered** — the daily cycle is initiated by the Orchestration Evaluation Scheduler (`scheduler_design.md` §4.1) with a governance-authorized `cycle_id` and `execution_mode`; no ad-hoc self-triggering by the daily flow
2. **Config V2-governed** — the trigger cadence is governed by Config V2 Group A `outreach_daily_trigger_hour_cst`; no hardcoded timing value exists in this document (AP-DF6)
3. **Preconditioned** — a valid ACTIVE config version, a valid `execution_mode`, and a valid `correlation_id` must exist before any candidate is evaluated (inherited from `system_loop.md` §5.2)
4. **Intent-delegated** — the daily orchestration flow produces or receives orchestration intents; it does not execute actions directly (AP-DF1)
5. **Attribution-continuous** — a `correlation_id` generated at loop start propagates through every directive evaluation, execution service call, provider interaction, and log record within the cycle (AP-DF5)
6. **Replay-safe** — every orchestration decision must be historically reproducible; no daily orchestration action may depend on mutable in-process state unavailable in replay context (AP-DF3)
7. **Idempotent** — re-running the same daily cycle for the same inputs must produce the same end state, with no duplicate side effects

---

### 2.2 Three-Tier Daily Orchestration Architecture

```
Scheduler Trigger (cycle_id, execution_mode, config_version_id)
  ↓
Directive Layer  →  Intent / Advisory Assessment Generation
  ↓
Orchestration Services  →  Governance-Authorized Execution Delegation
  ↓
Provider Layer  →  Operational Delivery (never owned by daily flow)
```

The daily orchestration flow coordinates the first two tiers and delegates to the third. It does not collapse tiers. A daily flow step that calls a provider API directly is a specification violation (AP-DF1). A daily flow step that re-implements directive logic is a specification violation (AP-DF8).

---

### 2.3 Directive Assessment Outputs Consumed by Daily Orchestration

| Directive | Structured output consumed | Consumed at step |
|---|---|---|
| `outreach_eligibility_rules.md` | `EligibilityAssessment` — ELIGIBLE/INELIGIBLE/BLOCKED/SHADOW_ONLY | §4.3 Eligibility Orchestration |
| `outreach_retry_policy.md` | `RetryPolicyAssessment` — RETRY_AUTHORIZED/RETRY_BLOCKED/RETRY_EXHAUSTED/RETRY_PENDING | §4.4 Retry Orchestration Coordination |
| `core_decision_engine.md` | `OrchestrationIntent` — INITIATE_OUTREACH/RETRY_OUTREACH/DEFER_PENDING_AI/ESCALATE/CLOSE/HOLD | §5.3 Canonical Sequence (Decision Engine step) |
| `channel_selection_rules.md` | `ChannelSelectionAssessment` — CALL/SMS/EMAIL/NO_CHANNEL_ELIGIBLE | §5.3 Canonical Sequence (Channel Selection step) |
| `escalation_rules.md` | `EscalationOrchestrationAssessment` — escalation_candidate, escalation_type, escalation_severity | §4.5 Escalation Coordination |
| `llm_processing_contract.md` | `AIAssessment` — ai_governance_tier, advisory_scope, advisory_content | §4.6 AI Enrichment Coordination |
| `ghl_integration_contract.md` | `ProviderOrchestrationAssessment` — governance_scope, provider_event_type | §5.3 Canonical Sequence (Provider Assessment step) |

Daily orchestration consumes these outputs in governance-defined order (§5.3). It does not re-implement directive logic (AP-DF8).

---

### 2.4 Daily Orchestration Layer Responsibilities

| Responsibility | Daily orchestration owns | Daily orchestration does NOT own |
|---|---|---|
| Consuming scheduler trigger attribution | Yes | Defining trigger cadence (Config V2 owns) |
| Validating governance preconditions | Yes | Evaluating eligibility logic (directives own) |
| Propagating `correlation_id` | Yes | Generating idempotency keys for directive evaluations |
| Coordinating intent delegation to services | Yes | Executing outreach dispatch (orchestration services own) |
| Consuming provider orchestration assessments | Yes | Making provider API calls (provider orchestration services own) |
| Coordinating replay cycle sequencing | Yes | Generating live inferences during replay (AP-RT2) |
| Emitting cycle-level observability records | Yes | Implementing AI confidence scoring |
| Sequencing provider sync before evaluation | Yes | Executing SQL Server queries (Provider Synchronization Loop owns) |

---

## 3. RUNTIME MODES GOVERNING DAILY ORCHESTRATION

---

### 3.1 Mode Inheritance from Parent Contract

Daily orchestration inherits all six runtime mode definitions from `system_loop.md` §3.1. This section summarizes mode behavior as it applies to the daily orchestration flow. For authoritative mode definitions, see `system_loop.md` §3.

| Mode | Daily orchestration behavior |
|---|---|
| **LIVE** | Full candidate evaluation; full intent production; delegation to outreach orchestration service when `ProviderOrchestrationAssessment.governance_scope = AUTHORIZED`; all domains active |
| **SHADOW** | Full candidate evaluation; all intents produced with `governance_scope = SHADOW_ONLY`; no LIVE outbound dispatch delegated; all outcomes tagged `execution_mode = SHADOW` |
| **REPLAY** | Historical orchestration simulation only; SHADOW-only outputs; no LIVE dispatch, no LIVE AI inference, no state transitions; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` |
| **REGENERATION** | Not applicable to daily orchestration flow; regeneration is a Report Generation Loop concern (`system_loop.md` §4.6) |
| **DEGRADED** | Evaluation continues for non-dispatch domains; outbound dispatch blocked when provider unavailable; AI scope restricted when AI unavailable; all degradation states observable |
| **MAINTENANCE** | All daily orchestration evaluation suspended; no candidate evaluation; no intent production |

---

### 3.2 Mode Enforcement in Daily Orchestration

Every step in the daily orchestration flow checks execution mode before producing outputs. A step that produces LIVE outputs without checking execution mode is a specification violation. Mode checking is not optional or deferred — it is the second precondition after config version validation.

* **LIVE mode** — `OrchestrationIntent.governance_scope = AUTHORIZED`; full delegation path active
* **SHADOW mode** — `OrchestrationIntent.governance_scope = SHADOW_ONLY`; delegation produces no outbound dispatch
* **REPLAY mode** — all outputs carry `execution_type = replay`; no LIVE path is reachable (AP-DF3, AP-RT2)
* **DEGRADED mode** — outputs carry `DEGRADED` annotation; blocked domains depend on degradation cause (§10.2)
* **MAINTENANCE mode** — daily cycle does not start; scheduler trigger is suppressed (`scheduler_design.md` §3.1)

---

## 4. DAILY ORCHESTRATION EXECUTION DOMAINS

---

The daily orchestration flow is organized into ten coordination domains. Each domain maps to a specific governance responsibility within the daily evaluation cycle. Domains are sequenced deterministically (§5.3). No domain may be skipped. No domain may produce direct provider execution output.

---

### 4.1 Candidate Loading Orchestration

| Attribute | Specification |
|---|---|
| **Purpose** | Load student candidate records from `student_trigger_data` (PostgreSQL, synchronized from SQL Server); apply pre-evaluation filter to exclude structurally invalid records before directive evaluation begins |
| **Replay behavior** | Sources candidate records from stored `student_trigger_data` snapshot at historical timestamp; no SQL Server re-sync occurs during replay |
| **SHADOW behavior** | Candidate loading proceeds normally; loaded candidates evaluated with SHADOW-only output restriction |
| **LIVE behavior** | Candidate records loaded from current `student_trigger_data`; loaded candidate count emitted in cycle observability record |
| **Attribution requirements** | `sync_cycle_id` annotated on each candidate record to establish provenance chain from SQL Server source through orchestration cycle |
| **Observability requirements** | Structured log: `candidates_loaded`, `pre_filter_exclusions`, `load_duration_ms`, `sync_age_hours` at load time |
| **Idempotency guarantees** | Candidate loading is read-only; re-running produces the same candidate set given the same `student_trigger_data` state |

---

### 4.2 Governance Precondition Validation

| Attribute | Specification |
|---|---|
| **Purpose** | Validate all governance preconditions required before any candidate evaluation begins; inherited from `system_loop.md` §5.2; this domain is the gate that must pass before proceeding to §4.3 |
| **Replay behavior** | Precondition validation uses `historical_config_version_id`; execution mode check validates `execution_type = replay` |
| **SHADOW behavior** | Full precondition validation applies; SHADOW mode does not relax preconditions |
| **LIVE behavior** | All preconditions must be satisfied; failure at any precondition stops the cycle with structured error emission |
| **Attribution requirements** | `config_version_id`, `execution_mode`, `correlation_id` all validated; their values propagated to every subsequent domain |
| **Observability requirements** | Precondition failure produces structured log: `PRECONDITION_FAILED_{CAUSE}`, `failed_precondition_field`, `correlation_id` |
| **Idempotency guarantees** | Precondition validation is stateless; re-running produces same outcome given same system state |

Preconditions required (inherited from `system_loop.md` §5.2):

| Precondition | Required value | Failure behavior |
|---|---|---|
| `config_version_id` | Non-null ACTIVE config version | Cycle stops; `PRECONDITION_FAILED_NO_ACTIVE_CONFIG` emitted; escalation candidacy generated |
| `execution_mode` | `SHADOW` or `LIVE` (or `REPLAY` for replay context) | Cycle stops; structured error emitted |
| `correlation_id` | UUID v4 generated for this cycle | Cycle stops |
| Config V2 threshold resolution | All required Group A, F, K variables resolvable | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning; cycle continues with DEGRADED annotation |
| SQL Server data age | `sync_lag_hours ≤ sql_server_max_sync_age_hours` (Config V2 Group K) | Cycle continues with `STALE_SQL_SERVER_DATA` annotation; not blocking |

---

### 4.3 Eligibility Orchestration

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate eligibility assessment for each loaded candidate via `outreach_eligibility_rules.md`; produce `EligibilityAssessment` records; exclude ineligible students from further evaluation in this cycle |
| **Replay behavior** | Eligibility evaluation uses `historical_config_version_id`; `EligibilityAssessment` produced with `governance_scope = REPLAY_ONLY` |
| **SHADOW behavior** | Full eligibility evaluation; `EligibilityAssessment.governance_scope = SHADOW_ONLY` |
| **LIVE behavior** | Full eligibility evaluation; eligible students advance to decision engine; ineligible students produce skip records with `skip_reason` |
| **Attribution requirements** | `correlation_id` propagated to every `EligibilityAssessment` record; `config_version_id` recorded in each assessment |
| **Observability requirements** | Per-cycle log: `candidates_evaluated`, `eligible_count`, `ineligible_count`, `blocked_count`, `shadow_only_count`, `skip_reason_distribution` |
| **Idempotency guarantees** | Eligibility assessment keyed on `(student_id, cycle_date, config_version_id)`; re-evaluating the same student in the same cycle with the same config produces the same assessment |

---

### 4.4 Retry Orchestration Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate retry policy assessment for students in `NO_RESPONSE` state whose retry window has elapsed; produce `RetryPolicyAssessment` records; governed by `system_loop.md` §4.2 and §6 |
| **Replay behavior** | Retry policy evaluated under `historical_config_version_id`; `RetryPolicyAssessment` produced with `governance_scope = REPLAY_ONLY`; no LIVE retry dispatch |
| **SHADOW behavior** | Retry candidacy assessed and logged; no LIVE dispatch produced |
| **LIVE behavior** | Retry intents produced for `retry_authorized = true` students; delegated to outreach orchestration service |
| **Attribution requirements** | `causation_id` linked to prior `OrchestrationIntent` for the student; `correlation_id` propagated |
| **Observability requirements** | Per-cycle log: `retry_candidates_evaluated`, `retry_authorized_count`, `retry_blocked_count`, `retry_exhausted_count` |
| **Idempotency guarantees** | Retry idempotency key: `(student_id, checkpoint_type, contact_attempt)` per `system_loop.md` §11.5; duplicate key is a no-op |

---

### 4.5 Escalation Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate escalation candidacy assessment for students meeting escalation criteria per `escalation_rules.md`; produce `EscalationOrchestrationAssessment` records; route candidacy signals to escalation routing service |
| **Replay behavior** | Escalation candidacy assessed under `historical_config_version_id`; outputs carry `REPLAY_ESCALATION_CANDIDATE` scope; no live routing |
| **SHADOW behavior** | Escalation candidacy assessed and logged; no live operator routing |
| **LIVE behavior** | `EscalationOrchestrationAssessment` records with `escalation_candidate = true` delegated to escalation routing service; routing is advisory — human acknowledgement required |
| **Attribution requirements** | `causation_id` linked to originating cycle `correlation_id`; escalation record contains originating `OrchestrationIntent.intent_id` |
| **Observability requirements** | Per-cycle log: `escalation_candidates_evaluated`, `candidacy_produced_count`, `escalation_types_distribution` |
| **Idempotency guarantees** | Keyed on `(student_id, escalation_type, cycle_date)` per `system_loop.md` §11.5; duplicate signal within same cycle suppressed |

---

### 4.6 AI Enrichment Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate AI advisory enrichment for evaluated candidates; verify AI advisory freshness against `ai_insight_ttl_hours` from Config V2 Group H; consume `AIAssessment` outputs; restrict AI advisory scope based on governance tier |
| **Replay behavior** | No live AI inference; AI content sourced from `warehouse.snapshot_ai_narratives` (FINALIZED) or `ai_insights` table (non-finalized); stale AI in replay returns historical advisory or `UNAVAILABLE` |
| **SHADOW behavior** | AI advisory evaluated; outputs tagged `outcome = shadow_only`; FINALIZED_COPY semantics apply normally |
| **LIVE behavior** | `AIAssessment.advisory_content` informs but does not authorize `OrchestrationIntent` (AP-DF9, AP-RT11); `ai_governance_tier` governs advisory scope |
| **Attribution requirements** | `ai_version_number`, `prompt_version`, `model_used`, `generated_at` captured in assessment record; `correlation_id` propagated |
| **Observability requirements** | Per-cycle log: `stale_ai_count`, `missing_ai_count`, `finalized_copy_count`, `ai_governance_tier_distribution` |
| **Idempotency guarantees** | AI advisory consumption is read-only; enrichment does not mutate `ai_insights` table (AI Refresh Orchestration Loop owns mutations, `system_loop.md` §4.4) |

---

### 4.7 Provider Synchronization Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Validate that Provider Synchronization Loop (`system_loop.md` §4.7) has completed successfully before candidate evaluation consumes `student_trigger_data`; assess sync lag against `sql_server_max_sync_age_hours` from Config V2 Group K |
| **Replay behavior** | Replay uses stored `student_trigger_data` snapshot; no SQL Server re-sync validation during replay; `sync_lag_hours` annotation preserved from original cycle records |
| **SHADOW behavior** | Sync validation proceeds normally in all execution modes |
| **LIVE behavior** | Sync completion record verified; `sync_lag_hours` assessed; `STALE_SQL_SERVER_DATA` annotation applied to affected candidates if lag threshold exceeded |
| **Attribution requirements** | `sync_cycle_id` from Provider Synchronization Loop linked to daily orchestration cycle |
| **Observability requirements** | Per-cycle log: `sync_lag_hours`, `stale_threshold_exceeded`, `sync_validation_outcome` |
| **Idempotency guarantees** | Sync validation is read-only; daily flow does not invoke sync directly |

---

### 4.8 Observability Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Emit structured observability records throughout the daily orchestration cycle; ensure every domain completion, every skip, every failure, and every degradation state is observable; never suppress observability even under failure conditions |
| **Replay behavior** | Replay cycles emit full replay diagnostic records in addition to standard observability; all outputs carry `execution_type = replay` tag |
| **SHADOW behavior** | Full observability records required; all outcomes tagged `execution_mode = SHADOW` |
| **LIVE behavior** | Full observability records emitted at cycle completion; PII-free structured logs per AP-DF13 |
| **Attribution requirements** | Every observability record carries `correlation_id`, `cycle_id`, `execution_mode`, `config_version_id` |
| **Observability requirements** | See §11.3 for the full required daily orchestration observability field set |
| **Idempotency guarantees** | Observability records are append-only; idempotency not required for structured log emission |

---

### 4.9 Replay Orchestration Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Coordinate replay mode behavior when the daily orchestration flow runs as a historical simulation; ensure all LIVE effects are suppressed; ensure replay diagnostic records are complete |
| **Replay behavior** | This domain IS the active governance domain when `execution_type = replay`; all other domains subordinate to replay suppression rules (§7) |
| **SHADOW behavior** | Replay within SHADOW mode produces SHADOW-only diagnostic outputs; no LIVE effects |
| **LIVE behavior** | Replay Orchestration Scheduler never triggers LIVE daily cycles with `execution_type = replay`; this domain is inactive in normal LIVE operation (AP-DF3, AP-SCH3) |
| **Attribution requirements** | `replay_cycle_id`, `source_artifact_id`, `historical_config_version_id`, `fingerprint_comparison_outcome`, `replay_partial` required |
| **Observability requirements** | Full replay diagnostic set per `system_loop.md` §7.4 |
| **Idempotency guarantees** | Replay idempotency key: `(source_artifact_id, replay_cycle_id)` per `system_loop.md` §11.5 |

---

### 4.10 Degradation Coordination

| Attribute | Specification |
|---|---|
| **Purpose** | Govern the daily orchestration flow's behavior when one or more operational components are degraded; ensure degradation is deterministic, observable, and produces escalation candidacy; ensure no domain silently absorbs a degraded state |
| **Replay behavior** | Replay permitted if warehouse accessible and historical config resolvable; replay partial annotation applied when any threshold is UNKNOWN_V0 |
| **SHADOW behavior** | Degradation behavior applies normally in SHADOW mode |
| **LIVE behavior** | Degradation condition table (§10.2) governs which domains continue and which are blocked; every degraded state produces a structured observability record |
| **Attribution requirements** | Degradation records carry `degradation_cause`, `affected_domains`, `degradation_onset_timestamp`, `correlation_id` |
| **Observability requirements** | `SCHEDULER_DEGRADED` and `SCHEDULER_RECOVERY` observable state transition records emitted on degradation and recovery; escalation candidacy generated |
| **Idempotency guarantees** | Degradation coordination does not produce side effects; degradation records are append-only observability records |

---

## 5. CANONICAL GOVERNANCE SEQUENCING

---

### 5.1 Sequencing Principles

The canonical daily orchestration governance sequencing is deterministic. The following principles govern its execution:

1. **Precondition gate is mandatory** — config version, execution mode, attribution context validated before any evaluation begins (`system_loop.md` §5.2)
2. **Sync completion precedes evaluation** — Provider Synchronization Loop must complete successfully before candidate evaluation consumes `student_trigger_data` (`system_loop.md` §5.1)
3. **AI freshness precedes evaluation** — AI Refresh Orchestration Loop runs before Orchestration Evaluation Loop if AI advisory freshness is required for the cycle (`system_loop.md` §5.1)
4. **Directive evaluation is ordered** — eligibility, retry, decision, channel, escalation directives evaluated in governance-defined order; outputs are structured assessment objects, not action strings
5. **Intent persistence precedes delegation** — `OrchestrationIntent` records written to `student_timeline_events` before any execution delegation; write failure is a cycle failure
6. **Execution delegation is not execution** — daily flow delegates to orchestration services; it does not own the execution path
7. **Observability emission is mandatory** — structured log emitted at cycle completion; never omitted (AP-RT15, AP-DF15)

---

### 5.2 Governance Precondition Gate

Inherited verbatim from `system_loop.md` §5.2. Before any candidate evaluation:

| Precondition | Required value | Failure behavior |
|---|---|---|
| `config_version_id` | Non-null ACTIVE config version | Cycle does not start; structured error log emitted; escalation candidacy generated |
| `execution_mode` | `SHADOW` or `LIVE` | Cycle does not start; structured error log emitted |
| `correlation_id` | UUID v4 generated for this cycle | Cycle does not start |
| Config V2 threshold resolution | All required Group variables resolvable | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning; cycle continues with DEGRADED annotation |
| SQL Server data age | `sync_lag_hours ≤ sql_server_max_sync_age_hours` (Config V2 Group K) | Cycle continues with `STALE_SQL_SERVER_DATA` annotation; not blocking |

---

### 5.3 Canonical Daily Orchestration Evaluation Sequence

The governed daily runtime sequencing is:

```
PRECONDITION GATE (§5.2 — config_version_id, execution_mode, correlation_id)
  ↓
PROVIDER SYNC VALIDATION (sql_server_max_sync_age_hours check — §4.7)
  ↓
AI FRESHNESS GATE (ai_insight_ttl_hours check per student — §4.6)
  ↓
CANDIDATE LOADING (student_trigger_data read — §4.1)
  ↓
ELIGIBILITY ASSESSMENT (outreach_eligibility_rules.md → EligibilityAssessment — §4.3)
  ↓
RETRY POLICY ASSESSMENT (outreach_retry_policy.md → RetryPolicyAssessment, for retry candidates — §4.4)
  ↓
CORE DECISION ENGINE (core_decision_engine.md → OrchestrationIntent — system_loop.md §5.3)
  ↓
CHANNEL SELECTION (channel_selection_rules.md → ChannelSelectionAssessment — system_loop.md §5.3)
  ↓
ESCALATION CANDIDACY ASSESSMENT (escalation_rules.md → EscalationOrchestrationAssessment — §4.5)
  ↓
INTENT RECORD PERSISTENCE (student_timeline_events append — system_loop.md §5.1)
  ↓
EXECUTION DELEGATION (orchestration services, under governance authorization — §5.4)
  ↓
PROVIDER ORCHESTRATION ASSESSMENT (ghl_integration_contract.md → ProviderOrchestrationAssessment)
  ↓
OBSERVABILITY EMISSION (§4.8 — cycle completion record)
```

This sequence is deterministic. No step may be skipped. No step may produce direct execution output that bypasses the next step. No step may produce LIVE output when `execution_mode` is SHADOW or REPLAY.

---

### 5.4 Intent Delegation Boundaries

| Stage | Owner | Daily flow responsibility |
|---|---|---|
| Advisory generation | Directive layer | Invoke directive evaluation; receive assessment objects |
| Intent validation | Daily orchestration flow | Validate `OrchestrationIntent` is governance-authorized; check `execution_mode` |
| Execution delegation | Orchestration services | Daily flow delegates; does not own execution path |
| Provider dispatch | Provider orchestration services | Daily flow coordinates; does not call GHL directly (AP-DF1, AP-DF2) |
| State persistence | State management service | Daily flow does not write state transitions directly (AP-DF7) |
| Observability | Daily orchestration flow | Loop emits structured cycle-level log |

---

## 6. STATE TRANSITION GOVERNANCE

---

### 6.1 Governance-Safe State Coordination

Daily orchestration does not own state transitions. The V1 pattern:

> `QUEUED → CONTACTED` triggered by "Send payload to GHL"

is replaced with:

> `OrchestrationIntent` produced by decision engine → delegated to orchestration services → `ProviderOrchestrationAssessment` authorizes dispatch → state management service records transition

Daily orchestration's role: **coordinate the sequence that produces intents; delegate execution; never write state directly.**

---

### 6.2 State Transition Authority

| State transition | Authority | Daily flow role |
|---|---|---|
| Any state → CONTACTED | State management service (after confirmed dispatch) | Produces intent; does not write transition |
| CONTACTED → NO_RESPONSE | State management service (after timeout or GHL webhook) | Does not own; informs retry assessment |
| NO_RESPONSE → re-evaluation (retry) | State management service (after retry authorization) | Retry domain (§4.4) produces intent |
| Any state → INTERVENTION_REQUIRED | State management service (after escalation routing) | Escalation domain (§4.5) produces candidacy |
| Any state → CLOSED | State management service (via decision engine close intent) | Produces close intent only |
| CONTACTED → RESPONDED | State management service (after GHL webhook inbound) | Does not own; inbound webhook handled by ingestion service |

State transitions are always initiated by governance-authorized intents, never by direct runtime loop writes (AP-DF7). Every state transition produces an observable record with `correlation_id`.

---

### 6.3 Replay-Safe State Semantics

In REPLAY mode:

* Daily orchestration flow produces no state transitions
* Historical state records from `state_transition_log` are the authoritative source for what transitions occurred
* Re-evaluating a historical cycle produces a fingerprint comparison between the historical decision and the current re-evaluation result
* `fingerprint_comparison_outcome = MATCH | DIVERGENT | UNKNOWN` emitted in replay diagnostic record
* No state write authority exists in replay context (AP-OWN2)

---

## 7. REPLAY & REGENERATION SEMANTICS

---

### 7.1 Daily Replay Orchestration

When the daily orchestration flow runs in REPLAY mode (`execution_type = replay`), it follows the governed replay lifecycle from `system_loop.md` §7.1:

```
GOVERNANCE AUTHORIZATION (operator-initiated; authorization record written)
  ↓
REPLAY PRECONDITION GATE (source_artifact_id, historical_config_version_id validated)
  ↓
HISTORICAL CANDIDATE STATE RESOLUTION (student state from state_transition_log at historical timestamp)
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

The following LIVE effects are suppressed in all daily orchestration replay contexts:

| Effect category | Suppression mechanism | Reference |
|---|---|---|
| Outbound GHL dispatch | `ProviderOrchestrationAssessment.outbound_suppressed = true` | AP-GHL5; AP-DF3 |
| Live AI inference | `AIAssessment.ai_blocked = true`; FINALIZED_COPY sourced from warehouse | AP-AI5; AP-DF10 |
| Student state transitions | Replay Services hold no state write authority | AP-OWN2; AP-DF7 |
| Escalation routing | Escalation outputs carry `REPLAY_ESCALATION_CANDIDATE` scope | AP-DF3 |
| Warehouse mutations | Replay loop reads warehouse; does not write | AP-OWN15 |

---

### 7.3 Regeneration Restrictions

Daily orchestration flow is not involved in report regeneration. Regeneration is a Report Generation Loop concern (`system_loop.md` §4.6, FAD-2). The daily orchestration flow:

* Does not execute in REGENERATION mode
* Does not re-evaluate students during a regeneration cycle
* Does not access `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives` directly

---

## 8. PROVIDER GOVERNANCE

---

### 8.1 Provider Boundary Principles

Daily orchestration flow never owns provider governance. Inherited from `system_loop.md` §8.1:

* Daily orchestration flow produces `OrchestrationIntent` records
* Orchestration services evaluate `ProviderOrchestrationAssessment` before delegating to GHL
* If `governance_scope ≠ AUTHORIZED`, no outbound dispatch occurs
* No step in daily orchestration may construct a GHL API call, an SMS payload, an email body, or a meeting booking request (AP-DF1, AP-DF2)

---

### 8.2 GHL Integration Governance

The `ghl_integration_contract.md` governs all provider interactions. Daily orchestration flow consumes `ProviderOrchestrationAssessment` and delegates; it does not own:

* GHL API endpoint routing
* SMS/email/call payload construction
* Outbound retry within provider layer
* Provider circuit breaker state
* Provider delivery confirmation telemetry

All of the above are governed by `ghl_integration_contract.md` RULE 1–6 and consumed by the daily flow as assessment outputs only.

---

### 8.3 Provider Failure Daily Behavior

| Provider failure state | Daily orchestration behavior |
|---|---|
| Circuit breaker OPEN | Outbound dispatch blocked; `governance_scope = UNAVAILABLE`; provider failure escalation candidacy generated; non-dispatch domains continue |
| Provider outage active | Same as circuit breaker OPEN |
| Retry budget exhausted | `RETRY_EXHAUSTED` annotation; escalation candidacy generated; no further retry dispatch in this cycle |
| Sync lag exceeds threshold | `STALE_SQL_SERVER_DATA` annotation; evaluation continues with annotated data |
| `AUTH_FAILURE` | TERMINAL class; no retry; alert escalation; all subsequent provider interactions blocked until key rotation confirmed |

No provider failure results in silent absorption (AP-DF11). Every failure produces an observable audit record and an escalation candidacy signal (AP-RT6).

---

## 9. AI GOVERNANCE

---

### 9.1 Advisory-Only Daily Principle

AI advisory outputs are consumed by the daily orchestration flow, not obeyed. Inherited from `system_loop.md` §9.1:

* `AIAssessment.advisory_content.recommended_intervention` informs but does not authorize `OrchestrationIntent`
* `AIAssessment.confidence_metadata.confidence_score` governs advisory scope (FULL/LIMITED/UNAVAILABLE) but does not override rule-based eligibility
* No step in the daily orchestration flow may produce an `OrchestrationIntent` from AI advisory output alone (AP-DF9, AP-RT11)

---

### 9.2 Stale AI Daily Restrictions

| AI governance tier | Daily orchestration behavior |
|---|---|
| CONFIDENT (≥ 0.70, within TTL) | Full advisory scope; may elevate escalation severity in LIVE mode |
| ADVISORY (< 0.70 or approaching TTL) | Limited advisory scope; may not independently drive LIVE escalation |
| STALE (beyond `ai_insight_ttl_hours`) | Advisory scope limited; LIVE escalation from AI advisory blocked; rule-based evaluation only |
| IN_FLIGHT | Prior version served if available; DEFERRED advisory scope; cycle proceeds without waiting |
| UNAVAILABLE (null insight) | Rule-based evaluation only; cycle not blocked |

Stale AI does not block the daily orchestration cycle. It restricts advisory scope and escalation authority only.

---

### 9.3 FINALIZED_COPY Daily Semantics

Once AI text is physically copied to `warehouse.snapshot_ai_narratives` at FINALIZED state (FAD-1):

* The daily orchestration flow does not re-request AI evaluation for this content
* Replay reads this content directly — no live AI inference triggered
* `ai_governance_tier = FINALIZED_COPY` overrides all staleness assessments in daily evaluation
* No step in daily orchestration may trigger mutation of `warehouse.snapshot_ai_narratives` (AP-OWN15, AP-DF12)

---

## 10. FAILURE & DEGRADATION GOVERNANCE

---

### 10.1 Deterministic Degradation Principles

Degradation in daily orchestration is observable, not silent. Inherited from `system_loop.md` §10.1:

Every degraded daily orchestration state must:

* Emit a structured log entry with `degradation_cause`, `affected_domains`, and `outcome = partial` or `outcome = failure`
* Produce an escalation candidacy signal for human awareness
* Describe what domains continued and what domains were blocked
* Never silently swallow a failure or substitute a silent default (AP-DF11)

Explicitly prohibited patterns:

* Generic "fallback logic" without observable cause classification (replaces V1 "fallback logic" failure checkpoint)
* Silent skip of a failed candidate without structured error record (AP-RT5)
* Swallowing provider failure without audit record (AP-RT6)
* Retrying without an upper bound from Config V2 (AP-RT14)

---

### 10.2 Daily Degradation Condition Table

| Condition | Affected daily domains | Daily flow behavior | Orchestration continues | Observability required |
|---|---|---|---|---|
| Provider circuit breaker OPEN | §4.1 (delegation), §4.4 (retry delegation) | Outbound dispatch blocked; `governance_scope = UNAVAILABLE` | Yes (eligibility, AI, sync, escalation) | `CIRCUIT_BREAKER_OPEN` event; provider failure escalation candidacy |
| Provider outage active | §4.1, §4.4 | Same as circuit open | Yes | `PROVIDER_OUTAGE` event; degradation onset record |
| AI provider unavailable | §4.6 | AI enrichment blocked; rule-based evaluation only | Yes | `AI_PROVIDER_UNAVAILABLE` event; stale AI annotation |
| SQL Server sync lag exceeded | §4.7, §4.1 | `STALE_SQL_SERVER_DATA` annotation; evaluation continues | Yes | `SYNC_LAG_EXCEEDED` event |
| SQL Server connection failed | §4.7 | Sync validation blocked; last successful sync data used | Yes (with stale annotation) | `SQL_SERVER_UNAVAILABLE` event; escalation candidacy |
| Duplicate event storm | Inbound webhook coordination | Deduplication gate absorbs; `DUPLICATE_SUPPRESSED` scope | Yes | `DUPLICATE_EVENT_STORM` event; dedup count emitted |
| Config threshold missing | All domains | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning; DEGRADED annotation | Yes (annotated) | `CONFIG_THRESHOLD_MISSING` warning per key |
| Compliance hold (individual student) | §4.3, §4.1 dispatch | Dispatch blocked for that student; others unaffected | Yes | `COMPLIANCE_HOLD_DISPATCH_BLOCKED` per student |
| Warehouse write failure | Intent persistence (§5.1) | Cycle fails for affected record; dead-letter for retry | No (for that record) | `WAREHOUSE_WRITE_FAILURE` event; recovery path documented |

---

### 10.3 Provider Outage Daily Behavior

When a provider outage is detected during a daily orchestration cycle:

* **Outbound dispatch** — blocked for all students in the cycle; `governance_scope = UNAVAILABLE`; escalation candidacy generated
* **Inbound webhook ingestion** — continues normally; webhooks ingested and attributed; no state transitions without governance authorization
* **SQL Server reads** — unaffected; sync loop continues
* **AI evaluation** — unaffected
* **Retry budget protection** — retry attempts blocked by provider outage are not consumed from student retry budget (governed by `outreach_retry_policy.md`)

---

### 10.4 AI Outage Daily Behavior

When the AI provider is unavailable:

* **AI enrichment coordination** — blocked for new requests; circuit breaker state updated
* **Candidate evaluation** — proceeds with rule-based evaluation only; AI advisory scope = UNAVAILABLE
* **FINALIZED_COPY records** — unaffected; sourced from warehouse regardless of AI provider state
* **Escalation candidacy** — rule-based severity assessment applies; AI may not elevate without advisory content

---

### 10.5 Synchronization Lag Governance

Sync lag governance inherits from `system_loop.md` §10.5 and §10.7:

* `STALE_SQL_SERVER_DATA` annotation applied when `sync_lag_hours` exceeds `sql_server_max_sync_age_hours`
* Annotated decisions carry `STALE_SQL_SERVER_DATA` annotation in `OrchestrationIntent` records
* Persistent sync backlog generates escalation candidacy if lag exceeds governance-defined threshold
* Daily orchestration does not block on sync lag — governance model allows annotated-data evaluation

---

## 11. ATTRIBUTION & OBSERVABILITY

---

### 11.1 Daily Orchestration Attribution Lineage

The full attribution lineage chain for any outreach event within a daily orchestration cycle:

```
Scheduler Trigger  →  cycle_id + triggered_at (scheduler_design.md §4.1)
  ↓
Config V2 Timing  →  outreach_daily_trigger_hour_cst (Group A) — governs when trigger fires
  ↓
Daily Orchestration Loop  →  correlation_id + config_version_id + execution_mode
  ↓
OrchestrationIntent  →  intent_id + causation_id + correlation_id
  ↓
ProviderOrchestrationAssessment  →  governance_scope + correlation_id
  ↓
processed_events  →  idempotency_key + correlation_id
  ↓
ghl_messages  →  ghl_message_id + correlation_id
```

Every link in this chain is required. A missing link is an attribution defect (AP-DF5, AP-RT4, spec/06).

---

### 11.2 Daily Attribution Requirements

Every daily orchestration record must carry (inherited from `system_loop.md` §11.2):

| Field | Required in |
|---|---|
| `correlation_id` | All records in every domain |
| `causation_id` | All records derived from a prior orchestration record |
| `config_version_id` | All orchestration evaluation records |
| `execution_mode` | All records |
| `execution_type` | All records (`original`, `replay`, `regeneration`, `recovery`) |
| `loop_name` | Structured log entries |
| `actor_identity` | Human-initiated actions; `system` for automated loops |
| `attribution_timestamp` | All records |

---

### 11.3 Daily Orchestration Observability Fields

Every daily orchestration cycle emits a structured JSON record to stdout upon completion:

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "daily_orchestration",
  "event": "loop_cycle_complete",
  "loop_name": "orchestration_evaluation_loop",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | REPLAY | DEGRADED | MAINTENANCE",
  "execution_type": "original | replay | regeneration | recovery",
  "config_version_id": "string | null",
  "duration_ms": 0,
  "outcome": "success | failure | partial | shadow_only",
  "candidates_loaded": 0,
  "candidates_evaluated": 0,
  "eligible_count": 0,
  "ineligible_count": 0,
  "intents_produced": 0,
  "retry_intents_produced": 0,
  "escalation_candidacy_produced": 0,
  "dispatch_authorized": 0,
  "dispatch_blocked_unavailable": 0,
  "degradation_flags": [],
  "config_threshold_missing_keys": []
}
```

PII (student name, email, phone, transcript content) must not appear in daily orchestration observability records (AP-DF13, AP-RT13).

---

### 11.4 Correlation Propagation

`correlation_id` propagation rules (inherited from `system_loop.md` §11.1):

* Generated at the start of every daily orchestration cycle
* Propagates through every directive evaluation within the cycle
* Propagates through every execution service call within the cycle
* Propagates through every provider orchestration assessment within the cycle
* Persisted in every `OrchestrationIntent` record, every `state_transition_log` record, every `processed_events` record, and every structured log entry within the cycle

A failure that cannot be traced from symptom to root cause using a single `correlation_id` is an observability defect (spec/06).

---

## 12. ARCHITECTURE PRESERVATION RULES

---

The following rules are MUST NOT prohibitions. Violation of any rule is a specification defect.

| Rule | Prohibition |
|---|---|
| **AP-DF1** | MUST NOT allow any step in daily orchestration to directly call a provider API (GHL, AI provider, SMS, email, meeting booking); all provider interactions are delegated to governance-authorized orchestration services via `ghl_integration_contract.md` and `llm_processing_contract.md` boundaries |
| **AP-DF2** | MUST NOT allow any step in daily orchestration to construct a GHL API payload, an SMS message body, an email template, or a meeting booking request; provider payload construction is exclusively owned by provider orchestration services |
| **AP-DF3** | MUST NOT allow replay-triggered daily orchestration cycles to produce LIVE effects; all replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; replay cycles may not acquire LIVE window idempotency keys |
| **AP-DF4** | MUST NOT allow silent fallback execution in any daily orchestration domain; every failure path is deterministic and observable; generic "fallback logic" is not permitted as a failure response specification |
| **AP-DF5** | MUST NOT allow any daily orchestration action to exist without a `correlation_id`, `execution_mode`, and `config_version_id`; unattributed orchestration actions are specification violations |
| **AP-DF6** | MUST NOT embed hardcoded timing or concurrency values in daily orchestration governance; daily trigger timing is governed by Config V2 Group A `outreach_daily_trigger_hour_cst`; no hardcoded "6:00 PM CST", "Max 50 concurrent", or any other hardcoded operational threshold |
| **AP-DF7** | MUST NOT allow the daily orchestration flow to write state transitions directly; state transitions are produced as `OrchestrationIntent` records and delegated to the state management service |
| **AP-DF8** | MUST NOT allow any daily orchestration domain to re-implement directive logic; eligibility, retry policy, decision engine, channel selection, escalation, AI governance, and provider governance evaluations are delegated to their respective directives (AP-RT12) |
| **AP-DF9** | MUST NOT allow an `OrchestrationIntent` to be produced from AI advisory output alone; AI advisory informs but does not authorize orchestration decisions; rule-based directive evaluation must produce the intent (AP-RT11) |
| **AP-DF10** | MUST NOT allow live AI inference during replay orchestration; FINALIZED_COPY sourced exclusively from `warehouse.snapshot_ai_narratives` in replay; non-finalized AI sourced from `ai_insights` table historical records |
| **AP-DF11** | MUST NOT silently swallow daily orchestration failures; every caught exception must be classified with a stable `error_class`, logged with full context (excluding PII), and produce either a retry path or a dead-letter record with recovery instructions (AP-RT14) |
| **AP-DF12** | MUST NOT allow any daily orchestration domain to trigger mutation of `warehouse.snapshot_ai_narratives`; these records are immutable after FINALIZED state (FAD-1, AP-OWN15) |
| **AP-DF13** | MUST NOT log raw PII (student name, email, phone, transcript content, payment details) in daily orchestration observability records; opaque `student_id` and `correlation_id` only (AP-RT13) |
| **AP-DF14** | MUST NOT allow duplicate LIVE execution of the same daily orchestration intent; the idempotency key in `processed_events` must be checked before any execution delegation; a duplicate key is a no-op (AP-RT10) |
| **AP-DF15** | MUST NOT allow an orphaned daily orchestration cycle — a cycle that began (correlation_id generated) but did not emit a structured observability record at completion; every cycle that starts must emit a completion log, even if the outcome is `failure` (AP-RT15) |

---

## 13. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Orchestration Evaluation Loop active; Provider Synchronization Loop active
* Retry orchestration coordination deferred — single attempt per student per cycle
* Escalation coordination: candidacy assessed and logged; no live routing
* AI enrichment coordination: deferred; rule-based evaluation only
* Snapshot finalization, report generation, replay coordination: deferred
* SHADOW mode enforcement on all daily automation
* Config V2 Group A, F, K thresholds active; remaining groups deferred
* Observability: minimal — cycle start/end records only
* Trigger timing governed by Config V2 Group A `outreach_daily_trigger_hour_cst`; no hardcoded timing (AP-DF6)

---

### STANDARD

* All daily orchestration domains active
* Retry orchestration coordination active
* Escalation coordination active with live routing
* AI enrichment coordination active
* Snapshot finalization loop active
* Replay orchestration coordination: diagnostic mode; operator-initiated only
* All 10 Config V2 groups active
* Full idempotency enforcement across all domains
* Full observability pipeline

---

### PRODUCTION

* All 10 daily orchestration execution domains fully active
* Full governance precondition enforcement before every cycle
* Compliance hold enforcement active per student
* Emergency recovery orchestration cycles governed (UE-RT5 resolved)
* Full provider degradation governance (circuit breaker, retry collapse, provider outage)
* AI governance tier enforcement active for all orchestration decisions
* Full observability pipeline: `correlation_id` traceability end-to-end verified

---

## 14. ACCEPTANCE CRITERIA

---

### AC-DF1 — Governance Precondition Enforcement

**Given** no ACTIVE config version exists
**When** the daily orchestration cycle is triggered
**Then** the cycle does not start; `PRECONDITION_FAILED_NO_ACTIVE_CONFIG` is emitted; no candidate is evaluated; no intent is produced; an escalation candidacy signal is generated

---

### AC-DF2 — No Direct Provider Dispatch

**Given** an `OrchestrationIntent` with `intent_type = INITIATE_OUTREACH` is produced
**When** the daily orchestration flow processes the intent
**Then** the intent is delegated to the outreach orchestration service; the daily flow does not construct a GHL API payload, an SMS message, an email body, or a meeting booking request

---

### AC-DF3 — Replay LIVE Suppression

**Given** `execution_type = replay`
**When** the daily orchestration flow evaluates a student's historical orchestration context
**Then** no LIVE outbound dispatch is generated; no LIVE AI inference is triggered; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; a replay diagnostic record is emitted

---

### AC-DF4 — Config V2 Trigger Timing

**Given** `outreach_daily_trigger_hour_cst` is present in the ACTIVE config version
**When** the Orchestration Evaluation Scheduler fires the daily cycle
**Then** the trigger time is governed by the Config V2 variable; no hardcoded "6:00 PM CST" or other hardcoded timing value determines the trigger

---

### AC-DF5 — No Hardcoded Batch Concurrency

**Given** a batch of candidates is evaluated in the daily orchestration cycle
**When** the cycle coordinates parallel evaluation
**Then** the concurrency limit is governed by Config V2; no hardcoded "Max 50 concurrent executions" value is applied

---

### AC-DF6 — Attribution Continuity

**Given** a daily orchestration cycle is triggered
**When** the cycle completes
**Then** a single `correlation_id` is present in the cycle's structured log, in every `OrchestrationIntent` record produced, in every `processed_events` record written, and in every directive evaluation record within the cycle; no orchestration record exists without a `correlation_id`

---

### AC-DF7 — SHADOW Mode Enforcement

**Given** `execution_mode = SHADOW`
**When** the daily orchestration flow produces an `OrchestrationIntent` with `intent_type = INITIATE_OUTREACH`
**Then** the intent carries `governance_scope = SHADOW_ONLY`; no LIVE dispatch is delegated; all outputs are tagged `outcome = shadow_only`

---

### AC-DF8 — Provider Failure Observability

**Given** the GHL provider circuit breaker opens during a daily orchestration cycle
**When** outbound dispatch delegation is attempted
**Then** `ProviderOrchestrationAssessment.governance_scope = UNAVAILABLE`; a `CIRCUIT_BREAKER_OPEN` structured log is emitted; a provider failure escalation candidacy signal is produced; non-dispatch domains continue

---

### AC-DF9 — No Silent Failure Absorption

**Given** a candidate evaluation fails with an unexpected exception
**When** the daily orchestration flow handles the failure
**Then** the exception is classified with a stable `error_class`; a structured skip record is emitted with `skip_reason` and `correlation_id`; the failure is not silently swallowed; remaining candidates are evaluated

---

### AC-DF10 — Idempotent Daily Cycle

**Given** the daily orchestration cycle has already produced an `OrchestrationIntent` for a student with a given idempotency key
**When** the cycle is re-triggered for the same inputs
**Then** the `processed_events` dedup check fires; the duplicate key is a no-op; no second intent is produced; no second dispatch is delegated

---

### AC-DF11 — Stale AI Restriction

**Given** `AIAssessment.ai_governance_tier = STALE` for a student
**When** the daily orchestration flow evaluates escalation candidacy for that student
**Then** stale AI advisory does not independently drive LIVE escalation; rule-based evaluation proceeds; escalation severity may not be elevated by STALE AI; the stale annotation is present in the escalation candidacy record

---

### AC-DF12 — Orphaned Cycle Prevention

**Given** a daily orchestration cycle begins (correlation_id generated)
**When** the cycle encounters a fatal error mid-execution
**Then** a structured completion log is emitted with `outcome = failure`; the failure is classified; a dead-letter record is written for unprocessed candidates; the cycle does not terminate silently

---

## 15. UNRESOLVED CONCERNS

---

### UE-DF1 — Scheduler Trigger Timing Drift (OPERATIONAL DECISION)

**Problem:** The daily orchestration cycle is triggered by `outreach_daily_trigger_hour_cst` from Config V2 Group A, but the governance protocol for when the trigger is considered "missed" vs. "late" within the same calendar day has not been defined.

**Impact:** Ambiguity between a late trigger and a missed cycle could cause unnecessary recovery cycles or mask actual misses.

**Classification:** Operational decision. Mirrors UE-SCH1 in `scheduler_design.md`. Resolution requires a "late window" tolerance variable in Config V2 Group I.

---

### UE-DF2 — Stale SQL Server Data Decision Threshold (OPERATIONAL DECISION)

**Problem:** The daily orchestration flow annotates candidates with `STALE_SQL_SERVER_DATA` when sync lag exceeds `sql_server_max_sync_age_hours` but continues evaluation. The governance protocol for when annotated-data evaluation should be blocked rather than annotated has not been defined.

**Impact:** Severe sync lag could cause orchestration decisions based on data that is days out of date.

**Classification:** Operational decision. Requires a second Config V2 threshold (likely Group K) governing when sync lag becomes blocking.

---

### UE-DF3 — Per-Student Evaluation Parallelism Governance (OPERATIONAL DECISION)

**Problem:** The governance model for per-student evaluation parallelism within a single daily cycle relies on Config V2 but the specific variable and its authorization scope have not been defined.

**Impact:** Without explicit parallelism governance, the system cannot deterministically prevent resource contention during large batch cycles.

**Classification:** Operational decision. Requires a Config V2 Group I variable governing per-cycle evaluation concurrency with replay-safe semantics.

---

### UE-DF4 — Intent Persistence Write Failure Recovery (GOVERNANCE DECISION)

**Problem:** When `OrchestrationIntent` persistence fails for one student mid-cycle, the governance protocol for whether to continue with remaining candidates or halt the cycle has not been defined.

**Impact:** Continuing creates a cycle where some intents were produced and some were not, with partial lineage. Halting abandons other students.

**Classification:** Governance decision. Mirrors UE-RT2. Requires defining failure granularity (per-student rollback vs cycle-level rollback) and the recovery path.

---

### UE-DF5 — AI Advisory Absence Escalation in DEGRADED Mode (OPERATIONAL DECISION)

**Problem:** When the daily cycle runs in DEGRADED mode due to AI provider unavailability, the governance model for when rule-based-only evaluation requires human review has not been defined.

**Impact:** Orchestration decisions made without AI advisory may be of lower quality for high-escalation-risk students with no escalation path flagging this condition.

**Classification:** Operational decision. Requires an escalation candidacy type for AI-unavailable DEGRADED evaluation and a Config V2 threshold governing when this escalation fires.

---

## 16. DOWNSTREAM GOVERNANCE

---

### 16.1 Parent Contract Inheritance

This document is a child of:

| Parent contract | Governs this document via |
|---|---|
| `runtime/system_loop.md` | §4.1 (Orchestration Evaluation Loop), §5 (governance sequencing), §6 (retry governance), §3.1 (mode definitions), §8 (provider governance), §9 (AI governance), §10 (degradation governance), §11 (attribution and observability), §12 (AP-RT1–AP-RT15) |
| `runtime/scheduler_design.md` | §4.1 (Orchestration Evaluation Scheduler trigger semantics), §3 (scheduler mode restrictions), §5 (orchestration window governance), §6 (Config V2 timing variables) |

Where this document conflicts with parent contract semantics, the parent contracts govern.

---

### 16.2 Sibling Document Relationship

| Sibling document | Relationship |
|---|---|
| `runtime/retry_cycle_flow.md` | Defines retry orchestration sequencing detail; governed by `system_loop.md` §4.2 and §6; retry orchestration coordination (§4.4 of this document) delegates to `outreach_retry_policy.md` which governs the sequencing described in `retry_cycle_flow.md` |

---

### 16.3 Directive Dependencies

| Directive | Daily flow dependency |
|---|---|
| `directives/outreach_eligibility_rules.md` | `EligibilityAssessment` consumed by §4.3 |
| `directives/outreach_retry_policy.md` | `RetryPolicyAssessment` consumed by §4.4 |
| `directives/core_decision_engine.md` | `OrchestrationIntent` consumed by §5.3 |
| `directives/channel_selection_rules.md` | `ChannelSelectionAssessment` consumed by §5.3 |
| `directives/escalation_rules.md` | `EscalationOrchestrationAssessment` consumed by §4.5 |
| `directives/llm_processing_contract.md` | `AIAssessment` consumed by §4.6 |
| `directives/ghl_integration_contract.md` | `ProviderOrchestrationAssessment` consumed by §5.3 |
| `directives/agent_ownership_matrix.md` | Authority domain definitions consumed by §6.2, §7.2 |

---

## 17. REFERENCES

---

**Governing parent contracts (authoritative over this document):**
* `runtime/system_loop.md`
* `runtime/scheduler_design.md`

**Sibling runtime documents:**
* `runtime/retry_cycle_flow.md`

**Directive contracts (consumed by this document):**
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
