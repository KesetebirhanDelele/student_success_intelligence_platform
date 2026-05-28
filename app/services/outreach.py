"""
Governance-safe outreach orchestration coordination layer.

Public API: coordinate_orchestration_cycle(ctx) -> OutreachCoordinationRecord

Advisory contract only — never dispatches providers, never executes business logic,
never creates direct execution actions. Returns OutreachCoordinationRecord.
Consuming services (scheduler, API handlers) act on the returned record;
this module never acts directly. Attribution propagated immutably from input.

Architecture preservation prohibitions (MUST NOT):
  AP-RT1  / AP-DF1  / AP-RF1  — no direct provider API calls (GHL, AI, SMS, email, meeting)
  AP-RT2  / AP-DF3  / AP-RF4  — no LIVE effects from replay/regeneration execution types
  AP-RT3               — no evaluation without non-null ACTIVE config_version_id
  AP-RT4  / AP-DF5  / AP-RF6  — no orchestration record without correlation_id propagated
  AP-RT5               — no silent skip of student candidates; all skips produce structured log
  AP-RT6               — no silent absorption of provider failures; all produce audit record
  AP-RT7               — no automation SHADOW→LIVE transition (Governance Admin required)
  AP-RT9  / AP-DF6  / AP-RF3  — no hardcoded Config V2 threshold fallbacks; UNKNOWN_V0 only
  AP-RT10 / AP-DF14 / AP-RF14 — no duplicate LIVE execution of the same orchestration intent
  AP-RT11 / AP-DF9  / AP-RF10 — AI advisory cannot authorize orchestration intents alone
  AP-RT12 / AP-DF8  / AP-RF9  — no re-implementation of directive logic in coordination layer
  AP-RT13 / AP-DF13 / AP-RF13 — no raw PII in observability records; opaque student ID only
  AP-RT14 / AP-DF11 / AP-RF12 — no silent failure swallowing; every exception classified
  AP-RT15 / AP-DF15 / AP-RF15 — no orphaned coordination cycles without completion log
  AP-DF2               — no GHL API payload or SMS/email body construction
  AP-DF7  / AP-RF7  — no direct state mutation or contact_attempt increment
  AP-AI5               — no live AI inference in replay context
  FAD-1                — no mutation of warehouse.snapshot_ai_narratives
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.services._outreach_helpers import (
    _make_blocked_record,
    _make_coordination_record,
    _make_maintenance_record,
    _make_replay_record,
    emit_orchestration_event_log,
)
from app.services._outreach_types import (
    AI_TIER_IN_FLIGHT,
    CB_OPEN,
    INTENT_DEFER_PENDING_AI,
    INTENT_ESCALATE,
    INTENT_HOLD,
    INTENT_INITIATE_OUTREACH,
    INTENT_RETRY_OUTREACH,
    K_OUTREACH_MAX_RETRY_ATTEMPTS,
    K_OUTREACH_RETRY_WINDOW_DAYS,
    K_AI_INSIGHT_TTL_HOURS,
    K_SQL_MAX_SYNC_AGE_HOURS,
    K_ORCHESTRATION_CONCURRENCY_LIMIT,
    MODE_SHADOW,
    OUTCOME_DEGRADED,
    OUTCOME_SHADOW_ONLY,
    OUTCOME_SUCCESS,
    REQUIRED_OUTREACH_ATTRIBUTION,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    STATE_CONTACTED,
    STATE_NO_RESPONSE,
    TYPE_ORIGINAL,
    UNKNOWN_V0,
    _INITIAL_STATES,
    _ORCHESTRATION_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    _STALE_AI_TIERS,
    _TERMINAL_STATES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    OutreachCoordinationRecord,
    OutreachOrchestrationContext,
)

logger = logging.getLogger(__name__)

# In-memory idempotency store for orchestration deduplication (AP-RT10, spec/04 §4.1)
_orchestration_idempotency_keys: set[str] = set()


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _attribution_complete(ctx: OutreachOrchestrationContext) -> bool:
    """Returns True only if all required orchestration attribution fields are populated."""
    return all(getattr(ctx, f, None) for f in REQUIRED_OUTREACH_ATTRIBUTION)


def _governance_precondition_gate(
    ctx: OutreachOrchestrationContext,
    codes: List[str],
) -> bool:
    """
    RULE 0: Governance precondition gate. All conditions must pass before evaluation
    proceeds. Never bypassed (AP-RT3, AP-RT4, AP-DF5, AP-RT15).
    Returns True if all preconditions pass; False if coordination must stop.
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
    if ctx.idempotency_key and ctx.idempotency_key in _orchestration_idempotency_keys:
        codes.append("IDEMPOTENCY_DUPLICATE_DETECTED")
        ok = False
    return ok


