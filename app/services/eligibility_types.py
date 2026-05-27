"""
Governance-safe eligibility assessment contract types.

Input and output dataclasses for the orchestration eligibility service.
Consumed by app/services/eligibility.py (rule evaluation) and the Core
Decision Engine.

No rule logic lives here. No imports from app services. Types only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Eligibility scope values (directive §3.2) ─────────────────────────────────
SCOPE_OUTREACH            = "OUTREACH"
SCOPE_RETRY               = "RETRY"
SCOPE_ESCALATION          = "ESCALATION_CANDIDATE"
SCOPE_REPLAY              = "REPLAY_CANDIDATE"
SCOPE_PRIORITIZATION_ONLY = "PRIORITIZATION_ONLY"
SCOPE_NONE                = "NONE"

# ── AI governance tiers (directive §7) ────────────────────────────────────────
AI_CONFIDENT      = "CONFIDENT"
AI_ADVISORY       = "ADVISORY"
AI_STALE          = "STALE"
AI_IN_FLIGHT      = "IN_FLIGHT"
AI_UNAVAILABLE    = "UNAVAILABLE"
AI_FINALIZED_COPY = "FINALIZED_COPY"

# ── UNKNOWN_V0: mandatory sentinel for missing Config V2 thresholds (AP-E9) ───
UNKNOWN_V0 = "UNKNOWN_V0"

# ── Priority levels ───────────────────────────────────────────────────────────
PRI_CRITICAL = "CRITICAL"
PRI_HIGH     = "HIGH"
PRI_MEDIUM   = "MEDIUM"
PRI_LOW      = "LOW"
PRI_UNKNOWN  = "UNKNOWN"

# ── Config rule-set key constants (Rule 3 threshold table) ───────────────────
K_EXCL_WINDOW  = "outreach_exclusion_window_hours"
K_MIN_HWS      = "hws_behind_minimum_threshold"
K_MIN_EFF      = "avg_eff_rating_minimum_threshold"
K_MAX_INACT    = "last_activity_max_days"
K_MAX_ATTEMPTS = "outreach_max_attempts"
K_RETRY_WINDOW = "outreach_retry_window_hours"
K_PAYMENT_RISK = "payment_balance_risk_threshold"
K_AI_TTL       = "ai_insight_ttl_hours"
K_ESC_REPEAT   = "prior_escalation_repeat_threshold"
K_HWS_HIGH     = "hws_behind_high_risk_threshold"
K_INACT_HIGH   = "last_activity_high_risk_days"
K_SYNC_AGE     = "sql_server_max_sync_age_hours"

REQUIRED_ATTRIBUTION = ("origin_source", "origin_authority",
                        "actor_identity", "attribution_timestamp")

# ── Input dataclasses ─────────────────────────────────────────────────────────

@dataclass
class GovernanceCtx:
    config_version_id: Optional[str]
    config_version_status: str           # ACTIVE | SUPERSEDED
    config_rule_set: Dict[str, Any]
    execution_mode: str                  # SHADOW | LIVE
    execution_type: str                  # original | replay | regeneration
    correlation_id: Optional[str]
    causation_id: Optional[str]
    attribution_context: Dict[str, Any]
    fingerprint_context: Optional[Dict[str, Any]]
    idempotency_key: Optional[str]
    compliance_hold_flag: bool = False
    replay_context: Optional[Dict[str, Any]] = None


@dataclass
class AcademicCtx:
    """SQL Server-authoritative fields govern eligibility (AP-E8, INVARIANT-6)."""
    user_id: Optional[int]               # never logged raw — AP-E10
    access_state: Optional[str]          # ACTIVE | REVOKED | SUSPENDED
    hws_behind: Optional[int]
    avg_eff_rating: Optional[float]
    last_activity_days: Optional[int]
    payment_balance: Optional[float]
    email: Optional[str]                 # contact gate only; never logged
    phone_number: Optional[str]          # contact gate only; never logged
    sql_server_sync_timestamp: Optional[str] = None
    historical_risk_trend: Optional[str] = None
    prior_escalation_count: int = 0
    access_last_changed: Optional[str] = None


@dataclass
class OperationalCtx:
    outreach_state: Optional[str]
    contact_attempt_count: int
    retry_eligible: bool
    last_contact_timestamp: Optional[str] = None


@dataclass
class AICtx:
    ai_insight_state: Optional[str]
    ai_confidence_score: Optional[float]
    ai_stale_flag: bool
    ai_finalized_copy: bool
    ai_recommended_intervention: Optional[str] = None
    ai_generated_at: Optional[str] = None


@dataclass
class EligibilityContext:
    governance: GovernanceCtx
    academic: AcademicCtx
    operational: OperationalCtx
    ai: AICtx


# ── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class OrchestrationConstraints:
    max_attempts_constraint: Any = UNKNOWN_V0
    exclusion_window_constraint_hours: Any = UNKNOWN_V0
    retry_window_constraint_hours: Any = UNKNOWN_V0
    execution_mode_constraint: str = "SHADOW"
    ai_prioritization_applied: bool = False
    live_outreach_permitted: bool = False


@dataclass
class GovernanceRequirements:
    config_version_id: Optional[str] = None
    config_version_status: str = "UNKNOWN"
    execution_mode: str = "SHADOW"
    idempotency_key: Optional[str] = None
    governance_preconditions_met: bool = False
    blocking_governance_flags: List[str] = field(default_factory=list)


@dataclass
class ReplayRestrictions:
    is_replay: bool = False
    replay_eligible: bool = False
    live_eligible: bool = False
    source_artifact_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None
    fingerprint_comparison_outcome: Optional[str] = None
    replay_safe: bool = True


@dataclass
class AIOutputCtx:
    ai_input_used: bool = False
    ai_governance_tier: str = AI_UNAVAILABLE
    ai_confidence_score: Optional[float] = None
    stale_flag: bool = False
    fallback_applied: bool = False
    priority_adjustment_applied: bool = False
    ai_version_number: Optional[str] = None


@dataclass
class ThresholdBindings:
    exclusion_window_hours: Any = UNKNOWN_V0
    min_hws_behind: Any = UNKNOWN_V0
    min_effort_rating: Any = UNKNOWN_V0
    max_inactivity_days: Any = UNKNOWN_V0
    max_outreach_attempts: Any = UNKNOWN_V0
    retry_window_hours: Any = UNKNOWN_V0
    payment_risk_balance_threshold: Any = UNKNOWN_V0
    ai_insight_ttl_hours: Any = UNKNOWN_V0
    escalation_repeat_threshold: Any = UNKNOWN_V0
    hws_behind_high_risk: Any = UNKNOWN_V0
    inactivity_high_risk_days: Any = UNKNOWN_V0


@dataclass
class OrchestrationEligibilityAssessment:
    orchestration_eligible: bool
    eligibility_scope: str
    orchestration_priority: str = PRI_UNKNOWN
    orchestration_constraints: OrchestrationConstraints = field(
        default_factory=OrchestrationConstraints)
    governance_requirements: GovernanceRequirements = field(
        default_factory=GovernanceRequirements)
    replay_restrictions: ReplayRestrictions = field(
        default_factory=ReplayRestrictions)
    ai_context: AIOutputCtx = field(default_factory=AIOutputCtx)
    threshold_bindings: ThresholdBindings = field(default_factory=ThresholdBindings)
    attribution_metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    config_version_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None
    execution_mode: str = "SHADOW"
    execution_type: str = "original"
    attribution_status: str = "COMPLETE"
    degraded_evaluation: bool = False
    threshold_resolution_status: str = "COMPLETE"
    live_outreach_permitted: bool = False
    replay_safe: bool = True
    rule_path_taken: List[str] = field(default_factory=list)
    assessment_basis: str = "RULE_BASED"
    reason_codes: List[str] = field(default_factory=list)
    eligibility_blocked: bool = False
    blocking_reason: Optional[str] = None
    config_threshold_warnings: List[str] = field(default_factory=list)
    student_id_opaque: Optional[str] = None
