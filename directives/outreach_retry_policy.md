# directives/outreach_retry_policy.md

---

## LAYER 3 — DIRECTIVES (ORCHESTRATION RETRY ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-25 to reflect the finalized governed historical intelligence platform architecture established in `directives/core_decision_engine.md` and `directives/outreach_eligibility_rules.md`. The previous version described a communication-attempt retry execution policy (CALL → SMS → EMAIL sequencing, hardcoded attempt limits, fixed 24-hour intervals) that is architecturally incompatible with the governance-aware orchestration-intelligence platform defined in spec/01 through spec/09. Retry policy is no longer a dispatch sequencer. It is orchestration retry advisement and retry eligibility governance.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **Orchestration Retry Architecture** defines the retry advisement and retry eligibility governance layer of the Student Success Intelligence Platform. It specifies:

* How a student transitions from a prior-contact context into retry orchestration consideration
* What governance preconditions must hold before retry evaluation may proceed
* How config-version-governed thresholds determine retry window eligibility, cooldown state, and escalation candidacy
* How provider failure lineage affects retry timing and escalation thresholds
* How replay, regeneration, and SHADOW execution semantics constrain retry advisement outputs
* How AI-governance tiers influence retry priority without overriding rule-based retry eligibility
* What attribution, observability, and lineage metadata must accompany every retry advisement output

This directive is the authoritative specification for **orchestration retry advisement and retry eligibility governance**. It is consumed by the outreach orchestration service after the Core Decision Engine (`directives/core_decision_engine.md`) has produced a `RETRY_OUTREACH` intent, and by the Core Decision Engine itself to enrich the retry eligibility signals that feed into its Rule 11 evaluation.

---

### 1.2 Retry Advisory Categories

Retry governance produces multiple distinct advisory categories, not a single binary retry gate. The following categories are defined:

| Category | Definition | Governing rule(s) |
|---|---|---|
| **Retry cooldown eligibility** | The config-bound retry window has elapsed since the last contact timestamp, accounting for any provider-failure cooldown extensions | Rules 9, 11 |
| **Retry attempt eligibility** | The contact attempt count is within the config-bound maximum; at least one retry attempt remains available | Rules 3, 7 |
| **Escalation candidacy within retry context** | Consecutive non-response, provider failure threshold, compliance hold, or critical risk signals mandate escalation routing instead of retry dispatch | Rules 2, 7, 8, 9 |
| **Replay retry eligibility** | The historical retry decision context, fingerprint, and config lineage permit replay assessment; replay isolation semantics are enforceable | Rule 10 |
| **Retry priority** | Multi-factor risk signals — attempt proximity to maximum, historical escalation recurrence, engagement signal, provider failure history — determine retry urgency | Rules 12, 13 |
| **AI-assisted retry prioritization eligibility** | AI insight freshness, governance tier, and confidence metadata qualify the AI signal for use in retry priority adjustment | Rules 5, 13 |

All six categories are evaluated when evaluation proceeds past Rule 0. The resulting `RetryOrchestrationAssessment` output carries the advisory outcome across all six.

---

### 1.3 What Retry Policy Is NOT

To prevent scope creep and architectural boundary violations, this directive explicitly defines what retry policy advisement does NOT do:

* **Does not dispatch outbound retry communications.** Retry advisement determines eligibility and advisory scope. The Core Decision Engine produces the `RETRY_OUTREACH` intent. The outreach orchestration service dispatches retry communications under governance enforcement. The retry policy is advisory to the orchestration service and cannot bypass it.
* **Does not select retry channels.** CALL, SMS, EMAIL, and channel fallback sequencing for retry attempts are the channel orchestration layer's responsibility. Retry policy knows nothing about channel availability, channel selection, or channel-specific retry timing. The legacy `CALL → SMS → EMAIL` model belongs in the channel layer, not here.
* **Does not mutate outreach state or retry lineage.** No state machine transition (e.g., NO_RESPONSE → RETRY) originates from retry policy evaluation. All state writes belong to the state management service.
* **Does not dispatch escalation.** Escalation candidacy identified during retry evaluation is carried in the advisory output for the escalation routing service to act on. The escalation action is not initiated here.
* **Does not interact directly with providers.** Provider failure lineage is an INPUT to retry policy evaluation, sourced from the outreach history. The retry policy does not query providers, retry provider calls, or manage provider circuit breakers.
* **Does not override governance invariants.** Retry policy operates within INVARIANT-1 through INVARIANT-7 (spec/03 §40). It does not adjudicate them.
* **Does not write to any database.** All database writes — idempotency key storage, audit log entries, retry state records — are the responsibility of consuming services.

---

## 2. INPUT MODEL

---

The retry assessment context is **lineage-aware and governance-aware**. Every input carries metadata establishing its authority class and origin. Inputs from SQL Server (`origin_authority = sql_server_authoritative`) govern eligibility decisions. Platform-supplementary inputs provide retry operational context but do not override SQL Server-authoritative state (INVARIANT-6, spec/03 §40).

---

### 2.1 Retry Context

Retry lineage, attempt history, and prior escalation context sourced from platform-owned operational tables.

| Field | Type | Authority | Description |
|---|---|---|---|
| `contact_attempt_count` | integer | `platform_supplementary` | Total contact attempts made in the current outreach cycle |
| `last_contact_timestamp` | datetime | `platform_supplementary` | Most recent outreach event timestamp; used for cooldown window calculation |
| `last_contact_outcome` | enum | `platform_supplementary` | Outcome of most recent contact: `CONNECTED`, `NO_ANSWER`, `VOICEMAIL`, `DELIVERY_FAILED`, `PROVIDER_ERROR`, `OPTED_OUT` |
| `retry_attempt_number` | integer | `platform_supplementary` | Count of retry attempts specifically (excludes initial contact); must be ≤ `contact_attempt_count - 1` |
| `retry_history` | list | `platform_supplementary` | Log of retry attempts: timestamps, outcomes, retry gap durations, provider identifiers |
| `delivery_failure_lineage` | list | `platform_supplementary` | Sequence of delivery failure events in the current cycle: failure type, provider, timestamp |
| `consecutive_no_response_count` | integer | `platform_supplementary` | Count of sequential no-response outcomes (NO_ANSWER, VOICEMAIL, no inbound response) without a CONNECTED outcome |
| `provider_failure_count` | integer | `platform_supplementary` | Count of `PROVIDER_ERROR` or `DELIVERY_FAILED` outcomes in the current cycle (excludes NO_ANSWER, VOICEMAIL) |
| `channel_exhaustion_state` | enum | `platform_supplementary` | Current channel availability: `AVAILABLE`, `PARTIAL`, `EXHAUSTED`; sourced from channel availability service |
| `prior_escalation_history` | list | `platform_supplementary` | Escalation events in the current cycle: reason, urgency, resolution timestamp if any |
| `orchestration_history` | list | `platform_supplementary` | Prior orchestration intents produced for this student in the current cycle |
| `quick_action_history` | list | `platform_supplementary` | Recent operator quick actions: `ESCALATE`, `CLOSE_CASE`, `FORCE_RETRY`, etc. |

---

### 2.2 Governance Context

