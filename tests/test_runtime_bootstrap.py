"""
Governance certification suite for app/bootstrap/*.

Self-contained — pure function tests, no DB, no HTTP, no mocks.
All tests are synchronous (no pytest-asyncio dependency).
Pattern mirrors tests/test_router_governance.py.

Coverage:
  TestClassifyExecutionMode         — valid/invalid mode handling, SHADOW fallback
  TestDeriveGovernanceScope         — scope derivation for all modes
  TestClassifyStartup               — startup classification paths
  TestValidateConfigV2              — None / empty / multiple / single cases
  TestCheckAttributionComplete      — complete / incomplete / missing cases
  TestBuildSchedulerTiming          — config sourced / fallback / UNKNOWN_V0
  TestRuntimeBootstrapContextProps  — dataclass properties (is_shadow, is_replay …)
  TestRuntimeBootstrapContextLogDict — as_log_dict shape and no-PII guarantee
  TestInitializeRuntimeContextShadow — SHADOW startup invariants
  TestInitializeRuntimeContextReplay — REPLAY startup invariants
  TestInitializeRuntimeContextLive   — LIVE startup invariants
  TestInitializeRuntimeContextDegrade — degradation code propagation
  TestShadowSafeDefaults            — system never defaults to unrestricted LIVE
  TestConfigV2UNKNOWN_V0Semantics   — UNKNOWN_V0 explicit, not silent
  TestDegradationVisibility         — degradation_state and codes exposed
  TestInvariantPreservation         — architectural invariants checked in bulk
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest

from app.bootstrap._bootstrap_helpers import (
    build_scheduler_timing,
    check_attribution_complete,
    classify_execution_mode,
    classify_startup,
    derive_governance_scope,
    validate_config_v2,
)
from app.bootstrap._bootstrap_types import (
    BOOTSTRAP_MODE_DEGRADED,
    BOOTSTRAP_MODE_LIVE,
    BOOTSTRAP_MODE_MAINTENANCE,
    BOOTSTRAP_MODE_REGENERATION,
    BOOTSTRAP_MODE_REPLAY,
    BOOTSTRAP_MODE_SHADOW,
    DEGRADE_ATTRIBUTION_INCOMPLETE,
    DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE,
    DEGRADE_CONFIG_V2_NO_ACTIVE,
    DEGRADE_CONFIG_V2_UNAVAILABLE,
    DEGRADE_EXECUTION_MODE_INVALID,
    SCOPE_DEGRADED,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    STARTUP_CLASS_DEGRADED,
    STARTUP_CLASS_MAINTENANCE,
    STARTUP_CLASS_REPLAY_SAFE,
    STARTUP_CLASS_SHADOW_SAFE,
    UNKNOWN_V0,
    RuntimeBootstrapContext,
)
from app.bootstrap.runtime_context import initialize_runtime_context


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _codes() -> List[str]:
    return []


def _full_attribution() -> Dict[str, Any]:
    return {
        "origin_source": "test",
        "origin_authority": "unit_test",
        "attribution_timestamp": "2026-05-28T00:00:00+00:00",
    }


def _partial_attribution() -> Dict[str, Any]:
    return {"origin_source": "test"}  # missing origin_authority and timestamp


class _FakeConfig:
    """Minimal Config V2 stand-in with version_id attribute."""
    def __init__(self, version_id: str = "v1.0"):
        self.version_id = version_id


# ── TestClassifyExecutionMode ────────────────────────────────────────────────

class TestClassifyExecutionMode:
    def test_shadow_is_valid(self):
        codes = _codes()
        mode, valid = classify_execution_mode(BOOTSTRAP_MODE_SHADOW, codes)
        assert mode == BOOTSTRAP_MODE_SHADOW
        assert valid is True
        assert codes == []

    def test_live_is_valid(self):
        codes = _codes()
        mode, valid = classify_execution_mode(BOOTSTRAP_MODE_LIVE, codes)
        assert mode == BOOTSTRAP_MODE_LIVE
        assert valid is True
        assert codes == []

    def test_replay_is_valid(self):
        codes = _codes()
        mode, valid = classify_execution_mode(BOOTSTRAP_MODE_REPLAY, codes)
        assert mode == BOOTSTRAP_MODE_REPLAY
        assert valid is True

    def test_regeneration_is_valid(self):
        codes = _codes()
        mode, valid = classify_execution_mode(BOOTSTRAP_MODE_REGENERATION, codes)
        assert mode == BOOTSTRAP_MODE_REGENERATION
        assert valid is True

    def test_degraded_is_valid(self):
        codes = _codes()
        mode, valid = classify_execution_mode(BOOTSTRAP_MODE_DEGRADED, codes)
        assert mode == BOOTSTRAP_MODE_DEGRADED
        assert valid is True

    def test_maintenance_is_valid(self):
        codes = _codes()
        mode, valid = classify_execution_mode(BOOTSTRAP_MODE_MAINTENANCE, codes)
        assert mode == BOOTSTRAP_MODE_MAINTENANCE
        assert valid is True

    def test_invalid_mode_degrades_to_shadow(self):
        codes = _codes()
        mode, valid = classify_execution_mode("INVALID_MODE", codes)
        assert mode == BOOTSTRAP_MODE_SHADOW  # explicit safe default
        assert valid is False

    def test_invalid_mode_appends_degrade_code(self):
        codes = _codes()
        classify_execution_mode("UNKNOWN", codes)
        assert DEGRADE_EXECUTION_MODE_INVALID in codes

    def test_empty_string_degrades_to_shadow(self):
        codes = _codes()
        mode, valid = classify_execution_mode("", codes)
        assert mode == BOOTSTRAP_MODE_SHADOW
        assert valid is False
        assert DEGRADE_EXECUTION_MODE_INVALID in codes

    def test_lowercase_mode_is_invalid(self):
        codes = _codes()
        mode, valid = classify_execution_mode("shadow", codes)
        assert valid is False  # case-sensitive match required

    def test_none_str_representation_is_invalid(self):
        codes = _codes()
        mode, _ = classify_execution_mode("None", codes)
        assert mode == BOOTSTRAP_MODE_SHADOW


# ── TestDeriveGovernanceScope ────────────────────────────────────────────────

class TestDeriveGovernanceScope:
    def test_shadow_maps_to_shadow_only(self):
        assert derive_governance_scope(BOOTSTRAP_MODE_SHADOW) == SCOPE_SHADOW_ONLY

    def test_live_maps_to_shadow_only(self):
        # LIVE → SHADOW_ONLY until Phase-12 cert. Never AUTHORIZED.
        scope = derive_governance_scope(BOOTSTRAP_MODE_LIVE)
        assert scope == SCOPE_SHADOW_ONLY

    def test_replay_maps_to_replay_only(self):
        assert derive_governance_scope(BOOTSTRAP_MODE_REPLAY) == SCOPE_REPLAY_ONLY

    def test_regeneration_maps_to_replay_only(self):
        assert derive_governance_scope(BOOTSTRAP_MODE_REGENERATION) == SCOPE_REPLAY_ONLY

    def test_maintenance_maps_to_maintenance(self):
        assert derive_governance_scope(BOOTSTRAP_MODE_MAINTENANCE) == SCOPE_MAINTENANCE

    def test_degraded_maps_to_degraded(self):
        assert derive_governance_scope(BOOTSTRAP_MODE_DEGRADED) == SCOPE_DEGRADED

    def test_authorized_scope_never_returned(self):
        for mode in [
            BOOTSTRAP_MODE_SHADOW, BOOTSTRAP_MODE_LIVE,
            BOOTSTRAP_MODE_REPLAY, BOOTSTRAP_MODE_REGENERATION,
            BOOTSTRAP_MODE_MAINTENANCE, BOOTSTRAP_MODE_DEGRADED,
        ]:
            assert derive_governance_scope(mode) != "AUTHORIZED"


# ── TestClassifyStartup ──────────────────────────────────────────────────────

class TestClassifyStartup:
    def test_shadow_no_degradation_is_shadow_safe(self):
        result = classify_startup(BOOTSTRAP_MODE_SHADOW, [])
        assert result == STARTUP_CLASS_SHADOW_SAFE

    def test_live_no_degradation_is_shadow_safe(self):
        result = classify_startup(BOOTSTRAP_MODE_LIVE, [])
        assert result == STARTUP_CLASS_SHADOW_SAFE

    def test_replay_no_degradation_is_replay_safe(self):
        result = classify_startup(BOOTSTRAP_MODE_REPLAY, [])
        assert result == STARTUP_CLASS_REPLAY_SAFE

    def test_regeneration_no_degradation_is_replay_safe(self):
        result = classify_startup(BOOTSTRAP_MODE_REGENERATION, [])
        assert result == STARTUP_CLASS_REPLAY_SAFE

    def test_maintenance_no_degradation_is_maintenance(self):
        result = classify_startup(BOOTSTRAP_MODE_MAINTENANCE, [])
        assert result == STARTUP_CLASS_MAINTENANCE

    def test_any_degradation_code_overrides_to_degraded(self):
        result = classify_startup(BOOTSTRAP_MODE_SHADOW, [DEGRADE_CONFIG_V2_NO_ACTIVE])
        assert result == STARTUP_CLASS_DEGRADED

    def test_degradation_overrides_replay_classification(self):
        result = classify_startup(BOOTSTRAP_MODE_REPLAY, [DEGRADE_EXECUTION_MODE_INVALID])
        assert result == STARTUP_CLASS_DEGRADED

    def test_degradation_overrides_maintenance_classification(self):
        result = classify_startup(BOOTSTRAP_MODE_MAINTENANCE, ["SOME_CODE"])
        assert result == STARTUP_CLASS_DEGRADED


# ── TestValidateConfigV2 ─────────────────────────────────────────────────────

class TestValidateConfigV2:
    def test_none_returns_unknown_v0(self):
        codes = _codes()
        version_id, valid = validate_config_v2(None, codes)
        assert version_id == UNKNOWN_V0
        assert valid is False

    def test_none_appends_unavailable_code(self):
        codes = _codes()
        validate_config_v2(None, codes)
        assert DEGRADE_CONFIG_V2_UNAVAILABLE in codes

    def test_empty_list_returns_unknown_v0(self):
        codes = _codes()
        version_id, valid = validate_config_v2([], codes)
        assert version_id == UNKNOWN_V0
        assert valid is False

    def test_empty_list_appends_no_active_code(self):
        codes = _codes()
        validate_config_v2([], codes)
        assert DEGRADE_CONFIG_V2_NO_ACTIVE in codes

    def test_multiple_configs_returns_unknown_v0(self):
        codes = _codes()
        configs = [_FakeConfig("v1"), _FakeConfig("v2")]
        version_id, valid = validate_config_v2(configs, codes)
        assert version_id == UNKNOWN_V0
        assert valid is False

    def test_multiple_configs_appends_multiple_active_code(self):
        codes = _codes()
        validate_config_v2([_FakeConfig("a"), _FakeConfig("b")], codes)
        assert DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE in codes

    def test_single_config_returns_version_id(self):
        codes = _codes()
        version_id, valid = validate_config_v2([_FakeConfig("v3.0")], codes)
        assert version_id == "v3.0"
        assert valid is True
        assert codes == []

    def test_single_config_with_id_attribute_fallback(self):
        class _ConfigById:
            id = "cfg-abc"
        codes = _codes()
        version_id, valid = validate_config_v2([_ConfigById()], codes)
        assert version_id == "cfg-abc"
        assert valid is True

    def test_single_config_string_fallback(self):
        codes = _codes()
        version_id, valid = validate_config_v2(["raw-version-str"], codes)
        assert version_id == "raw-version-str"
        assert valid is True

    def test_no_mutation_of_existing_codes(self):
        codes = ["PRE_EXISTING"]
        validate_config_v2([], codes)
        assert "PRE_EXISTING" in codes
        assert DEGRADE_CONFIG_V2_NO_ACTIVE in codes


# ── TestCheckAttributionComplete ─────────────────────────────────────────────

class TestCheckAttributionComplete:
    def test_full_attribution_is_complete(self):
        assert check_attribution_complete(_full_attribution()) is True

    def test_none_attribution_is_incomplete(self):
        assert check_attribution_complete(None) is False

    def test_empty_dict_is_incomplete(self):
        assert check_attribution_complete({}) is False

    def test_missing_origin_authority_is_incomplete(self):
        d = _full_attribution()
        del d["origin_authority"]
        assert check_attribution_complete(d) is False

    def test_missing_origin_source_is_incomplete(self):
        d = _full_attribution()
        del d["origin_source"]
        assert check_attribution_complete(d) is False

    def test_missing_attribution_timestamp_is_incomplete(self):
        d = _full_attribution()
        del d["attribution_timestamp"]
        assert check_attribution_complete(d) is False

    def test_empty_string_value_is_incomplete(self):
        d = _full_attribution()
        d["origin_source"] = ""
        assert check_attribution_complete(d) is False


# ── TestBuildSchedulerTiming ─────────────────────────────────────────────────

class TestBuildSchedulerTiming:
    def test_no_rule_set_uses_fallbacks(self):
        timing = build_scheduler_timing(None, fallback_hour=9, fallback_minute=30, fallback_timezone="UTC")
        assert timing["trigger_hour"] == 9
        assert timing["trigger_minute"] == 30
        assert timing["timezone_str"] == "UTC"
        assert timing["config_sourced"] is False

    def test_empty_rule_set_uses_fallbacks(self):
        timing = build_scheduler_timing({}, fallback_hour=8, fallback_minute=0, fallback_timezone="US/Central")
        assert timing["trigger_hour"] == 8
        assert timing["trigger_minute"] == 0

    def test_config_v2_values_take_precedence(self):
        rule_set = {
            "outreach_daily_trigger_hour_cst": 14,
            "outreach_daily_trigger_minute_cst": 15,
        }
        timing = build_scheduler_timing(rule_set, fallback_hour=8, fallback_minute=0, fallback_timezone="US/Central")
        assert timing["trigger_hour"] == 14
        assert timing["trigger_minute"] == 15
        assert timing["config_sourced"] is True

    def test_unknown_v0_value_falls_back_to_settings(self):
        rule_set = {"outreach_daily_trigger_hour_cst": UNKNOWN_V0}
        timing = build_scheduler_timing(rule_set, fallback_hour=7, fallback_minute=5, fallback_timezone="UTC")
        assert timing["trigger_hour"] == 7  # UNKNOWN_V0 → settings fallback

    def test_partial_config_uses_fallback_for_missing(self):
        rule_set = {"outreach_daily_trigger_hour_cst": 10}  # minute absent
        timing = build_scheduler_timing(rule_set, fallback_hour=8, fallback_minute=45, fallback_timezone="UTC")
        assert timing["trigger_hour"] == 10
        assert timing["trigger_minute"] == 45  # falls back

    def test_timezone_always_from_fallback(self):
        timing = build_scheduler_timing({"some_key": "val"}, fallback_hour=8, fallback_minute=0, fallback_timezone="America/Chicago")
        assert timing["timezone_str"] == "America/Chicago"


# ── TestRuntimeBootstrapContextProps ─────────────────────────────────────────

class TestRuntimeBootstrapContextProps:
    def _make_ctx(self, mode: str, scope: str, degraded: bool = False) -> RuntimeBootstrapContext:
        return RuntimeBootstrapContext(
            startup_correlation_id=str(uuid.uuid4()),
            execution_mode=mode,
            governance_scope=scope,
            startup_classification=STARTUP_CLASS_SHADOW_SAFE,
            config_version_id=UNKNOWN_V0,
            shadow_containment_active=True,
            live_effects_suppressed=True,
            replay_safe=True,
            attribution_complete=False,
            degradation_state=degraded,
            degradation_codes=[],
            startup_timestamp="2026-05-28T00:00:00+00:00",
        )

    def test_is_shadow_true_for_shadow_mode(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_SHADOW, SCOPE_SHADOW_ONLY)
        assert ctx.is_shadow is True

    def test_is_shadow_false_for_live_mode(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_LIVE, SCOPE_SHADOW_ONLY)
        assert ctx.is_shadow is False

    def test_is_replay_true_for_replay_mode(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_REPLAY, SCOPE_REPLAY_ONLY)
        assert ctx.is_replay is True

    def test_is_replay_true_for_regeneration_mode(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_REGENERATION, SCOPE_REPLAY_ONLY)
        assert ctx.is_replay is True

    def test_is_replay_false_for_shadow_mode(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_SHADOW, SCOPE_SHADOW_ONLY)
        assert ctx.is_replay is False

    def test_is_maintenance_true_for_maintenance_mode(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_MAINTENANCE, SCOPE_MAINTENANCE)
        assert ctx.is_maintenance is True

    def test_is_degraded_reflects_degradation_state(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_SHADOW, SCOPE_SHADOW_ONLY, degraded=True)
        assert ctx.is_degraded is True

    def test_is_degraded_false_when_no_degradation(self):
        ctx = self._make_ctx(BOOTSTRAP_MODE_SHADOW, SCOPE_SHADOW_ONLY, degraded=False)
        assert ctx.is_degraded is False


# ── TestRuntimeBootstrapContextLogDict ───────────────────────────────────────

class TestRuntimeBootstrapContextLogDict:
    def _make_ctx(self) -> RuntimeBootstrapContext:
        return RuntimeBootstrapContext(
            startup_correlation_id="test-corr-id",
            execution_mode=BOOTSTRAP_MODE_SHADOW,
            governance_scope=SCOPE_SHADOW_ONLY,
            startup_classification=STARTUP_CLASS_SHADOW_SAFE,
            config_version_id=UNKNOWN_V0,
            shadow_containment_active=True,
            live_effects_suppressed=True,
            replay_safe=True,
            attribution_complete=False,
            degradation_state=True,
            degradation_codes=[DEGRADE_CONFIG_V2_NO_ACTIVE],
            startup_timestamp="2026-05-28T00:00:00+00:00",
        )

    def test_log_dict_contains_required_governance_fields(self):
        d = self._make_ctx().as_log_dict()
        required = [
            "startup_correlation_id", "execution_mode", "governance_scope",
            "startup_classification", "config_version_id",
            "shadow_containment_active", "live_effects_suppressed",
            "replay_safe", "attribution_complete", "degradation_state",
            "degradation_codes", "startup_timestamp",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_log_dict_no_pii_fields(self):
        d = self._make_ctx().as_log_dict()
        pii_fields = {"email", "phone", "first_name", "last_name", "name",
                      "student_id", "user_id", "UserID", "Email", "PhoneNumber"}
        for f in pii_fields:
            assert f not in d, f"PII field found in log dict: {f}"

    def test_log_dict_degradation_codes_is_list(self):
        d = self._make_ctx().as_log_dict()
        assert isinstance(d["degradation_codes"], list)

    def test_log_dict_startup_correlation_id_matches(self):
        ctx = self._make_ctx()
        d = ctx.as_log_dict()
        assert d["startup_correlation_id"] == "test-corr-id"

    def test_log_dict_config_version_id_is_unknown_v0(self):
        d = self._make_ctx().as_log_dict()
        assert d["config_version_id"] == UNKNOWN_V0


# ── TestInitializeRuntimeContextShadow ───────────────────────────────────────

class TestInitializeRuntimeContextShadow:
    def test_shadow_mode_produces_shadow_only_scope(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_mode_sets_shadow_containment_active(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.shadow_containment_active is True

    def test_shadow_mode_sets_live_effects_suppressed(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.live_effects_suppressed is True

    def test_shadow_mode_replay_safe_is_true(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.replay_safe is True

    def test_shadow_mode_produces_startup_correlation_id(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.startup_correlation_id
        # Must be UUID-shaped (basic check)
        parts = ctx.startup_correlation_id.split("-")
        assert len(parts) == 5

    def test_shadow_mode_no_active_config_yields_unknown_v0(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        assert ctx.config_version_id == UNKNOWN_V0

    def test_shadow_mode_startup_classification_is_shadow_safe_with_no_config(self):
        # With no active config → DEGRADED classification (degradation_codes non-empty)
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        assert ctx.startup_classification == STARTUP_CLASS_DEGRADED

    def test_shadow_mode_with_active_config_is_shadow_safe(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("v1.0")],
        )
        assert ctx.startup_classification == STARTUP_CLASS_SHADOW_SAFE
        assert ctx.config_version_id == "v1.0"

    def test_shadow_startup_correlation_is_unique_per_call(self):
        ctx1 = initialize_runtime_context(execution_mode="SHADOW")
        ctx2 = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx1.startup_correlation_id != ctx2.startup_correlation_id


# ── TestInitializeRuntimeContextReplay ───────────────────────────────────────

class TestInitializeRuntimeContextReplay:
    def test_replay_mode_produces_replay_only_scope(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_FakeConfig("v1")],
        )
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_mode_produces_replay_only_scope(self):
        ctx = initialize_runtime_context(
            execution_mode="REGENERATION",
            active_configs=[_FakeConfig("v1")],
        )
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_mode_replay_safe_is_true(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_FakeConfig("v1")],
        )
        assert ctx.replay_safe is True

    def test_replay_mode_live_effects_suppressed(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_FakeConfig("v1")],
        )
        assert ctx.live_effects_suppressed is True

    def test_replay_mode_startup_classification_is_replay_safe_with_config(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_FakeConfig("v1")],
        )
        assert ctx.startup_classification == STARTUP_CLASS_REPLAY_SAFE


# ── TestInitializeRuntimeContextLive ─────────────────────────────────────────

class TestInitializeRuntimeContextLive:
    def test_live_mode_produces_shadow_only_scope(self):
        ctx = initialize_runtime_context(
            execution_mode="LIVE",
            active_configs=[_FakeConfig("v1")],
        )
        # LIVE → SHADOW_ONLY until Phase-12 cert — never AUTHORIZED
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_shadow_containment_active(self):
        ctx = initialize_runtime_context(execution_mode="LIVE", active_configs=[_FakeConfig("v1")])
        assert ctx.shadow_containment_active is True

    def test_live_mode_live_effects_suppressed(self):
        ctx = initialize_runtime_context(execution_mode="LIVE", active_configs=[_FakeConfig("v1")])
        assert ctx.live_effects_suppressed is True

    def test_live_mode_governance_scope_never_authorized(self):
        ctx = initialize_runtime_context(execution_mode="LIVE", active_configs=[_FakeConfig("v1")])
        assert ctx.governance_scope != "AUTHORIZED"


# ── TestInitializeRuntimeContextDegrade ──────────────────────────────────────

class TestInitializeRuntimeContextDegrade:
    def test_no_active_config_sets_degradation_state(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        assert ctx.degradation_state is True

    def test_no_active_config_includes_no_active_code(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        assert DEGRADE_CONFIG_V2_NO_ACTIVE in ctx.degradation_codes

    def test_multiple_active_configs_sets_degradation(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("a"), _FakeConfig("b")],
        )
        assert ctx.degradation_state is True
        assert DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE in ctx.degradation_codes

    def test_invalid_mode_sets_degradation(self):
        ctx = initialize_runtime_context(execution_mode="NOT_A_MODE")
        assert ctx.degradation_state is True
        assert DEGRADE_EXECUTION_MODE_INVALID in ctx.degradation_codes

    def test_invalid_mode_degrades_execution_mode_to_shadow(self):
        ctx = initialize_runtime_context(execution_mode="BAD_MODE")
        assert ctx.execution_mode == BOOTSTRAP_MODE_SHADOW

    def test_partial_attribution_appends_incomplete_code(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("v1")],
            attribution=_partial_attribution(),
        )
        assert DEGRADE_ATTRIBUTION_INCOMPLETE in ctx.degradation_codes

    def test_full_attribution_does_not_append_incomplete_code(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("v1")],
            attribution=_full_attribution(),
        )
        assert DEGRADE_ATTRIBUTION_INCOMPLETE not in ctx.degradation_codes

    def test_none_attribution_does_not_append_incomplete_code(self):
        # None attribution is non-blocking — only partial (present but incomplete) triggers code
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("v1")],
            attribution=None,
        )
        assert DEGRADE_ATTRIBUTION_INCOMPLETE not in ctx.degradation_codes

    def test_degradation_codes_is_list(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert isinstance(ctx.degradation_codes, list)


# ── TestShadowSafeDefaults ────────────────────────────────────────────────────

class TestShadowSafeDefaults:
    def test_shadow_containment_always_active(self):
        for mode in ["SHADOW", "LIVE", "REPLAY", "REGENERATION", "MAINTENANCE", "DEGRADED"]:
            ctx = initialize_runtime_context(execution_mode=mode, active_configs=[_FakeConfig("v1")])
            assert ctx.shadow_containment_active is True, f"shadow_containment_active False for mode={mode}"

    def test_live_effects_always_suppressed(self):
        for mode in ["SHADOW", "LIVE", "REPLAY", "REGENERATION", "MAINTENANCE", "DEGRADED"]:
            ctx = initialize_runtime_context(execution_mode=mode, active_configs=[_FakeConfig("v1")])
            assert ctx.live_effects_suppressed is True, f"live_effects_suppressed False for mode={mode}"

    def test_authorized_scope_never_returned_for_any_mode(self):
        for mode in ["SHADOW", "LIVE", "REPLAY", "REGENERATION", "MAINTENANCE", "DEGRADED"]:
            ctx = initialize_runtime_context(execution_mode=mode, active_configs=[_FakeConfig("v1")])
            assert ctx.governance_scope != "AUTHORIZED", f"AUTHORIZED scope returned for mode={mode}"

    def test_replay_safe_always_true(self):
        for mode in ["SHADOW", "LIVE", "REPLAY", "REGENERATION", "MAINTENANCE", "DEGRADED"]:
            ctx = initialize_runtime_context(execution_mode=mode, active_configs=[_FakeConfig("v1")])
            assert ctx.replay_safe is True, f"replay_safe False for mode={mode}"


# ── TestConfigV2UNKNOWN_V0Semantics ──────────────────────────────────────────

class TestConfigV2UNKNOWN_V0Semantics:
    def test_unknown_v0_is_explicit_not_empty_string(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        assert ctx.config_version_id == UNKNOWN_V0
        assert ctx.config_version_id != ""
        assert ctx.config_version_id is not None

    def test_unknown_v0_constant_value(self):
        assert UNKNOWN_V0 == "UNKNOWN_V0"

    def test_unknown_v0_propagates_to_degradation_state(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        assert ctx.degradation_state is True

    def test_unknown_v0_in_scheduler_timing_falls_back_to_settings(self):
        rule_set = {
            "outreach_daily_trigger_hour_cst": UNKNOWN_V0,
            "outreach_daily_trigger_minute_cst": UNKNOWN_V0,
        }
        timing = build_scheduler_timing(rule_set, fallback_hour=9, fallback_minute=15, fallback_timezone="UTC")
        assert timing["trigger_hour"] == 9
        assert timing["trigger_minute"] == 15

    def test_single_active_config_eliminates_unknown_v0(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("v2.0")],
        )
        assert ctx.config_version_id == "v2.0"
        assert ctx.config_version_id != UNKNOWN_V0


# ── TestDegradationVisibility ─────────────────────────────────────────────────

class TestDegradationVisibility:
    def test_degradation_state_exposed_in_log_dict(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        d = ctx.as_log_dict()
        assert "degradation_state" in d
        assert d["degradation_state"] is True

    def test_degradation_codes_exposed_in_log_dict(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=[])
        d = ctx.as_log_dict()
        assert "degradation_codes" in d
        assert isinstance(d["degradation_codes"], list)
        assert len(d["degradation_codes"]) > 0

    def test_clean_startup_has_empty_degradation_codes(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_FakeConfig("v1")],
            attribution=_full_attribution(),
        )
        assert ctx.degradation_codes == []
        assert ctx.degradation_state is False

    def test_multiple_degradation_codes_accumulated(self):
        ctx = initialize_runtime_context(
            execution_mode="BAD_MODE",
            active_configs=[],
        )
        assert len(ctx.degradation_codes) >= 2  # invalid mode + no active config


# ── TestInvariantPreservation ─────────────────────────────────────────────────

class TestInvariantPreservation:
    def test_startup_correlation_id_never_empty(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.startup_correlation_id
        assert len(ctx.startup_correlation_id) > 0

    def test_startup_timestamp_is_iso_format(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert "T" in ctx.startup_timestamp  # ISO-8601 has T separator

    def test_execution_mode_never_empty(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.execution_mode

    def test_governance_scope_never_empty(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.governance_scope

    def test_startup_classification_never_empty(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.startup_classification

    def test_config_version_id_never_none(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.config_version_id is not None

    def test_scheduler_timing_always_dict(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert isinstance(ctx.scheduler_timing, dict)

    def test_scheduler_timing_has_required_keys(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert "trigger_hour" in ctx.scheduler_timing
        assert "trigger_minute" in ctx.scheduler_timing
        assert "timezone_str" in ctx.scheduler_timing

    def test_degradation_codes_never_none(self):
        ctx = initialize_runtime_context(execution_mode="SHADOW")
        assert ctx.degradation_codes is not None
        assert isinstance(ctx.degradation_codes, list)
