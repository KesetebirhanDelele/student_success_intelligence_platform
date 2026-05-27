# failure/failure_playbook.md

---

## LAYER 8 — FAILURE PLAYBOOK (GOVERNANCE-SAFE RESILIENCE ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `spec/01_requirements.md` through `spec/09_warehouse_physical_architecture.md`, all seven governance-safe directives, and the four rewritten runtime contracts. The previous version described MVP-era operational recovery documentation: simplistic failure categories (External/Internal/Data/Concurrency), a hardcoded retry matrix with fixed retry counts ("GHL Trigger: 1–2", "LLM Call: 1", "Scheduler: 1"), "Retry immediately (once)" as a first-class recovery instruction, "Trigger recovery execution" as a scheduler recovery action, three-tier scope behavior (MVP/STANDARD/PRODUCTION), and generic log field lists. That architecture is incompatible with the governance-safe orchestration model. Failure handling is no longer operational retry handling. It is governance-safe resilience orchestration — deterministic degradation coordination with replay-safe recovery governance and observable recovery lineage management. This document is the **canonical parent resilience contract** for `failure/scheduling_failures.md`, `failure/ghl_failures.md`, and `failure/llm_failures.md`.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe Resilience Orchestration Architecture** defines:

* How failure governance domains are categorized, governed, and made historically explainable
* What execution modes govern resilience behavior — and what is permitted in each mode
* How deterministic degradation is coordinated without silent fallback execution
* How Config V2 governs recovery cadences, retry thresholds, and degradation escalation — not hardcoded values
* How replay-safe recovery semantics prevent historical simulation from generating LIVE effects
* How provider governance boundaries are maintained during resilience orchestration
* How AI advisory governance applies during degraded orchestration evaluation
* How recovery attribution lineage enables forensic reconstruction of every recovery action
* How failure state governance preserves immutable lineage and externalized state authority
* What authority boundaries the resilience layer holds vs what it must not own

This document is the **canonical parent resilience contract** for:

* `failure/scheduling_failures.md` — governed by §2.4, §4.4, §10.4
* `failure/ghl_failures.md` — governed by §2.2, §4.2, §10.2, §10.6
* `failure/llm_failures.md` — governed by §2.3, §4.3, §10.3

Child resilience documents describe domain-specific failure sequencing detail. This document establishes the governance model all such sequencing must conform to. Where child documents conflict with this document, this document governs.

---

### 1.2 What Failure Handling Is NOT

In the governance-safe orchestration model, failure handling is explicitly **NOT**:

* **Silent recovery execution** — "Retry immediately (once)" is not a permitted recovery instruction; every recovery path is deterministic, observable, and governed (AP-FP3)
* **Direct provider execution recovery** — no step in resilience orchestration calls a provider API, triggers a GHL workflow, or constructs an outbound payload; all dispatch remains delegated under governance authorization (AP-FP1)
* **Hardcoded retry count enforcement** — "Max Retries: 1–2" and similar fixed values are not permitted; retry thresholds are governed by Config V2 Group A `outreach_max_retry_attempts`; no hardcoded fallback substitution is allowed (AP-FP5)
* **Non-attributed recovery behavior** — recovery actions without `correlation_id`, `causation_id`, `execution_mode`, and `config_version_id` are not permitted (AP-FP6)
* **Replay-triggered LIVE recovery** — a replay-mode resilience simulation may not generate LIVE recovery effects; all replay recovery outputs carry `execution_type = replay` and are SHADOW-only (AP-FP2)
* **Immutable lineage corruption** — no recovery action may overwrite, backfill, or retroactively modify records in `student_timeline_events`, `state_transition_log`, `warehouse.student_snapshots`, or `warehouse.snapshot_ai_narratives` (AP-FP7)
* **Hidden fallback execution** — escalation to a silent default channel, silent rule-based substitution, or undocumented degraded behavior is a specification defect, not a safe fallback (AP-FP4)

Explicitly prohibited in resilience orchestration:

* Direct provider execution recovery (AP-FP1)
* Replay-triggered LIVE recovery effects (AP-FP2)
* "Retry immediately once" semantics (AP-FP3)
* Silent fallback execution in any failure domain (AP-FP4)
* Hardcoded retry count substitution (AP-FP5)
* Non-attributable recovery actions (AP-FP6)
* Immutable record mutation (AP-FP7)
* Governance bypass during recovery (AP-FP8)

---

### 1.3 Resilience Governance Layer Definition

Resilience orchestration sits at the containment boundary between:

* The **runtime orchestration layer** (`runtime/system_loop.md`) — defines degradation governance, mode transitions, and the deterministic degradation condition table; resilience layer inherits and coordinates these governance constraints
* The **scheduler orchestration layer** (`runtime/scheduler_design.md`) — governs scheduler lag detection and recovery cycle attribution; resilience layer coordinates recovery cycle governance
* The **daily outreach orchestration layer** (`runtime/daily_outreach_flow.md`) — defines daily cycle degradation behavior per §4.4 and §9; resilience layer inherits these semantics
* The **retry orchestration layer** (`runtime/retry_cycle_flow.md`) — defines retry degradation, starvation, and provider outage behavior per §10; resilience layer inherits these semantics
* The **directive layer** (`directives/`) — produces advisory assessments used during degraded evaluation; resilience layer does not re-implement directive logic
* The **provider governance layer** (`directives/ghl_integration_contract.md`) — defines provider failure behavior, circuit breaker semantics, and inbound webhook handling during outages

| Layer | Resilience layer relationship |
|---|---|
| `runtime/system_loop.md` §10 | Authoritative degradation governance; resilience layer inherits §10.1–§10.8 verbatim |
| `runtime/scheduler_design.md` | Scheduler lag governance; recovery cycle attribution semantics |
| `runtime/daily_outreach_flow.md` | Daily cycle degradation and degraded-mode sequencing |
| `runtime/retry_cycle_flow.md` | Retry starvation, retry budget protection, degraded retry mode |
| Orchestration services | Validate and execute under governance authorization; resilience layer coordinates but does not own |
| Provider systems | Operational delivery; resilience layer coordinates circuit breaker signals but does not own provider calls |

---

## 2. FAILURE GOVERNANCE DOMAINS

---

### 2.1 Orchestration Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Runtime orchestration loop failures: precondition gate failures, invalid execution mode, missing correlation_id, Config V2 threshold resolution failures, incomplete cycle completion |
| **Recovery philosophy** | Precondition failures are hard stops — cycles do not proceed without a valid config_version_id and execution_mode; threshold resolution failures use `UNKNOWN_V0` substitution with DEGRADED annotation |
| **Replay behavior** | Orchestration failure records are preserved; replay may simulate the failed cycle to produce a fingerprint comparison; no LIVE output produced |
| **SHADOW behavior** | Failure detected and logged with `execution_mode = SHADOW`; no LIVE escalation routing |
| **LIVE behavior** | Failure detected, logged, escalation candidacy produced; recovery cycle attribution generated if applicable |
| **Observability requirements** | Structured failure log with `failure_domain = orchestration`, `correlation_id`, `config_version_id`, `failure_cause`, `affected_loop`, `outcome = failure` |
| **Attribution requirements** | `correlation_id` generated at cycle start even on precondition failure; `config_version_id` or `null` annotated |
| **Idempotency guarantees** | Idempotency key logged even on failure so recovery cycle can be keyed to same cycle_id |

