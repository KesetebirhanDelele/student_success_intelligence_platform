# directives/escalation_rules.md

---

## LAYER 3 — DIRECTIVES (ESCALATION ORCHESTRATION ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `directives/core_decision_engine.md`, `directives/outreach_eligibility_rules.md`, and `directives/outreach_retry_policy.md`. The previous version described a simplistic operational escalation logic model (`escalation_required: true/false`, hardcoded thresholds, direct notify/flag actions, scope-gated MAX_ATTEMPTS tables) that is architecturally incompatible with the governance-aware orchestration-intelligence platform defined in spec/01 through spec/09. Escalation is no longer a dispatch trigger. It is orchestration escalation advisement.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **Escalation Orchestration Architecture** defines the escalation advisement and escalation candidacy determination layer of the Student Success Intelligence Platform. It specifies:

* How a student enters escalation candidacy within any orchestration evaluation context
* What governance preconditions must hold before escalation evaluation may proceed
* How config-version-governed thresholds determine escalation triggers, severity, and candidacy class
* How retry exhaustion lineage, inactivity severity, payment risk, and academic risk signals combine into escalation candidacy
* How provider failure state triggers escalation advisory conditions
* How replay, regeneration, and SHADOW execution semantics constrain escalation advisory outputs
* How AI-governance tiers influence escalation severity without overriding rule-based escalation eligibility
* What attribution, observability, and lineage metadata must accompany every escalation advisory output

This directive is the authoritative specification for **orchestration escalation advisement and escalation candidacy determination**. It is consumed by:

* The Core Decision Engine (`directives/core_decision_engine.md`) when it produces `ESCALATE_TO_OPERATOR` intents
* The outreach orchestration service when retry exhaustion or delivery failure signals require escalation routing
* The retry policy (`directives/outreach_retry_policy.md`) when its escalation candidacy signals need severity classification
* The escalation routing service when it requires a classified `EscalationOrchestrationAssessment` to route to the correct operator tier

---

### 1.2 Escalation Assessment Categories

Escalation governance produces multiple distinct advisory categories, not a single binary escalation trigger. The following categories are defined:

| Category | Definition | Governing rule(s) |
|---|---|---|
| **Governance escalation candidacy** | Governance preconditions are met, no blocking terminal state, and the student is not already in terminal escalation state | Rules 0, 1, 2 |
| **Config-bound escalation eligibility** | Escalation thresholds resolved from the ACTIVE config version permit evaluation to proceed | Rule 3 |
| **Risk-driven escalation candidacy** | Academic, operational, inactivity, or payment risk signals meet config-bound thresholds for escalation advisement | Rules 6, 7, 8, 9, 10, 12 |
| **Operational escalation candidacy** | Provider failure, retry exhaustion, or channel collapse conditions require escalation routing instead of continued automated retry | Rules 6, 11 |
| **Compliance-driven escalation candidacy** | A compliance hold, access revocation, or governance invariant violation mandates operator escalation | Rule 13 |
| **AI-assisted escalation severity** | AI insight freshness, governance tier, and confidence metadata may elevate escalation severity above the rule-based baseline; AI cannot create escalation candidacy where rules find none | Rules 5, 14 |
| **Replay escalation candidacy** | The historical escalation decision context, fingerprint, and config lineage permit replay assessment; replay isolation semantics are enforceable; escalation advisories in replay are SHADOW-only | Rule 4, §6 |

All seven categories are evaluated when evaluation proceeds past Rule 0. The resulting `EscalationOrchestrationAssessment` output carries the advisory outcome across all applicable categories.

---

### 1.3 What Escalation Is NOT

To prevent scope creep and architectural boundary violations, this directive explicitly defines what escalation assessment does NOT do:

* **Does not directly assign a case to a human.** Escalation advisement determines candidacy and severity. Human assignment routing, mentor selection, and operator-queue placement belong to the escalation routing service. This directive is advisory to that service.
* **Does not create tasks, tickets, or Basecamp todos.** Task creation is a side effect of the escalation routing service consuming this advisory. The advisory specifies what should happen; the routing service decides whether and how to execute.
* **Does not dispatch Slack messages, emails, or notifications directly.** All outbound notifications — operator alerts, mentor notifications, management escalations — are executed by the notification dispatch service consuming the escalation routing service's output.
* **Does not mutate student lifecycle state directly.** State machine transitions (`CONTACTED → INTERVENTION_REQUIRED`, `ANALYZED → INTERVENTION_REQUIRED`) are the responsibility of the state management service. This directive produces advisement; the state management service writes the transition.
* **Does not execute compliance actions.** Compliance holds, deletions, and audit trail entries belong exclusively to the Compliance Governance Pathway. This directive flags a student for compliance-driven escalation candidacy; the Compliance Governance Pathway executes.
* **Does not override governance invariants (INVARIANT-1 through INVARIANT-7 in spec/03 §40).** Escalation assessment operates within those invariants. It does not adjudicate them.
* **Does not write to any database.** All database writes — idempotency key storage, audit log entries, escalation history records, state transition records — are the responsibility of consuming services.
* **Does not produce LIVE escalation execution in replay or regeneration mode.** Escalation advisories produced in replay context are governance-annotated SHADOW outputs only. They simulate historical escalation conditions without triggering any outbound operator action.

---

## 2. INPUT MODEL

---

The escalation assessment context is **lineage-aware and governance-aware**. Every input carries metadata establishing its authority class and origin. Inputs from SQL Server (`origin_authority = sql_server_authoritative`) govern eligibility decisions for academic and access signals. Platform-supplementary inputs provide operational escalation context but do not override SQL Server-authoritative state (INVARIANT-6, spec/03 §40).

---

### 2.1 Student Risk Context

Retry exhaustion lineage, academic risk signals, inactivity history, payment risk, and prior intervention history.

| Field | Type | Authority | Description |
|---|---|---|---|
| `outreach_state` | enum | `platform_supplementary` | Current state in the Outreach lifecycle domain (ELIGIBLE through CLOSED); see spec/03 §3 |
| `contact_attempt_count` | integer | `platform_supplementary` | Total contact attempts made in the current outreach cycle |
| `consecutive_no_response_count` | integer | `platform_supplementary` | Sequential NO_RESPONSE outcomes without any CONNECTED outcome in the current cycle |
| `last_contact_timestamp` | datetime | `platform_supplementary` | Most recent outreach event timestamp |
| `last_contact_outcome` | enum | `platform_supplementary` | Outcome of most recent contact: `CONNECTED`, `NO_ANSWER`, `VOICEMAIL`, `DELIVERY_FAILED`, `PROVIDER_ERROR`, `OPTED_OUT` |
| `retry_exhausted` | boolean | `platform_supplementary` | True if `contact_attempt_count ≥ MAX_OUTREACH_ATTEMPTS` per config-bound threshold |
| `channel_exhaustion_state` | enum | `platform_supplementary` | `AVAILABLE`, `PARTIAL`, `EXHAUSTED`; from the channel orchestration service |
| `hws_behind` | integer | `sql_server_authoritative` | Assignments behind schedule (SQL Server-authoritative) |
| `avg_eff_rating` | float | `sql_server_authoritative` | Average effort rating 0.0–5.0 (SQL Server-authoritative) |
| `last_activity_days` | integer | `sql_server_authoritative` | Days since last recorded activity (SQL Server-authoritative) |
| `payment_balance` | decimal | `sql_server_authoritative` | Outstanding payment balance in USD (SQL Server-authoritative) |
| `access_state` | enum | `sql_server_authoritative` | Current platform access status: `ACTIVE`, `REVOKED`, `SUSPENDED` (SQL Server-authoritative) |
| `prior_escalation_count` | integer | `platform_supplementary` | Total escalation events recorded for this student in prior cycles |
| `prior_intervention_count` | integer | `platform_supplementary` | Total operator interventions recorded for this student across all history |
| `historical_escalation_patterns` | list | `platform_supplementary` | Recurrence patterns of escalation triggers across prior cycles |
| `last_escalation_timestamp` | datetime | `platform_supplementary` | Most recent escalation event timestamp; used for cooldown enforcement |
| `last_escalation_reason_codes` | list | `platform_supplementary` | Reason codes from the most recent escalation event; used for recurrence detection |
| `mentor_intervention_history` | list | `platform_supplementary` | Record of prior mentor assignment attempts, outcomes, and timestamps |
| `sql_server_sync_timestamp` | datetime | `sql_server_authoritative` | Timestamp of the most recent SQL Server sync that updated academic fields |

---

### 2.2 Governance Context

