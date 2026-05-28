"""
Governance certification suite for repository persistence layer (Phase 48).

Self-contained: no mocks, no patches, no database connection.
Direct invocation of repository governance helpers.

Validates all repository governance contracts:
  FAD-4   — append-only enforcement (no UPDATE/DELETE on lineage tables)
  FAD-1   — FINALIZED mutation blocked
  IML-1   — attribution immutability; persisted attribution never overwritten
  INV-5   — no persistence without correlation_id
  CID-1   — correlation_id required on every persisted record
  RSV-1   — replay records distinguishable from LIVE
  AP-RT2  — replay cannot overwrite LIVE persistence
  AP-RT13 — PII never logged in PersistenceRecord observability
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from app.repositories._repository_helpers import (
    _check_attribution_complete,
    _check_attribution_fields,
    _check_finalized_protection,
    _check_idempotency,
    _check_replay_live_overwrite,
    _governance_persistence_gate,
    _make_persistence_record,
    emit_persistence_log,
)
from app.repositories._repository_types import (
    CODE_ATTRIBUTION_INCOMPLETE,
    CODE_CORRELATION_ID_MISSING,
    CODE_EXECUTION_MODE_MISSING,
    CODE_EXECUTION_TYPE_MISSING,
    CODE_FINALIZED_MUTATION_BLOCKED,
    CODE_GOVERNANCE_SCOPE_MISSING,
    CODE_IDEMPOTENCY_DUPLICATE,
    CODE_INVALID_EXECUTION_MODE,
    CODE_INVALID_EXECUTION_TYPE,
    CODE_REPLAY_LIVE_OVERWRITE_BLOCKED,
    MODE_DEGRADED,
    MODE_LIVE,
    MODE_MAINTENANCE,
    MODE_REGENERATION,
    MODE_REPLAY,
    MODE_SHADOW,
    PERSIST_CLASS_APPEND_ONLY,
    PERSIST_CLASS_FINALIZED_ARTIFACT,
    PERSIST_CLASS_IDEMPOTENCY_STORE,
    PERSIST_CLASS_MUTABLE_OPERATIONAL,
    PERSIST_OUTCOME_BLOCKED,
    PERSIST_OUTCOME_DUPLICATE_REJECTED,
    PERSIST_OUTCOME_FINALIZED_PROTECTED,
    PERSIST_OUTCOME_SUCCESS,
    REQUIRED_PERSISTENCE_ATTRIBUTION,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    TYPE_ORIGINAL,
    TYPE_RECOVERY,
    TYPE_REGENERATION,
    TYPE_REPLAY,
    _REPLAY_EXECUTION_TYPES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    AttributionFields,
    PersistenceRecord,
)


# ── Test helpers ───────────────────────────────────────────────────────────────

def _uid() -> str:
    return str(uuid.uuid4())


def _live_attribution(**overrides) -> AttributionFields:
    defaults = dict(
        correlation_id=_uid(),
        execution_mode=MODE_SHADOW,
        execution_type=TYPE_ORIGINAL,
        governance_scope=SCOPE_SHADOW_ONLY,
        causation_id=_uid(),
        config_version_id="cfg-v2-001",
        orchestration_cycle_id=_uid(),
        origin_source="orchestration_engine",
        origin_authority="system_governance",
        is_replay=False,
        attribution_complete=True,
    )
    defaults.update(overrides)
    return AttributionFields(**defaults)


def _replay_attribution(**overrides) -> AttributionFields:
    defaults = dict(
        correlation_id=_uid(),
        execution_mode=MODE_LIVE,
        execution_type=TYPE_REPLAY,
        governance_scope=SCOPE_REPLAY_ONLY,
        causation_id=_uid(),
        config_version_id="cfg-v2-001",
        historical_config_version_id="hist-cfg-v2-001",
        origin_source="replay_service",
        origin_authority="system_governance",
        is_replay=True,
        attribution_complete=True,
    )
    defaults.update(overrides)
    return AttributionFields(**defaults)


def _minimal_record(attribution: AttributionFields) -> PersistenceRecord:
    return _make_persistence_record(
        attribution=attribution,
        event="test_event",
        table_name="outreach_history",
        persistence_class=PERSIST_CLASS_APPEND_ONLY,
        blocked=False,
        blocking_codes=[],
        blocking_reason=None,
        outcome=PERSIST_OUTCOME_SUCCESS,
        record_id=None,
        idempotency_key=None,
        duration_ms=5,
    )


# ── TestAttributionFieldsDataclass ────────────────────────────────────────────

class TestAttributionFieldsDataclass:
    """AttributionFields construction and field defaults."""

    def test_required_fields_present(self):
        a = _live_attribution()
        assert a.correlation_id
        assert a.execution_mode
        assert a.execution_type
        assert a.governance_scope

    def test_is_replay_default_false(self):
        a = AttributionFields(
            correlation_id=_uid(),
            execution_mode=MODE_SHADOW,
            execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY,
        )
        assert a.is_replay is False

    def test_replay_attribution_is_replay_true(self):
        a = _replay_attribution()
        assert a.is_replay is True

    def test_optional_fields_default_none(self):
        a = AttributionFields(
            correlation_id=_uid(),
            execution_mode=MODE_SHADOW,
            execution_type=TYPE_ORIGINAL,
            governance_scope=SCOPE_SHADOW_ONLY,
        )
        assert a.causation_id is None
        assert a.config_version_id is None
        assert a.orchestration_cycle_id is None
        assert a.origin_source is None
        assert a.origin_authority is None
        assert a.historical_config_version_id is None


# ── TestCheckAttributionFields ────────────────────────────────────────────────

class TestCheckAttributionFields:
    """_check_attribution_fields: validates governance attribution for persistence."""

    def test_complete_attribution_passes(self):
        a = _live_attribution()
        codes = _check_attribution_fields(a)
        assert codes == []

    def test_missing_correlation_id_blocked(self):
        a = _live_attribution(correlation_id="")
        codes = _check_attribution_fields(a)
        assert CODE_CORRELATION_ID_MISSING in codes

    def test_missing_execution_mode_blocked(self):
        a = _live_attribution(execution_mode="")
        codes = _check_attribution_fields(a)
        assert CODE_EXECUTION_MODE_MISSING in codes

    def test_invalid_execution_mode_blocked(self):
        a = _live_attribution(execution_mode="BANANA")
        codes = _check_attribution_fields(a)
        assert CODE_INVALID_EXECUTION_MODE in codes

    def test_missing_execution_type_blocked(self):
        a = _live_attribution(execution_type="")
        codes = _check_attribution_fields(a)
        assert CODE_EXECUTION_TYPE_MISSING in codes

    def test_invalid_execution_type_blocked(self):
        a = _live_attribution(execution_type="UNKNOWN")
        codes = _check_attribution_fields(a)
        assert CODE_INVALID_EXECUTION_TYPE in codes

    def test_missing_governance_scope_blocked(self):
        a = _live_attribution(governance_scope="")
        codes = _check_attribution_fields(a)
        assert CODE_GOVERNANCE_SCOPE_MISSING in codes

    def test_all_valid_modes_pass(self):
        for mode in _VALID_EXECUTION_MODES:
            a = _live_attribution(execution_mode=mode)
            codes = _check_attribution_fields(a)
            assert CODE_INVALID_EXECUTION_MODE not in codes, f"Mode {mode} should pass"

    def test_all_valid_types_pass(self):
        for etype in _VALID_EXECUTION_TYPES:
            a = _live_attribution(execution_type=etype)
            codes = _check_attribution_fields(a)
            assert CODE_INVALID_EXECUTION_TYPE not in codes, f"Type {etype} should pass"


# ── TestCheckAttributionComplete ──────────────────────────────────────────────

class TestCheckAttributionComplete:
    """_check_attribution_complete: four required fields determine completeness."""

    def test_all_required_fields_present_true(self):
        a = _live_attribution()
        assert _check_attribution_complete(a) is True

    def test_missing_correlation_id_false(self):
        a = _live_attribution(correlation_id="")
        assert _check_attribution_complete(a) is False

    def test_missing_execution_mode_false(self):
        a = _live_attribution(execution_mode="")
        assert _check_attribution_complete(a) is False

    def test_missing_execution_type_false(self):
        a = _live_attribution(execution_type="")
        assert _check_attribution_complete(a) is False

    def test_missing_governance_scope_false(self):
        a = _live_attribution(governance_scope="")
        assert _check_attribution_complete(a) is False

    def test_required_fields_constant_has_four_elements(self):
        assert len(REQUIRED_PERSISTENCE_ATTRIBUTION) == 4

    def test_replay_attribution_complete(self):
        a = _replay_attribution()
        assert _check_attribution_complete(a) is True


# ── TestCheckFinalizedProtection ──────────────────────────────────────────────

class TestCheckFinalizedProtection:
    """_check_finalized_protection: FINALIZED mutation blocked (FAD-1, INV-6)."""

    def test_not_finalized_passes(self):
        codes = _check_finalized_protection(False, "ai_insights", 1)
        assert codes == []

    def test_finalized_blocked(self):
        codes = _check_finalized_protection(True, "ai_insights", 1)
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_finalized_no_record_id_still_blocked(self):
        codes = _check_finalized_protection(True, "ai_insights", None)
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_not_finalized_any_table_passes(self):
        for table in ["outreach_history", "state_transition_log", "processed_events"]:
            codes = _check_finalized_protection(False, table, None)
            assert codes == [], f"Table {table} non-finalized should pass"

    def test_finalized_returns_exactly_one_code(self):
        codes = _check_finalized_protection(True, "ai_insights", 42)
        assert len(codes) == 1
        assert codes[0] == CODE_FINALIZED_MUTATION_BLOCKED


# ── TestCheckReplayLiveOverwrite ──────────────────────────────────────────────

class TestCheckReplayLiveOverwrite:
    """_check_replay_live_overwrite: replay cannot overwrite LIVE records (RSV-1, AP-RT2)."""

    def test_replay_over_live_blocked(self):
        codes = _check_replay_live_overwrite(is_replay=True, target_is_live=True)
        assert CODE_REPLAY_LIVE_OVERWRITE_BLOCKED in codes

    def test_replay_over_replay_allowed(self):
        codes = _check_replay_live_overwrite(is_replay=True, target_is_live=False)
        assert codes == []

    def test_live_over_live_allowed(self):
        codes = _check_replay_live_overwrite(is_replay=False, target_is_live=True)
        assert codes == []

    def test_live_over_replay_allowed(self):
        codes = _check_replay_live_overwrite(is_replay=False, target_is_live=False)
        assert codes == []

    def test_replay_overwrite_returns_exactly_one_code(self):
        codes = _check_replay_live_overwrite(is_replay=True, target_is_live=True)
        assert len(codes) == 1


# ── TestCheckIdempotency ──────────────────────────────────────────────────────

class TestCheckIdempotency:
    """_check_idempotency: LIVE duplicate rejected; replay duplication permitted (RSV-1)."""

    def test_new_key_original_passes(self):
        store: set = set()
        codes = _check_idempotency("key-abc", store, TYPE_ORIGINAL)
        assert codes == []

    def test_duplicate_key_original_blocked(self):
        store = {"key-abc"}
        codes = _check_idempotency("key-abc", store, TYPE_ORIGINAL)
        assert CODE_IDEMPOTENCY_DUPLICATE in codes

    def test_duplicate_key_replay_allowed(self):
        store = {"key-abc"}
        codes = _check_idempotency("key-abc", store, TYPE_REPLAY)
        assert codes == []

    def test_duplicate_key_regeneration_allowed(self):
        store = {"key-abc"}
        codes = _check_idempotency("key-abc", store, TYPE_REGENERATION)
        assert codes == []

    def test_none_key_passes(self):
        store = {"key-abc"}
        codes = _check_idempotency(None, store, TYPE_ORIGINAL)
        assert codes == []

    def test_recovery_type_duplicate_blocked(self):
        store = {"key-abc"}
        codes = _check_idempotency("key-abc", store, TYPE_RECOVERY)
        assert CODE_IDEMPOTENCY_DUPLICATE in codes


# ── TestGovernancePersistenceGate ─────────────────────────────────────────────

class TestGovernancePersistenceGate:
    """_governance_persistence_gate: RULE 0 combined gate for all persistence ops."""

    def test_complete_attribution_passes(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
        )
        assert codes == []

    def test_missing_correlation_id_blocked(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(correlation_id=""),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
        )
        assert CODE_CORRELATION_ID_MISSING in codes

    def test_finalized_blocked(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="ai_insights",
            is_finalized=True,
        )
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_replay_over_live_blocked(self):
        codes = _governance_persistence_gate(
            attribution=_replay_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
            target_is_live=True,
        )
        assert CODE_REPLAY_LIVE_OVERWRITE_BLOCKED in codes

    def test_idempotency_duplicate_blocked(self):
        store = {"idem-key-001"}
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key="idem-key-001",
            idempotency_store=store,
            table_name="outreach_history",
        )
        assert CODE_IDEMPOTENCY_DUPLICATE in codes

    def test_multiple_violations_accumulate(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(correlation_id="", execution_mode="INVALID"),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="ai_insights",
            is_finalized=True,
        )
        assert CODE_CORRELATION_ID_MISSING in codes
        assert CODE_INVALID_EXECUTION_MODE in codes
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_replay_attribution_passes_gate(self):
        codes = _governance_persistence_gate(
            attribution=_replay_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
            target_is_live=False,
        )
        assert codes == []

    def test_new_idempotency_key_passes(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key="new-unique-key",
            idempotency_store=set(),
            table_name="outreach_history",
        )
        assert codes == []


# ── TestPersistenceRecordConstruction ────────────────────────────────────────

class TestPersistenceRecordConstruction:
    """_make_persistence_record: all fields populated, PII excluded."""

    def test_record_has_all_required_fields(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.persistence_id
        assert r.timestamp
        assert r.event == "test_event"
        assert r.table_name == "outreach_history"
        assert r.correlation_id == a.correlation_id
        assert r.execution_mode == a.execution_mode
        assert r.execution_type == a.execution_type
        assert r.governance_scope == a.governance_scope
        assert r.is_replay == a.is_replay
        assert r.outcome == PERSIST_OUTCOME_SUCCESS
        assert r.blocked is False

    def test_blocked_record_has_blocking_codes(self):
        a = _live_attribution()
        r = _make_persistence_record(
            attribution=a,
            event="test_blocked",
            table_name="outreach_history",
            persistence_class=PERSIST_CLASS_APPEND_ONLY,
            blocked=True,
            blocking_codes=[CODE_FINALIZED_MUTATION_BLOCKED],
            blocking_reason=CODE_FINALIZED_MUTATION_BLOCKED,
            outcome=PERSIST_OUTCOME_BLOCKED,
            record_id=None,
            idempotency_key=None,
            duration_ms=1,
        )
        assert r.blocked is True
        assert CODE_FINALIZED_MUTATION_BLOCKED in r.blocking_codes
        assert r.blocking_reason == CODE_FINALIZED_MUTATION_BLOCKED

    def test_persistence_id_is_unique(self):
        a = _live_attribution()
        ids = {_minimal_record(a).persistence_id for _ in range(10)}
        assert len(ids) == 10

    def test_blocking_codes_is_copy(self):
        codes = [CODE_FINALIZED_MUTATION_BLOCKED]
        a = _live_attribution()
        r = _make_persistence_record(
            attribution=a,
            event="test",
            table_name="ai_insights",
            persistence_class=PERSIST_CLASS_FINALIZED_ARTIFACT,
            blocked=True,
            blocking_codes=codes,
            blocking_reason=codes[0],
            outcome=PERSIST_OUTCOME_BLOCKED,
            record_id=None,
            idempotency_key=None,
            duration_ms=1,
        )
        codes.append("EXTRA")
        assert "EXTRA" not in r.blocking_codes

    def test_attribution_complete_derived_correctly(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.attribution_complete is True

    def test_incomplete_attribution_reflected_in_record(self):
        a = _live_attribution(correlation_id="")
        r = _minimal_record(a)
        assert r.attribution_complete is False

    def test_replay_context_preserved(self):
        a = _replay_attribution()
        r = _minimal_record(a)
        assert r.is_replay is True
        assert r.governance_scope == SCOPE_REPLAY_ONLY


# ── TestObservabilityEmission ─────────────────────────────────────────────────

class TestObservabilityEmission:
    """emit_persistence_log: structured log emitted; PII excluded; warning on blocked."""

    def test_emits_on_success_path(self, caplog):
        a = _live_attribution()
        r = _minimal_record(a)
        with caplog.at_level(logging.INFO, logger="app.repositories._repository_helpers"):
            emit_persistence_log(r)
        assert any("test_event" in m for m in caplog.messages)

    def test_emits_warning_on_blocked_path(self, caplog):
        a = _live_attribution()
        r = _make_persistence_record(
            attribution=a,
            event="blocked_event",
            table_name="outreach_history",
            persistence_class=PERSIST_CLASS_APPEND_ONLY,
            blocked=True,
            blocking_codes=[CODE_CORRELATION_ID_MISSING],
            blocking_reason=CODE_CORRELATION_ID_MISSING,
            outcome=PERSIST_OUTCOME_BLOCKED,
            record_id=None,
            idempotency_key=None,
            duration_ms=1,
        )
        with caplog.at_level(logging.WARNING, logger="app.repositories._repository_helpers"):
            emit_persistence_log(r)
        warn_messages = [m for m in caplog.messages if "blocked_event" in m]
        assert warn_messages

    def test_log_contains_correlation_id(self, caplog):
        a = _live_attribution()
        r = _minimal_record(a)
        with caplog.at_level(logging.INFO, logger="app.repositories._repository_helpers"):
            emit_persistence_log(r)
        combined = " ".join(caplog.messages)
        assert a.correlation_id in combined

    def test_log_contains_governance_scope(self, caplog):
        a = _live_attribution()
        r = _minimal_record(a)
        with caplog.at_level(logging.INFO, logger="app.repositories._repository_helpers"):
            emit_persistence_log(r)
        assert any(SCOPE_SHADOW_ONLY in m for m in caplog.messages)

    def test_log_does_not_contain_pii_keys(self, caplog):
        a = _live_attribution()
        r = _minimal_record(a)
        with caplog.at_level(logging.INFO, logger="app.repositories._repository_helpers"):
            emit_persistence_log(r)
        combined = " ".join(caplog.messages)
        # PII keys must not appear in log entries
        for pii_key in ("email", "phone", "first_name", "last_name", "PhoneNumber", "Email"):
            assert pii_key not in combined, f"PII key '{pii_key}' found in log"

    def test_finalized_protected_emits_warning(self, caplog):
        a = _live_attribution()
        r = _make_persistence_record(
            attribution=a,
            event="finalized_protected_event",
            table_name="ai_insights",
            persistence_class=PERSIST_CLASS_FINALIZED_ARTIFACT,
            blocked=True,
            blocking_codes=[CODE_FINALIZED_MUTATION_BLOCKED],
            blocking_reason=CODE_FINALIZED_MUTATION_BLOCKED,
            outcome=PERSIST_OUTCOME_FINALIZED_PROTECTED,
            record_id=42,
            idempotency_key=None,
            duration_ms=1,
        )
        with caplog.at_level(logging.WARNING, logger="app.repositories._repository_helpers"):
            emit_persistence_log(r)
        warn_msgs = [m for m in caplog.messages if "finalized_protected_event" in m]
        assert warn_msgs


# ── TestAppendOnlyGovernance ──────────────────────────────────────────────────

class TestAppendOnlyGovernance:
    """Governance contracts for append-only lineage tables (FAD-4, IML-1)."""

    def test_outreach_history_pass_returns_empty_codes(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
        )
        assert codes == []

    def test_state_transition_pass_returns_empty_codes(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="state_transition_log",
        )
        assert codes == []

    def test_append_only_gate_does_not_block_replay_append(self):
        # Replay can append new records; it cannot overwrite LIVE ones
        codes = _governance_persistence_gate(
            attribution=_replay_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
            target_is_live=False,  # appending a new row, not overwriting
        )
        assert codes == []

    def test_append_only_gate_blocks_replay_live_overwrite(self):
        codes = _governance_persistence_gate(
            attribution=_replay_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="outreach_history",
            target_is_live=True,
        )
        assert CODE_REPLAY_LIVE_OVERWRITE_BLOCKED in codes

    def test_replay_records_tagged_is_replay_true(self):
        a = _replay_attribution()
        r = _minimal_record(a)
        assert r.is_replay is True

    def test_live_records_tagged_is_replay_false(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.is_replay is False

    def test_replay_scope_is_replay_only(self):
        a = _replay_attribution()
        assert a.governance_scope == SCOPE_REPLAY_ONLY

    def test_live_scope_is_shadow_only(self):
        a = _live_attribution()
        assert a.governance_scope == SCOPE_SHADOW_ONLY


# ── TestFinalizedArtifactGovernance ───────────────────────────────────────────

class TestFinalizedArtifactGovernance:
    """FINALIZED artifact immutability (FAD-1, INV-1, INV-6, IML-1)."""

    def test_not_finalized_permits_write(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="ai_insights",
            is_finalized=False,
        )
        assert codes == []

    def test_finalized_blocks_write(self):
        codes = _governance_persistence_gate(
            attribution=_live_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="ai_insights",
            is_finalized=True,
        )
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_finalized_replay_still_blocked(self):
        # Replay cannot overwrite FINALIZED artifacts either
        codes = _governance_persistence_gate(
            attribution=_replay_attribution(),
            idempotency_key=None,
            idempotency_store=set(),
            table_name="ai_insights",
            is_finalized=True,
        )
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_finalized_blocking_code_consistent(self):
        codes = _check_finalized_protection(True, "ai_insights", 99)
        assert codes == [CODE_FINALIZED_MUTATION_BLOCKED]

    def test_finalized_protected_outcome_in_record(self):
        a = _live_attribution()
        r = _make_persistence_record(
            attribution=a,
            event="ai_insight_finalize_protected",
            table_name="ai_insights",
            persistence_class=PERSIST_CLASS_FINALIZED_ARTIFACT,
            blocked=True,
            blocking_codes=[CODE_FINALIZED_MUTATION_BLOCKED],
            blocking_reason=CODE_FINALIZED_MUTATION_BLOCKED,
            outcome=PERSIST_OUTCOME_FINALIZED_PROTECTED,
            record_id=5,
            idempotency_key=None,
            duration_ms=1,
        )
        assert r.outcome == PERSIST_OUTCOME_FINALIZED_PROTECTED
        assert r.blocked is True


# ── TestIdempotencyGovernance ─────────────────────────────────────────────────

class TestIdempotencyGovernance:
    """Deterministic idempotency: duplicate LIVE rejected; replay duplication permitted."""

    def test_first_write_original_passes(self):
        store: set = set()
        codes = _check_idempotency("idem-001", store, TYPE_ORIGINAL)
        assert codes == []

    def test_second_write_original_blocked(self):
        store = {"idem-001"}
        codes = _check_idempotency("idem-001", store, TYPE_ORIGINAL)
        assert CODE_IDEMPOTENCY_DUPLICATE in codes

    def test_second_write_replay_allowed(self):
        store = {"idem-001"}
        codes = _check_idempotency("idem-001", store, TYPE_REPLAY)
        assert codes == []

    def test_second_write_regeneration_allowed(self):
        store = {"idem-001"}
        codes = _check_idempotency("idem-001", store, TYPE_REGENERATION)
        assert codes == []

    def test_no_key_always_passes(self):
        store = {"anything"}
        codes = _check_idempotency(None, store, TYPE_ORIGINAL)
        assert codes == []

    def test_unique_key_per_call_passes(self):
        store: set = set()
        for i in range(5):
            key = f"key-{i}"
            codes = _check_idempotency(key, store, TYPE_ORIGINAL)
            assert codes == [], f"key-{i} should pass on first use"
            store.add(key)


# ── TestAttributionContinuity ─────────────────────────────────────────────────

class TestAttributionContinuity:
    """Attribution continuity: all fields propagated to PersistenceRecord (IML-1, INV-5)."""

    def test_correlation_id_propagated(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.correlation_id == a.correlation_id

    def test_causation_id_propagated(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.causation_id == a.causation_id

    def test_execution_mode_propagated(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.execution_mode == a.execution_mode

    def test_execution_type_propagated(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.execution_type == a.execution_type

    def test_governance_scope_propagated(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.governance_scope == a.governance_scope

    def test_is_replay_propagated(self):
        a = _replay_attribution()
        r = _minimal_record(a)
        assert r.is_replay == a.is_replay

    def test_attribution_complete_propagated(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.attribution_complete is True

    def test_attribution_fields_immutable_after_record_creation(self):
        a = _live_attribution()
        original_cid = a.correlation_id
        r = _minimal_record(a)
        # Mutating source fields after record creation does not affect the record
        a.correlation_id = "mutated"
        assert r.correlation_id == original_cid


# ── TestReplaySafeGovernance ──────────────────────────────────────────────────

class TestReplaySafeGovernance:
    """Replay persistence: distinguishable, queryable, non-overwriting (RSV-1, AP-RT2)."""

    def test_replay_record_has_replay_only_scope(self):
        a = _replay_attribution()
        r = _minimal_record(a)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_live_record_does_not_have_replay_scope(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert r.governance_scope != SCOPE_REPLAY_ONLY

    def test_replay_type_in_replay_execution_types(self):
        assert TYPE_REPLAY in _REPLAY_EXECUTION_TYPES

    def test_regeneration_type_in_replay_execution_types(self):
        assert TYPE_REGENERATION in _REPLAY_EXECUTION_TYPES

    def test_original_type_not_in_replay_execution_types(self):
        assert TYPE_ORIGINAL not in _REPLAY_EXECUTION_TYPES

    def test_recovery_type_not_in_replay_execution_types(self):
        assert TYPE_RECOVERY not in _REPLAY_EXECUTION_TYPES

    def test_replay_cannot_overwrite_live(self):
        codes = _check_replay_live_overwrite(is_replay=True, target_is_live=True)
        assert len(codes) == 1
        assert codes[0] == CODE_REPLAY_LIVE_OVERWRITE_BLOCKED

    def test_replay_can_append_to_new_row(self):
        codes = _check_replay_live_overwrite(is_replay=True, target_is_live=False)
        assert codes == []


# ── TestInvariantPreservation ─────────────────────────────────────────────────

class TestInvariantPreservation:
    """Cross-cutting invariants: no governance bypass, no PII, deterministic behavior."""

    def test_governance_gate_always_returns_list(self):
        for mode in _VALID_EXECUTION_MODES:
            for etype in _VALID_EXECUTION_TYPES:
                a = _live_attribution(execution_mode=mode, execution_type=etype)
                result = _governance_persistence_gate(
                    attribution=a,
                    idempotency_key=None,
                    idempotency_store=set(),
                    table_name="outreach_history",
                )
                assert isinstance(result, list)

    def test_persistence_record_blocking_codes_always_list(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert isinstance(r.blocking_codes, list)

    def test_persistence_record_rule_path_always_list(self):
        a = _live_attribution()
        r = _minimal_record(a)
        assert isinstance(r.rule_path_taken, list)

    def test_check_attribution_complete_pure_function(self):
        a = _live_attribution()
        result1 = _check_attribution_complete(a)
        result2 = _check_attribution_complete(a)
        assert result1 == result2

    def test_finalized_check_pure_function(self):
        result1 = _check_finalized_protection(True, "ai_insights", 1)
        result2 = _check_finalized_protection(True, "ai_insights", 1)
        assert result1 == result2

    def test_replay_check_pure_function(self):
        result1 = _check_replay_live_overwrite(True, True)
        result2 = _check_replay_live_overwrite(True, True)
        assert result1 == result2

    def test_governance_gate_accumulates_all_violations(self):
        a = AttributionFields(
            correlation_id="",
            execution_mode="INVALID_MODE",
            execution_type="INVALID_TYPE",
            governance_scope="",
        )
        codes = _governance_persistence_gate(
            attribution=a,
            idempotency_key=None,
            idempotency_store=set(),
            table_name="ai_insights",
            is_finalized=True,
        )
        # All four violations present
        assert CODE_CORRELATION_ID_MISSING in codes
        assert CODE_INVALID_EXECUTION_MODE in codes
        assert CODE_INVALID_EXECUTION_TYPE in codes
        assert CODE_GOVERNANCE_SCOPE_MISSING in codes
        assert CODE_FINALIZED_MUTATION_BLOCKED in codes

    def test_persistence_record_has_unique_id_per_call(self):
        a = _live_attribution()
        records = [_minimal_record(a) for _ in range(20)]
        ids = {r.persistence_id for r in records}
        assert len(ids) == 20
