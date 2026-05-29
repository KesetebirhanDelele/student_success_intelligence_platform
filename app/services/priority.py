"""
Governance-safe orchestration prioritization advisory service.

Public API: assess_orchestration_priority(ctx) -> PrioritizationRecord

Advisory contract only — never creates eligibility, never dispatches outreach,
never escalates directly, never mutates orchestration state, never overrides
governance rules. Returns PrioritizationRecord. Consuming services act on the
returned record. Attribution propagated immutably from input.

Architecture preservation prohibitions (MUST NOT):
  AP-D1   / AP-E2   — no direct database writes or state mutation
  AP-D8             — no LIVE priority effects from replay/regeneration
  AP-D9   / AP-E9   — no hardcoded scoring threshold constants; UNKNOWN_V0 only
  AP-D10  / AP-E7   — no raw PII in observability; every path emits telemetry
  AP-D12            — no AI-only LIVE advisory when AI tier is STALE/UNAVAILABLE
  AP-D13  / AP-E15  — no attribution field overwriting across evaluation paths
  AP-D14            — no idempotency key reuse across cycles
  AP-D15            — no evaluation if RULE 0 has not passed
  AP-E1             — no direct outreach execution
  AP-E5             — no overwriting of historical scoring lineage (append-only)
  AP-E6             — no replay scope producing LIVE orchestration candidacy
  FAD-4             — no mutation of append-only scoring lineage
  IML-1             — no mutation of immutable historical scoring records
  IML-3             — no overwrite of replay scoring lineage; LIVE/REPLAY distinguishable
  INV-4 / AP-RT2    — no LIVE scoring effects from replay execution
  INV-5             — no governance record without correlation_id and attribution
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services._priority_helpers import (
    _make_blocked_priority_record,
    _make_maintenance_priority_record,
    _make_priority_record,
    _make_replay_priority_record,
    emit_priority_event_log,
)
from app.services._priority_types import (
    AI_RECOMMEND_ESCALATE,
    AI_REVIEWED,
    BASIS_AI_ASSISTED,
    BASIS_FALLBACK,
    BASIS_RULE_BASED,
    K_AI_INSIGHT_TTL_HOURS,
    K_AVG_EFF_RATING,
    K_ESCALATION_REPEAT,
    K_HWS_BEHIND_HIGH_RISK,
    K_HWS_BEHIND_MODERATE,
    K_INACTIVITY_HIGH_RISK,
    K_INACTIVITY_MODERATE,
    K_PAYMENT_RISK,
    MODE_SHADOW,
    OUTCOME_DEFERRED,
    OUTCOME_SHADOW_ONLY,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_UNKNOWN,
    REQUIRED_PRIORITY_ATTRIBUTION,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    SCOPE_SHADOW_ONLY,
    TIER_ADVISORY,
    TIER_CONFIDENT,
    TIER_FINALIZED_COPY,
    TIER_IN_FLIGHT,
    TIER_STALE,
    TIER_UNAVAILABLE,
    TREND_CRITICAL,
    TREND_DECLINING,
    TYPE_ORIGINAL,
    UNKNOWN_V0,
    _AI_IN_FLIGHT_STATES,
    _AI_UNAVAILABLE_STATES,
    _AI_UPWARD_RECOMMENDATIONS,
    _PRIORITY_LEVELS,
    _PRIORITY_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    PrioritizationContext,
    PrioritizationRecord,
)

logger = logging.getLogger(__name__)

# In-memory idempotency store for prioritization deduplication (AP-D14, spec/04 §4.1)
_priority_idempotency_keys: set[str] = set()


# ── Pure helpers ───────────────────────────────────────────────────────────────

def _attribution_complete(ctx: PrioritizationContext) -> bool:
    return all(getattr(ctx, f, None) for f in REQUIRED_PRIORITY_ATTRIBUTION)


def _governance_precondition_gate(
    ctx: PrioritizationContext,
    codes: List[str],
) -> bool:
    """
    RULE 0: Governance precondition gate. All conditions must pass before any
    evaluation proceeds. Never bypassed (INV-5, AP-D15, spec/04 §4.1).
    Returns True if all preconditions pass; False if assessment must stop.
    """
    ok = True
    if ctx.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append("INVALID_EXECUTION_MODE")
        ok = False
    if ctx.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append("INVALID_EXECUTION_TYPE")
        ok = False
    if not ctx.config_version_id:
        codes.append("CONFIG_VERSION_ID_MISSING")
        ok = False
    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
        ok = False
    if not ctx.origin_source:
        codes.append("ORIGIN_SOURCE_MISSING")
        ok = False
    if not ctx.origin_authority:
        codes.append("ORIGIN_AUTHORITY_MISSING")
        ok = False
    if not ctx.actor_identity:
        codes.append("ACTOR_IDENTITY_MISSING")
        ok = False
    if ctx.idempotency_key and ctx.idempotency_key in _priority_idempotency_keys:
        codes.append("IDEMPOTENCY_DUPLICATE_DETECTED")
        ok = False
    return ok


def _resolve_priority_thresholds(
    rule_set: Dict[str, Any],
    missing_keys: List[str],
) -> Dict[str, Any]:
    """
    Resolve Config V2 scoring thresholds from rule_set.
    Missing or UNKNOWN_V0 inputs resolve to UNKNOWN_V0 sentinel — never hardcoded (AP-D9).
    """
    result: Dict[str, Any] = {}
    for k in _PRIORITY_THRESHOLD_KEYS:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def _classify_ai_tier(
    ctx: PrioritizationContext,
    thresholds: Dict[str, Any],
) -> str:
    """
    Classify AI governance tier from context.
    FINALIZED_COPY check fires first (immutable content — FAD-1, spec/03 §27).
    Returns one of the 6 defined tiers.
    """
    if ctx.ai_finalized_copy:
        return TIER_FINALIZED_COPY
    if ctx.ai_insight_state in _AI_IN_FLIGHT_STATES:
        return TIER_IN_FLIGHT
    if ctx.ai_insight_state in _AI_UNAVAILABLE_STATES or not ctx.ai_insight_state:
        return TIER_UNAVAILABLE
    if ctx.ai_insight_state == AI_REVIEWED:
        # Staleness check: explicit flag takes precedence
        if ctx.ai_stale_flag is True:
            return TIER_STALE
        if ctx.ai_stale_flag is False:
            confidence = ctx.ai_confidence_score
            if confidence is None:
                return TIER_ADVISORY
            return TIER_CONFIDENT if confidence >= 0.70 else TIER_ADVISORY
        # ai_stale_flag is None — can't determine without TTL config
        if thresholds.get(K_AI_INSIGHT_TTL_HOURS) == UNKNOWN_V0:
            return TIER_UNAVAILABLE  # staleness indeterminate without TTL (UD-2)
        # TTL is available but caller didn't set ai_stale_flag — treat as not stale
        confidence = ctx.ai_confidence_score
        if confidence is None:
            return TIER_ADVISORY
        return TIER_CONFIDENT if confidence >= 0.70 else TIER_ADVISORY
    return TIER_UNAVAILABLE


def _score_risk_factors(
    ctx: PrioritizationContext,
    thresholds: Dict[str, Any],
    ai_tier: str,
    codes: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    RULE 6: Multi-factor risk scoring. Produces advisory scoring factors and
    risk contributions. Never hardcodes thresholds — UNKNOWN_V0 skips that factor.
    AI signals are advisory only (AP-D12); they cannot override rule-based scoring.
    """
    factors: List[Dict[str, Any]] = []
    contributions: List[str] = []

    def add(factor: str, contribution: str, key: str, value: Any) -> None:
        factors.append({"factor": factor, "contribution": contribution,
                        "threshold_key": key, "value": value})
        contributions.append(contribution)

    # HWs behind (SQL Server-authoritative — INVARIANT-6)
    if ctx.hws_behind is not None:
        hw_high = thresholds.get(K_HWS_BEHIND_HIGH_RISK)
        hw_mod  = thresholds.get(K_HWS_BEHIND_MODERATE)
        if hw_high != UNKNOWN_V0 and isinstance(hw_high, (int, float)) and ctx.hws_behind >= hw_high:
            add("hws_behind", RISK_HIGH, K_HWS_BEHIND_HIGH_RISK, ctx.hws_behind)
            codes.append("HWS_BEHIND_HIGH_RISK")
        elif hw_mod != UNKNOWN_V0 and isinstance(hw_mod, (int, float)) and ctx.hws_behind >= hw_mod:
            add("hws_behind", RISK_MEDIUM, K_HWS_BEHIND_MODERATE, ctx.hws_behind)
            codes.append("HWS_BEHIND_MODERATE_RISK")

    # Avg effort rating (SQL Server-authoritative)
    if ctx.avg_eff_rating is not None:
        eff_thresh = thresholds.get(K_AVG_EFF_RATING)
        if eff_thresh != UNKNOWN_V0 and isinstance(eff_thresh, (int, float)) and ctx.avg_eff_rating < eff_thresh:
            add("avg_eff_rating", RISK_MEDIUM, K_AVG_EFF_RATING, ctx.avg_eff_rating)
            codes.append("EFF_RATING_MEDIUM_RISK")

    # Inactivity (SQL Server-authoritative)
    if ctx.last_activity_days is not None:
        inact_high = thresholds.get(K_INACTIVITY_HIGH_RISK)
        inact_mod  = thresholds.get(K_INACTIVITY_MODERATE)
        if inact_high != UNKNOWN_V0 and isinstance(inact_high, (int, float)) and ctx.last_activity_days > inact_high:
            add("last_activity_days", RISK_HIGH, K_INACTIVITY_HIGH_RISK, ctx.last_activity_days)
            codes.append("INACTIVITY_HIGH_RISK")
        elif inact_mod != UNKNOWN_V0 and isinstance(inact_mod, (int, float)) and ctx.last_activity_days > inact_mod:
            add("last_activity_days", RISK_MEDIUM, K_INACTIVITY_MODERATE, ctx.last_activity_days)
            codes.append("INACTIVITY_MODERATE_RISK")

    # Payment balance (SQL Server-authoritative)
    if ctx.payment_balance is not None:
        pay_thresh = thresholds.get(K_PAYMENT_RISK)
        if pay_thresh != UNKNOWN_V0 and isinstance(pay_thresh, (int, float)) and ctx.payment_balance > pay_thresh:
            add("payment_balance", RISK_MEDIUM, K_PAYMENT_RISK, ctx.payment_balance)
            codes.append("PAYMENT_BALANCE_MEDIUM_RISK")

    # Historical escalation recurrence (platform_supplementary)
    if ctx.prior_escalation_count is not None:
        esc_thresh = thresholds.get(K_ESCALATION_REPEAT)
        if esc_thresh != UNKNOWN_V0 and isinstance(esc_thresh, (int, float)) and ctx.prior_escalation_count >= esc_thresh:
            add("prior_escalation_count", RISK_HIGH, K_ESCALATION_REPEAT, ctx.prior_escalation_count)
            codes.append("ESCALATION_RECURRENCE_HIGH_RISK")

    # Historical risk trend (platform_supplementary)
    if ctx.historical_risk_trend == TREND_CRITICAL:
        add("historical_risk_trend", RISK_HIGH, "historical_risk_trend", ctx.historical_risk_trend)
        codes.append("HISTORICAL_TREND_CRITICAL")
    elif ctx.historical_risk_trend == TREND_DECLINING:
        add("historical_risk_trend", RISK_MEDIUM, "historical_risk_trend", ctx.historical_risk_trend)
        codes.append("HISTORICAL_TREND_DECLINING")

    # Access transition recency — LOW signal (platform_supplementary)
    if ctx.access_last_changed_days is not None and ctx.access_last_changed_days <= 7:
        add("access_last_changed_days", RISK_LOW, "access_last_changed_days", ctx.access_last_changed_days)
        codes.append("ACCESS_TRANSITION_RECENT")

    # AI risk signals — advisory only; cannot grant eligibility (AP-D12, AP-E1)
    ai_rec = ctx.ai_recommended_intervention
    if ai_tier == TIER_CONFIDENT and ai_rec == AI_RECOMMEND_ESCALATE:
        add("ai_escalation_signal", RISK_HIGH, "ai_recommended_intervention", ai_rec)
        codes.append("AI_ESCALATION_SIGNAL_CONFIDENT")
    elif ai_tier == TIER_ADVISORY and ai_rec == AI_RECOMMEND_ESCALATE:
        add("ai_escalation_signal", RISK_MEDIUM, "ai_recommended_intervention", ai_rec)
        codes.append("AI_ESCALATION_SIGNAL_ADVISORY")
    elif ai_tier == TIER_STALE and ai_rec == AI_RECOMMEND_ESCALATE:
        add("ai_escalation_signal_stale", RISK_LOW, "ai_recommended_intervention", ai_rec)
        codes.append("AI_ESCALATION_SIGNAL_STALE_LOW")

    return factors, contributions


