# directives/outreach_eligibility_rules.md

---

## LAYER 3 — DIRECTIVES (ORCHESTRATION ELIGIBILITY ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-25 to reflect the finalized governed historical intelligence platform architecture established in `directives/core_decision_engine.md`. The previous version described a threshold-based outreach eligibility model (`eligible: true/false`, hardcoded thresholds, simple exclusion rules) that is architecturally incompatible with the governance-aware orchestration-intelligence platform defined in spec/01 through spec/09. Eligibility is no longer a contact decision. It is orchestration candidacy determination.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **Orchestration Eligibility Architecture** defines the candidacy determination layer of the Student Success Intelligence Platform. It specifies:

* How a student enters or is excluded from orchestration consideration in any given evaluation cycle
* What governance preconditions must hold before eligibility evaluation may proceed
* How config-version-governed thresholds determine academic and operational candidacy
* How replay, regeneration, and SHADOW execution semantics constrain eligibility outputs
* How AI-governance tiers influence orchestration priority without overriding rule-based eligibility
* What attribution, observability, and lineage metadata must accompany every eligibility assessment output

This directive is the authoritative specification for **orchestration candidacy determination**. It is consumed by the Core Decision Engine (`directives/core_decision_engine.md`) as part of the operational and governance input model that governs intent production.

---

### 1.2 Eligibility Categories

Eligibility is not a single binary decision. The following distinct eligibility categories are defined:

| Category | Definition | Governing rule(s) |
|---|---|---|
| **Operational eligibility** | The student's current outreach lifecycle state and operational signals are consistent with orchestration consideration in this cycle | Rules 1, 6, 7, 8 |
| **Orchestration eligibility** | Governance preconditions are met, operational eligibility is confirmed, and the student qualifies for a specific orchestration candidacy scope | Rules 0, 1, 2, 8 |
| **Governance eligibility** | The ACTIVE config version is resolved, attribution context is complete, execution mode is valid, and no duplicate orchestration exists for this cycle key | Rule 0 |
| **Replay eligibility** | The student's historical decision context, fingerprint, and config lineage permit replay assessment; replay isolation semantics are enforceable | Rule 10 |
| **Escalation eligibility** | Academic, operational, or historical risk signals meet the threshold for escalation candidacy, or a governance condition (compliance hold, access revocation) mandates escalation routing | Rules 2, 4, 9 |
| **AI-assisted prioritization eligibility** | AI insight freshness, governance tier, and confidence metadata qualify the AI signal for use in orchestration priority adjustment | Rules 5, 11 |

All six categories must be evaluated. The resulting `OrchestrationEligibilityAssessment` output carries the assessment outcome across all six.

---

### 1.3 What Eligibility Is NOT

To prevent scope creep and architectural boundary violations, this directive explicitly defines what eligibility assessment does NOT do:

* **Does not authorize outreach execution.** Eligibility assessment determines candidacy. The Core Decision Engine produces the orchestration intent. Orchestration services execute with governance enforcement. Eligibility is advisory to the decision engine and cannot bypass it.
* **Does not mutate outreach state or any lifecycle state.** No state machine transition (e.g., ELIGIBLE → QUEUED) originates from eligibility evaluation. All transitions belong to the state management service.
* **Does not execute escalation.** Escalation candidacy identified during eligibility evaluation is carried in the assessment output for the decision engine and escalation routing service to act on. The escalation action is not initiated here.
* **Does not select outreach channels.** CALL, SMS, EMAIL, and channel fallback sequencing are the outreach orchestration service's responsibility. Eligibility assessment knows nothing about channel availability or selection.
* **Does not publish reports, finalize snapshots, or initiate compliance actions.** These lifecycle actions belong to their respective orchestration services.
* **Does not override governance invariants (INVARIANT-1 through INVARIANT-7 in spec/03).** Eligibility assessment operates within those invariants. It does not adjudicate them.
* **Does not write to any database.** All database writes — idempotency key storage, audit log entries, state transition records — are the responsibility of consuming services.

---

## 2. INPUT MODEL

---

The eligibility assessment context is **lineage-aware and governance-aware**. Every input carries metadata establishing its authority class and origin. Inputs from SQL Server (`origin_authority = sql_server_authoritative`) govern eligibility decisions for academic and access signals. Platform-supplementary inputs provide operational context but do not override SQL Server-authoritative state (INVARIANT-6, spec/03 §40).

---

### 2.1 Operational Context

Real-time outreach and engagement state sourced from platform-owned operational tables.

| Field | Type | Authority | Description |
|---|---|---|---|
| `outreach_state` | enum | `platform_supplementary` | Current state in the Outreach lifecycle domain (ELIGIBLE through CLOSED); see spec/03 §3 |
| `contact_attempt_count` | integer | `platform_supplementary` | Total contact attempts made in the current outreach cycle |
| `last_contact_timestamp` | datetime | `platform_supplementary` | Most recent outreach event timestamp |
| `last_contact_outcome` | enum | `platform_supplementary` | Outcome of most recent contact (CONNECTED, NO_ANSWER, VOICEMAIL, etc.) |
| `retry_eligible` | boolean | `platform_supplementary` | Whether the config-bound retry window has passed since last contact |
| `engagement_signal_score` | float | `platform_supplementary` | Recent engagement responsiveness score (0.0–1.0) |
| `ghl_last_message_timestamp` | datetime | `platform_supplementary` | Most recent inbound GHL message timestamp |
| `campaign_activity_count` | integer | `platform_supplementary` | Total outreach campaign interactions |
| `quick_action_history` | list | `platform_supplementary` | Recent operator quick actions (ESCALATE, CLOSE_CASE, FORCE_RETRY, etc.) |
| `state_transition_history` | list | `platform_supplementary` | Full outreach state transition log for this student and cycle |
| `retry_history` | list | `platform_supplementary` | Log of retry attempts: timestamps, outcomes, and retry gap durations |
| `escalation_history` | list | `platform_supplementary` | Escalation events in the current cycle: reason, urgency, resolution timestamp if any |
| `orchestration_history` | list | `platform_supplementary` | Prior orchestration intents produced for this student in the current cycle |

---

### 2.2 Academic Context

SQL Server-mirrored academic signals. All fields carry `origin_authority = sql_server_authoritative` and govern eligibility decisions.

| Field | Type | Authority | Description |
|---|---|---|---|
| `user_id` | integer | `sql_server_authoritative` | Authoritative student identifier (SQL Server primary key) |
| `checkpoint_type` | string | `sql_server_authoritative` | Curriculum checkpoint: SQL / SSRS / SSIS / Post-completion |
| `hws_behind` | integer | `sql_server_authoritative` | Assignments behind schedule |
| `avg_eff_rating` | float | `sql_server_authoritative` | Average effort rating (0.0–5.0) |
| `last_activity_days` | integer | `sql_server_authoritative` | Days since last recorded activity |
| `per_comp_act` | float | `sql_server_authoritative` | Curriculum completion percentage |
| `cap_start_date` | date | `sql_server_authoritative` | CAP enrollment start date (NULL if not enrolled) |
| `launch_start_date` | date | `sql_server_authoritative` | Launch program start date (NULL if not enrolled) |
| `current_section` | string | `sql_server_authoritative` | Current curriculum section |
| `payment_balance` | decimal | `sql_server_authoritative` | Outstanding payment balance |
| `class_fees_paid` | decimal | `sql_server_authoritative` | Total fees paid to date |
| `access_state` | enum | `sql_server_authoritative` | Current platform access status (ACTIVE, REVOKED, SUSPENDED) |
| `access_last_changed` | datetime | `sql_server_authoritative` | Timestamp of most recent access state change |
| `cohort_classification` | list | `platform_supplementary` | Platform-derived cohort memberships (CAP_HOPEFUL, LAUNCH_HOPEFUL, etc.) |
| `sql_server_sync_timestamp` | datetime | `sql_server_authoritative` | Timestamp of the most recent SQL Server sync cycle that updated this record |
| `email` | string | `sql_server_authoritative` | Contact email address (used for contact data gate only; never in log output) |
| `phone_number` | string | `sql_server_authoritative` | Contact phone number (used for contact data gate only; never in log output) |

> **SQL Server authority rule:** `access_state`, `hws_behind`, `avg_eff_rating`, `last_activity_days`, `per_comp_act`, `payment_balance`, `email`, and `phone_number` are SQL Server-authoritative for eligibility decisions. Platform-supplementary signals for the same fields MUST NOT override these values (INVARIANT-6, spec/03 §40).

---

### 2.3 Governance Context

