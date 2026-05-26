# directives/llm_processing_contract.md

---

## LAYER 3 — DIRECTIVES (AI ORCHESTRATION CONTRACT ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governance-safe AI orchestration architecture established across `directives/core_decision_engine.md`, `directives/outreach_eligibility_rules.md`, `directives/outreach_retry_policy.md`, and `directives/escalation_rules.md`. The previous version described a simple LLM integration contract (transcript ingestion, hardcoded sentiment/issues/meeting_recommended output schema, binary retry/fallback handling) that is architecturally incompatible with the governance-aware orchestration-intelligence platform defined in spec/01 through spec/09. AI is no longer a transcript-to-output pipeline. It is a governance-safe advisory intelligence layer operating under config-version governance, replay-safe semantics, and immutable lineage guarantees.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **AI Orchestration Contract Architecture** defines the governance-safe AI advisement layer of the Student Success Intelligence Platform. It specifies:

* The canonical role of AI in the platform as an advisory intelligence layer, not a workflow authority
* The six-tier AI governance model that classifies AI insight state and determines advisory scope at any given moment
* The governance preconditions that must hold before AI evaluation may proceed
* How config-version-governed thresholds (TTL, confidence ceilings, provider selection) determine AI governance tier assignment and advisory scope
* How replay, regeneration, and SHADOW execution semantics constrain AI output behavior and prevent live AI provider calls during historical replay
* How immutable snapshot AI content (FINALIZED_COPY) is served without re-inference and without post-finalization mutation
* How provider failure states, inference timeouts, and confidence collapse are handled deterministically without silent substitution or hidden fallback models
* What attribution, observability, and lineage metadata must accompany every AI advisory output to ensure all AI advisories remain historically explainable

This directive is the authoritative specification for **governance-safe AI orchestration advisement**. It is consumed by:

* The Core Decision Engine (`directives/core_decision_engine.md`) when it incorporates AI advisory signals into its `RECOMMEND_INTERVENTION` and `DEFER_PENDING_AI` intent pathways
* The outreach eligibility service when AI insight confidence and governance tier influence orchestration priority scoring
* The escalation rules service (`directives/escalation_rules.md`) when AI governance tier and confidence are evaluated as advisory severity adjusters (Rules 5, 14)
* The snapshot orchestration service when AI narrative content is physically copied into FINALIZED snapshot records
* The report orchestration service when AI narrative sourcing for historical regeneration must be resolved from FINALIZED_COPY rather than live inference

---

### 1.2 What AI Is in This Platform

AI in the Student Success Intelligence Platform is:

* **Advisory intelligence layer** — AI insights inform orchestration priority, risk summary narrative, and intervention recommendation. AI does not govern these decisions; it enriches them.
* **Prioritization assistant** — AI confidence scores and sentiment outputs contribute to orchestration priority scoring alongside deterministic rule-based signals. AI advisory weight is bounded by AP-AI14.
* **Summarization engine** — AI produces natural-language risk summaries, engagement narratives, and student profile summaries for operator-facing dashboards and reports. These are presentation-layer advisory content, not governance state.
* **Enrichment provider** — AI supplements SQL Server-authoritative academic signals with trend interpretation, pattern recognition across historical data, and context inference. AI-derived enrichment does not override SQL Server-authoritative values (INVARIANT-6, spec/03 §40).
* **Narrative generation assistant** — AI generates narrative text physically copied into FINALIZED snapshot records. Once physically copied, that text is immutable (FAD-1, spec/01 §12.5.4).
* **Orchestration support layer** — AI output in the `DEFER_PENDING_AI` intent pathway (Core Decision Engine Rule 8) signals that an orchestration decision should wait for AI insight generation to complete before proceeding. This is advisory to the scheduler; the scheduler decides how long to wait.

---

### 1.3 What AI Is NOT in This Platform

To prevent scope creep and architectural boundary violations, this directive explicitly defines what AI does NOT do:

* **Is not a governance decision-maker.** No AI output may authorize, block, or override deterministic governance decisions, lifecycle state transitions, eligibility classifications, or config-bound threshold evaluations. Governance is always deterministic; AI is always advisory.
* **Is not a workflow execution authority.** AI does not trigger outreach, dispatch notifications, assign escalation cases, create Basecamp tasks, or execute any side effect. Every AI advisory output is consumed by an orchestration service; the service decides whether and how to act.
* **Is not an autonomous escalation trigger.** AI insights may elevate escalation severity above a rule-based baseline only when rule-based escalation candidacy signals already exist. AI cannot create escalation candidacy where rules find none (AP-AI14; mirrors escalation AP-X14).
* **Is not allowed to mutate student lifecycle state.** AI outputs never directly write state transitions. All state writes belong to the state management service.
* **Is not allowed to override INVARIANT-1 through INVARIANT-7.** AI operates within the governance invariants defined in spec/03 §40. AI that would violate any invariant is classified as exceeding its advisory ceiling (spec/01 §12.5.3) and must be blocked.
* **Is not allowed to call live AI providers during replay.** All replay paths that require AI content resolve it exclusively from physically stored snapshot copies (`warehouse.snapshot_ai_narratives`). Any code path that calls an AI provider during replay is a specification violation (AP-AI5; spec/01 §12.5.5).
* **Is not allowed to regenerate FINALIZED_COPY AI content.** AI content that has been physically copied into a FINALIZED snapshot is immutable. No post-finalization operation — force-refresh, AI provider change, compliance deletion of `ai_insights` records, model upgrade — may alter frozen snapshot AI text (AP-AI12; FAD-1).

---

### 1.4 Seven AI Advisory Categories

AI governance produces multiple distinct advisory categories. The following categories are defined:

| Category | Definition | Governing rule(s) |
|---|---|---|
| **Governance candidacy** | Governance preconditions are met; AI evaluation may proceed; no governance block applies | Rule 0 |
| **AI tier classification** | The AI insight's freshness, confidence, and state determine its governance tier (CONFIDENT through FINALIZED_COPY) | Rules 3, 5 |
| **Advisory scope determination** | The assigned tier determines the scope of advisory influence permitted in orchestration (FULL, LIMITED, UNAVAILABLE, IMMUTABLE) | Rule 6 |
| **Replay-safe AI resolution** | Historical replay resolves AI content from FINALIZED_COPY; live inference is suppressed; replay isolation semantics are enforced | Rule 4, §7 |
| **Deterministic degradation** | Provider failure, inference timeout, STALE tier, and UNAVAILABLE tier produce deterministic fallback behavior with full observability | Rules 7, 8, §10 |
| **Attribution continuity** | Every AI advisory output carries full attribution, lineage, and observability metadata enabling historical explainability | Rule 9, §9 |
| **Immutable snapshot eligibility** | AI content qualifies for physical copy into a FINALIZED snapshot only under defined conditions; post-finalization mutability is prohibited | Rule 10, §7.3 |

---

## 2. AI GOVERNANCE TIERS

---

### 2.1 Tier Definitions

The AI governance tier is assigned per evaluation based on the AI insight's freshness, confidence score, and lifecycle state. The tier governs the advisory scope permitted to that insight in any given orchestration context.

| Tier | Assignment Condition | Advisory Scope | Replay Behavior | LIVE Escalation | Degradation Expected |
|---|---|---|---|---|---|
| `CONFIDENT` | `ai_confidence_score ≥ confidence_ceiling_threshold` AND `insight_age ≤ ai_insight_ttl_hours` AND `ai_insight_state = AI_REVIEWED` | FULL — insight may influence priority, severity adjustment, and intervention recommendation | Suppressed; FINALIZED_COPY serves instead | Permitted as severity adjuster when rule-based signals exist | None |
| `ADVISORY` | `ai_confidence_score < confidence_ceiling_threshold` AND `insight_age ≤ ai_insight_ttl_hours` AND `ai_insight_state = AI_REVIEWED` | LIMITED — insight informs priority scoring only; cannot drive LIVE escalation severity escalation independently | Suppressed; FINALIZED_COPY serves instead | NOT permitted as standalone severity driver | None |
| `STALE` | `insight_age > ai_insight_ttl_hours` AND `ai_insight_state = AI_REVIEWED` | LIMITED — insight is served with `stale: true` annotation; cannot drive LIVE escalation or upgrade severity above rule-based baseline | Suppressed; FINALIZED_COPY serves instead | BLOCKED — STALE AI must not drive LIVE escalation (AP-AI11) | Annotation required: `stale_for_hours` appended to all outputs |
| `IN_FLIGHT` | `ai_insight_state IN (AI_GENERATING, AI_PENDING, AI_QUEUED)` | DEFERRED — orchestration decision deferred via `DEFER_PENDING_AI` intent; prior tier insight used if available with ADVISORY scope | Not applicable — in-flight insights do not exist at replay time | BLOCKED — in-flight state cannot drive escalation | Decision engine returns `DEFER_PENDING_AI` |
| `UNAVAILABLE` | `ai_insight_state IN (AI_GENERATION_FAILED, AI_ARCHIVED)` OR `insight is null` OR `inference call failed` | NONE — no AI advisory influence; orchestration proceeds on rule-based signals only | Suppressed; FINALIZED_COPY serves or no AI content served | BLOCKED — unavailable AI must not drive escalation (AP-AI11) | Full degradation: rule-based only mode; `AI_UNAVAILABLE` reason code |
| `FINALIZED_COPY` | `ai_finalized_copy = true` (physically copied into `warehouse.snapshot_ai_narratives`) | IMMUTABLE — served as-is for regeneration and historical display; no advisory influence on live orchestration | This IS the replay AI source; served exactly as stored | Not applicable — FINALIZED_COPY is never used in live escalation evaluation | None; immutable state; mutation is a specification violation |