Governance context is mandatory for every retry evaluation. Retry assessments produced without full governance context are invalid and must not be consumed by orchestration services.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ID of the ACTIVE config version at assessment time (must be resolved before Rule 0 executes) |
| `config_version_status` | enum | Status of the resolved config version: `ACTIVE` (operational) or `SUPERSEDED` (replay only) |
| `config_rule_set` | object | Extracted threshold values from the ACTIVE (or historical) config version's `rule_set_snapshot` |
| `execution_mode` | enum | Platform execution mode: `SHADOW` (default; no outbound effects) or `LIVE` (requires Phase 12 certification) |
| `execution_type` | enum | `original`, `replay`, or `regeneration`; drives replay-safety rules (§6) |
| `correlation_id` | uuid | UUID v4 propagated from the triggering scheduler run or operator action |
| `causation_id` | uuid | UUID v4 of the upstream event that caused this retry evaluation (may be null for root events) |
| `attribution_context` | object | Full attribution metadata: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp` |
| `fingerprint_context` | object | Snapshot Reproducibility Fingerprint components at the time of this evaluation; used for replay safety |
| `idempotency_key` | string | Retry-assessment-level idempotency key `(student_id, checkpoint_type, cycle_timestamp, retry_attempt_number)` |
| `compliance_hold_flag` | boolean | True if the student's snapshot is currently under `COMPLIANCE_HOLD` |
| `replay_context` | object | Present only when `execution_type ∈ {replay, regeneration}`; contains source artifact ID, historical config reference, and fingerprint from the source snapshot |

---

### 2.3 Attribution Context

Attribution context establishes the provenance of the retry assessment and must propagate unchanged to all downstream records.

| Field | Type | Description |
|---|---|---|
| `origin_source` | enum | Who triggered the assessment: `system_automated` (scheduler), `operator` (manual retry action), or `scheduler` |
| `origin_authority` | enum | Authority class of the triggering source: `platform_supplementary` for all retry assessments |
| `actor_identity` | string | Service identifier: `retry_policy_v{N}` |
| `attribution_timestamp` | ISO-8601 | Timestamp of the originating event that caused this assessment (not the processing timestamp) |
| `historical_context` | list | Prior `(snapshot_month, config_version_id, retry_outcome)` tuples for longitudinal continuity |
| `prior_intervention_count` | integer | Total operator interventions recorded across all history |
| `prior_escalation_count` | integer | Total escalations in this student's history across all cycles |
| `historical_risk_trend` | enum | Trend derived from prior finalized snapshots: `IMPROVING`, `STABLE`, `DECLINING`, `CRITICAL`, `UNKNOWN` |

---

### 2.4 AI Context

AI insight state, staleness metadata, and confidence context. AI inputs are **advisory only** for retry priority adjustment; they cannot override governance retry limits, eligibility state, or hard governance rules (§7).

| Field | Type | Description |
|---|---|---|
| `ai_insight_state` | enum | Lifecycle state of the AI insight record (`AI_REVIEWED`, `AI_GENERATION_FAILED`, `AI_GENERATING`, `AI_PENDING`, `AI_ARCHIVED`, etc.) |
| `ai_insight_version` | integer | `version_number` of the AI insight record; used for staleness tracking |
| `ai_recommended_intervention` | enum | AI's recommended intervention pathway: `NONE`, `OUTREACH`, `MEETING`, `RESOURCE_DELIVERY`, `ESCALATE` |
| `ai_confidence_score` | float | Model-reported confidence (0.0–1.0); drives AI governance tier selection (Rule 5) |
| `ai_generated_at` | datetime | Timestamp of AI insight generation |
| `ai_stale_flag` | boolean | True if insight age exceeds `ai_insight_ttl_hours` from the ACTIVE config |
| `ai_ttl_hours` | integer | TTL from the ACTIVE config version; used for staleness determination |
| `ai_finalized_copy` | boolean | Whether the AI content is a snapshot-frozen physical copy (immutable; must not drive new retry priority decisions) |
| `ai_input_metrics_hash` | string | Hash of input metrics used to generate the insight; used for reproducibility verification |

---

### 2.5 Operational Context

Academic and platform signals supplementing retry advisement evaluation.

| Field | Type | Authority | Description |
|---|---|---|---|
| `outreach_state` | enum | `platform_supplementary` | Current state in the Outreach lifecycle domain (ELIGIBLE through CLOSED); see spec/03 §3 |
| `access_state` | enum | `sql_server_authoritative` | Current platform access status (ACTIVE, REVOKED, SUSPENDED) |
| `email` | string | `sql_server_authoritative` | Contact email (used for contact data gate; never in log output) |
| `phone_number` | string | `sql_server_authoritative` | Contact phone number (used for contact data gate; never in log output) |
| `engagement_signal_score` | float | `platform_supplementary` | Recent engagement responsiveness score (0.0–1.0) |
| `payment_balance` | decimal | `sql_server_authoritative` | Outstanding payment balance |
| `sql_server_sync_timestamp` | datetime | `sql_server_authoritative` | Most recent SQL Server sync cycle timestamp |

---

## 3. OUTPUT MODEL

---

The retry assessment produces a single **`RetryOrchestrationAssessment`** object per evaluation. This object is advisory: it does not execute actions, does not mutate state, and does not enforce governance boundaries. The outreach orchestration service consumes this assessment when preparing to dispatch a retry communication, using its retry scope and constraints to govern dispatch decisions.

---

### 3.1 RetryOrchestrationAssessment Schema

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "RETRY_ELIGIBLE | RETRY_DEFERRED | RETRY_EXHAUSTED | ESCALATION_CANDIDATE | REPLAY_RETRY_CANDIDATE | NONE",
  "retry_constraints": {
    "max_attempts_constraint": 0,
    "remaining_attempts": 0,
    "effective_retry_window_hours": 0,
    "execution_mode_constraint": "SHADOW | LIVE",
    "live_retry_permitted": false,
    "channel_exhaustion_state": "AVAILABLE | PARTIAL | EXHAUSTED",
    "ai_prioritization_applied": false
  },
  "governance_requirements": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "execution_mode": "SHADOW | LIVE",
    "idempotency_key": "string",
    "governance_preconditions_met": false,
    "blocking_governance_flags": []
  },
  "escalation_recommendation": {
    "escalation_recommended": false,
    "escalation_urgency": "LOW | MEDIUM | HIGH | CRITICAL | NONE",
    "escalation_reason_codes": [],
    "escalation_context": {}
  },
  "observability_metadata": {
    "correlation_id": "uuid",
    "causation_id": "uuid | null",
    "execution_type": "original | replay | regeneration",
    "assessment_version": "string",
    "rule_path_taken": [],
    "assessment_basis": "RULE_BASED | AI_ASSISTED | FALLBACK | HISTORICAL_REPLAY"
  },
  "attribution_metadata": {
    "origin_source": "system_automated | operator | scheduler",
    "origin_authority": "platform_supplementary",
    "attribution_timestamp": "ISO-8601",
    "actor_identity": "retry_policy_v1"
  },
  "replay_restrictions": {
    "is_replay": false,
    "replay_eligible": false,
    "live_eligible": false,
    "source_artifact_id": "string | null",
    "historical_config_version_id": "string | null",
    "fingerprint_comparison_outcome": "MATCH | DIVERGENT | UNKNOWN | null",
    "replay_safe": true
  },
  "config_version_reference": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "threshold_bindings": {
      "retry_window_hours": 0,
      "max_outreach_attempts": 0,
      "provider_failure_cooldown_extension_hours": 0,
      "provider_failure_retry_limit": 0,
      "consecutive_no_response_escalation_threshold": 0,
      "retry_window_mode": "ROLLING | FIXED",
      "ai_insight_ttl_hours": 0,
      "escalation_repeat_threshold": 0
    }
  },
  "cooldown_metadata": {
    "retry_window_hours": 0,
    "elapsed_hours_since_last_contact": 0.0,
    "remaining_hours_in_cooldown": 0.0,
    "cooldown_active": false,
    "provider_failure_extended": false,
    "provider_failure_extension_hours": 0,
    "effective_retry_window_hours": 0,
    "retry_window_mode": "ROLLING | FIXED"
  },
  "retry_priority": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
  "ai_context": {
    "ai_input_used": false,
    "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | UNAVAILABLE | IN_FLIGHT | FINALIZED_COPY",
    "ai_confidence_score": 0.0,
    "stale_flag": false,
    "fallback_applied": false,
    "priority_adjustment_applied": false,
    "ai_version_number": null
  },
  "reason_codes": [],
  "retry_blocked": false,
  "blocking_reason": null
}
```

---

### 3.2 Retry Scope Values

| Scope | Meaning | Downstream implication |
|---|---|---|
| `RETRY_ELIGIBLE` | Retry window has elapsed, attempt count is within maximum, contact data is present, and governance preconditions are met | Outreach orchestration service may proceed to dispatch retry; channel layer selects retry channel |
| `RETRY_DEFERRED` | Governance and attempt conditions are met, but the cooldown window has not yet elapsed since the last contact | No retry dispatch; orchestration service re-evaluates at next scheduled cycle or when cooldown expires |
| `RETRY_EXHAUSTED` | Max attempt count has been reached; no further retry advisement is produced | Decision engine produces `CLOSE_ORCHESTRATION` intent; escalation routing notified for human review |
| `ESCALATION_CANDIDATE` | Consecutive non-response, provider failure threshold, compliance hold, or critical risk signals mandate escalation routing instead of retry | Decision engine produces `ESCALATE_TO_OPERATOR`; retry dispatch suppressed |
| `REPLAY_RETRY_CANDIDATE` | Evaluation is in replay or regeneration context; historical retry state assessed; live retry dispatch prohibited | Assessment documents historical retry candidacy; no outbound side effects |
| `NONE` | No retry candidacy: terminal state, governance block, first-contact context, or contact data unavailable | No retry advisement produced; orchestration service takes no retry action |

---

### 3.3 Key Output Clarifications

* **Retry advisements are advisory.** The `RetryOrchestrationAssessment` is a recommendation to consuming services. The outreach orchestration service validates current student state and may reject the advisement if state has advanced since the assessment was produced.
* **The policy never writes to the database.** All persistence — idempotency key storage, audit log entries, retry records — is the responsibility of consuming services.
* **Channel selection is not in scope.** `RETRY_ELIGIBLE` scope does not specify which channel to use. The channel orchestration layer is responsible for channel selection, accounting for channel exhaustion state carried in `retry_constraints`.
* **Threshold bindings in `config_version_reference` are the historical record.** The specific values that governed this assessment are captured in the output and stored with the assessment record, enabling historical audit without re-querying the config registry.
* **`live_retry_permitted = false` is the default.** Until Phase 12 production governance certification, all retry assessments carry `live_retry_permitted = false` in `retry_constraints`, regardless of `retry_scope`. SHADOW mode suppression enforcement belongs to consuming services.

---

## 4. RETRY RULES (ORDERED)

---

Rules are evaluated in the order defined below. **Stop at the first terminal rule unless otherwise stated.** Each rule that fires contributes to `rule_path_taken` in `observability_metadata`.

Non-terminal rules (marked `CONTINUE`) populate assessment fields and do not stop evaluation. Terminal rules (marked `STOP`) produce the final assessment immediately.

---

### RULE 0 — GOVERNANCE PRECONDITION GATE

**This rule is mandatory. No subsequent rules execute if this rule blocks. This rule fires before any other rule, including business rules.**

BLOCK assessment production IF any of the following are true:

