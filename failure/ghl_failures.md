# failure/ghl_failures.md

---

## LAYER 8 — FAILURE HANDLING (GOVERNANCE-SAFE EXTERNAL PROVIDER RESILIENCE ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `spec/01_requirements.md` through `spec/09_warehouse_physical_architecture.md`, all seven governance-safe directives, and the four rewritten runtime contracts. The previous version described MVP-era CRM/provider recovery documentation: a four-type failure taxonomy (Trigger Failure/Workflow Execution Failure/Webhook Failure/Delayed Response); a hardcoded timeout table specifying "5–10 seconds" for API response, "5–30 minutes" for webhook arrival, and "up to 1 hour" for transcript availability; a fixed retry matrix with "Immediate retry (1x)" for API trigger failures; "Retry immediately (once)" as a first-class recovery step in §4.1; three-tier scope behavior (MVP/STANDARD/PRODUCTION); a seven-field plaintext log requirement; and a simplistic state impact table showing direct `CONTACTED → NO_RESPONSE` state transitions without governance context. That architecture is incompatible with the governance-safe orchestration model. GHL failure handling is no longer CRM retry documentation. It is governance-safe external provider resilience architecture — deterministic provider recovery coordination with replay-safe provider failure governance and observable provider degradation management. This document is the **canonical child resilience contract** governing GHL and all external provider failure behavior, governed by `failure/failure_playbook.md` (parent resilience contract) and `directives/ghl_integration_contract.md` (parent provider orchestration contract).

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe External Provider Resilience Architecture** defines:

* How provider failure governance domains are categorized, governed, and made historically explainable
* What execution modes govern provider resilience behavior — and what is permitted in each mode
* How deterministic provider degradation is coordinated without silent fallback execution
* How Config V2 Group F thresholds govern provider retry windows, circuit breaker behavior, and timeout handling — not hardcoded values
* How replay-safe provider recovery semantics prevent historical simulation from generating LIVE outbound effects
* How provider authority boundaries are maintained during resilience orchestration
* How AI advisory governance applies during degraded provider evaluation
* How provider recovery attribution lineage enables forensic reconstruction of every provider recovery action
* How provider failure state governance preserves immutable lineage and externalized state authority
* What authority boundaries the provider resilience layer holds vs what it must not own

This document is the **canonical child resilience contract** for external provider failure handling, governed by:

* `failure/failure_playbook.md` — parent resilience contract; §2.2, §4.2, §4.7, §7.1, §12, §13 govern this document
* `directives/ghl_integration_contract.md` — parent provider orchestration contract; RULE 0–RULE 11, §8, §13 govern this document

Where this document conflicts with `failure/failure_playbook.md`, `failure/failure_playbook.md` governs. Where this document conflicts with `directives/ghl_integration_contract.md`, `directives/ghl_integration_contract.md` governs.

---

### 1.2 What GHL Failure Handling Is NOT

In the governance-safe orchestration model, GHL failure handling is explicitly **NOT**:

* **"Retry immediately (once)"** — replaced by governed provider recovery orchestration coordination (AP-GF3); Config V2 Group F `provider_failure_max_retry_attempts` governs retry authorization; no hardcoded retry-once pattern is permitted in any provider failure domain
* **Hardcoded timeout handling** — "5–10 seconds for API response," "5–30 minutes for webhook arrival," "up to 1 hour for transcript availability" are not governed values; all timeouts are governed by Config V2 Group F OPERATIONAL_TUNING variables (AP-GF5)
* **Direct retry execution** — the provider resilience layer does not call GHL APIs, construct outbound payloads, increment attempt counts, or resend communications; all dispatch is delegated to provider orchestration services under governance authorization (AP-GF1)
* **Silent channel downgrade** — when the configured provider is unavailable, there is no silent routing to an alternative channel; provider outage transitions to `governance_scope = UNAVAILABLE`; outbound is deferred to queue with full observability (AP-GF4)
* **Immutable state mutation** — no recovery action may overwrite, backfill, or retroactively modify records in `ghl_messages`, `outreach_history`, `student_campaign_activity`, `processed_events`, or `student_timeline_events` (AP-GF7)
* **Replay-triggered LIVE delivery** — a replay-mode provider failure simulation may not generate LIVE outbound effects; all replay provider recovery outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY` (AP-GF2)
* **Direct state transition authority** — the resilience layer does not write state transitions; it coordinates failure detection signals; state write authority belongs exclusively to the state management service (§6.1)

Explicitly prohibited in provider resilience orchestration:

* Direct provider retry execution (AP-GF1)
* Replay-triggered LIVE outbound effects (AP-GF2)
* "Retry immediately (once)" semantics (AP-GF3)
* Silent provider fallback or channel downgrade (AP-GF4)
* Hardcoded timeout, retry count, or circuit breaker threshold values (AP-GF5)
* Non-attributable recovery actions (AP-GF6)
* Immutable provider record mutation (AP-GF7)
* Governance bypass during provider recovery (AP-GF8)
* Duplicate LIVE outbound recovery execution (AP-GF9)
* Orphaned provider recovery execution (AP-GF10)

---

### 1.3 Parent Contract Inheritance Table

This document is a governed child contract. Governing sections from parent contracts:

| Parent contract | Governing sections | What they govern in this document |
|---|---|---|
| `failure/failure_playbook.md` | §2.2 (Provider Failures); §4.2 (Provider Outage Degradation); §4.7 (Duplicate Event Storm); §7.1 (Recovery Coordination Model); §12 (AP-FP1–AP-FP15); §13 (AC-FP1–AC-FP12) | Core provider resilience governance; recovery coordination model; AP rules inherited |
| `directives/ghl_integration_contract.md` | RULE 0–RULE 11; §6 (Config V2 Governance); §7 (Replay Semantics); §8 (Provider Degradation); §9 (Outbound Authority); §13 (AP-GHL1–AP-GHL15) | Provider evaluation rules; config threshold governance; degradation conditions; AP-GHL rules extended here |
| `runtime/system_loop.md` | §8.3 (Provider Failure Runtime Behavior); §10.1 (Degradation Principles) | Runtime-level provider failure behavior; AUTH_FAILURE TERMINAL classification |
| `runtime/daily_outreach_flow.md` | §4.4 (Retry Orchestration Coordination) | Daily cycle retry coordination context |
| `runtime/retry_cycle_flow.md` | §10 (Retry Degradation); §8 (Provider Governance) | Retry budget protection; provider outage retry budget exemption |

Where this document conflicts with any parent contract, the parent contract governs.

---

## 2. PROVIDER FAILURE GOVERNANCE DOMAINS

---

### 2.1 Outbound Delivery Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | GHL API request failure (HTTP 4xx/5xx, timeout, connection failure); GHL accepts trigger but workflow execution does not complete; delivery confirmation not received |
| **Recovery philosophy** | Outbound delivery failures are contained at the provider governance boundary; circuit breaker state governs retry authorization; no direct retry from resilience layer (AP-GF1); retry authorization governed by Config V2 Group F `provider_failure_max_retry_attempts` |
| **Replay behavior** | Replay may simulate historical delivery failures; no LIVE dispatch from replay context; historical delivery state sourced from `ghl_messages`, `outreach_history`, `processed_events` |
| **SHADOW behavior** | Failure detected and logged with `execution_mode = SHADOW`; no LIVE delivery; `governance_scope = SHADOW_ONLY` |
| **LIVE behavior** | Circuit breaker checks precede retry authorization; circuit OPEN blocks dispatch; `PROVIDER_OUTAGE` or `CIRCUIT_OPEN` event emitted; escalation candidacy generated on repeated failure; `governance_scope = UNAVAILABLE` |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = outbound_delivery`, `provider_name = ghl`, `http_status_code`, `provider_error_class`, `retry_attempt_number`, `correlation_id` |
| **Attribution requirements** | `correlation_id` from orchestration cycle; `upstream_intent_id` from Core Decision Engine intent; `ghl_message_id` if returned by API response |
| **Idempotency guarantees** | `processed_events` dedup gate `(student_id, checkpoint_type, contact_attempt)` checked before re-dispatch; duplicate recovery → no-op |

