# directives/core_decision_engine.md

---

## LAYER 3 — DIRECTIVES (ORCHESTRATION-INTELLIGENCE BEHAVIOR)

---

> **Version note:** This file was completely rewritten on 2026-05-25 to reflect the finalized governed historical intelligence platform architecture. The previous version described a legacy outreach trigger engine (contact_attempt-based CALL/SMS/EMAIL triggers, LLM meeting recommendations) that is architecturally incompatible with the governed six-domain lifecycle platform defined in spec/01 through spec/09. The engine is no longer a trigger dispatcher. It is an orchestration-intelligence engine.

---

## 1. PURPOSE

---

### 1.1 What the Engine Is

The **Core Decision Engine** is the **orchestration-intelligence authority** for the Student Success Intelligence Platform. It synthesizes multi-domain inputs — academic, operational, AI, governance, and historical — into **governance-safe orchestration intents** that downstream execution services consume to drive deterministic, auditable, lifecycle-aware actions.

The engine's responsibilities are:

* **Orchestration intent generation** — determining what orchestration action is warranted for a student in a given lifecycle context, expressed as a typed intent that downstream services can execute or reject
* **Governance-safe action determination** — ensuring that every intent produced complies with platform invariants (INVARIANT-1 through INVARIANT-7 in spec/03), lifecycle domain rules (Domains 1–6 in spec/03), and config-bound thresholds (FAD-3, spec/01 §12)
* **Eligibility interpretation** — translating raw academic and operational signals into structured eligibility assessments anchored to the ACTIVE config version
* **Intervention prioritization** — ranking competing intervention pathways by risk-adjusted urgency, using AI insight confidence and historical trend signals where available
* **Escalation routing** — determining when automated orchestration must defer to a human operator and producing the escalation context needed for that routing
* **Orchestration context production** — constructing the full attribution, lineage, and observability context attached to every intent, enabling downstream services to execute with full governance awareness

### 1.2 What the Engine Is NOT

The engine explicitly does NOT:

* **Execute outreach directly** — channel selection (CALL, SMS, EMAIL), GHL API calls, and communication dispatch belong to the outreach orchestration service; the engine produces an intent for that service, not the dispatch itself
* **Mutate student state directly** — state machine transitions (ELIGIBLE → QUEUED, NO_RESPONSE → RETRY, etc.) are the responsibility of the state management service; the engine may recommend transitions but never writes them
* **Execute compliance actions** — compliance deletion, anonymization, and audit trail creation belong exclusively to the Compliance Governance Pathway; the engine may flag a student for compliance review but never initiates compliance execution
* **Publish reports directly** — report generation, publication, and historical regeneration belong to the report orchestration service; the engine provides context for report-readiness decisions, not the generation itself
* **Finalize snapshots directly** — snapshot FINALIZED boundary enforcement belongs to the snapshot orchestration service; the engine provides snapshot-readiness signals, not the finalization write

The engine is **advisory to orchestration services**. Orchestration services enforce governance boundaries, write audit records, and execute side effects. The engine reasons about what should happen; services decide whether and how to make it happen.

---

## 2. INPUT MODEL

---

The decision context is **lineage-aware**. Every input carries metadata establishing its authority class and origin. Inputs from SQL Server (`origin_authority = sql_server_authoritative`) govern eligibility decisions. Platform-supplementary inputs provide context but do not override SQL Server-authoritative state.

---

### 2.1 Operational Inputs

Real-time outreach and engagement state sourced from platform-owned operational tables.

| Field | Type | Authority | Source Table | Description |
|---|---|---|---|---|
| `outreach_state` | enum | `platform_supplementary` | `outreach_tracking` | Current state in the Outreach lifecycle domain (ELIGIBLE through CLOSED) |
| `contact_attempt_count` | integer | `platform_supplementary` | `outreach_tracking` | Total contact attempts made in current cycle |
| `last_contact_timestamp` | datetime | `platform_supplementary` | `outreach_history` | Most recent outreach event timestamp |
| `last_contact_outcome` | enum | `platform_supplementary` | `outreach_history` | Outcome of most recent contact (CONNECTED, NO_ANSWER, VOICEMAIL, etc.) |
| `retry_eligible` | boolean | `platform_supplementary` | derived | Whether retry window has passed per config-bound retry policy |
| `engagement_signal_score` | float | `platform_supplementary` | `student_campaign_activity` | Recent engagement responsiveness score (0.0–1.0) |
| `ghl_last_message_timestamp` | datetime | `platform_supplementary` | `ghl_message_cache` | Most recent inbound GHL message timestamp |
| `campaign_activity_count` | integer | `platform_supplementary` | `student_campaign_activity` | Total outreach campaign interactions |
| `quick_action_history` | list | `platform_supplementary` | `student_quick_action_log` | Recent operator quick actions (ESCALATE, CLOSE_CASE, FORCE_RETRY, etc.) |
| `state_transition_history` | list | `platform_supplementary` | `state_transition_log` | Full outreach state transition log for this student |

---

### 2.2 Academic Inputs

SQL Server-mirrored academic signals. All fields carry `origin_authority = sql_server_authoritative` and govern eligibility decisions.

| Field | Type | Authority | Source | Description |
|---|---|---|---|---|
| `user_id` | integer | `sql_server_authoritative` | `student_trigger_data` | Authoritative student identifier (SQL Server primary key) |
| `checkpoint_type` | string | `sql_server_authoritative` | `student_trigger_data` | Curriculum checkpoint (SQL / SSRS / SSIS / Post-completion) |
| `hws_behind` | integer | `sql_server_authoritative` | `student_trigger_data` | Assignments behind schedule |
| `avg_eff_rating` | float | `sql_server_authoritative` | `student_trigger_data` | Average effort rating (0.0–5.0) |
| `last_activity_days` | integer | `sql_server_authoritative` | `student_trigger_data` | Days since last recorded activity |
| `per_comp_act` | float | `sql_server_authoritative` | `student_trigger_data` | Curriculum completion percentage (used for CAP/Launch eligibility) |
| `cap_start_date` | date | `sql_server_authoritative` | `student_trigger_data` | CAP enrollment start date (NULL if not enrolled) |
| `launch_start_date` | date | `sql_server_authoritative` | `student_trigger_data` | Launch program start date (NULL if not enrolled) |
| `current_section` | string | `sql_server_authoritative` | `student_trigger_data` | Current curriculum section (used for cohort classification) |
| `payment_balance` | decimal | `sql_server_authoritative` | `student_trigger_data` | Outstanding payment balance |
| `class_fees_paid` | decimal | `sql_server_authoritative` | `student_trigger_data` | Total fees paid to date |
| `access_state` | enum | `sql_server_authoritative` | `student_trigger_data` | Current platform access status (ACTIVE, REVOKED, SUSPENDED) |
| `access_last_changed` | datetime | `sql_server_authoritative` | `student_trigger_data` | Timestamp of most recent access state change |
| `cohort_classification` | list | `platform_supplementary` | `student_cohort_memberships` | Platform-derived cohort memberships (CAP_HOPEFUL, LAUNCH_HOPEFUL, etc.) |
| `sql_server_sync_timestamp` | datetime | `sql_server_authoritative` | `student_trigger_data` | Timestamp of the most recent SQL Server sync cycle that updated this record |

> **SQL Server authority rule:** `access_state`, `hws_behind`, `avg_eff_rating`, `last_activity_days`, `per_comp_act`, and `payment_balance` are SQL Server-authoritative for eligibility decisions. Platform-supplementary signals for the same fields must not override these values (INVARIANT-6).

---

### 2.3 AI Inputs

AI insight version state, including staleness metadata and confidence context. AI inputs are **advisory only**; they cannot override SQL Server-authoritative eligibility state or hard governance rules (see §6).