def _aggregate_priority(contributions: List[str]) -> str:
    """Aggregate risk contributions into an advisory priority tier."""
    high = contributions.count(RISK_HIGH)
    med  = contributions.count(RISK_MEDIUM)
    if high >= 2:
        return PRIORITY_CRITICAL
    if high >= 1 and med >= 1:
        return PRIORITY_HIGH
    if high >= 1:
        return PRIORITY_MEDIUM   # single HIGH factor without MEDIUM support
    if med >= 1:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW          # all LOW or no contributions


def _apply_ai_adjustment(
    priority: str,
    ai_tier: str,
    ai_intervention: Optional[str],
    codes: List[str],
) -> Tuple[str, bool]:
    """
    RULE 8: Apply AI advisory priority adjustment.
    AI is advisory only — cannot override governance invariants (AP-D12, AP-E1).
    STALE AI: no adjustment. UNAVAILABLE: fallback noted, no adjustment.
    FINALIZED_COPY: immutable, no adjustment.
    Returns (adjusted_priority, adjustment_applied).
    """
    levels = list(_PRIORITY_LEVELS)   # [CRITICAL, HIGH, MEDIUM, LOW]

    if ai_tier == TIER_CONFIDENT:
        if ai_intervention == AI_RECOMMEND_ESCALATE:
            codes.append("AI_CONFIDENT_ESCALATE_TO_CRITICAL")
            return PRIORITY_CRITICAL, True
        if ai_intervention in _AI_UPWARD_RECOMMENDATIONS:
            if priority in levels:
                idx = levels.index(priority)
                if idx > 0:
                    new_priority = levels[idx - 1]
                    codes.append("AI_CONFIDENT_PRIORITY_UPGRADED")
                    return new_priority, True

    elif ai_tier == TIER_ADVISORY:
        if ai_intervention == AI_RECOMMEND_ESCALATE:
            # +1 level (not directly to CRITICAL unless already HIGH)
            if priority in levels:
                idx = levels.index(priority)
                if idx > 0:
                    new_priority = levels[idx - 1]
                    codes.append("AI_ADVISORY_PRIORITY_UPGRADED")
                    return new_priority, True

    elif ai_tier == TIER_STALE:
        codes.append("STALE_AI_PRIORITIZATION_SKIPPED")
    elif ai_tier == TIER_UNAVAILABLE:
        codes.append("AI_UNAVAILABLE_FALLBACK_APPLIED")
    elif ai_tier == TIER_FINALIZED_COPY:
        codes.append("AI_FINALIZED_COPY_NOT_APPLIED")

    return priority, False