**Prohibited patterns:**
* Constructing direct GHL API retry calls from the resilience layer (AP-GF1)
* Hardcoded retry count ("retry 1x") as recovery instruction (AP-GF3)
* Consuming retry budget for outage-blocked dispatch attempts (AP-FP12 inherited; `provider_outage_exempted = true` annotation required)

---

### 2.2 Duplicate Delivery Governance

| Attribute | Specification |
|---|---|
| **Governance scope** | Same outbound trigger dispatched twice (idempotency key collision in `processed_events`); duplicate inbound webhook delivery (same `ghl_message_id`); competing orchestration cycles triggering the same student |
| **Recovery philosophy** | Duplicate detection is handled at the idempotency gate in `ghl_integration_contract.md` RULE 6; the resilience layer observes and emits deduplication observability records; it does not own the dedup gate |
| **Replay behavior** | Historical duplicates visible; replay reads `processed_events` to simulate deduplication outcomes; no new duplicates created by replay |
| **SHADOW behavior** | Duplicate detection operates identically in SHADOW and LIVE modes; `DUPLICATE_SUPPRESSED` scope logged |
| **LIVE behavior** | `governance_scope = DUPLICATE_SUPPRESSED`; `provider_event_type = DEDUPLICATION_SUPPRESS`; `processed_events` audit entry required; no silent drop (AP-GF11) |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = duplicate_delivery`, `ghl_message_id` (inbound) or `idempotency_key` (outbound), `duplicate_detected_at`, `suppression_reason` |
| **Attribution requirements** | Duplicate suppression record carries `correlation_id` of the duplicate attempt; original record ID referenced |
| **Idempotency guarantees** | Duplicate detection is itself idempotent — detecting the same duplicate twice produces one suppression record, not two |

**Prohibited patterns:**
* Silent webhook deduplication drop without `processed_events` audit entry (AP-GF11)
* Processing a duplicate outbound trigger as a new delivery attempt (AP-GF9)

---

### 2.3 Inbound Webhook Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Schema validation failure (malformed payload, missing required fields); semantic validation failure (unknown `user_id`, unrecognized event type); webhook arrival timeout (expected event not received within Config V2 Group F `provider_delivery_sla_hours`); unknown webhook event type |
| **Recovery philosophy** | Schema-invalid webhooks are rejected (HTTP 400); semantic-invalid webhooks are rejected and logged; missing webhooks are annotated `NO_RESPONSE` by the state management service after the governed timeout window; no direct state mutation by the resilience layer |
| **Replay behavior** | Historical webhook failure records available in `ghl_messages`; replay sources webhook context from historical records; no live GHL webhook ingestion during replay |
| **SHADOW behavior** | Webhook validation applies identically in SHADOW and LIVE modes; invalid webhooks rejected in both modes |
| **LIVE behavior** | Schema invalid → HTTP 400, `WEBHOOK_SCHEMA_INVALID` reason code, no platform record created; missing webhook → state management service coordinates `NO_RESPONSE` after timeout governed by Config V2 Group F `provider_delivery_sla_hours` |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = webhook_failure`, `webhook_event_type`, `ghl_message_id`, `validation_result`, `failure_cause` |
| **Attribution requirements** | `ghl_message_id` required on all inbound webhook records; `attribution_timestamp` from GHL payload (not ingestion time); `ATTRIBUTION_TIMESTAMP_INFERRED` annotation if absent |
| **Idempotency guarantees** | `ghl_message_id` deduplication gate (RULE 6) prevents duplicate webhook processing; schema-invalid webhooks do not enter platform tables |

**Prohibited patterns:**
* Hardcoded webhook arrival timeout ("5–30 minutes") — governed by Config V2 Group F `provider_delivery_sla_hours` (AP-GF5)
* Storing malformed webhook payloads in typed tables before validation (AP-GHL13 inherited)

---

### 2.4 Provider Timeout Governance

| Attribute | Specification |
|---|---|
| **Governance scope** | GHL API response timeout at outbound dispatch; webhook arrival timeout (delivery confirmation not received within SLA window); transcript availability timeout |
| **Recovery philosophy** | All timeout windows governed by Config V2 Group F OPERATIONAL_TUNING variables; no hardcoded timeout values permitted (AP-GF5); timeout failures classified `error_class = TimeoutError` and accumulate in circuit breaker failure count |
| **Replay behavior** | Timeout records available in historical `ghl_messages`; replay uses historical timeout records; no live GHL timeout re-execution |
| **SHADOW behavior** | Timeout detected and logged; no LIVE retry from SHADOW context |
| **LIVE behavior** | `TimeoutError` classified; circuit breaker failure count incremented; retry authorization checked against Config V2 Group F `provider_failure_max_retry_attempts`; if circuit opens → `CIRCUIT_OPEN` event + `governance_scope = UNAVAILABLE` |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = provider_timeout`, `provider_error_class = TimeoutError`, `provider_call_duration_ms`, `timeout_threshold_applied` (Config V2 Group F variable name, not value) |
| **Attribution requirements** | `correlation_id`; `upstream_intent_id`; `retry_attempt_number` |
| **Idempotency guarantees** | Timeout failure does not consume idempotency key if dispatch was not confirmed; re-attempt uses same `(student_id, checkpoint_type, contact_attempt)` key |

**Prohibited patterns:**
* Hardcoded API response timeout ("5–10 seconds") — governed by Config V2 Group F OPERATIONAL_TUNING (AP-GF5)
* Hardcoded transcript availability timeout ("up to 1 hour") — governed by Config V2 Group F (AP-GF5)

---

### 2.5 Provider Outage Governance

| Attribute | Specification |
|---|---|
| **Governance scope** | Full GHL API unavailability (`provider_outage_active = true`); degraded provider mode (`provider_health_state = DEGRADED`); circuit breaker OPEN state; circuit breaker HALF_OPEN probe state |
| **Recovery philosophy** | Provider outage transitions all outbound to `governance_scope = UNAVAILABLE`; no silent routing to alternative channel (AP-GF4); outbound deferred to queue with full observability; inbound webhook ingestion unaffected by outage; `orchestration_continues = true` for non-dispatch domains |
| **Replay behavior** | Historical outage records visible; replay simulates outage constraints using historical provider health state; no LIVE provider calls during replay |
| **SHADOW behavior** | Outbound suppressed regardless of outage state; `governance_scope = SHADOW_ONLY` in SHADOW mode |
| **LIVE behavior** | `PROVIDER_OUTAGE_ACTIVE` event emitted; `governance_scope = UNAVAILABLE`; in-flight outreach intents preserved in QUEUED or RETRY_QUEUED state; retry budget protected (`provider_outage_exempted = true`); escalation candidacy generated on sustained outage |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = provider_outage`, `circuit_breaker_state`, `provider_health_state`, `governance_scope = UNAVAILABLE` |
| **Attribution requirements** | `correlation_id`; `provider_outage_window` (if known); `recovery_initiated_by` when outage resolves |
| **Idempotency guarantees** | No retry budget consumed during outage (`provider_outage_exempted = true`); recovery dispatch uses same idempotency key as original blocked dispatch |

**Prohibited patterns:**
* Silent routing to alternative channel during provider outage (AP-GF4)
* Consuming retry budget for outage-blocked dispatch (AP-FP12 inherited)

---

### 2.6 Degraded Synchronization Governance

