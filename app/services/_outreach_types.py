"""
Contract types for the governance-safe outreach orchestration coordination layer.
Not part of the public API. Consumed by outreach.py and _outreach_helpers.py.
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
TYPE_RECOVERY     = "recovery"

_VALID_EXECUTION_MODES = frozenset({MODE_SHADOW, MODE_LIVE})
_VALID_EXECUTION_TYPES = frozenset({TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION, TYPE_RECOVERY})
_REPLAY_TYPES          = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

# ── Governance scopes ─────────────────────────────────────────────────────────
SCOPE_AUTHORIZED  = "AUTHORIZED"    # requires Phase-12 certification — currently unreachable
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_MAINTENANCE = "MAINTENANCE"

# ── Orchestration intent types (runtime/system_loop.md §2.3) ─────────────────
INTENT_INITIATE_OUTREACH = "INITIATE_OUTREACH"
INTENT_RETRY_OUTREACH    = "RETRY_OUTREACH"
INTENT_ESCALATE          = "ESCALATE"
INTENT_CLOSE             = "CLOSE"
INTENT_DEFER_PENDING_AI  = "DEFER_PENDING_AI"
INTENT_HOLD              = "HOLD"

# ── Outreach lifecycle states (spec/03_state_transition_rules.md) ─────────────
STATE_ELIGIBLE              = "ELIGIBLE"
STATE_QUEUED                = "QUEUED"
STATE_CONTACTED             = "CONTACTED"
STATE_NO_RESPONSE           = "NO_RESPONSE"
STATE_RESPONDED             = "RESPONDED"
STATE_INTERVENTION_REQUIRED = "INTERVENTION_REQUIRED"
STATE_CLOSED                = "CLOSED"

_TERMINAL_STATES  = frozenset({STATE_RESPONDED, STATE_CLOSED, STATE_INTERVENTION_REQUIRED})
_INITIAL_STATES   = frozenset({None, STATE_ELIGIBLE, STATE_QUEUED})

# ── AI governance tiers (llm_processing_contract.md §2) ──────────────────────
AI_TIER_CONFIDENT     = "CONFIDENT"
AI_TIER_ADVISORY      = "ADVISORY"
AI_TIER_STALE         = "STALE"
AI_TIER_IN_FLIGHT     = "IN_FLIGHT"
AI_TIER_UNAVAILABLE   = "UNAVAILABLE"
AI_TIER_FINALIZED_COPY = "FINALIZED_COPY"

_STALE_AI_TIERS = frozenset({AI_TIER_STALE, AI_TIER_UNAVAILABLE})

# ── Circuit breaker states ────────────────────────────────────────────────────
CB_OPEN      = "OPEN"
CB_CLOSED    = "CLOSED"
CB_HALF_OPEN = "HALF_OPEN"
CB_UNKNOWN   = "UNKNOWN"

# ── Outcome values ────────────────────────────────────────────────────────────
OUTCOME_SUCCESS     = "success"
OUTCOME_FAILURE     = "failure"
OUTCOME_DEGRADED    = "degraded"
OUTCOME_SHADOW_ONLY = "shadow_only"

# ── Config V2 Group A / H / K threshold keys (spec/01 §12) ───────────────────
K_OUTREACH_MAX_RETRY_ATTEMPTS    = "outreach_max_retry_attempts"
K_OUTREACH_RETRY_WINDOW_DAYS     = "outreach_retry_window_days"
K_AI_INSIGHT_TTL_HOURS           = "ai_insight_ttl_hours"
K_SQL_MAX_SYNC_AGE_HOURS         = "sql_server_max_sync_age_hours"
K_ORCHESTRATION_CONCURRENCY_LIMIT = "orchestration_concurrency_limit"

_ORCHESTRATION_THRESHOLD_KEYS = (
    K_OUTREACH_MAX_RETRY_ATTEMPTS,
    K_OUTREACH_RETRY_WINDOW_DAYS,
    K_AI_INSIGHT_TTL_HOURS,
    K_SQL_MAX_SYNC_AGE_HOURS,
    K_ORCHESTRATION_CONCURRENCY_LIMIT,
)

UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields (subset that blocks RULE 0 if absent) ─────────
REQUIRED_OUTREACH_ATTRIBUTION = ("origin_source", "origin_authority", "actor_identity")


# ── Input context ─────────────────────────────────────────────────────────────

@dataclass
class OutreachOrchestrationContext:
    """Governance context for an outreach orchestration coordination evaluation."""

    # Governance §3.1 — mandatory
    config_version_id: Optional[str]
    execution_mode: str    # SHADOW | LIVE
    execution_type: str    # original | replay | regeneration | recovery
    correlation_id: Optional[str]

    config_rule_set: Optional[Dict[str, Any]] = None
    causation_id: Optional[str] = None
    orchestration_cycle_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    compliance_hold_flag: bool = False
    maintenance_mode_active: bool = False

    # Attribution §3.2 — set by platform; never accepted from external callers (AP-RT4)
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    actor_identity: Optional[str] = None
    attribution_timestamp: Optional[str] = None
    upstream_correlation_id: Optional[str] = None

    # Student context — opaque ID only; PII never logged (AP-RT13)
    student_id_opaque: Optional[str] = None
    checkpoint_type: Optional[str] = None
    outreach_state: Optional[str] = None
    contact_attempt_count: int = 0
    last_contact_at: Optional[str] = None    # ISO-8601

    # Provider context
    circuit_breaker_state: str = CB_UNKNOWN
    provider_degradation_state: str = "OPERATIONAL"
    sync_lag_hours: float = 0.0

    # AI context
    ai_governance_tier: Optional[str] = None
    ai_confidence_score: Optional[float] = None

    # Replay context
    historical_config_version_id: Optional[str] = None
    source_artifact_id: Optional[str] = None


# ── Output coordination record ────────────────────────────────────────────────

@dataclass
class OutreachCoordinationRecord:
    """
    Governance coordination record for an outreach orchestration evaluation.
    Advisory contract — not an execution result. Consuming services act on this.
    Never dispatches, never mutates state (AP-RT1, AP-DF1, AP-RF1).
    """

    # Core governance
    governance_scope: str
    intent_type: Optional[str]

    # Containment
    is_replay: bool
    live_effects_suppressed: bool

    # Attribution — propagated immutably from input (AP-RT4, AP-DF5)
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

    # Student lineage — opaque ID only (AP-RT13)
    student_id_opaque: Optional[str]
    checkpoint_type: Optional[str]
    contact_attempt_count: int

    # Dispatch authorization
    dispatch_authorized: bool
    dispatch_blocked_reason: Optional[str]

    # Degradation
    degraded: bool
    degradation_flags: List[str]
    degradation_cause: Optional[str]

    # Escalation
    escalation_candidate: bool
    escalation_candidacy_reason: Optional[str]

    # Compliance
    compliance_hold_active: bool

    # AI governance
    ai_governance_tier: Optional[str]
    ai_escalation_authority: bool
    stale_sql_server_data: bool

    # Result
    reason_codes: List[str]
    orchestration_blocked: bool
    blocking_reason: Optional[str]
    orchestration_continues: bool
