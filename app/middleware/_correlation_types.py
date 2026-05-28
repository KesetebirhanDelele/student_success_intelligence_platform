"""
Governance-safe attribution continuity middleware contract types.
Constants, types, and dataclasses. Consumed by _correlation_helpers.py and correlation.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Execution modes (runtime/system_loop.md §3.1) ────────────────────────────
MODE_LIVE = "LIVE"
MODE_SHADOW = "SHADOW"
MODE_REPLAY = "REPLAY"
MODE_REGENERATION = "REGENERATION"
MODE_DEGRADED = "DEGRADED"
MODE_MAINTENANCE = "MAINTENANCE"

# ── Execution types (spec/06 §3.8, runtime/system_loop.md §4.8) ──────────────
TYPE_ORIGINAL = "original"
TYPE_REPLAY = "replay"
TYPE_REGENERATION = "regeneration"
TYPE_RECOVERY = "recovery"

# ── Governance scopes ─────────────────────────────────────────────────────────
SCOPE_AUTHORIZED = "AUTHORIZED"       # Phase-12 cert required — unreachable
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_MAINTENANCE = "MAINTENANCE"

# ── Attribution outcomes ──────────────────────────────────────────────────────
OUTCOME_PROPAGATED = "propagated"
OUTCOME_BLOCKED = "blocked"

# ── HTTP header names (Starlette does case-insensitive lookup) ────────────────
HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_CAUSATION_ID = "X-Causation-ID"
HEADER_EXECUTION_MODE = "X-Execution-Mode"
HEADER_EXECUTION_TYPE = "X-Execution-Type"
HEADER_CONFIG_VERSION_ID = "X-Config-Version-ID"
HEADER_ORCHESTRATION_CYCLE_ID = "X-Orchestration-Cycle-ID"
HEADER_ORIGIN_SOURCE = "X-Origin-Source"
HEADER_ORIGIN_AUTHORITY = "X-Origin-Authority"
HEADER_HISTORICAL_CONFIG_VERSION_ID = "X-Historical-Config-Version-ID"
HEADER_ATTRIBUTION_TIMESTAMP = "X-Attribution-Timestamp"
HEADER_GOVERNANCE_SCOPE = "X-Governance-Scope"

# ── Validation frozensets ─────────────────────────────────────────────────────
_VALID_EXECUTION_MODES: frozenset = frozenset({
    MODE_LIVE, MODE_SHADOW, MODE_REPLAY,
    MODE_REGENERATION, MODE_DEGRADED, MODE_MAINTENANCE,
})
_VALID_EXECUTION_TYPES: frozenset = frozenset({
    TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION, TYPE_RECOVERY,
})
_REPLAY_EXECUTION_TYPES: frozenset = frozenset({TYPE_REPLAY, TYPE_REGENERATION})
_REPLAY_MODES: frozenset = frozenset({MODE_REPLAY, MODE_REGENERATION})

# ── Governance blocking codes ─────────────────────────────────────────────────
CODE_INVALID_EXECUTION_MODE = "INVALID_EXECUTION_MODE"
CODE_INVALID_EXECUTION_TYPE = "INVALID_EXECUTION_TYPE"
CODE_REPLAY_LINEAGE_INCOMPLETE = "REPLAY_LINEAGE_INCOMPLETE"
CODE_ATTRIBUTION_PARTIAL = "ATTRIBUTION_PARTIAL"

# ── Required attribution fields (spec/06 §2.2) ───────────────────────────────
REQUIRED_ATTRIBUTION_PAIR = (HEADER_ORIGIN_SOURCE, HEADER_ORIGIN_AUTHORITY)


@dataclass
class AttributionContext:
    """Resolved attribution context propagated to request.state.attribution."""
    correlation_id: str
    causation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str
    governance_scope: str
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    historical_config_version_id: Optional[str]
    attribution_timestamp: Optional[str]
    correlation_id_generated: bool        # True = server-generated; False = from header
    is_replay: bool                        # execution_type in _REPLAY_EXECUTION_TYPES
    attribution_complete: bool             # origin_source and origin_authority both present
    live_effects_suppressed: bool          # True unless governance_scope == SCOPE_AUTHORIZED
    rule_path_taken: List[str] = field(default_factory=list)


@dataclass
class PropagationRecord:
    """Structured observability record emitted on every attribution propagation path."""
    propagation_id: str
    timestamp: str
    event: str
    correlation_id: str
    causation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str
    governance_scope: str
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    historical_config_version_id: Optional[str]
    attribution_timestamp: Optional[str]
    correlation_id_generated: bool
    is_replay: bool
    attribution_complete: bool
    live_effects_suppressed: bool
    blocked: bool
    blocking_codes: List[str]
    blocking_reason: Optional[str]
    path: str
    method: str
    outcome: str
    duration_ms: Optional[int]
    rule_path_taken: List[str]