| Attribute | Specification |
|---|---|
| **Governance scope** | Delivery telemetry stale (GHL confirmation not received within `provider_delivery_sla_hours`); SQL Server sync lag exceeded at outreach trigger time; GHL event synchronization backlog |
| **Recovery philosophy** | Sync degradation annotates affected records; orchestration evaluation continues with annotation; no silent degradation (AP-GF4); persistent sync backlog generates escalation candidacy |
| **Replay behavior** | Historical sync lag records available via `state_transition_log`; historical delivery telemetry sourced from `outreach_history` at historical timestamp |
| **SHADOW behavior** | Sync lag annotated; orchestration continues with degraded annotation |
| **LIVE behavior** | `delivery_telemetry_stale = true` when stale beyond `provider_delivery_sla_hours`; `SYNC_LAG_HOURS = {value}` annotation when `sync_lag_hours > sql_server_max_sync_age_hours`; provider interactions not blocked by sync lag alone |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = degraded_synchronization`, `sync_lag_hours`, `delivery_telemetry_stale`, `stale_for_hours` |
| **Attribution requirements** | `sync_correlation_id`; `last_sync_timestamp`; `correlation_id` from orchestration cycle |
| **Idempotency guarantees** | Sync operations are read-only for GHL; annotation writes are idempotent |

---

### 2.7 Attribution-Loss Governance

| Attribute | Specification |
|---|---|
| **Governance scope** | Missing `ghl_message_id` on inbound GHL event; missing `correlation_id` in provider recovery path; broken `origin_source`/`origin_authority` chain; attribution field gaps preventing recovery lineage reconstruction |
| **Recovery philosophy** | Attribution failure is a specification defect; affected records are flagged `attribution_incomplete = true`; escalation candidacy generated; no silent continuation with broken attribution (AP-GF6) |
| **Replay behavior** | Attribution failure in replay: `fingerprint_comparison_outcome = UNKNOWN` with `attribution_incomplete = true`; replay continues with incomplete attribution annotation |
| **SHADOW behavior** | Attribution failure logged with SHADOW scope; flagged for review |
| **LIVE behavior** | `ATTRIBUTION_FAILURE` event emitted; affected record annotated `attribution_incomplete = true`; escalation candidacy generated; interaction not aborted unless precondition gate fails (RULE 0) |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = attribution_loss`, `missing_field`, `affected_record_id`, `attribution_incomplete = true` |
| **Attribution requirements** | Attribution failure record must itself carry `correlation_id` from the orchestration cycle even if downstream records are missing it |
| **Idempotency guarantees** | Attribution failure records are append-only; no retroactive lineage repair that mutates existing records (AP-GF7) |

---

### 2.8 Replay Provider Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Replay evaluation encountering a live GHL call attempt (blocked by RULE 1); historical config version unavailable for replay evaluation; historical provider records (`ghl_messages`) absent for replayed timestamp; fingerprint comparison failure |
| **Recovery philosophy** | Replay provider failures emit SHADOW-only diagnostics; no recovery path generates LIVE outbound effects; `replay_partial = true` annotated when historical data incomplete |
| **Replay behavior** | Replay provider failure is itself a replay event; loop emits failure diagnostic with `source_artifact_id`, `fingerprint_comparison_outcome = UNKNOWN`, `replay_partial = true`; governance scope remains `REPLAY_ONLY` |
| **SHADOW behavior** | All replay is SHADOW-mode by definition; failure scoped to `execution_type = replay` |
| **LIVE behavior** | No LIVE behavior during replay; LIVE mode may not be entered from replay context (AP-GF2) |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = replay_provider_failure`, `source_artifact_id`, `historical_config_version_id`, `replay_failure_cause`, `replay_partial` |
| **Attribution requirements** | `source_artifact_id` required; `historical_config_version_id` or null if resolution failed |
| **Idempotency guarantees** | Replay is inherently read-only for provider records; no idempotency key consumption during replay |

---

### 2.9 Regeneration Provider Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Regeneration evaluation attempting provider API access during report re-render; communication history gaps in `ghl_messages` or `outreach_history` preventing accurate historical communication summary |
| **Recovery philosophy** | Regeneration failure emits structured log and stops for the affected record; no retry within regeneration mode; no GHL API calls during regeneration; no platform state mutations |
| **Replay behavior** | Regeneration is not replay; regeneration failures do not produce replay diagnostics |
| **SHADOW behavior** | Regeneration may run in any mode; output tagged `execution_type = regeneration`; no LIVE dispatch |
| **LIVE behavior** | Regeneration reads `ghl_messages`, `outreach_history` exclusively for communication history context; no live GHL API calls; no state transitions; failure produces structured log; failed regeneration does not corrupt existing `REPORT_PUBLISHED` state |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = regeneration_provider_failure`, `source_artifact_id`, `lineage_version`, `regeneration_failure_cause` |
| **Attribution requirements** | `source_artifact_id`; `lineage_version` required |
| **Idempotency guarantees** | Regeneration creates new version lineage; does not overwrite existing published report (AP-GF7) |

---

### 2.10 Observability Degradation Governance

| Attribute | Specification |
|---|---|
| **Governance scope** | Structured provider log pipeline failures; telemetry write failures during provider interactions; circuit breaker state observability failures; delivery observability metric write failures |
| **Recovery philosophy** | Observability failure does not block provider interactions; structured logs that fail to write are directed to stderr with `OBSERVABILITY_DEGRADED` flag; the failure is itself observable |
| **Replay behavior** | Observability failure does not suppress replay diagnostic emission; replay diagnostics written to stderr if pipeline degraded |
| **SHADOW behavior** | Observability failure in SHADOW mode: directed to stderr; interaction continues |
| **LIVE behavior** | `OBSERVABILITY_DEGRADED` event emitted to stderr; provider interactions continue; escalation candidacy generated for persistent observability degradation |
| **Observability requirements** | `failure_domain = provider`, `provider_failure_type = observability_degradation`, `pipeline_stage`, `failure_cause`, directed to stderr |
| **Attribution requirements** | Minimal attribution preserved in stderr record: `correlation_id`, `timestamp`, `provider_name` |
| **Idempotency guarantees** | Observability writes are independent of business state; no idempotency concern for log writes |

---

## 3. FAILURE AUTHORITY BOUNDARIES

---

### 3.1 What the Provider Resilience Layer Coordinates

| Responsibility | Provider resilience layer owns | Provider resilience layer does NOT own |
|---|---|---|
| Provider failure classification and routing | Yes | Defining business-level eligibility or retry thresholds (directives own those) |
| Recovery coordination with attribution generation | Yes | Executing provider dispatch (orchestration services own this) |
| Circuit breaker signal consumption | Yes | Owning circuit breaker state (`ghl_integration_contract.md` RULE 4 owns this) |
| Degradation annotation coordination | Yes | Mode transition authority (Governance/Operational Administrator owns this) |
| Observability emission for provider failure events | Yes | Implementing telemetry pipelines or alerting infrastructure |
| Escalation candidacy generation on provider failure | Yes | Escalation routing (escalation routing service owns this) |
| Dead-letter record coordination | Yes | Dead-letter retry infrastructure implementation |
| Deduplication audit emission | Yes | Owning the `processed_events` gate (RULE 6 in `ghl_integration_contract.md` owns this) |

---

### 3.2 Provider Authority Restrictions

The provider resilience layer never escalates provider authority:

* GHL remains `platform_supplementary` during all failure conditions — failure does not grant GHL additional governance scope (AP-GF15)
* Provider outage does not authorize the resilience layer to directly dispatch from an alternative channel without governance authorization (AP-GF4)
* Provider recovery does not bypass normal governance authorization checks (AP-GF8)
* No provider interaction may be initiated by the resilience layer directly (AP-GF1)
* A GHL webhook that arrives during provider outage and claims `sql_server_authoritative` authority is a validation failure regardless of outage state (inherits AP-GHL4)

---

### 3.3 AI Authority Restrictions During Provider Failures

The provider resilience layer never expands AI advisory authority during provider failures:

* AI remains advisory-only during all provider failure scenarios
* Provider failure does not elevate AI advisory to decision-making authority
* AI advisory absence during provider degradation: rule-based evaluation proceeds; AI absence annotated
* FINALIZED_COPY records are never re-evaluated during provider failure — they remain immutable regardless of provider state

---

### 3.4 Replay Authority Restrictions

The provider resilience layer does not grant LIVE authority to replay-mode recovery:

* A provider failure detected during replay simulation produces no LIVE outbound effect (AP-GF2)
* Replay provider recovery outputs carry `execution_type = replay`, `governance_scope = REPLAY_ONLY`
* No mode transition from REPLAY to LIVE is permitted within a provider resilience recovery sequence (AP-GF8)

---

## 4. DETERMINISTIC PROVIDER DEGRADATION GOVERNANCE

---

### 4.1 Provider Degradation Principles

Degradation is observable, not silent. Inherited from `failure/failure_playbook.md` §4.1 and `runtime/system_loop.md` §10.1:

Every degraded provider state must:
* Emit a structured log entry with `degradation_cause`, `provider_name`, `governance_scope`, and `outcome = partial` or `outcome = failure`
* Produce an observable escalation candidacy signal when provider degradation exceeds governed thresholds
* Describe what provider interactions continued and what were blocked
* Never silently substitute an alternative delivery channel or swallow a provider failure

The following patterns are prohibited (AP-GF3, AP-GF4, AP-GF5):
* "Retry immediately once" — swallowing the first failure with an undocumented inline retry
* Routing to an alternative channel when GHL is unavailable without governance authorization
* Substituting hardcoded timeout, retry count, or circuit breaker threshold values for Config V2 Group F variables

---

### 4.2 Provider Outage Degradation

When `provider_outage_active = true`:

* **Outbound dispatch** — blocked for all students; `governance_scope = UNAVAILABLE`; `degradation_cause = PROVIDER_OUTAGE`; in-flight outreach intents preserved in QUEUED or RETRY_QUEUED state
* **Inbound webhook ingestion** — continues normally; outage does not affect inbound processing
* **SQL Server platform reads** — unaffected
* **AI evaluation** — unaffected
* **Retry budget protection** — retry attempts blocked by provider outage are not consumed from the student's retry budget; `provider_outage_exempted = true` annotation required (AP-FP12 inherited)
* **State transitions** — no `CONTACTED` state transition occurs without confirmed provider delivery

Inherits `failure/failure_playbook.md` §4.2 verbatim. `directives/ghl_integration_contract.md` §8.1 is authoritative for provider outage handling behavior.

---

### 4.3 Circuit Breaker Degradation

| Circuit breaker state | Provider resilience behavior |
|---|---|
| `CLOSED` | Provider healthy; provider interactions proceed normally |
| `OPEN` | Outbound dispatch blocked; `governance_scope = UNAVAILABLE`; `degradation_cause = CIRCUIT_OPEN`; `CIRCUIT_OPEN` reason code emitted; inbound unaffected |
| `HALF_OPEN` | One probe attempt allowed; circuit resilience layer observes probe outcome; does not own circuit state |
| `UNKNOWN` | Treated as `CLOSED` with `PROVIDER_HEALTH_UNKNOWN` observation; degraded signal emitted |

Circuit breaker state transitions are owned by the provider governance service (`ghl_integration_contract.md` RULE 4). The resilience layer consumes circuit state as a signal; it does not own circuit state management.

Circuit breaker reset window governed by Config V2 Group F `provider_failure_circuit_breaker_reset_hours`. No hardcoded reset window (AP-GF5).

---

### 4.4 Retry Budget Exhaustion

When `outbound_retry_budget_remaining = 0` (governed by Config V2 Group F `provider_failure_max_retry_attempts`):

* `governance_scope = UNAVAILABLE`; `degradation_cause = RETRY_EXHAUSTED`
* Escalation candidacy generated; consuming orchestration service evaluates escalation routing
* No automatic silent retry beyond the config-bound maximum (AP-GF3, AP-GF5)
* Retry exhaustion is an escalation trigger input; escalation routing governed by `directives/escalation_rules.md`
* Students with exhausted retry budgets: affected record annotated; no further dispatch authorized without governance authorization

No hardcoded retry count ("retry 1x") is permitted. Config V2 Group F `provider_failure_max_retry_attempts` is the exclusive retry ceiling.

---

### 4.5 Duplicate Event Storm Degradation

When a duplicate inbound webhook event storm is detected:

* `processed_events` deduplication gate absorbs all duplicates (RULE 6 in `ghl_integration_contract.md`)
* All duplicate detections produce a `processed_events` audit log entry — no silent drops (AP-GF11)
* `DUPLICATE_EVENT_STORM` event emitted with dedup count when storm volume exceeds governed threshold
* Duplicate event storms do not degrade outbound orchestration domains
* Provider resilience layer observes and reports; does not own the dedup gate

Inherits `failure/failure_playbook.md` §4.7 verbatim.

---

### 4.6 Webhook Backlog Degradation

When an expected webhook is not received within the governed SLA window:

* Timeout window governed by Config V2 Group F `provider_delivery_sla_hours`; no hardcoded "5–30 minutes" (AP-GF5)
* After timeout: `WEBHOOK_ARRIVAL_TIMEOUT` event emitted with `ghl_message_id = null`
* State management service coordinates `NO_RESPONSE` state transition — resilience layer does not write the transition (§6.1)
* If multiple students are missing webhooks in the same cycle: `WEBHOOK_BACKLOG_DETECTED` aggregate event with affected student count
* Persistent webhook backlog generates escalation candidacy

---

### 4.7 Synchronization Backlog Degradation

When `sync_lag_hours > sql_server_max_sync_age_hours` (Config V2 Group K):

* Affected provider interactions annotated with `SYNC_LAG_HOURS = {value}` reason code
* `sync_recency_within_policy = false` set in synchronization metadata
* Provider interactions not blocked by sync lag alone (spec/05 §11.1)
* Persistent sync backlog generates escalation candidacy if lag exceeds governance-defined threshold
* Recovery: sync loop retries; no special provider recovery cycle required

---

### 4.8 Authentication Failure Degradation

When GHL API authentication fails (`provider_error_class = AUTH_FAILURE`):

* **TERMINAL failure class** — no retry; no circuit breaker accumulation; immediate alert
* `governance_scope = UNAVAILABLE`; `degradation_cause = AUTH_FAILURE_TERMINAL`
* All subsequent provider interactions blocked until authentication is restored and key rotation confirmed
* Authentication failure does not corrupt platform state; in-flight orchestration intents preserved in QUEUED state
* `AUTH_FAILURE_TERMINAL` event emitted; operator escalation required (AP-GF12)
* Key rotation and authentication restoration governed by `spec/09_security_privacy.md`

Inherits `runtime/system_loop.md` §8.3 `AUTH_FAILURE` TERMINAL classification and `directives/ghl_integration_contract.md` §12.2 verbatim.

---

### 4.9 Observability Degradation

When the provider observability pipeline degrades:

* `OBSERVABILITY_DEGRADED` event directed to stderr with `provider_name`, `pipeline_stage`, `failure_cause`
* Provider interactions continue; observability failure does not block dispatch or ingestion
* Failed log lines preserved in stderr for recovery
* Persistent observability degradation generates escalation candidacy
* Minimum context preserved in stderr: `correlation_id`, `timestamp`, `provider_name`

---

## 5. REPLAY & REGENERATION PROVIDER FAILURE SEMANTICS

---

### 5.1 Replay Provider Failure Governance

When the provider resilience layer operates in REPLAY mode (`execution_type = replay`):

* Replay may simulate historical provider failure scenarios from `ghl_messages`, `outreach_history`, and `state_transition_log` records
* Replay may not generate LIVE outbound provider effects from historical failure simulation
* Historical provider failure records are read-only reference points; replay does not re-execute historical provider recovery actions
* Replay provider failure diagnostics carry `governance_scope = REPLAY_ONLY`; they may not be consumed as LIVE recovery signals
* `fingerprint_comparison_outcome = MATCH | DIVERGENT | UNKNOWN` emitted for simulated vs historical provider failure behavior

---

### 5.2 Replay Outbound Suppression Rules

The following LIVE effects are suppressed in all replay provider recovery contexts:

| Effect category | Suppression mechanism |
|---|---|
| Outbound GHL dispatch from recovery | `ProviderOrchestrationAssessment.outbound_suppressed = true` (RULE 1) |
| Live GHL API calls during replay failure simulation | Blocked by RULE 1; all provider context from historical records exclusively |
| State transitions during replay provider simulation | Replay Services hold no state write authority |
| Escalation routing during replay | `REPLAY_ESCALATION_CANDIDATE` scope; no live operator routing |
| `processed_events` key consumption during replay | Replay reads existing entries; does not create new entries for already-existing events |

---

### 5.3 Historical Provider Visibility

In REPLAY mode, provider context is sourced exclusively from platform-owned historical records:

* Outbound trigger history from `outreach_history` and `processed_events`
* Inbound webhook history from `ghl_messages` and `student_campaign_activity`
* Delivery state history from `outreach_history.delivery_state` at historical timestamp
* Circuit breaker history from `state_transition_log` events at historical timestamp
* Config V2 Group F thresholds from `historical_config_version_id` at time of original provider interaction

