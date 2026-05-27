# failure/llm_failures.md

---

## LAYER 8 — FAILURE HANDLING (GOVERNANCE-SAFE AI RESILIENCE ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governance-safe AI resilience orchestration architecture established across `failure/failure_playbook.md`, `directives/llm_processing_contract.md`, `runtime/system_loop.md`, `runtime/retry_cycle_flow.md`, and all canonical spec documents. The previous version described MVP-era LLM/provider recovery documentation: simplistic failure categories (Invalid Output Structure, Invalid Field Values, Timeout/No Response, Hallucinated Output, Partial Output), "Retry LLM call (once)" as a first-class recovery instruction, a fixed retry matrix ("Invalid JSON: 1 retry / Timeout: 1 retry / Hallucination: No retry"), "Use deterministic rule-based decision engine only" as an undocumented silent fallback, `RESPONDED → INTERVENTION_REQUIRED` as a direct state impact, three-tier scope behavior (MVP/STANDARD/PRODUCTION), and generic log field lists. That architecture is incompatible with the governance-safe orchestration model. AI resilience is no longer LLM retry handling. It is governance-safe AI resilience orchestration — deterministic AI degradation coordination with replay-safe AI recovery governance and observable AI degradation lineage management. This document is the **authoritative AI resilience child contract** governed by `failure/failure_playbook.md §2.3`, `§3.3`, `§4.3`, and all AP-FP rules.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

The **Governance-Safe AI Resilience Orchestration Architecture** defines:

* How AI failure governance domains are categorized, coordinated, and made historically explainable
* What AI resilience behaviors are permitted in each execution mode — and what is explicitly prohibited
* How deterministic AI degradation is coordinated without silent model substitution, hidden inference retries, or undocumented fallback evaluation
* How Config V2 governs AI retry authorization, inference timeout thresholds, TTL boundaries, and degradation escalation conditions — not hardcoded values
* How replay-safe AI recovery semantics prevent historical simulation from generating LIVE inference effects
* How AI advisory governance boundaries are maintained during AI resilience orchestration
* How FINALIZED_COPY immutability is preserved under all AI failure conditions
* How AI failure attribution lineage enables forensic reconstruction of every AI degradation event
* How inference-failure containment prevents AI unavailability from blocking orchestration cycles
* What authority boundaries the AI resilience layer holds vs what it must not own

This document is a **child resilience contract** governed by:

* `failure/failure_playbook.md` — §2.3 (AI Failures domain); §3.3 (AI Authority Restrictions); §4.3 (AI Provider Outage Degradation); §8 (Attribution & Observability); §9 (Idempotency Guarantees); all AP-FP rules
* `directives/llm_processing_contract.md` — the authoritative AI orchestration contract; all AP-AI rules; six-tier AI governance model; FINALIZED_COPY semantics; replay-safe AI behavior
* `runtime/system_loop.md` — §10 (Degradation & Failure Governance); §3 (Runtime Modes); §9 (AI Advisory Governance)
* `runtime/retry_cycle_flow.md` — §9 (AI Advisory Governance in retry); §7 (Replay suppression in retry context); §8 (Provider governance in retry)

Where this document conflicts with parent contract semantics, the parent contracts govern. Where this document defines AI-specific failure domain detail not present in parent contracts, this document is authoritative.

---

### 1.2 What AI Resilience Handling Is NOT

In the governance-safe orchestration model, AI resilience handling is explicitly **NOT**:

* **"Retry LLM call (once)"** — this is not a permitted AI recovery instruction; inference retry authorization is governed by Config V2 `provider_failure_retry_limit` and `provider_degradation_state`; no hardcoded retry-once pattern is allowed (AP-LF3, inheriting AP-FP3)
* **Silent model substitution** — when the configured AI provider is unavailable, there is no fallback to an alternative provider; degradation is explicit, observable, and logged; the AI governance tier transitions to UNAVAILABLE (AP-LF6, inheriting AP-AI8)
* **Hidden inference retries** — inference retries that are not attributed to the originating orchestration cycle, do not emit structured log entries, and do not decrement from the governed retry budget are prohibited (AP-LF7, inheriting AP-FP6)
* **Non-attributed AI recovery** — recovery actions without `correlation_id`, `causation_id`, `execution_mode`, `config_version_id`, `ai_governance_tier`, and `ai_failure_class` are not permitted (AP-LF8, inheriting AP-FP6)
* **Replay-triggered LIVE inference** — a replay-mode AI resilience simulation may not generate new AI provider calls; all replay AI content is sourced exclusively from `warehouse.snapshot_ai_narratives` (AP-LF1, inheriting AP-AI5 and AP-FP2)
* **FINALIZED_COPY mutation** — no AI failure recovery path may overwrite, regenerate, or retroactively modify AI text physically copied into `warehouse.snapshot_ai_narratives` (AP-LF2, inheriting AP-AI6 and FAD-1)
* **AI authority escalation** — AI failure does not elevate AI from advisory to decision-making authority; AI absence is annotated and rule-based evaluation proceeds; AI resilience does not expand AI governance scope during degraded operation (AP-LF9, inheriting AP-FP9)
* **Blocking orchestration on AI failure** — AI failure never blocks an orchestration cycle; AI advisory absence is a scope restriction, not a blocking failure; rule-based evaluation proceeds (AP-LF10, inheriting AP-FP9 and AP-AI3)
* **Immutable lineage corruption** — no AI recovery action may overwrite, backfill, or retroactively modify records in `ai_insights`, `warehouse.snapshot_ai_narratives`, `state_transition_log`, or `student_timeline_events` (AP-LF11, inheriting AP-FP7)

Explicitly prohibited in AI resilience orchestration:

* Replay-triggered LIVE AI inference (AP-LF1)
* FINALIZED_COPY mutation under any AI failure condition (AP-LF2)
* "Retry inference once" semantics (AP-LF3)
* Silent AI fallback execution without structured log (AP-LF4)
* Hardcoded inference retry thresholds (AP-LF5)
* Silent model substitution on provider unavailability (AP-LF6)
* Hidden inference retries without attribution (AP-LF7)
* Non-attributable AI recovery actions (AP-LF8)
* AI authority escalation during failure (AP-LF9)
* Blocking orchestration cycle on AI failure (AP-LF10)
* Immutable record mutation during AI recovery (AP-LF11)
* Duplicate LIVE inference execution from recovery coordination (AP-LF12)
* AI governance bypass during recovery coordination (AP-LF13)
* PII in AI resilience observability records (AP-LF14)
* Silent AI error swallowing (AP-LF15)

---

### 1.3 AI Resilience Governance Layer Definition

AI resilience orchestration sits at the containment boundary between:

* The **AI orchestration contract** (`directives/llm_processing_contract.md`) — defines the six-tier AI governance model (CONFIDENT, ADVISORY, STALE, IN_FLIGHT, UNAVAILABLE, FINALIZED_COPY); AI advisory scope rules; FINALIZED_COPY immutability (FAD-1); replay-safe AI semantics; AP-AI1–AP-AI15 prohibitions. AI resilience layer inherits all AI governance constraints from this directive.
* The **parent resilience contract** (`failure/failure_playbook.md`) — defines failure governance domains, recovery orchestration coordination, attribution lineage, idempotency guarantees, and AP-FP prohibitions. AI resilience inherits §2.3, §3.3, §4.3 directly.
* The **runtime orchestration layer** (`runtime/system_loop.md`) — defines degradation governance, AI advisory governance (§9), mode transitions, and the deterministic degradation condition table (§10). AI resilience layer inherits §9 and §10 AI-relevant conditions.
* The **retry orchestration layer** (`runtime/retry_cycle_flow.md`) — defines AI advisory governance during retry evaluation (§9), replay suppression (§7), and AI failure handling within retry cycles. AI resilience layer inherits these retry-context semantics.
* The **execution layer** (`backend/src/services/`) — validates and executes AI evaluation under governance authorization; AI resilience layer coordinates but does not own inference execution.

| Layer | AI resilience layer relationship |
|---|---|
| `directives/llm_processing_contract.md` | Authoritative AI governance; AI resilience inherits AP-AI1–AP-AI15, six-tier model, FINALIZED_COPY semantics |
| `failure/failure_playbook.md §2.3` | Canonical AI failure domain definition; AI resilience inherits governance scope, replay behavior, SHADOW/LIVE behavior, attribution requirements |
| `runtime/system_loop.md §9–10` | AI advisory governance; degradation governance; AI resilience inherits §9 (AI Advisory Governance) and §10 (AI-relevant conditions) verbatim |
| `runtime/retry_cycle_flow.md §7, §9` | Retry AI governance; replay suppression in retry; AI resilience inherits AI failure handling in retry context |
| Orchestration services | Authorize and execute AI inference under governance; AI resilience coordinates but does not own |
| AI provider systems | Execute inference; AI resilience coordinates circuit breaker signals but does not own provider calls |

