"""
Governance certification suite for the GHL provider containment orchestration layer.

Self-contained: no mocks, no patches. Direct invocation of assess_provider_orchestration.
Validates all governance contracts: RULE 0-11, AP-GHL1-15, AP-GF1-10.
"""
import uuid

import pytest

import app.services.ghl as ghl_module
from app.services.ghl import assess_provider_orchestration
from app.services._ghl_types import (
    CB_CLOSED,
    CB_HALF_OPEN,
    CB_OPEN,
    CB_UNKNOWN,
    SCOPE_BLOCKED,
    SCOPE_DUPLICATE_SUPPRESSED,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    UNKNOWN_V0,
    ProviderOrchestrationContext,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


_FULL_RULE_SET = {
    "provider_failure_max_retry_attempts": 3,
    "provider_failure_circuit_breaker_threshold": 5,
    "provider_failure_circuit_breaker_reset_hours": 1,
    "provider_failure_retry_backoff_base_seconds": 2,
    "provider_delivery_sla_hours": 24,
    "sql_server_max_sync_age_hours": 2,
}


def _full_ctx(**overrides) -> ProviderOrchestrationContext:
    """Valid LIVE context with all required attribution and a full rule set."""
    base = dict(
        config_version_id="cfg-v2-test",
        execution_mode="LIVE",
        execution_type="original",
        config_rule_set=dict(_FULL_RULE_SET),
        correlation_id=_uuid(),
        origin_source="ssip_test",
        origin_authority="test_authority",
        actor_identity="test_actor",
        idempotency_key=_uuid(),
    )
    base.update(overrides)
    return ProviderOrchestrationContext(**base)


def _shadow_ctx(**overrides) -> ProviderOrchestrationContext:
    return _full_ctx(execution_mode="SHADOW", **overrides)


def _replay_ctx(**overrides) -> ProviderOrchestrationContext:
    return _full_ctx(execution_mode="SHADOW", execution_type="replay", **overrides)


# ── TestRule0PreconditionGate ─────────────────────────────────────────────────

class TestRule0PreconditionGate:

    def test_missing_config_version_id_is_blocked(self):
        ctx = _full_ctx(config_version_id=None)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "CONFIG_VERSION_ID_MISSING" in a.reason_codes

    def test_invalid_execution_mode_is_blocked(self):
        ctx = _full_ctx(execution_mode="REPLAY")
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "INVALID_EXECUTION_MODE" in a.reason_codes

    def test_missing_correlation_id_is_blocked(self):
        ctx = _full_ctx(correlation_id=None)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "CORRELATION_ID_MISSING" in a.reason_codes

    def test_missing_origin_source_is_blocked(self):
        ctx = _full_ctx(origin_source=None)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "ORIGIN_SOURCE_MISSING" in a.reason_codes

    def test_missing_origin_authority_is_blocked(self):
        ctx = _full_ctx(origin_authority=None)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "ORIGIN_AUTHORITY_MISSING" in a.reason_codes

    def test_invalid_execution_type_is_blocked(self):
        ctx = _full_ctx(execution_type="unknown_type")
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "INVALID_EXECUTION_TYPE" in a.reason_codes

    def test_multiple_missing_fields_report_all_codes(self):
        ctx = _full_ctx(config_version_id=None, correlation_id=None, origin_source=None)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "CONFIG_VERSION_ID_MISSING" in a.reason_codes
        assert "CORRELATION_ID_MISSING" in a.reason_codes
        assert "ORIGIN_SOURCE_MISSING" in a.reason_codes

    def test_valid_context_passes_rule0(self):
        ctx = _shadow_ctx()
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope != SCOPE_BLOCKED
        assert "RULE_0" in a.rule_path_taken

    def test_blocked_assessment_orchestration_does_not_continue(self):
        ctx = _full_ctx(config_version_id=None)
        a = assess_provider_orchestration(ctx)
        assert a.orchestration_continues is False
        assert a.outbound_blocked is True


# ── TestShadowContainmentGovernance ──────────────────────────────────────────

class TestShadowContainmentGovernance:

    def test_shadow_mode_suppresses_outbound(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert a.outbound_suppressed is True

    def test_shadow_mode_sets_scope_shadow_only(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert a.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_mode_sets_provider_event_shadow_simulation(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert a.provider_event_type == "SHADOW_SIMULATION"

    def test_shadow_mode_orchestration_continues(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert a.orchestration_continues is True

    def test_shadow_mode_does_not_mark_provider_blocked(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert a.provider_blocked is False

    def test_shadow_mode_contains_shadow_suppressed_code(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert "SHADOW_OUTBOUND_SUPPRESSED" in a.reason_codes

    def test_shadow_mode_outbound_blocked_is_true(self):
        a = assess_provider_orchestration(_shadow_ctx())
        assert a.outbound_blocked is True


# ── TestReplayContainmentGovernance ──────────────────────────────────────────

class TestReplayContainmentGovernance:

    def test_replay_type_suppresses_outbound(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.outbound_suppressed is True

    def test_regeneration_type_suppresses_outbound(self):
        ctx = _full_ctx(execution_mode="SHADOW", execution_type="regeneration")
        a = assess_provider_orchestration(ctx)
        assert a.outbound_suppressed is True
        assert a.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_sets_scope_replay_only(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_sets_historical_context_only(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.historical_provider_context_only is True

    def test_replay_preserves_historical_config_version_id(self):
        ctx = _replay_ctx(historical_config_version_id="cfg-v1-historical")
        a = assess_provider_orchestration(ctx)
        assert a.historical_config_version_id == "cfg-v1-historical"

    def test_replay_outbound_blocked_is_true(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.outbound_blocked is True

    def test_replay_orchestration_continues_true(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.orchestration_continues is True

    def test_replay_no_ghl_message_id_emitted(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.ghl_message_id is None

    def test_replay_provider_source_set_from_source_artifact_id(self):
        ctx = _replay_ctx(source_artifact_id="artifact-abc-123")
        a = assess_provider_orchestration(ctx)
        assert a.replay_provider_source == "artifact-abc-123"


# ── TestProviderHealthAssessment ─────────────────────────────────────────────

class TestProviderHealthAssessment:

    def test_circuit_breaker_open_blocks_assessment(self):
        ctx = _full_ctx(circuit_breaker_state=CB_OPEN)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "CIRCUIT_BREAKER_OPEN" in a.reason_codes

    def test_circuit_breaker_open_orchestration_does_not_continue(self):
        ctx = _full_ctx(circuit_breaker_state=CB_OPEN)
        a = assess_provider_orchestration(ctx)
        assert a.orchestration_continues is False

    def test_circuit_breaker_closed_allows_continuation(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_CLOSED)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope != SCOPE_BLOCKED

    def test_circuit_breaker_unknown_allows_continuation(self):
        ctx = _shadow_ctx(circuit_breaker_state=CB_UNKNOWN)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope != SCOPE_BLOCKED

    def test_provider_outage_sets_degraded(self):
        ctx = _shadow_ctx(provider_outage_active=True)
        a = assess_provider_orchestration(ctx)
        assert a.degraded is True
        assert a.degradation_cause == "provider_outage"

    def test_provider_outage_does_not_block_shadow(self):
        ctx = _shadow_ctx(provider_outage_active=True)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_SHADOW_ONLY
        assert a.orchestration_continues is True

    def test_sync_lag_exceeded_sets_degraded(self):
        ctx = _shadow_ctx(sync_lag_hours=5.0)  # exceeds rule set max of 2
        a = assess_provider_orchestration(ctx)
        assert a.degraded is True
        assert "SYNC_LAG_EXCEEDED" in a.reason_codes

    def test_sync_lag_within_threshold_not_degraded_from_lag(self):
        ctx = _shadow_ctx(sync_lag_hours=1.0)  # within rule set max of 2
        a = assess_provider_orchestration(ctx)
        assert "SYNC_LAG_EXCEEDED" not in a.reason_codes


# ── TestOutboundAuthorizationGovernance ──────────────────────────────────────

class TestOutboundAuthorizationGovernance:

    def test_live_mode_suppressed_pending_phase12(self):
        a = assess_provider_orchestration(_full_ctx())
        assert a.outbound_suppressed is True
        assert "LIVE_SCOPE_SHADOW_ONLY_PHASE11" in a.reason_codes

    def test_live_mode_scope_is_shadow_only(self):
        a = assess_provider_orchestration(_full_ctx())
        assert a.governance_scope == SCOPE_SHADOW_ONLY

    def test_compliance_hold_blocks_live(self):
        ctx = _full_ctx(compliance_hold_active=True)
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "COMPLIANCE_HOLD_ACTIVE" in a.reason_codes

    def test_compliance_hold_orchestration_does_not_continue(self):
        ctx = _full_ctx(compliance_hold_active=True)
        a = assess_provider_orchestration(ctx)
        assert a.orchestration_continues is False

    def test_retry_budget_exhausted_blocks(self):
        ctx = _full_ctx(retry_attempt_count=3)  # equals max of 3
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope == SCOPE_BLOCKED
        assert "RETRY_BUDGET_EXHAUSTED" in a.reason_codes

    def test_retry_within_budget_continues(self):
        ctx = _shadow_ctx(retry_attempt_count=1)  # less than max of 3
        a = assess_provider_orchestration(ctx)
        assert a.governance_scope != SCOPE_BLOCKED


# ── TestAttributionContinuity ─────────────────────────────────────────────────

class TestAttributionContinuity:

    def test_origin_source_propagated_to_assessment(self):
        ctx = _shadow_ctx(origin_source="ssip_test_source")
        a = assess_provider_orchestration(ctx)
        assert a.origin_source == "ssip_test_source"

    def test_origin_authority_propagated_to_assessment(self):
        ctx = _shadow_ctx(origin_authority="platform_authority")
        a = assess_provider_orchestration(ctx)
        assert a.origin_authority == "platform_authority"

    def test_correlation_id_propagated_to_assessment(self):
        cid = _uuid()
        ctx = _shadow_ctx(correlation_id=cid)
        a = assess_provider_orchestration(ctx)
        assert a.correlation_id == cid

    def test_causation_id_propagated_to_assessment(self):
        cid = _uuid()
        ctx = _shadow_ctx(causation_id=cid)
        a = assess_provider_orchestration(ctx)
        assert a.causation_id == cid

    def test_upstream_intent_id_propagated_to_assessment(self):
        uid = _uuid()
        ctx = _shadow_ctx(upstream_intent_id=uid)
        a = assess_provider_orchestration(ctx)
        assert a.upstream_intent_id == uid

    def test_attribution_propagated_through_blocked_path(self):
        src = "ssip_blocked_path"
        ctx = _full_ctx(origin_source=src, config_version_id=None)
        a = assess_provider_orchestration(ctx)
        # RULE 0 blocks before checking origin_source, but source is still None if not set
        # Here origin_source IS set, so it should propagate
        assert a.origin_source == src

    def test_attribution_propagated_through_replay_path(self):
        cid = _uuid()
        ctx = _replay_ctx(correlation_id=cid)
        a = assess_provider_orchestration(ctx)
        assert a.correlation_id == cid


# ── TestUnknownV0Substitution ─────────────────────────────────────────────────

class TestUnknownV0Substitution:

    def test_missing_config_key_resolves_to_unknown_v0(self):
        ctx = _shadow_ctx(config_rule_set={})
        a = assess_provider_orchestration(ctx)
        assert all(v == UNKNOWN_V0 for v in a.threshold_bindings.values())

    def test_unknown_v0_input_is_treated_as_missing(self):
        ctx = _shadow_ctx(config_rule_set={
            "provider_failure_max_retry_attempts": UNKNOWN_V0,
        })
        a = assess_provider_orchestration(ctx)
        assert a.threshold_bindings.get("provider_failure_max_retry_attempts") == UNKNOWN_V0

    def test_replay_thresholds_are_all_unknown_v0(self):
        ctx = _replay_ctx(config_rule_set=dict(_FULL_RULE_SET))
        a = assess_provider_orchestration(ctx)
        assert all(v == UNKNOWN_V0 for v in a.threshold_bindings.values())

    def test_no_hardcoded_defaults_in_empty_rule_set(self):
        ctx = _shadow_ctx(config_rule_set={})
        a = assess_provider_orchestration(ctx)
        for v in a.threshold_bindings.values():
            assert v == UNKNOWN_V0, f"Expected UNKNOWN_V0, got hardcoded value: {v}"

    def test_partial_rule_set_only_resolved_keys_are_non_unknown(self):
        ctx = _shadow_ctx(config_rule_set={
            "provider_failure_max_retry_attempts": 5,
        })
        a = assess_provider_orchestration(ctx)
        assert a.threshold_bindings["provider_failure_max_retry_attempts"] == 5
        assert a.threshold_bindings["provider_failure_circuit_breaker_threshold"] == UNKNOWN_V0


# ── TestDegradationObservability ──────────────────────────────────────────────

class TestDegradationObservability:

    def test_degradation_cause_set_for_outage(self):
        ctx = _shadow_ctx(provider_outage_active=True)
        a = assess_provider_orchestration(ctx)
        assert a.degradation_cause == "provider_outage"

    def test_degradation_cause_set_for_sync_lag(self):
        ctx = _shadow_ctx(sync_lag_hours=10.0)
        a = assess_provider_orchestration(ctx)
        assert a.degradation_cause == "sync_lag_exceeded"

    def test_degradation_cause_set_for_missing_thresholds(self):
        # RULE 10 (threshold degradation) runs only on LIVE paths — shadow exits at RULE 6
        ctx = _full_ctx(config_rule_set={})
        a = assess_provider_orchestration(ctx)
        assert a.degraded is True
        assert a.degradation_cause is not None

    def test_outage_takes_priority_over_sync_lag_for_cause(self):
        ctx = _shadow_ctx(provider_outage_active=True, sync_lag_hours=10.0)
        a = assess_provider_orchestration(ctx)
        # outage is RULE 4, sync lag is RULE 5 — outage degrades first
        assert a.degradation_cause == "provider_outage"

    def test_non_degraded_path_has_no_degradation_cause(self):
        ctx = _shadow_ctx()
        a = assess_provider_orchestration(ctx)
        if not a.degraded:
            assert a.degradation_cause is None

    def test_degradation_codes_present_in_reason_codes(self):
        ctx = _shadow_ctx(provider_outage_active=True, sync_lag_hours=10.0)
        a = assess_provider_orchestration(ctx)
        assert "PROVIDER_OUTAGE_ACTIVE" in a.reason_codes
        assert "SYNC_LAG_EXCEEDED" in a.reason_codes


# ── TestGovernanceInvariantPreservation ───────────────────────────────────────

class TestGovernanceInvariantPreservation:

    def test_assessment_always_has_event_id(self):
        for ctx in [_shadow_ctx(), _replay_ctx(), _full_ctx(), _full_ctx(config_version_id=None)]:
            a = assess_provider_orchestration(ctx)
            assert a.event_id and len(a.event_id) > 0

    def test_rule_path_always_starts_with_rule_0(self):
        for ctx in [_shadow_ctx(), _replay_ctx(), _full_ctx(config_version_id=None)]:
            a = assess_provider_orchestration(ctx)
            assert a.rule_path_taken[0] == "RULE_0"

    def test_blocked_assessment_orchestration_does_not_continue(self):
        ctx = _full_ctx(compliance_hold_active=True)
        a = assess_provider_orchestration(ctx)
        assert a.orchestration_continues is False

    def test_replay_assessment_orchestration_continues(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.orchestration_continues is True

    def test_provider_is_always_ghl(self):
        for ctx in [_shadow_ctx(), _replay_ctx(), _full_ctx(), _full_ctx(config_version_id=None)]:
            a = assess_provider_orchestration(ctx)
            assert a.provider == "ghl"

    def test_execution_mode_preserved_in_assessment(self):
        a_shadow = assess_provider_orchestration(_shadow_ctx())
        assert a_shadow.execution_mode == "SHADOW"
        a_live = assess_provider_orchestration(_full_ctx())
        assert a_live.execution_mode == "LIVE"

    def test_execution_type_preserved_in_assessment(self):
        a = assess_provider_orchestration(_replay_ctx())
        assert a.execution_type == "replay"

    def test_duration_ms_is_non_negative(self):
        for ctx in [_shadow_ctx(), _replay_ctx(), _full_ctx()]:
            a = assess_provider_orchestration(ctx)
            assert a.duration_ms >= 0


# ── TestIdempotencyProtection ─────────────────────────────────────────────────

class TestIdempotencyProtection:

    def setup_method(self):
        ghl_module._outbound_idempotency_keys.clear()

    def test_duplicate_idempotency_key_is_suppressed(self):
        key = _uuid()
        # First call registers the key
        assess_provider_orchestration(_full_ctx(idempotency_key=key))
        # Second call with the same key is a duplicate
        second = assess_provider_orchestration(_full_ctx(idempotency_key=key))
        assert second.governance_scope == SCOPE_DUPLICATE_SUPPRESSED
        assert "IDEMPOTENCY_DUPLICATE_SUPPRESSED" in second.reason_codes

    def test_different_idempotency_keys_are_not_suppressed(self):
        a1 = assess_provider_orchestration(_full_ctx(idempotency_key=_uuid()))
        a2 = assess_provider_orchestration(_full_ctx(idempotency_key=_uuid()))
        assert a1.governance_scope != SCOPE_DUPLICATE_SUPPRESSED
        assert a2.governance_scope != SCOPE_DUPLICATE_SUPPRESSED

    def test_duplicate_scope_is_duplicate_suppressed(self):
        key = _uuid()
        assess_provider_orchestration(_full_ctx(idempotency_key=key))
        a = assess_provider_orchestration(_full_ctx(idempotency_key=key))
        assert a.governance_scope == SCOPE_DUPLICATE_SUPPRESSED

    def test_null_idempotency_key_not_deduplicated(self):
        # Two calls with no idempotency key should NOT trigger dedup
        a1 = assess_provider_orchestration(_full_ctx(idempotency_key=None))
        a2 = assess_provider_orchestration(_full_ctx(idempotency_key=None))
        assert a1.governance_scope != SCOPE_DUPLICATE_SUPPRESSED
        assert a2.governance_scope != SCOPE_DUPLICATE_SUPPRESSED

    def test_dedup_outbound_suppressed(self):
        key = _uuid()
        assess_provider_orchestration(_full_ctx(idempotency_key=key))
        a = assess_provider_orchestration(_full_ctx(idempotency_key=key))
        assert a.outbound_suppressed is True
        assert a.outbound_blocked is True

    def test_shadow_context_does_not_register_idempotency_key(self):
        key = _uuid()
        # Shadow mode exits at RULE 6, before RULE 9 — key must not be registered
        assess_provider_orchestration(_shadow_ctx(idempotency_key=key))
        assert key not in ghl_module._outbound_idempotency_keys

    def test_replay_context_does_not_register_idempotency_key(self):
        key = _uuid()
        # Replay exits at RULE 1 — key must not be registered
        assess_provider_orchestration(_replay_ctx(idempotency_key=key))
        assert key not in ghl_module._outbound_idempotency_keys
