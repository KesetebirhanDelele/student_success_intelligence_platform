"""
Contract types for the governance-safe AI orchestration layer.
Not part of the public API. Consumed by ai_insights.py and _ai_helpers.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Execution modes ───────────────────────────────────────────────────────────
MODE_SHADOW = "SHADOW"
MODE_LIVE   = "LIVE"

# ── Execution types ───────────────────────────────────────────────────────────
TYPE_ORIGINAL     = "original"
TYPE_REPLAY       = "replay"
TYPE_REGENERATION = "regeneration"

_VALID_EXECUTION_MODES = frozenset({MODE_SHADOW, MODE_LIVE})
_VALID_EXECUTION_TYPES = frozenset({TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION})
_REPLAY_TYPES          = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

# ── AI governance tiers (llm_processing_contract.md §2) ──────────────────────
TIER_CONFIDENT      = "CONFIDENT"
TIER_ADVISORY       = "ADVISORY"
TIER_STALE          = "STALE"
TIER_IN_FLIGHT      = "IN_FLIGHT"
TIER_UNAVAILABLE    = "UNAVAILABLE"
TIER_FINALIZED_COPY = "FINALIZED_COPY"

# ── Advisory scopes (llm_processing_contract.md §4.2) ────────────────────────
SCOPE_FULL        = "FULL"
SCOPE_LIMITED     = "LIMITED"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_IMMUTABLE   = "IMMUTABLE"
SCOPE_DEFERRED    = "DEFERRED"

# ── AI insight states ─────────────────────────────────────────────────────────
STATE_AI_PENDING           = "AI_PENDING"
STATE_AI_GENERATING        = "AI_GENERATING"
STATE_AI_QUEUED            = "AI_QUEUED"
STATE_AI_GENERATED         = "AI_GENERATED"
STATE_AI_REVIEWED          = "AI_REVIEWED"
STATE_AI_GENERATION_FAILED = "AI_GENERATION_FAILED"
STATE_AI_ARCHIVED          = "AI_ARCHIVED"

_IN_FLIGHT_STATES        = frozenset({STATE_AI_PENDING, STATE_AI_GENERATING, STATE_AI_QUEUED})
_TERMINAL_FAILURE_STATES = frozenset({STATE_AI_GENERATION_FAILED, STATE_AI_ARCHIVED})

# ── Config V2 Group H AI threshold keys (llm_processing_contract.md §6.1) ────
K_AI_INSIGHT_TTL_HOURS = "ai_insight_ttl_hours"
K_AI_LLM_PROVIDER      = "ai_llm_provider"

_AI_THRESHOLD_KEYS = (K_AI_INSIGHT_TTL_HOURS, K_AI_LLM_PROVIDER)

UNKNOWN_V0 = "UNKNOWN_V0"

# ── Confidence tier boundaries (operational defaults — no config key yet; UE-AI2) ─
CONFIDENCE_HIGH_FLOOR   = 0.70
CONFIDENCE_MEDIUM_FLOOR = 0.40

CONFIDENCE_TIER_HIGH     = "HIGH"
CONFIDENCE_TIER_MEDIUM   = "MEDIUM"
CONFIDENCE_TIER_LOW      = "LOW"
CONFIDENCE_TIER_UNSCORED = "UNSCORED"

# ── Circuit breaker states ────────────────────────────────────────────────────
CB_OPEN      = "OPEN"
CB_CLOSED    = "CLOSED"
CB_HALF_OPEN = "HALF_OPEN"
CB_UNKNOWN   = "UNKNOWN"

# ── Assessment outcome values ─────────────────────────────────────────────────
OUTCOME_SUCCESS  = "success"
OUTCOME_FAILURE  = "failure"
OUTCOME_DEGRADED = "degraded"
OUTCOME_DEFERRED = "deferred"

# ── Assessment basis values ───────────────────────────────────────────────────
BASIS_RULE_BASED        = "RULE_BASED"
BASIS_AI_ASSISTED       = "AI_ASSISTED"
BASIS_FALLBACK          = "FALLBACK"
BASIS_FINALIZED_COPY    = "FINALIZED_COPY"
BASIS_HISTORICAL_REPLAY = "HISTORICAL_REPLAY"

# ── Replay AI source values ───────────────────────────────────────────────────
REPLAY_SOURCE_FINALIZED_COPY = "FINALIZED_COPY"
REPLAY_SOURCE_NONE           = "NONE"

# ── Required attribution fields (subset that blocks Rule 0 if absent) ─────────
REQUIRED_AI_ATTRIBUTION = ("origin_source", "origin_authority", "actor_identity")


# ── Input context ─────────────────────────────────────────────────────────────

@dataclass
class AIOrchestrationContext:
    """Governance context for an AI orchestration evaluation."""

    # Governance §3.1 — mandatory
    config_version_id: Optional[str]
    execution_mode: str    # SHADOW | LIVE
    execution_type: str    # original | replay | regeneration
    correlation_id: Optional[str]

    config_rule_set: Optional[Dict[str, Any]] = None
    causation_id: Optional[str] = None
    upstream_intent_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    compliance_hold_flag: bool = False

    # Attribution §3.2 — set by platform; never accepted from external callers (AP-AI15)
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    actor_identity: Optional[str] = None
    attribution_timestamp: Optional[str] = None
    upstream_correlation_id: Optional[str] = None

    # AI context §3.4
    ai_insight_id: Optional[str] = None
    ai_insight_state: Optional[str] = None
    ai_insight_version: Optional[int] = None
    ai_generated_at: Optional[str] = None   # ISO-8601
    ai_confidence_score: Optional[float] = None
    ai_prompt_version: Optional[str] = None
    ai_model_used: Optional[str] = None
    ai_stale_flag: bool = False
    ai_finalized_copy: bool = False
    ai_input_metrics_hash: Optional[str] = None
    ai_risk_summary: Optional[str] = None
    ai_recommended_intervention: Optional[str] = None
    ai_sentiment: Optional[str] = None

    # Operational context §3.5
    provider_degradation_state: str = "OPERATIONAL"
    inference_retry_count: int = 0
    inference_last_failure_type: Optional[str] = None
    circuit_breaker_state: str = CB_UNKNOWN
    provider_retry_budget_remaining: int = 0

    # Replay context
    historical_config_version_id: Optional[str] = None
    source_artifact_id: Optional[str] = None

    # Student — opaque ID only; PII never logged (AP-AI10)
    student_id_opaque: Optional[str] = None


# ── Output assessment ─────────────────────────────────────────────────────────

@dataclass
class AIAssessment:
    """
    Governance assessment for an AI orchestration evaluation.
    Advisory contract — not an execution result. Consuming services act on this.
    """

    # Core governance
    ai_governance_tier: str
    advisory_scope: str

    # Replay restrictions
    is_replay: bool
    live_inference_suppressed: bool
    replay_ai_source: Optional[str]
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]

    # Attribution — propagated immutably from input (AP-AI15)
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    upstream_intent_id: Optional[str]
    upstream_correlation_id: Optional[str]

    # Config lineage
    config_version_id: Optional[str]
    threshold_bindings: Dict[str, Any]

    # Observability
    event_id: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    execution_type: str
    execution_mode: str
    rule_path_taken: List[str]
    assessment_basis: str
    inference_duration_ms: int
    duration_ms: int
    outcome: str
    error_class: Optional[str]

    # Confidence metadata
    confidence_score: Optional[float]
    confidence_tier: str
    stale_flag: bool
    stale_for_hours: float
    insight_age_hours: float
    ttl_hours_applied: Any   # float | UNKNOWN_V0

    # Degradation
    degraded: bool
    degradation_cause: Optional[str]
    fallback_applied: bool
    fallback_type: Optional[str]
    orchestration_continues: bool

    # Advisory content (AP-AI1 — advisory only; never execution authority)
    advisory_sentiment: Optional[str]
    advisory_risk_summary: Optional[str]
    advisory_recommended_intervention: Optional[str]
    advisory_prioritization_signal: Optional[str]

    # Snapshot eligibility
    eligible_for_snapshot: bool
    eligibility_reason: Optional[str]
    finalized_copy: bool

    # Model lineage
    provider: Optional[str]
    model_identifier: Optional[str]
    prompt_version: Optional[str]
    ai_version_number: Optional[int]

    # Result
    reason_codes: List[str]
    ai_blocked: bool
    blocking_reason: Optional[str]