---

## 2. AI FAILURE GOVERNANCE DOMAINS

---

### 2.1 Inference Timeout Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | AI provider response latency exceeding the timeout boundary; governed by `spec/05_external_integrations.md` and `directives/llm_processing_contract.md` §8.2 |
| **Recovery philosophy** | Single inference timeout is not immediately terminal; the governed retry policy applies using `provider_failure_retry_limit` from `directives/llm_processing_contract.md §3.5`; if retry also times out, `UNAVAILABLE` tier assigned; no "retry once" hardcoded pattern (AP-LF3) |
| **Replay behavior** | Timeout records are preserved in `ai_insights` with `ai_insight_state = AI_GENERATION_FAILED`; replay does not re-trigger inference; historical timeout facts are observable from `state_transition_log` at historical timestamp |
| **SHADOW behavior** | Timeout detected and logged with `execution_mode = SHADOW`; AI governance tier transitions to UNAVAILABLE; orchestration continues without AI advisory |
| **LIVE behavior** | `inference_last_failure_type = TIMEOUT` logged; governed retry policy evaluated; if exhausted, `ai_governance_tier = UNAVAILABLE`; `INFERENCE_TIMEOUT_EXHAUSTED` reason code emitted; orchestration continues on rule-based signals |
| **Attribution requirements** | `correlation_id`, `causation_id` from orchestration cycle; `ai_version_number`, `prompt_version`, `model_used` from inference context; `inference_duration_ms` measured at call boundary |
| **Idempotency guarantees** | Inference retry keyed on `(student_id, insight_type, date_period, prompt_version)`; duplicate retry requests from recovery coordination are no-ops |

---

### 2.2 Model Unavailability Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | AI provider unreachable, circuit breaker OPEN, provider returning 5xx, authentication failures — governed by `directives/llm_processing_contract.md §8`, Rule 8 |
| **Recovery philosophy** | Provider unavailability assigns `UNAVAILABLE` tier immediately when circuit breaker is OPEN or retry budget is exhausted; no silent substitution of alternative provider (AP-LF6); orchestration proceeds on rule-based signals with `fallback_type = RULE_BASED_ONLY`; no "fallback to another model" permitted |
| **Replay behavior** | Historically unavailable AI sourced from `warehouse.snapshot_ai_narratives` if FINALIZED_COPY exists; if no FINALIZED_COPY exists, `ai_governance_tier = UNAVAILABLE` with reason code `REPLAY_AI_SOURCE_MISSING`; no live provider call during replay (AP-LF1) |
| **SHADOW behavior** | Provider failure detected; `ai_governance_tier = UNAVAILABLE`; SHADOW output carries `advisory_scope = UNAVAILABLE`; orchestration not blocked |
| **LIVE behavior** | `circuit_breaker_state = OPEN` or `provider_degradation_state = UNAVAILABLE`; Rule 8 in `llm_processing_contract.md` assigns UNAVAILABLE tier; `AI_PROVIDER_UNAVAILABLE` event emitted; stale insight served if within `ai_insight_ttl_hours` with STALE tier and LIMITED scope; snapshot finalization continues with `ai_content_stale = true` |
| **Attribution requirements** | `ai_failure_class = PROVIDER_UNAVAILABLE`; `circuit_breaker_state`, `provider_degradation_state` in failure record; `correlation_id` from orchestration cycle |
| **Idempotency guarantees** | AI refresh blocked for all new requests when provider is unavailable; existing FINALIZED_COPY records remain immutable and are never refreshed (AP-LF2) |

**Prohibited patterns in model unavailability handling:**
* Silent substitution of alternative AI provider (AP-LF6, inheriting AP-AI8)
* Upgrading AI advisory authority because preferred provider is unavailable (AP-LF9)
* Blocking orchestration cycle while waiting for provider recovery (AP-LF10)

---

### 2.3 Stale AI Governance Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | AI insight age exceeding `ai_insight_ttl_hours` from Config V2 Group H; governed by `directives/llm_processing_contract.md Rule 5` and `§6.2 AI TTL Governance` |
| **Recovery philosophy** | Stale AI is not a failure requiring recovery coordination; it is a degraded advisory state; STALE tier AI is served with `stale: true` annotation and LIMITED scope; STALE AI must not drive LIVE escalation (AP-AI11); rule-based evaluation proceeds normally; staleness annotation prevents escalation pathway misuse |
| **Replay behavior** | Historical staleness assessment uses TTL value from historical config version (`replay_context.historical_config_version_id`); an insight that was STALE at original execution time is STALE in replay; a fresh insight at original execution time is not retroactively assessed as STALE under a new TTL boundary (FAD-3) |
| **SHADOW behavior** | STALE tier assigned; `stale_flag = true`; `stale_for_hours` populated; advisory scope = LIMITED; SHADOW-mode orchestration continues without LIVE escalation from AI |
| **LIVE behavior** | `ai_governance_tier = STALE`; `advisory_scope = LIMITED`; `recommended_intervention = null` per Rule 7 in `llm_processing_contract.md`; `AI_LIVE_ESCALATION_BLOCKED_STALE_TIER` reason code; AI content still served for display-layer use; rule-based escalation continues independently |
| **Attribution requirements** | `stale_for_hours`, `ai_insight_ttl_hours_applied`, `config_version_id` in all STALE advisory outputs |
| **Idempotency guarantees** | Staleness is computed at evaluation time; no mutation of the underlying `ai_insights` record; stale insight evaluation is idempotent for the same input state |

---

### 2.4 Degraded Inference Quality Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | AI confidence score below governance thresholds; structural validation failures on inference output; schema contract violations; governed by `directives/llm_processing_contract.md Rule 5` (confidence collapse) and `§11` (failure semantics) |
| **Recovery philosophy** | Confidence collapse assigns ADVISORY tier with LIMITED scope — it is not a recovery-requiring failure; schema validation failures that cannot be resolved by governed retry coordination assign UNAVAILABLE tier; no structural output that fails validation may enter the orchestration pipeline as valid advisory content |
| **Replay behavior** | Historically low-confidence insights retain their original tier assessment (ADVISORY, not retroactively upgraded); schema failure records preserved in `ai_insights` with `AI_GENERATION_FAILED` state |
| **SHADOW behavior** | Degraded confidence noted with `confidence_tier = LOW` and `degradation_cause = CONFIDENCE_COLLAPSE`; advisory scope = LIMITED; orchestration continues |
| **LIVE behavior** | `ai_governance_tier = ADVISORY` for confidence collapse; `advisory_scope = LIMITED`; `recommended_intervention = null`; for schema validation failure after retry exhaustion: `ai_governance_tier = UNAVAILABLE`; `ai_failure_class = INVALID_STRUCTURE | SCHEMA_MISMATCH`; rule-based evaluation only |
| **Attribution requirements** | `ai_failure_class` (one of `CONFIDENCE_COLLAPSE`, `INVALID_STRUCTURE`, `SCHEMA_MISMATCH`, `PARTIAL_OUTPUT`) in failure record; `retry_count` at failure; `prompt_version` and `model_used` |
| **Idempotency guarantees** | Schema validation failure record append-only; retry coordination keyed on `(student_id, insight_type, date_period, prompt_version)`; duplicate coordination requests are no-ops |

---

### 2.5 Duplicate Inference Governance Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Concurrent or repeated AI evaluation requests for the same `(student_id, checkpoint_type, cycle_timestamp)` idempotency key; governed by `directives/llm_processing_contract.md Rule 0` idempotency gate |
| **Recovery philosophy** | Duplicate inference requests are blocked at the Rule 0 governance precondition gate; `IDEMPOTENCY_DUPLICATE` reason code emitted; the prior assessment for this key is NOT re-served from cache — the consumer must look up the stored result; no silent duplicate execution |
| **Replay behavior** | Replay idempotency is inherently enforced — replay is read-only and does not invoke inference; duplicate replay evaluations of the same historical context are permitted (they produce the same result from stored data); no idempotency key consumption during replay |
| **SHADOW behavior** | Duplicate detected; `ai_blocked = true`; `IDEMPOTENCY_DUPLICATE` logged at WARN level; SHADOW cycle not blocked |
| **LIVE behavior** | Rule 0 blocks with `IDEMPOTENCY_DUPLICATE`; `ai_blocked = true`; `blocking_reason = GOVERNANCE_PRECONDITION_FAILED`; structured WARN log emitted; no second inference call made |
| **Attribution requirements** | `idempotency_key` in duplicate detection log; `correlation_id` from originating cycle; `ai_version_number` of the pre-existing result |
| **Idempotency guarantees** | Idempotency key `(student_id, checkpoint_type, cycle_timestamp)` is the dedup gate; duplicate requests → no-op; this is the primary mechanism preventing duplicate LIVE inference execution (AP-LF12) |

