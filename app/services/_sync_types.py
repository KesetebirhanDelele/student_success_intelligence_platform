"""
Contract types for the governance-safe synchronization orchestration coordination layer.
Not part of the public API. Consumed by sync.py and _sync_helpers.py.
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
SCOPE_AUTHORIZED  = "AUTHORIZED"    # Phase-12 certification — currently unreachable
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_MAINTENANCE = "MAINTENANCE"

# ── Sync intent types ─────────────────────────────────────────────────────────
INTENT_INGEST_AUTHORITATIVE = "INGEST_AUTHORITATIVE"
INTENT_RECONCILE_CONFLICTS  = "RECONCILE_CONFLICTS"
INTENT_DEFER_STALE          = "DEFER_STALE"
INTENT_HOLD                 = "HOLD"

# ── Sync domains ──────────────────────────────────────────────────────────────
DOMAIN_TRIGGER_DATA   = "TRIGGER_DATA"
DOMAIN_INTERVIEW_PREP = "INTERVIEW_PREP"
DOMAIN_FULL           = "FULL"

_VALID_SYNC_DOMAINS = frozenset({DOMAIN_TRIGGER_DATA, DOMAIN_INTERVIEW_PREP, DOMAIN_FULL})

# ── Authority classifications ─────────────────────────────────────────────────
AUTHORITY_SQL_SERVER    = "sql_server_authoritative"
AUTHORITY_SUPPLEMENTARY = "platform_supplementary"
ORIGIN_MIRRORED_SQL     = "mirrored_sql_server"

# ── Outcome values ────────────────────────────────────────────────────────────
OUTCOME_SUCCESS     = "success"
OUTCOME_FAILURE     = "failure"
OUTCOME_DEGRADED    = "degraded"
OUTCOME_SHADOW_ONLY = "shadow_only"

# ── Circuit breaker states ────────────────────────────────────────────────────
CB_OPEN      = "OPEN"
CB_CLOSED    = "CLOSED"
CB_HALF_OPEN = "HALF_OPEN"
CB_UNKNOWN   = "UNKNOWN"

# ── Config V2 Group A / K sync threshold keys (spec/01 §12) ──────────────────
K_SYNC_BATCH_SIZE           = "sync_batch_size"
K_SQL_MAX_SYNC_AGE_HOURS    = "sql_server_max_sync_age_hours"
K_SYNC_MAX_RETRY_ATTEMPTS   = "sync_max_retry_attempts"
K_SYNC_CONFLICT_THRESHOLD   = "sync_conflict_threshold"
K_SYNC_LAG_ESCALATION_HOURS = "sync_lag_escalation_hours"

_SYNC_THRESHOLD_KEYS = (
    K_SYNC_BATCH_SIZE,
    K_SQL_MAX_SYNC_AGE_HOURS,
    K_SYNC_MAX_RETRY_ATTEMPTS,
    K_SYNC_CONFLICT_THRESHOLD,
    K_SYNC_LAG_ESCALATION_HOURS,
)

UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields (block RULE 0 if absent) ─────────────────────
REQUIRED_SYNC_ATTRIBUTION = ("origin_source", "origin_authority", "actor_identity")


# ── Input context ─────────────────────────────────────────────────────────────

@dataclass
class SyncOrchestrationContext:
    """Governance context for a synchronization orchestration coordination evaluation."""

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
    compliance_hold_flag: bool = False

    # Attribution — set by platform; never accepted from external callers
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    actor_identity: Optional[str] = None
    attribution_timestamp: Optional[str] = None
    upstream_correlation_id: Optional[str] = None

    # Sync domain and row metadata
    sync_domain: str = DOMAIN_TRIGGER_DATA
    rows_scanned: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0

    # Provider state
    sql_server_available: bool = True
    sync_lag_hours: float = 0.0
    circuit_breaker_state: str = CB_UNKNOWN

    # FINALIZED artifact detection (INV-1, INV-6, FAD-1)
    finalized_artifacts_detected: int = 0

    # Replay context
    historical_config_version_id: Optional[str] = None
    source_artifact_id: Optional[str] = None


# ── Output coordination record ────────────────────────────────────────────────

@dataclass
class SyncCoordinationRecord:
    """
    Governance coordination record for a synchronization orchestration evaluation.
    Advisory contract — not an execution result. Consuming services act on this.
    Never dispatches, never mutates state, never writes to SQL Server (FAD-5, ABG-1).
    """

    # Core governance
    governance_scope: str
    sync_intent: Optional[str]

    # Containment
    is_replay: bool
    live_effects_suppressed: bool

    # Attribution — propagated immutably from input (INV-5)
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    upstream_correlation_id: Optional[str]
    authoritative_source: str    # always AUTHORITY_SQL_SERVER for sync (ABG-1)

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

    # Sync lineage
    sync_domain: str
    rows_scanned: int
    rows_valid: int
    rows_invalid: int

    # Authorization
    dispatch_authorized: bool
    sync_blocked_reason: Optional[str]

    # Authoritative boundary enforcement (FAD-5, spec/05 §3.1)
    sql_server_read_only_enforced: bool    # always True — write attempt = ArchitecturalViolation
    conflict_preservation_required: bool   # True when conflicts must be logged with both values

    # FINALIZED immutability (INV-1, INV-6, FAD-1)
    finalized_artifacts_protected: bool
    finalized_artifacts_detected: int

    # Append-only lineage (FAD-4, INV per spec/08 §2)
    append_only_lineage_preserved: bool    # always True

    # Degradation
    degraded: bool
    degradation_flags: List[str]
    degradation_cause: Optional[str]

    # Result
    reason_codes: List[str]
    orchestration_blocked: bool
    blocking_reason: Optional[str]
    orchestration_continues: bool
