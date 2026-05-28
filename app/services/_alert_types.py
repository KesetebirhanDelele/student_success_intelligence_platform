"""
Contract types for the governance-safe degradation observability classification layer.
Not part of the public API. Consumed by alerts.py and _alert_helpers.py.
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

# ── Severity levels (spec/06 §10.1) ───────────────────────────────────────────
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH     = "HIGH"
SEVERITY_MEDIUM   = "MEDIUM"
SEVERITY_LOW      = "LOW"
SEVERITY_INFO     = "INFO"
SEVERITY_UNKNOWN  = "UNKNOWN"

_SEVERITY_LEVELS = (SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO)

# ── Degradation domains (failure_playbook.md §2, spec/06 §10) ─────────────────
DOMAIN_ORCHESTRATION   = "orchestration"
DOMAIN_PROVIDER        = "provider"
DOMAIN_AI              = "ai"
DOMAIN_SCHEDULER       = "scheduler"
DOMAIN_SYNCHRONIZATION = "synchronization"
DOMAIN_REPLAY          = "replay"
DOMAIN_ATTRIBUTION     = "attribution"
DOMAIN_OBSERVABILITY   = "observability"
DOMAIN_COMPLIANCE      = "compliance"
DOMAIN_FINGERPRINT     = "fingerprint"
DOMAIN_UNKNOWN         = "unknown"

_VALID_ALERT_DOMAINS = frozenset({
    DOMAIN_ORCHESTRATION, DOMAIN_PROVIDER, DOMAIN_AI, DOMAIN_SCHEDULER,
    DOMAIN_SYNCHRONIZATION, DOMAIN_REPLAY, DOMAIN_ATTRIBUTION,
    DOMAIN_OBSERVABILITY, DOMAIN_COMPLIANCE, DOMAIN_FINGERPRINT,
})

# ── Recovery actions (failure_playbook.md §7.1, §11.1) ────────────────────────
ACTION_GOVERNED_RECOVERY     = "governed_recovery_cycle"
ACTION_DEAD_LETTER           = "dead_letter"
ACTION_DEGRADED_CONTINUATION = "degraded_continuation"
ACTION_ESCALATION_CANDIDACY  = "escalation_candidacy"
ACTION_NO_OP                 = "no_op"
ACTION_UNKNOWN               = "unknown"

# ── Assessment basis ───────────────────────────────────────────────────────────
BASIS_RULE_BASED       = "RULE_BASED"
BASIS_CONFIG_GOVERNED  = "CONFIG_V2_GOVERNED"
BASIS_FALLBACK         = "FALLBACK"
BASIS_HISTORICAL_REPLAY = "HISTORICAL_REPLAY"

# ── Outcome values ─────────────────────────────────────────────────────────────
OUTCOME_SUCCESS     = "success"
OUTCOME_FAILURE     = "failure"
OUTCOME_DEGRADED    = "degraded"
OUTCOME_SHADOW_ONLY = "shadow_only"

# ── Config V2 alert threshold keys (spec/06 §10, failure_playbook.md §7.2) ────
K_SCHEDULER_HEARTBEAT_MS      = "scheduler_heartbeat_interval_ms"
K_SYNC_STALE_HOURS            = "sql_server_max_sync_age_hours"
K_AI_STALE_HIGH_HOURS         = "ai_stale_high_threshold_hours"
K_AI_ABSENT_CRITICAL_HOURS    = "ai_absent_critical_threshold_hours"
K_STUCK_WORKFLOW_HIGH_HOURS   = "stuck_workflow_high_threshold_hours"
K_STUCK_COMPLIANCE_HIGH_HOURS = "stuck_compliance_threshold_hours"
K_PROVIDER_RETRY_LIMIT        = "provider_failure_max_retry_attempts"
K_SLA_REPORT_MS               = "report_generation_sla_ms"

_ALERT_THRESHOLD_KEYS = (
    K_SCHEDULER_HEARTBEAT_MS,
    K_SYNC_STALE_HOURS,
    K_AI_STALE_HIGH_HOURS,
    K_AI_ABSENT_CRITICAL_HOURS,
    K_STUCK_WORKFLOW_HIGH_HOURS,
    K_STUCK_COMPLIANCE_HIGH_HOURS,
    K_PROVIDER_RETRY_LIMIT,
    K_SLA_REPORT_MS,
)

UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields (block RULE 0 if absent) ──────────────────────
REQUIRED_ALERT_ATTRIBUTION = ("origin_source", "origin_authority", "actor_identity")


# ── Input context ──────────────────────────────────────────────────────────────

@dataclass
class AlertClassificationContext:
    """Governance context for a degradation alert classification evaluation."""

    # Governance — mandatory
    config_version_id: Optional[str]
    execution_mode: str   # SHADOW | LIVE
    execution_type: str   # original | replay | regeneration | recovery
    correlation_id: Optional[str]

    # Degradation condition
    degradation_domain: Optional[str]
    failure_cause: Optional[str]
    error_class: Optional[str]

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

    # Degradation signals (for severity classification)
    scheduler_lag_ms: Optional[int] = None
    sync_lag_hours: Optional[float] = None
    ai_stale_hours: Optional[float] = None
    ai_absent_hours: Optional[float] = None
    retry_count: Optional[int] = None
    circuit_breaker_open: bool = False
    provider_outage_active: bool = False
    compliance_hold_active: bool = False
    fingerprint_divergence: bool = False
    workflow_stuck_hours: Optional[float] = None
    is_observability_degraded: bool = False

    # Replay/regeneration context
    source_artifact_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None

    # State lineage
    execution_state_before: Optional[str] = None
    execution_state_after: Optional[str] = None

    # Opaque student identifier — never raw PII (AP-FP13, spec/06 §12.1)
    student_id_opaque: Optional[str] = None


# ── Output record ──────────────────────────────────────────────────────────────

@dataclass
class DegradationAlertRecord:
    """
    Governance-safe degradation alert classification record.
    Advisory contract only — classifies and emits; never executes remediation,
    never dispatches operations, never mutates orchestration state (AP-FP1, AP-FP4).
    Attribution propagated immutably from input.
    """

    # Classification outputs
    severity: str              # CRITICAL | HIGH | MEDIUM | LOW | INFO | UNKNOWN
    degradation_domain: str
    failure_cause: Optional[str]
    error_class_classified: Optional[str]
    recovery_action: str
    escalation_candidacy: bool

    # Governance
    governance_scope: str
    assessment_basis: str

    # Containment
    is_replay: bool
    live_effects_suppressed: bool

    # Attribution — propagated immutably (AP-FP6, spec/06 §1.3)
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
    alert_id: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    execution_type: str
    execution_mode: str
    rule_path_taken: List[str]
    duration_ms: int
    outcome: str

    # Degradation detail
    degraded: bool
    degradation_flags: List[str]
    degradation_cause: Optional[str]

    # Result
    reason_codes: List[str]
    orchestration_blocked: bool
    blocking_reason: Optional[str]
    orchestration_continues: bool

    # Suppression visibility — always True; suppression is never silent (AP-FP4)
    suppression_visible: bool

    # State lineage
    execution_state_before: Optional[str]
    execution_state_after: Optional[str]
    causation_chain_preserved: bool

    # Invariant fields — always True (FAD-4, IML-1, IML-3)
    append_only_enforced: bool      # always True — FAD-4; alert lineage never overwritten
    replay_lineage_preserved: bool  # always True — IML-3; replay alerts distinguishable from LIVE
    alert_lineage_immutable: bool   # always True — IML-1; historical alert records never mutated

    # Authorization (Phase-12 cert gate)
    alert_emit_authorized: bool     # False until Phase-12 cert

    # Opaque student identifier — never raw PII
    student_id_opaque: Optional[str]
