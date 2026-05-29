"""
Runtime bootstrap governance contract types.

Constants, invariants, and dataclasses for startup governance classification.

Governance alignment:
  SHADOW-safe default — system never starts in unrestricted LIVE scope
  Config V2 UNKNOWN_V0 safety semantics — degradation is explicit, never silent
  Replay-safe initialization — REPLAY scope never leaks into LIVE paths
  Attribution continuity — startup context carries full attribution fields
  AP-RT13 — as_log_dict() contains no PII fields
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Execution modes (runtime/system_loop.md §3.1) ────────────────────────────
BOOTSTRAP_MODE_SHADOW       = "SHADOW"
BOOTSTRAP_MODE_LIVE         = "LIVE"
BOOTSTRAP_MODE_REPLAY       = "REPLAY"
BOOTSTRAP_MODE_REGENERATION = "REGENERATION"
BOOTSTRAP_MODE_DEGRADED     = "DEGRADED"
BOOTSTRAP_MODE_MAINTENANCE  = "MAINTENANCE"

_VALID_BOOTSTRAP_MODES: frozenset = frozenset({
    BOOTSTRAP_MODE_SHADOW, BOOTSTRAP_MODE_LIVE, BOOTSTRAP_MODE_REPLAY,
    BOOTSTRAP_MODE_REGENERATION, BOOTSTRAP_MODE_DEGRADED, BOOTSTRAP_MODE_MAINTENANCE,
})

_REPLAY_BOOTSTRAP_MODES: frozenset = frozenset({
    BOOTSTRAP_MODE_REPLAY, BOOTSTRAP_MODE_REGENERATION,
})

# ── Governance scopes (derived; AUTHORIZED is unreachable — Phase-12 cert) ───
SCOPE_SHADOW_ONLY  = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY  = "REPLAY_ONLY"
SCOPE_MAINTENANCE  = "MAINTENANCE"
SCOPE_DEGRADED     = "DEGRADED"

# ── Startup classification outcomes ──────────────────────────────────────────
STARTUP_CLASS_SHADOW_SAFE   = "SHADOW_SAFE"
STARTUP_CLASS_DEGRADED      = "DEGRADED"
STARTUP_CLASS_REPLAY_SAFE   = "REPLAY_SAFE"
STARTUP_CLASS_MAINTENANCE   = "MAINTENANCE"

# ── Degradation codes (emitted in startup log and RuntimeBootstrapContext) ───
DEGRADE_CONFIG_V2_UNAVAILABLE       = "CONFIG_V2_UNAVAILABLE"
DEGRADE_CONFIG_V2_NO_ACTIVE         = "CONFIG_V2_NO_ACTIVE_VERSION"
DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE   = "CONFIG_V2_MULTIPLE_ACTIVE_VERSIONS"
DEGRADE_EXECUTION_MODE_INVALID      = "EXECUTION_MODE_INVALID"
DEGRADE_ATTRIBUTION_INCOMPLETE      = "ATTRIBUTION_INCOMPLETE"

# ── Config V2 sentinel — emitted when no ACTIVE config version exists ─────────
UNKNOWN_V0 = "UNKNOWN_V0"

# ── Required attribution fields for bootstrap completeness assessment ─────────
REQUIRED_BOOTSTRAP_ATTRIBUTION = (
    "origin_source",
    "origin_authority",
    "attribution_timestamp",
)


@dataclass
class RuntimeBootstrapContext:
    """
    Immutable governance-safe runtime bootstrap context.

    Produced once at startup by initialize_runtime_context().
    Consumed by: main.py startup handler, scheduler configuration.
    Never mutated after construction.

    Governance guarantees:
    - shadow_containment_active is always True (AUTHORIZED scope unreachable)
    - live_effects_suppressed is always True (AUTHORIZED scope unreachable)
    - replay_safe is always True (governance_scope derivation enforces it)
    - degradation_state is explicit — no silent fallback
    - as_log_dict() contains no PII (AP-RT13)
    """
    startup_correlation_id: str
    execution_mode: str
    governance_scope: str
    startup_classification: str
    config_version_id: str           # UNKNOWN_V0 when Config V2 unavailable
    shadow_containment_active: bool  # True unless AUTHORIZED (unreachable)
    live_effects_suppressed: bool    # True unless AUTHORIZED (unreachable)
    replay_safe: bool                # Always True — scope derivation enforces
    attribution_complete: bool
    degradation_state: bool
    degradation_codes: List[str]
    startup_timestamp: str
    scheduler_timing: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_shadow(self) -> bool:
        return self.execution_mode == BOOTSTRAP_MODE_SHADOW

    @property
    def is_replay(self) -> bool:
        return self.execution_mode in _REPLAY_BOOTSTRAP_MODES

    @property
    def is_maintenance(self) -> bool:
        return self.execution_mode == BOOTSTRAP_MODE_MAINTENANCE

    @property
    def is_degraded(self) -> bool:
        return self.degradation_state

    def as_log_dict(self) -> Dict[str, Any]:
        """
        Structured startup log payload — no PII (AP-RT13).
        Contains only governance classification fields.
        """
        return {
            "startup_correlation_id": self.startup_correlation_id,
            "execution_mode": self.execution_mode,
            "governance_scope": self.governance_scope,
            "startup_classification": self.startup_classification,
            "config_version_id": self.config_version_id,
            "shadow_containment_active": self.shadow_containment_active,
            "live_effects_suppressed": self.live_effects_suppressed,
            "replay_safe": self.replay_safe,
            "attribution_complete": self.attribution_complete,
            "degradation_state": self.degradation_state,
            "degradation_codes": self.degradation_codes,
            "startup_timestamp": self.startup_timestamp,
        }