* `config_version_id` is null (config resolution failed; see §5.1)
* `config_version_status` is not `ACTIVE` and `execution_type = original` (SUPERSEDED versions are only valid in replay mode)
* `execution_mode` is not one of `SHADOW` or `LIVE`
* `execution_mode = LIVE` and Phase 12 production governance certification has not been confirmed (see `execution/build_phases.md` Phase 12)
* `correlation_id` is null
* `attribution_context` is incomplete (missing any of: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`)
* `idempotency_key` already exists in the idempotency store for this `(student_id, checkpoint_type, cycle_timestamp, retry_attempt_number)` — duplicate retry orchestration detected
* `execution_type ∈ {replay, regeneration}` AND `replay_context` is absent or incomplete
* `retry_attempt_number > contact_attempt_count - 1` — internal retry lineage inconsistency (retry count exceeds contact count; governance defect)

THEN:

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "NONE",
  "retry_blocked": true,
  "blocking_reason": "GOVERNANCE_PRECONDITION_FAILED",
  "governance_requirements": {
    "governance_preconditions_met": false
  },
  "reason_codes": [
    "CONFIG_UNRESOLVED | CONFIG_VERSION_NOT_ACTIVE | EXECUTION_MODE_INVALID | LIVE_CERTIFICATION_REQUIRED | CORRELATION_ID_MISSING | ATTRIBUTION_INCOMPLETE | IDEMPOTENCY_DUPLICATE | REPLAY_CONTEXT_MISSING | RETRY_LINEAGE_INCONSISTENT"
  ]
}
```

STOP.

> **Governance integrity note:** The governance precondition gate ensures that orchestration integrity precedes all business rules. A blocked assessment at Rule 0 is a definitive governance failure, not a data problem to work around. No fallback, no retry of the assessment, no default behavior. The assessment is invalid and must not be consumed.

---

### RULE 1 — TERMINAL STATE CHECK

IF `outreach_state = CLOSED`:

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "NONE",
  "reason_codes": ["OUTREACH_CLOSED_TERMINAL"]
}
```

STOP.

> CLOSED is a terminal state in the Outreach lifecycle domain (spec/03 §4). A student in CLOSED state cannot re-enter retry candidacy. A new outreach cycle must be initiated through the state management service, not through retry re-evaluation.

---

### RULE 2 — COMPLIANCE HOLD GATE

IF `compliance_hold_flag = true`:

```json
{
  "retry_orchestration_eligible": true,
  "retry_scope": "ESCALATION_CANDIDATE",
  "retry_priority": "CRITICAL",
  "escalation_recommendation": {
    "escalation_recommended": true,
    "escalation_urgency": "CRITICAL",
    "escalation_reason_codes": ["COMPLIANCE_HOLD_ACTIVE"],
    "escalation_context": {
      "note": "Student snapshot is under COMPLIANCE_HOLD. All automated retry orchestration is suspended until the hold is resolved via the Compliance Governance Pathway."
    }
  },
  "reason_codes": ["COMPLIANCE_HOLD_ACTIVE"],
  "governance_requirements": {
    "blocking_governance_flags": ["COMPLIANCE_HOLD_ACTIVE"]
  }
}
```

STOP.

> A compliance hold suspends all automated retry orchestration. The student is exclusively eligible for escalation candidacy — routing to the Compliance Governance Pathway for human operator review (spec/03 Domain 6). No retry dispatch may proceed until the hold is resolved.

---

### RULE 3 — CONFIG-BOUND THRESHOLD RESOLUTION

**This rule is non-terminal. It must execute before any threshold-dependent rule (Rules 7, 8, 9, 11, 12, 13).**

Resolve all threshold bindings from `config_rule_set` (the ACTIVE or historical config version's `rule_set_snapshot`):

| Threshold variable | Config key | Used in rule |
|---|---|---|
| `RETRY_WINDOW_HOURS` | `outreach_retry_window_hours` | Rule 11 |
| `MAX_OUTREACH_ATTEMPTS` | `outreach_max_attempts` | Rule 7 |
| `PROVIDER_FAILURE_COOLDOWN_EXTENSION_HOURS` | `provider_failure_cooldown_extension_hours` | Rule 9, 11 |
| `PROVIDER_FAILURE_RETRY_LIMIT` | `provider_failure_retry_limit` | Rule 9 |
| `CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD` | `consecutive_no_response_escalation_threshold` | Rule 8 |
| `RETRY_WINDOW_MODE` | `retry_window_behavior` | Rule 11 (ROLLING or FIXED) |
| `AI_INSIGHT_TTL_HOURS` | `ai_insight_ttl_hours` | Rule 5 |
| `ESCALATION_REPEAT_THRESHOLD` | `prior_escalation_repeat_threshold` | Rule 12 |

All resolved bindings are written to `config_version_reference.threshold_bindings` in the assessment output. This is the historical record of which thresholds governed this assessment.

IF any threshold is missing from `config_rule_set`:

* Substitute `UNKNOWN_V0` for that threshold in internal evaluation
* Log `CONFIG_THRESHOLD_MISSING` at `warn` level with the specific missing key name
* Add `CONFIG_THRESHOLD_MISSING_{KEY_NAME}` to `reason_codes`
* Exclude rules that depend solely on the missing threshold from evaluation
* Continue with all rules that do not depend on missing thresholds

**No hardcoded threshold values are permitted as substitutes.** Missing config thresholds degrade coverage; they never justify fallback to compiled-in constants (AP-R9).

CONTINUE.

---

### RULE 4 — CONTACT DATA GATE

IF `email` is null AND `phone_number` is null:

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "NONE",
  "reason_codes": ["NO_CONTACT_INFO"]
}
```

STOP.

> No contact information means no retry orchestration is possible for any channel. The student cannot be a retry candidate. The Core Decision Engine will produce `CLOSE_ORCHESTRATION` or `RECOMMEND_INTERVENTION` based on broader context.

---

### RULE 5 — AI GOVERNANCE TIER ASSESSMENT

**This rule is non-terminal. It determines the `ai_governance_tier` that governs Rule 13 behavior.**

| Condition | AI Governance Tier |
|---|---|
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score ≥ 0.70` | `CONFIDENT` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score < 0.70` | `ADVISORY` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = true` | `STALE` |
| `ai_insight_state ∈ {AI_GENERATING, AI_PENDING}` | `IN_FLIGHT` — triggers Rule 5A |
| `ai_insight_state ∈ {AI_GENERATION_FAILED, null}` | `UNAVAILABLE` |
| `ai_finalized_copy = true` | `FINALIZED_COPY` — immutable; no priority adjustment permitted; used only in report regeneration context (§7.4) |

Staleness is determined by: `current_timestamp - ai_generated_at > AI_INSIGHT_TTL_HOURS` (from config-bound threshold resolution, Rule 3).

If `AI_INSIGHT_TTL_HOURS` was not resolved (missing from config), `ai_stale_flag` cannot be determined. Set `ai_governance_tier = UNAVAILABLE` and log `AI_TTL_NOT_CONFIGURED`.

CONTINUE.

---

### RULE 5A — PENDING AI GATE (conditional exit from Rule 5)

IF `ai_governance_tier = IN_FLIGHT` AND `execution_type = original`:

```json
{
  "retry_orchestration_eligible": true,
  "retry_scope": "RETRY_DEFERRED",
  "retry_priority": "UNKNOWN",
  "ai_context": {
    "ai_governance_tier": "IN_FLIGHT"
  },
  "reason_codes": ["AI_INSIGHT_IN_FLIGHT_DEFER_PENDING"]
}
```

STOP.

> In replay mode, do not defer on IN_FLIGHT AI. Use STALE tier instead — historical replay must not wait for a new AI insight to be generated.

---

### RULE 6 — FIRST CONTACT GATE

IF `contact_attempt_count = 0`:

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "NONE",
  "retry_blocked": true,
  "blocking_reason": "NOT_A_RETRY_CONTEXT",
  "reason_codes": ["NO_PRIOR_CONTACT_NOT_RETRY"]
}
```

STOP.

> Retry policy advisement is valid only when prior contact has been made. A student with `contact_attempt_count = 0` is in a first-outreach context, not a retry context. The outreach orchestration service must consult the eligibility assessment and Core Decision Engine for `INITIATE_OUTREACH`, not this directive.

---

### RULE 7 — MAX ATTEMPTS EXHAUSTION GATE

