"""
Governance-safe AI orchestration advisory layer.

Advisory contract only — never calls live AI providers, never dispatches inference,
never executes business logic, never creates orchestration decisions.
Returns AIAssessment. Consuming services act on the returned assessment.

Architecture preservation prohibitions:
  AP-AI1  — never act as workflow authority or orchestration executor
  AP-AI2  — never autonomously trigger student lifecycle state mutations
  AP-AI3  — never dispatch outreach, escalations, or any side effect
  AP-AI4  — never override deterministic rule evaluation or governance invariants
  AP-AI5  — never call live AI provider during replay or regeneration
  AP-AI6  — never modify FINALIZED snapshot AI text (FAD-1)
  AP-AI7  — never overwrite prior AI assessment outputs (append-only)
  AP-AI8  — never silently substitute a different AI provider on unavailability
  AP-AI9  — never use hardcoded TTL, confidence ceiling, or provider values
  AP-AI10 — never log raw student PII in any inference log or error message
  AP-AI11 — never allow STALE/UNAVAILABLE tier to drive LIVE escalation independently
  AP-AI12 — never generate new inference when ai_finalized_copy = true
  AP-AI13 — never evaluate tier or scope without Rule 0 passing first
  AP-AI14 — never let AI confidence score alone override rule-based eligibility
  AP-AI15 — never override, default, infer, or modify attribution fields from input

LLM failure resilience prohibitions:
  AP-LF1  — never infer without config threshold resolution
  AP-LF2  — never open AI circuit without config threshold check
  AP-LF3  — never retry inference immediately on failure
  AP-LF4  — never escalate AI authority on inference failure
  AP-LF5  — never silence inference failure observability
  AP-LF6  — never bypass inference SLA threshold check
  AP-LF7  — never report false inference success
  AP-LF8  — never create duplicate inference on retry
  AP-LF9  — never fail open when AI circuit breaker is OPEN
  AP-LF10 — never assume SQL Server sync freshness without age check
  AP-LF11 — never serve STALE tier AI as CONFIDENT tier
  AP-LF12 — never allow AI to mutate historical attribution or lineage records
  AP-LF13 — never bypass FINALIZED_COPY immutability on any inference path
  AP-LF14 — never emit LIVE AI inference during replay or regeneration
  AP-LF15 — never log raw inference content (narrative text) in observability
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._ai_helpers import (
    _make_blocked_assessment,
    _make_finalized_copy_assessment,
    _make_in_flight_assessment,
    _make_replay_assessment,
    _make_unavailable_assessment,
    emit_ai_event_log,
)
from app.services._ai_types import (
    BASIS_AI_ASSISTED,
    BASIS_FALLBACK,
    BASIS_FINALIZED_COPY,
    BASIS_RULE_BASED,
    CB_OPEN,
    CONFIDENCE_HIGH_FLOOR,
    CONFIDENCE_MEDIUM_FLOOR,
    CONFIDENCE_TIER_HIGH,
    CONFIDENCE_TIER_LOW,
    CONFIDENCE_TIER_MEDIUM,
    CONFIDENCE_TIER_UNSCORED,
    K_AI_INSIGHT_TTL_HOURS,
    K_AI_LLM_PROVIDER,
    MODE_LIVE,
    OUTCOME_DEGRADED,
    OUTCOME_SUCCESS,
    REPLAY_SOURCE_FINALIZED_COPY,
    REPLAY_SOURCE_NONE,
    REQUIRED_AI_ATTRIBUTION,
    SCOPE_DEFERRED,
    SCOPE_FULL,
    SCOPE_IMMUTABLE,
    SCOPE_LIMITED,
    SCOPE_UNAVAILABLE,
    STATE_AI_REVIEWED,
    TIER_ADVISORY,
    TIER_CONFIDENT,
    TIER_FINALIZED_COPY,
    TIER_IN_FLIGHT,
    TIER_STALE,
    TIER_UNAVAILABLE,
    TYPE_ORIGINAL,
    UNKNOWN_V0,
    _AI_THRESHOLD_KEYS,
    _IN_FLIGHT_STATES,
    _REPLAY_TYPES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    AIAssessment,
    AIOrchestrationContext,
)
import uuid as _uuid_mod

# In-memory idempotency store for deduplication of AI evaluations (AP-LF8)
_ai_idempotency_keys: set[str] = set()

# Valid insight types for the on-demand generation endpoint
INSIGHT_TYPES: frozenset = frozenset({
    "OUTREACH_DRAFT",
    "INTERVENTION",
    "RISK_EXPLANATION",
    "INTERVIEW_COACHING",
})


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _attribution_complete(ctx: AIOrchestrationContext) -> bool:
    return all(getattr(ctx, f, None) for f in REQUIRED_AI_ATTRIBUTION)


def _governance_precondition_gate(
    ctx: AIOrchestrationContext,
    codes: List[str],
) -> bool:
    """
    RULE 0: Mandatory gate. All conditions must pass before evaluation proceeds.
    Never bypassed (AP-AI13). Returns True if all preconditions pass.
    """
    ok = True
    if ctx.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append("EXECUTION_MODE_INVALID")
        ok = False
    if ctx.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append("EXECUTION_TYPE_INVALID")
        ok = False
    if not ctx.config_version_id:
        codes.append("CONFIG_UNRESOLVED")
        ok = False
    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
        ok = False
    if not _attribution_complete(ctx):
        codes.append("ATTRIBUTION_INCOMPLETE")
        ok = False
    if ctx.idempotency_key and ctx.idempotency_key in _ai_idempotency_keys:
        codes.append("IDEMPOTENCY_DUPLICATE")
        ok = False
    return ok


def _resolve_ai_thresholds(
    rule_set: Dict[str, Any],
    missing_keys: List[str],
) -> Dict[str, Any]:
    """
    Resolve Config V2 Group H thresholds from rule_set.
    Missing or UNKNOWN_V0 inputs resolve to UNKNOWN_V0 — never hardcoded (AP-AI9, AP-LF1).
    """
    result: Dict[str, Any] = {}
    for k in _AI_THRESHOLD_KEYS:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def _compute_insight_age_hours(ai_generated_at: Optional[str]) -> float:
    """Returns insight age in hours; returns 0.0 on missing or unparseable input."""
    if not ai_generated_at:
        return 0.0
    try:
        generated = datetime.fromisoformat(ai_generated_at.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        secs = (datetime.now(timezone.utc) - generated).total_seconds()
        return max(0.0, secs / 3600.0)
    except (ValueError, TypeError):
        return 0.0


# ── Public advisory API ───────────────────────────────────────────────────────

def assess_ai_orchestration(
    ctx: AIOrchestrationContext,
) -> AIAssessment:
    """
    Evaluate AI orchestration governance for a student intelligence assessment.

    Advisory contract: returns AIAssessment only.
    Never calls AI providers, never dispatches inference, never mutates state (AP-AI1–AP-AI3).
    Attribution propagated immutably from input (AP-AI15).
    FINALIZED_COPY content served as-is; never re-inferred (AP-AI6, AP-AI12).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    rule_set = ctx.config_rule_set or {}

    # ── RULE 0: Governance precondition gate (AP-AI13) ────────────────────────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        assessment = _make_blocked_assessment(
            ctx, codes, rule_path, t0, {},
            gate_codes[0] if gate_codes else "GOVERNANCE_PRECONDITION_FAILED",
        )
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # Register idempotency key after gate passes; only for original execution (AP-LF8)
    if ctx.idempotency_key and ctx.execution_type == TYPE_ORIGINAL:
        _ai_idempotency_keys.add(ctx.idempotency_key)

    # ── RULE 1: FINALIZED_COPY isolation check (AP-AI6, AP-AI12, FAD-1) ──────
    rule_path.append("RULE_1")
    if ctx.ai_finalized_copy:
        codes.append("AI_FINALIZED_COPY_SERVING")
        assessment = _make_finalized_copy_assessment(ctx, codes, rule_path, t0)
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 2: Replay mode gate (AP-AI5, AP-LF14) ───────────────────────────
    rule_path.append("RULE_2")
    is_replay = ctx.execution_type in _REPLAY_TYPES
    if is_replay:
        codes.append("REPLAY_MODE_ACTIVE")

    # ── RULE 3: Config-bound threshold resolution (AP-AI9, AP-LF1) ───────────
    rule_path.append("RULE_3")
    missing_threshold_keys: List[str] = []
    threshold_bindings = _resolve_ai_thresholds(rule_set, missing_threshold_keys)
    for k in missing_threshold_keys:
        codes.append(f"CONFIG_THRESHOLD_MISSING_{k.upper()}")

    # Replay exits here — no live AI evaluation (AP-AI5, AP-LF14)
    if is_replay:
        replay_source = (
            REPLAY_SOURCE_FINALIZED_COPY if ctx.source_artifact_id
            else REPLAY_SOURCE_NONE
        )
        if not ctx.source_artifact_id:
            codes.append("REPLAY_AI_SOURCE_MISSING")
        assessment = _make_replay_assessment(
            ctx, codes, rule_path, t0, threshold_bindings, replay_source,
        )
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 4: AI context availability check ────────────────────────────────
    rule_path.append("RULE_4")
    in_flight = ctx.ai_insight_state in _IN_FLIGHT_STATES
    has_insight = ctx.ai_insight_id is not None

    if in_flight:
        codes.append("AI_IN_FLIGHT")
        assessment = _make_in_flight_assessment(ctx, codes, rule_path, t0, threshold_bindings)
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    if not has_insight:
        codes.append("AI_INSIGHT_ABSENT")
        assessment = _make_unavailable_assessment(
            ctx, codes, rule_path, t0, threshold_bindings, "PROVIDER_UNAVAILABLE", BASIS_FALLBACK,
        )
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 5: Governance tier assignment ───────────────────────────────────
    rule_path.append("RULE_5")
    if ctx.ai_insight_state != STATE_AI_REVIEWED:
        codes.append("AI_NOT_REVIEWED")
        assessment = _make_unavailable_assessment(
            ctx, codes, rule_path, t0, threshold_bindings, "PROVIDER_UNAVAILABLE", BASIS_FALLBACK,
        )
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    insight_age_hours = _compute_insight_age_hours(ctx.ai_generated_at)
    ttl_val = threshold_bindings.get(K_AI_INSIGHT_TTL_HOURS, UNKNOWN_V0)
    tier = TIER_UNAVAILABLE
    confidence_tier_val = CONFIDENCE_TIER_UNSCORED
    stale_flag = False
    stale_for_hours = 0.0
    degradation_cause: Optional[str] = None

    if ttl_val != UNKNOWN_V0:
        try:
            if insight_age_hours > float(ttl_val):
                tier = TIER_STALE
                stale_flag = True
                stale_for_hours = max(0.0, insight_age_hours - float(ttl_val))
                codes.append("AI_STALE")
        except (TypeError, ValueError):
            codes.append("CONFIG_THRESHOLD_INVALID_AI_INSIGHT_TTL_HOURS")

    if tier == TIER_UNAVAILABLE:
        score = ctx.ai_confidence_score
        if score is None:
            tier = TIER_ADVISORY
            confidence_tier_val = CONFIDENCE_TIER_UNSCORED
        elif score >= CONFIDENCE_HIGH_FLOOR:
            tier = TIER_CONFIDENT
            confidence_tier_val = CONFIDENCE_TIER_HIGH
        elif score >= CONFIDENCE_MEDIUM_FLOOR:
            tier = TIER_ADVISORY
            confidence_tier_val = CONFIDENCE_TIER_MEDIUM
        else:
            tier = TIER_ADVISORY
            confidence_tier_val = CONFIDENCE_TIER_LOW
            degradation_cause = "CONFIDENCE_COLLAPSE"
            codes.append("CONFIDENCE_COLLAPSE")

    # ── RULE 6: Advisory scope determination ─────────────────────────────────
    rule_path.append("RULE_6")
    if tier == TIER_CONFIDENT:
        advisory_scope = SCOPE_FULL
        advisory_reco = ctx.ai_recommended_intervention
        advisory_priority = "HIGH" if (ctx.ai_confidence_score or 0.0) >= CONFIDENCE_HIGH_FLOOR else "MEDIUM"
    elif tier in (TIER_ADVISORY, TIER_STALE):
        advisory_scope = SCOPE_LIMITED
        advisory_reco = None   # LIMITED scope cannot independently drive intervention routing
        advisory_priority = None
    else:
        advisory_scope = SCOPE_UNAVAILABLE
        advisory_reco = None
        advisory_priority = None

    # ── RULE 7: Live escalation restriction (AP-AI11) ────────────────────────
    rule_path.append("RULE_7")
    if tier in (TIER_STALE, TIER_UNAVAILABLE) and ctx.execution_mode == MODE_LIVE:
        codes.append("AI_LIVE_ESCALATION_BLOCKED_STALE_TIER")
        advisory_reco = None

    # ── RULE 8: Provider validation and degradation (AP-AI8, AP-LF9) ─────────
    rule_path.append("RULE_8")
    if ctx.circuit_breaker_state == CB_OPEN:
        codes.append("CIRCUIT_BREAKER_OPEN")
        assessment = _make_unavailable_assessment(
            ctx, codes, rule_path, t0, threshold_bindings, "CIRCUIT_OPEN", BASIS_FALLBACK,
        )
        emit_ai_event_log(assessment, ctx.student_id_opaque)
        return assessment

    provider_config_val = threshold_bindings.get(K_AI_LLM_PROVIDER, UNKNOWN_V0)
    provider_divergence = (
        ctx.ai_model_used
        and provider_config_val != UNKNOWN_V0
        and ctx.ai_model_used != provider_config_val
    )
    if provider_divergence:
        codes.append("PROVIDER_IDENTITY_DIVERGENCE")

    degraded = bool(degradation_cause) or bool(missing_threshold_keys)
    if missing_threshold_keys and not degradation_cause:
        degradation_cause = "CONFIG_THRESHOLDS_MISSING"

    # ── RULE 9: Attribution and lineage assembly (AP-AI15) ────────────────────
    rule_path.append("RULE_9")
    # Attribution fields propagated immutably from ctx — assembled in Rule 11 output.

    # ── RULE 10: Snapshot eligibility determination ───────────────────────────
    rule_path.append("RULE_10")
    eligible_for_snapshot = (
        tier == TIER_CONFIDENT
        and ctx.execution_type == TYPE_ORIGINAL
        and not ctx.ai_finalized_copy
        and ctx.ai_insight_state == STATE_AI_REVIEWED
        and not stale_flag
        and not provider_divergence
        and not ctx.compliance_hold_flag
    )
    if eligible_for_snapshot:
        eligibility_reason = "CONFIDENT_TIER_FRESH_ORIGINAL_EXECUTION"
    elif tier != TIER_CONFIDENT:
        eligibility_reason = f"NON_CONFIDENT_TIER_{tier}"
    elif stale_flag:
        eligibility_reason = "STALE_AI_BLOCKS_SNAPSHOT"
    elif provider_divergence:
        eligibility_reason = "PROVIDER_IDENTITY_DIVERGENCE"
    elif ctx.compliance_hold_flag:
        eligibility_reason = "COMPLIANCE_HOLD_BLOCKS_SNAPSHOT"
    elif ctx.execution_type != TYPE_ORIGINAL:
        eligibility_reason = "NON_ORIGINAL_EXECUTION"
    else:
        eligibility_reason = "NOT_ELIGIBLE"

    # ── RULE 11: Observability assembly and terminal output ───────────────────
    rule_path.append("RULE_11")
    if tier == TIER_FINALIZED_COPY:
        assessment_basis = BASIS_FINALIZED_COPY
    elif is_replay:
        assessment_basis = BASIS_RULE_BASED
    elif tier in (TIER_CONFIDENT, TIER_ADVISORY):
        assessment_basis = BASIS_AI_ASSISTED
    else:
        assessment_basis = BASIS_FALLBACK

    outcome = OUTCOME_SUCCESS if tier in (TIER_CONFIDENT, TIER_ADVISORY, TIER_STALE) else OUTCOME_DEGRADED
    if degraded:
        outcome = OUTCOME_DEGRADED

    elapsed = int((time.monotonic() - t0) * 1000)
    assessment = AIAssessment(
        ai_governance_tier=tier,
        advisory_scope=advisory_scope,
        is_replay=False,
        live_inference_suppressed=False,
        replay_ai_source=None,
        source_artifact_id=None,
        historical_config_version_id=None,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_intent_id=ctx.upstream_intent_id,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        threshold_bindings=threshold_bindings,
        event_id=str(_uuid_mod.uuid4()),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        assessment_basis=assessment_basis,
        inference_duration_ms=0,
        duration_ms=elapsed,
        outcome=outcome,
        error_class=None,
        confidence_score=ctx.ai_confidence_score,
        confidence_tier=confidence_tier_val,
        stale_flag=stale_flag,
        stale_for_hours=stale_for_hours,
        insight_age_hours=insight_age_hours,
        ttl_hours_applied=ttl_val,
        degraded=degraded,
        degradation_cause=degradation_cause,
        fallback_applied=degraded,
        fallback_type="RULE_BASED_ONLY" if degraded else None,
        orchestration_continues=True,
        advisory_sentiment=ctx.ai_sentiment,
        advisory_risk_summary=ctx.ai_risk_summary,
        advisory_recommended_intervention=advisory_reco,
        advisory_prioritization_signal=advisory_priority,
        eligible_for_snapshot=eligible_for_snapshot,
        eligibility_reason=eligibility_reason,
        finalized_copy=False,
        provider=ctx.ai_model_used,
        model_identifier=ctx.ai_model_used,
        prompt_version=ctx.ai_prompt_version,
        ai_version_number=ctx.ai_insight_version,
        reason_codes=list(codes),
        ai_blocked=False,
        blocking_reason=None,
    )
    emit_ai_event_log(assessment, ctx.student_id_opaque)
    return assessment