---

### 2.2 Tier Assignment Precedence

When multiple conditions could apply, tier assignment follows this precedence:

1. **FINALIZED_COPY** — always takes precedence when `ai_finalized_copy = true`. No tier re-evaluation.
2. **UNAVAILABLE** — applies when insight record is null, inference failed, or insight state is terminal-failure.
3. **IN_FLIGHT** — applies when insight state is generating/pending; checked before staleness.
4. **STALE** — applies when insight exists and is `AI_REVIEWED` but age exceeds TTL.
5. **ADVISORY** — applies when insight is fresh but confidence is below threshold.
6. **CONFIDENT** — applies only when both freshness and confidence conditions are met.

---

### 2.3 Config-Bound Tier Boundaries

Tier boundaries are not hardcoded. They resolve from the ACTIVE config version's `rule_set_snapshot` per Rule 3:

* **TTL boundary** → `ai_insight_ttl_hours` (Group H, `ai_insight_ttl_hours`, default 24H, class OPERATIONAL_TUNING)
* **Confidence boundary** → `ai_confidence_ceiling_threshold` (not a separate catalog entry; the threshold used is derived from the orchestration context — see Rule 5)
* **Provider selection** → `ai_llm_provider` (Group H, class ARCHITECTURAL_CONSTANT)

No hardcoded values may appear in tier assignment logic (AP-AI9).

---

## 3. INPUT MODEL

---

The AI processing context is **lineage-aware and governance-aware**. Every input carries metadata establishing its authority class and origin. AI inputs operate on SQL Server-authoritative academic signals but do not override them. AI advisory outputs are bounded to the advisory scope permitted by the resolved governance tier.

---

### 3.1 Governance Context

Governance context is mandatory for every AI evaluation. AI assessments produced without full governance context are invalid and must not be surfaced as actionable.

| Field | Type | Description |
|---|---|---|
| `config_version_id` | string | ID of the ACTIVE config version at evaluation time; must be resolved before Rule 0 executes |
| `config_version_status` | enum | Status of the resolved config version: `ACTIVE` (operational) or `SUPERSEDED` (replay only) |
| `execution_mode` | enum | Platform execution mode: `SHADOW` (default; no outbound effects) or `LIVE` (requires Phase 12 certification) |
| `execution_type` | enum | `original`, `replay`, or `regeneration`; drives replay-safety rules (§7) |
| `correlation_id` | uuid | UUID v4 propagated from the triggering scheduler run or operator action; required for all evaluations |
| `causation_id` | uuid | UUID v4 of the upstream orchestration intent that triggered this AI evaluation; enables multi-hop lineage |
| `attribution_context` | object | Full attribution metadata: `origin_source`, `origin_authority`, `actor_identity`, `attribution_timestamp` |
| `fingerprint_context` | object | Snapshot Reproducibility Fingerprint components at evaluation time: `schema_version`, `configuration_registry_version`, `ai_prompt_version`, `ai_model_version`, `report_template_version` |
| `idempotency_key` | string | AI evaluation idempotency key `(student_id, checkpoint_type, cycle_timestamp)` to prevent duplicate AI calls |
| `compliance_hold_flag` | boolean | True if the student's snapshot is under `COMPLIANCE_HOLD`; blocks certain AI evaluation paths |
| `replay_context` | object | If `execution_type = replay`: `is_replay: true`, `source_correlation_id`, `historical_config_version_id`, `source_artifact_id`, `replay_lineage_chain` |

---

### 3.2 Attribution Context

Attribution context drives lineage propagation through the AI advisory output. Every AI assessment output must carry this context unchanged from input (AP-AI15).

| Field | Type | Authority | Description |
|---|---|---|---|
| `origin_source` | enum | Input passthrough | How this evaluation was triggered: `system_automated`, `operator`, `scheduler`, `replay_engine` |
| `origin_authority` | enum | Input passthrough | Governance authority class of the triggering event: `platform_supplementary`, `sql_server_authoritative`, `operator_initiated` |
| `actor_identity` | string | Input passthrough | Identity of the triggering actor (e.g., `decision_engine_v2`, `snapshot_orchestrator_v1`, `replay_engine_v1`) |
| `attribution_timestamp` | datetime | Input passthrough | ISO-8601 timestamp of the triggering event; used as the attribution anchor in all lineage records |
| `upstream_intent_id` | string | Input passthrough | ID of the upstream orchestration intent that prompted this AI evaluation; nullable for standalone AI generation |
| `upstream_correlation_id` | uuid | Input passthrough | Correlation ID of the upstream call chain; must match `correlation_id` in governance context |

---

### 3.3 Historical Context

Long-term AI insight history and snapshot lineage enabling continuity assessment, trend interpretation, and replay source resolution.

| Field | Type | Description |
|---|---|---|
| `prior_ai_versions` | list | Version history of AI insights for this student: up to 5 most recent entries with `version_number`, `generated_at`, `governance_tier`, `confidence_score`, `sentiment` |
| `prior_snapshot_months` | list | Months for which this student has a FINALIZED snapshot; each entry carries `snapshot_month`, `ai_finalized_copy`, `ai_model_version`, `ai_prompt_version` |
| `most_recent_finalized_ai_copy` | object | Physical copy reference from the most recent FINALIZED snapshot: `snapshot_id`, `ai_narrative_hash`, `model_version_at_finalization`, `prompt_version_at_finalization` |
| `replay_lineage` | list | For replay evaluations: chain of prior replay runs for this student with outcomes and config version references |
| `historical_report_lineage` | list | Prior report generation events: generation timestamps, config versions used, finalization outcomes, POTENTIALLY_DIVERGENT flags |
| `ai_sentiment_trend` | enum | Trend derived from prior AI insight sentiment: `IMPROVING`, `STABLE`, `DECLINING`, `CRITICAL`, `INSUFFICIENT_HISTORY`; advisory only |

---

### 3.4 AI Context

Current AI insight state, provider metadata, and confidence signals driving tier assignment.

| Field | Type | Description |
|---|---|---|
| `ai_insight_id` | uuid | Primary key of the relevant `ai_insights` record; null if no insight exists |
| `ai_insight_state` | enum | Current lifecycle state: `AI_PENDING`, `AI_GENERATING`, `AI_GENERATED`, `AI_REVIEWED`, `AI_GENERATION_FAILED`, `AI_ARCHIVED`, `AI_QUEUED` |
| `ai_insight_version` | integer | `version_number` of the AI insight record; used for staleness tracking and lineage continuity |
| `ai_generated_at` | datetime | Timestamp of AI insight generation; used to compute insight age against `ai_insight_ttl_hours` |
| `ai_confidence_score` | float | Model-reported confidence (0.0–1.0); drives tier boundary assessment in Rule 5 |
| `ai_prompt_version` | string | Prompt template version identifier used for this insight; must match the fingerprint component |
| `ai_model_used` | string | LLM model identifier used for this insight; must match `ai_llm_provider` config value |
| `ai_stale_flag` | boolean | True if insight age exceeds `ai_insight_ttl_hours` from the ACTIVE config; computed pre-evaluation |
| `ai_finalized_copy` | boolean | Whether this AI content is a snapshot-frozen physical copy (`warehouse.snapshot_ai_narratives`); if true, Rule 2 applies immediately |
| `ai_input_metrics_hash` | string | Hash of the student input metrics used to generate this insight; used for reproducibility verification in replay |
| `ai_risk_summary` | string | Risk summary narrative from the most recent `AI_REVIEWED` insight; advisory text for operator display |
| `ai_recommended_intervention` | enum | AI's recommended intervention pathway: `NONE`, `OUTREACH`, `MEETING`, `RESOURCE_DELIVERY`, `ESCALATE`; advisory only |
| `ai_sentiment` | string | Sentiment classification: `positive`, `neutral`, `negative`, `critical`; advisory only |

---

### 3.5 Operational Context

Provider state, inference retry history, and orchestration degradation state affecting AI evaluation behavior.

| Field | Type | Description |
|---|---|---|
| `provider_degradation_state` | enum | Current state of the AI provider: `OPERATIONAL`, `DEGRADED`, `UNAVAILABLE`, `RATE_LIMITED`, `CIRCUIT_OPEN`; sourced from provider health service |
| `inference_retry_count` | integer | Count of inference retries attempted in this evaluation cycle; used to assess exhaustion state |
| `inference_last_failure_type` | enum | Type of the most recent inference failure: `TIMEOUT`, `RATE_LIMIT`, `PROVIDER_ERROR`, `INVALID_RESPONSE`, `AUTH_FAILURE`; null if no failure |
| `inference_last_failure_timestamp` | datetime | Timestamp of the most recent inference failure in this cycle; null if no failure |
| `orchestration_degradation_mode` | boolean | True if the orchestration layer is operating in degraded mode (e.g., AI unavailable, rule-based only) |
| `circuit_breaker_state` | enum | AI provider circuit breaker state: `CLOSED` (normal), `HALF_OPEN` (testing recovery), `OPEN` (failing fast) |
| `provider_retry_budget_remaining` | integer | Remaining inference retry attempts before exhaustion per `provider_failure_retry_limit` config key |