IF `contact_attempt_count ≥ MAX_OUTREACH_ATTEMPTS`:

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "RETRY_EXHAUSTED",
  "retry_priority": "MEDIUM",
  "retry_constraints": {
    "max_attempts_constraint": "{MAX_OUTREACH_ATTEMPTS}",
    "remaining_attempts": 0
  },
  "escalation_recommendation": {
    "escalation_recommended": true,
    "escalation_urgency": "MEDIUM",
    "escalation_reason_codes": ["MAX_ATTEMPTS_EXHAUSTED_REVIEW_REQUIRED"],
    "escalation_context": {
      "note": "All config-bound retry attempts have been exhausted. Human review is required before this case can be closed or escalated."
    }
  },
  "reason_codes": ["MAX_ATTEMPTS_EXHAUSTED"]
}
```

STOP.

> Max attempts exhausted is a terminal candidacy condition within the current outreach cycle. The Core Decision Engine will produce `CLOSE_ORCHESTRATION` based on this signal. The escalation recommendation ensures that a human operator reviews the student before the case is closed.

---

### RULE 8 — CONSECUTIVE NON-RESPONSE ESCALATION GATE

IF `consecutive_no_response_count ≥ CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD`:

```json
{
  "retry_orchestration_eligible": true,
  "retry_scope": "ESCALATION_CANDIDATE",
  "retry_priority": "HIGH",
  "escalation_recommendation": {
    "escalation_recommended": true,
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["CONSECUTIVE_NO_RESPONSE_THRESHOLD_EXCEEDED"],
    "escalation_context": {
      "consecutive_no_response_count": "{consecutive_no_response_count}",
      "threshold": "{CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD}"
    }
  },
  "reason_codes": ["CONSECUTIVE_NO_RESPONSE_ESCALATION"]
}
```

STOP.

> Repeated no-response across sequential attempts indicates automated retry is unlikely to succeed. Escalation to an operator for manual review or intervention changes the approach.

---

### RULE 9 — PROVIDER FAILURE ASSESSMENT

**This rule is non-terminal. It evaluates provider failure lineage and adjusts retry constraints accordingly.**

IF `provider_failure_count > 0` within the current retry cycle:

Extend the effective retry window: `effective_retry_window_hours = RETRY_WINDOW_HOURS + PROVIDER_FAILURE_COOLDOWN_EXTENSION_HOURS`.

Set `cooldown_metadata.provider_failure_extended = true`.
Set `cooldown_metadata.provider_failure_extension_hours = PROVIDER_FAILURE_COOLDOWN_EXTENSION_HOURS`.
Add `PROVIDER_FAILURE_COOLDOWN_EXTENDED` to `reason_codes`.

IF `provider_failure_count ≥ PROVIDER_FAILURE_RETRY_LIMIT`:

```json
{
  "retry_orchestration_eligible": true,
  "retry_scope": "ESCALATION_CANDIDATE",
  "retry_priority": "HIGH",
  "escalation_recommendation": {
    "escalation_recommended": true,
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["PROVIDER_FAILURE_LIMIT_EXCEEDED"],
    "escalation_context": {
      "provider_failure_count": "{provider_failure_count}",
      "provider_failure_retry_limit": "{PROVIDER_FAILURE_RETRY_LIMIT}"
    }
  },
  "reason_codes": ["PROVIDER_FAILURE_ESCALATION"]
}
```

STOP.

IF `provider_failure_count < PROVIDER_FAILURE_RETRY_LIMIT`:

Adjust `retry_constraints.effective_retry_window_hours` to reflect the extension.
Log `PROVIDER_FAILURE_COOLDOWN_EXTENDED` at `warn` level.

CONTINUE.

> Provider failures require extended cooldown to avoid hammering a recovering provider. The cooldown extension is config-governed, not hardcoded. If provider failures exceed the retry limit, escalation ensures a human can investigate whether the provider issue is systemic.

---

### RULE 10 — REPLAY ELIGIBILITY GATE

**This rule fires only when `execution_type ∈ {replay, regeneration}`. It is non-terminal when replay preconditions pass; terminal when they fail.**

Replay preconditions — ALL must hold:

1. `config_version_id` matches the historical config reference from `replay_context` (not the current ACTIVE version)
2. `fingerprint_context` is populated with the historical snapshot's stored fingerprint components
3. `execution_mode = SHADOW` — replay execution must never be `LIVE`
4. `replay_context.source_artifact_id` is present and resolvable

IF all preconditions pass:

Set `retry_scope = REPLAY_RETRY_CANDIDATE`.
Set `replay_restrictions.replay_eligible = true`.
Set `replay_restrictions.live_eligible = false`.
Set `replay_restrictions.replay_safe = true`.
Set `retry_constraints.live_retry_permitted = false`.
Compute `fingerprint_comparison_outcome` by comparing historical fingerprint components against current system state.
Record `REPLAY_RETRY_CANDIDATE` in `reason_codes`.

CONTINUE. (Replay assessment continues through Rules 12 and 13 using historical context, but the `retry_scope` remains `REPLAY_RETRY_CANDIDATE` regardless of cooldown or priority assessment results — no scope upgrade to `RETRY_ELIGIBLE` is permitted in replay.)

IF any precondition fails:

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "NONE",
  "retry_blocked": true,
  "blocking_reason": "REPLAY_PRECONDITION_VIOLATED",
  "replay_restrictions": {
    "replay_eligible": false,
    "live_eligible": false,
    "replay_safe": false
  },
  "reason_codes": [
    "REPLAY_CONFIG_MISMATCH | REPLAY_LIVE_MODE_BLOCKED | REPLAY_FINGERPRINT_MISSING | REPLAY_SOURCE_ARTIFACT_MISSING"
  ]
}
```

STOP.

---

### RULE 11 — RETRY COOLDOWN ASSESSMENT

**This rule determines whether the retry window has elapsed. It is the primary gate for `RETRY_ELIGIBLE` vs `RETRY_DEFERRED` scope.**

Calculate elapsed hours: `elapsed_hours = current_timestamp - last_contact_timestamp`.

Determine effective retry window:
* If Rule 9 applied a provider failure extension: `effective_window = RETRY_WINDOW_HOURS + PROVIDER_FAILURE_COOLDOWN_EXTENSION_HOURS`
* Otherwise: `effective_window = RETRY_WINDOW_HOURS`

Apply retry window mode from `RETRY_WINDOW_MODE`:
* `ROLLING`: window resets from the last contact timestamp (most common; prevents overlapping retry cycles)
* `FIXED`: window computes from the cycle start timestamp (anchors to the outreach cycle epoch rather than the most recent attempt)

Write to `cooldown_metadata`:
* `retry_window_hours = RETRY_WINDOW_HOURS`
* `elapsed_hours_since_last_contact = elapsed_hours`
* `effective_retry_window_hours = effective_window`
* `remaining_hours_in_cooldown = max(0, effective_window - elapsed_hours)`
* `cooldown_active = elapsed_hours < effective_window`
* `retry_window_mode = RETRY_WINDOW_MODE`

IF `elapsed_hours < effective_window` (cooldown active):

```json
{
  "retry_orchestration_eligible": false,
  "retry_scope": "RETRY_DEFERRED",
  "retry_priority": "UNKNOWN",
  "reason_codes": ["RETRY_COOLDOWN_ACTIVE"]
}
```

STOP.

IF `elapsed_hours ≥ effective_window` (cooldown elapsed):

Set `retry_scope = RETRY_ELIGIBLE` (unless already set to `REPLAY_RETRY_CANDIDATE` by Rule 10).
Set `retry_constraints.remaining_attempts = MAX_OUTREACH_ATTEMPTS - contact_attempt_count`.
Record `RETRY_COOLDOWN_ELAPSED` in `reason_codes`.

CONTINUE.

---

### RULE 12 — MULTI-FACTOR RETRY PRIORITY ASSESSMENT

**This rule is non-terminal. It produces `retry_priority` used by Rule 13 and carried in the advisory output.**

Evaluate retry urgency factors against config-bound thresholds (resolved in Rule 3):

| Factor | Condition | Risk contribution |
|---|---|---|
| Attempt proximity to maximum | `remaining_attempts = 1` | `+HIGH` |
| Attempt proximity to maximum | `remaining_attempts = 2` | `+MEDIUM` |
| Attempt proximity to maximum | `remaining_attempts > 2` | `+LOW` |
| Historical escalation recurrence | `prior_escalation_count ≥ ESCALATION_REPEAT_THRESHOLD` | `+HIGH` |
| Historical trend — critical | `historical_risk_trend = CRITICAL` | `+HIGH` |
| Historical trend — declining | `historical_risk_trend = DECLINING` | `+MEDIUM` |
| Provider failure history | `provider_failure_count > 0` in current cycle | `+MEDIUM` |
| Low engagement signal | `engagement_signal_score < 0.1` | `+HIGH` |
| Low engagement signal (moderate) | `engagement_signal_score ≥ 0.1` AND `< 0.3` | `+MEDIUM` |

Aggregate priority:
* 2+ HIGH contributions → `retry_priority = CRITICAL`
* 1 HIGH + 1+ MEDIUM → `retry_priority = HIGH`
* 0 HIGH + 1+ MEDIUM → `retry_priority = MEDIUM`
* All LOW or no contributions → `retry_priority = LOW`

If one or more thresholds are missing from config (Rule 3 issued `CONFIG_THRESHOLD_MISSING`), exclude the associated factor from scoring and add `PARTIAL_PRIORITY_ASSESSMENT` to `reason_codes`.

CONTINUE.

---

### RULE 13 — AI-ASSISTED RETRY PRIORITIZATION

**This rule is non-terminal. It may adjust `retry_priority` upward based on AI governance tier and recommendation. It cannot override governance blocks or add retry eligibility.**

IF `ai_governance_tier = CONFIDENT` AND `ai_recommended_intervention = ESCALATE`:

Upgrade `retry_priority` to `CRITICAL` (regardless of prior Rule 12 assessment).
Set `ai_context.priority_adjustment_applied = true`.
Add `AI_ESCALATION_SIGNAL_CONFIDENT` to `reason_codes`.

IF `ai_governance_tier = CONFIDENT` AND `ai_recommended_intervention ∈ {MEETING, OUTREACH, RESOURCE_DELIVERY}`:

