"""
Governance-safe channel advisory service.
Implements ChannelAdvisoryAssessment per directives/channel_selection_rules.md §4.

AP-C1–AP-C15 (all absolute prohibitions):
  AP-C1/C2/C3 — no dispatch, no state mutation, no config mutation
  AP-C4/C5    — no immutable snapshot overwrites, no historical output overwrites
  AP-C6/C7    — REPLAY_CHANNEL_CANDIDATE only in replay; no audit bypass
  AP-C8/C9    — SQL Server contact data governs; no hardcoded channel order
  AP-C10      — no raw PII in logs (phone, email, user_id)
  AP-C11–C15  — live_delivery_permitted=False in replay; unique idempotency keys;
                Rule 0 gates all evaluation; prohibited channels never in candidates;
                attribution propagated unchanged
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.services._channel_advisory_helpers import (
    assess_ai_tier,
    emit_assessment as _emit,
    emit_log as _emit_log,
    prioritize_channels,
    resolve_thresholds,
)
from app.services.channel_selector_types import (
    ALL_CHANNELS, CH_CALL, CH_EMAIL, CH_SMS,
    AI_ADVISORY, AI_CONFIDENT, AI_FINALIZED_COPY,
    AI_IN_FLIGHT, AI_STALE, AI_UNAVAILABLE,
    K_AI_TTL, K_CALL_ENG, K_COOLDOWN_HOURS, K_DELIVERY_FAIL_SUSP,
    K_EMAIL_ENG, K_OPT_OUT_PERIOD, K_PREFERRED_CHANNEL, K_SMS_ENG,
    PREF_CALL, PREF_EMAIL, PREF_SMS,
    REQUIRED_ATTRIBUTION,
    SCOPE_CHANNEL_EXHAUSTED, SCOPE_MULTI_CHANNEL_ELIGIBLE,
    SCOPE_NONE, SCOPE_REPLAY_CANDIDATE, UNKNOWN_V0,
    AIOutputCtx, ChannelAdvisoryAssessment, ChannelAdvisoryContext,
    EscalationConstraints, GovernanceConstraints,
    ProviderHealthMetadata, ReplayRestrictions, ThresholdBindings,
)

logger = logging.getLogger(__name__)

_KEY_MAP: Dict[str, str] = {
    K_PREFERRED_CHANNEL:  "preferred_initial_channel",
    K_DELIVERY_FAIL_SUSP: "delivery_failure_suspension_threshold",
    K_CALL_ENG:           "call_engagement_score_threshold",
    K_SMS_ENG:            "sms_engagement_score_threshold",
    K_EMAIL_ENG:          "email_engagement_score_threshold",
    K_COOLDOWN_HOURS:     "channel_specific_cooldown_hours",
    K_AI_TTL:             "ai_insight_ttl_hours",
    K_OPT_OUT_PERIOD:     "channel_opt_out_respect_period_hours",
}

_CH_PREF_MAP: Dict[str, str] = {
    PREF_CALL: CH_CALL, PREF_SMS: CH_SMS, PREF_EMAIL: CH_EMAIL,
}


def _t(val: Any) -> Optional[Any]:
    return None if val == UNKNOWN_V0 else val


def assess_channel_advisory(
    ctx: ChannelAdvisoryContext,
) -> ChannelAdvisoryAssessment:
    """
    Governance-safe channel advisement. Advisory only. Never dispatches.
    Implements Rules 0–13 per directives/channel_selection_rules.md §4.
    """
    t0   = time.monotonic()
    gov  = ctx.governance
    comm = ctx.communication
    op   = ctx.operational
    ai   = ctx.ai

    path:               List[str] = []
    codes:              List[str] = []
    prohibited:         List[str] = []
    threshold_warnings: List[str] = []
    degraded   = False
    sid: Optional[str] = None   # AP-C10: no raw user_id in scope output

    gc     = GovernanceConstraints(
        execution_mode_constraint=gov.execution_mode,
        config_version_id=gov.config_version_id,
        idempotency_key=gov.idempotency_key,
    )
    esc    = EscalationConstraints()
    rr     = ReplayRestrictions()
    ai_out = AIOutputCtx()
    tb     = ThresholdBindings()
    ph     = ProviderHealthMetadata()
    is_replay = gov.execution_type in ("replay", "regeneration")

    # ── RULE 0: Governance Precondition Gate ────────────────────────────────
    path.append("RULE_0")
    r0: List[str] = []
    if not gov.config_version_id:
        r0.append("CONFIG_UNRESOLVED")
    if gov.config_version_status != "ACTIVE" and gov.execution_type == "original":
        r0.append("CONFIG_VERSION_NOT_ACTIVE")
    if gov.execution_mode not in ("SHADOW", "LIVE"):
        r0.append("EXECUTION_MODE_INVALID")
    if not gov.correlation_id:
        r0.append("CORRELATION_ID_MISSING")
    _a = gov.attribution_context or {}
    if any(k not in _a or not _a[k] for k in REQUIRED_ATTRIBUTION):
        r0.append("ATTRIBUTION_INCOMPLETE")
    if gov.execution_type not in ("original", "replay", "regeneration"):
        r0.append("EXECUTION_TYPE_INVALID")
    if is_replay and not gov.replay_context:
        r0.append("REPLAY_CONTEXT_MISSING")
    if r0:
        gc.governance_preconditions_met = False
        gc.blocking_governance_flags = r0
        _emit_log(
            level="error", event="governance_precondition_failed",
            gov=gov, sid=sid, scope=SCOPE_NONE, produced=False,
            path=path, codes=r0, ph=ph, ai_tier=AI_UNAVAILABLE,
            duration_ms=int((time.monotonic() - t0) * 1000), outcome="blocked",
        )
        return ChannelAdvisoryAssessment(
            channel_advisory_produced=False,
            advisory_scope=SCOPE_NONE,
            governance_constraints=gc,
            escalation_constraints=esc,
            replay_restrictions=rr,
            ai_context=ai_out,
            threshold_bindings=tb,
            provider_health_metadata=ph,
            execution_mode=gov.execution_mode,
            execution_type=gov.execution_type,
            config_version_id=gov.config_version_id,
            correlation_id=gov.correlation_id,
            causation_id=gov.causation_id,
            attribution_metadata=dict(gov.attribution_context),
            rule_path_taken=list(path),
            reason_codes=r0,
            advisory_blocked=True,
            blocking_reason="GOVERNANCE_PRECONDITION_FAILED",
            student_id_opaque=sid,
        )
    gc.governance_preconditions_met = True

    # ── RULE 1: Terminal State Check ────────────────────────────────────────
    path.append("RULE_1")
    if op.outreach_state == "CLOSED":
        codes.append("OUTREACH_CLOSED_TERMINAL")
        return _emit(ctx, gov, sid, SCOPE_NONE, False, path, codes, gc, esc, rr,
                     ai_out, tb, ph, threshold_warnings, degraded, t0,
                     prohibited=prohibited)

    # ── RULE 2: Compliance Hold Gate ────────────────────────────────────────
    path.append("RULE_2")
    if gov.compliance_hold_flag:
        prohibited.extend(list(ALL_CHANNELS))
        codes.extend(["COMPLIANCE_HOLD_ACTIVE", "ALL_CHANNELS_COMPLIANCE_BLOCKED"])
        gc.compliance_channel_restrictions = list(ALL_CHANNELS)
        gc.blocking_governance_flags.append("COMPLIANCE_HOLD_ACTIVE")
        esc.escalation_recommended = True
        esc.escalation_urgency = "CRITICAL"
        esc.escalation_reason_codes = ["COMPLIANCE_HOLD_ALL_CHANNELS_BLOCKED"]
        esc.escalation_context = {
            "note": "All channels prohibited under COMPLIANCE_HOLD."
        }
        return _emit(ctx, gov, sid, SCOPE_NONE, True, path, codes, gc, esc, rr,
                     ai_out, tb, ph, threshold_warnings, degraded, t0,
                     prohibited=prohibited)

    # ── RULE 3: Config-Bound Threshold Resolution ───────────────────────────
    path.append("RULE_3")
    resolve_thresholds(_KEY_MAP, gov.config_rule_set, tb, codes, threshold_warnings)
    if threshold_warnings:
        degraded = True

    # ── RULE 4: Contact Data Gate (per channel) ─────────────────────────────
    path.append("RULE_4")
    if not op.phone_number:
        prohibited.extend([CH_CALL, CH_SMS])
        codes.append("NO_PHONE_NUMBER")
    if not op.email:
        prohibited.append(CH_EMAIL)
        codes.append("NO_EMAIL_ADDRESS")
    eligible: List[str] = [c for c in ALL_CHANNELS if c not in prohibited]
    if not eligible:
        codes.append("NO_CONTACT_INFO_ANY_CHANNEL")
        return _emit(ctx, gov, sid, SCOPE_NONE, False, path, codes, gc, esc, rr,
                     ai_out, tb, ph, threshold_warnings, degraded, t0,
                     prohibited=prohibited)

    # ── RULE 5: AI Governance Tier Assessment ───────────────────────────────
    path.append("RULE_5")
    ai_tier = assess_ai_tier(ai, tb, ai_out, codes)

    # Rule 5A: IN_FLIGHT defers without blocking
    if ai_tier == AI_IN_FLIGHT:
        if is_replay:
            ai_tier = AI_STALE
            ai_out.ai_governance_tier = AI_STALE
        else:
            codes.append("AI_INSIGHT_IN_FLIGHT_CHANNEL_ADVISORY_PROCEEDS")
            ai_out.ai_input_used = False

    # ── RULE 6: Opt-Out and Consent Channel Gate ─────────────────────────────
    path.append("RULE_6")
    opt_out = op.channel_opt_out_state or {}
    for ch in list(eligible):
        if opt_out.get(ch, False):
            eligible.remove(ch)
            prohibited.append(ch)
            gc.opt_out_channel_exclusions.append(ch)
            codes.append(f"{ch}_OPT_OUT_ACTIVE")
    if not eligible:
        codes.append("CHANNEL_EXHAUSTED_OPT_OUT")
        esc.escalation_recommended = True
        esc.escalation_urgency = "MEDIUM"
        esc.escalation_reason_codes = ["ALL_CHANNELS_OPT_OUT_PROHIBITED"]
        esc.escalation_context = {
            "note": "All channels prohibited by active opt-out registrations."
        }
        return _emit(ctx, gov, sid, SCOPE_CHANNEL_EXHAUSTED, True, path, codes,
                     gc, esc, rr, ai_out, tb, ph, threshold_warnings, degraded,
                     t0, prohibited=prohibited)

    # ── RULE 7: Provider Health and Channel Suspension Gate ──────────────────
    path.append("RULE_7")
    phs  = op.provider_health_state or {}
    susp = op.channel_suspension_state or {}
    ph.call_provider_state  = phs.get(CH_CALL,  "UNKNOWN")
    ph.sms_provider_state   = phs.get(CH_SMS,   "UNKNOWN")
    ph.email_provider_state = phs.get(CH_EMAIL, "UNKNOWN")
    if not phs:
        codes.append("PROVIDER_HEALTH_UNKNOWN")

    degraded_chs: List[str] = []
    for ch in list(eligible):
        state = phs.get(ch, "HEALTHY") if phs else "HEALTHY"
        if state == "UNAVAILABLE":
            eligible.remove(ch)
            prohibited.append(ch)
            ph.suspended_channels.append(ch)
            ph.channel_suspension_applied = True
            codes.append(f"{ch}_PROVIDER_UNAVAILABLE")
        elif susp.get(ch, False):
            eligible.remove(ch)
            prohibited.append(ch)
            gc.suspended_channel_exclusions.append(ch)
            ph.suspended_channels.append(ch)
            ph.channel_suspension_applied = True
            codes.append(f"{ch}_DELIVERY_FAILURE_SUSPENDED")
        elif state == "DEGRADED":
            degraded_chs.append(ch)
            codes.append(f"{ch}_PROVIDER_DEGRADED")
    for ch in degraded_chs:
        if ch in eligible:
            eligible.remove(ch)
            eligible.append(ch)
    if not eligible:
        codes.append("CHANNEL_EXHAUSTED_PROVIDER_FAILURE")
        esc.escalation_recommended = True
        esc.escalation_urgency = "HIGH"
        esc.escalation_reason_codes = ["ALL_CHANNELS_PROVIDER_UNAVAILABLE_OR_SUSPENDED"]
        esc.escalation_context = {
            "note": "All channels unavailable or suspended due to provider state."
        }
        return _emit(ctx, gov, sid, SCOPE_CHANNEL_EXHAUSTED, True, path, codes,
                     gc, esc, rr, ai_out, tb, ph, threshold_warnings, degraded,
                     t0, prohibited=prohibited)

    # ── RULE 8: Channel Exhaustion Gate ─────────────────────────────────────
    path.append("RULE_8")
    if op.channel_exhaustion_state == "EXHAUSTED" and not eligible:
        codes.append("ALL_CHANNELS_EXHAUSTED")
        esc.escalation_recommended = True
        esc.escalation_urgency = "HIGH"
        esc.escalation_reason_codes = ["CHANNEL_EXHAUSTION_CONFIRMED"]
        esc.escalation_context = {"channel_exhaustion_state": "EXHAUSTED"}
        return _emit(ctx, gov, sid, SCOPE_CHANNEL_EXHAUSTED, True, path, codes,
                     gc, esc, rr, ai_out, tb, ph, threshold_warnings, degraded,
                     t0, prohibited=prohibited)
    if op.channel_exhaustion_state == "PARTIAL":
        codes.append("CHANNEL_EXHAUSTION_PARTIAL")

    # ── RULE 9: Replay Channel Gate ──────────────────────────────────────────
    scope_locked: Optional[str] = None
    if is_replay:
        path.append("RULE_9")
        rc       = gov.replay_context or {}
        src      = rc.get("source_artifact_id")
        hist_cfg = rc.get("historical_config_version_id") or rc.get("config_version_id")
        fp       = gov.fingerprint_context or {}
        r9: List[str] = []
        if gov.execution_mode == "LIVE":
            r9.append("REPLAY_LIVE_MODE_BLOCKED")
        if not src:
            r9.append("REPLAY_SOURCE_ARTIFACT_MISSING")
        if not fp:
            r9.append("REPLAY_FINGERPRINT_MISSING")
        if r9:
            codes.extend(r9)
            rr.replay_eligible = False
            rr.live_eligible   = False
            rr.replay_safe     = False
            return _emit(ctx, gov, sid, SCOPE_NONE, False, path, codes, gc, esc,
                         rr, ai_out, tb, ph, threshold_warnings, degraded, t0,
                         prohibited=prohibited, blocked=True,
                         blocking_reason="REPLAY_PRECONDITION_VIOLATED")
        rr.is_replay                     = True
        rr.replay_eligible               = True
        rr.live_eligible                 = False
        rr.source_artifact_id            = src
        rr.historical_config_version_id  = hist_cfg
        rr.replay_safe                   = True
        rr.fingerprint_comparison_outcome = "UNKNOWN"
        gc.live_delivery_permitted = False
        codes.append("REPLAY_CHANNEL_CANDIDATE")
        scope_locked = SCOPE_REPLAY_CANDIDATE
        # FAD-2: AI tier locked to FINALIZED_COPY in replay
        if ai.ai_finalized_copy:
            ai_tier = AI_FINALIZED_COPY
            ai_out.ai_governance_tier = AI_FINALIZED_COPY

    # ── RULE 10: Delivery Failure Pattern Assessment ─────────────────────────
    path.append("RULE_10")
    fail_counts = op.channel_delivery_failure_counts or {}
    susp_th     = _t(tb.delivery_failure_suspension_threshold)
    if not fail_counts:
        codes.append("DELIVERY_FAILURE_COUNTS_UNKNOWN")
    for ch in list(eligible):
        cnt = fail_counts.get(ch, 0)
        if susp_th is not None and cnt >= susp_th:
            eligible.remove(ch)
            prohibited.append(ch)
            gc.suspended_channel_exclusions.append(ch)
            ph.suspended_channels.append(ch)
            ph.channel_suspension_applied = True
            codes.append(f"{ch}_DELIVERY_FAILURE_SUSPENDED")
    if not eligible:
        codes.append("CHANNEL_EXHAUSTED_DELIVERY_FAILURE")
        esc.escalation_recommended = True
        esc.escalation_urgency = "HIGH"
        esc.escalation_reason_codes = ["ALL_CHANNELS_DELIVERY_FAILURE_SUSPENDED"]
        return _emit(ctx, gov, sid,
                     scope_locked or SCOPE_CHANNEL_EXHAUSTED, True,
                     path, codes, gc, esc, rr, ai_out, tb, ph,
                     threshold_warnings, degraded, t0, prohibited=prohibited)

    # ── RULE 11: Engagement-Signal-Aware Channel Prioritization ─────────────
    path.append("RULE_11")
    candidates, has_pref = prioritize_channels(eligible, op, comm, tb, codes)

    # ── RULE 12: AI-Assisted Channel Prioritization Adjustment ───────────────
    path.append("RULE_12")
    if not scope_locked and ai_tier in (AI_CONFIDENT, AI_ADVISORY):
        pref_ch = _CH_PREF_MAP.get(ai.ai_channel_preference_signal or "")
        if pref_ch and pref_ch not in prohibited and pref_ch in candidates:
            if ai_tier == AI_CONFIDENT:
                candidates.remove(pref_ch)
                candidates.insert(0, pref_ch)
                ai_out.channel_priority_adjustment_applied = True
                ai_out.ai_channel_preference_signal = ai.ai_channel_preference_signal
                codes.append("AI_CHANNEL_PREFERENCE_SIGNAL_CONFIDENT")
                has_pref = True
            elif not has_pref:
                candidates.remove(pref_ch)
                candidates.insert(0, pref_ch)
                ai_out.channel_priority_adjustment_applied = True
                ai_out.ai_channel_preference_signal = ai.ai_channel_preference_signal
                codes.append("AI_CHANNEL_PREFERENCE_SIGNAL_ADVISORY")
                has_pref = True
    elif ai_tier == AI_STALE:
        codes.append("STALE_AI_CHANNEL_ADVISORY_SKIPPED")
        if gov.execution_mode == "LIVE":
            codes.append("STALE_AI_LIVE_MODE_RESTRICTED")
    elif ai_tier == AI_UNAVAILABLE:
        ai_out.fallback_applied = True
        codes.append("AI_UNAVAILABLE_FALLBACK_APPLIED")
    elif ai_tier == AI_FINALIZED_COPY:
        codes.append("AI_FINALIZED_COPY_NOT_APPLIED")

    # ── RULE 13: Default Advisory Output ─────────────────────────────────────
    path.append("RULE_13")
    if scope_locked:
        scope = scope_locked
    elif len(candidates) == 1:
        scope = f"{candidates[0]}_PREFERRED"
    elif has_pref or ai_out.channel_priority_adjustment_applied:
        scope = f"{candidates[0]}_PREFERRED"
    else:
        scope = SCOPE_MULTI_CHANNEL_ELIGIBLE

    return _emit(ctx, gov, sid, scope, True, path, codes, gc, esc, rr,
                 ai_out, tb, ph, threshold_warnings, degraded, t0,
                 candidates=candidates, prohibited=prohibited)