---

### 2.2 Provider Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | GHL API failures, workflow execution failures, webhook failures, delayed response failures — governed by `directives/ghl_integration_contract.md` |
| **Recovery philosophy** | Provider failures are contained at the provider governance boundary; outbound dispatch is blocked when `ProviderOrchestrationAssessment.governance_scope ≠ AUTHORIZED`; circuit breaker state governs retry authorization; provider-level retries are distinct from orchestration-level retry cycles |
| **Replay behavior** | Historical provider interactions sourced from `processed_events` and `ghl_messages` exclusively; no live GHL calls during replay; failure simulations produce SHADOW-only diagnostics |
| **SHADOW behavior** | Provider assessment evaluated; outbound suppressed; failure logged with `outcome = shadow_only` |
| **LIVE behavior** | Circuit breaker checks precede dispatch delegation; circuit OPEN blocks dispatch; escalation candidacy generated; `PROVIDER_OUTAGE` structured event emitted |
| **Observability requirements** | `failure_domain = provider`, `provider_name`, `error_class`, `http_status_code`, `circuit_breaker_state`, `correlation_id`, `ghl_message_id` (if available) |
| **Attribution requirements** | `correlation_id` from orchestration cycle; `causation_id` from originating OrchestrationIntent; `provider_event_type` from ProviderOrchestrationAssessment |
| **Idempotency guarantees** | `processed_events` dedup gate prevents duplicate execution on provider failure and retry; idempotency key `(student_id, checkpoint_type, contact_attempt)` |

**Prohibited patterns in provider failure handling:**
* Constructing direct GHL API retry calls from resilience layer (AP-FP1)
* Silent provider fallback to alternate channel without governance authorization (AP-FP4)
* Consuming a student's retry budget for attempts blocked by provider outage (AP-FP12; governed by `outreach_retry_policy.md`)

---

### 2.3 AI Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | LLM API failures, invalid response structures, schema validation failures, timeout failures, hallucination detection, partial output failures — governed by `directives/llm_processing_contract.md` |
| **Recovery philosophy** | AI is advisory-only; AI failure never blocks orchestration; AI advisory absence is a scope restriction, not a blocking failure; rule-based evaluation proceeds when AI is unavailable (AP-AI3) |
| **Replay behavior** | No live AI inference in replay; FINALIZED_COPY sourced exclusively from `warehouse.snapshot_ai_narratives`; non-finalized records sourced from `ai_insights` table at historical timestamp; `ai_blocked = true` in replay context |
| **SHADOW behavior** | AI failure logged with `outcome = shadow_only`; orchestration not blocked in SHADOW mode |
| **LIVE behavior** | AI failure produces `ai_governance_tier = UNAVAILABLE`; advisory scope blocked; rule-based evaluation only; `AI_PROVIDER_UNAVAILABLE` event emitted; stale AI served if within `ai_insight_ttl_hours` |
| **Observability requirements** | `failure_domain = ai`, `ai_governance_tier`, `ai_failure_class` (one of: `TIMEOUT`, `INVALID_STRUCTURE`, `SCHEMA_MISMATCH`, `HALLUCINATION_DETECTED`, `PARTIAL_OUTPUT`, `PROVIDER_UNAVAILABLE`), `retry_count`, `fallback_scope` |
| **Attribution requirements** | `ai_version_number`, `prompt_version`, `model_used` in failure record; `correlation_id` from orchestration cycle |
| **Idempotency guarantees** | AI refresh keyed on `(student_id, insight_type, date_period, prompt_version)`; duplicate refresh requests are no-ops |

**Prohibited patterns in AI failure handling:**
* Allowing AI failure to block orchestration cycle (AP-FP9)
* Substituting a silent rule-based default without logging the AI governance tier (AP-FP4)
* Treating AI advisory absence as a system-level failure requiring escalation (AP-FP9)
* Using STALE AI to independently drive LIVE escalation (AP-AI11 from `system_loop.md` §9.2)

---

### 2.4 Scheduler Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Missed execution cycles, duplicate execution triggers, partial execution, scheduler crash, time drift — governed by `runtime/scheduler_design.md` §4.1–§4.10 and `system_loop.md` §10.5 |
| **Recovery philosophy** | Recovery cycles carry full attribution (`execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`); recovery is idempotent — keyed to same cycle_id as missed cycle; "trigger recovery execution" is not a permitted semantic — recovery is governed recovery orchestration coordination |
| **Replay behavior** | Scheduler failure records preserved; recovery cycles themselves may be replayed; `execution_type = recovery` and `execution_type = replay` are distinct and may not be conflated |
| **SHADOW behavior** | Scheduler lag detected; recovery cycle evaluated in SHADOW mode if system is in SHADOW |
| **LIVE behavior** | Lag detection triggers recovery orchestration cycle with full attribution; persistent lag generates escalation candidacy |
| **Observability requirements** | `failure_domain = scheduler`, `expected_trigger_time`, `actual_trigger_time`, `lag_duration_ms`, `recovery_cycle_id`, `execution_type = recovery`, `correlation_id` |
| **Attribution requirements** | `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by` in recovery cycle record |
| **Idempotency guarantees** | Recovery cycle uses same idempotency key as missed cycle; duplicate processing blocked; already-processed records skipped via `processed_events` gate |

**Prohibited patterns in scheduler failure handling:**
* "Trigger recovery execution immediately" as a direct execution instruction (AP-FP4)
* Recovery cycle without attribution annotation (`recovery_of_cycle_date` missing) (AP-FP6)
* Duplicate recovery cycles for the same missed cycle window (AP-FP11)

---

### 2.5 Replay Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Replay authorization failures, historical config resolution failures, `state_transition_log` read failures, fingerprint comparison failures, partial replay execution |
| **Recovery philosophy** | Replay failures emit SHADOW-only diagnostics; no recovery path should produce LIVE effects; `replay_partial = true` annotated when historical data is incomplete |
| **Replay behavior** | Replay failure is itself a replay event; replay loop emits failure diagnostic with `source_artifact_id`, `fingerprint_comparison_outcome = UNKNOWN`, `replay_partial = true` |
| **SHADOW behavior** | All replay is SHADOW-mode by definition; failure scoped to `execution_type = replay` |
| **LIVE behavior** | No LIVE behavior during replay; LIVE mode may not be entered from replay context |
| **Observability requirements** | `failure_domain = replay`, `source_artifact_id`, `historical_config_version_id`, `replay_failure_cause`, `replay_partial` |
| **Attribution requirements** | `source_artifact_id` required; `historical_config_version_id` or null if resolution failed |
| **Idempotency guarantees** | Replay is inherently read-only; no idempotency key consumption during replay |