Upgrade `retry_priority` by one level (LOW → MEDIUM, MEDIUM → HIGH; CRITICAL remains CRITICAL).
Set `ai_context.priority_adjustment_applied = true`.
Add `AI_INTERVENTION_SIGNAL_CONFIDENT` to `reason_codes`.

IF `ai_governance_tier = ADVISORY` AND `ai_recommended_intervention = ESCALATE`:

Upgrade `retry_priority` by one level only (not to CRITICAL unless already HIGH).
Set `ai_context.priority_adjustment_applied = true`.
Add `AI_ESCALATION_SIGNAL_ADVISORY` to `reason_codes`.

IF `ai_governance_tier = STALE`:

Do NOT adjust `retry_priority` based on AI recommendation.
Record `STALE_AI_PRIORITIZATION_SKIPPED` in `reason_codes`.
If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`.

IF `ai_governance_tier = UNAVAILABLE`:

Set `ai_context.fallback_applied = true`.
Record `AI_UNAVAILABLE_FALLBACK_APPLIED` in `reason_codes`.
No priority adjustment. Rule 12's rule-based assessment governs.

IF `ai_governance_tier = FINALIZED_COPY`:

No priority adjustment from this source. Immutable snapshot copies are not inputs for new retry priority decisions.
Record `AI_FINALIZED_COPY_NOT_APPLIED` in `reason_codes`.

CONTINUE.

---

### RULE 14 — DEFAULT RETRY ADVISORY OUTPUT

**Terminal. Produces the final `RetryOrchestrationAssessment` from the accumulated state of prior rules.**

At this point, `retry_scope`, `retry_priority`, `ai_context`, `cooldown_metadata`, `escalation_recommendation`, `reason_codes`, and all governance/attribution fields have been populated by prior non-terminal rules.

Set `retry_orchestration_eligible`:
* `true` if `retry_scope ∈ {RETRY_ELIGIBLE, ESCALATION_CANDIDATE, REPLAY_RETRY_CANDIDATE}`
* `false` if `retry_scope ∈ {RETRY_DEFERRED, RETRY_EXHAUSTED, NONE}`

Set `governance_requirements.governance_preconditions_met = true` (Rule 0 passed).
Set `retry_constraints.live_retry_permitted = false` until Phase 12 production governance certification (see `execution/build_phases.md` Phase 12).

Set `assessment_basis`:
* `AI_ASSISTED` if `ai_context.priority_adjustment_applied = true`
* `FALLBACK` if `ai_context.fallback_applied = true`
* `HISTORICAL_REPLAY` if `execution_type ∈ {replay, regeneration}`
* `RULE_BASED` otherwise

Emit the completed `RetryOrchestrationAssessment`.

STOP.

---

## 5. CONFIG VERSION GOVERNANCE

---

### 5.1 Config Resolution Protocol

Before Rule 0 executes, the retry assessment service MUST:

1. Query the Config Version Registry for the **currently ACTIVE version** (`status = ACTIVE`)
2. Extract the full `rule_set_snapshot` from the ACTIVE version record
3. Bind the `config_version_id` to the assessment context
4. Validate that exactly one `ACTIVE` version exists; if zero or multiple exist, emit `GOVERNANCE_PRECONDITION_FAILED` and stop

In replay mode (`execution_type ∈ {replay, regeneration}`), the resolution protocol changes:

1. Extract the `config_registry_version` component from `replay_context.fingerprint`
2. Query the Config Version Registry for that specific historical version (may be `SUPERSEDED` or `ARCHIVED`)
3. If unavailable, block replay — `REPLAY_CONFIG_UNAVAILABLE`; do NOT substitute the current ACTIVE version

Config resolution failure is never silently ignored. An assessment produced without a resolved config version is invalid.

---

### 5.2 Threshold Binding

All threshold comparisons (Rules 7, 8, 9, 11, 12, 13) MUST use values extracted from the resolved config version's `rule_set_snapshot`. No hardcoded threshold values exist in this directive or in any implementation code that executes this retry architecture (AP-R9).

The same student with the same retry history may produce different retry assessments under different config versions. This is expected behavior (FAD-3, spec/01 §12). Config-version governance is what makes historical reproducibility possible.

---

### 5.3 Config Lineage in Output

Every assessment carries `config_version_id` in `governance_requirements` AND a full `config_version_reference.threshold_bindings` record capturing the specific values resolved from that version. This enables:

* Historical audit of which thresholds governed any retry decision, without re-querying the config registry
* Replay verification: the stored threshold bindings in the assessment record can be compared against the historical config version's `rule_set_snapshot` to confirm reproducibility
* Retry timing calibration analysis: downstream observability systems can correlate configured retry windows with outreach outcome rates across config versions

---

### 5.4 Prospective-Only Semantics (FAD-3 Enforcement)

Activating a new config version does NOT:

* Retroactively change historical retry assessment outputs
* Recalculate retry windows for historical outreach records
* Alter finalized snapshot cohort classifications
* Trigger reprocessing of any prior student data

Retry assessments under the new config version take effect at the next scheduled evaluation cycle. Prior assessments, and the records they produced, are permanently attributed to the config version in effect when they were made.

---

## 6. REPLAY & REGENERATION SEMANTICS

---

### 6.1 Replay Retry Behavior

A replay retry evaluation determines whether a student was a valid retry candidate at a specific historical point in time. It does not produce any new retry actions.

Replay retry rules:

* The historical config version governs all threshold evaluations (§5.1)
* `execution_mode` is forced to `SHADOW`; replay assessments are never `LIVE`
* `retry_scope` is always `REPLAY_RETRY_CANDIDATE` for a valid replay — never `RETRY_ELIGIBLE`
* AI signals for replay use the `ai_finalized_copy` from the source snapshot — no fresh AI analysis is triggered
* `fingerprint_comparison_outcome` is computed and recorded in `replay_restrictions`
* Replay idempotency keys are NOT stored in the operational idempotency store — replay evaluations are read-only with respect to state
* Cooldown window calculation in replay uses historical timestamps from `retry_history` inputs — not `current_timestamp`

---

### 6.2 Regeneration Retry Behavior

Report regeneration context requires historical retry re-evaluation to reconstruct the retry candidacy signals that informed a prior reporting cycle. In this context:

* The decision engine invokes the retry policy in `execution_type = regeneration` mode
* Historical config version is used; no current ACTIVE version thresholds apply
* AI content is sourced exclusively from snapshot physical copies — no live `ai_insights` queries
* If stored fingerprint components differ from current system state, `fingerprint_comparison_outcome = DIVERGENT`; this does not block regeneration but annotates the output with `POTENTIALLY_DIVERGENT`
* No new retry history records, state transitions, or governance-sensitive writes may result from a regeneration assessment
* `retry_scope` remains `REPLAY_RETRY_CANDIDATE`; regeneration cannot produce `RETRY_ELIGIBLE` scope

---

### 6.3 SHADOW Execution Semantics

SHADOW mode is the default for all assessments until Phase 12 production governance certification. In SHADOW mode:

* All rules evaluate normally; the assessment is produced with full governance context
* `retry_constraints.live_retry_permitted = false` regardless of `retry_scope`
* The consuming outreach orchestration service is responsible for enforcing outbound dispatch suppression based on `execution_mode = SHADOW`
* Governance audit log entries ARE written in SHADOW mode; a SHADOW retry assessment is a real platform event with real audit requirements
* The retry policy carries no responsibility for SHADOW enforcement; it carries the mode flag and trusts consuming services to respect it

---

### 6.4 Replay Observability Isolation

Every replay assessment must be distinguishable from the original assessment in all log and telemetry output:

* `execution_type: replay` in `observability_metadata`
* `source_artifact_id` referencing the original snapshot or scheduler job in `replay_restrictions`
* `fingerprint_comparison_outcome` in `replay_restrictions`
* `correlation_id` is freshly generated for the replay job; `causation_id` is set to the original job's `correlation_id`
* Replay assessments must not share idempotency keys with original assessments

---

## 7. AI GOVERNANCE

---

### 7.1 AI Governance Principle for Retry

AI insight output is **advisory for retry prioritization only**. It cannot:

* Override config-bound retry window thresholds
* Override max attempt limits
* Grant retry eligibility to a student whose attempts are exhausted or whose governance is blocked
* Produce `LIVE` retry eligibility unilaterally
* Modify or invalidate historical retry assessments produced under prior config versions
* Override governance blocks (Rules 0, 2, 7, 8)
* Trigger live retry escalation when `ai_governance_tier = STALE`

AI insight output CAN:

* Adjust `retry_priority` upward when governance tier is `CONFIDENT` or `ADVISORY` (Rule 13)
* Contribute escalation candidacy context when AI recommends `ESCALATE` at CONFIDENT tier
* Set `assessment_basis = AI_ASSISTED` in observability metadata when priority adjustment is applied

---

### 7.2 AI Governance Tier Behavior in Retry Context

| Tier | Retry behavior | Priority adjustment |
|---|---|---|
| `CONFIDENT` (≥ 0.70 confidence, fresh) | AI signals applied to Rule 13 priority adjustment; escalation signals honored | Full adjustment: ESCALATE → CRITICAL; others → +1 level |
| `ADVISORY` (< 0.70 confidence, fresh) | AI signals applied at reduced weight; escalation raises one level only | Partial adjustment: ESCALATE → +1 level; others → no adjustment |
| `STALE` (beyond TTL or failed with prior) | No priority adjustment; stale flag recorded; assessment continues without AI | No adjustment; `STALE_AI_PRIORITIZATION_SKIPPED` in reason_codes |
| `UNAVAILABLE` (no prior AI_REVIEWED) | Pure rule-based assessment; `fallback_applied = true` | No adjustment; `AI_UNAVAILABLE_FALLBACK_APPLIED` in reason_codes |
| `IN_FLIGHT` | Assessment deferred to `RETRY_DEFERRED` scope (Rule 5A) | Not applicable; IN_FLIGHT triggers defer |
| `FINALIZED_COPY` | Immutable snapshot content; not used for new retry priority decisions | No adjustment; `AI_FINALIZED_COPY_NOT_APPLIED` in reason_codes |

---

### 7.3 Stale AI Protection in LIVE Mode

IF `execution_mode = LIVE` AND `ai_governance_tier = STALE`:

* Do NOT adjust `retry_priority` based on AI recommendation
* `retry_constraints.live_retry_permitted` remains governed solely by rule-based assessment
* If rule-based assessment independently produces `RETRY_ELIGIBLE` scope, it remains valid; AI staleness does not retract rule-based eligibility
* Add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`
* The assessment output must explicitly flag the staleness condition and the AI generation timestamp so downstream operators are aware

