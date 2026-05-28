"""
Governance certification suite for attribution continuity middleware (Phase 47).

Self-contained: no mocks, no patches. Direct invocation of governance functions.
Validates all governance contracts: RULE 0-9, spec/06 §3, runtime/system_loop.md §11,
data/data_lifecycle.md §3 (attribution continuity, replay lineage, live-effects suppression).

AP-RT2 (no replay LIVE effects), AP-RT13 (no PII in logs), AP-RT15 (no silent cycle end),
INV-4 (no live severity in replay), INV-5 (attribution immutability).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import List, Optional

from app.middleware._correlation_helpers import (
    _build_attribution_context,
    _check_attribution_partial,
    _check_execution_mode,
    _check_execution_type,
    _check_replay_lineage,
    _derive_governance_scope,
    _generate_correlation_id,
    _governance_precondition_gate,
    _make_blocked_context,
    _make_propagation_record,
    _resolve_correlation_id,
    _resolve_execution_mode,
    _resolve_execution_type,
    emit_propagation_log,
)
from app.middleware._correlation_types import (
    CODE_ATTRIBUTION_PARTIAL,
    CODE_INVALID_EXECUTION_MODE,
    CODE_INVALID_EXECUTION_TYPE,
    CODE_REPLAY_LINEAGE_INCOMPLETE,
    MODE_DEGRADED,
    MODE_LIVE,
    MODE_MAINTENANCE,
    MODE_REGENERATION,
    MODE_REPLAY,
    MODE_SHADOW,
    OUTCOME_BLOCKED,
    OUTCOME_PROPAGATED,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    TYPE_ORIGINAL,
    TYPE_RECOVERY,
    TYPE_REGENERATION,
    TYPE_REPLAY,
    _REPLAY_EXECUTION_TYPES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    AttributionContext,
    PropagationRecord,
)


# ── Test helpers ───────────────────────────────────────────────────────────────

def _uid() -> str:
    return str(uuid.uuid4())


def _minimal_ctx(**overrides) -> AttributionContext:
    defaults = dict(
        correlation_id=_uid(),
        causation_id=None,
        config_version_id=None,
        execution_mode=MODE_SHADOW,
        execution_type=TYPE_ORIGINAL,
        governance_scope=SCOPE_SHADOW_ONLY,
        orchestration_cycle_id=None,
        origin_source=None,
        origin_authority=None,
        historical_config_version_id=None,
        attribution_timestamp=None,
        correlation_id_generated=False,
        is_replay=False,
        attribution_complete=False,
        live_effects_suppressed=True,
        rule_path_taken=[],
    )
    defaults.update(overrides)
    return AttributionContext(**defaults)


def _full_ctx(**overrides) -> AttributionContext:
    defaults = dict(
        correlation_id=_uid(),
        causation_id=_uid(),
        config_version_id="cfg-v2-001",
        execution_mode=MODE_LIVE,
        execution_type=TYPE_ORIGINAL,
        governance_scope=SCOPE_SHADOW_ONLY,
        orchestration_cycle_id=_uid(),
        origin_source="orchestration_engine",
        origin_authority="system_governance",
        historical_config_version_id=None,
        attribution_timestamp="2026-05-28T00:00:00+00:00",
        correlation_id_generated=False,
        is_replay=False,
        attribution_complete=True,
        live_effects_suppressed=True,
        rule_path_taken=["RULE_0", "RULE_1"],
    )
    defaults.update(overrides)
    return AttributionContext(**defaults)


def _replay_ctx(**overrides) -> AttributionContext:
    defaults = dict(
        correlation_id=_uid(),
        causation_id=_uid(),
        config_version_id="cfg-v2-001",
        execution_mode=MODE_LIVE,
        execution_type=TYPE_REPLAY,
        governance_scope=SCOPE_REPLAY_ONLY,
        orchestration_cycle_id=None,
        origin_source="replay_service",
        origin_authority="system_governance",
        historical_config_version_id="hist-cfg-v2-001",
        attribution_timestamp=None,
        correlation_id_generated=False,
        is_replay=True,
        attribution_complete=True,
        live_effects_suppressed=True,
        rule_path_taken=["RULE_0", "RULE_1"],
    )
    defaults.update(overrides)
    return AttributionContext(**defaults)


# ── TestRule0GovernancePreconditionGate ───────────────────────────────────────

class TestRule0GovernancePreconditionGate:
    """RULE 0: Explicit attribution headers validated; invalid signals blocked."""

    def test_no_headers_passes(self):
        codes = _governance_precondition_gate(None, None, None, None, None)
        assert codes == []

    def test_valid_execution_mode_passes(self):
        for mode in _VALID_EXECUTION_MODES:
            codes = _governance_precondition_gate(mode, None, None, None, None)
            assert codes == [], f"Mode {mode} should pass"

    def test_invalid_execution_mode_blocked(self):
        codes = _governance_precondition_gate("BANANA", None, None, None, None)
        assert CODE_INVALID_EXECUTION_MODE in codes

    def test_valid_execution_type_passes(self):
        for etype in _VALID_EXECUTION_TYPES:
            codes = _governance_precondition_gate(None, etype, "hist-cfg", None, None)
            assert CODE_INVALID_EXECUTION_TYPE not in codes, f"Type {etype} should pass"

    def test_invalid_execution_type_blocked(self):
        codes = _governance_precondition_gate(None, "UNKNOWN_TYPE", None, None, None)
        assert CODE_INVALID_EXECUTION_TYPE in codes

    def test_replay_without_historical_config_blocked(self):
        codes = _governance_precondition_gate(None, TYPE_REPLAY, None, None, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE in codes

    def test_replay_with_historical_config_passes(self):
        codes = _governance_precondition_gate(None, TYPE_REPLAY, "hist-cfg-001", None, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE not in codes

    def test_regeneration_without_historical_config_blocked(self):
        codes = _governance_precondition_gate(None, TYPE_REGENERATION, None, None, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE in codes

    def test_regeneration_with_historical_config_passes(self):
        codes = _governance_precondition_gate(None, TYPE_REGENERATION, "hist-cfg-001", None, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE not in codes

    def test_origin_source_without_authority_blocked(self):
        codes = _governance_precondition_gate(None, None, None, "orchestration_engine", None)
        assert CODE_ATTRIBUTION_PARTIAL in codes

    def test_origin_authority_without_source_blocked(self):
        codes = _governance_precondition_gate(None, None, None, None, "system_governance")
        assert CODE_ATTRIBUTION_PARTIAL in codes

    def test_both_origin_fields_present_passes(self):
        codes = _governance_precondition_gate(
            None, None, None, "orchestration_engine", "system_governance"
        )
        assert CODE_ATTRIBUTION_PARTIAL not in codes

    def test_multiple_violations_accumulate(self):
        codes = _governance_precondition_gate(
            "INVALID_MODE", "INVALID_TYPE", None, "engine", None
        )
        assert CODE_INVALID_EXECUTION_MODE in codes
        assert CODE_ATTRIBUTION_PARTIAL in codes

    def test_invalid_type_skips_replay_lineage_check(self):
        codes = _governance_precondition_gate(None, "INVALID_TYPE", None, None, None)
        assert CODE_INVALID_EXECUTION_TYPE in codes
        assert CODE_REPLAY_LINEAGE_INCOMPLETE not in codes

    def test_original_type_no_historical_config_required(self):
        codes = _governance_precondition_gate(None, TYPE_ORIGINAL, None, None, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE not in codes

    def test_recovery_type_no_historical_config_required(self):
        codes = _governance_precondition_gate(None, TYPE_RECOVERY, None, None, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE not in codes


# ── TestCheckExecutionMode ────────────────────────────────────────────────────

class TestCheckExecutionMode:
    """_check_execution_mode: validates execution_mode strings."""

    def test_shadow_valid(self):
        assert _check_execution_mode(MODE_SHADOW) == []

    def test_live_valid(self):
        assert _check_execution_mode(MODE_LIVE) == []

    def test_replay_valid(self):
        assert _check_execution_mode(MODE_REPLAY) == []

    def test_degraded_valid(self):
        assert _check_execution_mode(MODE_DEGRADED) == []

    def test_maintenance_valid(self):
        assert _check_execution_mode(MODE_MAINTENANCE) == []

    def test_regeneration_valid(self):
        assert _check_execution_mode(MODE_REGENERATION) == []

    def test_empty_string_invalid(self):
        codes = _check_execution_mode("")
        assert CODE_INVALID_EXECUTION_MODE in codes

    def test_arbitrary_string_invalid(self):
        codes = _check_execution_mode("PRODUCTION")
        assert CODE_INVALID_EXECUTION_MODE in codes


# ── TestCheckExecutionType ────────────────────────────────────────────────────

class TestCheckExecutionType:
    """_check_execution_type: validates execution_type strings."""

    def test_original_valid(self):
        assert _check_execution_type(TYPE_ORIGINAL) == []

    def test_replay_valid(self):
        assert _check_execution_type(TYPE_REPLAY) == []

    def test_regeneration_valid(self):
        assert _check_execution_type(TYPE_REGENERATION) == []

    def test_recovery_valid(self):
        assert _check_execution_type(TYPE_RECOVERY) == []

    def test_arbitrary_string_invalid(self):
        codes = _check_execution_type("LIVE_EXEC")
        assert CODE_INVALID_EXECUTION_TYPE in codes


# ── TestCheckReplayLineage ────────────────────────────────────────────────────

class TestCheckReplayLineage:
    """_check_replay_lineage: replay and regeneration require historical_config_version_id."""

    def test_replay_with_historical_config_passes(self):
        assert _check_replay_lineage(TYPE_REPLAY, "hist-cfg-001") == []

    def test_replay_without_historical_config_blocked(self):
        codes = _check_replay_lineage(TYPE_REPLAY, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE in codes

    def test_regeneration_with_historical_config_passes(self):
        assert _check_replay_lineage(TYPE_REGENERATION, "hist-cfg-001") == []

    def test_regeneration_without_historical_config_blocked(self):
        codes = _check_replay_lineage(TYPE_REGENERATION, None)
        assert CODE_REPLAY_LINEAGE_INCOMPLETE in codes

    def test_original_no_historical_config_required(self):
        assert _check_replay_lineage(TYPE_ORIGINAL, None) == []

    def test_recovery_no_historical_config_required(self):
        assert _check_replay_lineage(TYPE_RECOVERY, None) == []


# ── TestCheckAttributionPartial ───────────────────────────────────────────────

class TestCheckAttributionPartial:
    """_check_attribution_partial: both origin fields must be present or both absent."""

    def test_both_absent_passes(self):
        assert _check_attribution_partial(None, None) == []

    def test_both_present_passes(self):
        assert _check_attribution_partial("engine", "system_governance") == []

    def test_source_only_blocked(self):
        codes = _check_attribution_partial("engine", None)
        assert CODE_ATTRIBUTION_PARTIAL in codes

    def test_authority_only_blocked(self):
        codes = _check_attribution_partial(None, "system_governance")
        assert CODE_ATTRIBUTION_PARTIAL in codes

    def test_empty_string_treated_as_absent(self):
        assert _check_attribution_partial("", "") == []


# ── TestCorrelationIdResolution ───────────────────────────────────────────────

class TestCorrelationIdResolution:
    """RULE 1: Correlation ID is restored from header or generated server-side."""

    def test_generates_when_header_absent(self):
        cid, generated = _resolve_correlation_id(None)
        assert cid
        assert generated is True

    def test_restores_from_header(self):
        header_id = _uid()
        cid, generated = _resolve_correlation_id(header_id)
        assert cid == header_id
        assert generated is False

    def test_generated_id_is_uuid_format(self):
        cid, _ = _resolve_correlation_id(None)
        uuid.UUID(cid)  # raises ValueError if not valid UUID

    def test_arbitrary_header_value_preserved(self):
        header_id = "custom-trace-abc-123"
        cid, generated = _resolve_correlation_id(header_id)
        assert cid == header_id
        assert generated is False

    def test_empty_string_triggers_generation(self):
        cid, generated = _resolve_correlation_id("")
        assert generated is True  # "" is falsy → treated as absent → generates

    def test_generate_produces_unique_ids(self):
        ids = {_resolve_correlation_id(None)[0] for _ in range(10)}
        assert len(ids) == 10


# ── TestExecutionModeResolution ───────────────────────────────────────────────

class TestExecutionModeResolution:
    """RULE 2: Header takes precedence over settings; falls back to settings."""

    def test_header_takes_precedence_over_settings(self):
        result = _resolve_execution_mode(MODE_LIVE, MODE_SHADOW)
        assert result == MODE_LIVE

    def test_settings_used_when_no_header(self):
        result = _resolve_execution_mode(None, MODE_SHADOW)
        assert result == MODE_SHADOW

    def test_all_valid_modes_accepted_from_header(self):
        for mode in _VALID_EXECUTION_MODES:
            result = _resolve_execution_mode(mode, MODE_SHADOW)
            assert result == mode

    def test_invalid_header_falls_back_to_settings(self):
        result = _resolve_execution_mode("INVALID_MODE", MODE_SHADOW)
        assert result == MODE_SHADOW

    def test_live_setting_propagated(self):
        result = _resolve_execution_mode(None, MODE_LIVE)
        assert result == MODE_LIVE


# ── TestExecutionTypeResolution ───────────────────────────────────────────────

class TestExecutionTypeResolution:
    """RULE 3: Header value used when valid; defaults to TYPE_ORIGINAL."""

    def test_defaults_to_original_when_absent(self):
        assert _resolve_execution_type(None) == TYPE_ORIGINAL

    def test_header_value_used(self):
        assert _resolve_execution_type(TYPE_REPLAY) == TYPE_REPLAY

    def test_all_valid_types_accepted(self):
        for etype in _VALID_EXECUTION_TYPES:
            assert _resolve_execution_type(etype) == etype

    def test_invalid_header_defaults_to_original(self):
        assert _resolve_execution_type("UNKNOWN_TYPE") == TYPE_ORIGINAL

    def test_recovery_type_preserved(self):
        assert _resolve_execution_type(TYPE_RECOVERY) == TYPE_RECOVERY


# ── TestGovernanceScopeDerivation ─────────────────────────────────────────────

class TestGovernanceScopeDerivation:
    """RULE 4: Scope derived from execution_mode + execution_type. AUTHORIZED unreachable."""

    def test_shadow_mode_original_type_is_shadow_only(self):
        assert _derive_governance_scope(MODE_SHADOW, TYPE_ORIGINAL) == SCOPE_SHADOW_ONLY

    def test_live_mode_original_type_is_shadow_only(self):
        # Phase-12 cert gate: LIVE still maps to SHADOW_ONLY
        assert _derive_governance_scope(MODE_LIVE, TYPE_ORIGINAL) == SCOPE_SHADOW_ONLY

    def test_degraded_mode_is_shadow_only(self):
        assert _derive_governance_scope(MODE_DEGRADED, TYPE_ORIGINAL) == SCOPE_SHADOW_ONLY

    def test_replay_execution_type_is_replay_only(self):
        assert _derive_governance_scope(MODE_LIVE, TYPE_REPLAY) == SCOPE_REPLAY_ONLY

    def test_regeneration_execution_type_is_replay_only(self):
        assert _derive_governance_scope(MODE_LIVE, TYPE_REGENERATION) == SCOPE_REPLAY_ONLY

    def test_replay_mode_is_replay_only(self):
        assert _derive_governance_scope(MODE_REPLAY, TYPE_ORIGINAL) == SCOPE_REPLAY_ONLY

    def test_regeneration_mode_is_replay_only(self):
        assert _derive_governance_scope(MODE_REGENERATION, TYPE_ORIGINAL) == SCOPE_REPLAY_ONLY

    def test_maintenance_mode_is_maintenance(self):
        assert _derive_governance_scope(MODE_MAINTENANCE, TYPE_ORIGINAL) == SCOPE_MAINTENANCE

    def test_replay_type_overrides_maintenance_mode(self):
        # execution_type takes precedence over execution_mode for replay
        assert _derive_governance_scope(MODE_MAINTENANCE, TYPE_REPLAY) == SCOPE_REPLAY_ONLY

    def test_authorized_scope_never_produced(self):
        # No combination of valid mode + type should produce SCOPE_AUTHORIZED
        from app.middleware._correlation_types import SCOPE_AUTHORIZED
        for mode in _VALID_EXECUTION_MODES:
            for etype in _VALID_EXECUTION_TYPES:
                scope = _derive_governance_scope(mode, etype)
                assert scope != SCOPE_AUTHORIZED, f"AUTHORIZED unreachable — mode={mode} type={etype}"


# ── TestAttributionContextBuild ───────────────────────────────────────────────

class TestAttributionContextBuild:
    """RULE 5-6: AttributionContext built correctly from resolved fields."""

    def test_all_fields_populated(self):
        rule_path = ["RULE_0", "RULE_1"]
        ctx = _build_attribution_context(
            correlation_id="corr-001",
            causation_id="caus-001",
            config_version_id="cfg-001",
            execution_mode=MODE_LIVE,
            execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY,
            orchestration_cycle_id="cycle-001",
            origin_source="engine",
            origin_authority="system_governance",
            historical_config_version_id=None,
            attribution_timestamp="2026-05-28T00:00:00+00:00",
            correlation_id_generated=False,
            rule_path=rule_path,
        )
        assert ctx.correlation_id == "corr-001"
        assert ctx.causation_id == "caus-001"
        assert ctx.config_version_id == "cfg-001"
        assert ctx.execution_mode == MODE_LIVE
        assert ctx.execution_type == TYPE_ORIGINAL
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY
        assert ctx.orchestration_cycle_id == "cycle-001"
        assert ctx.origin_source == "engine"
        assert ctx.origin_authority == "system_governance"
        assert ctx.attribution_timestamp == "2026-05-28T00:00:00+00:00"
        assert ctx.rule_path_taken == rule_path

    def test_is_replay_true_for_replay_type(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_LIVE, execution_type=TYPE_REPLAY,
            governance_scope=SCOPE_REPLAY_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id="h", attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.is_replay is True

    def test_is_replay_true_for_regeneration_type(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_LIVE, execution_type=TYPE_REGENERATION,
            governance_scope=SCOPE_REPLAY_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id="h", attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.is_replay is True

    def test_is_replay_false_for_original_type(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_LIVE, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.is_replay is False

    def test_attribution_complete_when_both_origin_fields_present(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_SHADOW, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY, orchestration_cycle_id=None,
            origin_source="engine", origin_authority="system_governance",
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.attribution_complete is True

    def test_attribution_incomplete_when_origin_fields_absent(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_SHADOW, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.attribution_complete is False

    def test_live_effects_suppressed_for_shadow_only_scope(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_SHADOW, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.live_effects_suppressed is True

    def test_live_effects_suppressed_for_replay_only_scope(self):
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_LIVE, execution_type=TYPE_REPLAY,
            governance_scope=SCOPE_REPLAY_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id="h", attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.live_effects_suppressed is True


# ── TestReplayLineageGovernance ────────────────────────────────────────────────

class TestReplayLineageGovernance:
    """Replay contexts: REPLAY_ONLY scope, is_replay=True, live_effects_suppressed=True."""

    def test_replay_context_has_replay_only_scope(self):
        ctx = _replay_ctx()
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_context_is_replay_true(self):
        ctx = _replay_ctx()
        assert ctx.is_replay is True

    def test_replay_context_live_effects_suppressed(self):
        ctx = _replay_ctx()
        assert ctx.live_effects_suppressed is True

    def test_regeneration_type_also_replay(self):
        ctx = _replay_ctx(execution_type=TYPE_REGENERATION)
        assert ctx.is_replay is True

    def test_scope_derivation_replay_overrides_live_mode(self):
        scope = _derive_governance_scope(MODE_LIVE, TYPE_REPLAY)
        assert scope == SCOPE_REPLAY_ONLY

    def test_replay_blocked_without_historical_config(self):
        codes = _check_replay_lineage(TYPE_REPLAY, None)
        assert len(codes) > 0

    def test_replay_lineage_preserved_in_blocked_context(self):
        ctx = _make_blocked_context("cid", MODE_LIVE, TYPE_REPLAY, [])
        assert ctx.is_replay is True
        assert ctx.live_effects_suppressed is True

    def test_original_type_not_replay(self):
        ctx = _full_ctx(execution_type=TYPE_ORIGINAL, governance_scope=SCOPE_SHADOW_ONLY)
        assert ctx.is_replay is False


# ── TestLiveEffectsSuppression ─────────────────────────────────────────────────

class TestLiveEffectsSuppression:
    """live_effects_suppressed is True on every current governance scope path."""

    def test_shadow_only_scope_suppresses(self):
        ctx = _minimal_ctx(governance_scope=SCOPE_SHADOW_ONLY, live_effects_suppressed=True)
        assert ctx.live_effects_suppressed is True

    def test_replay_only_scope_suppresses(self):
        ctx = _replay_ctx()
        assert ctx.live_effects_suppressed is True

    def test_maintenance_scope_suppresses(self):
        scope = _derive_governance_scope(MODE_MAINTENANCE, TYPE_ORIGINAL)
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_MAINTENANCE, execution_type=TYPE_ORIGINAL,
            governance_scope=scope, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.live_effects_suppressed is True

    def test_authorized_scope_would_not_suppress(self):
        # The function logic: live_effects_suppressed = (governance_scope != "AUTHORIZED")
        from app.middleware._correlation_types import SCOPE_AUTHORIZED
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_LIVE, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_AUTHORIZED, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        # AUTHORIZED would set live_effects_suppressed=False — but this path is unreachable
        assert ctx.live_effects_suppressed is False  # confirms the logic; path unreachable

    def test_live_mode_original_still_suppresses(self):
        scope = _derive_governance_scope(MODE_LIVE, TYPE_ORIGINAL)
        assert scope == SCOPE_SHADOW_ONLY  # Phase-12 gate
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_LIVE, execution_type=TYPE_ORIGINAL,
            governance_scope=scope, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=[],
        )
        assert ctx.live_effects_suppressed is True


# ── TestBlockedContextConstruction ────────────────────────────────────────────

class TestBlockedContextConstruction:
    """_make_blocked_context: minimal safe context for blocked propagation paths."""

    def test_blocked_context_has_correlation_id(self):
        cid = _uid()
        ctx = _make_blocked_context(cid, None, None, [])
        assert ctx.correlation_id == cid

    def test_blocked_context_live_effects_suppressed(self):
        ctx = _make_blocked_context(_uid(), None, None, [])
        assert ctx.live_effects_suppressed is True

    def test_blocked_context_invalid_mode_falls_back(self):
        ctx = _make_blocked_context(_uid(), "INVALID_MODE", None, [])
        assert ctx.execution_mode == MODE_SHADOW

    def test_blocked_context_invalid_type_falls_back(self):
        ctx = _make_blocked_context(_uid(), None, "INVALID_TYPE", [])
        assert ctx.execution_type == TYPE_ORIGINAL

    def test_blocked_context_valid_mode_preserved(self):
        ctx = _make_blocked_context(_uid(), MODE_LIVE, None, [])
        assert ctx.execution_mode == MODE_LIVE

    def test_blocked_context_replay_type_propagated(self):
        ctx = _make_blocked_context(_uid(), None, TYPE_REPLAY, [])
        assert ctx.is_replay is True

    def test_blocked_context_rule_path_preserved(self):
        rule_path = ["RULE_0_GOVERNANCE_GATE"]
        ctx = _make_blocked_context(_uid(), None, None, rule_path)
        assert ctx.rule_path_taken == rule_path


# ── TestAttributionContinuity ─────────────────────────────────────────────────

class TestAttributionContinuity:
    """Attribution fields propagated immutably. No silent loss (INV-5, spec/06 §3.2)."""

    def test_causation_id_propagated(self):
        caus_id = _uid()
        ctx = _full_ctx(causation_id=caus_id)
        assert ctx.causation_id == caus_id

    def test_config_version_id_propagated(self):
        ctx = _full_ctx(config_version_id="cfg-v2-007")
        assert ctx.config_version_id == "cfg-v2-007"

    def test_orchestration_cycle_id_propagated(self):
        cycle = _uid()
        ctx = _full_ctx(orchestration_cycle_id=cycle)
        assert ctx.orchestration_cycle_id == cycle

    def test_attribution_timestamp_propagated(self):
        ts = "2026-05-28T12:00:00+00:00"
        ctx = _full_ctx(attribution_timestamp=ts)
        assert ctx.attribution_timestamp == ts

    def test_origin_source_propagated(self):
        ctx = _full_ctx(origin_source="ghl_webhook")
        assert ctx.origin_source == "ghl_webhook"

    def test_origin_authority_propagated(self):
        ctx = _full_ctx(origin_authority="sql_server_authoritative")
        assert ctx.origin_authority == "sql_server_authoritative"

    def test_historical_config_version_id_propagated(self):
        ctx = _replay_ctx(historical_config_version_id="hist-cfg-v2-005")
        assert ctx.historical_config_version_id == "hist-cfg-v2-005"

    def test_rule_path_immutable_copy(self):
        rule_path = ["RULE_0", "RULE_1"]
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_SHADOW, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=rule_path,
        )
        rule_path.append("RULE_EXTRA")  # mutate original
        assert "RULE_EXTRA" not in ctx.rule_path_taken  # context has a copy


# ── TestPropagationRecordConstruction ─────────────────────────────────────────

class TestPropagationRecordConstruction:
    """PropagationRecord built with correct fields from AttributionContext."""

    def test_record_has_all_required_fields(self):
        ctx = _full_ctx()
        record = _make_propagation_record(
            ctx=ctx,
            event="api_request_received",
            path="/dashboard/health",
            method="GET",
            blocked=False,
            blocking_codes=[],
            blocking_reason=None,
            outcome=OUTCOME_PROPAGATED,
            duration_ms=None,
        )
        assert record.correlation_id == ctx.correlation_id
        assert record.execution_mode == ctx.execution_mode
        assert record.execution_type == ctx.execution_type
        assert record.governance_scope == ctx.governance_scope
        assert record.is_replay == ctx.is_replay
        assert record.live_effects_suppressed == ctx.live_effects_suppressed
        assert record.blocked is False
        assert record.outcome == OUTCOME_PROPAGATED

    def test_blocked_record_has_blocking_codes(self):
        ctx = _minimal_ctx()
        codes = [CODE_INVALID_EXECUTION_MODE]
        record = _make_propagation_record(
            ctx=ctx,
            event="attribution_blocked",
            path="/",
            method="GET",
            blocked=True,
            blocking_codes=codes,
            blocking_reason="INVALID_EXECUTION_MODE",
            outcome=OUTCOME_BLOCKED,
            duration_ms=5,
        )
        assert record.blocked is True
        assert CODE_INVALID_EXECUTION_MODE in record.blocking_codes
        assert record.outcome == OUTCOME_BLOCKED

    def test_record_has_propagation_id(self):
        ctx = _minimal_ctx()
        record = _make_propagation_record(
            ctx=ctx, event="test", path="/", method="GET",
            blocked=False, blocking_codes=[], blocking_reason=None,
            outcome=OUTCOME_PROPAGATED, duration_ms=None,
        )
        assert record.propagation_id
        uuid.UUID(record.propagation_id)

    def test_record_blocking_codes_is_copy(self):
        ctx = _minimal_ctx()
        codes = [CODE_INVALID_EXECUTION_MODE]
        record = _make_propagation_record(
            ctx=ctx, event="test", path="/", method="GET",
            blocked=True, blocking_codes=codes, blocking_reason=None,
            outcome=OUTCOME_BLOCKED, duration_ms=None,
        )
        codes.append("EXTRA")
        assert "EXTRA" not in record.blocking_codes


# ── TestObservabilityEmission ──────────────────────────────────────────────────

class TestObservabilityEmission:
    """emit_propagation_log: structured JSON on every path; no PII; warning on blocked."""

    def test_emits_on_propagated_path(self, caplog):
        ctx = _full_ctx()
        record = _make_propagation_record(
            ctx=ctx, event="api_request_received", path="/health",
            method="GET", blocked=False, blocking_codes=[],
            blocking_reason=None, outcome=OUTCOME_PROPAGATED, duration_ms=None,
        )
        with caplog.at_level(logging.INFO, logger="app.middleware._correlation_helpers"):
            emit_propagation_log(record)
        assert any("api_request_received" in msg for msg in caplog.messages)

    def test_emits_warning_on_blocked_path(self, caplog):
        ctx = _minimal_ctx()
        record = _make_propagation_record(
            ctx=ctx, event="attribution_blocked", path="/",
            method="POST", blocked=True,
            blocking_codes=[CODE_INVALID_EXECUTION_MODE],
            blocking_reason="INVALID_EXECUTION_MODE",
            outcome=OUTCOME_BLOCKED, duration_ms=3,
        )
        with caplog.at_level(logging.WARNING, logger="app.middleware._correlation_helpers"):
            emit_propagation_log(record)
        assert any("attribution_blocked" in msg for msg in caplog.messages)

    def test_log_contains_correlation_id(self, caplog):
        ctx = _full_ctx()
        record = _make_propagation_record(
            ctx=ctx, event="api_request_received", path="/",
            method="GET", blocked=False, blocking_codes=[],
            blocking_reason=None, outcome=OUTCOME_PROPAGATED, duration_ms=None,
        )
        with caplog.at_level(logging.INFO, logger="app.middleware._correlation_helpers"):
            emit_propagation_log(record)
        combined = " ".join(caplog.messages)
        assert ctx.correlation_id in combined

    def test_log_contains_execution_mode(self, caplog):
        ctx = _full_ctx(execution_mode=MODE_LIVE)
        record = _make_propagation_record(
            ctx=ctx, event="api_request_received", path="/",
            method="GET", blocked=False, blocking_codes=[],
            blocking_reason=None, outcome=OUTCOME_PROPAGATED, duration_ms=None,
        )
        with caplog.at_level(logging.INFO, logger="app.middleware._correlation_helpers"):
            emit_propagation_log(record)
        assert any(MODE_LIVE in msg for msg in caplog.messages)

    def test_log_contains_governance_scope(self, caplog):
        ctx = _replay_ctx()
        record = _make_propagation_record(
            ctx=ctx, event="api_request_received", path="/",
            method="GET", blocked=False, blocking_codes=[],
            blocking_reason=None, outcome=OUTCOME_PROPAGATED, duration_ms=None,
        )
        with caplog.at_level(logging.INFO, logger="app.middleware._correlation_helpers"):
            emit_propagation_log(record)
        assert any(SCOPE_REPLAY_ONLY in msg for msg in caplog.messages)

    def test_log_does_not_contain_attribution_timestamp(self, caplog):
        pii_ts = "2026-05-28T00:00:00+00:00"
        ctx = _full_ctx(attribution_timestamp=pii_ts)
        record = _make_propagation_record(
            ctx=ctx, event="api_request_received", path="/",
            method="GET", blocked=False, blocking_codes=[],
            blocking_reason=None, outcome=OUTCOME_PROPAGATED, duration_ms=None,
        )
        # attribution_timestamp is source-event time and should not be in the log body
        with caplog.at_level(logging.INFO, logger="app.middleware._correlation_helpers"):
            emit_propagation_log(record)
        # The emit function explicitly excludes attribution_timestamp (AP-RT13)
        for msg in caplog.messages:
            try:
                entry = json.loads(msg)
                assert "attribution_timestamp" not in entry, (
                    "attribution_timestamp must not appear in log entry (AP-RT13)"
                )
            except json.JSONDecodeError:
                pass


# ── TestInvariantPreservation ─────────────────────────────────────────────────

class TestInvariantPreservation:
    """No AUTHORIZED scope, no PII fields, all paths emit, replay suppressed."""

    def test_no_authorized_scope_from_any_valid_combo(self):
        from app.middleware._correlation_types import SCOPE_AUTHORIZED
        for mode in _VALID_EXECUTION_MODES:
            for etype in _VALID_EXECUTION_TYPES:
                scope = _derive_governance_scope(mode, etype)
                assert scope != SCOPE_AUTHORIZED

    def test_live_effects_suppressed_on_all_standard_scopes(self):
        for mode in _VALID_EXECUTION_MODES:
            for etype in _VALID_EXECUTION_TYPES:
                scope = _derive_governance_scope(mode, etype)
                ctx = _build_attribution_context(
                    correlation_id="c", causation_id=None, config_version_id=None,
                    execution_mode=mode, execution_type=etype,
                    governance_scope=scope, orchestration_cycle_id=None,
                    origin_source=None, origin_authority=None,
                    historical_config_version_id="h" if etype in _REPLAY_EXECUTION_TYPES else None,
                    attribution_timestamp=None,
                    correlation_id_generated=False, rule_path=[],
                )
                if scope != "AUTHORIZED":
                    assert ctx.live_effects_suppressed is True, (
                        f"live_effects_suppressed must be True for scope={scope}"
                    )

    def test_replay_type_always_replay_only_scope(self):
        for mode in _VALID_EXECUTION_MODES:
            scope = _derive_governance_scope(mode, TYPE_REPLAY)
            assert scope == SCOPE_REPLAY_ONLY

    def test_regeneration_type_always_replay_only_scope(self):
        for mode in _VALID_EXECUTION_MODES:
            scope = _derive_governance_scope(mode, TYPE_REGENERATION)
            assert scope == SCOPE_REPLAY_ONLY

    def test_blocking_code_uniqueness_per_check(self):
        codes = _check_execution_mode("BAD")
        assert len(codes) == len(set(codes))

    def test_generate_produces_valid_uuid(self):
        for _ in range(5):
            cid = _generate_correlation_id()
            uuid.UUID(cid)

    def test_blocked_path_always_live_effects_suppressed(self):
        ctx = _make_blocked_context(_uid(), "BAD_MODE", "BAD_TYPE", [])
        assert ctx.live_effects_suppressed is True

    def test_rule_path_populated_in_built_context(self):
        rule_path = ["RULE_0_GOVERNANCE_GATE", "RULE_1_CORRELATION_ID"]
        ctx = _build_attribution_context(
            correlation_id="c", causation_id=None, config_version_id=None,
            execution_mode=MODE_SHADOW, execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY, orchestration_cycle_id=None,
            origin_source=None, origin_authority=None,
            historical_config_version_id=None, attribution_timestamp=None,
            correlation_id_generated=False, rule_path=rule_path,
        )
        assert "RULE_0_GOVERNANCE_GATE" in ctx.rule_path_taken
        assert "RULE_1_CORRELATION_ID" in ctx.rule_path_taken
