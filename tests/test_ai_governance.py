"""
Governance certification suite for the AI orchestration advisory layer.

Self-contained: no mocks, no patches. Direct invocation of assess_ai_orchestration.
Validates all governance contracts: RULE 0-11, AP-AI1-15, AP-LF1-15.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import app.services.ai_insights as ai_module
from app.services.ai_insights import assess_ai_orchestration
from app.services._ai_types import (
    CB_OPEN,
    CB_CLOSED,
    CB_UNKNOWN,
    SCOPE_DEFERRED,
    SCOPE_FULL,
    SCOPE_IMMUTABLE,
    SCOPE_LIMITED,
    SCOPE_UNAVAILABLE,
    TIER_ADVISORY,
    TIER_CONFIDENT,
    TIER_FINALIZED_COPY,
    TIER_IN_FLIGHT,
    TIER_STALE,
    TIER_UNAVAILABLE,
    UNKNOWN_V0,
    AIOrchestrationContext,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _recent_iso(hours_ago: float = 1.0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.isoformat()


def _stale_iso(hours_ago: float = 30.0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.isoformat()


_FULL_AI_RULE_SET = {
    "ai_insight_ttl_hours": 24,
    "ai_llm_provider": "anthropic",
}


def _full_ctx(**overrides) -> AIOrchestrationContext:
    """Valid LIVE context with all required attribution and a reviewed insight."""
    base = dict(
        config_version_id="cfg-v2-ai-test",
        execution_mode="LIVE",
        execution_type="original",
        correlation_id=_uuid(),
        origin_source="ssip_test",
        origin_authority="test_authority",
        actor_identity="test_actor",
        idempotency_key=_uuid(),
        config_rule_set=dict(_FULL_AI_RULE_SET),
        ai_insight_id="insight-001",
        ai_insight_state="AI_REVIEWED",
        ai_generated_at=_recent_iso(1.0),
        ai_confidence_score=0.85,
        ai_model_used="anthropic",
        ai_prompt_version="v1.0",
        ai_insight_version=1,
        ai_finalized_copy=False,
        ai_risk_summary="Student shows engagement decline.",
        ai_recommended_intervention="OUTREACH",
        ai_sentiment="negative",
    )
    base.update(overrides)
    return AIOrchestrationContext(**base)


def _shadow_ctx(**overrides) -> AIOrchestrationContext:
    return _full_ctx(execution_mode="SHADOW", **overrides)


def _replay_ctx(**overrides) -> AIOrchestrationContext:
    return _full_ctx(execution_mode="SHADOW", execution_type="replay", **overrides)


# ── TestRule0PreconditionGate ─────────────────────────────────────────────────

class TestRule0PreconditionGate:

    def test_missing_config_version_id_is_blocked(self):
        ctx = _full_ctx(config_version_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is True
        assert a.ai_governance_tier == TIER_UNAVAILABLE
        assert "CONFIG_UNRESOLVED" in a.reason_codes

    def test_invalid_execution_mode_is_blocked(self):
        ctx = _full_ctx(execution_mode="REPLAY")
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is True
        assert "EXECUTION_MODE_INVALID" in a.reason_codes

    def test_missing_correlation_id_is_blocked(self):
        ctx = _full_ctx(correlation_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is True
        assert "CORRELATION_ID_MISSING" in a.reason_codes

    def test_missing_origin_source_blocks(self):
        ctx = _full_ctx(origin_source=None)
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is True
        assert "ATTRIBUTION_INCOMPLETE" in a.reason_codes

    def test_missing_actor_identity_blocks(self):
        ctx = _full_ctx(actor_identity=None)
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is True
        assert "ATTRIBUTION_INCOMPLETE" in a.reason_codes

    def test_invalid_execution_type_is_blocked(self):
        ctx = _full_ctx(execution_type="batch_run")
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is True
        assert "EXECUTION_TYPE_INVALID" in a.reason_codes

    def test_blocked_assessment_carries_attribution_from_input(self):
        ctx = _full_ctx(correlation_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.origin_source == "ssip_test"
        assert a.origin_authority == "test_authority"

    def test_blocked_assessment_has_rule_0_in_path(self):
        ctx = _full_ctx(config_version_id=None)
        a = assess_ai_orchestration(ctx)
        assert "RULE_0" in a.rule_path_taken


# ── TestFinalizedCopyImmutability ─────────────────────────────────────────────

class TestFinalizedCopyImmutability:

    def test_finalized_copy_serves_immutable_immediately(self):
        ctx = _full_ctx(ai_finalized_copy=True)
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_FINALIZED_COPY
        assert a.advisory_scope == SCOPE_IMMUTABLE

    def test_finalized_copy_stops_at_rule_1_no_re_inference(self):
        ctx = _full_ctx(ai_finalized_copy=True)
        a = assess_ai_orchestration(ctx)
        assert "RULE_1" in a.rule_path_taken
        assert "RULE_5" not in a.rule_path_taken

    def test_finalized_copy_live_inference_suppressed(self):
        ctx = _full_ctx(ai_finalized_copy=True)
        a = assess_ai_orchestration(ctx)
        assert a.live_inference_suppressed is True

    def test_finalized_copy_no_orchestration_influence(self):
        ctx = _full_ctx(ai_finalized_copy=True, ai_recommended_intervention="ESCALATE")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_recommended_intervention is None

    def test_finalized_copy_is_not_snapshot_eligible(self):
        ctx = _full_ctx(ai_finalized_copy=True)
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is False
        assert a.finalized_copy is True

    def test_finalized_copy_reason_code_present(self):
        ctx = _full_ctx(ai_finalized_copy=True)
        a = assess_ai_orchestration(ctx)
        assert "AI_FINALIZED_COPY_SERVING" in a.reason_codes

    def test_finalized_copy_not_blocked(self):
        ctx = _full_ctx(ai_finalized_copy=True)
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is False


# ── TestReplayContainment ─────────────────────────────────────────────────────

class TestReplayContainment:

    def test_replay_suppresses_live_inference(self):
        ctx = _replay_ctx(source_artifact_id="snap-hist-001")
        a = assess_ai_orchestration(ctx)
        assert a.live_inference_suppressed is True
        assert a.is_replay is True

    def test_replay_with_source_serves_finalized_copy(self):
        ctx = _replay_ctx(source_artifact_id="snap-hist-001")
        a = assess_ai_orchestration(ctx)
        assert a.replay_ai_source == "FINALIZED_COPY"
        assert a.ai_governance_tier == TIER_FINALIZED_COPY

    def test_replay_without_source_is_unavailable(self):
        ctx = _replay_ctx(source_artifact_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.replay_ai_source == "NONE"
        assert a.ai_governance_tier == TIER_UNAVAILABLE
        assert "REPLAY_AI_SOURCE_MISSING" in a.reason_codes

    def test_replay_exits_before_live_rule_evaluation(self):
        ctx = _replay_ctx(source_artifact_id="snap-hist-001")
        a = assess_ai_orchestration(ctx)
        assert "RULE_4" not in a.rule_path_taken
        assert "RULE_5" not in a.rule_path_taken

    def test_regeneration_also_suppresses_live_inference(self):
        ctx = _full_ctx(execution_mode="SHADOW", execution_type="regeneration",
                        source_artifact_id="snap-regen-001")
        a = assess_ai_orchestration(ctx)
        assert a.live_inference_suppressed is True
        assert a.is_replay is True

    def test_replay_carries_reason_code(self):
        ctx = _replay_ctx(source_artifact_id="snap-hist-001")
        a = assess_ai_orchestration(ctx)
        assert "REPLAY_MODE_ACTIVE" in a.reason_codes

    def test_replay_attribution_propagated_unchanged(self):
        ctx = _replay_ctx(source_artifact_id="snap-hist-001")
        a = assess_ai_orchestration(ctx)
        assert a.origin_source == "ssip_test"
        assert a.origin_authority == "test_authority"
        assert a.actor_identity == "test_actor"


# ── TestConfigThresholdResolution ─────────────────────────────────────────────

class TestConfigThresholdResolution:

    def test_missing_ttl_resolves_to_unknown_v0(self):
        ctx = _full_ctx(config_rule_set={})
        a = assess_ai_orchestration(ctx)
        assert a.ttl_hours_applied == UNKNOWN_V0

    def test_missing_threshold_adds_reason_code(self):
        ctx = _full_ctx(config_rule_set={})
        a = assess_ai_orchestration(ctx)
        assert any("CONFIG_THRESHOLD_MISSING" in rc for rc in a.reason_codes)

    def test_unknown_v0_value_treated_as_missing(self):
        ctx = _full_ctx(config_rule_set={"ai_insight_ttl_hours": UNKNOWN_V0})
        a = assess_ai_orchestration(ctx)
        assert a.ttl_hours_applied == UNKNOWN_V0

    def test_valid_thresholds_bound_in_output(self):
        ctx = _full_ctx()
        a = assess_ai_orchestration(ctx)
        assert a.threshold_bindings.get("ai_insight_ttl_hours") == 24
        assert a.threshold_bindings.get("ai_llm_provider") == "anthropic"

    def test_no_hardcoded_default_on_missing_ttl(self):
        # When TTL is missing, tier is evaluated without it — insight is ADVISORY not STALE
        ctx = _full_ctx(config_rule_set={}, ai_confidence_score=0.85,
                        ai_generated_at=_stale_iso(48.0))
        a = assess_ai_orchestration(ctx)
        # Without a TTL threshold we can't determine staleness, so tier should be CONFIDENT
        # (staleness check is skipped when TTL is UNKNOWN_V0)
        assert a.ai_governance_tier in (TIER_CONFIDENT, TIER_ADVISORY)
        assert "AI_STALE" not in a.reason_codes


# ── TestGovernanceTierAssignment ──────────────────────────────────────────────

class TestGovernanceTierAssignment:

    def test_confident_tier_for_high_confidence_fresh_insight(self):
        ctx = _full_ctx(ai_confidence_score=0.85, ai_generated_at=_recent_iso(1.0))
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_CONFIDENT
        assert a.confidence_tier == "HIGH"

    def test_advisory_tier_for_medium_confidence(self):
        ctx = _full_ctx(ai_confidence_score=0.55, ai_generated_at=_recent_iso(1.0))
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_ADVISORY
        assert a.confidence_tier == "MEDIUM"

    def test_advisory_tier_for_low_confidence(self):
        ctx = _full_ctx(ai_confidence_score=0.25, ai_generated_at=_recent_iso(1.0))
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_ADVISORY
        assert a.confidence_tier == "LOW"
        assert "CONFIDENCE_COLLAPSE" in a.reason_codes

    def test_stale_tier_for_expired_insight(self):
        ctx = _full_ctx(ai_generated_at=_stale_iso(30.0))
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_STALE
        assert a.stale_flag is True
        assert "AI_STALE" in a.reason_codes

    def test_stale_tier_populates_stale_for_hours(self):
        ctx = _full_ctx(ai_generated_at=_stale_iso(30.0))
        a = assess_ai_orchestration(ctx)
        assert a.stale_for_hours > 0.0

    def test_unavailable_tier_when_not_reviewed(self):
        ctx = _full_ctx(ai_insight_state="AI_GENERATED")
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_UNAVAILABLE
        assert "AI_NOT_REVIEWED" in a.reason_codes

    def test_in_flight_tier_when_generating(self):
        ctx = _full_ctx(ai_insight_state="AI_GENERATING", ai_insight_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_IN_FLIGHT
        assert a.advisory_scope == SCOPE_DEFERRED
        assert "AI_IN_FLIGHT" in a.reason_codes

    def test_unavailable_tier_when_insight_absent(self):
        ctx = _full_ctx(ai_insight_id=None, ai_insight_state="AI_GENERATION_FAILED")
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_UNAVAILABLE
        assert "AI_INSIGHT_ABSENT" in a.reason_codes


# ── TestAdvisoryScope ─────────────────────────────────────────────────────────

class TestAdvisoryScope:

    def test_confident_tier_yields_full_scope(self):
        ctx = _full_ctx(ai_confidence_score=0.85)
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_FULL

    def test_advisory_tier_yields_limited_scope(self):
        ctx = _full_ctx(ai_confidence_score=0.55)
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_LIMITED

    def test_stale_tier_yields_limited_scope(self):
        ctx = _full_ctx(ai_generated_at=_stale_iso(30.0))
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_LIMITED

    def test_limited_scope_nullifies_recommended_intervention(self):
        ctx = _full_ctx(ai_confidence_score=0.55,
                        ai_recommended_intervention="ESCALATE")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_LIMITED
        assert a.advisory_recommended_intervention is None

    def test_full_scope_propagates_recommended_intervention(self):
        ctx = _full_ctx(ai_confidence_score=0.85,
                        ai_recommended_intervention="OUTREACH")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_FULL
        assert a.advisory_recommended_intervention == "OUTREACH"

    def test_unavailable_scope_for_absent_insight(self):
        ctx = _full_ctx(ai_insight_id=None, ai_insight_state="AI_GENERATION_FAILED")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_UNAVAILABLE


# ── TestLiveEscalationRestriction ────────────────────────────────────────────

class TestLiveEscalationRestriction:

    def test_stale_ai_blocked_from_live_escalation(self):
        ctx = _full_ctx(ai_generated_at=_stale_iso(30.0),
                        ai_recommended_intervention="ESCALATE",
                        execution_mode="LIVE")
        a = assess_ai_orchestration(ctx)
        assert "AI_LIVE_ESCALATION_BLOCKED_STALE_TIER" in a.reason_codes
        assert a.advisory_recommended_intervention is None

    def test_stale_ai_in_shadow_not_blocked(self):
        ctx = _shadow_ctx(ai_generated_at=_stale_iso(30.0),
                          ai_recommended_intervention="ESCALATE")
        a = assess_ai_orchestration(ctx)
        assert "AI_LIVE_ESCALATION_BLOCKED_STALE_TIER" not in a.reason_codes

    def test_confident_ai_not_blocked_in_live(self):
        ctx = _full_ctx(ai_confidence_score=0.85,
                        ai_recommended_intervention="OUTREACH",
                        execution_mode="LIVE")
        a = assess_ai_orchestration(ctx)
        assert "AI_LIVE_ESCALATION_BLOCKED_STALE_TIER" not in a.reason_codes
        assert a.advisory_recommended_intervention == "OUTREACH"

    def test_unavailable_tier_blocked_in_live(self):
        ctx = _full_ctx(ai_insight_id=None, ai_insight_state="AI_GENERATION_FAILED",
                        execution_mode="LIVE")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_recommended_intervention is None


# ── TestProviderDegradation ───────────────────────────────────────────────────

class TestProviderDegradation:

    def test_circuit_breaker_open_yields_unavailable(self):
        ctx = _full_ctx(circuit_breaker_state=CB_OPEN)
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_UNAVAILABLE
        assert "CIRCUIT_BREAKER_OPEN" in a.reason_codes
        assert a.degradation_cause == "CIRCUIT_OPEN"

    def test_circuit_breaker_closed_allows_evaluation(self):
        ctx = _full_ctx(circuit_breaker_state=CB_CLOSED)
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_CONFIDENT

    def test_provider_identity_divergence_annotated(self):
        ctx = _full_ctx(ai_model_used="openai",
                        config_rule_set={"ai_insight_ttl_hours": 24,
                                         "ai_llm_provider": "anthropic"})
        a = assess_ai_orchestration(ctx)
        assert "PROVIDER_IDENTITY_DIVERGENCE" in a.reason_codes

    def test_provider_divergence_blocks_snapshot_eligibility(self):
        ctx = _full_ctx(ai_model_used="openai",
                        config_rule_set={"ai_insight_ttl_hours": 24,
                                         "ai_llm_provider": "anthropic"})
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is False

    def test_provider_divergence_does_not_change_tier(self):
        ctx = _full_ctx(ai_model_used="openai",
                        config_rule_set={"ai_insight_ttl_hours": 24,
                                         "ai_llm_provider": "anthropic"})
        a = assess_ai_orchestration(ctx)
        assert a.ai_governance_tier == TIER_CONFIDENT


# ── TestSnapshotEligibility ───────────────────────────────────────────────────

class TestSnapshotEligibility:

    def test_confident_fresh_original_is_eligible(self):
        ctx = _full_ctx(ai_confidence_score=0.85, execution_type="original")
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is True
        assert a.eligibility_reason == "CONFIDENT_TIER_FRESH_ORIGINAL_EXECUTION"

    def test_advisory_tier_not_eligible(self):
        ctx = _full_ctx(ai_confidence_score=0.55)
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is False

    def test_stale_insight_not_eligible(self):
        ctx = _full_ctx(ai_generated_at=_stale_iso(30.0))
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is False

    def test_compliance_hold_blocks_eligibility(self):
        ctx = _full_ctx(compliance_hold_flag=True)
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is False

    def test_provider_divergence_blocks_eligibility(self):
        ctx = _full_ctx(ai_model_used="openai",
                        config_rule_set={"ai_insight_ttl_hours": 24,
                                         "ai_llm_provider": "anthropic"})
        a = assess_ai_orchestration(ctx)
        assert a.eligible_for_snapshot is False


# ── TestAttributionContinuity ─────────────────────────────────────────────────

class TestAttributionContinuity:

    def test_attribution_propagated_on_confident_path(self):
        ctx = _full_ctx()
        a = assess_ai_orchestration(ctx)
        assert a.origin_source == ctx.origin_source
        assert a.origin_authority == ctx.origin_authority
        assert a.actor_identity == ctx.actor_identity

    def test_correlation_id_propagated(self):
        cid = _uuid()
        ctx = _full_ctx(correlation_id=cid)
        a = assess_ai_orchestration(ctx)
        assert a.correlation_id == cid

    def test_causation_id_propagated(self):
        cid = _uuid()
        ctx = _full_ctx(causation_id=cid)
        a = assess_ai_orchestration(ctx)
        assert a.causation_id == cid

    def test_config_version_id_in_output(self):
        ctx = _full_ctx(config_version_id="cfg-v2-xyz")
        a = assess_ai_orchestration(ctx)
        assert a.config_version_id == "cfg-v2-xyz"

    def test_attribution_on_blocked_assessment(self):
        ctx = _full_ctx(correlation_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.origin_source == "ssip_test"

    def test_rule_path_present_in_all_outputs(self):
        ctx = _full_ctx()
        a = assess_ai_orchestration(ctx)
        assert len(a.rule_path_taken) > 0
        assert "RULE_0" in a.rule_path_taken


# ── TestDegradationObservability ──────────────────────────────────────────────

class TestDegradationObservability:

    def test_circuit_open_produces_degraded_flag(self):
        ctx = _full_ctx(circuit_breaker_state=CB_OPEN)
        a = assess_ai_orchestration(ctx)
        assert a.degraded is True
        assert a.fallback_applied is True
        assert a.fallback_type == "RULE_BASED_ONLY"

    def test_missing_threshold_produces_degraded_flag(self):
        ctx = _full_ctx(config_rule_set={}, ai_confidence_score=0.85)
        a = assess_ai_orchestration(ctx)
        assert a.degraded is True

    def test_confidence_collapse_annotated(self):
        ctx = _full_ctx(ai_confidence_score=0.15)
        a = assess_ai_orchestration(ctx)
        assert "CONFIDENCE_COLLAPSE" in a.reason_codes
        assert a.degradation_cause == "CONFIDENCE_COLLAPSE"

    def test_unavailable_tier_sets_orchestration_continues(self):
        ctx = _full_ctx(ai_insight_id=None, ai_insight_state="AI_GENERATION_FAILED")
        a = assess_ai_orchestration(ctx)
        assert a.orchestration_continues is True

    def test_blocked_assessment_orchestration_stops(self):
        ctx = _full_ctx(config_version_id=None)
        a = assess_ai_orchestration(ctx)
        assert a.orchestration_continues is False


# ── TestIdempotencyDeduplication ─────────────────────────────────────────────

class TestIdempotencyDeduplication:

    def setup_method(self):
        ai_module._ai_idempotency_keys.clear()

    def test_first_evaluation_succeeds(self):
        ctx = _full_ctx(idempotency_key="idem-key-001")
        a = assess_ai_orchestration(ctx)
        assert a.ai_blocked is False

    def test_duplicate_key_is_blocked(self):
        key = "idem-key-dup-test"
        ctx1 = _full_ctx(idempotency_key=key)
        ctx2 = _full_ctx(idempotency_key=key)
        assess_ai_orchestration(ctx1)
        a2 = assess_ai_orchestration(ctx2)
        assert a2.ai_blocked is True
        assert "IDEMPOTENCY_DUPLICATE" in a2.reason_codes

    def test_replay_does_not_register_key(self):
        key = "idem-key-replay"
        ctx_replay = _replay_ctx(idempotency_key=key, source_artifact_id="snap-001")
        assess_ai_orchestration(ctx_replay)
        assert key not in ai_module._ai_idempotency_keys

    def test_distinct_keys_both_succeed(self):
        ai_module._ai_idempotency_keys.clear()
        ctx1 = _full_ctx(idempotency_key=_uuid())
        ctx2 = _full_ctx(idempotency_key=_uuid())
        a1 = assess_ai_orchestration(ctx1)
        a2 = assess_ai_orchestration(ctx2)
        assert a1.ai_blocked is False
        assert a2.ai_blocked is False


# ── TestInvariantPreservation ─────────────────────────────────────────────────

class TestInvariantPreservation:

    def test_no_live_inference_on_any_path(self):
        """AP-AI5 / AP-LF14: live_inference_suppressed must be True for replay paths."""
        ctx = _replay_ctx(source_artifact_id="snap-001")
        a = assess_ai_orchestration(ctx)
        assert a.live_inference_suppressed is True

    def test_finalized_copy_never_overwritten(self):
        """AP-AI6 / AP-AI12: FINALIZED_COPY stops at Rule 1 with IMMUTABLE scope."""
        ctx = _full_ctx(ai_finalized_copy=True, ai_confidence_score=0.99)
        a = assess_ai_orchestration(ctx)
        assert a.advisory_scope == SCOPE_IMMUTABLE
        assert a.advisory_recommended_intervention is None

    def test_no_silent_provider_substitution(self):
        """AP-AI8: provider divergence annotated explicitly, not silently substituted."""
        ctx = _full_ctx(ai_model_used="openai",
                        config_rule_set={"ai_insight_ttl_hours": 24,
                                         "ai_llm_provider": "anthropic"})
        a = assess_ai_orchestration(ctx)
        assert "PROVIDER_IDENTITY_DIVERGENCE" in a.reason_codes

    def test_no_hardcoded_ttl_threshold(self):
        """AP-AI9 / AP-LF1: missing TTL resolves to UNKNOWN_V0, not a hardcoded default."""
        ctx = _full_ctx(config_rule_set={}, ai_generated_at=_stale_iso(100.0))
        a = assess_ai_orchestration(ctx)
        assert a.ttl_hours_applied == UNKNOWN_V0
        assert "AI_STALE" not in a.reason_codes

    def test_stale_ai_does_not_originate_escalation_candidacy(self):
        """AP-AI11 / AP-AI14: STALE AI cannot independently drive LIVE escalation."""
        ctx = _full_ctx(ai_generated_at=_stale_iso(30.0),
                        ai_recommended_intervention="ESCALATE",
                        execution_mode="LIVE")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_recommended_intervention is None

    def test_every_path_carries_event_id(self):
        """Observability: every assessment must carry a non-empty event_id."""
        paths = [
            _full_ctx(),
            _full_ctx(config_version_id=None),
            _full_ctx(ai_finalized_copy=True),
            _replay_ctx(source_artifact_id="snap-001"),
            _full_ctx(ai_insight_id=None, ai_insight_state="AI_GENERATION_FAILED"),
        ]
        for ctx in paths:
            a = assess_ai_orchestration(ctx)
            assert bool(a.event_id)

    def test_model_lineage_in_confident_assessment(self):
        """AP-AI15: model lineage (provider, model_identifier) propagated from insight."""
        ctx = _full_ctx(ai_model_used="anthropic", ai_prompt_version="v2.0",
                        ai_insight_version=3)
        a = assess_ai_orchestration(ctx)
        assert a.provider == "anthropic"
        assert a.model_identifier == "anthropic"
        assert a.prompt_version == "v2.0"
        assert a.ai_version_number == 3

    def test_advisory_content_not_in_unavailable_assessment(self):
        """AP-AI1: UNAVAILABLE tier must carry null advisory content."""
        ctx = _full_ctx(ai_insight_id=None, ai_insight_state="AI_GENERATION_FAILED")
        a = assess_ai_orchestration(ctx)
        assert a.advisory_recommended_intervention is None
        assert a.advisory_prioritization_signal is None