---

### 7.4 AI Snapshot Isolation (FAD-1 Enforcement)

When `ai_finalized_copy = true`:

* The assessment MUST NOT request, apply, or reference live `ai_insights` records for this student in the same evaluation context
* `ai_governance_tier` is set to `FINALIZED_COPY` regardless of the live `ai_insights` record state
* No priority adjustment is applied from the frozen copy — finalized snapshot copies are for report regeneration, not new retry priority decisions

---

### 7.5 Deterministic Fallback

When AI input is `UNAVAILABLE` or `STALE`, the assessment MUST produce a deterministic rule-based output using only operational signals and config-bound thresholds. The fallback path is not a degraded mode — it is a fully specified assessment path that satisfies the same correctness and reproducibility requirements as the AI-assisted path.

`ai_context.fallback_applied = true` in the output signals to downstream services that this assessment operated without current AI assistance.

---

## 8. OBSERVABILITY & ATTRIBUTION

---

### 8.1 Required Telemetry per Assessment

Every retry evaluation MUST emit a structured log entry (JSON, to stdout per spec/06 §2) containing:

| Log field | Source |
|---|---|
| `timestamp` | ISO-8601 at assessment start |
| `level` | `info` (normal), `warn` (fallback/stale/provider failure), `error` (governance gate failure) |
| `service` | `retry_policy` |
| `event` | `retry_orchestration_produced` or `governance_precondition_failed` |
| `correlation_id` | From `governance_context.correlation_id` |
| `causation_id` | From `governance_context.causation_id` (null if root event) |
| `student_id_opaque` | Opaque hash of the student ID — never the raw SQL Server `user_id` |
| `execution_type` | `original`, `replay`, or `regeneration` |
| `execution_mode` | `SHADOW` or `LIVE` |
| `config_version_id` | ID of the resolved config version |
| `retry_scope` | The scope value produced |
| `retry_orchestration_eligible` | Boolean |
| `retry_priority` | Priority value produced |
| `ai_governance_tier` | Tier from Rule 5 |
| `cooldown_active` | From `cooldown_metadata` |
| `elapsed_hours_since_last_contact` | From `cooldown_metadata` |
| `effective_retry_window_hours` | From `cooldown_metadata` |
| `rule_path_taken` | Array of rule IDs that fired |
| `assessment_basis` | `RULE_BASED`, `AI_ASSISTED`, `FALLBACK`, or `HISTORICAL_REPLAY` |
| `escalation_recommended` | From `escalation_recommendation` |
| `duration_ms` | Assessment duration |
| `outcome` | `success`, `blocked`, `fallback` |
| `error_class` | Populated only on `error` level |

---

### 8.2 Correlation ID Propagation

The `correlation_id` assigned at the triggering scheduler run or operator action MUST propagate without modification through:

* The assessment context inputs
* The `RetryOrchestrationAssessment` output
* Every downstream service call that consumes the assessment (outreach orchestration service, escalation routing service)
* Every database write and audit log entry produced by consuming services

The causal chain from scheduler run → retry assessment → outreach dispatch → state transition → audit log must be reconstructable from a single `correlation_id` query.

---

### 8.3 Attribution Propagation

The attribution fields set in the assessment context (`origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`) MUST propagate to every downstream record created as a result of consuming this assessment. The retry policy sets attribution at the `system_automated` / `platform_supplementary` tier; consuming services append their own actor identity but do not overwrite the assessment's attribution context.

Attribution fields are immutable once set. Consuming services MUST NOT rewrite, strip, or reinterpret attribution fields from the assessment output.

---

### 8.4 Retry Trace Metadata

The `rule_path_taken` field in `observability_metadata` provides a complete trace of which rules fired during this assessment, in order. This trace enables:

* Historical explainability of why a specific retry was permitted, deferred, or escalated
* Retry timing calibration analysis: which rules fire most frequently, and which rule combinations correlate with successful subsequent contact
* Debugging: when an assessment produces an unexpected scope, the rule path identifies the exact decision branch

Rule path entries use canonical rule identifiers from §4 (e.g., `["RULE_0", "RULE_1", "RULE_3", "RULE_4", "RULE_5", "RULE_9", "RULE_11", "RULE_12", "RULE_13", "RULE_14"]`).

---

### 8.5 PII Redaction Rules

The following fields MUST NEVER appear in log output, telemetry, or observability metadata:

* Raw `user_id` (SQL Server primary key) → substitute `student_id_opaque` (opaque hash)
* `email` → `***@***`
* `phone_number` → `***`
* Student name → `[REDACTED]`
* AI-generated narrative text → NEVER in logs; stored only in database
* Raw payment amounts with student context → aggregate only; no per-student payment values in logs

PII redaction applies equally to SHADOW and LIVE mode, to original and replay executions, and to all log levels including debug.

---

## 9. FAILURE & SAFETY SEMANTICS

---

### 9.1 Missing Data Behavior

| Missing field | Governance classification | Response |
|---|---|---|
| `config_version_id` | Governance-critical | Block assessment at Rule 0; `GOVERNANCE_PRECONDITION_FAILED`; do not default to any version |
| `correlation_id` | Governance-critical | Block assessment at Rule 0 |
| `attribution_context` incomplete | Governance-critical | Block assessment at Rule 0 |
| `last_contact_timestamp` | Governance-critical (for retry timing) | Block assessment; `MISSING_RETRY_TIMESTAMP`; cooldown cannot be computed without an anchor |
| `contact_attempt_count` null | Operational fallback | Treat as 0 → Rule 6 gate fires; log `CONTACT_ATTEMPT_COUNT_UNKNOWN` |
| `ai_insight_state` null | AI fallback | Set `ai_governance_tier = UNAVAILABLE`; fallback applies |
| Historical inputs absent | Historical fallback | Continue without historical enrichment; set `historical_risk_trend = UNKNOWN`; log warning |
| `channel_exhaustion_state` null | Operational fallback | Treat as `AVAILABLE`; log `CHANNEL_EXHAUSTION_UNKNOWN`; add `MISSING_CHANNEL_STATE` to reason_codes |
| `provider_failure_count` null | Operational fallback | Treat as 0; no provider failure extension applied; log `PROVIDER_FAILURE_COUNT_UNKNOWN` |

Missing data from governance-critical sources blocks evaluation. Missing data from supplementary or historical sources triggers fallback behavior. Unblocked assessments with missing supplementary data must include `MISSING_DATA_FALLBACK_APPLIED` in `reason_codes`.

---

### 9.2 Stale Retry Lineage

IF `last_contact_timestamp` is older than the current outreach cycle epoch (i.e., the timestamp predates the current outreach cycle start):

* Emit `STALE_RETRY_LINEAGE` warning at `warn` level
* Proceed with cooldown calculation using the available timestamp
* Add `STALE_RETRY_LINEAGE_WARNING` to `reason_codes`
* Alert operational telemetry so the outreach history service can be verified

---

### 9.3 Invalid Config Resolution

IF the Config Version Registry returns zero or multiple ACTIVE versions:

* Block assessment unconditionally at Rule 0
* Log `CONFIG_REGISTRY_INCONSISTENT` at `error` level with `error_class: ContractViolation`
* Emit escalation alert to the operator notification service
* Do NOT default to hardcoded threshold values
* Retry config resolution is permitted; if 3 consecutive resolution failures occur, escalate as a production incident

---

### 9.4 Duplicate Retry Orchestration Detection

IF `idempotency_key` already exists in the idempotency store for `(student_id, checkpoint_type, cycle_timestamp, retry_attempt_number)`:

* Block assessment at Rule 0
* `IDEMPOTENCY_DUPLICATE` in `reason_codes`
* Do NOT produce a new assessment; the prior assessment for this cycle key is the canonical record
* Log at `warn` level (duplicates are expected in retry scenarios caused by scheduler at-least-once delivery; they are not errors)

---

### 9.5 Replay Conflict Behavior

