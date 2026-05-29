"""
Config V2 Startup Gap Fix — Phase 59 certification.

Tests for RISK-001 (Config V2 startup gap) and RISK-003 (PostgreSQL startup verification).

Coverage:
  TestConfigVersionRowContract       — dataclass attributes and version_id semantics
  TestConfigVersionRowValidation     — ConfigVersionRow with validate_config_v2
  TestBootstrapWithConfigVersionRow  — initialize_runtime_context using ConfigVersionRow
  TestUnknownV0Preservation          — UNKNOWN_V0 preserved for all failure paths
  TestMultipleActiveConfigs          — multiple ACTIVE rows produce degradation
  TestReplayBehaviorUnchanged        — replay mode scope and attribution unchanged
  TestLoadActiveConfigVersionsUnit   — async DB function with mocked session
  TestVerifyStartupDbStateUnit       — async verification function with mocked session

Async tests use asyncio.run() — no pytest-asyncio dependency (avoids RISK-007).
All pure tests are synchronous.
"""
from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bootstrap._bootstrap_helpers import validate_config_v2
from app.bootstrap._bootstrap_types import (
    DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE,
    DEGRADE_CONFIG_V2_NO_ACTIVE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    STARTUP_CLASS_DEGRADED,
    STARTUP_CLASS_REPLAY_SAFE,
    STARTUP_CLASS_SHADOW_SAFE,
    UNKNOWN_V0,
)
from app.bootstrap.runtime_context import initialize_runtime_context
from app.database import ConfigVersionRow, load_active_config_versions, verify_startup_db_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_config_row(
    version_number: int = 1,
    db_id: int = 1,
    status: str = "ACTIVE",
) -> ConfigVersionRow:
    return ConfigVersionRow(
        version_id=str(version_number),
        id=db_id,
        version_number=version_number,
        status=status,
    )


def _codes() -> List[str]:
    return []


def _make_db_row(id_val: int = 1, version_number: int = 1) -> MagicMock:
    row = MagicMock()
    row.id = id_val
    row.version_number = version_number
    row.status = "ACTIVE"
    return row


# ── TestConfigVersionRowContract ─────────────────────────────────────────────

class TestConfigVersionRowContract:
    def test_version_id_is_string(self):
        row = _make_config_row(version_number=1)
        assert isinstance(row.version_id, str)

    def test_version_id_matches_version_number_as_string(self):
        row = _make_config_row(version_number=3)
        assert row.version_id == "3"

    def test_id_attr_is_integer(self):
        row = _make_config_row(db_id=5)
        assert row.id == 5

    def test_version_number_attr_accessible(self):
        row = _make_config_row(version_number=2)
        assert row.version_number == 2

    def test_status_attr_accessible(self):
        row = _make_config_row(status="ACTIVE")
        assert row.status == "ACTIVE"

    def test_v1_default_version_id_equals_one(self):
        row = _make_config_row(version_number=1, db_id=1)
        assert row.version_id == "1"

    def test_version_id_prioritized_over_id_by_validate_config_v2(self):
        # validate_config_v2 checks version_id first — version_id must win
        row = ConfigVersionRow(version_id="v1", id=99, version_number=1, status="ACTIVE")
        codes = _codes()
        version_id, valid = validate_config_v2([row], codes)
        assert version_id == "v1"
        assert valid is True

    def test_version_id_not_unknown_v0(self):
        row = _make_config_row(version_number=1)
        assert row.version_id != UNKNOWN_V0


# ── TestConfigVersionRowValidation ───────────────────────────────────────────

class TestConfigVersionRowValidation:
    def test_single_active_row_is_valid(self):
        row = _make_config_row()
        codes = _codes()
        version_id, valid = validate_config_v2([row], codes)
        assert valid is True
        assert codes == []

    def test_single_active_row_returns_version_number_string(self):
        row = _make_config_row(version_number=1)
        codes = _codes()
        version_id, valid = validate_config_v2([row], codes)
        assert version_id == "1"
        assert version_id != UNKNOWN_V0

    def test_empty_list_produces_no_active_code(self):
        codes = _codes()
        version_id, valid = validate_config_v2([], codes)
        assert version_id == UNKNOWN_V0
        assert valid is False
        assert DEGRADE_CONFIG_V2_NO_ACTIVE in codes

    def test_two_active_rows_produces_multiple_active_code(self):
        rows = [_make_config_row(1, 1), _make_config_row(2, 2)]
        codes = _codes()
        version_id, valid = validate_config_v2(rows, codes)
        assert version_id == UNKNOWN_V0
        assert valid is False
        assert DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE in codes

    def test_exactly_one_row_no_degradation_codes(self):
        codes = _codes()
        validate_config_v2([_make_config_row()], codes)
        assert codes == []