Governance context is mandatory for every escalation evaluation. Assessments produced without full governance context are invalid.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ID of the ACTIVE config version at evaluation time (must be resolved before rule evaluation begins) |
| `config_version_status` | enum | Status of the resolved config version: `ACTIVE` (normal) or `SUPERSEDED` (valid in replay mode only) |
| `config_rule_set` | object | Extracted threshold values from the ACTIVE (or historical) config version's `rule_set_snapshot` |
| `execution_mode` | enum | Platform execution mode: `SHADOW` (default; no outbound effects) or `LIVE` (requires Phase 12 certification) |
| `execution_type` | enum | `original`, `replay`, or `regeneration`; drives replay-safety rules (§6) |
| `correlation_id` | uuid | UUID v4 propagated from the triggering scheduler run or operator action |
| `causation_id` | uuid | UUID v4 of the upstream event that caused this escalation evaluation (enables multi-hop lineage; null for root events) |
| `attribution_context` | object | Full attribution metadata: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp` |
| `fingerprint_context` | object | Snapshot Reproducibility Fingerprint components at evaluation time; used for replay safety and divergence detection |
| `idempotency_key` | string | Escalation-level idempotency key `(student_id, checkpoint_type, cycle_timestamp, escalation_trigger)` to prevent duplicate escalation advisory production |
| `compliance_hold_flag` | boolean | True if the student's snapshot is currently under `COMPLIANCE_HOLD` |
| `replay_context` | object | Present only when `execution_type ∈ {replay, regeneration}`; contains historical fingerprint, source artifact ID, and config lineage |

---

### 2.3 Attribution Context

| Field | Type | Description |
|---|---|---|
| `origin_source` | string | Triggering source: `system_automated`, `operator`, `scheduler`, `compliance_pathway` |
| `origin_authority` | string | Authority class: `sql_server_authoritative` or `platform_supplementary` |
| `actor_identity` | string | Identity of the triggering actor (scheduler job ID, operator user ID, or `escalation_assessment_v{N}`) |
| `attribution_timestamp` | datetime | ISO-8601 timestamp at which the triggering event was recorded |
| `upstream_correlation_id` | uuid | Correlation ID of the upstream eligibility or retry assessment that triggered this escalation evaluation |
| `upstream_intent` | string | The `orchestration_intent` from the Core Decision Engine that led to this escalation evaluation; may be null for compliance-path escalations |

---

### 2.4 AI Context

AI inputs are **advisory only**. They cannot override SQL Server-authoritative risk state, config-bound escalation thresholds, or governance blocks.

| Field | Type | Description |
|---|---|---|
| `ai_insight_state` | enum | Current lifecycle state of the AI insight: `AI_REVIEWED`, `AI_GENERATING`, `AI_PENDING`, `AI_GENERATION_FAILED`, `AI_ARCHIVED`, null |
| `ai_recommended_intervention` | enum | AI's recommended intervention: `NONE`, `OUTREACH`, `MEETING`, `RESOURCE_DELIVERY`, `ESCALATE` |
| `ai_sentiment` | string | Sentiment classification from AI insight: `positive`, `neutral`, `negative`, `critical` |
| `ai_confidence_score` | float | Model-reported confidence (0.0–1.0) |
| `ai_generated_at` | datetime | Timestamp of AI insight generation |
| `ai_stale_flag` | boolean | True if the insight age exceeds `ai_insight_ttl_hours` from the ACTIVE config |
| `ai_governance_tier` | enum | Resolved in Rule 5: `CONFIDENT`, `ADVISORY`, `STALE`, `IN_FLIGHT`, `UNAVAILABLE`, `FINALIZED_COPY` |
| `ai_finalized_copy` | boolean | True if the AI content is a snapshot-frozen physical copy; immutable; must not influence new escalation decisions |
| `ai_ttl_hours` | integer | TTL from the resolved config version; used for staleness assessment |
| `ai_input_metrics_hash` | string | Hash of the input metrics used to generate this insight; used for replay reproducibility |

---

### 2.5 Operational Context

| Field | Type | Description |
|---|---|---|
| `provider_failure_count` | integer | Count of provider-level delivery failures in the current outreach cycle |
| `provider_failure_breakdown` | object | Per-channel provider failure counts: `{call: N, sms: N, email: N}` |
| `automation_degradation_state` | enum | `HEALTHY`, `DEGRADED`, `SUSPENDED`; reflects orchestration infrastructure health |
| `escalation_cooldown_active` | boolean | True if the student is within the escalation cooldown window for the current trigger type |
| `escalation_cooldown_expires_at` | datetime | When the current escalation cooldown expires; null if no active cooldown |
| `orchestration_health_state` | enum | `HEALTHY`, `DEGRADED`, `OUTAGE`; from the orchestration health monitor |
| `last_provider_outage_timestamp` | datetime | Most recent provider-level outage timestamp; used for replay-safe provider attribution |
| `circuit_breaker_state` | enum | Circuit breaker state for the active outreach provider: `CLOSED`, `HALF_OPEN`, `OPEN` |

---

## 3. OUTPUT MODEL

---

Escalation evaluation produces a single `EscalationOrchestrationAssessment` per evaluation. The assessment is advisory: it does not execute actions, does not mutate state, and does not enforce governance boundaries. Downstream orchestration services and the escalation routing service consume the assessment and are responsible for execution, audit trail creation, and governance enforcement.

---

### 3.1 EscalationOrchestrationAssessment Schema

```json
{
  "escalation_candidate": true,
  "escalation_type": "NONE | RETRY_EXHAUSTION | CONSECUTIVE_NO_RESPONSE | PAYMENT_RISK | INACTIVITY | ACADEMIC_RISK | PRIOR_ESCALATION_RECURRENCE | PROVIDER_FAILURE | COMPLIANCE_HOLD | ACCESS_REVOKED | AI_CONFIDENCE | MULTI_FACTOR",
  "escalation_severity": "NONE | LOW | MEDIUM | HIGH | CRITICAL",
  "escalation_constraints": {
    "live_escalation_permitted": false,
    "execution_mode_constraint": "SHADOW | LIVE",
    "replay_escalation_ceiling": "SHADOW_ADVISORY_ONLY"
  },
  "replay_restrictions": {
    "is_replay": false,
    "replay_escalation_scope": "REPLAY_ESCALATION_CANDIDATE | null",
    "live_escalation_suppressed": true,
    "source_artifact_id": "string | null",
    "historical_config_version_id": "string | null",
    "fingerprint_comparison_outcome": "MATCH | DIVERGENT | UNKNOWN | null"
  },
  "governance_requirements": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "execution_mode": "SHADOW | LIVE",
    "idempotency_key": "string",
    "governance_preconditions_met": true,
    "blocking_governance_flags": []
  },
  "observability_metadata": {
    "correlation_id": "uuid",
    "causation_id": "uuid | null",
    "execution_type": "original | replay | regeneration",
    "service": "escalation_assessment",
    "rule_path_taken": ["RULE_N", "RULE_M"],
    "assessment_basis": "RULE_BASED | AI_ASSISTED | FALLBACK | HISTORICAL_REPLAY",
    "duration_ms": 0
  },
  "attribution_metadata": {
    "origin_source": "system_automated",
    "origin_authority": "platform_supplementary",
    "actor_identity": "escalation_assessment_v{N}",
    "attribution_timestamp": "ISO-8601"
  },
  "escalation_lineage_metadata": {
    "prior_escalation_count": 0,
    "prior_escalation_reason_codes": [],
    "last_escalation_timestamp": "ISO-8601 | null",
    "escalation_recurrence_detected": false,
    "cooldown_active": false,
    "cooldown_expires_at": "ISO-8601 | null"
  },
  "config_version_reference": {
    "config_version_id": "string",
    "threshold_bindings": {}
  },
  "ai_context": {
    "ai_input_used": false,
    "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | UNAVAILABLE | IN_FLIGHT | FINALIZED_COPY",
    "ai_confidence_score": 0.0,
    "ai_sentiment": "string | null",
    "stale_flag": false,
    "fallback_applied": false,
    "severity_adjustment_applied": false,
    "ai_version_number": null
  },
  "reason_codes": ["string"],
  "escalation_blocked": false,
  "blocking_reason": null
}
```

---

### 3.2 Escalation Type Values

| Type | Meaning | Primary rule |
|---|---|---|
| `NONE` | No escalation conditions met in this evaluation cycle | Rule 16 |
| `RETRY_EXHAUSTION` | All config-bound retry attempts exhausted; human review required before case closure | Rule 6 |
| `CONSECUTIVE_NO_RESPONSE` | Config-bound consecutive non-response threshold exceeded | Rule 7 |
| `PAYMENT_RISK` | Outstanding payment balance exceeds config-bound payment risk thresholds | Rule 8 |
| `INACTIVITY` | Days of inactivity exceed config-bound high-risk inactivity threshold | Rule 9 |
| `ACADEMIC_RISK` | Homework delinquency and/or effort rating signals exceed high-risk thresholds | Rule 10 |
| `PRIOR_ESCALATION_RECURRENCE` | Number of prior escalations in current enrollment exceeds config-bound repeat threshold | Rule 12 |
| `PROVIDER_FAILURE` | Provider failure count exceeds config-bound limit; automated retry is unreliable | Rule 11 |
| `COMPLIANCE_HOLD` | Student snapshot is under active COMPLIANCE_HOLD | Rule 13 |
| `ACCESS_REVOKED` | SQL Server-authoritative access state is REVOKED | Rule 13 |
| `AI_CONFIDENCE` | AI sentiment or intervention recommendation at CONFIDENT tier recommends ESCALATE | Rule 14 |
| `MULTI_FACTOR` | Multiple risk factors combine to produce CRITICAL severity | Rule 15 |

---

### 3.3 Output Clarifications

* **Assessments are advisory.** The `escalation_candidate` flag is a recommendation to the consuming escalation routing service. The routing service validates current state and executes operator routing; the assessment does not.
* **The assessment never writes to the database.** All database writes — idempotency key storage, escalation history records, operator assignment records, audit entries — are the responsibility of consuming services.
* **The assessment carries full governance context.** Every downstream service that consumes the assessment receives the full `governance_requirements`, `attribution_metadata`, `config_version_reference`, and `observability_metadata` needed to execute with governance fidelity, without re-querying the assessment service.
* **Replay assessments are advisory simulations.** `escalation_candidate = true` in a replay context means "this student would have been an escalation candidate under historical conditions." It does not authorize outbound operator notification or state transition.

---

## 4. ESCALATION RULES (ORDERED)

---

Rules are evaluated in the order defined below. **Stop at the first terminal rule unless otherwise stated.** Each rule that fires contributes to `rule_path_taken` in `observability_metadata`.

Non-terminal rules (marked `CONTINUE`) accumulate escalation signals and contribute to Rule 15 severity assessment. Terminal rules (marked `STOP`) produce the final assessment immediately.

---

### RULE 0 — GOVERNANCE PRECONDITION GATE

**This rule is mandatory. No subsequent rules execute if this rule blocks.**

BLOCK escalation evaluation IF:

* `config_version_id` is null (config resolution failed; see §5.1)
* `execution_mode` is not one of `SHADOW`, `LIVE`
* `correlation_id` is null
* `attribution_context` is incomplete (any required attribution field absent)
* `idempotency_key` already exists in the dedup store for `(student_id, checkpoint_type, cycle_timestamp, escalation_trigger)`
* `execution_type ∉ {original, replay, regeneration}`

THEN:

```json
{
  "escalation_candidate": false,
  "escalation_type": "NONE",
  "escalation_severity": "NONE",
  "escalation_blocked": true,
  "blocking_reason": "GOVERNANCE_PRECONDITION_FAILED",
  "reason_codes": ["CONFIG_UNRESOLVED | EXECUTION_MODE_INVALID | CORRELATION_ID_MISSING | ATTRIBUTION_INCOMPLETE | IDEMPOTENCY_DUPLICATE | EXECUTION_TYPE_INVALID"]
}
```

STOP.

---

### RULE 1 — TERMINAL STATE CHECK

IF `outreach_state = CLOSED`:

```json
{
  "escalation_candidate": false,
  "escalation_type": "NONE",
  "escalation_severity": "NONE",
  "reason_codes": ["OUTREACH_CLOSED_TERMINAL"]
}
```

STOP.

> CLOSED is a terminal state (spec/03 §4). A student in CLOSED state cannot re-enter escalation candidacy. If escalation is required for a closed case, a compliance or governance-initiated pathway must be used, not this assessment directive.

IF `outreach_state = INTERVENTION_REQUIRED`:

```json
{
  "escalation_candidate": false,
  "escalation_type": "NONE",
  "escalation_severity": "NONE",
  "reason_codes": ["ALREADY_IN_INTERVENTION_REQUIRED"]
}
```

STOP.

> A student already in INTERVENTION_REQUIRED is already in the escalation-resolved state. Duplicate escalation advisory for a student already escalated is not a new escalation signal.

---

### RULE 2 — COMPLIANCE HOLD GATE

IF `compliance_hold_flag = true`:

```json
{
  "escalation_candidate": true,
  "escalation_type": "COMPLIANCE_HOLD",
  "escalation_severity": "CRITICAL",
  "escalation_constraints": {
    "live_escalation_permitted": false,
    "execution_mode_constraint": "SHADOW"
  },
  "governance_requirements": {
    "blocking_governance_flags": ["COMPLIANCE_HOLD_ACTIVE"]
  },
  "reason_codes": ["COMPLIANCE_HOLD_ACTIVE"]
}
```

STOP.

> A compliance hold suspends all automated orchestration. The student is exclusively eligible for COMPLIANCE_HOLD escalation candidacy — routing to the Compliance Governance Pathway (spec/03 Domain 6). The CRITICAL severity ensures the escalation routing service treats this with maximum urgency. `live_escalation_permitted = false` even in LIVE execution mode: compliance-hold escalation routing requires separate governance authorization.

---

### RULE 3 — CONFIG-BOUND THRESHOLD RESOLUTION

**This rule is non-terminal. It must execute before any threshold-dependent rule (Rules 6–15).**

Resolve all threshold bindings from `config_rule_set` (the ACTIVE or historical config version's `rule_set_snapshot`):

| Threshold variable | Config key | Used in rule |
|---|---|---|
| `MAX_OUTREACH_ATTEMPTS` | `outreach_max_attempts` | Rule 6 |
| `CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD` | `consecutive_no_response_escalation_threshold` | Rule 7 |
| `PAYMENT_HIGH_RISK_BALANCE_THRESHOLD` | `payment_high_risk_balance_threshold` | Rule 8 |
| `PAYMENT_AT_RISK_BALANCE_THRESHOLD` | `payment_at_risk_balance_threshold` | Rule 8 |
| `LAST_ACTIVITY_HIGH_RISK_DAYS` | `last_activity_high_risk_days` | Rule 9 |
| `LAST_ACTIVITY_AT_RISK_DAYS` | `last_activity_at_risk_days` | Rule 9 |
| `HWS_BEHIND_HIGH_RISK_THRESHOLD` | `hws_behind_high_risk_threshold` | Rule 10 |
| `HWS_BEHIND_AT_RISK_THRESHOLD` | `hws_behind_at_risk_threshold` | Rule 10 |
| `AVG_EFF_RATING_HIGH_RISK_THRESHOLD` | `avg_eff_rating_high_risk_threshold` | Rule 10 |
| `AVG_EFF_RATING_AT_RISK_THRESHOLD` | `avg_eff_rating_at_risk_threshold` | Rule 10 |
| `PROVIDER_FAILURE_RETRY_LIMIT` | `provider_failure_retry_limit` | Rule 11 |
| `PRIOR_ESCALATION_REPEAT_THRESHOLD` | `prior_escalation_repeat_threshold` | Rule 12 |
| `AI_INSIGHT_TTL_HOURS` | `ai_insight_ttl_hours` | Rule 5 |

All resolved bindings are written to `config_version_reference.threshold_bindings` in the assessment output. This is the historical record of which thresholds governed this escalation assessment.

IF any threshold is missing from `config_rule_set`:

* Substitute `UNKNOWN_V0` for that threshold in internal evaluation
* Log `CONFIG_THRESHOLD_MISSING` at `warn` level with the specific missing key name
* Add `CONFIG_THRESHOLD_MISSING_{KEY_NAME}` to `reason_codes`
* Exclude rules that depend solely on the missing threshold from evaluation
* Continue with all rules that do not depend on missing thresholds

**No hardcoded threshold values are permitted as substitutes.** Missing config thresholds degrade escalation coverage; they never justify fallback to compiled-in constants (AP-X9).

CONTINUE.

---

### RULE 4 — REPLAY MODE GATE

**This rule is non-terminal. It enforces replay escalation isolation.**

IF `execution_type ∈ {replay, regeneration}`:

* Set `replay_restrictions.is_replay = true`
* Set `replay_restrictions.replay_escalation_scope = REPLAY_ESCALATION_CANDIDATE`
* Set `escalation_constraints.live_escalation_permitted = false`
* Set `escalation_constraints.execution_mode_constraint = SHADOW`
* Resolve historical config version from `replay_context.fingerprint.config_registry_version` (see §6.1)
  * If unavailable: block evaluation; emit `REPLAY_CONFIG_UNAVAILABLE`; STOP
* Add `REPLAY_ESCALATION_SHADOW_ENFORCED` to `reason_codes`

All subsequent rules evaluate normally against historical inputs and historical config thresholds, but the resulting assessment is constrained to SHADOW advisory output only.

CONTINUE.

---

### RULE 5 — AI GOVERNANCE TIER ASSESSMENT

**This rule is non-terminal. It determines the `ai_governance_tier` that governs Rule 14 behavior.**

| Condition | AI Governance Tier |
|---|---|
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score ≥ 0.70` | `CONFIDENT` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score < 0.70` | `ADVISORY` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = true` | `STALE` |
| `ai_insight_state ∈ {AI_GENERATING, AI_PENDING}` | `IN_FLIGHT` |
| `ai_insight_state ∈ {AI_GENERATION_FAILED, null}` | `UNAVAILABLE` |
| `ai_finalized_copy = true` | `FINALIZED_COPY` — immutable; not used for new escalation severity decisions |