---

### 2.6 Regeneration Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Report re-render failures from FINALIZED snapshot data; warehouse read failures during regeneration; lineage resolution failures |
| **Recovery philosophy** | Regeneration failure emits structured log and stops for the affected record; no retry within regeneration mode; no warehouse mutation on failure; failed regeneration does not corrupt existing published report |
| **Replay behavior** | Regeneration is not replay; regeneration does not simulate orchestration decisions; failures do not produce replay diagnostics |
| **SHADOW behavior** | Regeneration may run in any mode; output tagged `execution_type = regeneration`; no LIVE dispatch |
| **LIVE behavior** | Regeneration re-renders reports; no outbound provider calls; no state transitions |
| **Observability requirements** | `failure_domain = regeneration`, `source_artifact_id`, `lineage_version`, `regeneration_failure_cause`, `output_identical = false` |
| **Attribution requirements** | `source_artifact_id`, `lineage_version` required |
| **Idempotency guarantees** | Regeneration creates new version lineage; does not overwrite existing published report (AP-FP7) |

---

### 2.7 Synchronization Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | SQL Server sync lag exceeded, SQL Server connection failures, data integrity failures from upstream source — governed by `system_loop.md` §10.7 and §4.7 |
| **Recovery philosophy** | Sync failures annotate affected records; orchestration continues with `STALE_SQL_SERVER_DATA` annotation; persistent sync failures generate escalation candidacy; no silent degradation |
| **Replay behavior** | Sync failure records available in replay; historical sync state sourced from `state_transition_log` at historical timestamp |
| **SHADOW behavior** | Sync lag annotated; orchestration continues with annotation |
| **LIVE behavior** | `sql_server_max_sync_age_hours` threshold check against Config V2 Group K; `STALE_SQL_SERVER_DATA` annotation on affected students; `SQL_SERVER_UNAVAILABLE` event emitted on connection failure |
| **Observability requirements** | `failure_domain = synchronization`, `sync_lag_hours`, `sql_server_max_sync_age_hours_applied`, `affected_student_count`, `sync_failure_cause` |
| **Attribution requirements** | `sync_cycle_id`, `correlation_id` from orchestration cycle |
| **Idempotency guarantees** | Sync operations are read-only for SQL Server; write authority is PostgreSQL-exclusive; no duplicate state writes from sync failures |

---

### 2.8 Observability Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Structured log pipeline failures, telemetry write failures, observability pipeline degradation |
| **Recovery philosophy** | Observability failure does not block orchestration; structured logs that fail to write are directed to stderr with `OBSERVABILITY_DEGRADED` flag; the failure is itself observable |
| **Replay behavior** | Observability failure does not suppress replay diagnostic emission; replay diagnostics written to stderr if pipeline degraded |
| **SHADOW behavior** | Observability failure in SHADOW mode: directed to stderr; loop continues |
| **LIVE behavior** | `OBSERVABILITY_DEGRADED` event emitted to stderr; orchestration loop continues; escalation candidacy generated for persistent observability degradation |
| **Observability requirements** | `failure_domain = observability`, `pipeline_stage`, `failure_cause`, directed to stderr |
| **Attribution requirements** | Minimal attribution preserved in stderr record: `correlation_id`, `timestamp`, `loop_name` |
| **Idempotency guarantees** | Observability writes are independent of business state; no idempotency concern for log writes themselves |

---

### 2.9 Attribution Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Missing `correlation_id`, missing `causation_id` on derived records, broken lineage chain, orphaned orchestration cycles |
| **Recovery philosophy** | Attribution failure is a specification defect; affected records are flagged `attribution_incomplete = true`; no silent continuation with broken attribution; escalation candidacy generated |
| **Replay behavior** | Replay requires full attribution chain for fingerprint comparison; attribution failure produces `fingerprint_comparison_outcome = UNKNOWN` with `attribution_incomplete = true` |
| **SHADOW behavior** | Attribution failure logged with SHADOW scope; flagged for review |
| **LIVE behavior** | `ATTRIBUTION_FAILURE` event emitted; affected cycle annotated; escalation candidacy generated; cycle not aborted unless precondition gate fails |
| **Observability requirements** | `failure_domain = attribution`, `missing_field`, `affected_record_id`, `attribution_incomplete = true` |
| **Attribution requirements** | Attribution failure record must itself carry `correlation_id` from the cycle even if downstream records are missing it |
| **Idempotency guarantees** | Attribution failure records are append-only; no retroactive lineage repair that mutates existing records (AP-FP7) |

---

### 2.10 Compliance Execution Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Compliance hold activation failures, pre-action audit gate failures, compliance state transition conflicts — governed by `spec/09_security_privacy.md` |
| **Recovery philosophy** | Compliance failures are hard stops for affected records; outbound dispatch is blocked; no silent degradation; escalation candidacy mandatory |
| **Replay behavior** | Compliance hold records are immutable; replay reads historical compliance state; no compliance hold modifications during replay |
| **SHADOW behavior** | Compliance hold assessment logged; no LIVE dispatch in SHADOW mode regardless of compliance state |
| **LIVE behavior** | Compliance hold active → `COMPLIANCE_HOLD_DISPATCH_BLOCKED` per affected student; other students in cycle unaffected |
| **Observability requirements** | `failure_domain = compliance`, `student_id`, `compliance_hold_type`, `dispatch_blocked = true`, `correlation_id` |
| **Attribution requirements** | Compliance hold activation record with `actor_identity`, `authorization_timestamp`, `correlation_id` |
| **Idempotency guarantees** | Compliance workflow: one active workflow per student; audit records are append-only; terminal states irreversible |

---

## 3. FAILURE AUTHORITY BOUNDARIES

---

### 3.1 What the Resilience Layer Coordinates

| Responsibility | Resilience layer owns | Resilience layer does NOT own |
|---|---|---|
| Failure classification and routing | Yes | Defining business-level eligibility or retry thresholds (directives own those) |
| Recovery cycle attribution generation | Yes | Executing recovery orchestration (orchestration services own this) |
| Degradation state coordination | Yes | Mode transition authority (Governance/Operational Administrator owns this) |
| Observability emission for failure events | Yes | Implementing telemetry pipelines or alerting infrastructure |
| Circuit breaker signal consumption | Yes | Owning circuit breaker state (provider governance services own this) |
| Escalation candidacy generation for failures | Yes | Escalation routing to human operators (escalation routing service owns this) |
| Dead-letter record coordination | Yes | Dead-letter retry infrastructure implementation |

---