---

### 2.6 Replay Inference Governance Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Any condition in replay or regeneration execution where an AI provider call would be triggered; governed by `directives/llm_processing_contract.md Rule 2` and AP-AI5 |
| **Recovery philosophy** | Replay-triggered AI provider calls are a specification violation — they must be detected at the Rule 2 gate and blocked unconditionally; the AI resilience layer never permits live inference during replay regardless of what historical AI failure state is being simulated; replay AI failure simulation is read-only |
| **Replay behavior** | All replay AI evaluation sources content from `warehouse.snapshot_ai_narratives` (FINALIZED_COPY) or returns UNAVAILABLE; `live_inference_suppressed = true` always; `replay_restrictions.replay_ai_source = FINALIZED_COPY | NONE`; historical config version used for threshold resolution; no new AI content created |
| **SHADOW behavior** | Replay mode is SHADOW by definition; all replay failure simulation outputs carry `governance_scope = REPLAY_ONLY`; no LIVE escalation routing |
| **LIVE behavior** | No LIVE behavior during replay; LIVE mode may not be entered from replay context (AP-LF1) |
| **Attribution requirements** | `source_artifact_id`, `historical_config_version_id`, `fingerprint_comparison_outcome`, `replay_partial` in all replay AI failure diagnostics |
| **Idempotency guarantees** | Replay is inherently idempotent — read-only; no inference key consumption; no state mutation |

---

### 2.7 FINALIZED_COPY Protection Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Any AI failure recovery path that would — if incorrectly implemented — attempt to regenerate, overwrite, or modify AI narrative text physically copied into `warehouse.snapshot_ai_narratives`; governed by FAD-1, AP-AI6, AP-AI12, and AP-LF2 |
| **Recovery philosophy** | FINALIZED_COPY AI content is immutable under all AI failure conditions without exception; Rule 1 in `llm_processing_contract.md` fires immediately when `ai_finalized_copy = true` and stops all further evaluation; provider outage, model upgrade, compliance deletion of `ai_insights` records, and TTL expiry cannot affect frozen snapshot AI text |
| **Replay behavior** | FINALIZED_COPY is the exclusive AI source for replay; it is read-only in replay; replay diagnostics referencing FINALIZED_COPY carry `replay_ai_source = FINALIZED_COPY` |
| **SHADOW behavior** | FINALIZED_COPY isolation enforced in SHADOW mode identically to LIVE mode; Rule 1 fires unconditionally |
| **LIVE behavior** | Rule 1 assigns tier = FINALIZED_COPY, scope = IMMUTABLE immediately; no re-inference, no tier re-evaluation, no advisory scope expansion; `AI_FINALIZED_COPY_SERVING` reason code |
| **Attribution requirements** | `snapshot_version_reference`, `ai_narrative_hash`, `model_version_at_finalization`, `prompt_version_at_finalization` in FINALIZED_COPY serving record |
| **Idempotency guarantees** | FINALIZED state is irreversible; FINALIZED_COPY records are never modified; re-finalization of the same `(student_id, snapshot_month)` is blocked (AP-LF2) |

**Prohibited patterns in FINALIZED_COPY handling:**
* Force-refresh of source `ai_insights` record that propagates to snapshot (AP-LF2, FAD-1)
* AI provider change that retroactively modifies `warehouse.snapshot_ai_narratives` rows (AP-AI8, spec/01 §12.6.5)
* Compliance deletion of `ai_insights` that reaches `warehouse.snapshot_ai_narratives` (AP-LF2, §7.3 of `llm_processing_contract.md`)
* Model version upgrade that overwrites frozen snapshot AI text (AP-LF2, FAD-1)

---

### 2.8 Fingerprint Divergence Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Mismatch between the provider/model/prompt version that generated an insight and the currently configured provider/model/prompt in the ACTIVE config version; governed by `directives/llm_processing_contract.md Rule 8` (provider identity divergence) and snapshot reproducibility fingerprint semantics |
| **Recovery philosophy** | Provider identity divergence does not invalidate an existing insight; the insight is still served at its assigned tier; however, fingerprint divergence blocks snapshot eligibility (`eligible_for_snapshot = false`); no silent remediation of diverged fingerprints |
| **Replay behavior** | Regeneration with fingerprint divergence carries `POTENTIALLY_DIVERGENT` annotation; both fingerprint versions are recorded; regeneration is not blocked; `output_identical = false` annotated in regeneration log |
| **SHADOW behavior** | Divergence detected; `PROVIDER_IDENTITY_DIVERGENCE` reason code; snapshot eligibility blocked; tier unchanged; orchestration not blocked |
| **LIVE behavior** | `PROVIDER_IDENTITY_DIVERGENCE` reason code; `eligible_for_snapshot = false`; insight served at existing tier; snapshot orchestration informed not to copy this insight |
| **Attribution requirements** | `historical_model_used`, `current_ai_llm_provider_config`, both fingerprint versions in divergence record |
| **Idempotency guarantees** | Divergence annotation is computed, not stored; the underlying `ai_insights` record is not modified; idempotent for the same input state |

---

### 2.9 Attribution-Loss Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Missing `correlation_id`, incomplete attribution context, broken `causation_id` chain, or missing `ai_version_number` in AI advisory outputs; governed by `failure/failure_playbook.md §2.9` and AP-AI15 |
| **Recovery philosophy** | Attribution failure in AI evaluation is a specification defect; affected assessments are flagged `attribution_incomplete = true`; Rule 0 in `llm_processing_contract.md` blocks evaluation when attribution context is incomplete; no silent continuation with broken attribution |
| **Replay behavior** | Attribution failure in replay produces `fingerprint_comparison_outcome = UNKNOWN` with `attribution_incomplete = true`; replay diagnostic still emitted |
| **SHADOW behavior** | Attribution failure logged; `ATTRIBUTION_PARTIAL` or `ATTRIBUTION_FAILURE` reason code; assessment blocked or degraded per Rule 0 |
| **LIVE behavior** | Rule 0 blocks with `ATTRIBUTION_INCOMPLETE` if required fields are missing; `ATTRIBUTION_FAILURE` event emitted; escalation candidacy generated; cycle not aborted unless Rule 0 precondition gate fails |
| **Attribution requirements** | Attribution failure record must itself carry the `correlation_id` from the cycle even if downstream AI records are missing it (inheriting `failure_playbook.md §2.9`) |
| **Idempotency guarantees** | Attribution failure records are append-only; no retroactive lineage repair that mutates existing records (AP-LF11) |

---

### 2.10 Observability Degradation Failures

| Attribute | Specification |
|---|---|
| **Governance scope** | Structured AI telemetry pipeline failures, AI inference metric write failures, AI assessment log pipeline degradation |
| **Recovery philosophy** | Observability failure does not block AI evaluation; structured AI assessment logs that fail to write are directed to stderr with `OBSERVABILITY_DEGRADED` flag; the failure is itself observable; AI inference continues regardless of observability pipeline state |
| **Replay behavior** | Replay AI diagnostics written to stderr if pipeline degraded; observability failure does not suppress replay fingerprint comparison output |
| **SHADOW behavior** | Observability failure directed to stderr; AI evaluation continues; SHADOW cycle loop continues |
| **LIVE behavior** | `OBSERVABILITY_DEGRADED` event emitted to stderr; AI evaluation continues; escalation candidacy generated for persistent observability degradation |
| **Attribution requirements** | Minimal attribution preserved in stderr record: `correlation_id`, `timestamp`, `ai_governance_tier`, `event` |
| **Idempotency guarantees** | Observability writes are independent of AI evaluation state; no idempotency concern for log writes |

---

## 3. AI FAILURE AUTHORITY BOUNDARIES

---

### 3.1 What the AI Resilience Layer Coordinates

| Responsibility | AI resilience layer owns | AI resilience layer does NOT own |
|---|---|---|
| AI failure classification and tier coordination | Yes | Defining business-level eligibility or retry thresholds (directives own those) |
| AI recovery cycle attribution generation | Yes | Executing recovery orchestration (orchestration services own this) |
| AI degradation state coordination | Yes | Mode transition authority (Governance/Operational Administrator owns this) |
| Observability emission for AI failure events | Yes | Implementing telemetry pipelines or alerting infrastructure |
| Circuit breaker signal coordination for AI | Yes | Owning circuit breaker state (provider governance services own this) |
| Escalation candidacy generation for AI failures | Yes | Escalation routing to human operators (escalation routing service owns this) |
| FINALIZED_COPY protection enforcement | Yes | Writing to or modifying `warehouse.snapshot_ai_narratives` (snapshot orchestration service owns this) |