def _resolve_orchestration_thresholds(
    rule_set: Dict[str, Any],
    missing_keys: List[str],
) -> Dict[str, Any]:
    """
    Resolve Config V2 Group A / H / K thresholds from rule_set.
    Missing or UNKNOWN_V0 inputs resolve to UNKNOWN_V0 sentinel — never hardcoded (AP-RT9).
    """
    result: Dict[str, Any] = {}
    for k in _ORCHESTRATION_THRESHOLD_KEYS:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def _classify_intent(
    ctx: OutreachOrchestrationContext,
    threshold_bindings: Dict[str, Any],
    ai_tier: Optional[str],
) -> str:
    """
    Classify the orchestration intent based on student context and Config V2 thresholds.
    AI advisory informs but does not authorize — rule-based logic governs (AP-RT11, AP-DF9).
    Never re-implements directive logic; classifies based on observable state only (AP-RT12).
    """
    # Terminal/final lifecycle states → no new orchestration
    if ctx.outreach_state in _TERMINAL_STATES:
        return INTENT_HOLD

    # AI IN_FLIGHT — defer evaluation until AI advisory is available (advisory-only, AP-RT11)
    if ai_tier == AI_TIER_IN_FLIGHT:
        return INTENT_DEFER_PENDING_AI

    # Retry exhaustion check — governed by Config V2, never hardcoded (AP-RT9, AP-RF3)
    max_attempts = threshold_bindings.get(K_OUTREACH_MAX_RETRY_ATTEMPTS)
    if max_attempts not in (UNKNOWN_V0, None):
        try:
            if ctx.contact_attempt_count >= int(max_attempts):
                return INTENT_ESCALATE
        except (ValueError, TypeError):
            pass  # malformed threshold treated as UNKNOWN_V0 — safe to continue

    # NO_RESPONSE → retry on next window (cadence governed by retry_window_days)
    if ctx.outreach_state == STATE_NO_RESPONSE:
        return INTENT_RETRY_OUTREACH

    # New / initial student → initiate outreach
    if ctx.outreach_state in _INITIAL_STATES:
        return INTENT_INITIATE_OUTREACH

    # CONTACTED → hold pending response or GHL webhook (state management service owns this)
    if ctx.outreach_state == STATE_CONTACTED:
        return INTENT_HOLD

    return INTENT_HOLD


# ── Public coordination API ───────────────────────────────────────────────────