Replay may not generate new delivery attempts, new state transitions, or new AI content to substitute for historically absent provider data. `replay_partial = true` annotated when historical provider data is incomplete.

---

### 5.4 Regeneration Provider Failure Semantics

Regeneration failures (re-render from FINALIZED snapshot data including communication history) are distinct from replay failures:

* Regeneration reads `ghl_messages`, `outreach_history` exclusively for communication history context
* Regeneration failure does not corrupt existing `REPORT_PUBLISHED` state (AP-GF7)
* No live GHL API calls, no state transitions, no outbound dispatch during regeneration failure recovery
* Failed regeneration job records are append-only; recovery requires a new governed regeneration job
* Regeneration does not create `processed_events` entries for historical provider interactions it reads

---

## 6. PROVIDER FAILURE STATE GOVERNANCE

---

### 6.1 State Authority During Provider Failures

The provider resilience layer does not own state transitions. State write authority is externalized to the state management service in all provider failure scenarios:

| Provider failure scenario | State coordination | Resilience layer role |
|---|---|---|
| Outbound delivery failure | State remains at pre-dispatch state (e.g., `QUEUED`) | Structured failure log; escalation candidacy coordination |
| Webhook arrival timeout | State management service transitions to `NO_RESPONSE` after governed SLA window | Coordinates timeout detection signal; does not write transition directly |
| Provider outage blocks dispatch | State preserved as QUEUED or RETRY_QUEUED | `PROVIDER_OUTAGE` event; retry budget protection annotation |
| Duplicate webhook detected | No new state transition | `DUPLICATE_SUPPRESSED` scope; `processed_events` audit entry |
| Authentication failure | No state change for students | `AUTH_FAILURE_TERMINAL` alert; all further dispatch blocked |
| Retry budget exhausted | No state transition from resilience layer | `RETRY_EXHAUSTED` annotation; escalation candidacy coordination |
| Replay provider failure | No state change (replay is read-only) | Replay diagnostic emission |

---

### 6.2 Immutable Record Protections During Provider Recovery

Provider recovery orchestration must never mutate:

* `ghl_messages` — append-only; replay and recovery produce new entries, not mutations (AP-GF7)
* `outreach_history` — append-only; recovery records are new entries (AP-GF7)
* `student_campaign_activity` — append-only; campaign records preserved immutably
* `processed_events` — append-only; dedup audit records are not modifiable
* `warehouse.student_snapshots` — FINALIZED state is irreversible; provider failures do not affect snapshot content
* `warehouse.snapshot_ai_narratives` — FINALIZED_COPY is immutable; provider failures do not trigger AI re-evaluation
* `state_transition_log` — append-only; recovery produces new entries, not retroactive corrections

---

### 6.3 Eligibility and Retry Policy During Provider Failures

The provider resilience layer coordinates eligibility assessment during degraded provider operation:

* Eligibility assessment (`outreach_eligibility_rules.md`) remains directive-owned even during provider failures
* Retry policy assessment (`outreach_retry_policy.md`) remains directive-owned even during provider failures
* Provider resilience layer receives `EligibilityAssessment` and `RetryPolicyAssessment` outputs — it does not re-implement these directives (AP-GF8)
* During provider outage: students in QUEUED state remain eligible for the next outreach cycle when provider recovers; eligibility is re-assessed at that time
* Retry budget protection applies: provider-outage-blocked attempts do not consume student retry budget

---

## 7. PROVIDER RECOVERY ORCHESTRATION COORDINATION

---

### 7.1 Governed Provider Recovery Coordination Model

The V1 pattern:

> "Retry immediately (once)" and "Proceed with retry policy"

is replaced with:

> **Governed Provider Recovery Orchestration Coordination** — the resilience layer produces a recovery attribution record linked to the provider failure event, coordinates recovery through the same governance-authorized orchestration sequence as the original attempt, and observably completes

Provider recovery coordination model:

```
PROVIDER FAILURE DETECTION  →  structured provider failure log emitted (§11.1)
  ↓
RECOVERY AUTHORIZATION GATE  →  execution_mode, config_version_id, circuit_breaker_state,
                                  and (if required) operator authorization validated;
                                  replay context: LIVE delivery blocked
  ↓
IDEMPOTENCY CHECK  →  same (student_id, checkpoint_type, contact_attempt) key checked;
                       if already recovered, no-op; DUPLICATE_SUPPRESSED logged
  ↓
RECOVERY ATTRIBUTION  →  provider_failure_type, recovery_of_cycle_date, lag_detected_at,
                          recovery_initiated_by, provider_outage_window (if applicable) annotated
  ↓
RECOVERY ORCHESTRATION DELEGATION  →  governed orchestration sequence (same as normal cycle);
                                        already-processed students skipped via processed_events
  ↓
OBSERVABILITY EMISSION  →  provider recovery cycle completion record (§11.2)
```

---

### 7.2 Config V2-Governed Provider Resilience Thresholds

All provider resilience behavior is governed by Config V2, not hardcoded values:

| Provider resilience threshold | Config V2 source | Group |
|---|---|---|
| Provider retry attempt ceiling | `provider_failure_max_retry_attempts` | F |
| Circuit breaker failure threshold | `provider_failure_circuit_breaker_threshold` | F |
| Circuit breaker reset window | `provider_failure_circuit_breaker_reset_hours` | F |
| Retry backoff base interval | `provider_failure_retry_backoff_base_seconds` | F |
| Delivery SLA window (webhook arrival) | `provider_delivery_sla_hours` | F |
| API timeout window | (Config V2 Group F OPERATIONAL_TUNING) | F |
| Circuit breaker probe interval | (Config V2 Group F OPERATIONAL_TUNING) | F |
| Sync lag tolerance | `sql_server_max_sync_age_hours` | K |
| Escalation threshold for sustained outage | (Config V2 Group F OPERATIONAL_TUNING) | F |

No hardcoded provider resilience thresholds are permitted. Substituting a literal integer for any of these values in provider failure handling logic is a specification defect (AP-GF5).

---

### 7.3 Provider Recovery Attribution Requirements

Every provider recovery action must carry:

| Field | Required value |
|---|---|
| `execution_type` | `recovery` |
| `provider_failure_type` | one of the 10 domains in §2 |
| `recovery_of_cycle_date` | ISO-8601 date of the original failed delivery attempt |
| `lag_detected_at` | ISO-8601 timestamp when failure or lag was detected |
| `recovery_initiated_by` | Operator identity or `system_provider_monitor` |
| `provider_outage_window` | Reference to provider outage window record, if recovery follows outage |
| `recovery_authorization_record_id` | Reference to admin authorization record (where required) |
| `circuit_breaker_resolved` | `true` if recovery follows circuit breaker reset |
| `auth_failure_resolved` | `true` if recovery follows authentication key rotation |

---

## 8. ATTRIBUTION & OBSERVABILITY

---

### 8.1 Provider Failure Attribution Lineage Chain

Every provider failure record must carry a complete attribution lineage:

```
Config V2 Group F governance  →  config_version_id + provider_failure_max_retry_attempts
  ↓
Orchestration cycle  →  correlation_id + cycle_id + execution_mode
  ↓
Core Decision Engine intent  →  upstream_intent_id (outbound) or ghl_message_id (inbound)
  ↓
Provider failure event  →  provider_failure_type + failure_cause + provider_error_class
  ↓
Recovery record (if applicable)  →  recovery_of_cycle_date + recovery_initiated_by
  ↓
Dead-letter or escalation candidacy  →  escalation_type + escalation_severity
```

A provider failure that cannot be traced from symptom back to root cause using a single `correlation_id` is an observability defect.

---

### 8.2 Outbound Correlation Propagation

Every outbound recovery action propagates:

* `correlation_id` from the recovery orchestration cycle
* `upstream_intent_id` from the Core Decision Engine intent that authorized re-dispatch
* `causation_id` referencing the original OrchestrationIntent that produced the failed dispatch
* Recovery records carry the recovery cycle's own `correlation_id` — not retroactively attributed to the original failed cycle

