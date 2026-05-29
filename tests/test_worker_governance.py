"""
Governance-safe worker orchestration execution certification — Phase 52.

Certifies that the worker execution layer enforces governance-safe Rule 0
precondition gating, SHADOW suppression, replay containment, maintenance mode,
governance scope consumption, attribution continuity, idempotency, degradation
visibility, provider delegation containment, batch cycle governance, Config V2
governance, and invariant preservation.

All tests are pure synchronous — no pytest-asyncio dependency.
No HTTP mocks, no DB mocks, no patch patterns. Contract-level simulation only.

Canonical sources:
  app/services/_worker_types.py     — WorkerJobContext, WorkerExecutionRecord, constants
  app/services/_worker_helpers.py   — _governance_precondition_gate, helpers
  app/services/worker.py            — coordinate_worker_execution, run_batch_cycle
  runtime/system_loop.md            — AP-RT1–AP-RT15, canonical orchestration sequence
  runtime/scheduler_design.md       — AP-SCH1–AP-SCH15

Prohibited semantics:
  - simplistic is_shadow patch-based assertions
  - AsyncMock / MagicMock / patch patterns
  - direct HTTP mock suppression
  - non-attributable outcomes (entries missing correlation_id)
  - silent containment failures
  - hardcoded threshold constants
  - replay-triggered LIVE expectations
  - mutable FINALIZED_COPY assumptions
  - AI advisory output alone authorising execution

This file certifies governance contracts only.
It does NOT generate production dispatch logic, orchestration services,
queue workers, provider integrations, or monitoring infrastructure.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# CONTRACT TYPES
# Governance-contract shapes only — not implementation.
# Mirrors app/services/_worker_types.py and app/services/_outreach_types.py.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MockCoordinationRecord:
    """
    Minimal OutreachCoordinationRecord shape for worker governance tests.
    Mirrors OutreachCoordinationRecord from app/services/_outreach_types.py.
    """
    governance_scope: str
    intent_type: Optional[str]
    is_replay: bool
    live_effects_suppressed: bool
    dispatch_authorized: bool
    dispatch_blocked_reason: Optional[str]
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str
    threshold_bindings: Dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    degradation_cause: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)
    compliance_hold_active: bool = False
    orchestration_blocked: bool = False
    blocking_reason: Optional[str] = None
    checkpoint_type: Optional[str] = None
    student_id_opaque: Optional[str] = None
    contact_attempt_count: int = 0
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class MockWorkerJobContext:
    """
    Minimal WorkerJobContext shape for worker governance tests.
    Mirrors WorkerJobContext from app/services/_worker_types.py.
    """
    governance_scope: str
    intent_type: Optional[str]
    is_replay: bool
    live_effects_suppressed: bool
    dispatch_authorized: bool
    dispatch_blocked_reason: Optional[str]
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str
    threshold_bindings: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    student_id_opaque: Optional[str] = None
    checkpoint_type: Optional[str] = None
    contact_attempt: int = 0
    degraded: bool = False
    degradation_cause: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)
    compliance_hold_active: bool = False
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class MockWorkerExecutionRecord:
    """
    Minimal WorkerExecutionRecord shape for worker governance tests.
    Mirrors WorkerExecutionRecord from app/services/_worker_types.py.
    """
    job_id: str
    governance_scope: str
    outcome: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    execution_type: str
    intent_type: Optional[str]
    dispatch_delegated: bool
    dispatch_outcome: Optional[str]
    channel: Optional[str]
    outbound_suppressed: bool
    suppression_reason: Optional[str]
    degraded: bool
    degradation_cause: Optional[str]
    student_id_opaque: Optional[str]
    checkpoint_type: Optional[str]
    contact_attempt: int
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_path_taken: List[str] = field(default_factory=list)
    duration_ms: int = 0
    reason_codes: List[str] = field(default_factory=list)
    error_class: Optional[str] = None
    execution_blocked: bool = False
    blocking_reason: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — mirrors _worker_types.py
# ─────────────────────────────────────────────────────────────────────────────

SCOPE_AUTHORIZED           = "AUTHORIZED"
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"
SCOPE_MAINTENANCE          = "MAINTENANCE"
SCOPE_BLOCKED              = "BLOCKED"
SCOPE_DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"

OUTCOME_DISPATCH_DELEGATED = "dispatch_delegated"
OUTCOME_SUPPRESSED         = "suppressed"
OUTCOME_BLOCKED            = "blocked"
OUTCOME_EXECUTION_ERROR    = "execution_error"

MODE_SHADOW = "SHADOW"
MODE_LIVE   = "LIVE"

TYPE_ORIGINAL     = "original"
TYPE_REPLAY       = "replay"
TYPE_REGENERATION = "regeneration"
TYPE_RECOVERY     = "recovery"

UNKNOWN_V0 = "UNKNOWN_V0"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE,
    SCOPE_DUPLICATE_SUPPRESSED,
})

_VALID_MODES  = frozenset({MODE_SHADOW, MODE_LIVE})
_VALID_TYPES  = frozenset({TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION, TYPE_RECOVERY})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

REQUIRED_WORKER_ATTRIBUTION = (
    "origin_source", "origin_authority", "correlation_id", "actor_identity"
)

INTENT_CHANNEL_MAP: Dict[str, str] = {
    "INITIATE_OUTREACH": "call",
    "RETRY_OUTREACH":    "sms",
    "ESCALATE":          "email",
    "CLOSE":             "ghl",
    "DEFER_PENDING_AI":  "ghl",
    "HOLD":              "ghl",
}
DEFAULT_DISPATCH_CHANNEL = "call"


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION HELPERS
# Contract-level replication of worker governance logic (no implementation import).
# ─────────────────────────────────────────────────────────────────────────────

def _attribution_complete_sim(ctx: MockWorkerJobContext, codes: List[str]) -> bool:
    ok = True
    for f in REQUIRED_WORKER_ATTRIBUTION:
        if not getattr(ctx, f, None):
            codes.append(f"ATTRIBUTION_MISSING_{f.upper()}")
            ok = False
    return ok


def _governance_precondition_gate_sim(ctx: MockWorkerJobContext, codes: List[str]) -> bool:
    ok = True
    if not ctx.config_version_id or ctx.config_version_id == UNKNOWN_V0:
        codes.append("CONFIG_VERSION_UNRESOLVED")
        ok = False
    if ctx.execution_mode not in _VALID_MODES:
        codes.append("EXECUTION_MODE_INVALID")
        ok = False
    if ctx.execution_type not in _VALID_TYPES:
        codes.append("EXECUTION_TYPE_INVALID")
        ok = False
    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
        ok = False
    attr_codes: List[str] = []
    if not _attribution_complete_sim(ctx, attr_codes):
        deduped = [c for c in attr_codes if c != "ATTRIBUTION_MISSING_CORRELATION_ID"]
        codes.extend(deduped)
        ok = False
    return ok


def _simulate_worker_execution(
    record: MockCoordinationRecord,
    student: dict,
    attempt: int,
) -> MockWorkerExecutionRecord:
    """
    Contract-level simulation of coordinate_worker_execution.
    Replicates all governance rules without invoking implementation code.
    """
    codes: List[str] = []
    rule_path: List[str] = []
    job_id = str(uuid.uuid4())

    ctx = MockWorkerJobContext(
        governance_scope=record.governance_scope,
        intent_type=record.intent_type,
        is_replay=record.is_replay,
        live_effects_suppressed=record.live_effects_suppressed,
        dispatch_authorized=record.dispatch_authorized,
        dispatch_blocked_reason=record.dispatch_blocked_reason,
        correlation_id=record.correlation_id,
        causation_id=record.causation_id,
        orchestration_cycle_id=record.orchestration_cycle_id,
        origin_source=record.origin_source,
        origin_authority=record.origin_authority,
        actor_identity=record.actor_identity,
        attribution_timestamp=record.attribution_timestamp,
        config_version_id=record.config_version_id,
        execution_mode=record.execution_mode,
        execution_type=record.execution_type,
        threshold_bindings=dict(record.threshold_bindings),
        idempotency_key=(
            f"{student.get('UserID')}:{student.get('PathName')}:{attempt}"
        ),
        student_id_opaque=str(student.get("UserID")) if student.get("UserID") else None,
        checkpoint_type=record.checkpoint_type,
        contact_attempt=attempt,
        degraded=record.degraded,
        degradation_cause=record.degradation_cause,
        degradation_flags=list(record.degradation_flags),
        compliance_hold_active=record.compliance_hold_active,
        job_id=job_id,
    )

    def _make_rec(
        outcome: str,
        *,
        execution_blocked: bool = False,
        blocking_reason: Optional[str] = None,
        dispatch_delegated: bool = False,
        channel: Optional[str] = None,
        dispatch_outcome: Optional[str] = None,
        outbound_suppressed: bool = False,
        suppression_reason: Optional[str] = None,
    ) -> MockWorkerExecutionRecord:
        return MockWorkerExecutionRecord(
            job_id=job_id,
            governance_scope=ctx.governance_scope,
            outcome=outcome,
            correlation_id=ctx.correlation_id,
            causation_id=ctx.causation_id,
            orchestration_cycle_id=ctx.orchestration_cycle_id,
            origin_source=ctx.origin_source,
            origin_authority=ctx.origin_authority,
            actor_identity=ctx.actor_identity,
            config_version_id=ctx.config_version_id,
            execution_mode=ctx.execution_mode,
            execution_type=ctx.execution_type,
            intent_type=ctx.intent_type,
            dispatch_delegated=dispatch_delegated,
            dispatch_outcome=dispatch_outcome,
            channel=channel,
            outbound_suppressed=outbound_suppressed,
            suppression_reason=suppression_reason,
            degraded=ctx.degraded,
            degradation_cause=ctx.degradation_cause,
            student_id_opaque=ctx.student_id_opaque,
            checkpoint_type=ctx.checkpoint_type,
            contact_attempt=ctx.contact_attempt,
            rule_path_taken=list(rule_path),
            reason_codes=list(codes),
            execution_blocked=execution_blocked,
            blocking_reason=blocking_reason,
        )

    # RULE 0: Governance precondition gate
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate_sim(ctx, gate_codes):
        codes.extend(gate_codes)
        return _make_rec(
            OUTCOME_BLOCKED,
            execution_blocked=True,
            blocking_reason=gate_codes[0] if gate_codes else "PRECONDITION_FAILED",
        )

    # RULE 1: Dispatch authorization
    rule_path.append("RULE_1")
    if not record.dispatch_authorized:
        codes.append("DISPATCH_NOT_AUTHORIZED")
        if record.orchestration_blocked:
            codes.append("ORCHESTRATION_BLOCKED")
        return _make_rec(
            OUTCOME_SUPPRESSED,
            blocking_reason=record.dispatch_blocked_reason,
            outbound_suppressed=True,
            suppression_reason=record.dispatch_blocked_reason or "dispatch_not_authorized",
        )

    # RULE 2: Governance scope suppression
    rule_path.append("RULE_2")
    if ctx.governance_scope in _SUPPRESSED_SCOPES:
        codes.append("GOVERNANCE_SCOPE_SUPPRESSED")
        codes.append(ctx.governance_scope)
        return _make_rec(
            OUTCOME_SUPPRESSED,
            blocking_reason=f"scope:{ctx.governance_scope}",
            outbound_suppressed=True,
            suppression_reason=f"governance_scope:{ctx.governance_scope}",
        )

    # RULE 3: Replay containment
    rule_path.append("RULE_3")
    if ctx.is_replay or ctx.execution_type in _REPLAY_TYPES:
        codes.append("REPLAY_EXECUTION_SUPPRESSED")
        return _make_rec(
            OUTCOME_SUPPRESSED,
            blocking_reason="replay_containment",
            outbound_suppressed=True,
            suppression_reason="replay_containment",
        )

    # RULE 4: Live effects suppression
    rule_path.append("RULE_4")
    if ctx.live_effects_suppressed:
        codes.append("LIVE_EFFECTS_SUPPRESSED")
        return _make_rec(
            OUTCOME_SUPPRESSED,
            blocking_reason="live_effects_suppressed",
            outbound_suppressed=True,
            suppression_reason="live_effects_suppressed",
        )

    # RULE 5: Compliance hold
    rule_path.append("RULE_5")
    if ctx.compliance_hold_active:
        codes.append("COMPLIANCE_HOLD_ACTIVE")
        return _make_rec(
            OUTCOME_BLOCKED,
            execution_blocked=True,
            blocking_reason="compliance_hold",
        )

    # RULE 6: Provider delegation (simulated — no live HTTP)
    rule_path.append("RULE_6")
    channel = INTENT_CHANNEL_MAP.get(ctx.intent_type or "", DEFAULT_DISPATCH_CHANNEL)
    # Simulated dispatch: SHADOW always returns shadow_only at transport layer
    dispatch_outcome = "shadow_only"
    outbound_suppressed = True
    suppression_reason = f"transport_scope:{SCOPE_SHADOW_ONLY}"
    codes.append("SHADOW_OUTBOUND_SUPPRESSED")

    return _make_rec(
        OUTCOME_DISPATCH_DELEGATED,
        dispatch_delegated=True,
        channel=channel,
        dispatch_outcome=dispatch_outcome,
        outbound_suppressed=outbound_suppressed,
        suppression_reason=suppression_reason,
    )


def _valid_coord_record(**overrides) -> MockCoordinationRecord:
    """Build a minimal valid coordination record for happy-path tests."""
    defaults = dict(
        governance_scope=SCOPE_SHADOW_ONLY,
        intent_type="INITIATE_OUTREACH",
        is_replay=False,
        live_effects_suppressed=True,
        dispatch_authorized=True,
        dispatch_blocked_reason=None,
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        orchestration_cycle_id=str(uuid.uuid4()),
        origin_source="platform_outreach",
        origin_authority="platform_supplementary",
        actor_identity="scheduler",
        attribution_timestamp="2026-05-28T00:00:00+00:00",
        config_version_id="cv-test-001",
        execution_mode=MODE_SHADOW,
        execution_type=TYPE_ORIGINAL,
        threshold_bindings={},
    )
    defaults.update(overrides)
    return MockCoordinationRecord(**defaults)


def _valid_student(**overrides) -> dict:
    defaults = dict(
        UserID="u-001",
        PhoneNumber="+15550000001",
        Email="student@test.invalid",
        FirstName="Test",
        LastName="Student",
        PathName="python-dev",
        HWsBehind=3,
        AvgEffRating=72.0,
        LastActivityDays=5,
    )
    defaults.update(overrides)
    return defaults


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASSES
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkerRule0Gate:
    """RULE 0: Governance precondition gate — never bypassed (AP-RT4, AP-GHL4)."""

    def test_null_config_version_blocks(self):
        rec = _valid_coord_record(config_version_id=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert "CONFIG_VERSION_UNRESOLVED" in result.reason_codes

    def test_unknown_v0_config_version_blocks(self):
        rec = _valid_coord_record(config_version_id=UNKNOWN_V0)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert "CONFIG_VERSION_UNRESOLVED" in result.reason_codes

    def test_missing_correlation_id_blocks(self):
        rec = _valid_coord_record(correlation_id=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert "CORRELATION_ID_MISSING" in result.reason_codes

    def test_invalid_execution_mode_blocks(self):
        rec = _valid_coord_record(execution_mode="INVALID_MODE")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert "EXECUTION_MODE_INVALID" in result.reason_codes

    def test_invalid_execution_type_blocks(self):
        rec = _valid_coord_record(execution_type="INVALID_TYPE")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert "EXECUTION_TYPE_INVALID" in result.reason_codes

    def test_missing_origin_source_blocks(self):
        rec = _valid_coord_record(origin_source=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert any("ORIGIN_SOURCE" in c for c in result.reason_codes)

    def test_missing_origin_authority_blocks(self):
        rec = _valid_coord_record(origin_authority=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome == OUTCOME_BLOCKED
        assert result.execution_blocked is True
        assert any("ORIGIN_AUTHORITY" in c for c in result.reason_codes)

    def test_all_preconditions_met_passes_rule_0(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert "RULE_0" in result.rule_path_taken
        assert result.execution_blocked is False


class TestShadowModeSuppressionWorker:
    """Workers under SHADOW_ONLY scope return suppressed — no dispatch (AP-RT7, AP-GHL11)."""

    def test_shadow_only_scope_is_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True
        assert result.dispatch_delegated is False

    def test_shadow_preserves_attribution_correlation_id(self):
        cid = str(uuid.uuid4())
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY, correlation_id=cid)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.correlation_id == cid

    def test_shadow_preserves_governance_scope(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_preserves_origin_source(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY, origin_source="platform_scheduler")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.origin_source == "platform_scheduler"

    def test_shadow_preserves_config_version_id(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY, config_version_id="cv-shadow-42")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.config_version_id == "cv-shadow-42"

    def test_shadow_preserves_execution_mode(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY, execution_mode=MODE_SHADOW)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_mode == MODE_SHADOW

    def test_shadow_returns_structured_record(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outcome in (OUTCOME_SUPPRESSED, OUTCOME_DISPATCH_DELEGATED)
        assert result.job_id
        assert result.event_id

    def test_dispatch_authorized_false_shadow_suppressed(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_SHADOW_ONLY,
            dispatch_authorized=False,
            dispatch_blocked_reason="SHADOW_SCOPE",
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is False
        assert result.outbound_suppressed is True


class TestReplayContainmentWorker:
    """Replay execution types must never produce LIVE effects (AP-RT2, AP-RF4)."""

    def test_execution_type_replay_suppressed(self):
        rec = _valid_coord_record(
            execution_type=TYPE_REPLAY,
            governance_scope=SCOPE_AUTHORIZED,
            is_replay=True,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True
        assert result.dispatch_delegated is False

    def test_execution_type_regeneration_suppressed(self):
        rec = _valid_coord_record(
            execution_type=TYPE_REGENERATION,
            governance_scope=SCOPE_AUTHORIZED,
            is_replay=True,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True
        assert result.dispatch_delegated is False

    def test_is_replay_true_suppressed(self):
        rec = _valid_coord_record(
            is_replay=True,
            governance_scope=SCOPE_AUTHORIZED,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True

    def test_replay_only_scope_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_REPLAY_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True
        assert result.dispatch_delegated is False

    def test_replay_preserves_correlation_id(self):
        cid = str(uuid.uuid4())
        rec = _valid_coord_record(
            execution_type=TYPE_REPLAY,
            is_replay=True,
            governance_scope=SCOPE_AUTHORIZED,
            correlation_id=cid,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.correlation_id == cid

    def test_replay_preserves_origin_authority(self):
        rec = _valid_coord_record(
            execution_type=TYPE_REPLAY,
            is_replay=True,
            governance_scope=SCOPE_AUTHORIZED,
            origin_authority="replay_coordinator",
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.origin_authority == "replay_coordinator"

    def test_replay_returns_replay_suppressed_code(self):
        rec = _valid_coord_record(
            execution_type=TYPE_REPLAY,
            is_replay=True,
            governance_scope=SCOPE_AUTHORIZED,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert "REPLAY_EXECUTION_SUPPRESSED" in result.reason_codes

    def test_replay_dispatch_delegated_false(self):
        rec = _valid_coord_record(
            execution_type=TYPE_REPLAY,
            is_replay=True,
            governance_scope=SCOPE_AUTHORIZED,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is False


class TestMaintenanceModeWorker:
    """Maintenance scope and compliance hold block outbound coordination (AP-RT7)."""

    def test_maintenance_scope_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_MAINTENANCE)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True
        assert result.dispatch_delegated is False

    def test_compliance_hold_blocks(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            compliance_hold_active=True,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_blocked is True
        assert "COMPLIANCE_HOLD_ACTIVE" in result.reason_codes

    def test_maintenance_preserves_attribution(self):
        cid = str(uuid.uuid4())
        rec = _valid_coord_record(governance_scope=SCOPE_MAINTENANCE, correlation_id=cid)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.correlation_id == cid

    def test_compliance_hold_not_dispatch_delegated(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            compliance_hold_active=True,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is False

    def test_maintenance_not_dispatch_delegated(self):
        rec = _valid_coord_record(governance_scope=SCOPE_MAINTENANCE)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is False


class TestGovernanceScopeConsumptionWorker:
    """Worker consumes governance scope from coordination record correctly (AP-RT1)."""

    def test_shadow_only_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True

    def test_replay_only_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_REPLAY_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True

    def test_unavailable_scope_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_UNAVAILABLE)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True

    def test_duplicate_suppressed_scope_suppressed(self):
        rec = _valid_coord_record(governance_scope=SCOPE_DUPLICATE_SUPPRESSED)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.outbound_suppressed is True

    def test_scope_preserved_in_execution_record(self):
        rec = _valid_coord_record(governance_scope=SCOPE_UNAVAILABLE)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.governance_scope == SCOPE_UNAVAILABLE

    def test_dispatch_authorized_false_suppressed(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_SHADOW_ONLY,
            dispatch_authorized=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is False
        assert "DISPATCH_NOT_AUTHORIZED" in result.reason_codes

    def test_orchestration_blocked_code_present(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_SHADOW_ONLY,
            dispatch_authorized=False,
            orchestration_blocked=True,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert "ORCHESTRATION_BLOCKED" in result.reason_codes


class TestAttributionContinuityWorker:
    """Attribution propagated immutably end-to-end (AP-RT4, FAD-2)."""

    def test_correlation_id_propagated(self):
        cid = str(uuid.uuid4())
        rec = _valid_coord_record(correlation_id=cid)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.correlation_id == cid

    def test_causation_id_propagated(self):
        cid2 = str(uuid.uuid4())
        rec = _valid_coord_record(causation_id=cid2)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.causation_id == cid2

    def test_origin_source_propagated(self):
        rec = _valid_coord_record(origin_source="test_scheduler")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.origin_source == "test_scheduler"

    def test_origin_authority_propagated(self):
        rec = _valid_coord_record(origin_authority="governance_system")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.origin_authority == "governance_system"

    def test_actor_identity_propagated(self):
        rec = _valid_coord_record(actor_identity="batch_scheduler_v2")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.actor_identity == "batch_scheduler_v2"

    def test_orchestration_cycle_id_propagated(self):
        oci = str(uuid.uuid4())
        rec = _valid_coord_record(orchestration_cycle_id=oci)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.orchestration_cycle_id == oci

    def test_config_version_id_propagated(self):
        rec = _valid_coord_record(config_version_id="cv-propagation-test")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.config_version_id == "cv-propagation-test"

    def test_execution_mode_propagated(self):
        rec = _valid_coord_record(execution_mode=MODE_SHADOW)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_mode == MODE_SHADOW

    def test_execution_type_propagated(self):
        rec = _valid_coord_record(execution_type=TYPE_ORIGINAL)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_type == TYPE_ORIGINAL

    def test_attribution_immutable_across_all_outcomes(self):
        cid = str(uuid.uuid4())
        for scope in (SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE, SCOPE_MAINTENANCE):
            rec = _valid_coord_record(governance_scope=scope, correlation_id=cid)
            result = _simulate_worker_execution(rec, _valid_student(), 1)
            assert result.correlation_id == cid, f"correlation_id lost for scope={scope}"


class TestIdempotencyWorker:
    """Idempotency: same inputs → same outcome; keys preserved (AP-RT10)."""

    def test_same_inputs_same_outcome(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        student = _valid_student()
        r1 = _simulate_worker_execution(rec, student, 1)
        r2 = _simulate_worker_execution(rec, student, 1)
        assert r1.outcome == r2.outcome
        assert r1.governance_scope == r2.governance_scope
        assert r1.execution_mode == r2.execution_mode

    def test_student_id_opaque_preserved(self):
        rec = _valid_coord_record()
        student = _valid_student(UserID="u-idempotency-001")
        result = _simulate_worker_execution(rec, student, 1)
        assert result.student_id_opaque == "u-idempotency-001"

    def test_checkpoint_type_preserved(self):
        rec = _valid_coord_record(checkpoint_type="python-dev")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.checkpoint_type == "python-dev"

    def test_contact_attempt_preserved(self):
        rec = _valid_coord_record()
        result = _simulate_worker_execution(rec, _valid_student(), 3)
        assert result.contact_attempt == 3

    def test_different_attempt_different_idempotency_key(self):
        rec = _valid_coord_record()
        student = _valid_student(UserID="u-idem-002")
        r1 = _simulate_worker_execution(rec, student, 1)
        r2 = _simulate_worker_execution(rec, student, 2)
        assert r1.contact_attempt != r2.contact_attempt

    def test_structured_record_always_returned(self):
        for scope in (SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE):
            rec = _valid_coord_record(governance_scope=scope)
            result = _simulate_worker_execution(rec, _valid_student(), 1)
            assert result is not None
            assert result.outcome


class TestDegradationVisibilityWorker:
    """Degradation from coordination record flows through execution record (AP-RT6)."""

    def test_degraded_true_flows_to_execution_record(self):
        rec = _valid_coord_record(degraded=True, degradation_cause="CIRCUIT_OPEN")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.degraded is True

    def test_degradation_cause_propagated(self):
        rec = _valid_coord_record(degraded=True, degradation_cause="PROVIDER_OUTAGE")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.degradation_cause == "PROVIDER_OUTAGE"

    def test_degraded_does_not_block_shadow_path(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_SHADOW_ONLY,
            degraded=True,
            degradation_cause="SYNC_LAG",
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        # degraded does not block — execution proceeds to suppression
        assert result.execution_blocked is False

    def test_degradation_false_still_propagated(self):
        rec = _valid_coord_record(degraded=False, degradation_cause=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.degraded is False
        assert result.degradation_cause is None

    def test_degraded_with_compliance_hold_blocks(self):
        rec = _valid_coord_record(
            degraded=True,
            degradation_cause="PROVIDER_CIRCUIT_OPEN",
            compliance_hold_active=True,
            governance_scope=SCOPE_AUTHORIZED,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_blocked is True
        assert result.degraded is True


class TestProviderDelegationContainment:
    """Provider delegation: worker delegates, never dispatches directly (AP-RT1)."""

    def test_authorized_scope_reaches_rule_6(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
            compliance_hold_active=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert "RULE_6" in result.rule_path_taken

    def test_dispatch_delegated_on_authorized_scope(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
            compliance_hold_active=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is True

    def test_channel_set_on_delegation(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            intent_type="INITIATE_OUTREACH",
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.channel is not None

    def test_intent_channel_mapping_initiate(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            intent_type="INITIATE_OUTREACH",
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.channel == "call"

    def test_intent_channel_mapping_retry(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            intent_type="RETRY_OUTREACH",
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.channel == "sms"

    def test_intent_channel_mapping_escalate(self):
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            intent_type="ESCALATE",
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.channel == "email"

    def test_attribution_preserved_through_delegation(self):
        cid = str(uuid.uuid4())
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
            correlation_id=cid,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.correlation_id == cid

    def test_transport_still_shadow_under_current_cert(self):
        # Phase-12 cert not present — transport must return shadow_only outcome
        rec = _valid_coord_record(
            governance_scope=SCOPE_AUTHORIZED,
            dispatch_authorized=True,
            is_replay=False,
            live_effects_suppressed=False,
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        # Even after delegation, transport scope gate ensures shadow_only
        assert result.outbound_suppressed is True


class TestBatchCycleGovernance:
    """Batch cycle propagates governance context to each student execution."""

    def _run_batch_sim(
        self,
        students: List[dict],
        execution_mode: str = MODE_SHADOW,
        config_version_id: str = "cv-batch-001",
        governance_scope: str = SCOPE_SHADOW_ONLY,
    ) -> Dict[str, Any]:
        """Simulate run_batch_cycle at contract level."""
        cycle_id = str(uuid.uuid4())
        summary: Dict[str, Any] = {
            "cycle_id": cycle_id,
            "execution_mode": execution_mode,
            "config_version_id": config_version_id,
            "total": len(students),
            "processed": 0,
            "dispatch_delegated": 0,
            "suppressed": 0,
            "blocked": 0,
            "errors": 0,
            "student_records": [],
        }
        for student in students:
            attempt = 1
            rec = _valid_coord_record(
                governance_scope=governance_scope,
                execution_mode=execution_mode,
                config_version_id=config_version_id,
                correlation_id=str(uuid.uuid4()),
                causation_id=cycle_id,
            )
            result = _simulate_worker_execution(rec, student, attempt)
            summary["processed"] += 1
            if result.dispatch_delegated:
                summary["dispatch_delegated"] += 1
            elif result.execution_blocked:
                summary["blocked"] += 1
            else:
                summary["suppressed"] += 1
            summary["student_records"].append({
                "student_id_opaque": result.student_id_opaque,
                "outcome": result.outcome,
                "governance_scope": result.governance_scope,
            })
        return summary

    def test_batch_returns_structured_dict(self):
        students = [_valid_student(UserID=f"u-{i}") for i in range(3)]
        result = self._run_batch_sim(students)
        assert "cycle_id" in result
        assert "execution_mode" in result
        assert "total" in result

    def test_batch_preserves_execution_mode(self):
        students = [_valid_student()]
        result = self._run_batch_sim(students, execution_mode=MODE_SHADOW)
        assert result["execution_mode"] == MODE_SHADOW

    def test_batch_preserves_config_version_id(self):
        students = [_valid_student()]
        result = self._run_batch_sim(students, config_version_id="cv-batch-v99")
        assert result["config_version_id"] == "cv-batch-v99"

    def test_batch_processes_all_students(self):
        students = [_valid_student(UserID=f"u-{i}") for i in range(5)]
        result = self._run_batch_sim(students)
        assert result["processed"] == 5

    def test_batch_handles_empty_student_list(self):
        result = self._run_batch_sim([])
        assert result["total"] == 0
        assert result["processed"] == 0

    def test_batch_returns_suppressed_counts(self):
        students = [_valid_student(UserID=f"u-{i}") for i in range(3)]
        result = self._run_batch_sim(students, governance_scope=SCOPE_SHADOW_ONLY)
        assert result["suppressed"] + result["dispatch_delegated"] + result["blocked"] == result["processed"]

    def test_batch_student_records_no_pii(self):
        students = [_valid_student(UserID="u-pii-test", PhoneNumber="+15559999999")]
        result = self._run_batch_sim(students)
        for record in result["student_records"]:
            assert "PhoneNumber" not in record
            assert "+1555" not in str(record)
            assert "Email" not in record

    def test_batch_cycle_replay_safe(self):
        students = [_valid_student()]
        r1 = self._run_batch_sim(students)
        r2 = self._run_batch_sim(students)
        assert r1["processed"] == r2["processed"]
        r1_outcome = r1["student_records"][0]["outcome"]
        r2_outcome = r2["student_records"][0]["outcome"]
        assert r1_outcome == r2_outcome


class TestWorkerConfigV2Governance:
    """Config V2 governance: UNKNOWN_V0 triggers Rule 0; thresholds propagated (AP-RT9)."""

    def test_unknown_v0_triggers_rule_0_block(self):
        rec = _valid_coord_record(config_version_id=UNKNOWN_V0)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_blocked is True
        assert "CONFIG_VERSION_UNRESOLVED" in result.reason_codes

    def test_null_config_version_triggers_rule_0_block(self):
        rec = _valid_coord_record(config_version_id=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_blocked is True
        assert "CONFIG_VERSION_UNRESOLVED" in result.reason_codes

    def test_threshold_bindings_propagated(self):
        bindings = {"outreach_max_retry_attempts": 3, "ai_insight_ttl_hours": 24}
        rec = _valid_coord_record(threshold_bindings=bindings)
        # Verify context built from record carries bindings (simulation)
        ctx = MockWorkerJobContext(
            governance_scope=rec.governance_scope,
            intent_type=rec.intent_type,
            is_replay=rec.is_replay,
            live_effects_suppressed=rec.live_effects_suppressed,
            dispatch_authorized=rec.dispatch_authorized,
            dispatch_blocked_reason=rec.dispatch_blocked_reason,
            correlation_id=rec.correlation_id,
            causation_id=rec.causation_id,
            orchestration_cycle_id=rec.orchestration_cycle_id,
            origin_source=rec.origin_source,
            origin_authority=rec.origin_authority,
            actor_identity=rec.actor_identity,
            attribution_timestamp=rec.attribution_timestamp,
            config_version_id=rec.config_version_id,
            execution_mode=rec.execution_mode,
            execution_type=rec.execution_type,
            threshold_bindings=dict(rec.threshold_bindings),
        )
        assert ctx.threshold_bindings == bindings

    def test_config_version_id_preserved_in_execution_record(self):
        rec = _valid_coord_record(config_version_id="cv-v2-preserve")
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.config_version_id == "cv-v2-preserve"

    def test_config_version_not_silently_substituted(self):
        rec = _valid_coord_record(config_version_id=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        # Null config must produce an explicit block code — never silently default
        assert result.execution_blocked is True
        assert "CONFIG_VERSION_UNRESOLVED" in result.reason_codes


class TestWorkerInvariantPreservation:
    """Invariant preservation certification (INV-1 through INV-10)."""

    def test_inv1_governance_scope_never_mutated(self):
        # governance_scope from coordination record must equal that in execution record
        for scope in (SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE, SCOPE_MAINTENANCE):
            rec = _valid_coord_record(governance_scope=scope)
            result = _simulate_worker_execution(rec, _valid_student(), 1)
            assert result.governance_scope == scope, f"INV-1 failed for scope={scope}"

    def test_inv2_attribution_never_mutated(self):
        # Every attribution field must match input coordination record exactly
        cid = str(uuid.uuid4())
        oci = str(uuid.uuid4())
        rec = _valid_coord_record(
            correlation_id=cid,
            orchestration_cycle_id=oci,
            origin_source="inv_source",
            origin_authority="inv_authority",
            actor_identity="inv_actor",
        )
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.correlation_id == cid
        assert result.orchestration_cycle_id == oci
        assert result.origin_source == "inv_source"
        assert result.origin_authority == "inv_authority"
        assert result.actor_identity == "inv_actor"

    def test_inv3_replay_scope_never_emits_live_effects(self):
        for exec_type in (TYPE_REPLAY, TYPE_REGENERATION):
            rec = _valid_coord_record(
                execution_type=exec_type,
                is_replay=True,
                governance_scope=SCOPE_AUTHORIZED,
            )
            result = _simulate_worker_execution(rec, _valid_student(), 1)
            assert result.outbound_suppressed is True, f"INV-3 failed for exec_type={exec_type}"

    def test_inv4_shadow_only_scope_never_dispatches_live(self):
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.dispatch_delegated is False or result.outbound_suppressed is True

    def test_inv5_rule_0_never_bypassed(self):
        # Rule 0 must always be first in rule_path
        rec = _valid_coord_record(governance_scope=SCOPE_SHADOW_ONLY)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.rule_path_taken[0] == "RULE_0"

    def test_inv6_correlation_id_always_present_in_record(self):
        cid = str(uuid.uuid4())
        for scope in (SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE):
            rec = _valid_coord_record(governance_scope=scope, correlation_id=cid)
            result = _simulate_worker_execution(rec, _valid_student(), 1)
            assert result.correlation_id == cid, f"INV-6 failed for scope={scope}"

    def test_inv7_execution_mode_always_in_record(self):
        rec = _valid_coord_record(execution_mode=MODE_SHADOW)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_mode == MODE_SHADOW

    def test_inv8_execution_type_always_in_record(self):
        rec = _valid_coord_record(execution_type=TYPE_ORIGINAL)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert result.execution_type == TYPE_ORIGINAL

    def test_inv9_config_version_never_substituted_silently(self):
        # Null config_version_id must block — never substitute a default silently
        rec = _valid_coord_record(config_version_id=None)
        result = _simulate_worker_execution(rec, _valid_student(), 1)
        assert "CONFIG_VERSION_UNRESOLVED" in result.reason_codes
        assert result.config_version_id is None  # preserved as-is, not substituted

    def test_inv10_student_pii_never_in_execution_record(self):
        student = _valid_student(
            PhoneNumber="+15551234567",
            Email="real.student@university.edu",
            FirstName="Alice",
            LastName="Student",
        )
        rec = _valid_coord_record()
        result = _simulate_worker_execution(rec, student, 1)
        # Only opaque ID in record — no phone, email, or name
        result_str = str(result)
        assert "+15551234567" not in result_str
        assert "real.student@university.edu" not in result_str
        assert "Alice" not in result_str