# ── Public advisory API ────────────────────────────────────────────────────────

def assess_orchestration_priority(
    ctx: PrioritizationContext,
) -> PrioritizationRecord:
    """
    Evaluate governance-safe orchestration prioritization advisory for one context.

    Advisory contract: returns PrioritizationRecord only.
    Never creates eligibility, never dispatches outreach, never mutates state.
    Every path emits a structured observability record (AP-E7).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    degradation_flags: List[str] = []
    rule_set = ctx.config_rule_set or {}

    # ── RULE 0: Governance precondition gate (INV-5, AP-D15, spec/04 §4.1) ────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        record = _make_blocked_priority_record(
            ctx, codes, rule_path, t0,
            gate_codes[0] if gate_codes else "GOVERNANCE_PRECONDITION_FAILED",
        )
        emit_priority_event_log(record)
        return record

    # Register idempotency key for original execution only (AP-D14)
    if ctx.idempotency_key and ctx.execution_type == TYPE_ORIGINAL:
        _priority_idempotency_keys.add(ctx.idempotency_key)

    # ── RULE 1: Maintenance mode suspension ──────────────────────────────────
    rule_path.append("RULE_1")
    if ctx.maintenance_mode_active:
        codes.append("MAINTENANCE_MODE_ACTIVE")
        record = _make_maintenance_priority_record(ctx, codes, rule_path, t0)
        emit_priority_event_log(record)
        return record

    # ── RULE 2: Replay/regeneration containment (INV-4, AP-D8, AP-E6) ───────
    rule_path.append("RULE_2")
    is_replay = ctx.execution_type in _REPLAY_TYPES
    if is_replay:
        codes.append("REPLAY_MODE_ACTIVE")
        if not ctx.source_artifact_id:
            codes.append("REPLAY_SOURCE_ARTIFACT_MISSING")
        record = _make_replay_priority_record(ctx, codes, rule_path, t0, {})
        emit_priority_event_log(record)
        return record

    # ── RULE 3: Config V2 threshold resolution (AP-D9, AP-E9, spec/01 §12) ──
    rule_path.append("RULE_3")
    missing_threshold_keys: List[str] = []
    threshold_bindings = _resolve_priority_thresholds(rule_set, missing_threshold_keys)
    for k in missing_threshold_keys:
        flag = f"CONFIG_THRESHOLD_MISSING_{k.upper()}"
        codes.append(flag)
        degradation_flags.append(flag)

    # ── RULE 4: Shadow mode detection ────────────────────────────────────────
    rule_path.append("RULE_4")
    shadow_mode = ctx.execution_mode == MODE_SHADOW  # noqa: F841

    # ── RULE 5: AI governance tier classification (directives/core_decision_engine §6) ──
    rule_path.append("RULE_5")
    ai_tier = _classify_ai_tier(ctx, threshold_bindings)
    codes.append(f"AI_TIER_{ai_tier}")

    # RULE 5A: AI IN_FLIGHT advisory deferral (original execution only)
    if ai_tier == TIER_IN_FLIGHT and ctx.execution_type == TYPE_ORIGINAL:
        rule_path.append("RULE_5A")
        codes.append("AI_INSIGHT_IN_FLIGHT_DEFER")
        record = _make_priority_record(
            ctx=ctx,
            codes=codes,
            rule_path=rule_path,
            t0=t0,
            threshold_bindings=threshold_bindings,
            advisory_priority=PRIORITY_UNKNOWN,
            governance_scope=SCOPE_SHADOW_ONLY,
            assessment_basis=BASIS_RULE_BASED,
            scoring_factors=[],
            risk_contributions=[],
            ai_governance_tier=ai_tier,
            ai_priority_adjustment_applied=False,
            ai_fallback_applied=False,
            degraded=False,
            degradation_flags=[],
            degradation_cause=None,
            outcome=OUTCOME_DEFERRED,
            scoring_emit_authorized=False,
        )
        emit_priority_event_log(record)
        return record

    # ── RULE 6: Multi-factor risk scoring (advisory — AP-D12) ────────────────
    rule_path.append("RULE_6")
    scoring_factors, risk_contributions = _score_risk_factors(
        ctx, threshold_bindings, ai_tier, codes,
    )

    # ── RULE 7: Priority tier classification from contributions ───────────────
    rule_path.append("RULE_7")
    base_priority = _aggregate_priority(risk_contributions)
    codes.append(f"BASE_PRIORITY_{base_priority}")

    # ── RULE 8: AI advisory priority adjustment (AP-D12, AP-E1) ──────────────
    rule_path.append("RULE_8")
    ai_fallback_applied = ai_tier == TIER_UNAVAILABLE
    advisory_priority, ai_adjustment_applied = _apply_ai_adjustment(
        base_priority, ai_tier, ctx.ai_recommended_intervention, codes
    )

    # Assessment basis: AI_ASSISTED > FALLBACK > RULE_BASED
    if ai_adjustment_applied:
        assessment_basis = BASIS_AI_ASSISTED
    elif ai_fallback_applied:
        assessment_basis = BASIS_FALLBACK
    else:
        assessment_basis = BASIS_RULE_BASED

    # ── RULE 9: Scope assignment (Phase-12 cert gate) ─────────────────────────
    # Current deployment: both LIVE and SHADOW produce SHADOW_ONLY.
    rule_path.append("RULE_9")
    if ctx.execution_mode == MODE_SHADOW:
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY
    else:
        # LIVE mode: Phase-12 cert not yet granted — advisory scope only
        codes.append("LIVE_SCOPE_SHADOW_ONLY_PHASE11")
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY

    # ── RULE 10: Advisory emit authorization + terminal output ─────────────────
    rule_path.append("RULE_10")
    scoring_emit_authorized = False   # Phase-12 cert required for True; see RULE 9

    degraded = bool(degradation_flags)
    degradation_cause = degradation_flags[0] if degraded else None

    record = _make_priority_record(
        ctx=ctx,
        codes=codes,
        rule_path=rule_path,
        t0=t0,
        threshold_bindings=threshold_bindings,
        advisory_priority=advisory_priority,
        governance_scope=governance_scope,
        assessment_basis=assessment_basis,
        scoring_factors=scoring_factors,
        risk_contributions=risk_contributions,
        ai_governance_tier=ai_tier,
        ai_priority_adjustment_applied=ai_adjustment_applied,
        ai_fallback_applied=ai_fallback_applied,
        degraded=degraded,
        degradation_flags=degradation_flags,
        degradation_cause=degradation_cause,
        outcome=outcome,
        scoring_emit_authorized=scoring_emit_authorized,
    )
    emit_priority_event_log(record)
    return record


# ── Simple display / batch-scoring API (not governance assessment) ─────────────

class StudentPriorityScore:
    """Lightweight scoring result for display and queue sorting. Not a governance record."""
    __slots__ = ("level", "score", "recommended_action", "reason_codes")

    def __init__(
        self,
        level: str,
        score: float,
        recommended_action: str,
        reason_codes: List[str],
    ) -> None:
        self.level = level
        self.score = score
        self.recommended_action = recommended_action
        self.reason_codes = reason_codes


def score_student(
    student: Dict[str, Any],
    tracking: Optional[Dict[str, Any]] = None,
) -> StudentPriorityScore:
    """
    Heuristic priority score for a student dict.
    For display and queue sorting only — not a governance assessment.
    Use assess_orchestration_priority() for governance decisions.
    """
    codes: List[str] = []
    score = 0.0

    hws = student.get("HWsBehind") or 0
    inactivity = student.get("LastActivityDays") or 0
    eff = student.get("AvgEffRating")
    balance = student.get("PaymentBalance") or 0

    if hws >= 3:
        score += 40.0
        codes.append("HWS_BEHIND_HIGH_RISK")
    elif hws >= 1:
        score += 20.0
        codes.append("HWS_BEHIND_MODERATE")

    if inactivity > 14:
        score += 30.0
        codes.append("INACTIVITY_HIGH_RISK")
    elif inactivity > 7:
        score += 15.0
        codes.append("INACTIVITY_MODERATE")

    if eff is not None and eff < 3.0:
        score += 20.0
        codes.append("EFF_RATING_LOW")

    if balance > 0:
        score += 10.0
        codes.append("PAYMENT_BALANCE_RISK")

    if tracking:
        state = tracking.get("state", "")
        if state == "INTERVENTION_REQUIRED":
            score += 20.0
            codes.append("INTERVENTION_STATE")
        elif state == "NO_RESPONSE":
            score += 10.0
            codes.append("NO_RESPONSE_STATE")

    if score >= 60:
        level = PRIORITY_CRITICAL
        action = "ESCALATE"
    elif score >= 40:
        level = PRIORITY_HIGH
        action = "CONTACT_IMMEDIATELY"
    elif score >= 20:
        level = PRIORITY_MEDIUM
        action = "SCHEDULE_OUTREACH"
    else:
        level = PRIORITY_LOW
        action = "MONITOR"

    return StudentPriorityScore(
        level=level, score=score, recommended_action=action, reason_codes=codes,
    )


def risk_level_for_display(profile: Any) -> str:
    """
    Display-only risk string from a StudentTriggerData ORM object or None.
    Returns "HIGH", "MEDIUM", "LOW", or "UNKNOWN". Not a governance decision.
    """
    if profile is None:
        return "UNKNOWN"
    hws = getattr(profile, "HWsBehind", None)
    inactivity = getattr(profile, "LastActivityDays", None)
    if (hws is not None and hws >= 3) or (inactivity is not None and inactivity > 14):
        return RISK_HIGH
    if (hws is not None and hws >= 1) or (inactivity is not None and inactivity > 7):
        return RISK_MEDIUM
    return RISK_LOW