---

### 3.2 AI Advisory Authority Restrictions

The AI resilience layer never expands AI advisory authority during failures:

* AI is advisory-only in all failure and degradation contexts (AP-LF9, inheriting AP-FP9)
* AI failure does not elevate AI from advisory-only to decision-making authority — not even temporarily
* AI absence during degradation: rule-based evaluation proceeds; AI absence is annotated with `AI_ADVISORY_ABSENT` reason code
* FINALIZED_COPY records are never re-evaluated or regenerated during AI failure — they remain immutable (AP-LF2)
* Stale AI must not drive LIVE escalation (AP-AI11 from `llm_processing_contract.md`)
* `provider_authority_class` remains `platform_supplementary` during all AI failure conditions (inheriting `failure_playbook.md §3.2`)

---

### 3.3 Replay Authority Restrictions

The AI resilience layer does not grant LIVE authority to replay-mode AI failure simulation:

* A failure detected during replay AI simulation produces no LIVE inference effect (AP-LF1, inheriting AP-FP2)
* Replay AI failure outputs are always `execution_type = replay`, `governance_scope = REPLAY_ONLY`
* No mode transition from REPLAY to LIVE is permitted within an AI resilience recovery sequence (AP-LF13)
* Replay may simulate historical AI failure states from `state_transition_log` records
* Replay may not re-run historical inference to produce AI content not captured in FINALIZED_COPY

---

### 3.4 Recovery Scope Restrictions

The AI resilience layer does not re-implement directive logic:

* AI resilience consumes structured `AIAssessment` objects from `directives/llm_processing_contract.md` — it does not re-implement tier assignment logic
* Retry authorization is assessed by `directives/outreach_retry_policy.md` — AI resilience coordinates, it does not own retry policy
* Eligibility assessment remains directive-owned during AI failure (inheriting `failure_playbook.md §6.3`)
* AI resilience does not re-implement any of AP-AI1 through AP-AI15 — it inherits and enforces them

---

## 4. DETERMINISTIC AI DEGRADATION GOVERNANCE

---

### 4.1 AI Degradation Principles

AI degradation is observable, not silent. Inherited from `failure/failure_playbook.md §4.1` and `directives/llm_processing_contract.md §10`:

Every degraded AI state must:
* Emit a structured log entry with `ai_failure_class`, `ai_governance_tier`, `fallback_type`, and `outcome = degraded`
* Produce an `ai_governance_tier = UNAVAILABLE | STALE | ADVISORY` with corresponding `advisory_scope`
* Describe what operations continued and what advisory scope was restricted
* Never silently substitute an alternative model, silently swallow a failure, or proceed without logging the degradation event

The following patterns are prohibited (AP-LF3, AP-LF4, AP-LF6):
* `try { ... } catch (e) {}` semantics on inference calls — swallowing without logging
* Falling back to a hardcoded alternative provider when the configured provider is unavailable
* Retrying inference without governing the retry count against `provider_failure_retry_limit`

---

### 4.2 Provider Outage AI Degradation

When the AI provider is unavailable (circuit breaker OPEN or `provider_degradation_state = UNAVAILABLE`):

* **AI refresh orchestration** — blocked; no new inference calls; `CIRCUIT_BREAKER_OPEN` or `PROVIDER_UNAVAILABLE` event emitted
* **Orchestration evaluation** — proceeds with rule-based evaluation only; `advisory_scope = UNAVAILABLE`; `fallback_type = RULE_BASED_ONLY`
* **Stale AI serving** — if an existing insight is within `ai_insight_ttl_hours`, it is served with STALE tier and LIMITED scope; LIVE escalation blocked; display-layer content still provided
* **Snapshot finalization** — not blocked; `ai_content_stale = true` flag set when finalized without current AI
* **FINALIZED_COPY records** — unaffected regardless of provider state; sourced from `warehouse.snapshot_ai_narratives` exclusively (AP-LF2)
* **Retry budget protection** — inference retries blocked by provider outage are not consumed from the student's retry budget (inheriting `failure_playbook.md §4.2`)

---

### 4.3 Inference Timeout AI Degradation

When an inference call exceeds the governed timeout boundary:

* `inference_last_failure_type = TIMEOUT` logged at WARN level with `inference_duration_ms`
* Governed retry policy evaluated: `inference_retry_count < provider_retry_budget_remaining` → retry authorized
* If retry also times out: `INFERENCE_TIMEOUT_EXHAUSTED` reason code; `ai_governance_tier = UNAVAILABLE`
* Timeout duration boundaries resolve from `spec/05_external_integrations.md` — not from hardcoded values (AP-LF5)
* Orchestration cycle not blocked; rule-based evaluation proceeds with UNAVAILABLE AI advisory

---

### 4.4 Confidence Collapse AI Degradation

When AI confidence score falls below the ADVISORY tier lower boundary (< 0.40 per Rule 5 defaults):

* `ai_governance_tier = ADVISORY`; `confidence_tier = LOW`; `degradation_cause = CONFIDENCE_COLLAPSE`
* `advisory_scope = LIMITED` — priority scoring only; no independent intervention routing
* `recommended_intervention = null` — confidence collapse disables intervention recommendation
* No recovery coordination required; confidence collapse is a degraded-advisory state, not a failure requiring recovery
* `CONFIDENCE_COLLAPSE` annotation in observability; consuming services handle null advisory content gracefully

---

### 4.5 Schema Validation AI Degradation

When AI inference output fails structural or schema validation:

* Validation failure does not enter the orchestration pipeline as valid advisory content
* `ai_failure_class = INVALID_STRUCTURE | SCHEMA_MISMATCH | PARTIAL_OUTPUT` in failure record
* Governed retry coordination evaluated per `provider_failure_retry_limit`; if retry also fails, `ai_governance_tier = UNAVAILABLE`
* `AI_GENERATION_FAILED` state written to `ai_insights` record by consuming AI service (not by AI resilience layer directly)
* Orchestration cycle not blocked; rule-based evaluation proceeds

---

### 4.6 AI Insight Backlog Degradation

When inference requests exceed the governed queue capacity or delivery SLA:

* `ai_insight_state IN (AI_GENERATING, AI_PENDING, AI_QUEUED)` → `IN_FLIGHT` tier assigned
* Prior AI version advisory content used at ADVISORY scope if available (`prior_ai_versions` non-empty)
* Decision engine issues `DEFER_PENDING_AI` intent if no prior version is available
* IN_FLIGHT state is an expected operating condition, not a failure requiring recovery coordination
* `reason_codes: ["AI_IN_FLIGHT"]` in all IN_FLIGHT assessments

---

### 4.7 Config Threshold Missing AI Degradation

When a required Config V2 AI threshold (`ai_insight_ttl_hours`, `ai_llm_provider`) cannot be resolved:

* `UNKNOWN_V0` substituted; `CONFIG_THRESHOLD_MISSING_{KEY}` warning emitted
* Dependent rules in `llm_processing_contract.md` excluded from evaluation pass
* Affected evaluation annotated DEGRADED; `reason_codes: ["CONFIG_THRESHOLD_MISSING_{KEY}"]`
* Substituting a hardcoded fallback value (bypassing UNKNOWN_V0 substitution) is prohibited (AP-LF5)
* Persistent missing threshold generates escalation candidacy

---

## 5. REPLAY & REGENERATION AI FAILURE SEMANTICS

---

### 5.1 Replay AI Failure Governance

When the AI resilience layer operates in REPLAY mode (`execution_type = replay`), AI failure behavior is constrained:

* Replay may simulate historical AI failure scenarios from `state_transition_log` records at historical timestamps
* Replay may not generate LIVE inference calls from historical AI failure simulation (AP-LF1)
* Historical AI failure records are read-only reference points; replay does not re-execute historical inference to produce new AI content
* Replay AI failure diagnostics carry `governance_scope = REPLAY_ONLY`; they may not be consumed as LIVE recovery signals
* `fingerprint_comparison_outcome = MATCH | DIVERGENT | UNKNOWN` emitted for simulated vs historical AI failure behavior
* Historical config version resolved from `replay_context.historical_config_version_id` — not from ACTIVE version (per spec/01 §12.4.1)

---

### 5.2 Replay AI Recovery Restrictions

The following LIVE AI effects are suppressed in all replay AI failure contexts:

