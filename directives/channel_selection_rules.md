# directives/channel_selection_rules.md

---

## LAYER 3 — DIRECTIVES (CHANNEL ORCHESTRATION ADVISORY ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-25 to reflect the finalized governed historical intelligence platform architecture established in `directives/core_decision_engine.md`, `directives/outreach_eligibility_rules.md`, and `directives/outreach_retry_policy.md`. The previous version described a communication-channel execution strategy (CALL → SMS → EMAIL sequencing, hardcoded fallback logic, scope-gated `selected_channel` output) that is architecturally incompatible with the governance-aware orchestration-intelligence platform defined in spec/01 through spec/09. Channel selection is no longer a routing executor. It is governance-aware channel advisement for orchestration candidates.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **Channel Orchestration Advisory Architecture** defines the channel advisement layer of the Student Success Intelligence Platform. It specifies:

* How channel candidacy is assessed for a student entering outreach or retry orchestration
* What governance preconditions must hold before channel advisement may proceed
* How config-version-governed constraints determine channel eligibility, prohibition, and prioritization
* How provider health state, delivery failure lineage, and opt-out restrictions constrain channel advisories
* How replay, regeneration, and SHADOW execution semantics constrain channel advisement outputs
* How AI-governance tiers influence channel prioritization without overriding rule-based channel constraints
* What attribution, observability, and lineage metadata must accompany every channel advisory output

This directive is the authoritative specification for **governance-aware channel orchestration advisement**. It is consumed by the outreach orchestration service after the Core Decision Engine (`directives/core_decision_engine.md`) has produced a `INITIATE_OUTREACH` or `RETRY_OUTREACH` intent, and after the retry policy (`directives/outreach_retry_policy.md`) has confirmed `RETRY_ELIGIBLE` scope for retry contexts. The channel advisory governs which channels are available candidates for the orchestration service to attempt.

---

### 1.2 Channel Advisory Categories

Channel advisement produces multiple distinct advisory categories, not a single channel selection output. The following categories are defined:

| Category | Definition | Governing rule(s) |
|---|---|---|
| **Contact data channel eligibility** | Each channel's availability based on SQL Server-authoritative contact data (phone for CALL/SMS, email for EMAIL) | Rules 4, 6 |
| **Opt-out compliance** | Per-channel opt-out restrictions, compliance-hold channel blocks, and regulatory consent state | Rules 2, 6 |
| **Provider health eligibility** | Per-channel provider availability based on provider health state and delivery failure suspension thresholds | Rules 7, 10 |
| **Channel exhaustion state** | Whether all, some, or no channels remain available for advisory candidacy after all constraint layers are applied | Rule 8 |
| **Engagement-signal-aware prioritization** | Config-governed engagement thresholds that inform which channel has the highest historical responsiveness for this student | Rule 11 |
| **AI-assisted channel prioritization** | AI governance tier and sentiment signals that may adjust channel priority ordering within the permissible candidates | Rules 5, 12 |

All six categories are evaluated when assessment proceeds past Rule 0. The resulting `ChannelAdvisoryAssessment` output carries the advisory outcome across all six.

---

### 1.3 What Channel Advisement Is NOT

To prevent scope creep and architectural boundary violations, this directive explicitly defines what channel advisement does NOT do:

* **Does not execute outbound delivery.** Channel advisement determines candidacy and ordering. The outreach orchestration service and provider dispatch layer execute delivery. The advisory is consumed by the orchestration service; it cannot bypass it.
* **Does not sequence provider calls.** Which provider API to call, in what order, with what retry behavior at the provider level — these are provider orchestration layer concerns. This directive produces advisory candidates; the provider layer executes.
* **Does not authorize retry execution.** Retry eligibility is governed by `directives/outreach_retry_policy.md`. Channel advisement is consulted after retry eligibility is confirmed; it does not re-adjudicate retry authorization.
* **Does not mutate outreach state or channel lineage.** No state machine transition (e.g., RETRY → CONTACTED) originates from channel advisory evaluation. All state writes belong to the state management service.
* **Does not dispatch escalation.** Escalation-relevant signals identified during channel evaluation (e.g., channel exhaustion indicating systemic provider failure) are carried in the advisory output for the escalation routing service to act on.
* **Does not override governance invariants (INVARIANT-1 through INVARIANT-7 in spec/03 §40).** Channel advisement operates within those invariants. It does not adjudicate them.
* **Does not write to any database.** All database writes — idempotency key storage, audit log entries, channel selection records — are the responsibility of consuming services.

---

## 2. INPUT MODEL

---

The channel advisory context is **lineage-aware and governance-aware**. Every input carries metadata establishing its authority class and origin. Inputs from SQL Server (`origin_authority = sql_server_authoritative`) govern contact data eligibility for channel advisement. Platform-supplementary inputs provide operational channel context but do not override SQL Server-authoritative state (INVARIANT-6, spec/03 §40).

---

### 2.1 Communication Context

Prior channel history, delivery history, engagement signals, and retry lineage sourced from platform-owned operational tables.

| Field | Type | Authority | Description |
|---|---|---|---|
| `contact_attempt_count` | integer | `platform_supplementary` | Total contact attempts made in the current outreach cycle |
| `last_channel_used` | enum | `platform_supplementary` | Most recent channel attempted: `CALL`, `SMS`, `EMAIL`, `NONE` |
| `last_contact_timestamp` | datetime | `platform_supplementary` | Most recent outreach event timestamp |
| `last_contact_outcome` | enum | `platform_supplementary` | Outcome of most recent contact: `CONNECTED`, `NO_ANSWER`, `VOICEMAIL`, `DELIVERY_FAILED`, `PROVIDER_ERROR`, `OPTED_OUT` |
| `channel_delivery_history` | list | `platform_supplementary` | Per-channel delivery outcomes across all attempts in the current cycle: `{channel, outcome, timestamp, provider}` |
| `channel_attempt_counts` | object | `platform_supplementary` | Per-channel attempt counts in the current cycle: `{CALL: N, SMS: N, EMAIL: N}` |
| `engagement_history` | list | `platform_supplementary` | Inbound response events by channel: `{channel, event_type, timestamp}` |
| `retry_lineage` | object | `platform_supplementary` | Retry context: `{retry_attempt_number, retry_history, consecutive_no_response_count, provider_failure_count}` |
| `escalation_lineage` | list | `platform_supplementary` | Escalation events in the current cycle: reason, urgency, resolution timestamp if any |
| `orchestration_history` | list | `platform_supplementary` | Prior orchestration intents and channel advisory outputs produced for this student in the current cycle |
| `quick_action_history` | list | `platform_supplementary` | Recent operator quick actions: `ESCALATE`, `CLOSE_CASE`, `FORCE_RETRY`, `CHANNEL_OVERRIDE`, etc. |

---

### 2.2 Governance Context

