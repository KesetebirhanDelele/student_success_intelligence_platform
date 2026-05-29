"""
Governance-safe router layer type definitions.

Constants, DTOs, and governance codes for API request/response contracts.

Governance alignment:
  CID-1  — correlation_id propagated from every request
  IML-1  — attribution fields immutably propagated into response meta
  INV-5  — no response without correlation_id in meta
  AP-RT13 — PII excluded from meta fields
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Request/response header constants ─────────────────────────────────────────
GOVERNANCE_CORRELATION_HEADER = "X-Correlation-ID"
GOVERNANCE_CAUSATION_HEADER = "X-Causation-ID"
GOVERNANCE_EXECUTION_TYPE_HEADER = "X-Execution-Type"

# ── SHADOW suppression visibility codes ───────────────────────────────────────
SUPPRESSION_SHADOW_MODE = "SHADOW_MODE_ACTIVE"
SUPPRESSION_LIVE_EFFECTS_DISABLED = "LIVE_EFFECTS_SUPPRESSED"

# ── FINALIZED protection classification codes (FAD-1) ─────────────────────────
FINALIZED_READ_ONLY = "FINALIZED_READ_ONLY"
FINALIZED_ACTIVE = "ACTIVE"

# ── Replay classification codes (RSV-1) ───────────────────────────────────────
REPLAY_SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
REPLAY_EXECUTION_TYPES = frozenset({"replay", "regeneration"})

# ── Attribution completeness gate (INV-5, CID-1) ─────────────────────────────
REQUIRED_ROUTER_ATTRIBUTION = ("correlation_id", "execution_mode", "governance_scope")

# ── Governance scope constants ────────────────────────────────────────────────
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_LIVE_AUTHORIZED = "LIVE_AUTHORIZED"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"


@dataclass
class GovernanceMeta:
    """
    Governance metadata for API response envelopes (CID-1, IML-1, INV-5).

    Propagated immutably from request attribution to every governed response.
    Never contains PII fields (AP-RT13): no email, phone, student name.

    suppression_codes enumerates all active live-effect suppressions so
    callers can reason about why effects were not applied (SHADOW visibility).
    """
    correlation_id: str
    execution_mode: str
    governance_scope: str
    timestamp: str
    causation_id: Optional[str] = None
    config_version_id: Optional[str] = None
    execution_type: str = "original"
    is_replay: bool = False
    attribution_complete: bool = False
    suppression_codes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "config_version_id": self.config_version_id,
            "execution_mode": self.execution_mode,
            "execution_type": self.execution_type,
            "governance_scope": self.governance_scope,
            "is_replay": self.is_replay,
            "attribution_complete": self.attribution_complete,
            "suppression_codes": self.suppression_codes,
            "timestamp": self.timestamp,
        }