---

### 8.3 Causation Lineage in Provider Recovery

Every provider recovery action propagates causation lineage:

* Recovery orchestration intent carries `causation_id` referencing the original `OrchestrationIntent`
* Recovery dispatch record links to original dispatch attempt via `recovery_of_cycle_date`
* Recovery `processed_events` entry links to original idempotency key `(student_id, checkpoint_type, contact_attempt)`

---

### 8.4 Replay Provider Diagnostics

Replay provider recovery diagnostics must carry:

| Field | Specification |
|---|---|
| `source_artifact_id` | ID of the original provider interaction being replayed |
| `historical_config_version_id` | Config version at time of original provider failure |
| `fingerprint_comparison_outcome` | `MATCH \| DIVERGENT \| UNKNOWN` |
| `replay_partial` | `true` if historical provider data was incomplete |
| `execution_type` | `replay` |
| `governance_scope` | `REPLAY_ONLY` |
| `replay_provider_source` | `PROCESSED_EVENTS \| HISTORICAL_LOG \| NONE` |

---

### 8.5 Webhook Delivery Observability

All inbound webhook failure events emit the structured diagnostics inherited from `directives/ghl_integration_contract.md` §10.5:

| Field | Description |
|---|---|
| `webhook_received_at` | Platform-side ingestion timestamp |
| `attribution_timestamp` | Event occurrence time from GHL payload |
| `attribution_timestamp_delta_ms` | Delta between GHL event time and platform ingestion time |
| `ghl_message_id` | GHL message identifier |
| `dedup_result` | `new` or `duplicate` |
| `validation_result` | `schema_valid`, `schema_invalid`, `semantic_invalid` |
| `event_type_classified` | Classified webhook event type |

---

## 9. PROVIDER FAILURE IDEMPOTENCY GUARANTEES

---

### 9.1 Core Idempotency Principle

Every provider recovery operation must satisfy the idempotency principle inherited from `spec/04_idempotency_concurrency.md` §2.1:

> Repeated operations MUST NOT create duplicate effects. Same request → same outcome. Same input + same state → same persisted result; no first-run/second-run divergence.

---

### 9.2 Domain-Specific Provider Idempotency Keys

| Domain | Idempotency key | Behavior on duplicate |
|---|---|---|
| Outbound dispatch recovery | `(student_id, checkpoint_type, contact_attempt)` | Duplicate → no-op; `DUPLICATE_SUPPRESSED` logged |
| Inbound webhook ingestion | `ghl_message_id` | Duplicate → HTTP 200; `WEBHOOK_DUPLICATE_SUPPRESSED` audit; no new record |
| Campaign activity ingestion | `(student_id, campaign_id, event_type, attribution_timestamp)` | Duplicate → deduplication suppress; no new record |
| Provider recovery cycle | `(cycle_date, execution_type = recovery, config_version_id)` | Duplicate recovery → no-op |
| AI refresh during provider recovery | `(student_id, insight_type, date_period, prompt_version)` | Duplicate refresh → no-op |
| Delivery telemetry annotation | `(student_id, delivery_event_id)` | Duplicate annotation → idempotent update |

---

### 9.3 Idempotency Violations Are Production Defects

A provider recovery operation that "works once but produces duplicate effects on the second run" is not "fragile" — it is broken. The following patterns are idempotency defects:

* Recovery that re-dispatches an outbound trigger without checking `processed_events` first
* Recovery cycle that re-processes already-processed students without checking their idempotency key
* Webhook ingestion that processes a duplicate `ghl_message_id` without the dedup gate
* AI refresh recovery that overwrites a FINALIZED_COPY record in `warehouse.snapshot_ai_narratives`

---

## 10. DETERMINISTIC PROVIDER DEGRADATION CONDITION TABLE

---

### 10.1 Canonical Provider Degradation Conditions

| Condition | Affected domains | Provider behavior | Orchestration continues | Resilience action |
|---|---|---|---|---|
| Provider circuit breaker OPEN | Outbound dispatch (§2.5) | `governance_scope = UNAVAILABLE`; `degradation_cause = CIRCUIT_OPEN` | Yes | `CIRCUIT_OPEN` event + escalation candidacy |
| Provider outage active | Outbound dispatch (§2.5) | Same as circuit OPEN; retry budget protected | Yes | `PROVIDER_OUTAGE_ACTIVE` + degradation onset record |
| Retry budget exhausted | Retry orchestration (§2.1) | `governance_scope = UNAVAILABLE`; `degradation_cause = RETRY_EXHAUSTED` | Yes | `RETRY_BUDGET_EXHAUSTED` + escalation candidacy |
| Webhook arrival timeout | Inbound (§2.3) | State management coordinates `NO_RESPONSE` after SLA window | Yes | `WEBHOOK_ARRIVAL_TIMEOUT` + escalation candidacy |
| Duplicate outbound trigger | Idempotency (§2.2) | `governance_scope = DUPLICATE_SUPPRESSED` | Yes | `OUTBOUND_DUPLICATE_SUPPRESSED` audit entry |
| Duplicate inbound webhook | Idempotency (§2.2) | HTTP 200; `governance_scope = DUPLICATE_SUPPRESSED` | Yes | `WEBHOOK_DUPLICATE_SUPPRESSED` audit entry |
| Provider authentication failure | All outbound (§4.8) | TERMINAL; all dispatch blocked until key rotation | No (all outbound) | `AUTH_FAILURE_TERMINAL` + immediate alert |
| Webhook schema invalid | Inbound (§2.3) | HTTP 400; no record created | Inbound only | `WEBHOOK_SCHEMA_INVALID` + structured log |
| Config threshold missing | All domains | `UNKNOWN_V0` substituted; DEGRADED annotation | Yes | `CONFIG_THRESHOLD_MISSING_{KEY}` per key |
| Replay mode | All outbound (§2.8) | `governance_scope = REPLAY_ONLY`; all outbound suppressed | No (outbound) | `OUTBOUND_SUPPRESSED_REPLAY` reason code |
| SHADOW mode | All outbound | `governance_scope = SHADOW_ONLY`; no live delivery | No (live outbound) | `SHADOW_DISPATCH_SUPPRESSED` reason code |
| Sync lag exceeded | Synchronization (§2.6) | `delivery_telemetry_stale` annotation; sync lag annotated | Yes | `SYNC_LAG_HOURS = {value}` annotation |
| Attribution loss | Attribution (§2.7) | `attribution_incomplete = true` on affected record | Yes | `ATTRIBUTION_FAILURE` + escalation candidacy |
| Observability pipeline degraded | All domains (§2.10) | Logs to stderr; `OBSERVABILITY_DEGRADED` | Yes | Direct stderr alert |

---

## 11. PROVIDER RESILIENCE OBSERVABILITY SCHEMA

---

### 11.1 Structured Provider Failure Log Record

Every provider failure event must emit a structured JSON record extending the parent schema from `failure/failure_playbook.md` §11.1:

```json
{
  "timestamp": "ISO-8601",
  "level": "warn | error",
  "service": "provider_resilience_orchestration",
  "event": "provider_failure_detected",
  "failure_domain": "provider",
  "provider_failure_type": "outbound_delivery | duplicate_delivery | webhook_failure | provider_timeout | provider_outage | degraded_synchronization | attribution_loss | replay_provider_failure | regeneration_provider_failure | observability_degradation",
  "provider_name": "ghl | future_provider",
  "ghl_message_id": "string | null",
  "cycle_id": "uuid | null",
  "correlation_id": "uuid | null",
  "causation_id": "uuid | null",
  "execution_mode": "SHADOW | LIVE | REPLAY | REGENERATION | DEGRADED | MAINTENANCE",
  "execution_type": "original | recovery | replay | regeneration",
  "config_version_id": "string | null",
  "governance_scope": "AUTHORIZED | BLOCKED | SHADOW_ONLY | REPLAY_ONLY | DUPLICATE_SUPPRESSED | UNAVAILABLE",
  "circuit_breaker_state": "CLOSED | OPEN | HALF_OPEN | UNKNOWN",
  "http_status_code": "integer | null",
  "provider_error_class": "TimeoutError | RateLimitError | AuthError | ValidationError | UpstreamUnavailable | SchemaInvalid | DeduplicationSuppressed | ContractViolation | AttributionFailure | IdempotencyViolation | string",
  "webhook_event_type": "CALL_COMPLETED | SMS_RESPONSE | EMAIL_RESPONSE | TRANSCRIPT_READY | CAMPAIGN_PARTICIPATION | null",
  "retry_attempt_number": 0,
  "delivery_state": "PENDING | DELIVERED | FAILED | NO_RESPONSE | UNKNOWN | null",
  "outbound_suppressed": false,
  "recovery_action": "governed_recovery_cycle | dead_letter | degraded_continuation | escalation_candidacy | no_op | deferred_to_queue | duplicate_suppressed",
  "failure_cause": "string",
  "degradation_flags": [],
  "attribution_incomplete": false,
  "outcome": "failure | partial | degraded | suppressed"
}
```