---

## 4. OUTPUT MODEL

---

### 4.1 AIAssessment Schema

The AI orchestration contract produces a single **governance-safe AIAssessment** per evaluation. The assessment is advisory: it does not execute actions, does not mutate state, and does not enforce governance boundaries. Consuming orchestration services incorporate the assessment into their intent production under governance enforcement.

```json
{
  "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | IN_FLIGHT | UNAVAILABLE | FINALIZED_COPY",
  "advisory_scope": "FULL | LIMITED | UNAVAILABLE | IMMUTABLE | DEFERRED",
  "advisory_content": {
    "sentiment": "positive | neutral | negative | critical | null",
    "risk_summary": "string | null",
    "recommended_intervention": "NONE | OUTREACH | MEETING | RESOURCE_DELIVERY | ESCALATE | null",
    "prioritization_signal": "HIGH | MEDIUM | LOW | null",
    "sentiment_trend": "IMPROVING | STABLE | DECLINING | CRITICAL | INSUFFICIENT_HISTORY | null",
    "narrative_available": false,
    "advisory_confidence": 0.0
  },
  "replay_restrictions": {
    "is_replay": false,
    "replay_safe": true,
    "live_inference_suppressed": false,
    "source_artifact_id": null,
    "historical_config_version_id": null,
    "replay_ai_source": "FINALIZED_COPY | NONE | null"
  },
  "attribution_metadata": {
    "origin_source": "system_automated | operator | scheduler | replay_engine",
    "origin_authority": "platform_supplementary",
    "actor_identity": "ai_assessment_v{N}",
    "attribution_timestamp": "ISO-8601",
    "upstream_intent_id": null,
    "upstream_correlation_id": "uuid | null"
  },
  "config_version_reference": {
    "config_version_id": "string",
    "config_version_status": "ACTIVE | SUPERSEDED",
    "ai_ttl_hours_applied": 0,
    "ai_provider_applied": "string",
    "threshold_bindings": {
      "ai_insight_ttl_hours": 0,
      "ai_llm_provider": "string"
    }
  },
  "model_version_metadata": {
    "provider": "string",
    "model_identifier": "string",
    "prompt_version": "string",
    "ai_version_number": 0,
    "provider_config_key": "ai_llm_provider"
  },
  "confidence_metadata": {
    "confidence_score": 0.0,
    "confidence_tier": "HIGH | MEDIUM | LOW | UNSCORED",
    "stale_flag": false,
    "stale_for_hours": 0,
    "insight_age_hours": 0,
    "ttl_hours_applied": 0
  },
  "degradation_metadata": {
    "degraded": false,
    "degradation_cause": "PROVIDER_UNAVAILABLE | INFERENCE_TIMEOUT | STALE_AI | CONFIDENCE_COLLAPSE | CIRCUIT_OPEN | null",
    "fallback_applied": false,
    "fallback_type": "RULE_BASED_ONLY | PRIOR_VERSION | FINALIZED_COPY | null",
    "orchestration_continues": true
  },
  "observability_metadata": {
    "correlation_id": "uuid",
    "causation_id": "uuid | null",
    "execution_type": "original | replay | regeneration",
    "service": "ai_assessment",
    "rule_path_taken": [],
    "assessment_basis": "RULE_BASED | AI_ASSISTED | FALLBACK | FINALIZED_COPY | HISTORICAL_REPLAY",
    "inference_duration_ms": 0,
    "outcome": "success | failure | degraded | deferred",
    "error_class": null
  },
  "immutable_snapshot_eligibility": {
    "eligible_for_snapshot": false,
    "eligibility_reason": "string | null",
    "finalized_copy": false,
    "snapshot_version_reference": null
  },
  "reason_codes": [],
  "ai_blocked": false,
  "blocking_reason": null
}
```

---

### 4.2 Advisory Scope Values

| Scope | Permitted Influence | Conditions |
|---|---|---|
| `FULL` | Priority scoring, severity adjustment, intervention recommendation, narrative display | Tier = CONFIDENT |
| `LIMITED` | Priority scoring and narrative display only; no severity adjustment; no LIVE escalation driving | Tier = ADVISORY or STALE |
| `IMMUTABLE` | Narrative display from physical copy only; no live orchestration influence | Tier = FINALIZED_COPY |
| `DEFERRED` | No influence until inference completes; prior advisory scope applies from most recent ADVISED version | Tier = IN_FLIGHT |
| `UNAVAILABLE` | No AI advisory influence; orchestration proceeds on rule-based signals exclusively | Tier = UNAVAILABLE |

---

### 4.3 Output Clarifications

* **AI assessments are advisory.** The `advisory_content` fields are recommendations to consuming orchestration services. Deterministic rule evaluation governs eligibility decisions; AI advisory signals enrich those decisions within the advisory scope.
* **The AI assessment never writes to the database.** No INSERT, UPDATE, or DELETE arises from producing an AIAssessment. All database writes — `ai_insights` records, `snapshot_ai_narratives` rows, audit log entries — belong to the consuming service.
* **The assessment carries full governance context.** Every downstream service consuming the assessment receives `governance_requirements`, `attribution_metadata`, and `observability_metadata` needed to execute with governance fidelity.
* **Advisory content is null-safe.** All `advisory_content` fields are nullable. A null field means no advisory signal is available for that dimension — it does not mean the field was omitted in error. Consuming services must handle null advisory content gracefully by proceeding on rule-based logic.
* **Degradation is always explicit.** When AI advisory content is unavailable or limited, `degradation_metadata.degraded = true` and `fallback_type` is set. Silent degradation is prohibited (AP-AI8).

---

## 5. RULES

---

Rules are evaluated in the order defined below. **Stop at the first terminal rule unless otherwise stated.** Each rule that fires appends its identifier to `rule_path_taken` in `observability_metadata`.

Non-terminal rules (marked `CONTINUE`) contribute state to subsequent rules. Terminal rules (marked `STOP`) produce the final AIAssessment immediately.

---

### RULE 0 — GOVERNANCE PRECONDITION GATE

**This rule is mandatory. No subsequent rules execute if this rule blocks.**

BLOCK AI evaluation IF:

* `config_version_id` is null (config resolution failed)
* `execution_mode` is not one of `SHADOW`, `LIVE`
* `correlation_id` is null
* `attribution_context` is incomplete (missing any required field from §3.2)
* `idempotency_key` already exists for this `(student_id, checkpoint_type, cycle_timestamp)` in the dedup store
* `execution_type` is not one of `original`, `replay`, `regeneration`

THEN:

```json
{
  "ai_governance_tier": "UNAVAILABLE",
  "advisory_scope": "UNAVAILABLE",
  "ai_blocked": true,
  "blocking_reason": "GOVERNANCE_PRECONDITION_FAILED",
  "reason_codes": ["CONFIG_UNRESOLVED | EXECUTION_MODE_INVALID | CORRELATION_ID_MISSING | ATTRIBUTION_INCOMPLETE | IDEMPOTENCY_DUPLICATE | EXECUTION_TYPE_INVALID"]
}
```

STOP.

---

### RULE 1 — FINALIZED_COPY ISOLATION CHECK

**This rule is mandatory. If AI content is FINALIZED_COPY, no re-inference or re-evaluation may occur.**

IF `ai_finalized_copy = true`:

* Assign tier: `FINALIZED_COPY`
* Assign scope: `IMMUTABLE`
* Source `advisory_content` from the physically stored text in `warehouse.snapshot_ai_narratives` — NOT from `ai_insights` and NOT from a new inference call
* Set `replay_restrictions.replay_ai_source = FINALIZED_COPY`
* Set `immutable_snapshot_eligibility.finalized_copy = true`

THEN:

```json
{
  "ai_governance_tier": "FINALIZED_COPY",
  "advisory_scope": "IMMUTABLE",
  "reason_codes": ["AI_FINALIZED_COPY_SERVING"]
}
```

STOP. No re-inference permitted. No tier re-evaluation. No advisory scope expansion.

This enforces FAD-1 (spec/01 §12.5.4): AI text physically copied into a FINALIZED snapshot is immutable. Post-finalization operations must not affect frozen snapshot AI text.

---

### RULE 2 — REPLAY MODE GATE

**This rule is mandatory for replay and regeneration execution types.**

IF `execution_type IN (replay, regeneration)`:

* Live AI provider calls are prohibited (AP-AI5; spec/01 §12.5.5)
* AI content must be sourced exclusively from `warehouse.snapshot_ai_narratives` using the historical `source_artifact_id`
* If no FINALIZED_COPY exists for the relevant historical context, set `ai_governance_tier = UNAVAILABLE` with reason code `REPLAY_AI_SOURCE_MISSING`
* Set `replay_restrictions.live_inference_suppressed = true`
* Resolve AI config thresholds from the historical config version (`replay_context.historical_config_version_id`), NOT from the ACTIVE version (per spec/01 §12.4.1)
* Set `replay_restrictions.historical_config_version_id` from `replay_context.historical_config_version_id`

