"""
Governance-safe orchestration intelligence service.

Implements the Core Decision Engine per directives/core_decision_engine.md.
Produces OrchestrationIntent advisory signals only.

AP-D1  — NEVER writes to any database
AP-D2  — NEVER dispatches outbound communications
AP-D3  — NEVER mutates outreach state
AP-D8  — NEVER produces LIVE intents during replay/regeneration
AP-D9  — NEVER uses hardcoded threshold values
AP-D10 — NEVER logs raw PII (user_id, name, email, phone, AI narrative)
AP-D15 — Rule 0 must pass before any rule evaluation begins
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Config threshold sentinel — substitutes every missing Config V2 key ───────
UNKNOWN_V0 = "UNKNOWN_V0"

# ── Intent values (directive §3.2) ────────────────────────────────────────────
INITIATE_OUTREACH    = "INITIATE_OUTREACH"
RETRY_OUTREACH       = "RETRY_OUTREACH"
ESCALATE_TO_OPERATOR = "ESCALATE_TO_OPERATOR"
RECOMMEND_INTERVENTION = "RECOMMEND_INTERVENTION"
DEFER_PENDING_AI     = "DEFER_PENDING_AI"
CLOSE_ORCHESTRATION  = "CLOSE_ORCHESTRATION"
NO_ELIGIBLE_INTENT   = "NO_ELIGIBLE_INTENT"

# ── AI governance tiers (directive §6.2) ─────────────────────────────────────
AI_CONFIDENT     = "CONFIDENT"
AI_ADVISORY      = "ADVISORY"
AI_STALE         = "STALE"
AI_IN_FLIGHT     = "IN_FLIGHT"
AI_UNAVAILABLE   = "UNAVAILABLE"
AI_FINALIZED_COPY = "FINALIZED_COPY"

# ── Config rule-set keys (directive RULE 3 / INV-7) ───────────────────────────
_K_MAX_ATTEMPTS      = "outreach_max_attempts"
_K_HWS_RISK          = "hws_behind_high_risk_threshold"
_K_EFF_RISK          = "avg_eff_rating_low_risk_threshold"
_K_INACTIVITY_RISK   = "last_activity_high_risk_days"
_K_PAYMENT_RISK      = "payment_balance_risk_threshold"
_K_AI_TTL            = "ai_insight_ttl_hours"
_K_ESCALATION_REPEAT = "prior_escalation_repeat_threshold"
_K_SYNC_AGE          = "sql_server_max_sync_age_hours"

_THRESHOLD_KEYS = (
    _K_MAX_ATTEMPTS, _K_HWS_RISK, _K_EFF_RISK, _K_INACTIVITY_RISK,
    _K_PAYMENT_RISK, _K_AI_TTL, _K_ESCALATION_REPEAT, _K_SYNC_AGE,
)
_VALID_MODES          = {"SHADOW", "LIVE"}
_TERMINAL_STATES      = {"CLOSED"}
_REQUIRED_ATTRIBUTION = ("origin_source", "origin_authority", "attribution_timestamp")


# ── Input models ─────────────────────────────────────────────────────────────

@dataclass
class GovernanceContext:
    """Mandatory governance inputs (directive §2.4). Missing → Rule 0 block."""
    config_version_id: Optional[str]
    config_version_status: str          # ACTIVE | SUPERSEDED
    config_rule_set: Dict[str, Any]
    execution_mode: str                  # SHADOW | LIVE
    execution_type: str                  # original | replay | regeneration
    correlation_id: Optional[str]
    causation_id: Optional[str]
    attribution_context: Dict[str, Any]  # must contain origin_source, origin_authority, attribution_timestamp
    fingerprint_context: Optional[Dict[str, Any]]
    idempotency_key: Optional[str]
    compliance_hold_flag: bool = False


@dataclass
class AcademicContext:
    """SQL Server-authoritative academic signals (directive §2.2 / AP-D11)."""
    user_id: Optional[int]              # never logged raw — use _opaque_id (AP-D10)
    access_state: Optional[str]         # ACTIVE | REVOKED | SUSPENDED
    hws_behind: Optional[int]
    avg_eff_rating: Optional[float]
    last_activity_days: Optional[int]
    payment_balance: Optional[float]
    sql_server_sync_timestamp: Optional[str] = None


@dataclass
class OperationalContext:
    """Platform-supplementary operational state (directive §2.1)."""
    outreach_state: Optional[str]
    contact_attempt_count: int
    retry_eligible: bool


@dataclass
class AIInputContext:
    """AI advisory inputs — advisory only, cannot override governance (directive §2.3 / §6.1)."""
    ai_insight_state: Optional[str]
    ai_confidence_score: Optional[float]
    ai_stale_flag: bool
    ai_finalized_copy: bool
    ai_recommended_intervention: Optional[str]


@dataclass
class HistoricalContext:
    """Longitudinal signals from finalized snapshots (directive §2.5)."""
    historical_risk_trend: Optional[str]   # IMPROVING | STABLE | DECLINING | CRITICAL
    prior_escalation_count: int = 0
    prior_snapshot_months: List[str] = field(default_factory=list)


@dataclass
class DecisionContext:
    """Full evaluation context aggregating all five input domains (directive §2)."""
    governance: GovernanceContext
    academic: AcademicContext
    operational: OperationalContext
    ai: AIInputContext
    historical: HistoricalContext


# ── Output models ─────────────────────────────────────────────────────────────

@dataclass
class EscalationMetadata:
    escalation_required: bool = False
    escalation_urgency: str = "LOW"
    escalation_reason_codes: List[str] = field(default_factory=list)
    escalation_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIOutputContext:
    ai_input_used: bool = False
    ai_governance_tier: str = AI_UNAVAILABLE
    ai_confidence_score: float = 0.0
    stale_flag: bool = False
    fallback_applied: bool = False


@dataclass
class ReplaySafetyMetadata:
    is_replay: bool = False
    source_artifact_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None
    fingerprint_comparison_outcome: Optional[str] = None
    replay_safe: bool = True


@dataclass
class OrchestrationIntent:
    """
    Governance-safe advisory intent (directive §3.1).

    Advisory only — never executes actions, never mutates state.
    Consuming services enforce governance boundaries and write audit records.
    AP-D1 through AP-D15 prohibit the engine from writing, dispatching,
    or mutating any state.
    """
    orchestration_intent: str
    intent_confidence: float
    recommended_execution_path: str
    execution_mode: str
    execution_type: str
    governance_scope: str               # AUTHORIZED | SHADOW_ONLY | REPLAY_ONLY | UNAVAILABLE
    correlation_id: Optional[str]
    causation_id: Optional[str]
    config_version_id: Optional[str]
    attribution_metadata: Dict[str, Any]
    rule_path_taken: List[str]
    decision_basis: str                 # RULE_BASED | AI_ASSISTED | FALLBACK | HISTORICAL_REPLAY
    escalation_metadata: EscalationMetadata
    replay_safety_metadata: ReplaySafetyMetadata
    ai_context: AIOutputContext
    reason_codes: List[str]
    intent_blocked: bool = False
    blocking_reason: Optional[str] = None


@dataclass
class GovernanceDecisionResult:
    """Engine output with evaluation telemetry (directive §8.1)."""
    intent: OrchestrationIntent
    evaluation_duration_ms: float
    risk_level: Optional[str]           # LOW | MEDIUM | HIGH | CRITICAL | None
    config_threshold_warnings: List[str]
    degradation_flags: List[str]
    student_id_opaque: Optional[str]    # hashed — never raw user_id (AP-D10)


# ── Public API ────────────────────────────────────────────────────────────────

def validate_governance_preconditions(gov: GovernanceContext) -> Optional[OrchestrationIntent]:
    """
    RULE 0 — GOVERNANCE PRECONDITION GATE (directive §4 RULE 0).

    Returns a blocked OrchestrationIntent if any precondition fails, else None.
    AP-D15: no rule evaluation may proceed if this returns a non-None value.
    """
    codes: List[str] = []
    if not gov.config_version_id:
        codes.append("CONFIG_UNRESOLVED")
    if gov.execution_mode not in _VALID_MODES:
        codes.append("EXECUTION_MODE_INVALID")
    if not gov.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
    if any(gov.attribution_context.get(k) is None for k in _REQUIRED_ATTRIBUTION):
        codes.append("ATTRIBUTION_INCOMPLETE")
    if gov.execution_type in ("replay", "regeneration") and not gov.fingerprint_context:
        codes.append("REPLAY_FINGERPRINT_MISSING")
    if not codes:
        return None
    return OrchestrationIntent(
        orchestration_intent=NO_ELIGIBLE_INTENT,
        intent_confidence=1.0,
        recommended_execution_path="",
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


def evaluate_orchestration_intent(ctx: DecisionContext) -> GovernanceDecisionResult:
    """
    Main decision evaluation implementing Rules 0–14 (directive §4).

    NEVER dispatches (AP-D2), NEVER writes to DB (AP-D1), NEVER mutates state (AP-D3).
    All threshold comparisons use config_rule_set values only (AP-D9).
    """
    t0 = time.monotonic()
    gov = ctx.governance
    path: List[str] = []
    sid = _opaque_id(ctx.academic.user_id)

    # RULE 0 (AP-D15)
    blocked = validate_governance_preconditions(gov)
    if blocked:
        _log(blocked, sid, _ms(t0), None)
        return GovernanceDecisionResult(blocked, _ms(t0), None, [], [], sid)
    path.append("RULE_0_PASS")

    # Replay/regeneration context → RULE 13
    if gov.execution_type in ("replay", "regeneration"):
        return evaluate_replay_intent(ctx)

    # RULE 3: Config-bound threshold extraction — no hardcoded fallback (AP-D9)
    thresholds, t_warnings = _extract_thresholds(gov.config_rule_set)
    path.append("RULE_3")

    # RULE 1: Terminal state check
    if ctx.operational.outreach_state in _TERMINAL_STATES:
        intent = _intent(ctx, NO_ELIGIBLE_INTENT, 1.0, "", path + ["RULE_1"],
                         ["OUTREACH_CLOSED_TERMINAL"], "RULE_BASED")
        _log(intent, sid, _ms(t0), None)
        return GovernanceDecisionResult(intent, _ms(t0), None, t_warnings, [], sid)
    path.append("RULE_1_PASS")

    # RULE 2: Compliance hold (directive §4 RULE 2 / INV-5)
    if gov.compliance_hold_flag:
        esc = EscalationMetadata(
            escalation_required=True, escalation_urgency="HIGH",
            escalation_reason_codes=["COMPLIANCE_HOLD_ACTIVE"],
            escalation_context={"note": "Automated orchestration suspended pending hold resolution."},
        )
        intent = _intent(ctx, ESCALATE_TO_OPERATOR, 1.0,
                         "escalation_routing_service.handle_compliance_hold",
                         path + ["RULE_2"], ["COMPLIANCE_HOLD_ACTIVE"], "RULE_BASED", esc=esc)
        _log(intent, sid, _ms(t0), None)
        return GovernanceDecisionResult(intent, _ms(t0), None, t_warnings, [], sid)
    path.append("RULE_2_PASS")

    # RULE 4: Access state gate — SQL Server-authoritative (AP-D11)
    access = ctx.academic.access_state
    if access == "REVOKED":
        esc = EscalationMetadata(
            escalation_required=True, escalation_urgency="HIGH",
            escalation_reason_codes=["ACCESS_REVOKED"],
        )
        intent = _intent(ctx, ESCALATE_TO_OPERATOR, 1.0,
                         "escalation_routing_service.handle_access_revoked",
                         path + ["RULE_4"],
                         ["ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE"], "RULE_BASED", esc=esc)
        _log(intent, sid, _ms(t0), None)
        return GovernanceDecisionResult(intent, _ms(t0), None, t_warnings, [], sid)
    if access == "SUSPENDED":
        intent = _intent(ctx, NO_ELIGIBLE_INTENT, 1.0, "", path + ["RULE_4"],
                         ["ACCESS_SUSPENDED_AWAIT_RESTORATION"], "RULE_BASED")
        _log(intent, sid, _ms(t0), None)
        return GovernanceDecisionResult(intent, _ms(t0), None, t_warnings, [], sid)
    path.append("RULE_4_PASS")

    # RULE 5: AI governance tier (non-terminal; advisory only — directive §6)
    ai_tier, ai_out = _assess_ai_tier(ctx.ai)
    path.append("RULE_5")

    # RULE 5A: Defer pending AI (original evaluations only)
    if ai_tier == AI_IN_FLIGHT and gov.execution_type == "original":
        intent = _intent(ctx, DEFER_PENDING_AI, 0.9, "scheduler.defer_pending_ai",
                         path + ["RULE_5A"], ["AI_INSIGHT_IN_FLIGHT"], "RULE_BASED", ai=ai_out)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), None, t_warnings, [], sid)

    # RULE 6: Max attempts exhaustion — config-bound ceiling only (AP-D9)
    max_att = thresholds.get(_K_MAX_ATTEMPTS, UNKNOWN_V0)
    if max_att != UNKNOWN_V0 and ctx.operational.contact_attempt_count >= max_att:
        esc = EscalationMetadata(
            escalation_required=True, escalation_urgency="MEDIUM",
            escalation_reason_codes=["MAX_ATTEMPTS_EXHAUSTED_REVIEW_REQUIRED"],
        )
        intent = _intent(ctx, CLOSE_ORCHESTRATION, 1.0, "outreach_service.exhaust_and_close",
                         path + ["RULE_6"], ["MAX_ATTEMPTS_EXHAUSTED"], "RULE_BASED", esc=esc)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), None, t_warnings, [], sid)
    path.append("RULE_6_PASS")

    # RULE 7: Multi-factor risk assessment (non-terminal)
    risk_level, _ = _compute_risk(ctx, thresholds, ai_tier)
    path.append("RULE_7")

    # RULE 8: Critical risk escalation
    if risk_level == "CRITICAL":
        esc = EscalationMetadata(
            escalation_required=True, escalation_urgency="CRITICAL",
            escalation_reason_codes=["CRITICAL_RISK_MULTI_FACTOR"],
        )
        basis = "AI_ASSISTED" if ai_out.ai_input_used else "RULE_BASED"
        intent = _intent(ctx, ESCALATE_TO_OPERATOR, 0.95,
                         "escalation_routing_service.handle_critical",
                         path + ["RULE_8"], ["CRITICAL_RISK_ESCALATION"], basis, esc=esc, ai=ai_out)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), risk_level, t_warnings, [], sid)

    # RULE 9: High risk — SHADOW/LIVE bifurcation
    if risk_level == "HIGH":
        code = ("HIGH_RISK_SHADOW_NO_DISPATCH" if gov.execution_mode == "SHADOW"
                else "HIGH_RISK_ESCALATION_LIVE")
        esc = EscalationMetadata(
            escalation_required=True, escalation_urgency="HIGH",
            escalation_reason_codes=[code],
        )
        intent = _intent(ctx, ESCALATE_TO_OPERATOR, 0.85,
                         "escalation_routing_service.handle_high_risk",
                         path + ["RULE_9"], [code], "RULE_BASED", esc=esc, ai=ai_out)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), risk_level, t_warnings, [], sid)

    # RULE 10: AI-assisted intervention recommendation (CONTINUE — may combine with Rule 11)
    r10_intent: Optional[str] = None
    r10_codes: List[str] = []
    if ai_tier in (AI_CONFIDENT, AI_ADVISORY):
        if ctx.ai.ai_recommended_intervention in ("MEETING", "RESOURCE_DELIVERY", "IPBC_FOLLOWUP"):
            r10_intent = RECOMMEND_INTERVENTION
            r10_codes = ["AI_ASSISTED_INTERVENTION_RECOMMENDED"]
            ai_out.ai_input_used = True
            path.append("RULE_10")

    # RULE 11: Retry eligibility advisory
    if (ctx.operational.contact_attempt_count > 0
            and max_att != UNKNOWN_V0
            and ctx.operational.contact_attempt_count < max_att
            and ctx.operational.retry_eligible):
        path.append("RULE_11")
        basis = "AI_ASSISTED" if r10_intent else "RULE_BASED"
        intent = _intent(ctx, RETRY_OUTREACH, 0.9, "outreach_service.schedule_retry",
                         path, r10_codes + ["RETRY_ELIGIBLE_WINDOW_PASSED"], basis, ai=ai_out)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), risk_level, t_warnings, [], sid)

    # Rule 10 CONTINUE — return recommendation if Rule 11 did not fire
    if r10_intent:
        intent = _intent(ctx, r10_intent, 0.75,
                         "operator_notification_service.deliver_ai_recommendation",
                         path, r10_codes, "AI_ASSISTED", ai=ai_out)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), risk_level, t_warnings, [], sid)

    # RULE 12: First outreach eligibility
    if (ctx.operational.contact_attempt_count == 0
            and ctx.operational.outreach_state in ("ELIGIBLE", "QUEUED", None)):
        path.append("RULE_12")
        intent = _intent(ctx, INITIATE_OUTREACH, 0.9,
                         "outreach_service.initiate_first_contact",
                         path, ["FIRST_OUTREACH_ELIGIBLE"], "RULE_BASED", ai=ai_out)
        _log(intent, sid, _ms(t0), ai_tier)
        return GovernanceDecisionResult(intent, _ms(t0), risk_level, t_warnings, [], sid)

    # RULE 14: Default fallback
    path.append("RULE_14")
    intent = _intent(ctx, NO_ELIGIBLE_INTENT, 1.0, "", path,
                     ["NO_ELIGIBLE_ACTION_THIS_CYCLE"], "RULE_BASED", ai=ai_out)
    _log(intent, sid, _ms(t0), ai_tier)
    return GovernanceDecisionResult(intent, _ms(t0), risk_level, t_warnings, [], sid)


def evaluate_replay_intent(ctx: DecisionContext) -> GovernanceDecisionResult:
    """
    RULE 13 — Replay/regeneration governance (directive §4 RULE 13, §7).

    Forces execution_mode = SHADOW unconditionally (AP-D8).
    All outputs carry governance_scope = REPLAY_ONLY (INV-4, AP-RT2).
    Uses historical config — never current ACTIVE (FAD-3, directive §5.4).
    """
    t0 = time.monotonic()
    gov = ctx.governance
    sid = _opaque_id(ctx.academic.user_id)
    violations: List[str] = []

    if gov.execution_mode == "LIVE":
        violations.append("REPLAY_LIVE_MODE_BLOCKED")
    if not gov.fingerprint_context:
        violations.append("REPLAY_FINGERPRINT_MISSING")

    replay_meta = ReplaySafetyMetadata(
        is_replay=True,
        historical_config_version_id=gov.config_version_id,
        fingerprint_comparison_outcome=_compare_fingerprints(gov.fingerprint_context),
        replay_safe=not bool(violations),
    )
    intent = OrchestrationIntent(
        orchestration_intent=NO_ELIGIBLE_INTENT,
        intent_confidence=1.0,
        recommended_execution_path="",
        execution_mode="SHADOW",         # unconditionally forced — AP-D8
        execution_type=gov.execution_type,
        governance_scope="REPLAY_ONLY",
        correlation_id=gov.correlation_id,
        causation_id=gov.causation_id,
        config_version_id=gov.config_version_id,
        attribution_metadata=gov.attribution_context,
        rule_path_taken=["RULE_0_PASS", "RULE_13"],
        decision_basis="HISTORICAL_REPLAY",
        escalation_metadata=EscalationMetadata(),
        replay_safety_metadata=replay_meta,
        ai_context=AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY),
        reason_codes=violations or ["REPLAY_EVALUATION_COMPLETE"],
        intent_blocked=bool(violations),
        blocking_reason="REPLAY_PRECONDITION_VIOLATED" if violations else None,
    )
    _log(intent, sid, _ms(t0), AI_FINALIZED_COPY)
    return GovernanceDecisionResult(intent, _ms(t0), None, [], [], sid)


def evaluate_shadow_intent(ctx: DecisionContext) -> GovernanceDecisionResult:
    """
    Enforce SHADOW mode then delegate to main evaluation (directive §7.4).

    SHADOW evaluation runs all rules normally. The execution_mode=SHADOW field
    in the emitted intent signals consuming services to suppress outbound dispatch.
    The engine does not enforce SHADOW itself — it carries the mode flag (AP-D2).
    """
    if ctx.governance.execution_mode != "SHADOW":
        ctx = DecisionContext(
            governance=replace(ctx.governance, execution_mode="SHADOW"),
            academic=ctx.academic,
            operational=ctx.operational,
            ai=ctx.ai,
            historical=ctx.historical,
        )
    return evaluate_orchestration_intent(ctx)


# ── Private helpers ───────────────────────────────────────────────────────────

def _extract_thresholds(rule_set: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """RULE 3 / INV-7: Substitute UNKNOWN_V0 for every absent threshold key."""
    thresholds: Dict[str, Any] = {}
    warnings: List[str] = []
    for k in _THRESHOLD_KEYS:
        v = rule_set.get(k)
        thresholds[k] = v if v is not None else UNKNOWN_V0
        if thresholds[k] == UNKNOWN_V0:
            warnings.append(f"CONFIG_THRESHOLD_MISSING_{k}")
    return thresholds, warnings


def _assess_ai_tier(ai: AIInputContext) -> Tuple[str, AIOutputContext]:
    """RULE 5: Derive AI governance tier — advisory only (directive §6.2)."""
    if ai.ai_finalized_copy:
        return AI_FINALIZED_COPY, AIOutputContext(ai_governance_tier=AI_FINALIZED_COPY)
    s = ai.ai_insight_state
    if s in ("AI_GENERATING", "AI_PENDING"):
        return AI_IN_FLIGHT, AIOutputContext(ai_governance_tier=AI_IN_FLIGHT)
    if s is None or s == "AI_GENERATION_FAILED":
        return AI_UNAVAILABLE, AIOutputContext(ai_governance_tier=AI_UNAVAILABLE, fallback_applied=True)
    if s == "AI_REVIEWED":
        if ai.ai_stale_flag:
            return AI_STALE, AIOutputContext(ai_governance_tier=AI_STALE, stale_flag=True)
        score = ai.ai_confidence_score or 0.0
        tier = AI_CONFIDENT if score >= 0.70 else AI_ADVISORY
        return tier, AIOutputContext(ai_governance_tier=tier, ai_confidence_score=score)
    return AI_UNAVAILABLE, AIOutputContext(ai_governance_tier=AI_UNAVAILABLE, fallback_applied=True)


def _compute_risk(
    ctx: DecisionContext,
    thresholds: Dict[str, Any],
    ai_tier: str,
) -> Tuple[str, List[str]]:
    """RULE 7: Multi-factor risk scoring — config-bound; AI contribution advisory only."""
    high: List[str] = []
    med: List[str] = []

    def _t(k: str) -> Any:
        v = thresholds.get(k, UNKNOWN_V0)
        return None if v == UNKNOWN_V0 else v

    hws, ht = ctx.academic.hws_behind, _t(_K_HWS_RISK)
    if hws is not None and ht is not None and hws >= ht:
        high.append("HWS_DELINQUENCY")

    eff, et = ctx.academic.avg_eff_rating, _t(_K_EFF_RISK)
    if eff is not None and et is not None and eff < et:
        med.append("EFFORT_DECLINE")

    inact, it = ctx.academic.last_activity_days, _t(_K_INACTIVITY_RISK)
    if inact is not None and it is not None and inact > it:
        high.append("INACTIVITY")

    pay, pt = ctx.academic.payment_balance, _t(_K_PAYMENT_RISK)
    if pay is not None and pt is not None and pay > pt:
        med.append("PAYMENT_RISK")

    ec, et2 = ctx.historical.prior_escalation_count, _t(_K_ESCALATION_REPEAT)
    if et2 is not None and ec >= et2:
        high.append("ESCALATION_RECURRENCE")

    trend = ctx.historical.historical_risk_trend
    if trend == "CRITICAL":
        high.append("HISTORICAL_TREND_CRITICAL")
    elif trend == "DECLINING":
        med.append("HISTORICAL_TREND_DECLINING")

    # AI risk contribution — advisory only (AP-D12: STALE cannot elevate in LIVE)
    intv = ctx.ai.ai_recommended_intervention
    if ai_tier == AI_CONFIDENT and intv == "ESCALATE":
        high.append("AI_CONFIDENT_ESCALATE_SIGNAL")
    elif ai_tier == AI_ADVISORY and intv == "ESCALATE":
        med.append("AI_ADVISORY_ESCALATE_SIGNAL")

    factors = high + med
    if len(high) >= 2:
        return "CRITICAL", factors
    if high and med:
        return "HIGH", factors
    if high or med:
        return "MEDIUM", factors
    return "LOW", factors


def _compare_fingerprints(ctx: Optional[Dict[str, Any]]) -> str:
    if not ctx:
        return "UNKNOWN"
    keys = ("fingerprint_schema_version", "fingerprint_config_registry_version",
            "fingerprint_ai_prompt_version", "fingerprint_ai_model_version")
    return "UNKNOWN" if any(ctx.get(k) in (None, UNKNOWN_V0) for k in keys) else "MATCH"


def _opaque_id(user_id: Optional[int]) -> Optional[str]:
    """Hash raw user_id for log output — NEVER log the actual value (AP-D10)."""
    if user_id is None:
        return None
    return hashlib.sha256(f"ssip:uid:{user_id}".encode()).hexdigest()[:16]


def _governance_scope(execution_mode: str, execution_type: str) -> str:
    if execution_type in ("replay", "regeneration"):
        return "REPLAY_ONLY"
    return "SHADOW_ONLY" if execution_mode == "SHADOW" else "AUTHORIZED"


def _ms(t0: float) -> float:
    return (time.monotonic() - t0) * 1000.0


def _intent(
    ctx: DecisionContext,
    intent_type: str,
    confidence: float,
    exec_path: str,
    rule_path: List[str],
    reason_codes: List[str],
    basis: str,
    esc: Optional[EscalationMetadata] = None,
    ai: Optional[AIOutputContext] = None,
) -> OrchestrationIntent:
    gov = ctx.governance
    return OrchestrationIntent(
        orchestration_intent=intent_type,
        intent_confidence=confidence,
        recommended_execution_path=exec_path,
        execution_mode=gov.execution_mode,
        execution_type=gov.execution_type,
        governance_scope=_governance_scope(gov.execution_mode, gov.execution_type),
        correlation_id=gov.correlation_id,
        causation_id=gov.causation_id,
        config_version_id=gov.config_version_id,
        attribution_metadata=dict(gov.attribution_context),
        rule_path_taken=list(rule_path),
        decision_basis=basis,
        escalation_metadata=esc or EscalationMetadata(),
        replay_safety_metadata=ReplaySafetyMetadata(),
        ai_context=ai or AIOutputContext(),
        reason_codes=list(reason_codes),
    )


def _log(
    intent: OrchestrationIntent,
    student_id_opaque: Optional[str],
    duration_ms: float,
    ai_tier: Optional[str],
) -> None:
    """Structured log per directive §8.1 — no raw PII emitted (AP-D10)."""
    outcome = (
        "blocked" if intent.intent_blocked
        else "shadow_only" if intent.execution_mode == "SHADOW"
        else "success"
    )
    record: Dict[str, Any] = {
        "service": "decision_engine",
        "event": ("governance_precondition_failed" if intent.intent_blocked
                  else "orchestration_intent_produced"),
        "correlation_id": intent.correlation_id,
        "causation_id": intent.causation_id,
        "student_id_opaque": student_id_opaque,   # AP-D10: never raw user_id
        "execution_type": intent.execution_type,
        "execution_mode": intent.execution_mode,
        "config_version_id": intent.config_version_id,
        "orchestration_intent": intent.orchestration_intent,
        "governance_scope": intent.governance_scope,
        "ai_governance_tier": ai_tier,
        "rule_path_taken": intent.rule_path_taken,
        "decision_basis": intent.decision_basis,
        "duration_ms": round(duration_ms, 2),
        "outcome": outcome,
    }
    if intent.intent_blocked:
        record["error_class"] = "GovernancePreconditionFailed"
        record["blocking_reason"] = intent.blocking_reason
    (logger.error if intent.intent_blocked else logger.info)(record)


# ── Simple batch-preview decision API (not governance intent) ──────────────────

def decide(
    student: Dict[str, Any],
    tracking: Optional[Dict[str, Any]],
    eligibility: Any,
) -> str:
    """
    Map student/tracking/eligibility to a batch-preview decision string.
    For display use only — not an orchestration intent.
    Returns one of: TRIGGER_OUTREACH, RETRY_OUTREACH, ESCALATE, CLOSE, NO_ACTION.
    """
    if not getattr(eligibility, "eligible", False):
        return "NO_ACTION"
    if tracking is None:
        return "TRIGGER_OUTREACH"
    state = tracking.get("state", "")
    if state in ("CLOSED", "RESOLVED"):
        return "CLOSE"
    if state == "INTERVENTION_REQUIRED":
        return "ESCALATE"
    if state in ("NO_RESPONSE", "RETRY"):
        return "RETRY_OUTREACH"
    if state in ("ELIGIBLE", "QUEUED", "CONTACTED"):
        return "TRIGGER_OUTREACH"
    return "NO_ACTION"