Governance context is mandatory for every eligibility evaluation. Assessments produced without full governance context are invalid and must not be consumed by the Core Decision Engine.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ID of the ACTIVE config version at assessment time (must be resolved before Rule 0 executes) |
| `config_version_status` | enum | Status of the resolved config version: `ACTIVE` (operational) or `SUPERSEDED` (replay only) |
| `config_rule_set` | object | Extracted threshold values from the ACTIVE (or historical) config version's `rule_set_snapshot` |
| `execution_mode` | enum | Platform execution mode: `SHADOW` (default; no outbound effects) or `LIVE` (requires Phase 12 certification) |
| `execution_type` | enum | `original`, `replay`, or `regeneration`; drives replay-safety rules (§6) |
| `correlation_id` | uuid | UUID v4 propagated from the triggering scheduler run or operator action |
| `causation_id` | uuid | UUID v4 of the upstream event that caused this assessment (may be null for root events) |
| `attribution_context` | object | Full attribution metadata: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp` |
| `fingerprint_context` | object | Snapshot Reproducibility Fingerprint components at the time of this evaluation; used for replay safety |
| `idempotency_key` | string | Assessment-level idempotency key `(student_id, checkpoint_type, cycle_timestamp)` |
| `compliance_hold_flag` | boolean | True if the student's snapshot is currently under `COMPLIANCE_HOLD` |
| `replay_context` | object | Present only when `execution_type ∈ {replay, regeneration}`; contains source artifact ID, historical config reference, and fingerprint from the source snapshot |

---

### 2.4 AI Context

AI insight state, staleness metadata, and confidence context. AI inputs are **advisory only** for prioritization adjustment; they cannot override SQL Server-authoritative eligibility state or hard governance rules (§7).

| Field | Type | Description |
|---|---|---|
| `ai_insight_state` | enum | Lifecycle state of the AI insight record (`AI_REVIEWED`, `AI_GENERATION_FAILED`, `AI_GENERATING`, `AI_PENDING`, `AI_ARCHIVED`, etc.) |
| `ai_insight_version` | integer | `version_number` of the AI insight record; used for staleness tracking |
| `ai_recommended_intervention` | enum | AI's recommended intervention pathway: `NONE`, `OUTREACH`, `MEETING`, `RESOURCE_DELIVERY`, `ESCALATE` |
| `ai_confidence_score` | float | Model-reported confidence (0.0–1.0); drives AI governance tier selection (Rule 5) |
| `ai_generated_at` | datetime | Timestamp of AI insight generation |
| `ai_prompt_version` | string | Prompt template version used for this insight |
| `ai_model_used` | string | LLM model identifier used for this insight |
| `ai_stale_flag` | boolean | True if insight age exceeds `ai_insight_ttl_hours` from the ACTIVE config |
| `ai_ttl_hours` | integer | TTL from the ACTIVE config version; used for staleness determination |
| `ai_finalized_copy` | boolean | Whether the AI content is a snapshot-frozen physical copy (immutable; must not drive new eligibility decisions) |
| `ai_input_metrics_hash` | string | Hash of input metrics used to generate the insight; used for reproducibility verification |

---

### 2.5 Attribution Context

Attribution context establishes the provenance of the eligibility assessment and must propagate unchanged to all downstream records.

| Field | Type | Description |
|---|---|---|
| `origin_source` | enum | Who triggered the assessment: `system_automated` (scheduler), `operator` (manual action), or `scheduler` |
| `origin_authority` | enum | Authority class of the triggering source: `platform_supplementary` for all eligibility assessments |
| `actor_identity` | string | Service identifier: `eligibility_assessment_v{N}` |
| `attribution_timestamp` | ISO-8601 | Timestamp of the originating event that caused this assessment (not the processing timestamp) |
| `historical_context` | list | List of prior `(snapshot_month, config_version_id, assessment_outcome)` tuples for longitudinal continuity |
| `prior_intervention_count` | integer | Total operator interventions recorded across all history |
| `prior_escalation_count` | integer | Total escalations in this student's history |
| `historical_risk_trend` | enum | Trend derived from prior finalized snapshots: `IMPROVING`, `STABLE`, `DECLINING`, `CRITICAL`, `UNKNOWN` |
| `last_resolution_timestamp` | datetime | Most recent RESOLVED or CLOSED outreach timestamp |

---

## 3. OUTPUT MODEL

---

The eligibility assessment produces a single **`OrchestrationEligibilityAssessment`** object per evaluation. This object is advisory: it does not execute actions, does not mutate state, and does not enforce governance boundaries. The Core Decision Engine consumes this assessment as part of its input model to produce a governance-safe `OrchestrationIntent`.

---

### 3.1 OrchestrationEligibilityAssessment Schema

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "OUTREACH | RETRY | ESCALATION_CANDIDATE | REPLAY_CANDIDATE | PRIORITIZATION_ONLY | NONE",
  "orchestration_constraints": {
    "max_attempts_constraint": 0,
    "exclusion_window_constraint_hours": 0,
    "retry_window_constraint_hours": 0,
    "execution_mode_constraint": "SHADOW | LIVE",
    "ai_prioritization_applied": false,
    "live_outreach_permitted": false
  },
  "governance_requirements": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "execution_mode": "SHADOW | LIVE",
    "idempotency_key": "string",
    "governance_preconditions_met": false,
    "blocking_governance_flags": []
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
    "actor_identity": "eligibility_assessment_v1"
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
      "exclusion_window_hours": 0,
      "min_hws_behind": 0,
      "min_effort_rating": 0.0,
      "max_inactivity_days": 0,
      "max_outreach_attempts": 0,
      "retry_window_hours": 0,
      "payment_risk_balance_threshold": 0.0,
      "ai_insight_ttl_hours": 0,
      "escalation_repeat_threshold": 0
    }
  },
  "fingerprint_context": {},
  "orchestration_priority": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
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
  "eligibility_blocked": false,
  "blocking_reason": null
}
```

---

### 3.2 Eligibility Scope Values

| Scope | Meaning | Downstream implication |
|---|---|---|
| `OUTREACH` | Student has no prior contact in this cycle; operational and governance eligibility confirmed; candidate for first-contact orchestration | Decision engine may produce `INITIATE_OUTREACH` intent |
| `RETRY` | Prior contact exists; retry window has passed; contact attempt count within config-bound maximum; candidate for retry orchestration | Decision engine may produce `RETRY_OUTREACH` intent |
| `ESCALATION_CANDIDATE` | Academic, operational, or governance signals (compliance hold, access revocation, critical risk) mandate escalation routing | Decision engine produces `ESCALATE_TO_OPERATOR` intent |
| `REPLAY_CANDIDATE` | Evaluation is in replay or regeneration context; operational candidacy is assessed but live orchestration is prohibited; no outbound-effect intent permitted | Decision engine produces `NO_ELIGIBLE_INTENT` with `execution_type = replay` |
| `PRIORITIZATION_ONLY` | Student is not yet eligible for outreach or retry (e.g., AI insight is in-flight, or exclusion window not fully elapsed) but AI signals are available for priority pre-assessment | Decision engine may produce `DEFER_PENDING_AI` or advisory-only output |
| `NONE` | No orchestration candidacy in this cycle; student is in a terminal state, all attempts exhausted, or compliance blocking is active | Decision engine produces `NO_ELIGIBLE_INTENT` or `CLOSE_ORCHESTRATION` |

---

### 3.3 Key Output Clarifications

* **Eligibility does not authorize execution.** The `OrchestrationEligibilityAssessment` is advisory to the Core Decision Engine. The engine applies its own rule set (Rules 0–14 in `directives/core_decision_engine.md`) to produce the final `OrchestrationIntent`. An `orchestration_eligible = true` assessment does not guarantee an outreach intent will be produced.
* **Orchestration services still validate.** Even after the decision engine produces an intent, the outreach orchestration service validates that the student's current state has not advanced since the assessment was produced. The assessment is point-in-time.
* **Eligibility is advisory and auditable.** Every assessment is logged with full governance context. The assessment output and the rule path that produced it must be reproducible from the stored assessment record and the bound config version's `rule_set_snapshot`.
* **The assessment never writes to the database.** All persistence — idempotency key storage, assessment log entries, state records — is the responsibility of the consuming service or the Core Decision Engine's consuming orchestration services.
* **Threshold bindings in `config_version_reference` are the historical record.** The specific threshold values that governed this assessment are captured in the output and stored with the assessment record, enabling historical audit without re-querying the config registry.

---

## 4. ELIGIBILITY RULES (ORDERED)

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
* `idempotency_key` already exists in the idempotency store for this `(student_id, checkpoint_type, cycle_timestamp)` — duplicate orchestration detected
* `execution_type ∈ {replay, regeneration}` AND `replay_context` is absent or incomplete