| Effect category | Suppression mechanism |
|---|---|
| Live AI inference during replay failure simulation | `ai_blocked = true`; `live_inference_suppressed = true`; FINALIZED_COPY sourced from warehouse exclusively |
| New AI insight record creation during replay | Replay Services hold no `ai_insights` write authority |
| FINALIZED_COPY mutation during replay | `warehouse.snapshot_ai_narratives` is read-only in replay context (AP-LF1, AP-LF2) |
| Escalation routing during replay | `REPLAY_ESCALATION_CANDIDATE` scope only; no live operator routing |
| Stale AI upgrade during replay | Replay AI tier assessment uses historical TTL from historical config version |

---

### 5.3 Historical AI Visibility

In REPLAY mode:

* Historical AI failure records sourced from `ai_insights` table at historical timestamp — not from live provider state
* Historical AI confidence and tier assessed using TTL from `historical_config_version_id` rule_set_snapshot
* FINALIZED_COPY AI content sourced exclusively from `warehouse.snapshot_ai_narratives` — never re-inferred
* If no FINALIZED_COPY exists for the replay context: `ai_governance_tier = UNAVAILABLE` with reason code `REPLAY_AI_SOURCE_MISSING`
* Replay may not generate new AI content to substitute for historically unavailable AI
* `replay_partial = true` annotated when historical AI failure data is incomplete

---

### 5.4 Regeneration AI Failure Semantics

Regeneration failures (re-render from FINALIZED snapshot data) are distinct from replay AI failures:

* Regeneration AI content is sourced exclusively from `warehouse.snapshot_ai_narratives` physical copies — same rule as replay
* Regeneration cannot overwrite historical AI narrative content; the regenerated report uses the physically stored text unchanged (AP-LF2)
* If the current fingerprint differs from the historical snapshot fingerprint, `POTENTIALLY_DIVERGENT` annotation is added; regeneration is not blocked
* No live AI inference during regeneration failure recovery
* Failed regeneration AI sourcing produces `ai_governance_tier = UNAVAILABLE` in the regenerated report; report is annotated with `ai_content_unavailable = true`; report generation is not blocked

---

### 5.5 Replay Inference Suppression Gate

Rule 2 in `directives/llm_processing_contract.md` is the mandatory suppression gate. When this gate fires:

* `live_inference_suppressed = true` is set unconditionally
* `replay_restrictions.replay_ai_source` is resolved to `FINALIZED_COPY` or `NONE`
* If any code path attempts to bypass Rule 2 and call an AI provider during replay, the violation must be detected and blocked at the Rule 2 gate (AP-AI5; spec/01 §12.5.5)
* A replay that returns AI content from a live provider call is a specification violation, not a degraded recovery state — it is an AP-LF1 violation

---

## 6. AI FAILURE STATE GOVERNANCE

---

### 6.1 State Authority During AI Failures

The AI resilience layer does not own state transitions. State write authority is externalized to the state management service in all AI failure scenarios:

| AI failure scenario | State coordination | AI resilience layer role |
|---|---|---|
| AI provider unavailable | No student state change required | Annotates advisory absence; orchestration proceeds with rule-based |
| Inference timeout (first attempt) | No student state change | Logs timeout; governed retry evaluated |
| Inference timeout (retry exhausted) | `ai_insight_state = AI_GENERATION_FAILED` written by AI service | Coordinates UNAVAILABLE tier; orchestration proceeds |
| Schema validation failure | `ai_insight_state = AI_GENERATION_FAILED` written by AI service | Coordinates UNAVAILABLE tier after retry exhaustion |
| STALE AI evaluation | No state change | STALE tier assigned; LIMITED scope applied |
| FINALIZED_COPY present | No state change | Rule 1 fires; FINALIZED_COPY served; no re-inference |
| Confidence collapse | No state change | ADVISORY tier assigned; LIMITED scope |
| Duplicate inference detected | No state change | `IDEMPOTENCY_DUPLICATE` logged; second call blocked |

---

### 6.2 Immutable Record Protections During AI Recovery

AI recovery coordination must never mutate:

* `warehouse.snapshot_ai_narratives` — FINALIZED_COPY is immutable; AI recovery does not re-render or overwrite narrative content (AP-LF2, FAD-1)
* `warehouse.student_snapshots` — FINALIZED state is irreversible; AI recovery does not modify snapshot finalization records (AP-LF11, inheriting AP-FP7)
* `warehouse.monthly_reports` — REPORT_PUBLISHED is immutable; AI recovery does not overwrite published reports (AP-LF11)
* `state_transition_log` — append-only; AI recovery produces new entries, not retroactive corrections
* `student_timeline_events` — append-only; AI recovery intent records are new entries, not mutations

---

### 6.3 AI Insight Record Governance During Recovery

* `ai_insights` records carry `model_used` as an immutable field after `AI_GENERATED` state (spec/01 §12.6.5)
* AI recovery coordination never modifies the `model_used` field on existing `ai_insights` records
* New AI evaluation after recovery produces a new `ai_insights` record with a new `ai_insight_version` — it does not overwrite prior records (AP-AI7)
* Failed inference records are preserved in `ai_insights` with `ai_insight_state = AI_GENERATION_FAILED`; these are observable historical artifacts

---

## 7. AI RECOVERY ORCHESTRATION COORDINATION

---

### 7.1 Governed AI Recovery Coordination Model

The V1 pattern:

> "Retry LLM call (once)" and "Proceed without LLM"

is replaced with:

> **Governed AI Recovery Orchestration Coordination** — the AI resilience layer coordinates tier transitions, retry budget evaluation, and degradation annotation through the same governance-authorized AI orchestration sequence; recovery does not bypass Rule 0, Rule 2, or any governance precondition gate; retry authorization is governed by `provider_failure_retry_limit` from `directives/llm_processing_contract.md §3.5`

AI recovery coordination model:

```
INFERENCE FAILURE DETECTED  →  structured AI failure log emitted (ai_failure_class, retry_count, correlation_id)
  ↓
RETRY AUTHORIZATION GATE  →  inference_retry_count < provider_retry_budget_remaining?
  ├── YES → governed retry coordination (same attribution chain; retry attributed, not hidden)
  └── NO  → UNAVAILABLE tier assigned; RULE_BASED_ONLY fallback_type
  ↓
OBSERVABILITY EMISSION  →  ai_governance_tier + advisory_scope + degradation_cause + outcome
  ↓
ORCHESTRATION CONTINUATION  →  consuming services receive AIAssessment; orchestration cycle not blocked
```

---

### 7.2 Config V2-Governed AI Recovery Thresholds

AI recovery behavior is governed by Config V2, not by hardcoded values:

| AI recovery threshold | Config V2 source | Group |
|---|---|---|
| AI insight freshness boundary | `ai_insight_ttl_hours` | H |
| AI provider selection | `ai_llm_provider` | H |
| Provider retry budget | `provider_failure_retry_limit` | per `spec/05_external_integrations.md` |
| SQL Server sync age for AI input staleness | `sql_server_max_sync_age_hours` | K |

No hardcoded AI recovery thresholds are permitted. Substituting a literal integer for any of these values in AI failure handling logic is a specification defect (AP-LF5).

---

### 7.3 AI Dead-Letter Governance

Failed AI evaluations that cannot be resolved by governed retry coordination are not silently discarded:

* Failed evaluation record preserved in `ai_insights` with `ai_insight_state = AI_GENERATION_FAILED`
* Dead-letter-equivalent state carries full attribution: `correlation_id`, `causation_id`, `ai_failure_class`, `ai_version_number`, `prompt_version`, `model_used`, `attempt_count`
* AI generation failure records produce escalation candidacy for persistent patterns (e.g., repeated GENERATION_FAILED for the same student)
* Recovery from AI generation failure requires a new governed evaluation with a new `ai_insight_version` — not a direct re-execution of the failed inference

---

## 8. ATTRIBUTION & OBSERVABILITY

---

### 8.1 AI Failure Attribution Lineage Chain

Every AI failure record must carry a complete attribution lineage:

```
Config V2 governance  →  config_version_id + ai_insight_ttl_hours + ai_llm_provider
  ↓
Orchestration cycle  →  correlation_id + cycle_id + execution_mode + execution_type
  ↓
Originating AI evaluation request  →  causation_id + idempotency_key + attribution_context
  ↓
AI governance tier assignment  →  ai_governance_tier + advisory_scope + rule_path_taken
  ↓
AI failure event  →  ai_failure_class + error_class + inference_retry_count + inference_duration_ms
  ↓
Degradation record  →  degradation_cause + fallback_type + fallback_applied
  ↓
Escalation candidacy (if applicable)  →  escalation_type + escalation_severity
```

An AI failure that cannot be traced from symptom back to root cause using a single `correlation_id` is an observability defect (inheriting `failure_playbook.md §8.1`).

---

### 8.2 AI Causation Propagation

Every AI recovery coordination action must propagate causation lineage:

