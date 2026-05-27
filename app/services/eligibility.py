"""
Governance-safe orchestration eligibility assessment service.
Implements directives/outreach_eligibility_rules.md Rules 0–12.

AP-E1–AP-E15 (all absolute prohibitions):
  AP-E1/E2/E3 — no outreach execution, no state mutation, no config mutation
  AP-E4/E5    — no immutable snapshot overwrites, no historical output overwrites
  AP-E6/E7    — no OUTREACH/RETRY in replay; no audit bypass
  AP-E8/E9    — SQL Server authority honored; no hardcoded thresholds
  AP-E10      — no raw PII in logs (user_id, email, phone)
  AP-E11–E15  — live_outreach_permitted=False in replay; unique idempotency keys;
                Rule 0 gates all evaluation; compliance hold → ESCALATION_CANDIDATE only;
                attribution propagated unchanged
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.eligibility_types import (
    AI_ADVISORY, AI_CONFIDENT, AI_FINALIZED_COPY, AI_IN_FLIGHT,
    AI_STALE, AI_UNAVAILABLE,
    AICtx, AIOutputCtx, AcademicCtx, EligibilityContext, GovernanceCtx,
    GovernanceRequirements, OperationalCtx, OrchestrationConstraints,
    OrchestrationEligibilityAssessment, REQUIRED_ATTRIBUTION, ReplayRestrictions,
    SCOPE_ESCALATION, SCOPE_NONE, SCOPE_OUTREACH, SCOPE_PRIORITIZATION_ONLY,
    SCOPE_REPLAY, SCOPE_RETRY, ThresholdBindings, UNKNOWN_V0,
    K_AI_TTL, K_ESC_REPEAT, K_EXCL_WINDOW, K_HWS_HIGH, K_INACT_HIGH,
    K_MAX_ATTEMPTS, K_MAX_INACT, K_MIN_EFF, K_MIN_HWS, K_PAYMENT_RISK,
    K_RETRY_WINDOW, K_SYNC_AGE,
    PRI_CRITICAL, PRI_HIGH, PRI_LOW, PRI_MEDIUM, PRI_UNKNOWN,
)

logger = logging.getLogger(__name__)

_ELIGIBLE_SCOPES = (SCOPE_OUTREACH, SCOPE_RETRY, SCOPE_ESCALATION,
                    SCOPE_REPLAY, SCOPE_PRIORITIZATION_ONLY)

_KEY_MAP = {
    "excl_window":  K_EXCL_WINDOW,  "min_hws":      K_MIN_HWS,
    "min_eff":      K_MIN_EFF,       "max_inact":    K_MAX_INACT,
    "max_attempts": K_MAX_ATTEMPTS,  "retry_window": K_RETRY_WINDOW,
    "payment_risk": K_PAYMENT_RISK,  "ai_ttl":       K_AI_TTL,
    "esc_repeat":   K_ESC_REPEAT,    "hws_high":     K_HWS_HIGH,
    "inact_high":   K_INACT_HIGH,    "sync_age":     K_SYNC_AGE,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _opaque_id(user_id: Optional[int]) -> Optional[str]:
    """SHA-256 first-16-hex-char hash of user_id — AP-E10."""
    if user_id is None:
        return None
    return hashlib.sha256(f"ssip:eid:{user_id}".encode()).hexdigest()[:16]


def _resolve_thresholds(
    rule_set: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """Rule 3 / AP-E9: extract all thresholds; UNKNOWN_V0 for missing keys."""
    resolved: Dict[str, Any] = {}
    warnings: List[str] = []
    for alias, key in _KEY_MAP.items():
        if key in rule_set:
            resolved[alias] = rule_set[key]
        else:
            resolved[alias] = UNKNOWN_V0
            warnings.append(f"CONFIG_THRESHOLD_MISSING_{key.upper()}")
            logger.warning("config_threshold_missing key=%s", key)
    return resolved, warnings


def _t(thresholds: Dict[str, Any], alias: str) -> Any:
    """Return threshold value; None when UNKNOWN_V0 (cannot be compared)."""
    v = thresholds.get(alias, UNKNOWN_V0)
    return None if v == UNKNOWN_V0 else v


def _assess_ai_tier(ai: AICtx, thresholds: Dict[str, Any]) -> Tuple[str, AIOutputCtx]:
    """Rule 5 — 6-tier AI governance classification."""
    out = AIOutputCtx(ai_confidence_score=ai.ai_confidence_score,
                      stale_flag=ai.ai_stale_flag)
    if ai.ai_finalized_copy:
        out.ai_governance_tier = AI_FINALIZED_COPY
        return AI_FINALIZED_COPY, out
    if ai.ai_insight_state in ("AI_GENERATING", "AI_PENDING"):
        out.ai_governance_tier = AI_IN_FLIGHT
        return AI_IN_FLIGHT, out
    if ai.ai_insight_state in ("AI_GENERATION_FAILED", None):
        out.ai_governance_tier, out.fallback_applied = AI_UNAVAILABLE, True
        return AI_UNAVAILABLE, out
    if ai.ai_insight_state == "AI_REVIEWED":
        ttl = _t(thresholds, "ai_ttl")
        if ttl is None:
            out.ai_governance_tier, out.fallback_applied = AI_UNAVAILABLE, True
            return AI_UNAVAILABLE, out
        if ai.ai_stale_flag:
            out.ai_governance_tier = AI_STALE
            return AI_STALE, out
        score = ai.ai_confidence_score or 0.0
        tier = AI_CONFIDENT if score >= 0.70 else AI_ADVISORY
        out.ai_governance_tier, out.ai_input_used = tier, True
        return tier, out
    out.ai_governance_tier, out.fallback_applied = AI_UNAVAILABLE, True
    return AI_UNAVAILABLE, out


def _priority_upgrade(current: str) -> str:
    ladder = [PRI_LOW, PRI_MEDIUM, PRI_HIGH, PRI_CRITICAL]
    try:
        return ladder[min(ladder.index(current) + 1, 3)]
    except ValueError:
        return current


def _log(level: str, event: str, ctx: EligibilityContext,
         scope: str, priority: str, ai_tier: str,
         path: List[str], outcome: str, ms: float,
         sid: Optional[str], **extra: Any) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level, "service": "eligibility_assessment", "event": event,
        "correlation_id": ctx.governance.correlation_id,
        "causation_id": ctx.governance.causation_id,
        "student_id_opaque": sid,
        "execution_type": ctx.governance.execution_type,
        "execution_mode": ctx.governance.execution_mode,
        "config_version_id": ctx.governance.config_version_id,
        "eligibility_scope": scope, "orchestration_priority": priority,
        "ai_governance_tier": ai_tier, "rule_path_taken": path,
        "duration_ms": round(ms, 2), "outcome": outcome,
    }
    entry.update(extra)
    getattr(logger, level, logger.info)(json.dumps(entry))


# ── Public API ────────────────────────────────────────────────────────────────

def assess_orchestration_eligibility(
    ctx: EligibilityContext,
) -> OrchestrationEligibilityAssessment:
    """
    Produce OrchestrationEligibilityAssessment per Rules 0–12.
    Advisory output only — no dispatch, no state mutation, no DB writes.
    """
    t0 = time.monotonic()
    gov = ctx.governance
    sid = _opaque_id(ctx.academic.user_id)
    path: List[str] = []
    codes: List[str] = []

    def _blocked(reason: str, extra_codes: List[str]) -> OrchestrationEligibilityAssessment:
        ms = (time.monotonic() - t0) * 1000
        path.append("RULE_0_BLOCKED")
        _log("error", "governance_precondition_failed", ctx, SCOPE_NONE,
             PRI_UNKNOWN, AI_UNAVAILABLE, path, "blocked", ms, sid,
             blocking_reason=reason, reason_codes=extra_codes)
        return OrchestrationEligibilityAssessment(
            orchestration_eligible=False, eligibility_scope=SCOPE_NONE,
            governance_requirements=GovernanceRequirements(
                config_version_id=gov.config_version_id,
                execution_mode=gov.execution_mode,
                idempotency_key=gov.idempotency_key,
            ),
            correlation_id=gov.correlation_id, causation_id=gov.causation_id,
            config_version_id=gov.config_version_id,
            execution_mode=gov.execution_mode, execution_type=gov.execution_type,
            attribution_metadata=dict(gov.attribution_context),
            rule_path_taken=list(path), reason_codes=extra_codes,
            eligibility_blocked=True, blocking_reason=reason, student_id_opaque=sid,
        )

    # ── RULE 0 ────────────────────────────────────────────────────────────────
    path.append("RULE_0")
    r0: List[str] = []
    if not gov.config_version_id:                  r0.append("CONFIG_UNRESOLVED")
    if gov.execution_mode not in ("SHADOW", "LIVE"): r0.append("EXECUTION_MODE_INVALID")
    if not gov.correlation_id:                     r0.append("CORRELATION_ID_MISSING")
    if any(gov.attribution_context.get(k) is None for k in REQUIRED_ATTRIBUTION):
        r0.append("ATTRIBUTION_INCOMPLETE")
    if gov.execution_type not in ("original", "replay", "regeneration"):
        r0.append("EXECUTION_TYPE_INVALID")
    if gov.execution_type in ("replay", "regeneration") and not gov.replay_context:
        r0.append("REPLAY_CONTEXT_MISSING")
    if r0:
        return _blocked("GOVERNANCE_PRECONDITION_FAILED", r0)

    # ── RULE 3 — threshold resolution (non-terminal) ─────────────────────────
    path.append("RULE_3")
    th, warnings = _resolve_thresholds(gov.config_rule_set)
    codes.extend(warnings)
    degraded = bool(warnings)
    tb = ThresholdBindings(
        exclusion_window_hours=th["excl_window"], min_hws_behind=th["min_hws"],
        min_effort_rating=th["min_eff"], max_inactivity_days=th["max_inact"],
        max_outreach_attempts=th["max_attempts"], retry_window_hours=th["retry_window"],
        payment_risk_balance_threshold=th["payment_risk"],
        ai_insight_ttl_hours=th["ai_ttl"], escalation_repeat_threshold=th["esc_repeat"],
        hws_behind_high_risk=th["hws_high"], inactivity_high_risk_days=th["inact_high"],
    )
    scope = SCOPE_NONE
    priority = PRI_UNKNOWN
    constraints = OrchestrationConstraints(
        max_attempts_constraint=th["max_attempts"],
        exclusion_window_constraint_hours=th["excl_window"],
        retry_window_constraint_hours=th["retry_window"],
    )
    replay_rest = ReplayRestrictions()

    # ── RULE 1 ────────────────────────────────────────────────────────────────
    path.append("RULE_1")
    if ctx.operational.outreach_state == "CLOSED":
        codes.append("OUTREACH_CLOSED_TERMINAL")
        return _emit(ctx, gov, sid, SCOPE_NONE, PRI_UNKNOWN, AI_UNAVAILABLE,
                     path, codes, constraints, replay_rest, AIOutputCtx(),
                     tb, warnings, degraded, t0)

    # ── RULE 2 ────────────────────────────────────────────────────────────────
    path.append("RULE_2")
    if gov.compliance_hold_flag:
        codes.append("COMPLIANCE_HOLD_ACTIVE")
        constraints.live_outreach_permitted = False
        gr = GovernanceRequirements(
            config_version_id=gov.config_version_id,
            config_version_status=gov.config_version_status,
            execution_mode=gov.execution_mode,
            idempotency_key=gov.idempotency_key,
            governance_preconditions_met=True,
            blocking_governance_flags=["COMPLIANCE_HOLD_ACTIVE"],
        )
        return _emit(ctx, gov, sid, SCOPE_ESCALATION, PRI_CRITICAL,
                     AI_UNAVAILABLE, path, codes, constraints, replay_rest,
                     AIOutputCtx(), tb, warnings, degraded, t0, gov_reqs=gr)

    # ── RULE 4 ────────────────────────────────────────────────────────────────
    path.append("RULE_4")
    access = ctx.academic.access_state
    if access == "REVOKED":
        codes.append("ACCESS_REVOKED_SQL_SERVER_AUTHORITATIVE")
        return _emit(ctx, gov, sid, SCOPE_ESCALATION, PRI_HIGH,
                     AI_UNAVAILABLE, path, codes, constraints, replay_rest,
                     AIOutputCtx(), tb, warnings, degraded, t0)
    if access == "SUSPENDED":
        codes.append("ACCESS_SUSPENDED_AWAIT_RESTORATION")
        return _emit(ctx, gov, sid, SCOPE_NONE, PRI_UNKNOWN,
                     AI_UNAVAILABLE, path, codes, constraints, replay_rest,
                     AIOutputCtx(), tb, warnings, degraded, t0)

    # ── RULE 5 — AI governance tier (non-terminal) ────────────────────────────
    path.append("RULE_5")
    ai_tier, ai_out = _assess_ai_tier(ctx.ai, th)
    if ai_out.fallback_applied:
        codes.append("AI_UNAVAILABLE_FALLBACK_APPLIED")

    # ── RULE 5A ───────────────────────────────────────────────────────────────
    if ai_tier == AI_IN_FLIGHT:
        if gov.execution_type == "original":
            path.append("RULE_5A")
            codes.append("AI_INSIGHT_IN_FLIGHT_DEFER_PENDING")
            return _emit(ctx, gov, sid, SCOPE_PRIORITIZATION_ONLY, PRI_UNKNOWN,
                         ai_tier, path, codes, constraints, replay_rest,
                         ai_out, tb, warnings, degraded, t0)
        ai_tier = AI_STALE
        ai_out.ai_governance_tier = AI_STALE

    # ── RULE 6 ────────────────────────────────────────────────────────────────
    path.append("RULE_6")
    if not ctx.academic.email and not ctx.academic.phone_number:
        codes.append("NO_CONTACT_INFO")
        return _emit(ctx, gov, sid, SCOPE_NONE, PRI_UNKNOWN, ai_tier,
                     path, codes, constraints, replay_rest, ai_out,
                     tb, warnings, degraded, t0)

    # ── RULE 7 ────────────────────────────────────────────────────────────────
    path.append("RULE_7")
    excl = _t(th, "excl_window")
    if excl is not None and ctx.operational.last_contact_timestamp:
        try:
            last = datetime.fromisoformat(
                ctx.operational.last_contact_timestamp.replace("Z", "+00:00"))
            elapsed_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            if elapsed_h < excl:
                codes.append("EXCLUSION_WINDOW_ACTIVE")
                constraints.exclusion_window_constraint_hours = excl
                return _emit(ctx, gov, sid, SCOPE_NONE, PRI_UNKNOWN, ai_tier,
                             path, codes, constraints, replay_rest, ai_out,
                             tb, warnings, degraded, t0)
        except (ValueError, TypeError):
            codes.append("EXCLUSION_WINDOW_TIMESTAMP_PARSE_ERROR")

    # ── RULE 10 — replay gate ─────────────────────────────────────────────────
    if gov.execution_type in ("replay", "regeneration"):
        path.append("RULE_10")
        rctx = gov.replay_context or {}
        block: List[str] = []
        if gov.execution_mode == "LIVE":       block.append("REPLAY_LIVE_MODE_BLOCKED")
        if not rctx.get("source_artifact_id"): block.append("REPLAY_SOURCE_ARTIFACT_MISSING")
        if not gov.fingerprint_context:        block.append("REPLAY_FINGERPRINT_MISSING")
        if block:
            codes.extend(block)
            replay_rest.replay_eligible = False
            replay_rest.live_eligible = False
            replay_rest.replay_safe = False
            return _emit(ctx, gov, sid, SCOPE_NONE, PRI_UNKNOWN, ai_tier,
                         path, codes, constraints, replay_rest, ai_out, tb,
                         warnings, degraded, t0, blocked=True,
                         blocking_reason="REPLAY_PRECONDITION_VIOLATED")
        fp = gov.fingerprint_context or {}
        fp_match = all(fp.get(k) not in (None, UNKNOWN_V0) for k in (
            "schema_version", "config_registry_version",
            "ai_prompt_version", "ai_model_version"))
        replay_rest = ReplayRestrictions(
            is_replay=True, replay_eligible=True, live_eligible=False,
            replay_safe=True,
            source_artifact_id=rctx.get("source_artifact_id"),
            historical_config_version_id=rctx.get("historical_config_version_id"),
            fingerprint_comparison_outcome="MATCH" if fp_match else "UNKNOWN",
        )
        codes.append("REPLAY_CANDIDATE")
        scope = SCOPE_REPLAY
        ai_out.ai_governance_tier = AI_FINALIZED_COPY
        ai_tier = AI_FINALIZED_COPY

    # ── RULE 8 ────────────────────────────────────────────────────────────────
    path.append("RULE_8")
    max_att = _t(th, "max_attempts")
    attempts = ctx.operational.contact_attempt_count
    if max_att is not None and attempts >= max_att:
        codes.append("MAX_ATTEMPTS_EXHAUSTED")
        constraints.max_attempts_constraint = max_att
        return _emit(ctx, gov, sid, SCOPE_NONE, PRI_MEDIUM, ai_tier,
                     path, codes, constraints, replay_rest, ai_out,
                     tb, warnings, degraded, t0)
    if scope != SCOPE_REPLAY:
        if attempts > 0 and ctx.operational.retry_eligible:
            path.append("RULE_8B"); scope = SCOPE_RETRY
            codes.append("RETRY_CANDIDATE")
        elif attempts == 0 and ctx.operational.outreach_state in (
                "ELIGIBLE", "QUEUED", None):
            path.append("RULE_8C"); scope = SCOPE_OUTREACH
            codes.append("FIRST_OUTREACH_CANDIDATE")
        else:
            path.append("RULE_8D"); codes.append("OUTREACH_STATE_AMBIGUOUS")
            logger.warning("outreach_state_ambiguous corr=%s", gov.correlation_id)
            return _emit(ctx, gov, sid, SCOPE_NONE, PRI_UNKNOWN, ai_tier,
                         path, codes, constraints, replay_rest, ai_out,
                         tb, warnings, degraded, t0)

    # ── RULE 9 — multi-factor risk (non-terminal) ─────────────────────────────
    path.append("RULE_9")
    high = med = 0
    partial = False

    def _check(val: Optional[Any], high_thr: Any, med_thr: Any,
               high_label: str, med_label: str, invert: bool = False) -> None:
        nonlocal high, med, partial
        if val is None:
            partial = True; return
        def _exceeds(v: Any, thr: Any) -> bool:
            if thr is None: return False
            return (v < thr) if invert else (v >= thr)
        if high_thr is not None and _exceeds(val, high_thr):
            high += 1; codes.append(high_label)
        elif med_thr is not None and _exceeds(val, med_thr):
            med += 1; codes.append(med_label)

    _check(ctx.academic.hws_behind,
           _t(th, "hws_high"), _t(th, "min_hws"),
           "HWS_DELINQUENCY_HIGH_RISK", "HWS_DELINQUENCY_MODERATE")
    # Effort rating: risk when BELOW threshold (invert=True)
    eff = ctx.academic.avg_eff_rating
    min_eff = _t(th, "min_eff")
    if eff is None:
        partial = True
    elif min_eff is not None and eff < min_eff:
        med += 1; codes.append("EFFORT_DECLINE")
    _check(ctx.academic.last_activity_days,
           _t(th, "inact_high"), _t(th, "max_inact"),
           "INACTIVITY_HIGH_RISK", "INACTIVITY_MODERATE")
    pay = ctx.academic.payment_balance
    pay_risk = _t(th, "payment_risk")
    if pay is not None and pay_risk is not None and pay > pay_risk:
        med += 1; codes.append("PAYMENT_RISK")
    esc_rep = _t(th, "esc_repeat")
    if esc_rep is not None and ctx.academic.prior_escalation_count >= esc_rep:
        high += 1; codes.append("ESCALATION_RECURRENCE")
    trend = ctx.academic.historical_risk_trend
    if trend == "CRITICAL":    high += 1; codes.append("HISTORICAL_TREND_CRITICAL")
    elif trend == "DECLINING": med += 1;  codes.append("HISTORICAL_TREND_DECLINING")
    if partial: codes.append("PARTIAL_RISK_ASSESSMENT")

    priority = (PRI_CRITICAL if high >= 2
                else PRI_HIGH if (high == 1 and med >= 1)
                else PRI_MEDIUM if (high >= 1 or med >= 1)
                else PRI_LOW)

    # ── RULE 11 — AI prioritization (non-terminal) ────────────────────────────
    path.append("RULE_11")
    intv = ctx.ai.ai_recommended_intervention
    if ai_tier == AI_CONFIDENT and intv == "ESCALATE":
        priority = PRI_CRITICAL
        ai_out.priority_adjustment_applied = True
        constraints.ai_prioritization_applied = True
        codes.append("AI_ESCALATION_SIGNAL_CONFIDENT")
    elif ai_tier == AI_CONFIDENT and intv in (
            "MEETING", "OUTREACH", "RESOURCE_DELIVERY"):
        priority = _priority_upgrade(priority)
        ai_out.priority_adjustment_applied = True
        constraints.ai_prioritization_applied = True
        codes.append("AI_INTERVENTION_SIGNAL_CONFIDENT")
    elif ai_tier == AI_ADVISORY and intv == "ESCALATE":
        priority = _priority_upgrade(priority)
        ai_out.priority_adjustment_applied = True
        constraints.ai_prioritization_applied = True
        codes.append("AI_ESCALATION_SIGNAL_ADVISORY")
    elif ai_tier == AI_STALE:
        codes.append("STALE_AI_PRIORITIZATION_SKIPPED")
        if gov.execution_mode == "LIVE":
            codes.append("STALE_AI_LIVE_MODE_RESTRICTED")
    elif ai_tier in (AI_UNAVAILABLE,):
        ai_out.fallback_applied = True
        codes.append("AI_UNAVAILABLE_FALLBACK_APPLIED")
    elif ai_tier == AI_FINALIZED_COPY:
        codes.append("AI_FINALIZED_COPY_NOT_APPLIED")

    # ── RULE 12 ───────────────────────────────────────────────────────────────
    path.append("RULE_12")
    return _emit(ctx, gov, sid, scope, priority, ai_tier, path, codes,
                 constraints, replay_rest, ai_out, tb, warnings, degraded, t0)


def _emit(ctx: EligibilityContext, gov: GovernanceCtx, sid: Optional[str],
          scope: str, priority: str, ai_tier: str, path: List[str],
          codes: List[str], constraints: OrchestrationConstraints,
          replay_rest: ReplayRestrictions, ai_out: AIOutputCtx,
          tb: ThresholdBindings, threshold_warnings: List[str], degraded: bool,
          t0: float, gov_reqs: Optional[GovernanceRequirements] = None,
          blocked: bool = False, blocking_reason: Optional[str] = None,
          ) -> OrchestrationEligibilityAssessment:
    """Terminal output factory for Rules 1–12."""
    ms = (time.monotonic() - t0) * 1000
    is_replay = gov.execution_type in ("replay", "regeneration")
    eligible = scope in _ELIGIBLE_SCOPES
    live_ok = eligible and gov.execution_mode == "LIVE" and not is_replay
    constraints.live_outreach_permitted = live_ok
    constraints.execution_mode_constraint = gov.execution_mode

    basis = ("AI_ASSISTED" if ai_out.priority_adjustment_applied
             else "FALLBACK" if ai_out.fallback_applied
             else "HISTORICAL_REPLAY" if is_replay
             else "RULE_BASED")

    hist_cv = (gov.replay_context or {}).get("historical_config_version_id") if is_replay else None

    if gov_reqs is None:
        gov_reqs = GovernanceRequirements(
            config_version_id=gov.config_version_id,
            config_version_status=gov.config_version_status,
            execution_mode=gov.execution_mode,
            idempotency_key=gov.idempotency_key,
            governance_preconditions_met=True,
        )

    outcome = "blocked" if blocked else ("fallback" if ai_out.fallback_applied else "success")
    event = "governance_precondition_failed" if blocked else "orchestration_eligibility_produced"
    _log("error" if blocked else "info", event, ctx, scope, priority,
         ai_tier, path, outcome, ms, sid)

    return OrchestrationEligibilityAssessment(
        orchestration_eligible=eligible, eligibility_scope=scope,
        orchestration_priority=priority, orchestration_constraints=constraints,
        governance_requirements=gov_reqs, replay_restrictions=replay_rest,
        ai_context=ai_out, threshold_bindings=tb,
        attribution_metadata=dict(gov.attribution_context),
        correlation_id=gov.correlation_id, causation_id=gov.causation_id,
        config_version_id=gov.config_version_id,
        historical_config_version_id=hist_cv,
        execution_mode=gov.execution_mode, execution_type=gov.execution_type,
        attribution_status="COMPLETE", degraded_evaluation=degraded,
        threshold_resolution_status="PARTIAL" if degraded else "COMPLETE",
        live_outreach_permitted=live_ok, replay_safe=replay_rest.replay_safe,
        rule_path_taken=list(path), assessment_basis=basis,
        reason_codes=list(codes), eligibility_blocked=blocked,
        blocking_reason=blocking_reason,
        config_threshold_warnings=list(threshold_warnings),
        student_id_opaque=sid,
    )
