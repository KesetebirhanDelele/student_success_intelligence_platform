"""
Contract types for the governance-safe timeline lineage service.
Not part of the public API. Consumed by timeline.py and _timeline_helpers.py.
"""
from __future__ import annotations

from dataclasses import dataclass
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
SCOPE_AUTHORIZED  = "AUTHORIZED"    # Phase-12 certification — currently unreachable
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_MAINTENANCE = "MAINTENANCE"

# ── Event types ───────────────────────────────────────────────────────────────
EVENT_ORCHESTRATION         = "ORCHESTRATION"
EVENT_RETRY                 = "RETRY"
EVENT_ESCALATION            = "ESCALATION"
EVENT_PROVIDER_SUPPRESSION  = "PROVIDER_SUPPRESSION"
EVENT_REPLAY                = "REPLAY"
EVENT_DEGRADATION           = "DEGRADATION"
EVENT_GOVERNANCE_TRANSITION = "GOVERNANCE_TRANSITION"
EVENT_AI_LIFECYCLE          = "AI_LIFECYCLE"
EVENT_SNAPSHOT_LIFECYCLE    = "SNAPSHOT_LIFECYCLE"
EVENT_COMMUNICATION         = "COMMUNICATION"
EVENT_STATE_CHANGE          = "STATE_CHANGE"
EVENT_NOTE                  = "NOTE"
EVENT_CONFIG_TRANSITION     = "CONFIG_TRANSITION"
EVENT_COMPLIANCE_LIFECYCLE  = "COMPLIANCE_LIFECYCLE"
EVENT_UNKNOWN               = "UNKNOWN"

_VALID_EVENT_TYPE_HINTS = frozenset({
    EVENT_ORCHESTRATION, EVENT_RETRY, EVENT_ESCALATION, EVENT_PROVIDER_SUPPRESSION,
    EVENT_REPLAY, EVENT_DEGRADATION, EVENT_GOVERNANCE_TRANSITION, EVENT_AI_LIFECYCLE,
    EVENT_SNAPSHOT_LIFECYCLE, EVENT_COMMUNICATION, EVENT_STATE_CHANGE, EVENT_NOTE,
    EVENT_CONFIG_TRANSITION, EVENT_COMPLIANCE_LIFECYCLE, EVENT_UNKNOWN,
})

# ── Lineage visibility ────────────────────────────────────────────────────────
VISIBILITY_LIVE_VISIBLE        = "LIVE_VISIBLE"
VISIBILITY_SHADOW_VISIBLE      = "SHADOW_VISIBLE"
VISIBILITY_REPLAY_ONLY         = "REPLAY_ONLY"
VISIBILITY_FINALIZED_PROTECTED = "FINALIZED_PROTECTED"

# ── Authority classifications ─────────────────────────────────────────────────
AUTHORITY_SQL_SERVER = "sql_server_authoritative"
AUTHORITY_PLATFORM   = "platform_supplementary"
AUTHORITY_OPERATOR   = "operator_authorized"
AUTHORITY_GHL        = "ghl_sync"
AUTHORITY_AI         = "ai_subsystem"
AUTHORITY_COMPLIANCE = "compliance_authorized"
AUTHORITY_SYSTEM     = "system_automated"

# ── Origin source values (spec/03 §39.2) ─────────────────────────────────────
ORIGIN_MIRRORED_SQL    = "mirrored_sql_server"
ORIGIN_SCHEDULER       = "scheduler"
ORIGIN_OPERATOR        = "operator"
ORIGIN_PLATFORM_MANUAL = "platform_manual"
ORIGIN_PLATFORM_SYSTEM = "platform_system"
ORIGIN_COMPLIANCE      = "compliance_pathway"
ORIGIN_GHL             = "ghl"
ORIGIN_AI              = "ai_subsystem"

_SQL_SERVER_ORIGINS = frozenset({ORIGIN_MIRRORED_SQL})

# ── Raw event source identifiers (spec/08 §4) ─────────────────────────────────
SOURCE_OUTREACH_HISTORY     = "outreach_history"
SOURCE_STATE_TRANSITION_LOG = "state_transition_log"
SOURCE_STUDENT_NOTES        = "student_notes"
SOURCE_AI_INSIGHTS          = "ai_insights"
SOURCE_GHL_MESSAGES         = "ghl_messages"
SOURCE_CAMPAIGN_ACTIVITY    = "student_campaign_activity"
SOURCE_QUICK_ACTION_LOG     = "student_quick_action_log"
SOURCE_SNAPSHOT_LIFECYCLE   = "snapshot_lifecycle_log"
SOURCE_REPORT_LIFECYCLE     = "report_lifecycle_log"
SOURCE_CONFIG_LIFECYCLE     = "config_version_registry"
SOURCE_COMPLIANCE_AUDIT     = "compliance_audit"
SOURCE_ORCHESTRATION        = "orchestration_coordinator"