* Retry attempts carry the same `correlation_id` and `causation_id` as the original evaluation request
* Post-recovery AI assessments carry `causation_id` referencing the original failing assessment intent
* New `ai_insight_version` records created after recovery carry the recovery cycle's `correlation_id` in their audit trail
* Attribution fields propagate unchanged through all AIAssessment outputs (AP-AI15)

---

### 8.3 Inference-Failure Replay Diagnostics

AI replay failure diagnostics must carry:

| Field | Specification |
|---|---|
| `source_artifact_id` | ID of the historical AI evaluation or snapshot being replayed |
| `historical_config_version_id` | Config version at time of original AI failure |
| `fingerprint_comparison_outcome` | `MATCH \| DIVERGENT \| UNKNOWN` |
| `replay_partial` | `true` if historical AI data was incomplete |
| `execution_type` | `replay` |
| `governance_scope` | `REPLAY_ONLY` |
| `replay_ai_source` | `FINALIZED_COPY \| NONE` |
| `live_inference_suppressed` | `true` always during replay |

---

### 8.4 AI Recovery Audit Continuity

All AI recovery coordination produces observable, auditable records:

* AI failure records are append-only — no retroactive updates to prior `ai_insights` records
* Every AI recovery coordination is attributable to `actor_identity` (`system` for automated; named for operator-initiated)
* AI recovery records are preserved with `execution_type = recovery` where applicable
* AI resilience layer does not produce records that contradict the append-only history of AI insight evaluation

---

## 9. AI FAILURE IDEMPOTENCY GUARANTEES

---

### 9.1 Core AI Idempotency Principle

Every AI recovery coordination in the resilience layer must satisfy the idempotency principle inherited from `spec/04_idempotency_concurrency.md §2.1`:

> Repeated operations MUST NOT create duplicate effects. Same request → same outcome. Same input + same state → same persisted result; no first-run/second-run divergence.

---

### 9.2 AI Domain-Specific Idempotency Keys

| Domain | Idempotency key | Behavior on duplicate |
|---|---|---|
| AI evaluation request | `(student_id, checkpoint_type, cycle_timestamp)` | Duplicate → no-op; `IDEMPOTENCY_DUPLICATE` logged at WARN |
| AI insight generation | `(student_id, insight_type, date_period, prompt_version)` | Duplicate → no-op; prior record returned |
| AI inference retry | `(student_id, insight_type, date_period, prompt_version, retry_attempt_number)` | Duplicate retry → no-op |
| Snapshot AI physical copy | `(student_id, snapshot_month)` | FINALIZED is irreversible; no re-finalization; AP-LF2 |
| Report regeneration with AI | New version lineage created | Does not overwrite existing REPORT_PUBLISHED |
| AI recovery escalation candidacy | `(student_id, ai_failure_class, cycle_id)` | Duplicate candidacy → idempotent confirmation |

---

### 9.3 AI Idempotency Violations Are Production Defects

An AI operation that "works once but produces duplicate effects on the second run" is broken. AI idempotency violations in recovery paths must be fixed before the change ships:

* Recovery that calls the AI provider a second time without checking the idempotency gate (AP-LF12)
* Recovery that overwrites a FINALIZED_COPY record in `warehouse.snapshot_ai_narratives` (AP-LF2)
* Recovery that writes a duplicate `ai_insights` record for the same `(student_id, insight_type, date_period, prompt_version)` without versioning
* Recovery that triggers duplicate LIVE escalation candidacy for the same AI failure event

---

## 10. DETERMINISTIC AI DEGRADATION CONDITION TABLE

---

### 10.1 Canonical AI Degradation Conditions

Inherited from `directives/llm_processing_contract.md §10` and `runtime/system_loop.md §10.2` with AI resilience annotations:

| Condition | AI governance tier | Advisory scope | Fallback type | Orchestration | Resilience escalation |
|---|---|---|---|---|---|
| Provider circuit breaker OPEN | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Continues | `CIRCUIT_BREAKER_OPEN` + escalation candidacy |
| Provider UNAVAILABLE + retry budget exhausted | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Continues | `PROVIDER_RETRY_EXHAUSTED` + escalation candidacy |
| Inference timeout (single attempt) | In-flight evaluation | Governed retry authorized | None yet | Retry coordinated | `INFERENCE_TIMEOUT` WARN log |
| Inference timeout (retry also timed out) | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Continues | `INFERENCE_TIMEOUT_EXHAUSTED` + escalation candidacy |
| AI insight STALE (beyond TTL) | `STALE` | `LIMITED` | None (stale served annotated) | Continues; LIVE escalation blocked | `stale_flag = true`; `stale_for_hours` populated |
| AI insight MISSING (null) | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Continues | `AI_INSIGHT_ABSENT` reason code |
| Confidence collapse (< 0.40) | `ADVISORY` | `LIMITED` | None (ADVISORY scope) | Continues; no independent intervention | `CONFIDENCE_COLLAPSE` degradation_cause |
| AI generation IN_FLIGHT | `IN_FLIGHT` | `DEFERRED` | Prior version at ADVISORY | `DEFER_PENDING_AI` if no prior; else prior version advisory | `AI_IN_FLIGHT` reason code |
| Schema validation failure (retry exhausted) | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Continues | `INVALID_STRUCTURE \| SCHEMA_MISMATCH` reason code |
| FINALIZED_COPY present | `FINALIZED_COPY` | `IMMUTABLE` | Served from warehouse | No live inference; regeneration read-only | `AI_FINALIZED_COPY_SERVING` reason code |
| Replay with no FINALIZED_COPY | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Replay continues without AI | `REPLAY_AI_SOURCE_MISSING` reason code |
| Provider identity divergence | Tier unchanged | Scope unchanged | No snapshot eligibility | Continues; snapshot blocked | `PROVIDER_IDENTITY_DIVERGENCE` + `eligible_for_snapshot = false` |
| Config threshold missing (`ai_insight_ttl_hours`) | Degraded tier resolution | As resolved | `RULE_BASED_ONLY` for dependent rules | Continues excluding dependent rules | `CONFIG_THRESHOLD_MISSING_AI_INSIGHT_TTL_HOURS` |
| AI Advisory absent in degraded retry | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Retry proceeds rule-based | `AI_ADVISORY_ABSENT_DEGRADED` annotation (UE-RF5) |
| Governance precondition failure (Rule 0) | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Blocked until precondition resolved | `GOVERNANCE_PRECONDITION_FAILED` reason code |

---

## 11. AI RESILIENCE OBSERVABILITY SCHEMA

---

### 11.1 Structured AI Failure Log Record

Every AI failure event must emit a structured JSON record:

```json
{
  "timestamp": "ISO-8601",
  "level": "warn | error",
  "service": "ai_resilience_orchestration",
  "event": "ai_failure_detected | ai_degradation_active | ai_recovery_coordinated",
  "failure_domain": "ai",
  "ai_failure_class": "TIMEOUT | INVALID_STRUCTURE | SCHEMA_MISMATCH | HALLUCINATION_DETECTED | PARTIAL_OUTPUT | PROVIDER_UNAVAILABLE | CONFIDENCE_COLLAPSE | DUPLICATE_INFERENCE | REPLAY_INFERENCE_SUPPRESSED | FINALIZED_COPY_PROTECTION | FINGERPRINT_DIVERGENCE | ATTRIBUTION_LOSS | OBSERVABILITY_DEGRADED",
  "correlation_id": "uuid",
  "causation_id": "uuid | null",
  "execution_mode": "SHADOW | LIVE | REPLAY | REGENERATION | DEGRADED | MAINTENANCE",
  "execution_type": "original | replay | regeneration | recovery",
  "config_version_id": "string | null",
  "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | IN_FLIGHT | UNAVAILABLE | FINALIZED_COPY",
  "advisory_scope": "FULL | LIMITED | UNAVAILABLE | IMMUTABLE | DEFERRED",
  "degradation_cause": "PROVIDER_UNAVAILABLE | INFERENCE_TIMEOUT | STALE_AI | CONFIDENCE_COLLAPSE | CIRCUIT_OPEN | SCHEMA_INVALID | REPLAY_SUPPRESSION | null",
  "fallback_type": "RULE_BASED_ONLY | PRIOR_VERSION | FINALIZED_COPY | null",
  "fallback_applied": false,
  "retry_count": 0,
  "provider_degradation_state": "OPERATIONAL | DEGRADED | UNAVAILABLE | RATE_LIMITED | CIRCUIT_OPEN",
  "circuit_breaker_state": "CLOSED | HALF_OPEN | OPEN",
  "ai_version_number": 0,
  "prompt_version": "string | null",
  "model_used": "string | null",
  "inference_duration_ms": 0,
  "affected_student_id": "uuid",
  "recovery_action": "governed_retry | unavailable_tier_assigned | stale_tier_served | rule_based_fallback | dead_letter | escalation_candidacy | no_op",
  "orchestration_continues": true,
  "idempotency_key": "string | null",
  "reason_codes": [],
  "outcome": "failure | partial | degraded"
}
```

