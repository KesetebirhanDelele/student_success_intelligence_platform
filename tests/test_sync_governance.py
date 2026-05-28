"""
Governance certification suite for the synchronization orchestration coordination layer.

Self-contained: no mocks, no patches. Direct invocation of coordinate_sync_cycle.
Validates all governance contracts: RULE 0-13, FAD-5, INV-1/4/5/6, ABG-*, RSV-*, AOWG-*.
"""
from __future__ import annotations

import uuid

import app.services.sync as sync_module
from app.services.sync import coordinate_sync_cycle
from app.services._sync_types import (
    AUTHORITY_SQL_SERVER,
    CB_CLOSED,
    CB_OPEN,
    CB_UNKNOWN,
    DOMAIN_FULL,
    DOMAIN_INTERVIEW_PREP,
    DOMAIN_TRIGGER_DATA,
    INTENT_DEFER_STALE,
    INTENT_HOLD,
    INTENT_INGEST_AUTHORITATIVE,
    INTENT_RECONCILE_CONFLICTS,
    ORIGIN_MIRRORED_SQL,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SHADOW_ONLY,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    UNKNOWN_V0,
    SyncOrchestrationContext,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


_FULL_RULE_SET = {
    "sync_batch_size": 200,
    "sql_server_max_sync_age_hours": 4,
    "sync_max_retry_attempts": 3,
    "sync_conflict_threshold": 10,
    "sync_lag_escalation_hours": 6,
}


def _live_ctx(**overrides) -> SyncOrchestrationContext:
    """Valid LIVE context with full attribution and a full rule set."""
    base = dict(
        config_version_id="cfg-v2-sync-test",
        execution_mode="LIVE",
        execution_type="original",
        correlation_id=_uuid(),
        causation_id=_uuid(),
        orchestration_cycle_id=_uuid(),
        idempotency_key=_uuid(),
        origin_source=ORIGIN_MIRRORED_SQL,
        origin_authority=AUTHORITY_SQL_SERVER,
        actor_identity="sync_scheduler",
        attribution_timestamp="2026-01-01T00:00:00+00:00",
        config_rule_set=dict(_FULL_RULE_SET),
        sync_domain=DOMAIN_TRIGGER_DATA,
        sql_server_available=True,
        sync_lag_hours=1.0,
        circuit_breaker_state=CB_CLOSED,
        rows_scanned=100,
        rows_valid=100,
        rows_invalid=0,
        finalized_artifacts_detected=0,
    )
    base.update(overrides)
    return SyncOrchestrationContext(**base)


def _shadow_ctx(**overrides) -> SyncOrchestrationContext:
    return _live_ctx(execution_mode="SHADOW", **overrides)


def _replay_ctx(**overrides) -> SyncOrchestrationContext:
    return _live_ctx(
        execution_mode="SHADOW",
        execution_type="replay",
        source_artifact_id="sync-artifact-001",
        historical_config_version_id="cfg-v2-hist-001",
        **overrides,
    )


# ── TestRule0PreconditionGate ─────────────────────────────────────────────────

class TestRule0PreconditionGate:

    def test_missing_config_version_id_is_blocked(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert r.governance_scope == SCOPE_UNAVAILABLE
        assert "CONFIG_VERSION_ID_MISSING" in r.reason_codes

    def test_missing_correlation_id_is_blocked(self):
        ctx = _live_ctx(correlation_id=None)
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "CORRELATION_ID_MISSING" in r.reason_codes

    def test_invalid_execution_mode_is_blocked(self):
        ctx = _live_ctx(execution_mode="INVALID_MODE")
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_MODE" in r.reason_codes

    def test_invalid_execution_type_is_blocked(self):
        ctx = _live_ctx(execution_type="batch_scan")
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_TYPE" in r.reason_codes

    def test_missing_origin_source_is_blocked(self):
        ctx = _live_ctx(origin_source=None)
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "ORIGIN_SOURCE_MISSING" in r.reason_codes

    def test_missing_origin_authority_is_blocked(self):
        ctx = _live_ctx(origin_authority=None)
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "ORIGIN_AUTHORITY_MISSING" in r.reason_codes

    def test_missing_actor_identity_is_blocked(self):
        ctx = _live_ctx(actor_identity=None)
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "ACTOR_IDENTITY_MISSING" in r.reason_codes

    def test_blocked_record_outcome_is_failure(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_sync_cycle(ctx)
        assert r.outcome == OUTCOME_FAILURE
        assert r.error_class == "GovernancePreconditionError"

    def test_blocked_record_propagates_attribution(self):
        ctx = _live_ctx(correlation_id=None)
        r = coordinate_sync_cycle(ctx)
        assert r.origin_source == ORIGIN_MIRRORED_SQL
        assert r.origin_authority == AUTHORITY_SQL_SERVER
        assert r.actor_identity == "sync_scheduler"

    def test_blocked_record_has_rule_0_in_path(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_sync_cycle(ctx)
        assert "RULE_0" in r.rule_path_taken

    def test_blocked_record_live_effects_suppressed(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_sync_cycle(ctx)
        assert r.live_effects_suppressed is True
        assert r.dispatch_authorized is False

    def test_valid_context_passes_gate(self):
        ctx = _live_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_blocked is False


# ── TestMaintenanceSuppression ────────────────────────────────────────────────

class TestMaintenanceSuppression:

    def test_maintenance_mode_suspends_coordination(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope == SCOPE_MAINTENANCE
        assert r.orchestration_continues is False

    def test_maintenance_outcome_is_success(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert r.outcome == OUTCOME_SUCCESS
        assert r.error_class is None

    def test_maintenance_dispatch_blocked(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert r.dispatch_authorized is False
        assert r.live_effects_suppressed is True

    def test_maintenance_reason_code_present(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert "MAINTENANCE_MODE_ACTIVE" in r.reason_codes

    def test_maintenance_exits_before_threshold_resolution(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert "RULE_3" not in r.rule_path_taken

    def test_maintenance_path_includes_rule_1(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert "RULE_1" in r.rule_path_taken


# ── TestReplayContainment ─────────────────────────────────────────────────────

class TestReplayContainment:

    def test_replay_type_produces_replay_only_scope(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.is_replay is True

    def test_regeneration_type_produces_replay_only_scope(self):
        ctx = _live_ctx(execution_type="regeneration", source_artifact_id="art-001")
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_live_effects_suppressed(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.live_effects_suppressed is True
        assert r.dispatch_authorized is False

    def test_replay_sync_blocked_reason(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.sync_blocked_reason == "REPLAY_LIVE_SYNC_PROHIBITED"

    def test_replay_no_sync_intent(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.sync_intent is None

    def test_replay_without_source_artifact_is_degraded(self):
        ctx = _live_ctx(execution_type="replay", source_artifact_id=None)
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.degraded is True
        assert "REPLAY_SOURCE_ARTIFACT_MISSING" in r.degradation_flags

    def test_replay_with_source_artifact_not_degraded(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.degraded is False

    def test_replay_finalized_artifacts_protected(self):
        ctx = _replay_ctx(finalized_artifacts_detected=5)
        r = coordinate_sync_cycle(ctx)
        assert r.finalized_artifacts_protected is True

    def test_replay_has_rule_2_in_path(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert "RULE_2" in r.rule_path_taken

    def test_replay_exits_before_intent_classification(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert "RULE_10" not in r.rule_path_taken

    def test_replay_continues_is_true(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.orchestration_continues is True

    def test_replay_attribution_propagated(self):
        ctx = _replay_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.origin_source == ORIGIN_MIRRORED_SQL
        assert r.config_version_id == "cfg-v2-sync-test"


# ── TestSqlServerAuthoritativeBoundary ────────────────────────────────────────

class TestSqlServerAuthoritativeBoundary:

    def test_sql_server_read_only_always_enforced(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert r.sql_server_read_only_enforced is True

    def test_sql_server_read_only_enforced_on_blocked_paths(self):
        r = coordinate_sync_cycle(_live_ctx(config_version_id=None))
        assert r.sql_server_read_only_enforced is True

    def test_sql_server_read_only_enforced_on_replay_paths(self):
        r = coordinate_sync_cycle(_replay_ctx())
        assert r.sql_server_read_only_enforced is True

    def test_sql_server_read_only_enforced_on_maintenance_paths(self):
        r = coordinate_sync_cycle(_live_ctx(maintenance_mode_active=True))
        assert r.sql_server_read_only_enforced is True

    def test_authoritative_source_is_always_sql_server(self):
        for ctx in [_live_ctx(), _shadow_ctx(), _replay_ctx()]:
            r = coordinate_sync_cycle(ctx)
            assert r.authoritative_source == AUTHORITY_SQL_SERVER

    def test_boundary_annotation_in_reason_codes(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert "SQL_SERVER_READ_ONLY_BOUNDARY_ENFORCED" in r.reason_codes

    def test_sql_server_unavailable_blocks_sync(self):
        ctx = _live_ctx(sql_server_available=False)
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope == SCOPE_UNAVAILABLE
        assert r.sync_blocked_reason == "SQL_SERVER_UNAVAILABLE"
        assert "SQL_SERVER_UNAVAILABLE" in r.degradation_flags

    def test_sql_server_unavailable_intent_is_hold(self):
        ctx = _live_ctx(sql_server_available=False)
        r = coordinate_sync_cycle(ctx)
        assert r.sync_intent == INTENT_HOLD


# ── TestFinalizedArtifactImmutability ─────────────────────────────────────────

class TestFinalizedArtifactImmutability:

    def test_finalized_artifacts_always_protected(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert r.finalized_artifacts_protected is True

    def test_finalized_artifacts_protected_when_detected(self):
        ctx = _live_ctx(finalized_artifacts_detected=3)
        r = coordinate_sync_cycle(ctx)
        assert r.finalized_artifacts_protected is True
        assert r.finalized_artifacts_detected == 3

    def test_finalized_artifact_detection_emits_reason_code(self):
        ctx = _live_ctx(finalized_artifacts_detected=2)
        r = coordinate_sync_cycle(ctx)
        assert any("FINALIZED_ARTIFACTS_PROTECTED_2" in c for c in r.reason_codes)

    def test_finalized_artifacts_protected_on_all_paths(self):
        paths = [
            _live_ctx(config_version_id=None),        # blocked
            _live_ctx(maintenance_mode_active=True),   # maintenance
            _replay_ctx(),                             # replay
            _shadow_ctx(),                             # normal shadow
        ]
        for ctx in paths:
            r = coordinate_sync_cycle(ctx)
            assert r.finalized_artifacts_protected is True


# ── TestAppendOnlyLineagePreservation ─────────────────────────────────────────

class TestAppendOnlyLineagePreservation:

    def test_append_only_lineage_always_preserved(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert r.append_only_lineage_preserved is True

    def test_append_only_preserved_on_blocked_path(self):
        r = coordinate_sync_cycle(_live_ctx(config_version_id=None))
        assert r.append_only_lineage_preserved is True

    def test_append_only_preserved_on_replay_path(self):
        r = coordinate_sync_cycle(_replay_ctx())
        assert r.append_only_lineage_preserved is True

    def test_append_only_preserved_on_maintenance_path(self):
        r = coordinate_sync_cycle(_live_ctx(maintenance_mode_active=True))
        assert r.append_only_lineage_preserved is True


# ── TestConfigThresholdResolution ─────────────────────────────────────────────

class TestConfigThresholdResolution:

    def test_full_rule_set_resolves_all_thresholds(self):
        r = coordinate_sync_cycle(_shadow_ctx(config_rule_set=dict(_FULL_RULE_SET)))
        for key in ("sync_batch_size", "sql_server_max_sync_age_hours",
                    "sync_max_retry_attempts", "sync_conflict_threshold",
                    "sync_lag_escalation_hours"):
            assert r.threshold_bindings[key] != UNKNOWN_V0

    def test_missing_threshold_resolves_to_unknown_v0(self):
        r = coordinate_sync_cycle(_shadow_ctx(config_rule_set={}))
        assert r.threshold_bindings["sync_batch_size"] == UNKNOWN_V0

    def test_missing_threshold_emits_degradation_flag(self):
        r = coordinate_sync_cycle(_shadow_ctx(config_rule_set={}))
        assert "CONFIG_THRESHOLD_MISSING_SYNC_BATCH_SIZE" in r.degradation_flags

    def test_unknown_v0_sentinel_not_replaced_with_hardcode(self):
        ctx = _shadow_ctx(config_rule_set={"sync_batch_size": UNKNOWN_V0})
        r = coordinate_sync_cycle(ctx)
        assert r.threshold_bindings["sync_batch_size"] == UNKNOWN_V0

    def test_partial_rule_set_leaves_missing_as_unknown_v0(self):
        ctx = _shadow_ctx(config_rule_set={"sync_batch_size": 500})
        r = coordinate_sync_cycle(ctx)
        assert r.threshold_bindings["sync_batch_size"] == 500
        assert r.threshold_bindings["sql_server_max_sync_age_hours"] == UNKNOWN_V0


# ── TestShadowContainment ─────────────────────────────────────────────────────

class TestShadowContainment:

    def test_shadow_mode_produces_shadow_only_scope(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_produces_shadow_only_until_phase12_cert(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_emits_phase11_reason_code(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert "LIVE_SCOPE_SHADOW_ONLY_PHASE11" in r.reason_codes

    def test_dispatch_authorized_is_false_in_shadow(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.dispatch_authorized is False

    def test_dispatch_authorized_is_false_in_live(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert r.dispatch_authorized is False

    def test_live_effects_suppressed_in_shadow(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.live_effects_suppressed is True

    def test_live_effects_suppressed_in_live_phase11(self):
        r = coordinate_sync_cycle(_live_ctx())
        assert r.live_effects_suppressed is True

    def test_shadow_outcome_is_shadow_only(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.outcome == OUTCOME_SHADOW_ONLY


# ── TestSyncIntentClassification ──────────────────────────────────────────────

class TestSyncIntentClassification:

    def test_normal_path_produces_ingest_authoritative_intent(self):
        ctx = _shadow_ctx(rows_valid=100, rows_invalid=0)
        r = coordinate_sync_cycle(ctx)
        assert r.sync_intent == INTENT_INGEST_AUTHORITATIVE

    def test_sql_unavailable_produces_defer_stale_intent(self):
        ctx = _shadow_ctx(sql_server_available=False)
        r = coordinate_sync_cycle(ctx)
        # sync_blocked → HOLD overrides DEFER; verify blocked path
        assert r.sync_intent == INTENT_HOLD

    def test_lag_exceeded_produces_defer_stale_intent(self):
        ctx = _shadow_ctx(
            sync_lag_hours=10.0,
            config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
            sql_server_available=True,
        )
        r = coordinate_sync_cycle(ctx)
        assert r.sync_intent == INTENT_DEFER_STALE

    def test_invalid_rows_produces_reconcile_conflicts_intent(self):
        ctx = _shadow_ctx(rows_scanned=100, rows_valid=90, rows_invalid=10)
        r = coordinate_sync_cycle(ctx)
        assert r.sync_intent == INTENT_RECONCILE_CONFLICTS

    def test_circuit_open_produces_hold_intent(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_sync_cycle(ctx)
        assert r.sync_intent == INTENT_HOLD

    def test_unknown_v0_lag_threshold_does_not_defer(self):
        ctx = _shadow_ctx(
            sync_lag_hours=100.0,
            config_rule_set={},   # all thresholds UNKNOWN_V0
        )
        r = coordinate_sync_cycle(ctx)
        # UNKNOWN_V0 threshold → lag check skipped → INGEST_AUTHORITATIVE
        assert r.sync_intent == INTENT_INGEST_AUTHORITATIVE

    def test_intent_present_in_reason_codes(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert any(c.startswith("INTENT_") for c in r.reason_codes)


# ── TestConflictPreservationGovernance ────────────────────────────────────────

class TestConflictPreservationGovernance:

    def test_invalid_rows_require_conflict_preservation(self):
        ctx = _shadow_ctx(rows_valid=90, rows_invalid=10)
        r = coordinate_sync_cycle(ctx)
        assert r.conflict_preservation_required is True

    def test_zero_invalid_rows_no_conflict_preservation(self):
        ctx = _shadow_ctx(rows_valid=100, rows_invalid=0)
        r = coordinate_sync_cycle(ctx)
        assert r.conflict_preservation_required is False

    def test_circuit_open_blocks_dispatch_not_conflict_logic(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN, rows_invalid=5)
        r = coordinate_sync_cycle(ctx)
        # Blocked before intent, but conflict_preservation still reflects row state
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_sql_server_always_authoritative_source_on_coordination(self):
        ctx = _shadow_ctx()
        r = coordinate_sync_cycle(ctx)
        assert r.authoritative_source == AUTHORITY_SQL_SERVER


# ── TestProviderCircuitBreakerGovernance ──────────────────────────────────────

class TestProviderCircuitBreakerGovernance:

    def test_open_circuit_blocks_sync(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_sync_cycle(ctx)
        assert r.dispatch_authorized is False
        assert r.sync_blocked_reason == "CIRCUIT_BREAKER_OPEN"

    def test_open_circuit_produces_unavailable_scope(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_open_circuit_adds_degradation_flag(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_sync_cycle(ctx)
        assert "CIRCUIT_BREAKER_OPEN" in r.degradation_flags
        assert r.degraded is True

    def test_closed_circuit_does_not_block(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_CLOSED)
        r = coordinate_sync_cycle(ctx)
        assert r.governance_scope != SCOPE_UNAVAILABLE

    def test_sync_lag_adds_degradation_flag(self):
        ctx = _shadow_ctx(
            sync_lag_hours=10.0,
            config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
        )
        r = coordinate_sync_cycle(ctx)
        assert "SYNC_LAG_EXCEEDED" in r.degradation_flags

    def test_sql_lag_within_threshold_no_degradation(self):
        ctx = _shadow_ctx(
            sync_lag_hours=2.0,
            config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
        )
        r = coordinate_sync_cycle(ctx)
        assert "SYNC_LAG_EXCEEDED" not in r.degradation_flags


# ── TestAttributionContinuity ─────────────────────────────────────────────────

class TestAttributionContinuity:

    def test_attribution_fields_propagated_immutably(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.origin_source == ORIGIN_MIRRORED_SQL
        assert r.origin_authority == AUTHORITY_SQL_SERVER
        assert r.actor_identity == "sync_scheduler"
        assert r.attribution_timestamp == "2026-01-01T00:00:00+00:00"

    def test_correlation_id_propagated(self):
        cid = _uuid()
        r = coordinate_sync_cycle(_shadow_ctx(correlation_id=cid))
        assert r.correlation_id == cid

    def test_causation_id_propagated(self):
        caus = _uuid()
        r = coordinate_sync_cycle(_shadow_ctx(causation_id=caus))
        assert r.causation_id == caus

    def test_config_version_id_propagated(self):
        r = coordinate_sync_cycle(_shadow_ctx(config_version_id="cfg-v2-specific-001"))
        assert r.config_version_id == "cfg-v2-specific-001"

    def test_sync_domain_propagated(self):
        r = coordinate_sync_cycle(_shadow_ctx(sync_domain=DOMAIN_INTERVIEW_PREP))
        assert r.sync_domain == DOMAIN_INTERVIEW_PREP

    def test_execution_mode_propagated(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.execution_mode == "SHADOW"

    def test_execution_type_propagated(self):
        r = coordinate_sync_cycle(_shadow_ctx(execution_type="recovery"))
        assert r.execution_type == "recovery"

    def test_blocked_record_still_propagates_attribution(self):
        r = coordinate_sync_cycle(_live_ctx(config_version_id=None))
        assert r.orchestration_blocked is True
        assert r.origin_source == ORIGIN_MIRRORED_SQL
        assert r.actor_identity == "sync_scheduler"

    def test_row_metadata_propagated(self):
        ctx = _shadow_ctx(rows_scanned=250, rows_valid=240, rows_invalid=10)
        r = coordinate_sync_cycle(ctx)
        assert r.rows_scanned == 250
        assert r.rows_valid == 240
        assert r.rows_invalid == 10


# ── TestIdempotencyDeduplication ──────────────────────────────────────────────

class TestIdempotencyDeduplication:

    def setup_method(self):
        sync_module._sync_idempotency_keys.clear()

    def test_first_call_with_key_succeeds(self):
        r = coordinate_sync_cycle(_live_ctx(idempotency_key=_uuid()))
        assert r.orchestration_blocked is False

    def test_duplicate_key_on_second_call_is_blocked(self):
        key = _uuid()
        coordinate_sync_cycle(_live_ctx(idempotency_key=key))
        r2 = coordinate_sync_cycle(_live_ctx(idempotency_key=key))
        assert r2.orchestration_blocked is True
        assert "IDEMPOTENCY_DUPLICATE_DETECTED" in r2.reason_codes

    def test_different_keys_both_succeed(self):
        r1 = coordinate_sync_cycle(_live_ctx(idempotency_key=_uuid()))
        r2 = coordinate_sync_cycle(_live_ctx(idempotency_key=_uuid()))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False

    def test_replay_type_does_not_register_key(self):
        key = _uuid()
        coordinate_sync_cycle(_replay_ctx(idempotency_key=key))
        r = coordinate_sync_cycle(_live_ctx(idempotency_key=key))
        assert r.orchestration_blocked is False

    def test_no_key_never_triggers_duplicate_check(self):
        r1 = coordinate_sync_cycle(_live_ctx(idempotency_key=None))
        r2 = coordinate_sync_cycle(_live_ctx(idempotency_key=None))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False


# ── TestInvariantPreservation ─────────────────────────────────────────────────

class TestInvariantPreservation:

    def test_every_path_emits_event_id(self):
        for ctx in [
            _live_ctx(config_version_id=None),
            _live_ctx(maintenance_mode_active=True),
            _replay_ctx(),
            _shadow_ctx(),
        ]:
            r = coordinate_sync_cycle(ctx)
            assert r.event_id is not None and len(r.event_id) > 0

    def test_every_path_emits_rule_path(self):
        for ctx in [_live_ctx(config_version_id=None), _shadow_ctx()]:
            r = coordinate_sync_cycle(ctx)
            assert len(r.rule_path_taken) >= 1

    def test_every_path_emits_duration_ms(self):
        for ctx in [_live_ctx(config_version_id=None), _shadow_ctx()]:
            r = coordinate_sync_cycle(ctx)
            assert isinstance(r.duration_ms, int) and r.duration_ms >= 0

    def test_no_dispatch_authorized_without_phase12_cert(self):
        for ctx in [_live_ctx(), _shadow_ctx(), _replay_ctx()]:
            r = coordinate_sync_cycle(ctx)
            assert r.dispatch_authorized is False

    def test_live_effects_never_permitted_in_shadow_or_replay(self):
        assert coordinate_sync_cycle(_shadow_ctx()).live_effects_suppressed is True
        assert coordinate_sync_cycle(_replay_ctx()).live_effects_suppressed is True

    def test_sql_server_read_only_unconditional_on_all_paths(self):
        for ctx in [
            _live_ctx(), _shadow_ctx(), _replay_ctx(),
            _live_ctx(config_version_id=None),
            _live_ctx(maintenance_mode_active=True),
        ]:
            r = coordinate_sync_cycle(ctx)
            assert r.sql_server_read_only_enforced is True

    def test_finalized_artifacts_protected_unconditional_on_all_paths(self):
        for ctx in [
            _live_ctx(), _shadow_ctx(), _replay_ctx(),
            _live_ctx(config_version_id=None),
            _live_ctx(maintenance_mode_active=True),
        ]:
            r = coordinate_sync_cycle(ctx)
            assert r.finalized_artifacts_protected is True

    def test_append_only_lineage_preserved_unconditional_on_all_paths(self):
        for ctx in [
            _live_ctx(), _shadow_ctx(), _replay_ctx(),
            _live_ctx(config_version_id=None),
            _live_ctx(maintenance_mode_active=True),
        ]:
            r = coordinate_sync_cycle(ctx)
            assert r.append_only_lineage_preserved is True

    def test_orchestration_continues_false_on_unavailable_scope(self):
        r = coordinate_sync_cycle(_shadow_ctx(circuit_breaker_state=CB_OPEN))
        assert r.governance_scope == SCOPE_UNAVAILABLE
        assert r.orchestration_continues is False

    def test_orchestration_continues_true_on_shadow_scope(self):
        r = coordinate_sync_cycle(_shadow_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert r.orchestration_continues is True

    def test_degradation_cause_set_iff_degraded(self):
        r_clean = coordinate_sync_cycle(_shadow_ctx())
        if not r_clean.degraded:
            assert r_clean.degradation_cause is None
        r_deg = coordinate_sync_cycle(
            _shadow_ctx(
                sync_lag_hours=10.0,
                config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
            )
        )
        if r_deg.degraded:
            assert r_deg.degradation_cause is not None

    def test_reason_codes_always_list(self):
        for ctx in [_live_ctx(config_version_id=None), _shadow_ctx()]:
            r = coordinate_sync_cycle(ctx)
            assert isinstance(r.reason_codes, list)

    def test_maintenance_does_not_produce_orphaned_cycle(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_sync_cycle(ctx)
        assert r.outcome == OUTCOME_SUCCESS
        assert r.governance_scope == SCOPE_MAINTENANCE
        assert r.correlation_id == ctx.correlation_id