THEN:

```json
{
  "replay_restrictions": {
    "is_replay": true,
    "live_inference_suppressed": true,
    "replay_ai_source": "FINALIZED_COPY | NONE"
  },
  "reason_codes": ["REPLAY_MODE_ACTIVE"]
}
```

CONTINUE to Rule 3 using historical config version.

---

### RULE 3 — CONFIG-BOUND THRESHOLD RESOLUTION

**This rule is non-terminal. Execute before any threshold-dependent rule.**

Resolve from `config_rule_set` (ACTIVE config version's `rule_set_snapshot`, or historical version's snapshot if Rule 2 applied):

| Threshold variable | Config key | Used in rule |
|---|---|---|
| `AI_INSIGHT_TTL_HOURS` | `ai_insight_ttl_hours` | Rule 5 |
| `AI_LLM_PROVIDER` | `ai_llm_provider` | Rule 8, provider validation |

If any threshold key is absent from `config_rule_set`:
* Substitute `UNKNOWN_V0` as the resolved value
* Log a `WARN`-level event with the missing key name and the config version ID being resolved
* Add `CONFIG_THRESHOLD_MISSING_{KEY}` to `reason_codes`
* Exclude all dependent rules that require the missing threshold
* Continue evaluation with remaining independent rules
* Set `degraded: true` in `degradation_metadata`

CONTINUE.

---

### RULE 4 — AI CONTEXT AVAILABILITY CHECK

**This rule determines whether a usable AI insight exists to evaluate.**

IF `ai_insight_id` is null AND `ai_insight_state` is not in `(AI_GENERATING, AI_PENDING, AI_QUEUED)`:
* No insight exists and none is in flight
* Assign tier: `UNAVAILABLE`
* Assign scope: `UNAVAILABLE`
* Set `reason_codes: ["AI_INSIGHT_ABSENT"]`
* Set `degradation_metadata.degraded = true`, `degradation_cause = PROVIDER_UNAVAILABLE`, `fallback_type = RULE_BASED_ONLY`

STOP with UNAVAILABLE tier if no insight is absent and none in flight.

IF `ai_insight_state IN (AI_GENERATING, AI_PENDING, AI_QUEUED)`:
* Assign tier: `IN_FLIGHT`
* Assign scope: `DEFERRED`
* Set `reason_codes: ["AI_IN_FLIGHT"]`
* Use prior AI version advisory content at ADVISORY scope if `prior_ai_versions` has at least one `AI_REVIEWED` entry
* Advisory signal from prior version is annotated `prior_version_advisory: true`

STOP with IN_FLIGHT tier.

CONTINUE to Rule 5 if an `AI_REVIEWED` insight exists.

---

### RULE 5 — GOVERNANCE TIER ASSIGNMENT

**This rule is non-terminal. Assigns the final tier for fresh insights.**

Compute `insight_age_hours = NOW() − ai_generated_at`.

IF `ai_insight_state ≠ AI_REVIEWED`:
* Assign tier: `UNAVAILABLE`
* `reason_codes: ["AI_NOT_REVIEWED"]`
STOP.

IF `insight_age_hours > AI_INSIGHT_TTL_HOURS` (resolved per Rule 3):
* Assign tier: `STALE`
* Assign scope: `LIMITED`
* Set `confidence_metadata.stale_flag = true`
* Set `confidence_metadata.stale_for_hours = insight_age_hours − AI_INSIGHT_TTL_HOURS`
* `reason_codes: ["AI_STALE"]`
CONTINUE to Rule 6 with STALE tier.

IF `ai_confidence_score ≥ 0.70`:
* Assign tier: `CONFIDENT`
* `confidence_metadata.confidence_tier = HIGH`
CONTINUE to Rule 6 with CONFIDENT tier.

IF `ai_confidence_score ≥ 0.40` AND `ai_confidence_score < 0.70`:
* Assign tier: `ADVISORY`
* `confidence_metadata.confidence_tier = MEDIUM`
CONTINUE to Rule 6 with ADVISORY tier.

IF `ai_confidence_score < 0.40`:
* Assign tier: `ADVISORY`
* `confidence_metadata.confidence_tier = LOW`
* `degradation_metadata.degradation_cause = CONFIDENCE_COLLAPSE`
CONTINUE to Rule 6 with ADVISORY tier (low confidence).

> Note: The 0.70 and 0.40 boundary values are current operational defaults. They are not sourced from the config catalog (no dedicated config key exists in V2; see UE-AI2). When a dedicated confidence ceiling config key is added to the V2 catalog, Rule 5 must be updated to resolve it via Rule 3 (AP-AI9 requirement).

---

### RULE 6 — ADVISORY SCOPE DETERMINATION

**This rule is non-terminal. Converts tier into permitted advisory scope.**

IF tier = `CONFIDENT`:
* scope = `FULL`
* `advisory_content` fully populated: sentiment, risk_summary, recommended_intervention, prioritization_signal, sentiment_trend, narrative_available, advisory_confidence
CONTINUE.

IF tier = `ADVISORY`:
* scope = `LIMITED`
* `advisory_content` partially populated: sentiment, risk_summary, narrative_available
* `advisory_content.recommended_intervention = null` (ADVISORY tier cannot independently drive intervention routing)
* `advisory_content.prioritization_signal = null` (ADVISORY tier informs but cannot set priority independently)
CONTINUE.

IF tier = `STALE`:
* scope = `LIMITED`
* Same partial population as ADVISORY scope
* All advisory content carries `stale: true` annotation in `confidence_metadata`
CONTINUE.

---

### RULE 7 — LIVE ESCALATION RESTRICTION

**This rule is non-terminal. Enforces the STALE/UNAVAILABLE escalation block.**

IF tier IN (`STALE`, `UNAVAILABLE`) AND `execution_mode = LIVE`:
* Set `advisory_content.recommended_intervention = null` — tier cannot drive LIVE escalation or intervention dispatch
* Add `reason_codes: ["AI_LIVE_ESCALATION_BLOCKED_STALE_TIER"]`
* This does NOT block orchestration — rule-based signals continue to drive escalation independently

IF tier = `CONFIDENT` or `ADVISORY` AND `ai_recommended_intervention = ESCALATE`:
* This is an escalation recommendation, not an escalation execution
* The escalation rules directive (Rules 5, 14) governs whether this AI signal may elevate severity
* AI cannot originate escalation candidacy without rule-based basis (AP-AI14; mirrors escalation AP-X14)

CONTINUE.

---

### RULE 8 — PROVIDER VALIDATION AND DEGRADATION

**This rule is non-terminal. Validates provider state and applies degradation handling.**

IF `circuit_breaker_state = OPEN`:
* Assign tier: `UNAVAILABLE`
* scope: `UNAVAILABLE`
* `degradation_metadata.degradation_cause = CIRCUIT_OPEN`
* `degradation_metadata.fallback_type = RULE_BASED_ONLY`
* `reason_codes: ["CIRCUIT_BREAKER_OPEN"]`
STOP with UNAVAILABLE tier.

IF `provider_degradation_state IN (UNAVAILABLE, RATE_LIMITED)` AND `inference_retry_count ≥ provider_retry_budget_remaining`:
* Retry budget exhausted
* Assign tier: `UNAVAILABLE`
* `degradation_metadata.degradation_cause = PROVIDER_UNAVAILABLE`
* `degradation_metadata.fallback_type = RULE_BASED_ONLY`
* `reason_codes: ["PROVIDER_RETRY_EXHAUSTED"]`
STOP with UNAVAILABLE tier.

IF `ai_model_used ≠ AI_LLM_PROVIDER` (resolved per Rule 3):
* Provider identity mismatch — the insight was generated by a different provider than currently configured
* This does NOT invalidate the insight; it means the fingerprint diverges from the current config
* Add `reason_codes: ["PROVIDER_IDENTITY_DIVERGENCE"]`
* Set `immutable_snapshot_eligibility.eligible_for_snapshot = false` (fingerprint divergence blocks snapshot eligibility)
* Tier is unchanged

CONTINUE.

---

### RULE 9 — ATTRIBUTION AND LINEAGE ASSEMBLY

**This rule is non-terminal. Assembles the full attribution and lineage metadata into the assessment output.**

Propagate all attribution fields from `§3.2 Attribution Context` unchanged into `attribution_metadata` in the output (AP-AI15). Attribution fields must not be modified, defaulted, or inferred by the AI assessment service.

Assemble `config_version_reference`:
* `config_version_id` from governance context
* `config_version_status` from governance context
* `ai_ttl_hours_applied` from resolved `AI_INSIGHT_TTL_HOURS` (Rule 3)
* `ai_provider_applied` from resolved `AI_LLM_PROVIDER` (Rule 3)
* `threshold_bindings` with all resolved thresholds

Assemble `model_version_metadata`:
* `provider` from `ai_model_used` on the insight record
* `model_identifier` from `ai_model_used`
* `prompt_version` from `ai_prompt_version`
* `ai_version_number` from `ai_insight_version`

CONTINUE.

---

### RULE 10 — SNAPSHOT ELIGIBILITY DETERMINATION