### 3.2 Provider Authority Restrictions

The resilience layer never escalates provider authority:

* Providers remain `platform_supplementary` during failures — failure does not grant providers additional governance scope
* Provider outage does not authorize alternative direct dispatch from resilience layer (AP-FP1)
* Provider recovery does not bypass normal governance authorization checks (AP-FP8)
* No provider interaction may be initiated by the resilience layer directly

---

### 3.3 AI Authority Restrictions

The resilience layer never expands AI advisory authority during failures:

* AI is advisory-only in all failure and degradation contexts (AP-FP9)
* AI failure does not trigger escalation of AI authority to decision-making role
* AI advisory absence during degradation: rule-based evaluation proceeds; AI absence is annotated
* FINALIZED_COPY records are never re-evaluated during AI failure — they remain immutable

---

### 3.4 Replay Authority Restrictions

The resilience layer does not grant LIVE authority to replay-mode recovery:

* A failure detected during replay simulation produces no LIVE recovery effect (AP-FP2)
* Replay recovery outputs are always `execution_type = replay`, `governance_scope = REPLAY_ONLY`
* No mode transition from REPLAY to LIVE is permitted within a resilience recovery sequence (AP-FP8)

---

## 4. DETERMINISTIC DEGRADATION GOVERNANCE

---

### 4.1 Degradation Principles

Degradation is observable, not silent. Inherited verbatim from `runtime/system_loop.md` §10.1:

Every degraded runtime state must:
* Emit a structured log entry with `degradation_cause`, `affected_domains`, and `outcome = partial` or `outcome = failure`
* Produce an observable escalation candidacy signal for human awareness
* Describe what operations continued and what operations were blocked
* Never silently swallow a failure or substitute a silent default

The following patterns are prohibited (AP-FP3, AP-FP4, AP-FP5):
* `try { ... } catch (e) {}` semantics — swallowing an error without logging
* Falling back to a hardcoded default when a Config V2 threshold is missing
* Retrying indefinitely without an upper bound from Config V2

---

### 4.2 Provider Outage Degradation

When a provider outage is detected:

* **Outbound dispatch** — blocked for all students in the current cycle; `governance_scope = UNAVAILABLE`; escalation candidacy generated for provider failure
* **Inbound webhook ingestion** — continues normally; webhooks received during provider outage are ingested and attributed; no state transitions produced without governance authorization
* **SQL Server platform reads** — unaffected
* **AI evaluation** — unaffected
* **Retry budget protection** — retry attempts blocked by provider outage are not consumed from the student's retry budget; `provider_outage_exempted = true` annotation required (governed by `outreach_retry_policy.md`; see `runtime/retry_cycle_flow.md` UE-RF4)

---

### 4.3 AI Provider Outage Degradation

When the AI provider is unavailable:

* **AI refresh orchestration** — blocked for new requests; circuit breaker state updated
* **Orchestration evaluation** — proceeds with rule-based evaluation only; AI advisory scope = UNAVAILABLE
* **Snapshot finalization** — not blocked; `ai_content_stale = true` flag set
* **Escalation candidacy** — rule-based severity assessment applies; AI advisory absence is annotated
* **FINALIZED_COPY records** — unaffected; sourced from warehouse regardless of AI provider state

---

### 4.4 Scheduler Outage Degradation

When scheduler lag is detected (expected cycle with no completion record within governed window):

* Lag detection compares expected trigger time (governed by Config V2 Group A `outreach_daily_trigger_hour_cst`) against last recorded cycle completion timestamp
* Missed cycle triggers a **governed recovery orchestration cycle** with `execution_type = recovery`
* Recovery cycle carries full attribution: `recovery_of_cycle_date`, `lag_detected_at`, `recovery_initiated_by`
* Recovery cycle is idempotent — same idempotency key as missed cycle; duplicate processing blocked
* Scheduler lag persisting beyond governance-defined bounds generates escalation candidacy

---

### 4.5 Synchronization Lag Degradation

When SQL Server sync lag exceeds `sql_server_max_sync_age_hours` from Config V2 Group K:

* Affected student records annotated with `stale_sql_server_data = true`
* Orchestration evaluation does not block — annotated decisions carry `STALE_SQL_SERVER_DATA` annotation
* Persistent sync backlog generates escalation candidacy if lag exceeds governance-defined threshold
* Recovery: sync loop retries; sync recovery does not require special recovery cycle

---

### 4.6 Config Threshold Missing Degradation

When a required Config V2 threshold cannot be resolved:

