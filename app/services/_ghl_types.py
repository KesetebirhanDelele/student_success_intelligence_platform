"""
Contract types for the governance-safe GHL provider containment orchestration layer.
Not part of the public API. Consumed by ghl.py and _ghl_helpers.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Execution modes (provider-layer: SHADOW or LIVE per ghl_integration_contract.md §3.1) ──
MODE_LIVE         = "LIVE"
MODE_SHADOW       = "SHADOW"

# ── Governance scope values (ghl_integration_contract.md §4.2) ──────────────
SCOPE_AUTHORIZED           = "AUTHORIZED"
SCOPE_BLOCKED              = "BLOCKED"
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"

# ── Provider event types ─────────────────────────────────────────────────────
EVENT_OUTBOUND_TRIGGER       = "OUTBOUND_TRIGGER"
EVENT_SHADOW_SIMULATION      = "SHADOW_SIMULATION"
EVENT_REPLAY_SIMULATION      = "REPLAY_SIMULATION"
EVENT_DEDUPLICATION_SUPPRESS = "DEDUPLICATION_SUPPRESS"

# ── Circuit breaker states ───────────────────────────────────────────────────
CB_CLOSED    = "CLOSED"
CB_OPEN      = "OPEN"
CB_HALF_OPEN = "HALF_OPEN"
CB_UNKNOWN   = "UNKNOWN"

# ── Config V2 Group F provider threshold keys (ghl_integration_contract.md §6.1) ─
K_PROVIDER_MAX_RETRY = "provider_failure_max_retry_attempts"
K_CB_THRESHOLD       = "provider_failure_circuit_breaker_threshold"
K_CB_RESET_HOURS     = "provider_failure_circuit_breaker_reset_hours"
K_BACKOFF_BASE       = "provider_failure_retry_backoff_base_seconds"
K_DELIVERY_SLA       = "provider_delivery_sla_hours"
K_SYNC_MAX_AGE       = "sql_server_max_sync_age_hours"

_PROVIDER_THRESHOLD_KEYS = (
    K_PROVIDER_MAX_RETRY, K_CB_THRESHOLD, K_CB_RESET_HOURS,
    K_BACKOFF_BASE, K_DELIVERY_SLA, K_SYNC_MAX_AGE,
)

UNKNOWN_V0 = "UNKNOWN_V0"

# Required attribution fields for all provider interactions (§3.2)
REQUIRED_PROVIDER_ATTRIBUTION = (
    "origin_source", "origin_authority", "correlation_id", "actor_identity",
)

# Valid execution types for GHL provider context
_VALID_TYPES  = frozenset({"original", "replay", "regeneration"})
_REPLAY_TYPES = frozenset({"replay", "regeneration"})

# Valid execution modes at the provider boundary (SHADOW or LIVE only — §3.1)
_VALID_PROVIDER_MODES = frozenset({MODE_SHADOW, MODE_LIVE})


# ── Input context ────────────────────────────────────────────────────────────

@dataclass
class ProviderOrchestrationContext:
    """Governance context for a provider interaction evaluation."""

    # Governance §3.1
    config_version_id: Optional[str]
    execution_mode: str       # SHADOW | LIVE
    execution_type: str       # original | replay | regeneration
    config_rule_set: Optional[Dict[str, Any]] = None
    compliance_hold_active: bool = False
    idempotency_key: Optional[str] = None

    # Attribution §3.2 — set by platform; never accepted from external callers (AP-GHL15)
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    upstream_intent_id: Optional[str] = None
    actor_identity: Optional[str] = None

    # Provider §3.3
    provider_health_state: str = "UNKNOWN"
    circuit_breaker_state: str = CB_UNKNOWN
    ghl_message_id: Optional[str] = None
    retry_attempt_count: int = 0
    outbound_retry_budget_remaining: int = 0

    # Replay context
    historical_config_version_id: Optional[str] = None
    source_artifact_id: Optional[str] = None

    # Operational §3.5
    provider_outage_active: bool = False
    sync_lag_hours: float = 0.0
    delivery_telemetry_stale: bool = False

    # Student — opaque ID only; PII never logged (AP-GHL10)
    student_id_opaque: Optional[str] = None

    # Interaction path
    interaction_path: str = "outbound"   # outbound | inbound_webhook


# ── Output assessment ────────────────────────────────────────────────────────

@dataclass
class ProviderOrchestrationAssessment:
    """
    Governance assessment record for a provider interaction.
    Advisory contract — not an execution result. Consuming services act on this.
    """

    # Core governance
    provider_event_type: Optional[str]
    governance_scope: str

    # Replay restrictions
    is_replay: bool
    outbound_suppressed: bool
    historical_provider_context_only: bool
    historical_config_version_id: Optional[str]
    replay_provider_source: Optional[str]

    # Attribution — propagated immutably from input (AP-GHL15)
    origin_source: Optional[str]
    origin_authority: Optional[str]
    correlation_id: Optional[str]
    causation_id: Optional[str]
    upstream_intent_id: Optional[str]

    # Config lineage
    config_version_id: Optional[str]
    threshold_bindings: Dict[str, Any]

    # Provider lineage
    provider: str
    ghl_message_id: Optional[str]
    provider_error_class: Optional[str]

    # Degradation
    degraded: bool
    degradation_cause: Optional[str]
    outbound_blocked: bool
    orchestration_continues: bool

    # Observability
    event_id: str
    rule_path_taken: List[str]
    assessment_basis: str
    execution_type: str
    execution_mode: str
    duration_ms: int
    outcome: str

    # Result
    reason_codes: List[str]
    provider_blocked: bool
    blocking_reason: Optional[str]