| Field | Type | Description |
|---|---|---|
| `ai_insight_state` | enum | Current lifecycle state of the relevant AI insight record (`AI_REVIEWED`, `AI_GENERATION_FAILED`, `AI_ARCHIVED`, etc.) |
| `ai_insight_version` | integer | `version_number` of the AI insight record; used for staleness tracking |
| `ai_risk_summary` | string | Risk summary text from the most recent `AI_REVIEWED` insight (may be null) |
| `ai_recommended_intervention` | enum | AI's recommended intervention pathway: `NONE`, `OUTREACH`, `MEETING`, `RESOURCE_DELIVERY`, `ESCALATE` |
| `ai_sentiment` | string | Sentiment classification from AI insight |
| `ai_confidence_score` | float | Model-reported confidence (0.0–1.0); drives AI governance tier selection (§6.2) |
| `ai_generated_at` | datetime | Timestamp of AI insight generation |
| `ai_prompt_version` | string | Prompt template version used for this insight |
| `ai_model_used` | string | LLM model identifier used for this insight |
| `ai_stale_flag` | boolean | True if the insight age exceeds `ai_insight_ttl_hours` from the ACTIVE config |
| `ai_ttl_hours` | integer | TTL from the ACTIVE config version; used for staleness assessment |
| `ai_finalized_copy` | boolean | Whether the AI content is a snapshot-frozen physical copy (immutable; must not be regenerated in this context) |
| `ai_input_metrics_hash` | string | Hash of the input metrics used to generate this insight; used for reproducibility verification |

---

### 2.4 Governance Inputs

Governance context is mandatory for every decision evaluation. Decisions produced without full governance context are invalid.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ID of the ACTIVE config version at decision time (must be resolved before rule evaluation begins) |
| `config_version_status` | enum | Status of the resolved config version (`ACTIVE`, `SUPERSEDED`). SUPERSEDED is only valid in replay mode. |
| `config_rule_set` | object | Extracted threshold values from the ACTIVE (or historical) config version's `rule_set_snapshot` |
| `execution_mode` | enum | Platform execution mode: `SHADOW` (default; no outbound effects) or `LIVE` (requires Phase 12 certification) |
| `execution_type` | enum | `original`, `replay`, or `regeneration`; drives replay-safety rules (§7) |
| `correlation_id` | uuid | UUID v4 propagated from the triggering scheduler run or operator action |
| `causation_id` | uuid | UUID v4 of the upstream event that caused this decision evaluation (enables multi-hop lineage; may be null for root events) |
| `attribution_context` | object | Full attribution metadata to be attached to the intent output: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp` |
| `fingerprint_context` | object | Snapshot Reproducibility Fingerprint components at the time of this evaluation; used for replay safety and regeneration validation |
| `idempotency_key` | string | Decision-level idempotency key `(student_id, checkpoint_type, cycle_timestamp)` to prevent duplicate intent production |
| `compliance_hold_flag` | boolean | True if the student's snapshot is currently under `COMPLIANCE_HOLD`; blocks certain orchestration paths |

---

### 2.5 Historical Inputs

Long-term longitudinal signals from finalized snapshots and historical intelligence records.

| Field | Type | Description |
|---|---|---|
| `prior_snapshot_months` | list | List of months for which this student has a FINALIZED snapshot |
| `most_recent_snapshot_state` | enum | State of the most recent snapshot for this student (FINALIZED, GENERATION_FAILED, etc.) |
| `most_recent_snapshot_month` | string | Year-month of the most recent FINALIZED snapshot |
| `historical_risk_trend` | enum | Trend direction derived from prior snapshots: `IMPROVING`, `STABLE`, `DECLINING`, `CRITICAL` |
| `prior_intervention_count` | integer | Total operator interventions recorded for this student across all history |
| `prior_escalation_count` | integer | Total escalations in this student's history |
| `prior_ai_insight_versions` | list | Version history of AI insights for this student (most recent 3 versions); used for sentiment trend analysis |
| `last_intervention_timestamp` | datetime | Most recent operator intervention timestamp |
| `last_resolution_timestamp` | datetime | Most recent RESOLVED or CLOSED outreach timestamp |
| `historical_escalation_patterns` | list | Recurrence of escalation-triggering conditions across prior cycles; used for pattern-based escalation thresholds |

---

## 3. OUTPUT MODEL

---

The engine produces a single **governance-safe orchestration intent** per evaluation. The intent is advisory: it does not execute actions, it does not mutate state, and it does not enforce governance boundaries. Downstream orchestration services consume the intent and are responsible for validation, execution, audit trail creation, and governance enforcement.

---

### 3.1 OrchestrationIntent Schema

```json
{
  "orchestration_intent": "INITIATE_OUTREACH | RETRY_OUTREACH | ESCALATE_TO_OPERATOR | RECOMMEND_INTERVENTION | DEFER_PENDING_AI | CLOSE_ORCHESTRATION | NO_ELIGIBLE_INTENT",
  "intent_confidence": 0.0,
  "recommended_execution_path": "string — the orchestration service and operation being recommended",
  "governance_requirements": {
    "execution_mode": "SHADOW | LIVE",
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "idempotency_key": "string",
    "attribution_anchor": {
      "origin_source": "system_automated | operator | scheduler",
      "origin_authority": "platform_supplementary",
      "actor_identity": "decision_engine_v{N}",
      "attribution_timestamp": "ISO-8601"
    },
    "governance_preconditions_met": true,
    "blocking_governance_flags": []
  },
  "observability_metadata": {
    "correlation_id": "uuid",
    "causation_id": "uuid | null",
    "execution_type": "original | replay | regeneration",
    "decision_version": "string",
    "rule_path_taken": ["RULE_N", "RULE_M"],
    "decision_basis": "RULE_BASED | AI_ASSISTED | FALLBACK | HISTORICAL_REPLAY"
  },
  "escalation_metadata": {
    "escalation_required": false,
    "escalation_urgency": "LOW | MEDIUM | HIGH | CRITICAL",
    "escalation_reason_codes": [],
    "escalation_context": {}
  },
  "attribution_metadata": {
    "origin_source": "system_automated",
    "origin_authority": "platform_supplementary",
    "attribution_timestamp": "ISO-8601",
    "actor_identity": "decision_engine"
  },
  "replay_safety_metadata": {
    "is_replay": false,
    "source_artifact_id": "string | null",
    "historical_config_version_id": "string | null",
    "fingerprint_comparison_outcome": "MATCH | DIVERGENT | UNKNOWN | null",
    "replay_safe": true
  },
  "ai_context": {
    "ai_input_used": false,
    "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | UNAVAILABLE",
    "ai_confidence_score": 0.0,
    "stale_flag": false,
    "fallback_applied": false,
    "ai_version_number": null
  },
  "reason_codes": ["string"],
  "intent_blocked": false,
  "blocking_reason": null
}
```

---

### 3.2 OrchestrationIntent Values

| Intent | Meaning | Downstream consumer |
|---|---|---|
| `INITIATE_OUTREACH` | Student is newly eligible; first orchestrated contact cycle should begin | Outreach orchestration service |
| `RETRY_OUTREACH` | Prior contact was made; retry window has passed; retry is eligible and warranted | Outreach orchestration service |
| `ESCALATE_TO_OPERATOR` | Risk factors or governance conditions require human operator review; automated orchestration deferred | Escalation routing service |
| `RECOMMEND_INTERVENTION` | AI insight or rule-based analysis recommends a specific intervention (meeting, resource delivery, IPBC follow-up); advisory to operator | Operator notification service |
| `DEFER_PENDING_AI` | AI insight is in-flight (`AI_GENERATING`, `AI_PENDING`); decision deferred until AI insight is available | Scheduler / retry queue |
| `CLOSE_ORCHESTRATION` | All retry paths exhausted, or student state is CLOSED, or student is resolved; no further automated orchestration warranted | State management service |
| `NO_ELIGIBLE_INTENT` | No conditions in this cycle trigger any orchestration; no action warranted | None (cycle completes normally) |

---

### 3.3 Key Output Clarifications

* **Decisions are advisory.** The engine's `orchestration_intent` is a recommendation to the consuming service. Orchestration services may reject an intent if current state validation fails (e.g., the student state has advanced since the intent was produced).
* **The engine never writes to the database.** No INSERT, UPDATE, or DELETE arises from the engine's evaluation. All database writes — state transitions, audit log entries, outreach history, idempotency key storage — are the responsibility of consuming services.
* **Intent does not include channel selection.** CALL, SMS, EMAIL, and channel fallback are orchestration-layer concerns determined by the outreach service, not by the decision engine. The engine produces `INITIATE_OUTREACH`; the outreach service selects the channel.
* **The intent carries full governance context.** Every downstream service that consumes the intent receives the full `governance_requirements`, `attribution_metadata`, and `observability_metadata` needed to execute with governance fidelity, without re-querying the engine.

---

## 4. DECISION RULES

---

Rules are evaluated in the order defined below. **Stop at the first terminal rule unless otherwise stated.** Each rule that fires contributes to `rule_path_taken` in `observability_metadata`.

Non-terminal rules (marked `CONTINUE`) may combine with later rules. Terminal rules (marked `STOP`) produce the final intent immediately.

---

### RULE 0 — GOVERNANCE PRECONDITION GATE

**This rule is mandatory. No subsequent rules execute if this rule blocks.**

BLOCK intent production IF:

* `config_version_id` is null (config resolution failed; see §5.4)
* `execution_mode` is not one of `SHADOW`, `LIVE`
* `correlation_id` is null
* `attribution_context` is incomplete (missing any required attribution field)
* `idempotency_key` already exists in the dedup store for this `(student_id, checkpoint_type, cycle_timestamp)`

THEN:

```json
{
  "orchestration_intent": "NO_ELIGIBLE_INTENT",
  "intent_blocked": true,
  "blocking_reason": "GOVERNANCE_PRECONDITION_FAILED",
  "reason_codes": ["CONFIG_UNRESOLVED | EXECUTION_MODE_INVALID | CORRELATION_ID_MISSING | ATTRIBUTION_INCOMPLETE | IDEMPOTENCY_DUPLICATE"]
}
```

STOP.

---

### RULE 1 — TERMINAL STATE CHECK

IF `outreach_state = CLOSED`:

```json
{
  "orchestration_intent": "NO_ELIGIBLE_INTENT",
  "reason_codes": ["OUTREACH_CLOSED_TERMINAL"]
}
```

STOP.

---

### RULE 2 — COMPLIANCE HOLD CHECK

IF `compliance_hold_flag = true`:

```json
{
  "orchestration_intent": "ESCALATE_TO_OPERATOR",
  "escalation_metadata": {
    "escalation_required": true,
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["COMPLIANCE_HOLD_ACTIVE"],
    "escalation_context": {
      "note": "Student snapshot is under COMPLIANCE_HOLD. All automated orchestration is suspended until hold is resolved via the Compliance Governance Pathway."
    }
  },
  "reason_codes": ["COMPLIANCE_HOLD_ACTIVE"]
}
```

STOP.

---

### RULE 3 — CONFIG-BOUND THRESHOLD EXTRACTION

**This rule is non-terminal. Execute before any threshold-dependent rule.**

Resolve from `config_rule_set` (ACTIVE config version's `rule_set_snapshot`):

| Threshold variable | Config key |
|---|---|
| `MAX_ATTEMPTS` | `outreach_max_attempts` |
| `RETRY_WINDOW_HOURS` | `outreach_retry_window_hours` |
| `HWS_BEHIND_RISK_THRESHOLD` | `hws_behind_high_risk_threshold` |
| `AVG_EFF_RATING_RISK_THRESHOLD` | `avg_eff_rating_low_risk_threshold` |
| `INACTIVITY_RISK_DAYS` | `last_activity_high_risk_days` |
| `AI_INSIGHT_TTL_HOURS` | `ai_insight_ttl_hours` |
| `PAYMENT_RISK_BALANCE_THRESHOLD` | `payment_balance_risk_threshold` |
| `ESCALATION_REPEAT_THRESHOLD` | `prior_escalation_repeat_threshold` |
| `RETRY_WINDOW_MODE` | `retry_window_behavior` |

If any threshold is missing from `config_rule_set`, substitute `UNKNOWN_V0` for that threshold, log a `CONFIG_THRESHOLD_MISSING` warning, and continue with rule-based logic excluding rules that depend on the missing threshold.

CONTINUE.

---

### RULE 4 — ACCESS STATE GATE

IF `access_state ≠ ACTIVE` (per SQL Server-authoritative field):

* IF `access_state = REVOKED`:

```json
{
  "orchestration_intent": "ESCALATE_TO_OPERATOR",
  "escalation_metadata": {
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["ACCESS_REVOKED"]
  },
  "reason_codes": ["ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE"]
}
```

STOP.

* IF `access_state = SUSPENDED`:

```json
{
  "orchestration_intent": "NO_ELIGIBLE_INTENT",
  "reason_codes": ["ACCESS_SUSPENDED_AWAIT_RESTORATION"]
}
```

STOP.

---

### RULE 5 — STALE AI ASSESSMENT

**Non-terminal. Determines `ai_governance_tier` used by all subsequent AI-referencing rules.**

| Condition | AI Governance Tier |
|---|---|
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score ≥ 0.70` | `CONFIDENT` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score < 0.70` | `ADVISORY` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = true` | `STALE` |
| `ai_insight_state = AI_GENERATING OR AI_PENDING` | `IN_FLIGHT` — triggers RULE 5A |
| `ai_insight_state = AI_GENERATION_FAILED` OR `ai_insight_state = null` | `UNAVAILABLE` |
| `ai_finalized_copy = true` | `FINALIZED_COPY` — immutable; no regeneration or override permitted |