Staleness is determined by: `current_timestamp - ai_generated_at > AI_INSIGHT_TTL_HOURS` (from config-bound threshold resolution, Rule 3).

If `AI_INSIGHT_TTL_HOURS` was not resolved (missing from config), `ai_stale_flag` cannot be determined. Set `ai_governance_tier = UNAVAILABLE` and log `AI_TTL_NOT_CONFIGURED`.

In replay mode: `IN_FLIGHT` AI is treated as `STALE` — historical replay must not wait for a new AI insight to be generated.

CONTINUE.

---

### RULE 6 — RETRY EXHAUSTION ESCALATION

IF `retry_exhausted = true` OR `contact_attempt_count ≥ MAX_OUTREACH_ATTEMPTS`:

Set `escalation_signals.retry_exhaustion = {severity: "MEDIUM", reason_code: "RETRY_EXHAUSTION"}`.
Add `RETRY_EXHAUSTION` to accumulated escalation signals.
Add `RETRY_ATTEMPTS_EXHAUSTED` to `reason_codes`.
Set `escalation_type = RETRY_EXHAUSTION` (if no higher-priority type already set).

> Retry exhaustion is a mandatory escalation signal. When all config-bound attempts are consumed without resolution, continued automated orchestration is inappropriate. The escalation routing service must present this case to an operator before it can be closed.

CONTINUE.

---

### RULE 7 — CONSECUTIVE NON-RESPONSE ESCALATION

IF `CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD` is resolved AND `consecutive_no_response_count ≥ CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD`:

Set `escalation_signals.consecutive_no_response = {severity: "HIGH", reason_code: "CONSECUTIVE_NO_RESPONSE"}`.
Add `CONSECUTIVE_NO_RESPONSE_THRESHOLD_EXCEEDED` to `reason_codes`.

IF `CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD = UNKNOWN_V0`:

Add `CONFIG_THRESHOLD_MISSING_CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD` to `reason_codes`.
Skip this rule's signal contribution.

CONTINUE.

---

### RULE 8 — PAYMENT-RISK ESCALATION

**Sub-rule 8A — HIGH_RISK payment:**

IF `PAYMENT_HIGH_RISK_BALANCE_THRESHOLD` is resolved AND `payment_balance ≥ PAYMENT_HIGH_RISK_BALANCE_THRESHOLD`:

Set `escalation_signals.payment_risk = {severity: "HIGH", tier: "HIGH_RISK", reason_code: "PAYMENT_HIGH_RISK"}`.
Add `PAYMENT_HIGH_RISK_THRESHOLD_EXCEEDED` to `reason_codes`.

CONTINUE.

**Sub-rule 8B — AT_RISK payment:**

IF `PAYMENT_AT_RISK_BALANCE_THRESHOLD` is resolved AND `payment_balance ≥ PAYMENT_AT_RISK_BALANCE_THRESHOLD` AND Sub-rule 8A did not fire:

Set `escalation_signals.payment_risk = {severity: "MEDIUM", tier: "AT_RISK", reason_code: "PAYMENT_AT_RISK"}`.
Add `PAYMENT_AT_RISK_THRESHOLD_EXCEEDED` to `reason_codes`.

CONTINUE.

---

### RULE 9 — INACTIVITY ESCALATION

**Sub-rule 9A — HIGH_RISK inactivity:**

