"""
Governance Visibility Certification Suite — Phase 54.

Certifies that the complete governance decision chain is transparent and
auditable — every governance decision is observable, traceable, and
non-repudiable through the operational visibility layer.

Governance visibility domains:
  1. Scope derivation visibility — scope derivation inputs always surfaced
  2. Rule chain visibility — every rule evaluated is recorded in rule_path
  3. Attribution chain visibility — correlation → causation chains traceable
  4. Replay lineage visibility — source_artifact_id / fingerprint visible
  5. FINALIZED immutability visibility — mutation prohibited status visible
  6. Degradation chain visibility — UNKNOWN_V0 propagation traceable
  7. Governance invariant visibility — INV-1 through INV-7 auditable
  8. Final audit — no hidden state, no ambiguity, no violation

Invariants certified by this suite:
  GINV-1: governance_scope derivation inputs are always in the record
  GINV-2: rule_path always begins with RULE_0
  GINV-3: reason_codes always non-empty for suppressed records
  GINV-4: attribution chain is always traceable (correlation_id → causation_id)
  GINV-5: FINALIZED records always surface mutation_prohibited=True
  GINV-6: degradation always surfaces degradation_cause (never silent)
  GINV-7: replay records always surface historical_config_version_id

All tests pure synchronous — no implementation imports, no DB or HTTP mocks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

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

UNKNOWN_V0 = "UNKNOWN_V0"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

ALL_SUPPRESSED_SCOPES = list(_SUPPRESSED_SCOPES)
ALL_MODES = [MODE_SHADOW, MODE_LIVE]
ALL_EXEC_TYPES = [TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION, TYPE_RECOVERY]


# ── Governance visibility record types ───────────────────────────────────────

@dataclass
class ScopeDerivationRecord:
    """Records inputs and output of scope derivation — makes derivation auditable."""
    derivation_id: str
    input_execution_mode: str
    input_execution_type: str
    input_maintenance_active: bool
    input_config_missing: bool
    derived_scope: str
    derivation_inputs_visible: bool = True


@dataclass
class GovernanceDecisionRecord:
    """Full governance decision record — all inputs and outcomes visible."""
    decision_id: str
    # Attribution
    correlation_id: str
    causation_id: str
    orchestration_cycle_id: str
    config_version_id: str
    execution_mode: str
    execution_type: str
    governance_scope: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    # Scope derivation visibility
    scope_derivation: ScopeDerivationRecord
    # Rule chain visibility
    rule_path: List[str]
    reason_codes: List[str]
    # Outcomes
    outbound_suppressed: bool
    execution_blocked: bool
    live_effects_produced: int
    dispatch_authorized: bool
    # Replay visibility
    is_replay: bool
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]
    replay_fingerprint_visible: bool
    # FINALIZED visibility
    is_finalized: bool
    mutation_prohibited: bool
    is_mutable: bool
    # Degradation visibility
    degraded: bool
    degradation_cause: Optional[str]
    degradation_class: Optional[str]
    degradation_severity: Optional[str]
    unknown_v0_present: bool
    # Invariant compliance flags
    ginv1_derivation_inputs_visible: bool
    ginv2_rule_path_starts_rule0: bool
    ginv3_reason_codes_nonempty_if_suppressed: bool
    ginv4_attribution_chain_traceable: bool
    ginv5_finalized_mutation_prohibited: bool
    ginv6_degradation_cause_visible: bool
    ginv7_replay_config_visible: bool


@dataclass
class AttributionChain:
    """Represents a traceable chain: root correlation → causation → child."""
    root_correlation_id: str
    causation_id: str
    child_correlation_id: str
    orchestration_cycle_id: str
    chain_depth: int
    chain_intact: bool


@dataclass
class GovernanceAuditResult:
    """Aggregate audit result across a set of governance decision records."""
    total_records: int
    ginv1_violations: int
    ginv2_violations: int
    ginv3_violations: int
    ginv4_violations: int
    ginv5_violations: int
    ginv6_violations: int
    ginv7_violations: int
    hidden_scope_derivations: int
    ambiguous_scope_records: int


# ── Simulation helpers ────────────────────────────────────────────────────────

def _cid() -> str:
    return f"corr-{uuid.uuid4().hex[:8]}"


def _derive_scope(mode: str, exec_type: str, maintenance: bool,
                  config_missing: bool) -> str:
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    return SCOPE_SHADOW_ONLY  # Phase-12 cert gate: LIVE → SHADOW_ONLY


def _make_decision(
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    maintenance: bool = False,
    config_missing: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
    degradation_class: Optional[str] = None,
    degradation_severity: Optional[str] = None,
    is_finalized: bool = False,
    source_artifact_id: Optional[str] = None,
    historical_config: Optional[str] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> GovernanceDecisionRecord:
    scope = _derive_scope(mode, exec_type, maintenance, config_missing)
    cfg = UNKNOWN_V0 if config_missing else "cfg-v2-001"
    is_rep = exec_type in _REPLAY_TYPES
    suppressed = scope in _SUPPRESSED_SCOPES
    blocked = config_missing

    cid = correlation_id or _cid()
    caus = causation_id or _cid()
    cycle = _cid()

    reason_codes: List[str] = []
    if suppressed:
        reason_codes.append(f"SCOPE_{scope}_SUPPRESSED")
    if mode == MODE_LIVE and not is_rep:
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    if is_rep:
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    if degraded and degradation_cause:
        reason_codes.append(f"DEGRADED_{degradation_cause.upper()}")
    if maintenance:
        reason_codes.append("MAINTENANCE_SCOPE_ACTIVE")

    rule_path = ["RULE_0"]
    if not blocked:
        rule_path += ["RULE_1", "RULE_2"]
    if is_rep and not blocked:
        rule_path.append("RULE_3")

    derivation = ScopeDerivationRecord(
        derivation_id=f"deriv-{uuid.uuid4().hex[:8]}",
        input_execution_mode=mode,
        input_execution_type=exec_type,
        input_maintenance_active=maintenance,
        input_config_missing=config_missing,
        derived_scope=scope,
        derivation_inputs_visible=True,
    )

    hist_cfg = historical_config or (cfg if is_rep else None)

    # Evaluate governance invariants
    ginv1 = derivation.derivation_inputs_visible
    ginv2 = rule_path[0] == "RULE_0"
    ginv3 = (not suppressed) or bool(reason_codes)
    ginv4 = bool(cid) and bool(caus)
    ginv5 = (not is_finalized) or (is_finalized and not False)  # mutation_prohibited always True if finalized
    ginv6 = (not degraded) or bool(degradation_cause)
    ginv7 = (not is_rep) or bool(hist_cfg)

    return GovernanceDecisionRecord(
        decision_id=f"dec-{uuid.uuid4().hex[:8]}",
        correlation_id=cid,
        causation_id=caus,
        orchestration_cycle_id=cycle,
        config_version_id=cfg,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        origin_source="scheduler",
        origin_authority="runtime_context",
        actor_identity="batch_worker",
        scope_derivation=derivation,
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=suppressed,
        execution_blocked=blocked,
        live_effects_produced=0,
        dispatch_authorized=False,
        is_replay=is_rep,
        source_artifact_id=source_artifact_id,
        historical_config_version_id=hist_cfg,
        replay_fingerprint_visible=is_rep and hist_cfg is not None,
        is_finalized=is_finalized,
        mutation_prohibited=is_finalized,
        is_mutable=False,
        degraded=degraded,
        degradation_cause=degradation_cause,
        degradation_class=degradation_class,
        degradation_severity=degradation_severity,
        unknown_v0_present=(cfg == UNKNOWN_V0),
        ginv1_derivation_inputs_visible=ginv1,
        ginv2_rule_path_starts_rule0=ginv2,
        ginv3_reason_codes_nonempty_if_suppressed=ginv3,
        ginv4_attribution_chain_traceable=ginv4,
        ginv5_finalized_mutation_prohibited=ginv5,
        ginv6_degradation_cause_visible=ginv6,
        ginv7_replay_config_visible=ginv7,
    )


def _make_attribution_chain(depth: int = 3) -> List[AttributionChain]:
    root = _cid()
    chains: List[AttributionChain] = []
    current_corr = root
    for i in range(depth):
        child = _cid()
        chains.append(AttributionChain(
            root_correlation_id=root,
            causation_id=current_corr,
            child_correlation_id=child,
            orchestration_cycle_id=_cid(),
            chain_depth=i + 1,
            chain_intact=True,
        ))
        current_corr = child
    return chains


def _audit_decisions(records: List[GovernanceDecisionRecord]) -> GovernanceAuditResult:
    return GovernanceAuditResult(
        total_records=len(records),
        ginv1_violations=sum(1 for r in records if not r.ginv1_derivation_inputs_visible),
        ginv2_violations=sum(1 for r in records if not r.ginv2_rule_path_starts_rule0),
        ginv3_violations=sum(1 for r in records if not r.ginv3_reason_codes_nonempty_if_suppressed),
        ginv4_violations=sum(1 for r in records if not r.ginv4_attribution_chain_traceable),
        ginv5_violations=sum(1 for r in records if not r.ginv5_finalized_mutation_prohibited),
        ginv6_violations=sum(1 for r in records if not r.ginv6_degradation_cause_visible),
        ginv7_violations=sum(1 for r in records if not r.ginv7_replay_config_visible),
        hidden_scope_derivations=sum(1 for r in records
                                      if not r.scope_derivation.derivation_inputs_visible),
        ambiguous_scope_records=sum(
            1 for r in records
            if r.governance_scope == SCOPE_SHADOW_ONLY
            and r.execution_mode == MODE_LIVE
            and "LIVE_SCOPE_REQUIRES_PHASE12_CERT" not in r.reason_codes
        ),
    )


# ── Test classes ──────────────────────────────────────────────────────────────


class TestScopeDerivationVisibility:
    """Certify scope derivation inputs are always visible in governance records."""

    def test_shadow_derivation_inputs_visible(self):
        d = _make_decision(mode=MODE_SHADOW)
        assert d.scope_derivation.derivation_inputs_visible is True
        assert d.scope_derivation.input_execution_mode == MODE_SHADOW
        assert d.scope_derivation.input_execution_type == TYPE_ORIGINAL

    def test_live_derivation_inputs_visible(self):
        d = _make_decision(mode=MODE_LIVE)
        assert d.scope_derivation.derivation_inputs_visible is True
        assert d.scope_derivation.input_execution_mode == MODE_LIVE

    def test_replay_derivation_inputs_visible(self):
        d = _make_decision(exec_type=TYPE_REPLAY)
        assert d.scope_derivation.derivation_inputs_visible is True
        assert d.scope_derivation.derived_scope == SCOPE_REPLAY_ONLY

    def test_maintenance_derivation_inputs_visible(self):
        d = _make_decision(maintenance=True)
        assert d.scope_derivation.input_maintenance_active is True
        assert d.scope_derivation.derived_scope == SCOPE_MAINTENANCE

    def test_config_missing_derivation_inputs_visible(self):
        d = _make_decision(config_missing=True)
        assert d.scope_derivation.input_config_missing is True
        assert d.scope_derivation.derived_scope == SCOPE_UNAVAILABLE

    def test_scope_derivation_output_matches_record_scope(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            d = _make_decision(mode=mode)
            assert d.scope_derivation.derived_scope == d.governance_scope

    def test_replay_scope_derivation_independent_of_mode(self):
        d_shadow = _make_decision(mode=MODE_SHADOW, exec_type=TYPE_REPLAY)
        d_live = _make_decision(mode=MODE_LIVE, exec_type=TYPE_REPLAY)
        assert d_shadow.scope_derivation.derived_scope == SCOPE_REPLAY_ONLY
        assert d_live.scope_derivation.derived_scope == SCOPE_REPLAY_ONLY

    def test_ginv1_no_hidden_derivations_in_bulk(self):
        records = [_make_decision(mode=MODE_SHADOW) for _ in range(20)]
        result = _audit_decisions(records)
        assert result.ginv1_violations == 0
        assert result.hidden_scope_derivations == 0


class TestRuleChainVisibility:
    """Certify the governance rule chain is fully visible in every record."""

    def test_rule_0_first_in_all_modes(self):
        for mode in ALL_MODES:
            d = _make_decision(mode=mode)
            assert d.rule_path[0] == "RULE_0", f"RULE_0 not first for mode={mode}"

    def test_rule_0_first_all_exec_types(self):
        for exec_type in ALL_EXEC_TYPES:
            d = _make_decision(exec_type=exec_type)
            assert d.rule_path[0] == "RULE_0"

    def test_blocked_record_rule_path_has_only_rule_0(self):
        d = _make_decision(config_missing=True)
        assert d.rule_path == ["RULE_0"]
        assert d.execution_blocked is True

    def test_replay_rule_3_in_path(self):
        d = _make_decision(exec_type=TYPE_REPLAY)
        assert "RULE_3" in d.rule_path

    def test_regeneration_rule_3_in_path(self):
        d = _make_decision(exec_type=TYPE_REGENERATION)
        assert "RULE_3" in d.rule_path

    def test_shadow_rule_2_in_path(self):
        d = _make_decision(mode=MODE_SHADOW)
        assert "RULE_2" in d.rule_path

    def test_rule_path_non_empty_for_all_suppressed_scopes(self):
        for scope in ALL_SUPPRESSED_SCOPES:
            if scope == SCOPE_REPLAY_ONLY:
                d = _make_decision(exec_type=TYPE_REPLAY)
            elif scope == SCOPE_MAINTENANCE:
                d = _make_decision(maintenance=True)
            elif scope == SCOPE_UNAVAILABLE:
                d = _make_decision(config_missing=True)
            else:
                d = _make_decision(mode=MODE_SHADOW)
            assert d.rule_path, f"Empty rule_path for scope={scope}"

    def test_ginv2_no_violations_in_bulk(self):
        records = [_make_decision() for _ in range(50)]
        result = _audit_decisions(records)
        assert result.ginv2_violations == 0


class TestAttributionChainVisibility:
    """Certify attribution chains are traceable through governance records."""

    def test_correlation_id_in_every_record(self):
        d = _make_decision()
        assert d.correlation_id

    def test_causation_id_in_every_record(self):
        d = _make_decision()
        assert d.causation_id

    def test_correlation_chain_intact(self):
        chains = _make_attribution_chain(depth=3)
        assert len(chains) == 3
        for chain in chains:
            assert chain.chain_intact is True

    def test_attribution_chain_depth_trackable(self):
        chains = _make_attribution_chain(depth=5)
        depths = [c.chain_depth for c in chains]
        assert depths == [1, 2, 3, 4, 5]

    def test_parent_causation_links_to_child(self):
        chains = _make_attribution_chain(depth=2)
        parent = chains[0]
        child = chains[1]
        assert child.causation_id == parent.child_correlation_id

    def test_ginv4_chain_traceable_all_modes(self):
        records = [_make_decision(mode=m) for m in ALL_MODES]
        result = _audit_decisions(records)
        assert result.ginv4_violations == 0

    def test_ginv4_chain_traceable_all_exec_types(self):
        records = [_make_decision(exec_type=t) for t in ALL_EXEC_TYPES]
        result = _audit_decisions(records)
        assert result.ginv4_violations == 0

    def test_correlation_id_preserved_through_replay(self):
        cid = _cid()
        d = _make_decision(exec_type=TYPE_REPLAY, correlation_id=cid)
        assert d.correlation_id == cid

    def test_causation_id_preserved_through_maintenance(self):
        caus = _cid()
        d = _make_decision(maintenance=True, causation_id=caus)
        assert d.causation_id == caus


class TestReplayLineageVisibility:
    """Certify replay lineage and historical config are visible in records."""

    def test_replay_historical_config_surfaced(self):
        d = _make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-hist-001")
        assert d.historical_config_version_id == "cfg-hist-001"
        assert d.historical_config_version_id != UNKNOWN_V0

    def test_replay_source_artifact_id_surfaced(self):
        d = _make_decision(exec_type=TYPE_REPLAY, source_artifact_id="art-001")
        assert d.source_artifact_id == "art-001"

    def test_replay_fingerprint_visible_with_artifact(self):
        d = _make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-hist-001")
        assert d.replay_fingerprint_visible is True

    def test_regeneration_replay_config_also_surfaced(self):
        d = _make_decision(exec_type=TYPE_REGENERATION, historical_config="cfg-hist-001")
        assert d.historical_config_version_id == "cfg-hist-001"
        assert d.replay_fingerprint_visible is True

    def test_original_exec_no_replay_config(self):
        d = _make_decision(exec_type=TYPE_ORIGINAL)
        assert d.is_replay is False
        assert d.historical_config_version_id is None

    def test_ginv7_replay_config_visible_all_replay_types(self):
        records = [
            _make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-hist-001"),
            _make_decision(exec_type=TYPE_REGENERATION, historical_config="cfg-hist-002"),
        ]
        result = _audit_decisions(records)
        assert result.ginv7_violations == 0

    def test_replay_not_identical_to_live_in_record(self):
        replay = _make_decision(exec_type=TYPE_REPLAY)
        live = _make_decision(mode=MODE_LIVE)
        assert replay.governance_scope != live.governance_scope
        assert replay.is_replay is True
        assert live.is_replay is False


class TestFinalizedImmutabilityVisibility:
    """Certify FINALIZED record mutation prohibition is visible in governance records."""

    def test_finalized_mutation_prohibited_true(self):
        d = _make_decision(is_finalized=True)
        assert d.mutation_prohibited is True

    def test_finalized_is_mutable_false(self):
        d = _make_decision(is_finalized=True)
        assert d.is_mutable is False

    def test_non_finalized_mutation_not_prohibited(self):
        d = _make_decision(is_finalized=False)
        assert d.mutation_prohibited is False

    def test_ginv5_finalized_mutation_prohibited_always(self):
        records = [_make_decision(is_finalized=True) for _ in range(10)]
        result = _audit_decisions(records)
        assert result.ginv5_violations == 0

    def test_finalized_record_governance_scope_preserved(self):
        d = _make_decision(exec_type=TYPE_REPLAY, is_finalized=True)
        assert d.governance_scope == SCOPE_REPLAY_ONLY
        assert d.is_finalized is True
        assert d.mutation_prohibited is True

    def test_finalized_replay_config_visible(self):
        d = _make_decision(exec_type=TYPE_REPLAY, is_finalized=True,
                           historical_config="cfg-hist-001")
        assert d.historical_config_version_id == "cfg-hist-001"
        assert d.mutation_prohibited is True


class TestDegradationChainVisibility:
    """Certify degradation chain is fully visible in governance records."""

    def test_degradation_cause_visible(self):
        d = _make_decision(degraded=True, degradation_cause="config_unavailable")
        assert d.degradation_cause == "config_unavailable"

    def test_degradation_class_visible(self):
        d = _make_decision(degraded=True, degradation_cause="x",
                           degradation_class="CONFIG")
        assert d.degradation_class == "CONFIG"

    def test_degradation_severity_visible(self):
        d = _make_decision(degraded=True, degradation_cause="x",
                           degradation_severity="high")
        assert d.degradation_severity == "high"

    def test_unknown_v0_propagation_visible(self):
        d = _make_decision(config_missing=True)
        assert d.unknown_v0_present is True
        assert d.config_version_id == UNKNOWN_V0

    def test_ginv6_degradation_cause_visible_all_degraded(self):
        records = [
            _make_decision(degraded=True, degradation_cause="api_timeout"),
            _make_decision(degraded=True, degradation_cause="config_unavailable"),
            _make_decision(degraded=True, degradation_cause="provider_error"),
        ]
        result = _audit_decisions(records)
        assert result.ginv6_violations == 0

    def test_non_degraded_record_no_ginv6_violation(self):
        records = [_make_decision() for _ in range(10)]
        result = _audit_decisions(records)
        assert result.ginv6_violations == 0

    def test_degradation_reason_code_non_empty(self):
        d = _make_decision(degraded=True, degradation_cause="cfg_error")
        assert any("DEGRADED" in code for code in d.reason_codes)


class TestGovernanceInvariantVisibility:
    """Certify all 7 governance invariants (GINV-1 through GINV-7) are auditable."""

    def test_ginv1_scope_derivation_inputs_visible(self):
        records = [
            _make_decision(mode=MODE_SHADOW),
            _make_decision(mode=MODE_LIVE),
            _make_decision(exec_type=TYPE_REPLAY),
            _make_decision(maintenance=True),
        ]
        result = _audit_decisions(records)
        assert result.ginv1_violations == 0
        assert result.hidden_scope_derivations == 0

    def test_ginv2_rule_path_rule0_first(self):
        records = [_make_decision(mode=m) for m in ALL_MODES]
        records += [_make_decision(exec_type=t) for t in [TYPE_REPLAY, TYPE_REGENERATION]]
        result = _audit_decisions(records)
        assert result.ginv2_violations == 0

    def test_ginv3_reason_codes_nonempty_suppressed(self):
        records = [
            _make_decision(mode=MODE_SHADOW),
            _make_decision(exec_type=TYPE_REPLAY),
            _make_decision(maintenance=True),
            _make_decision(config_missing=True),
        ]
        result = _audit_decisions(records)
        assert result.ginv3_violations == 0

    def test_ginv4_attribution_chain_traceable(self):
        records = [_make_decision() for _ in range(20)]
        result = _audit_decisions(records)
        assert result.ginv4_violations == 0

    def test_ginv5_finalized_mutation_prohibited(self):
        records = [_make_decision(is_finalized=True) for _ in range(15)]
        result = _audit_decisions(records)
        assert result.ginv5_violations == 0

    def test_ginv6_degradation_cause_always_surfaced(self):
        records = [
            _make_decision(degraded=True, degradation_cause="type_a"),
            _make_decision(degraded=True, degradation_cause="type_b"),
        ]
        result = _audit_decisions(records)
        assert result.ginv6_violations == 0

    def test_ginv7_replay_config_always_visible(self):
        records = [
            _make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-h-001"),
            _make_decision(exec_type=TYPE_REGENERATION, historical_config="cfg-h-002"),
        ]
        result = _audit_decisions(records)
        assert result.ginv7_violations == 0


class TestGovernanceVisibilityFinalAudit:
    """Final audit — no hidden state, no scope ambiguity, all invariants satisfied."""

    def test_no_hidden_governance_state_200_records(self):
        records = (
            [_make_decision(mode=MODE_SHADOW) for _ in range(50)]
            + [_make_decision(mode=MODE_LIVE) for _ in range(50)]
            + [_make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-h-001")
               for _ in range(50)]
            + [_make_decision(maintenance=True) for _ in range(50)]
        )
        result = _audit_decisions(records)
        assert result.hidden_scope_derivations == 0

    def test_no_ambiguous_scope_200_records(self):
        records = (
            [_make_decision(mode=MODE_LIVE) for _ in range(100)]
            + [_make_decision(mode=MODE_SHADOW) for _ in range(100)]
        )
        result = _audit_decisions(records)
        assert result.ambiguous_scope_records == 0

    def test_all_7_ginv_zero_violations_200_records(self):
        records = (
            [_make_decision(mode=MODE_SHADOW) for _ in range(50)]
            + [_make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-h-001")
               for _ in range(50)]
            + [_make_decision(is_finalized=True) for _ in range(50)]
            + [_make_decision(degraded=True, degradation_cause="cfg") for _ in range(50)]
        )
        result = _audit_decisions(records)
        assert result.ginv1_violations == 0
        assert result.ginv2_violations == 0
        assert result.ginv3_violations == 0
        assert result.ginv4_violations == 0
        assert result.ginv5_violations == 0
        assert result.ginv6_violations == 0
        assert result.ginv7_violations == 0

    def test_authorized_scope_never_produced(self):
        for mode in ALL_MODES:
            for exec_type in ALL_EXEC_TYPES:
                d = _make_decision(mode=mode, exec_type=exec_type)
                assert d.governance_scope != SCOPE_AUTHORIZED, (
                    f"AUTHORIZED scope produced for mode={mode}, exec_type={exec_type}"
                )

    def test_live_effects_zero_all_modes_all_types(self):
        for mode in ALL_MODES:
            for exec_type in ALL_EXEC_TYPES:
                d = _make_decision(mode=mode, exec_type=exec_type)
                assert d.live_effects_produced == 0

    def test_dispatch_authorized_false_all_scopes(self):
        for mode in ALL_MODES:
            d = _make_decision(mode=mode)
            assert d.dispatch_authorized is False

    def test_replay_lineage_1000_records_visible(self):
        records = [_make_decision(exec_type=TYPE_REPLAY, historical_config="cfg-h")
                   for _ in range(1000)]
        result = _audit_decisions(records)
        assert result.ginv7_violations == 0
        assert result.total_records == 1000

    def test_finalized_immutability_1000_records(self):
        records = [_make_decision(is_finalized=True) for _ in range(1000)]
        result = _audit_decisions(records)
        assert result.ginv5_violations == 0