CONTINUE.

---

### RULE 5A — DEFER PENDING AI (conditional exit from Rule 5)

IF AI governance tier = `IN_FLIGHT` AND `execution_type = original`:

```json
{
  "orchestration_intent": "DEFER_PENDING_AI",
  "reason_codes": ["AI_INSIGHT_IN_FLIGHT"],
  "ai_context": {
    "ai_governance_tier": "IN_FLIGHT"
  }
}
```

STOP. (Do not block orchestration if in replay mode; use STALE tier instead.)

---

### RULE 6 — MAX ATTEMPTS EXHAUSTION CHECK

IF `contact_attempt_count ≥ MAX_ATTEMPTS` (from config-bound threshold):

```json
{
  "orchestration_intent": "CLOSE_ORCHESTRATION",
  "recommended_execution_path": "outreach_service.exhaust_and_close",
  "reason_codes": ["MAX_ATTEMPTS_EXHAUSTED"],
  "escalation_metadata": {
    "escalation_required": true,
    "escalation_urgency": "MEDIUM",
    "escalation_reason_codes": ["MAX_ATTEMPTS_EXHAUSTED_REVIEW_REQUIRED"]
  }
}
```

STOP.

---

### RULE 7 — MULTI-FACTOR RISK ASSESSMENT

**Non-terminal. Produces a risk score used by Rules 8–10.**

Evaluate risk factors against config-bound thresholds (from Rule 3):

