"""
Contract types for the governance-safe orchestration prioritization advisory service.
Not part of the public API. Consumed by priority.py and _priority_helpers.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ── Execution modes ────────────────────────────────────────────────────────────
MODE_SHADOW = "SHADOW"
MODE_LIVE   = "LIVE"

# ── Execution types ────────────────────────────────────────────────────────────
TYPE_ORIGINAL     = "original"
TYPE_REPLAY       = "replay"
TYPE_REGENERATION = "regeneration"
TYPE_RECOVERY     = "recovery"

_VALID_EXECUTION_MODES = frozenset({MODE_SHADOW, MODE_LIVE})
_VALID_EXECUTION_TYPES = frozenset({TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION, TYPE_RECOVERY})
_REPLAY_TYPES          = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

# ── Governance scopes ──────────────────────────────────────────────────────────
SCOPE_AUTHORIZED  = "AUTHORIZED"   # Phase-12 certification gate — currently unreachable
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_MAINTENANCE = "MAINTENANCE"

# ── Advisory priority tiers ────────────────────────────────────────────────────
PRIORITY_CRITICAL = "CRITICAL"
PRIORITY_HIGH     = "HIGH"
PRIORITY_MEDIUM   = "MEDIUM"
PRIORITY_LOW      = "LOW"
PRIORITY_UNKNOWN  = "UNKNOWN"

_PRIORITY_LEVELS = (PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

# ── Risk contribution levels ───────────────────────────────────────────────────
RISK_HIGH   = "HIGH"
RISK_MEDIUM = "MEDIUM"
RISK_LOW    = "LOW"

# ── AI governance tiers ────────────────────────────────────────────────────────
TIER_CONFIDENT      = "CONFIDENT"
TIER_ADVISORY       = "ADVISORY"
TIER_STALE          = "STALE"
TIER_IN_FLIGHT      = "IN_FLIGHT"
TIER_UNAVAILABLE    = "UNAVAILABLE"
TIER_FINALIZED_COPY = "FINALIZED_COPY"

# ── AI insight states ──────────────────────────────────────────────────────────
AI_REVIEWED          = "AI_REVIEWED"
AI_GENERATING        = "AI_GENERATING"
AI_PENDING           = "AI_PENDING"
AI_GENERATION_FAILED = "AI_GENERATION_FAILED"
AI_ARCHIVED          = "AI_ARCHIVED"

_AI_IN_FLIGHT_STATES   = frozenset({AI_GENERATING, AI_PENDING})
_AI_UNAVAILABLE_STATES = frozenset({AI_GENERATION_FAILED, AI_ARCHIVED})

# ── AI recommendation values ───────────────────────────────────────────────────
AI_RECOMMEND_NONE              = "NONE"
AI_RECOMMEND_OUTREACH          = "OUTREACH"
AI_RECOMMEND_MEETING           = "MEETING"
AI_RECOMMEND_RESOURCE_DELIVERY = "RESOURCE_DELIVERY"
AI_RECOMMEND_ESCALATE          = "ESCALATE"

_AI_UPWARD_RECOMMENDATIONS = frozenset({
    AI_RECOMMEND_MEETING,
    AI_RECOMMEND_OUTREACH,
    AI_RECOMMEND_RESOURCE_DELIVERY,
})

# ── Historical risk trends ─────────────────────────────────────────────────────
TREND_IMPROVING = "IMPROVING"
TREND_STABLE    = "STABLE"
TREND_DECLINING = "DECLINING"
TREND_CRITICAL  = "CRITICAL"
TREND_UNKNOWN   = "UNKNOWN"

# ── Assessment basis ───────────────────────────────────────────────────────────
BASIS_RULE_BASED        = "RULE_BASED"
BASIS_AI_ASSISTED       = "AI_ASSISTED"
BASIS_FALLBACK          = "FALLBACK"
BASIS_HISTORICAL_REPLAY = "HISTORICAL_REPLAY"

# ── Outcome values ─────────────────────────────────────────────────────────────
OUTCOME_SUCCESS     = "success"
OUTCOME_FAILURE     = "failure"
OUTCOME_DEGRADED    = "degraded"
OUTCOME_SHADOW_ONLY = "shadow_only"
OUTCOME_DEFERRED    = "deferred"

# ── Config V2 scoring threshold keys (spec/01 §12, directives/core_decision_engine §4) ──
K_HWS_BEHIND_HIGH_RISK = "hws_behind_high_risk_threshold"
K_HWS_BEHIND_MODERATE  = "hws_behind_moderate_threshold"
K_AVG_EFF_RATING       = "avg_eff_rating_low_risk_threshold"
K_INACTIVITY_HIGH_RISK = "last_activity_high_risk_days"
K_INACTIVITY_MODERATE  = "last_activity_moderate_days"
K_PAYMENT_RISK         = "payment_balance_risk_threshold"
K_ESCALATION_REPEAT    = "prior_escalation_repeat_threshold"
K_AI_INSIGHT_TTL_HOURS = "ai_insight_ttl_hours"

_PRIORITY_THRESHOLD_KEYS = (
    K_HWS_BEHIND_HIGH_RISK,
    K_HWS_BEHIND_MODERATE,
    K_AVG_EFF_RATING,
    K_INACTIVITY_HIGH_RISK,
    K_INACTIVITY_MODERATE,
    K_PAYMENT_RISK,
    K_ESCALATION_REPEAT,
    K_AI_INSIGHT_TTL_HOURS,
)

UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields (block RULE 0 if absent) ──────────────────────
REQUIRED_PRIORITY_ATTRIBUTION = ("origin_source", "origin_authority", "actor_identity")


# ── Input context ──────────────────────────────────────────────────────────────

@dataclass
class PrioritizationContext:
    """Governance context for an orchestration prioritization advisory evaluation."""

    # Governance — mandatory
    config_version_id: Optional[str]
    execution_mode: str   # SHADOW | LIVE
    execution_type: str   # original | replay | regeneration | recovery
    correlation_id: Optional[str]

    config_rule_set: Optional[Dict[str, Any]] = None
    causation_id: Optional[str] = None
    orchestration_cycle_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    maintenance_mode_active: bool = False

    # Attribution — propagated immutably; never accepted from external callers
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    actor_identity: Optional[str] = None
    attribution_timestamp: Optional[str] = None
    upstream_correlation_id: Optional[str] = None

    # Academic signals (SQL Server-authoritative — INVARIANT-6)
    hws_behind: Optional[int] = None
    avg_eff_rating: Optional[float] = None
    last_activity_days: Optional[int] = None
    payment_balance: Optional[float] = None
    access_last_changed_days: Optional[int] = None  # days since last access state change

    # Historical signals (platform_supplementary)
    historical_risk_trend: Optional[str] = None
    prior_escalation_count: Optional[int] = None

    # AI governance inputs — advisory only (AP-D12)
    ai_insight_state: Optional[str] = None
    ai_confidence_score: Optional[float] = None
    ai_recommended_intervention: Optional[str] = None
    ai_stale_flag: Optional[bool] = None
    ai_finalized_copy: bool = False

    # Replay/regeneration context
    source_artifact_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None

    # State lineage
    execution_state_before: Optional[str] = None
    execution_state_after: Optional[str] = None

    # Opaque student identifier — never raw PII (AP-D10, AP-RT13)
    student_id_opaque: Optional[str] = None


# ── Output record ──────────────────────────────────────────────────────────────

@dataclass
class PrioritizationRecord:
    """
    Advisory orchestration prioritization record.
    Advisory contract only — consuming services act on the returned record.
    Never dispatches, never mutates state (AP-E1, AP-E2, AP-D1, AP-D3).
    Attribution propagated immutably from input.
    """

    # Advisory priority output
    advisory_priority: str             # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
    governance_scope: str
    assessment_basis: str              # RULE_BASED | AI_ASSISTED | FALLBACK | HISTORICAL_REPLAY

    # Containment
    is_replay: bool
    live_effects_suppressed: bool

    # Attribution — propagated immutably (AP-D13, AP-E15)
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    upstream_correlation_id: Optional[str]

    # Config lineage
    config_version_id: Optional[str]
    historical_config_version_id: Optional[str]
    threshold_bindings: Dict[str, Any]

    # Observability
    event_id: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    execution_type: str
    execution_mode: str
    rule_path_taken: List[str]
    duration_ms: int
    outcome: str
    error_class: Optional[str]

    # Scoring lineage — immutable historical explainability (AP-E5, FAD-4, IML-1)
    scoring_factors: List[Dict[str, Any]]  # [{factor, contribution, threshold_key, value}]
    risk_contributions: List[str]          # list of RISK_HIGH/MEDIUM/LOW per factor

    # AI governance context
    ai_governance_tier: str
    ai_confidence_score: Optional[float]
    ai_priority_adjustment_applied: bool
    ai_fallback_applied: bool

    # State lineage
    execution_state_before: Optional[str]
    execution_state_after: Optional[str]
    causation_chain_preserved: bool

    # Invariant fields — always True (FAD-4, IML-1, IML-3)
    append_only_enforced: bool       # always True — FAD-4; scoring lineage never overwritten
    replay_lineage_preserved: bool   # always True — IML-3; replay scoring distinguishable from LIVE
    scoring_lineage_immutable: bool  # always True — IML-1; historical scoring records never mutated

    # Authorization (Phase-12 cert gate)
    scoring_emit_authorized: bool    # False until Phase-12 cert

    # Degradation
    degraded: bool
    degradation_flags: List[str]
    degradation_cause: Optional[str]

    # Result
    reason_codes: List[str]
    orchestration_blocked: bool
    blocking_reason: Optional[str]
    orchestration_continues: bool