IF `LAST_ACTIVITY_HIGH_RISK_DAYS` is resolved AND `last_activity_days > LAST_ACTIVITY_HIGH_RISK_DAYS`:

Set `escalation_signals.inactivity = {severity: "HIGH", tier: "HIGH_RISK", reason_code: "INACTIVITY_HIGH_RISK"}`.
Add `INACTIVITY_HIGH_RISK_THRESHOLD_EXCEEDED` to `reason_codes`.

CONTINUE.

**Sub-rule 9B — AT_RISK inactivity:**

IF `LAST_ACTIVITY_AT_RISK_DAYS` is resolved AND `last_activity_days > LAST_ACTIVITY_AT_RISK_DAYS` AND Sub-rule 9A did not fire:

Set `escalation_signals.inactivity = {severity: "MEDIUM", tier: "AT_RISK", reason_code: "INACTIVITY_AT_RISK"}`.
Add `INACTIVITY_AT_RISK_THRESHOLD_EXCEEDED` to `reason_codes`.

CONTINUE.

---

### RULE 10 — ACADEMIC RISK ESCALATION

Evaluate homework and effort signals against config-bound thresholds:

**Sub-rule 10A — HIGH_RISK homework delinquency:**

IF `HWS_BEHIND_HIGH_RISK_THRESHOLD` is resolved AND `hws_behind ≥ HWS_BEHIND_HIGH_RISK_THRESHOLD`:

Set `escalation_signals.hw_risk = {severity: "HIGH", tier: "HIGH_RISK", reason_code: "HW_HIGH_RISK_DELINQUENCY"}`.
Add `HWS_BEHIND_HIGH_RISK_THRESHOLD_EXCEEDED` to `reason_codes`.

**Sub-rule 10B — AT_RISK homework delinquency:**

IF `HWS_BEHIND_AT_RISK_THRESHOLD` is resolved AND `hws_behind ≥ HWS_BEHIND_AT_RISK_THRESHOLD` AND Sub-rule 10A did not fire:

Set `escalation_signals.hw_risk = {severity: "MEDIUM", tier: "AT_RISK", reason_code: "HW_AT_RISK_DELINQUENCY"}`.
Add `HWS_BEHIND_AT_RISK_THRESHOLD_EXCEEDED` to `reason_codes`.

**Sub-rule 10C — HIGH_RISK effort decline:**

IF `AVG_EFF_RATING_HIGH_RISK_THRESHOLD` is resolved AND `avg_eff_rating ≤ AVG_EFF_RATING_HIGH_RISK_THRESHOLD`:

Set `escalation_signals.effort_risk = {severity: "HIGH", tier: "HIGH_RISK", reason_code: "EFFORT_HIGH_RISK_DECLINE"}`.
Add `AVG_EFF_RATING_HIGH_RISK_THRESHOLD_MET` to `reason_codes`.

**Sub-rule 10D — AT_RISK effort decline:**

IF `AVG_EFF_RATING_AT_RISK_THRESHOLD` is resolved AND `avg_eff_rating ≤ AVG_EFF_RATING_AT_RISK_THRESHOLD` AND Sub-rule 10C did not fire:

Set `escalation_signals.effort_risk = {severity: "MEDIUM", tier: "AT_RISK", reason_code: "EFFORT_AT_RISK_DECLINE"}`.
Add `AVG_EFF_RATING_AT_RISK_THRESHOLD_MET` to `reason_codes`.

CONTINUE.

---

### RULE 11 — PROVIDER FAILURE ESCALATION

IF `PROVIDER_FAILURE_RETRY_LIMIT` is resolved AND `provider_failure_count ≥ PROVIDER_FAILURE_RETRY_LIMIT`:

Set `escalation_signals.provider_failure = {severity: "HIGH", reason_code: "PROVIDER_FAILURE_LIMIT_EXCEEDED"}`.
Add `PROVIDER_FAILURE_ESCALATION` to `reason_codes`.

IF `channel_exhaustion_state = EXHAUSTED`:

Set `escalation_signals.channel_exhaustion = {severity: "HIGH", reason_code: "ALL_CHANNELS_EXHAUSTED"}`.
Add `CHANNEL_EXHAUSTION_ESCALATION` to `reason_codes`.

IF `PROVIDER_FAILURE_RETRY_LIMIT = UNKNOWN_V0` AND `provider_failure_count > 0`:

Add `CONFIG_THRESHOLD_MISSING_PROVIDER_FAILURE_RETRY_LIMIT` to `reason_codes`.
Log `PROVIDER_FAILURE_ESCALATION_THRESHOLD_UNCONFIGURED` at `warn` level.

CONTINUE.

---

### RULE 12 — PRIOR ESCALATION RECURRENCE

IF `PRIOR_ESCALATION_REPEAT_THRESHOLD` is resolved AND `prior_escalation_count ≥ PRIOR_ESCALATION_REPEAT_THRESHOLD`:

Set `escalation_signals.recurrence = {severity: "HIGH", reason_code: "PRIOR_ESCALATION_RECURRENCE"}`.
Set `escalation_lineage_metadata.escalation_recurrence_detected = true`.
Add `PRIOR_ESCALATION_REPEAT_THRESHOLD_EXCEEDED` to `reason_codes`.

IF `PRIOR_ESCALATION_REPEAT_THRESHOLD = UNKNOWN_V0`:

Add `CONFIG_THRESHOLD_MISSING_PRIOR_ESCALATION_REPEAT_THRESHOLD` to `reason_codes`.
Skip this rule's signal contribution.

CONTINUE.

---

### RULE 13 — COMPLIANCE-DRIVEN ESCALATION

**Sub-rule 13A — Access Revocation:**

IF `access_state = REVOKED` (SQL Server-authoritative):

Set `escalation_signals.access_revocation = {severity: "HIGH", reason_code: "ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE"}`.
Set `escalation_type = ACCESS_REVOKED` (if compliance hold is not also active).
Add `ACCESS_REVOKED_ESCALATION` to `reason_codes`.

CONTINUE.

**Sub-rule 13B — Access Suspension with Pending Escalation:**

IF `access_state = SUSPENDED` AND any other escalation signal is accumulated:

Add `ACCESS_SUSPENDED_ESCALATION_CONTEXT` to `reason_codes`.

CONTINUE.

> SQL Server is the authority for access state (INVARIANT-6, spec/03 §40). Platform-supplementary records indicating active outreach do not override a SQL Server-authoritative `REVOKED` state.

---

### RULE 14 — AI-CONFIDENCE ESCALATION SEVERITY ADJUSTMENT

**This rule is non-terminal. It may elevate escalation severity based on AI governance tier and recommendation. It cannot create escalation candidacy where rules 6–13 found none.**

IF `ai_governance_tier = CONFIDENT` AND `ai_recommended_intervention = ESCALATE`:

Upgrade `escalation_severity` to `CRITICAL` (regardless of prior Rules 6–13 assessment).
Set `ai_context.severity_adjustment_applied = true`.
Add `AI_ESCALATION_SIGNAL_CONFIDENT` to `reason_codes`.

IF `ai_governance_tier = CONFIDENT` AND `ai_sentiment ∈ {"negative", "critical"}` AND at least one escalation signal is accumulated:

Upgrade `escalation_severity` by one level (MEDIUM → HIGH; HIGH → CRITICAL; CRITICAL remains CRITICAL).
Set `ai_context.severity_adjustment_applied = true`.
Add `AI_NEGATIVE_SENTIMENT_ESCALATION_ADJUSTMENT` to `reason_codes`.

IF `ai_governance_tier = ADVISORY` AND `ai_recommended_intervention = ESCALATE` AND at least one escalation signal is accumulated:

Upgrade `escalation_severity` by one level only.
Set `ai_context.severity_adjustment_applied = true`.
Add `AI_ESCALATION_SIGNAL_ADVISORY` to `reason_codes`.

IF `ai_governance_tier = STALE`:

Do NOT adjust escalation severity based on AI recommendation.
Add `STALE_AI_ESCALATION_SKIPPED` to `reason_codes`.
If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED`.

IF `ai_governance_tier ∈ {UNAVAILABLE, IN_FLIGHT}`:

Set `ai_context.fallback_applied = true`.
Add `AI_UNAVAILABLE_FALLBACK_APPLIED` to `reason_codes`.
No severity adjustment. Rule 15 rule-based assessment governs exclusively.

IF `ai_governance_tier = FINALIZED_COPY`:

No severity adjustment from this source.
Add `AI_FINALIZED_COPY_NOT_APPLIED` to `reason_codes`.

IF no escalation signals were accumulated in Rules 6–13:

AI recommendation alone MUST NOT create escalation candidacy. Add `AI_ESCALATION_SIGNAL_WITHOUT_RULE_BASIS_SUPPRESSED` to `reason_codes`.
`escalation_candidate` remains `false`.

CONTINUE.

---

### RULE 15 — MULTI-FACTOR ESCALATION SEVERITY ASSESSMENT

**This rule is non-terminal. It aggregates all accumulated escalation signals into the final severity determination.**

Count accumulated signal severities across Rules 6–14:

* Count of `HIGH` contributions from: Rule 6 (if `retry_exhausted`), Rule 7, Rule 8A, Rule 9A, Rule 10A, Rule 10C, Rule 11, Rule 12, Rule 13A
* Count of `MEDIUM` contributions from: Rule 6 (base), Rule 8B, Rule 9B, Rule 10B, Rule 10D

Aggregate severity:
* 3+ HIGH contributions → `escalation_severity = CRITICAL`; `escalation_type = MULTI_FACTOR`
* 2 HIGH contributions → `escalation_severity = HIGH`; `escalation_type = MULTI_FACTOR`
* 1 HIGH + 1+ MEDIUM → `escalation_severity = HIGH`
* 0 HIGH + 2+ MEDIUM → `escalation_severity = MEDIUM`
* 0 HIGH + 1 MEDIUM → `escalation_severity = MEDIUM`
* 0 HIGH + 0 MEDIUM + RETRY_EXHAUSTION only → `escalation_severity = MEDIUM`
* No signals → `escalation_severity = NONE`; `escalation_candidate = false`

If AI severity adjustment was applied in Rule 14, the aggregate severity after Rule 14 governs. The pre-AI severity is preserved in `observability_metadata` as `pre_ai_escalation_severity` for audit purposes.

If one or more thresholds were missing from config (Rule 3 issued `CONFIG_THRESHOLD_MISSING`), exclude the associated signals from severity scoring and add `PARTIAL_ESCALATION_ASSESSMENT` to `reason_codes`.

CONTINUE.

---

### RULE 16 — DEFAULT ESCALATION ADVISORY OUTPUT

**Terminal. Produces the final `EscalationOrchestrationAssessment` from the accumulated state of prior rules.**

At this point, `escalation_type`, `escalation_severity`, `ai_context`, `escalation_lineage_metadata`, `reason_codes`, and all governance/attribution fields have been populated by prior non-terminal rules.

Set `escalation_candidate`:
* `true` if `escalation_severity ∈ {LOW, MEDIUM, HIGH, CRITICAL}`
* `false` if `escalation_severity = NONE`

Set `governance_requirements.governance_preconditions_met = true` (Rule 0 passed).
Set `escalation_constraints.live_escalation_permitted = false` until Phase 12 production governance certification (see `execution/build_phases.md` Phase 12). In replay mode, `live_escalation_permitted = false` unconditionally.

Set `assessment_basis`:
* `AI_ASSISTED` if `ai_context.severity_adjustment_applied = true`
* `FALLBACK` if `ai_context.fallback_applied = true`
* `HISTORICAL_REPLAY` if `execution_type ∈ {replay, regeneration}`
* `RULE_BASED` otherwise

Emit the completed `EscalationOrchestrationAssessment`.

STOP.

---

## 4B. OPERATOR-INITIATED ESCALATION (MANUAL ACTION)

---

This section covers operator escalation triggered via `POST /actions/manual` with `action_type: "ESCALATE"`. It is **distinct** from the automated assessment rules in §4 — it does not run through the escalation advisement rules above. It goes directly to the state management service via the manual action API.

This pathway produces an escalation **state transition** (not an escalation advisement). The state management service writes the `INTERVENTION_REQUIRED` state, the `OutreachHistory` record, and the `StateTransitionLog` entry.

---

### Valid Source States (spec/03 §6.3)

```plaintext
CONTACTED → INTERVENTION_REQUIRED  ✓
NO_RESPONSE → INTERVENTION_REQUIRED  ✓
RETRY → INTERVENTION_REQUIRED  ✓
RESPONDED → INTERVENTION_REQUIRED  ✓
```

### Blocked Source States (spec/03 §6.3)

```plaintext
CLOSED → ESCALATE  ✗  (terminal; no transitions)
ELIGIBLE → ESCALATE  ✗  (not yet in outreach)
QUEUED → ESCALATE  ✗  (not yet contacted)
ANALYZED → ESCALATE  ✗  (automated path handles ANALYZED → INTERVENTION_REQUIRED)
INTERVENTION_REQUIRED → ESCALATE  ✗  (already escalated)
RESOLVED → ESCALATE  ✗  (case concluded)
```

### Governance Requirements

* `execution_mode` carries from the operator's session context
* `correlation_id` is generated fresh by the manual action API
* Attribution: `origin_source = operator`, `actor_identity = {operator_user_id}`
* Audit entries: `OutreachHistory` record with `action = "ESCALATED"`; `StateTransitionLog` record with `from_state`, `to_state = INTERVENTION_REQUIRED`, `actor = "operator"`, `correlation_id`, `timestamp`, and optional `notes`

### Governance Constraints

* Operator escalation is **never blocked by `MAX_OUTREACH_ATTEMPTS`** — the MAX_ATTEMPTS guard applies only to `FORCE_RETRY` (spec/03 §6.3)
* Operator escalation MUST write audit records to `state_transition_log` and `outreach_history` — these are mandatory even in SHADOW mode
* Operator escalation in SHADOW mode does NOT send outbound notifications; the state transition is written and audited, but notification dispatch is suppressed
* Operator escalation MUST NOT occur from CLOSED state — this is a governance invariant, not a soft constraint

---

## 5. CONFIG VERSION GOVERNANCE

---

### 5.1 Config Resolution Protocol

Before Rule 0 executes, the escalation assessment service MUST:

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

All threshold comparisons (Rules 6–15) MUST use values extracted from the resolved config version's `rule_set_snapshot`. No hardcoded threshold values exist in this directive or in any implementation code that executes this escalation architecture (AP-X9).

The same student with the same risk signals may produce different escalation candidacy assessments under different config versions. This is expected behavior (FAD-3, spec/01 §12). Config-version governance is what makes historical reproducibility possible.

---

### 5.3 Config Lineage in Output

Every assessment carries `config_version_id` in `governance_requirements` AND a full `config_version_reference.threshold_bindings` record capturing the specific values resolved from that version. This enables:

* Historical audit of which thresholds governed any escalation decision, without re-querying the config registry
* Replay verification: the stored threshold bindings in the assessment record can be compared against the historical config version's `rule_set_snapshot` to confirm reproducibility
* Threshold calibration analysis: downstream observability systems can correlate threshold values with escalation rates and intervention success across config versions

---

### 5.4 Prospective-Only Semantics (FAD-3 Enforcement)

Activating a new config version does NOT:

* Retroactively change historical escalation assessment outputs
* Recalculate escalation thresholds for historical escalation records
* Alter finalized snapshot cohort classifications
* Trigger reprocessing of any prior student data

Escalation assessments under the new config version take effect at the next scheduled evaluation cycle. Prior assessments, and the records they produced, are permanently attributed to the config version in effect when they were made.

---

## 6. REPLAY & REGENERATION SEMANTICS

---

### 6.1 Replay Escalation Behavior

A replay escalation evaluation determines whether a student was a valid escalation candidate at a specific historical point in time. It does not produce any new escalation actions.

Replay escalation rules:

* The historical config version governs all threshold evaluations (§5.1)
* `execution_mode` is forced to `SHADOW`; replay assessments are never `LIVE`
* `escalation_constraints.live_escalation_permitted = false` unconditionally in replay
* `replay_restrictions.replay_escalation_scope = REPLAY_ESCALATION_CANDIDATE` for a valid replay — the assessment never produces a scope that could drive outbound operator notification
* AI signals for replay use the `ai_finalized_copy` from the source snapshot — no fresh AI analysis is triggered
* Escalation cooldown evaluation in replay uses historical timestamps — not `current_timestamp`
* `fingerprint_comparison_outcome` is computed by comparing historical fingerprint components against current system state and recorded in `replay_restrictions`
* Replay idempotency keys are NOT stored in the operational idempotency store — replay evaluations are read-only with respect to state

---

### 6.2 Regeneration Escalation Behavior

Report regeneration context requires historical escalation re-evaluation to reconstruct the escalation signals that informed a prior reporting cycle:

* The decision engine invokes the escalation assessment in `execution_type = regeneration` mode
* Historical config version is used; no current ACTIVE version thresholds apply
* AI content is sourced exclusively from snapshot physical copies — no live `ai_insights` queries
* If stored fingerprint components differ from current system state, `fingerprint_comparison_outcome = DIVERGENT`; this does not block regeneration but annotates the output with `POTENTIALLY_DIVERGENT` (spec/03 §22.3)
* No new escalation history records, state transitions, or governance-sensitive writes may result from a regeneration assessment
* `replay_restrictions.replay_escalation_scope = REPLAY_ESCALATION_CANDIDATE`; regeneration cannot produce escalation candidacy that drives outbound action

---

### 6.3 SHADOW Escalation Execution Semantics

SHADOW mode is the default for all assessments until Phase 12 production governance certification:

* All rules evaluate normally; the assessment is produced with full governance context
* `escalation_constraints.live_escalation_permitted = false` regardless of `escalation_severity`
* The consuming escalation routing service is responsible for enforcing notification dispatch suppression based on `execution_mode = SHADOW`
* Governance audit log entries ARE written in SHADOW mode; a SHADOW escalation assessment is a real platform event with real audit requirements
* The escalation assessment carries no responsibility for SHADOW enforcement; it carries the mode flag and trusts consuming services to respect it

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

### 7.1 AI Governance Principle for Escalation

AI insight output is **advisory for escalation severity elevation only**. It cannot:

* Create escalation candidacy where rules 6–13 found none (see Rule 14 constraint)
* Override SQL Server-authoritative risk state for access, academic signals, or payment balance
* Override config-bound escalation threshold evaluations
* Produce `LIVE` escalation unilaterally
* Modify or invalidate historical escalation assessments produced under prior config versions
* Override governance blocks (Rules 0, 1, 2)
* Trigger live escalation notification when `ai_governance_tier = STALE`

AI insight output CAN:

* Elevate `escalation_severity` by one level when governance tier is `ADVISORY` and rule-based signals exist (Rule 14)
* Elevate `escalation_severity` to CRITICAL when governance tier is `CONFIDENT` and `ai_recommended_intervention = ESCALATE` (Rule 14)
* Set `assessment_basis = AI_ASSISTED` in observability metadata when severity adjustment is applied
* Contribute `ai_sentiment` as a severity-escalation signal at CONFIDENT tier when negative/critical sentiment accompanies an existing escalation basis

---

### 7.2 AI Governance Tier Behavior in Escalation Context

| Tier | Escalation behavior | Severity adjustment |
|---|---|---|
| `CONFIDENT` (≥ 0.70 confidence, fresh) | AI signals applied to Rule 14 severity adjustment; ESCALATE recommendation honored; negative sentiment with rule basis honored | Full adjustment: ESCALATE → CRITICAL; negative sentiment + rule basis → +1 level |
| `ADVISORY` (< 0.70 confidence, fresh) | AI signals applied at reduced weight; ESCALATE raises one level only if rule basis exists | Partial: ESCALATE + rule basis → +1 level; sentiment alone → no adjustment |
| `STALE` (beyond TTL or failed with prior) | No severity adjustment; stale flag recorded; assessment continues without AI | No adjustment; `STALE_AI_ESCALATION_SKIPPED` in reason_codes |
| `UNAVAILABLE` (no prior AI_REVIEWED) | Pure rule-based assessment; `fallback_applied = true` | No adjustment; `AI_UNAVAILABLE_FALLBACK_APPLIED` in reason_codes |
| `IN_FLIGHT` | AI assessment deferred; treated as STALE in replay mode; treated as UNAVAILABLE in original mode | No adjustment; `AI_IN_FLIGHT_TREATED_AS_UNAVAILABLE` in reason_codes |
| `FINALIZED_COPY` | Immutable snapshot content; not used for new escalation severity decisions | No adjustment; `AI_FINALIZED_COPY_NOT_APPLIED` in reason_codes |

---

### 7.3 Stale AI Protection in LIVE Mode

IF `execution_mode = LIVE` AND `ai_governance_tier = STALE`:

* Do NOT adjust `escalation_severity` based on AI recommendation
* `escalation_constraints.live_escalation_permitted` is governed solely by rule-based assessment
* If rule-based assessment independently produces `escalation_candidate = true`, it remains valid; AI staleness does not retract rule-based candidacy
* Add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`
* The assessment output must explicitly flag the staleness condition and `ai_generated_at` so downstream operators are aware of AI context age