| Factor | Condition | Risk contribution |
|---|---|---|
| Homework delinquency | `hws_behind ≥ HWS_BEHIND_RISK_THRESHOLD` | `+HIGH` |
| Effort decline | `avg_eff_rating < AVG_EFF_RATING_RISK_THRESHOLD` | `+MEDIUM` |
| Inactivity | `last_activity_days > INACTIVITY_RISK_DAYS` | `+HIGH` |
| Payment risk | `payment_balance > PAYMENT_RISK_BALANCE_THRESHOLD` | `+MEDIUM` |
| Access risk | `access_last_changed` within 7 days AND `access_state = ACTIVE` | `+LOW` |
| Historical escalation recurrence | `prior_escalation_count ≥ ESCALATION_REPEAT_THRESHOLD` | `+HIGH` |
| Historical trend | `historical_risk_trend = CRITICAL` | `+HIGH`; `= DECLINING` → `+MEDIUM` |
| AI risk signal (CONFIDENT tier only) | `ai_recommended_intervention = ESCALATE` | `+HIGH` |
| AI risk signal (ADVISORY tier only) | `ai_recommended_intervention = ESCALATE` | `+MEDIUM` |
| Stale AI (STALE tier) | AI previously recommended escalation | `+LOW` (logged but not determinative) |

Aggregate risk level:
* 2+ HIGH contributions → `risk_level = CRITICAL`
* 1 HIGH + 1+ MEDIUM → `risk_level = HIGH`
* 0–1 HIGH with MEDIUM contributions → `risk_level = MEDIUM`
* All LOW contributions → `risk_level = LOW`

CONTINUE.

---

### RULE 8 — CRITICAL RISK ESCALATION

IF `risk_level = CRITICAL`:

```json
{
  "orchestration_intent": "ESCALATE_TO_OPERATOR",
  "escalation_metadata": {
    "escalation_required": true,
    "escalation_urgency": "CRITICAL",
    "escalation_reason_codes": ["CRITICAL_RISK_MULTI_FACTOR"],
    "escalation_context": {
      "risk_contributions": ["...enumerated factors from Rule 7..."],
      "ai_governance_tier": "...",
      "historical_risk_trend": "..."
    }
  },
  "reason_codes": ["CRITICAL_RISK_ESCALATION"]
}
```

STOP.

---

### RULE 9 — HIGH RISK ESCALATION (SHADOW/LIVE bifurcation)

IF `risk_level = HIGH`:

* IF `execution_mode = SHADOW`:

```json
{
  "orchestration_intent": "ESCALATE_TO_OPERATOR",
  "escalation_metadata": {
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["HIGH_RISK_SHADOW_MODE"],
    "escalation_context": {
      "note": "SHADOW mode: escalation intent produced; no outbound notification dispatched."
    }
  },
  "governance_requirements": {
    "execution_mode": "SHADOW"
  },
  "reason_codes": ["HIGH_RISK_SHADOW_NO_DISPATCH"]
}
```

STOP.

* IF `execution_mode = LIVE`:

```json
{
  "orchestration_intent": "ESCALATE_TO_OPERATOR",
  "escalation_metadata": {
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["HIGH_RISK_LIVE_ESCALATION"]
  },
  "reason_codes": ["HIGH_RISK_ESCALATION_LIVE"]
}
```

STOP.

---

### RULE 10 — AI-ASSISTED INTERVENTION RECOMMENDATION

IF `ai_governance_tier = CONFIDENT OR ADVISORY` AND `ai_recommended_intervention ∈ {MEETING, RESOURCE_DELIVERY, IPBC_FOLLOWUP}`:

```json
{
  "orchestration_intent": "RECOMMEND_INTERVENTION",
  "recommended_execution_path": "operator_notification_service.deliver_ai_recommendation",
  "ai_context": {
    "ai_input_used": true,
    "ai_governance_tier": "...",
    "ai_confidence_score": 0.0,
    "ai_recommended_intervention": "MEETING | RESOURCE_DELIVERY | IPBC_FOLLOWUP"
  },
  "reason_codes": ["AI_ASSISTED_INTERVENTION_RECOMMENDED"]
}
```

> This rule is **CONTINUE**, not STOP. An AI-assisted intervention recommendation may be combined with a retry advisory (Rule 11) if retry is also eligible. Orchestration services must handle combined intents; final execution decision belongs to the service.

CONTINUE (may combine with Rule 11).

---

### RULE 11 — RETRY ELIGIBILITY ADVISORY

IF `contact_attempt_count > 0` AND `contact_attempt_count < MAX_ATTEMPTS` AND `retry_eligible = true`:

```json
{
  "orchestration_intent": "RETRY_OUTREACH",
  "recommended_execution_path": "outreach_service.schedule_retry",
  "governance_requirements": {
    "idempotency_key": "...",
    "execution_mode": "..."
  },
  "reason_codes": ["RETRY_ELIGIBLE_WINDOW_PASSED"]
}
```

STOP (unless combined with Rule 10 intent from CONTINUE path).

---

### RULE 12 — FIRST OUTREACH ELIGIBILITY

IF `contact_attempt_count = 0` AND `outreach_state ∈ {ELIGIBLE, QUEUED}`:

```json
{
  "orchestration_intent": "INITIATE_OUTREACH",
  "recommended_execution_path": "outreach_service.initiate_first_contact",
  "governance_requirements": {
    "idempotency_key": "...",
    "execution_mode": "...",
    "config_version_id": "..."
  },
  "reason_codes": ["FIRST_OUTREACH_ELIGIBLE"]
}
```

STOP.

---

### RULE 13 — REPLAY MODE SAFETY GATE

**This rule fires only when `execution_type ∈ {replay, regeneration}`.**

Before any intent is emitted in replay mode:

1. Confirm `config_version_id` matches the historical config reference for the replay period — not the current ACTIVE config.
2. Confirm `fingerprint_context` is populated with the historical snapshot's stored fingerprint components.
3. Confirm `execution_mode = SHADOW` — replay execution must never be `LIVE`.
4. Override any `orchestration_intent` that would produce outbound side effects: downgrade to `NO_ELIGIBLE_INTENT` with `execution_type = replay`.

IF replay preconditions are violated:

```json
{
  "orchestration_intent": "NO_ELIGIBLE_INTENT",
  "intent_blocked": true,
  "blocking_reason": "REPLAY_PRECONDITION_VIOLATED",
  "reason_codes": ["REPLAY_CONFIG_MISMATCH | REPLAY_LIVE_MODE_BLOCKED | REPLAY_FINGERPRINT_MISSING"]
}
```

STOP.

---

### RULE 14 — DEFAULT

IF no prior rule produced a terminal intent:

```json
{
  "orchestration_intent": "NO_ELIGIBLE_INTENT",
  "reason_codes": ["NO_ELIGIBLE_ACTION_THIS_CYCLE"]
}
```

STOP.

---

## 5. CONFIG VERSION GOVERNANCE

---

### 5.1 Config Resolution Protocol

At the start of every decision evaluation, before Rule 0 executes, the engine MUST:

1. Query the Config Version Registry for the **currently ACTIVE version** (`status = ACTIVE`)
2. Extract the full `rule_set_snapshot` from the ACTIVE version record
3. Bind the `config_version_id` to the decision context; this ID is carried through all outputs and into the orchestration intent's `governance_requirements`
4. Validate that exactly one `ACTIVE` version exists; if zero or two exist, emit `GOVERNANCE_PRECONDITION_FAILED` and stop

Config resolution failure is never silently ignored. A decision produced without a resolved config version is invalid and must not be consumed by orchestration services.

---

### 5.2 Config-Bound Threshold Usage

All threshold comparisons (Rules 3, 6, 7, 8, 9, 11, 12) MUST use values extracted from the resolved config version's `rule_set_snapshot`, not hardcoded defaults. The rule evaluation is config-version dependent: the same student with the same academic signals may produce different intents under different config versions. This is expected behavior (FAD-3).

---