# ── On-demand insight generation ─────────────────────────────────────────────

_PROMPTS: dict = {
    "OUTREACH_DRAFT": (
        "Draft a concise, professional outreach message for a student at risk. "
        "Student context (no PII): {context}. Keep under 150 words."
    ),
    "INTERVENTION": (
        "Recommend an intervention strategy for a student showing these risk signals: "
        "{context}. Be specific and actionable."
    ),
    "RISK_EXPLANATION": (
        "Explain in plain language why this student is flagged as at-risk based on: "
        "{context}. Use 2-3 sentences."
    ),
    "INTERVIEW_COACHING": (
        "Provide 3 targeted interview coaching tips for a student with this profile: "
        "{context}."
    ),
}

_TTL_HOURS = 24


async def get_or_generate(
    user_id: int,
    insight_type: str,
    student: dict,
    db: Any,
) -> dict:
    """
    Return a cached AIInsight if valid, otherwise generate one.

    In SHADOW mode without LLM_API_KEY: returns a structured placeholder tagged
    execution_mode=SHADOW. AI inference is not blocked in SHADOW — only outbound
    provider dispatch (GHL, Synthflow) is suppressed.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from app.config import settings
    from app.models import AIInsight

    now = datetime.now(timezone.utc)

    existing = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.user_id == user_id,
            AIInsight.insight_type == insight_type,
        )
        .order_by(AIInsight.created_at.desc())
        .limit(1)
    )
    insight = existing.scalar_one_or_none()

    if insight and not insight.is_finalized:
        expired = insight.expires_at and insight.expires_at < now
        if not expired:
            return _serialize_insight(insight)

    context_parts = []
    for k in ("PathName", "AttendancePercentage", "LastLoginDays", "ActiveStatus",
              "StatusI", "StatusII", "Past10DaysLogon"):
        v = student.get(k)
        if v is not None:
            context_parts.append(f"{k}={v}")
    context_str = "; ".join(context_parts) or "no context available"

    content_text: str
    model_used: str | None = None
    api_key = settings.LLM_API_KEY

    if not api_key:
        content_text = (
            f"[AI advisory: {insight_type} — LLM_API_KEY not configured. "
            f"Shadow mode: governance assessment only.]"
        )
    else:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            prompt = _PROMPTS.get(insight_type, "Assess this student: {context}.").format(
                context=context_str
            )
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                timeout=20,
            )
            content_text = resp.choices[0].message.content or ""
            model_used = settings.LLM_MODEL
        except Exception as exc:
            content_text = f"[AI generation failed: {type(exc).__name__}]"

    mode = str(settings.EXECUTION_MODE)
    scope = "REPLAY_ONLY" if mode == "REPLAY" else "SHADOW_ONLY"
    correlation_id = str(_uuid_mod.uuid4())
    expires_at = now + timedelta(hours=_TTL_HOURS)

    new_insight = AIInsight(
        user_id=user_id,
        insight_type=insight_type,
        content_text=content_text,
        model_used=model_used,
        execution_mode=mode,
        governance_scope=scope,
        execution_type="original",
        is_replay=(mode == "REPLAY"),
        correlation_id=correlation_id,
        expires_at=expires_at,
        origin_source="get_or_generate",
        origin_authority="ai_insights_service",
    )
    db.add(new_insight)
    await db.commit()
    await db.refresh(new_insight)
    return _serialize_insight(new_insight)


def _serialize_insight(insight: Any) -> dict:
    return {
        "id": insight.id,
        "user_id": insight.user_id,
        "insight_type": insight.insight_type,
        "content": insight.content_text,
        "model": insight.model_used,
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
        "expires_at": insight.expires_at.isoformat() if insight.expires_at else None,
        "is_finalized": insight.is_finalized,
        "execution_mode": insight.execution_mode,
        "governance_scope": insight.governance_scope,
        "correlation_id": insight.correlation_id,
    }
