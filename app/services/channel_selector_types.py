"""
Governance-safe channel advisory contract types.

Input and output dataclasses for the channel advisory service.
Consumed by app/services/channel_selector.py.
No rule logic. Types only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Advisory scope values (directive §3.2) ────────────────────────────────────
SCOPE_CALL_PREFERRED         = "CALL_PREFERRED"
SCOPE_SMS_PREFERRED          = "SMS_PREFERRED"
SCOPE_EMAIL_PREFERRED        = "EMAIL_PREFERRED"
SCOPE_MULTI_CHANNEL_ELIGIBLE = "MULTI_CHANNEL_ELIGIBLE"
SCOPE_CHANNEL_EXHAUSTED      = "CHANNEL_EXHAUSTED"
SCOPE_REPLAY_CANDIDATE       = "REPLAY_CHANNEL_CANDIDATE"
SCOPE_NONE                   = "NONE"

# ── Channel identifiers ───────────────────────────────────────────────────────
CH_CALL  = "CALL"
CH_SMS   = "SMS"
CH_EMAIL = "EMAIL"
ALL_CHANNELS = (CH_CALL, CH_SMS, CH_EMAIL)

# Scopes that represent advisory candidacy suitable for outbound delivery
_DELIVERY_SCOPES = frozenset({
    SCOPE_CALL_PREFERRED, SCOPE_SMS_PREFERRED,
    SCOPE_EMAIL_PREFERRED, SCOPE_MULTI_CHANNEL_ELIGIBLE,
})

# ── AI governance tiers (directive §7) ───────────────────────────────────────
AI_CONFIDENT      = "CONFIDENT"
AI_ADVISORY       = "ADVISORY"
AI_STALE          = "STALE"
AI_IN_FLIGHT      = "IN_FLIGHT"
AI_UNAVAILABLE    = "UNAVAILABLE"
AI_FINALIZED_COPY = "FINALIZED_COPY"

# ── UNKNOWN_V0: mandatory sentinel for missing Config V2 thresholds (AP-C9) ──
UNKNOWN_V0 = "UNKNOWN_V0"

# ── Advisory confidence levels ────────────────────────────────────────────────
CONF_HIGH    = "HIGH"
CONF_MEDIUM  = "MEDIUM"
CONF_LOW     = "LOW"
CONF_UNKNOWN = "UNKNOWN"

# ── AI channel preference signals ────────────────────────────────────────────
PREF_CALL  = "PREFER_CALL"
PREF_SMS   = "PREFER_SMS"
PREF_EMAIL = "PREFER_EMAIL"
PREF_NONE  = "NO_PREFERENCE"

# ── Config rule-set key constants (Rule 3 threshold table) ───────────────────
K_PREFERRED_CHANNEL  = "outreach_initial_channel_preference"
K_DELIVERY_FAIL_SUSP = "channel_delivery_failure_suspension_threshold"
K_CALL_ENG           = "call_engagement_score_threshold"
K_SMS_ENG            = "sms_engagement_score_threshold"
K_EMAIL_ENG          = "email_engagement_score_threshold"
K_COOLDOWN_HOURS     = "channel_specific_cooldown_hours"
K_AI_TTL             = "ai_insight_ttl_hours"
K_OPT_OUT_PERIOD     = "channel_opt_out_respect_period_hours"

REQUIRED_ATTRIBUTION = (
    "origin_source", "origin_authority",
    "actor_identity", "attribution_timestamp",
)

# ── Input dataclasses ─────────────────────────────────────────────────────────

@dataclass
class GovernanceCtx:
    config_version_id: Optional[str]
    config_version_status: str
    config_rule_set: Dict[str, Any]
    execution_mode: str
    execution_type: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    attribution_context: Dict[str, Any]
    fingerprint_context: Optional[Dict[str, Any]]
    idempotency_key: Optional[str]
    compliance_hold_flag: bool = False
    replay_context: Optional[Dict[str, Any]] = None


@dataclass
class CommunicationCtx:
    contact_attempt_count: int = 0
    last_channel_used: Optional[str] = None
    last_contact_timestamp: Optional[str] = None
    last_contact_outcome: Optional[str] = None
    channel_delivery_history: List[Dict[str, Any]] = field(default_factory=list)
    channel_attempt_counts: Dict[str, int] = field(default_factory=dict)
    engagement_history: List[Dict[str, Any]] = field(default_factory=list)
    retry_lineage: Optional[Dict[str, Any]] = None
    escalation_lineage: List[Dict[str, Any]] = field(default_factory=list)
    orchestration_history: List[Dict[str, Any]] = field(default_factory=list)
    quick_action_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AICtx:
    ai_insight_state: Optional[str]
    ai_confidence_score: Optional[float]
    ai_stale_flag: bool
    ai_finalized_copy: bool
    ai_channel_preference_signal: Optional[str] = None
    ai_sentiment: Optional[str] = None
    ai_generated_at: Optional[str] = None
    ai_insight_version: Optional[int] = None
    ai_ttl_hours: Optional[int] = None
    ai_recommended_intervention: Optional[str] = None


@dataclass
class OperationalCtx:
    email: Optional[str]         # contact gate only; never logged — AP-C10
    phone_number: Optional[str]  # contact gate only; never logged — AP-C10
    access_state: Optional[str]
    outreach_state: Optional[str] = None
    engagement_signal_score: Optional[float] = None
    provider_health_state: Optional[Dict[str, str]] = None
    channel_opt_out_state: Optional[Dict[str, bool]] = None
    channel_delivery_failure_counts: Optional[Dict[str, int]] = None
    channel_suspension_state: Optional[Dict[str, bool]] = None
    channel_exhaustion_state: Optional[str] = None
    ghl_delivery_capability: Optional[Dict[str, bool]] = None
    sql_server_sync_timestamp: Optional[str] = None
    historical_risk_trend: Optional[str] = None


@dataclass
class ChannelAdvisoryContext:
    governance: GovernanceCtx
    communication: CommunicationCtx
    operational: OperationalCtx
    ai: AICtx


# ── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class GovernanceConstraints:
    execution_mode_constraint: str = "SHADOW"
    live_delivery_permitted: bool = False
    governance_scope: str = "SHADOW_ONLY"
    suppression_reason: Optional[str] = None
    compliance_channel_restrictions: List[str] = field(default_factory=list)
    opt_out_channel_exclusions: List[str] = field(default_factory=list)
    suspended_channel_exclusions: List[str] = field(default_factory=list)
    config_version_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    governance_preconditions_met: bool = False
    blocking_governance_flags: List[str] = field(default_factory=list)


@dataclass
class EscalationConstraints:
    escalation_recommended: bool = False
    escalation_urgency: str = "NONE"
    escalation_reason_codes: List[str] = field(default_factory=list)
    escalation_context: Dict[str, Any] = field(default_factory=dict)


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
    channel_priority_adjustment_applied: bool = False
    ai_channel_preference_signal: Optional[str] = None
    ai_version_number: Optional[str] = None


@dataclass
class ThresholdBindings:
    preferred_initial_channel: Any = UNKNOWN_V0
    delivery_failure_suspension_threshold: Any = UNKNOWN_V0
    call_engagement_score_threshold: Any = UNKNOWN_V0
    sms_engagement_score_threshold: Any = UNKNOWN_V0
    email_engagement_score_threshold: Any = UNKNOWN_V0
    channel_specific_cooldown_hours: Any = UNKNOWN_V0
    ai_insight_ttl_hours: Any = UNKNOWN_V0
    channel_opt_out_respect_period_hours: Any = UNKNOWN_V0


@dataclass
class ProviderHealthMetadata:
    call_provider_state: str = "UNKNOWN"
    sms_provider_state: str = "UNKNOWN"
    email_provider_state: str = "UNKNOWN"
    channel_suspension_applied: bool = False
    suspended_channels: List[str] = field(default_factory=list)


@dataclass
class ChannelAdvisoryAssessment:
    channel_advisory_produced: bool
    advisory_scope: str
    recommended_channel_candidates: List[str] = field(default_factory=list)
    prohibited_channels: List[str] = field(default_factory=list)
    governance_constraints: GovernanceConstraints = field(
        default_factory=GovernanceConstraints)
    escalation_constraints: EscalationConstraints = field(
        default_factory=EscalationConstraints)
    replay_restrictions: ReplayRestrictions = field(
        default_factory=ReplayRestrictions)
    ai_context: AIOutputCtx = field(default_factory=AIOutputCtx)
    threshold_bindings: ThresholdBindings = field(default_factory=ThresholdBindings)
    provider_health_metadata: ProviderHealthMetadata = field(
        default_factory=ProviderHealthMetadata)
    advisory_confidence: str = CONF_UNKNOWN
    execution_mode: str = "SHADOW"
    execution_type: str = "original"
    config_version_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    attribution_metadata: Dict[str, Any] = field(default_factory=dict)
    attribution_status: str = "COMPLETE"
    degraded_evaluation: bool = False
    rule_path_taken: List[str] = field(default_factory=list)
    assessment_basis: str = "RULE_BASED"
    reason_codes: List[str] = field(default_factory=list)
    advisory_blocked: bool = False
    blocking_reason: Optional[str] = None
    config_threshold_warnings: List[str] = field(default_factory=list)
    student_id_opaque: Optional[str] = None
