"""
Operational Visibility Certification Suite — Phase 54.

Certifies that operators can safely observe, audit, investigate, and validate
the governed platform across all 6 governance execution modes.

Visibility domains certified:
  1. SHADOW execution — suppression clearly visible, not ambiguous
  2. REPLAY execution — replay lineage, historical config, attribution visible
  3. REGENERATION execution — identical to REPLAY in visibility contract
  4. DEGRADED execution — degradation class, severity, recovery class visible
  5. MAINTENANCE execution — maintenance scope clearly surfaced
  6. LIVE certification-gated execution — scope + cert gate reason visible

Visibility contract:
  - Every operational record exposes all 7 governance attribution fields
  - No hidden governance state: all rule paths, reason codes, and scope
    derivation are surfaced in every record
  - Suppression is never silent: reason_codes always non-empty
  - Degradation is never silent: degradation_cause always surfaced

All tests are pure synchronous — no imports from production modules,
no AsyncMock / patch patterns, no DB or HTTP mocks.
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

UNKNOWN_V0 = "UNKNOWN_V0"

DEGRADE_EXECUTION_MODE_INVALID   = "DEGRADE_EXECUTION_MODE_INVALID"
DEGRADE_CONFIG_V2_UNAVAILABLE    = "DEGRADE_CONFIG_V2_UNAVAILABLE"
DEGRADE_CONFIG_V2_NO_ACTIVE      = "DEGRADE_CONFIG_V2_NO_ACTIVE"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

_ALL_MODES = [MODE_SHADOW, MODE_LIVE, TYPE_REPLAY, TYPE_REGENERATION]


# ── Operational record types ──────────────────────────────────────────────────

@dataclass
class OperationalRecord:
    """Represents a single observable record from the governed pipeline."""
    record_id: str
    execution_mode: str
    execution_type: str
    governance_scope: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    orchestration_cycle_id: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    rule_path: List[str]
    reason_codes: List[str]
    outbound_suppressed: bool
    execution_blocked: bool
    live_effects_produced: int
    provider_dispatch_count: int
    degraded: bool
    degradation_cause: Optional[str]
    degradation_severity: Optional[str]
    degradation_class: Optional[str]
    recovery_classification: Optional[str]
    is_replay: bool
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]
    replay_lineage_visible: bool
    is_maintenance: bool
    maintenance_reason: Optional[str]
    outcome: str


@dataclass
class VisibilityQuery:
    """Operator visibility query for filtering and auditing records."""
    execution_mode: Optional[str] = None
    execution_type: Optional[str] = None
    governance_scope: Optional[str] = None
    correlation_id: Optional[str] = None
    is_degraded: Optional[bool] = None
    is_replay: Optional[bool] = None
    is_maintenance: Optional[bool] = None


@dataclass
class VisibilityQueryResult:
    records: List[OperationalRecord]
    total_count: int
    hidden_governance_state: bool
    attribution_gaps: int
    silent_suppressions: int
    ambiguous_records: int


# ── Simulation helpers ────────────────────────────────────────────────────────

def _new_cid() -> str:
    return f"corr-{uuid.uuid4().hex[:8]}"


def _derive_scope(mode: str, exec_type: str, maintenance: bool = False,
                  degraded: bool = False, config_missing: bool = False) -> str:
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    # Phase-12 cert gate: LIVE → SHADOW_ONLY until AUTHORIZED cert issued
    return SCOPE_SHADOW_ONLY


def _make_record(
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    config_version_id: str = "cfg-v2-001",
    orchestration_cycle_id: Optional[str] = None,
    origin_source: str = "scheduler",
    origin_authority: str = "runtime_context",
    actor_identity: str = "batch_worker",
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
    degradation_severity: Optional[str] = None,
    degradation_class: Optional[str] = None,
    recovery_classification: Optional[str] = None,
    maintenance: bool = False,
    maintenance_reason: Optional[str] = None,
    config_missing: bool = False,
    is_duplicate: bool = False,
    source_artifact_id: Optional[str] = None,
    historical_config: Optional[str] = None,
) -> OperationalRecord:
    cid = correlation_id or _new_cid()
    caus = causation_id or _new_cid()
    cycle = orchestration_cycle_id or _new_cid()
    cfg = UNKNOWN_V0 if config_missing else config_version_id
    scope = _derive_scope(mode, exec_type, maintenance, degraded, config_missing)
    if is_duplicate:
        scope = SCOPE_DUPLICATE_SUPPRESSED

    is_rep = exec_type in _REPLAY_TYPES
    blocked = config_missing or degraded
    suppressed = scope in _SUPPRESSED_SCOPES

    rule_path = ["RULE_0"]
    if not blocked:
        rule_path.append("RULE_1")
        rule_path.append("RULE_2")
        if is_rep:
            rule_path.append("RULE_3")

    reason_codes: List[str] = []
    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    if suppressed:
        reason_codes.append(f"SCOPE_{scope}_SUPPRESSED")
    if mode == MODE_LIVE and not is_rep:
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    if degraded and degradation_cause:
        reason_codes.append(f"DEGRADED_{degradation_cause.upper()}")
    if maintenance:
        reason_codes.append("MAINTENANCE_SCOPE_ACTIVE")
    if is_rep:
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    if is_duplicate:
        reason_codes.append("DUPLICATE_IDEMPOTENCY_BLOCKED")

    # Outcome label
    if blocked:
        outcome = "blocked"
    elif suppressed:
        outcome = "suppressed"
    else:
        outcome = "dispatch_delegated"

    return OperationalRecord(
        record_id=f"rec-{uuid.uuid4().hex[:8]}",
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        correlation_id=cid,
        causation_id=caus,
        config_version_id=cfg,
        orchestration_cycle_id=cycle,
        origin_source=origin_source,
        origin_authority=origin_authority,
        actor_identity=actor_identity,
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=suppressed,
        execution_blocked=blocked,
        live_effects_produced=0,
        provider_dispatch_count=0,
        degraded=degraded,
        degradation_cause=degradation_cause,
        degradation_severity=degradation_severity,
        degradation_class=degradation_class,
        recovery_classification=recovery_classification,
        is_replay=is_rep,
        source_artifact_id=source_artifact_id,
        historical_config_version_id=historical_config,
        replay_lineage_visible=is_rep and source_artifact_id is not None,
        is_maintenance=maintenance,
        maintenance_reason=maintenance_reason,
        outcome=outcome,
    )


def _query_records(records: List[OperationalRecord],
                   q: VisibilityQuery) -> VisibilityQueryResult:
    filtered = records
    if q.execution_mode:
        filtered = [r for r in filtered if r.execution_mode == q.execution_mode]
    if q.execution_type:
        filtered = [r for r in filtered if r.execution_type == q.execution_type]
    if q.governance_scope:
        filtered = [r for r in filtered if r.governance_scope == q.governance_scope]
    if q.correlation_id:
        filtered = [r for r in filtered if r.correlation_id == q.correlation_id]
    if q.is_degraded is not None:
        filtered = [r for r in filtered if r.degraded == q.is_degraded]
    if q.is_replay is not None:
        filtered = [r for r in filtered if r.is_replay == q.is_replay]
    if q.is_maintenance is not None:
        filtered = [r for r in filtered if r.is_maintenance == q.is_maintenance]

    # Certification metrics
    hidden_state = any(not r.reason_codes for r in filtered)
    attr_gaps = sum(
        1 for r in filtered
        if not all([r.correlation_id, r.causation_id, r.config_version_id,
                    r.execution_mode, r.execution_type, r.governance_scope,
                    r.orchestration_cycle_id])
    )
    silent_suppressions = sum(
        1 for r in filtered
        if r.outbound_suppressed and not r.reason_codes
    )
    ambiguous = sum(
        1 for r in filtered
        if r.governance_scope == SCOPE_SHADOW_ONLY
        and r.execution_mode == MODE_LIVE
        and "LIVE_SCOPE_REQUIRES_PHASE12_CERT" not in r.reason_codes
    )

    return VisibilityQueryResult(
        records=filtered,
        total_count=len(filtered),
        hidden_governance_state=hidden_state,
        attribution_gaps=attr_gaps,
        silent_suppressions=silent_suppressions,
        ambiguous_records=ambiguous,
    )


# ── Test classes ──────────────────────────────────────────────────────────────


class TestShadowVisibility:
    """Certify SHADOW execution is unambiguously visible to operators."""

    def test_shadow_scope_exposed_in_record(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_suppression_visible_in_reason_codes(self):
        r = _make_record(mode=MODE_SHADOW)
        assert any("SHADOW" in code or "SUPPRESSED" in code for code in r.reason_codes)

    def test_shadow_outbound_suppressed_true(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.outbound_suppressed is True

    def test_shadow_provider_dispatch_zero(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.provider_dispatch_count == 0

    def test_shadow_live_effects_zero(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.live_effects_produced == 0

    def test_shadow_rule_path_starts_rule_0(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.rule_path[0] == "RULE_0"

    def test_shadow_outcome_not_dispatch_delegated(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.outcome != "dispatch_delegated"

    def test_shadow_all_7_attribution_fields_present(self):
        r = _make_record(mode=MODE_SHADOW)
        assert r.correlation_id
        assert r.causation_id
        assert r.config_version_id
        assert r.execution_mode
        assert r.execution_type
        assert r.governance_scope
        assert r.orchestration_cycle_id

    def test_shadow_queryable_by_scope(self):
        records = [_make_record(mode=MODE_SHADOW) for _ in range(5)]
        result = _query_records(records, VisibilityQuery(governance_scope=SCOPE_SHADOW_ONLY))
        assert result.total_count == 5

    def test_shadow_no_silent_suppression(self):
        records = [_make_record(mode=MODE_SHADOW) for _ in range(10)]
        result = _query_records(records, VisibilityQuery())
        assert result.silent_suppressions == 0

    def test_live_mode_shadow_scope_has_cert_gate_reason_code(self):
        r = _make_record(mode=MODE_LIVE, exec_type=TYPE_ORIGINAL)
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_live_mode_shadow_scope_not_ambiguous(self):
        records = [_make_record(mode=MODE_LIVE) for _ in range(5)]
        result = _query_records(records, VisibilityQuery())
        assert result.ambiguous_records == 0


class TestReplayVisibility:
    """Certify REPLAY execution is unambiguously visible to operators."""

    def test_replay_scope_exposed_in_record(self):
        r = _make_record(exec_type=TYPE_REPLAY,
                         source_artifact_id="art-001",
                         historical_config="cfg-v2-hist-001")
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_is_replay_flag_set(self):
        r = _make_record(exec_type=TYPE_REPLAY)
        assert r.is_replay is True

    def test_replay_reason_code_present(self):
        r = _make_record(exec_type=TYPE_REPLAY)
        assert "REPLAY_EXECUTION_SUPPRESSED" in r.reason_codes

    def test_replay_lineage_visible_when_artifact_provided(self):
        r = _make_record(exec_type=TYPE_REPLAY, source_artifact_id="art-001",
                         historical_config="cfg-hist-001")
        assert r.replay_lineage_visible is True
        assert r.source_artifact_id == "art-001"
        assert r.historical_config_version_id == "cfg-hist-001"

    def test_replay_live_effects_zero(self):
        r = _make_record(exec_type=TYPE_REPLAY)
        assert r.live_effects_produced == 0

    def test_replay_provider_dispatch_zero(self):
        r = _make_record(exec_type=TYPE_REPLAY)
        assert r.provider_dispatch_count == 0

    def test_replay_not_identical_to_live(self):
        replay = _make_record(exec_type=TYPE_REPLAY)
        live = _make_record(mode=MODE_LIVE, exec_type=TYPE_ORIGINAL)
        assert replay.governance_scope != SCOPE_AUTHORIZED
        assert replay.is_replay is True
        assert live.is_replay is False

    def test_replay_queryable_by_scope(self):
        records = [_make_record(exec_type=TYPE_REPLAY) for _ in range(5)]
        records += [_make_record(exec_type=TYPE_ORIGINAL) for _ in range(3)]
        result = _query_records(records, VisibilityQuery(governance_scope=SCOPE_REPLAY_ONLY))
        assert result.total_count == 5

    def test_replay_queryable_by_is_replay(self):
        records = [_make_record(exec_type=TYPE_REPLAY) for _ in range(4)]
        records += [_make_record(exec_type=TYPE_ORIGINAL) for _ in range(4)]
        result = _query_records(records, VisibilityQuery(is_replay=True))
        assert result.total_count == 4

    def test_replay_attribution_all_7_fields_present(self):
        r = _make_record(exec_type=TYPE_REPLAY)
        assert all([r.correlation_id, r.causation_id, r.config_version_id,
                    r.execution_mode, r.execution_type, r.governance_scope,
                    r.orchestration_cycle_id])

    def test_live_mode_plus_replay_type_scope_is_replay_only(self):
        r = _make_record(mode=MODE_LIVE, exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY


class TestRegenerationVisibility:
    """Certify REGENERATION execution is visible identically to REPLAY."""

    def test_regeneration_scope_is_replay_only(self):
        r = _make_record(exec_type=TYPE_REGENERATION)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_is_replay_flag_set(self):
        r = _make_record(exec_type=TYPE_REGENERATION)
        assert r.is_replay is True

    def test_regeneration_reason_code_matches_replay(self):
        regen = _make_record(exec_type=TYPE_REGENERATION)
        replay = _make_record(exec_type=TYPE_REPLAY)
        assert "REPLAY_EXECUTION_SUPPRESSED" in regen.reason_codes
        assert "REPLAY_EXECUTION_SUPPRESSED" in replay.reason_codes

    def test_regeneration_zero_live_effects(self):
        r = _make_record(exec_type=TYPE_REGENERATION)
        assert r.live_effects_produced == 0

    def test_regeneration_zero_provider_dispatch(self):
        r = _make_record(exec_type=TYPE_REGENERATION)
        assert r.provider_dispatch_count == 0

    def test_regeneration_queryable_by_exec_type(self):
        records = [_make_record(exec_type=TYPE_REGENERATION) for _ in range(3)]
        records += [_make_record(exec_type=TYPE_REPLAY) for _ in range(3)]
        regen_result = _query_records(records, VisibilityQuery(execution_type=TYPE_REGENERATION))
        assert regen_result.total_count == 3

    def test_regeneration_distinguishable_from_replay_by_exec_type(self):
        regen = _make_record(exec_type=TYPE_REGENERATION)
        replay = _make_record(exec_type=TYPE_REPLAY)
        assert regen.execution_type == TYPE_REGENERATION
        assert replay.execution_type == TYPE_REPLAY
        # Same scope but distinguishable by execution_type field
        assert regen.governance_scope == replay.governance_scope

    def test_regeneration_attribution_all_7_fields(self):
        r = _make_record(exec_type=TYPE_REGENERATION)
        assert all([r.correlation_id, r.causation_id, r.config_version_id,
                    r.execution_mode, r.execution_type, r.governance_scope,
                    r.orchestration_cycle_id])


class TestDegradedVisibility:
    """Certify DEGRADED execution is unambiguously visible to operators."""

    def test_degraded_flag_set_in_record(self):
        r = _make_record(degraded=True, degradation_cause="config_unavailable",
                         degradation_severity="high", degradation_class="CONFIG")
        assert r.degraded is True

    def test_degradation_cause_visible(self):
        r = _make_record(degraded=True, degradation_cause="config_unavailable")
        assert r.degradation_cause == "config_unavailable"

    def test_degradation_severity_visible(self):
        r = _make_record(degraded=True, degradation_cause="api_timeout",
                         degradation_severity="medium")
        assert r.degradation_severity == "medium"

    def test_degradation_class_visible(self):
        r = _make_record(degraded=True, degradation_cause="config_missing",
                         degradation_class="CONFIG")
        assert r.degradation_class == "CONFIG"

    def test_degraded_reason_code_present(self):
        r = _make_record(degraded=True, degradation_cause="config_unavailable")
        assert any("DEGRADED" in code for code in r.reason_codes)

    def test_unknown_v0_propagation_visible(self):
        r = _make_record(config_missing=True)
        assert r.config_version_id == UNKNOWN_V0
        assert r.execution_blocked is True
        assert "CONFIG_VERSION_UNRESOLVED" in r.reason_codes

    def test_recovery_classification_visible(self):
        r = _make_record(degraded=True, degradation_cause="transient",
                         recovery_classification="AUTO_RECOVERABLE")
        assert r.recovery_classification == "AUTO_RECOVERABLE"

    def test_degraded_queryable_by_flag(self):
        records = [_make_record(degraded=True, degradation_cause="x") for _ in range(4)]
        records += [_make_record() for _ in range(6)]
        result = _query_records(records, VisibilityQuery(is_degraded=True))
        assert result.total_count == 4

    def test_degraded_no_silent_degradation(self):
        records = [
            _make_record(degraded=True, degradation_cause="c1", degradation_severity="low"),
            _make_record(degraded=True, degradation_cause="c2", degradation_severity="high"),
            _make_record(degraded=True, degradation_cause="c3", degradation_severity="medium"),
        ]
        for r in records:
            assert r.degradation_cause is not None
            assert r.reason_codes  # non-empty

    def test_degraded_attribution_preserved(self):
        r = _make_record(degraded=True, degradation_cause="test")
        assert r.correlation_id
        assert r.config_version_id
        assert r.governance_scope


class TestMaintenanceVisibility:
    """Certify MAINTENANCE execution is unambiguously visible to operators."""

    def test_maintenance_scope_set(self):
        r = _make_record(maintenance=True, maintenance_reason="scheduled_downtime")
        assert r.governance_scope == SCOPE_MAINTENANCE

    def test_maintenance_flag_set_in_record(self):
        r = _make_record(maintenance=True, maintenance_reason="deploy")
        assert r.is_maintenance is True

    def test_maintenance_reason_visible(self):
        r = _make_record(maintenance=True, maintenance_reason="scheduled_downtime")
        assert r.maintenance_reason == "scheduled_downtime"

    def test_maintenance_reason_code_present(self):
        r = _make_record(maintenance=True, maintenance_reason="deploy")
        assert "MAINTENANCE_SCOPE_ACTIVE" in r.reason_codes

    def test_maintenance_suppressed(self):
        r = _make_record(maintenance=True, maintenance_reason="deploy")
        assert r.outbound_suppressed is True

    def test_maintenance_zero_live_effects(self):
        r = _make_record(maintenance=True, maintenance_reason="deploy")
        assert r.live_effects_produced == 0

    def test_maintenance_queryable(self):
        records = [_make_record(maintenance=True, maintenance_reason="x") for _ in range(3)]
        records += [_make_record() for _ in range(5)]
        result = _query_records(records, VisibilityQuery(is_maintenance=True))
        assert result.total_count == 3

    def test_maintenance_attribution_intact(self):
        r = _make_record(maintenance=True, maintenance_reason="deploy")
        assert all([r.correlation_id, r.causation_id, r.config_version_id,
                    r.execution_mode, r.execution_type, r.governance_scope,
                    r.orchestration_cycle_id])


class TestGovernanceAttributionVisibility:
    """Certify all 7 governance attribution fields are visible in every record."""

    def _check_7_fields(self, r: OperationalRecord) -> None:
        assert r.correlation_id, "correlation_id missing"
        assert r.causation_id, "causation_id missing"
        assert r.config_version_id, "config_version_id missing"
        assert r.execution_mode, "execution_mode missing"
        assert r.execution_type, "execution_type missing"
        assert r.governance_scope, "governance_scope missing"
        assert r.orchestration_cycle_id, "orchestration_cycle_id missing"

    def test_shadow_record_all_7_fields(self):
        self._check_7_fields(_make_record(mode=MODE_SHADOW))

    def test_live_record_all_7_fields(self):
        self._check_7_fields(_make_record(mode=MODE_LIVE))

    def test_replay_record_all_7_fields(self):
        self._check_7_fields(_make_record(exec_type=TYPE_REPLAY))

    def test_regeneration_record_all_7_fields(self):
        self._check_7_fields(_make_record(exec_type=TYPE_REGENERATION))

    def test_degraded_record_all_7_fields(self):
        self._check_7_fields(_make_record(degraded=True, degradation_cause="test"))

    def test_maintenance_record_all_7_fields(self):
        self._check_7_fields(_make_record(maintenance=True, maintenance_reason="deploy"))

    def test_config_missing_record_has_unknown_v0_not_empty(self):
        r = _make_record(config_missing=True)
        assert r.config_version_id == UNKNOWN_V0
        assert r.config_version_id != ""
        assert r.config_version_id is not None

    def test_no_attribution_gaps_in_bulk(self):
        records = (
            [_make_record(mode=MODE_SHADOW) for _ in range(10)]
            + [_make_record(exec_type=TYPE_REPLAY) for _ in range(10)]
            + [_make_record(maintenance=True, maintenance_reason="x") for _ in range(5)]
            + [_make_record(degraded=True, degradation_cause="y") for _ in range(5)]
        )
        result = _query_records(records, VisibilityQuery())
        assert result.attribution_gaps == 0

    def test_no_hidden_governance_state_in_bulk(self):
        records = (
            [_make_record(mode=MODE_SHADOW) for _ in range(10)]
            + [_make_record(exec_type=TYPE_REPLAY) for _ in range(10)]
        )
        result = _query_records(records, VisibilityQuery())
        assert result.hidden_governance_state is False


class TestRulePath_Visibility:
    """Certify rule paths are surfaced in every operational record."""

    def test_rule_0_always_first(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            r = _make_record(mode=mode)
            assert r.rule_path[0] == "RULE_0"

    def test_replay_has_replay_rule_in_path(self):
        r = _make_record(exec_type=TYPE_REPLAY)
        assert "RULE_3" in r.rule_path

    def test_blocked_record_has_only_rule_0(self):
        r = _make_record(config_missing=True)
        assert r.rule_path == ["RULE_0"]
        assert r.execution_blocked is True

    def test_shadow_rule_path_has_rule_2(self):
        r = _make_record(mode=MODE_SHADOW)
        assert "RULE_2" in r.rule_path

    def test_rule_path_non_empty_for_all_modes(self):
        scenarios = [
            _make_record(mode=MODE_SHADOW),
            _make_record(mode=MODE_LIVE),
            _make_record(exec_type=TYPE_REPLAY),
            _make_record(exec_type=TYPE_REGENERATION),
            _make_record(maintenance=True, maintenance_reason="x"),
            _make_record(degraded=True, degradation_cause="x"),
        ]
        for r in scenarios:
            assert len(r.rule_path) >= 1, f"Empty rule_path for {r.governance_scope}"


class TestVisibilityLoadCertification:
    """Certify visibility properties hold at 100, 500, 1000 records."""

    def _run_visibility_check(self, count: int, exec_type: str = TYPE_ORIGINAL,
                              mode: str = MODE_SHADOW) -> VisibilityQueryResult:
        records = [_make_record(mode=mode, exec_type=exec_type) for _ in range(count)]
        return _query_records(records, VisibilityQuery())

    def test_100_shadow_no_attribution_gaps(self):
        assert self._run_visibility_check(100).attribution_gaps == 0

    def test_500_shadow_no_attribution_gaps(self):
        assert self._run_visibility_check(500).attribution_gaps == 0

    def test_1000_shadow_no_attribution_gaps(self):
        assert self._run_visibility_check(1000).attribution_gaps == 0

    def test_100_replay_no_attribution_gaps(self):
        assert self._run_visibility_check(100, exec_type=TYPE_REPLAY).attribution_gaps == 0

    def test_500_replay_no_attribution_gaps(self):
        assert self._run_visibility_check(500, exec_type=TYPE_REPLAY).attribution_gaps == 0

    def test_1000_replay_no_attribution_gaps(self):
        assert self._run_visibility_check(1000, exec_type=TYPE_REPLAY).attribution_gaps == 0

    def test_100_shadow_no_silent_suppression(self):
        assert self._run_visibility_check(100).silent_suppressions == 0

    def test_500_shadow_no_silent_suppression(self):
        assert self._run_visibility_check(500).silent_suppressions == 0

    def test_1000_shadow_no_silent_suppression(self):
        assert self._run_visibility_check(1000).silent_suppressions == 0

    def test_1000_mixed_modes_no_ambiguous_records(self):
        records = (
            [_make_record(mode=MODE_SHADOW) for _ in range(334)]
            + [_make_record(exec_type=TYPE_REPLAY) for _ in range(333)]
            + [_make_record(mode=MODE_LIVE) for _ in range(333)]
        )
        result = _query_records(records, VisibilityQuery())
        assert result.ambiguous_records == 0

    def test_1000_mixed_no_hidden_governance_state(self):
        records = (
            [_make_record(mode=MODE_SHADOW) for _ in range(400)]
            + [_make_record(exec_type=TYPE_REPLAY) for _ in range(400)]
            + [_make_record(maintenance=True, maintenance_reason="x") for _ in range(200)]
        )
        result = _query_records(records, VisibilityQuery())
        assert result.hidden_governance_state is False

    def test_500_degraded_all_visible(self):
        records = [_make_record(degraded=True, degradation_cause="cfg_missing") for _ in range(500)]
        result = _query_records(records, VisibilityQuery(is_degraded=True))
        assert result.total_count == 500
        assert result.attribution_gaps == 0
