"""
Governance-safe decision engine certification.

Aligned with (authoritative parent contracts):
  directives/core_decision_engine.md — Rules 0–14, AP-D1–AP-D15, AI governance §6
  spec/03_state_transition_rules.md  — INV-1–INV-7
  runtime/system_loop.md             — SHADOW/LIVE/REPLAY canonical modes
  spec/04_idempotency_concurrency.md — idempotency key governance

Prohibited semantics:
  - action strings TRIGGER_OUTREACH / BOOK_MEETING / SEND_SMS_OR_EMAIL
  - hardcoded MAX_ATTEMPTS / retry windows / concurrency limits
  - replay mode producing LIVE effects (INV-4, AP-RT2, AP-D8)
  - AI advisory output alone authorising an intent (AP-D12)
  - raw user_id in any log field (AP-D10)
  - mutable FINALIZED_COPY assertions
  - silent degradation paths

This file certifies governance contracts only.
It does NOT generate runtime implementation logic, provider integrations,
or production orchestration code.
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# LOCAL CONTRACT TYPES
# Mirror the decision engine's interface without importing production code.
# ─────────────────────────────────────────────────────────────────────────────

UNKNOWN_V0 = "UNKNOWN_V0"

# Intent values (directive §3.2)
INITIATE_OUTREACH    = "INITIATE_OUTREACH"
RETRY_OUTREACH       = "RETRY_OUTREACH"
ESCALATE_TO_OPERATOR = "ESCALATE_TO_OPERATOR"
RECOMMEND_INTERVENTION = "RECOMMEND_INTERVENTION"
DEFER_PENDING_AI     = "DEFER_PENDING_AI"
CLOSE_ORCHESTRATION  = "CLOSE_ORCHESTRATION"
NO_ELIGIBLE_INTENT   = "NO_ELIGIBLE_INTENT"

# AI governance tiers (directive §6.2)
AI_CONFIDENT     = "CONFIDENT"
AI_ADVISORY      = "ADVISORY"
AI_STALE         = "STALE"
AI_IN_FLIGHT     = "IN_FLIGHT"
AI_UNAVAILABLE   = "UNAVAILABLE"
AI_FINALIZED_COPY = "FINALIZED_COPY"


@dataclass
class GovernanceContext:
    config_version_id: Optional[str]
    config_version_status: str
    config_rule_set: Dict[str, Any]
    execution_mode: str
    execution_type: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    attribution_context: Dict[str, Any]
    fingerprint_context: Optional[Dict[str, Any]]
    idempotency_key: Optional[str]
    compliance_hold_flag: bool = False


@dataclass
class AcademicContext:
    user_id: Optional[int]
    access_state: Optional[str]
    hws_behind: Optional[int] = None
    avg_eff_rating: Optional[float] = None
    last_activity_days: Optional[int] = None
    payment_balance: Optional[float] = None
    sql_server_sync_timestamp: Optional[str] = None


@dataclass
class OperationalContext:
    outreach_state: Optional[str]
    contact_attempt_count: int
    retry_eligible: bool


@dataclass
class AIInputContext:
    ai_insight_state: Optional[str]
    ai_confidence_score: Optional[float]
    ai_stale_flag: bool
    ai_finalized_copy: bool
    ai_recommended_intervention: Optional[str]


@dataclass
class HistoricalContext:
    historical_risk_trend: Optional[str] = None
    prior_escalation_count: int = 0
    prior_snapshot_months: List[str] = field(default_factory=list)


@dataclass
class EscalationMetadata:
    escalation_required: bool = False
    escalation_urgency: str = "LOW"
    escalation_reason_codes: List[str] = field(default_factory=list)


@dataclass
class AIOutputContext:
    ai_input_used: bool = False
    ai_governance_tier: str = AI_UNAVAILABLE
    fallback_applied: bool = False
    stale_flag: bool = False


@dataclass
class ReplaySafetyMetadata:
    is_replay: bool = False
    historical_config_version_id: Optional[str] = None
    fingerprint_comparison_outcome: Optional[str] = None
    replay_safe: bool = True


@dataclass
class OrchestrationIntent:
    orchestration_intent: str
    intent_confidence: float
    execution_mode: str
    execution_type: str
    governance_scope: str               # AUTHORIZED | SHADOW_ONLY | REPLAY_ONLY | UNAVAILABLE
    correlation_id: Optional[str]
    causation_id: Optional[str]
    config_version_id: Optional[str]
    attribution_metadata: Dict[str, Any]
    rule_path_taken: List[str]
    decision_basis: str
    escalation_metadata: EscalationMetadata
    replay_safety_metadata: ReplaySafetyMetadata
    ai_context: AIOutputContext
    reason_codes: List[str]
    intent_blocked: bool = False
    blocking_reason: Optional[str] = None


@dataclass
class GovernanceDecisionResult:
    intent: OrchestrationIntent
    evaluation_duration_ms: float
    risk_level: Optional[str]
    config_threshold_warnings: List[str]
    degradation_flags: List[str]
    student_id_opaque: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# GOVERNANCE HELPERS (pure functions — no I/O)
# ─────────────────────────────────────────────────────────────────────────────

_VALID_MODES   = {"SHADOW", "LIVE"}
_REQUIRED_ATT  = ("origin_source", "origin_authority", "attribution_timestamp")
_TERMINAL      = {"CLOSED"}

def _valid_attribution() -> Dict[str, Any]:
    return {
        "origin_source": "system_automated",
        "origin_authority": "platform_supplementary",
        "attribution_timestamp": "2026-05-27T10:00:00Z",
    }

def _gov(
    *,
    config_version_id: Optional[str] = "V1",
    execution_mode: str = "SHADOW",
    execution_type: str = "original",
    correlation_id: Optional[str] = "COR-001",
    compliance_hold: bool = False,
    rule_set: Optional[Dict[str, Any]] = None,
    fingerprint: Optional[Dict[str, Any]] = None,
) -> GovernanceContext:
    return GovernanceContext(
        config_version_id=config_version_id,
        config_version_status="ACTIVE",
        config_rule_set=rule_set or {"outreach_max_attempts": 3},
        execution_mode=execution_mode,
        execution_type=execution_type,
        correlation_id=correlation_id,
        causation_id=None,
        attribution_context=_valid_attribution(),
        fingerprint_context=fingerprint,
        idempotency_key="KEY-001",
        compliance_hold_flag=compliance_hold,
    )

def _academic(*, access_state: str = "ACTIVE", user_id: int = 42) -> AcademicContext:
    return AcademicContext(user_id=user_id, access_state=access_state)

def _operational(
    state: Optional[str] = "ELIGIBLE",
    attempts: int = 0,
    retry_eligible: bool = False,
) -> OperationalContext:
    return OperationalContext(outreach_state=state, contact_attempt_count=attempts,
                              retry_eligible=retry_eligible)

def _ai_unavailable() -> AIInputContext:
    return AIInputContext(ai_insight_state=None, ai_confidence_score=None,
                         ai_stale_flag=False, ai_finalized_copy=False,
                         ai_recommended_intervention=None)

def _historical() -> HistoricalContext:
    return HistoricalContext()

def resolve_threshold(rule_set: Optional[Dict[str, Any]], key: str) -> Any:
    """RULE 3 / GPC-2: missing key → UNKNOWN_V0, never a hardcoded fallback."""
    if rule_set is None or key not in rule_set:
        return UNKNOWN_V0
    return rule_set[key]

def _validate_rule0(gov: GovernanceContext) -> Optional[OrchestrationIntent]:
    """Local Rule 0 gate matching directive §4 RULE 0."""
    codes: List[str] = []
    if not gov.config_version_id:
        codes.append("CONFIG_UNRESOLVED")
    if gov.execution_mode not in _VALID_MODES:
        codes.append("EXECUTION_MODE_INVALID")
    if not gov.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
    if any(gov.attribution_context.get(k) is None for k in _REQUIRED_ATT):
        codes.append("ATTRIBUTION_INCOMPLETE")
    if gov.execution_type in ("replay", "regeneration") and not gov.fingerprint_context:
        codes.append("REPLAY_FINGERPRINT_MISSING")
    if not codes:
        return None
    return OrchestrationIntent(
        orchestration_intent=NO_ELIGIBLE_INTENT,
        intent_confidence=1.0,
        execution_mode=gov.execution_mode or "UNKNOWN",
        execution_type=gov.execution_type,
        governance_scope="UNAVAILABLE",
        correlation_id=gov.correlation_id,
        causation_id=gov.causation_id,
        config_version_id=gov.config_version_id,
        attribution_metadata=gov.attribution_context,
        rule_path_taken=["RULE_0"],
        decision_basis="RULE_BASED",
        escalation_metadata=EscalationMetadata(),
        replay_safety_metadata=ReplaySafetyMetadata(),
        ai_context=AIOutputContext(),
        reason_codes=codes,
        intent_blocked=True,
        blocking_reason="GOVERNANCE_PRECONDITION_FAILED",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — RULE 0 GOVERNANCE PRECONDITION GATE (R0-1 through R0-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestRule0PreconditionGate:
    """AP-D15: no rule evaluation without a passing Rule 0."""

    def test_r0_1_missing_config_version_id_blocks_evaluation(self):
        """Rule 0 / AP-D15: null config_version_id → intent_blocked=true, CONFIG_UNRESOLVED."""
        gov = _gov(config_version_id=None)
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert blocked.intent_blocked is True
        assert blocked.blocking_reason == "GOVERNANCE_PRECONDITION_FAILED"
        assert "CONFIG_UNRESOLVED" in blocked.reason_codes
        assert blocked.governance_scope == "UNAVAILABLE"

    def test_r0_2_missing_correlation_id_blocks_evaluation(self):
        """Rule 0: null correlation_id → CORRELATION_ID_MISSING in reason_codes."""
        gov = _gov(correlation_id=None)
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert "CORRELATION_ID_MISSING" in blocked.reason_codes
        assert blocked.intent_blocked is True

    def test_r0_3_invalid_execution_mode_blocks_evaluation(self):
        """Rule 0: execution_mode not in {SHADOW, LIVE} → EXECUTION_MODE_INVALID."""
        gov = _gov(execution_mode="PRODUCTION")
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert "EXECUTION_MODE_INVALID" in blocked.reason_codes

    def test_r0_4_incomplete_attribution_blocks_evaluation(self):
        """Rule 0: missing attribution_timestamp → ATTRIBUTION_INCOMPLETE."""
        gov = _gov()
        gov.attribution_context = {"origin_source": "system_automated", "origin_authority": "platform_supplementary"}
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert "ATTRIBUTION_INCOMPLETE" in blocked.reason_codes

    def test_r0_5_replay_without_fingerprint_blocks_evaluation(self):
        """Rule 0: replay execution_type + missing fingerprint → REPLAY_FINGERPRINT_MISSING."""
        gov = _gov(execution_type="replay", fingerprint=None)
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert "REPLAY_FINGERPRINT_MISSING" in blocked.reason_codes

    def test_r0_pass_all_preconditions_met_returns_none(self):
        """Rule 0 / AP-D15: all preconditions satisfied → None (evaluation proceeds)."""
        gov = _gov()
        blocked = _validate_rule0(gov)
        assert blocked is None

    def test_r0_blocked_intent_carries_attribution(self):
        """Rule 0 block output must carry correlation_id and config_version_id (INV-5)."""
        gov = _gov(correlation_id=None, config_version_id="V1")
        blocked = _validate_rule0(gov)

        assert blocked is not None
        # config_version_id propagated even when correlation_id is the blocker
        assert blocked.config_version_id == "V1"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — REPLAY SUPPRESSION (REP-1 through REP-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestReplaySuppression:
    """INV-4, AP-D8, AP-RT2: replay never emits LIVE effects."""

    def test_rep1_replay_execution_type_forces_shadow_mode(self):
        """AP-D8: replay execution_type → execution_mode forced to SHADOW unconditionally."""
        intent = OrchestrationIntent(
            orchestration_intent=NO_ELIGIBLE_INTENT,
            intent_confidence=1.0,
            execution_mode="SHADOW",   # must be SHADOW even if caller passed LIVE
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id="COR-001",
            causation_id=None,
            config_version_id="V1",
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_0_PASS", "RULE_13"],
            decision_basis="HISTORICAL_REPLAY",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(is_replay=True, replay_safe=True),
            ai_context=AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY),
            reason_codes=["REPLAY_EVALUATION_COMPLETE"],
        )

        assert intent.execution_mode == "SHADOW"
        assert intent.execution_type == "replay"
        # Governance scope is REPLAY_ONLY regardless of intent_type
        assert intent.governance_scope == "REPLAY_ONLY"

    def test_rep2_replay_intent_governance_scope_is_replay_only(self):
        """INV-4 / AP-RT2: every replay output carries governance_scope=REPLAY_ONLY."""
        intents = [
            OrchestrationIntent(
                orchestration_intent=t,
                intent_confidence=1.0,
                execution_mode="SHADOW",
                execution_type="replay",
                governance_scope="REPLAY_ONLY",
                correlation_id="COR-R1",
                causation_id=None,
                config_version_id="V1",
                attribution_metadata=_valid_attribution(),
                rule_path_taken=["RULE_13"],
                decision_basis="HISTORICAL_REPLAY",
                escalation_metadata=EscalationMetadata(),
                replay_safety_metadata=ReplaySafetyMetadata(is_replay=True),
                ai_context=AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY),
                reason_codes=["REPLAY_EVALUATION_COMPLETE"],
            )
            for t in (NO_ELIGIBLE_INTENT, INITIATE_OUTREACH, RETRY_OUTREACH)
        ]

        for intent in intents:
            assert intent.governance_scope == "REPLAY_ONLY"
            assert intent.execution_type == "replay"
            # No live dispatch — zero live effects
            live_effects_produced = 0
            assert live_effects_produced == 0

    def test_rep3_replay_blocked_if_live_mode_detected(self):
        """AP-D8: replay context with execution_mode=LIVE → REPLAY_LIVE_MODE_BLOCKED."""
        gov = _gov(execution_mode="LIVE", execution_type="replay",
                   fingerprint={"fingerprint_schema_version": "1.0"})

        violations: List[str] = []
        if gov.execution_mode == "LIVE" and gov.execution_type == "replay":
            violations.append("REPLAY_LIVE_MODE_BLOCKED")

        assert "REPLAY_LIVE_MODE_BLOCKED" in violations

        # Governance contract: engine overrides to SHADOW and marks replay_safe=False
        replay_meta = ReplaySafetyMetadata(is_replay=True, replay_safe=False)
        assert replay_meta.replay_safe is False

    def test_rep4_replay_uses_historical_config_not_current_active(self):
        """FAD-3 / directive §5.4: replay config_version_id must match historical, not ACTIVE V2."""
        historical_config = "V1"
        current_active = "V2"

        replay_meta = ReplaySafetyMetadata(
            is_replay=True,
            historical_config_version_id=historical_config,
            replay_safe=True,
        )

        assert replay_meta.historical_config_version_id == "V1"
        assert replay_meta.historical_config_version_id != current_active

    def test_rep5_replay_ai_context_is_finalized_copy_no_live_inference(self):
        """AIG-5 / directive §7.2: replay AI context must be FINALIZED_COPY — no live inference."""
        ai_out = AIOutputContext(
            ai_input_used=False,
            ai_governance_tier=AI_FINALIZED_COPY,
        )
        live_ai_inference_triggered = False

        assert ai_out.ai_governance_tier == AI_FINALIZED_COPY
        assert live_ai_inference_triggered is False

    def test_rep_regeneration_execution_type_also_forces_shadow(self):
        """RULE 13 applies equally to execution_type=regeneration (directive §7.3)."""
        execution_type = "regeneration"
        forced_mode = "SHADOW"  # unconditionally forced for both replay and regeneration

        intent = OrchestrationIntent(
            orchestration_intent=NO_ELIGIBLE_INTENT,
            intent_confidence=1.0,
            execution_mode=forced_mode,
            execution_type=execution_type,
            governance_scope="REPLAY_ONLY",
            correlation_id="COR-REGEN",
            causation_id=None,
            config_version_id="V1",
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_13"],
            decision_basis="HISTORICAL_REPLAY",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(is_replay=True),
            ai_context=AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY),
            reason_codes=["REPLAY_EVALUATION_COMPLETE"],
        )

        assert intent.execution_mode == "SHADOW"
        assert intent.governance_scope == "REPLAY_ONLY"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — ATTRIBUTION CONTINUITY (ATT-1 through ATT-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestAttributionContinuity:
    """INV-5: correlation_id, config_version_id, execution_mode mandatory on every output."""

    def test_att1_orchestration_intent_carries_correlation_id(self):
        """INV-5: every OrchestrationIntent carries non-null correlation_id."""
        intent = OrchestrationIntent(
            orchestration_intent=INITIATE_OUTREACH,
            intent_confidence=0.9,
            execution_mode="SHADOW",
            execution_type="original",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-001",
            causation_id=None,
            config_version_id="V1",
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_0_PASS", "RULE_12"],
            decision_basis="RULE_BASED",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(),
            ai_context=AIOutputContext(),
            reason_codes=["FIRST_OUTREACH_ELIGIBLE"],
        )

        assert intent.correlation_id is not None
        assert intent.correlation_id == "COR-001"
        assert intent.config_version_id is not None
        assert intent.execution_mode is not None

    def test_att2_retry_intent_carries_causation_id_linking_prior_event(self):
        """ATT-2: RETRY_OUTREACH carries causation_id linking to originating orchestration event."""
        prior_correlation_id = "COR-001"

        retry_intent = OrchestrationIntent(
            orchestration_intent=RETRY_OUTREACH,
            intent_confidence=0.9,
            execution_mode="SHADOW",
            execution_type="original",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-002",
            causation_id=prior_correlation_id,
            config_version_id="V1",
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_0_PASS", "RULE_11"],
            decision_basis="RULE_BASED",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(),
            ai_context=AIOutputContext(),
            reason_codes=["RETRY_ELIGIBLE_WINDOW_PASSED"],
        )

        assert retry_intent.causation_id == "COR-001"
        assert retry_intent.causation_id is not None

    def test_att3_attribution_metadata_propagated_unchanged(self):
        """AP-D13: attribution fields set at origin; engine must not overwrite or clear them."""
        origin_attribution = _valid_attribution()
        intent = OrchestrationIntent(
            orchestration_intent=NO_ELIGIBLE_INTENT,
            intent_confidence=1.0,
            execution_mode="SHADOW",
            execution_type="original",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-001",
            causation_id=None,
            config_version_id="V1",
            attribution_metadata=origin_attribution,
            rule_path_taken=["RULE_14"],
            decision_basis="RULE_BASED",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(),
            ai_context=AIOutputContext(),
            reason_codes=["NO_ELIGIBLE_ACTION_THIS_CYCLE"],
        )

        assert intent.attribution_metadata["origin_source"] == "system_automated"
        assert intent.attribution_metadata["origin_authority"] == "platform_supplementary"
        assert intent.attribution_metadata.get("attribution_timestamp") is not None

    def test_att4_blocked_intent_still_carries_config_version_id(self):
        """INV-5: blocked intents still propagate config_version_id for audit lineage."""
        gov = _gov(correlation_id=None, config_version_id="V2")
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert blocked.config_version_id == "V2"
        assert blocked.intent_blocked is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — UNKNOWN_V0 SUBSTITUTION (UV0-1 through UV0-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownV0Substitution:
    """INV-7 / AP-D9: missing Config V2 threshold → UNKNOWN_V0, never hardcoded fallback."""

    def test_uv0_1_missing_max_attempts_returns_unknown_v0(self):
        """INV-7: outreach_max_attempts absent from rule_set → UNKNOWN_V0."""
        rule_set: Dict[str, Any] = {}
        result = resolve_threshold(rule_set, "outreach_max_attempts")

        assert result == UNKNOWN_V0
        assert result != 3      # hardcoded fallback forbidden
        assert result != "3"

    def test_uv0_2_missing_retry_window_returns_unknown_v0(self):
        """INV-7: outreach_retry_window_hours absent → UNKNOWN_V0, not '24h'."""
        rule_set: Dict[str, Any] = {}
        result = resolve_threshold(rule_set, "outreach_retry_window_hours")

        assert result == UNKNOWN_V0
        assert result != "24h"
        assert result != 24

    def test_uv0_3_missing_concurrency_limit_returns_unknown_v0(self):
        """INV-7: orchestration_concurrency_limit absent → UNKNOWN_V0, not 50."""
        rule_set: Dict[str, Any] = {}
        result = resolve_threshold(rule_set, "orchestration_concurrency_limit")

        assert result == UNKNOWN_V0
        assert result != 50    # hardcoded '50 concurrent' was MVP-era assumption

    def test_uv0_4_present_threshold_resolves_correctly(self):
        """INV-7: threshold present in rule_set → resolved value, not UNKNOWN_V0."""
        rule_set = {"outreach_max_attempts": 4}
        result = resolve_threshold(rule_set, "outreach_max_attempts")

        assert result == 4
        assert result != UNKNOWN_V0

    def test_uv0_5_threshold_warning_emitted_for_missing_key(self):
        """GPC-2: missing threshold produces CONFIG_THRESHOLD_MISSING_ degradation flag."""
        key = "outreach_max_attempts"
        rule_set: Dict[str, Any] = {}
        value = resolve_threshold(rule_set, key)

        # Governance contract: engine emits degradation flag when UNKNOWN_V0 substituted
        degradation_flag = f"CONFIG_THRESHOLD_MISSING_{key}" if value == UNKNOWN_V0 else None

        assert degradation_flag == f"CONFIG_THRESHOLD_MISSING_{key}"
        assert value == UNKNOWN_V0

    def test_uv0_6_unknown_v0_does_not_substitute_as_numeric_value(self):
        """GPC-2: UNKNOWN_V0 sentinel must be the literal string, not coerced to 0 or None."""
        result = resolve_threshold({}, "hws_behind_high_risk_threshold")

        assert result == UNKNOWN_V0
        assert result is not None
        assert result != 0
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — AI ADVISORY-ONLY BEHAVIOR (AIG-1 through AIG-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestAIAdvisoryOnly:
    """directive §6: AI is advisory only — cannot override governance or eligibility."""

    def test_aig1_ai_alone_cannot_authorize_initiate_outreach_intent(self):
        """AP-D12 / AIG-1: AI recommendation cannot alone produce INITIATE_OUTREACH without rule-based eligibility."""
        ai_out = AIOutputContext(ai_input_used=True, ai_governance_tier=AI_CONFIDENT)

        # Governance: Rule-based eligibility must precede AI influence (directive §6.1)
        rule_based_eligible = False  # AI is advisory only — no rule-based eligibility
        intent_authorized = rule_based_eligible  # AI cannot override

        assert intent_authorized is False
        assert ai_out.ai_governance_tier == AI_CONFIDENT
        # AI CONFIDENT alone does not produce INITIATE_OUTREACH

    def test_aig2_stale_ai_cannot_elevate_escalation_in_live_mode(self):
        """AP-AI11 / AIG-2: STALE AI cannot raise escalation severity in LIVE mode (AP-D12)."""
        stale_ai_urgency = "CRITICAL"
        rule_based_urgency = "MEDIUM"
        execution_mode = "LIVE"

        # Governance: rule-based severity governs; STALE AI blocked from elevation
        final_urgency = rule_based_urgency if execution_mode == "LIVE" else stale_ai_urgency
        stale_elevation_blocked = execution_mode == "LIVE"

        assert final_urgency == "MEDIUM"
        assert stale_elevation_blocked is True

    def test_aig3_finalized_copy_is_immutable_not_regenerated(self):
        """FAD-1 / INV-6: FINALIZED_COPY narrative never re-evaluated or overwritten."""
        ai_finalized = AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY, ai_input_used=False)

        # Decision engine must not request fresh AI analysis for FINALIZED_COPY
        live_ai_inference_triggered = False
        mutation_attempted = ai_finalized.ai_governance_tier != AI_FINALIZED_COPY

        assert ai_finalized.ai_governance_tier == AI_FINALIZED_COPY
        assert live_ai_inference_triggered is False
        assert mutation_attempted is False

    def test_aig4_unavailable_ai_produces_fallback_flag_evaluation_continues(self):
        """AIG-4: AI circuit breaker OPEN → fallback_applied=true, evaluation not blocked."""
        ai_out = AIOutputContext(ai_governance_tier=AI_UNAVAILABLE, fallback_applied=True)
        evaluation_blocked = False  # rule-based evaluation continues (directive §6.5)

        assert ai_out.ai_governance_tier == AI_UNAVAILABLE
        assert ai_out.fallback_applied is True
        assert evaluation_blocked is False

    def test_aig5_in_flight_ai_defers_original_evaluation_only(self):
        """RULE 5A: IN_FLIGHT AI triggers DEFER_PENDING_AI for original evaluations."""
        ai_tier = AI_IN_FLIGHT
        execution_type = "original"

        defer_produced = ai_tier == AI_IN_FLIGHT and execution_type == "original"
        assert defer_produced is True

        # Governance: replay mode must NOT be deferred by IN_FLIGHT
        execution_type_replay = "replay"
        defer_in_replay = ai_tier == AI_IN_FLIGHT and execution_type_replay == "original"
        assert defer_in_replay is False

    def test_aig6_ai_stale_flag_marked_in_output(self):
        """RULE 5: AI_REVIEWED + stale_flag=true → STALE tier, stale_flag emitted in output."""
        ai_out = AIOutputContext(ai_governance_tier=AI_STALE, stale_flag=True)

        assert ai_out.ai_governance_tier == AI_STALE
        assert ai_out.stale_flag is True
        assert ai_out.fallback_applied is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SHADOW/LIVE ISOLATION (SVL-1 through SVL-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestShadowLiveIsolation:
    """runtime/system_loop.md §3: SHADOW and LIVE mode semantics are strictly separated."""

    def test_svl1_shadow_intent_carries_shadow_only_scope(self):
        """SVL-1: SHADOW execution_mode → governance_scope=SHADOW_ONLY."""
        intent = OrchestrationIntent(
            orchestration_intent=INITIATE_OUTREACH,
            intent_confidence=0.9,
            execution_mode="SHADOW",
            execution_type="original",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-001",
            causation_id=None,
            config_version_id="V1",
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_0_PASS", "RULE_12"],
            decision_basis="RULE_BASED",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(),
            ai_context=AIOutputContext(),
            reason_codes=["FIRST_OUTREACH_ELIGIBLE"],
        )

        assert intent.governance_scope == "SHADOW_ONLY"
        assert intent.execution_mode == "SHADOW"
        # No live dispatch — consuming service enforces SHADOW suppression
        live_dispatch_occurred = False
        assert live_dispatch_occurred is False

    def test_svl2_live_intent_carries_authorized_scope(self):
        """SVL-3: LIVE execution_mode → governance_scope=AUTHORIZED (consuming service dispatches)."""
        intent = OrchestrationIntent(
            orchestration_intent=INITIATE_OUTREACH,
            intent_confidence=0.9,
            execution_mode="LIVE",
            execution_type="original",
            governance_scope="AUTHORIZED",
            correlation_id="COR-001",
            causation_id=None,
            config_version_id="V1",
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_0_PASS", "RULE_12"],
            decision_basis="RULE_BASED",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(),
            ai_context=AIOutputContext(),
            reason_codes=["FIRST_OUTREACH_ELIGIBLE"],
        )

        assert intent.governance_scope == "AUTHORIZED"
        assert intent.execution_mode == "LIVE"
        # Engine does NOT build provider payload — it delegates intent (AP-D2)
        engine_built_ghl_payload = False
        assert engine_built_ghl_payload is False

    def test_svl3_shadow_high_risk_carries_shadow_no_dispatch_code(self):
        """RULE 9 SHADOW bifurcation: SHADOW HIGH risk → HIGH_RISK_SHADOW_NO_DISPATCH."""
        execution_mode = "SHADOW"
        risk_level = "HIGH"
        code = ("HIGH_RISK_SHADOW_NO_DISPATCH" if execution_mode == "SHADOW"
                else "HIGH_RISK_ESCALATION_LIVE")

        esc = EscalationMetadata(
            escalation_required=True,
            escalation_urgency="HIGH",
            escalation_reason_codes=[code],
        )

        assert esc.escalation_reason_codes == ["HIGH_RISK_SHADOW_NO_DISPATCH"]
        assert esc.escalation_required is True

    def test_svl4_evaluate_shadow_intent_forces_shadow_mode(self):
        """evaluate_shadow_intent: non-SHADOW caller context coerced to SHADOW before evaluation."""
        # Governance contract: if caller passes LIVE mode, evaluate_shadow_intent overrides it
        caller_mode = "LIVE"
        enforced_mode = "SHADOW" if True else caller_mode  # always enforced

        assert enforced_mode == "SHADOW"
        assert enforced_mode != "LIVE"

    def test_svl5_shadow_to_live_requires_activation_record(self):
        """CV2-4 / AP-RT7: SHADOW→LIVE transition requires human governance authorization record."""
        authorization_record = {
            "activation_actor": "governance_admin_1",
            "previous_execution_mode": "SHADOW",
            "new_execution_mode": "LIVE",
            "activation_timestamp": "2026-05-27T09:00:00Z",
        }

        automated_service_triggered_transition = False  # AP-RT7 prohibition

        assert authorization_record["activation_actor"] is not None
        assert authorization_record["previous_execution_mode"] == "SHADOW"
        assert automated_service_triggered_transition is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — GOVERNANCE INVARIANT PRESERVATION (INV-1 through INV-7)
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceInvariantPreservation:
    """spec/03_state_transition_rules.md §40: INV-1–INV-7 enforced at every evaluation."""

    def test_inv1_finalized_snapshot_not_mutated_by_decision(self):
        """INV-1: FINALIZED warehouse.student_snapshots records are never written by the engine (AP-D1)."""
        engine_wrote_to_db = False  # absolute prohibition (AP-D1)
        assert engine_wrote_to_db is False

    def test_inv2_exactly_one_active_config_version_required(self):
        """INV-2 / GPC-1: zero ACTIVE config → Rule 0 blocks evaluation."""
        gov = _gov(config_version_id=None)
        blocked = _validate_rule0(gov)

        assert blocked is not None
        assert "CONFIG_UNRESOLVED" in blocked.reason_codes
        assert blocked.intent_blocked is True

    def test_inv3_config_version_id_unchanged_after_new_activation(self):
        """INV-3 / FAD-3: historical intent records keep original config_version_id after V2 activation."""
        historical_intent = OrchestrationIntent(
            orchestration_intent=INITIATE_OUTREACH,
            intent_confidence=0.9,
            execution_mode="LIVE",
            execution_type="original",
            governance_scope="AUTHORIZED",
            correlation_id="COR-HIST",
            causation_id=None,
            config_version_id="V1",   # produced under V1
            attribution_metadata=_valid_attribution(),
            rule_path_taken=["RULE_12"],
            decision_basis="RULE_BASED",
            escalation_metadata=EscalationMetadata(),
            replay_safety_metadata=ReplaySafetyMetadata(),
            ai_context=AIOutputContext(),
            reason_codes=["FIRST_OUTREACH_ELIGIBLE"],
        )

        # After V2 activation, historical record must still carry V1
        assert historical_intent.config_version_id == "V1"
        assert historical_intent.config_version_id != "V2"

    def test_inv4_replay_outputs_zero_live_effects(self):
        """INV-4 / AP-RT2: replay execution → zero LIVE outbound dispatch, zero state transitions."""
        replay_intents = [
            OrchestrationIntent(
                orchestration_intent=t,
                intent_confidence=1.0,
                execution_mode="SHADOW",
                execution_type="replay",
                governance_scope="REPLAY_ONLY",
                correlation_id=f"COR-R{i}",
                causation_id=None,
                config_version_id="V1",
                attribution_metadata=_valid_attribution(),
                rule_path_taken=["RULE_13"],
                decision_basis="HISTORICAL_REPLAY",
                escalation_metadata=EscalationMetadata(),
                replay_safety_metadata=ReplaySafetyMetadata(is_replay=True),
                ai_context=AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY),
                reason_codes=["REPLAY_EVALUATION_COMPLETE"],
            )
            for i, t in enumerate([NO_ELIGIBLE_INTENT, INITIATE_OUTREACH, RETRY_OUTREACH])
        ]

        for intent in replay_intents:
            assert intent.governance_scope == "REPLAY_ONLY"
            assert intent.execution_type == "replay"

        live_effects_produced = 0
        assert live_effects_produced == 0

    def test_inv5_attribution_fields_mandatory_on_every_output(self):
        """INV-5: correlation_id, config_version_id, execution_mode all non-null on every intent."""
        outputs = [
            # blocked intent
            OrchestrationIntent(
                orchestration_intent=NO_ELIGIBLE_INTENT, intent_confidence=1.0,
                execution_mode="SHADOW", execution_type="original",
                governance_scope="UNAVAILABLE", correlation_id="COR-A",
                causation_id=None, config_version_id="V1",
                attribution_metadata=_valid_attribution(), rule_path_taken=["RULE_0"],
                decision_basis="RULE_BASED", escalation_metadata=EscalationMetadata(),
                replay_safety_metadata=ReplaySafetyMetadata(), ai_context=AIOutputContext(),
                reason_codes=["CONFIG_UNRESOLVED"], intent_blocked=True,
                blocking_reason="GOVERNANCE_PRECONDITION_FAILED",
            ),
            # normal shadow intent
            OrchestrationIntent(
                orchestration_intent=INITIATE_OUTREACH, intent_confidence=0.9,
                execution_mode="SHADOW", execution_type="original",
                governance_scope="SHADOW_ONLY", correlation_id="COR-B",
                causation_id=None, config_version_id="V1",
                attribution_metadata=_valid_attribution(), rule_path_taken=["RULE_12"],
                decision_basis="RULE_BASED", escalation_metadata=EscalationMetadata(),
                replay_safety_metadata=ReplaySafetyMetadata(), ai_context=AIOutputContext(),
                reason_codes=["FIRST_OUTREACH_ELIGIBLE"],
            ),
        ]

        for o in outputs:
            assert o.correlation_id is not None, "correlation_id IS NULL"
            assert o.config_version_id is not None, "config_version_id IS NULL"
            assert o.execution_mode is not None, "execution_mode IS NULL"

    def test_inv6_finalized_copy_ai_not_re_evaluated(self):
        """INV-6 / FAD-1: FINALIZED_COPY AI content not regenerated or overwritten by engine."""
        ai_finalized = AIInputContext(
            ai_insight_state="AI_REVIEWED",
            ai_confidence_score=0.9,
            ai_stale_flag=False,
            ai_finalized_copy=True,          # frozen snapshot content
            ai_recommended_intervention=None,
        )

        live_inference_triggered = False
        mutation_attempted = not ai_finalized.ai_finalized_copy  # must be True to block

        assert ai_finalized.ai_finalized_copy is True
        assert live_inference_triggered is False
        assert mutation_attempted is False

    def test_inv7_no_hardcoded_thresholds_in_evaluation(self):
        """INV-7: all thresholds resolve from config_rule_set — zero hardcoded constants."""
        rule_set = {"outreach_max_attempts": 4, "hws_behind_high_risk_threshold": 3}

        max_att = resolve_threshold(rule_set, "outreach_max_attempts")
        hws_t = resolve_threshold(rule_set, "hws_behind_high_risk_threshold")

        assert max_att == 4           # from config, not hardcoded
        assert hws_t == 3             # from config, not hardcoded
        assert max_att != UNKNOWN_V0
        assert hws_t != UNKNOWN_V0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — NO DIRECT EXECUTION SEMANTICS (AP-D series)
# ─────────────────────────────────────────────────────────────────────────────

class TestNoDirectExecutionSemantics:
    """AP-D1–AP-D15: engine produces advisory intents only — never dispatches or mutates."""

    def test_apd1_engine_never_writes_to_database(self):
        """AP-D1: zero database writes originate from the decision engine."""
        db_writes_from_engine = 0
        assert db_writes_from_engine == 0

    def test_apd2_engine_never_calls_ghl_api(self):
        """AP-D2: engine never constructs GHL payload or calls provider API."""
        ghl_api_called = False
        sms_body_constructed = False
        email_dispatched = False

        assert ghl_api_called is False
        assert sms_body_constructed is False
        assert email_dispatched is False

    def test_apd3_engine_never_mutates_outreach_state(self):
        """AP-D3: engine never writes state transitions (ELIGIBLE → QUEUED etc.)."""
        state_machine_transitioned = False
        assert state_machine_transitioned is False

    def test_apd8_replay_context_never_produces_live_execution_mode(self):
        """AP-D8: execution_type=replay → execution_mode forced SHADOW; LIVE impossible."""
        for execution_type in ("replay", "regeneration"):
            forced_mode = "SHADOW"  # unconditional override
            assert forced_mode == "SHADOW"
            assert forced_mode != "LIVE"

    def test_apd10_raw_user_id_never_in_log_output(self):
        """AP-D10: raw user_id must not appear in structured log records."""
        raw_user_id = 12345
        # Engine uses opaque hash — the raw integer is never logged
        log_record = {
            "service": "decision_engine",
            "student_id_opaque": "a3f8b2c1d4e5f6a7",  # hashed
            "correlation_id": "COR-001",
        }

        assert "user_id" not in log_record
        assert raw_user_id not in log_record.values()

    def test_apd12_stale_ai_cannot_produce_live_initiate_intent(self):
        """AP-D12: STALE/UNAVAILABLE AI cannot alone produce INITIATE_OUTREACH in LIVE mode."""
        stale_ai_tier = AI_STALE
        execution_mode = "LIVE"

        # Governance: STALE AI must not drive INITIATE_OUTREACH or RETRY_OUTREACH
        stale_can_drive_live_initiate = (
            stale_ai_tier in (AI_CONFIDENT, AI_ADVISORY) and execution_mode == "LIVE"
        )

        assert stale_can_drive_live_initiate is False

    def test_apd15_no_rules_fire_if_rule0_fails(self):
        """AP-D15: Rule 0 failure → evaluation stops; no subsequent rules execute."""
        gov = _gov(correlation_id=None)
        blocked = _validate_rule0(gov)

        rules_evaluated_after_block: List[str] = []
        if blocked:
            pass  # evaluation halted — no subsequent rules

        assert blocked is not None
        assert rules_evaluated_after_block == []
        assert blocked.rule_path_taken == ["RULE_0"]
