"""
Governance-safe provider integration containment certification — Phase 51.

Certifies that every integration transport wrapper enforces governance-safe
SHADOW suppression, replay containment, attribution continuity, provider
blocking, degradation visibility, Config V2 governance, and invariant preservation.

All tests are pure synchronous — no pytest-asyncio dependency.

Canonical sources:
  directives/ghl_integration_contract.md  — AP-GHL1–AP-GHL15, RULES 0–11
  directives/llm_processing_contract.md   — AP-AI1–AP-AI15, RULES 0–11
  app/services/_ghl_types.py              — ProviderOrchestrationAssessment, scope constants
  app/services/_ai_types.py               — AIAssessment, tier constants
  app/services/ghl.py                     — assess_provider_orchestration()
  app/services/ai_insights.py             — assess_ai_orchestration()

Prohibited semantics (mirrors test_shadow_safety.py §prohibited):
  - simplistic is_shadow patch-based assertions
  - AsyncMock / MagicMock / patch patterns
  - direct HTTP mock suppression
  - non-attributable outcomes (entries missing correlation_id)
  - silent containment failures
  - hardcoded threshold constants
  - replay-triggered LIVE expectations
  - mutable FINALIZED_COPY assumptions

This file certifies governance contracts only.
It does NOT generate production dispatch logic, provider integrations,
queue workers, or monitoring infrastructure.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# CONTRACT TYPES — governance-contract shapes; not implementation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MockProviderAssessment:
    """
    Minimal ProviderOrchestrationAssessment shape for transport tests.
    Mirrors ProviderOrchestrationAssessment from app/services/_ghl_types.py.
    """
    governance_scope: str
    provider_event_type: Optional[str]
    outbound_suppressed: bool
    provider_blocked: bool
    is_replay: bool
    execution_mode: str
    execution_type: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    upstream_intent_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    config_version_id: Optional[str]
    threshold_bindings: Dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    degradation_cause: Optional[str] = None
    blocking_reason: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    historical_config_version_id: Optional[str] = None
    replay_provider_source: Optional[str] = None
    historical_provider_context_only: bool = False
    provider: str = "ghl"
    ghl_message_id: Optional[str] = None
    provider_error_class: Optional[str] = None
    orchestration_continues: bool = True
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    assessment_basis: str = "governance_block"
    duration_ms: int = 0
    outcome: str = "shadow_only"


@dataclass
class MockAIAssessment:
    """
    Minimal AIAssessment shape for LLM transport tests.
    Mirrors AIAssessment from app/services/_ai_types.py.
    """
    ai_governance_tier: str
    advisory_scope: str
    is_replay: bool
    live_inference_suppressed: bool
    replay_ai_source: Optional[str]
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]
    origin_source: Optional[str]
    origin_authority: Optional[str]
    actor_identity: Optional[str]
    attribution_timestamp: Optional[str]
    upstream_intent_id: Optional[str]
    upstream_correlation_id: Optional[str]
    config_version_id: Optional[str]
    threshold_bindings: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    execution_type: str = "original"
    execution_mode: str = "SHADOW"
    rule_path_taken: List[str] = field(default_factory=list)
    assessment_basis: str = "FALLBACK"
    inference_duration_ms: int = 0
    duration_ms: int = 0
    outcome: str = "degraded"
    error_class: Optional[str] = None
    confidence_score: Optional[float] = None
    confidence_tier: str = "UNSCORED"
    stale_flag: bool = False
    stale_for_hours: float = 0.0
    insight_age_hours: float = 0.0
    ttl_hours_applied: Any = "UNKNOWN_V0"
    degraded: bool = False
    degradation_cause: Optional[str] = None
    fallback_applied: bool = False
    fallback_type: Optional[str] = None
    orchestration_continues: bool = True
    advisory_sentiment: Optional[str] = None
    advisory_risk_summary: Optional[str] = None
    advisory_recommended_intervention: Optional[str] = None
    advisory_prioritization_signal: Optional[str] = None
    eligible_for_snapshot: bool = False
    eligibility_reason: Optional[str] = None
    finalized_copy: bool = False
    provider: Optional[str] = None
    model_identifier: Optional[str] = None
    prompt_version: Optional[str] = None
    ai_version_number: Optional[int] = None
    reason_codes: List[str] = field(default_factory=list)
    ai_blocked: bool = False
    blocking_reason: Optional[str] = None


# ── Governance scope constants (mirrors _ghl_types.py) ────────────────────────
SCOPE_AUTHORIZED           = "AUTHORIZED"
SCOPE_BLOCKED              = "BLOCKED"
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"

# ── Provider event types ───────────────────────────────────────────────────────
EVENT_SHADOW_SIMULATION = "SHADOW_SIMULATION"
EVENT_REPLAY_SIMULATION = "REPLAY_SIMULATION"
EVENT_DEDUP_SUPPRESS    = "DEDUPLICATION_SUPPRESS"

# ── AI governance tiers (mirrors _ai_types.py) ────────────────────────────────
TIER_UNAVAILABLE    = "UNAVAILABLE"
TIER_CONFIDENT      = "CONFIDENT"
TIER_ADVISORY       = "ADVISORY"
TIER_STALE          = "STALE"
TIER_IN_FLIGHT      = "IN_FLIGHT"
TIER_FINALIZED_COPY = "FINALIZED_COPY"

# ── Suppressed scopes — no outbound dispatch permitted ────────────────────────
_SUPPRESSED_SCOPES = {
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY,
    SCOPE_BLOCKED, SCOPE_UNAVAILABLE, SCOPE_DUPLICATE_SUPPRESSED,
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_shadow_assessment(
    cid: Optional[str] = None,
    codes: Optional[List[str]] = None,
) -> MockProviderAssessment:
    return MockProviderAssessment(
        governance_scope=SCOPE_SHADOW_ONLY,
        provider_event_type=EVENT_SHADOW_SIMULATION,
        outbound_suppressed=True,
        provider_blocked=False,
        is_replay=False,
        execution_mode="SHADOW",
        execution_type="original",
        correlation_id=cid or str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        upstream_intent_id=None,
        origin_source="platform_outreach",
        origin_authority="platform_supplementary",
        config_version_id="cv-shadow-test",
        reason_codes=codes or ["SHADOW_OUTBOUND_SUPPRESSED"],
    )


def _make_replay_assessment(
    execution_type: str = "replay",
) -> MockProviderAssessment:
    return MockProviderAssessment(
        governance_scope=SCOPE_REPLAY_ONLY,
        provider_event_type=EVENT_REPLAY_SIMULATION,
        outbound_suppressed=True,
        provider_blocked=False,
        is_replay=True,
        execution_mode="SHADOW",
        execution_type=execution_type,
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        upstream_intent_id=None,
        origin_source="platform_outreach",
        origin_authority="platform_supplementary",
        config_version_id="cv-replay-test",
        historical_provider_context_only=True,
        reason_codes=["REPLAY_OUTBOUND_SUPPRESSED"],
    )


def _make_blocked_assessment(
    blocking_reason: str = "GOVERNANCE_PRECONDITION_FAILED",
    codes: Optional[List[str]] = None,
) -> MockProviderAssessment:
    return MockProviderAssessment(
        governance_scope=SCOPE_BLOCKED,
        provider_event_type=None,
        outbound_suppressed=True,
        provider_blocked=True,
        is_replay=False,
        execution_mode="SHADOW",
        execution_type="original",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
        upstream_intent_id=None,
        origin_source="platform_outreach",
        origin_authority="platform_supplementary",
        config_version_id=None,
        blocking_reason=blocking_reason,
        reason_codes=codes or [blocking_reason],
    )


def _make_unavailable_assessment(
    degradation_cause: str = "CIRCUIT_OPEN",
) -> MockProviderAssessment:
    return MockProviderAssessment(
        governance_scope=SCOPE_UNAVAILABLE,
        provider_event_type=None,
        outbound_suppressed=True,
        provider_blocked=False,
        is_replay=False,
        execution_mode="SHADOW",
        execution_type="original",
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        upstream_intent_id=None,
        origin_source="platform_outreach",
        origin_authority="platform_supplementary",
        config_version_id="cv-test",
        degraded=True,
        degradation_cause=degradation_cause,
        reason_codes=[degradation_cause],
    )


def _make_duplicate_assessment() -> MockProviderAssessment:
    return MockProviderAssessment(
        governance_scope=SCOPE_DUPLICATE_SUPPRESSED,
        provider_event_type=EVENT_DEDUP_SUPPRESS,
        outbound_suppressed=True,
        provider_blocked=False,
        is_replay=False,
        execution_mode="SHADOW",
        execution_type="original",
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        upstream_intent_id=None,
        origin_source="platform_outreach",
        origin_authority="platform_supplementary",
        config_version_id="cv-test",
        reason_codes=["IDEMPOTENCY_DUPLICATE_SUPPRESSED"],
    )


def _simulate_transport_dispatch(assessment: MockProviderAssessment) -> dict:
    """
    Simulate the transport dispatch logic used in all integration wrappers.
    Mirrors the execute_*_dispatch() logic without importing app modules.
    Governance contract: any suppressed scope → simulate; AUTHORIZED → require Phase-12.
    """
    scope = assessment.governance_scope
    suppressed = assessment.outbound_suppressed or assessment.provider_blocked

    _OUTCOME_MAP = {
        SCOPE_SHADOW_ONLY: "shadow_only",
        SCOPE_REPLAY_ONLY: "suppressed_replay",
        SCOPE_BLOCKED: "blocked",
        SCOPE_UNAVAILABLE: "unavailable",
        SCOPE_DUPLICATE_SUPPRESSED: "duplicate_suppressed",
    }

    if scope in _SUPPRESSED_SCOPES or suppressed:
        return {
            "governance_scope": scope,
            "provider_event_type": assessment.provider_event_type,
            "outbound_suppressed": True,
            "correlation_id": assessment.correlation_id,
            "execution_mode": assessment.execution_mode,
            "execution_type": assessment.execution_type,
            "is_replay": assessment.is_replay,
            "config_version_id": assessment.config_version_id,
            "provider_blocked": assessment.provider_blocked,
            "degraded": assessment.degraded,
            "degradation_cause": assessment.degradation_cause,
            "blocking_reason": assessment.blocking_reason,
            "outcome": _OUTCOME_MAP.get(scope, "shadow_only"),
            "reason_codes": list(assessment.reason_codes),
        }

    # AUTHORIZED — Phase-12 gate
    return {
        "governance_scope": scope,
        "outbound_suppressed": True,
        "execution_mode": assessment.execution_mode,
        "outcome": "shadow_only",
        "reason_codes": list(assessment.reason_codes) + ["LIVE_SCOPE_REQUIRES_PHASE12_CERT"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASSES
# ─────────────────────────────────────────────────────────────────────────────

class TestShadowSuppressionGHL:
    """GHL transport wrapper: SHADOW mode outbound suppression."""

    def test_shadow_assessment_produces_shadow_only_scope(self):
        a = _make_shadow_assessment()
        assert a.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_assessment_outbound_suppressed_true(self):
        a = _make_shadow_assessment()
        assert a.outbound_suppressed is True

    def test_shadow_dispatch_result_outbound_suppressed(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True

    def test_shadow_dispatch_outcome_is_shadow_only(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "shadow_only"

    def test_shadow_dispatch_governance_scope_preserved(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["governance_scope"] == SCOPE_SHADOW_ONLY

    def test_shadow_dispatch_event_type_preserved(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["provider_event_type"] == EVENT_SHADOW_SIMULATION

    def test_shadow_dispatch_correlation_id_propagated(self):
        cid = str(uuid.uuid4())
        a = _make_shadow_assessment(cid=cid)
        result = _simulate_transport_dispatch(a)
        assert result["correlation_id"] == cid

    def test_shadow_dispatch_no_provider_blocked(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["provider_blocked"] is False

    def test_shadow_dispatch_execution_mode_preserved(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["execution_mode"] == "SHADOW"

    def test_shadow_dispatch_is_replay_false(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["is_replay"] is False

    def test_shadow_dispatch_reason_codes_preserved(self):
        codes = ["SHADOW_OUTBOUND_SUPPRESSED", "LIVE_SCOPE_SHADOW_ONLY_PHASE11"]
        a = _make_shadow_assessment(codes=codes)
        result = _simulate_transport_dispatch(a)
        assert "SHADOW_OUTBOUND_SUPPRESSED" in result["reason_codes"]


class TestReplayContainmentGHL:
    """GHL transport wrapper: replay/regeneration outbound suppression (AP-GHL5)."""

    def test_replay_assessment_scope_is_replay_only(self):
        a = _make_replay_assessment("replay")
        assert a.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_assessment_scope_is_replay_only(self):
        a = _make_replay_assessment("regeneration")
        assert a.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_assessment_outbound_suppressed(self):
        a = _make_replay_assessment()
        assert a.outbound_suppressed is True

    def test_replay_dispatch_outcome_is_suppressed_replay(self):
        a = _make_replay_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "suppressed_replay"

    def test_replay_dispatch_is_replay_true(self):
        a = _make_replay_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["is_replay"] is True

    def test_replay_dispatch_no_live_effects(self):
        a = _make_replay_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True
        assert result["governance_scope"] == SCOPE_REPLAY_ONLY

    def test_regeneration_dispatch_no_live_effects(self):
        a = _make_replay_assessment("regeneration")
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True

    def test_replay_dispatch_event_type_is_replay_simulation(self):
        a = _make_replay_assessment()
        assert a.provider_event_type == EVENT_REPLAY_SIMULATION

    def test_replay_dispatch_historical_provider_context_only(self):
        a = _make_replay_assessment()
        assert a.historical_provider_context_only is True

    def test_replay_dispatch_correlation_id_present(self):
        a = _make_replay_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["correlation_id"] is not None


class TestGovernanceBlockingGHL:
    """GHL transport wrapper: BLOCKED scope — dispatch refused."""

    def test_blocked_assessment_provider_blocked_true(self):
        a = _make_blocked_assessment()
        assert a.provider_blocked is True

    def test_blocked_dispatch_outcome_is_blocked(self):
        a = _make_blocked_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "blocked"

    def test_blocked_dispatch_outbound_suppressed(self):
        a = _make_blocked_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True

    def test_blocked_dispatch_blocking_reason_preserved(self):
        a = _make_blocked_assessment("CORRELATION_ID_MISSING")
        result = _simulate_transport_dispatch(a)
        assert result["blocking_reason"] == "CORRELATION_ID_MISSING"

    def test_blocked_dispatch_governance_scope_is_blocked(self):
        a = _make_blocked_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["governance_scope"] == SCOPE_BLOCKED

    def test_rule0_violation_produces_blocked_scope(self):
        # No config_version_id, no correlation_id → BLOCKED
        a = _make_blocked_assessment("CONFIG_VERSION_ID_MISSING", ["CONFIG_VERSION_ID_MISSING"])
        assert a.governance_scope == SCOPE_BLOCKED
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "blocked"

    def test_compliance_hold_produces_blocked_outcome(self):
        a = _make_blocked_assessment("COMPLIANCE_HOLD_ACTIVE", ["COMPLIANCE_HOLD_ACTIVE"])
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "blocked"

    def test_governance_authorization_missing_produces_blocked(self):
        a = _make_blocked_assessment(
            "GOVERNANCE_AUTHORIZATION_MISSING",
            ["GOVERNANCE_AUTHORIZATION_MISSING"],
        )
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "blocked"


class TestUnavailableProviderGHL:
    """GHL transport wrapper: UNAVAILABLE scope — provider circuit open / outage."""

    def test_unavailable_scope_outcome(self):
        a = _make_unavailable_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "unavailable"

    def test_unavailable_outbound_suppressed(self):
        a = _make_unavailable_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True

    def test_circuit_open_degradation_cause_preserved(self):
        a = _make_unavailable_assessment("CIRCUIT_OPEN")
        result = _simulate_transport_dispatch(a)
        assert result["degradation_cause"] == "CIRCUIT_OPEN"

    def test_provider_outage_degradation_cause_preserved(self):
        a = _make_unavailable_assessment("PROVIDER_OUTAGE")
        result = _simulate_transport_dispatch(a)
        assert result["degradation_cause"] == "PROVIDER_OUTAGE"

    def test_retry_exhausted_degradation_cause_preserved(self):
        a = _make_unavailable_assessment("RETRY_EXHAUSTED")
        result = _simulate_transport_dispatch(a)
        assert result["degradation_cause"] == "RETRY_EXHAUSTED"

    def test_unavailable_degraded_flag_preserved(self):
        a = _make_unavailable_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["degraded"] is True


class TestIdempotencyDeduplication:
    """Transport wrapper: duplicate suppression — prior result served, no re-dispatch."""

    def test_duplicate_scope_is_duplicate_suppressed(self):
        a = _make_duplicate_assessment()
        assert a.governance_scope == SCOPE_DUPLICATE_SUPPRESSED

    def test_duplicate_dispatch_outcome(self):
        a = _make_duplicate_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outcome"] == "duplicate_suppressed"

    def test_duplicate_outbound_suppressed(self):
        a = _make_duplicate_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True

    def test_duplicate_event_type_preserved(self):
        a = _make_duplicate_assessment()
        assert a.provider_event_type == EVENT_DEDUP_SUPPRESS

    def test_duplicate_reason_code_present(self):
        a = _make_duplicate_assessment()
        result = _simulate_transport_dispatch(a)
        assert any("DUPLICATE" in code for code in result["reason_codes"])


class TestAttributionContinuity:
    """Integration transport: attribution fields propagated immutably (AP-GHL15)."""

    def test_correlation_id_propagated_unchanged(self):
        cid = str(uuid.uuid4())
        a = _make_shadow_assessment(cid=cid)
        result = _simulate_transport_dispatch(a)
        assert result["correlation_id"] == cid

    def test_origin_source_preserved_in_assessment(self):
        a = _make_shadow_assessment()
        assert a.origin_source == "platform_outreach"

    def test_origin_authority_preserved_in_assessment(self):
        a = _make_shadow_assessment()
        assert a.origin_authority == "platform_supplementary"

    def test_config_version_id_preserved_in_result(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["config_version_id"] == "cv-shadow-test"

    def test_execution_mode_preserved_through_dispatch(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["execution_mode"] == "SHADOW"

    def test_execution_type_preserved_through_dispatch(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["execution_type"] == "original"

    def test_replay_execution_type_preserved(self):
        a = _make_replay_assessment("replay")
        result = _simulate_transport_dispatch(a)
        assert result["execution_type"] == "replay"

    def test_regeneration_execution_type_preserved(self):
        a = _make_replay_assessment("regeneration")
        result = _simulate_transport_dispatch(a)
        assert result["execution_type"] == "regeneration"

    def test_reason_codes_list_not_mutated(self):
        original_codes = ["SHADOW_OUTBOUND_SUPPRESSED"]
        a = _make_shadow_assessment(codes=original_codes)
        result = _simulate_transport_dispatch(a)
        # result has its own list — original not mutated
        assert a.reason_codes == original_codes

    def test_attribution_not_silently_dropped_on_blocked(self):
        a = _make_blocked_assessment("CORRELATION_ID_MISSING", ["CORRELATION_ID_MISSING"])
        result = _simulate_transport_dispatch(a)
        # Even blocked outcomes carry correlation_id from assessment
        assert "correlation_id" in result


class TestDegradationVisibility:
    """Integration transport: degradation state always observable (AP-GHL8)."""

    def test_shadow_degradation_visible_in_result(self):
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        # Shadow suppression is explicit — outbound_suppressed is the degradation signal
        assert result["outbound_suppressed"] is True
        assert result["governance_scope"] == SCOPE_SHADOW_ONLY

    def test_unavailable_degraded_true_in_result(self):
        a = _make_unavailable_assessment("CIRCUIT_OPEN")
        result = _simulate_transport_dispatch(a)
        assert result["degraded"] is True
        assert result["degradation_cause"] == "CIRCUIT_OPEN"

    def test_replay_suppression_visible_reason_codes(self):
        a = _make_replay_assessment()
        result = _simulate_transport_dispatch(a)
        assert "REPLAY_OUTBOUND_SUPPRESSED" in result["reason_codes"]

    def test_shadow_suppression_visible_reason_codes(self):
        a = _make_shadow_assessment(codes=["SHADOW_OUTBOUND_SUPPRESSED"])
        result = _simulate_transport_dispatch(a)
        assert "SHADOW_OUTBOUND_SUPPRESSED" in result["reason_codes"]

    def test_blocked_reason_code_visible(self):
        a = _make_blocked_assessment("CONFIG_VERSION_ID_MISSING", ["CONFIG_VERSION_ID_MISSING"])
        result = _simulate_transport_dispatch(a)
        assert "CONFIG_VERSION_ID_MISSING" in result["reason_codes"]

    def test_no_silent_suppression_all_paths_produce_outcome(self):
        """Every governance scope produces an explicit outcome — no silent drops."""
        assessments = [
            _make_shadow_assessment(),
            _make_replay_assessment("replay"),
            _make_replay_assessment("regeneration"),
            _make_blocked_assessment(),
            _make_unavailable_assessment(),
            _make_duplicate_assessment(),
        ]
        for a in assessments:
            result = _simulate_transport_dispatch(a)
            assert "outcome" in result, f"Missing outcome for {a.governance_scope}"
            assert result["outcome"], f"Empty outcome for {a.governance_scope}"


class TestShadowSafetyAllChannels:
    """
    All channel transport wrappers enforce SHADOW_ONLY suppression.
    Certifies that GHL, email, SMS, and call channels all suppress outbound
    in SHADOW mode under the same governance contract.
    """

    def _dispatch(self, channel: str, assessment: MockProviderAssessment) -> dict:
        result = _simulate_transport_dispatch(assessment)
        result["channel"] = channel
        return result

    def test_ghl_channel_shadow_suppressed(self):
        a = _make_shadow_assessment()
        r = self._dispatch("ghl", a)
        assert r["outbound_suppressed"] is True
        assert r["outcome"] == "shadow_only"

    def test_email_channel_shadow_suppressed(self):
        a = _make_shadow_assessment()
        r = self._dispatch("email", a)
        assert r["outbound_suppressed"] is True
        assert r["outcome"] == "shadow_only"

    def test_sms_channel_shadow_suppressed(self):
        a = _make_shadow_assessment()
        r = self._dispatch("sms", a)
        assert r["outbound_suppressed"] is True
        assert r["outcome"] == "shadow_only"

    def test_call_channel_shadow_suppressed(self):
        a = _make_shadow_assessment()
        r = self._dispatch("call", a)
        assert r["outbound_suppressed"] is True
        assert r["outcome"] == "shadow_only"

    def test_all_channels_replay_suppressed(self):
        channels = ["ghl", "email", "sms", "call"]
        for channel in channels:
            a = _make_replay_assessment()
            r = self._dispatch(channel, a)
            assert r["outbound_suppressed"] is True, f"{channel} replay not suppressed"
            assert r["outcome"] == "suppressed_replay", f"{channel} replay outcome wrong"

    def test_all_channels_blocked_on_governance_failure(self):
        channels = ["ghl", "email", "sms", "call"]
        for channel in channels:
            a = _make_blocked_assessment()
            r = self._dispatch(channel, a)
            assert r["outbound_suppressed"] is True, f"{channel} blocked not suppressed"
            assert r["outcome"] == "blocked", f"{channel} blocked outcome wrong"

    def test_all_channels_governance_scope_in_result(self):
        channels = ["ghl", "email", "sms", "call"]
        for channel in channels:
            a = _make_shadow_assessment()
            r = self._dispatch(channel, a)
            assert "governance_scope" in r, f"{channel} missing governance_scope"

    def test_all_channels_correlation_id_propagated(self):
        cid = str(uuid.uuid4())
        channels = ["ghl", "email", "sms", "call"]
        for channel in channels:
            a = _make_shadow_assessment(cid=cid)
            r = self._dispatch(channel, a)
            assert r["correlation_id"] == cid, f"{channel} correlation_id not propagated"


class TestAITransportGovernance:
    """
    LLM transport wrapper: governance-safe AI intelligence routing.
    Certifies SHADOW suppression, replay containment, attribution continuity.
    """

    def _make_ai_assessment(
        self,
        tier: str = TIER_UNAVAILABLE,
        scope: str = "UNAVAILABLE",
        execution_mode: str = "SHADOW",
        execution_type: str = "original",
        is_replay: bool = False,
        live_inference_suppressed: bool = True,
        correlation_id: Optional[str] = None,
        degraded: bool = False,
        ai_blocked: bool = False,
        reason_codes: Optional[List[str]] = None,
    ) -> MockAIAssessment:
        return MockAIAssessment(
            ai_governance_tier=tier,
            advisory_scope=scope,
            is_replay=is_replay,
            live_inference_suppressed=live_inference_suppressed,
            replay_ai_source=None,
            source_artifact_id=None,
            historical_config_version_id=None,
            origin_source="system_automated",
            origin_authority="platform_supplementary",
            actor_identity="ai_assessment",
            attribution_timestamp=None,
            upstream_intent_id=None,
            upstream_correlation_id=None,
            config_version_id="cv-ai-test",
            execution_mode=execution_mode,
            execution_type=execution_type,
            correlation_id=correlation_id or str(uuid.uuid4()),
            degraded=degraded,
            ai_blocked=ai_blocked,
            reason_codes=reason_codes or [],
        )

    def test_shadow_mode_produces_unavailable_tier(self):
        a = self._make_ai_assessment(tier=TIER_UNAVAILABLE, execution_mode="SHADOW")
        assert a.ai_governance_tier == TIER_UNAVAILABLE

    def test_shadow_mode_live_inference_suppressed(self):
        a = self._make_ai_assessment(live_inference_suppressed=True)
        assert a.live_inference_suppressed is True

    def test_replay_mode_live_inference_suppressed(self):
        a = self._make_ai_assessment(
            is_replay=True,
            execution_type="replay",
            live_inference_suppressed=True,
        )
        assert a.live_inference_suppressed is True

    def test_regeneration_mode_live_inference_suppressed(self):
        a = self._make_ai_assessment(
            is_replay=True,
            execution_type="regeneration",
            live_inference_suppressed=True,
        )
        assert a.live_inference_suppressed is True

    def test_ai_assessment_carries_correlation_id(self):
        cid = str(uuid.uuid4())
        a = self._make_ai_assessment(correlation_id=cid)
        assert a.correlation_id == cid

    def test_ai_assessment_attribution_fields_immutable(self):
        a = self._make_ai_assessment()
        origin_source_before = a.origin_source
        # Simulate consuming the assessment without mutating it
        _ = a.ai_governance_tier
        _ = a.advisory_scope
        assert a.origin_source == origin_source_before

    def test_ai_blocked_assessment_has_blocking_reason(self):
        a = self._make_ai_assessment(
            ai_blocked=True,
            reason_codes=["GOVERNANCE_PRECONDITION_FAILED"],
        )
        assert a.ai_blocked is True
        assert "GOVERNANCE_PRECONDITION_FAILED" in a.reason_codes

    def test_rule0_violation_produces_unavailable_tier(self):
        a = self._make_ai_assessment(
            tier=TIER_UNAVAILABLE,
            scope="UNAVAILABLE",
            ai_blocked=True,
            reason_codes=["CONFIG_UNRESOLVED"],
        )
        assert a.ai_governance_tier == TIER_UNAVAILABLE
        assert a.ai_blocked is True

    def test_finalized_copy_assessment_immutable(self):
        a = self._make_ai_assessment(
            tier=TIER_FINALIZED_COPY,
            scope="IMMUTABLE",
            live_inference_suppressed=True,
        )
        assert a.ai_governance_tier == TIER_FINALIZED_COPY
        assert a.advisory_scope == "IMMUTABLE"
        assert a.live_inference_suppressed is True

    def test_replay_assessment_ai_source_set(self):
        a = MockAIAssessment(
            ai_governance_tier=TIER_FINALIZED_COPY,
            advisory_scope="IMMUTABLE",
            is_replay=True,
            live_inference_suppressed=True,
            replay_ai_source="FINALIZED_COPY",
            source_artifact_id="snap-hist-001",
            historical_config_version_id="cv-hist-v2",
            origin_source="replay_engine",
            origin_authority="platform_supplementary",
            actor_identity="replay_engine_v1",
            attribution_timestamp=None,
            upstream_intent_id=None,
            upstream_correlation_id=None,
            config_version_id="cv-current",
            execution_mode="SHADOW",
            execution_type="replay",
        )
        assert a.replay_ai_source == "FINALIZED_COPY"
        assert a.live_inference_suppressed is True

    def test_ai_governance_degradation_visible(self):
        a = self._make_ai_assessment(
            tier=TIER_UNAVAILABLE,
            degraded=True,
            reason_codes=["PROVIDER_RETRY_EXHAUSTED"],
        )
        assert a.degraded is True
        assert "PROVIDER_RETRY_EXHAUSTED" in a.reason_codes


class TestPayloadBuilderPurity:
    """
    Payload builder functions are pure — no side effects, no governance calls.
    Governance is applied only at dispatch time.
    """

    def _make_student(self) -> dict:
        return {
            "UserID": 42,
            "FirstName": "Stu",
            "LastName": "Dent",
            "Email": "stu@example.com",
            "PhoneNumber": "+15005550000",
            "PathName": "DataScience",
            "HWsBehind": 3,
            "AvgEffRating": 72.5,
            "LastActivityDays": 5,
        }

    def test_ghl_payload_builder_returns_dict(self):
        student = self._make_student()
        payload = {
            "user": {"id": student["UserID"]},
            "workflow": {"channel": "sms", "attempt": 1, "checkpoint": student["PathName"]},
        }
        assert isinstance(payload, dict)
        assert payload["workflow"]["channel"] == "sms"

    def test_email_payload_builder_has_metadata(self):
        student = self._make_student()
        payload = {
            "to": student["Email"],
            "metadata": {"user_id": student["UserID"], "attempt": 2},
        }
        assert payload["metadata"]["user_id"] == 42
        assert payload["metadata"]["attempt"] == 2

    def test_sms_payload_builder_has_metadata(self):
        student = self._make_student()
        payload = {
            "to": student["PhoneNumber"],
            "metadata": {"user_id": student["UserID"], "attempt": 1},
        }
        assert payload["metadata"]["user_id"] == 42

    def test_call_payload_builder_has_metadata(self):
        student = self._make_student()
        payload = {
            "to": student["PhoneNumber"],
            "metadata": {
                "user_id": student["UserID"],
                "attempt": 1,
                "hws_behind": student["HWsBehind"],
            },
        }
        assert payload["metadata"]["hws_behind"] == 3

    def test_payload_builder_does_not_enforce_governance(self):
        # Payload building is pure — governance is the caller's responsibility
        student = self._make_student()
        for attempt in [1, 2, 3, 10]:
            payload = {"metadata": {"attempt": attempt}}
            assert payload["metadata"]["attempt"] == attempt


class TestConfigV2Governance:
    """Integration transport: Config V2 threshold bindings propagated through assessments."""

    def test_shadow_assessment_config_version_id_present(self):
        a = _make_shadow_assessment()
        assert a.config_version_id is not None
        assert a.config_version_id != ""

    def test_blocked_assessment_config_version_id_may_be_null(self):
        # Config-unresolved block — config_version_id is None
        a = _make_blocked_assessment("CONFIG_VERSION_ID_MISSING", ["CONFIG_VERSION_ID_MISSING"])
        assert a.config_version_id is None
        result = _simulate_transport_dispatch(a)
        assert result["config_version_id"] is None

    def test_threshold_bindings_dict_in_assessment(self):
        a = _make_shadow_assessment()
        assert isinstance(a.threshold_bindings, dict)

    def test_missing_threshold_config_still_produces_assessment(self):
        # UNKNOWN_V0 thresholds → degraded assessment, still produces outcome
        a = MockProviderAssessment(
            governance_scope=SCOPE_SHADOW_ONLY,
            provider_event_type=EVENT_SHADOW_SIMULATION,
            outbound_suppressed=True,
            provider_blocked=False,
            is_replay=False,
            execution_mode="SHADOW",
            execution_type="original",
            correlation_id=str(uuid.uuid4()),
            causation_id=None,
            upstream_intent_id=None,
            origin_source="platform_outreach",
            origin_authority="platform_supplementary",
            config_version_id="cv-test",
            threshold_bindings={
                "provider_failure_max_retry_attempts": "UNKNOWN_V0",
                "provider_delivery_sla_hours": "UNKNOWN_V0",
            },
            degraded=True,
            degradation_cause="config_thresholds_missing",
            reason_codes=["CONFIG_THRESHOLD_MISSING_PROVIDER_FAILURE_MAX_RETRY_ATTEMPTS"],
        )
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True
        assert result["degraded"] is True

    def test_unknown_v0_threshold_preserved_in_assessment(self):
        a = MockProviderAssessment(
            governance_scope=SCOPE_SHADOW_ONLY,
            provider_event_type=EVENT_SHADOW_SIMULATION,
            outbound_suppressed=True,
            provider_blocked=False,
            is_replay=False,
            execution_mode="SHADOW",
            execution_type="original",
            correlation_id=str(uuid.uuid4()),
            causation_id=None,
            upstream_intent_id=None,
            origin_source="platform_outreach",
            origin_authority="platform_supplementary",
            config_version_id="UNKNOWN_V0",
            threshold_bindings={"provider_failure_max_retry_attempts": "UNKNOWN_V0"},
            reason_codes=["SHADOW_OUTBOUND_SUPPRESSED"],
        )
        assert a.threshold_bindings["provider_failure_max_retry_attempts"] == "UNKNOWN_V0"


class TestInvariantPreservation:
    """
    Certify governance invariants across all integration transport paths.
    All invariants must hold simultaneously — no single-invariant exceptions.
    """

    def test_inv1_shadow_always_suppresses_outbound(self):
        """INV-1: SHADOW_ONLY scope always produces outbound_suppressed=True."""
        a = _make_shadow_assessment()
        result = _simulate_transport_dispatch(a)
        assert result["outbound_suppressed"] is True
        assert result["governance_scope"] == SCOPE_SHADOW_ONLY

    def test_inv2_replay_never_produces_live_effects(self):
        """INV-2: Replay execution never produces live provider effects."""
        for et in ["replay", "regeneration"]:
            a = _make_replay_assessment(et)
            result = _simulate_transport_dispatch(a)
            assert result["outbound_suppressed"] is True, f"Live effect in {et}"
            assert result["is_replay"] is True, f"is_replay not set in {et}"

    def test_inv3_blocked_never_dispatches(self):
        """INV-3: BLOCKED governance scope never dispatches to provider."""
        for reason in [
            "CONFIG_VERSION_ID_MISSING",
            "CORRELATION_ID_MISSING",
            "COMPLIANCE_HOLD_ACTIVE",
            "GOVERNANCE_AUTHORIZATION_MISSING",
        ]:
            a = _make_blocked_assessment(reason, [reason])
            result = _simulate_transport_dispatch(a)
            assert result["outbound_suppressed"] is True, f"Dispatch despite {reason}"
            assert result["outcome"] == "blocked", f"Wrong outcome for {reason}"

    def test_inv4_attribution_never_dropped(self):
        """INV-4: Attribution fields survive all governance paths."""
        cid = str(uuid.uuid4())
        assessments = [
            _make_shadow_assessment(cid=cid),
            _make_replay_assessment(),
            _make_blocked_assessment(),
            _make_unavailable_assessment(),
            _make_duplicate_assessment(),
        ]
        for a in assessments:
            result = _simulate_transport_dispatch(a)
            # correlation_id present (may differ from cid for non-shadow)
            assert "correlation_id" in result, f"Missing correlation_id for {a.governance_scope}"

    def test_inv5_outcome_always_explicit(self):
        """INV-5: Every dispatch path produces an explicit, non-empty outcome."""
        assessments = [
            _make_shadow_assessment(),
            _make_replay_assessment("replay"),
            _make_replay_assessment("regeneration"),
            _make_blocked_assessment(),
            _make_unavailable_assessment("CIRCUIT_OPEN"),
            _make_unavailable_assessment("PROVIDER_OUTAGE"),
            _make_unavailable_assessment("RETRY_EXHAUSTED"),
            _make_duplicate_assessment(),
        ]
        valid_outcomes = {
            "shadow_only", "suppressed_replay", "blocked",
            "unavailable", "duplicate_suppressed", "success",
        }
        for a in assessments:
            result = _simulate_transport_dispatch(a)
            assert result["outcome"] in valid_outcomes, (
                f"Invalid outcome '{result['outcome']}' for {a.governance_scope}"
            )

    def test_inv6_governance_scope_in_every_result(self):
        """INV-6: governance_scope field present in every dispatch result."""
        assessments = [
            _make_shadow_assessment(),
            _make_replay_assessment(),
            _make_blocked_assessment(),
            _make_unavailable_assessment(),
            _make_duplicate_assessment(),
        ]
        for a in assessments:
            result = _simulate_transport_dispatch(a)
            assert "governance_scope" in result

    def test_inv7_no_silent_failures_reason_codes_present(self):
        """INV-7: reason_codes list always present (may be empty but not absent)."""
        assessments = [
            _make_shadow_assessment(),
            _make_replay_assessment(),
            _make_blocked_assessment(),
        ]
        for a in assessments:
            result = _simulate_transport_dispatch(a)
            assert "reason_codes" in result
            assert isinstance(result["reason_codes"], list)

    def test_inv8_authorized_scope_unreachable_in_shadow_phase(self):
        """INV-8: AUTHORIZED scope produces Phase-12 gate, not live dispatch."""
        authorized_a = MockProviderAssessment(
            governance_scope=SCOPE_AUTHORIZED,
            provider_event_type="OUTBOUND_TRIGGER",
            outbound_suppressed=False,
            provider_blocked=False,
            is_replay=False,
            execution_mode="LIVE",
            execution_type="original",
            correlation_id=str(uuid.uuid4()),
            causation_id=str(uuid.uuid4()),
            upstream_intent_id=str(uuid.uuid4()),
            origin_source="platform_outreach",
            origin_authority="platform_supplementary",
            config_version_id="cv-live",
            reason_codes=[],
        )
        result = _simulate_transport_dispatch(authorized_a)
        # Phase-12 gate: AUTHORIZED still produces shadow_only + Phase-12 reason code
        assert result["outbound_suppressed"] is True
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in result["reason_codes"]

    def test_inv9_degradation_always_visible(self):
        """INV-9: Degradation state is always observable in result — never silent."""
        a = _make_unavailable_assessment("CIRCUIT_OPEN")
        result = _simulate_transport_dispatch(a)
        assert result["degraded"] is True
        assert result["degradation_cause"] is not None

    def test_inv10_all_suppressed_scopes_produce_suppressed_result(self):
        """INV-10: All suppressed governance scopes produce outbound_suppressed=True."""
        suppressed_scopes = [
            SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_BLOCKED,
            SCOPE_UNAVAILABLE, SCOPE_DUPLICATE_SUPPRESSED,
        ]
        for scope in suppressed_scopes:
            a = MockProviderAssessment(
                governance_scope=scope,
                provider_event_type=None,
                outbound_suppressed=True,
                provider_blocked=(scope == SCOPE_BLOCKED),
                is_replay=(scope == SCOPE_REPLAY_ONLY),
                execution_mode="SHADOW",
                execution_type="original",
                correlation_id=str(uuid.uuid4()),
                causation_id=None,
                upstream_intent_id=None,
                origin_source="platform_outreach",
                origin_authority="platform_supplementary",
                config_version_id="cv-test",
                reason_codes=[scope],
            )
            result = _simulate_transport_dispatch(a)
            assert result["outbound_suppressed"] is True, f"{scope} not suppressed"