THEN:

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "eligibility_blocked": true,
  "blocking_reason": "GOVERNANCE_PRECONDITION_FAILED",
  "governance_requirements": {
    "governance_preconditions_met": false
  },
  "reason_codes": [
    "CONFIG_UNRESOLVED | CONFIG_VERSION_NOT_ACTIVE | EXECUTION_MODE_INVALID | LIVE_CERTIFICATION_REQUIRED | CORRELATION_ID_MISSING | ATTRIBUTION_INCOMPLETE | IDEMPOTENCY_DUPLICATE | REPLAY_CONTEXT_MISSING"
  ]
}
```

STOP.

> **Governance integrity note:** The governance precondition gate ensures that orchestration integrity precedes all business rules. A blocked assessment at Rule 0 is a definitive governance failure, not a data problem to work around. No fallback, no retry, no default behavior. The assessment is invalid and must not be consumed.

---

### RULE 1 — TERMINAL STATE CHECK

IF `outreach_state = CLOSED`:

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "reason_codes": ["OUTREACH_CLOSED_TERMINAL"]
}
```

STOP.

> CLOSED is a terminal state in the Outreach lifecycle domain (spec/03 §4). A student in CLOSED state cannot re-enter orchestration candidacy. If re-engagement is required, a new outreach cycle must be initiated through the state management service, not through eligibility re-evaluation.

---

### RULE 2 — COMPLIANCE HOLD GATE

IF `compliance_hold_flag = true`:

```json
{
  "orchestration_eligible": true,
  "eligibility_scope": "ESCALATION_CANDIDATE",
  "orchestration_priority": "CRITICAL",
  "reason_codes": ["COMPLIANCE_HOLD_ACTIVE"],
  "governance_requirements": {
    "blocking_governance_flags": ["COMPLIANCE_HOLD_ACTIVE"]
  }
}
```

STOP.

> A compliance hold suspends all automated outreach orchestration. The student is exclusively eligible for escalation candidacy — routing to the Compliance Governance Pathway for human operator review (spec/03 Domain 6). No outreach or retry orchestration may proceed until the hold is resolved. The `CRITICAL` priority ensures escalation routing services treat this with maximum urgency.

---

### RULE 3 — CONFIG-BOUND THRESHOLD RESOLUTION

**This rule is non-terminal. It must execute before any threshold-dependent rule (Rules 6, 7, 8, 9, 11).**

Resolve all threshold bindings from `config_rule_set` (the ACTIVE or historical config version's `rule_set_snapshot`):

| Threshold variable | Config key | Used in rule |
|---|---|---|
| `EXCLUSION_WINDOW_HOURS` | `outreach_exclusion_window_hours` | Rule 7 |
| `MIN_HWS_BEHIND` | `hws_behind_minimum_threshold` | Rule 9 |
| `MIN_EFFORT_RATING` | `avg_eff_rating_minimum_threshold` | Rule 9 |
| `MAX_INACTIVITY_DAYS` | `last_activity_max_days` | Rule 9 |
| `MAX_OUTREACH_ATTEMPTS` | `outreach_max_attempts` | Rule 8 |
| `RETRY_WINDOW_HOURS` | `outreach_retry_window_hours` | Rule 8 |
| `PAYMENT_RISK_THRESHOLD` | `payment_balance_risk_threshold` | Rule 9 |
| `AI_INSIGHT_TTL_HOURS` | `ai_insight_ttl_hours` | Rule 5 |
| `ESCALATION_REPEAT_THRESHOLD` | `prior_escalation_repeat_threshold` | Rule 9 |
| `HWS_BEHIND_HIGH_RISK` | `hws_behind_high_risk_threshold` | Rule 9 |
| `INACTIVITY_HIGH_RISK_DAYS` | `last_activity_high_risk_days` | Rule 9 |

All resolved bindings are written to `config_version_reference.threshold_bindings` in the assessment output. This is the historical record of which thresholds governed this assessment.

IF any threshold is missing from `config_rule_set`:

* Substitute `UNKNOWN_V0` for that threshold in internal evaluation
* Log `CONFIG_THRESHOLD_MISSING` at `warn` level with the specific missing key name
* Add `CONFIG_THRESHOLD_MISSING_{KEY_NAME}` to `reason_codes`
* Exclude rules that depend solely on the missing threshold from evaluation
* Continue with all rules that do not depend on missing thresholds

**No hardcoded threshold values are permitted as substitutes.** Missing config thresholds degrade coverage; they never justify fallback to compiled-in constants (AP-E9).

CONTINUE.

---

### RULE 4 — ACCESS STATE GATE

IF `access_state ≠ ACTIVE` (per SQL Server-authoritative field):

**REVOKED:**

```json
{
  "orchestration_eligible": true,
  "eligibility_scope": "ESCALATION_CANDIDATE",
  "orchestration_priority": "HIGH",
  "reason_codes": ["ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE"]
}
```

STOP. (Access revocation requires operator intervention before any outreach orchestration can proceed.)

**SUSPENDED:**

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "reason_codes": ["ACCESS_SUSPENDED_AWAIT_RESTORATION"]
}
```

STOP. (Suspended access is not a terminal state but no outreach candidacy exists until access is restored. The state management service may transition the student when restoration is confirmed.)

> SQL Server is the authority for access state (INVARIANT-6, spec/03 §40). Platform-supplementary records indicating active outreach do not override a SQL Server-authoritative `REVOKED` or `SUSPENDED` state.

---

### RULE 5 — AI GOVERNANCE TIER ASSESSMENT

**This rule is non-terminal. It determines the `ai_governance_tier` that governs Rule 11 behavior.**

| Condition | AI Governance Tier |
|---|---|
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score ≥ 0.70` | `CONFIDENT` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score < 0.70` | `ADVISORY` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = true` | `STALE` |
| `ai_insight_state ∈ {AI_GENERATING, AI_PENDING}` | `IN_FLIGHT` — triggers Rule 5A |
| `ai_insight_state ∈ {AI_GENERATION_FAILED, null}` | `UNAVAILABLE` |
| `ai_finalized_copy = true` | `FINALIZED_COPY` — immutable; no prioritization adjustment permitted; used only by report regeneration context (§7.4) |

Staleness is determined by: `current_timestamp - ai_generated_at > AI_INSIGHT_TTL_HOURS` (from config-bound threshold resolution, Rule 3).

If `AI_INSIGHT_TTL_HOURS` was not resolved (missing from config), `ai_stale_flag` cannot be determined. Set `ai_governance_tier = UNAVAILABLE` and log `AI_TTL_NOT_CONFIGURED`.

CONTINUE.

---

### RULE 5A — PENDING AI GATE (conditional exit from Rule 5)

IF `ai_governance_tier = IN_FLIGHT` AND `execution_type = original`:

```json
{
  "orchestration_eligible": true,
  "eligibility_scope": "PRIORITIZATION_ONLY",
  "orchestration_priority": "UNKNOWN",
  "ai_context": {
    "ai_governance_tier": "IN_FLIGHT"
  },
  "reason_codes": ["AI_INSIGHT_IN_FLIGHT_DEFER_PENDING"]
}
```

STOP. (In replay mode, do not defer on IN_FLIGHT AI — use STALE tier instead, since historical replay must not wait for a new AI insight to be generated.)

---

### RULE 6 — CONTACT DATA GATE

IF `email` is null AND `phone_number` is null:

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "reason_codes": ["NO_CONTACT_INFO"]
}
```

STOP.

> No contact information means no outreach orchestration is possible for any channel. The student cannot be a candidate for OUTREACH or RETRY scope. Escalation scope is not blocked by this rule — a student without contact info may still be escalated to an operator who can investigate. However, given CLOSED is not the state here and escalation was not triggered by Rules 2 or 4, this assessment produces NONE scope. The Core Decision Engine may still produce `RECOMMEND_INTERVENTION` based on broader context.

---

### RULE 7 — EXCLUSION WINDOW ASSESSMENT

IF `last_contact_timestamp` is not null AND `EXCLUSION_WINDOW_HOURS` is resolved:

Calculate elapsed hours: `current_timestamp - last_contact_timestamp`.

IF elapsed hours < `EXCLUSION_WINDOW_HOURS`:

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "reason_codes": ["EXCLUSION_WINDOW_ACTIVE"],
  "orchestration_constraints": {
    "exclusion_window_constraint_hours": "{EXCLUSION_WINDOW_HOURS}"
  }
}
```

STOP.

> The exclusion window prevents over-contact. It is config-version-governed, not hardcoded. The same student evaluated under different config versions may have different exclusion windows. This is expected (FAD-3). The elapsed time and configured window value are recorded in the assessment output for auditability.

---

### RULE 8 — OUTREACH CYCLE ASSESSMENT