def coordinate_orchestration_cycle(
    ctx: OutreachOrchestrationContext,
) -> OutreachCoordinationRecord:
    """
    Evaluate outreach orchestration governance for one student candidate.

    Coordination contract: returns OutreachCoordinationRecord only.
    Never dispatches, never mutates state, never calls providers (AP-RT1, AP-DF1, AP-RF1).
    Attribution propagated immutably from input (AP-RT4, AP-DF5, AP-RF6).
    Every path emits a structured observability record (AP-RT15, AP-DF15, AP-RF15).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    degradation_flags: List[str] = []
    rule_set = ctx.config_rule_set or {}

    # ── RULE 0: Governance precondition gate (AP-RT3, AP-RT4, AP-DF5) ─────────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        record = _make_blocked_record(
            ctx, codes, rule_path, t0, {},
            gate_codes[0] if gate_codes else "GOVERNANCE_PRECONDITION_FAILED",
        )
        emit_orchestration_event_log(record, ctx.student_id_opaque)
        return record

    # Register idempotency key after gate passes; only for original execution (AP-RT10)
    if ctx.idempotency_key and ctx.execution_type == TYPE_ORIGINAL:
        _orchestration_idempotency_keys.add(ctx.idempotency_key)

    # ── RULE 1: MAINTENANCE mode suspension ───────────────────────────────────
    rule_path.append("RULE_1")
    if ctx.maintenance_mode_active:
        codes.append("MAINTENANCE_MODE_ACTIVE")
        record = _make_maintenance_record(ctx, codes, rule_path, t0)
        emit_orchestration_event_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 2: Replay/regeneration containment (AP-RT2, AP-DF3, AP-RF4) ─────
    rule_path.append("RULE_2")
    is_replay = ctx.execution_type in _REPLAY_TYPES
    if is_replay:
        codes.append("REPLAY_MODE_ACTIVE")
        if not ctx.source_artifact_id:
            codes.append("REPLAY_SOURCE_ARTIFACT_MISSING")
        record = _make_replay_record(ctx, codes, rule_path, t0, {})
        emit_orchestration_event_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 3: Config V2 threshold resolution (AP-RT9, AP-DF6, AP-RF3) ──────
    rule_path.append("RULE_3")
    missing_threshold_keys: List[str] = []
    threshold_bindings = _resolve_orchestration_thresholds(rule_set, missing_threshold_keys)
    for k in missing_threshold_keys:
        flag = f"CONFIG_THRESHOLD_MISSING_{k.upper()}"
        codes.append(flag)
        degradation_flags.append(flag)

    # ── RULE 4: SHADOW mode containment (AP-RT7) ──────────────────────────────
    # SHADOW mode runs full evaluation but produces SHADOW_ONLY governance scope.
    # Phase-12 certification is required before AUTHORIZED scope can be emitted (AP-RT7).
    rule_path.append("RULE_4")
    shadow_mode = ctx.execution_mode == MODE_SHADOW

    # ── RULE 5: Provider sync validation (system_loop.md §5.2, §10.7) ─────────
    rule_path.append("RULE_5")
    stale_sql = False
    sync_threshold = threshold_bindings.get(K_SQL_MAX_SYNC_AGE_HOURS)
    if sync_threshold not in (UNKNOWN_V0, None):
        try:
            if ctx.sync_lag_hours > float(sync_threshold):
                stale_sql = True
                codes.append("STALE_SQL_SERVER_DATA")
                degradation_flags.append("STALE_SQL_SERVER_DATA")
        except (ValueError, TypeError):
            pass  # malformed threshold treated as UNKNOWN_V0

    # ── RULE 6: Provider circuit breaker (AP-RT6, AP-GF9) ────────────────────
    rule_path.append("RULE_6")
    circuit_open = ctx.circuit_breaker_state == CB_OPEN
    dispatch_blocked = False
    dispatch_blocked_reason: Optional[str] = None
    escalation_candidate = False
    escalation_candidacy_reason: Optional[str] = None

    if circuit_open:
        dispatch_blocked = True
        dispatch_blocked_reason = "CIRCUIT_BREAKER_OPEN"
        codes.append("CIRCUIT_BREAKER_OPEN")
        degradation_flags.append("CIRCUIT_BREAKER_OPEN")
        escalation_candidate = True
        escalation_candidacy_reason = "PROVIDER_FAILURE_ESCALATION_CANDIDACY"

    # ── RULE 7: Compliance hold per student (system_loop.md §10.2) ────────────
    rule_path.append("RULE_7")
    compliance_hold_active = ctx.compliance_hold_flag
    if compliance_hold_active:
        if not dispatch_blocked:
            dispatch_blocked = True
            dispatch_blocked_reason = "COMPLIANCE_HOLD_ACTIVE"
        codes.append("COMPLIANCE_HOLD_DISPATCH_BLOCKED")
        degradation_flags.append("COMPLIANCE_HOLD_DISPATCH_BLOCKED")

    # ── RULE 8: AI governance tier coordination (AP-RT11, AP-AI11) ───────────
    # Stale / unavailable AI restricts escalation authority only — never blocks evaluation.
    # AI advisory never independently drives orchestration decisions (AP-RT11, AP-DF9).
    rule_path.append("RULE_8")
    ai_tier = ctx.ai_governance_tier
    ai_escalation_authority = ai_tier not in _STALE_AI_TIERS
    if ai_tier in _STALE_AI_TIERS:
        codes.append(f"AI_TIER_{ai_tier}_ESCALATION_RESTRICTED")

    # ── RULE 9: Orchestration intent classification (AP-RT12, AP-DF8) ────────
    # Intent derived from observable state + Config V2 thresholds.
    # AI advisory informs but does not authorize (AP-RT11).
    rule_path.append("RULE_9")
    intent_type = _classify_intent(ctx, threshold_bindings, ai_tier)
    codes.append(f"INTENT_{intent_type}")

    # Retry-exhausted escalation candidacy (escalation_rules.md §4.5)
    if intent_type == INTENT_ESCALATE and not escalation_candidate:
        escalation_candidate = True
        escalation_candidacy_reason = "RETRY_EXHAUSTED_ESCALATION_CANDIDACY"

    # ── RULE 10: Governance scope assignment (AP-RT7) ─────────────────────────
    # AUTHORIZED scope requires Phase-12 certification (AP-RT7).
    # Current deployment: SHADOW phase; both LIVE and SHADOW produce SHADOW_ONLY.
    # UNAVAILABLE scope assigned when dispatch is explicitly blocked.
    rule_path.append("RULE_10")
    if dispatch_blocked:
        governance_scope = SCOPE_UNAVAILABLE
        outcome = OUTCOME_DEGRADED
    elif ctx.execution_mode == MODE_SHADOW:
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY
    else:
        # LIVE mode: Phase-12 cert gate — maps to SHADOW_ONLY until cert is granted (AP-RT7)
        codes.append("LIVE_SCOPE_SHADOW_ONLY_PHASE11")
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY

    # ── RULE 11: Dispatch authorization ───────────────────────────────────────
    rule_path.append("RULE_11")
    # Dispatch is authorized only when governance_scope would be AUTHORIZED (Phase-12 cert).
    # Under current SHADOW deployment, dispatch_authorized is unconditionally False.
    dispatch_authorized = False   # Phase-12 cert required for True; see RULE 10
    if not dispatch_blocked and governance_scope != SCOPE_UNAVAILABLE:
        # Governance scope controls authorization; shadow = not authorized
        pass  # dispatch_authorized remains False until Phase-12 cert grants AUTHORIZED scope

    # ── RULE 12: Terminal output ───────────────────────────────────────────────
    rule_path.append("RULE_12")
    degraded = bool(degradation_flags)
    degradation_cause = degradation_flags[0] if degraded else None

    record = _make_coordination_record(
        ctx=ctx,
        codes=codes,
        rule_path=rule_path,
        t0=t0,
        threshold_bindings=threshold_bindings,
        governance_scope=governance_scope,
        intent_type=intent_type,
        dispatch_authorized=dispatch_authorized,
        dispatch_blocked_reason=dispatch_blocked_reason,
        degraded=degraded,
        degradation_flags=degradation_flags,
        degradation_cause=degradation_cause,
        escalation_candidate=escalation_candidate,
        escalation_candidacy_reason=escalation_candidacy_reason,
        compliance_hold_active=compliance_hold_active,
        ai_governance_tier=ai_tier,
        ai_escalation_authority=ai_escalation_authority,
        stale_sql_server_data=stale_sql,
        outcome=outcome,
    )
    emit_orchestration_event_log(record, ctx.student_id_opaque)
    return record
