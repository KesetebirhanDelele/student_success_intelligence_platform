"""
Governance certification suite for the timeline lineage service.

Self-contained: no mocks, no patches. Direct invocation of classify_timeline_event.
Validates all governance contracts: RULE 0-12, FAD-4, IML-1/3/4, CID-*, ATT-*, INV-4/5/6.
"""
from __future__ import annotations

import uuid

import app.services.timeline as timeline_module
from app.services.timeline import classify_timeline_event
from app.services._timeline_types import (
    AUTHORITY_GHL,
    AUTHORITY_OPERATOR,
    AUTHORITY_SQL_SERVER,
    AUTHORITY_SYSTEM,
    EVENT_AI_LIFECYCLE,
    EVENT_COMMUNICATION,
    EVENT_COMPLIANCE_LIFECYCLE,
    EVENT_CONFIG_TRANSITION,
    EVENT_ESCALATION,
    EVENT_GOVERNANCE_TRANSITION,
    EVENT_NOTE,
    EVENT_ORCHESTRATION,
    EVENT_SNAPSHOT_LIFECYCLE,
    EVENT_STATE_CHANGE,
    EVENT_UNKNOWN,
    ORIGIN_GHL,
    ORIGIN_MIRRORED_SQL,
    ORIGIN_OPERATOR,
    ORIGIN_SCHEDULER,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SHADOW_ONLY,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    SOURCE_AI_INSIGHTS,
    SOURCE_COMPLIANCE_AUDIT,
    SOURCE_CONFIG_LIFECYCLE,
    SOURCE_GHL_MESSAGES,
    SOURCE_OUTREACH_HISTORY,
    SOURCE_SNAPSHOT_LIFECYCLE,
    SOURCE_STATE_TRANSITION_LOG,
    SOURCE_STUDENT_NOTES,
    UNKNOWN_V0,
    VISIBILITY_FINALIZED_PROTECTED,
    VISIBILITY_REPLAY_ONLY,
    VISIBILITY_SHADOW_VISIBLE,
    TimelineEventContext,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


_FULL_RULE_SET = {
    "timeline_max_events_per_student": 200,
    "timeline_retention_days": 365,
    "timeline_replay_window_days": 90,
}


def _live_ctx(**overrides) -> TimelineEventContext:
    """Valid LIVE context with full attribution and a complete rule set."""
    base = dict(
        config_version_id="cfg-v2-timeline-test",
        execution_mode="LIVE",
        execution_type="original",
        correlation_id=_uuid(),
        causation_id=_uuid(),
        orchestration_cycle_id=_uuid(),
        idempotency_key=_uuid(),
        origin_source=ORIGIN_SCHEDULER,
        origin_authority=AUTHORITY_SYSTEM,
        actor_identity="scheduler@system",
        attribution_timestamp="2026-01-01T00:00:00+00:00",
        config_rule_set=dict(_FULL_RULE_SET),
        raw_event_source=SOURCE_OUTREACH_HISTORY,
    )
    base.update(overrides)
    return TimelineEventContext(**base)


def _shadow_ctx(**overrides) -> TimelineEventContext:
    return _live_ctx(execution_mode="SHADOW", **overrides)


def _replay_ctx(**overrides) -> TimelineEventContext:
    defaults = dict(
        execution_type="replay",
        source_artifact_id="timeline-artifact-001",
        idempotency_key=None,
    )
    defaults.update(overrides)
    return _live_ctx(**defaults)


# ── RULE 0: Precondition gate ─────────────────────────────────────────────────

class TestRule0PreconditionGate:

    def test_missing_config_version_id_is_blocked(self):
        r = classify_timeline_event(_live_ctx(config_version_id=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "CONFIG_VERSION_ID_MISSING" in r.reason_codes

    def test_missing_correlation_id_is_blocked(self):
        r = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "CORRELATION_ID_MISSING" in r.reason_codes

    def test_invalid_execution_mode_is_blocked(self):
        r = classify_timeline_event(_live_ctx(execution_mode="INVALID", idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_MODE" in r.reason_codes

    def test_invalid_execution_type_is_blocked(self):
        r = classify_timeline_event(_live_ctx(execution_type="invalid_type", idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_TYPE" in r.reason_codes

    def test_missing_origin_source_is_blocked(self):
        r = classify_timeline_event(_live_ctx(origin_source=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "ORIGIN_SOURCE_MISSING" in r.reason_codes

    def test_missing_origin_authority_is_blocked(self):
        r = classify_timeline_event(_live_ctx(origin_authority=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "ORIGIN_AUTHORITY_MISSING" in r.reason_codes

    def test_missing_actor_identity_is_blocked(self):
        r = classify_timeline_event(_live_ctx(actor_identity=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "ACTOR_IDENTITY_MISSING" in r.reason_codes

    def test_blocked_record_outcome_is_failure(self):
        r = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.outcome == OUTCOME_FAILURE

    def test_blocked_record_propagates_attribution(self):
        ctx = _live_ctx(correlation_id=None, idempotency_key=None, origin_source=ORIGIN_OPERATOR)
        r = classify_timeline_event(ctx)
        assert r.origin_source == ORIGIN_OPERATOR

    def test_blocked_record_has_rule_0_in_path(self):
        r = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        assert "RULE_0" in r.rule_path_taken

    def test_blocked_record_live_effects_suppressed(self):
        r = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.live_effects_suppressed is True

    def test_valid_context_passes_gate(self):
        r = classify_timeline_event(_live_ctx())
        assert r.orchestration_blocked is False
        assert r.governance_scope == SCOPE_SHADOW_ONLY


# ── RULE 1: Maintenance suppression ──────────────────────────────────────────

class TestMaintenanceSuppression:

    def test_maintenance_mode_suspends_classification(self):
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert r.governance_scope == SCOPE_MAINTENANCE

    def test_maintenance_outcome_is_success(self):
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert r.outcome == OUTCOME_SUCCESS

    def test_maintenance_lineage_emit_not_authorized(self):
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert r.lineage_emit_authorized is False

    def test_maintenance_reason_code_present(self):
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert "MAINTENANCE_MODE_ACTIVE" in r.reason_codes

    def test_maintenance_path_includes_rule_1(self):
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert "RULE_1" in r.rule_path_taken

    def test_maintenance_exits_before_event_classification(self):
        # event_type=None because classification (RULE 7) is not reached
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert r.event_type is None


# ── RULE 2: Replay containment ────────────────────────────────────────────────

class TestReplayContainment:

    def test_replay_type_produces_replay_only_scope(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_type_produces_replay_only_scope(self):
        r = classify_timeline_event(_replay_ctx(execution_type="regeneration"))
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_live_effects_suppressed(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.live_effects_suppressed is True

    def test_replay_is_replay_flag(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.is_replay is True

    def test_replay_no_event_type(self):
        # INV-4, AP-RT2 — no live classification in replay context
        r = classify_timeline_event(_replay_ctx())
        assert r.event_type is None

    def test_replay_lineage_visibility_is_replay_only(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.lineage_visibility == VISIBILITY_REPLAY_ONLY

    def test_replay_without_source_artifact_is_degraded(self):
        r = classify_timeline_event(_replay_ctx(source_artifact_id=None))
        assert r.degraded is True
        assert "REPLAY_SOURCE_ARTIFACT_MISSING" in r.degradation_flags

    def test_replay_with_source_artifact_not_degraded(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.degraded is False

    def test_replay_finalized_lineage_protected(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.finalized_lineage_protected is True

    def test_replay_has_rule_2_in_path(self):
        r = classify_timeline_event(_replay_ctx())
        assert "RULE_2" in r.rule_path_taken

    def test_replay_exits_before_event_classification_rule(self):
        # RULE_7 (event classification) must NOT appear in replay path
        r = classify_timeline_event(_replay_ctx())
        assert "RULE_7" not in r.rule_path_taken

    def test_replay_orchestration_continues(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.orchestration_continues is True

    def test_replay_attribution_propagated(self):
        r = classify_timeline_event(_replay_ctx(actor_identity="replay-operator"))
        assert r.actor_identity == "replay-operator"


# ── RULE 5: FINALIZED lineage protection ──────────────────────────────────────

class TestFinalizedLineageProtection:

    def test_finalized_lineage_detected_emits_reason_code(self):
        r = classify_timeline_event(_live_ctx(finalized_lineage_detected=True))
        assert "FINALIZED_LINEAGE_PROTECTED" in r.reason_codes

    def test_finalized_lineage_detected_sets_visibility(self):
        r = classify_timeline_event(_live_ctx(finalized_lineage_detected=True))
        assert r.lineage_visibility == VISIBILITY_FINALIZED_PROTECTED

    def test_finalized_lineage_protected_unconditional(self):
        r = classify_timeline_event(_live_ctx(finalized_lineage_detected=False))
        assert r.finalized_lineage_protected is True

    def test_finalized_lineage_detected_false_gives_shadow_visibility(self):
        r = classify_timeline_event(_live_ctx(finalized_lineage_detected=False))
        assert r.lineage_visibility == VISIBILITY_SHADOW_VISIBLE

    def test_finalized_lineage_protected_on_all_record_types(self):
        blocked = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        replay = classify_timeline_event(_replay_ctx())
        maint = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        normal = classify_timeline_event(_live_ctx())
        for r in (blocked, replay, maint, normal):
            assert r.finalized_lineage_protected is True


# ── Append-only guarantees ────────────────────────────────────────────────────

class TestAppendOnlyGuarantees:

    def test_append_only_enforced_on_normal_path(self):
        r = classify_timeline_event(_live_ctx())
        assert r.append_only_enforced is True

    def test_append_only_enforced_on_blocked_path(self):
        r = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.append_only_enforced is True

    def test_append_only_enforced_on_replay_path(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.append_only_enforced is True

    def test_append_only_enforced_on_maintenance_path(self):
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert r.append_only_enforced is True


# ── RULE 6: Causation chain preservation ──────────────────────────────────────

class TestCausationChainPreservation:

    def test_causation_id_present_sets_preserved_true(self):
        r = classify_timeline_event(_live_ctx(causation_id=_uuid()))
        assert r.causation_chain_preserved is True

    def test_causation_id_absent_sets_preserved_false(self):
        r = classify_timeline_event(_live_ctx(causation_id=None))
        assert r.causation_chain_preserved is False

    def test_causation_id_absent_emits_degradation_flag(self):
        r = classify_timeline_event(_live_ctx(causation_id=None))
        assert "CAUSATION_CHAIN_INCOMPLETE" in r.degradation_flags
        assert r.degraded is True

    def test_causation_chain_preserved_on_replay_path(self):
        r = classify_timeline_event(_replay_ctx(causation_id=_uuid()))
        assert r.causation_chain_preserved is True

    def test_state_lineage_propagated(self):
        r = classify_timeline_event(_live_ctx(
            execution_state_before="NO_RESPONSE",
            execution_state_after="RETRY",
        ))
        assert r.execution_state_before == "NO_RESPONSE"
        assert r.execution_state_after == "RETRY"


# ── RULE 7: Event type classification ─────────────────────────────────────────

class TestEventTypeClassification:

    def test_outreach_history_source_produces_orchestration(self):
        r = classify_timeline_event(_live_ctx(raw_event_source=SOURCE_OUTREACH_HISTORY))
        assert r.event_type == EVENT_ORCHESTRATION

    def test_state_transition_log_source_produces_state_change(self):
        r = classify_timeline_event(_live_ctx(raw_event_source=SOURCE_STATE_TRANSITION_LOG))
        assert r.event_type == EVENT_STATE_CHANGE

    def test_student_notes_source_produces_note(self):
        r = classify_timeline_event(_live_ctx(raw_event_source=SOURCE_STUDENT_NOTES))
        assert r.event_type == EVENT_NOTE

    def test_ai_insights_source_produces_ai_lifecycle(self):
        r = classify_timeline_event(_live_ctx(
            raw_event_source=SOURCE_AI_INSIGHTS,
            origin_source=ORIGIN_SCHEDULER,
        ))
        assert r.event_type == EVENT_AI_LIFECYCLE

    def test_ghl_messages_source_produces_communication(self):
        r = classify_timeline_event(_live_ctx(raw_event_source=SOURCE_GHL_MESSAGES))
        assert r.event_type == EVENT_COMMUNICATION

    def test_hint_overrides_source_map(self):
        r = classify_timeline_event(_live_ctx(
            raw_event_source=SOURCE_OUTREACH_HISTORY,
            event_type_hint=EVENT_ESCALATION,
        ))
        assert r.event_type == EVENT_ESCALATION

    def test_unknown_source_produces_unknown_type(self):
        r = classify_timeline_event(_live_ctx(
            raw_event_source=None,
            event_type_hint=None,
        ))
        assert r.event_type == EVENT_UNKNOWN

    def test_snapshot_lifecycle_source_produces_snapshot_lifecycle(self):
        r = classify_timeline_event(_live_ctx(raw_event_source=SOURCE_SNAPSHOT_LIFECYCLE))
        assert r.event_type == EVENT_SNAPSHOT_LIFECYCLE

    def test_compliance_audit_source_produces_compliance_lifecycle(self):
        r = classify_timeline_event(_live_ctx(raw_event_source=SOURCE_COMPLIANCE_AUDIT))
        assert r.event_type == EVENT_COMPLIANCE_LIFECYCLE


# ── RULE 8: SQL Server authority preservation ─────────────────────────────────

class TestSqlServerAuthorityPreservation:

    def test_sql_server_origin_emits_authority_preserved_code(self):
        r = classify_timeline_event(_live_ctx(
            origin_source=ORIGIN_MIRRORED_SQL,
            origin_authority=AUTHORITY_SQL_SERVER,
        ))
        assert "SQL_SERVER_AUTHORITY_PRESERVED" in r.reason_codes

    def test_sql_server_origin_sets_authoritative_source(self):
        r = classify_timeline_event(_live_ctx(
            origin_source=ORIGIN_MIRRORED_SQL,
            origin_authority=AUTHORITY_SQL_SERVER,
        ))
        assert r.authoritative_source == AUTHORITY_SQL_SERVER

    def test_ghl_origin_sets_ghl_authority(self):
        r = classify_timeline_event(_live_ctx(
            origin_source=ORIGIN_GHL,
            origin_authority=AUTHORITY_GHL,
            raw_event_source=SOURCE_GHL_MESSAGES,
        ))
        assert r.authoritative_source == AUTHORITY_GHL

    def test_operator_origin_sets_operator_authority(self):
        r = classify_timeline_event(_live_ctx(
            origin_source=ORIGIN_OPERATOR,
            origin_authority=AUTHORITY_OPERATOR,
        ))
        assert r.authoritative_source == AUTHORITY_OPERATOR

    def test_non_sql_origin_does_not_emit_sql_code(self):
        r = classify_timeline_event(_live_ctx(origin_source=ORIGIN_SCHEDULER))
        assert "SQL_SERVER_AUTHORITY_PRESERVED" not in r.reason_codes

    def test_sql_server_authority_preserved_unconditional(self):
        # The invariant field is always True — this service never overwrites authority
        for origin in (ORIGIN_SCHEDULER, ORIGIN_OPERATOR, ORIGIN_GHL, ORIGIN_MIRRORED_SQL):
            r = classify_timeline_event(_live_ctx(origin_source=origin))
            assert r.sql_server_authority_preserved is True


# ── Shadow containment ────────────────────────────────────────────────────────

class TestShadowContainment:

    def test_shadow_mode_produces_shadow_only_scope(self):
        r = classify_timeline_event(_shadow_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_produces_shadow_only_until_phase12_cert(self):
        r = classify_timeline_event(_live_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_emits_phase11_reason_code(self):
        r = classify_timeline_event(_live_ctx())
        assert "LIVE_SCOPE_SHADOW_ONLY_PHASE11" in r.reason_codes

    def test_lineage_emit_not_authorized_in_shadow(self):
        r = classify_timeline_event(_shadow_ctx())
        assert r.lineage_emit_authorized is False

    def test_lineage_emit_not_authorized_in_live(self):
        r = classify_timeline_event(_live_ctx())
        assert r.lineage_emit_authorized is False

    def test_live_effects_suppressed_in_shadow(self):
        r = classify_timeline_event(_shadow_ctx())
        assert r.live_effects_suppressed is True

    def test_live_effects_suppressed_in_live_phase11(self):
        r = classify_timeline_event(_live_ctx())
        assert r.live_effects_suppressed is True

    def test_shadow_outcome_is_shadow_only(self):
        r = classify_timeline_event(_shadow_ctx())
        assert r.outcome == OUTCOME_SHADOW_ONLY


# ── Attribution continuity ────────────────────────────────────────────────────

class TestAttributionContinuity:

    def test_origin_source_propagated(self):
        r = classify_timeline_event(_live_ctx(origin_source=ORIGIN_OPERATOR))
        assert r.origin_source == ORIGIN_OPERATOR

    def test_origin_authority_propagated(self):
        r = classify_timeline_event(_live_ctx(origin_authority=AUTHORITY_OPERATOR))
        assert r.origin_authority == AUTHORITY_OPERATOR

    def test_actor_identity_propagated(self):
        r = classify_timeline_event(_live_ctx(actor_identity="operator-007"))
        assert r.actor_identity == "operator-007"

    def test_correlation_id_propagated(self):
        cid = _uuid()
        r = classify_timeline_event(_live_ctx(correlation_id=cid))
        assert r.correlation_id == cid

    def test_causation_id_propagated(self):
        caus = _uuid()
        r = classify_timeline_event(_live_ctx(causation_id=caus))
        assert r.causation_id == caus

    def test_config_version_id_propagated(self):
        r = classify_timeline_event(_live_ctx(config_version_id="cfg-lineage-test"))
        assert r.config_version_id == "cfg-lineage-test"

    def test_execution_mode_propagated(self):
        r = classify_timeline_event(_live_ctx(execution_mode="SHADOW"))
        assert r.execution_mode == "SHADOW"

    def test_execution_type_propagated(self):
        r = classify_timeline_event(_live_ctx(execution_type="recovery"))
        assert r.execution_type == "recovery"

    def test_blocked_record_still_propagates_attribution(self):
        ctx = _live_ctx(
            correlation_id=None,
            idempotency_key=None,
            origin_source=ORIGIN_OPERATOR,
            actor_identity="blocked-actor",
        )
        r = classify_timeline_event(ctx)
        assert r.origin_source == ORIGIN_OPERATOR
        assert r.actor_identity == "blocked-actor"


# ── Config V2 threshold resolution ───────────────────────────────────────────

class TestConfigThresholdResolution:

    def test_full_rule_set_resolves_all_thresholds(self):
        r = classify_timeline_event(_live_ctx(config_rule_set=dict(_FULL_RULE_SET)))
        for v in r.threshold_bindings.values():
            assert v != UNKNOWN_V0

    def test_missing_threshold_resolves_to_unknown_v0(self):
        r = classify_timeline_event(_live_ctx(config_rule_set={}))
        for v in r.threshold_bindings.values():
            assert v == UNKNOWN_V0

    def test_missing_threshold_emits_degradation_flag(self):
        r = classify_timeline_event(_live_ctx(config_rule_set={}))
        assert any("CONFIG_THRESHOLD_MISSING_" in f for f in r.degradation_flags)
        assert r.degraded is True

    def test_unknown_v0_sentinel_in_rule_set_treated_as_missing(self):
        r = classify_timeline_event(_live_ctx(config_rule_set={
            "timeline_max_events_per_student": UNKNOWN_V0,
        }))
        assert r.threshold_bindings["timeline_max_events_per_student"] == UNKNOWN_V0

    def test_partial_rule_set_leaves_missing_keys_as_unknown_v0(self):
        r = classify_timeline_event(_live_ctx(config_rule_set={
            "timeline_max_events_per_student": 200,
        }))
        assert r.threshold_bindings["timeline_max_events_per_student"] == 200
        assert r.threshold_bindings["timeline_retention_days"] == UNKNOWN_V0


# ── Idempotency deduplication ─────────────────────────────────────────────────

class TestIdempotencyDeduplication:

    def setup_method(self):
        timeline_module._timeline_idempotency_keys.clear()

    def test_first_call_with_key_succeeds(self):
        key = _uuid()
        r = classify_timeline_event(_live_ctx(idempotency_key=key))
        assert r.orchestration_blocked is False

    def test_duplicate_key_on_second_call_is_blocked(self):
        key = _uuid()
        classify_timeline_event(_live_ctx(idempotency_key=key))
        r2 = classify_timeline_event(_live_ctx(idempotency_key=key))
        assert r2.orchestration_blocked is True
        assert "IDEMPOTENCY_DUPLICATE_DETECTED" in r2.reason_codes

    def test_different_keys_both_succeed(self):
        r1 = classify_timeline_event(_live_ctx(idempotency_key=_uuid()))
        r2 = classify_timeline_event(_live_ctx(idempotency_key=_uuid()))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False

    def test_replay_type_does_not_register_key(self):
        key = _uuid()
        classify_timeline_event(_replay_ctx(idempotency_key=key))
        # After replay with same key, a LIVE original should succeed (key not registered)
        r = classify_timeline_event(_live_ctx(idempotency_key=key))
        assert r.orchestration_blocked is False

    def test_no_key_never_triggers_duplicate_check(self):
        r1 = classify_timeline_event(_live_ctx(idempotency_key=None))
        r2 = classify_timeline_event(_live_ctx(idempotency_key=None))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False


# ── Invariant preservation ────────────────────────────────────────────────────

class TestInvariantPreservation:

    def test_every_path_emits_event_id(self):
        blocked = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        replay = classify_timeline_event(_replay_ctx())
        maint = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        normal = classify_timeline_event(_live_ctx())
        for r in (blocked, replay, maint, normal):
            assert r.event_id and len(r.event_id) > 0

    def test_every_path_emits_rule_path(self):
        blocked = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        replay = classify_timeline_event(_replay_ctx())
        maint = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        normal = classify_timeline_event(_live_ctx())
        for r in (blocked, replay, maint, normal):
            assert len(r.rule_path_taken) > 0

    def test_every_path_emits_duration_ms(self):
        blocked = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        replay = classify_timeline_event(_replay_ctx())
        normal = classify_timeline_event(_live_ctx())
        for r in (blocked, replay, normal):
            assert isinstance(r.duration_ms, int)
            assert r.duration_ms >= 0

    def test_no_lineage_emit_authorized_without_phase12_cert(self):
        for r in [
            classify_timeline_event(_live_ctx()),
            classify_timeline_event(_shadow_ctx()),
            classify_timeline_event(_replay_ctx()),
        ]:
            assert r.lineage_emit_authorized is False

    def test_live_effects_never_permitted_in_shadow_or_replay(self):
        for r in [
            classify_timeline_event(_shadow_ctx()),
            classify_timeline_event(_replay_ctx()),
        ]:
            assert r.live_effects_suppressed is True

    def test_append_only_enforced_unconditional_on_all_paths(self):
        for r in [
            classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None)),
            classify_timeline_event(_replay_ctx()),
            classify_timeline_event(_live_ctx(maintenance_mode_active=True)),
            classify_timeline_event(_live_ctx()),
        ]:
            assert r.append_only_enforced is True

    def test_finalized_lineage_protected_unconditional_on_all_paths(self):
        for r in [
            classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None)),
            classify_timeline_event(_replay_ctx()),
            classify_timeline_event(_live_ctx(maintenance_mode_active=True)),
            classify_timeline_event(_live_ctx()),
        ]:
            assert r.finalized_lineage_protected is True

    def test_replay_lineage_preserved_unconditional_on_all_paths(self):
        for r in [
            classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None)),
            classify_timeline_event(_replay_ctx()),
            classify_timeline_event(_live_ctx(maintenance_mode_active=True)),
            classify_timeline_event(_live_ctx()),
        ]:
            assert r.replay_lineage_preserved is True

    def test_orchestration_continues_false_on_blocked(self):
        r = classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.orchestration_continues is False

    def test_orchestration_continues_true_on_shadow_scope(self):
        r = classify_timeline_event(_live_ctx())
        assert r.orchestration_continues is True

    def test_orchestration_continues_true_on_replay(self):
        r = classify_timeline_event(_replay_ctx())
        assert r.orchestration_continues is True

    def test_degradation_cause_set_iff_degraded(self):
        degraded = classify_timeline_event(_live_ctx(causation_id=None))
        not_degraded = classify_timeline_event(_live_ctx(config_rule_set=dict(_FULL_RULE_SET)))
        assert degraded.degraded is True
        assert degraded.degradation_cause is not None
        if not not_degraded.degraded:
            assert not_degraded.degradation_cause is None

    def test_reason_codes_always_list(self):
        for r in [
            classify_timeline_event(_live_ctx(correlation_id=None, idempotency_key=None)),
            classify_timeline_event(_replay_ctx()),
            classify_timeline_event(_live_ctx()),
        ]:
            assert isinstance(r.reason_codes, list)

    def test_maintenance_does_not_produce_orphaned_cycle(self):
        # AP-RT15: every path emits observability; maintenance is an authorized suppression
        r = classify_timeline_event(_live_ctx(maintenance_mode_active=True))
        assert r.outcome == OUTCOME_SUCCESS
        assert r.governance_scope == SCOPE_MAINTENANCE
        assert "MAINTENANCE_MODE_ACTIVE" in r.reason_codes