---

### 11.2 Provider Recovery Cycle Completion Record

A governed provider recovery cycle emits a completion record extending the parent record from `failure/failure_playbook.md` §11.2:

```json
{
  "timestamp": "ISO-8601",
  "level": "info",
  "service": "provider_resilience_orchestration",
  "event": "provider_recovery_cycle_complete",
  "provider_name": "ghl | future_provider",
  "cycle_id": "uuid",
  "correlation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | DEGRADED",
  "execution_type": "recovery",
  "config_version_id": "string",
  "recovery_of_cycle_date": "YYYY-MM-DD | null",
  "lag_detected_at": "ISO-8601 | null",
  "recovery_initiated_by": "system_provider_monitor | operator_id",
  "recovery_authorization_record_id": "uuid | null",
  "provider_outage_window": "string | null",
  "circuit_breaker_resolved": false,
  "auth_failure_resolved": false,
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

### AP-GF1 — No Direct Provider Retry from Resilience Layer

MUST NOT allow any step in the provider resilience layer to directly call a GHL API, construct an outbound payload, initiate a retry dispatch, or trigger a webhook. All provider interactions remain delegated to provider orchestration services under governance authorization. Inherits AP-FP1 and AP-GHL12.

### AP-GF2 — No Replay-Triggered LIVE Outbound Effects

MUST NOT allow replay-mode provider failure simulation to generate LIVE outbound effects. All outputs from replay-mode provider resilience evaluation carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`. No mode transition from REPLAY to LIVE occurs within a provider resilience sequence. Inherits AP-FP2 and AP-GHL5.

### AP-GF3 — No "Retry Immediately" Semantics

MUST NOT use "retry immediately (once)" or equivalent as a provider recovery instruction. Provider retry behavior is governed by Config V2 Group F `provider_failure_max_retry_attempts` and `provider_failure_retry_backoff_base_seconds`. No hardcoded retry-once pattern is permitted in any provider failure domain. Inherits AP-FP3.

### AP-GF4 — No Silent Provider Fallback

MUST NOT silently route to an alternative provider, substitute a silent channel downgrade, or execute undocumented degraded delivery when the configured provider is unavailable. Provider outage transitions to `governance_scope = UNAVAILABLE`; outbound is deferred to queue with full observability. Inherits AP-FP4 and AP-GHL8.

### AP-GF5 — No Hardcoded Provider Resilience Thresholds

MUST NOT substitute hardcoded values for Config V2-governed provider resilience thresholds (`provider_failure_max_retry_attempts`, `provider_failure_circuit_breaker_threshold`, `provider_failure_circuit_breaker_reset_hours`, `provider_failure_retry_backoff_base_seconds`, `provider_delivery_sla_hours`, `sql_server_max_sync_age_hours`). When thresholds are missing, `UNKNOWN_V0` substitution applies with DEGRADED annotation. Inherits AP-FP5 and AP-GHL9.

### AP-GF6 — No Non-Attributable Provider Recovery Actions

MUST NOT allow any provider recovery action without `correlation_id`, `execution_mode`, `execution_type`, `config_version_id`, and `ghl_message_id` (where applicable). Provider recovery actions without complete attribution are orphaned specification defects. Inherits AP-FP6.

### AP-GF7 — No Immutable Provider Record Mutation

MUST NOT overwrite, backfill, or retroactively modify any record in `ghl_messages`, `outreach_history`, `student_campaign_activity`, `processed_events`, `state_transition_log`, or `student_timeline_events`. All provider recovery actions produce new append-only records. Inherits AP-FP7 and AP-GHL7.

### AP-GF8 — No Governance Bypass During Provider Recovery

MUST NOT bypass eligibility assessment, retry policy assessment, circuit breaker checks, config version validation, or execution mode checks during provider recovery orchestration. Recovery cycles are subject to the same governance precondition gate (RULE 0) as original cycles. Inherits AP-FP8 and AP-GHL4.

### AP-GF9 — No Duplicate LIVE Outbound Recovery Execution

MUST NOT produce duplicate outbound recovery dispatches for the same delivery attempt. Outreach domain idempotency key `(student_id, checkpoint_type, contact_attempt)` must be checked against `processed_events` before initiating recovery dispatch. Duplicate recovery dispatch → no-op. Inherits AP-FP11.

### AP-GF10 — No Orphaned Provider Recovery Execution

MUST NOT allow a provider recovery execution to proceed without a completion record written to `student_timeline_events` — even on failure. Every recovery cycle has an observable start and an observable end. Inherits AP-FP15.

### AP-GF11 — No Silent Webhook Deduplication Drop

MUST NOT silently discard a duplicate inbound webhook event without producing a `processed_events` audit entry. Every duplicate webhook detection produces a logged suppression record. Silent drops are prohibited. Inherits AP-GHL7 and spec/05 §5.5.

### AP-GF12 — No Silent Authentication Failure

MUST NOT allow GHL API authentication failure to produce a silent governance-affecting error. `AUTH_FAILURE` is a TERMINAL error class; it generates an immediate alert, requires key rotation, and blocks all subsequent provider interactions until authentication is restored. Inherits AP-GHL14 and `runtime/system_loop.md` §8.3.

### AP-GF13 — No PII in Provider Resilience Observability

MUST NOT log raw PII (student name, email, phone, transcript content) in provider resilience orchestration structured log records. `student_id` (UUID) is the permitted reference. GHL payload PII fields must be redacted before logging in any provider failure record. Inherits AP-FP13 and AP-GHL10.

### AP-GF14 — No Silent Error Swallowing

MUST NOT use `try { ... } catch (e) {}` semantics anywhere in the provider resilience layer. Every caught exception is tagged with a stable `error_class` string and emitted as a structured log before any fallback or continuation path is taken. Inherits AP-FP14.

### AP-GF15 — No Provider Authority Escalation During Failures

MUST NOT expand GHL's authority during provider outage, circuit breaker degradation, or any failure condition. GHL remains `platform_supplementary` in all failure scenarios. Provider failure does not grant GHL write authority over governance state, eligibility decisions, snapshot content, or config version thresholds. Inherits `failure/failure_playbook.md` §3.2 and AP-GHL1.

---

## 13. ACCEPTANCE CRITERIA

---

### AC-GF1 — Deterministic Provider Resilience Behavior

**Given** any provider failure condition defined in §10.1
**When** the provider resilience orchestration layer processes the failure
**Then** the outcome is deterministic: the same failure input produces the same structured failure log, the same recovery action classification, and the same escalation candidacy signal — with no undocumented variation between runs

---

### AC-GF2 — Replay-Safe Provider Recovery Behavior

**Given** a replay-mode provider resilience evaluation of a historical provider failure
**When** the failure simulation completes
**Then** no LIVE outbound effects are produced; all outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; `fingerprint_comparison_outcome` is emitted; no `processed_events` entries are created for already-existing historical events

---

### AC-GF3 — Immutable Provider Lineage Preservation

**Given** a provider recovery cycle completes
**When** any record is written
**Then** no existing record in `ghl_messages`, `outreach_history`, `student_campaign_activity`, `processed_events`, or `state_transition_log` is modified; only new append-only records are produced

---

### AC-GF4 — Degraded-Mode Safety on Provider Outage

