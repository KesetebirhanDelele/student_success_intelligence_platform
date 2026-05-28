"""
Governance-safe repository persistence contract types.
Constants, types, and dataclasses. Consumed by _repository_helpers.py and repository.py.

Governance invariants enforced at persistence layer:
  FAD-4   — append-only audit/lineage tables; no UPDATE or DELETE
  FAD-1   — no mutation of FINALIZED warehouse/AI artifact records
  IML-1   — attribution immutability; persisted attribution never overwritten
  IML-3   — replay lineage preserved; historical_config_version_id carried on replay rows
  AOWG-1  — no sync path produces warehouse INSERT/UPDATE/DELETE outside repository
  INV-1   — no mutation of FINALIZED warehouse records
  INV-4   — no LIVE severity classification from replay execution paths
  INV-5   — no governance record without correlation_id and attribution
  CID-1   — correlation continuity; correlation_id propagated on every persisted record
  RSV-1   — replay persistence distinguishable and queryable from LIVE persistence
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Execution modes ───────────────────────────────────────────────────────────
MODE_LIVE = "LIVE"
MODE_SHADOW = "SHADOW"
MODE_REPLAY = "REPLAY"
MODE_REGENERATION = "REGENERATION"
MODE_DEGRADED = "DEGRADED"
MODE_MAINTENANCE = "MAINTENANCE"

# ── Execution types ───────────────────────────────────────────────────────────
TYPE_ORIGINAL = "original"
TYPE_REPLAY = "replay"
TYPE_REGENERATION = "regeneration"
TYPE_RECOVERY = "recovery"

# ── Governance scopes ─────────────────────────────────────────────────────────
SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY = "REPLAY_ONLY"
SCOPE_MAINTENANCE = "MAINTENANCE"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_AUTHORIZED = "AUTHORIZED"  # Phase-12 cert — unreachable

# ── Persistence classification ────────────────────────────────────────────────
PERSIST_CLASS_APPEND_ONLY = "append_only"           # outreach_history, state_transition_log
PERSIST_CLASS_MUTABLE_OPERATIONAL = "mutable_operational"  # student_outreach_tracking
PERSIST_CLASS_FINALIZED_ARTIFACT = "finalized_artifact"    # ai_insights (is_finalized=True)
PERSIST_CLASS_IDEMPOTENCY_STORE = "idempotency_store"      # processed_events

# ── Persistence outcomes ──────────────────────────────────────────────────────
PERSIST_OUTCOME_SUCCESS = "success"
PERSIST_OUTCOME_BLOCKED = "blocked"
PERSIST_OUTCOME_DUPLICATE_REJECTED = "duplicate_rejected"
PERSIST_OUTCOME_FINALIZED_PROTECTED = "finalized_protected"
PERSIST_OUTCOME_DEGRADED = "degraded"

# ── Governance blocking codes ─────────────────────────────────────────────────
CODE_FINALIZED_MUTATION_BLOCKED = "FINALIZED_MUTATION_BLOCKED"
CODE_REPLAY_LIVE_OVERWRITE_BLOCKED = "REPLAY_LIVE_OVERWRITE_BLOCKED"
CODE_ATTRIBUTION_INCOMPLETE = "ATTRIBUTION_INCOMPLETE"
CODE_IDEMPOTENCY_DUPLICATE = "IDEMPOTENCY_DUPLICATE"
CODE_CORRELATION_ID_MISSING = "CORRELATION_ID_MISSING"
CODE_EXECUTION_MODE_MISSING = "EXECUTION_MODE_MISSING"
CODE_EXECUTION_TYPE_MISSING = "EXECUTION_TYPE_MISSING"
CODE_GOVERNANCE_SCOPE_MISSING = "GOVERNANCE_SCOPE_MISSING"
CODE_INVALID_EXECUTION_MODE = "INVALID_EXECUTION_MODE"
CODE_INVALID_EXECUTION_TYPE = "INVALID_EXECUTION_TYPE"

# ── Validation frozensets ─────────────────────────────────────────────────────
_VALID_EXECUTION_MODES: frozenset = frozenset({
    MODE_LIVE, MODE_SHADOW, MODE_REPLAY,
    MODE_REGENERATION, MODE_DEGRADED, MODE_MAINTENANCE,
})
_VALID_EXECUTION_TYPES: frozenset = frozenset({
    TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION, TYPE_RECOVERY,
})
_REPLAY_EXECUTION_TYPES: frozenset = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

# ── Required attribution minimum for governance-safe persistence ──────────────
# All four fields must be non-empty for attribution_complete=True (INV-5, CID-1)
REQUIRED_PERSISTENCE_ATTRIBUTION: tuple = (
    "correlation_id", "execution_mode", "execution_type", "governance_scope",
)


@dataclass
class AttributionFields:
    """
    Attribution fields required on all governance-safe persistence operations.
    Propagated immutably from middleware/service layer to repository layer.
    """
    correlation_id: str
    execution_mode: str
    execution_type: str
    governance_scope: str
    causation_id: Optional[str] = None
    config_version_id: Optional[str] = None
    orchestration_cycle_id: Optional[str] = None
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    historical_config_version_id: Optional[str] = None
    is_replay: bool = False
    attribution_complete: bool = False


@dataclass
class PersistenceRecord:
    """
    Structured observability record emitted on every persistence path.
    Blocked, success, duplicate-rejected, and finalized-protected paths all emit.
    PII never logged (no student email/phone — AP-RT13).
    """
    persistence_id: str
    timestamp: str
    event: str
    table_name: str
    persistence_class: str
    correlation_id: str
    causation_id: Optional[str]
    execution_mode: str
    execution_type: str
    governance_scope: str
    is_replay: bool
    attribution_complete: bool
    outcome: str
    blocked: bool
    blocking_codes: List[str]
    blocking_reason: Optional[str]
    record_id: Optional[int]
    idempotency_key: Optional[str]
    duration_ms: Optional[int]
    rule_path_taken: List[str] = field(default_factory=list)