**This rule determines the primary orchestration candidacy scope based on contact attempt count and retry state. Non-terminal; populates `eligibility_scope` for downstream use.**

**Sub-rule 8A — Max Attempts Exhausted:**

IF `contact_attempt_count ≥ MAX_OUTREACH_ATTEMPTS`:

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "orchestration_priority": "MEDIUM",
  "reason_codes": ["MAX_ATTEMPTS_EXHAUSTED"],
  "orchestration_constraints": {
    "max_attempts_constraint": "{MAX_OUTREACH_ATTEMPTS}"
  }
}
```

STOP. (Max attempts exhausted is a terminal candidacy condition. The Core Decision Engine will produce `CLOSE_ORCHESTRATION` based on this signal.)

**Sub-rule 8B — Retry Eligible:**

IF `contact_attempt_count > 0` AND `contact_attempt_count < MAX_OUTREACH_ATTEMPTS` AND `retry_eligible = true`:

Set `eligibility_scope = RETRY`. Record `RETRY_CANDIDATE` in `reason_codes`.

CONTINUE.

**Sub-rule 8C — First Outreach Candidate:**

IF `contact_attempt_count = 0` AND `outreach_state ∈ {ELIGIBLE, QUEUED}`:

Set `eligibility_scope = OUTREACH`. Record `FIRST_OUTREACH_CANDIDATE` in `reason_codes`.

CONTINUE.

**Sub-rule 8D — Ambiguous Cycle State:**

IF none of 8A, 8B, or 8C apply (e.g., `outreach_state` is not ELIGIBLE or QUEUED but contact_attempt_count is 0):

Set `eligibility_scope = NONE`. Add `OUTREACH_STATE_AMBIGUOUS` to `reason_codes`. Log warning.

STOP.

---

### RULE 9 — MULTI-FACTOR ACADEMIC SIGNAL ASSESSMENT

**This rule is non-terminal. It produces `orchestration_priority` used by Rule 11 and carried in the assessment output for the Core Decision Engine's multi-factor risk scoring (Rule 7 in `directives/core_decision_engine.md`).**

Evaluate academic and operational risk factors against config-bound thresholds (resolved in Rule 3):

| Factor | Condition | Risk contribution |
|---|---|---|
| Homework delinquency | `hws_behind ≥ HWS_BEHIND_HIGH_RISK` | `+HIGH` |
| Homework threshold met (moderate) | `hws_behind ≥ MIN_HWS_BEHIND` AND `hws_behind < HWS_BEHIND_HIGH_RISK` | `+MEDIUM` |
| Effort decline | `avg_eff_rating < MIN_EFFORT_RATING` | `+MEDIUM` |
| Inactivity (high risk) | `last_activity_days > INACTIVITY_HIGH_RISK_DAYS` | `+HIGH` |
| Inactivity (moderate) | `last_activity_days > MAX_INACTIVITY_DAYS` AND `last_activity_days ≤ INACTIVITY_HIGH_RISK_DAYS` | `+MEDIUM` |
| Payment risk | `payment_balance > PAYMENT_RISK_THRESHOLD` | `+MEDIUM` |
| Access transition risk | `access_last_changed` within 7 days AND `access_state = ACTIVE` | `+LOW` |
| Historical escalation recurrence | `prior_escalation_count ≥ ESCALATION_REPEAT_THRESHOLD` | `+HIGH` |
| Historical trend — critical | `historical_risk_trend = CRITICAL` | `+HIGH` |
| Historical trend — declining | `historical_risk_trend = DECLINING` | `+MEDIUM` |

Aggregate priority:
* 2+ HIGH contributions → `orchestration_priority = CRITICAL`
* 1 HIGH + 1+ MEDIUM → `orchestration_priority = HIGH`
* 0 HIGH + 1+ MEDIUM → `orchestration_priority = MEDIUM`
* All LOW or no contributions → `orchestration_priority = LOW`

If one or more thresholds are missing from config (Rule 3 issued `CONFIG_THRESHOLD_MISSING`), exclude the associated risk factor from scoring and add `PARTIAL_RISK_ASSESSMENT` to `reason_codes`.

CONTINUE.

---

### RULE 10 — REPLAY ELIGIBILITY GATE

**This rule fires only when `execution_type ∈ {replay, regeneration}`. It is non-terminal when replay preconditions pass; terminal when they fail.**

Replay preconditions — ALL must hold:

1. `config_version_id` matches the historical config reference from `replay_context` (not the current ACTIVE version)
2. `fingerprint_context` is populated with the historical snapshot's stored fingerprint components
3. `execution_mode = SHADOW` — replay execution must never be `LIVE`
4. `replay_context.source_artifact_id` is present and resolvable

IF all preconditions pass:

Set `eligibility_scope = REPLAY_CANDIDATE`.
Set `replay_restrictions.replay_eligible = true`.
Set `replay_restrictions.live_eligible = false`.
Set `replay_restrictions.replay_safe = true`.
Compute `fingerprint_comparison_outcome` by comparing historical fingerprint components against current system state.
Record `REPLAY_CANDIDATE` in `reason_codes`.

CONTINUE. (Replay assessment continues through Rules 9 and 11 using historical context, but the eligibility_scope remains REPLAY_CANDIDATE regardless of academic signal assessment results — no scope upgrade to OUTREACH or RETRY is permitted in replay.)

IF any precondition fails:

```json
{
  "orchestration_eligible": false,
  "eligibility_scope": "NONE",
  "eligibility_blocked": true,
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

### RULE 11 — AI-ASSISTED PRIORITIZATION ADJUSTMENT

**This rule is non-terminal. It may adjust `orchestration_priority` upward based on AI governance tier and recommendation. It cannot override governance blocks or add orchestration eligibility.**

IF `ai_governance_tier = CONFIDENT` AND `ai_recommended_intervention = ESCALATE`:

Upgrade `orchestration_priority` to `CRITICAL` (regardless of prior Rule 9 assessment).
Set `ai_context.priority_adjustment_applied = true`.
Add `AI_ESCALATION_SIGNAL_CONFIDENT` to `reason_codes`.

IF `ai_governance_tier = CONFIDENT` AND `ai_recommended_intervention ∈ {MEETING, OUTREACH, RESOURCE_DELIVERY}`:

Upgrade `orchestration_priority` by one level (LOW → MEDIUM, MEDIUM → HIGH; CRITICAL remains CRITICAL).
Set `ai_context.priority_adjustment_applied = true`.
Add `AI_INTERVENTION_SIGNAL_CONFIDENT` to `reason_codes`.

IF `ai_governance_tier = ADVISORY` AND `ai_recommended_intervention = ESCALATE`:

Upgrade `orchestration_priority` by one level only (not to CRITICAL unless already HIGH).
Set `ai_context.priority_adjustment_applied = true`.
Add `AI_ESCALATION_SIGNAL_ADVISORY` to `reason_codes`.

IF `ai_governance_tier = STALE`:

Do NOT adjust `orchestration_priority` based on AI recommendation.
Record `STALE_AI_PRIORITIZATION_SKIPPED` in `reason_codes`.
If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`.

IF `ai_governance_tier = UNAVAILABLE`:

Set `ai_context.fallback_applied = true`.
Record `AI_UNAVAILABLE_FALLBACK_APPLIED` in `reason_codes`.
No priority adjustment. Rule 9's rule-based assessment governs.

IF `ai_governance_tier = FINALIZED_COPY`:

No prioritization adjustment from this source. Immutable snapshot copies are not inputs for new eligibility decisions.
Record `AI_FINALIZED_COPY_NOT_APPLIED` in `reason_codes`.

CONTINUE.

---

### RULE 12 — DEFAULT ELIGIBILITY OUTPUT

**Terminal. Produces the final `OrchestrationEligibilityAssessment` output from the accumulated state of prior rules.**

At this point, `eligibility_scope`, `orchestration_priority`, `ai_context`, `reason_codes`, and all governance/attribution fields have been populated by prior non-terminal rules.

Set `orchestration_eligible`:
* `true` if `eligibility_scope ∈ {OUTREACH, RETRY, ESCALATION_CANDIDATE, REPLAY_CANDIDATE, PRIORITIZATION_ONLY}`
* `false` if `eligibility_scope = NONE`

Set `governance_requirements.governance_preconditions_met = true` (Rule 0 passed).
Set `assessment_basis`:
* `AI_ASSISTED` if `ai_context.priority_adjustment_applied = true`
* `FALLBACK` if `ai_context.fallback_applied = true`
* `HISTORICAL_REPLAY` if `execution_type ∈ {replay, regeneration}`
* `RULE_BASED` otherwise

Emit the completed `OrchestrationEligibilityAssessment`.

STOP.

---

## 5. CONFIG VERSION GOVERNANCE

---

### 5.1 Config Resolution Protocol

Before Rule 0 executes, the assessment service MUST:

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

All threshold comparisons (Rules 6, 7, 8, 9, 11) MUST use values extracted from the resolved config version's `rule_set_snapshot`. No hardcoded threshold values exist in this directive or in any implementation code that executes this eligibility architecture (AP-E9).

The same student with the same academic signals may produce different eligibility assessments under different config versions. This is expected behavior (FAD-3, spec/01 §12). Config-version governance is what makes historical reproducibility possible.

---

### 5.3 Config Lineage in Output

Every assessment carries `config_version_id` in `governance_requirements` AND a full `config_version_reference.threshold_bindings` record capturing the specific values resolved from that version. This enables:

* Historical audit of which thresholds governed any eligibility decision, without re-querying the config registry
* Replay verification: the stored threshold bindings in the assessment record can be compared against the historical config version's `rule_set_snapshot` to confirm reproducibility
* Threshold calibration analysis: downstream observability systems can correlate threshold values with outreach outcome rates across config versions

---

### 5.4 Prospective-Only Semantics (FAD-3 Enforcement)

Activating a new config version does NOT:

* Retroactively change historical assessment outputs
* Recalculate eligibility for historical outreach records
* Alter finalized snapshot cohort classifications
* Trigger reprocessing of any prior student data

Eligibility assessments under the new config version take effect at the next scheduled evaluation cycle. Prior assessments, and the records they produced, are permanently attributed to the config version in effect when they were made.

---

## 6. REPLAY & REGENERATION SEMANTICS

---

### 6.1 Replay Eligibility Behavior

A replay evaluation determines whether a student was a valid orchestration candidate at a specific historical point in time. It does not produce any new orchestration actions.

Replay eligibility rules:

* The historical config version governs all threshold evaluations (§5.1)
* `execution_mode` is forced to `SHADOW`; replay assessments are never `LIVE`
* `eligibility_scope` is always `REPLAY_CANDIDATE` for a valid replay — never `OUTREACH` or `RETRY`
* AI signals for replay use the `ai_finalized_copy` from the source snapshot — no fresh AI analysis is triggered
* `fingerprint_comparison_outcome` is computed by comparing the historical fingerprint components against current system state and recorded in `replay_restrictions`
* Replay idempotency keys are NOT stored in the operational idempotency store — replay evaluations are read-only with respect to state

---

### 6.2 Regeneration Eligibility Behavior

Report regeneration context requires historical eligibility re-evaluation to reconstruct the candidacy signals that informed a prior reporting cycle. In this context:

* The decision engine invokes the eligibility assessment in `execution_type = regeneration` mode
* Historical config version is used; no current ACTIVE version thresholds apply
* AI content is sourced exclusively from snapshot physical copies — no live `ai_insights` queries
* If stored fingerprint components differ from current system state, `fingerprint_comparison_outcome = DIVERGENT`; this does not block regeneration but annotates the output with `POTENTIALLY_DIVERGENT`
* No new outreach history records, state transitions, or governance-sensitive writes may result from a regeneration assessment

---

### 6.3 SHADOW Execution Semantics

SHADOW mode is the default for all assessments until Phase 12 production governance certification. In SHADOW mode:

* All rules evaluate normally; the assessment is produced with full governance context
* `orchestration_constraints.live_outreach_permitted = false` regardless of `eligibility_scope`
* The consuming Core Decision Engine produces intents normally; consuming orchestration services are responsible for enforcing outbound dispatch suppression based on `execution_mode = SHADOW`
* Governance audit log entries ARE written in SHADOW mode; a SHADOW eligibility assessment is a real platform event with real audit requirements
* The eligibility assessment carries no responsibility for SHADOW enforcement; it carries the mode flag and trusts consuming services to respect it

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

### 7.1 AI Governance Principle for Eligibility

AI insight output is **advisory for prioritization only**. It cannot:

* Override SQL Server-authoritative eligibility state (access, enrollment, academic metrics)
* Override config-bound threshold evaluations for academic signal assessment
* Grant or remove orchestration eligibility (AI cannot make a non-eligible student eligible)
* Produce `LIVE` eligibility assessments unilaterally
* Modify or invalidate historical eligibility assessments produced under prior config versions
* Override governance blocks (Rule 0, Rule 2, Rule 4)

AI insight output CAN:

* Adjust `orchestration_priority` upward when governance tier is `CONFIDENT` or `ADVISORY` (Rule 11)
* Contribute context for escalation candidacy assessment (Rule 9 AI risk contribution)
* Set `assessment_basis = AI_ASSISTED` in observability metadata when priority adjustment is applied
* Provide contextual signals that the Core Decision Engine uses for its own AI-assisted rules (Rules 7, 10 in `directives/core_decision_engine.md`)

---

### 7.2 AI Governance Tier Behavior in Eligibility Context

| Tier | Eligibility behavior | Priority adjustment |
|---|---|---|
| `CONFIDENT` (≥ 0.70 confidence, fresh) | AI signals applied to Rule 11 priority adjustment; escalation signals honored | Full adjustment: ESCALATE → CRITICAL; others → +1 level |
| `ADVISORY` (< 0.70 confidence, fresh) | AI signals applied at reduced weight; escalation raises one level, not two | Partial adjustment: ESCALATE → +1 level only; others → no adjustment |
| `STALE` (beyond TTL or failed with prior) | No priority adjustment; stale flag recorded; assessment continues without AI | No adjustment; `STALE_AI_PRIORITIZATION_SKIPPED` in reason_codes |
| `UNAVAILABLE` (no prior AI_REVIEWED) | Pure rule-based assessment; fallback_applied = true | No adjustment; `AI_UNAVAILABLE_FALLBACK_APPLIED` in reason_codes |
| `IN_FLIGHT` | Assessment deferred to PRIORITIZATION_ONLY scope (Rule 5A) | Not applicable; IN_FLIGHT triggers defer |
| `FINALIZED_COPY` | Immutable snapshot content; not used for new eligibility decisions | No adjustment; `AI_FINALIZED_COPY_NOT_APPLIED` in reason_codes |

---

### 7.3 Stale AI Protection in LIVE Mode

IF `execution_mode = LIVE` AND `ai_governance_tier = STALE`:

* Do NOT produce any eligibility scope that depends on AI recommendation
* `orchestration_constraints.live_outreach_permitted` remains governed solely by rule-based assessment
* If rule-based assessment independently produces `OUTREACH` or `RETRY` scope, it remains valid; AI staleness does not retract rule-based eligibility
* Add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`
* The assessment output must explicitly flag the staleness condition and the AI generation timestamp so that downstream operators are aware

---

### 7.4 AI Snapshot Isolation (FAD-1 Enforcement)

When `ai_finalized_copy = true`:

* The assessment MUST NOT request, apply, or reference live `ai_insights` records for this student in the same evaluation context
* `ai_governance_tier` is set to `FINALIZED_COPY` regardless of the live `ai_insights` record state
* No priority adjustment is applied from the frozen copy — finalized snapshot copies are for report regeneration, not new eligibility decisions

---

### 7.5 Deterministic Fallback

When AI input is `UNAVAILABLE` or `STALE`, the assessment MUST produce a deterministic rule-based output using only SQL Server-authoritative signals and config-bound thresholds. The fallback path is not a degraded mode — it is a fully specified assessment path that satisfies the same correctness and reproducibility requirements as the AI-assisted path.

`ai_context.fallback_applied = true` in the output signals to downstream services that this assessment operated without current AI assistance.

---

## 8. OBSERVABILITY & ATTRIBUTION

---

### 8.1 Required Telemetry per Assessment

Every eligibility evaluation MUST emit a structured log entry (JSON, to stdout per spec/06 §2) containing:

| Log field | Source |
|---|---|
| `timestamp` | ISO-8601 at assessment start |
| `level` | `info` (normal), `warn` (fallback/stale), `error` (governance gate failure) |
| `service` | `eligibility_assessment` |
| `event` | `orchestration_eligibility_produced` or `governance_precondition_failed` |
| `correlation_id` | From `governance_context.correlation_id` |
| `causation_id` | From `governance_context.causation_id` (null if root event) |
| `student_id_opaque` | Opaque hash of the student ID — never the raw SQL Server `user_id` |
| `execution_type` | `original`, `replay`, or `regeneration` |
| `execution_mode` | `SHADOW` or `LIVE` |
| `config_version_id` | ID of the resolved config version |
| `eligibility_scope` | The scope value produced |
| `orchestration_eligible` | Boolean |
| `orchestration_priority` | Priority value produced |
| `ai_governance_tier` | Tier from Rule 5 |
| `rule_path_taken` | Array of rule IDs that fired |
| `assessment_basis` | `RULE_BASED`, `AI_ASSISTED`, `FALLBACK`, or `HISTORICAL_REPLAY` |
| `duration_ms` | Assessment duration |
| `outcome` | `success`, `blocked`, `fallback` |
| `error_class` | Populated only on `error` level |

---

### 8.2 Correlation ID Propagation

The `correlation_id` assigned at the triggering scheduler run or operator action MUST propagate without modification through:

* The assessment context inputs
* The `OrchestrationEligibilityAssessment` output
* Every downstream service call that consumes the assessment (Core Decision Engine, orchestration services)
* Every database write and audit log entry produced by consuming services

The causal chain from scheduler run → eligibility assessment → decision engine intent → outreach dispatch → state transition → audit log must be reconstructable from a single `correlation_id` query.

---

### 8.3 Attribution Propagation

The attribution fields set in the assessment context (`origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`) MUST propagate to every downstream record created as a result of consuming this assessment. The eligibility assessment sets attribution at the `system_automated` / `platform_supplementary` tier; consuming services append their own actor identity but do not overwrite the assessment's attribution context.

Attribution fields are immutable once set. Consuming services MUST NOT rewrite, strip, or reinterpret attribution fields from the assessment output.

---

### 8.4 Eligibility Trace Metadata

The `rule_path_taken` field in `observability_metadata` provides a complete trace of which rules fired during this assessment, in order. This trace enables:

* Historical explainability of why a student received a specific eligibility scope
* Threshold calibration analysis: which rules fire most frequently, and which rule combinations correlate with outreach success
* Debugging: when an assessment produces an unexpected scope, the rule path identifies the exact decision branch

Rule path entries use the canonical rule identifiers from §4 (e.g., `["RULE_0", "RULE_1", "RULE_3", "RULE_4", "RULE_5", "RULE_8B", "RULE_9", "RULE_11", "RULE_12"]`).

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
| SQL Server-authoritative academic fields (all null) | Governance-critical | Block assessment; emit `MISSING_SQL_SERVER_DATA`; do not substitute platform estimates |
| `attribution_context` incomplete | Governance-critical | Block assessment at Rule 0 |
| `outreach_state` null | Operational fallback | Default to `ELIGIBLE` with `OUTREACH_STATE_UNKNOWN` in reason_codes; log warning |
| `ai_insight_state` null | AI fallback | Set `ai_governance_tier = UNAVAILABLE`; fallback applies |
| Historical inputs absent | Historical fallback | Continue without historical enrichment; set `historical_risk_trend = UNKNOWN`; log warning |
| `retry_eligible` null | Operational fallback | Treat as `false`; `RETRY_ELIGIBLE_UNKNOWN` in reason_codes |

Missing data from SQL Server-authoritative sources blocks evaluation. Missing data from supplementary or historical sources triggers fallback behavior. Unblocked assessments with missing supplementary data must include `MISSING_DATA_FALLBACK_APPLIED` in `reason_codes`.

---

### 9.2 Stale SQL Server Data

IF `sql_server_sync_timestamp` is older than `sql_server_max_sync_age_hours` (from config):

* Emit `STALE_SQL_SERVER_DATA` warning in log
* Proceed with assessment but include `STALE_DATA_WARNING` in `reason_codes`
* Do NOT produce `LIVE` eligibility scope based on stale SQL Server data; force `execution_mode_constraint = SHADOW` in `orchestration_constraints` with `STALE_DATA_SHADOW_OVERRIDE`
* Alert operational telemetry so the sync service can be triggered

---

### 9.3 Invalid Config Resolution

IF the Config Version Registry returns zero or multiple ACTIVE versions:

* Block assessment unconditionally at Rule 0
* Log `CONFIG_REGISTRY_INCONSISTENT` at `error` level with `error_class: ContractViolation`
* Emit escalation alert to the operator notification service
* Do NOT default to hardcoded threshold values
* Retry is permitted; if 3 consecutive resolution failures occur, escalate as a production incident

---

### 9.4 Duplicate Orchestration Detection

IF `idempotency_key` already exists in the idempotency store for `(student_id, checkpoint_type, cycle_timestamp)`:

* Block assessment at Rule 0
* `IDEMPOTENCY_DUPLICATE` in `reason_codes`
* Do NOT produce a new assessment; the prior assessment for this cycle key is the canonical record
* Log at `warn` level (duplicates are expected in retry scenarios; they are not errors)

---

### 9.5 Replay Conflict Behavior

| Replay failure scenario | Behavior |
|---|---|
| Historical config version unavailable | Block replay at Rule 10; `REPLAY_CONFIG_UNAVAILABLE`; do not substitute current ACTIVE version |
| Fingerprint components incomplete | Proceed with available components; log `REPLAY_FINGERPRINT_PARTIAL`; set `fingerprint_comparison_outcome = UNKNOWN` |
| Replay context indicates `execution_mode = LIVE` | Override to `SHADOW`; log `REPLAY_MODE_OVERRIDE`; never allow live eligibility from replay context |
| Historical student state unavailable | Block replay at Rule 10; `REPLAY_STATE_UNAVAILABLE`; do not reconstruct from current state |
| Fingerprint divergence detected | Continue; set `fingerprint_comparison_outcome = DIVERGENT`; annotate output with `POTENTIALLY_DIVERGENT`; do not block |

---

### 9.6 Stale AI Behavior

IF AI governance tier is `STALE`:

* No priority adjustment (Rule 11)
* Add `STALE_AI_PRIORITIZATION_SKIPPED` to `reason_codes`
* If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED`
* Include `ai_generated_at` in `ai_context` output so downstream operators know the age of the last AI insight
* Rule-based assessment governs exclusively; fallback path is fully deterministic

---

### 9.7 Attribution Gap Behavior

IF `attribution_context` is partially populated (some required fields present, some absent):

* Block assessment at Rule 0; `ATTRIBUTION_INCOMPLETE` in `reason_codes`
* Do NOT produce an assessment with a partial attribution context
* Partial attribution is a governance defect: an assessment that cannot be fully attributed cannot be audited

---

## 10. ARCHITECTURE PRESERVATION RULES

---

The following prohibitions are absolute. No implementation code, configuration change, or emergency workaround may violate them. A violation is a production defect requiring immediate rollback.

| Rule | Prohibition |
|---|---|
| `AP-E1` | The eligibility assessment MUST NOT directly execute outreach. It determines candidacy; it does not initiate contact. |
| `AP-E2` | The eligibility assessment MUST NOT mutate outreach state, snapshot state, or any lifecycle domain state. All state writes belong to consuming services. |
| `AP-E3` | The eligibility assessment MUST NOT modify the Config Version Registry. Config lifecycle transitions are operator-initiated governance workflows. |
| `AP-E4` | The eligibility assessment MUST NOT overwrite, modify, or supplement an immutable snapshot's stored content. FINALIZED snapshots are immutable (FAD-1, spec/03 INVARIANT-1). |
| `AP-E5` | The eligibility assessment MUST NOT overwrite historical assessment outputs. Each assessment is append-only. A re-evaluation produces a NEW assessment record with its own idempotency key and attribution. |
| `AP-E6` | The eligibility assessment MUST NOT corrupt replay semantics. A replay assessment must produce a `REPLAY_CANDIDATE` scope only; it must not produce `OUTREACH` or `RETRY` scope that could drive outbound communication. |
| `AP-E7` | The eligibility assessment MUST NOT bypass the audit trail. Every assessment — including blocked assessments from Rule 0 — must produce a telemetry log entry. |
| `AP-E8` | The eligibility assessment MUST NOT use platform-supplementary signals to override SQL Server-authoritative eligibility state for access, enrollment, or academic metrics (INVARIANT-6, spec/03 §40). |
| `AP-E9` | The eligibility assessment MUST NOT use hardcoded threshold values. All threshold comparisons must use values extracted from the resolved config version's `rule_set_snapshot`. |
| `AP-E10` | The eligibility assessment MUST NOT log raw student PII. `user_id`, name, email, phone, and AI narrative content are prohibited in all log output. Only opaque student identifiers are permitted. |
| `AP-E11` | The eligibility assessment MUST NOT produce a `LIVE` eligibility scope during replay or regeneration execution. `execution_type ∈ {replay, regeneration}` unconditionally constrains `live_outreach_permitted = false`. |
| `AP-E12` | The eligibility assessment MUST NOT reuse idempotency keys across evaluation cycles. Each `(student_id, checkpoint_type, cycle_timestamp)` is unique per cycle. |
| `AP-E13` | The eligibility assessment MUST NOT execute if the GOVERNANCE PRECONDITION GATE (Rule 0) has not passed. No rule evaluation, no output production, and no telemetry beyond the BLOCKED log entry. |
| `AP-E14` | The eligibility assessment MUST NOT produce an assessment that elevates `orchestration_eligible = true` for a student under `COMPLIANCE_HOLD` to any scope other than `ESCALATION_CANDIDATE`. Automated outreach orchestration is suspended until the hold resolves. |
| `AP-E15` | The eligibility assessment MUST NOT override or reinterpret attribution fields from inputs. Attribution is set at origin and propagated unchanged through all outputs. |

---

## 11. SCOPE BEHAVIOR

---

### 11.1 Across All Scopes (Non-Negotiable)

Regardless of scope tier, the following are mandatory and cannot be reduced:

* GOVERNANCE PRECONDITION GATE (Rule 0) evaluated before any eligibility rule
* Config V1 seed as the ACTIVE version at platform initialization (governance invariant: exactly one ACTIVE version)
* No hardcoded thresholds; all threshold comparisons from `config_rule_set`
* SHADOW execution mode as default; `live_outreach_permitted = false` until Phase 12 certification
* Idempotency key checked before producing any assessment
* Attribution fields carried on every assessment output
* PII redaction rules in all log output
* AP-E1 through AP-E15 prohibitions enforced
* INVARIANT-1 through INVARIANT-7 from spec/03 §40 respected

---

### 11.2 MVP Scope

MVP scope MAY reduce:

| Reduced behavior | What is acceptable |
|---|---|
| AI prioritization | `ai_governance_tier` always `UNAVAILABLE`; pure rule-based assessment; Rules 5, 5A, 11 are no-ops; `fallback_applied = true` on every output |
| AI staleness evaluation | Rule 5 short-circuits directly to `UNAVAILABLE`; no TTL comparison |
| Historical inputs | `historical_risk_trend = UNKNOWN`; prior snapshot context absent |
| Orchestration history | `orchestration_history` input treated as empty |
| Escalation routing | `ESCALATION_CANDIDATE` scope produced; escalation notification service may be stub |

MVP scope MAY NOT:

* Skip config resolution (Rule 3 and the config resolution protocol in §5.1 are mandatory)
* Hardcode any threshold
* Violate attribution or lineage guarantees on assessment outputs
* Produce `LIVE` eligibility scope
* Skip idempotency key validation
* Produce assessments without the governance precondition gate (Rule 0)

---

### 11.3 STANDARD Scope

STANDARD scope enables over MVP:

* AI governance tiers `CONFIDENT` and `ADVISORY` active; Rule 11 priority adjustments applied
* Historical risk trend inputs active; `historical_risk_trend` values `DECLINING` and `CRITICAL` contribute to Rule 9 scoring
* Retry history and orchestration history inputs consumed for Rule 8 cycle assessment
* Escalation routing service operational; `ESCALATION_CANDIDATE` scope drives actual escalation dispatch
* `STALE` AI detection active using `AI_INSIGHT_TTL_HOURS` config threshold

STANDARD scope MAY NOT produce LIVE outbound eligibility. `live_outreach_permitted` remains `false` until Phase 12.

---

### 11.4 PRODUCTION Scope

PRODUCTION scope enables over STANDARD:

* `execution_mode = LIVE` permitted after Phase 12 production governance certification; `live_outreach_permitted = true` for `OUTREACH` and `RETRY` scope assessments
* Full multi-factor academic signal scoring with all AI governance tiers active
* Historical escalation pattern analysis contributing to Rule 9 priority assessment
* Full replay and regeneration eligibility semantics active (Rule 10)
* Fingerprint comparison logging for all replay/regeneration assessments
* Full RBAC enforcement: which operator roles may consume which eligibility scope classes
* Compliance hold detection (Rule 2) fully integrated with the Compliance Governance Pathway

---

## 12. ACCEPTANCE CRITERIA

---

### AC-E1 — Deterministic Eligibility

**Given** the same student context, the same config version, and the same AI governance tier
**When** the assessment is evaluated twice with identical inputs
**Then** the output `orchestration_eligible`, `eligibility_scope`, `orchestration_priority`, `reason_codes`, and `rule_path_taken` are identical; no non-deterministic elements appear in the output; `assessment_basis` is consistent across both evaluations

---

### AC-E2 — Replay-Safe Eligibility

**Given** a replay evaluation context with a historical config version and `execution_type = replay`
**When** the assessment is produced
**Then** `eligibility_scope = REPLAY_CANDIDATE`; `replay_restrictions.live_eligible = false`; `orchestration_constraints.live_outreach_permitted = false`; `execution_mode_constraint = SHADOW`; the historical config version's thresholds govern all rule evaluations; no scope upgrade to `OUTREACH` or `RETRY` occurs regardless of academic signal values

---

### AC-E3 — Config-Version Reproducibility

**Given** a historical evaluation context referencing a `SUPERSEDED` config version
**When** the assessment is evaluated in replay mode
**Then** the threshold bindings in `config_version_reference.threshold_bindings` match the `SUPERSEDED` version's `rule_set_snapshot`; the current ACTIVE version's thresholds are not consulted; `config_version_id` in the output matches the historical version

---

### AC-E4 — Attribution Continuity

**Given** an assessment with a populated attribution context
**When** the assessment is produced
**Then** the output `attribution_metadata` carries the same `origin_source`, `origin_authority`, and `attribution_timestamp` from the input context; the fields are not overwritten, augmented, or cleared; `correlation_id` appears in both the assessment output and the corresponding log entry

---

### AC-E5 — Immutable Historical Protection

**Given** a student with `ai_finalized_copy = true` in an assessment context
**When** the assessment evaluates AI signals
**Then** `ai_governance_tier = FINALIZED_COPY`; no priority adjustment is applied from the frozen copy; live `ai_insights` records are not queried for this student; `AI_FINALIZED_COPY_NOT_APPLIED` appears in `reason_codes`

---

### AC-E6 — Stale AI Protection in LIVE Mode

**Given** `execution_mode = LIVE` and `ai_governance_tier = STALE`
**When** the assessment evaluates Rule 11
**Then** no priority adjustment is applied based on the stale AI recommendation; `STALE_AI_LIVE_MODE_RESTRICTED` appears in `reason_codes`; the rule-based assessment from Rule 9 governs `orchestration_priority` exclusively

---

### AC-E7 — SHADOW-vs-LIVE Isolation

**Given** `execution_mode = SHADOW`
**When** any eligibility scope is produced
**Then** `orchestration_constraints.live_outreach_permitted = false` regardless of scope value; `execution_mode_constraint = SHADOW` in `orchestration_constraints`; the consuming Core Decision Engine and orchestration services are responsible for enforcing outbound dispatch suppression; the assessment log confirms SHADOW mode

---

### AC-E8 — Governance Precondition Blocking

**Given** `config_version_id` cannot be resolved (Config Version Registry returns zero ACTIVE versions)
**When** the assessment service evaluates
**Then** the assessment is blocked at Rule 0; `eligibility_blocked = true` and `blocking_reason = GOVERNANCE_PRECONDITION_FAILED` in the output; `CONFIG_UNRESOLVED` in `reason_codes`; no subsequent rules execute; no orchestration eligibility is produced; exactly one structured log entry is emitted recording the blocked state

---

### AC-E9 — SQL Server Authority Boundary

**Given** a student whose SQL Server-authoritative `access_state = REVOKED` and whose platform-supplementary records indicate active outreach is in progress
**When** the assessment evaluates
**Then** Rule 4 fires; `eligibility_scope = ESCALATION_CANDIDATE`; `ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE` in `reason_codes`; no `OUTREACH` or `RETRY` scope is produced; the SQL Server-authoritative value governs over any platform-supplementary signal

---

### AC-E10 — Compliance Hold Isolation

**Given** a student with `compliance_hold_flag = true`
**When** the assessment evaluates
**Then** Rule 2 fires; `eligibility_scope = ESCALATION_CANDIDATE` only; `orchestration_priority = CRITICAL`; `COMPLIANCE_HOLD_ACTIVE` in `reason_codes`; `blocking_governance_flags = ["COMPLIANCE_HOLD_ACTIVE"]` in `governance_requirements`; evaluation stops at Rule 2 regardless of academic signal values

---

### AC-E11 — Contact Data Gate

**Given** a student with `email = null` AND `phone_number = null`
**When** the assessment evaluates
**Then** Rule 6 fires; `orchestration_eligible = false`; `eligibility_scope = NONE`; `NO_CONTACT_INFO` in `reason_codes`; no `OUTREACH` or `RETRY` scope is produced

---

### AC-E12 — Idempotency Enforcement

**Given** an assessment where `idempotency_key` for `(student_id, checkpoint_type, cycle_timestamp)` already exists in the idempotency store
**When** the assessment evaluates
**Then** the assessment is blocked at Rule 0; `IDEMPOTENCY_DUPLICATE` in `reason_codes`; no new assessment is produced; the prior assessment for this cycle key is the canonical record

---

## 13. DOWNSTREAM IMPLICATIONS

---

### 13.1 Core Decision Engine

The `OrchestrationEligibilityAssessment` is the primary upstream input to the Core Decision Engine's eligibility interpretation function (§1.1, `directives/core_decision_engine.md`). Implications:

* The decision engine consumes `eligibility_scope`, `orchestration_priority`, `ai_context`, `governance_requirements`, and `config_version_reference` from the assessment
* The decision engine's Rule 7 (Multi-Factor Risk Assessment) uses the individual risk factor evidence accumulated in this assessment's Rule 9 evaluation — both should produce consistent risk characterizations
* The decision engine's Rules 11 and 12 (Retry and First Outreach) are informed by the `RETRY` and `OUTREACH` scope designations from this assessment's Rule 8
* The decision engine's GOVERNANCE PRECONDITION GATE (Rule 0) re-validates governance preconditions independently; passing Rule 0 in the eligibility assessment does not exempt the decision engine from its own Rule 0
* The assessment's `correlation_id` and `attribution_metadata` propagate unchanged through the decision engine's intent output

---

### 13.2 Outreach Orchestration Service

The outreach service is the terminal consumer of `OUTREACH` and `RETRY` scope assessments (after the decision engine produces the corresponding intent). Implications:

* Must validate `orchestration_constraints.live_outreach_permitted` before executing any outbound dispatch
* Must store the `idempotency_key` from the assessment context before executing any GHL API call
* Must produce outreach history records carrying the `correlation_id` and `attribution_metadata` from the assessment
* Channel selection (CALL / SMS / EMAIL / fallback chain) is the outreach service's responsibility; the eligibility assessment carries no channel information

---

### 13.3 Timeline Ingestion Service

Timeline ingestion must propagate `origin_source` and `origin_authority` from all events it ingests. The eligibility assessment relies on `state_transition_history`, `campaign_activity_count`, and `ghl_last_message_timestamp` as operational inputs (§2.1). Ingestion failures that break attribution on timeline events will degrade operational input quality and may trigger `MISSING_DATA_FALLBACK_APPLIED` in assessment outputs.

---

### 13.4 Snapshot Orchestration Service

The snapshot service does not directly consume eligibility assessment outputs in the operational flow. However:

* The assessment's `config_version_id` aligns with the same config version that snapshot finalization binds to the Reproducibility Fingerprint
* The `compliance_hold_flag` check (Rule 2) reflects the same hold condition that prevents snapshot finalization from proceeding in the Compliance Governance Pathway
* In regeneration context, the assessment's historical config version and threshold bindings must align with the snapshot's stored fingerprint components

---

### 13.5 Report Generation Service

The report service does not consume eligibility assessments directly. However:

* In regeneration context, the historical eligibility assessment records provide the candidacy signals that informed which students were evaluated in a prior cycle
* The assessment's `fingerprint_comparison_outcome` in replay mode corresponds to the `POTENTIALLY_DIVERGENT` annotation the report service may apply to regenerated reports
* Historical assessment records must be queryable by `(student_id, cycle_timestamp, config_version_id)` for regeneration context reconstruction

---

### 13.6 Observability Infrastructure

The assessment's log output feeds operational telemetry for:

* Eligibility scope distribution: what fraction of evaluations produce each scope value
* AI governance tier distribution: signals when AI freshness degrades fleet-wide
* Config version adoption: which config version governs which assessments
* SHADOW vs LIVE eligibility distribution: readiness signal for Phase 12 certification
* Rule path distribution: which rules fire most frequently; signals threshold calibration needs
* Priority distribution: tracks how risk profiles shift across cohorts and time periods

---

### 13.7 API Contract Implications

The `GET /students/{id}/orchestration-context` endpoint (spec/07) must return eligibility assessment outputs in a format consistent with the `OrchestrationEligibilityAssessment` schema (§3.1). Constraints:

* Raw `user_id` values must not be exposed; opaque student identifiers only (spec/09 §3)
* `config_version_reference.threshold_bindings` must be included when the endpoint is called in audit or replay context
* Attribution fields in `attribution_metadata` must not be stripped or summarized in the API response
* Replay assessment outputs must be clearly distinguished from original assessment outputs in the API response schema

---

## 14. UNRESOLVED ARCHITECTURAL CONCERNS

---

The following concerns carry forward from the Core Decision Engine's unresolved concerns (§14, `directives/core_decision_engine.md`) and from the eligibility architecture specifically.

| ID | Category | Description | Blocking tier |
|---|---|---|---|
| `UE-1` | Config Threshold Coverage | The `rule_set_snapshot` schema for config V1 must include all thresholds referenced in Rule 3 (§4). If any threshold is absent from V1, every assessment emits `CONFIG_THRESHOLD_MISSING` warnings. The V1 seed schema must be audited against Rule 3's full threshold list before STANDARD scope enablement. | STANDARD |
| `UE-2` | AI Staleness Threshold | `AI_INSIGHT_TTL_HOURS` is config-bound but not confirmed present in V1 seed. Until specified, Rule 5 cannot determine `ai_governance_tier = STALE` deterministically; it defaults to `UNAVAILABLE`. | STANDARD |
| `UE-3` | Opaque Student ID Hashing | The hashing scheme for `student_id_opaque` in log output is unspecified (UO-3 from prior sessions). The eligibility assessment log output must be consistent with whatever scheme the platform adopts. | PRODUCTION |
| `UE-4` | Exclusion Window Unit Consistency | The exclusion window threshold is specified here in hours (`EXCLUSION_WINDOW_HOURS`) but the current outreach history table stores timestamps. The elapsed-time calculation in Rule 7 must be verified against the actual stored precision of `last_contact_timestamp` to prevent off-by-one behavior at DST boundaries and year rollovers. | STANDARD |
| `UE-5` | LIVE Certification Gate | `execution_constraints.live_outreach_permitted` depends on Phase 12 production governance certification. The mechanism for the certification signal — how the assessment service knows Phase 12 has been completed — is not yet specified. A feature flag, a config registry entry, or an explicit environment variable are all candidates. Until specified, all assessments default to `live_outreach_permitted = false`. | PRODUCTION |
| `UE-6` | Contact Data Authority | `email` and `phone_number` are treated as SQL Server-authoritative fields in §2.2. However, the platform may have platform-supplementary contact preferences (e.g., GHL opt-out records) that override contact-data eligibility. The interaction between SQL Server-authoritative contact data and platform-supplementary opt-out state is not fully specified. Until resolved, Rule 6 uses only SQL Server-authoritative contact fields. | STANDARD |
| `UE-7` | AI Priority Adjustment Ceiling | Rule 11 defines priority upgrade behavior (ESCALATE → CRITICAL; others → +1 level). If a student is already at `CRITICAL` priority from Rule 9, the `+1 level` AI adjustment is a no-op. The question of whether a `CONFIDENT` AI `ESCALATE` signal should produce additional escalation urgency metadata (beyond what Rule 9 already produces) is unresolved. Currently treated as no-op at ceiling. | STANDARD |

---

## 15. REFERENCES

---

This directive defines the orchestration eligibility architecture. It is subordinate to the following in case of conflict (highest to lowest precedence):

* `directives/core_decision_engine.md` — the orchestration-intelligence authority; the decision engine produces final intents from this assessment; its INVARIANT and GOVERNANCE structures supersede this directive
* `spec/03_state_transition_rules.md` — §40 INVARIANT-1 through INVARIANT-7; Domain 5 config version governance; §39 attribution standard; Domain 6 compliance governance
* `spec/01_requirements.md` — FAD-1 through FAD-6; §2.3 operational domains; §2.4 cohort identification rules; §12 configurable rule governance
* `spec/04_idempotency_concurrency.md` — §4 idempotency keys; §20 event attribution; §23 execution mode interactions
* `spec/06_observability_operations.md` — §1 governance-aware observability; §2.1 universal log schema; §1.5 replay observability
* `spec/09_security_privacy.md` — §1.2 historical integrity; §1.3 lineage integrity; §3 PII protection; §4 audit survivability
* `spec/05_external_integrations.md` — §2.3 lineage-preserving integration; §3 SQL Server synchronization governance
* `spec/08_data_model.md` — data classification and mutability boundaries per schema tier
* `execution/build_phases.md` — Phase 12 LIVE certification gate; governance-first sequencing
* `execution/implementation_plan.md` — service implementation ordering; SHADOW → LIVE model

---

## END OF FILE