* `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning emitted
* Affected loop annotated DEGRADED for that cycle
* Loop continues with degraded annotation — does not abort
* Persistent missing threshold generates escalation candidacy
* Substituting a hardcoded fallback value (bypassing UNKNOWN_V0 substitution) is prohibited (AP-FP5)

---

### 4.7 Duplicate Event Storm Degradation

Inbound webhook duplicate events are absorbed by the deduplication gate in `ghl_integration_contract.md` RULE 6:

* `processed_events` dedup lookup occurs before any state management service call
* All duplicate detections produce an audit log entry — no silent drops
* Duplicate event storms do not degrade outbound orchestration domains
* `DUPLICATE_EVENT_STORM` event emitted with dedup count when storm threshold exceeded

---

## 5. REPLAY & REGENERATION FAILURE SEMANTICS

---

### 5.1 Replay Failure Governance

When the resilience layer operates in REPLAY mode (`execution_type = replay`), failure behavior is constrained:

* Replay may simulate historical failure scenarios from `state_transition_log` records
* Replay may not generate LIVE recovery effects from historical failure simulation
* Historical failure records are read-only reference points; replay does not re-execute historical recovery actions
* Replay failure diagnostics carry `governance_scope = REPLAY_ONLY`; they may not be consumed as LIVE recovery signals
* `fingerprint_comparison_outcome = MATCH | DIVERGENT | UNKNOWN` emitted for simulated vs historical failure behavior

---

### 5.2 Replay Recovery Restrictions

The following LIVE effects are suppressed in all replay recovery contexts:

| Effect category | Suppression mechanism |
|---|---|
| Outbound provider dispatch from recovery | `ProviderOrchestrationAssessment.outbound_suppressed = true` |
| Live AI inference during replay failure simulation | `AIAssessment.ai_blocked = true`; FINALIZED_COPY sourced from warehouse |
| State transitions during replay recovery simulation | Replay Services hold no state write authority (AP-OWN2) |
| Escalation routing during replay | `REPLAY_ESCALATION_CANDIDATE` scope; no live operator routing |
| Warehouse mutations during replay | Replay reads warehouse; does not write (AP-OWN15) |

---

### 5.3 Historical Recovery Visibility

In REPLAY mode:

* Historical failure records are sourced from `state_transition_log` at historical timestamps — not from live counters
* Historical config version resolved from `historical_config_version_id` at time of original failure
* Historical AI content sourced from `warehouse.snapshot_ai_narratives` (FINALIZED) or `ai_insights` (non-finalized) at historical timestamp
* Replay may not generate new AI content to substitute for historically unavailable AI
* `replay_partial = true` annotated when historical failure data is incomplete

---

### 5.4 Regeneration Failure Semantics

Regeneration failures (re-render from FINALIZED snapshot data) are distinct from replay failures:

* Regeneration creates new version lineage — it does not overwrite the original published report
* Regeneration failure does not corrupt existing REPORT_PUBLISHED state (AP-FP7)
* No live inference, no state transitions, no provider calls during regeneration failure recovery
* Failed regeneration job records are append-only; recovery requires a new governed regeneration job

---

## 6. FAILURE STATE GOVERNANCE

---

### 6.1 State Authority During Failures

The resilience layer does not own state transitions. State write authority is externalized to the state management service in all failure scenarios:

| Failure scenario | State coordination | Resilience layer role |
|---|---|---|
| Provider dispatch failure | State remains at pre-dispatch state (e.g., `QUEUED`) | Produces structured failure log; coordinates escalation candidacy |
| Provider webhook missing (timeout) | State management service transitions to `NO_RESPONSE` after timeout | Coordinates timeout detection signal; does not write transition directly |
| AI failure during evaluation | No state change required | Annotates advisory absence; orchestration proceeds |
| Scheduler missed cycle | No state change for students (processing deferred) | Recovery cycle coordination with full attribution |
| Duplicate execution detected | No state change | `DUPLICATE_SUPPRESSED` scope logged; execution blocked |
| Config threshold missing | No state change for students | DEGRADED annotation on cycle; loop continues |
| Compliance hold active | No dispatch state written | `COMPLIANCE_HOLD_DISPATCH_BLOCKED` per student |

---

### 6.2 Immutable Record Protections During Recovery

Recovery orchestration must never mutate:

* `warehouse.student_snapshots` — FINALIZED state is irreversible (AP-OWN15, AP-FP7)
* `warehouse.snapshot_ai_narratives` — FINALIZED_COPY is immutable; recovery does not re-render narrative content
* `warehouse.monthly_reports` — REPORT_PUBLISHED is immutable; recovery does not overwrite published reports
* `state_transition_log` — append-only; recovery produces new entries, not retroactive corrections
* `student_timeline_events` — append-only; recovery intent records are new entries, not mutations

---

### 6.3 Eligibility and Retry Policy During Failures

The resilience layer coordinates eligibility assessment during degraded operation:

* Eligibility assessment (`outreach_eligibility_rules.md`) remains directive-owned even during failures
* Retry policy assessment (`outreach_retry_policy.md`) remains directive-owned even during failures
* Resilience layer receives `EligibilityAssessment` and `RetryPolicyAssessment` outputs — it does not re-implement these directives (AP-FP10)
* During AI outage: rule-based evaluation proceeds; AI advisory absence annotated; eligibility not blocked

---

## 7. RECOVERY ORCHESTRATION COORDINATION

---

### 7.1 Governed Recovery Coordination Model

The V1 pattern:

> "Trigger recovery execution immediately" and "Process missed workload"

is replaced with:

> **Governed Recovery Orchestration Coordination** — the resilience layer produces a `RecoveryOrchestrationRecord` with `execution_type = recovery`, links it to the missed cycle via `recovery_of_cycle_date`, and coordinates the recovery cycle through the same governance-authorized orchestration sequence as the original missed cycle

Recovery coordination model:

```
FAILURE DETECTION  →  structured failure log emitted
  ↓
RECOVERY AUTHORIZATION GATE  →  execution_mode, config_version_id, correlation_id validated
  ↓
IDEMPOTENCY CHECK  →  same cycle_id key checked; if already recovered, no-op
  ↓
RECOVERY CYCLE ATTRIBUTION  →  recovery_of_cycle_date, lag_detected_at, recovery_initiated_by annotated
  ↓
RECOVERY ORCHESTRATION DELEGATION  →  governed orchestration sequence (same as normal cycle)
  ↓
OBSERVABILITY EMISSION  →  recovery cycle completion record
```

---

### 7.2 Config V2-Governed Recovery Thresholds

Recovery behavior is governed by Config V2, not by hardcoded values:

| Recovery threshold | Config V2 source | Group |
|---|---|---|
| Retry attempt ceiling | `outreach_max_retry_attempts` | A |
| Retry window cadence | `outreach_retry_window_days` | A |
| Sync lag tolerance | `sql_server_max_sync_age_hours` | K |
| AI insight freshness | `ai_insight_ttl_hours` | H |
| Daily trigger hour | `outreach_daily_trigger_hour_cst` | A |

No hardcoded recovery thresholds are permitted. Substituting a literal integer for any of these values in failure handling logic is a specification defect (AP-FP5).

---

### 7.3 Dead-Letter Governance

Failed operations that cannot be recovered by normal retry coordination are directed to dead-letter:

* Dead-letter record carries full attribution: `correlation_id`, `causation_id`, `failure_domain`, `failure_cause`, `original_operation`, `attempt_count`
* Dead-letter records are append-only; no silent discard
* Dead-letter records produce escalation candidacy for human review
* Recovery from dead-letter requires a new governed cycle with `execution_type = recovery` — not a direct re-execution

---

## 8. ATTRIBUTION & OBSERVABILITY

---

### 8.1 Failure Attribution Lineage Chain

Every failure record must carry a complete attribution lineage:

```
Config V2 governance  →  config_version_id + relevant threshold keys
  ↓
Orchestration cycle  →  correlation_id + cycle_id + execution_mode
  ↓
Originating OrchestrationIntent  →  causation_id (if derived from prior intent)
  ↓
Failure event  →  failure_domain + failure_cause + error_class
  ↓
Recovery record (if applicable)  →  recovery_of_cycle_date + recovery_initiated_by
  ↓
