# directives/ghl_integration_contract.md

---

## LAYER 3 — DIRECTIVES (EXTERNAL PROVIDER ORCHESTRATION CONTRACT)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `directives/core_decision_engine.md`, `directives/outreach_eligibility_rules.md`, `directives/outreach_retry_policy.md`, `directives/channel_selection_rules.md`, `directives/escalation_rules.md`, and `directives/llm_processing_contract.md`. The previous version described a simplistic CRM/provider integration guidance file (direct GHL trigger payload, hardcoded webhook state transitions, minimal error handling, no governance context) that is architecturally incompatible with the governance-safe orchestration-intelligence platform defined in spec/01 through spec/09. GHL integration is no longer a trigger pipeline. It is a governance-safe external provider orchestration contract.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **External Provider Orchestration Contract** defines the provider boundary governance, provider interaction semantics, and provider attribution requirements for the Student Success Intelligence Platform's integration with GHL (GoHighLevel) and all future communication provider surfaces. It specifies:

* How outbound provider dispatch is authorized, governed, and suppressed under replay, SHADOW, and degraded conditions
* What authority boundaries GHL and all external providers hold relative to platform governance layers
* How inbound provider events (webhooks) are validated, deduplicated, attributed, and ingested without compromising governance state
* How config-version-governed thresholds determine provider retry windows, circuit breaker behavior, and outage handling
* How replay, regeneration, and SHADOW execution semantics constrain provider interaction outputs
* How provider degradation is handled deterministically — never silently — and how provider outages remain fully observable
* What attribution, observability, and lineage metadata must accompany every provider interaction event to maintain historical explainability
* How synchronization between external provider state and platform state is governed without overwriting authoritative records

This directive is the authoritative specification for **governance-safe external provider orchestration**. It is consumed by:

* The outreach orchestration service when it must dispatch outbound GHL triggers under governance enforcement
* The GHL webhook ingestion service when it ingests inbound provider events and must attribute, deduplicate, and route them
* The channel orchestration advisory layer when it evaluates provider health state as a constraint on channel candidacy
* The Core Decision Engine when it requires provider state context for orchestration intent generation
* The escalation routing service when provider failure or delivery collapse triggers escalation candidacy

---

### 1.2 What GHL Is

In the governance-safe external provider orchestration model, GHL is:

* **Operational communication provider** — executes call, SMS, and email delivery workflows on behalf of authorized platform outreach intents
* **Execution telemetry provider** — returns delivery confirmation, call outcome, response event, and campaign participation events to the platform via inbound webhooks
* **Engagement metadata provider** — provides historical communication metadata (campaign activity, transcript availability, delivery state) that enriches platform intelligence surfaces
* **Delivery-state integration surface** — reports outbound execution state to the platform; the platform owns the authoritative record of what actions were taken and what outcomes occurred

---

### 1.3 What GHL Is NOT

GHL is explicitly **NOT**:

* **Governance authority** — GHL has no authority over cohort classification, risk scoring, eligibility decisions, config version thresholds, or lifecycle state machine transitions
* **Orchestration authority** — GHL does not determine who should be contacted, when, or through which channel; the Core Decision Engine and orchestration service make those determinations
* **Historical source-of-truth** — GHL communication event records are execution metadata; the platform's append-only event log is the authoritative history
* **Replay authority** — GHL cannot replay, regenerate, or reconstruct historical student intelligence; that authority belongs exclusively to the platform's warehouse layer
* **Snapshot authority** — GHL has no write access to `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives`; GHL-originated events supplement but never modify finalized snapshot content
* **Escalation authority** — GHL delivery failures and provider errors are operational signals that may contribute to escalation candidacy assessment; they do not directly trigger escalation without governance routing
* **Config authority** — GHL cannot modify, override, or supersede any config version threshold; provider behavior is governed by ACTIVE platform config, not by GHL platform configuration

---

### 1.4 Provider Interaction Categories

Provider interactions fall into distinct governance categories. Each category has defined authority, replay behavior, and degradation semantics.

| Category | Direction | Authority class | Replay behavior | SHADOW behavior | Degradation |
|---|---|---|---|---|---|
| **Outbound trigger dispatch** | Platform → GHL | Requires Core Decision Engine intent | Suppressed in replay | Simulated only | Degrades to queue |
| **Inbound webhook ingestion** | GHL → Platform | `platform_supplementary`, `is_authoritative = false` | REPLAY_SIMULATION only | Ingested in SHADOW | Deduplication prevents corruption |
| **Delivery state sync** | GHL → Platform | `platform_supplementary` | Historical context only | Ingested | Stale telemetry flagged |
| **Campaign activity ingestion** | GHL → Platform | `platform_supplementary` | Historical context only | Ingested | Deduplicated |
| **Provider health assessment** | Platform reads circuit breaker state | Platform-owned | Historical state only | From input context | UNAVAILABLE scope |

---

## 2. EXTERNAL AUTHORITY BOUNDARIES

---

### 2.1 System Authority Classification

| System | Role | Authority Class | Write Authority over Platform Schemas |
|---|---|---|---|
| SQL Server (`AI_ChatBot_TriggerData`) | Academic state source of truth | `sql_server_authoritative` | Never — read-only pull only |
| GHL (GoHighLevel) | Communication execution, execution telemetry | `platform_supplementary` | Never — platform ingests GHL events; GHL does not write to platform tables |
| AI Providers | Augmentation service | `platform_supplementary` | Never — API calls only; governed by `directives/llm_processing_contract.md` |
| PostgreSQL `public` schema | Operational intelligence store | Platform-owned | Read/write by application service account |
| PostgreSQL `warehouse` schema | Immutable historical archive | Platform-owned | INSERT-only by finalization service account; no application service account may UPDATE or DELETE |
| PostgreSQL `compliance_audit` schema | Governance-isolated audit | Platform-owned | INSERT-only by compliance pathway service account |

**Governance constraint:** GHL is `platform_supplementary`. No GHL webhook, payload field, or API response may assert `sql_server_authoritative` authority. A GHL event that carries a field claiming to be authoritative is treated as a validation failure.

---

### 2.2 Authoritative vs Derivative Distinction

**Authoritative records** govern eligibility decisions. Fields derived from SQL Server `AI_ChatBot_TriggerData` — `hws_behind`, `avg_eff_rating`, `per_comp_act`, `payment_balance`, `access_state` — carry `origin_authority = sql_server_authoritative` and `is_authoritative = true`. They govern cohort classification, risk scoring, and threshold evaluation.

**Derivative records** provide execution context and operational telemetry. GHL communication events — delivery confirmations, call outcomes, SMS responses, campaign participation — carry `origin_authority = platform_supplementary` and `is_authoritative = false`. They enrich the student timeline and inform operator dashboards but do not govern academic eligibility or snapshot classification.

**Conflict resolution:** When a SQL Server-authoritative record and a GHL-derived record exist for the same student action, both records are retained. The SQL Server-authoritative record governs eligibility. The GHL-derived record is retained as execution context. Neither record is deleted or overwritten. The conflict is logged.

---

### 2.3 Operational vs Historical Ownership

| Layer | Operational Ownership | Historical Ownership |
|---|---|---|
| Academic state | SQL Server owns source; platform owns mirror in `student_trigger_data` | Platform owns immutable snapshots in `warehouse.student_snapshots` |
| Communication events | GHL owns execution; platform owns the event log in `ghl_messages`, `outreach_history` | Platform owns append-only timeline records in `student_timeline_events` |
| Delivery telemetry | GHL owns delivery confirmation; platform owns the ingested record | Platform owns delivery records as `is_authoritative = false` timeline events |
| Campaign activity | GHL owns campaign execution; platform owns campaign activity records | Platform owns `student_campaign_activity` append-only |
| Config thresholds | Platform owns the config version registry | Platform owns every prior config version permanently |

---

### 2.4 Synchronization vs Mutation

**Synchronization** copies external state into a platform-owned derivative. The copy may be updated on subsequent syncs or webhook deliveries. The external system's own state is not changed.

**Mutation** changes platform-owned state via state machine transitions. External providers do not trigger platform mutations directly. GHL webhooks provide inputs that the platform processes according to its own state machine rules. A webhook carrying `CALL_COMPLETED` does not directly transition a student to `RESPONDED` — the platform's state management service makes that transition after processing the validated, attributed webhook record.

**Provider events** are records of external execution outcomes. They do not claim causality over platform state. A `DELIVERY_CONFIRMED` event records that GHL reported successful delivery; it does not assert that the platform's student contacted state was changed by the delivery.

---

## 3. INPUT MODEL

---

The provider orchestration context is **lineage-aware and governance-aware**. Every input carries metadata establishing its authority class and origin. Inputs from SQL Server (`origin_authority = sql_server_authoritative`) govern eligibility decisions. Provider-supplementary inputs provide operational execution context but do not override SQL Server-authoritative state (INVARIANT-6, spec/03 §40).

---

### 3.1 Governance Context