### 5.3 Config Lineage in Output

Every orchestration intent carries `config_version_id` in `governance_requirements`. This enables downstream services and audit consumers to verify which thresholds governed a particular decision, at any point in time, without re-executing the engine.

---

### 5.4 Historical Replay Config Semantics

In replay mode (`execution_type ∈ {replay, regeneration}`):

* The engine MUST use the **historical config version** bound to the source snapshot's fingerprint, not the current ACTIVE version
* If the historical config version is `SUPERSEDED` or `ARCHIVED`, it remains valid for replay purposes; its `rule_set_snapshot` is fully queryable per spec/03 §32.3
* If the historical config version is unavailable (corrupted, missing), replay is blocked — `REPLAY_CONFIG_UNAVAILABLE`
* A replay run that uses the current ACTIVE config instead of the historical config is a **reproducibility defect** and violates FAD-3

---

### 5.5 Prospective-Only Config Semantics (FAD-3 Enforcement)

Activating a new config version does NOT:
* Retroactively change historical decision outputs
* Recalculate thresholds for historical outreach records
* Alter finalized snapshot cohort classifications
* Trigger reprocessing of any prior student data

The engine's config-bound decisions take effect at the next scheduled evaluation cycle after the new version becomes ACTIVE. Prior decisions, and the records they produced, are permanently attributed to the config version in effect when they were made.

---

## 6. AI GOVERNANCE

---

### 6.1 AI Governance Principle

AI insight output is **advisory**. It cannot:

* Override SQL Server-authoritative eligibility state
* Override config-bound threshold evaluations
* Override state machine transition validity rules
* Produce `LIVE` execution intents unilaterally
* Modify or invalidate historical decisions produced under prior config versions

AI insight output CAN:
* Raise the escalation urgency tier (from MEDIUM to HIGH) when AI governance tier is CONFIDENT
* Recommend specific intervention pathways (RECOMMEND_INTERVENTION intents)
* Provide contextual signals for operator notification payloads
* Inform the `intent_confidence` score of AI-influenced intents

---

### 6.2 AI Governance Tier Behavior

| Tier | Behavior |
|---|---|
| `CONFIDENT` (≥ 0.70 confidence, fresh) | AI signals used directly in Rules 7 and 10; intervention recommendations produced |
| `ADVISORY` (< 0.70 confidence, fresh) | AI signals logged and noted but carry reduced weight; escalation raised only one urgency tier, not two |
| `STALE` (beyond TTL or AI_GENERATION_FAILED with prior) | Prior insight served with `stale: true`; used for LOW risk contribution only; cannot drive `LIVE` orchestration intents |
| `UNAVAILABLE` (no prior AI_REVIEWED) | Pure rule-based logic only; AI signals not applied; `fallback_applied = true` in output |
| `IN_FLIGHT` | Decision deferred (DEFER_PENDING_AI); no AI signal applied |
| `FINALIZED_COPY` | Snapshot-frozen text; immutable; never used as input for new decisions; only relevant to report regeneration context |

---

### 6.3 Stale AI Protection in LIVE Mode

IF `execution_mode = LIVE` AND `ai_governance_tier = STALE` AND `ai_recommended_intervention ≠ NONE`:

* The stale AI recommendation MUST NOT produce an `INITIATE_OUTREACH` or `RETRY_OUTREACH` intent based solely on AI input
* A `RECOMMEND_INTERVENTION` intent MAY be produced with `stale_flag = true` and a recommendation to refresh the AI insight first
* The operator notification must include the staleness flag and the `ai_generated_at` timestamp so the operator is aware the recommendation is based on outdated analysis

---

### 6.4 AI Snapshot Isolation (FAD-1 Enforcement)

When `ai_finalized_copy = true` (the AI content was physically copied into a FINALIZED snapshot):

* The engine MUST NOT request, apply, or reference live `ai_insights` records for this student in the same evaluation context
* The frozen copy is used exclusively by report generation and historical regeneration services — not by the decision engine in its orchestration role
* Force-refresh of `ai_insights` records has zero effect on any decision that already produced an intent in a prior cycle

---

### 6.5 Deterministic Fallback

When AI input is `UNAVAILABLE` or `STALE`, the engine MUST produce a deterministic rule-based output using only SQL Server-authoritative signals and config-bound thresholds. The fallback path is not a degraded mode — it is a fully specified decision path that must satisfy the same correctness and reproducibility requirements as the AI-assisted path.

The `ai_context.fallback_applied = true` flag in the output enables downstream services and operators to identify evaluations that operated without current AI assistance.

---

## 7. REPLAY & REGENERATION SEMANTICS

---

### 7.1 Execution Types

| Execution type | Meaning | Key constraints |
|---|---|---|
| `original` | First-time evaluation of a live decision cycle | Uses ACTIVE config; may produce `LIVE` or `SHADOW` intents |
| `replay` | Re-executing a historical decision context for verification or audit | Must use historical config version; `execution_mode` forced to `SHADOW`; no outbound effects |
| `regeneration` | Reconstructing a report or snapshot output from historical data | Historical fingerprint used; no new LLM calls; AI content sourced from physical snapshot copy |

---

### 7.2 Replay Execution Rules

A replay evaluation MUST:

1. Use the config version from the source snapshot's fingerprint (`config_registry_version` component of FAD-6 fingerprint)
2. Use the AI insight version and prompt version from the source snapshot's fingerprint (`ai_prompt_version`, `ai_model_version` components)
3. Set `execution_mode = SHADOW` unconditionally; replay runs never produce `LIVE` intents
4. Set `ai_finalized_copy = true` if the AI content is sourced from a FINALIZED snapshot — the engine must not request fresh AI analysis
5. Record `execution_type = replay` in all output observability metadata
6. Not create new idempotency keys in the operational store — replay evaluations are read-only with respect to state
7. Not produce `INITIATE_OUTREACH`, `RETRY_OUTREACH`, or `CLOSE_ORCHESTRATION` intents with outbound side effects

A replay evaluation MAY:
* Produce `NO_ELIGIBLE_INTENT` with `execution_type = replay` to confirm no action was warranted historically
* Surface `RECOMMEND_INTERVENTION` intents for audit visibility (operator-facing; no dispatch)
* Record `fingerprint_comparison_outcome` to flag whether the historical and current system fingerprints match

---

### 7.3 Regeneration Semantics

Historical report regeneration is executed by the report orchestration service, not by the decision engine. However, the decision engine MAY be invoked during regeneration context to validate historical decision inputs. In this context:

* The engine operates in `execution_type = regeneration`, `execution_mode = SHADOW`
* Historical config version is used, not the current ACTIVE version
* AI content is sourced exclusively from snapshot physical copies — no live `ai_insights` queries
* If the stored fingerprint differs from the current system fingerprint, `fingerprint_comparison_outcome = DIVERGENT` is produced; this does not block regeneration but annotates it with `POTENTIALLY_DIVERGENT`
* Regeneration context MUST NOT create new outreach history records, state transitions, or any governance-sensitive writes

---

### 7.4 SHADOW Execution Semantics

SHADOW mode is the default for all evaluations until Phase 12 certification (per `execution/build_phases.md` Phase 12 and `execution/implementation_plan.md` §8). In SHADOW mode:

* All decision rules evaluate normally
* Orchestration intents are produced normally and delivered to consuming services
* Consuming services MUST NOT dispatch real outbound communications
* The `execution_mode = SHADOW` field in `governance_requirements` is the gate signal for outbound dispatch suppression — consuming services are responsible for respecting it
* Governance audit log entries ARE written in SHADOW mode; a SHADOW execution is a real platform event with real audit requirements
* The decision engine carries no responsibility for SHADOW enforcement; it carries the mode flag and trusts consuming services to enforce it

---