Governance context is mandatory for every channel advisory evaluation. Advisories produced without full governance context are invalid and must not be consumed by orchestration services.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ID of the ACTIVE config version at advisory time (must be resolved before Rule 0 executes) |
| `config_version_status` | enum | Status of the resolved config version: `ACTIVE` (operational) or `SUPERSEDED` (replay only) |
| `config_rule_set` | object | Extracted threshold values from the ACTIVE (or historical) config version's `rule_set_snapshot` |
| `execution_mode` | enum | Platform execution mode: `SHADOW` (default; no outbound effects) or `LIVE` (requires Phase 12 certification) |
| `execution_type` | enum | `original`, `replay`, or `regeneration`; drives replay-safety rules (§6) |
| `correlation_id` | uuid | UUID v4 propagated from the triggering scheduler run or operator action |
| `causation_id` | uuid | UUID v4 of the upstream event that caused this advisory evaluation (may be null for root events) |
| `attribution_context` | object | Full attribution metadata: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp` |
| `fingerprint_context` | object | Snapshot Reproducibility Fingerprint components at the time of this evaluation; used for replay safety |
| `idempotency_key` | string | Advisory-level idempotency key `(student_id, checkpoint_type, cycle_timestamp, contact_attempt_count)` |
| `compliance_hold_flag` | boolean | True if the student's snapshot is currently under `COMPLIANCE_HOLD` |
| `replay_context` | object | Present only when `execution_type ∈ {replay, regeneration}`; contains source artifact ID, historical config reference, and fingerprint from the source snapshot |

---

### 2.3 Attribution Context

Attribution context establishes the provenance of the channel advisory and must propagate unchanged to all downstream records.

| Field | Type | Description |
|---|---|---|
| `origin_source` | enum | Who triggered the advisory: `system_automated` (scheduler), `operator` (manual channel action), or `scheduler` |
| `origin_authority` | enum | Authority class of the triggering source: `platform_supplementary` for all channel advisory evaluations |
| `actor_identity` | string | Service identifier: `channel_advisory_v{N}` |
| `attribution_timestamp` | ISO-8601 | Timestamp of the originating event that caused this advisory (not the processing timestamp) |
| `historical_context` | list | Prior `(snapshot_month, config_version_id, channel_advisory_outcome)` tuples for longitudinal continuity |
| `prior_intervention_count` | integer | Total operator interventions recorded across all history |
| `historical_risk_trend` | enum | Trend derived from prior finalized snapshots: `IMPROVING`, `STABLE`, `DECLINING`, `CRITICAL`, `UNKNOWN` |

---

### 2.4 AI Context

AI insight state, sentiment advisories, and confidence metadata. AI inputs are **advisory only** for channel prioritization adjustment; they cannot override governance channel constraints, opt-out restrictions, or provider health gates (§7).

| Field | Type | Description |
|---|---|---|
| `ai_insight_state` | enum | Lifecycle state of the AI insight record (`AI_REVIEWED`, `AI_GENERATION_FAILED`, `AI_GENERATING`, `AI_PENDING`, `AI_ARCHIVED`, etc.) |
| `ai_insight_version` | integer | `version_number` of the AI insight record; used for staleness tracking |
| `ai_recommended_intervention` | enum | AI's recommended intervention pathway: `NONE`, `OUTREACH`, `MEETING`, `RESOURCE_DELIVERY`, `ESCALATE` |
| `ai_sentiment` | string | Sentiment classification from the AI insight (e.g., `POSITIVE`, `NEUTRAL`, `NEGATIVE`); used for channel preference adjustment |
| `ai_channel_preference_signal` | enum | AI-derived channel preference signal when available: `PREFER_CALL`, `PREFER_SMS`, `PREFER_EMAIL`, `NO_PREFERENCE`; advisory only |
| `ai_confidence_score` | float | Model-reported confidence (0.0–1.0); drives AI governance tier selection (Rule 5) |
| `ai_generated_at` | datetime | Timestamp of AI insight generation |
| `ai_stale_flag` | boolean | True if insight age exceeds `ai_insight_ttl_hours` from the ACTIVE config |
| `ai_ttl_hours` | integer | TTL from the ACTIVE config version; used for staleness determination |
| `ai_finalized_copy` | boolean | Whether the AI content is a snapshot-frozen physical copy (immutable; must not drive new channel priority decisions) |
| `ai_input_metrics_hash` | string | Hash of input metrics used to generate the insight; used for reproducibility verification |

---

### 2.5 Operational Context

Provider health state, opt-out restrictions, delivery failure patterns, and contact availability sourced from both SQL Server-authoritative and platform-supplementary sources.

| Field | Type | Authority | Description |
|---|---|---|---|
| `email` | string | `sql_server_authoritative` | Contact email address (used for contact data gate only; never in log output) |
| `phone_number` | string | `sql_server_authoritative` | Contact phone number (used for contact data gate only; never in log output) |
| `access_state` | enum | `sql_server_authoritative` | Current platform access status (ACTIVE, REVOKED, SUSPENDED) |
| `outreach_state` | enum | `platform_supplementary` | Current state in the Outreach lifecycle domain |
| `engagement_signal_score` | float | `platform_supplementary` | Recent engagement responsiveness score (0.0–1.0); used for channel prioritization |
| `provider_health_state` | object | `platform_supplementary` | Per-channel provider availability: `{CALL: HEALTHY|DEGRADED|UNAVAILABLE, SMS: ..., EMAIL: ...}`; sourced from provider health service |
| `channel_opt_out_state` | object | `platform_supplementary` | Per-channel opt-out status: `{CALL: false, SMS: true, EMAIL: false}`; sourced from opt-out registry |
| `channel_delivery_failure_counts` | object | `platform_supplementary` | Per-channel consecutive delivery failure counts in the current cycle: `{CALL: N, SMS: N, EMAIL: N}` |
| `channel_suspension_state` | object | `platform_supplementary` | Per-channel active suspension flags: `{CALL: false, SMS: false, EMAIL: false}`; driven by delivery failure threshold |
| `channel_exhaustion_state` | enum | `platform_supplementary` | Aggregate channel availability: `AVAILABLE`, `PARTIAL`, `EXHAUSTED`; derived from above fields |
| `ghl_delivery_capability` | object | `platform_supplementary` | GHL-reported delivery capability per channel at advisory time: `{CALL: true, SMS: true, EMAIL: true}` |
| `sql_server_sync_timestamp` | datetime | `sql_server_authoritative` | Most recent SQL Server sync cycle timestamp |

---

## 3. OUTPUT MODEL

---

The channel advisory produces a single **`ChannelAdvisoryAssessment`** object per evaluation. This object is advisory: it does not execute delivery, does not mutate state, and does not enforce governance boundaries. The outreach orchestration service consumes this assessment to determine which channels are valid candidates, their recommended ordering, and any constraints that govern dispatch.

---

### 3.1 ChannelAdvisoryAssessment Schema

```json
{
  "channel_advisory_produced": false,
  "advisory_scope": "CALL_PREFERRED | SMS_PREFERRED | EMAIL_PREFERRED | MULTI_CHANNEL_ELIGIBLE | CHANNEL_EXHAUSTED | REPLAY_CHANNEL_CANDIDATE | NONE",
  "recommended_channel_candidates": [],
  "prohibited_channels": [],
  "governance_constraints": {
    "execution_mode_constraint": "SHADOW | LIVE",
    "live_delivery_permitted": false,
    "compliance_channel_restrictions": [],
    "opt_out_channel_exclusions": [],
    "suspended_channel_exclusions": [],
    "config_version_id": "string",
    "idempotency_key": "string",
    "governance_preconditions_met": false,
    "blocking_governance_flags": []
  },
  "escalation_constraints": {
    "escalation_recommended": false,
    "escalation_urgency": "LOW | MEDIUM | HIGH | CRITICAL | NONE",
    "escalation_reason_codes": [],
    "escalation_context": {}
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
    "actor_identity": "channel_advisory_v1"
  },
  "config_version_reference": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "threshold_bindings": {
      "preferred_initial_channel": "CALL | SMS | EMAIL",
      "delivery_failure_channel_suspension_threshold": 0,
      "call_engagement_score_threshold": 0.0,
      "sms_engagement_score_threshold": 0.0,
      "email_engagement_score_threshold": 0.0,
      "channel_specific_cooldown_hours": 0,
      "ai_insight_ttl_hours": 0,
      "channel_opt_out_respect_period_hours": 0
    }
  },
  "provider_health_metadata": {
    "call_provider_state": "HEALTHY | DEGRADED | UNAVAILABLE | UNKNOWN",
    "sms_provider_state": "HEALTHY | DEGRADED | UNAVAILABLE | UNKNOWN",
    "email_provider_state": "HEALTHY | DEGRADED | UNAVAILABLE | UNKNOWN",
    "channel_suspension_applied": false,
    "suspended_channels": []
  },
  "advisory_confidence": "LOW | MEDIUM | HIGH | UNKNOWN",
  "ai_context": {
    "ai_input_used": false,
    "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | UNAVAILABLE | IN_FLIGHT | FINALIZED_COPY",
    "ai_confidence_score": 0.0,
    "stale_flag": false,
    "fallback_applied": false,
    "channel_priority_adjustment_applied": false,
    "ai_channel_preference_signal": "PREFER_CALL | PREFER_SMS | PREFER_EMAIL | NO_PREFERENCE | null",
    "ai_version_number": null
  },
  "reason_codes": [],
  "advisory_blocked": false,
  "blocking_reason": null
}
```

---

### 3.2 Advisory Scope Values

| Scope | Meaning | Downstream implication |
|---|---|---|
| `CALL_PREFERRED` | CALL is the governance-safe recommended primary candidate based on contact data, provider health, engagement signals, and config constraints; SMS and EMAIL are secondary candidates if available | Orchestration service attempts CALL first; channel layer sequences fallbacks |
| `SMS_PREFERRED` | SMS is the recommended primary candidate; CALL and EMAIL are secondary candidates | Orchestration service attempts SMS first |
| `EMAIL_PREFERRED` | EMAIL is the recommended primary candidate; CALL and SMS may be secondary candidates | Orchestration service attempts EMAIL first |
| `MULTI_CHANNEL_ELIGIBLE` | Multiple channels are equally valid advisory candidates; no single channel has priority signal advantage over others | Orchestration service applies its own sequencing rule; all candidates in `recommended_channel_candidates` are permissible |
| `CHANNEL_EXHAUSTED` | All available channels are prohibited by opt-out, delivery failure suspension, provider unavailability, or contact data absence; no channel advisory is safe | Orchestration service routes to escalation; no outbound dispatch permitted |
| `REPLAY_CHANNEL_CANDIDATE` | Advisory is in replay or regeneration context; historical channel candidacy assessed; live delivery advisement prohibited | Assessment documents historical channel state; no outbound side effects |
| `NONE` | No channel advisory produced; governance block, terminal state, compliance hold, or contact data entirely absent | Orchestration service takes no channel action; blocked or escalated per governing intent |

---

### 3.3 Key Output Clarifications

* **Channel advisories do not execute delivery.** The `ChannelAdvisoryAssessment` is advisory to the outreach orchestration service. The service validates current state and may reject or reorder candidates based on its own runtime checks.
* **The advisory never writes to the database.** All persistence — idempotency key storage, advisory log entries, channel history records — is the responsibility of consuming services.
* **Provider dispatch belongs outside this directive.** Which provider API to call, in which order, with what timeout — these are provider orchestration layer concerns. This directive produces `recommended_channel_candidates`; the provider layer executes against them.
* **`live_delivery_permitted = false` is the default.** Until Phase 12 production governance certification, all advisories carry `live_delivery_permitted = false` in `governance_constraints`, regardless of `advisory_scope`. SHADOW mode suppression enforcement belongs to consuming services.
* **Threshold bindings in `config_version_reference` are the historical record.** The specific values that governed this advisory are captured in the output, enabling historical audit without re-querying the config registry.
* **`recommended_channel_candidates` is an ordered list.** The first element is the primary recommendation. The ordering reflects engagement signal assessment and AI-assisted adjustment. The orchestration service must respect this ordering unless it has a runtime override (e.g., operator `CHANNEL_OVERRIDE` quick action).

---

## 4. CHANNEL ADVISORY RULES (ORDERED)

---

Rules are evaluated in the order defined below. **Stop at the first terminal rule unless otherwise stated.** Each rule that fires contributes to `rule_path_taken` in `observability_metadata`.

Non-terminal rules (marked `CONTINUE`) populate advisory fields and do not stop evaluation. Terminal rules (marked `STOP`) produce the final advisory immediately.

---

### RULE 0 — GOVERNANCE PRECONDITION GATE

**This rule is mandatory. No subsequent rules execute if this rule blocks. This rule fires before any other rule, including business rules.**

BLOCK advisory production IF any of the following are true:

* `config_version_id` is null (config resolution failed; see §5.1)
* `config_version_status` is not `ACTIVE` and `execution_type = original` (SUPERSEDED versions are only valid in replay mode)
* `execution_mode` is not one of `SHADOW` or `LIVE`
* `execution_mode = LIVE` and Phase 12 production governance certification has not been confirmed (see `execution/build_phases.md` Phase 12)
* `correlation_id` is null
* `attribution_context` is incomplete (missing any of: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`)
* `idempotency_key` already exists in the idempotency store for this `(student_id, checkpoint_type, cycle_timestamp, contact_attempt_count)` — duplicate advisory detected
* `execution_type ∈ {replay, regeneration}` AND `replay_context` is absent or incomplete

THEN:

```json
{
  "channel_advisory_produced": false,
  "advisory_scope": "NONE",
  "advisory_blocked": true,
  "blocking_reason": "GOVERNANCE_PRECONDITION_FAILED",
  "governance_constraints": {
    "governance_preconditions_met": false
  },
  "reason_codes": [
    "CONFIG_UNRESOLVED | CONFIG_VERSION_NOT_ACTIVE | EXECUTION_MODE_INVALID | LIVE_CERTIFICATION_REQUIRED | CORRELATION_ID_MISSING | ATTRIBUTION_INCOMPLETE | IDEMPOTENCY_DUPLICATE | REPLAY_CONTEXT_MISSING"
  ]
}
```

STOP.

> **Governance integrity note:** The governance precondition gate ensures that orchestration integrity precedes all channel business rules. A blocked advisory at Rule 0 is a definitive governance failure, not a data problem to work around. No fallback, no default channel, no retry. The advisory is invalid and must not be consumed.

---

### RULE 1 — TERMINAL STATE CHECK

IF `outreach_state = CLOSED`:

```json
{
  "channel_advisory_produced": false,
  "advisory_scope": "NONE",
  "reason_codes": ["OUTREACH_CLOSED_TERMINAL"]
}
```

STOP.

> CLOSED is a terminal state in the Outreach lifecycle domain (spec/03 §4). A student in CLOSED state cannot re-enter channel advisory candidacy. A new outreach cycle must be initiated through the state management service, not through re-evaluation.

---

### RULE 2 — COMPLIANCE HOLD GATE

IF `compliance_hold_flag = true`:

```json
{
  "channel_advisory_produced": true,
  "advisory_scope": "NONE",
  "recommended_channel_candidates": [],
  "prohibited_channels": ["CALL", "SMS", "EMAIL"],
  "governance_constraints": {
    "blocking_governance_flags": ["COMPLIANCE_HOLD_ACTIVE"],
    "compliance_channel_restrictions": ["CALL", "SMS", "EMAIL"]
  },
  "escalation_constraints": {
    "escalation_recommended": true,
    "escalation_urgency": "CRITICAL",
    "escalation_reason_codes": ["COMPLIANCE_HOLD_ALL_CHANNELS_BLOCKED"],
    "escalation_context": {
      "note": "All channels prohibited under COMPLIANCE_HOLD. Automated delivery suspended until hold resolves via the Compliance Governance Pathway."
    }
  },
  "reason_codes": ["COMPLIANCE_HOLD_ACTIVE", "ALL_CHANNELS_COMPLIANCE_BLOCKED"]
}
```

STOP.

> Compliance hold suspends all automated channel advisement. No channel is a valid candidate while a COMPLIANCE_HOLD is active. The escalation constraint ensures routing services treat this with maximum urgency. Channel-specific advisement cannot resume until the hold is resolved.

---

### RULE 3 — CONFIG-BOUND THRESHOLD RESOLUTION

**This rule is non-terminal. It must execute before any threshold-dependent rule (Rules 6, 7, 10, 11, 12).**