Governance state required before any provider interaction may proceed.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ACTIVE config version ID; null triggers RULE 0 block |
| `execution_mode` | enum | `SHADOW` or `LIVE`; governs whether outbound dispatch is live or simulated |
| `execution_type` | enum | `original`, `replay`, `regeneration`; governs provider interaction suppression |
| `replay_restrictions` | object | Replay lineage context: `is_replay`, `source_artifact_id`, `historical_config_version_id` |
| `compliance_hold_active` | boolean | When true, outbound dispatch is blocked for the student; inbound ingestion continues |
| `fingerprint_context` | object | Config fingerprint of the current operation; used for replay divergence detection |
| `idempotency_key` | string | Unique key for this provider interaction; checked against processed records before dispatch |
| `rule_set_snapshot` | object | Snapshot of all relevant config thresholds at evaluation time; must match the ACTIVE version |

---

### 3.2 Attribution Context

Attribution fields that identify the authority chain for this provider interaction.

| Field | Type | Description |
|---|---|---|
| `origin_source` | string | Source of this interaction: `ghl_webhook`, `platform_outreach`, `platform_generated`, etc. |
| `origin_authority` | string | Authority class: `sql_server_authoritative` or `platform_supplementary` |
| `correlation_id` | string (UUID v4) | Propagated from the triggering sync, webhook entry point, or orchestration job |
| `causation_id` | string (UUID v4) \| null | The event that caused this interaction (upstream intent ID or webhook ID) |
| `upstream_intent_id` | string (UUID v4) \| null | The Core Decision Engine intent that authorized this outbound dispatch |
| `actor_identity` | string | Identifies the orchestration layer actor executing this interaction |

---

### 3.3 Provider Context

GHL account state, provider health, delivery state, and webhook lineage.

| Field | Type | Description |
|---|---|---|
| `provider_account_id` | string \| null | GHL account identifier for the outbound trigger |
| `provider_health_state` | enum | Current provider operational state: `HEALTHY`, `DEGRADED`, `OUTAGE`, `UNKNOWN` |
| `circuit_breaker_state` | enum | Provider circuit breaker state: `CLOSED` (normal), `OPEN` (blocking), `HALF_OPEN` (probing) |
| `delivery_state` | enum \| null | Most recent delivery state for this student's outreach cycle: `PENDING`, `DELIVERED`, `FAILED`, `NO_RESPONSE`, `UNKNOWN` |
| `ghl_message_id` | string \| null | Inbound webhook: GHL's message identifier; deduplication anchor for `processed_events` |
| `webhook_event_type` | string \| null | Inbound: GHL event type from payload (`CALL_COMPLETED`, `SMS_RESPONSE`, `EMAIL_RESPONSE`, `TRANSCRIPT_READY`) |
| `webhook_payload_valid` | boolean \| null | Inbound: whether the webhook payload passed schema validation |
| `retry_attempt_count` | integer | Number of prior provider retry attempts in the current outreach cycle |
| `provider_failure_history` | list | Sequence of prior provider error classes for this student in the current cycle |

---

### 3.4 Historical Context

Snapshot, replay, escalation, and orchestration lineage for this provider interaction.

| Field | Type | Description |
|---|---|---|
| `snapshot_lineage` | object \| null | Reference to the most recent snapshot that captured this student's state |
| `replay_source_artifact_id` | string \| null | In replay: the specific snapshot or event log artifact being replayed |
| `escalation_lineage` | object \| null | Prior escalation events for this student, if any; used for escalation recurrence detection |
| `orchestration_lineage` | object \| null | Prior orchestration intents for this student in the current cycle |
| `prior_outreach_event_ids` | list | IDs of prior outreach history records for this student's current cycle |
| `prior_provider_correlation_ids` | list | Correlation IDs of prior provider interactions; used for traceability |

---

### 3.5 Operational Context

Provider outage state, degradation indicators, synchronization lag, and duplicate event state.

| Field | Type | Description |
|---|---|---|
| `provider_outage_active` | boolean | Whether the provider is currently in a known outage window |
| `orchestration_degradation_mode` | enum \| null | Active degradation mode: `CIRCUIT_OPEN`, `RETRY_EXHAUSTED`, `SYNC_LAG`, `OUTAGE`, null |
| `sync_lag_hours` | float | Hours since the most recent successful GHL event synchronization |
| `max_sync_age_hours` | float | Config-bound threshold for acceptable synchronization lag (from Group K) |
| `delivery_telemetry_stale` | boolean | Whether delivery state telemetry is stale beyond the SLA window |
| `duplicate_event_detected` | boolean | Whether the inbound event has been identified as a duplicate via `processed_events` |
| `outbound_retry_budget_remaining` | integer | Remaining outbound retry attempts available in the current cycle |

---

## 4. OUTPUT MODEL

---

### 4.1 ProviderOrchestrationAssessment Schema

Provider orchestration evaluation produces a **ProviderOrchestrationAssessment** object, not a raw webhook payload or trigger response. The assessment captures the governance-safe result of the provider interaction evaluation.

```json
{
  "provider_event_type": "OUTBOUND_TRIGGER | WEBHOOK_INBOUND | DELIVERY_CONFIRMATION | RESPONSE_EVENT | CAMPAIGN_PARTICIPATION | SYNC_EVENT | DEDUPLICATION_SUPPRESS | REPLAY_SIMULATION | SHADOW_SIMULATION | null",

  "governance_scope": "AUTHORIZED | BLOCKED | SHADOW_ONLY | REPLAY_ONLY | DUPLICATE_SUPPRESSED | UNAVAILABLE",

  "replay_restrictions": {
    "is_replay": false,
    "replay_safe": true,
    "outbound_suppressed": false,
    "historical_provider_context_only": false,
    "source_artifact_id": null,
    "historical_config_version_id": null,
    "replay_provider_source": "PROCESSED_EVENTS | HISTORICAL_LOG | NONE | null"
  },

  "attribution_metadata": {
    "origin_source": "string",
    "origin_authority": "platform_supplementary",
    "is_authoritative": false,
    "actor_identity": "string",
    "attribution_timestamp": "ISO-8601",
    "correlation_id": "uuid",
    "causation_id": "uuid | null",
    "upstream_intent_id": "uuid | null"
  },

  "config_version_reference": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "threshold_bindings": {
      "provider_failure_max_retry_attempts": 0,
      "provider_failure_circuit_breaker_threshold": 0,
      "provider_failure_circuit_breaker_reset_hours": 0,
      "provider_failure_retry_backoff_base_seconds": 0,
      "provider_delivery_sla_hours": 0,
      "sql_server_max_sync_age_hours": 0
    }
  },

  "provider_lineage_metadata": {
    "provider": "ghl | future_provider",
    "provider_account_id": "string | null",
    "ghl_message_id": "string | null",
    "ghl_workflow_id": "string | null",
    "delivery_state": "PENDING | DELIVERED | FAILED | UNKNOWN | null",
    "provider_response_code": "integer | null",
    "provider_error_class": "TIMEOUT | RATE_LIMIT | AUTH_FAILURE | SERVER_ERROR | SCHEMA_MISMATCH | WEBHOOK_INVALID | null"
  },

  "synchronization_metadata": {
    "sync_correlation_id": "uuid | null",
    "last_sync_timestamp": "ISO-8601 | null",
    "sync_lag_hours": 0.0,
    "delivery_telemetry_stale": false,
    "stale_for_hours": 0.0,
    "sync_recency_within_policy": true
  },

  "degradation_metadata": {
    "degraded": false,
    "degradation_cause": "PROVIDER_OUTAGE | CIRCUIT_OPEN | RETRY_EXHAUSTED | SYNC_LAG | DUPLICATE_EVENT | REPLAY_SUPPRESSED | COMPLIANCE_HOLD | GOVERNANCE_BLOCKED | null",
    "outbound_blocked": false,
    "fallback_applied": false,
    "fallback_type": "PLATFORM_QUEUE | PRIOR_EVENT_SERVED | HISTORICAL_CONTEXT | null",
    "orchestration_continues": true
  },

  "observability_metadata": {
    "correlation_id": "uuid",
    "causation_id": "uuid | null",
    "execution_type": "original | replay | regeneration",
    "service": "ghl_provider_orchestration",
    "event_id": "uuid",
    "rule_path_taken": [],
    "assessment_basis": "RULE_BASED | PROVIDER_TELEMETRY | FALLBACK | HISTORICAL_REPLAY",
    "provider_call_duration_ms": 0,
    "outcome": "success | failure | degraded | suppressed | shadow_only | duplicate_suppressed",
    "error_class": null
  },

  "reason_codes": [],
  "provider_blocked": false,
  "blocking_reason": null
}
```

---

### 4.2 Governance Scope Values

| Scope | Meaning | Outbound dispatch | Inbound ingestion |
|---|---|---|---|
| `AUTHORIZED` | Governance authorization confirmed; LIVE mode; circuit closed; no compliance hold | Permitted | Proceeds normally |
| `BLOCKED` | Governance precondition failed; dispatch prohibited | Prohibited | Rejected (invalid webhook) or blocked (compliance hold) |
| `SHADOW_ONLY` | `execution_mode = SHADOW`; outbound simulated; no live provider call | Simulated only | Ingested and tagged as SHADOW |
| `REPLAY_ONLY` | `execution_type` = replay/regeneration; outbound suppressed | Suppressed | Historical context only |
| `DUPLICATE_SUPPRESSED` | Idempotency key matched; prior result served | No new dispatch | No new record created |
| `UNAVAILABLE` | Provider circuit open or active outage; orchestration continues without provider | Deferred to queue | Unaffected by provider outage |