**Given** the provider circuit breaker is OPEN or `provider_outage_active = true`
**When** an outreach orchestration cycle runs
**Then** outbound dispatch is blocked with `governance_scope = UNAVAILABLE`; no student's retry budget is consumed for outage-blocked attempts; inbound webhook ingestion continues unaffected; AI evaluation continues unaffected; no silent routing to an alternative channel occurs

---

### AC-GF5 — Provider Recovery Attribution Continuity

**Given** any provider recovery action is taken
**When** the recovery record is written
**Then** `correlation_id`, `causation_id` (where applicable), `execution_mode`, `execution_type = recovery`, `config_version_id`, and `provider_failure_type` are present on every record; a provider failure that cannot be traced to root cause via a single `correlation_id` is an observability defect

---

### AC-GF6 — Provider Failure Containment

**Given** a GHL API failure or webhook failure occurs
**When** the resilience layer processes the failure
**Then** no direct provider retry is attempted from the resilience layer; circuit breaker state is consulted; structured failure log is emitted; `governance_scope = UNAVAILABLE` blocks dispatch for affected students; no silent fallback to alternative channel without governance authorization

---

### AC-GF7 — Idempotent Provider Recovery Orchestration

**Given** the same provider recovery dispatch is triggered twice
**When** the second recovery evaluation is performed
**Then** the `processed_events` idempotency key check `(student_id, checkpoint_type, contact_attempt)` returns a match; the second dispatch is a no-op; `DUPLICATE_SUPPRESSED` is logged; no duplicate delivery to the student occurs

---

### AC-GF8 — Config V2-Governed Provider Thresholds

**Given** a Config V2 provider threshold (`provider_failure_max_retry_attempts`, `provider_delivery_sla_hours`) is missing
**When** the resilience layer evaluates provider recovery
**Then** `UNKNOWN_V0` is substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning is emitted; no hardcoded integer is used; affected interaction is annotated DEGRADED; orchestration continues with annotation

---

### AC-GF9 — No Hardcoded Provider Retry Semantics

**Given** a GHL API failure occurs during outreach dispatch
**When** the resilience layer determines recovery behavior
**Then** no "retry immediately (once)" or fixed-count retry is applied from the resilience layer; retry authorization is governed by `outreach_retry_policy.md` assessment and Config V2 Group F `provider_failure_max_retry_attempts`; no literal integer replaces the Config V2 variable

---

### AC-GF10 — Replay Provider Outbound Suppression

**Given** `execution_type = replay`
**When** a provider failure evaluation reaches the outbound dispatch path
**Then** `governance_scope = REPLAY_ONLY`; `replay_restrictions.outbound_suppressed = true`; `provider_event_type = REPLAY_SIMULATION`; no live GHL API call is made; all provider context is sourced from `ghl_messages`, `outreach_history`, and `processed_events`

---

### AC-GF11 — Duplicate Webhook Protection

**Given** the same GHL webhook event arrives twice (by `ghl_message_id`)
**When** the second delivery arrives
**Then** HTTP 200 is returned; no new record is created in any platform table; a `processed_events` audit entry records the duplicate detection; `provider_event_type = DEDUPLICATION_SUPPRESS`; no state transition is triggered by the duplicate; the suppression is observable and attributable

---

### AC-GF12 — Authentication Failure Governance

**Given** GHL API authentication fails (`provider_error_class = AUTH_FAILURE`)
**When** the resilience layer processes the failure
**Then** TERMINAL classification is applied; no retry is attempted; an immediate alert is generated; all subsequent provider dispatch is blocked until key rotation is confirmed; in-flight orchestration intents are preserved in QUEUED state; no student data is corrupted

---

## 14. UNRESOLVED GOVERNANCE CONCERNS

---

The following governance decisions affecting provider resilience behavior are deferred. They are documented for governance review and are not blocking.

**UE-GF1: Cross-provider failover authorization** — When GHL is unavailable, may the platform activate an alternative communication provider? Currently: queued indefinitely during outage. Governance decision required to define which providers are authorized for failover and what approval is required. Cross-references `directives/ghl_integration_contract.md` UE-GHL3. (GOVERNANCE DECISION)

**UE-GF2: Webhook signature verification implementation** — GHL webhook authenticity verification (HMAC signature, IP allowlist) is not implemented at MVP scope. Without signature verification, injection of fake provider events is possible. Implementation required before STANDARD scope per spec/05 §15 UI-3. Cross-references `directives/ghl_integration_contract.md` UE-GHL2. (IMPLEMENTATION DEPENDENCY)

**UE-GF3: Provider retry budget protection scope** — Does `provider_outage_exempted = true` apply to all future providers or GHL-specific only? Currently: assumed GHL-specific. Governance decision required to define scope. Cross-references `failure/failure_playbook.md` UE-FP3 and `runtime/retry_cycle_flow.md` UE-RF4. (GOVERNANCE DECISION)

**UE-GF4: GHL event synchronization SLA governance** — No SLA governs GHL event synchronization lag. `DELIVERY_TELEMETRY_STALE` annotations lack an actionable alerting threshold. Governance decision required to define `ghl_event_sync_max_lag_hours` Config V2 variable. Cross-references `directives/ghl_integration_contract.md` UE-GHL6. (GOVERNANCE DECISION)

**UE-GF5: Opt-out synchronization from GHL** — Students who opt out via GHL receive continued outreach if opt-out is not synchronized to the platform. No synchronization mechanism is defined. Governance decision required before PRODUCTION scope. Cross-references `directives/ghl_integration_contract.md` UE-GHL5. (GOVERNANCE DECISION)

---

## 15. DOWNSTREAM REFERENCES

---

### 15.1 Authoritative Parent Contracts

This document is a governed child contract of:

| Contract | Governing sections |
|---|---|
| `failure/failure_playbook.md` | §2.2 (Provider Failures); §4.2 (Provider Outage Degradation); §4.7 (Duplicate Event Storm); §7.1 (Recovery Coordination Model); §12 (AP-FP1–AP-FP15); §13 (AC-FP1–AC-FP12) |
| `directives/ghl_integration_contract.md` | RULE 0–RULE 11; §6 (Config V2 Governance); §7 (Replay Semantics); §8 (Provider Degradation); §9 (Outbound Authority Controls); §13 (AP-GHL1–AP-GHL15) |
| `runtime/system_loop.md` | §8.3 (Provider Failure Runtime Behavior); §10.1 (Degradation Principles) |
| `runtime/daily_outreach_flow.md` | §4.4 (Retry Orchestration Coordination) |
| `runtime/retry_cycle_flow.md` | §10 (Retry Degradation); §8 (Provider Governance at Retry Layer) |
| `spec/04_idempotency_concurrency.md` | §2 (Core Principles); §4.1 (Outreach Domain Idempotency Key) |
| `spec/05_external_integrations.md` | §5.5 (Deduplication expectations); §11.2 (Failure classification); §11.5 (Provider outage handling) |
| `spec/06_observability_operations.md` | Structured log requirements; correlation ID propagation |
| `spec/09_security_privacy.md` | Compliance hold governance; PII protection; authentication failure governance |

Where this document conflicts with any parent contract, the parent contract governs.

---

### 15.2 Related Child Contracts

| Contract | Relationship |
|---|---|
| `failure/scheduling_failures.md` | Sibling child contract; scheduler-triggered recovery cycles generate provider interactions governed by this document |
| `failure/llm_failures.md` | Sibling child contract; AI provider failures are a distinct failure domain governed by that document |

---

### 15.3 Directive Dependencies

| Directive | Provider resilience dependency |
|---|---|
| `directives/outreach_retry_policy.md` | Retry authorization during provider failures; retry budget protection semantics |
| `directives/outreach_eligibility_rules.md` | Eligibility assessment during degraded provider evaluation |
| `directives/ghl_integration_contract.md` | Circuit breaker governance; dedup gate; provider failure behavior; authoritative provider orchestration contract |
| `directives/llm_processing_contract.md` | AI advisory governance during provider degradation |
| `directives/escalation_rules.md` | Escalation candidacy generation on provider failure conditions |
| `directives/core_decision_engine.md` | Governance chain upstream from outbound dispatch; `INITIATE_OUTREACH`/`RETRY_OUTREACH` intent authorization |

---

## END OF FILE