---

### 7.4 AI Snapshot Isolation (FAD-1 Enforcement)

When `ai_finalized_copy = true`:

* The assessment MUST NOT request, apply, or reference live `ai_insights` records for this student in the same evaluation context
* `ai_governance_tier` is set to `FINALIZED_COPY` regardless of the live `ai_insights` record state
* No severity adjustment is applied from the frozen copy — finalized snapshot copies are for report regeneration, not new escalation severity decisions

---

### 7.5 Deterministic Fallback

When AI input is `UNAVAILABLE` or `STALE`, the assessment MUST produce a deterministic rule-based output using only SQL Server-authoritative signals, platform-supplementary operational signals, and config-bound thresholds. The fallback path is not a degraded mode — it is a fully specified assessment path that satisfies the same correctness and reproducibility requirements as the AI-assisted path.

`ai_context.fallback_applied = true` in the output signals to downstream services that this assessment operated without current AI assistance.

---

## 8. OBSERVABILITY & ATTRIBUTION

---

### 8.1 Required Telemetry per Assessment

Every escalation evaluation MUST emit a structured log entry (JSON, to stdout per spec/06 §2) containing:

| Log field | Source |
|---|---|
| `timestamp` | ISO-8601 at assessment start |
| `level` | `info` (normal), `warn` (fallback/stale/partial), `error` (governance gate failure) |
| `service` | `escalation_assessment` |
| `event` | `escalation_advisory_produced` or `governance_precondition_failed` |
| `correlation_id` | From `governance_context.correlation_id` |
| `causation_id` | From `governance_context.causation_id` (null if root event) |
| `student_id_opaque` | Opaque hash of the student ID — never the raw SQL Server `user_id` |
| `execution_type` | `original`, `replay`, or `regeneration` |
| `execution_mode` | `SHADOW` or `LIVE` |
| `config_version_id` | ID of the resolved config version |
| `escalation_candidate` | Boolean |
| `escalation_type` | Type value produced |
| `escalation_severity` | Severity value produced |
| `ai_governance_tier` | Tier from Rule 5 |
| `rule_path_taken` | Array of rule IDs that fired |
| `assessment_basis` | `RULE_BASED`, `AI_ASSISTED`, `FALLBACK`, or `HISTORICAL_REPLAY` |
| `duration_ms` | Assessment duration |
| `outcome` | `success`, `blocked`, `fallback`, `partial` |
| `error_class` | Populated only on `error` level |

---

### 8.2 Escalation Lineage Traceability

Every escalation advisory must be traceable from the triggering event back through:

* The upstream `correlation_id` from the eligibility or retry assessment that triggered this evaluation
* The config version that governed the threshold evaluations
* The rule path that produced the escalation type and severity
* The AI governance tier and whether a severity adjustment was applied

The lineage chain must be reconstructable from a single `correlation_id` query across the log stream. An escalation advisory that cannot be fully traced to its governance context is incomplete and represents an observability gap (spec/06 §3 correlation ID requirements).

---

### 8.3 Attribution Propagation

The attribution fields set in the assessment context (`origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`) MUST propagate to every downstream record created as a result of consuming this assessment. The escalation assessment sets attribution at the `system_automated` / `platform_supplementary` tier; consuming services append their own actor identity but do not overwrite the assessment's attribution context.

Attribution fields are immutable once set. Consuming services MUST NOT rewrite, strip, or reinterpret attribution fields from the assessment output.

---

### 8.4 Escalation Trace Metadata

The `rule_path_taken` field in `observability_metadata` provides a complete trace of which rules fired during this assessment, in order. This enables:

* Historical explainability of why a student received a specific escalation type and severity
* Threshold calibration analysis: which rules fire most frequently, and which rule combinations correlate with positive intervention outcomes
* Debugging: when an assessment produces an unexpected severity, the rule path identifies the exact signal combination

Rule path entries use the canonical rule identifiers from §4 (e.g., `["RULE_0", "RULE_1", "RULE_3", "RULE_4", "RULE_5", "RULE_6", "RULE_9A", "RULE_10A", "RULE_14", "RULE_15", "RULE_16"]`).

---

### 8.5 PII Redaction Rules

The following fields MUST NEVER appear in log output, telemetry, or observability metadata:

* Raw `user_id` (SQL Server primary key) → substitute `student_id_opaque` (opaque hash)
* `email` → `***@***`
* `phone_number` → `***`
* Student name → `[REDACTED]`
* AI-generated narrative text → NEVER in logs; stored only in database
* Raw payment amounts with student context → aggregate only; no per-student payment values in logs
* Escalation notes or operator-supplied text → never in telemetry; stored only in audit records

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
| SQL Server-authoritative academic fields (all null) | Governance-critical | Block assessment; emit `MISSING_SQL_SERVER_DATA`; do not substitute platform estimates |
| `outreach_state` null | Operational fallback | Default to `ELIGIBLE`; add `OUTREACH_STATE_UNKNOWN` to reason_codes; log warning |
| `ai_insight_state` null | AI fallback | Set `ai_governance_tier = UNAVAILABLE`; fallback applies |
| `consecutive_no_response_count` null | Operational fallback | Treat as 0; `CONSECUTIVE_NO_RESPONSE_COUNT_UNKNOWN` in reason_codes; log warning |
| `prior_escalation_count` null | Historical fallback | Treat as 0; `PRIOR_ESCALATION_COUNT_UNKNOWN` in reason_codes; log warning |
| `provider_failure_count` null | Operational fallback | Treat as 0; no provider failure extension applied; `PROVIDER_FAILURE_COUNT_UNKNOWN` in reason_codes |
| Historical inputs absent | Historical fallback | Continue without historical enrichment; `historical_escalation_patterns = []`; log warning |

Missing data from SQL Server-authoritative sources blocks evaluation. Missing data from supplementary or historical sources triggers fallback behavior. Unblocked assessments with missing supplementary data must include `MISSING_DATA_FALLBACK_APPLIED` in `reason_codes`.

---

### 9.2 Stale SQL Server Data

IF `sql_server_sync_timestamp` is older than `sql_server_max_sync_age_hours` (from config, Group I):

* Emit `STALE_SQL_SERVER_DATA` warning in log
* Proceed with assessment but include `STALE_DATA_WARNING` in `reason_codes`
* Do NOT produce `LIVE` escalation scope based on stale SQL Server data; force `execution_mode_constraint = SHADOW` in `escalation_constraints` with `STALE_DATA_SHADOW_OVERRIDE`
* Alert operational telemetry so the sync service can be triggered

---

### 9.3 Invalid Config Resolution

IF the Config Version Registry returns zero or multiple ACTIVE versions:

* Block assessment unconditionally at Rule 0
* Log `CONFIG_REGISTRY_INCONSISTENT` at `error` level with `error_class: ContractViolation`
* Emit escalation alert to the operator notification service (the irony is intentional: config failure is itself an escalation signal)
* Do NOT default to hardcoded threshold values
* Retry config resolution is permitted; if 3 consecutive resolution failures occur, escalate as a production incident

---

### 9.4 Duplicate Escalation Detection

IF `idempotency_key` already exists in the idempotency store for `(student_id, checkpoint_type, cycle_timestamp, escalation_trigger)`:

* Block assessment at Rule 0
* `IDEMPOTENCY_DUPLICATE` in `reason_codes`
* Do NOT produce a new assessment; the prior assessment for this cycle key is the canonical record
* Log at `warn` level (duplicates are expected in retry scenarios caused by scheduler at-least-once delivery; they are not errors)

---

### 9.5 Replay Conflict Behavior

| Replay failure scenario | Behavior |
|---|---|
| Historical config version unavailable | Block replay at Rule 4; `REPLAY_CONFIG_UNAVAILABLE`; do not substitute current ACTIVE version |
| Fingerprint components incomplete | Proceed with available components; log `REPLAY_FINGERPRINT_PARTIAL`; set `fingerprint_comparison_outcome = UNKNOWN` |
| Replay context indicates `execution_mode = LIVE` | Override to `SHADOW`; log `REPLAY_MODE_OVERRIDE`; never allow live escalation from replay context |
| Historical escalation state unavailable | Block replay at Rule 4; `REPLAY_STATE_UNAVAILABLE`; do not reconstruct from current state |
| Fingerprint divergence detected | Continue; set `fingerprint_comparison_outcome = DIVERGENT`; annotate output with `POTENTIALLY_DIVERGENT`; do not block (spec/03 §22.3) |

---

### 9.6 Stale AI Behavior

IF AI governance tier is `STALE`:

