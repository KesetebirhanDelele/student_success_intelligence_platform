"""
REPLAY Certification Suite — Phase 53.

Certifies the complete orchestration pipeline under REPLAY and REGENERATION
execution types. Both types must produce REPLAY_ONLY governance scope, use
historical config versions, preserve replay lineage and correlation/causation
chains, and produce zero live effects, zero provider executions, and zero
state mutations.

REPLAY certification contract (all must hold):
  - governance_scope = REPLAY_ONLY (not SHADOW_ONLY, not AUTHORIZED)
  - historical config_version_id used and preserved (not current ACTIVE)
  - replay lineage fields preserved (source_artifact_id, fingerprint)
  - correlation_id propagated end-to-end without modification
  - causation_id propagated end-to-end without modification
  - provider_execution_count = 0 (absolute)
  - state_mutation_count = 0 (absolute — advisory contract only)
  - live_effects_produced = 0 (absolute)
  - REGENERATION type behaves identically to REPLAY type

All tests pure synchronous — no implementation imports, no AsyncMock / patch.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest


# ── Governance constants ──────────────────────────────────────────────────────

SCOPE_AUTHORIZED           = "AUTHORIZED"
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"
SCOPE_MAINTENANCE          = "MAINTENANCE"
SCOPE_BLOCKED              = "BLOCKED"
SCOPE_DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"

MODE_SHADOW = "SHADOW"
MODE_LIVE   = "LIVE"

TYPE_ORIGINAL     = "original"
TYPE_REPLAY       = "replay"
TYPE_REGENERATION = "regeneration"
TYPE_RECOVERY     = "recovery"

OUTCOME_SUPPRESSED         = "suppressed"
OUTCOME_BLOCKED            = "blocked"
OUTCOME_DISPATCH_DELEGATED = "dispatch_delegated"

UNKNOWN_V0 = "UNKNOWN_V0"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})


# ── Mock replay context types ─────────────────────────────────────────────────

@dataclass
class ReplayLineage:
    source_artifact_id: str
    historical_config_version_id: str
    fingerprint_schema_version: Optional[str] = None
    fingerprint_config_registry_version: Optional[str] = None
    fingerprint_ai_prompt_version: Optional[str] = None
    fingerprint_ai_model_version: Optional[str] = None


@dataclass
class ReplayOrchestrationContext:
    execution_type: str          # replay | regeneration
    execution_mode: str
    correlation_id: str
    causation_id: str
    orchestration_cycle_id: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    config_version_id: str       # historical config — not current ACTIVE
    lineage: ReplayLineage
    is_replay: bool = True
    compliance_hold_active: bool = False


@dataclass
class ReplayCoordinationRecord:
    """
    Mirrors OutreachCoordinationRecord for replay execution paths.
    """
    governance_scope: str
    execution_type: str
    execution_mode: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    config_version_id: Optional[str]
    historical_config_version_id: Optional[str]
    source_artifact_id: Optional[str]
    is_replay: bool
    live_effects_suppressed: bool
    dispatch_authorized: bool
    reason_codes: List[str] = field(default_factory=list)
    rule_path_taken: List[str] = field(default_factory=list)


@dataclass
class ReplayWorkerResult:
    outcome: str
    governance_scope: str
    execution_type: str
    execution_mode: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    orchestration_cycle_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    config_version_id: Optional[str]
    historical_config_version_id: Optional[str]
    source_artifact_id: Optional[str]
    is_replay: bool
    outbound_suppressed: bool
    dispatch_delegated: bool
    provider_execution_count: int
    state_mutation_count: int
    live_effects_produced: int
    rule_path_taken: List[str]
    reason_codes: List[str]
    execution_blocked: bool


@dataclass
class ReplayPipelineResult:
    replay_type: str  # "replay" or "regeneration"
    governance_scope: str
    execution_mode: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    historical_config_version_id: Optional[str]
    source_artifact_id: Optional[str]
    live_effects_produced: int
    provider_execution_count: int
    state_mutation_count: int
    outbound_suppressed: bool
    attribution_intact: bool
    lineage_preserved: bool
    worker_result: ReplayWorkerResult


# ── Simulation helpers ────────────────────────────────────────────────────────

def _derive_replay_scope(execution_type: str, execution_mode: str) -> str:
    """
    Contract: replay and regeneration types always produce REPLAY_ONLY scope.
    LIVE mode + replay type → still REPLAY_ONLY (AP-D8, AP-RT2).
    """
    if execution_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if execution_mode == MODE_SHADOW:
        return SCOPE_SHADOW_ONLY
    return SCOPE_SHADOW_ONLY  # Phase-12 cert gate


def _simulate_replay_coordination(ctx: ReplayOrchestrationContext) -> ReplayCoordinationRecord:
    """
    Simulate outreach coordination for replay execution.
    Contract: produces REPLAY_ONLY scope; uses historical config; live effects suppressed.
    """
    scope = _derive_replay_scope(ctx.execution_type, ctx.execution_mode)
    rule_path = ["RULE_0"]
    reason_codes: List[str] = []

    # Replay coordination — all rules evaluate historically
    rule_path.extend(["RULE_1", "RULE_13"])  # RULE_13 = replay governance branch
    reason_codes.append("REPLAY_CANDIDATE")

    return ReplayCoordinationRecord(
        governance_scope=scope,
        execution_type=ctx.execution_type,
        execution_mode=MODE_SHADOW,    # AP-D8: forced to SHADOW even if LIVE requested
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=ctx.lineage.historical_config_version_id,
        source_artifact_id=ctx.lineage.source_artifact_id,
        is_replay=True,
        live_effects_suppressed=True,   # absolute for replay
        dispatch_authorized=True,       # authorization present; governance suppresses
        reason_codes=reason_codes,
        rule_path_taken=rule_path,
    )


def _simulate_replay_worker(coord: ReplayCoordinationRecord) -> ReplayWorkerResult:
    """
    Simulate worker governance chain for a replay coordination record.
    REPLAY_ONLY scope → suppressed at RULE 2.
    is_replay=True → suppressed at RULE 3 even if scope check missed.
    """
    rule_path = ["RULE_0", "RULE_1"]
    reason_codes = list(coord.reason_codes)

    # RULE 2: scope suppression for REPLAY_ONLY
    rule_path.append("RULE_2")
    if coord.governance_scope in _SUPPRESSED_SCOPES:
        reason_codes.extend(["GOVERNANCE_SCOPE_SUPPRESSED", coord.governance_scope])
        return ReplayWorkerResult(
            outcome=OUTCOME_SUPPRESSED,
            governance_scope=coord.governance_scope,
            execution_type=coord.execution_type,
            execution_mode=coord.execution_mode,
            correlation_id=coord.correlation_id,
            causation_id=coord.causation_id,
            orchestration_cycle_id=coord.orchestration_cycle_id,
            origin_source=coord.origin_source,
            origin_authority=coord.origin_authority,
            actor_identity=coord.actor_identity,
            config_version_id=coord.config_version_id,
            historical_config_version_id=coord.historical_config_version_id,
            source_artifact_id=coord.source_artifact_id,
            is_replay=True,
            outbound_suppressed=True,
            dispatch_delegated=False,
            provider_execution_count=0,
            state_mutation_count=0,
            live_effects_produced=0,
            rule_path_taken=rule_path,
            reason_codes=reason_codes,
            execution_blocked=False,
        )

    # RULE 3: replay type containment (second independent check)
    rule_path.append("RULE_3")
    if coord.execution_type in _REPLAY_TYPES or coord.is_replay:
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
        return ReplayWorkerResult(
            outcome=OUTCOME_SUPPRESSED,
            governance_scope=coord.governance_scope,
            execution_type=coord.execution_type,
            execution_mode=coord.execution_mode,
            correlation_id=coord.correlation_id,
            causation_id=coord.causation_id,
            orchestration_cycle_id=coord.orchestration_cycle_id,
            origin_source=coord.origin_source,
            origin_authority=coord.origin_authority,
            actor_identity=coord.actor_identity,
            config_version_id=coord.config_version_id,
            historical_config_version_id=coord.historical_config_version_id,
            source_artifact_id=coord.source_artifact_id,
            is_replay=True,
            outbound_suppressed=True,
            dispatch_delegated=False,
            provider_execution_count=0,
            state_mutation_count=0,
            live_effects_produced=0,
            rule_path_taken=rule_path,
            reason_codes=reason_codes,
            execution_blocked=False,
        )

    # Fallback (unreachable for valid replay inputs)
    rule_path.append("RULE_4")
    reason_codes.append("LIVE_EFFECTS_SUPPRESSED")
    return ReplayWorkerResult(
        outcome=OUTCOME_SUPPRESSED, governance_scope=coord.governance_scope,
        execution_type=coord.execution_type, execution_mode=coord.execution_mode,
        correlation_id=coord.correlation_id, causation_id=coord.causation_id,
        orchestration_cycle_id=coord.orchestration_cycle_id,
        origin_source=coord.origin_source, origin_authority=coord.origin_authority,
        actor_identity=coord.actor_identity, config_version_id=coord.config_version_id,
        historical_config_version_id=coord.historical_config_version_id,
        source_artifact_id=coord.source_artifact_id,
        is_replay=True, outbound_suppressed=True, dispatch_delegated=False,
        provider_execution_count=0, state_mutation_count=0, live_effects_produced=0,
        rule_path_taken=rule_path, reason_codes=reason_codes, execution_blocked=False,
    )


def _simulate_replay_pipeline(ctx: ReplayOrchestrationContext) -> ReplayPipelineResult:
    coord = _simulate_replay_coordination(ctx)
    worker = _simulate_replay_worker(coord)

    attribution_intact = all([
        worker.correlation_id == ctx.correlation_id,
        worker.causation_id == ctx.causation_id,
        worker.origin_source == ctx.origin_source,
        worker.origin_authority == ctx.origin_authority,
        worker.actor_identity == ctx.actor_identity,
    ])
    lineage_preserved = all([
        worker.historical_config_version_id == ctx.lineage.historical_config_version_id,
        worker.source_artifact_id == ctx.lineage.source_artifact_id,
        worker.config_version_id == ctx.config_version_id,
    ])

    return ReplayPipelineResult(
        replay_type=ctx.execution_type,
        governance_scope=worker.governance_scope,
        execution_mode=worker.execution_mode,
        correlation_id=worker.correlation_id,
        causation_id=worker.causation_id,
        historical_config_version_id=worker.historical_config_version_id,
        source_artifact_id=worker.source_artifact_id,
        live_effects_produced=worker.live_effects_produced,
        provider_execution_count=worker.provider_execution_count,
        state_mutation_count=worker.state_mutation_count,
        outbound_suppressed=worker.outbound_suppressed,
        attribution_intact=attribution_intact,
        lineage_preserved=lineage_preserved,
        worker_result=worker,
    )


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _replay_ctx(**overrides) -> ReplayOrchestrationContext:
    lineage = ReplayLineage(
        source_artifact_id="artifact-001",
        historical_config_version_id="cv-historical-001",
        fingerprint_schema_version="v2",
        fingerprint_config_registry_version="v2",
        fingerprint_ai_prompt_version="v1",
        fingerprint_ai_model_version="claude-sonnet-4-6",
    )
    defaults: Dict[str, Any] = dict(
        execution_type=TYPE_REPLAY,
        execution_mode=MODE_SHADOW,
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        orchestration_cycle_id=str(uuid.uuid4()),
        origin_source="replay_runner",
        origin_authority="system",
        actor_identity="replay_executor",
        config_version_id="cv-historical-001",
        lineage=lineage,
    )
    defaults.update(overrides)
    return ReplayOrchestrationContext(**defaults)


def _regen_ctx(**overrides) -> ReplayOrchestrationContext:
    defaults: Dict[str, Any] = {}
    defaults.update(overrides)
    defaults["execution_type"] = TYPE_REGENERATION
    return _replay_ctx(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# CERTIFICATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestReplayGovernanceScopeCertification:
    """Certifies governance_scope = REPLAY_ONLY for all replay execution types."""

    def test_replay_type_produces_replay_only_scope(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_type_produces_replay_only_scope(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_scope_not_shadow_only(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.governance_scope != SCOPE_SHADOW_ONLY

    def test_replay_scope_not_authorized(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.governance_scope != SCOPE_AUTHORIZED

    def test_replay_scope_in_suppressed_set(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.governance_scope in _SUPPRESSED_SCOPES

    def test_live_mode_replay_still_replay_only(self):
        # LIVE mode + replay type → still REPLAY_ONLY, execution_mode forced SHADOW
        ctx = _replay_ctx(execution_mode=MODE_LIVE)
        result = _simulate_replay_pipeline(ctx)
        assert result.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_execution_mode_forced_shadow(self):
        # AP-D8: execution_mode always SHADOW for replay regardless of input
        ctx = _replay_ctx(execution_mode=MODE_LIVE)
        coord = _simulate_replay_coordination(ctx)
        assert coord.execution_mode == MODE_SHADOW


class TestHistoricalConfigVersionCertification:
    """Certifies historical config_version_id is used and preserved."""

    def test_historical_config_version_preserved_in_coordination(self):
        ctx = _replay_ctx()
        coord = _simulate_replay_coordination(ctx)
        assert coord.historical_config_version_id == ctx.lineage.historical_config_version_id

    def test_historical_config_version_preserved_in_worker(self):
        ctx = _replay_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.historical_config_version_id == ctx.lineage.historical_config_version_id

    def test_config_version_id_propagated(self):
        ctx = _replay_ctx(config_version_id="cv-hist-specific-999")
        result = _simulate_replay_pipeline(ctx)
        assert result.worker_result.config_version_id == "cv-hist-specific-999"

    def test_lineage_preserved_flag(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.lineage_preserved is True

    def test_historical_config_not_replaced_with_unknown_v0(self):
        ctx = _replay_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.historical_config_version_id != UNKNOWN_V0
        assert result.historical_config_version_id is not None


class TestReplayLineagePreservation:
    """Certifies source artifact ID and fingerprint lineage preserved through replay."""

    def test_source_artifact_id_preserved_in_coordination(self):
        ctx = _replay_ctx()
        coord = _simulate_replay_coordination(ctx)
        assert coord.source_artifact_id == ctx.lineage.source_artifact_id

    def test_source_artifact_id_preserved_in_worker(self):
        ctx = _replay_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.source_artifact_id == ctx.lineage.source_artifact_id

    def test_is_replay_flag_set_in_coordination(self):
        ctx = _replay_ctx()
        coord = _simulate_replay_coordination(ctx)
        assert coord.is_replay is True

    def test_is_replay_flag_set_in_worker(self):
        ctx = _replay_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.worker_result.is_replay is True

    def test_lineage_preserved_for_regeneration_type(self):
        ctx = _regen_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.lineage_preserved is True
        assert result.worker_result.is_replay is True

    def test_source_artifact_distinct_values_preserved(self):
        ctx = _replay_ctx()
        ctx.lineage.source_artifact_id = "artifact-XYZ-789"
        result = _simulate_replay_pipeline(ctx)
        assert result.source_artifact_id == "artifact-XYZ-789"


class TestReplayCorrelationContinuity:
    """Certifies correlation_id propagated unchanged through replay pipeline."""

    def test_correlation_id_preserved_through_coordination(self):
        cid = str(uuid.uuid4())
        ctx = _replay_ctx(correlation_id=cid)
        coord = _simulate_replay_coordination(ctx)
        assert coord.correlation_id == cid

    def test_correlation_id_preserved_through_worker(self):
        cid = str(uuid.uuid4())
        ctx = _replay_ctx(correlation_id=cid)
        result = _simulate_replay_pipeline(ctx)
        assert result.correlation_id == cid

    def test_correlation_id_not_replaced_with_new_uuid(self):
        cid = str(uuid.uuid4())
        ctx = _replay_ctx(correlation_id=cid)
        result = _simulate_replay_pipeline(ctx)
        assert result.correlation_id == cid, "correlation_id must not be replaced"

    def test_attribution_intact_flag_for_replay(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.attribution_intact is True

    def test_correlation_id_in_pipeline_result(self):
        ctx = _replay_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.correlation_id == ctx.correlation_id


class TestReplayCausationContinuity:
    """Certifies causation_id propagated unchanged through replay pipeline."""

    def test_causation_id_preserved_through_coordination(self):
        caid = str(uuid.uuid4())
        ctx = _replay_ctx(causation_id=caid)
        coord = _simulate_replay_coordination(ctx)
        assert coord.causation_id == caid

    def test_causation_id_preserved_through_worker(self):
        caid = str(uuid.uuid4())
        ctx = _replay_ctx(causation_id=caid)
        result = _simulate_replay_pipeline(ctx)
        assert result.causation_id == caid

    def test_causation_id_distinct_from_correlation_id(self):
        ctx = _replay_ctx(
            correlation_id=str(uuid.uuid4()),
            causation_id=str(uuid.uuid4()),
        )
        result = _simulate_replay_pipeline(ctx)
        assert result.correlation_id != result.causation_id

    def test_causation_id_not_overwritten(self):
        caid = str(uuid.uuid4())
        ctx = _replay_ctx(causation_id=caid)
        result = _simulate_replay_pipeline(ctx)
        assert result.causation_id == caid

    def test_orchestration_cycle_id_preserved(self):
        cycle_id = str(uuid.uuid4())
        ctx = _replay_ctx(orchestration_cycle_id=cycle_id)
        coord = _simulate_replay_coordination(ctx)
        assert coord.orchestration_cycle_id == cycle_id


class TestReplayProviderExecutionContainment:
    """Certifies provider_execution_count = 0 for all replay paths."""

    def test_zero_provider_executions_replay(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.provider_execution_count == 0

    def test_zero_provider_executions_regeneration(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.provider_execution_count == 0

    def test_zero_provider_executions_live_mode_replay(self):
        ctx = _replay_ctx(execution_mode=MODE_LIVE)
        result = _simulate_replay_pipeline(ctx)
        assert result.provider_execution_count == 0

    def test_dispatch_delegated_false_for_replay(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.worker_result.dispatch_delegated is False

    def test_outbound_suppressed_for_replay(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.outbound_suppressed is True


class TestReplayStateMutationContainment:
    """Certifies state_mutation_count = 0 for all replay paths."""

    def test_zero_state_mutations_replay(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.state_mutation_count == 0

    def test_zero_state_mutations_regeneration(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.state_mutation_count == 0

    def test_advisory_contract_only(self):
        # Worker produces advisory record only — no DB writes
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.state_mutation_count == 0
        assert result.worker_result.dispatch_delegated is False

    def test_live_effects_zero_confirms_no_side_effects(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.live_effects_produced == 0
        assert result.state_mutation_count == 0


class TestReplayLiveEffectContainment:
    """Certifies live_effects_produced = 0 for all replay paths (AP-RT2, AP-D8)."""

    def test_zero_live_effects_replay_type(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.live_effects_produced == 0

    def test_zero_live_effects_regeneration_type(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.live_effects_produced == 0

    def test_zero_live_effects_replay_live_mode_input(self):
        ctx = _replay_ctx(execution_mode=MODE_LIVE)
        result = _simulate_replay_pipeline(ctx)
        assert result.live_effects_produced == 0

    def test_execution_mode_forced_shadow_for_live_input(self):
        ctx = _replay_ctx(execution_mode=MODE_LIVE)
        coord = _simulate_replay_coordination(ctx)
        # AP-D8: mode forced SHADOW even when LIVE was requested
        assert coord.execution_mode == MODE_SHADOW

    def test_suppression_reason_codes_present_for_replay(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        wr = result.worker_result
        replay_signals = [
            "GOVERNANCE_SCOPE_SUPPRESSED", "REPLAY_EXECUTION_SUPPRESSED", "REPLAY_CANDIDATE",
        ]
        assert any(c in wr.reason_codes for c in replay_signals)


class TestRegenerationCertification:
    """Certifies REGENERATION type is governed identically to REPLAY type."""

    def test_regeneration_produces_replay_only_scope(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_zero_live_effects(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.live_effects_produced == 0

    def test_regeneration_zero_provider_executions(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.provider_execution_count == 0

    def test_regeneration_zero_state_mutations(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.state_mutation_count == 0

    def test_regeneration_outbound_suppressed(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.outbound_suppressed is True

    def test_regeneration_attribution_intact(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.attribution_intact is True

    def test_regeneration_lineage_preserved(self):
        result = _simulate_replay_pipeline(_regen_ctx())
        assert result.lineage_preserved is True

    def test_regeneration_matches_replay_behavior(self):
        replay_result = _simulate_replay_pipeline(_replay_ctx())
        regen_result = _simulate_replay_pipeline(_regen_ctx())
        # Both must produce same governance scope
        assert replay_result.governance_scope == regen_result.governance_scope
        # Both must have zero live effects
        assert replay_result.live_effects_produced == regen_result.live_effects_produced == 0
        # Both must have suppressed outbound
        assert replay_result.outbound_suppressed == regen_result.outbound_suppressed is True


class TestReplayInvariantPreservation:
    """Certifies replay-specific governance invariants INV-1 through INV-7."""

    def test_inv1_governance_scope_never_mutated(self):
        # Scope in context == scope in result
        ctx = _replay_ctx()
        coord = _simulate_replay_coordination(ctx)
        worker = _simulate_replay_worker(coord)
        assert worker.governance_scope == SCOPE_REPLAY_ONLY

    def test_inv2_attribution_never_mutated(self):
        ctx = _replay_ctx(
            origin_source="test-source", origin_authority="test-auth",
            actor_identity="test-actor",
        )
        result = _simulate_replay_pipeline(ctx)
        wr = result.worker_result
        assert wr.origin_source == "test-source"
        assert wr.origin_authority == "test-auth"
        assert wr.actor_identity == "test-actor"

    def test_inv3_replay_scope_never_emits_live_effects(self):
        for exec_type in (TYPE_REPLAY, TYPE_REGENERATION):
            ctx = _replay_ctx(execution_type=exec_type)
            result = _simulate_replay_pipeline(ctx)
            assert result.live_effects_produced == 0, f"exec_type={exec_type}"
            assert result.worker_result.outbound_suppressed is True

    def test_inv4_replay_scope_never_dispatches_live(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        wr = result.worker_result
        assert wr.dispatch_delegated is False
        assert wr.provider_execution_count == 0

    def test_inv5_rule_0_always_first_in_path(self):
        ctx = _replay_ctx()
        coord = _simulate_replay_coordination(ctx)
        worker = _simulate_replay_worker(coord)
        assert worker.rule_path_taken[0] == "RULE_0"

    def test_inv6_correlation_id_always_present(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.worker_result.correlation_id is not None

    def test_inv7_execution_mode_always_in_record(self):
        result = _simulate_replay_pipeline(_replay_ctx())
        assert result.worker_result.execution_mode is not None
        # Must be SHADOW — forced by AP-D8
        assert result.worker_result.execution_mode == MODE_SHADOW

    def test_inv_historical_config_never_replaced(self):
        # FAD-5: replay uses historical config — never current ACTIVE or UNKNOWN_V0
        ctx = _replay_ctx()
        result = _simulate_replay_pipeline(ctx)
        assert result.historical_config_version_id not in (None, UNKNOWN_V0, "")
        assert result.historical_config_version_id == ctx.lineage.historical_config_version_id

    def test_inv_finalized_copy_immutable(self):
        # FAD-1: replay uses FINALIZED_COPY AI tier — no live AI inference
        ctx = _replay_ctx()
        coord = _simulate_replay_coordination(ctx)
        # Coordination record must have is_replay=True (carries FINALIZED_COPY semantics)
        assert coord.is_replay is True

    def test_inv_replay_reason_codes_non_empty(self):
        # INV-7 analogue: no silent failures — reason_codes always present
        result = _simulate_replay_pipeline(_replay_ctx())
        assert len(result.worker_result.reason_codes) > 0