---

### 4.3 Output Clarifications

* **Provider outputs are operational telemetry, not governance state.** GHL webhook data ingested and stored in platform tables has `is_authoritative = false`. It does not override SQL Server-authoritative eligibility state.
* **Orchestration services enforce governance.** The ProviderOrchestrationAssessment is an advisory contract. The outreach orchestration service reads this assessment and enforces governance boundaries before executing any outbound call or storing any inbound record.
* **Providers may not mutate governance state.** No GHL payload field, webhook parameter, or API response attribute may alter the platform's config version, snapshot state, compliance workflow, or eligibility classification.
* **Attribution fields carry what was in the input.** Attribution fields are propagated unchanged per AP-GHL15. No downstream processing step overwrites `origin_source`, `origin_authority`, or `is_authoritative`.

---

## 5. EVALUATION RULES

---

### RULE 0 — Governance Precondition Gate

**Trigger:** Any provider interaction event enters evaluation.

**Gate conditions** (any one blocks all further evaluation → `governance_scope = BLOCKED`):

| Condition | Block reason |
|---|---|
| `config_version_id` is null | No ACTIVE config version; threshold resolution impossible |
| `execution_mode` not in `{SHADOW, LIVE}` | Unknown execution mode; governance boundary undefined |
| `correlation_id` is null | Attribution chain incomplete; observability broken |
| `origin_source` or `origin_authority` missing | Attribution fields required before any ingestion or dispatch |
| Duplicate `idempotency_key` for OUTBOUND_TRIGGER | Prior dispatch already processed; no re-trigger |
| `execution_type` not in `{original, replay, regeneration}` | Unknown execution type; replay semantics undefined |

**On block:** Set `governance_scope = BLOCKED`, `provider_blocked = true`, `blocking_reason = [condition]`, emit `GOVERNANCE_PRECONDITION_FAILED` reason code. → **STOP**

**On pass:** → **CONTINUE to RULE 1**

---

### RULE 1 — Replay / Regeneration Mode Gate

**Trigger:** `execution_type` is `replay` or `regeneration`.

**Required behavior:**

* Set `replay_restrictions.is_replay = true`
* Set `replay_restrictions.outbound_suppressed = true`
* Set `replay_restrictions.historical_provider_context_only = true`
* Set `governance_scope = REPLAY_ONLY`
* Set `provider_event_type = REPLAY_SIMULATION`
* Resolve historical config version from `replay_restrictions.historical_config_version_id`; if unavailable → substitute `UNKNOWN_V0` for all threshold bindings; emit `REPLAY_CONFIG_VERSION_MISSING` reason code
* Source all provider telemetry exclusively from platform-owned historical records (`ghl_messages`, `outreach_history`, `processed_events`)
* **DO NOT query live GHL API; DO NOT dispatch outbound triggers** (AP-GHL5)

**On replay:** → **CONTINUE to RULE 3** (using historical config resolution)

**On non-replay:** → **CONTINUE to RULE 2**

---

### RULE 2 — Execution Mode Gate (SHADOW)

**Trigger:** `execution_mode = SHADOW`.

**Required behavior:**

* Set `governance_scope = SHADOW_ONLY`
* Set `degradation_metadata.outbound_blocked = true`
* Set `provider_event_type = SHADOW_SIMULATION` for outbound paths
* For inbound webhook paths in SHADOW mode: preserve inbound event type; ingest and attribute normally; tag `execution_mode = SHADOW` in event log
* All outbound provider dispatches produce SHADOW_SIMULATION events only; no live GHL API call
* Emit `SHADOW_DISPATCH_SUPPRESSED` reason code for outbound paths

**On SHADOW:** → **CONTINUE to RULE 3**

**On LIVE:** → **CONTINUE to RULE 3**

---

### RULE 3 — Config-Bound Threshold Resolution

**Trigger:** All evaluation reaching this rule.

**Resolution steps:**

1. Query `config_version_registry WHERE status = 'ACTIVE'` → returns exactly one row (enforced by partial unique index; spec/05 §8.4)
2. Capture `version_id` and extract provider threshold fields:
   * `provider_failure_max_retry_attempts` (Group F, PROVIDER_FAILURE_THRESHOLD)
   * `provider_failure_circuit_breaker_threshold` (Group F, PROVIDER_FAILURE_THRESHOLD)
   * `provider_failure_circuit_breaker_reset_hours` (Group F, PROVIDER_FAILURE_THRESHOLD)
   * `provider_failure_retry_backoff_base_seconds` (Group F, OPERATIONAL_TUNING)
   * `provider_delivery_sla_hours` (Group F, OPERATIONAL_TUNING)
   * `sql_server_max_sync_age_hours` (Group K, ARCHITECTURAL_CONSTANT)
3. Store all resolved values in `config_version_reference.threshold_bindings`

**Missing threshold key behavior:** If a required threshold key is absent from the ACTIVE config version record:
* Substitute sentinel `UNKNOWN_V0` for that threshold value
* Emit `CONFIG_THRESHOLD_MISSING_{KEY}` reason code (one per missing key)
* Do **NOT** use hardcoded fallback values (AP-GHL9)
* Continue evaluation with `UNKNOWN_V0` in place; affected rules that require the missing threshold emit additional reason codes

**Replay config resolution:** In replay/regeneration contexts, resolve thresholds from `historical_config_version_id`. If unavailable → `UNKNOWN_V0` for all thresholds.

**On resolution:** → **CONTINUE to RULE 4**

---

### RULE 4 — Provider Health Assessment

**Trigger:** All evaluation reaching this rule.

**Circuit breaker check:**

| Circuit breaker state | Behavior |
|---|---|
| `CLOSED` | Provider healthy; evaluation continues |
| `OPEN` | Set `governance_scope = UNAVAILABLE`; `degradation_cause = CIRCUIT_OPEN`; emit `CIRCUIT_OPEN` reason code → **STOP for outbound; CONTINUE for inbound** |
| `HALF_OPEN` | Allow one probe attempt; track outcome for circuit state evaluation |
| `UNKNOWN` | Treat as `CLOSED` with `PROVIDER_HEALTH_UNKNOWN` reason code; log degraded signal |

**Provider outage check:**
* If `provider_outage_active = true` → set `governance_scope = UNAVAILABLE`; `degradation_cause = PROVIDER_OUTAGE`; emit `PROVIDER_OUTAGE_ACTIVE` reason code → **STOP for outbound; CONTINUE for inbound**
* Provider outage does not block inbound webhook ingestion

**Retry budget check (outbound only):**
* If `outbound_retry_budget_remaining = 0` → set `governance_scope = UNAVAILABLE`; `degradation_cause = RETRY_EXHAUSTED`; emit `RETRY_BUDGET_EXHAUSTED` reason code → **STOP for outbound**

**On AVAILABLE:** → **CONTINUE to RULE 5**

---

### RULE 5 — Outbound Authorization Check

**Trigger:** Outbound dispatch path AND `governance_scope` not already blocked.

**Authorization requirement:** Every outbound GHL trigger must trace to a governance-authorized `INITIATE_OUTREACH` or `RETRY_OUTREACH` intent produced by the Core Decision Engine (AP-GHL12).

**Validation steps:**
1. `upstream_intent_id` must be present and non-null
2. Referenced intent must carry `execution_mode` consistent with current context
3. Intent type must be `INITIATE_OUTREACH` or `RETRY_OUTREACH`
4. Intent's `config_version_id` must match the currently resolved config version

**On authorization failure:** Set `governance_scope = BLOCKED`; `provider_blocked = true`; emit `GOVERNANCE_AUTHORIZATION_MISSING` reason code → **STOP**

**Compliance hold check (outbound):**
* If `compliance_hold_active = true` → set `governance_scope = BLOCKED`; `degradation_cause = COMPLIANCE_HOLD`; emit `COMPLIANCE_HOLD_ACTIVE_DISPATCH_BLOCKED` reason code → **STOP**

**On authorization confirmed:** → **CONTINUE to RULE 6**

**Non-outbound paths (inbound webhook):** RULE 5 is skipped → **CONTINUE to RULE 6**

---

### RULE 6 — Idempotency and Deduplication

**Trigger:** All evaluation reaching this rule.

**Outbound idempotency check:**
* Construct outreach domain idempotency key: `(user_id, checkpoint_type, contact_attempt)` per spec/04 §2
* Query `processed_events` for this key
* If key exists → set `governance_scope = DUPLICATE_SUPPRESSED`; `provider_event_type = DEDUPLICATION_SUPPRESS`; emit `OUTBOUND_DUPLICATE_SUPPRESSED` → **STOP** (serve prior result)
* If key does not exist → record will be created on successful dispatch