# Canonical source → event type mapping (spec/08 §16)
_SOURCE_EVENT_TYPE_MAP: Dict[str, str] = {
    SOURCE_OUTREACH_HISTORY:     EVENT_ORCHESTRATION,
    SOURCE_STATE_TRANSITION_LOG: EVENT_STATE_CHANGE,
    SOURCE_STUDENT_NOTES:        EVENT_NOTE,
    SOURCE_AI_INSIGHTS:          EVENT_AI_LIFECYCLE,
    SOURCE_GHL_MESSAGES:         EVENT_COMMUNICATION,
    SOURCE_CAMPAIGN_ACTIVITY:    EVENT_COMMUNICATION,
    SOURCE_QUICK_ACTION_LOG:     EVENT_GOVERNANCE_TRANSITION,
    SOURCE_SNAPSHOT_LIFECYCLE:   EVENT_SNAPSHOT_LIFECYCLE,
    SOURCE_REPORT_LIFECYCLE:     EVENT_GOVERNANCE_TRANSITION,
    SOURCE_CONFIG_LIFECYCLE:     EVENT_CONFIG_TRANSITION,
    SOURCE_COMPLIANCE_AUDIT:     EVENT_COMPLIANCE_LIFECYCLE,
    SOURCE_ORCHESTRATION:        EVENT_ORCHESTRATION,
}

# ── Outcome values ────────────────────────────────────────────────────────────
OUTCOME_SUCCESS     = "success"
OUTCOME_FAILURE     = "failure"
OUTCOME_DEGRADED    = "degraded"
OUTCOME_SHADOW_ONLY = "shadow_only"

# ── Config V2 Group K timeline governance threshold keys (spec/01 §12) ───────
K_TIMELINE_MAX_EVENTS         = "timeline_max_events_per_student"
K_TIMELINE_RETENTION_DAYS     = "timeline_retention_days"
K_TIMELINE_REPLAY_WINDOW_DAYS = "timeline_replay_window_days"

_TIMELINE_THRESHOLD_KEYS = (
    K_TIMELINE_MAX_EVENTS,
    K_TIMELINE_RETENTION_DAYS,
    K_TIMELINE_REPLAY_WINDOW_DAYS,
)

UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields (block RULE 0 if absent) ─────────────────────
REQUIRED_TIMELINE_ATTRIBUTION = ("origin_source", "origin_authority", "actor_identity")


# ── Input context ─────────────────────────────────────────────────────────────

@dataclass
class TimelineEventContext:
    """Governance context for a timeline event lineage classification evaluation."""

    # Governance §3.1 — mandatory
    config_version_id: Optional[str]
    execution_mode: str    # SHADOW | LIVE
    execution_type: str    # original | replay | regeneration | recovery
    correlation_id: Optional[str]

    config_rule_set: Optional[Dict[str, Any]] = None
    causation_id: Optional[str] = None
    orchestration_cycle_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    maintenance_mode_active: bool = False

    # Attribution — set by platform; never accepted from external callers
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    actor_identity: Optional[str] = None
    attribution_timestamp: Optional[str] = None
    upstream_correlation_id: Optional[str] = None

    # Event classification inputs
    event_type_hint: Optional[str] = None      # caller hint; canonical classification applied
    raw_event_source: Optional[str] = None     # DB table / system for source→type mapping

    # State lineage (spec/03 §39, spec/08 §16)
    execution_state_before: Optional[str] = None
    execution_state_after: Optional[str] = None

    # Lineage governance context
    finalized_lineage_detected: bool = False   # event associated with FINALIZED context (IML-1)
    source_artifact_id: Optional[str] = None  # replay source artifact
    historical_config_version_id: Optional[str] = None

    # Opaque student identifier — never contains raw PII (AP-RT13)
    student_id_opaque: Optional[str] = None


# ── Output lineage record ─────────────────────────────────────────────────────

@dataclass
class TimelineLineageRecord:
    """
    Governance lineage record for a timeline event classification evaluation.
    Advisory contract — not an execution result. Consuming services act on this.
    Never dispatches, never mutates historical timeline state (FAD-4, IML-1).
    """

    # Core governance
    governance_scope: str
    event_type: Optional[str]       # None on replay — no live classification (INV-4, AP-RT2)
    lineage_visibility: str

    # Containment
    is_replay: bool
    live_effects_suppressed: bool

    # Attribution — propagated immutably from input (INV-5, ATT-*)
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    upstream_correlation_id: Optional[str]
    authoritative_source: str

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

    # Timeline lineage governance (FAD-4, IML-1, IML-3, CID-*, ATT-*)
    execution_state_before: Optional[str]
    execution_state_after: Optional[str]
    causation_chain_preserved: bool
    append_only_enforced: bool          # always True — FAD-4; no timeline record is ever overwritten
    finalized_lineage_protected: bool   # always True — IML-1, IML-3; FINALIZED events never mutated
    replay_lineage_preserved: bool      # always True — IML-3; replay events distinguishable from LIVE

    # SQL Server authority preservation (INVARIANT-6, spec/03 §39.3)
    sql_server_authority_preserved: bool  # always True — SQL Server origin never overwritten

    # Authorization (Phase-12 cert gate — same pattern as dispatch_authorized in other layers)
    lineage_emit_authorized: bool       # False until Phase-12 cert; see RULE 11

    # Degradation
    degraded: bool
    degradation_flags: List[str]
    degradation_cause: Optional[str]

    # Result
    reason_codes: List[str]
    orchestration_blocked: bool
    blocking_reason: Optional[str]
    orchestration_continues: bool