> PII (student name, contact details, transcript text, AI narrative text) must NOT appear in any field of this record (AP-LF14, inheriting AP-AI10).

---

### 11.2 AI Recovery Coordination Completion Record

A governed AI recovery coordination emits a completion record:

```json
{
  "timestamp": "ISO-8601",
  "level": "info",
  "service": "ai_resilience_orchestration",
  "event": "ai_recovery_coordination_complete",
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "execution_mode": "SHADOW | LIVE | DEGRADED",
  "execution_type": "original | recovery",
  "config_version_id": "string",
  "ai_governance_tier_at_recovery": "UNAVAILABLE | ADVISORY | STALE | CONFIDENT",
  "advisory_scope_at_recovery": "UNAVAILABLE | LIMITED | FULL",
  "fallback_type_applied": "RULE_BASED_ONLY | PRIOR_VERSION | STALE_ANNOTATED | null",
  "retry_attempts_made": 0,
  "provider_retry_budget_remaining": 0,
  "orchestration_continued": true,
  "escalation_candidacy_generated": false,
  "ai_version_number": 0,
  "outcome": "success | partial | failure"
}
```

---

## 12. ARCHITECTURE PRESERVATION RULES

---

### AP-LF1 — No Replay-Triggered LIVE AI Inference

MUST NOT allow replay-mode AI failure simulation to generate live AI provider calls. All outputs from replay-mode AI resilience evaluation carry `execution_type = replay`, `live_inference_suppressed = true`, and `governance_scope = REPLAY_ONLY`. No mode transition from REPLAY to LIVE occurs within an AI resilience sequence. Violation is a specification defect (inheriting AP-FP2, AP-AI5).

### AP-LF2 — No FINALIZED_COPY Mutation Under Any Condition

MUST NOT overwrite, regenerate, backfill, or retroactively modify AI narrative text physically copied into `warehouse.snapshot_ai_narratives` — not during provider outage recovery, not during force-refresh coordination, not during model upgrade coordination, not during compliance deletion of `ai_insights` records, not during inference retry coordination. FINALIZED_COPY is immutable without exception (inheriting FAD-1, AP-AI6, AP-AI12, AP-FP7).

### AP-LF3 — No "Retry Inference Once" Semantics

MUST NOT use "retry LLM call (once)" or equivalent as an AI recovery instruction. Inference retry authorization is governed by `provider_failure_retry_limit` from the operational context. No hardcoded retry-once pattern is permitted in any AI failure domain (inheriting AP-FP3).

### AP-LF4 — No Silent AI Fallback Execution

MUST NOT silently transition AI tier, silently suppress AI advisory, or silently apply rule-based substitution without emitting a structured failure log with `ai_failure_class`, `degradation_cause`, and `fallback_type`. Hidden AI degradation mode switching, undocumented silent substitution, and silent UNAVAILABLE tier assignment are prohibited (inheriting AP-FP4, AP-AI8).

### AP-LF5 — No Hardcoded AI Recovery Thresholds

MUST NOT substitute hardcoded values for Config V2-governed AI thresholds (`ai_insight_ttl_hours`, `ai_llm_provider`, `provider_failure_retry_limit`, `sql_server_max_sync_age_hours`). When thresholds are missing, `UNKNOWN_V0` substitution applies with DEGRADED annotation — not a hardcoded integer fallback (inheriting AP-FP5, AP-AI9).

### AP-LF6 — No Silent Model Substitution

MUST NOT substitute an alternative AI provider when the configured provider (`ai_llm_provider`) is unavailable. Degradation must be explicit: `ai_governance_tier = UNAVAILABLE`, `degradation_cause = PROVIDER_UNAVAILABLE`, `fallback_type = RULE_BASED_ONLY`. Selecting an undeclared alternative model is a specification violation regardless of its availability (inheriting AP-AI8).

### AP-LF7 — No Hidden Inference Retries

MUST NOT execute inference retries that are not attributed to the originating orchestration cycle, do not emit a structured log entry, or do not decrement from the governed retry budget. Every retry attempt is attributed, observable, and budget-bounded (inheriting AP-FP6).

### AP-LF8 — No Non-Attributable AI Recovery Actions

MUST NOT allow any AI recovery coordination action without `correlation_id`, `execution_mode`, `execution_type`, `config_version_id`, `ai_governance_tier`, and `ai_failure_class`. AI recovery actions without complete attribution are orphaned records — they are specification defects, not acceptable approximations (inheriting AP-FP6).

### AP-LF9 — No AI Authority Escalation During Failure

MUST NOT expand AI advisory scope or elevate AI from advisory-only to decision-making authority during degraded operation. AI failure does not promote AI governance tier. AI absence during failures is annotated and rule-based evaluation proceeds. Provider outage that disables AI does not change AI's governance role (inheriting AP-FP9, AP-AI1).

### AP-LF10 — No Blocking Orchestration on AI Failure

MUST NOT allow AI failure — in any failure class — to block an orchestration cycle. AI advisory absence is a scope restriction (`advisory_scope = UNAVAILABLE`), not a blocking condition. Orchestration proceeds on rule-based signals when AI is unavailable. AI is not on the critical path for orchestration completion (inheriting AP-FP9, AP-AI3).

### AP-LF11 — No Immutable Record Mutation During AI Recovery