Dead-letter or escalation candidacy  →  escalation_type + escalation_severity
```

A failure that cannot be traced from symptom back to root cause using a single `correlation_id` is an observability defect (spec/06).

---

### 8.2 Causation Propagation in Recovery

Every recovery action must propagate causation lineage:

* Recovery cycle links to the original missed cycle via `recovery_of_cycle_date`
* Recovery intents carry `causation_id` referencing the original `OrchestrationIntent` where applicable
* Recovery observability records carry `execution_type = recovery` and `correlation_id` from the recovery cycle
* Recovery records are not retroactively attributed to the original cycle's `correlation_id` — they carry the recovery cycle's own `correlation_id`

---

### 8.3 Replay Diagnostics

Replay recovery diagnostics must carry:

| Field | Specification |
|---|---|
| `source_artifact_id` | ID of the original cycle or event being replayed |
| `historical_config_version_id` | Config version at time of original failure |
| `fingerprint_comparison_outcome` | `MATCH \| DIVERGENT \| UNKNOWN` |
| `replay_partial` | `true` if historical data was incomplete |
| `execution_type` | `replay` |
| `governance_scope` | `REPLAY_ONLY` |

---

### 8.4 Recovery Audit Continuity

All recovery actions produce observable, auditable records:

* Recovery action records are append-only — no retroactive updates to prior records
* Every recovery action is attributable to an `actor_identity` (`system` for automated; named for operator-initiated)
* Recovery audit records are preserved in `student_timeline_events` with `execution_type = recovery`
* Resilience layer does not produce audit records that contradict the append-only record of prior events

---

## 9. FAILURE IDEMPOTENCY GUARANTEES

---

### 9.1 Core Idempotency Principle

Every recovery operation in the resilience layer must satisfy the idempotency principle inherited from `spec/04_idempotency_concurrency.md` §2.1:

> Repeated operations MUST NOT create duplicate effects. Same request → same outcome. Same input + same state → same persisted result; no first-run/second-run divergence.

---

### 9.2 Domain-Specific Idempotency Keys

| Domain | Idempotency key | Behavior on duplicate |
|---|---|---|
| Outreach dispatch recovery | `(student_id, checkpoint_type, contact_attempt)` | Duplicate → no-op; `DUPLICATE_SUPPRESSED` logged |
| Scheduler recovery cycle | `(cycle_date, execution_type = recovery, config_version_id)` | Duplicate recovery cycle → no-op |
| AI refresh recovery | `(student_id, insight_type, date_period, prompt_version)` | Duplicate refresh → no-op |
| Snapshot finalization recovery | `(student_id, snapshot_month)` | FINALIZED is irreversible; no re-finalization |
| Report regeneration | New version lineage created | Does not overwrite existing REPORT_PUBLISHED |
| Compliance hold activation | One active workflow per student | Duplicate hold activation → idempotent hold confirmation |

---

### 9.3 Idempotency Violations Are Production Defects

An operation that "works once but produces duplicate effects on the second run" is not "fragile" — it is broken. Idempotency violations in recovery paths must be fixed before the change ships. The following patterns are idempotency defects:

* Recovery that sends a second GHL dispatch without checking `processed_events` first
* Recovery cycle that re-processes already-processed students without checking their idempotency key
* AI refresh recovery that overwrites a FINALIZED_COPY record in `warehouse.snapshot_ai_narratives`
* State transition retry that writes a duplicate state record without deduplication

---

## 10. DETERMINISTIC DEGRADATION CONDITION TABLE

---

### 10.1 Canonical Degradation Conditions

Inherited from `runtime/system_loop.md` §10.2 with resilience-layer annotations:

| Condition | Affected domains | Runtime behavior | Orchestration continues | Resilience escalation |
|---|---|---|---|---|
| Provider circuit breaker OPEN | Provider (§2.2) | Outbound dispatch blocked; `governance_scope = UNAVAILABLE` | Yes | `CIRCUIT_BREAKER_OPEN` + escalation candidacy |
| Provider outage active | Provider (§2.2) | Same as circuit open; retry budget protected | Yes | `PROVIDER_OUTAGE` + degradation onset record |
| AI provider unavailable | AI (§2.3) | AI refresh blocked; rule-based evaluation only | Yes | `AI_PROVIDER_UNAVAILABLE` + stale AI annotation |
| SQL Server sync lag exceeded | Sync (§2.7) | `STALE_SQL_SERVER_DATA` annotation; orchestration continues | Yes | `SYNC_LAG_EXCEEDED` event |
| SQL Server connection failed | Sync (§2.7) | Sync blocked for cycle; last successful sync data used | Yes (stale annotation) | `SQL_SERVER_UNAVAILABLE` + escalation candidacy |
| Scheduler lag detected | Scheduler (§2.4) | Missed cycle detection; governed recovery cycle triggered | Yes (recovery) | `SCHEDULER_LAG_DETECTED` + recovery attribution |
| Duplicate event storm | Provider inbound (§2.2) | Dedup gate absorbs; `DUPLICATE_SUPPRESSED` scope | Yes | `DUPLICATE_EVENT_STORM` + dedup count |
| Config threshold missing | All domains | `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning | Yes (DEGRADED annotation) | `CONFIG_THRESHOLD_MISSING` per key |
| Observability pipeline degraded | All domains | Loops continue; `OBSERVABILITY_DEGRADED` to stderr | Yes | Direct stderr alert |
| Compliance hold active (batch) | Provider (§2.10) | Outbound dispatch blocked for affected student | Yes (others unaffected) | `COMPLIANCE_HOLD_DISPATCH_BLOCKED` per student |
| Warehouse write failure | Sync (§2.7), Attribution (§2.9) | Loop fails for affected record; dead-letter | No (that record) | `WAREHOUSE_WRITE_FAILURE` + dead-letter |
| Retry starvation detected | Retry orchestration | All retry candidates within window; cycle completes normally | Yes | `RETRY_STARVATION_DETECTED` flag; escalation candidacy if persistent (UE-RF3) |
| AI advisory absent in DEGRADED retry | AI (§2.3), Retry | Rule-based evaluation only; AI absence annotated | Yes | `AI_ADVISORY_ABSENT_DEGRADED` annotation (UE-RF5) |

---

## 11. RESILIENCE OBSERVABILITY SCHEMA

---

### 11.1 Structured Failure Log Record

Every failure event must emit a structured JSON record:

```json
{
  "timestamp": "ISO-8601",
  "level": "warn | error",
  "service": "resilience_orchestration",
  "event": "failure_detected",
  "failure_domain": "orchestration | provider | ai | scheduler | replay | regeneration | synchronization | observability | attribution | compliance",
  "correlation_id": "uuid",
  "causation_id": "uuid | null",
  "execution_mode": "SHADOW | LIVE | REPLAY | REGENERATION | DEGRADED | MAINTENANCE",
  "execution_type": "original | replay | regeneration | recovery",
  "config_version_id": "string | null",
  "failure_cause": "string",
  "error_class": "TimeoutError | RateLimitError | AuthError | ValidationError | UpstreamUnavailable | ContractViolation | AttributionFailure | IdempotencyViolation | ComplianceHold | ConfigThresholdMissing | string",
  "affected_student_id": "uuid | null",
  "affected_loop": "string | null",
  "recovery_action": "governed_recovery_cycle | dead_letter | degraded_continuation | escalation_candidacy | no_op",
  "recovery_of_cycle_date": "YYYY-MM-DD | null",
  "degradation_flags": [],
  "idempotency_key": "string | null",
  "outcome": "failure | partial | degraded"
}
```

---

### 11.2 Recovery Cycle Completion Record

A governed recovery cycle emits the same completion record as a normal cycle with additional recovery attribution fields:

```json
{
  "timestamp": "ISO-8601",
  "level": "info",
  "service": "resilience_orchestration",
  "event": "recovery_cycle_complete",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | DEGRADED",
  "execution_type": "recovery",
  "config_version_id": "string",
  "recovery_of_cycle_date": "YYYY-MM-DD",
  "lag_detected_at": "ISO-8601",
  "recovery_initiated_by": "system | operator_id",
  "recovery_candidates_processed": 0,
  "recovery_skipped_already_processed": 0,
  "recovery_failed_count": 0,
  "duration_ms": 0,
  "outcome": "success | partial | failure"
}
```

---

## 12. ARCHITECTURE PRESERVATION RULES

---

### AP-FP1 — No Direct Provider Execution Recovery

MUST NOT allow any step in the resilience layer to directly call a provider API, construct a GHL payload, initiate an SMS or email dispatch, or trigger a webhook. All provider interactions remain delegated to provider orchestration services under governance authorization. Violation is a specification defect.

### AP-FP2 — No Replay-Triggered LIVE Recovery

MUST NOT allow replay-mode failure simulation to generate LIVE recovery effects. All outputs from replay-mode resilience evaluation carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`. No mode transition from REPLAY to LIVE occurs within a resilience sequence.

### AP-FP3 — No "Retry Immediately" Semantics

MUST NOT use "retry immediately (once)" or equivalent as a recovery instruction. Recovery retry behavior is governed by Config V2 Group A thresholds. No hardcoded retry-once pattern is permitted in any failure domain.

### AP-FP4 — No Silent Fallback Execution

MUST NOT silently fall back to a default recovery behavior without emitting a structured failure log. Hidden degradation mode switching, undocumented rule-based substitution, and silent channel downgrade are prohibited.

### AP-FP5 — No Hardcoded Recovery Thresholds

MUST NOT substitute hardcoded values for Config V2-governed recovery thresholds (`outreach_max_retry_attempts`, `outreach_retry_window_days`, `sql_server_max_sync_age_hours`, `ai_insight_ttl_hours`). When thresholds are missing, `UNKNOWN_V0` substitution applies with DEGRADED annotation (not a hardcoded integer fallback).

### AP-FP6 — No Non-Attributable Recovery Actions

MUST NOT allow any recovery action without `correlation_id`, `execution_mode`, `execution_type`, and `config_version_id`. Recovery actions without complete attribution are orphaned — they are specification defects, not acceptable approximations.

### AP-FP7 — No Immutable Record Mutation

MUST NOT overwrite, backfill, or retroactively modify any record in `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `warehouse.monthly_reports`, `state_transition_log`, or `student_timeline_events`. All recovery actions produce new append-only records.

### AP-FP8 — No Governance Bypass During Recovery

MUST NOT bypass eligibility assessment, retry policy assessment, config version validation, or execution mode checks during recovery orchestration. Recovery cycles are subject to the same governance precondition gate as normal cycles.

### AP-FP9 — No AI Authority Escalation During Failure

MUST NOT expand AI advisory scope during degraded operation. AI remains advisory-only. AI failure does not elevate AI to decision-making authority. AI absence during failures is annotated and rule-based evaluation proceeds.

### AP-FP10 — No Directive Re-Implementation

MUST NOT re-implement the logic of `outreach_eligibility_rules.md`, `outreach_retry_policy.md`, `channel_selection_rules.md`, `core_decision_engine.md`, `escalation_rules.md`, or `ghl_integration_contract.md` within the resilience layer. Resilience layer consumes structured assessment objects from these directives.

### AP-FP11 — No Duplicate Recovery Cycles

MUST NOT produce duplicate recovery cycles for the same missed execution window. Recovery cycle idempotency key `(cycle_date, execution_type = recovery, config_version_id)` must be checked before initiating recovery. Duplicate recovery cycle → no-op.

### AP-FP12 — No Retry Budget Consumption on Provider Outage

MUST NOT consume a student's retry budget for attempts that were blocked by provider outage. Retry budget protection (`provider_outage_exempted = true`) is required when provider unavailability blocked dispatch.

### AP-FP13 — No PII in Resilience Observability Records

MUST NOT log raw PII (student name, email, phone number, academic transcript content) in resilience orchestration structured log records. `student_id` (UUID) is the permitted reference.

### AP-FP14 — No Silent Error Swallowing

MUST NOT use `try { ... } catch (e) {}` semantics anywhere in the resilience layer. Every caught exception is tagged with a stable `error_class` string and emitted as a structured log before any fallback or continuation path is taken.

### AP-FP15 — No Orphaned Recovery Execution

MUST NOT allow a recovery execution to proceed without a completion record written to `student_timeline_events` — even on failure. Every recovery cycle has an observable start and an observable end.

---

## 13. ACCEPTANCE CRITERIA

---

### AC-FP1 — Deterministic Resilience Behavior

**Given** any failure condition defined in §10.1
**When** the resilience orchestration layer processes the failure
**Then** the outcome is deterministic: the same failure input produces the same structured failure log, the same recovery action classification, and the same escalation candidacy signal — with no undocumented variation between runs

---

### AC-FP2 — Replay-Safe Recovery Behavior

**Given** a replay-mode resilience evaluation of a historical failure
**When** the failure simulation completes
**Then** no LIVE recovery effects are produced; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; `fingerprint_comparison_outcome` is emitted

---

### AC-FP3 — Immutable Lineage Preservation