### 7.5 Replay Traceability

Every replay execution must produce a log entry distinguishable from the original execution (spec/06 §1.5):

* `execution_type: replay` in observability metadata
* `source_artifact_id` referencing the original snapshot or job
* `fingerprint_comparison_outcome` in `replay_safety_metadata`
* The same `correlation_id` propagation rules apply; replay jobs generate their own `correlation_id` and set `causation_id` to the original job's `correlation_id`

---

## 8. OBSERVABILITY & ATTRIBUTION

---

### 8.1 Required Telemetry per Evaluation

Every decision evaluation MUST emit a structured log entry (JSON, to stdout per spec/06 §2) covering:

| Log field | Source |
|---|---|
| `timestamp` | ISO-8601 at evaluation start |
| `level` | `info` (normal), `warn` (fallback/stale), `error` (governance gate failure) |
| `service` | `decision_engine` |
| `event` | `orchestration_intent_produced` or `governance_precondition_failed` |
| `correlation_id` | From `governance_inputs.correlation_id` |
| `causation_id` | From `governance_inputs.causation_id` (null if root event) |
| `student_id_opaque` | Opaque hash of the student ID — never the raw SQL Server user_id |
| `execution_type` | `original`, `replay`, or `regeneration` |
| `execution_mode` | `SHADOW` or `LIVE` |
| `config_version_id` | ID of the resolved config version |
| `orchestration_intent` | The intent value produced |
| `intent_confidence` | Float |
| `ai_governance_tier` | Tier from Rule 5 |
| `risk_level` | Risk level from Rule 7 |
| `rule_path_taken` | Array of rule IDs that fired |
| `decision_basis` | `RULE_BASED`, `AI_ASSISTED`, `FALLBACK`, or `HISTORICAL_REPLAY` |
| `duration_ms` | Evaluation duration |
| `outcome` | `success`, `blocked`, `fallback` |
| `error_class` | Populated only on `error` level |

---

### 8.2 Correlation ID Propagation

The `correlation_id` assigned at the triggering scheduler run or operator action entry point MUST propagate without modification through:

* The decision context inputs
* The orchestration intent output
* Every downstream service call that consumes the intent
* Every database write and audit log entry produced by consuming services

The `causation_id` in multi-hop workflows is the parent event's `correlation_id`. The causal chain from scheduler run to decision intent to outreach dispatch to state transition to audit log must be reconstructable from a single `correlation_id` query.

---

### 8.3 Attribution Propagation

The attribution fields set in the decision context (`origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`) MUST propagate to every downstream record created as a result of consuming this intent. The decision engine sets the attribution at the `system_automated` / `platform_supplementary` tier; consuming services append their own actor identity but do not overwrite the engine's attribution context.

Consuming services MUST NOT accept `origin_source = mirrored_sql_server` or `origin_authority = sql_server_authoritative` from client callers — those values are set only by the SQL Server sync service.

---

### 8.4 Governance Transition Log Entries

When the engine produces an intent that results in a governance boundary crossing (any domain transition toward an irreversible state), the consuming service MUST produce a governance telemetry entry in addition to the operational log entry (spec/06 §1.2). The governance entry carries:

* `event_type: governance_boundary_crossed`
* `domain`: the lifecycle domain affected
* `transition`: the from/to state
* `authorized_by`: actor identity
* `correlation_id` from the producing intent
* `config_version_id` from the producing intent
* `fingerprint_context` if applicable (snapshot domain)

The decision engine produces the context needed for these entries; it does not write them. Consuming services are responsible for the writes.

---

### 8.5 PII Redaction Rules

The following fields MUST NEVER appear in log output, telemetry, or observability metadata:

* Raw `user_id` (SQL Server primary key) → substitute `student_id_opaque` (opaque hash)
* Student email address → `***@***`
* Student phone number → `***`
* Student name → `[REDACTED]`
* AI-generated narrative text → NEVER in logs; AI content is stored only in the database, never in log streams
* Raw payment amounts with student context → aggregate only; no per-student payment values in logs

PII redaction applies equally to SHADOW and LIVE mode, to original and replay executions, and to all log levels including debug.

---

## 9. FAILURE & SAFETY SEMANTICS

---

### 9.1 Missing Data Behavior

| Missing field | Response |
|---|---|
| `config_version_id` | Block evaluation (Rule 0 GOVERNANCE_PRECONDITION_FAILED); do not default to any version |
| `sql_server_authoritative` academic fields (all null) | Block evaluation; emit `MISSING_SQL_SERVER_DATA`; do not substitute platform estimates |
| `outreach_state` null | Default to `ELIGIBLE` with reason code `OUTREACH_STATE_UNKNOWN`; log warning |
| `ai_insight_state` null | Set `ai_governance_tier = UNAVAILABLE`; fallback applies |
| `correlation_id` null | Block evaluation (Rule 0) |
| Historical inputs absent | Continue without historical enrichment; set `historical_risk_trend = UNKNOWN`; log warning |

Missing data from SQL Server-authoritative sources blocks evaluation. Missing data from supplementary or historical sources triggers fallback behavior. Unblocked evaluations with missing supplementary data must include `MISSING_DATA_FALLBACK_APPLIED` in `reason_codes`.

---

### 9.2 Stale SQL Server Data

IF `sql_server_sync_timestamp` is older than `sql_server_max_sync_age_hours` (from config):

* Emit `STALE_SQL_SERVER_DATA` warning in log
* Proceed with evaluation but include `STALE_DATA_WARNING` in `reason_codes`
* Do NOT produce `LIVE` intents based on stale SQL Server data; downgrade to `SHADOW` with `STALE_DATA_SHADOW_OVERRIDE`
* Alert operational telemetry so the sync service can be triggered

---

### 9.3 Invalid AI Input

IF AI insight schema validation fails (unexpected structure, missing required fields):

* Set `ai_governance_tier = UNAVAILABLE`
* Set `ai_context.fallback_applied = true`
* Log `AI_INVALID_SCHEMA` at `warn` level
* Continue with rule-based evaluation; AI signals not applied
* Do not propagate the invalid AI structure to consuming services

---

### 9.4 Config Resolution Failure

IF the Config Version Registry returns zero or multiple ACTIVE versions:

* Block evaluation unconditionally (Rule 0)
* Log `CONFIG_REGISTRY_INCONSISTENT` at `error` level with `error_class: ContractViolation`
* Emit escalation alert to operator notification service
* Do NOT default to any hardcoded threshold values
* Retry is permitted; if 3 consecutive resolution failures occur, escalate as a production incident

---

### 9.5 Replay Failure Behavior

| Replay failure scenario | Behavior |
|---|---|
| Historical config version unavailable | Block replay; emit `REPLAY_CONFIG_UNAVAILABLE`; do not substitute current ACTIVE version |
| Fingerprint components incomplete | Proceed with available components; log `REPLAY_FINGERPRINT_PARTIAL`; mark `fingerprint_comparison_outcome = UNKNOWN` |
| Replay produces `LIVE` execution mode | Override to `SHADOW`; log `REPLAY_MODE_OVERRIDE`; never allow live dispatch from replay context |
| Historical student state unavailable | Block replay; emit `REPLAY_STATE_UNAVAILABLE`; do not reconstruct from current state |

---

### 9.6 Orchestration Service Failure Feedback

If a consuming orchestration service rejects an intent (e.g., student state has advanced since the intent was produced), the service notifies the engine via the rejection feedback channel. The engine MUST NOT automatically re-evaluate; the scheduler triggers the next evaluation at the next cycle. Premature re-evaluation produces duplicate idempotency key violations and is prohibited.

---

## 10. ARCHITECTURE PRESERVATION RULES

---

The following prohibitions are absolute. No implementation code, configuration change, or emergency workaround may violate them. A violation is a production defect requiring immediate rollback.