MUST NOT overwrite, backfill, or retroactively modify any record in `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `warehouse.monthly_reports`, `state_transition_log`, or `student_timeline_events` during AI recovery coordination. All AI recovery coordination produces new append-only records (inheriting AP-FP7, AP-AI7).

### AP-LF12 — No Duplicate LIVE Inference Execution from Recovery

MUST NOT allow AI recovery coordination to produce a second live inference call for the same idempotency key `(student_id, checkpoint_type, cycle_timestamp)`. Idempotency gate check is mandatory before any recovery inference authorization. Duplicate recovery inference is a production defect (inheriting AP-FP11).

### AP-LF13 — No Governance Bypass During AI Recovery

MUST NOT bypass Rule 0 (governance precondition gate), Rule 1 (FINALIZED_COPY isolation check), or Rule 2 (replay mode gate) in `directives/llm_processing_contract.md` during AI recovery coordination. Recovery AI evaluations are subject to the same governance precondition gate as original AI evaluations (inheriting AP-FP8).

### AP-LF14 — No PII in AI Resilience Observability Records

MUST NOT log raw PII — student name, contact information, AI narrative text content, transcript text, or personally identifiable content — in any AI resilience structured log record. `student_id` (UUID opaque identifier) is the only permitted student reference (inheriting AP-AI10, AP-FP13).

### AP-LF15 — No Silent AI Error Swallowing

MUST NOT use `try { ... } catch (e) {}` semantics anywhere in the AI resilience layer on inference calls or tier transition coordination. Every caught exception is tagged with a stable `error_class` string and emitted as a structured log with `ai_failure_class` before any fallback or continuation path is taken (inheriting AP-FP14).

---

## 13. ACCEPTANCE CRITERIA

---

### AC-LF1 — Deterministic AI Resilience Behavior

**Given** any AI failure condition defined in §10.1
**When** the AI resilience orchestration layer processes the failure
**Then** the outcome is deterministic: the same AI failure input produces the same `ai_governance_tier`, the same `advisory_scope`, the same `fallback_type`, and the same structured failure log — with no undocumented variation between runs

---

### AC-LF2 — Replay-Safe AI Recovery Behavior

**Given** a replay-mode AI resilience evaluation of a historical AI failure
**When** the failure simulation completes
**Then** no LIVE AI inference is triggered; all outputs carry `execution_type = replay`, `live_inference_suppressed = true`, and `governance_scope = REPLAY_ONLY`; `fingerprint_comparison_outcome` is emitted; `replay_ai_source = FINALIZED_COPY | NONE`

---

### AC-LF3 — Immutable Lineage Preservation

**Given** an AI recovery coordination completes
**When** any record is written
**Then** no existing record in `warehouse.snapshot_ai_narratives`, `warehouse.student_snapshots`, `state_transition_log`, or `student_timeline_events` is modified; only new append-only records are produced; FINALIZED_COPY status is preserved unconditionally

---

### AC-LF4 — FINALIZED_COPY Immutability Under All Conditions

**Given** `ai_finalized_copy = true` for a student's snapshot AI content
**When** any AI failure recovery path is evaluated
**Then** Rule 1 fires immediately; `ai_governance_tier = FINALIZED_COPY`; no re-inference is triggered; no modification to `warehouse.snapshot_ai_narratives` is made; provider outage, model upgrade, TTL expiry, and compliance deletion scope all fail to reach the frozen snapshot text

---

### AC-LF5 — Degraded-Mode Safety

**Given** the AI provider is unavailable (circuit breaker OPEN or `provider_degradation_state = UNAVAILABLE`)
**When** an orchestration cycle runs
**Then** AI inference is blocked; `ai_governance_tier = UNAVAILABLE`; `advisory_scope = UNAVAILABLE`; `fallback_type = RULE_BASED_ONLY`; orchestration cycle continues on rule-based signals; no silent model substitution occurs; existing STALE insights are served with LIMITED scope if within TTL

---

### AC-LF6 — Attribution Continuity

**Given** any AI recovery coordination action is taken
**When** the AI failure record is written
**Then** `correlation_id`, `causation_id` (where applicable), `execution_mode`, `execution_type`, `config_version_id`, `ai_governance_tier`, and `ai_failure_class` are present on every record; a failure that cannot be traced to root cause via a single `correlation_id` is an observability defect

---

### AC-LF7 — Inference-Failure Containment

**Given** an AI inference failure occurs (timeout, schema invalid, provider error)
**When** the AI resilience layer processes the failure
**Then** the orchestration cycle is NOT blocked; `advisory_scope = UNAVAILABLE` is assigned; rule-based evaluation proceeds; no escalation of AI authority occurs; structured failure log is emitted with full `ai_failure_class` classification

---

### AC-LF8 — Idempotent AI Recovery Orchestration

**Given** the same AI evaluation request is submitted twice (duplicate idempotency key)
**When** the second request arrives
**Then** Rule 0 blocks with `IDEMPOTENCY_DUPLICATE`; no second inference call is made; no new `ai_insights` record is created; `IDEMPOTENCY_DUPLICATE` is logged at WARN level; the orchestration cycle that submitted the duplicate continues without AI blocking

---

### AC-LF9 — No Hardcoded AI Retry Semantics

**Given** an AI inference failure occurs
**When** the AI resilience layer determines recovery behavior
**Then** no "retry inference once" or fixed-count retry is applied; retry authorization is governed by `provider_failure_retry_limit`; no hardcoded integer retry count is used; `provider_retry_budget_remaining` is decremented per governed semantics

---

### AC-LF10 — Silent Model Substitution Prohibited

**Given** the configured AI provider (`ai_llm_provider`) is unavailable
**When** the AI resilience layer processes the unavailability
**Then** no alternative AI provider is silently substituted; `ai_governance_tier = UNAVAILABLE`; `degradation_cause = PROVIDER_UNAVAILABLE`; `PROVIDER_UNAVAILABLE` event is logged at WARN level; rule-based evaluation proceeds exclusively

---

### AC-LF11 — Replay AI Inference Suppression

**Given** `execution_type = replay` and the replay context contains a historical AI failure
**When** the AI resilience layer evaluates the historical failure
**Then** `live_inference_suppressed = true`; `replay_ai_source = FINALIZED_COPY | NONE`; no AI provider call is made; `governance_scope = REPLAY_ONLY`; `fingerprint_comparison_outcome` is emitted

---

### AC-LF12 — AI Failure Observability Completeness

**Given** any AI failure event is processed by the AI resilience layer
**When** the failure is logged
**Then** the structured JSON record contains `failure_domain = ai`, `ai_failure_class`, `correlation_id`, `execution_mode`, `ai_governance_tier`, `advisory_scope`, `degradation_cause`, `fallback_type`, and `outcome`; no unstructured console.log or silent error swallow occurs; no PII appears in the log record

---

## 14. UNRESOLVED GOVERNANCE CONCERNS

---

The following governance decisions affecting AI resilience behavior are deferred. They are documented here for governance review and are not blocking. The system operates without them using governed approximations noted below.

**UE-LF1: AI inference retry budget scope** — Does `provider_failure_retry_limit` apply per evaluation cycle, per student per day, or per provider per cycle? Currently: assumed per evaluation call. Governing decision: define scope in `directives/llm_processing_contract.md §3.5` (operational). See also `failure/failure_playbook.md UE-FP3`.

**UE-LF2: Persistent AI outage escalation threshold** — How many consecutive AI UNAVAILABLE events trigger a governance escalation vs a self-recovering no-op? Currently: any AI UNAVAILABLE generates escalation candidacy. Governing decision: define a persistence threshold in Config V2. (OPERATIONAL DECISION)

**UE-LF3: Stale AI serving window after provider recovery** — When the AI provider recovers from an outage, does the system immediately begin refreshing STALE insights for affected students, or does it wait for the next scheduled evaluation cycle? Currently: waits for next evaluation cycle. Governing decision: may be automated under Config V2 governance. (GOVERNANCE DECISION)

**UE-LF4: FINALIZED_COPY hash mismatch recovery** — When `ai_narrative_hash` on a stored FINALIZED_COPY record diverges from the expected hash during replay, what is the governed response? Currently: `POTENTIALLY_DIVERGENT` annotation; assessment still serves from stored copy. Governing decision: define explicit divergence remediation path. (GOVERNANCE DECISION)

**UE-LF5: AI hallucination containment gate** — What guardrails detect factually incorrect AI outputs before they reach advisory scope? Currently: confidence score and schema validation only; no semantic hallucination detector exists. Governing decision: define detection criteria and blocking thresholds. See `directives/llm_processing_contract.md UE-AI3`. (IMPLEMENTATION DEPENDENCY — blocks PRODUCTION advisory content serving without quality audit)

---

## 15. DOWNSTREAM REFERENCES

---

### 15.1 Authoritative Parent Contracts

This document inherits from:

| Contract | Governing sections |
|---|---|
| `failure/failure_playbook.md` | §2.3 (AI Failures domain); §3.3 (AI Authority Restrictions); §4.3 (AI Provider Outage Degradation); §5 (Replay & Regeneration Failure Semantics); §6 (Failure State Governance); §7 (Recovery Orchestration Coordination); §8 (Attribution & Observability); §9 (Idempotency Guarantees); §12 AP-FP1–AP-FP15 |
| `directives/llm_processing_contract.md` | §2 (AI Governance Tiers); §3 (Input Model); §4 (AIAssessment Schema); §5 (Rules 0–11); §6 (Config Version Governance); §7 (Replay & Regeneration Semantics); §8 (Provider Governance); §9 (Observability & Attribution); §10 (Deterministic Degradation Rules); §12 AP-AI1–AP-AI15 |
| `runtime/system_loop.md` | §9 (AI Advisory Governance); §10 (Degradation & Failure Governance); §3 (Runtime Modes); §11 (Attribution & Observability) |
| `runtime/retry_cycle_flow.md` | §7 (Replay suppression in retry); §8 (Provider governance in retry); §9 (AI Advisory Governance in retry); UE-RF5 (AI Advisory absent in degraded retry) |
| `spec/04_idempotency_concurrency.md` | §2 (Core principles); §4.x (Domain idempotency keys including AI refresh) |
| `spec/06_observability_operations.md` | Structured log requirements; correlation ID propagation; AI staleness alert thresholds §10.4 |
| `spec/09_security_privacy.md` | PII protection in AI inference logs and resilience records |

---

### 15.2 Relationship to Sibling Child Contracts

| Contract | AI resilience relationship |
|---|---|
| `failure/scheduling_failures.md` | Scheduler failure may affect AI evaluation cycle timing; AI advisory absence during scheduler recovery annotated with `AI_ADVISORY_ABSENT_DEGRADED` |
| `failure/ghl_failures.md` | Provider dispatch failure does not affect AI evaluation paths; AI and GHL failure domains are independent; both governed by `failure_playbook.md` AP-FP rules |

---

### 15.3 Foundational Architectural Decisions Preserved

| Decision | Preservation mechanism |
|---|---|
| **FAD-1** — AI text physically copied into FINALIZED snapshots is immutable | AP-LF2; §2.7 (FINALIZED_COPY Protection Failures); AC-LF4 |
| **FAD-3** — New config versions affect only evaluations begun after activation | §4.3 (Replay staleness assessment uses historical config); §2.3 (TTL boundary uses historical config in replay) |
| **Append-only architecture** | AP-LF11; §6.2; all recovery coordination produces new records only |
| **Historical reproducibility** | §5 (Replay & Regeneration AI Failure Semantics); §8.3 (Inference-Failure Replay Diagnostics) |
| **Governance invariants** | AP-LF13; Rule 0, Rule 1, Rule 2 gates preserved under all recovery conditions |
| **Snapshot reproducibility guarantees** | §2.8 (Fingerprint Divergence Failures); AC-LF4; fingerprint captured at finalization and immutable thereafter |

---

## END OF FILE
