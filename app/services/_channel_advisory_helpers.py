"""
Internal helpers for the channel advisory service.
Not part of the public API. Consumed only by channel_selector.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.channel_selector_types import (
    ALL_CHANNELS, CH_CALL, CH_EMAIL, CH_SMS,
    AI_ADVISORY, AI_CONFIDENT, AI_FINALIZED_COPY,
    AI_IN_FLIGHT, AI_STALE, AI_UNAVAILABLE,
    CONF_HIGH, CONF_LOW, CONF_MEDIUM, CONF_UNKNOWN,
    REQUIRED_ATTRIBUTION, SCOPE_CHANNEL_EXHAUSTED,
    SCOPE_MULTI_CHANNEL_ELIGIBLE, SCOPE_NONE, SCOPE_REPLAY_CANDIDATE,
    UNKNOWN_V0, _DELIVERY_SCOPES,
    AICtx, AIOutputCtx, ChannelAdvisoryAssessment, ChannelAdvisoryContext,
    CommunicationCtx, EscalationConstraints, GovernanceConstraints,
    GovernanceCtx, OperationalCtx, ProviderHealthMetadata,
    ReplayRestrictions, ThresholdBindings,
)

logger = logging.getLogger(__name__)


def _opaque_id(user_id: Any) -> Optional[str]:
    if user_id is None:
        return None
    return hashlib.sha256(f"ssip:cid:{user_id}".encode()).hexdigest()[:16]


def _t(val: Any) -> Optional[Any]:
    return None if val == UNKNOWN_V0 else val


def resolve_thresholds(
    key_map: Dict[str, str],
    rule_set: Dict[str, Any],
    tb: ThresholdBindings,
    codes: List[str],
    warnings: List[str],
) -> None:
    for key, attr in key_map.items():
        if key in rule_set:
            setattr(tb, attr, rule_set[key])
        else:
            tag = f"CONFIG_THRESHOLD_MISSING_{key.upper()}"
            codes.append(tag)
            warnings.append(tag)
            logger.warning('{"event":"CONFIG_THRESHOLD_MISSING","key":"%s"}', key)


def assess_ai_tier(
    ai: AICtx,
    tb: ThresholdBindings,
    ai_out: AIOutputCtx,
    codes: List[str],
) -> str:
    if ai.ai_finalized_copy:
        ai_out.ai_governance_tier = AI_FINALIZED_COPY
        return AI_FINALIZED_COPY
    ttl = _t(tb.ai_insight_ttl_hours)
    if ttl is None:
        codes.append("AI_TTL_NOT_CONFIGURED")
        ai_out.ai_governance_tier = AI_UNAVAILABLE
        return AI_UNAVAILABLE
    state = ai.ai_insight_state or ""
    if state in ("AI_GENERATING", "AI_PENDING"):
        ai_out.ai_governance_tier = AI_IN_FLIGHT
        return AI_IN_FLIGHT
    if state == "AI_GENERATION_FAILED" or not state:
        ai_out.ai_governance_tier = AI_UNAVAILABLE
        return AI_UNAVAILABLE
    if state == "AI_REVIEWED":
        stale = ai.ai_stale_flag
        if not stale and ai.ai_generated_at:
            try:
                gen = datetime.fromisoformat(
                    ai.ai_generated_at.replace("Z", "+00:00")
                )
                stale = (datetime.now(timezone.utc) - gen) > timedelta(hours=ttl)
            except (ValueError, TypeError):
                stale = True
        if stale:
            ai_out.ai_governance_tier = AI_STALE
            ai_out.stale_flag = True
            return AI_STALE
        score = ai.ai_confidence_score or 0.0
        ai_out.ai_confidence_score = score
        tier = AI_CONFIDENT if score >= 0.70 else AI_ADVISORY
        ai_out.ai_governance_tier = tier
        ai_out.ai_input_used = True
        return tier
    ai_out.ai_governance_tier = AI_UNAVAILABLE
    return AI_UNAVAILABLE


def prioritize_channels(
    eligible: List[str],
    op: OperationalCtx,
    comm: CommunicationCtx,
    tb: ThresholdBindings,
    codes: List[str],
) -> Tuple[List[str], bool]:
    """Return (ordered_candidates, has_preference_signal)."""
    resp: Dict[str, str] = {ch: "MEDIUM" for ch in eligible}
    for entry in comm.channel_delivery_history:
        ch = entry.get("channel")
        if ch not in eligible:
            continue
        outcome = entry.get("outcome", "")
        if outcome == "CONNECTED":
            resp[ch] = "HIGH"
        elif outcome in ("DELIVERY_FAILED", "NO_ANSWER") and resp.get(ch) != "HIGH":
            resp[ch] = "LOW"
        elif outcome in ("INBOUND_ENGAGEMENT", "OPENED", "REPLIED"):
            resp[ch] = "HIGH"

    score    = op.engagement_signal_score
    call_th  = _t(tb.call_engagement_score_threshold)
    sms_th   = _t(tb.sms_engagement_score_threshold)
    email_th = _t(tb.email_engagement_score_threshold)
    pref_cfg = _t(tb.preferred_initial_channel)

    if score is None:
        codes.append("ENGAGEMENT_SIGNAL_UNKNOWN")

    ordered  = list(eligible)
    has_pref = False

    if score is not None:
        if call_th is not None and score >= call_th and CH_CALL in ordered:
            ordered.remove(CH_CALL); ordered.insert(0, CH_CALL); has_pref = True
        elif sms_th is not None and score >= sms_th and CH_SMS in ordered:
            ordered.remove(CH_SMS); ordered.insert(0, CH_SMS); has_pref = True
        elif email_th is not None and score >= email_th and CH_EMAIL in ordered:
            ordered.remove(CH_EMAIL); ordered.insert(0, CH_EMAIL); has_pref = True

    if not has_pref and pref_cfg and pref_cfg in ordered:
        ordered.remove(pref_cfg)
        ordered.insert(0, pref_cfg)

    if call_th is None and sms_th is None and email_th is None:
        codes.append("PARTIAL_ENGAGEMENT_ASSESSMENT")

    return ordered, has_pref


def emit_log(
    *,
    level: str,
    event: str,
    gov: GovernanceCtx,
    sid: Optional[str],
    scope: str,
    produced: bool,
    path: List[str],
    codes: List[str],
    ph: ProviderHealthMetadata,
    ai_tier: str,
    duration_ms: int,
    outcome: str,
    candidates: Optional[List[str]] = None,
    prohibited: Optional[List[str]] = None,
) -> None:
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": "channel_advisory",
        "event": event,
        "correlation_id": gov.correlation_id,
        "causation_id": gov.causation_id,
        "student_id_opaque": sid,
        "execution_type": gov.execution_type,
        "execution_mode": gov.execution_mode,
        "config_version_id": gov.config_version_id,
        "advisory_scope": scope,
        "channel_advisory_produced": produced,
        "recommended_channel_candidates": candidates or [],
        "prohibited_channels": prohibited or [],
        "ai_governance_tier": ai_tier,
        "channel_suspension_applied": ph.channel_suspension_applied,
        "rule_path_taken": path,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "reason_codes": codes,
    }
    log_fn = getattr(logger, level if level in ("info", "warning", "error") else "info")
    log_fn(json.dumps(entry))


def emit_assessment(
    ctx: ChannelAdvisoryContext,
    gov: GovernanceCtx,
    sid: Optional[str],
    scope: str,
    produced: bool,
    path: List[str],
    codes: List[str],
    gc: GovernanceConstraints,
    esc: EscalationConstraints,
    rr: ReplayRestrictions,
    ai_out: AIOutputCtx,
    tb: ThresholdBindings,
    ph: ProviderHealthMetadata,
    threshold_warnings: List[str],
    degraded: bool,
    t0: float,
    *,
    prohibited: Optional[List[str]] = None,
    candidates: Optional[List[str]] = None,
    blocked: bool = False,
    blocking_reason: Optional[str] = None,
) -> ChannelAdvisoryAssessment:
    is_replay = gov.execution_type in ("replay", "regeneration")
    # AP-C11: live_delivery_permitted False in replay; False pre-Phase-12
    live_ok = (
        produced
        and scope in _DELIVERY_SCOPES
        and gov.execution_mode == "LIVE"
        and not is_replay
        and not blocked
    )
    gc.live_delivery_permitted = live_ok

    if is_replay:
        gc.governance_scope   = "REPLAY_ONLY"
        gc.suppression_reason = "REPLAY_EXECUTION"
    elif gov.execution_mode == "SHADOW":
        gc.governance_scope   = "SHADOW_ONLY"
        gc.suppression_reason = "SHADOW_MODE_ACTIVE"
    else:
        gc.governance_scope   = "AUTHORIZED" if live_ok else "SHADOW_ONLY"
        if not live_ok:
            gc.suppression_reason = "PRE_PHASE12_CERTIFICATION"

    attr    = gov.attribution_context or {}
    attr_ok = all(k in attr and attr[k] for k in REQUIRED_ATTRIBUTION)

    if is_replay:
        basis = "HISTORICAL_REPLAY"
    elif ai_out.channel_priority_adjustment_applied:
        basis = "AI_ASSISTED"
    elif ai_out.fallback_applied:
        basis = "FALLBACK"
    else:
        basis = "RULE_BASED"

    if is_replay:
        confidence = CONF_UNKNOWN
    elif scope in (SCOPE_NONE, SCOPE_CHANNEL_EXHAUSTED) or blocked:
        confidence = CONF_LOW
    elif threshold_warnings:
        confidence = CONF_LOW
    elif ai_out.ai_governance_tier in (AI_STALE, AI_UNAVAILABLE):
        confidence = CONF_MEDIUM
    elif scope == SCOPE_MULTI_CHANNEL_ELIGIBLE:
        confidence = CONF_MEDIUM
    elif scope.endswith("_PREFERRED"):
        confidence = CONF_HIGH if ai_out.ai_input_used else CONF_MEDIUM
    else:
        confidence = CONF_MEDIUM

    dur = int((time.monotonic() - t0) * 1000)
    lvl = "error" if blocked else ("warning" if degraded or threshold_warnings else "info")
    emit_log(
        level=lvl,
        event="channel_advisory_produced" if not blocked else "governance_precondition_failed",
        gov=gov, sid=sid, scope=scope, produced=produced,
        path=path, codes=codes, ph=ph, ai_tier=ai_out.ai_governance_tier,
        duration_ms=dur, outcome="blocked" if blocked else "success",
        candidates=candidates, prohibited=prohibited,
    )
    return ChannelAdvisoryAssessment(
        channel_advisory_produced=produced,
        advisory_scope=scope,
        recommended_channel_candidates=list(candidates or []),
        prohibited_channels=list(prohibited or []),
        governance_constraints=gc,
        escalation_constraints=esc,
        replay_restrictions=rr,
        ai_context=ai_out,
        threshold_bindings=tb,
        provider_health_metadata=ph,
        advisory_confidence=confidence,
        execution_mode=gov.execution_mode,
        execution_type=gov.execution_type,
        config_version_id=gov.config_version_id,
        historical_config_version_id=rr.historical_config_version_id,
        correlation_id=gov.correlation_id,
        causation_id=gov.causation_id,
        attribution_metadata=dict(gov.attribution_context),
        attribution_status="COMPLETE" if attr_ok else "INCOMPLETE",
        degraded_evaluation=degraded,
        rule_path_taken=list(path),
        assessment_basis=basis,
        reason_codes=list(codes),
        advisory_blocked=blocked,
        blocking_reason=blocking_reason,
        config_threshold_warnings=list(threshold_warnings),
        student_id_opaque=sid,
    )