# ── TestBootstrapWithConfigVersionRow ────────────────────────────────────────

class TestBootstrapWithConfigVersionRow:
    def test_single_active_row_eliminates_degradation_state(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.degradation_state is False

    def test_single_active_row_config_version_id_is_version_number(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(version_number=1)],
        )
        assert ctx.config_version_id == "1"

    def test_single_active_row_config_version_id_not_unknown_v0(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.config_version_id != UNKNOWN_V0

    def test_startup_classification_shadow_safe_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.startup_classification == STARTUP_CLASS_SHADOW_SAFE

    def test_shadow_containment_active_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.shadow_containment_active is True

    def test_live_effects_suppressed_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.live_effects_suppressed is True

    def test_governance_scope_is_shadow_only_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY

    def test_authorized_scope_unreachable_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.governance_scope != "AUTHORIZED"

    def test_live_mode_still_shadow_only_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="LIVE",
            active_configs=[_make_config_row()],
        )
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY

    def test_degradation_codes_empty_with_real_config(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.degradation_codes == []

    def test_startup_correlation_id_is_uuid_shaped(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row()],
        )
        assert ctx.startup_correlation_id
        parts = ctx.startup_correlation_id.split("-")
        assert len(parts) == 5

    def test_log_dict_config_version_id_is_version_number(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(version_number=1)],
        )
        d = ctx.as_log_dict()
        assert d["config_version_id"] == "1"
        assert d["degradation_state"] is False


# ── TestUnknownV0Preservation ────────────────────────────────────────────────

class TestUnknownV0Preservation:
    def test_empty_list_produces_unknown_v0(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert ctx.config_version_id == UNKNOWN_V0

    def test_empty_list_produces_degradation_state(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert ctx.degradation_state is True

    def test_empty_list_startup_classification_is_degraded(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert ctx.startup_classification == STARTUP_CLASS_DEGRADED

    def test_empty_list_includes_no_active_code(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert DEGRADE_CONFIG_V2_NO_ACTIVE in ctx.degradation_codes

    def test_shadow_containment_preserved_during_unknown_v0(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert ctx.shadow_containment_active is True

    def test_live_effects_suppressed_during_unknown_v0(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert ctx.live_effects_suppressed is True

    def test_unknown_v0_observable_in_log_dict(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        d = ctx.as_log_dict()
        assert d["config_version_id"] == UNKNOWN_V0
        assert d["degradation_state"] is True
        assert len(d["degradation_codes"]) > 0

    def test_unknown_v0_is_explicit_string_not_empty(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[],
        )
        assert ctx.config_version_id is not None
        assert ctx.config_version_id != ""
        assert ctx.config_version_id == "UNKNOWN_V0"


# ── TestMultipleActiveConfigs ─────────────────────────────────────────────────

class TestMultipleActiveConfigs:
    def test_two_rows_produces_unknown_v0(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(1, 1), _make_config_row(2, 2)],
        )
        assert ctx.config_version_id == UNKNOWN_V0

    def test_two_rows_produces_multiple_active_degradation_code(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(1, 1), _make_config_row(2, 2)],
        )
        assert DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE in ctx.degradation_codes

    def test_two_rows_degradation_state_is_true(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(1, 1), _make_config_row(2, 2)],
        )
        assert ctx.degradation_state is True

    def test_two_rows_observable_in_log_dict(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(1, 1), _make_config_row(2, 2)],
        )
        d = ctx.as_log_dict()
        assert d["degradation_state"] is True
        assert DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE in d["degradation_codes"]

    def test_two_rows_shadow_containment_still_active(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(1, 1), _make_config_row(2, 2)],
        )
        assert ctx.shadow_containment_active is True

    def test_two_rows_live_effects_still_suppressed(self):
        ctx = initialize_runtime_context(
            execution_mode="SHADOW",
            active_configs=[_make_config_row(1, 1), _make_config_row(2, 2)],
        )
        assert ctx.live_effects_suppressed is True


# ── TestReplayBehaviorUnchanged ───────────────────────────────────────────────

class TestReplayBehaviorUnchanged:
    def test_replay_with_config_row_produces_replay_only_scope(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row()],
        )
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_with_config_row_produces_replay_only_scope(self):
        ctx = initialize_runtime_context(
            execution_mode="REGENERATION",
            active_configs=[_make_config_row()],
        )
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_config_version_id_propagated(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row(version_number=1)],
        )
        assert ctx.config_version_id == "1"

    def test_replay_startup_classification_is_replay_safe(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row()],
        )
        assert ctx.startup_classification == STARTUP_CLASS_REPLAY_SAFE

    def test_replay_shadow_containment_active(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row()],
        )
        assert ctx.shadow_containment_active is True

    def test_replay_live_effects_suppressed(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row()],
        )
        assert ctx.live_effects_suppressed is True

    def test_replay_authorized_scope_unreachable(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row()],
        )
        assert ctx.governance_scope != "AUTHORIZED"

    def test_replay_with_empty_config_yields_replay_scope_and_degradation(self):
        # Replay scope is derived from execution_mode, independent of config presence.
        # Config absence causes degradation, but scope remains REPLAY_ONLY.
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[],
        )
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY
        assert ctx.degradation_state is True
        assert DEGRADE_CONFIG_V2_NO_ACTIVE in ctx.degradation_codes

    def test_replay_no_degradation_with_config_row(self):
        ctx = initialize_runtime_context(
            execution_mode="REPLAY",
            active_configs=[_make_config_row()],
        )
        assert ctx.degradation_state is False
        assert ctx.degradation_codes == []


