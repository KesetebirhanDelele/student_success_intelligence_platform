"""
Contract types for the governance-safe worker orchestration execution layer.
Not part of the public API. Consumed by worker.py and _worker_helpers.py.
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

# ── Governance scopes (aligned with outreach and GHL layers) ──────────────────
SCOPE_AUTHORIZED           = "AUTHORIZED"    # requires Phase-12 cert — currently unreachable
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"
SCOPE_MAINTENANCE          = "MAINTENANCE"
SCOPE_BLOCKED              = "BLOCKED"
SCOPE_DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"

# Worker scopes that suppress outbound delegation (AP-RT1, AP-RT2)
_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE,
    SCOPE_DUPLICATE_SUPPRESSED,
})

# ── Worker outcomes ───────────────────────────────────────────────────────────
OUTCOME_DISPATCH_DELEGATED = "dispatch_delegated"
OUTCOME_SUPPRESSED         = "suppressed"
OUTCOME_BLOCKED            = "blocked"
OUTCOME_EXECUTION_ERROR    = "execution_error"

# ── Channels ──────────────────────────────────────────────────────────────────
CHANNEL_GHL   = "ghl"
CHANNEL_CALL  = "call"
CHANNEL_SMS   = "sms"
CHANNEL_EMAIL = "email"

# ── Config V2 sentinel ────────────────────────────────────────────────────────
UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields for worker Rule 0 gate ───────────────────────
REQUIRED_WORKER_ATTRIBUTION = (
    "origin_source",
    "origin_authority",
    "correlation_id",
    "actor_identity",
)

# ── Intent-to-channel mapping (deterministic; no silent defaults) ─────────────
INTENT_CHANNEL_MAP: Dict[str, str] = {
    "INITIATE_OUTREACH": CHANNEL_CALL,
    "RETRY_OUTREACH":    CHANNEL_SMS,
    "ESCALATE":          CHANNEL_EMAIL,
    "CLOSE":             CHANNEL_GHL,
    "DEFER_PENDING_AI":  CHANNEL_GHL,
    "HOLD":              CHANNEL_GHL,
}
DEFAULT_DISPATCH_CHANNEL = CHANNEL_CALL


# ── Input context ─────────────────────────────────────────────────────────────

@dataclass
class WorkerJobContext:
    """
    Governance context for a worker execution job.
    Built from OutreachCoordinationRecord + student envelope + attempt.
    Opaque student ID only — PII never held here (AP-RT13).
    """

    # Governance — from OutreachCoordinationRecord
    governance_scope: str
    intent_type: Optional[str]
    is_replay: bool
    live_effects_suppressed: bool
    dispatch_authorized: bool
    dispatch_blocked_reason: Optional[str]

    # Attribution — propagated immutably (AP-RT4, AP-DF5)
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]

    # Config lineage
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str
    threshold_bindings: Dict[str, Any] = field(default_factory=dict)

    # Idempotency
    idempotency_key: Optional[str] = None

    # Student context — opaque only (AP-RT13)
    student_id_opaque: Optional[str] = None
    checkpoint_type: Optional[str] = None
    contact_attempt: int = 0

    # Provider context
    provider_health_state: str = "UNKNOWN"
    circuit_breaker_state: str = "UNKNOWN"

    # Degradation
    degraded: bool = False
    degradation_cause: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)

    # Compliance
    compliance_hold_active: bool = False

    # Worker job identity
    job_id: str = ""


# ── Output execution record ───────────────────────────────────────────────────

@dataclass
class WorkerExecutionRecord:
    """
    Worker execution coordination record.
    Advisory contract — records what the worker decided, not what it sent.
    Consuming services act on this; the worker never mutates state (AP-RT1, AP-DF1).
    Attribution propagated immutably from input (AP-RT4, AP-DF5, AP-RF6).
    """

    # Job identity
    job_id: str

    # Core governance
    governance_scope: str
    outcome: str

    # Attribution — propagated from WorkerJobContext (AP-RT4)
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]

    # Config lineage
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str

    # Worker decision
    intent_type: Optional[str]
    dispatch_delegated: bool
    dispatch_outcome: Optional[str]
    channel: Optional[str]

    # Suppression state
    outbound_suppressed: bool
    suppression_reason: Optional[str]

    # Degradation
    degraded: bool
    degradation_cause: Optional[str]

    # Student lineage — opaque only (AP-RT13)
    student_id_opaque: Optional[str]
    checkpoint_type: Optional[str]
    contact_attempt: int

    # Observability
    event_id: str
    rule_path_taken: List[str]
    duration_ms: int
    reason_codes: List[str]
    error_class: Optional[str]

    # Execution blocked
    execution_blocked: bool
    blocking_reason: Optional[str]