**Inbound webhook deduplication:**
* Check `ghl_message_id` against `processed_events`
* If `ghl_message_id` exists → duplicate delivery → set `provider_event_type = DEDUPLICATION_SUPPRESS`; emit `WEBHOOK_DUPLICATE_SUPPRESSED` reason code; HTTP 200 acknowledgement; no new record created → **STOP**
* For campaign activity: check `(student_id, campaign_id, event_type, attribution_timestamp)`

**All deduplication results (new or duplicate) produce a `processed_events` audit entry.** Silent drops are not permitted (spec/05 §5.5).

**On no duplicate:** → **CONTINUE to RULE 7**

---

### RULE 7 — Attribution and Lineage Validation

**Trigger:** All evaluation reaching this rule.

**Inbound attribution validation:**
* `origin_source` must be `ghl_webhook` for inbound GHL events; set by ingestion service at entry point; never accepted from webhook payload
* `origin_authority` must be `platform_supplementary`; a GHL payload asserting `sql_server_authoritative` is a specification violation → reject with `ATTRIBUTION_AUTHORITY_VIOLATION` reason code
* `is_authoritative` must be `false` for all GHL-originated events
* `attribution_timestamp` must reflect the GHL event occurrence time, not platform ingestion time; if payload provides an event timestamp, use it; if absent, record ingestion time with `ATTRIBUTION_TIMESTAMP_INFERRED` reason code

**Outbound attribution validation:**
* `origin_source` must be `platform_outreach` for platform-initiated dispatch
* `actor_identity` must identify the orchestration service performing the dispatch
* `attribution_timestamp` must reflect when the dispatch was initiated

**Attribution fields are set by the platform, never accepted from external callers (AP-GHL15).** A GHL payload carrying `origin_source = mirrored_sql_server` is rejected.

**Lineage propagation:**
* Propagate `correlation_id` through all downstream log entries and derived records
* Propagate `causation_id` to all platform records generated from this interaction
* Propagate `upstream_intent_id` to all outbound trigger records

**On attribution valid:** → **CONTINUE to RULE 8**

---

### RULE 8 — Inbound Webhook Event Classification

**Trigger:** Inbound webhook path only. Outbound path skips to RULE 9.

**Webhook schema validation:**
* Validate incoming payload against declared schema for the event type
* On schema validation failure → set `governance_scope = BLOCKED`; emit `WEBHOOK_SCHEMA_INVALID` reason code; HTTP 400; do not store → **STOP**
* Payloads passing structural validation but failing semantic validation (e.g., unknown `user_id`) → emit `WEBHOOK_SEMANTIC_INVALID` reason code; reject; do not store → **STOP**

**Event type classification:**

| Event type | Target table | Deduplication key | Key fields required |
|---|---|---|---|
| `CALL_COMPLETED` | `ghl_messages`, `outreach_history` | `ghl_message_id` | `call_connected`, `call_duration` |
| `SMS_RESPONSE` | `ghl_messages` | `ghl_message_id` | `response_body` |
| `EMAIL_RESPONSE` | `ghl_messages` | `ghl_message_id` | `engagement_type` |
| `TRANSCRIPT_READY` | `ghl_messages` | `ghl_message_id` | `transcript_reference_id` |
| `CAMPAIGN_PARTICIPATION` | `student_campaign_activity` | `(student_id, campaign_id, event_type, attribution_timestamp)` | `campaign_id`, `event_type` |

**Unknown event types:** Emit `WEBHOOK_EVENT_TYPE_UNKNOWN` reason code; log the full payload (PII-redacted); do not store in typed tables; store in raw event buffer for diagnostic review.

**On classification:** → **CONTINUE to RULE 9**

---

### RULE 9 — Synchronization State Assessment

**Trigger:** All evaluation reaching this rule.

**Synchronization lag check:**
* Compare `sync_lag_hours` against `sql_server_max_sync_age_hours` (Group K, ARCHITECTURAL_CONSTANT)
* If `sync_lag_hours > sql_server_max_sync_age_hours` → annotate `sync_recency_within_policy = false`; emit `SYNC_LAG_HOURS = {value}` in observability
* Sync lag annotation does not block provider interaction; it contextualizes the academic state freshness for consuming services

**Delivery telemetry staleness check:**
* If `delivery_telemetry_stale = true` → annotate `synchronization_metadata.delivery_telemetry_stale = true`; emit `DELIVERY_TELEMETRY_STALE` reason code
* Stale delivery telemetry does not block evaluation; it is flagged in the assessment output

**On assessment:** → **CONTINUE to RULE 10**

---

### RULE 10 — Provider Lineage and Observability Assembly

**Trigger:** All evaluation reaching this rule.

**Lineage assembly:**
* Populate `provider_lineage_metadata` with: `provider`, `provider_account_id`, `ghl_message_id` (inbound), `ghl_workflow_id` (outbound where available), `delivery_state`, `provider_response_code`, `provider_error_class`
* Populate `synchronization_metadata` with: `sync_correlation_id`, `last_sync_timestamp`, `sync_lag_hours`, `delivery_telemetry_stale`, `stale_for_hours`, `sync_recency_within_policy`
* Populate `config_version_reference` with the resolved ACTIVE version ID, status, and all threshold binding values
* Populate `attribution_metadata` with propagated `correlation_id`, `causation_id`, `upstream_intent_id`, `origin_source`, `origin_authority`, `is_authoritative`, `actor_identity`, `attribution_timestamp`

**Observability construction:**
* Generate unique `event_id` (UUID v4) for this provider interaction record
* Record `rule_path_taken` (ordered list of rules evaluated)
* Record `assessment_basis` (`RULE_BASED` for original; `HISTORICAL_REPLAY` for replay; `FALLBACK` for degraded path)
* Record `provider_call_duration_ms` where a live provider call occurred
* Record `outcome`: `success`, `failure`, `degraded`, `suppressed`, `shadow_only`, or `duplicate_suppressed`
* Set `error_class` if an error was encountered

**On assembly:** → **CONTINUE to RULE 11**

---

### RULE 11 — Terminal Output Production

**Trigger:** All evaluation reaching this rule.

**Final output assembly:**
* Populate all remaining `ProviderOrchestrationAssessment` fields not yet set
* Set `reason_codes` to the ordered list of all reason codes emitted during evaluation
* Set `provider_blocked` based on whether `governance_scope = BLOCKED`
* Emit structured log event with `service = ghl_provider_orchestration`, `outcome`, `correlation_id`, `duration_ms`, `rule_path_taken`

**No outbound dispatch is made from within this rule.** Dispatch is the responsibility of the outreach orchestration service, which consumes this assessment. → **STOP**

---

## 6. CONFIG VERSION GOVERNANCE

---

### 6.1 Provider Threshold Governance

Provider behavior is governed exclusively by thresholds from the ACTIVE config version. The following Config V2 variables govern provider orchestration (canonical source: spec/01 §12.3):

| Variable | Group | Class | Governs |
|---|---|---|---|
| `provider_failure_max_retry_attempts` | F | PROVIDER_FAILURE_THRESHOLD | Maximum outbound retry attempts before RETRY_EXHAUSTED |
| `provider_failure_circuit_breaker_threshold` | F | PROVIDER_FAILURE_THRESHOLD | Consecutive failures before circuit transitions to OPEN |
| `provider_failure_circuit_breaker_reset_hours` | F | PROVIDER_FAILURE_THRESHOLD | Hours before circuit transitions OPEN → HALF_OPEN |
| `provider_failure_retry_backoff_base_seconds` | F | OPERATIONAL_TUNING | Base interval for exponential backoff on retry |
| `provider_delivery_sla_hours` | F | OPERATIONAL_TUNING | SLA window for delivery confirmation before stale flag |
| `sql_server_max_sync_age_hours` | K | ARCHITECTURAL_CONSTANT | Maximum acceptable sync age before staleness annotation |

---

### 6.2 No Hardcoded Provider Configuration

All provider retry windows, cooldown periods, and circuit breaker thresholds must resolve from the ACTIVE config version at evaluation time. Hardcoded fallbacks are prohibited (AP-GHL9). If a required threshold key is absent from the ACTIVE config version, `UNKNOWN_V0` is substituted and `CONFIG_THRESHOLD_MISSING_{KEY}` is emitted.

---

### 6.3 Prospective-Only Config Activation (FAD-3)

Config version activation is always prospective. A new ACTIVE config version affects only provider interactions that begin evaluation after activation completes. In-flight provider interactions retain the config version active at their evaluation start. Historical provider interaction records retain the config version that governed them at their original evaluation time.

---

### 6.4 Replay Config Resolution

In replay and regeneration contexts, provider interaction evaluation resolves thresholds from `historical_config_version_id`. This ensures replay produces the same governance outcome as the original evaluation under the same config context. If `historical_config_version_id` is unavailable → `UNKNOWN_V0` for all thresholds; emit `REPLAY_CONFIG_VERSION_MISSING`.

---

### 6.5 Config Version Reproducibility in Provider Attribution

The `config_version_id` active at the time of a provider interaction is preserved in `config_version_reference.config_version_id`. This enables historical auditing of which config thresholds governed a specific provider interaction — when a retry budget was exhausted, which circuit breaker threshold was in effect, what SLA window was applied. Historical config versions are permanently queryable (spec/01 §12.1).