| Rule | Prohibition |
|---|---|
| `AP-D1` | The decision engine MUST NOT directly write to any database table. All writes are performed by consuming orchestration services. |
| `AP-D2` | The decision engine MUST NOT execute outbound communications (GHL API calls, SMS, email dispatches). Channel selection and dispatch are the outreach service's responsibility. |
| `AP-D3` | The decision engine MUST NOT mutate outreach state. State machine transitions are the state management service's responsibility. |
| `AP-D4` | The decision engine MUST NOT initiate or execute compliance actions. Compliance execution belongs to the Compliance Governance Pathway and its dedicated service account. |
| `AP-D5` | The decision engine MUST NOT publish, approve, or regenerate reports. Report lifecycle transitions belong to the report orchestration service. |
| `AP-D6` | The decision engine MUST NOT finalize snapshots. The VALIDATING → FINALIZED transition belongs to the snapshot orchestration service and must be executed by the finalization service account. |
| `AP-D7` | The decision engine MUST NOT modify the Config Version Registry. Config lifecycle transitions (PROPOSED → UNDER_REVIEW → APPROVED → ACTIVE) are operator-initiated governance workflows. |
| `AP-D8` | The decision engine MUST NOT produce `LIVE` intents during replay or regeneration execution. `execution_type ∈ {replay, regeneration}` unconditionally forces `execution_mode = SHADOW`. |
| `AP-D9` | The decision engine MUST NOT use hardcoded threshold values. All threshold comparisons must use values extracted from the resolved config version's `rule_set_snapshot`. |
| `AP-D10` | The decision engine MUST NOT log raw student PII (user_id, name, email, phone, AI narrative content). Only opaque student identifiers and aggregated signals are permitted in log output. |
| `AP-D11` | The decision engine MUST NOT override SQL Server-authoritative eligibility state with platform-supplementary signals for access, enrollment, or academic metrics. |
| `AP-D12` | The decision engine MUST NOT produce intents based on AI signals alone for `LIVE` mode when AI governance tier is `STALE` or `UNAVAILABLE`. |
| `AP-D13` | The decision engine MUST NOT overwrite, discard, or reinterpret attribution fields on inputs. Attribution is set at origin and propagated unchanged. |
| `AP-D14` | The decision engine MUST NOT reuse idempotency keys across cycles. Each `(student_id, checkpoint_type, cycle_timestamp)` key is unique and stored before the evaluation completes. |
| `AP-D15` | The decision engine MUST NOT execute if the GOVERNANCE PRECONDITION GATE (Rule 0) has not passed. No rule evaluation, no intent production, and no telemetry beyond the BLOCKED log entry. |

---

## 11. SCOPE BEHAVIOR

---

### 11.1 Across All Scopes (Non-Negotiable)

Regardless of scope tier, the following are mandatory and cannot be reduced:

* Three-schema PostgreSQL architecture and SQL Server read-only boundary (FAD-5)
* SHADOW execution mode as default (LIVE requires Phase 12 certification)
* Config V1 seed as the ACTIVE version at initialization (governance invariant: exactly one ACTIVE)
* Idempotency keys enforced from the first evaluation
* Attribution fields carried on every intent
* GOVERNANCE PRECONDITION GATE (Rule 0) evaluated before any rule
* PII redaction rules in all log output
* INVARIANT-1 through INVARIANT-7 from spec/03 §40

---

### 11.2 MVP Scope

MVP scope MAY reduce:

| Reduced behavior | What is acceptable |
|---|---|
| AI sophistication | `ai_governance_tier` always `UNAVAILABLE`; pure rule-based evaluation only |
| Orchestration depth | Rules 10 (AI intervention recommendation) and 5A (defer pending AI) are no-ops |
| Retry sophistication | `RETRY_WINDOW_HOURS` defaults to 24h if not in config; retry logic remains active |
| Historical inputs | Prior snapshot history absent; `historical_risk_trend = UNKNOWN` |
| Escalation routing | Escalation intents produced but escalation notification service may be stub only |

MVP scope MAY NOT:

* Skip config resolution (Rule 0 + Rule 3 are mandatory)
* Hardcode any threshold
* Violate lineage guarantees on intent outputs
* Produce `LIVE` intents
* Skip idempotency key storage

---

### 11.3 STANDARD Scope

STANDARD scope enables over MVP:

* AI governance tier `CONFIDENT` and `ADVISORY` active; Rule 10 produces live intervention recommendations
* Retry rules fully active with config-bound `RETRY_WINDOW_HOURS`
* Historical inputs active (prior snapshot trend available)
* Risk level MEDIUM handling produces intents (not silently skipped)
* Escalation routing service operational; escalation intents dispatched to operators

STANDARD scope MAY NOT produce LIVE outbound intents. `execution_mode` remains `SHADOW` until Phase 12.

---

### 11.4 PRODUCTION Scope

PRODUCTION scope enables over STANDARD:

* `execution_mode = LIVE` permitted after Phase 12 production governance certification
* Full multi-factor risk scoring with all AI governance tiers active
* Historical escalation pattern analysis (Rule 7 recurrence threshold)
* Operator review gate for CRITICAL escalation before orchestration execution
* Full replay and regeneration semantics active
* Fingerprint comparison logging for all regeneration contexts
* Full RBAC enforcement on which roles may consume which intent classes

---

## 12. ACCEPTANCE CRITERIA

---

### AC-1 — Deterministic Orchestration Outputs

**Given** the same student context, the same config version, and the same AI governance tier
**When** the decision engine is evaluated twice with identical inputs
**Then** the output `orchestration_intent`, `reason_codes`, `risk_level`, and `rule_path_taken` are identical; no non-deterministic elements appear in the output

---

### AC-2 — Replay-Safe Execution

**Given** a replay evaluation context with a historical config version and `execution_type = replay`
**When** the engine evaluates
**Then** the output carries `execution_mode = SHADOW` unconditionally; `execution_type = replay` appears in observability metadata; no outbound-effect intents (`INITIATE_OUTREACH`, `RETRY_OUTREACH`) are produced with LIVE execution mode; the historical config version's thresholds govern all rule evaluations

---

### AC-3 — Attribution Continuity

**Given** a decision evaluation with a populated attribution context
**When** the intent is produced
**Then** the intent's `attribution_metadata` carries the same `origin_source`, `origin_authority`, and `attribution_timestamp` from the input context; the fields are not overwritten, augmented, or cleared by the engine; the `correlation_id` appears in both the intent and the corresponding log entry

---

### AC-4 — Config-Version Reproducibility

**Given** a historical evaluation context referencing a `SUPERSEDED` config version
**When** the engine evaluates in replay mode
**Then** the thresholds extracted from the `SUPERSEDED` version's `rule_set_snapshot` govern all rule evaluations; the current ACTIVE version's thresholds are not consulted; the output `config_version_id` matches the historical version, not the current ACTIVE

---

### AC-5 — Immutable Historical Protection

**Given** an evaluation context where `compliance_hold_flag = true`
**When** the engine evaluates
**Then** the intent is `ESCALATE_TO_OPERATOR` with reason code `COMPLIANCE_HOLD_ACTIVE`; no `INITIATE_OUTREACH`, `RETRY_OUTREACH`, or `CLOSE_ORCHESTRATION` intents are produced; Rule 2 fires and the evaluation stops

---

### AC-6 — Stale-AI Protection in LIVE Mode

**Given** `execution_mode = LIVE` and `ai_governance_tier = STALE`
**When** the engine evaluates
**Then** the AI recommendation does not produce `INITIATE_OUTREACH` or `RETRY_OUTREACH` intents; if an intervention is recommended, the intent is `RECOMMEND_INTERVENTION` with `stale_flag = true`; the `reason_codes` include `STALE_AI_FALLBACK_APPLIED`

