"""
Governance certification suite for the orchestration prioritization advisory service.

Self-contained: no mocks, no patches. Direct invocation of assess_orchestration_priority.
Validates all governance contracts: RULE 0-10, AP-D*, AP-E*, FAD-4, IML-1/3, INV-4/5.
"""
from __future__ import annotations

import uuid

import app.services.priority as priority_module
from app.services.priority import assess_orchestration_priority
from app.services._priority_types import (
    AI_ARCHIVED,
    AI_GENERATION_FAILED,
    AI_GENERATING,
    AI_PENDING,
    AI_RECOMMEND_ESCALATE,
    AI_RECOMMEND_MEETING,
    AI_RECOMMEND_OUTREACH,
    AI_REVIEWED,
    BASIS_AI_ASSISTED,
    BASIS_FALLBACK,
    BASIS_HISTORICAL_REPLAY,
    BASIS_RULE_BASED,
    K_AVG_EFF_RATING,
    K_ESCALATION_REPEAT,
    K_HWS_BEHIND_HIGH_RISK,
    K_HWS_BEHIND_MODERATE,
    K_INACTIVITY_HIGH_RISK,
    K_INACTIVITY_MODERATE,
    K_PAYMENT_RISK,
    OUTCOME_DEFERRED,
    OUTCOME_FAILURE,
    OUTCOME_SHADOW_ONLY,
    OUTCOME_SUCCESS,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_UNKNOWN,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    TIER_ADVISORY,
    TIER_CONFIDENT,
    TIER_FINALIZED_COPY,
    TIER_IN_FLIGHT,
    TIER_STALE,
    TIER_UNAVAILABLE,
    TREND_CRITICAL,
    TREND_DECLINING,
    UNKNOWN_V0,
    PrioritizationContext,
)


# ── Test helpers ───────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


_FULL_RULE_SET = {
    "hws_behind_high_risk_threshold": 5,
    "hws_behind_moderate_threshold": 2,
    "avg_eff_rating_low_risk_threshold": 2.5,
    "last_activity_high_risk_days": 14,
    "last_activity_moderate_days": 7,
    "payment_balance_risk_threshold": 500.0,
    "prior_escalation_repeat_threshold": 3,
    "ai_insight_ttl_hours": 48,
}


def _live_ctx(**overrides) -> PrioritizationContext:
    """Valid LIVE context with full attribution and a complete rule set."""
    base = dict(
        config_version_id="cfg-v2-priority-test",
        execution_mode="LIVE",
        execution_type="original",
        correlation_id=_uuid(),
        causation_id=_uuid(),
        orchestration_cycle_id=_uuid(),
        idempotency_key=_uuid(),
        origin_source="scheduler",
        origin_authority="platform_supplementary",
        actor_identity="orchestration_scheduler@system",
        attribution_timestamp="2026-01-01T00:00:00+00:00",
        config_rule_set=dict(_FULL_RULE_SET),
    )
    base.update(overrides)
    return PrioritizationContext(**base)


def _shadow_ctx(**overrides) -> PrioritizationContext:
    return _live_ctx(execution_mode="SHADOW", **overrides)


def _replay_ctx(**overrides) -> PrioritizationContext:
    defaults = dict(
        execution_type="replay",
        source_artifact_id="priority-artifact-001",
        idempotency_key=None,
    )
    defaults.update(overrides)
    return _live_ctx(**defaults)


# ── RULE 0: Precondition gate ──────────────────────────────────────────────────