| Replay failure scenario | Behavior |
|---|---|
| Historical config version unavailable | Block replay at Rule 10; `REPLAY_CONFIG_UNAVAILABLE`; do not substitute current ACTIVE version |
| Fingerprint components incomplete | Proceed with available components; log `REPLAY_FINGERPRINT_PARTIAL`; set `fingerprint_comparison_outcome = UNKNOWN` |
| Replay context indicates `execution_mode = LIVE` | Override to `SHADOW`; log `REPLAY_MODE_OVERRIDE`; never allow live retry eligibility from replay context |
| Historical retry state unavailable | Block replay at Rule 10; `REPLAY_STATE_UNAVAILABLE`; do not reconstruct from current state |
| Fingerprint divergence detected | Continue; set `fingerprint_comparison_outcome = DIVERGENT`; annotate output with `POTENTIALLY_DIVERGENT`; do not block |

---

### 9.6 Stale AI Behavior

IF AI governance tier is `STALE`:

* No priority adjustment (Rule 13)
* Add `STALE_AI_PRIORITIZATION_SKIPPED` to `reason_codes`
* If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED`
* Include `ai_generated_at` in `ai_context` output so downstream operators know the age of the last AI insight
* Rule-based assessment governs exclusively; fallback path is fully deterministic

---

### 9.7 Provider Outage Handling

IF `provider_failure_count ≥ PROVIDER_FAILURE_RETRY_LIMIT` (Rule 9 trigger):

* ESCALATION_CANDIDATE scope is produced (see Rule 9)
* The escalation context includes provider failure count and limit for operator visibility
* The outreach orchestration service MUST NOT retry against a provider where the failure limit is exceeded without operator acknowledgment or a provider circuit breaker confirmation

IF a systemic provider outage is detected (all available channels are reporting `DELIVERY_FAILED`):

* `channel_exhaustion_state = EXHAUSTED` propagates into `retry_constraints`
* ESCALATION_CANDIDATE scope is appropriate even if provider failure count is below limit
* Log `SYSTEMIC_PROVIDER_OUTAGE_SUSPECTED` at `warn` level

---

### 9.8 Cooldown Corruption

IF `cooldown_metadata.elapsed_hours_since_last_contact` resolves to a negative value (future `last_contact_timestamp`):

* Log `COOLDOWN_TIMESTAMP_FUTURE` at `error` level with `error_class: DataIntegrityViolation`
* Block assessment; emit `COOLDOWN_CORRUPT`
* Do NOT produce a retry assessment with a corrupt cooldown anchor; the risk of over-contact from a clock skew issue is too high

IF `elapsed_hours_since_last_contact` resolves to an unreasonably large value (e.g., > 8760 hours — more than one year):

* Log `COOLDOWN_TIMESTAMP_STALE` at `warn` level
* Continue; set `cooldown_active = false`; add `STALE_CONTACT_TIMESTAMP` to `reason_codes`

---

## 10. ARCHITECTURE PRESERVATION RULES

---

The following prohibitions are absolute. No implementation code, configuration change, or emergency workaround may violate them. A violation is a production defect requiring immediate rollback.

| Rule | Prohibition |
|---|---|
| `AP-R1` | The retry policy MUST NOT directly dispatch outbound retry communications. It produces advisements; it does not initiate contact. |
| `AP-R2` | The retry policy MUST NOT mutate outreach state, retry lineage, or any lifecycle domain state. All state writes belong to consuming services. |
| `AP-R3` | The retry policy MUST NOT modify the Config Version Registry. Config lifecycle transitions are operator-initiated governance workflows. |
| `AP-R4` | The retry policy MUST NOT overwrite, modify, or supplement an immutable snapshot's stored content. FINALIZED snapshots are immutable (FAD-1, spec/03 INVARIANT-1). |
| `AP-R5` | The retry policy MUST NOT overwrite historical retry assessment outputs. Each assessment is append-only. A re-evaluation produces a NEW assessment record with its own idempotency key and attribution. |
| `AP-R6` | The retry policy MUST NOT corrupt replay retry semantics. A replay assessment must produce `REPLAY_RETRY_CANDIDATE` scope only; it must not produce `RETRY_ELIGIBLE` scope that could drive outbound retry dispatch. |
| `AP-R7` | The retry policy MUST NOT bypass the audit trail. Every assessment — including blocked assessments from Rule 0 — must produce a telemetry log entry. |
| `AP-R8` | The retry policy MUST NOT use platform-supplementary delivery failure signals to override SQL Server-authoritative eligibility state for access or compliance fields (INVARIANT-6, spec/03 §40). |
| `AP-R9` | The retry policy MUST NOT use hardcoded retry timing values. All threshold comparisons must use values extracted from the resolved config version's `rule_set_snapshot`. |
| `AP-R10` | The retry policy MUST NOT log raw student PII. `user_id`, name, email, phone, and AI narrative content are prohibited in all log output. Only opaque student identifiers are permitted. |
| `AP-R11` | The retry policy MUST NOT produce a `RETRY_ELIGIBLE` scope during replay or regeneration execution. `execution_type ∈ {replay, regeneration}` unconditionally constrains `live_retry_permitted = false` and `retry_scope = REPLAY_RETRY_CANDIDATE`. |
| `AP-R12` | The retry policy MUST NOT reuse idempotency keys across retry evaluation cycles. Each `(student_id, checkpoint_type, cycle_timestamp, retry_attempt_number)` is unique per cycle-attempt pair. |
| `AP-R13` | The retry policy MUST NOT evaluate retry rules if the GOVERNANCE PRECONDITION GATE (Rule 0) has not passed. No rule evaluation, no output production, and no telemetry beyond the BLOCKED log entry. |
| `AP-R14` | The retry policy MUST NOT produce a retry advisement that elevates `retry_orchestration_eligible = true` for a compliance-hold student to any scope other than `ESCALATION_CANDIDATE`. Automated retry orchestration is suspended until the hold resolves. |
| `AP-R15` | The retry policy MUST NOT override or reinterpret attribution fields from inputs. Attribution is set at origin and propagated unchanged through all outputs. |

---

## 11. SCOPE BEHAVIOR

---

### 11.1 Across All Scopes (Non-Negotiable)

Regardless of scope tier, the following are mandatory and cannot be reduced:

* GOVERNANCE PRECONDITION GATE (Rule 0) evaluated before any retry rule
* Config V1 seed as the ACTIVE version at platform initialization (governance invariant: exactly one ACTIVE version)
* No hardcoded retry timing values; all threshold comparisons from `config_rule_set`
* SHADOW execution mode as default; `live_retry_permitted = false` until Phase 12 certification
* Idempotency key checked before producing any assessment
* Attribution fields carried on every assessment output
* PII redaction rules in all log output
* AP-R1 through AP-R15 prohibitions enforced
* INVARIANT-1 through INVARIANT-7 from spec/03 §40 respected

---

### 11.2 MVP Scope

MVP scope MAY reduce:

| Reduced behavior | What is acceptable |
|---|---|
| AI prioritization | `ai_governance_tier` always `UNAVAILABLE`; pure rule-based assessment; Rules 5, 5A, 13 are no-ops; `fallback_applied = true` on every output |
| Provider failure assessment | `provider_failure_count` treated as 0; no cooldown extension applied; Rule 9 short-circuits |
| Consecutive non-response escalation | `consecutive_no_response_count` treated as 0; Rule 8 short-circuits |
| Historical inputs | `historical_risk_trend = UNKNOWN`; prior context absent |
| Channel exhaustion state | `channel_exhaustion_state` treated as `AVAILABLE`; no channel-layer signal consumed |

MVP scope MAY NOT:

* Skip config resolution (Rule 3 and the config resolution protocol in §5.1 are mandatory)
* Hardcode any retry timing value
* Violate attribution or lineage guarantees on assessment outputs
* Produce `RETRY_ELIGIBLE` scope in replay or regeneration context
* Skip idempotency key validation
* Produce assessments without the governance precondition gate (Rule 0)

---

### 11.3 STANDARD Scope

STANDARD scope enables over MVP:

* AI governance tiers `CONFIDENT` and `ADVISORY` active; Rule 13 priority adjustments applied
* Historical risk trend inputs active; `DECLINING` and `CRITICAL` contribute to Rule 12 scoring
* Consecutive non-response escalation gate active (Rule 8)
* Provider failure assessment active; cooldown extensions applied (Rule 9)
* Channel exhaustion state consumed from channel availability service
* `STALE` AI detection active using `AI_INSIGHT_TTL_HOURS` config threshold

STANDARD scope MAY NOT produce live retry dispatch. `live_retry_permitted` remains `false` until Phase 12.

---

### 11.4 PRODUCTION Scope

PRODUCTION scope enables over STANDARD:

* `execution_mode = LIVE` permitted following Phase 12 production governance certification
* `live_retry_permitted = true` once Phase 12 certification is confirmed in the governance registry
* Full provider failure lineage and circuit breaker state integration
* Full channel exhaustion state from production channel availability service
* Full engagement signal integration from production GHL message cache
* All Rule 13 AI governance tiers active including ADVISORY-tier escalation adjustments

PRODUCTION scope MUST NOT:

* Bypass Phase 12 certification to set `live_retry_permitted = true`
* Permit AI-only escalation from STALE governance tier in LIVE mode
* Produce LIVE retry scope during replay or regeneration execution

---

## 12. ACCEPTANCE CRITERIA

---

### AC-R1 — Deterministic Retry Evaluation

**Given** the same inputs and the same ACTIVE config version
**When** the retry policy is evaluated twice
**Then** the resulting `RetryOrchestrationAssessment` is identical in all fields

---

### AC-R2 — Replay Scope Ceiling

**Given** `execution_type = replay` or `execution_type = regeneration`
**When** the retry policy is evaluated with any contact history
**Then** `retry_scope = REPLAY_RETRY_CANDIDATE` and `live_retry_permitted = false` regardless of cooldown state or contact count

---

### AC-R3 — Config Version Reproducibility

**Given** an assessment produced under config version V1
**When** the assessment record is retrieved 30 days later
**Then** `config_version_reference.threshold_bindings` captures the exact threshold values that governed the assessment; no re-query of the config registry is required to verify the decision

---

### AC-R4 — Attribution Continuity

**Given** an assessment with complete `attribution_context` inputs
**When** the assessment is produced
**Then** `attribution_metadata.origin_source`, `attribution_metadata.origin_authority`, `attribution_metadata.actor_identity`, and `attribution_metadata.attribution_timestamp` in the output match the inputs without modification

---

### AC-R5 — Immutable Historical Protection

**Given** a replay assessment is produced for a student's historical retry cycle
**When** the replay assessment is stored
**Then** the original assessment record for that cycle is not modified, overwritten, or supplemented; the replay produces a new record with its own idempotency key

---

### AC-R6 — Stale AI Protection

**Given** `ai_governance_tier = STALE`
**When** the retry policy evaluates Rule 13
**Then** `ai_context.priority_adjustment_applied = false` and `retry_priority` reflects only Rule 12's rule-based assessment; `STALE_AI_PRIORITIZATION_SKIPPED` is in `reason_codes`

---

### AC-R7 — SHADOW Isolation

**Given** `execution_mode = SHADOW`
**When** the retry policy produces `retry_scope = RETRY_ELIGIBLE`
**Then** `retry_constraints.live_retry_permitted = false` regardless of scope

---

### AC-R8 — Governance Precondition Blocking

**Given** `correlation_id` is null
**When** the retry policy evaluates Rule 0
**Then** `retry_blocked = true`, `blocking_reason = "GOVERNANCE_PRECONDITION_FAILED"`, no subsequent rules fire, and a telemetry log entry is emitted for the blocked assessment

---

### AC-R9 — Provider Failure Cooldown Extension

**Given** `provider_failure_count > 0` AND `provider_failure_count < PROVIDER_FAILURE_RETRY_LIMIT`
**When** the retry policy evaluates Rule 9
**Then** `cooldown_metadata.effective_retry_window_hours = RETRY_WINDOW_HOURS + PROVIDER_FAILURE_COOLDOWN_EXTENSION_HOURS` and `cooldown_metadata.provider_failure_extended = true`

---

### AC-R10 — Consecutive Non-Response Escalation

**Given** `consecutive_no_response_count ≥ CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD`
**When** the retry policy evaluates Rule 8
**Then** `retry_scope = ESCALATION_CANDIDATE` and `escalation_recommendation.escalation_recommended = true` with urgency `HIGH`

---

### AC-R11 — Max Attempts Terminal

**Given** `contact_attempt_count ≥ MAX_OUTREACH_ATTEMPTS`
**When** the retry policy evaluates Rule 7
**Then** `retry_scope = RETRY_EXHAUSTED`, `retry_orchestration_eligible = false`, and `retry_constraints.remaining_attempts = 0`

---

### AC-R12 — First-Contact Gate

**Given** `contact_attempt_count = 0`
**When** the retry policy evaluates Rule 6
**Then** `retry_blocked = true`, `blocking_reason = "NOT_A_RETRY_CONTEXT"`, and `reason_codes` includes `NO_PRIOR_CONTACT_NOT_RETRY`

---

## 13. DOWNSTREAM IMPLICATIONS

---

### 13.1 Outreach Orchestration Service

The outreach orchestration service is the primary consumer of `RetryOrchestrationAssessment`. Required behavior:

* Must validate that `retry_scope = RETRY_ELIGIBLE` before dispatching any retry communication
* Must reject the advisement if the student's outreach state has advanced since the assessment was produced (point-in-time check)
* Must suppress outbound dispatch when `live_retry_permitted = false`
* Must route to the escalation service when `escalation_recommendation.escalation_recommended = true`
* Must store the assessment record (append-only) with its full governance context before dispatching

---

### 13.2 Channel Orchestration

The retry policy does not select retry channels. The channel orchestration layer receives `retry_constraints.channel_exhaustion_state` from the assessment and uses it to filter available channels. Sequencing (which channel to try next within a retry attempt) belongs entirely to the channel layer.

---

### 13.3 Escalation Workflows

`ESCALATION_CANDIDATE` scope and `escalation_recommendation.escalation_urgency` are the authoritative handoff signals to the escalation routing service. The escalation service must:

* Read `escalation_recommendation.escalation_reason_codes` to classify the escalation type
* Inherit `correlation_id` and `attribution_metadata` from the assessment for lineage continuity
* Not re-evaluate retry eligibility; the advisory is the definitive input for escalation routing

---

### 13.4 Observability

Key retry metrics for monitoring:

* `retry_scope` distribution: RETRY_ELIGIBLE / RETRY_DEFERRED / RETRY_EXHAUSTED / ESCALATION_CANDIDATE ratios signal whether retry timing config is correctly calibrated
* `cooldown_metadata.elapsed_hours_since_last_contact` distribution: reveals whether retry windows are realistic for student engagement patterns
* `provider_failure_count` aggregate: surface provider reliability trends before they reach escalation threshold
* `consecutive_no_response_count` aggregate: distinguish between retry timing issues and fundamental non-engagement patterns

---

### 13.5 APIs

The `RetryOrchestrationAssessment` schema (§3.1) is the contract exposed to consuming services. Breaking changes to this schema require a coordinated PR that updates all consumers in the same diff. The `config_version_reference.threshold_bindings` sub-schema must remain backward-compatible with historical assessment records; new threshold fields may be added but existing fields may not be removed without a deprecation path.

---

## 14. UNRESOLVED ARCHITECTURAL CONCERNS

---

The following concerns are documented for architectural resolution before production certification. They do not block directive authoring but must be resolved before PRODUCTION scope is enabled.

| ID | Concern | Impact |
|---|---|---|
| `UR-1` | `provider_failure_cooldown_extension_hours` and `provider_failure_retry_limit` must be confirmed present in Config V1 `rule_set_snapshot`; if absent, Rule 9 cannot execute in STANDARD scope | Config V1 seed may need to be updated before Phase 11 testing |
| `UR-2` | `consecutive_no_response_escalation_threshold` must be confirmed present in Config V1 `rule_set_snapshot`; if absent, Rule 8 cannot execute in STANDARD scope | Same as UR-1; audit of V1 seed against all 8 threshold variables in Rule 3 required |
| `UR-3` | `retry_window_behavior` (ROLLING vs FIXED) — ROLLING resets cooldown from last contact timestamp; FIXED computes from cycle epoch; the distinction substantially affects re-evaluation timing for students who receive partial-delivery retries; this architecture decision must be formalized before production | Incorrect mode could produce systematic over-contact (FIXED in a slow-cycle context) or systematic under-contact (ROLLING with a long window) |
| `UR-4` | Channel exhaustion state authority — the `channel_exhaustion_state` input must come from an authoritative channel availability service; the source, update frequency, and staleness threshold for this signal are unspecified in current inputs; if the signal is stale, AVAILABLE may be incorrectly assumed when channels are actually exhausted | Risk: retry dispatch against an exhausted channel; channel layer must handle gracefully |
| `UR-5` | Retry policy invocation boundary — whether this policy is evaluated by the Core Decision Engine as part of producing the `RETRY_OUTREACH` intent (allowing the engine to prevent a retry intent from being produced) vs. by the outreach orchestration service after receiving a `RETRY_OUTREACH` intent (allowing the service to suppress execution) is architecturally unresolved; the two models have different governance implications for who is responsible for intent-blocking vs. execution-blocking | If evaluated at orchestration service level, a `RETRY_OUTREACH` intent may be produced by the decision engine for a student that the retry policy would block; this requires the orchestration service to always validate the advisory before dispatch |

---

## REFERENCES

---

Canonical inputs used to produce this directive:

* `directives/core_decision_engine.md` — orchestration intent model, RETRY_OUTREACH intent semantics, AI governance, replay semantics, attribution model
* `directives/outreach_eligibility_rules.md` — eligibility scope architecture, RULE 0 pattern, AP-E governance rules, scope behavior tiers
* `spec/01_requirements.md` — system purpose, operational domains, cohort definitions
* `spec/03_state_transition_rules.md` — Outreach lifecycle domain, CLOSED terminal state, INVARIANT-1 through INVARIANT-7
* `spec/04_idempotency_concurrency.md` — idempotency key design, at-least-once delivery, dedup table pattern
* `spec/06_observability_operations.md` — structured logging contract, governance telemetry vs operational telemetry, correlation ID propagation
* `spec/09_security_privacy.md` — PII redaction requirements, opaque student identifier model
* `execution/build_phases.md` — Phase 12 LIVE certification requirements

---

## END OF FILE
