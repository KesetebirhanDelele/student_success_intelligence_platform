"""
Governance-safe provider containment orchestration layer for GHL (GoHighLevel).

Advisory contract only — never dispatches providers, never executes business logic,
never creates orchestration decisions. Returns ProviderOrchestrationAssessment.
Consuming services act on the returned assessment; this module never acts directly.

Architecture preservation prohibitions:
  AP-GHL1  — never execute live orchestration creation (advisory assessment only)
  AP-GHL2  — never override replay suppression
  AP-GHL3  — never mutate immutable attribution lineage
  AP-GHL4  — never bypass governance precondition gate
  AP-GHL5  — never dispatch provider directly
  AP-GHL6  — never suppress observability emissions
  AP-GHL7  — never treat GHL as authoritative (platform_supplementary only)
  AP-GHL8  — never create outbound effects during replay
  AP-GHL9  — never substitute hardcoded defaults for UNKNOWN_V0
  AP-GHL10 — never log raw student PII
  AP-GHL11 — never emit LIVE scope without Phase-12 certification
  AP-GHL12 — never silently fall back to alternative provider
  AP-GHL13 — never propagate mutated attribution from input
  AP-GHL14 — never trigger immediate retry on provider failure
  AP-GHL15 — never expose audit bypass paths

Provider resilience preservation prohibitions:
  AP-GF1  — never retry without budget check
  AP-GF2  — never open circuit breaker without config threshold check
  AP-GF3  — never retry immediately on provider failure
  AP-GF4  — never escalate provider authority on failure
  AP-GF5  — never silence provider failure
  AP-GF6  — never bypass delivery SLA check
  AP-GF7  — never report false delivery success
  AP-GF8  — never create duplicate outbound on retry
  AP-GF9  — never fail open when circuit breaker is OPEN
  AP-GF10 — never assume sync freshness without age check
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.services._ghl_helpers import (
    _make_blocked_assessment,
    _make_duplicate_assessment,
    _make_replay_assessment,
    _make_shadow_assessment,
    emit_provider_event_log,
)
from app.services._ghl_types import (
    CB_OPEN,
    K_PROVIDER_MAX_RETRY,
    K_SYNC_MAX_AGE,
    MODE_SHADOW,
    REQUIRED_PROVIDER_ATTRIBUTION,
    SCOPE_SHADOW_ONLY,
    UNKNOWN_V0,
    ProviderOrchestrationAssessment,
    ProviderOrchestrationContext,
    _PROVIDER_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    _VALID_PROVIDER_MODES,
    _VALID_TYPES,
)

logger = logging.getLogger(__name__)

# In-memory idempotency store for outbound deduplication (AP-GF8)
_outbound_idempotency_keys: set[str] = set()


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _attribution_complete(ctx: ProviderOrchestrationContext) -> bool:
    """Returns True only if all required provider attribution fields are populated."""
    return all(getattr(ctx, field, None) for field in REQUIRED_PROVIDER_ATTRIBUTION)


def _governance_scope_for_mode(execution_mode: str) -> str:
    """
    Provider-layer governance scope mapping.
    LIVE scope requires Phase-12 certification — currently SHADOW_ONLY (AP-GHL11).
    """
    if execution_mode == MODE_SHADOW:
        return SCOPE_SHADOW_ONLY
    return SCOPE_SHADOW_ONLY  # LIVE scope gated on Phase-12 cert — AP-GHL11


def _resolve_provider_thresholds(
    rule_set: Dict[str, Any],
    missing_keys: List[str],
) -> Dict[str, Any]:
    """
    Resolve Config V2 Group F thresholds from rule_set.
    Missing or UNKNOWN_V0 inputs resolve to UNKNOWN_V0 sentinel — never hardcoded (AP-GHL9).
    """
    result: Dict[str, Any] = {}
    for k in _PROVIDER_THRESHOLD_KEYS:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def _governance_precondition_gate(
    ctx: ProviderOrchestrationContext,
    codes: List[str],
) -> bool:
    """
    RULE 0: Governance precondition gate. All conditions must pass before evaluation
    proceeds. Never bypassed (AP-GHL4, AP-GHL15).
    Returns True if all preconditions pass; False if orchestration must stop.
    """
    ok = True
    if ctx.execution_mode not in _VALID_PROVIDER_MODES:
        codes.append("INVALID_EXECUTION_MODE")
        ok = False
    if ctx.execution_type not in _VALID_TYPES:
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
    return ok


# ── Public advisory API ───────────────────────────────────────────────────────

def assess_provider_orchestration(
    ctx: ProviderOrchestrationContext,
) -> ProviderOrchestrationAssessment:
    """
    Evaluate provider orchestration governance for a GHL interaction.

    Advisory contract: returns ProviderOrchestrationAssessment only.
    Never dispatches, never mutates state, never creates orchestration decisions (AP-GHL1, AP-GHL5).
    Attribution propagated immutably from input (AP-GHL3, AP-GHL13).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    rule_set = ctx.config_rule_set or {}

    # ── RULE 0: Governance precondition gate (AP-GHL4, AP-GHL15) ─────────────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        assessment = _make_blocked_assessment(
            ctx, codes, rule_path, t0, {},
            None, gate_codes[0] if gate_codes else "PRECONDITION_FAILED",
        )
        emit_provider_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 1: Replay containment (AP-GHL2, AP-GHL8) ────────────────────────
    rule_path.append("RULE_1")
    if ctx.execution_type in _REPLAY_TYPES:
        codes.append("REPLAY_OUTBOUND_SUPPRESSED")
        assessment = _make_replay_assessment(ctx, codes, rule_path, t0)
        emit_provider_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # Resolve Config V2 Group F thresholds once — referenced by RULES 3, 5, 7, 10
    missing_threshold_keys: List[str] = []
    threshold_bindings = _resolve_provider_thresholds(rule_set, missing_threshold_keys)

    # ── RULE 2: Compliance hold ───────────────────────────────────────────────
    rule_path.append("RULE_2")
    if ctx.compliance_hold_active:
        codes.append("COMPLIANCE_HOLD_ACTIVE")
        assessment = _make_blocked_assessment(
            ctx, codes, rule_path, t0, threshold_bindings,
            "compliance_hold", "COMPLIANCE_HOLD_ACTIVE",
        )
        emit_provider_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 3: Circuit breaker state (AP-GF2, AP-GF9) ───────────────────────
    rule_path.append("RULE_3")
    if ctx.circuit_breaker_state == CB_OPEN:
        codes.append("CIRCUIT_BREAKER_OPEN")
        assessment = _make_blocked_assessment(
            ctx, codes, rule_path, t0, threshold_bindings,
            "circuit_breaker_open", "CIRCUIT_BREAKER_OPEN",
        )
        emit_provider_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 4: Provider outage — degradation marker, not a hard block ────────
    rule_path.append("RULE_4")
    degraded = False
    degradation_cause: Optional[str] = None
    if ctx.provider_outage_active:
        codes.append("PROVIDER_OUTAGE_ACTIVE")
        degraded = True
        degradation_cause = "provider_outage"

    # ── RULE 5: Sync lag check (AP-GF10) ─────────────────────────────────────
    rule_path.append("RULE_5")
    sync_max_age = threshold_bindings.get(K_SYNC_MAX_AGE, UNKNOWN_V0)
    if sync_max_age == UNKNOWN_V0:
        codes.append("SYNC_MAX_AGE_UNKNOWN")
    else:
        try:
            if ctx.sync_lag_hours > float(sync_max_age):
                codes.append("SYNC_LAG_EXCEEDED")
                if not degraded:
                    degraded = True
                    degradation_cause = "sync_lag_exceeded"
        except (TypeError, ValueError):
            codes.append("SYNC_MAX_AGE_INVALID")

    # ── RULE 6: Shadow mode containment — suppress all outbound (AP-GHL11) ───
    rule_path.append("RULE_6")
    if ctx.execution_mode == MODE_SHADOW:
        codes.append("SHADOW_OUTBOUND_SUPPRESSED")
        assessment = _make_shadow_assessment(
            ctx, codes, rule_path, t0, threshold_bindings, degraded, degradation_cause,
        )
        emit_provider_event_log(assessment, ctx.student_id_opaque)
        return assessment

    # ── RULE 7: Retry budget check (AP-GF1, AP-GF3) ──────────────────────────
    rule_path.append("RULE_7")
    max_retry = threshold_bindings.get(K_PROVIDER_MAX_RETRY, UNKNOWN_V0)
    if max_retry != UNKNOWN_V0:
        try:
            if ctx.retry_attempt_count >= int(max_retry):
                codes.append("RETRY_BUDGET_EXHAUSTED")
                assessment = _make_blocked_assessment(
                    ctx, codes, rule_path, t0, threshold_bindings,
                    None, "RETRY_BUDGET_EXHAUSTED",
                )
                emit_provider_event_log(assessment, ctx.student_id_opaque)
                return assessment
        except (TypeError, ValueError):
            codes.append("MAX_RETRY_VALUE_INVALID")

    # ── RULE 9: Idempotency deduplication for outbound (AP-GF8) ──────────────
    rule_path.append("RULE_9")
    if ctx.idempotency_key:
        if ctx.idempotency_key in _outbound_idempotency_keys:
            codes.append("IDEMPOTENCY_DUPLICATE_SUPPRESSED")
            assessment = _make_duplicate_assessment(ctx, codes, rule_path, t0, threshold_bindings)
            emit_provider_event_log(assessment, ctx.student_id_opaque)
            return assessment
        _outbound_idempotency_keys.add(ctx.idempotency_key)

    # ── RULE 10: Config threshold degradation accumulation (AP-GHL9) ─────────
    rule_path.append("RULE_10")
    if missing_threshold_keys:
        for k in missing_threshold_keys:
            codes.append(f"CONFIG_THRESHOLD_MISSING_{k.upper()}")
        if not degraded:
            degraded = True
            degradation_cause = "config_thresholds_missing"

    # ── RULE 11: Authorization decision (AP-GHL11) ────────────────────────────
    # Phase-12 certification required for LIVE outbound scope — currently SHADOW_ONLY.
    # When Phase-12 cert is granted, this rule returns SCOPE_AUTHORIZED with
    # outbound_suppressed=False for LIVE mode. Implementation gated until then.
    rule_path.append("RULE_11")
    codes.append("LIVE_SCOPE_SHADOW_ONLY_PHASE11")
    assessment = _make_shadow_assessment(
        ctx, codes, rule_path, t0, threshold_bindings, degraded, degradation_cause,
    )
    emit_provider_event_log(assessment, ctx.student_id_opaque)
    return assessment
