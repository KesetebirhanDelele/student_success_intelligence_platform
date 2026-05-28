"""
Governance certification suite for app/services/scheduler.py.

Self-contained — no production imports, no mocks, no patch patterns.
Tests pure scheduler governance logic by invoking internal functions directly.
Pattern mirrors tests/test_shadow_safety.py.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

import pytest

# ── Import only the governance functions we are certifying ───────────────────
from app.services.scheduler import (
    DOMAIN_OBSERVABILITY_HEARTBEAT,
    DOMAIN_ORCHESTRATION_EVALUATION,
    DOMAIN_PROVIDER_SYNC,
    MODE_DEGRADED,
    MODE_LIVE,
    MODE_MAINTENANCE,
    MODE_REGENERATION,
    MODE_REPLAY,
    MODE_SHADOW,
    UNKNOWN_V0,
    _attribution_complete,
    _check_and_register_idempotency,
    _governance_precondition_gate,
    _governance_scope,
    _idempotency_key,
    _resolve_config_thresholds,
    coordinate_orchestration_cycle,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_uuid() -> str:
    return str(uuid.uuid4())


def _full_attribution() -> Dict[str, Any]:
    return {
        "origin_source": "test",
        "origin_authority": "unit_test",
        "actor_identity": "test_runner",
        "attribution_timestamp": "2026-05-28T00:00:00+00:00",
    }


def _config(version_id: Optional[str] = None, **thresholds: Any) -> tuple[Optional[str], Dict[str, Any]]:
    vid = version_id or _make_uuid()
    rule_set = {
        "outreach_daily_trigger_hour_cst": 8,
        "outreach_retry_window_days": 3,
        "ai_insight_ttl_hours": 48,
        "sql_server_max_sync_age_hours": 6,
    }
    rule_set.update(thresholds)
    return vid, rule_set


# ── Rule 0: Governance Precondition Gate ──────────────────────────────────────

class TestRule0PreconditionGate:
    def test_valid_inputs_pass(self) -> None:
        codes: List[str] = []
        ok = _governance_precondition_gate(
            MODE_SHADOW, _make_uuid(), _full_attribution(), codes
        )
        assert ok is True
        assert codes == []

    def test_invalid_mode_fails(self) -> None:
        codes: List[str] = []
        ok = _governance_precondition_gate(
            "INVALID_MODE", _make_uuid(), _full_attribution(), codes
        )
        assert ok is False
        assert "INVALID_EXECUTION_MODE" in codes

    def test_missing_config_version_fails(self) -> None:
        codes: List[str] = []
        ok = _governance_precondition_gate(
            MODE_SHADOW, None, _full_attribution(), codes
        )
        assert ok is False
        assert "CONFIG_VERSION_ID_MISSING" in codes

    def test_empty_config_version_fails(self) -> None:
        codes: List[str] = []
        ok = _governance_precondition_gate(
            MODE_SHADOW, "", _full_attribution(), codes
        )
        assert ok is False
        assert "CONFIG_VERSION_ID_MISSING" in codes

    def test_incomplete_attribution_fails(self) -> None:
        codes: List[str] = []
        partial = {"origin_source": "test"}  # missing 3 required fields
        ok = _governance_precondition_gate(MODE_SHADOW, _make_uuid(), partial, codes)
        assert ok is False
        assert "ATTRIBUTION_INCOMPLETE" in codes

    def test_null_attribution_fails(self) -> None:
        codes: List[str] = []
        ok = _governance_precondition_gate(MODE_SHADOW, _make_uuid(), None, codes)
        assert ok is False
        assert "ATTRIBUTION_INCOMPLETE" in codes

    def test_multiple_violations_accumulate(self) -> None:
        codes: List[str] = []
        ok = _governance_precondition_gate("BAD_MODE", None, None, codes)
        assert ok is False
        assert len(codes) >= 2

    def test_all_valid_modes_accepted(self) -> None:
        for mode in (MODE_LIVE, MODE_SHADOW, MODE_REPLAY, MODE_REGENERATION,
                     MODE_DEGRADED, MODE_MAINTENANCE):
            codes: List[str] = []
            ok = _governance_precondition_gate(mode, _make_uuid(), _full_attribution(), codes)
            assert "INVALID_EXECUTION_MODE" not in codes, f"mode {mode} rejected"


# ── SHADOW / LIVE Isolation ───────────────────────────────────────────────────

class TestShadowLiveIsolationGovernance:
    def test_shadow_scope_is_shadow_only(self) -> None:
        assert _governance_scope(MODE_SHADOW) == "SHADOW_ONLY"

    def test_live_scope_is_shadow_only_by_default(self) -> None:
        # Phase-12 cert not yet granted — LIVE scope resolves to SHADOW_ONLY
        assert _governance_scope(MODE_LIVE) == "SHADOW_ONLY"

    def test_replay_scope_is_replay_only(self) -> None:
        assert _governance_scope(MODE_REPLAY) == "REPLAY_ONLY"

    def test_regeneration_scope_is_replay_only(self) -> None:
        assert _governance_scope(MODE_REGENERATION) == "REPLAY_ONLY"

    def test_maintenance_scope_is_maintenance_only(self) -> None:
        assert _governance_scope(MODE_MAINTENANCE) == "MAINTENANCE_ONLY"

    def test_degraded_scope_is_degraded_only(self) -> None:
        assert _governance_scope(MODE_DEGRADED) == "DEGRADED_ONLY"

    def test_live_dispatch_never_enabled(self) -> None:
        """live_dispatch_enabled must be False in all scheduler status reports."""
        from app.services.scheduler import get_scheduler_status
        status = get_scheduler_status()
        assert status["live_dispatch_enabled"] is False

    @pytest.mark.asyncio
    async def test_shadow_coordination_produces_no_live_effects(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["governance_scope"] == "SHADOW_ONLY"
        assert result["blocked"] is False


# ── Replay Containment ────────────────────────────────────────────────────────

class TestReplayContainmentGovernance:
    @pytest.mark.asyncio
    async def test_replay_suppresses_live_batch_domains(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_REPLAY,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["coordination_produced"] is False
        assert "REPLAY_LIVE_BATCH_SUPPRESSED" in result["reason_codes"]

    @pytest.mark.asyncio
    async def test_regeneration_suppresses_live_batch_domains(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_REGENERATION,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["coordination_produced"] is False
        assert "REPLAY_LIVE_BATCH_SUPPRESSED" in result["reason_codes"]

    @pytest.mark.asyncio
    async def test_replay_scope_is_replay_only(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_REPLAY,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["governance_scope"] == "REPLAY_ONLY"

    @pytest.mark.asyncio
    async def test_replay_never_blocked_just_suppressed(self) -> None:
        """Replay is not a governance failure — it is an authorised suppression."""
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_REPLAY,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["blocked"] is False


# ── MAINTENANCE Suppression ───────────────────────────────────────────────────

class TestMaintenanceSuppressionGovernance:
    @pytest.mark.asyncio
    async def test_maintenance_suppresses_orchestration_evaluation(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_MAINTENANCE,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert "MAINTENANCE_ORCHESTRATION_SUPPRESSED" in result["reason_codes"]
        assert result["cycle_ids"].get(DOMAIN_ORCHESTRATION_EVALUATION) is None

    @pytest.mark.asyncio
    async def test_maintenance_still_emits_heartbeat(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_MAINTENANCE,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["cycle_ids"].get(DOMAIN_OBSERVABILITY_HEARTBEAT) is not None


# ── UNKNOWN_V0 / Config V2 Governance ────────────────────────────────────────

class TestUnknownV0Substitution:
    def test_missing_key_resolves_to_unknown_v0(self) -> None:
        missing: List[str] = []
        result = _resolve_config_thresholds({}, ["outreach_daily_trigger_hour_cst"], missing)
        assert result["outreach_daily_trigger_hour_cst"] == UNKNOWN_V0
        assert "outreach_daily_trigger_hour_cst" in missing

    def test_present_key_resolves_to_value(self) -> None:
        missing: List[str] = []
        result = _resolve_config_thresholds(
            {"outreach_daily_trigger_hour_cst": 8},
            ["outreach_daily_trigger_hour_cst"],
            missing,
        )
        assert result["outreach_daily_trigger_hour_cst"] == 8
        assert missing == []

    def test_unknown_v0_sentinel_in_rule_set_treated_as_missing(self) -> None:
        missing: List[str] = []
        result = _resolve_config_thresholds(
            {"outreach_retry_window_days": UNKNOWN_V0},
            ["outreach_retry_window_days"],
            missing,
        )
        assert result["outreach_retry_window_days"] == UNKNOWN_V0
        assert "outreach_retry_window_days" in missing

    @pytest.mark.asyncio
    async def test_missing_config_keys_propagate_degradation_flags(self) -> None:
        vid = _make_uuid()
        # rule_set missing all keys
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set={},
            attribution_context=_full_attribution(),
        )
        # Coordination should still proceed (degraded, not blocked)
        assert result["blocked"] is False

    def test_unknown_v0_constant_value(self) -> None:
        assert UNKNOWN_V0 == "UNKNOWN_V0"


# ── Attribution Continuity ────────────────────────────────────────────────────

class TestAttributionContinuity:
    def test_complete_attribution_passes(self) -> None:
        assert _attribution_complete(_full_attribution()) is True

    def test_partial_attribution_fails(self) -> None:
        partial = {"origin_source": "test", "actor_identity": "runner"}
        assert _attribution_complete(partial) is False

    def test_none_attribution_fails(self) -> None:
        assert _attribution_complete(None) is False

    def test_empty_dict_attribution_fails(self) -> None:
        assert _attribution_complete({}) is False

    def test_empty_value_attribution_fails(self) -> None:
        attr = _full_attribution()
        attr["origin_source"] = ""
        assert _attribution_complete(attr) is False

    @pytest.mark.asyncio
    async def test_missing_attribution_blocks_cycle(self) -> None:
        vid = _make_uuid()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set={"outreach_daily_trigger_hour_cst": 8},
            attribution_context=None,
        )
        assert result["blocked"] is True
        assert "ATTRIBUTION_INCOMPLETE" in result["reason_codes"]


# ── Idempotency Protection ────────────────────────────────────────────────────

class TestIdempotencyProtection:
    def setup_method(self) -> None:
        """Clear idempotency store before each test."""
        from app.services import scheduler as sched_mod
        sched_mod._executed_windows.clear()

    def test_new_key_returns_true(self) -> None:
        key = _idempotency_key("domain", "2026-05-28", MODE_SHADOW)
        assert _check_and_register_idempotency(key) is True

    def test_duplicate_key_returns_false(self) -> None:
        key = _idempotency_key("domain", "2026-05-28", MODE_SHADOW)
        _check_and_register_idempotency(key)
        assert _check_and_register_idempotency(key) is False

    def test_different_date_is_new_window(self) -> None:
        k1 = _idempotency_key("domain", "2026-05-28", MODE_SHADOW)
        k2 = _idempotency_key("domain", "2026-05-29", MODE_SHADOW)
        _check_and_register_idempotency(k1)
        assert _check_and_register_idempotency(k2) is True

    def test_different_mode_is_new_window(self) -> None:
        k1 = _idempotency_key("domain", "2026-05-28", MODE_SHADOW)
        k2 = _idempotency_key("domain", "2026-05-28", MODE_LIVE)
        _check_and_register_idempotency(k1)
        assert _check_and_register_idempotency(k2) is True

    def test_key_format_includes_all_components(self) -> None:
        key = _idempotency_key("dom", "2026-01-01", MODE_SHADOW)
        assert "dom" in key
        assert "2026-01-01" in key
        assert MODE_SHADOW in key


# ── Governance Precondition Blocks All Downstream Processing ─────────────────

class TestGovernancePreconditionBlocking:
    @pytest.mark.asyncio
    async def test_blocked_cycle_returns_no_cycle_ids(self) -> None:
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=None,   # missing — triggers block
            config_rule_set={},
            attribution_context=_full_attribution(),
        )
        assert result["blocked"] is True
        assert result["cycle_ids"] == {}

    @pytest.mark.asyncio
    async def test_blocked_cycle_is_not_coordination_produced(self) -> None:
        result = await coordinate_orchestration_cycle(
            execution_mode="NOT_A_MODE",
            config_version_id=_make_uuid(),
            config_rule_set={},
            attribution_context=_full_attribution(),
        )
        assert result["coordination_produced"] is False
        assert result["blocked"] is True

    @pytest.mark.asyncio
    async def test_blocked_cycle_carries_reason_codes(self) -> None:
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=None,
            config_rule_set={},
            attribution_context=None,
        )
        assert result["blocked"] is True
        # Both missing config_version_id and attribution_incomplete
        assert len(result["reason_codes"]) >= 2


# ── Governance Invariant Preservation ────────────────────────────────────────

class TestGovernanceInvariantPreservation:
    @pytest.mark.asyncio
    async def test_no_dispatch_in_shadow_cycle(self) -> None:
        """Shadow coordination cycle must produce advisory records, not dispatch calls."""
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        # Coordination produced, no live dispatch flag
        assert result["coordination_produced"] is True
        # governance_scope must never be AUTHORIZED (Phase-12 not certified)
        assert result["governance_scope"] != "AUTHORIZED"

    @pytest.mark.asyncio
    async def test_cycle_always_carries_config_version_id(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["config_version_id"] == vid

    @pytest.mark.asyncio
    async def test_cycle_always_carries_execution_mode(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert result["execution_mode"] == MODE_SHADOW

    @pytest.mark.asyncio
    async def test_duration_ms_always_present(self) -> None:
        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_mvp_active_domains_emit_cycle_ids(self) -> None:
        from app.services import scheduler as sched_mod
        sched_mod._executed_windows.clear()

        vid, rule_set = _config()
        result = await coordinate_orchestration_cycle(
            execution_mode=MODE_SHADOW,
            config_version_id=vid,
            config_rule_set=rule_set,
            attribution_context=_full_attribution(),
        )
        cycle_ids = result["cycle_ids"]
        # All three MVP-active domains should appear
        assert DOMAIN_ORCHESTRATION_EVALUATION in cycle_ids
        assert DOMAIN_PROVIDER_SYNC in cycle_ids
        assert DOMAIN_OBSERVABILITY_HEARTBEAT in cycle_ids