# ── TestLoadActiveConfigVersionsUnit ─────────────────────────────────────────

class TestLoadActiveConfigVersionsUnit:
    def test_returns_empty_list_on_db_exception(self):
        async def _run():
            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.side_effect = Exception("DB connection refused")
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        result = asyncio.run(_run())
        assert result == []

    def test_db_exception_returns_empty_not_none(self):
        async def _run():
            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.side_effect = Exception("timeout")
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        result = asyncio.run(_run())
        assert result is not None
        assert isinstance(result, list)

    def test_returns_single_config_row_on_one_active(self):
        async def _run():
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [_make_db_row(id_val=1, version_number=1)]

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.return_value = mock_result
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        result = asyncio.run(_run())
        assert len(result) == 1
        assert isinstance(result[0], ConfigVersionRow)

    def test_version_id_set_from_version_number(self):
        async def _run():
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [_make_db_row(id_val=1, version_number=1)]

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.return_value = mock_result
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        result = asyncio.run(_run())
        assert result[0].version_id == "1"

    def test_version_id_is_string_type(self):
        async def _run():
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [_make_db_row(id_val=1, version_number=1)]

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.return_value = mock_result
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        result = asyncio.run(_run())
        assert isinstance(result[0].version_id, str)

    def test_returns_empty_on_no_active_rows(self):
        async def _run():
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.return_value = mock_result
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        result = asyncio.run(_run())
        assert result == []

    def test_result_produces_valid_bootstrap_context(self):
        """End-to-end: DB result → bootstrap context with real config_version_id."""
        async def _run():
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [_make_db_row(id_val=1, version_number=1)]

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.return_value = mock_result
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        active_configs = asyncio.run(_run())
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=active_configs)
        assert ctx.degradation_state is False
        assert ctx.config_version_id == "1"
        assert ctx.config_version_id != UNKNOWN_V0

    def test_empty_result_produces_unknown_v0_context(self):
        """End-to-end: empty DB result → UNKNOWN_V0 degradation in bootstrap."""
        async def _run():
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.return_value = mock_result
                mock_factory.return_value = mock_cm
                return await load_active_config_versions()

        active_configs = asyncio.run(_run())
        ctx = initialize_runtime_context(execution_mode="SHADOW", active_configs=active_configs)
        assert ctx.config_version_id == UNKNOWN_V0
        assert ctx.degradation_state is True


# ── TestVerifyStartupDbStateUnit ──────────────────────────────────────────────