**Given** a recovery cycle completes
**When** any record is written
**Then** no existing record in `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `state_transition_log`, or `student_timeline_events` is modified; only new append-only records are produced

---

### AC-FP4 — Degraded-Mode Safety

**Given** provider outage is active
**When** an orchestration cycle runs
**Then** outbound dispatch is blocked for all affected students with `governance_scope = UNAVAILABLE`; no student's retry budget is consumed for outage-blocked attempts; AI evaluation and inbound webhook ingestion continue unaffected

---

### AC-FP5 — Attribution Continuity

**Given** any recovery action is taken
**When** the recovery record is written
**Then** `correlation_id`, `causation_id` (where applicable), `execution_mode`, `execution_type = recovery`, and `config_version_id` are present on every record; a failure that cannot be traced to root cause via a single `correlation_id` is an observability defect

---

### AC-FP6 — Provider Failure Containment

**Given** a GHL API failure or webhook failure occurs
**When** the resilience layer processes the failure
**Then** no direct provider retry is attempted from the resilience layer; circuit breaker state is consulted; structured failure log is emitted; `governance_scope = UNAVAILABLE` blocks dispatch; no silent fallback to alternate channel without governance authorization

---

### AC-FP7 — Idempotent Recovery Orchestration

**Given** the same recovery cycle is triggered twice (e.g., duplicate scheduler lag detection)
**When** the second recovery cycle is evaluated
**Then** the idempotency key check returns a match; the second recovery is a no-op; `DUPLICATE_SUPPRESSED` is logged; no duplicate state transitions or outreach dispatches are produced

---

### AC-FP8 — Config V2 Governed Recovery Thresholds

**Given** a Config V2 recovery threshold (`outreach_max_retry_attempts`, `outreach_retry_window_days`) is missing
**When** the resilience layer evaluates recovery
**Then** `UNKNOWN_V0` is substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning is emitted; no hardcoded integer is used; affected cycle is annotated DEGRADED; loop continues with annotation

---

### AC-FP9 — AI Advisory Absence Governance

**Given** the AI provider is unavailable during orchestration evaluation
**When** a student requires AI advisory enrichment
**Then** AI failure does not block orchestration; `ai_governance_tier = UNAVAILABLE` is annotated; rule-based evaluation proceeds; AI absence is logged; no AI authority escalation occurs

---

### AC-FP10 — No Hardcoded Retry Semantics

**Given** a provider failure occurs during outreach dispatch
**When** the resilience layer determines recovery behavior
**Then** no "retry immediately (once)" or fixed-count retry is applied from the resilience layer; retry authorization is governed by `outreach_retry_policy.md` assessment and Config V2 Group A thresholds; no hardcoded retry count is used

---

### AC-FP11 — Scheduler Recovery Attribution

**Given** a missed scheduler cycle is detected
**When** a governed recovery cycle is initiated
**Then** the recovery cycle carries `execution_type = recovery`, `recovery_of_cycle_date`, `lag_detected_at`, and `recovery_initiated_by`; the same idempotency key as the missed cycle is used; already-processed students are skipped

---

### AC-FP12 — Failure Observability Completeness

**Given** any failure event is processed by the resilience layer
**When** the failure is logged
**Then** the structured JSON record contains `failure_domain`, `correlation_id`, `execution_mode`, `failure_cause`, `error_class`, `recovery_action`, and `outcome`; no unstructured console.log or silent error swallow occurs

---

## 14. UNRESOLVED GOVERNANCE CONCERNS

---

The following governance decisions affecting resilience behavior are deferred. They are documented here for governance review and are not blocking. The system operates without them using governed approximations noted below.

**UE-FP1: Recovery cycle escalation threshold** — How many consecutive missed scheduler cycles trigger an escalation candidacy signal vs a self-recovering no-op? Currently: any lag detection generates escalation candidacy. Governing decision: define a persistence threshold in Config V2. (OPERATIONAL DECISION)

**UE-FP2: Dead-letter retention window** — How long are dead-letter records retained before expiration? Currently: indefinite retention assumed. Governing decision: define retention window in Config V2 Group K or equivalent. (OPERATIONAL DECISION)

**UE-FP3: Retry budget protection scope** — Does `provider_outage_exempted = true` apply to all provider types or GHL-specific? Currently: assumed GHL-specific. Governing decision: define provider scope in `outreach_retry_policy.md`. (GOVERNANCE DECISION — see `retry_cycle_flow.md` UE-RF4)

**UE-FP4: Observability degradation escalation** — How many consecutive observability write failures trigger a governance escalation? Currently: single failure → `OBSERVABILITY_DEGRADED` to stderr; no escalation candidacy threshold defined. (OPERATIONAL DECISION)

**UE-FP5: Compliance hold recovery path** — When a compliance hold is lifted, does the system automatically generate a new orchestration cycle for the unblocked student, or does it require operator-initiated trigger? Currently: requires operator-initiated trigger. Governing decision: may be automated under Config V2 governance. (GOVERNANCE DECISION)

---

## 15. DOWNSTREAM REFERENCES

---

### 15.1 Authoritative Parent Contracts

This document inherits from:

| Contract | Governing sections |
|---|---|
| `runtime/system_loop.md` | §10 (Degradation & Failure Governance); §3 (Runtime Modes); §11 (Attribution & Observability); §2.1 (Governance-Safe Sequencing) |
| `runtime/scheduler_design.md` | §4.1–§4.10 (Scheduler orchestration); §10.5 (Scheduler lag governance) |
| `runtime/daily_outreach_flow.md` | §9 (Degradation governance within daily cycle); §4.4 (Retry coordination) |
| `runtime/retry_cycle_flow.md` | §10 (Retry degradation); §7 (Replay suppression); §8 (Provider governance); §9 (AI governance) |
| `spec/04_idempotency_concurrency.md` | §2 (Core principles); §4.1–§4.6 (Domain idempotency keys) |
| `spec/06_observability_operations.md` | Structured log requirements; correlation ID propagation |
| `spec/09_security_privacy.md` | Compliance hold governance; PII protection in logs |

---

### 15.2 Child Contracts Governed by This Document

| Contract | Sections of this document that govern it |
|---|---|
| `failure/scheduling_failures.md` | §2.4 (Scheduler Failures); §4.4 (Scheduler Outage Degradation); §7.1 (Recovery Coordination); §12 (AP-FP rules); §13 (Acceptance Criteria) |
| `failure/ghl_failures.md` | §2.2 (Provider Failures); §4.2 (Provider Outage Degradation); §4.7 (Duplicate Event Storm); §12 (AP-FP rules); §13 (Acceptance Criteria) |
| `failure/llm_failures.md` | §2.3 (AI Failures); §4.3 (AI Provider Outage Degradation); §3.3 (AI Authority Restrictions); §12 (AP-FP rules); §13 (Acceptance Criteria) |

---

### 15.3 Required Child Contract Updates

The following child contracts contain V1-era semantics that conflict with this governance model and must be updated in subsequent phases:

| Contract | V1 violations to remove |
|---|---|
| `failure/scheduling_failures.md` | "Trigger recovery execution immediately" (§4.1); MVP/STANDARD/PRODUCTION scope tiers (§10); simple failure recovery flow diagram (§5) |
| `failure/ghl_failures.md` | "Retry immediately (once)" (§4.1); hardcoded timeout table (§5); fixed retry matrix (§6); MVP/STANDARD/PRODUCTION scope tiers (§9) |
| `failure/llm_failures.md` | "Retry LLM call (once)" (§4.1); fixed retry table (§5); "Use deterministic rule-based decision engine only" as an undocumented fallback (§6); MVP/STANDARD/PRODUCTION scope tiers (§9) |

These updates are downstream governance tasks. This document's semantics govern now; child contracts must be brought into conformance in subsequent update phases.

---

### 15.4 Directive Dependencies

| Directive | Resilience dependency |
|---|---|
| `directives/outreach_retry_policy.md` | Retry authorization during failures; retry budget protection semantics |
| `directives/outreach_eligibility_rules.md` | Eligibility assessment during degraded evaluation |
| `directives/ghl_integration_contract.md` | Circuit breaker governance; dedup gate; provider failure behavior |
| `directives/llm_processing_contract.md` | AI failure behavior; advisory scope during outage |
| `directives/escalation_rules.md` | Escalation candidacy generation on failure conditions |

---

## END OF FILE