class TestRule0PreconditionGate:

    def test_missing_config_version_id_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(config_version_id=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "CONFIG_VERSION_ID_MISSING" in r.reason_codes

    def test_missing_correlation_id_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "CORRELATION_ID_MISSING" in r.reason_codes

    def test_invalid_execution_mode_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(execution_mode="INVALID", idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_MODE" in r.reason_codes

    def test_invalid_execution_type_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(execution_type="bad_type", idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_TYPE" in r.reason_codes

    def test_missing_origin_source_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(origin_source=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "ORIGIN_SOURCE_MISSING" in r.reason_codes

    def test_missing_origin_authority_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(origin_authority=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "ORIGIN_AUTHORITY_MISSING" in r.reason_codes

    def test_missing_actor_identity_is_blocked(self):
        r = assess_orchestration_priority(_live_ctx(actor_identity=None, idempotency_key=None))
        assert r.orchestration_blocked is True
        assert "ACTOR_IDENTITY_MISSING" in r.reason_codes

    def test_blocked_record_outcome_is_failure(self):
        r = assess_orchestration_priority(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.outcome == OUTCOME_FAILURE

    def test_blocked_record_scope_is_unavailable(self):
        r = assess_orchestration_priority(_live_ctx(config_version_id=None, idempotency_key=None))
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_valid_context_passes_gate(self):
        r = assess_orchestration_priority(_live_ctx())
        assert r.orchestration_blocked is False
        assert "RULE_0" in r.rule_path_taken


# ── Maintenance suppression ────────────────────────────────────────────────────

class TestMaintenanceSuppression:

    def test_maintenance_mode_suspends_assessment(self):
        r = assess_orchestration_priority(_live_ctx(maintenance_mode_active=True))
        assert r.governance_scope == SCOPE_MAINTENANCE
        assert "MAINTENANCE_MODE_ACTIVE" in r.reason_codes

    def test_maintenance_outcome_is_success(self):
        r = assess_orchestration_priority(_live_ctx(maintenance_mode_active=True))
        assert r.outcome == OUTCOME_SUCCESS

    def test_maintenance_scoring_emit_not_authorized(self):
        r = assess_orchestration_priority(_live_ctx(maintenance_mode_active=True))
        assert r.scoring_emit_authorized is False

    def test_maintenance_live_effects_suppressed(self):
        r = assess_orchestration_priority(_live_ctx(maintenance_mode_active=True))
        assert r.live_effects_suppressed is True

    def test_maintenance_path_includes_rule_1(self):
        r = assess_orchestration_priority(_live_ctx(maintenance_mode_active=True))
        assert "RULE_1" in r.rule_path_taken

    def test_maintenance_exits_before_scoring(self):
        r = assess_orchestration_priority(_live_ctx(maintenance_mode_active=True))
        assert r.scoring_factors == []
        assert r.risk_contributions == []


# ── Replay containment ─────────────────────────────────────────────────────────

class TestReplayContainment:

    def test_replay_type_produces_replay_only_scope(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_type_produces_replay_only_scope(self):
        r = assess_orchestration_priority(_replay_ctx(execution_type="regeneration"))
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_live_effects_suppressed(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.live_effects_suppressed is True

    def test_replay_is_replay_flag(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.is_replay is True

    def test_replay_no_live_priority(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.advisory_priority == PRIORITY_UNKNOWN

    def test_replay_basis_is_historical(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.assessment_basis == BASIS_HISTORICAL_REPLAY

    def test_replay_without_source_artifact_is_degraded(self):
        r = assess_orchestration_priority(_replay_ctx(source_artifact_id=None))
        assert r.degraded is True
        assert "REPLAY_SOURCE_ARTIFACT_MISSING" in r.degradation_flags

    def test_replay_with_source_artifact_not_degraded(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.degraded is False

    def test_replay_orchestration_continues(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.orchestration_continues is True

    def test_replay_lineage_preserved_unconditional(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.replay_lineage_preserved is True

    def test_replay_exits_before_scoring(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.scoring_factors == []

    def test_replay_attribution_propagated(self):
        r = assess_orchestration_priority(_replay_ctx(origin_source="mirrored_sql_server"))
        assert r.origin_source == "mirrored_sql_server"


# ── Config threshold resolution ────────────────────────────────────────────────

class TestConfigThresholdResolution:

    def test_full_rule_set_resolves_all_thresholds(self):
        r = assess_orchestration_priority(_live_ctx())
        for k in _FULL_RULE_SET:
            assert r.threshold_bindings.get(k) == _FULL_RULE_SET[k]

    def test_missing_threshold_resolves_to_unknown_v0(self):
        r = assess_orchestration_priority(_live_ctx(config_rule_set={}))
        assert r.threshold_bindings.get(K_HWS_BEHIND_HIGH_RISK) == UNKNOWN_V0

    def test_missing_threshold_emits_degradation_flag(self):
        r = assess_orchestration_priority(_live_ctx(config_rule_set={}))
        assert any("CONFIG_THRESHOLD_MISSING" in f for f in r.degradation_flags)

    def test_unknown_v0_sentinel_in_rule_set_treated_as_missing(self):
        rs = dict(_FULL_RULE_SET)
        rs[K_HWS_BEHIND_HIGH_RISK] = UNKNOWN_V0
        r = assess_orchestration_priority(_live_ctx(config_rule_set=rs))
        assert r.threshold_bindings[K_HWS_BEHIND_HIGH_RISK] == UNKNOWN_V0

    def test_partial_rule_set_leaves_missing_keys_as_unknown_v0(self):
        partial = {"hws_behind_high_risk_threshold": 5}
        r = assess_orchestration_priority(_live_ctx(config_rule_set=partial))
        assert r.threshold_bindings[K_INACTIVITY_HIGH_RISK] == UNKNOWN_V0
        assert r.threshold_bindings[K_HWS_BEHIND_HIGH_RISK] == 5


# ── AI governance tier classification ─────────────────────────────────────────

class TestAIGovernanceTierClassification:

    def test_ai_reviewed_fresh_high_confidence_is_confident(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.85, ai_stale_flag=False,
        ))
        assert r.ai_governance_tier == TIER_CONFIDENT

    def test_ai_reviewed_fresh_low_confidence_is_advisory(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.50, ai_stale_flag=False,
        ))
        assert r.ai_governance_tier == TIER_ADVISORY

    def test_ai_reviewed_stale_is_stale_tier(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.90, ai_stale_flag=True,
        ))
        assert r.ai_governance_tier == TIER_STALE

    def test_ai_generating_is_in_flight(self):
        r = assess_orchestration_priority(_live_ctx(ai_insight_state=AI_GENERATING))
        assert r.ai_governance_tier == TIER_IN_FLIGHT

    def test_ai_pending_is_in_flight(self):
        r = assess_orchestration_priority(_live_ctx(ai_insight_state=AI_PENDING))
        assert r.ai_governance_tier == TIER_IN_FLIGHT

    def test_ai_generation_failed_is_unavailable(self):
        r = assess_orchestration_priority(_live_ctx(ai_insight_state=AI_GENERATION_FAILED))
        assert r.ai_governance_tier == TIER_UNAVAILABLE

    def test_ai_absent_is_unavailable(self):
        r = assess_orchestration_priority(_live_ctx(ai_insight_state=None))
        assert r.ai_governance_tier == TIER_UNAVAILABLE

    def test_ai_finalized_copy_is_finalized_copy_tier(self):
        r = assess_orchestration_priority(_live_ctx(ai_finalized_copy=True))
        assert r.ai_governance_tier == TIER_FINALIZED_COPY

    def test_in_flight_original_produces_deferred_outcome(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_GENERATING, execution_type="original",
        ))
        assert r.outcome == OUTCOME_DEFERRED
        assert r.advisory_priority == PRIORITY_UNKNOWN
        assert "AI_INSIGHT_IN_FLIGHT_DEFER" in r.reason_codes


# ── Multi-factor risk scoring ──────────────────────────────────────────────────

class TestMultiFactorRiskScoring:

    def test_hws_behind_high_risk_produces_high_contribution(self):
        r = assess_orchestration_priority(_live_ctx(hws_behind=6))
        assert "HWS_BEHIND_HIGH_RISK" in r.reason_codes
        assert "HIGH" in r.risk_contributions

    def test_hws_behind_moderate_produces_medium_contribution(self):
        r = assess_orchestration_priority(_live_ctx(hws_behind=3))
        assert "HWS_BEHIND_MODERATE_RISK" in r.reason_codes
        assert "MEDIUM" in r.risk_contributions

    def test_low_eff_rating_produces_medium_contribution(self):
        r = assess_orchestration_priority(_live_ctx(avg_eff_rating=1.5))
        assert "EFF_RATING_MEDIUM_RISK" in r.reason_codes
        assert "MEDIUM" in r.risk_contributions

    def test_high_inactivity_produces_high_contribution(self):
        r = assess_orchestration_priority(_live_ctx(last_activity_days=20))
        assert "INACTIVITY_HIGH_RISK" in r.reason_codes
        assert "HIGH" in r.risk_contributions

    def test_moderate_inactivity_produces_medium_contribution(self):
        r = assess_orchestration_priority(_live_ctx(last_activity_days=10))
        assert "INACTIVITY_MODERATE_RISK" in r.reason_codes
        assert "MEDIUM" in r.risk_contributions

    def test_high_payment_balance_produces_medium_contribution(self):
        r = assess_orchestration_priority(_live_ctx(payment_balance=750.0))
        assert "PAYMENT_BALANCE_MEDIUM_RISK" in r.reason_codes
        assert "MEDIUM" in r.risk_contributions

    def test_historical_trend_critical_produces_high_contribution(self):
        r = assess_orchestration_priority(_live_ctx(historical_risk_trend=TREND_CRITICAL))
        assert "HISTORICAL_TREND_CRITICAL" in r.reason_codes
        assert "HIGH" in r.risk_contributions

    def test_historical_trend_declining_produces_medium_contribution(self):
        r = assess_orchestration_priority(_live_ctx(historical_risk_trend=TREND_DECLINING))
        assert "HISTORICAL_TREND_DECLINING" in r.reason_codes
        assert "MEDIUM" in r.risk_contributions

    def test_missing_threshold_skips_that_factor(self):
        # No HWS threshold — factor should not fire even with high hws_behind
        rs = {k: v for k, v in _FULL_RULE_SET.items()
              if k not in (K_HWS_BEHIND_HIGH_RISK, K_HWS_BEHIND_MODERATE)}
        r = assess_orchestration_priority(_live_ctx(hws_behind=100, config_rule_set=rs))
        assert "HWS_BEHIND_HIGH_RISK" not in r.reason_codes

    def test_no_signals_produces_low_priority(self):
        r = assess_orchestration_priority(_live_ctx())
        assert r.advisory_priority == PRIORITY_LOW


# ── Priority tier classification ───────────────────────────────────────────────

class TestPriorityTierClassification:

    def test_two_high_contributions_produce_critical(self):
        r = assess_orchestration_priority(_live_ctx(
            hws_behind=6,         # HIGH
            last_activity_days=20, # HIGH
        ))
        assert r.advisory_priority == PRIORITY_CRITICAL

    def test_one_high_one_medium_produce_high(self):
        r = assess_orchestration_priority(_live_ctx(
            hws_behind=6,         # HIGH
            avg_eff_rating=1.5,   # MEDIUM
        ))
        assert r.advisory_priority == PRIORITY_HIGH

    def test_one_high_no_medium_produces_medium(self):
        r = assess_orchestration_priority(_live_ctx(
            hws_behind=6,         # HIGH only
        ))
        assert r.advisory_priority == PRIORITY_MEDIUM

    def test_medium_only_produces_medium(self):
        r = assess_orchestration_priority(_live_ctx(
            avg_eff_rating=1.5,   # MEDIUM
        ))
        assert r.advisory_priority == PRIORITY_MEDIUM

    def test_no_signals_produces_low(self):
        r = assess_orchestration_priority(_live_ctx())
        assert r.advisory_priority == PRIORITY_LOW

    def test_scoring_factors_carry_threshold_lineage(self):
        r = assess_orchestration_priority(_live_ctx(hws_behind=6))
        hw_factor = next((f for f in r.scoring_factors if f["factor"] == "hws_behind"), None)
        assert hw_factor is not None
        assert hw_factor["threshold_key"] == K_HWS_BEHIND_HIGH_RISK
        assert hw_factor["value"] == 6


# ── AI advisory priority adjustment ───────────────────────────────────────────

class TestAIPriorityAdjustment:

    def test_confident_escalate_upgrades_to_critical(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.90, ai_stale_flag=False,
            ai_recommended_intervention=AI_RECOMMEND_ESCALATE,
        ))
        assert r.advisory_priority == PRIORITY_CRITICAL
        assert r.ai_priority_adjustment_applied is True
        assert r.assessment_basis == BASIS_AI_ASSISTED
        assert "AI_CONFIDENT_ESCALATE_TO_CRITICAL" in r.reason_codes

    def test_confident_meeting_upgrades_one_level(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.90, ai_stale_flag=False,
            ai_recommended_intervention=AI_RECOMMEND_MEETING,
            avg_eff_rating=1.5,   # base MEDIUM
        ))
        assert r.advisory_priority == PRIORITY_HIGH
        assert r.ai_priority_adjustment_applied is True
        assert "AI_CONFIDENT_PRIORITY_UPGRADED" in r.reason_codes

    def test_advisory_escalate_upgrades_one_level(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.55, ai_stale_flag=False,
            ai_recommended_intervention=AI_RECOMMEND_ESCALATE,
            avg_eff_rating=1.5,   # base MEDIUM
        ))
        assert r.advisory_priority == PRIORITY_HIGH   # MEDIUM → HIGH (one level)
        assert r.ai_priority_adjustment_applied is True
        assert "AI_ADVISORY_PRIORITY_UPGRADED" in r.reason_codes

    def test_stale_ai_no_adjustment(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.90, ai_stale_flag=True,
            ai_recommended_intervention=AI_RECOMMEND_ESCALATE,
        ))
        assert r.ai_priority_adjustment_applied is False
        assert "STALE_AI_PRIORITIZATION_SKIPPED" in r.reason_codes

    def test_unavailable_ai_sets_fallback_applied(self):
        r = assess_orchestration_priority(_live_ctx(ai_insight_state=None))
        assert r.ai_fallback_applied is True
        assert r.assessment_basis == BASIS_FALLBACK
        assert "AI_UNAVAILABLE_FALLBACK_APPLIED" in r.reason_codes

    def test_finalized_copy_no_adjustment(self):
        r = assess_orchestration_priority(_live_ctx(
            ai_finalized_copy=True,
            ai_recommended_intervention=AI_RECOMMEND_ESCALATE,
        ))
        assert r.ai_priority_adjustment_applied is False
        assert "AI_FINALIZED_COPY_NOT_APPLIED" in r.reason_codes

    def test_critical_priority_not_exceeded_by_upward_adjustment(self):
        # CRITICAL → CRITICAL even with CONFIDENT MEETING upgrade attempt
        r = assess_orchestration_priority(_live_ctx(
            hws_behind=6,          # HIGH
            last_activity_days=20, # HIGH → CRITICAL
            ai_insight_state=AI_REVIEWED, ai_confidence_score=0.90, ai_stale_flag=False,
            ai_recommended_intervention=AI_RECOMMEND_MEETING,
        ))
        assert r.advisory_priority == PRIORITY_CRITICAL  # already at ceiling


# ── Shadow/LIVE containment ────────────────────────────────────────────────────

class TestShadowContainment:

    def test_shadow_mode_produces_shadow_only_scope(self):
        r = assess_orchestration_priority(_shadow_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_produces_shadow_only_until_phase12(self):
        r = assess_orchestration_priority(_live_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_emits_phase11_reason_code(self):
        r = assess_orchestration_priority(_live_ctx())
        assert "LIVE_SCOPE_SHADOW_ONLY_PHASE11" in r.reason_codes

    def test_scoring_emit_not_authorized_in_shadow(self):
        r = assess_orchestration_priority(_shadow_ctx())
        assert r.scoring_emit_authorized is False

    def test_scoring_emit_not_authorized_in_live(self):
        r = assess_orchestration_priority(_live_ctx())
        assert r.scoring_emit_authorized is False

    def test_live_effects_suppressed_in_shadow(self):
        r = assess_orchestration_priority(_shadow_ctx())
        assert r.live_effects_suppressed is True

    def test_live_effects_suppressed_in_live_phase11(self):
        r = assess_orchestration_priority(_live_ctx())
        assert r.live_effects_suppressed is True

    def test_shadow_outcome_is_shadow_only(self):
        r = assess_orchestration_priority(_shadow_ctx())
        assert r.outcome == OUTCOME_SHADOW_ONLY


# ── Attribution continuity ────────────────────────────────────────────────────

class TestAttributionContinuity:

    def test_origin_source_propagated(self):
        r = assess_orchestration_priority(_live_ctx(origin_source="operator"))
        assert r.origin_source == "operator"

    def test_origin_authority_propagated(self):
        r = assess_orchestration_priority(_live_ctx(origin_authority="operator_authorized"))
        assert r.origin_authority == "operator_authorized"

    def test_actor_identity_propagated(self):
        r = assess_orchestration_priority(_live_ctx(actor_identity="test_actor@system"))
        assert r.actor_identity == "test_actor@system"

    def test_correlation_id_propagated(self):
        cid = _uuid()
        r = assess_orchestration_priority(_live_ctx(correlation_id=cid))
        assert r.correlation_id == cid

    def test_causation_id_propagated(self):
        cid = _uuid()
        r = assess_orchestration_priority(_live_ctx(causation_id=cid))
        assert r.causation_id == cid

    def test_config_version_id_propagated(self):
        r = assess_orchestration_priority(_live_ctx(config_version_id="cfg-v2-attr-test"))
        assert r.config_version_id == "cfg-v2-attr-test"

    def test_execution_mode_propagated(self):
        r = assess_orchestration_priority(_shadow_ctx())
        assert r.execution_mode == "SHADOW"

    def test_blocked_record_still_propagates_attribution(self):
        r = assess_orchestration_priority(_live_ctx(
            correlation_id=None, origin_source="my_source", idempotency_key=None,
        ))
        assert r.orchestration_blocked is True
        assert r.origin_source == "my_source"


# ── Scoring lineage preservation ───────────────────────────────────────────────

class TestScoringLineagePreservation:

    def test_scoring_factors_include_threshold_key(self):
        r = assess_orchestration_priority(_live_ctx(hws_behind=6))
        assert any(f["threshold_key"] == K_HWS_BEHIND_HIGH_RISK for f in r.scoring_factors)

    def test_scoring_factors_include_actual_value(self):
        r = assess_orchestration_priority(_live_ctx(hws_behind=8))
        hw_factor = next((f for f in r.scoring_factors if f["factor"] == "hws_behind"), None)
        assert hw_factor is not None
        assert hw_factor["value"] == 8

    def test_replay_scoring_lineage_preserved_unconditional(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.replay_lineage_preserved is True

    def test_no_factors_on_blocked_path(self):
        r = assess_orchestration_priority(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.scoring_factors == []

    def test_threshold_bindings_in_output_match_rule_set(self):
        r = assess_orchestration_priority(_live_ctx(hws_behind=6))
        assert r.threshold_bindings[K_HWS_BEHIND_HIGH_RISK] == _FULL_RULE_SET[K_HWS_BEHIND_HIGH_RISK]


# ── Idempotency deduplication ──────────────────────────────────────────────────

class TestIdempotencyDeduplication:

    def setup_method(self):
        priority_module._priority_idempotency_keys.clear()

    def test_first_call_with_key_succeeds(self):
        r = assess_orchestration_priority(_live_ctx(idempotency_key="idem-001"))
        assert r.orchestration_blocked is False

    def test_duplicate_key_on_second_call_is_blocked(self):
        assess_orchestration_priority(_live_ctx(idempotency_key="idem-dup"))
        r = assess_orchestration_priority(_live_ctx(idempotency_key="idem-dup"))
        assert r.orchestration_blocked is True
        assert "IDEMPOTENCY_DUPLICATE_DETECTED" in r.reason_codes

    def test_different_keys_both_succeed(self):
        r1 = assess_orchestration_priority(_live_ctx(idempotency_key="idem-a"))
        r2 = assess_orchestration_priority(_live_ctx(idempotency_key="idem-b"))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False

    def test_replay_type_does_not_register_key(self):
        assess_orchestration_priority(_replay_ctx(idempotency_key=None))
        assert len(priority_module._priority_idempotency_keys) == 0

    def test_no_key_never_triggers_duplicate_check(self):
        r1 = assess_orchestration_priority(_live_ctx(idempotency_key=None))
        r2 = assess_orchestration_priority(_live_ctx(idempotency_key=None))
        assert r1.orchestration_blocked is False
        assert r2.orchestration_blocked is False


# ── Invariant preservation ────────────────────────────────────────────────────

class TestInvariantPreservation:

    def setup_method(self):
        priority_module._priority_idempotency_keys.clear()

    def _all_contexts(self):
        """Return one record for each major exit path."""
        return [
            assess_orchestration_priority(_live_ctx(correlation_id=None, idempotency_key=None)),  # blocked
            assess_orchestration_priority(_live_ctx(maintenance_mode_active=True)),               # maintenance
            assess_orchestration_priority(_replay_ctx()),                                          # replay
            assess_orchestration_priority(_live_ctx()),                                            # normal
            assess_orchestration_priority(_shadow_ctx()),                                          # shadow
        ]

    def test_append_only_enforced_unconditional_on_all_paths(self):
        for r in self._all_contexts():
            assert r.append_only_enforced is True

    def test_replay_lineage_preserved_unconditional_on_all_paths(self):
        for r in self._all_contexts():
            assert r.replay_lineage_preserved is True

    def test_scoring_lineage_immutable_unconditional_on_all_paths(self):
        for r in self._all_contexts():
            assert r.scoring_lineage_immutable is True

    def test_no_scoring_emit_authorized_without_phase12_cert(self):
        for r in self._all_contexts():
            assert r.scoring_emit_authorized is False

    def test_live_effects_never_permitted_outside_authorized_scope(self):
        for r in self._all_contexts():
            assert r.live_effects_suppressed is True

    def test_every_path_emits_event_id(self):
        for r in self._all_contexts():
            assert r.event_id is not None and r.event_id != ""

    def test_every_path_emits_rule_path(self):
        for r in self._all_contexts():
            assert len(r.rule_path_taken) >= 1
            assert "RULE_0" in r.rule_path_taken

    def test_every_path_emits_duration_ms(self):
        for r in self._all_contexts():
            assert isinstance(r.duration_ms, int) and r.duration_ms >= 0

    def test_orchestration_continues_false_on_blocked(self):
        r = assess_orchestration_priority(_live_ctx(correlation_id=None, idempotency_key=None))
        assert r.orchestration_continues is False

    def test_orchestration_continues_true_on_shadow_scope(self):
        r = assess_orchestration_priority(_shadow_ctx())
        assert r.orchestration_continues is True

    def test_orchestration_continues_true_on_replay(self):
        r = assess_orchestration_priority(_replay_ctx())
        assert r.orchestration_continues is True

    def test_degradation_cause_set_iff_degraded(self):
        r_degraded = assess_orchestration_priority(_live_ctx(config_rule_set={}))
        r_clean = assess_orchestration_priority(_live_ctx())
        assert r_degraded.degraded is True
        assert r_degraded.degradation_cause is not None
        if not r_clean.degraded:
            assert r_clean.degradation_cause is None

    def test_reason_codes_always_list(self):
        for r in self._all_contexts():
            assert isinstance(r.reason_codes, list)