class TestVerifyStartupDbStateUnit:
    def _make_session_with_error(self) -> AsyncMock:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_cm
        mock_cm.__aexit__.return_value = None
        mock_cm.execute.side_effect = Exception("DB down")
        return mock_cm

    def test_returns_dict_with_required_keys(self):
        async def _run():
            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_factory.return_value = self._make_session_with_error()
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert "config_version_registry_exists" in state
        assert "active_config_count" in state
        assert "active_config_version_number" in state
        assert "alembic_current_revision" in state

    def test_registry_exists_false_on_db_error(self):
        async def _run():
            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_factory.return_value = self._make_session_with_error()
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert state["config_version_registry_exists"] is False

    def test_verification_error_key_present_on_db_error(self):
        async def _run():
            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_factory.return_value = self._make_session_with_error()
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert "verification_error" in state

    def test_active_config_count_defaults_to_zero_on_error(self):
        async def _run():
            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_factory.return_value = self._make_session_with_error()
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert state["active_config_count"] == 0

    def test_registry_exists_true_when_table_present(self):
        async def _run():
            call_idx = [0]
            results = []

            # Call 1: information_schema count → 1 (table exists)
            r1 = MagicMock()
            r1.scalar_one.return_value = 1
            results.append(r1)

            # Call 2: active config rows → 1 active row
            r2 = MagicMock()
            r2.fetchall.return_value = [_make_db_row(1, 1)]
            results.append(r2)

            # Call 3: alembic_version
            r3 = MagicMock()
            r3.scalar_one_or_none.return_value = "0003"
            results.append(r3)

            async def _execute(*args, **kwargs):
                idx = call_idx[0]
                call_idx[0] += 1
                return results[idx] if idx < len(results) else MagicMock()

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.side_effect = _execute
                mock_factory.return_value = mock_cm
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert state["config_version_registry_exists"] is True

    def test_active_config_count_one_when_one_active(self):
        async def _run():
            call_idx = [0]
            results = []

            r1 = MagicMock()
            r1.scalar_one.return_value = 1
            results.append(r1)

            r2 = MagicMock()
            r2.fetchall.return_value = [_make_db_row(1, 1)]
            results.append(r2)

            r3 = MagicMock()
            r3.scalar_one_or_none.return_value = "0003"
            results.append(r3)

            async def _execute(*args, **kwargs):
                idx = call_idx[0]
                call_idx[0] += 1
                return results[idx] if idx < len(results) else MagicMock()

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.side_effect = _execute
                mock_factory.return_value = mock_cm
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert state["active_config_count"] == 1

    def test_alembic_revision_set_from_db(self):
        async def _run():
            call_idx = [0]
            results = []

            r1 = MagicMock()
            r1.scalar_one.return_value = 1
            results.append(r1)

            r2 = MagicMock()
            r2.fetchall.return_value = [_make_db_row(1, 1)]
            results.append(r2)

            r3 = MagicMock()
            r3.scalar_one_or_none.return_value = "0003"
            results.append(r3)

            async def _execute(*args, **kwargs):
                idx = call_idx[0]
                call_idx[0] += 1
                return results[idx] if idx < len(results) else MagicMock()

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.side_effect = _execute
                mock_factory.return_value = mock_cm
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert state["alembic_current_revision"] == "0003"

    def test_active_config_version_number_set_when_one_active(self):
        async def _run():
            call_idx = [0]
            results = []

            r1 = MagicMock()
            r1.scalar_one.return_value = 1
            results.append(r1)

            r2 = MagicMock()
            r2.fetchall.return_value = [_make_db_row(1, 1)]
            results.append(r2)

            r3 = MagicMock()
            r3.scalar_one_or_none.return_value = "0003"
            results.append(r3)

            async def _execute(*args, **kwargs):
                idx = call_idx[0]
                call_idx[0] += 1
                return results[idx] if idx < len(results) else MagicMock()

            with patch("app.database.AsyncSessionLocal") as mock_factory:
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_cm
                mock_cm.__aexit__.return_value = None
                mock_cm.execute.side_effect = _execute
                mock_factory.return_value = mock_cm
                return await verify_startup_db_state()

        state = asyncio.run(_run())
        assert state["active_config_version_number"] is not None