---

### AC-7 — SHADOW-vs-LIVE Separation

**Given** `execution_mode = SHADOW`
**When** `ESCALATE_TO_OPERATOR` or `INITIATE_OUTREACH` intent is produced
**Then** the `governance_requirements.execution_mode = SHADOW` is present in the intent; the consuming service is responsible for blocking outbound dispatch; the decision engine's audit log confirms the intent was produced in SHADOW mode

---

### AC-8 — Governance Precondition Blocking

**Given** `config_version_id` cannot be resolved (Config Version Registry returns zero ACTIVE versions)
**When** the engine evaluates
**Then** the evaluation is blocked at Rule 0; `intent_blocked = true` and `blocking_reason = GOVERNANCE_PRECONDITION_FAILED` appear in the output; no subsequent rules execute; no orchestration intent is produced

---

### AC-9 — SQL Server Authority Boundary

**Given** a student whose SQL Server-authoritative `access_state = REVOKED` and whose platform-supplementary records indicate an active outreach is in progress
**When** the engine evaluates
**Then** Rule 4 fires; `orchestration_intent = ESCALATE_TO_OPERATOR` with `reason_codes = [ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE]`; no outreach or retry intent is produced; the SQL Server-authoritative value governs over any platform-supplementary signal

---

## 13. DOWNSTREAM IMPLICATIONS

---

### 13.1 Outreach Orchestration Service

The outreach service is the primary consumer of `INITIATE_OUTREACH` and `RETRY_OUTREACH` intents. Implications:

* Must accept `governance_requirements.execution_mode` and enforce SHADOW suppression of outbound dispatch
* Must store the `idempotency_key` from the intent before executing any GHL API call
* Must produce `outreach_history` records with the `correlation_id` and `attribution_metadata` from the intent
* Must validate the student's current outreach state has not advanced before executing the intent (state may have changed between intent production and consumption)
* Channel selection (CALL / SMS / EMAIL / fallback chain) is the outreach service's responsibility, not the engine's

### 13.2 Timeline Ingestion Service

Timeline ingestion must propagate `origin_source` and `origin_authority` from all events it ingests. The decision engine relies on `student_campaign_activity` and `state_transition_log` as operational inputs (§2.1). Ingestion failures that break attribution on timeline events will degrade the operational input quality and may trigger `MISSING_DATA_FALLBACK_APPLIED` in decision outputs.

### 13.3 Snapshot Orchestration Service

The snapshot service does not directly consume decision engine intents. However:

* Snapshot finalization requires `AI_REVIEWED` AI insight state (Phase 5/6 interlocking per spec/03 §27.3)
* The decision engine's `DEFER_PENDING_AI` intent may signal that the AI insight necessary for snapshot finalization is not yet available
* The `config_version_id` produced by the engine aligns with the same config version that snapshot finalization binds to the Reproducibility Fingerprint
* The engine's `compliance_hold_flag` check (Rule 2) provides the signal that prevents orchestration from proceeding when a student's snapshot is under COMPLIANCE_HOLD

### 13.4 Report Generation Service

The report service does not directly consume decision engine intents in the operational flow. However:

* In regeneration context, the decision engine's replay semantics (§7.3) define which config version, AI version, and fingerprint context to use
* The `POTENTIALLY_DIVERGENT` flag in replay safety metadata corresponds to the same `POTENTIALLY_DIVERGENT` annotation the report service applies to regenerated reports
* The engine's `fingerprint_comparison_outcome` in replay mode is the signal for this flag

### 13.5 Observability Infrastructure

The decision engine's log output (§8.1) feeds operational telemetry for:

* Intent distribution dashboards (what fraction of evaluations produce each intent type)
* AI governance tier distribution (signals when AI freshness degrades fleet-wide)
* Config version adoption tracking (which version governs which evaluations)
* SHADOW vs LIVE intent distribution (readiness signal for Phase 12 certification)
* Rule path distribution (identifies which rules fire most frequently; signals threshold calibration needs)

### 13.6 API Contract Implications

The `GET /students/{id}/orchestration-context` and related read endpoints (spec/07) must return the resolved orchestration intent in a format consistent with the OrchestrationIntent schema (§3.1). The API contract cannot expose raw `user_id` values — opaque student identifiers must be used per PII rules (§8.5).

---

## 14. UNRESOLVED ARCHITECTURAL CONCERNS

---

The following concerns block full PRODUCTION scope enablement or introduce risk at STANDARD scope. Each is carried from prior architectural work (spec/09_security_privacy.md and execution/implementation_plan.md).

| ID | Category | Description | Blocking tier |
|---|---|---|---|
| `US-1` | Authentication | Authentication mechanism for decision engine consumers not specified. JWT vs session vs API key affects how `actor_identity` is populated in attribution context. | PRODUCTION |
| `US-2` | SQL Server RBAC | SQL Server read-only boundary must be verified at SQL Server RBAC level, not only application-level connection config. Engine relies on SQL Server authority being genuine. | PRODUCTION |
| `UD-1` | Config Threshold Coverage | The `rule_set_snapshot` schema for config versions must include all thresholds referenced in Rule 3 (§4). If any threshold is missing from V1, decisions will emit `CONFIG_THRESHOLD_MISSING` warnings for every evaluation. Config version V1 seed schema must be audited against Rule 3's full threshold list. | STANDARD |
| `UD-2` | AI Staleness Threshold | `AI_INSIGHT_TTL_HOURS` is config-bound but not specified in V1 seed. Until specified, the engine cannot determine `ai_governance_tier = STALE` deterministically. | STANDARD |
| `UD-3` | Opaque Student ID Hashing | The hashing scheme for `student_id_opaque` in log output is not yet specified (UO-3 from prior sessions). Decision engine log output must be consistent with whatever scheme is adopted. | PRODUCTION |
| `UD-4` | Escalation Delivery | `ESCALATE_TO_OPERATOR` intents require an escalation routing service. The delivery mechanism (email, PagerDuty, Slack, in-app notification) is unresolved (UO-4 from prior sessions). Intents will be produced but may not be consumed if the routing service is a stub. | STANDARD |
| `UD-5` | Replay Config Availability | If a historical config version is `ARCHIVED` and its `rule_set_snapshot` is no longer accessible in the registry, replay evaluations will fail with `REPLAY_CONFIG_UNAVAILABLE`. The retention policy for config version records must guarantee availability for the full replay window. | PRODUCTION |

---

## 15. REFERENCES

---

This directive governs the orchestration-intelligence behavior of the SSIP decision engine. It depends on and is superseded by the following in case of conflict (highest to lowest precedence):

* `spec/03_state_transition_rules.md` — §40 INVARIANT-1 through INVARIANT-7; all domain lifecycle rules; Domain 5 config version governance; §39 attribution standard
* `spec/01_requirements.md` — FAD-1 through FAD-6; §2.4 cohort identification rules; §4 NFRs; §12 configurable rule governance
* `spec/04_idempotency_concurrency.md` — §4 idempotency keys; §20 event attribution; §23 execution mode interactions
* `spec/06_observability_operations.md` — §1 governance-aware observability; §2.1 universal log schema; §1.5 replay observability
* `spec/09_security_privacy.md` — §1.2 historical integrity; §1.3 lineage integrity; §3 PII protection; §4 audit survivability
* `spec/05_external_integrations.md` — §2.3 lineage-preserving integration; §3 SQL Server synchronization governance
* `spec/08_data_model.md` — data classification and mutability boundaries per schema tier
* `execution/build_phases.md` — Phase 12 LIVE certification gate; governance-first sequencing
* `execution/implementation_plan.md` — service implementation ordering; SHADOW → LIVE model

---

## END OF FILE