---

## 7. REPLAY & REGENERATION SEMANTICS

---

### 7.1 Replay-Safe Provider Behavior

All provider interaction evaluation is replay-safe. A re-run of any provider interaction evaluation for the same inputs produces the same ProviderOrchestrationAssessment, the same governance scope, and the same attribution fields. No re-run creates additional outbound dispatches, duplicate inbound records, or modified state transitions.

Replay safety is enforced by:
* Idempotency keys (`processed_events` deduplication) on outbound triggers
* `ghl_message_id` deduplication on inbound webhooks
* Historical config version resolution (not live ACTIVE config) during replay evaluation
* RULE 1 gating all outbound dispatch during replay/regeneration

---

### 7.2 Outbound Suppression in Replay

Replay and regeneration evaluation **must not** generate live outbound GHL API calls (AP-GHL5). This is enforced by RULE 1. A replay path that reaches an outbound dispatch is a specification violation. The replay produces `REPLAY_SIMULATION` events that represent the historically-reconstructed provider context.

---

### 7.3 Historical Provider Resolution

During replay, provider context is resolved exclusively from platform-owned historical records:
* Outbound trigger history from `outreach_history` and `processed_events`
* Inbound webhook history from `ghl_messages`, `student_campaign_activity`
* Delivery state history from `outreach_history`

No live GHL API call is made during historical resolution.

---

### 7.4 Immutable Provider Lineage

Provider lineage records in `ghl_messages`, `outreach_history`, and `student_campaign_activity` are append-only. Replay and regeneration may not modify these records. A replay that would require altering a prior provider record is a specification violation.

The `processed_events` table is also append-only during replay. Replay reads existing entries to simulate provider context; it does not add new `processed_events` entries for events that already exist.

---

### 7.5 Replay Provider Visibility Rules

Replay assessments surface the following:

| Field | Replay value |
|---|---|
| `replay_restrictions.is_replay` | `true` |
| `replay_restrictions.outbound_suppressed` | `true` |
| `replay_restrictions.historical_provider_context_only` | `true` |
| `replay_restrictions.replay_provider_source` | `PROCESSED_EVENTS` or `HISTORICAL_LOG` |
| `governance_scope` | `REPLAY_ONLY` |
| `provider_event_type` | `REPLAY_SIMULATION` |

---

### 7.6 Historical Provider Explainability

Every provider interaction recorded in the platform must remain historically explainable via:
* `correlation_id` → links to the triggering orchestration intent
* `upstream_intent_id` → links to the Core Decision Engine intent that authorized outbound dispatch
* `config_version_id` → identifies config thresholds active at the time of the interaction
* `ghl_message_id` (inbound) or `idempotency_key` (outbound) → anchors the provider-side record
* `attribution_timestamp` → records when the event occurred in the source system

A provider interaction that cannot be traced from symptom back to root cause using a single `correlation_id` is an observability defect (spec/06 correlation ID requirement).

---

## 8. PROVIDER DEGRADATION GOVERNANCE

---

### 8.1 Outage Handling

When a provider outage is active (`provider_outage_active = true`):
* All outbound dispatch is blocked (`governance_scope = UNAVAILABLE`, `degradation_cause = PROVIDER_OUTAGE`)
* All in-flight outreach intents for affected students are preserved in QUEUED or RETRY_QUEUED state
* No student state machine transition to `CONTACTED` occurs without confirmed provider delivery
* Inbound webhook ingestion continues normally; outage does not affect inbound processing
* The platform serves all read operations (dashboards, timelines, historical queries) regardless of provider outage
* `orchestration_continues = true` — orchestration is not halted; it awaits provider recovery

---

### 8.2 Degraded Provider Mode

When the provider is `DEGRADED` but not fully unavailable:
* Outbound dispatch proceeds with increased monitoring
* `PROVIDER_DEGRADED` reason code emitted on every interaction during degraded window
* Circuit breaker failure count continues accumulating; circuit transitions to `OPEN` at `provider_failure_circuit_breaker_threshold`
* Retry attempts during degraded mode count against `provider_failure_max_retry_attempts` budget

---

### 8.3 Retry Collapse Handling

When the retry budget is exhausted (`outbound_retry_budget_remaining = 0`):
* `governance_scope = UNAVAILABLE`, `degradation_cause = RETRY_EXHAUSTED`
* Consuming orchestration service must evaluate escalation candidacy (per `directives/escalation_rules.md`)
* No automatic silent retry beyond the config-bound maximum (AP-GHL9)
* Retry exhaustion is an escalation trigger input; the consuming service routes to the escalation advisory layer

---

### 8.4 Synchronization Backlog Handling

When synchronization lag exceeds policy (`sync_lag_hours > sql_server_max_sync_age_hours`):
* Provider interactions are annotated with `SYNC_LAG_HOURS = {value}` reason code
* `sync_recency_within_policy = false` is set in `synchronization_metadata`
* Provider interactions are not blocked by sync lag alone (per spec/05 §11.1)
* Snapshot generation that depends on fresh academic state is subject to the staleness policy (spec/05 §11.1)

---

### 8.5 Duplicate Event Handling

When a duplicate inbound webhook event is detected:
* HTTP 200 acknowledgement is returned to GHL; no error or rejection
* The duplicate is discarded without reprocessing — no new records created
* A `processed_events` audit entry is created for the duplicate detection; silent drops are prohibited (spec/05 §5.5)
* `provider_event_type = DEDUPLICATION_SUPPRESS`, `governance_scope = DUPLICATE_SUPPRESSED`
* Deduplication applies equally in SHADOW and LIVE modes

---

## 9. OUTBOUND AUTHORITY CONTROLS

---

### 9.1 Outbound Authorization Requirements

Every outbound GHL trigger must be traceable to a governance-authorized intent from the Core Decision Engine. Authorization is verified by RULE 5. The governance chain is:

```
spec/01 Config V2 Thresholds
  → directives/outreach_eligibility_rules.md (eligibility assessment)
  → directives/outreach_retry_policy.md (retry eligibility)
  → directives/core_decision_engine.md (INITIATE_OUTREACH or RETRY_OUTREACH intent)
  → directives/channel_selection_rules.md (channel advisory)
  → outreach orchestration service (executes dispatch under governance)
  → ghl_integration_contract.md (provider boundary governance)
  → GHL API (delivers communication)
```

No step in this chain may be bypassed. An outbound trigger that does not trace through the full governance chain is a specification violation.

---

### 9.2 Orchestration vs Provider Responsibilities

| Responsibility | Owner |
|---|---|
| Determine whether a student should be contacted | Core Decision Engine |
| Determine eligibility for outreach | `directives/outreach_eligibility_rules.md` |
| Determine retry eligibility | `directives/outreach_retry_policy.md` |
| Determine channel | `directives/channel_selection_rules.md` |
| Execute governance-authorized dispatch | Outreach orchestration service |
| Execute communication delivery | GHL |
| Report delivery outcomes | GHL (via webhooks) |
| Ingest and attribute delivery outcomes | Platform GHL webhook ingestion service |
| Govern provider health and degradation | This directive |

---

### 9.3 Provider Execution Boundaries

GHL is authorized to:
* Execute communication workflows triggered by authorized platform dispatch
* Report delivery state to the platform via inbound webhooks
* Provide campaign activity metadata via inbound events

GHL is **not** authorized to:
* Override platform state machine transitions
* Claim authoritative student record ownership
* Assert SQL Server authority in webhook payloads
* Modify platform config thresholds
* Trigger additional platform orchestration actions beyond the scope of the authorized intent

---

### 9.4 SHADOW vs LIVE Restrictions

| Mode | Outbound behavior | Inbound behavior |
|---|---|---|
| LIVE | Authorized dispatch proceeds via GHL API; real communication delivered | Webhook events ingested normally; state transitions actioned |
| SHADOW | No live GHL API call; outbound simulated; `governance_scope = SHADOW_ONLY`; no real communication delivered | Webhook events ingested, attributed, and tagged `execution_mode = SHADOW`; state transitions may be simulated |

SHADOW mode does not affect inbound webhook ingestion; inbound events in SHADOW are ingested normally and tagged.

---

### 9.5 Replay Outbound Prohibition

Replay and regeneration must never generate live outbound GHL API calls. This prohibition is absolute (AP-GHL5). A replay execution that constructs a GHL trigger payload, calls a live GHL API endpoint, or delivers real communication to a student is a specification violation regardless of whether the original execution produced the same communication.

---

## 10. OBSERVABILITY & ATTRIBUTION

---

### 10.1 Provider Traceability Requirements