**This rule is non-terminal. Determines whether the AI advisory output is eligible for physical copy into a FINALIZED snapshot.**

Snapshot eligibility requires ALL of the following:

* `ai_governance_tier = CONFIDENT` (only CONFIDENT tier AI content is eligible for snapshot physical copy)
* `execution_type = original` (replay and regeneration cannot produce new snapshot AI content)
* `ai_finalized_copy = false` (content not already in a snapshot)
* `ai_insight_state = AI_REVIEWED`
* `insight_age_hours ≤ AI_INSIGHT_TTL_HOURS`
* No `PROVIDER_IDENTITY_DIVERGENCE` reason code (fingerprint must be clean)
* `compliance_hold_flag = false`

IF all conditions met:
* `immutable_snapshot_eligibility.eligible_for_snapshot = true`
* `immutable_snapshot_eligibility.eligibility_reason = "CONFIDENT_TIER_FRESH_ORIGINAL_EXECUTION"`

IF any condition is not met:
* `immutable_snapshot_eligibility.eligible_for_snapshot = false`
* `immutable_snapshot_eligibility.eligibility_reason` = first blocking condition name

CONTINUE.

---

### RULE 11 — OBSERVABILITY ASSEMBLY AND TERMINAL OUTPUT

**This rule is terminal. Assembles final observability metadata and produces the AIAssessment.**

Assemble `observability_metadata`:
* `correlation_id` from governance context
* `causation_id` from governance context
* `execution_type` from governance context
* `service = "ai_assessment"`
* `rule_path_taken` = accumulated rule identifiers from this evaluation pass
* `assessment_basis`: `FINALIZED_COPY` if Rule 1 fired; `HISTORICAL_REPLAY` if Rule 2 fired; `FALLBACK` if tier = UNAVAILABLE; `AI_ASSISTED` if tier in (CONFIDENT, ADVISORY); `RULE_BASED` if scope = UNAVAILABLE
* `inference_duration_ms` = wall-clock duration of inference call if one occurred; 0 if no inference call
* `outcome`: `success` if tier in (CONFIDENT, ADVISORY, STALE, FINALIZED_COPY); `deferred` if tier = IN_FLIGHT; `degraded` if fallback applied; `failure` if tier = UNAVAILABLE with error
* `error_class`: classified error type if outcome = failure; null otherwise

Produce final `AIAssessment` with all assembled fields.

STOP.

---

## 6. CONFIG VERSION GOVERNANCE

---

### 6.1 Config Resolution Protocol

All AI evaluation thresholds are resolved from the ACTIVE config version's `rule_set_snapshot` before any rule evaluation begins (Rule 3). For replay evaluations, thresholds resolve from the historical config version identified by `replay_context.historical_config_version_id` (spec/01 §12.4.1).

The resolution sequence:

1. Resolve `config_version_id` from governance context
2. Load `rule_set_snapshot` for that version
3. Extract `ai_insight_ttl_hours` and `ai_llm_provider` from the snapshot
4. For any missing key: substitute `UNKNOWN_V0`, log `CONFIG_THRESHOLD_MISSING_{KEY}`, add reason code, continue with remaining keys

---

### 6.2 AI TTL Governance

`ai_insight_ttl_hours` (Group H, class OPERATIONAL_TUNING, default 24H) governs the staleness boundary in Rule 5.

* The TTL is `OPERATIONAL_TUNING` — it does not require a replay impact assessment when changed (unlike `REPLAY_SENSITIVE_THRESHOLD` variables)
* A TTL change takes effect prospectively (FAD-3): existing AI insights evaluated after the new config activates will be assessed against the new TTL; prior evaluations retain their original TTL assessment
* Unplanned staleness exceeding 48 hours triggers a `SEVERITY: HIGH` governance alert (spec/01 §12.5.2; spec/06 §10.4)
* A snapshot finalized with stale AI content must carry `ai_content_stale: true` in the finalization record

---

### 6.3 Provider Governance

`ai_llm_provider` (Group H, class ARCHITECTURAL_CONSTANT, default `'anthropic'`) governs which AI provider is authoritative.

* Changing `ai_llm_provider` requires architecture board sign-off (class ARCHITECTURAL_CONSTANT per spec/01 §12.2)
* The provider value is stored in `rule_set_snapshot` and in the Snapshot Reproducibility Fingerprint (`ai_model_version` component)
* Provider changes do not retroactively modify `model_used` on existing `ai_insights` records or `snapshot_ai_narratives` rows (spec/01 §12.6.5)
* No silent provider substitution is permitted when the configured provider is unavailable (AP-AI8)

---

### 6.4 Confidence Ceiling Governance

No dedicated confidence ceiling config key exists in the V2 catalog at publication date (see UE-AI2). The 0.70 / 0.40 tier boundaries used in Rule 5 are current operational defaults.

* When a dedicated confidence config key is introduced to the V2 catalog, it must be classified `AI_ADVISORY_THRESHOLD` (class `AAT`) and require AI governance review before change
* Until the config key exists, the operational defaults in Rule 5 apply
* Changing the confidence ceiling threshold constitutes a `REPLAY_SENSITIVE_THRESHOLD` impact: re-classification of historical insights under a new confidence boundary must not occur retroactively (FAD-3)

---

### 6.5 Prospective-Only Activation

New config versions affect only AI evaluations that begin after the activation timestamp (`effective_from`). AI insights generated under a prior config version retain their original `ai_insight_ttl_hours` TTL assessment for historical lookup purposes. This implements FAD-3 (spec/01 §12.1.4).

---

## 7. REPLAY & REGENERATION SEMANTICS

---

### 7.1 Replay-Safe AI Behavior

Replay (`execution_type = replay`) must not produce new AI inference. All AI content for replay is sourced exclusively from:

1. The physically stored text in `warehouse.snapshot_ai_narratives` for the relevant historical context (FINALIZED_COPY source)
2. If no FINALIZED_COPY exists for the replay context: `ai_governance_tier = UNAVAILABLE` with reason code `REPLAY_AI_SOURCE_MISSING`

A replay that calls an AI provider for new inference content is a specification violation (AP-AI5; spec/01 §12.5.5). The violation must be detected at the Rule 2 gate and blocked.

Replay AI assessments carry:
* `replay_restrictions.is_replay = true`
* `replay_restrictions.live_inference_suppressed = true`
* `replay_restrictions.replay_ai_source = FINALIZED_COPY | NONE`
* Config thresholds from the historical version, not the ACTIVE version

---

### 7.2 Regeneration Restrictions

Report regeneration (`execution_type = regeneration`) follows the same AI sourcing rules as replay:

* AI narrative content in regenerated reports is sourced exclusively from `warehouse.snapshot_ai_narratives` physical copies
* Regeneration cannot overwrite historical AI content — the regenerated report uses the physically stored text and presents it unchanged
* If the current system's config version fingerprint differs from the fingerprint in the historical snapshot, the regenerated report is marked `POTENTIALLY_DIVERGENT` (spec/01 §12.4.4; spec/03 §22.3)
* The `POTENTIALLY_DIVERGENT` mark is logged with both fingerprint versions recorded; it does not prevent regeneration from completing

---

### 7.3 Immutable FINALIZED_COPY Semantics

FINALIZED snapshot AI content is immutable after the physical copy operation completes. The following operations must not modify frozen snapshot AI text (FAD-1; spec/01 §12.5.4):

* Force-refresh of the source `ai_insights` record
* AI provider change (`ai_llm_provider` config update)
* Compliance deletion of `ai_insights` records (compliance deletion scope is `ai_insights`; it must not reach `warehouse.snapshot_ai_narratives`)
* Model version upgrade

The `ai_prompt_version` and `ai_model_version` components of the Snapshot Reproducibility Fingerprint are captured at finalization and are immutable thereafter. These values in the fingerprint reflect the state at content lock time, not the current system state.

---

### 7.4 Historical AI Explainability

Every AI advisory produced under LIVE execution must remain historically explainable after the fact. This means:

* The `ai_version_number`, `model_identifier`, `prompt_version`, and `config_version_id` in the AIAssessment output must be preserved in the consuming service's audit log entry
* If a student's escalation, outreach decision, or intervention recommendation was influenced by an AI advisory, the audit record must carry the AI governance tier and confidence score that applied at decision time
* The lineage chain from AI insight → AIAssessment → orchestration intent → executed action must be reconstructable from the audit log alone, using the `correlation_id` and `causation_id` chain

---

## 8. PROVIDER GOVERNANCE

---

### 8.1 Provider Attribution Rules

Every AI advisory output carries `model_version_metadata.provider` and `model_version_metadata.model_identifier` from the source `ai_insights` record. This reflects the provider that was active at original insight generation time — not the currently configured provider.

Provider attribution is forward-only: changing `ai_llm_provider` does not retroactively modify attribution in prior `ai_insights` records, snapshot rows, or orchestration audit entries (spec/01 §12.6.5). The `model_used` field on `ai_insights` records is immutable after `AI_GENERATED` state.

---

### 8.2 Provider Degradation Handling

When the AI provider is degraded or unavailable (assessed via `provider_degradation_state` and `circuit_breaker_state`):

