"""
Governance certification suite for the outreach orchestration coordination layer.

Self-contained: no mocks, no patches. Direct invocation of coordinate_orchestration_cycle.
Validates all governance contracts: RULE 0-12, AP-RT*, AP-DF*, AP-RF*, AP-AI5, FAD-1.
"""
from __future__ import annotations

import uuid

import app.services.outreach as outreach_module
from app.services.outreach import coordinate_orchestration_cycle
from app.services._outreach_types import (
    AI_TIER_ADVISORY,
    AI_TIER_CONFIDENT,
    AI_TIER_FINALIZED_COPY,
    AI_TIER_IN_FLIGHT,
    AI_TIER_STALE,
    AI_TIER_UNAVAILABLE,
    CB_CLOSED,
    CB_OPEN,
    CB_UNKNOWN,
    INTENT_DEFER_PENDING_AI,
    INTENT_ESCALATE,
    INTENT_HOLD,
    INTENT_INITIATE_OUTREACH,
    INTENT_RETRY_OUTREACH,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SHADOW_ONLY,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    STATE_CLOSED,
    STATE_CONTACTED,
    STATE_ELIGIBLE,
    STATE_INTERVENTION_REQUIRED,
    STATE_NO_RESPONSE,
    STATE_QUEUED,
    STATE_RESPONDED,
    UNKNOWN_V0,
    OutreachOrchestrationContext,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


_FULL_RULE_SET = {
    "outreach_max_retry_attempts": 3,
    "outreach_retry_window_days": 7,
    "ai_insight_ttl_hours": 24,
    "sql_server_max_sync_age_hours": 4,
    "orchestration_concurrency_limit": 10,
}


def _live_ctx(**overrides) -> OutreachOrchestrationContext:
    """Valid LIVE context with full attribution and a full rule set."""
    base = dict(
        config_version_id="cfg-v2-outreach-test",
        execution_mode="LIVE",
        execution_type="original",
        correlation_id=_uuid(),
        causation_id=_uuid(),
        orchestration_cycle_id=_uuid(),
        idempotency_key=_uuid(),
        origin_source="ssip_scheduler",
        origin_authority="governance_engine",
        actor_identity="scheduler_service",
        attribution_timestamp="2026-01-01T00:00:00+00:00",
        config_rule_set=dict(_FULL_RULE_SET),
        student_id_opaque="stu_opaque_abc123",
        outreach_state=STATE_ELIGIBLE,
        contact_attempt_count=0,
        circuit_breaker_state=CB_CLOSED,
        sync_lag_hours=1.0,
        ai_governance_tier=AI_TIER_CONFIDENT,
    )
    base.update(overrides)
    return OutreachOrchestrationContext(**base)


def _shadow_ctx(**overrides) -> OutreachOrchestrationContext:
    return _live_ctx(execution_mode="SHADOW", **overrides)


def _replay_ctx(**overrides) -> OutreachOrchestrationContext:
    return _live_ctx(
        execution_mode="SHADOW",
        execution_type="replay",
        source_artifact_id="artifact-001",
        historical_config_version_id="cfg-v2-hist-001",
        **overrides,
    )


# ── TestRule0PreconditionGate ─────────────────────────────────────────────────

class TestRule0PreconditionGate:

    def test_missing_config_version_id_is_blocked(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert r.governance_scope == SCOPE_UNAVAILABLE
        assert "CONFIG_VERSION_ID_MISSING" in r.reason_codes

    def test_missing_correlation_id_is_blocked(self):
        ctx = _live_ctx(correlation_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "CORRELATION_ID_MISSING" in r.reason_codes

    def test_invalid_execution_mode_is_blocked(self):
        ctx = _live_ctx(execution_mode="INVALID_MODE")
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_MODE" in r.reason_codes

    def test_invalid_execution_type_is_blocked(self):
        ctx = _live_ctx(execution_type="batch_scan")
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_TYPE" in r.reason_codes

    def test_missing_origin_source_is_blocked(self):
        ctx = _live_ctx(origin_source=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "ORIGIN_SOURCE_MISSING" in r.reason_codes

    def test_missing_origin_authority_is_blocked(self):
        ctx = _live_ctx(origin_authority=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "ORIGIN_AUTHORITY_MISSING" in r.reason_codes

    def test_missing_actor_identity_is_blocked(self):
        ctx = _live_ctx(actor_identity=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert "ACTOR_IDENTITY_MISSING" in r.reason_codes

    def test_blocked_record_outcome_is_failure(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.outcome == OUTCOME_FAILURE
        assert r.error_class == "GovernancePreconditionError"

    def test_blocked_record_propagates_attribution(self):
        ctx = _live_ctx(correlation_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.origin_source == "ssip_scheduler"
        assert r.origin_authority == "governance_engine"
        assert r.actor_identity == "scheduler_service"

    def test_blocked_record_has_rule_0_in_path(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert "RULE_0" in r.rule_path_taken

    def test_blocked_record_live_effects_suppressed(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.live_effects_suppressed is True
        assert r.dispatch_authorized is False

    def test_valid_context_passes_gate(self):
        ctx = _live_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is False


# ── TestMaintenanceSuppression ────────────────────────────────────────────────

class TestMaintenanceSuppression:

    def test_maintenance_mode_suspends_coordination(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_MAINTENANCE
        assert r.orchestration_continues is False

    def test_maintenance_outcome_is_success(self):
        # Authorized suppression, not a failure
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        assert r.outcome == OUTCOME_SUCCESS
        assert r.error_class is None

    def test_maintenance_dispatch_blocked(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_authorized is False
        assert r.live_effects_suppressed is True

    def test_maintenance_reason_code_present(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        assert "MAINTENANCE_MODE_ACTIVE" in r.reason_codes

    def test_maintenance_path_includes_rule_1(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        assert "RULE_1" in r.rule_path_taken

    def test_maintenance_does_not_proceed_to_threshold_resolution(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        # Should not have RULE_3 in path — exits at RULE_1
        assert "RULE_3" not in r.rule_path_taken


# ── TestReplayContainment ─────────────────────────────────────────────────────

class TestReplayContainment:

    def test_replay_type_produces_replay_only_scope(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.is_replay is True

    def test_regeneration_type_produces_replay_only_scope(self):
        ctx = _live_ctx(execution_type="regeneration", source_artifact_id="art-001")
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_live_effects_suppressed(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.live_effects_suppressed is True
        assert r.dispatch_authorized is False

    def test_replay_dispatch_blocked_reason(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_blocked_reason == "REPLAY_LIVE_DISPATCH_PROHIBITED"

    def test_replay_no_intent_type(self):
        # No live intent in replay — historical simulation only (AP-RT2)
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type is None

    def test_replay_without_source_artifact_is_degraded(self):
        ctx = _live_ctx(execution_type="replay", source_artifact_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.degraded is True
        assert "REPLAY_SOURCE_ARTIFACT_MISSING" in r.degradation_flags

    def test_replay_with_source_artifact_not_degraded(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.degraded is False

    def test_replay_has_rule_2_in_path(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert "RULE_2" in r.rule_path_taken

    def test_replay_exits_before_intent_classification(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        # No RULE_9 (intent classification) should be reached
        assert "RULE_9" not in r.rule_path_taken

    def test_replay_attribution_propagated(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.origin_source == "ssip_scheduler"
        assert r.config_version_id == "cfg-v2-outreach-test"

    def test_replay_continues_is_true(self):
        ctx = _replay_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_continues is True


# ── TestConfigThresholdResolution ─────────────────────────────────────────────

class TestConfigThresholdResolution:

    def test_full_rule_set_resolves_all_thresholds(self):
        ctx = _shadow_ctx(config_rule_set=dict(_FULL_RULE_SET))
        r = coordinate_orchestration_cycle(ctx)
        for key in ("outreach_max_retry_attempts", "outreach_retry_window_days",
                    "ai_insight_ttl_hours", "sql_server_max_sync_age_hours",
                    "orchestration_concurrency_limit"):
            assert r.threshold_bindings[key] != UNKNOWN_V0

    def test_missing_threshold_resolves_to_unknown_v0(self):
        ctx = _shadow_ctx(config_rule_set={})
        r = coordinate_orchestration_cycle(ctx)
        assert r.threshold_bindings["outreach_max_retry_attempts"] == UNKNOWN_V0

    def test_missing_threshold_emits_degradation_flag(self):
        ctx = _shadow_ctx(config_rule_set={})
        r = coordinate_orchestration_cycle(ctx)
        assert "CONFIG_THRESHOLD_MISSING_OUTREACH_MAX_RETRY_ATTEMPTS" in r.degradation_flags

    def test_unknown_v0_sentinel_not_replaced_with_hardcode(self):
        ctx = _shadow_ctx(config_rule_set={"outreach_max_retry_attempts": UNKNOWN_V0})
        r = coordinate_orchestration_cycle(ctx)
        assert r.threshold_bindings["outreach_max_retry_attempts"] == UNKNOWN_V0

    def test_partial_rule_set_leaves_missing_as_unknown_v0(self):
        ctx = _shadow_ctx(config_rule_set={"outreach_max_retry_attempts": 5})
        r = coordinate_orchestration_cycle(ctx)
        assert r.threshold_bindings["outreach_max_retry_attempts"] == 5
        assert r.threshold_bindings["outreach_retry_window_days"] == UNKNOWN_V0


# ── TestShadowContainment ─────────────────────────────────────────────────────

class TestShadowContainment:

    def test_shadow_mode_produces_shadow_only_scope(self):
        ctx = _shadow_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_produces_shadow_only_until_phase12_cert(self):
        # Phase-12 cert required; LIVE currently maps to SHADOW_ONLY (AP-RT7)
        ctx = _live_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_emits_phase11_reason_code(self):
        ctx = _live_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert "LIVE_SCOPE_SHADOW_ONLY_PHASE11" in r.reason_codes

    def test_dispatch_authorized_is_false_in_shadow(self):
        ctx = _shadow_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_authorized is False

    def test_dispatch_authorized_is_false_in_live(self):
        ctx = _live_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_authorized is False

    def test_live_effects_suppressed_in_shadow(self):
        ctx = _shadow_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.live_effects_suppressed is True

    def test_live_effects_suppressed_in_live_phase11(self):
        ctx = _live_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.live_effects_suppressed is True

    def test_shadow_outcome_is_shadow_only(self):
        ctx = _shadow_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.outcome == OUTCOME_SHADOW_ONLY


# ── TestProviderCircuitBreakerGovernance ──────────────────────────────────────

class TestProviderCircuitBreakerGovernance:

    def test_open_circuit_breaker_blocks_dispatch(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_authorized is False
        assert r.dispatch_blocked_reason == "CIRCUIT_BREAKER_OPEN"

    def test_open_circuit_breaker_produces_unavailable_scope(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_open_circuit_breaker_sets_escalation_candidacy(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_orchestration_cycle(ctx)
        assert r.escalation_candidate is True
        assert r.escalation_candidacy_reason == "PROVIDER_FAILURE_ESCALATION_CANDIDACY"

    def test_open_circuit_adds_degradation_flag(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_orchestration_cycle(ctx)
        assert "CIRCUIT_BREAKER_OPEN" in r.degradation_flags

    def test_closed_circuit_does_not_block(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_CLOSED)
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_blocked_reason != "CIRCUIT_BREAKER_OPEN"
        assert r.governance_scope != SCOPE_UNAVAILABLE

    def test_stale_sql_adds_degradation_flag(self):
        ctx = _shadow_ctx(
            sync_lag_hours=10.0,
            config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
        )
        r = coordinate_orchestration_cycle(ctx)
        assert "STALE_SQL_SERVER_DATA" in r.degradation_flags
        assert r.stale_sql_server_data is True

    def test_sql_within_threshold_no_degradation(self):
        ctx = _shadow_ctx(
            sync_lag_hours=2.0,
            config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
        )
        r = coordinate_orchestration_cycle(ctx)
        assert "STALE_SQL_SERVER_DATA" not in r.degradation_flags


# ── TestComplianceHoldGovernance ──────────────────────────────────────────────

class TestComplianceHoldGovernance:

    def test_compliance_hold_blocks_dispatch(self):
        ctx = _shadow_ctx(compliance_hold_flag=True)
        r = coordinate_orchestration_cycle(ctx)
        assert r.dispatch_authorized is False
        assert r.compliance_hold_active is True

    def test_compliance_hold_produces_unavailable_scope(self):
        ctx = _shadow_ctx(compliance_hold_flag=True)
        r = coordinate_orchestration_cycle(ctx)
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_compliance_hold_reason_code_present(self):
        ctx = _shadow_ctx(compliance_hold_flag=True)
        r = coordinate_orchestration_cycle(ctx)
        assert "COMPLIANCE_HOLD_DISPATCH_BLOCKED" in r.reason_codes

    def test_compliance_hold_adds_degradation_flag(self):
        ctx = _shadow_ctx(compliance_hold_flag=True)
        r = coordinate_orchestration_cycle(ctx)
        assert "COMPLIANCE_HOLD_DISPATCH_BLOCKED" in r.degradation_flags

    def test_no_compliance_hold_active_is_false(self):
        ctx = _shadow_ctx(compliance_hold_flag=False)
        r = coordinate_orchestration_cycle(ctx)
        assert r.compliance_hold_active is False


# ── TestOrchestrationIntentClassification ─────────────────────────────────────

class TestOrchestrationIntentClassification:

    def test_eligible_state_produces_initiate_intent(self):
        ctx = _shadow_ctx(outreach_state=STATE_ELIGIBLE, contact_attempt_count=0)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_INITIATE_OUTREACH

    def test_queued_state_produces_initiate_intent(self):
        ctx = _shadow_ctx(outreach_state=STATE_QUEUED, contact_attempt_count=0)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_INITIATE_OUTREACH

    def test_none_state_produces_initiate_intent(self):
        ctx = _shadow_ctx(outreach_state=None, contact_attempt_count=0)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_INITIATE_OUTREACH

    def test_no_response_state_produces_retry_intent(self):
        ctx = _shadow_ctx(outreach_state=STATE_NO_RESPONSE, contact_attempt_count=1)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_RETRY_OUTREACH

    def test_contacted_state_produces_hold_intent(self):
        ctx = _shadow_ctx(outreach_state=STATE_CONTACTED)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_HOLD

    def test_terminal_state_responded_produces_hold(self):
        ctx = _shadow_ctx(outreach_state=STATE_RESPONDED)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_HOLD

    def test_terminal_state_closed_produces_hold(self):
        ctx = _shadow_ctx(outreach_state=STATE_CLOSED)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_HOLD

    def test_terminal_state_intervention_required_produces_hold(self):
        ctx = _shadow_ctx(outreach_state=STATE_INTERVENTION_REQUIRED)
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_HOLD

    def test_ai_in_flight_produces_defer_intent(self):
        ctx = _shadow_ctx(
            outreach_state=STATE_ELIGIBLE,
            ai_governance_tier=AI_TIER_IN_FLIGHT,
        )
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_DEFER_PENDING_AI

    def test_retry_exhaustion_produces_escalate_intent(self):
        ctx = _shadow_ctx(
            outreach_state=STATE_NO_RESPONSE,
            contact_attempt_count=5,
            config_rule_set={**_FULL_RULE_SET, "outreach_max_retry_attempts": 3},
        )
        r = coordinate_orchestration_cycle(ctx)
        assert r.intent_type == INTENT_ESCALATE

    def test_unknown_v0_max_attempts_does_not_escalate(self):
        # If threshold is UNKNOWN_V0, retry exhaustion check is skipped (AP-RT9)
        ctx = _shadow_ctx(
            outreach_state=STATE_NO_RESPONSE,
            contact_attempt_count=100,
            config_rule_set={},  # all keys missing → UNKNOWN_V0
        )
        r = coordinate_orchestration_cycle(ctx)
        # Should fall through to RETRY_OUTREACH, not ESCALATE
        assert r.intent_type == INTENT_RETRY_OUTREACH


# ── TestEscalationCandidacyGovernance ─────────────────────────────────────────

class TestEscalationCandidacyGovernance:

    def test_retry_exhaustion_sets_escalation_candidate(self):
        ctx = _shadow_ctx(
            outreach_state=STATE_NO_RESPONSE,
            contact_attempt_count=5,
            config_rule_set={**_FULL_RULE_SET, "outreach_max_retry_attempts": 3},
        )
        r = coordinate_orchestration_cycle(ctx)
        assert r.escalation_candidate is True
        assert r.escalation_candidacy_reason == "RETRY_EXHAUSTED_ESCALATION_CANDIDACY"

    def test_circuit_open_sets_escalation_candidate(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_OPEN)
        r = coordinate_orchestration_cycle(ctx)
        assert r.escalation_candidate is True
        assert r.escalation_candidacy_reason == "PROVIDER_FAILURE_ESCALATION_CANDIDACY"

    def test_normal_path_no_escalation_candidate(self):
        ctx = _shadow_ctx(
            outreach_state=STATE_ELIGIBLE,
            contact_attempt_count=0,
        )
        r = coordinate_orchestration_cycle(ctx)
        assert r.escalation_candidate is False
        assert r.escalation_candidacy_reason is None

    def test_stale_ai_restricts_escalation_authority(self):
        ctx = _shadow_ctx(ai_governance_tier=AI_TIER_STALE)
        r = coordinate_orchestration_cycle(ctx)
        assert r.ai_escalation_authority is False
        # Stale AI does NOT block evaluation — intent is still classified
        assert r.intent_type is not None

    def test_unavailable_ai_restricts_escalation_authority(self):
        ctx = _shadow_ctx(ai_governance_tier=AI_TIER_UNAVAILABLE)
        r = coordinate_orchestration_cycle(ctx)
        assert r.ai_escalation_authority is False

    def test_confident_ai_grants_escalation_authority(self):
        ctx = _shadow_ctx(ai_governance_tier=AI_TIER_CONFIDENT)
        r = coordinate_orchestration_cycle(ctx)
        assert r.ai_escalation_authority is True

    def test_advisory_ai_grants_escalation_authority(self):
        ctx = _shadow_ctx(ai_governance_tier=AI_TIER_ADVISORY)
        r = coordinate_orchestration_cycle(ctx)
        assert r.ai_escalation_authority is True


# ── TestAttributionContinuity ─────────────────────────────────────────────────

class TestAttributionContinuity:

    def test_attribution_fields_propagated_immutably(self):
        ctx = _shadow_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.origin_source == "ssip_scheduler"
        assert r.origin_authority == "governance_engine"
        assert r.actor_identity == "scheduler_service"
        assert r.attribution_timestamp == "2026-01-01T00:00:00+00:00"

    def test_correlation_id_propagated(self):
        cid = _uuid()
        ctx = _shadow_ctx(correlation_id=cid)
        r = coordinate_orchestration_cycle(ctx)
        assert r.correlation_id == cid

    def test_causation_id_propagated(self):
        caus = _uuid()
        ctx = _shadow_ctx(causation_id=caus)
        r = coordinate_orchestration_cycle(ctx)
        assert r.causation_id == caus

    def test_config_version_id_propagated(self):
        ctx = _shadow_ctx(config_version_id="cfg-v2-specific-001")
        r = coordinate_orchestration_cycle(ctx)
        assert r.config_version_id == "cfg-v2-specific-001"

    def test_student_id_opaque_propagated(self):
        ctx = _shadow_ctx(student_id_opaque="stu_opaque_xyz999")
        r = coordinate_orchestration_cycle(ctx)
        assert r.student_id_opaque == "stu_opaque_xyz999"

    def test_execution_mode_propagated(self):
        ctx = _shadow_ctx()
        r = coordinate_orchestration_cycle(ctx)
        assert r.execution_mode == "SHADOW"

    def test_execution_type_propagated(self):
        ctx = _shadow_ctx(execution_type="recovery")
        r = coordinate_orchestration_cycle(ctx)
        assert r.execution_type == "recovery"

    def test_blocked_record_still_propagates_attribution(self):
        ctx = _live_ctx(config_version_id=None)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is True
        assert r.origin_source == "ssip_scheduler"
        assert r.actor_identity == "scheduler_service"


# ── TestIdempotencyDeduplication ──────────────────────────────────────────────

class TestIdempotencyDeduplication:

    def setup_method(self):
        outreach_module._orchestration_idempotency_keys.clear()

    def test_first_call_with_key_succeeds(self):
        key = _uuid()
        ctx = _live_ctx(idempotency_key=key)
        r = coordinate_orchestration_cycle(ctx)
        assert r.orchestration_blocked is False

    def test_duplicate_key_on_second_call_is_blocked(self):
        key = _uuid()
        ctx1 = _live_ctx(idempotency_key=key)
        coordinate_orchestration_cycle(ctx1)
        ctx2 = _live_ctx(idempotency_key=key)
        r2 = coordinate_orchestration_cycle(ctx2)
        assert r2.orchestration_blocked is True
        assert "IDEMPOTENCY_DUPLICATE_DETECTED" in r2.reason_codes

    def test_different_keys_both_succeed(self):
        r1 = coordinate_orchestration_cycle(_live_ctx(idempotency_key=_uuid()))
        r2 = coordinate_orchestration_cycle(_live_ctx(idempotency_key=_uuid()))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False

    def test_replay_type_does_not_register_key(self):
        key = _uuid()
        ctx_replay = _replay_ctx(idempotency_key=key)
        coordinate_orchestration_cycle(ctx_replay)
        # The same key on a subsequent ORIGINAL should still succeed
        ctx_orig = _live_ctx(idempotency_key=key)
        r = coordinate_orchestration_cycle(ctx_orig)
        assert r.orchestration_blocked is False

    def test_no_key_never_triggers_duplicate_check(self):
        ctx1 = _live_ctx(idempotency_key=None)
        ctx2 = _live_ctx(idempotency_key=None)
        r1 = coordinate_orchestration_cycle(ctx1)
        r2 = coordinate_orchestration_cycle(ctx2)
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False


# ── TestInvariantPreservation ─────────────────────────────────────────────────

class TestInvariantPreservation:

    def test_every_path_emits_event_id(self):
        # Blocked path
        r1 = coordinate_orchestration_cycle(_live_ctx(config_version_id=None))
        assert r1.event_id is not None and len(r1.event_id) > 0
        # Maintenance path
        r2 = coordinate_orchestration_cycle(_live_ctx(maintenance_mode_active=True))
        assert r2.event_id is not None
        # Replay path
        r3 = coordinate_orchestration_cycle(_replay_ctx())
        assert r3.event_id is not None
        # Normal path
        r4 = coordinate_orchestration_cycle(_shadow_ctx())
        assert r4.event_id is not None

    def test_every_path_emits_rule_path(self):
        r1 = coordinate_orchestration_cycle(_live_ctx(config_version_id=None))
        assert len(r1.rule_path_taken) >= 1
        r2 = coordinate_orchestration_cycle(_shadow_ctx())
        assert len(r2.rule_path_taken) >= 1

    def test_every_path_emits_duration_ms(self):
        r1 = coordinate_orchestration_cycle(_live_ctx(config_version_id=None))
        assert isinstance(r1.duration_ms, int) and r1.duration_ms >= 0
        r2 = coordinate_orchestration_cycle(_shadow_ctx())
        assert isinstance(r2.duration_ms, int) and r2.duration_ms >= 0

    def test_no_dispatch_authorized_without_phase12_cert(self):
        # Invariant: dispatch_authorized must be False in current deployment
        for ctx in [_live_ctx(), _shadow_ctx(), _replay_ctx()]:
            r = coordinate_orchestration_cycle(ctx)
            assert r.dispatch_authorized is False, (
                f"dispatch_authorized was True for execution_mode={ctx.execution_mode}, "
                f"execution_type={ctx.execution_type}"
            )

    def test_live_effects_never_permitted_in_shadow_or_replay(self):
        r_shadow = coordinate_orchestration_cycle(_shadow_ctx())
        assert r_shadow.live_effects_suppressed is True
        r_replay = coordinate_orchestration_cycle(_replay_ctx())
        assert r_replay.live_effects_suppressed is True

    def test_degradation_cause_set_iff_degraded(self):
        r_clean = coordinate_orchestration_cycle(_shadow_ctx())
        if not r_clean.degraded:
            assert r_clean.degradation_cause is None
        r_stale = coordinate_orchestration_cycle(
            _shadow_ctx(
                sync_lag_hours=10.0,
                config_rule_set={**_FULL_RULE_SET, "sql_server_max_sync_age_hours": 4},
            )
        )
        if r_stale.degraded:
            assert r_stale.degradation_cause is not None

    def test_orchestration_continues_false_on_unavailable_scope(self):
        r = coordinate_orchestration_cycle(_shadow_ctx(circuit_breaker_state=CB_OPEN))
        assert r.governance_scope == SCOPE_UNAVAILABLE
        assert r.orchestration_continues is False

    def test_orchestration_continues_true_on_shadow_scope(self):
        r = coordinate_orchestration_cycle(_shadow_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert r.orchestration_continues is True

    def test_reason_codes_always_list(self):
        r1 = coordinate_orchestration_cycle(_live_ctx(config_version_id=None))
        assert isinstance(r1.reason_codes, list)
        r2 = coordinate_orchestration_cycle(_shadow_ctx())
        assert isinstance(r2.reason_codes, list)

    def test_maintenance_does_not_produce_orphaned_cycle(self):
        ctx = _live_ctx(maintenance_mode_active=True)
        r = coordinate_orchestration_cycle(ctx)
        # Governance contract: maintenance is a complete, non-orphaned suppression
        assert r.outcome == OUTCOME_SUCCESS
        assert r.governance_scope == SCOPE_MAINTENANCE
        assert r.correlation_id == ctx.correlation_id