* No severity adjustment (Rule 14)
* Add `STALE_AI_ESCALATION_SKIPPED` to `reason_codes`
* If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED`
* Include `ai_generated_at` in `ai_context` output so downstream operators know the age of the last AI insight
* Rule-based assessment governs exclusively; fallback path is fully deterministic

---

### 9.7 Provider Outage Handling

IF `automation_degradation_state = SUSPENDED` OR `orchestration_health_state = OUTAGE`:

* Set `escalation_signals.automation_degradation = {severity: "HIGH", reason_code: "AUTOMATION_DEGRADATION_ESCALATION"}`
* Add `ORCHESTRATION_DEGRADATION_ESCALATION` to `reason_codes`
* Log `AUTOMATION_DEGRADATION_ESCALATION_TRIGGERED` at `warn` level
* The escalation routing service MUST NOT assume automated follow-up will occur; human review is explicitly required

> Provider state (outage, circuit breaker) must not corrupt historical escalation lineage. Provider failure signals from historical contexts are sourced from `provider_failure_breakdown` inputs, not from live circuit breaker state. This ensures replay assessments reflect historical conditions accurately (AP-X5).

---

### 9.8 Attribution Gap Behavior

IF `attribution_context` is partially populated (some required fields present, some absent):

* Block assessment at Rule 0; `ATTRIBUTION_INCOMPLETE` in `reason_codes`
* Do NOT produce an assessment with a partial attribution context
* Partial attribution is a governance defect: an escalation that cannot be fully attributed cannot be audited

---

## 10. ARCHITECTURE PRESERVATION RULES

---

The following prohibitions are absolute. No implementation code, configuration change, or emergency workaround may violate them. A violation is a production defect requiring immediate rollback.

| Rule | Prohibition |
|---|---|
| `AP-X1` | The escalation assessment MUST NOT directly assign operators, create tasks, or initiate any human workflow. It determines candidacy and severity; it does not execute. |
| `AP-X2` | The escalation assessment MUST NOT dispatch Slack messages, send email notifications, or trigger any outbound communication. All notifications are the responsibility of the notification dispatch service consuming the escalation routing service's output. |
| `AP-X3` | The escalation assessment MUST NOT mutate outreach state, snapshot state, escalation history, or any lifecycle domain state. All state writes belong to consuming services. |
| `AP-X4` | The escalation assessment MUST NOT modify the Config Version Registry. Config lifecycle transitions are operator-initiated governance workflows. |
| `AP-X5` | The escalation assessment MUST NOT corrupt historical escalation lineage. Provider outage state, circuit breaker state, or live infrastructure state must not overwrite historical escalation attribution. Replay inputs are sourced from historical records, not live system state. |
| `AP-X6` | The escalation assessment MUST NOT overwrite, modify, or supplement an immutable snapshot's stored content. FINALIZED snapshots are immutable (FAD-1, spec/03 INVARIANT-1). |
| `AP-X7` | The escalation assessment MUST NOT overwrite historical escalation assessment outputs. Each assessment is append-only. A re-evaluation produces a NEW assessment record with its own idempotency key and attribution. |
| `AP-X8` | The escalation assessment MUST NOT corrupt replay semantics. A replay assessment must produce `REPLAY_ESCALATION_CANDIDATE` scope only; it must not produce escalation candidacy that drives outbound operator assignment or notification. |
| `AP-X9` | The escalation assessment MUST NOT use hardcoded escalation threshold values. All threshold comparisons must use values extracted from the resolved config version's `rule_set_snapshot`. |
| `AP-X10` | The escalation assessment MUST NOT log raw student PII. `user_id`, name, email, phone, payment amounts, and AI narrative content are prohibited in all log output. Only opaque student identifiers are permitted. |
| `AP-X11` | The escalation assessment MUST NOT produce `live_escalation_permitted = true` during replay or regeneration execution. `execution_type ∈ {replay, regeneration}` unconditionally constrains `live_escalation_permitted = false`. |
| `AP-X12` | The escalation assessment MUST NOT reuse idempotency keys across evaluation cycles. Each `(student_id, checkpoint_type, cycle_timestamp, escalation_trigger)` is unique per cycle-trigger pair. |
| `AP-X13` | The escalation assessment MUST NOT evaluate escalation rules if the GOVERNANCE PRECONDITION GATE (Rule 0) has not passed. No rule evaluation, no output production, and no telemetry beyond the BLOCKED log entry. |
| `AP-X14` | The escalation assessment MUST NOT allow AI recommendation alone to create escalation candidacy. AI may elevate severity when rule-based signals exist; it may not originate candidacy in the absence of any rule-based signal (Rule 14 constraint). |
| `AP-X15` | The escalation assessment MUST NOT override or reinterpret attribution fields from inputs. Attribution is set at origin and propagated unchanged through all outputs. |

---

## 11. SCOPE BEHAVIOR

---

### 11.1 Across All Scopes (Non-Negotiable)

Regardless of scope tier, the following are mandatory and cannot be reduced:

* GOVERNANCE PRECONDITION GATE (Rule 0) evaluated before any escalation rule
* Config V1 seed as the ACTIVE version at platform initialization (governance invariant: exactly one ACTIVE version)
* No hardcoded thresholds; all threshold comparisons from `config_rule_set`
* SHADOW execution mode as default; `live_escalation_permitted = false` until Phase 12 certification
* Idempotency key checked before producing any assessment
* Attribution fields carried on every assessment output
* PII redaction rules in all log output
* AP-X1 through AP-X15 prohibitions enforced
* INVARIANT-1 through INVARIANT-7 from spec/03 §40 respected

---

### 11.2 MVP Scope

MVP scope MAY reduce:

| Reduced behavior | What is acceptable |
|---|---|
| AI severity adjustment | `ai_governance_tier` always `UNAVAILABLE`; pure rule-based assessment; Rules 5, 14 are no-ops; `fallback_applied = true` on every output |
| Provider failure escalation | `provider_failure_count` treated as 0; Rule 11 short-circuits; `channel_exhaustion_state` treated as `AVAILABLE` |
| Consecutive non-response gate | `consecutive_no_response_count` treated as 0; Rule 7 short-circuits if threshold = UNKNOWN_V0 |
| Prior escalation recurrence | `prior_escalation_count` treated as 0; Rule 12 short-circuits if threshold = UNKNOWN_V0 |
| Historical inputs | `historical_escalation_patterns = []`; prior intervention context absent |
| Activity threshold gates | Rules 9A/9B short-circuit if both activity thresholds = UNKNOWN_V0; `INACTIVITY_THRESHOLD_NOT_CONFIGURED` in reason_codes |

MVP scope MAY NOT:

* Skip config resolution (Rule 3 and the config resolution protocol in §5.1 are mandatory)
* Hardcode any escalation threshold
* Violate attribution or lineage guarantees on assessment outputs
* Produce `LIVE` escalation candidacy
* Skip idempotency key validation
* Produce assessments without the governance precondition gate (Rule 0)
* Allow AI to create escalation candidacy without rule-based basis (AP-X14)

---

### 11.3 STANDARD Scope

STANDARD scope enables over MVP:

* AI governance tiers `CONFIDENT` and `ADVISORY` active; Rule 14 severity adjustments applied
* Historical escalation patterns active; recurrence detection in Rule 12 operational
* Consecutive non-response gate active (Rule 7) with config-bound threshold
* Provider failure assessment active; cooldown extensions fed from retry policy assessment (Rule 11)
* Channel exhaustion state consumed from channel availability service
* `STALE` AI detection active using `AI_INSIGHT_TTL_HOURS` config threshold
* Activity thresholds active in Rules 9A/9B when config-bound values are non-NULL

STANDARD scope MAY NOT produce LIVE outbound escalation. `live_escalation_permitted` remains `false` until Phase 12.

---

### 11.4 PRODUCTION Scope

PRODUCTION scope enables over STANDARD:

* `execution_mode = LIVE` permitted after Phase 12 production governance certification; `live_escalation_permitted = true` for escalation assessments that produce `escalation_candidate = true`
* Full provider failure lineage and circuit breaker state integration (Rule 11)
* Full historical escalation pattern analysis contributing to Rule 12 recurrence detection
* Full replay and regeneration escalation semantics active (Rule 4, §6)
* Fingerprint comparison logging for all replay/regeneration assessments
* Full RBAC enforcement: which operator roles may receive which escalation severity classes
* Compliance hold detection (Rule 2) fully integrated with the Compliance Governance Pathway
* Operator-initiated escalation (§4B) fully integrated with state management service

---

## 12. ACCEPTANCE CRITERIA

---

### AC-X1 — Deterministic Escalation Advisory

**Given** the same student risk context, the same config version, the same AI governance tier, and the same operational context
**When** the assessment is evaluated twice with identical inputs
**Then** the output `escalation_candidate`, `escalation_type`, `escalation_severity`, `reason_codes`, and `rule_path_taken` are identical; no non-deterministic elements appear in the output; `assessment_basis` is consistent across both evaluations

---

### AC-X2 — Replay-Safe Escalation Behavior

**Given** a replay evaluation context with `execution_type = replay`
**When** the assessment is produced
**Then** `replay_restrictions.replay_escalation_scope = REPLAY_ESCALATION_CANDIDATE`; `escalation_constraints.live_escalation_permitted = false`; the historical config version's thresholds govern all rule evaluations; no outbound operator notification or state transition may be triggered from this advisory; `execution_mode_constraint = SHADOW`

---

### AC-X3 — Config-Version Reproducibility

**Given** a historical evaluation context referencing a `SUPERSEDED` config version
**When** the assessment is evaluated in replay mode
**Then** the threshold bindings in `config_version_reference.threshold_bindings` match the `SUPERSEDED` version's `rule_set_snapshot`; the current ACTIVE version's thresholds are not consulted; `config_version_id` in the output matches the historical version

---

### AC-X4 — Attribution Continuity

**Given** an assessment with a populated attribution context
**When** the assessment is produced
**Then** the output `attribution_metadata` carries the same `origin_source`, `origin_authority`, and `attribution_timestamp` from the input context; the fields are not overwritten, augmented, or cleared; `correlation_id` appears in both the assessment output and the corresponding log entry

---

### AC-X5 — Immutable Historical Protection

**Given** a student with `ai_finalized_copy = true`
**When** the assessment evaluates AI signals
**Then** `ai_governance_tier = FINALIZED_COPY`; no severity adjustment is applied from the frozen copy; live `ai_insights` records are not queried for this student; `AI_FINALIZED_COPY_NOT_APPLIED` appears in `reason_codes`

---

### AC-X6 — Stale AI Protection in LIVE Mode

**Given** `execution_mode = LIVE` and `ai_governance_tier = STALE`
**When** the assessment evaluates Rule 14
**Then** no severity adjustment is applied based on the stale AI recommendation; `STALE_AI_LIVE_MODE_RESTRICTED` appears in `reason_codes`; the rule-based assessment from Rules 6–13 governs `escalation_severity` exclusively

---

### AC-X7 — SHADOW-vs-LIVE Escalation Isolation

**Given** `execution_mode = SHADOW`
**When** any escalation candidacy is produced
**Then** `escalation_constraints.live_escalation_permitted = false` regardless of `escalation_severity`; the consuming escalation routing service is responsible for enforcing dispatch suppression; the assessment log confirms SHADOW mode; governance audit entries are written

---

### AC-X8 — Governance Precondition Blocking

**Given** `config_version_id` cannot be resolved (Config Version Registry returns zero ACTIVE versions)
**When** the assessment service evaluates
**Then** the assessment is blocked at Rule 0; `escalation_blocked = true` and `blocking_reason = GOVERNANCE_PRECONDITION_FAILED` in the output; `CONFIG_UNRESOLVED` in `reason_codes`; no subsequent rules execute; no escalation candidacy is produced; exactly one structured log entry is emitted recording the blocked state

---

### AC-X9 — AI Cannot Originate Escalation

**Given** a student with no accumulated escalation signals from Rules 6–13 (all thresholds below trigger level)
**When** the AI governance tier is `CONFIDENT` and `ai_recommended_intervention = ESCALATE`
**Then** `escalation_candidate = false`; `escalation_severity = NONE`; `AI_ESCALATION_SIGNAL_WITHOUT_RULE_BASIS_SUPPRESSED` appears in `reason_codes`; AI recommendation alone does not produce escalation candidacy

---

### AC-X10 — Provider Failure Escalation

**Given** `provider_failure_count ≥ PROVIDER_FAILURE_RETRY_LIMIT` (from config)
**When** the assessment evaluates Rule 11
**Then** `escalation_signals.provider_failure` is accumulated; `PROVIDER_FAILURE_ESCALATION` in `reason_codes`; the escalation severity reflects provider failure contribution in Rule 15 aggregation; historical escalation lineage is sourced from input records, not live provider state

---

### AC-X11 — Compliance Hold Isolation

**Given** a student with `compliance_hold_flag = true`
**When** the assessment evaluates
**Then** Rule 2 fires; `escalation_type = COMPLIANCE_HOLD`; `escalation_severity = CRITICAL`; `COMPLIANCE_HOLD_ACTIVE` in `reason_codes`; `live_escalation_permitted = false` even in LIVE execution mode; evaluation stops at Rule 2 regardless of risk signal values

---

### AC-X12 — Idempotency Enforcement

**Given** an assessment where `idempotency_key` for `(student_id, checkpoint_type, cycle_timestamp, escalation_trigger)` already exists in the idempotency store
**When** the assessment evaluates
**Then** the assessment is blocked at Rule 0; `IDEMPOTENCY_DUPLICATE` in `reason_codes`; no new assessment is produced; the prior assessment for this cycle-trigger key is the canonical record

---

## 13. UNRESOLVED CONCERNS

---

The following concerns are identified as requiring governance resolution before the escalation orchestration architecture can be considered fully specified. Each is classified by dependency type.

| Ref | Concern | Classification | Blocking |
|---|---|---|---|
| `UE-1` | **Escalation ownership hierarchy.** Which operator tier receives which escalation severity? MEDIUM escalation notifies a coordinator; HIGH notifies a senior advisor; CRITICAL notifies a program director. This hierarchy is not specified in this directive. | Governance decision | Does not block SHADOW tier; blocks PRODUCTION escalation routing configuration |
| `UE-2` | **Mentor routing authority.** When escalation type includes an academic risk signal, does the escalation routing service have authority to assign a mentor directly, or does it require a coordinator review step first? The boundary between automated mentor suggestion and human override is undefined. | Operational policy dependency | Does not block escalation advisory production; blocks mentor assignment workflow design |
| `UE-3` | **Escalation SLA semantics.** What is the required response time for each escalation severity (MEDIUM, HIGH, CRITICAL)? Are SLA breaches themselves escalation triggers? This directive does not define SLA governance; it produces severity classifications only. | Governance decision | Does not block this directive; required for escalation routing service SLA tracking |
| `UE-4` | **Human override behavior and lineage.** When an operator dismisses or downgrades an escalation advisory (e.g., marks a CRITICAL advisory as handled with no intervention), does that dismissal persist in the escalation lineage? Does a dismissed escalation affect the `prior_escalation_count` used in Rule 12 recurrence detection? | Implementation dependency | Requires lineage schema clarification before Rule 12 can be fully implemented |
| `UE-5` | **AI escalation trust ceilings.** The current directive caps AI severity elevation at CRITICAL when `CONFIDENT` tier recommends ESCALATE. Should there be a per-time-window or per-enrollment ceiling on AI-assisted escalations to prevent runaway AI-driven escalation spikes? A student with persistently stale AI could, on AI refresh, generate a burst of CRITICAL advisories. | AI governance decision | Does not block current architecture; required before AI escalation influence is enabled in PRODUCTION scope |

---

## 14. DOWNSTREAM IMPLICATIONS

---

### 14.1 Core Decision Engine

The `EscalationOrchestrationAssessment` is consumed by the Core Decision Engine when it produces `ESCALATE_TO_OPERATOR` intents (`directives/core_decision_engine.md`). Implications:

* The decision engine's Rule 2 (Compliance Hold Check) produces `ESCALATE_TO_OPERATOR` intents; the escalation assessment provides the severity classification for those intents
* The decision engine's `escalation_metadata` field in the `OrchestrationIntent` schema is populated from this assessment's type, severity, and reason codes
* The decision engine passes `correlation_id` and `attribution_metadata` unchanged into the escalation assessment context; the escalation assessment must not overwrite them
* A blocked escalation assessment (Rule 0) does not prevent the decision engine from producing other intent types; the block applies only to escalation candidacy

---

### 14.2 Outreach Orchestration Service

The outreach service consults escalation assessment candidacy when retry advisement produces `ESCALATION_CANDIDATE` scope (from `directives/outreach_retry_policy.md`). Implications:

* Retry exhaustion (Rule 6 of this directive) mirrors the retry policy's `MAX_ATTEMPTS_EXHAUSTED` signal; both must produce consistent escalation signals for the same student state
* Channel exhaustion state from the outreach service propagates as input to this directive's Rule 11
* The outreach service must validate `escalation_constraints.live_escalation_permitted` before executing any escalation-derived notification dispatch

---

### 14.3 Escalation Routing Service

The escalation routing service is the terminal consumer of `escalation_candidate = true` assessments. Implications:

* Must validate `escalation_constraints.live_escalation_permitted` before routing to any operator or notification channel
* Must store the `idempotency_key` from the assessment before executing any assignment action
* Must produce escalation history records carrying `correlation_id` and `attribution_metadata` from the assessment
* Operator tier selection based on `escalation_severity` is the routing service's responsibility; this directive produces severity classification only

---

### 14.4 Replay and Report Orchestration Services

Replay and regeneration contexts require historical escalation re-evaluation for audit-trail reconstruction. Implications:

* Historical escalation assessments for FINALIZED snapshots are sourced from the stored `EscalationOrchestrationAssessment` records — not re-evaluated live
* If a snapshot's escalation history record is missing, replay must emit `REPLAY_STATE_UNAVAILABLE` (§9.5)
* Report regeneration that reconstructs historical escalation signals must attribute them to the historical config version, not the current ACTIVE version

---

## 15. REFERENCES

---

Depends on:

* `spec/01_requirements.md` — Section 12 (Config V2 Governance Catalog, especially Groups B, C, D, E, F, H, I) for all threshold variable canonical names and defaults
* `spec/03_state_transition_rules.md` — Domain 1 (Outreach lifecycle transitions); §6.3 (Manual ESCALATE valid/blocked states); §22.3 (POTENTIALLY_DIVERGENT fingerprint semantics); §31.1 (Config rollback prohibition); §40 (INVARIANT-1 through INVARIANT-7)
* `spec/04_idempotency_concurrency.md` — §18.1 (atomic activation), §18.4 (prospective-only), §18.5 (rollback prohibition)
* `spec/05_external_integrations.md` — §8.4 (exactly-one-ACTIVE guarantee for integration consumers)
* `spec/06_observability_operations.md` — §2 (structured logging requirements), §3 (correlation ID propagation), §10.4 (SEVERITY: HIGH stale AI alert > 48h), §10.9 (SEVERITY: MEDIUM fingerprint mismatch alert)
* `spec/07_api_contracts.md` — manual action API (`POST /actions/manual`) contract
* `spec/08_data_model.md` — `outreach_tracking`, `outreach_history`, `state_transition_log`, `config_version_registry` entity definitions
* `spec/09_security_privacy.md` — PII redaction requirements
* `directives/core_decision_engine.md` — orchestration intent model; escalation metadata schema; RULE 0 governance precondition gate pattern
* `directives/outreach_eligibility_rules.md` — escalation candidacy from eligibility context; AP-E1–AP-E15 pattern reference
* `directives/outreach_retry_policy.md` — escalation candidacy from retry exhaustion context; provider failure lineage inputs; AP-R1–AP-R15 pattern reference
* `directives/channel_selection_rules.md` — channel exhaustion state inputs (Rule 11)
* FAD-1 (Physical Copy AI Semantics) — AI finalized copy immutability (§7.4)
* FAD-3 (Prospective-Only Config) — config version prospective activation semantics (§5.4)

---

## END OF FILE