1. Rule 8 assigns `UNAVAILABLE` tier
2. `degradation_metadata.degraded = true` with explicit `degradation_cause`
3. `fallback_type = RULE_BASED_ONLY` (orchestration proceeds on rule-based signals)
4. No silent fallback to an alternative provider (AP-AI8)
5. The degradation event is logged at `WARN` level with the provider identity, failure type, and retry count

---

### 8.3 Provider Outage Semantics

When the AI provider is unreachable for an extended period:

* AI generation is deferred with exponential backoff; the backoff parameters derive from the provider failure governance (spec/01 §12.6.2)
* Snapshot finalization is not blocked by AI provider outage — FINALIZED snapshots may carry `ai_content_stale: true` when AI is unavailable at finalization time
* Provider unavailability does not corrupt platform state; all orchestration decisions continue deterministically on rule-based logic
* When AI generation eventually succeeds after an outage, the resulting `AI_REVIEWED` insight is evaluated against the ACTIVE config version TTL at evaluation time, not at the originally scheduled generation time

---

### 8.4 Provider Lineage Expectations

* `model_used` on every `ai_insights` record is the authoritative record of which provider and model generated that insight
* The `ai_llm_provider` config value at the time of generation is captured in `model_version_metadata.provider_config_key` in the assessment output
* If a provider change has occurred since a historical insight was generated, the assessment output carries both the historical `model_used` value and the current `ai_llm_provider` config value, annotated with `PROVIDER_IDENTITY_DIVERGENCE` reason code
* Provider identity must remain queryable historically: `SUPERSEDED` and `ARCHIVED` config versions retain their `ai_llm_provider` value in `rule_set_snapshot` permanently

---

### 8.5 Replay-Safe Provider Attribution

Provider attribution in historical records reflects the provider that was active at original execution time. Historical regeneration that resolves AI content from `warehouse.snapshot_ai_narratives` inherits the provider attribution from the stored snapshot row — it does not inherit the current `ai_llm_provider` config value. This ensures provider identity in historical reports is stable and accurate regardless of subsequent provider changes.

---

## 9. OBSERVABILITY & ATTRIBUTION

---

### 9.1 Required Telemetry Fields