Every provider interaction event must emit a structured log record (JSON to stdout):

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "ghl_provider_orchestration",
  "event": "short_event_name",
  "correlation_id": "uuid",
  "causation_id": "uuid | null",
  "upstream_intent_id": "uuid | null",
  "execution_type": "original | replay | regeneration",
  "execution_mode": "SHADOW | LIVE",
  "governance_scope": "string",
  "provider_event_type": "string | null",
  "ghl_message_id": "string | null",
  "duration_ms": 0,
  "outcome": "success | failure | degraded | suppressed | shadow_only | duplicate_suppressed",
  "error_class": "string | null",
  "reason_codes": []
}
```

PII fields (student name, email, phone, transcript content) must never appear in provider event logs (AP-GHL10). Log `correlation_id` and opaque `student_id` only.

---

### 10.2 Synchronization Lineage

Every outbound trigger and inbound webhook record carries:
* `sync_correlation_id` from the most recent SQL Server sync that updated the student's academic state
* `last_sync_timestamp` recording when academic state was last confirmed fresh
* `sync_lag_hours` at the time of the provider interaction

This enables post-incident investigation: "Was this outreach based on fresh or stale academic data?"

---

### 10.3 Attribution Continuity

Attribution fields — `origin_source`, `origin_authority`, `is_authoritative`, `attribution_timestamp`, `correlation_id` — are set at ingestion or dispatch initiation and are immutable thereafter (AP-GHL15). A log line missing any attribution field is an observability defect.

---

### 10.4 Replay Diagnostics

Replay assessments must emit additional diagnostic fields:

| Field | Description |
|---|---|
| `replay_source_artifact_id` | The historical event or snapshot artifact used as the replay source |
| `historical_config_version_id` | The config version resolved for this replay context |
| `fingerprint_comparison_outcome` | Whether the current config fingerprint matches the historical fingerprint: `MATCH`, `DIVERGENT`, `UNKNOWN` |
| `replay_partial` | Whether the replay used `UNKNOWN_V0` for any threshold |

---

### 10.5 Webhook Diagnostics

Inbound webhook events must emit:

| Field | Description |
|---|---|
| `webhook_received_at` | Ingestion timestamp (platform-side) |
| `attribution_timestamp` | Event occurrence time from GHL payload |
| `attribution_timestamp_delta_ms` | Delta between GHL event time and platform ingestion time |
| `ghl_message_id` | GHL's message identifier |
| `dedup_result` | `new` or `duplicate` |
| `validation_result` | `schema_valid`, `schema_invalid`, `semantic_invalid` |
| `event_type_classified` | The classified webhook event type |

---

### 10.6 Delivery Observability

Required telemetry for all outbound dispatch attempts:

| Metric | Description |
|---|---|
| `dispatch_initiated_at` | Timestamp when dispatch was authorized and initiated |
| `provider_call_start` | When the GHL API call was made |
| `provider_call_end` | When the GHL API response was received |
| `provider_call_duration_ms` | Elapsed time for the GHL API call |
| `provider_response_code` | HTTP status code returned by GHL |
| `delivery_state_after_dispatch` | `PENDING`, `DELIVERED`, or `FAILED` as reported by GHL |
| `retry_attempt_number` | Which retry attempt this was (0 = first attempt) |

---

## 11. DETERMINISTIC DEGRADATION RULES

---

All failure paths produce explicit, observable, logged fallback states. Silent degradation is prohibited (AP-GHL8).

| Condition | Trigger | `governance_scope` | `provider_event_type` | `degradation_cause` | `orchestration_continues` | Observability |
|---|---|---|---|---|---|---|
| Provider circuit breaker OPEN | `circuit_breaker_state = OPEN` | UNAVAILABLE | null | CIRCUIT_OPEN | true (outbound deferred; inbound unaffected) | `CIRCUIT_OPEN` reason code |
| Provider outage active | `provider_outage_active = true` | UNAVAILABLE | null | PROVIDER_OUTAGE | true | `PROVIDER_OUTAGE_ACTIVE` reason code |
| Retry budget exhausted | `outbound_retry_budget_remaining = 0` | UNAVAILABLE | null | RETRY_EXHAUSTED | true | `RETRY_BUDGET_EXHAUSTED`; escalation candidacy signaled |
| Replay/regeneration mode | `execution_type = replay/regeneration` | REPLAY_ONLY | REPLAY_SIMULATION | REPLAY_SUPPRESSED | false (outbound) | `OUTBOUND_SUPPRESSED_REPLAY` reason code |
| SHADOW execution mode | `execution_mode = SHADOW` | SHADOW_ONLY | SHADOW_SIMULATION | null | false (live outbound) | `SHADOW_DISPATCH_SUPPRESSED` reason code |
| Duplicate outbound key | `idempotency_key` in `processed_events` | DUPLICATE_SUPPRESSED | DEDUPLICATION_SUPPRESS | null | true | `OUTBOUND_DUPLICATE_SUPPRESSED` reason code |
| Duplicate inbound webhook | `ghl_message_id` in `processed_events` | DUPLICATE_SUPPRESSED | DEDUPLICATION_SUPPRESS | null | true | `WEBHOOK_DUPLICATE_SUPPRESSED` reason code |
| Governance authorization missing | `upstream_intent_id` null for outbound | BLOCKED | null | GOVERNANCE_BLOCKED | false | `GOVERNANCE_AUTHORIZATION_MISSING` reason code |
| Compliance hold active (outbound) | `compliance_hold_active = true` | BLOCKED | null | COMPLIANCE_HOLD | false | `COMPLIANCE_HOLD_ACTIVE_DISPATCH_BLOCKED` reason code |
| Webhook schema invalid | Payload fails schema validation | BLOCKED | null | null | false | `WEBHOOK_SCHEMA_INVALID`; HTTP 400 |
| Config threshold missing | Required key absent from ACTIVE config | AUTHORIZED (annotated) | preserved | null | true | `CONFIG_THRESHOLD_MISSING_{KEY}`; `UNKNOWN_V0` substituted |

---

## 12. FAILURE & SAFETY SEMANTICS

---

### 12.1 Missing Governance Context

When required governance context fields are null or missing (caught by RULE 0):
* Evaluation is blocked immediately; no provider interaction proceeds
* `governance_scope = BLOCKED`, `blocking_reason = GOVERNANCE_PRECONDITION_FAILED`
* Structured error log emitted with all available context fields
* Consuming service must not proceed with provider dispatch on a BLOCKED assessment

---

### 12.2 Provider Authentication Failure

When a GHL API call fails due to authentication error (`AUTH_FAILURE` class per spec/05 §11.2):
* TERMINAL failure class; no retry
* Alert emitted; key rotation required
* `provider_error_class = AUTH_FAILURE`, `governance_scope = UNAVAILABLE`
* Subsequent provider interactions for all students are blocked until authentication is restored
* Authentication failure does not corrupt platform state; in-flight orchestration intents remain in QUEUED state

---

### 12.3 Duplicate Detection Audit

Every deduplication event — outbound key match or inbound `ghl_message_id` match — produces an audit entry:

| Field | Value |
|---|---|
| `event_id` | Original event ID being duplicated |
| `duplicate_detected_at` | Ingestion timestamp of the duplicate attempt |
| `suppression_reason` | `OUTBOUND_DUPLICATE` or `WEBHOOK_DUPLICATE` |
| `correlation_id` | Correlation ID of the duplicate attempt |

Silent drops are not permitted. Every suppressed duplicate is logged. A missing audit entry for a suppressed duplicate is an observability defect.

---

### 12.4 Replay Conflict

When a replay evaluation encounters state conflicts with the historical record:

| Conflict | Behavior |
|---|---|
| Historical config version unavailable | `UNKNOWN_V0` for all thresholds; `REPLAY_CONFIG_VERSION_MISSING` reason code; `replay_partial = true` |
| Historical provider event record missing | `replay_provider_source = NONE`; emit `REPLAY_PROVIDER_HISTORY_MISSING`; assessment proceeds as REPLAY_SIMULATION with null provider context |
| Fingerprint divergence (current ≠ historical config) | `fingerprint_comparison_outcome = DIVERGENT`; emit `REPLAY_CONFIG_FINGERPRINT_DIVERGENT`; replay continues with historical config |

---

### 12.5 Attribution Gap

When a log line or provider record is missing required attribution fields:
* `correlation_id` missing → `ATTRIBUTION_CORRELATION_ID_MISSING` reason code; alert emitted; observability defect
* `origin_source` missing → `ATTRIBUTION_ORIGIN_SOURCE_MISSING` reason code; observability defect
* `attribution_timestamp` missing → `ATTRIBUTION_TIMESTAMP_INFERRED` reason code; platform ingestion time used as fallback; explicitly annotated

Attribution gaps are observability defects but do not block provider interaction processing. They are surfaced in `reason_codes` and in the structured event log.

---

## 13. ARCHITECTURE PRESERVATION RULES

---

The following rules are MUST NOT prohibitions. Violation of any rule is a specification defect.

| Rule | Prohibition |
|---|---|
| **AP-GHL1** | MUST NOT act as governance authority, eligibility decision-maker, or orchestration executor for the platform's student lifecycle state machine |
| **AP-GHL2** | MUST NOT write directly to any platform-owned schema (`public`, `warehouse`, `compliance_audit`) from any GHL-controlled service account or via any pathway other than the platform's governed ingestion service |
| **AP-GHL3** | MUST NOT trigger platform student lifecycle state transitions autonomously; GHL webhooks are inputs to the platform's state management service; they do not directly execute state transitions |
| **AP-GHL4** | MUST NOT override deterministic rule evaluation outcomes, governance invariants (INVARIANT-1 through INVARIANT-7, spec/03 §40), or config version thresholds |
| **AP-GHL5** | MUST NOT execute live outbound GHL API calls during replay or regeneration (enforced by RULE 1); replay produces `REPLAY_SIMULATION` events sourced exclusively from platform historical records |
| **AP-GHL6** | MUST NOT modify the content of `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives`; GHL execution telemetry supplements the student timeline but is never written to the immutable warehouse schema |
| **AP-GHL7** | MUST NOT overwrite prior communication event records; all GHL events are append-only to `ghl_messages`, `outreach_history`, `student_campaign_activity`; deduplication suppresses duplicates without modifying prior records |
| **AP-GHL8** | MUST NOT silently substitute an alternative provider when the configured provider is unavailable; provider outage transitions to `governance_scope = UNAVAILABLE`; the outbound dispatch is deferred to queue with full observability; no silent routing to an alternative provider |
| **AP-GHL9** | MUST NOT use hardcoded retry windows, cooldown periods, or circuit breaker thresholds; all such values must resolve from the ACTIVE config version (Group F variables); `UNKNOWN_V0` for missing keys |
| **AP-GHL10** | MUST NOT log raw PII (student name, email, phone, transcript content) in provider event logs; correlation IDs and opaque student IDs only; PII fields in GHL payloads must be redacted before logging |
| **AP-GHL11** | MUST NOT allow GHL delivery state alone to drive governance decisions (cohort classification, escalation initiation, access state changes); GHL delivery state is operational telemetry (`is_authoritative = false`); governance decisions require SQL Server-authoritative inputs |
| **AP-GHL12** | MUST NOT execute outbound dispatch without governance authorization tracing to a `INITIATE_OUTREACH` or `RETRY_OUTREACH` intent from the Core Decision Engine; no direct API trigger from external callers, ad-hoc scripts, or bypass routes |
| **AP-GHL13** | MUST NOT ingest inbound webhooks without schema validation (RULE 8) and idempotency check (RULE 6); malformed payloads are rejected with HTTP 400 and logged; they never enter platform tables |
| **AP-GHL14** | MUST NOT allow provider authentication failure to produce silent governance-affecting errors; `AUTH_FAILURE` is TERMINAL, generates an immediate alert, requires key rotation, and blocks all subsequent provider interactions until resolved |
| **AP-GHL15** | MUST NOT override, default, infer, or modify attribution fields (`origin_source`, `origin_authority`, `is_authoritative`, `attribution_timestamp`, `correlation_id`) from input context; these fields are set by the platform at ingestion or dispatch initiation and are immutable thereafter |

---

## 14. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Basic outbound trigger validation: RULE 0, RULE 5, RULE 6 (deduplication only; RULE 4 circuit breaker deferred)
* Webhook ingestion with schema validation (RULE 8) and `ghl_message_id` deduplication (RULE 6)
* Attribution fields set at ingestion: `origin_source`, `origin_authority`, `is_authoritative`, `correlation_id`
* One retry on provider 5xx; no circuit breaker; no exponential backoff
* No webhook signature verification (pending spec/05 UE-GHL2)
* SHADOW mode suppression enforced (RULE 2)
* Config-bound retry attempt limit from Group F; no hardcoded retry count

---

### STANDARD

* Full provider circuit breaker with `provider_failure_circuit_breaker_threshold` (Group F)
* Exponential backoff on retry using `provider_failure_retry_backoff_base_seconds` base
* GHL webhook signature verification (resolving UE-GHL2)
* Sync lag annotation via `sql_server_max_sync_age_hours` check (RULE 9)
* Delivery telemetry stale flag (`provider_delivery_sla_hours` threshold)
* Replay suppression fully enforced (RULE 1) with historical config resolution
* Attribution continuity validation (RULE 7) on all inbound events
* Full observability structured log fields (§10.1) on all provider events

---

### PRODUCTION

* Full circuit breaker with `HALF_OPEN` probe behavior and `provider_failure_circuit_breaker_reset_hours` reset timer
* GHL API rate-limit-aware retry with `Retry-After` header handling
* Replay diagnostics (§10.4) fully emitted for all replay-mode interactions
* Provider health state surfaced in operator dashboards
* Multi-provider extensibility: additional providers integrate via the same contract; no schema migration required
* Webhook deduplication window monitoring for duplicate delivery lag detection
* In-memory config reload for provider API credentials without service restart

---

## 15. ACCEPTANCE CRITERIA

---

### AC-GHL1 — Replay-Safe Provider Behavior

**Given** a provider interaction evaluation is re-run for the same inputs
**When** the re-run completes
**Then** no additional outbound dispatch is generated; no duplicate inbound records are created; the ProviderOrchestrationAssessment output is identical to the first run; `processed_events` contains exactly one entry per interaction

---

### AC-GHL2 — Outbound Suppression in Replay

**Given** `execution_type = replay`
**When** evaluation reaches RULE 1
**Then** `governance_scope = REPLAY_ONLY`; `replay_restrictions.outbound_suppressed = true`; `provider_event_type = REPLAY_SIMULATION`; no live GHL API call is made; all provider context is sourced from `ghl_messages` and `outreach_history`

---

### AC-GHL3 — Immutable Provider Lineage

**Given** a GHL communication event is ingested and stored
**When** a subsequent replay or regeneration occurs for the same student
**Then** the stored event record in `ghl_messages` or `outreach_history` is unchanged; `origin_source = ghl_webhook`; `is_authoritative = false`; `ghl_message_id` is preserved; no field is overwritten

---

### AC-GHL4 — Deterministic Degradation on Provider Outage

**Given** the provider circuit breaker transitions to OPEN
**When** an outbound dispatch is evaluated
**Then** `governance_scope = UNAVAILABLE`; `degradation_cause = CIRCUIT_OPEN`; no live GHL API call is made; the student's outreach state is preserved as QUEUED or RETRY_QUEUED; `CIRCUIT_OPEN` reason code is emitted; the platform continues to serve all read operations normally

---

### AC-GHL5 — Provider Attribution Continuity

**Given** a GHL webhook event is ingested
**When** the event is stored and surfaced in the student timeline
**Then** `origin_source = ghl_webhook`; `origin_authority = platform_supplementary`; `is_authoritative = false`; `attribution_timestamp` reflects the GHL event occurrence time; `ghl_message_id` is preserved in `processed_events`

---

### AC-GHL6 — Synchronization Safety

**Given** a SQL Server sync updates a student's academic state
**When** the updated state is available in `student_trigger_data`
**Then** no GHL-derived record overrides the SQL Server-authoritative value; both records are retained; the SQL Server-derived value governs eligibility classifications; `is_authoritative = true` is present on the authoritative record

---

### AC-GHL7 — Duplicate Event Protection

**Given** the same GHL webhook event is delivered twice (by `ghl_message_id`)
**When** the second delivery arrives
**Then** HTTP 200 is returned; no new record is created in any platform table; a `processed_events` audit entry records the duplicate detection; `provider_event_type = DEDUPLICATION_SUPPRESS`; no state transition is triggered by the duplicate

---

### AC-GHL8 — Config Version Reproducibility

**Given** a provider interaction was evaluated under config version V3
**When** a historical audit queries the interaction record
**Then** `config_version_reference.config_version_id = V3`; all threshold bindings active at evaluation time are preserved in `config_version_reference.threshold_bindings`; the SUPERSEDED V3 config version remains permanently queryable in `config_version_registry`

---

### AC-GHL9 — SHADOW-Mode Dispatch Suppression

**Given** `execution_mode = SHADOW`
**When** an outbound trigger evaluation is completed
**Then** `governance_scope = SHADOW_ONLY`; `provider_event_type = SHADOW_SIMULATION`; no live GHL API call is made; no real communication is delivered to the student; the assessment is logged with `outcome = shadow_only`

---

### AC-GHL10 — Webhook Schema Validation Rejection

**Given** a GHL webhook event arrives with an invalid payload schema
**When** RULE 8 validation executes
**Then** HTTP 400 is returned; no record is created in any platform table; `WEBHOOK_SCHEMA_INVALID` reason code is emitted; the invalid payload (PII-redacted) is logged for diagnostic review

---

### AC-GHL11 — Attribution Field Immutability

**Given** a provider event is ingested with `origin_source = ghl_webhook`
**When** any downstream processing step, ETL transform, or enrichment process runs
**Then** `origin_source`, `origin_authority`, `is_authoritative`, and `attribution_timestamp` are unchanged from their values at ingestion; no downstream step overwrites these fields

---

### AC-GHL12 — Compliance Hold Dispatch Blocking

**Given** `compliance_hold_active = true` for a student
**When** an outbound dispatch evaluation is performed for that student
**Then** `governance_scope = BLOCKED`; `degradation_cause = COMPLIANCE_HOLD`; `COMPLIANCE_HOLD_ACTIVE_DISPATCH_BLOCKED` reason code is emitted; no live GHL API call is made; the student's compliance workflow state is unaffected by the blocked dispatch

---

## 16. UNRESOLVED CONCERNS

---

### UE-GHL1 — Provider Lock-In (GOVERNANCE DECISION)

**Problem:** GHL is the single communication execution provider. No formally managed migration strategy exists for replacing GHL with an alternative provider or for operating multiple providers concurrently.

**Impact:** Blocks formally managed provider migration in PRODUCTION. The integration contract is designed to be provider-abstracted (§17 extensibility), but the governance process for activating a second provider under the same contract has not been defined.

**Classification:** Governance decision. Requires explicit governance approval before multi-provider activation.

---

### UE-GHL2 — Webhook Trust Boundaries (SECURITY / IMPLEMENTATION DEPENDENCY)

**Problem:** GHL webhook authenticity verification (HMAC signature, shared secret, IP allowlist) is not implemented at MVP scope. Without signature verification, any actor that knows the webhook endpoint can inject fake communication events.

**Impact:** Security exposure. Blocks PRODUCTION scope webhook trust guarantees. Resolution required before STANDARD scope per spec/05 §15 UI-3.

**Classification:** Implementation dependency. No governance decision required — implementation must comply with spec/09 security architecture.

---

### UE-GHL3 — Cross-Provider Failover (OPERATIONAL DECISION)

**Problem:** No specification defines provider failover behavior when GHL is unavailable. The current architecture defers outbound to a retry queue on outage but does not define whether an alternative provider may be activated during an outage window.

**Impact:** Blocks provider redundancy in PRODUCTION. A sustained GHL outage would queue all outbound communication indefinitely without a defined failover path.

**Classification:** Operational decision. Requires defining which alternative providers are authorized for failover activation and what governance approval is required.

---

### UE-GHL4 — Delivery Telemetry Consistency (OPERATIONAL DEPENDENCY)

**Problem:** The exact GHL API rate limits, delivery confirmation timing guarantees, and webhook delivery lag SLA are not formally documented. The `provider_delivery_sla_hours` threshold (Group F) is a platform-defined value that may not align with GHL's actual delivery timing.

**Impact:** Blocks SLA-bound delivery observability. A mismatch between `provider_delivery_sla_hours` and GHL's actual delivery timing produces spurious `DELIVERY_TELEMETRY_STALE` annotations.

**Classification:** Operational dependency. Resolution requires GHL SLA documentation and calibration of `provider_delivery_sla_hours` against observed delivery timing.

---

### UE-GHL5 — Opt-Out Authority Conflicts (GOVERNANCE DECISION)

**Problem:** When a student opts out of a channel in GHL (e.g., SMS carrier opt-out), the opt-out record exists in GHL's system. The synchronization mechanism for pulling opt-out state from GHL into the platform has not been defined. A student who opts out via GHL may still receive outreach on that channel if the opt-out is not synchronized.

**Impact:** Blocks formally governed cross-channel opt-out propagation in PRODUCTION.

**Classification:** Governance decision. Requires defining opt-out synchronization cadence, platform ownership of opt-out state, and conflict resolution when GHL and platform opt-out records disagree.

---

### UE-GHL6 — Synchronization SLA Governance (GOVERNANCE DECISION)

**Problem:** `sql_server_max_sync_age_hours` (Group K) defines maximum acceptable academic state staleness, but no equivalent SLA governs GHL event synchronization lag. When GHL webhook delivery is delayed, platform delivery telemetry becomes stale without a defined alerting threshold.

**Impact:** Blocks SLA-bound GHL event synchronization lag alerting. The `sync_lag_hours` annotation in `synchronization_metadata` has no actionable threshold.

**Classification:** Governance decision. Requires defining a `ghl_event_sync_max_lag_hours` config variable (proposed Group K addition) and the alerting/escalation policy for breaches.

---

## 17. DOWNSTREAM IMPLICATIONS

---

### 17.1 Service Layer

| Service | Provider governance dependency |
|---|---|
| `app/services/ghl_sync.py` | Validates inbound webhooks (RULE 8); deduplicates via `ghl_message_id` (RULE 6); sets attribution fields at ingestion (RULE 7); emits structured log events (§10.1) |
| `app/services/outreach.py` | Validates governance authorization before dispatch (RULE 5); checks idempotency key (RULE 6); applies circuit breaker state from provider health assessment (RULE 4); defers to queue on UNAVAILABLE |
| `app/services/snapshot.py` | Reads `ghl_messages` for communication history as `platform_supplementary` context; never reads GHL API directly; snapshot content lock reads `student_trigger_data` only |
| `app/services/timeline.py` | Aggregates GHL events (`origin_source = ghl_webhook`) alongside SQL Server-mirrored events; preserves `attribution_timestamp` vs `ingestion_timestamp` delta; `is_authoritative = false` on all GHL-derived timeline events |
| `app/services/report.py` | Reads `warehouse.student_snapshots` exclusively (FAD-2); no GHL API calls during report generation; communication history surfaces from `outreach_history`, not live GHL API |
| `app/services/escalation.py` | Consumes provider failure signals (retry exhaustion, circuit breaker state) as escalation candidacy inputs per `directives/escalation_rules.md`; does not act on GHL delivery state alone as an escalation trigger |

---

### 17.2 Scheduler Jobs

| Job | Provider governance dependency |
|---|---|
| GHL webhook ingestion (continuous) | Applies RULE 6 deduplication, RULE 7 attribution, RULE 8 classification on every inbound event |
| Outreach trigger dispatch | Applies full governance chain (RULE 0 through RULE 11) before any GHL API call |
| GHL campaign reconciliation | GHL read-only API; deduplicates by `(student_id, campaign_id, event_type, attribution_timestamp)`; no platform state mutations |
| Delivery confirmation reconciliation | Compares `outreach_history` expected deliveries against confirmed GHL events; flags `DELIVERY_TELEMETRY_STALE` for SLA breaches |
| Circuit breaker state monitor | Polls provider health state; transitions circuit state; emits degradation signals to orchestration services |

---

### 17.3 ETL Jobs

| ETL job | Attribution requirement |
|---|---|
| GHL webhook → `ghl_messages` | `origin_source = ghl_webhook`; `origin_authority = platform_supplementary`; `is_authoritative = false`; `ghl_message_id` preserved; `attribution_timestamp` from GHL payload |
| GHL webhook → `student_campaign_activity` | Same attribution requirements; dedup by `(student_id, campaign_id, event_type, attribution_timestamp)` |
| GHL webhook → `outreach_history` | Same attribution requirements; `(user_id, checkpoint_type, contact_attempt)` governs outreach domain idempotency |
| GHL webhook → `student_timeline_events` | Normalized to platform event schema; `is_authoritative = false`; preserves `attribution_timestamp` |

---

## 18. REFERENCES

---

Canonical inputs:

* `spec/01_requirements.md` — Config V2 Governance Catalog (§12); Group F provider failure thresholds; Group K system timing thresholds; provider governance foundations (§12.6)
* `spec/03_state_transition_rules.md` — All 6 lifecycle domain state machines; Event Attribution Standard (§39); Cross-Domain Invariants §40–44; INVARIANT-1 through INVARIANT-7
* `spec/04_idempotency_concurrency.md` — Idempotency keys per domain; outreach domain idempotency key `(user_id, checkpoint_type, contact_attempt)`; CONC-INVARIANT-1 through CONC-INVARIANT-7; §20 Event Idempotency and Attribution
* `spec/05_external_integrations.md` — GHL provider ownership boundaries (§5.1); communication event ingestion (§5.2); attribution preservation (§5.3); deduplication expectations (§5.5); replay handling (§5.6); failure classification (§11.2); provider outage handling (§11.5); future provider extensibility (§5.7)
* `spec/06_observability_operations.md` — Structured logging standards; correlation ID requirements; observability defect classification
* `spec/07_api_contracts.md` — Webhook ingestion endpoint contracts; outreach trigger API contracts
* `spec/08_data_model.md` — `ghl_messages`, `outreach_history`, `student_campaign_activity`, `processed_events`, `student_timeline_events` schema definitions
* `spec/09_security_privacy.md` — Lineage integrity protection (§1.3); historical integrity protection (§1.2); attribution immutability requirements; PII handling requirements
* `directives/core_decision_engine.md` — Authoritative source for INITIATE_OUTREACH and RETRY_OUTREACH intent production; governance chain upstream from this directive
* `directives/outreach_eligibility_rules.md` — Eligibility assessment upstream from outreach dispatch
* `directives/outreach_retry_policy.md` — Retry eligibility governance upstream from retry dispatch
* `directives/channel_selection_rules.md` — Channel advisory upstream from dispatch; provider health state as channel constraint
* `directives/escalation_rules.md` — Provider failure escalation candidacy (Rule 6); retry exhaustion escalation routing
* `directives/llm_processing_contract.md` — AI governance contract; provider governance philosophy alignment
* FAD-1 — AI physical copy immutability; GHL events do not enter `warehouse.snapshot_ai_narratives`
* FAD-2 — Historical report reproducibility; report generation reads `warehouse.student_snapshots` only; no GHL API call during regeneration
* FAD-3 — Prospective-only config activation; provider thresholds follow the same prospective-only semantics as all Config V2 variables

---

## END OF FILE