Resolve all threshold bindings from `config_rule_set` (the ACTIVE or historical config version's `rule_set_snapshot`):

| Threshold variable | Config key | Used in rule |
|---|---|---|
| `PREFERRED_INITIAL_CHANNEL` | `outreach_initial_channel_preference` | Rule 11 |
| `DELIVERY_FAILURE_CHANNEL_SUSPENSION_THRESHOLD` | `channel_delivery_failure_suspension_threshold` | Rule 7, 10 |
| `CALL_ENGAGEMENT_SCORE_THRESHOLD` | `call_engagement_score_threshold` | Rule 11 |
| `SMS_ENGAGEMENT_SCORE_THRESHOLD` | `sms_engagement_score_threshold` | Rule 11 |
| `EMAIL_ENGAGEMENT_SCORE_THRESHOLD` | `email_engagement_score_threshold` | Rule 11 |
| `CHANNEL_SPECIFIC_COOLDOWN_HOURS` | `channel_specific_cooldown_hours` | Rule 10 |
| `AI_INSIGHT_TTL_HOURS` | `ai_insight_ttl_hours` | Rule 5 |
| `CHANNEL_OPT_OUT_RESPECT_PERIOD_HOURS` | `channel_opt_out_respect_period_hours` | Rule 6 |

All resolved bindings are written to `config_version_reference.threshold_bindings` in the advisory output. This is the historical record of which thresholds governed this advisory.

IF any threshold is missing from `config_rule_set`:

* Substitute `UNKNOWN_V0` for that threshold in internal evaluation
* Log `CONFIG_THRESHOLD_MISSING` at `warn` level with the specific missing key name
* Add `CONFIG_THRESHOLD_MISSING_{KEY_NAME}` to `reason_codes`
* Exclude rules that depend solely on the missing threshold from evaluation
* Continue with all rules that do not depend on missing thresholds

**No hardcoded channel priority order or delivery failure thresholds are permitted as substitutes.** Missing config thresholds degrade coverage; they never justify fallback to compiled-in constants (AP-C9).

CONTINUE.

---

### RULE 4 — CONTACT DATA GATE (PER CHANNEL)

Evaluate per-channel contact data availability from SQL Server-authoritative fields:

* IF `phone_number` is null: CALL and SMS are unavailable. Add `CALL` and `SMS` to `prohibited_channels` with reason `NO_PHONE_NUMBER`.
* IF `email` is null: EMAIL is unavailable. Add `EMAIL` to `prohibited_channels` with reason `NO_EMAIL_ADDRESS`.

IF all three channels are prohibited after this rule:

```json
{
  "channel_advisory_produced": false,
  "advisory_scope": "NONE",
  "recommended_channel_candidates": [],
  "prohibited_channels": ["CALL", "SMS", "EMAIL"],
  "reason_codes": ["NO_CONTACT_INFO_ANY_CHANNEL"]
}
```

STOP.

IF at least one channel remains unpopulated after this rule: proceed with the remaining eligible candidates.

CONTINUE.

> Contact data absence is evaluated per-channel, not as a binary block. A student without a phone number may still be reachable by email. The advisory reflects which channels are actually available given authoritative contact data.

---

### RULE 5 — AI GOVERNANCE TIER ASSESSMENT

**This rule is non-terminal. It determines the `ai_governance_tier` that governs Rule 12 behavior.**

| Condition | AI Governance Tier |
|---|---|
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score ≥ 0.70` | `CONFIDENT` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = false` AND `ai_confidence_score < 0.70` | `ADVISORY` |
| `ai_insight_state = AI_REVIEWED` AND `ai_stale_flag = true` | `STALE` |
| `ai_insight_state ∈ {AI_GENERATING, AI_PENDING}` | `IN_FLIGHT` — triggers Rule 5A |
| `ai_insight_state ∈ {AI_GENERATION_FAILED, null}` | `UNAVAILABLE` |
| `ai_finalized_copy = true` | `FINALIZED_COPY` — immutable; no channel priority adjustment permitted; used only in report regeneration context |

Staleness is determined by: `current_timestamp - ai_generated_at > AI_INSIGHT_TTL_HOURS` (from config-bound threshold resolution, Rule 3).

If `AI_INSIGHT_TTL_HOURS` was not resolved (missing from config), set `ai_governance_tier = UNAVAILABLE` and log `AI_TTL_NOT_CONFIGURED`.

CONTINUE.

---

### RULE 5A — PENDING AI GATE (conditional exit from Rule 5)

IF `ai_governance_tier = IN_FLIGHT` AND `execution_type = original`:

Proceed with rule-based channel advisory only. Set `ai_context.ai_input_used = false`. Add `AI_INSIGHT_IN_FLIGHT_CHANNEL_ADVISORY_PROCEEDS` to `reason_codes`.

> Unlike eligibility assessment (which defers to PRIORITIZATION_ONLY scope when AI is IN_FLIGHT), channel advisement proceeds without AI input rather than deferring. The channel advisory is needed for the orchestration service to proceed; deferral here would stall outreach execution unnecessarily. The advisory is produced with `RULE_BASED` assessment basis.

CONTINUE (without AI input for Rule 12).

---

### RULE 6 — OPT-OUT AND CONSENT CHANNEL GATE

Evaluate per-channel opt-out state from `channel_opt_out_state`:

For each channel where `channel_opt_out_state[channel] = true`:

* Add channel to `prohibited_channels`
* Add channel to `governance_constraints.opt_out_channel_exclusions`
* Add `{CHANNEL}_OPT_OUT_ACTIVE` to `reason_codes`

If `CHANNEL_OPT_OUT_RESPECT_PERIOD_HOURS` is resolved and an opt-out was recently set (within the configured respect period), enforce the prohibition regardless of any operator override signal.

IF all previously eligible channels are now prohibited after this rule:

```json
{
  "channel_advisory_produced": true,
  "advisory_scope": "CHANNEL_EXHAUSTED",
  "recommended_channel_candidates": [],
  "escalation_constraints": {
    "escalation_recommended": true,
    "escalation_urgency": "MEDIUM",
    "escalation_reason_codes": ["ALL_CHANNELS_OPT_OUT_PROHIBITED"],
    "escalation_context": {
      "note": "All available channels are prohibited by active opt-out registrations. Human review required to determine appropriate next action."
    }
  },
  "reason_codes": ["CHANNEL_EXHAUSTED_OPT_OUT"]
}
```

STOP.

IF at least one channel remains eligible: continue with remaining eligible channels.

CONTINUE.

---

### RULE 7 — PROVIDER HEALTH AND CHANNEL SUSPENSION GATE

Evaluate per-channel provider health state from `provider_health_state`:

For each channel:

* IF `provider_health_state[channel] = UNAVAILABLE`: Add to `prohibited_channels`. Add `{CHANNEL}_PROVIDER_UNAVAILABLE` to `reason_codes`. Record in `provider_health_metadata.suspended_channels`.
* IF `provider_health_state[channel] = DEGRADED`: Retain channel as candidate but add `{CHANNEL}_PROVIDER_DEGRADED` to `reason_codes`. Deprioritize in `recommended_channel_candidates` ordering (lower position than HEALTHY channels).
* IF `channel_suspension_state[channel] = true` (delivery failure threshold exceeded per Rule 10 pre-pass): Add to `prohibited_channels`. Add `{CHANNEL}_DELIVERY_FAILURE_SUSPENDED` to `reason_codes`.

Set `provider_health_metadata.channel_suspension_applied = true` if any channel is suspended.

IF all eligible channels are prohibited after provider health and suspension evaluation:

```json
{
  "channel_advisory_produced": true,
  "advisory_scope": "CHANNEL_EXHAUSTED",
  "recommended_channel_candidates": [],
  "escalation_constraints": {
    "escalation_recommended": true,
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["ALL_CHANNELS_PROVIDER_UNAVAILABLE_OR_SUSPENDED"],
    "escalation_context": {
      "note": "All channels are unavailable or suspended due to provider health state or delivery failure thresholds. Systemic provider outage suspected."
    }
  },
  "reason_codes": ["CHANNEL_EXHAUSTED_PROVIDER_FAILURE"]
}
```

STOP.

CONTINUE.

---

### RULE 8 — CHANNEL EXHAUSTION GATE

**Evaluate aggregate `channel_exhaustion_state` as a cross-cutting check after per-channel gates.**

IF `channel_exhaustion_state = EXHAUSTED` AND `recommended_channel_candidates` is empty:

```json
{
  "channel_advisory_produced": true,
  "advisory_scope": "CHANNEL_EXHAUSTED",
  "recommended_channel_candidates": [],
  "prohibited_channels": ["CALL", "SMS", "EMAIL"],
  "escalation_constraints": {
    "escalation_recommended": true,
    "escalation_urgency": "HIGH",
    "escalation_reason_codes": ["CHANNEL_EXHAUSTION_CONFIRMED"],
    "escalation_context": {
      "channel_exhaustion_state": "EXHAUSTED",
      "note": "Channel exhaustion state confirmed by all constraint layers. No channels remain for advisory candidacy."
    }
  },
  "reason_codes": ["ALL_CHANNELS_EXHAUSTED"]
}
```

STOP.

IF `channel_exhaustion_state = PARTIAL` AND at least one channel remains eligible: add `CHANNEL_EXHAUSTION_PARTIAL` to `reason_codes` and continue.

CONTINUE.

---

### RULE 9 — REPLAY CHANNEL GATE

**This rule fires only when `execution_type ∈ {replay, regeneration}`. It is non-terminal when replay preconditions pass; terminal when they fail.**

Replay preconditions — ALL must hold:

1. `config_version_id` matches the historical config reference from `replay_context` (not the current ACTIVE version)
2. `fingerprint_context` is populated with the historical snapshot's stored fingerprint components
3. `execution_mode = SHADOW` — replay execution must never be `LIVE`
4. `replay_context.source_artifact_id` is present and resolvable

IF all preconditions pass:

Set `advisory_scope = REPLAY_CHANNEL_CANDIDATE`.
Set `replay_restrictions.replay_eligible = true`.
Set `replay_restrictions.live_eligible = false`.
Set `governance_constraints.live_delivery_permitted = false`.
Compute `fingerprint_comparison_outcome` by comparing historical fingerprint components against current system state.
Record `REPLAY_CHANNEL_CANDIDATE` in `reason_codes`.

CONTINUE. (Assessment continues through Rules 11 and 12 using historical context for historical channel state reconstruction, but `advisory_scope` remains `REPLAY_CHANNEL_CANDIDATE` unconditionally — no upgrade to `CALL_PREFERRED`, `SMS_PREFERRED`, `EMAIL_PREFERRED`, or `MULTI_CHANNEL_ELIGIBLE` is permitted in replay.)

IF any precondition fails:

```json
{
  "channel_advisory_produced": false,
  "advisory_scope": "NONE",
  "advisory_blocked": true,
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

### RULE 10 — DELIVERY FAILURE PATTERN ASSESSMENT

**This rule is non-terminal. It evaluates per-channel delivery failure lineage and applies channel-specific suspension where thresholds are exceeded.**

For each channel still in the eligible candidate set:

IF `channel_delivery_failure_counts[channel] ≥ DELIVERY_FAILURE_CHANNEL_SUSPENSION_THRESHOLD`:

* Mark channel as suspended: set `channel_suspension_state[channel] = true`
* Add channel to `prohibited_channels`
* Add channel to `provider_health_metadata.suspended_channels`
* Add `{CHANNEL}_DELIVERY_FAILURE_SUSPENDED` to `reason_codes`
* Set `provider_health_metadata.channel_suspension_applied = true`

IF `CHANNEL_SPECIFIC_COOLDOWN_HOURS` is resolved and a channel-specific cooldown is active since the last delivery failure on that channel:

* Retain the suspension for that channel until the cooldown elapses
* Add `{CHANNEL}_COOLDOWN_ACTIVE` to `reason_codes`

IF all remaining channels are suspended after this rule:

Transition to `CHANNEL_EXHAUSTED` scope. Produce escalation recommendation. STOP (same output as Rule 8 exhaustion path).

CONTINUE.

---

### RULE 11 — ENGAGEMENT-SIGNAL-AWARE CHANNEL PRIORITIZATION

**This rule is non-terminal. It determines the ordering of `recommended_channel_candidates` from the remaining eligible channels.**

Using `engagement_signal_score` and `channel_delivery_history`, apply config-governed engagement thresholds:

**Step 1 — Check engagement history for per-channel responsiveness:**

* IF prior `channel_delivery_history` contains a `CONNECTED` outcome on CALL within the current cycle: assign CALL a `responsiveness_score = HIGH`.
* IF prior `channel_delivery_history` contains an inbound engagement event via SMS: assign SMS a `responsiveness_score = HIGH`.
* IF prior `channel_delivery_history` contains an email open or reply event: assign EMAIL a `responsiveness_score = HIGH`.
* Channels without prior engagement history in the current cycle carry `responsiveness_score = MEDIUM`.
* Channels with `DELIVERY_FAILED` or `NO_ANSWER` outcomes (but not yet suspended) carry `responsiveness_score = LOW`.

**Step 2 — Apply engagement signal score thresholds from config:**

* IF `engagement_signal_score ≥ CALL_ENGAGEMENT_SCORE_THRESHOLD` AND CALL is eligible: position CALL first in `recommended_channel_candidates`.
* IF `engagement_signal_score ≥ SMS_ENGAGEMENT_SCORE_THRESHOLD` AND CALL is not preferred by Step 2: position SMS first.
* IF `engagement_signal_score ≥ EMAIL_ENGAGEMENT_SCORE_THRESHOLD` AND neither CALL nor SMS is preferred: position EMAIL first.
* IF no engagement threshold discriminates between eligible channels: use `PREFERRED_INITIAL_CHANNEL` from config as the default ordering anchor.

**Step 3 — Determine advisory scope:**

* Single eligible channel remains: set `advisory_scope` to that channel's `{CHANNEL}_PREFERRED` value.
* Two or more eligible channels with clear preference ordering: set `advisory_scope = {PRIMARY_CHANNEL}_PREFERRED`.
* Two or more eligible channels with no engagement-signal preference: set `advisory_scope = MULTI_CHANNEL_ELIGIBLE`.

Write the ordered `recommended_channel_candidates` list.

If one or more engagement thresholds are missing from config (Rule 3 issued `CONFIG_THRESHOLD_MISSING`): use `PREFERRED_INITIAL_CHANNEL` ordering for missing threshold dimensions and add `PARTIAL_ENGAGEMENT_ASSESSMENT` to `reason_codes`.

CONTINUE.

---

### RULE 12 — AI-ASSISTED CHANNEL PRIORITIZATION ADJUSTMENT

**This rule is non-terminal. It may adjust the ordering of `recommended_channel_candidates` based on AI governance tier and channel preference signal. It cannot override governance constraints, opt-out restrictions, or provider health prohibitions.**

IF `ai_governance_tier = CONFIDENT` AND `ai_channel_preference_signal ∈ {PREFER_CALL, PREFER_SMS, PREFER_EMAIL}`:

* Move the AI-preferred channel to position 1 in `recommended_channel_candidates` IF it is not already prohibited.
* Set `ai_context.channel_priority_adjustment_applied = true`.
* Add `AI_CHANNEL_PREFERENCE_SIGNAL_CONFIDENT` to `reason_codes`.
* Update `advisory_scope` to reflect the new primary channel preference.

IF `ai_governance_tier = ADVISORY` AND `ai_channel_preference_signal ∈ {PREFER_CALL, PREFER_SMS, PREFER_EMAIL}`:

* Move the AI-preferred channel to position 1 ONLY IF engagement signal score does not contradict the preference (i.e., Rule 11's primary channel has `responsiveness_score = LOW` for the AI-non-preferred channel, or equal scores for all channels).
* Set `ai_context.channel_priority_adjustment_applied = true`.
* Add `AI_CHANNEL_PREFERENCE_SIGNAL_ADVISORY` to `reason_codes`.

IF `ai_governance_tier = STALE`:

* Do NOT adjust channel ordering based on AI signal.
* Record `STALE_AI_CHANNEL_ADVISORY_SKIPPED` in `reason_codes`.
* If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`.

IF `ai_governance_tier = UNAVAILABLE`:

* Set `ai_context.fallback_applied = true`.
* Record `AI_UNAVAILABLE_FALLBACK_APPLIED` in `reason_codes`.
* No channel ordering adjustment. Rule 11's engagement-signal-based ordering governs.

IF `ai_governance_tier = FINALIZED_COPY`:

* No channel priority adjustment from this source. Immutable snapshot copies are not inputs for new channel advisory decisions.
* Record `AI_FINALIZED_COPY_NOT_APPLIED` in `reason_codes`.

AI cannot move a prohibited channel into `recommended_channel_candidates`. AI cannot remove channels from `prohibited_channels`. AI cannot override any constraint applied by Rules 2, 4, 6, 7, 8, or 10.

CONTINUE.

---

### RULE 13 — DEFAULT CHANNEL ADVISORY OUTPUT

**Terminal. Produces the final `ChannelAdvisoryAssessment` from the accumulated state of prior rules.**

At this point, `advisory_scope`, `recommended_channel_candidates`, `prohibited_channels`, `ai_context`, `provider_health_metadata`, `reason_codes`, and all governance/attribution fields have been populated by prior non-terminal rules.

Set `channel_advisory_produced = true`.
Set `governance_constraints.governance_preconditions_met = true` (Rule 0 passed).
Set `governance_constraints.live_delivery_permitted = false` until Phase 12 production governance certification.

Set `advisory_confidence`:
* `HIGH` if `advisory_scope ∈ {CALL_PREFERRED, SMS_PREFERRED, EMAIL_PREFERRED}` AND engagement history confirms the primary channel AND ai_governance_tier is `CONFIDENT` or `ADVISORY`
* `MEDIUM` if `advisory_scope = MULTI_CHANNEL_ELIGIBLE` OR engagement signals are partial OR AI tier is `STALE` / `UNAVAILABLE`
* `LOW` if multiple config thresholds were missing (Rule 3) OR all engagement scores are equal with no AI signal
* `UNKNOWN` if replay context applies

Set `assessment_basis`:
* `AI_ASSISTED` if `ai_context.channel_priority_adjustment_applied = true`
* `FALLBACK` if `ai_context.fallback_applied = true`
* `HISTORICAL_REPLAY` if `execution_type ∈ {replay, regeneration}`
* `RULE_BASED` otherwise

Emit the completed `ChannelAdvisoryAssessment`.

STOP.

---

## 5. CONFIG VERSION GOVERNANCE

---

### 5.1 Config Resolution Protocol

Before Rule 0 executes, the channel advisory service MUST:

1. Query the Config Version Registry for the **currently ACTIVE version** (`status = ACTIVE`)
2. Extract the full `rule_set_snapshot` from the ACTIVE version record
3. Bind the `config_version_id` to the advisory context
4. Validate that exactly one `ACTIVE` version exists; if zero or multiple exist, emit `GOVERNANCE_PRECONDITION_FAILED` and stop

In replay mode (`execution_type ∈ {replay, regeneration}`), the resolution protocol changes:

1. Extract the `config_registry_version` component from `replay_context.fingerprint`
2. Query the Config Version Registry for that specific historical version (may be `SUPERSEDED` or `ARCHIVED`)
3. If unavailable, block replay — `REPLAY_CONFIG_UNAVAILABLE`; do NOT substitute the current ACTIVE version

Config resolution failure is never silently ignored. An advisory produced without a resolved config version is invalid.

---

### 5.2 Threshold Binding

All threshold comparisons (Rules 6, 7, 10, 11, 12) MUST use values extracted from the resolved config version's `rule_set_snapshot`. No hardcoded channel priority order, engagement thresholds, or delivery failure limits exist in this directive or in any implementation code that executes this channel advisory architecture (AP-C9).

The same student with the same engagement history may receive different channel advisories under different config versions. This is expected behavior (FAD-3, spec/01 §12). Config-version governance is what makes historical reproducibility possible.

---

### 5.3 Config Lineage in Output

Every advisory carries `config_version_id` in `governance_constraints` AND a full `config_version_reference.threshold_bindings` record capturing the specific values resolved from that version. This enables:

* Historical audit of which thresholds governed any channel advisory, without re-querying the config registry
* Replay verification: the stored threshold bindings in the advisory record can be compared against the historical config version's `rule_set_snapshot` to confirm reproducibility
* Channel calibration analysis: downstream observability systems can correlate configured channel priorities with outreach outcome rates across config versions

---

### 5.4 Prospective-Only Semantics (FAD-3 Enforcement)

Activating a new config version does NOT:

* Retroactively change historical channel advisory outputs
* Recalculate channel priorities for historical outreach records
* Alter finalized snapshot cohort classifications
* Trigger reprocessing of any prior student data

Channel advisories under the new config version take effect at the next scheduled evaluation cycle. Prior advisories, and the records they produced, are permanently attributed to the config version in effect when they were made.

---

## 6. REPLAY & REGENERATION SEMANTICS

---

### 6.1 Replay Channel Advisory Behavior

A replay channel advisory evaluation determines what channels were valid candidates at a specific historical point in time. It does not produce any new delivery actions.

Replay channel advisory rules:

* The historical config version governs all threshold evaluations (§5.1)
* `execution_mode` is forced to `SHADOW`; replay advisories are never `LIVE`
* `advisory_scope` is always `REPLAY_CHANNEL_CANDIDATE` for a valid replay — never `CALL_PREFERRED`, `SMS_PREFERRED`, `EMAIL_PREFERRED`, or `MULTI_CHANNEL_ELIGIBLE`
* AI signals for replay use the `ai_finalized_copy` from the source snapshot — no fresh AI analysis is triggered
* `fingerprint_comparison_outcome` is computed and recorded in `replay_restrictions`
* Replay idempotency keys are NOT stored in the operational idempotency store — replay evaluations are read-only with respect to state
* Provider health state in replay uses historical provider health signals from `channel_delivery_history` inputs — not current `provider_health_state`

---

### 6.2 Regeneration Channel Advisory Behavior

Report regeneration context requires historical channel re-evaluation to reconstruct the channel candidacy signals that informed a prior reporting cycle. In this context:

* Historical config version is used; no current ACTIVE version thresholds apply
* AI content is sourced exclusively from snapshot physical copies — no live `ai_insights` queries
* If stored fingerprint components differ from current system state, `fingerprint_comparison_outcome = DIVERGENT`; this does not block regeneration but annotates the output with `POTENTIALLY_DIVERGENT`
* No new channel history records, state transitions, or governance-sensitive writes may result from a regeneration advisory
* `advisory_scope` remains `REPLAY_CHANNEL_CANDIDATE`; regeneration cannot produce `CALL_PREFERRED`, `SMS_PREFERRED`, `EMAIL_PREFERRED`, or `MULTI_CHANNEL_ELIGIBLE` scope

---

### 6.3 SHADOW Execution Semantics

SHADOW mode is the default for all advisories until Phase 12 production governance certification. In SHADOW mode:

* All rules evaluate normally; the advisory is produced with full governance context
* `governance_constraints.live_delivery_permitted = false` regardless of `advisory_scope`
* The consuming outreach orchestration service is responsible for enforcing outbound dispatch suppression based on `execution_mode = SHADOW`
* Governance audit log entries ARE written in SHADOW mode; a SHADOW channel advisory is a real platform event with real audit requirements
* The channel advisory carries no responsibility for SHADOW enforcement; it carries the mode flag and trusts consuming services to respect it

---

### 6.4 Replay Observability Isolation

Every replay advisory must be distinguishable from the original advisory in all log and telemetry output:

* `execution_type: replay` in `observability_metadata`
* `source_artifact_id` referencing the original snapshot or scheduler job in `replay_restrictions`
* `fingerprint_comparison_outcome` in `replay_restrictions`
* `correlation_id` is freshly generated for the replay job; `causation_id` is set to the original job's `correlation_id`
* Replay advisories must not share idempotency keys with original advisories

---

## 7. AI GOVERNANCE

---

### 7.1 AI Governance Principle for Channel Advisement

AI insight output is **advisory for channel prioritization ordering only**. It cannot:

* Override SQL Server-authoritative contact data availability (phone, email presence)
* Override opt-out restrictions applied by Rule 6
* Override provider health prohibitions applied by Rule 7
* Override delivery failure suspensions applied by Rule 10
* Grant channel candidacy to a prohibited channel
* Produce `LIVE` channel advisories unilaterally
* Modify or invalidate historical channel advisories produced under prior config versions
* Override governance blocks (Rules 0, 2, 8)

AI insight output CAN:

* Adjust the ordering of channels within `recommended_channel_candidates` when governance tier is `CONFIDENT` or `ADVISORY` (Rule 12)
* Contribute channel preference context from `ai_channel_preference_signal` and `ai_sentiment` when tier is CONFIDENT
* Set `assessment_basis = AI_ASSISTED` in observability metadata when channel priority adjustment is applied
* Provide contextual signals that the outreach orchestration service uses for operator-facing channel recommendations

---

### 7.2 AI Governance Tier Behavior in Channel Advisory Context

| Tier | Channel advisory behavior | Priority adjustment |
|---|---|---|
| `CONFIDENT` (≥ 0.70 confidence, fresh) | AI `channel_preference_signal` applied to Rule 12 ordering; preference moves preferred channel to position 1 if not prohibited | Full adjustment: preferred channel to position 1 unconditionally within permissible candidates |
| `ADVISORY` (< 0.70 confidence, fresh) | AI signal applied conditionally; only moves channel if engagement history does not contradict | Conditional adjustment: position 1 only when engagement scores are equal or preferred channel has higher responsiveness |
| `STALE` (beyond TTL or failed with prior) | No channel ordering adjustment; stale flag recorded; assessment continues without AI | No adjustment; `STALE_AI_CHANNEL_ADVISORY_SKIPPED` in reason_codes |
| `UNAVAILABLE` (no prior AI_REVIEWED) | Pure rule-based assessment; `fallback_applied = true` | No adjustment; `AI_UNAVAILABLE_FALLBACK_APPLIED` in reason_codes |
| `IN_FLIGHT` | Proceed without AI (Rule 5A); advisory is not deferred | Not applicable; IN_FLIGHT does not defer channel advisory |
| `FINALIZED_COPY` | Immutable snapshot content; not used for new channel advisory decisions | No adjustment; `AI_FINALIZED_COPY_NOT_APPLIED` in reason_codes |

---

### 7.3 Stale AI Protection in LIVE Mode

IF `execution_mode = LIVE` AND `ai_governance_tier = STALE`:

* Do NOT adjust channel ordering based on AI `channel_preference_signal`
* `governance_constraints.live_delivery_permitted` remains governed solely by rule-based assessment and governance gates
* Rule 11's engagement-signal-based ordering governs channel candidate order exclusively
* Add `STALE_AI_LIVE_MODE_RESTRICTED` to `reason_codes`
* The advisory output must explicitly flag the staleness condition so downstream operators are aware

---

### 7.4 AI Snapshot Isolation (FAD-1 Enforcement)

When `ai_finalized_copy = true`:

* The advisory MUST NOT request, apply, or reference live `ai_insights` records for this student in the same evaluation context
* `ai_governance_tier` is set to `FINALIZED_COPY` regardless of the live `ai_insights` record state
* No channel ordering adjustment is applied from the frozen copy — finalized snapshot copies are for report regeneration, not new channel advisory decisions

---

### 7.5 Deterministic Fallback

When AI input is `UNAVAILABLE`, `STALE`, or `IN_FLIGHT`, the advisory MUST produce a deterministic rule-based output using only contact data, engagement history, provider health, and config-bound thresholds. The fallback path is not a degraded mode — it is a fully specified advisory path that satisfies the same correctness and reproducibility requirements as the AI-assisted path.

`ai_context.fallback_applied = true` in the output signals to downstream services that this advisory operated without current AI assistance.

---

## 8. OBSERVABILITY & ATTRIBUTION

---

### 8.1 Required Telemetry per Advisory

Every channel advisory evaluation MUST emit a structured log entry (JSON, to stdout per spec/06 §2) containing:

| Log field | Source |
|---|---|
| `timestamp` | ISO-8601 at advisory start |
| `level` | `info` (normal), `warn` (fallback/stale/provider degraded), `error` (governance gate failure) |
| `service` | `channel_advisory` |
| `event` | `channel_advisory_produced` or `governance_precondition_failed` |
| `correlation_id` | From `governance_context.correlation_id` |
| `causation_id` | From `governance_context.causation_id` (null if root event) |
| `student_id_opaque` | Opaque hash of the student ID — never the raw SQL Server `user_id` |
| `execution_type` | `original`, `replay`, or `regeneration` |
| `execution_mode` | `SHADOW` or `LIVE` |
| `config_version_id` | ID of the resolved config version |
| `advisory_scope` | The scope value produced |
| `channel_advisory_produced` | Boolean |
| `recommended_channel_candidates` | Ordered list of channel enums (no contact PII) |
| `prohibited_channels` | List of prohibited channel enums |
| `ai_governance_tier` | Tier from Rule 5 |
| `channel_suspension_applied` | From `provider_health_metadata` |
| `advisory_confidence` | Confidence value from Rule 13 |
| `rule_path_taken` | Array of rule IDs that fired |
| `assessment_basis` | `RULE_BASED`, `AI_ASSISTED`, `FALLBACK`, or `HISTORICAL_REPLAY` |
| `escalation_recommended` | From `escalation_constraints` |
| `duration_ms` | Advisory duration |
| `outcome` | `success`, `blocked`, `fallback` |
| `error_class` | Populated only on `error` level |

---

### 8.2 Correlation ID Propagation

The `correlation_id` assigned at the triggering scheduler run or operator action MUST propagate without modification through:

* The advisory context inputs
* The `ChannelAdvisoryAssessment` output
* Every downstream service call that consumes the advisory (outreach orchestration service, provider dispatch layer)
* Every database write and audit log entry produced by consuming services

The causal chain from scheduler run → channel advisory → outreach dispatch → state transition → audit log must be reconstructable from a single `correlation_id` query.

---

### 8.3 Attribution Propagation

The attribution fields set in the advisory context (`origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp`) MUST propagate to every downstream record created as a result of consuming this advisory. The channel advisory sets attribution at the `system_automated` / `platform_supplementary` tier; consuming services append their own actor identity but do not overwrite the advisory's attribution context.

Attribution fields are immutable once set. Consuming services MUST NOT rewrite, strip, or reinterpret attribution fields from the advisory output.

---

### 8.4 Channel Advisory Trace Metadata

The `rule_path_taken` field in `observability_metadata` provides a complete trace of which rules fired during this advisory, in order. This trace enables:

* Historical explainability of why a specific channel was recommended, prohibited, or deprioritized
* Channel calibration analysis: which channels produce the highest CONNECTED rates, and how config thresholds correlate with delivery success
* Debugging: when an advisory produces an unexpected scope, the rule path identifies the exact constraint branch

Rule path entries use canonical rule identifiers from §4 (e.g., `["RULE_0", "RULE_1", "RULE_3", "RULE_4", "RULE_5", "RULE_7", "RULE_10", "RULE_11", "RULE_12", "RULE_13"]`).

---

### 8.5 PII Redaction Rules

The following fields MUST NEVER appear in log output, telemetry, or observability metadata:

* Raw `user_id` (SQL Server primary key) → substitute `student_id_opaque` (opaque hash)
* `email` → `***@***`
* `phone_number` → `***`
* Student name → `[REDACTED]`
* AI-generated narrative text → NEVER in logs; stored only in database
* Raw payment amounts with student context → aggregate only

PII redaction applies equally to SHADOW and LIVE mode, to original and replay executions, and to all log levels including debug.

---

## 9. FAILURE & SAFETY SEMANTICS

---

### 9.1 Missing Data Behavior

| Missing field | Governance classification | Response |
|---|---|---|
| `config_version_id` | Governance-critical | Block advisory at Rule 0; `GOVERNANCE_PRECONDITION_FAILED`; do not default to any version |
| `correlation_id` | Governance-critical | Block advisory at Rule 0 |
| `attribution_context` incomplete | Governance-critical | Block advisory at Rule 0 |
| SQL Server-authoritative contact fields (email, phone) | Contact data gate | Evaluate per Rule 4; channels without contact data are prohibited; no fallback to platform-supplementary estimates |
| `provider_health_state` null or absent | Operational fallback | Treat all channels as `HEALTHY`; add `PROVIDER_HEALTH_UNKNOWN` to `reason_codes`; log warning |
| `channel_opt_out_state` null or absent | Operational fallback | Treat all channels as opted-in; add `OPT_OUT_STATE_UNKNOWN` to `reason_codes`; log warning |
| `channel_delivery_failure_counts` null | Operational fallback | Treat all counts as 0; no delivery failure suspension applied; log `DELIVERY_FAILURE_COUNTS_UNKNOWN` |
| `engagement_signal_score` null | Operational fallback | Use `PREFERRED_INITIAL_CHANNEL` config ordering; add `ENGAGEMENT_SIGNAL_UNKNOWN` to `reason_codes` |
| `ai_insight_state` null | AI fallback | Set `ai_governance_tier = UNAVAILABLE`; fallback applies |
| Historical inputs absent | Historical fallback | Continue without historical enrichment; `historical_risk_trend = UNKNOWN`; log warning |

Missing data from SQL Server-authoritative sources blocks channel candidacy at the per-channel contact data level. Missing supplementary or historical data triggers fallback behavior. Unblocked advisories with missing supplementary data must include `MISSING_DATA_FALLBACK_APPLIED` in `reason_codes`.

---

### 9.2 Stale Contact Data

IF `sql_server_sync_timestamp` is older than `sql_server_max_sync_age_hours` (from config):

* Emit `STALE_SQL_SERVER_DATA` warning in log
* Proceed with advisory but include `STALE_DATA_WARNING` in `reason_codes`
* Do NOT produce LIVE channel advisories based on stale SQL Server contact data; force `live_delivery_permitted = false` with `STALE_DATA_SHADOW_OVERRIDE`

---

### 9.3 Invalid Config Resolution

IF the Config Version Registry returns zero or multiple ACTIVE versions:

* Block advisory unconditionally at Rule 0
* Log `CONFIG_REGISTRY_INCONSISTENT` at `error` level with `error_class: ContractViolation`
* Emit escalation alert to the operator notification service
* Do NOT default to hardcoded channel priority order
* Retry config resolution is permitted; if 3 consecutive resolution failures occur, escalate as a production incident

---

### 9.4 Duplicate Channel Advisory Detection

IF `idempotency_key` already exists in the idempotency store for `(student_id, checkpoint_type, cycle_timestamp, contact_attempt_count)`:

* Block advisory at Rule 0
* `IDEMPOTENCY_DUPLICATE` in `reason_codes`
* Do NOT produce a new advisory; the prior advisory for this cycle-attempt key is the canonical record
* Log at `warn` level (duplicates are expected in at-least-once delivery scenarios; they are not errors)

---

### 9.5 Replay Conflict Behavior

| Replay failure scenario | Behavior |
|---|---|
| Historical config version unavailable | Block replay at Rule 9; `REPLAY_CONFIG_UNAVAILABLE`; do not substitute current ACTIVE version |
| Fingerprint components incomplete | Proceed with available components; log `REPLAY_FINGERPRINT_PARTIAL`; set `fingerprint_comparison_outcome = UNKNOWN` |
| Replay context indicates `execution_mode = LIVE` | Override to `SHADOW`; log `REPLAY_MODE_OVERRIDE`; never allow live delivery from replay context |
| Historical channel delivery state unavailable | Block replay at Rule 9; `REPLAY_STATE_UNAVAILABLE`; do not reconstruct from current channel state |
| Fingerprint divergence detected | Continue; set `fingerprint_comparison_outcome = DIVERGENT`; annotate output with `POTENTIALLY_DIVERGENT`; do not block |

---

### 9.6 Stale AI Behavior

IF AI governance tier is `STALE`:

* No channel ordering adjustment (Rule 12)
* Add `STALE_AI_CHANNEL_ADVISORY_SKIPPED` to `reason_codes`
* If `execution_mode = LIVE`, add `STALE_AI_LIVE_MODE_RESTRICTED`
* Include `ai_generated_at` in `ai_context` output so downstream operators know the age of the last AI insight
* Rule 11's engagement-signal-based ordering governs exclusively; fallback is fully deterministic

---

### 9.7 Provider Outage Handling

IF all channels report `provider_health_state = UNAVAILABLE` or `DEGRADED`:

* `CHANNEL_EXHAUSTED` scope is appropriate even if delivery failure counts are below suspension threshold
* Add `SYSTEMIC_PROVIDER_OUTAGE_SUSPECTED` to `reason_codes`
* Log `SYSTEMIC_PROVIDER_OUTAGE_SUSPECTED` at `warn` level
* Escalation recommendation should reflect HIGH urgency in the advisory output

IF `channel_exhaustion_state = EXHAUSTED` arrives pre-computed from the input context:

* Trust the signal; do not require per-channel provider health confirmation
* Add `CHANNEL_EXHAUSTION_CONFIRMED_BY_INPUT` to `reason_codes`
* RULE 8 fires regardless of per-channel probe results

---

### 9.8 Missing Opt-Out Registry State

IF `channel_opt_out_state` is partially populated (some channels present, some absent):

* For channels with explicit opt-out records: apply Rule 6 as normal
* For channels with absent opt-out state: treat as opted-in (conservative default that avoids erroneously suppressing channels)
* Add `OPT_OUT_STATE_PARTIAL_{CHANNEL}` to `reason_codes` for each channel with missing state
* Log `OPT_OUT_REGISTRY_INCOMPLETE` at `warn` level

---

## 10. ARCHITECTURE PRESERVATION RULES

---

The following prohibitions are absolute. No implementation code, configuration change, or emergency workaround may violate them. A violation is a production defect requiring immediate rollback.

| Rule | Prohibition |
|---|---|
| `AP-C1` | The channel advisory MUST NOT directly dispatch outbound delivery. It produces advisories; it does not initiate contact. |
| `AP-C2` | The channel advisory MUST NOT mutate outreach state, channel lineage, or any lifecycle domain state. All state writes belong to consuming services. |
| `AP-C3` | The channel advisory MUST NOT modify the Config Version Registry. Config lifecycle transitions are operator-initiated governance workflows. |
| `AP-C4` | The channel advisory MUST NOT overwrite, modify, or supplement an immutable snapshot's stored content. FINALIZED snapshots are immutable (FAD-1, spec/03 INVARIANT-1). |
| `AP-C5` | The channel advisory MUST NOT overwrite historical advisory outputs. Each advisory is append-only. A re-evaluation produces a NEW advisory record with its own idempotency key and attribution. |
| `AP-C6` | The channel advisory MUST NOT corrupt replay semantics. A replay advisory must produce `REPLAY_CHANNEL_CANDIDATE` scope only; it must not produce `CALL_PREFERRED`, `SMS_PREFERRED`, `EMAIL_PREFERRED`, or `MULTI_CHANNEL_ELIGIBLE` scope that could authorize live delivery. |
| `AP-C7` | The channel advisory MUST NOT bypass the audit trail. Every advisory — including blocked advisories from Rule 0 — must produce a telemetry log entry. |
| `AP-C8` | The channel advisory MUST NOT use platform-supplementary opt-out or delivery signals to override SQL Server-authoritative contact data (phone, email) for channel availability determination. Contact data absence from SQL Server is definitive per channel. |
| `AP-C9` | The channel advisory MUST NOT use hardcoded channel priority orders, engagement thresholds, or delivery failure limits. All threshold comparisons must use values extracted from the resolved config version's `rule_set_snapshot`. |
| `AP-C10` | The channel advisory MUST NOT log raw student PII. `user_id`, name, email, phone, and AI narrative content are prohibited in all log output. Only opaque student identifiers are permitted. |
| `AP-C11` | The channel advisory MUST NOT produce a `CALL_PREFERRED`, `SMS_PREFERRED`, `EMAIL_PREFERRED`, or `MULTI_CHANNEL_ELIGIBLE` scope during replay or regeneration execution. `execution_type ∈ {replay, regeneration}` unconditionally constrains `advisory_scope = REPLAY_CHANNEL_CANDIDATE` and `live_delivery_permitted = false`. |
| `AP-C12` | The channel advisory MUST NOT reuse idempotency keys across advisory evaluation cycles. Each `(student_id, checkpoint_type, cycle_timestamp, contact_attempt_count)` is unique per cycle-attempt pair. |
| `AP-C13` | The channel advisory MUST NOT evaluate channel rules if the GOVERNANCE PRECONDITION GATE (Rule 0) has not passed. No rule evaluation, no output production, and no telemetry beyond the BLOCKED log entry. |
| `AP-C14` | The channel advisory MUST NOT add a prohibited channel (from opt-out, provider health, or delivery failure suspension) to `recommended_channel_candidates` regardless of AI advisory signal. AI cannot override governance-enforced channel prohibitions. |
| `AP-C15` | The channel advisory MUST NOT override or reinterpret attribution fields from inputs. Attribution is set at origin and propagated unchanged through all outputs. |

---

## 11. SCOPE BEHAVIOR

---

### 11.1 Across All Scopes (Non-Negotiable)

Regardless of scope tier, the following are mandatory and cannot be reduced:

* GOVERNANCE PRECONDITION GATE (Rule 0) evaluated before any channel advisory rule
* Config V1 seed as the ACTIVE version at platform initialization (governance invariant: exactly one ACTIVE version)
* No hardcoded channel priority order; all channel preferences from `config_rule_set`
* SHADOW execution mode as default; `live_delivery_permitted = false` until Phase 12 certification
* Idempotency key checked before producing any advisory
* Attribution fields carried on every advisory output
* PII redaction rules in all log output
* AP-C1 through AP-C15 prohibitions enforced
* INVARIANT-1 through INVARIANT-7 from spec/03 §40 respected

---

### 11.2 MVP Scope

MVP scope MAY reduce:

| Reduced behavior | What is acceptable |
|---|---|
| AI channel prioritization | `ai_governance_tier` always `UNAVAILABLE`; pure rule-based advisory; Rules 5, 5A, 12 are no-ops; `fallback_applied = true` on every output |
| Engagement-signal sophistication | `engagement_signal_score` treated as 0.5 (neutral); `PREFERRED_INITIAL_CHANNEL` from config governs ordering |
| Provider health assessment | `provider_health_state` treated as `HEALTHY` for all channels; Rule 7 short-circuits; no per-channel suspension applied |
| Opt-out state | `channel_opt_out_state` treated as all channels opted-in; Rule 6 short-circuits |
| Channel delivery failure suspension | `channel_delivery_failure_counts` treated as 0; Rule 10 short-circuits |

MVP scope MAY NOT:

* Skip config resolution (Rule 3 and the config resolution protocol in §5.1 are mandatory)
* Hardcode any channel priority order
* Violate attribution or lineage guarantees on advisory outputs
* Produce channel advisory scope other than `REPLAY_CHANNEL_CANDIDATE` in replay or regeneration context
* Skip idempotency key validation
* Produce advisories without the governance precondition gate (Rule 0)

---

### 11.3 STANDARD Scope

STANDARD scope enables over MVP:

* AI governance tiers `CONFIDENT` and `ADVISORY` active; Rule 12 channel priority adjustments applied
* Engagement-signal-aware channel prioritization fully active (Rule 11) using config-bound thresholds
* Per-channel opt-out state consumed from opt-out registry (Rule 6)
* Provider health assessment active; `DEGRADED` and `UNAVAILABLE` handling applied (Rule 7)
* Delivery failure channel suspension active using `DELIVERY_FAILURE_CHANNEL_SUSPENSION_THRESHOLD` (Rule 10)
* `STALE` AI detection active using `AI_INSIGHT_TTL_HOURS` config threshold

STANDARD scope MAY NOT produce live delivery advisories. `live_delivery_permitted` remains `false` until Phase 12.

---

### 11.4 PRODUCTION Scope

PRODUCTION scope enables over STANDARD:

* `execution_mode = LIVE` permitted following Phase 12 production governance certification; `live_delivery_permitted = true` once Phase 12 certification is confirmed
* Full provider health state integration from production provider health service
* Full opt-out registry integration from production opt-out service
* AI `channel_preference_signal` from CONFIDENT tier applied to production advisory ordering
* Full engagement signal integration from production GHL message cache
* Full replay and regeneration channel advisory semantics active (Rule 9)
* Fingerprint comparison logging for all replay/regeneration advisories
* Full RBAC enforcement: which operator roles may consume which advisory scope classes

PRODUCTION scope MUST NOT:

* Bypass Phase 12 certification to set `live_delivery_permitted = true`
* Permit AI-only channel preference from STALE governance tier in LIVE mode
* Produce LIVE delivery advisory scope during replay or regeneration execution

---

## 12. ACCEPTANCE CRITERIA

---

### AC-C1 — Deterministic Channel Advisory

**Given** the same student context, the same config version, the same engagement history, and the same AI governance tier
**When** the channel advisory is evaluated twice with identical inputs
**Then** the output `advisory_scope`, `recommended_channel_candidates`, `prohibited_channels`, `reason_codes`, and `rule_path_taken` are identical; no non-deterministic elements appear in the output

---

### AC-C2 — Replay-Safe Advisory

**Given** a replay evaluation context with a historical config version and `execution_type = replay`
**When** the advisory is produced
**Then** `advisory_scope = REPLAY_CHANNEL_CANDIDATE`; `replay_restrictions.live_eligible = false`; `governance_constraints.live_delivery_permitted = false`; no outbound-safe scope (`CALL_PREFERRED`, `SMS_PREFERRED`, `EMAIL_PREFERRED`, `MULTI_CHANNEL_ELIGIBLE`) is produced regardless of channel state values

---

### AC-C3 — Config-Version Reproducibility

**Given** an advisory produced under config version V1
**When** the advisory record is retrieved 30 days later
**Then** `config_version_reference.threshold_bindings` captures the exact threshold values that governed the advisory; no re-query of the config registry is required to verify the channel priority decision

---

### AC-C4 — Attribution Continuity

**Given** an advisory with complete `attribution_context` inputs
**When** the advisory is produced
**Then** `attribution_metadata.origin_source`, `attribution_metadata.origin_authority`, `attribution_metadata.actor_identity`, and `attribution_metadata.attribution_timestamp` in the output match the inputs without modification; `correlation_id` appears in both the advisory output and the corresponding log entry

---

### AC-C5 — Immutable Historical Protection

**Given** a replay advisory is produced for a student's historical outreach cycle
**When** the replay advisory is stored
**Then** the original advisory record for that cycle is not modified, overwritten, or supplemented; the replay produces a new record with its own idempotency key

---

### AC-C6 — Stale AI Protection

**Given** `ai_governance_tier = STALE`
**When** the channel advisory evaluates Rule 12
**Then** `ai_context.channel_priority_adjustment_applied = false`; `recommended_channel_candidates` ordering reflects only Rule 11's rule-based engagement assessment; `STALE_AI_CHANNEL_ADVISORY_SKIPPED` is in `reason_codes`

---

### AC-C7 — SHADOW Isolation

**Given** `execution_mode = SHADOW`
**When** the channel advisory produces any advisory scope
**Then** `governance_constraints.live_delivery_permitted = false` regardless of `advisory_scope`; the consuming orchestration service is responsible for enforcing outbound dispatch suppression; the advisory log confirms SHADOW mode

---

### AC-C8 — Governance Precondition Blocking

**Given** `correlation_id` is null
**When** the channel advisory evaluates Rule 0
**Then** `advisory_blocked = true`; `blocking_reason = "GOVERNANCE_PRECONDITION_FAILED"`; no subsequent rules fire; a telemetry log entry is emitted for the blocked advisory

---

### AC-C9 — Opt-Out Channel Prohibition

**Given** `channel_opt_out_state.SMS = true` and phone_number is present
**When** the channel advisory evaluates Rule 6
**Then** `SMS` appears in `prohibited_channels` and in `governance_constraints.opt_out_channel_exclusions`; `SMS` does not appear in `recommended_channel_candidates`; `SMS_OPT_OUT_ACTIVE` appears in `reason_codes`; AI cannot override this prohibition in Rule 12

---

### AC-C10 — Provider Health Channel Suspension

**Given** `provider_health_state.CALL = UNAVAILABLE`
**When** the channel advisory evaluates Rule 7
**Then** `CALL` appears in `prohibited_channels`; `CALL` does not appear in `recommended_channel_candidates`; `CALL_PROVIDER_UNAVAILABLE` appears in `reason_codes`; `provider_health_metadata.suspended_channels` includes `CALL`

---

### AC-C11 — Channel Exhaustion Escalation

**Given** all eligible channels are prohibited (opt-out, provider health, delivery failure suspension)
**When** the channel advisory evaluates Rule 8
**Then** `advisory_scope = CHANNEL_EXHAUSTED`; `recommended_channel_candidates = []`; `escalation_constraints.escalation_recommended = true`; `channel_advisory_produced = true` (the exhaustion is itself a valid advisory outcome to the orchestration service)

---

### AC-C12 — Contact Data Per-Channel Gate

**Given** `phone_number = null` AND `email` is present
**When** the channel advisory evaluates Rule 4
**Then** `CALL` and `SMS` appear in `prohibited_channels`; `EMAIL` remains in the eligible candidate pool; `NO_PHONE_NUMBER` appears in `reason_codes`; `advisory_scope` reflects email-only candidacy

---

## 13. DOWNSTREAM IMPLICATIONS

---

### 13.1 Outreach Orchestration Service

The outreach orchestration service is the primary consumer of `ChannelAdvisoryAssessment`. Required behavior:

* Must use `recommended_channel_candidates` ordered list to determine delivery attempt sequencing — first element is primary, subsequent elements are fallbacks
* Must suppress outbound dispatch when `live_delivery_permitted = false`
* Must not attempt delivery on any channel in `prohibited_channels`
* Must route to escalation service when `escalation_constraints.escalation_recommended = true`
* Must store the advisory record (append-only) with full governance context before dispatching
* Must validate that current provider state has not changed materially since the advisory was produced (point-in-time check on provider health)

---

### 13.2 Provider Orchestration

The channel advisory identifies candidates and ordering. The provider dispatch layer receives the ordered `recommended_channel_candidates` and executes against each candidate's configured provider:

* CALL candidates are dispatched via GHL voice call API
* SMS candidates are dispatched via GHL SMS API
* EMAIL candidates are dispatched via GHL email API

Provider-level retry logic (network timeouts, rate limits, exponential backoff) belongs entirely to the provider dispatch layer and is not within scope of channel advisory governance.

---

### 13.3 Channel State Feedback Loop

The channel advisory is a point-in-time governance assessment. When the orchestration service executes delivery against a recommended channel and receives a delivery failure, the failure is recorded in `channel_delivery_history` and `channel_delivery_failure_counts`. This updated state becomes input to the next channel advisory evaluation — the channel advisory does not consume real-time delivery feedback; it consumes the persisted state from prior delivery attempts.

This feedback loop means that the channel advisory architecture is naturally adaptive: repeated delivery failures on a channel accumulate in the input state until the suspension threshold is crossed, at which point Rule 10 prohibits that channel in future advisories.

---

### 13.4 Escalation Workflows

`CHANNEL_EXHAUSTED` scope and `escalation_constraints.escalation_urgency` are the authoritative handoff signals to the escalation routing service when all channel candidates are exhausted. The escalation service must:

* Read `escalation_constraints.escalation_reason_codes` to classify the escalation type (opt-out exhaustion vs. provider outage vs. delivery failure suspension)
* Inherit `correlation_id` and `attribution_metadata` from the advisory for lineage continuity
* Not re-evaluate channel candidacy; the advisory is the definitive input for escalation routing

---

### 13.5 Retry Policy Integration

The channel advisory is consulted by the outreach orchestration service after the retry policy (`directives/outreach_retry_policy.md`) confirms `RETRY_ELIGIBLE` scope. The retry policy's `retry_constraints.channel_exhaustion_state` field provides a pre-computed exhaustion signal; the channel advisory provides the per-channel resolution of that signal. Both assessments must be consistent: if the retry policy carries `channel_exhaustion_state = EXHAUSTED`, the channel advisory is expected to produce `CHANNEL_EXHAUSTED` scope.

If these signals disagree (retry policy signals AVAILABLE but channel advisory evaluates to EXHAUSTED), the channel advisory's per-channel assessment governs — it has evaluated all constraint layers and has the more complete picture.

---

### 13.6 Observability

Key channel advisory metrics for monitoring:

* `advisory_scope` distribution: `CALL_PREFERRED` / `SMS_PREFERRED` / `EMAIL_PREFERRED` / `MULTI_CHANNEL_ELIGIBLE` / `CHANNEL_EXHAUSTED` ratios signal whether channel availability is healthy and whether config engagement thresholds are correctly calibrated
* `prohibited_channels` frequency by channel and reason code: reveals opt-out rates, provider health trends, and delivery failure accumulation patterns
* `advisory_confidence` distribution: signals when engagement data quality degrades (shift toward LOW and UNKNOWN confidence)
* `channel_suspension_applied` rate: surface delivery failure suspension trends before they produce fleet-wide CHANNEL_EXHAUSTED events
* AI channel priority adjustment rate by tier: signals when AI channel preference signals are consistently overriding engagement-based ordering

---

### 13.7 APIs

The `ChannelAdvisoryAssessment` schema (§3.1) is the contract exposed to consuming services. Breaking changes to this schema require a coordinated PR that updates all consumers in the same diff. `config_version_reference.threshold_bindings` must remain backward-compatible with historical advisory records; new threshold fields may be added but existing fields may not be removed without a deprecation path. The `recommended_channel_candidates` field ordering is part of the contract — consumers that depend on array position for primary channel determination must not be broken by schema changes that alter ordering conventions.

---

## 14. UNRESOLVED ARCHITECTURAL CONCERNS

---

| ID | Concern | Impact |
|---|---|---|
| `UC-1` | Config V1 `rule_set_snapshot` must be audited for all 8 threshold variables introduced in Rule 3 (`outreach_initial_channel_preference`, `channel_delivery_failure_suspension_threshold`, `call_engagement_score_threshold`, `sms_engagement_score_threshold`, `email_engagement_score_threshold`, `channel_specific_cooldown_hours`, `channel_opt_out_respect_period_hours`, `ai_insight_ttl_hours`). If any are absent, the corresponding rules short-circuit with missing-threshold fallback behavior. V1 seed schema must be audited before STANDARD scope enablement. | STANDARD |
| `UC-2` | Opt-out registry source authority is unspecified. `channel_opt_out_state` is classified as `platform_supplementary`, but the update mechanism (GHL webhook-driven vs. operator manual entry vs. SQL Server-authoritative consent record) is not defined. Until specified, Rule 6 uses whatever state is present in `channel_opt_out_state`; missing state defaults to opted-in (conservative). | STANDARD |
| `UC-3` | Provider health service source is unspecified. `provider_health_state` is classified as `platform_supplementary`, but whether it comes from a dedicated provider health check service, GHL webhook delivery receipts, or outreach history aggregation is not defined. Until specified, MVP treats all channels as `HEALTHY`. | STANDARD |
| `UC-4` | Channel advisory idempotency key dimension — the key `(student_id, checkpoint_type, cycle_timestamp, contact_attempt_count)` uses `contact_attempt_count` as the fourth dimension (parallel to retry policy's `retry_attempt_number`). This means a student can receive multiple channel advisories within the same cycle timestamp if attempts are numbered. The question of whether a channel advisory should be produced once per cycle or once per outreach attempt must be resolved to finalize the idempotency key design. If per-cycle, the key reduces to 3 components (dropping `contact_attempt_count`). | STANDARD |
| `UC-5` | Channel advisory invocation boundary — whether this advisory is evaluated by the outreach orchestration service before every delivery attempt (per-attempt advisory) or once per retry cycle (per-retry advisory) is architecturally unresolved. Per-attempt enables the advisory to reflect updated provider health state between attempts within the same retry cycle; per-retry is simpler and aligned with the retry policy's evaluation model. This decision affects Rule 10 (delivery failure suspension) behavior: per-attempt mode allows real-time suspension within a cycle; per-retry mode only applies suspension on the next retry cycle. | PRODUCTION |

---

## 15. REFERENCES

---

This directive defines the channel orchestration advisory architecture. It is subordinate to the following in case of conflict (highest to lowest precedence):

* `directives/core_decision_engine.md` — the orchestration-intelligence authority; INITIATE_OUTREACH and RETRY_OUTREACH intents that channel advisement serves; AI governance model; replay semantics; attribution standard
* `directives/outreach_eligibility_rules.md` — eligibility scope architecture; governance precondition gate pattern; AP-E governance rules; scope behavior tiers
* `directives/outreach_retry_policy.md` — retry governance; channel_exhaustion_state signal passed to channel advisory; retry scope ceiling in replay context; AP-R governance rules
* `spec/03_state_transition_rules.md` — §40 INVARIANT-1 through INVARIANT-7; Outreach domain state machine; CLOSED terminal state; Domain 6 compliance governance
* `spec/01_requirements.md` — FAD-1 through FAD-6; §2.3 operational domains; §12 configurable rule governance
* `spec/04_idempotency_concurrency.md` — idempotency key design; at-least-once delivery; dedup table pattern
* `spec/05_external_integrations.md` — §2.3 lineage-preserving integration; §3 SQL Server synchronization governance; GHL integration semantics
* `spec/06_observability_operations.md` — structured logging contract; governance telemetry vs operational telemetry; correlation ID propagation
* `spec/09_security_privacy.md` — PII redaction requirements; opaque student identifier model
* `execution/build_phases.md` — Phase 12 LIVE certification requirements; governance-first sequencing
* `execution/implementation_plan.md` — service implementation ordering; SHADOW → LIVE model

---

## END OF FILE