Every AIAssessment emits a structured log event at `INFO` level on completion with the following fields:

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "ai_assessment",
  "event": "ai_assessment_completed | ai_assessment_blocked | ai_assessment_degraded",
  "correlation_id": "uuid",
  "causation_id": "uuid | null",
  "execution_type": "original | replay | regeneration",
  "ai_governance_tier": "CONFIDENT | ADVISORY | STALE | IN_FLIGHT | UNAVAILABLE | FINALIZED_COPY",
  "advisory_scope": "FULL | LIMITED | UNAVAILABLE | IMMUTABLE | DEFERRED",
  "assessment_basis": "RULE_BASED | AI_ASSISTED | FALLBACK | FINALIZED_COPY | HISTORICAL_REPLAY",
  "confidence_score": 0.0,
  "stale_flag": false,
  "stale_for_hours": 0,
  "degraded": false,
  "degradation_cause": null,
  "provider": "string | null",
  "model_identifier": "string | null",
  "inference_duration_ms": 0,
  "outcome": "success | failure | degraded | deferred",
  "error_class": null,
  "config_version_id": "string",
  "rule_path_taken": [],
  "reason_codes": []
}
```

PII fields (student name, contact details, transcript text) must NOT appear in any log line (AP-AI10). Log the `correlation_id` and `student_id` opaque identifier only.

---

### 9.2 Inference Lineage Traceability

Every AIAssessment output enables downstream services to reconstruct the full inference lineage:

* `correlation_id` links the assessment to the triggering scheduler run or operator action
* `causation_id` links the assessment to the upstream orchestration intent
* `model_version_metadata.ai_version_number` links to the specific `ai_insights` record
* `config_version_reference.config_version_id` links to the config version that governed TTL and provider evaluation
* `attribution_metadata.attribution_timestamp` provides the authoritative event time for audit purposes

The lineage chain: `scheduler run → orchestration intent → AI evaluation → AIAssessment → downstream service action` must be traversable in either direction using these identifiers from the audit log.

---

### 9.3 Attribution Continuity

Attribution fields from `§3.2 Attribution Context` propagate unchanged through the AIAssessment into every downstream service that consumes it (AP-AI15). The AI assessment service never overrides attribution metadata.

If a downstream service modifies attribution fields when consuming an AIAssessment, the modification constitutes an attribution boundary violation and must be detected by governance validation.

---

### 9.4 Replay Diagnostics

For replay assessments, the following additional observability fields are required:

| Field | Description |
|---|---|
| `replay_source_artifact_id` | ID of the historical snapshot from which FINALIZED_COPY AI content was sourced |
| `historical_config_version_id` | Config version used for replay threshold resolution |
| `fingerprint_comparison_outcome` | `MATCH`, `DIVERGENT`, `UNKNOWN`, or `null` |
| `replay_partial` | True if `CONFIG_THRESHOLD_MISSING` conditions were encountered during replay |

---

### 9.5 Provider Diagnostics

On every inference call (including retries and failures):

| Metric | Required behavior |
|---|---|
| `inference_request_start` | Logged at call initiation |
| `inference_request_end` | Logged at call completion or timeout |
| `inference_duration_ms` | Computed from start-to-end wall clock |
| `provider_status_code` | HTTP status code or provider-specific error class |
| `provider_error_body` | Full error body on failure (with secrets redacted per AP-AI10) |
| `retry_attempt_number` | Which retry this is (0 = initial attempt) |

---

### 9.6 Confidence Observability

The following confidence-related fields appear in every AIAssessment output regardless of tier:

| Field | Required value |
|---|---|
| `confidence_metadata.confidence_score` | Raw model-reported confidence from `ai_insights.confidence_score` |
| `confidence_metadata.confidence_tier` | Classified tier: HIGH (≥0.70), MEDIUM (0.40–0.69), LOW (<0.40), UNSCORED (null) |
| `confidence_metadata.stale_flag` | True if insight age exceeds TTL |
| `confidence_metadata.stale_for_hours` | Hours beyond TTL (0 if not stale) |
| `confidence_metadata.insight_age_hours` | Current age of the insight in hours |
| `confidence_metadata.ttl_hours_applied` | TTL value used in this evaluation (from Rule 3) |

---

## 10. DETERMINISTIC DEGRADATION RULES

---

Every degradation scenario produces an explicit, observable, documented fallback state. Silent AI degradation is prohibited (AP-AI8).

| Condition | Tier | Scope | Fallback Type | Orchestration Behavior | Required Observability |
|---|---|---|---|---|---|
| Provider circuit breaker OPEN | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Proceeds on deterministic rule signals | `WARN` log; `CIRCUIT_BREAKER_OPEN` reason code |
| Provider UNAVAILABLE + retry budget exhausted | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Proceeds on deterministic rule signals | `WARN` log; `PROVIDER_RETRY_EXHAUSTED` reason code |
| Inference timeout (single attempt) | Retry once per retry policy | — | — | Block on first timeout; retry | `WARN` log; `inference_last_failure_type = TIMEOUT` |
| Inference timeout (retry also times out) | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Proceeds on deterministic rule signals | `WARN` log; `INFERENCE_TIMEOUT_EXHAUSTED` reason code |
| AI insight STALE (beyond TTL) | `STALE` | `LIMITED` | None (stale insight served annotated) | Advisory scope limited; LIVE escalation blocked | `stale_flag = true`; `stale_for_hours` populated |
| AI insight MISSING (null) | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Proceeds on deterministic rule signals | `reason_codes: ["AI_INSIGHT_ABSENT"]` |
| Confidence collapse (score < 0.40) | `ADVISORY` | `LIMITED` | None (ADVISORY scope applies) | Priority scoring only; no independent intervention routing | `confidence_tier = LOW`; `degradation_cause = CONFIDENCE_COLLAPSE` |
| AI generation IN_FLIGHT (pending) | `IN_FLIGHT` | `DEFERRED` | Prior version at ADVISORY scope | `DEFER_PENDING_AI` intent if no prior version; else prior version advisory | `reason_codes: ["AI_IN_FLIGHT"]` |
| Replay with no FINALIZED_COPY | `UNAVAILABLE` | `UNAVAILABLE` | `RULE_BASED_ONLY` | Replay proceeds without AI advisory | `reason_codes: ["REPLAY_AI_SOURCE_MISSING"]` |
| Provider identity divergence | Tier unchanged | Scope unchanged | No snapshot eligibility | Continues; snapshot blocked | `reason_codes: ["PROVIDER_IDENTITY_DIVERGENCE"]`; `eligible_for_snapshot = false` |
| Config threshold missing | Degraded tier resolution | As resolved | `RULE_BASED_ONLY` for missing-dependent rules | Continues excluding dependent rules | `CONFIG_THRESHOLD_MISSING_{KEY}` reason code; `degraded = true` |

Orchestration continues safely in all degradation scenarios. There is no condition where AI unavailability halts the orchestration cycle.

---

## 11. FAILURE & SAFETY SEMANTICS

---

### 11.1 Missing Data Handling

| Missing Input | Effect | Recovery |
|---|---|---|
| `config_version_id` null | Rule 0 blocks; `ai_blocked = true` | Config resolution must succeed before AI evaluation |
| `correlation_id` null | Rule 0 blocks; `ai_blocked = true` | Correlation ID generation failure must be fixed upstream |
| `attribution_context` incomplete | Rule 0 blocks; `ai_blocked = true` | Attribution context is assembled by the calling service |
| `ai_insight_id` null, no in-flight | Rule 4: UNAVAILABLE tier, RULE_BASED_ONLY | Orchestration continues without AI |
| `ai_finalized_copy` null (expected true) | Treated as false; Rule 1 does not fire | Physical copy record must be present in snapshot table |

---

### 11.2 Stale SQL Server Data

If `sql_server_sync_timestamp` is older than `sql_server_max_sync_age_hours` (Group I, class ARCHITECTURAL_CONSTANT, default 4H):

* AI advisory content that references SQL Server-authoritative fields (hws_behind, avg_eff_rating, etc.) carries a `STALE_SQL_DATA` annotation in `reason_codes`
* The advisory is still served but annotated as potentially based on stale academic signals
* Snapshot eligibility is blocked when SQL Server data is stale (`eligible_for_snapshot = false`)

---

### 11.3 Duplicate Detection

If `idempotency_key` already exists in the dedup store for `(student_id, checkpoint_type, cycle_timestamp)`:

* Rule 0 blocks with `IDEMPOTENCY_DUPLICATE` reason code
* The prior assessment for this key is NOT re-served — the consumer must look up the stored result
* The duplicate detection event is logged at `WARN` level

---

### 11.4 Replay Conflict Handling

| Replay Conflict | Behavior |
|---|---|
| Historical config version not found | `UNAVAILABLE` tier; `reason_codes: ["REPLAY_CONFIG_VERSION_MISSING"]`; replay continues without AI |
| FINALIZED_COPY hash mismatch (stored ≠ expected) | `POTENTIALLY_DIVERGENT` annotation; assessment still serves from stored copy; `reason_codes: ["FINALIZED_COPY_HASH_DIVERGENCE"]` |
| Replay with LIVE execution_mode | Rule 0 blocks — replay in LIVE mode is a governance violation; `reason_codes: ["REPLAY_LIVE_MODE_VIOLATION"]` |

---

### 11.5 Attribution Gap Handling

If `attribution_context` is present but any individual field is null:

* The null field is preserved as-is in the output (AP-AI15: attribution fields must not be inferred or defaulted)
* Add `reason_codes: ["ATTRIBUTION_PARTIAL"]`
* The assessment is not blocked for partial attribution unless Rule 0's "attribution_context incomplete" condition triggers

---

## 12. ARCHITECTURE PRESERVATION RULES

---

These rules define what the AI orchestration contract MUST NOT do. Any implementation that violates these rules is non-compliant with this directive regardless of other factors.

| Rule | Prohibition | Specification basis |
|---|---|---|
| **AP-AI1** | MUST NOT act as a workflow authority, governance decision-maker, or orchestration executor. AI assessment is advisory-only. | §1.2, §1.3 |
| **AP-AI2** | MUST NOT autonomously trigger student lifecycle state mutations. State transitions are the state management service's responsibility. | §1.3, spec/03 |
| **AP-AI3** | MUST NOT autonomously dispatch outreach, escalations, notifications, or any other side effect. All side effects are executed by consuming services. | §1.3 |
| **AP-AI4** | MUST NOT override, bypass, or contradict deterministic rule evaluation outcomes, config-bound threshold decisions, or governance invariants (INVARIANT-1–INVARIANT-7). | §1.3, spec/03 §40 |
| **AP-AI5** | MUST NOT call a live AI provider during replay or regeneration execution. AI content for replay is sourced exclusively from `warehouse.snapshot_ai_narratives`. | §7.1, spec/01 §12.5.5 |
| **AP-AI6** | MUST NOT modify, overwrite, or corrupt AI text that has been physically copied into a FINALIZED snapshot record. FINALIZED_COPY AI content is immutable. | §7.3, FAD-1, spec/01 §12.5.4 |
| **AP-AI7** | MUST NOT overwrite prior AI assessment outputs. All AI assessment records are append-only. A new assessment is always a new record; historical assessments are never modified. | §9.2 |
| **AP-AI8** | MUST NOT silently substitute a different AI provider when the configured provider is unavailable. Degradation must be explicit, observable, and logged. | §8.2, §10 |
| **AP-AI9** | MUST NOT use hardcoded AI TTL, confidence ceiling, or provider selection values in rule evaluation. All threshold values must resolve from the ACTIVE config version's `rule_set_snapshot` via Rule 3. | §6.1, §6.4 |
| **AP-AI10** | MUST NOT log raw PII — student names, contact information, transcript text, or personally identifiable content — in any inference log, debug output, or error message. Log `correlation_id` and opaque `student_id` only. | §9.1, spec/09 |
| **AP-AI11** | MUST NOT allow STALE or UNAVAILABLE tier AI to drive LIVE escalation advisory or intervention routing independently. Rule-based signals must exist before AI severity adjustment applies. | §2.1, Rule 7 |
| **AP-AI12** | MUST NOT generate new AI inference content for a context where `ai_finalized_copy = true`. Rule 1 fires immediately; no re-evaluation occurs. | §7.3, FAD-1 |
| **AP-AI13** | MUST NOT evaluate AI governance tier, advisory scope, or AI content without Rule 0 passing first. Rule 0 is the mandatory governance gate for all AI evaluation. | Rule 0 |
| **AP-AI14** | MUST NOT allow AI confidence score alone to override rule-based eligibility, escalation candidacy, or orchestration intent classification. AI advisory scope is bounded; AI cannot originate candidacy without rule-based basis. | §1.3, Rule 7, spec/01 §12.5.1 |
| **AP-AI15** | MUST NOT override, default, infer, or modify attribution fields sourced from the input attribution context. Attribution must propagate unchanged through every output produced. | §9.3 |

---

## 13. SCOPE BEHAVIOR

---

### 13.1 MVP Scope

In MVP scope, AI usage is optional and may be disabled entirely.

| Behavior | MVP |
|---|---|
| AI evaluation | Optional; may be bypassed |
| Governance tier assignment | UNAVAILABLE if bypassed; full evaluation if enabled |
| Advisory scope | LIMITED or UNAVAILABLE |
| Snapshot eligibility | Disabled — no FINALIZED snapshots in MVP |
| Replay semantics | Not applicable — no historical snapshots in MVP |
| Config-bound threshold resolution | Required if AI is enabled; bypassed if AI disabled |
| Observability | Basic: `INFO` log on assessment completion |
| Degradation behavior | RULE_BASED_ONLY if AI disabled or unavailable |

---

### 13.2 STANDARD Scope

In STANDARD scope, AI evaluation is active with partial governance enforcement.

| Behavior | STANDARD |
|---|---|
| AI evaluation | Active; full tier assignment |
| Governance tier assignment | Full 6-tier evaluation |
| Advisory scope | FULL permitted for CONFIDENT tier |
| Snapshot eligibility | Active; CONFIDENT tier required |
| Replay semantics | Active; FINALIZED_COPY sourcing enforced |
| Config-bound threshold resolution | Required; all Group H variables must be resolved |
| Observability | Full structured log per §9.1 |
| Degradation behavior | All fallback paths active |

---

### 13.3 PRODUCTION Scope

In PRODUCTION scope, all governance enforcement is fully active.

| Behavior | PRODUCTION |
|---|---|
| AI evaluation | Full; AP-AI1–AP-AI15 all enforced |
| Governance tier assignment | Full 6-tier evaluation with config-bound boundaries |
| Advisory scope | FULL for CONFIDENT; LIMITED for ADVISORY/STALE; UNAVAILABLE for UNAVAILABLE |
| Snapshot eligibility | Active; fingerprint validation required |
| Replay semantics | Full enforcement; AP-AI5 violation detection active |
| Config-bound threshold resolution | Required; UNKNOWN_V0 degraded evaluation for missing keys |
| Observability | Full structured log + metrics (inference latency p50/p95/p99, success rate, tier distribution, degradation events) |
| Degradation behavior | All fallback paths active; escalation routing service notified on repeated UNAVAILABLE events |
| LIVE escalation restrictions | AP-AI11 fully enforced; STALE and UNAVAILABLE blocked from LIVE escalation contribution |

---

## 14. ACCEPTANCE CRITERIA

---

| ID | Criterion | Given | When | Then |
|---|---|---|---|---|
| AC-AI1 | CONFIDENT tier for fresh, high-confidence insight | `ai_insight_state = AI_REVIEWED`, `insight_age_hours ≤ TTL`, `confidence_score ≥ 0.70`, `execution_type = original` | AI assessment evaluated | Tier = CONFIDENT, scope = FULL, all advisory_content fields populated |
| AC-AI2 | STALE tier for expired insight | `ai_insight_state = AI_REVIEWED`, `insight_age_hours > TTL`, valid governance context | AI assessment evaluated | Tier = STALE, scope = LIMITED, `stale_flag = true`, `stale_for_hours` populated, `recommended_intervention = null` |
| AC-AI3 | UNAVAILABLE tier when insight absent | `ai_insight_id = null`, `ai_insight_state` not in-flight | AI assessment evaluated | Tier = UNAVAILABLE, scope = UNAVAILABLE, `degradation_metadata.fallback_type = RULE_BASED_ONLY`, orchestration continues |
| AC-AI4 | Replay suppresses live inference | `execution_type = replay` | AI assessment evaluated | `live_inference_suppressed = true`, `replay_ai_source = FINALIZED_COPY` or `NONE`, no provider call made |
| AC-AI5 | FINALIZED_COPY served immutably | `ai_finalized_copy = true` | AI assessment evaluated | Rule 1 fires immediately, tier = FINALIZED_COPY, scope = IMMUTABLE, no re-inference, no tier re-evaluation |
| AC-AI6 | Config version fingerprint mismatch annotated | Regeneration with diverged fingerprint | Report regeneration | `POTENTIALLY_DIVERGENT` annotation in output, historical config version retained, regeneration completes |
| AC-AI7 | Provider outage triggers UNAVAILABLE | `circuit_breaker_state = OPEN` or retry budget exhausted | AI assessment evaluated | Tier = UNAVAILABLE, `degradation_cause = CIRCUIT_OPEN | PROVIDER_RETRY_EXHAUSTED`, no silent fallback provider |
| AC-AI8 | Null config blocks evaluation | `config_version_id = null` | AI assessment evaluated | Rule 0 blocks, `ai_blocked = true`, `blocking_reason = GOVERNANCE_PRECONDITION_FAILED` |
| AC-AI9 | STALE AI blocked from LIVE escalation | Tier = STALE, `execution_mode = LIVE` | AI assessment drives escalation evaluation | `recommended_intervention = null`, `AI_LIVE_ESCALATION_BLOCKED_STALE_TIER` reason code, escalation_rules.md Rule 7 receives no AI escalation signal |
| AC-AI10 | AI advisory does not override deterministic rule outcome | AI sentiment = negative, but rule-based eligibility = NOT_ELIGIBLE | Eligibility assessment | Eligibility outcome = NOT_ELIGIBLE; AI advisory is recorded but does not change the eligibility decision |
| AC-AI11 | Attribution propagates unchanged | Attribution context with `origin_source = operator` | AI assessment produced | Output `attribution_metadata.origin_source = operator` unchanged; no defaulting or inference applied |
| AC-AI12 | Confidence collapse downgrades scope | `confidence_score = 0.30`, fresh insight | AI assessment evaluated | Tier = ADVISORY, `confidence_tier = LOW`, scope = LIMITED, `degradation_cause = CONFIDENCE_COLLAPSE`, advisory content partially populated |

---

## 15. UNRESOLVED CONCERNS

---

The following concerns are open at publication date. They require governance or operational decisions before the platform reaches full PRODUCTION scope for AI-assisted orchestration.

| ID | Concern | Classification | Blocking |
|---|---|---|---|
| **UE-AI1** | **Provider trust ceilings** — which AI providers are authorized at which governance tiers, and is there a governance approval chain for provider selection beyond `ARCHITECTURAL_CONSTANT` review? The current architecture allows any provider listed in `ai_llm_provider` but does not specify a formal trust taxonomy for multi-provider scenarios. | Governance decision | Blocks multi-provider AI configurations in PRODUCTION |
| **UE-AI2** | **Confidence calibration strategy** — the 0.70 (CONFIDENT) and 0.40 (ADVISORY) tier boundaries in Rule 5 are operational defaults, not config-governed values. No dedicated config catalog key exists. How are these boundaries calibrated, validated, and changed? What is the governance approval process for boundary adjustments? | AI governance decision | Blocks formal confidence governance; currently operational defaults |
| **UE-AI3** | **AI hallucination containment** — what guardrails exist for factually incorrect AI outputs? The current architecture marks AI as advisory-only (§1.3) and blocks AI from overriding deterministic rules, but there is no output validation layer that detects hallucinated student data, incorrect threshold citations, or factually inconsistent risk summaries before they are surfaced in operator dashboards. | Implementation dependency | Blocks PRODUCTION advisory_content serving without quality audit |
| **UE-AI4** | **Prompt governance** — `ai_prompt_version` is a Snapshot Reproducibility Fingerprint component and is captured at finalization. However, the review, approval, staging, and versioning process for prompt template changes is not defined. A prompt change can materially alter AI advisory content and risk classification across all students without a config version change. | AI governance decision | Blocks formal prompt change management in PRODUCTION |
| **UE-AI5** | **Model upgrade governance** — changing `ai_llm_provider` requires architecture sign-off (`ARCHITECTURAL_CONSTANT`). However, upgrading the model version within the same provider (e.g., `claude-sonnet-4-5` → `claude-sonnet-4-6`) is not governed by a config catalog variable. There is no defined process for testing model upgrades against historical advisory outputs before production activation, nor a defined rollback path if a model upgrade produces unexpected advisory drift. | AI governance decision | Blocks formally managed model versioning in PRODUCTION |

---

## 16. DOWNSTREAM IMPLICATIONS

---

### 16.1 Core Decision Engine Impact

The Core Decision Engine (`directives/core_decision_engine.md`) consumes `AIAssessment` outputs to:

* Inform its `DEFER_PENDING_AI` intent (when tier = IN_FLIGHT, the engine may defer its decision)
* Adjust orchestration priority in `RECOMMEND_INTERVENTION` intents (FULL scope only)
* Populate `ai_context` fields in the `OrchestrationIntent` output schema

The decision engine must not infer advisory scope from tier alone — it must read `advisory_scope` from the AIAssessment explicitly. An `advisory_scope = FULL` from a CONFIDENT tier insight permits full priority adjustment; `advisory_scope = LIMITED` from a STALE insight permits only display-layer use.

---

### 16.2 Escalation Rules Impact

The escalation rules directive (`directives/escalation_rules.md`) consumes AI governance tier and confidence from the AIAssessment to evaluate Rules 5 and 14 (AI-assisted severity adjustment). The following constraints apply:

* STALE or UNAVAILABLE tier AI must not contribute to LIVE escalation severity (AP-AI11; mirrors escalation AP-X14)
* AI cannot originate escalation candidacy where rule-based signals find none — the AIAssessment `recommended_intervention = ESCALATE` is advisory context for Rule 14, not a standalone escalation trigger
* The escalation assessment output's `ai_context.ai_governance_tier` is sourced from the AIAssessment's `ai_governance_tier` field

---

### 16.3 Snapshot Orchestration Impact

The snapshot orchestration service reads `immutable_snapshot_eligibility.eligible_for_snapshot` to determine whether AI content may be physically copied. Only CONFIDENT tier, fresh, original-execution assessments with clean provider identity are eligible. The orchestration service is responsible for the physical copy write; this directive specifies the eligibility determination only.

---

### 16.4 Report Orchestration Impact

Historical report regeneration (`execution_type = regeneration`) resolves all AI content from `warehouse.snapshot_ai_narratives`. The `replay_restrictions.replay_ai_source` field on the AIAssessment confirms whether FINALIZED_COPY content was successfully sourced. If `replay_ai_source = NONE`, the report is generated without AI content and is annotated accordingly.

---

## 17. REFERENCES

---

### Canonical Specification Inputs

* `spec/01_requirements.md` — Section 12 Config Governance Catalog (Group H AI/Provider variables; §12.5 AI Governance Requirements; §12.6 Provider Failure Governance)
* `spec/03_state_transition_rules.md` — AI insight lifecycle states (§27.x); snapshot finalization lifecycle (§22.x); `POTENTIALLY_DIVERGENT` semantics (§22.3); INVARIANT-1 through INVARIANT-7 (§40)
* `spec/04_idempotency_concurrency.md` — AI evaluation idempotency semantics; config version atomic swap (§18.x)
* `spec/05_external_integrations.md` — AI provider integration contract; GHL outreach provider contract
* `spec/06_observability_operations.md` — AI staleness alert thresholds (§10.4); governance alert severity model (§10.9)
* `spec/07_api_contracts.md` — AI insight API response shape; stale annotation contract
* `spec/08_data_model.md` — `ai_insights` table schema; `warehouse.snapshot_ai_narratives` schema; `config_version_registry` schema
* `spec/09_security_privacy.md` — PII handling in AI inputs and outputs; AI inference log redaction requirements

### Directive Dependencies

* `directives/core_decision_engine.md` — Consumes AIAssessment in §2.3 AI Inputs; produces `DEFER_PENDING_AI` intent based on IN_FLIGHT tier
* `directives/outreach_eligibility_rules.md` — Consumes AIAssessment for AI-assisted prioritization eligibility (Rule 11)
* `directives/outreach_retry_policy.md` — Consumes AIAssessment for AI-assisted retry priority adjustment (Rule 13)
* `directives/escalation_rules.md` — Consumes AIAssessment `ai_governance_tier` and `confidence_score` for escalation severity Rules 5 and 14

### Foundational Architectural Decisions

* **FAD-1 (Physical Copy AI Semantics)** — AI text physically copied into FINALIZED snapshots is immutable; post-finalization operations must not affect frozen snapshot AI text. Enforced by AP-AI6 and AP-AI12.
* **FAD-3 (Prospective-Only Config Activation)** — New config versions affect only evaluations that begin after activation. Historical evaluations retain original config version context. Enforced by §6.5 and replay semantics in §7.

---

## END OF FILE
