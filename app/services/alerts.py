"""
Governance-safe degradation observability classification service.

Public API: classify_degradation_alert(ctx: AlertClassificationContext) -> DegradationAlertRecord

Governance prohibitions (AP-FP1, AP-FP2, AP-FP4, AP-FP6, AP-FP7, AP-FP13, AP-FP14):
  - NEVER executes remediation or dispatches operational actions
  - NEVER mutates orchestration state
  - NEVER creates LIVE effects during replay execution
  - NEVER silently suppresses degradation (suppression always visible — AP-FP4)
  - NEVER bypasses attribution lineage (AP-FP6)
  - NEVER mutates immutable alert lineage (AP-FP7)
  - NEVER logs raw PII (AP-FP13); student_id_opaque is opaque handle only
  - NEVER swallows errors silently (AP-FP14)

RULE 0  Governance precondition gate (attribution, correlation, mode/type, replay lineage, idempotency)
RULE 1  Maintenance mode shortcut
RULE 2  Replay / regeneration path (SCOPE_REPLAY_ONLY, no LIVE effects)
RULE 3  Resolve Config V2 thresholds (UNKNOWN_V0 substitution for missing keys)
RULE 4  Classify error class from domain signals
RULE 5  Validate and normalize degradation domain
RULE 6  Classify severity (threshold-driven, UNKNOWN_V0-safe)
RULE 7  Classify recovery action and escalation candidacy
RULE 8  Classify degradation flags and cause
RULE 9  Determine governance scope (SHADOW_ONLY until Phase-12 AUTHORIZED cert)
RULE 10 Build record, emit observability log, return
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services._alert_helpers import (
    _make_alert_record,
    _make_blocked_alert_record,
    _make_maintenance_alert_record,
    _make_replay_alert_record,
    emit_alert_event_log,
)
from app.services._alert_types import (
    ACTION_DEAD_LETTER,
    ACTION_DEGRADED_CONTINUATION,
    ACTION_ESCALATION_CANDIDACY,
    ACTION_GOVERNED_RECOVERY,
    ACTION_NO_OP,
    DOMAIN_AI,
    DOMAIN_ATTRIBUTION,
    DOMAIN_COMPLIANCE,
    DOMAIN_FINGERPRINT,
    DOMAIN_OBSERVABILITY,
    DOMAIN_ORCHESTRATION,
    DOMAIN_PROVIDER,
    DOMAIN_REPLAY,
    DOMAIN_SCHEDULER,
    DOMAIN_SYNCHRONIZATION,
    DOMAIN_UNKNOWN,
    K_AI_ABSENT_CRITICAL_HOURS,
    K_AI_STALE_HIGH_HOURS,
    K_PROVIDER_RETRY_LIMIT,
    K_SCHEDULER_HEARTBEAT_MS,
    K_STUCK_COMPLIANCE_HIGH_HOURS,
    K_STUCK_WORKFLOW_HIGH_HOURS,
    K_SYNC_STALE_HOURS,
    MODE_SHADOW,
    OUTCOME_DEGRADED,
    OUTCOME_SUCCESS,
    REQUIRED_ALERT_ATTRIBUTION,
    SCOPE_SHADOW_ONLY,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    SEVERITY_UNKNOWN,
    UNKNOWN_V0,
    _ALERT_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    _VALID_ALERT_DOMAINS,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    AlertClassificationContext,
    DegradationAlertRecord,
)

logger = logging.getLogger(__name__)

_alert_idempotency_keys: set[str] = set()


def _attribution_complete(ctx: AlertClassificationContext) -> bool:
    return all(getattr(ctx, f, None) for f in REQUIRED_ALERT_ATTRIBUTION)


def _resolve_alert_thresholds(ctx: AlertClassificationContext) -> Dict[str, Any]:
    rule_set = ctx.config_rule_set or {}
    return {key: rule_set.get(key, UNKNOWN_V0) for key in _ALERT_THRESHOLD_KEYS}


def _threshold_value(thresholds: Dict[str, Any], key: str) -> Optional[Any]:
    """Return numeric threshold or None when UNKNOWN_V0 — prevents invalid comparisons."""
    v = thresholds.get(key, UNKNOWN_V0)
    return None if v == UNKNOWN_V0 else v


def _classify_error_class(ctx: AlertClassificationContext) -> Optional[str]:
    if ctx.error_class:
        return ctx.error_class
    return {
        DOMAIN_SCHEDULER: "SchedulerDegradationError",
        DOMAIN_PROVIDER: "ProviderDegradationError",
        DOMAIN_AI: "AIDegradationError",
        DOMAIN_SYNCHRONIZATION: "SynchronizationDegradationError",
        DOMAIN_COMPLIANCE: "ComplianceDegradationError",
        DOMAIN_ORCHESTRATION: "OrchestrationDegradationError",
        DOMAIN_REPLAY: "ReplayDegradationError",
        DOMAIN_ATTRIBUTION: "AttributionDegradationError",
        DOMAIN_OBSERVABILITY: "ObservabilityDegradationError",
        DOMAIN_FINGERPRINT: "FingerprintDegradationError",
    }.get(ctx.degradation_domain or DOMAIN_UNKNOWN)


def _classify_severity(
    ctx: AlertClassificationContext,
    thresholds: Dict[str, Any],
) -> str:
    domain = ctx.degradation_domain or DOMAIN_UNKNOWN

    if domain == DOMAIN_SCHEDULER:
        heartbeat_limit = _threshold_value(thresholds, K_SCHEDULER_HEARTBEAT_MS)
        if ctx.scheduler_lag_ms is not None and heartbeat_limit is not None:
            if ctx.scheduler_lag_ms > heartbeat_limit:
                return SEVERITY_CRITICAL
        stuck_limit = _threshold_value(thresholds, K_STUCK_WORKFLOW_HIGH_HOURS)
        if ctx.workflow_stuck_hours is not None and stuck_limit is not None:
            if ctx.workflow_stuck_hours > stuck_limit:
                return SEVERITY_HIGH
        return SEVERITY_HIGH if ctx.scheduler_lag_ms is not None else SEVERITY_UNKNOWN

    if domain == DOMAIN_SYNCHRONIZATION:
        sync_limit = _threshold_value(thresholds, K_SYNC_STALE_HOURS)
        if ctx.sync_lag_hours is not None and sync_limit is not None:
            if ctx.sync_lag_hours > sync_limit:
                return SEVERITY_HIGH
        return SEVERITY_MEDIUM if ctx.sync_lag_hours is not None else SEVERITY_UNKNOWN

    if domain == DOMAIN_AI:
        absent_limit = _threshold_value(thresholds, K_AI_ABSENT_CRITICAL_HOURS)
        if ctx.ai_absent_hours is not None and absent_limit is not None:
            if ctx.ai_absent_hours > absent_limit:
                return SEVERITY_CRITICAL
        stale_limit = _threshold_value(thresholds, K_AI_STALE_HIGH_HOURS)
        if ctx.ai_stale_hours is not None and stale_limit is not None:
            if ctx.ai_stale_hours > stale_limit:
                return SEVERITY_HIGH
        has_signal = ctx.ai_stale_hours is not None or ctx.ai_absent_hours is not None
        return SEVERITY_MEDIUM if has_signal else SEVERITY_UNKNOWN

    if domain == DOMAIN_PROVIDER:
        if ctx.circuit_breaker_open:
            return SEVERITY_CRITICAL
        if ctx.provider_outage_active:
            return SEVERITY_HIGH
        retry_limit = _threshold_value(thresholds, K_PROVIDER_RETRY_LIMIT)
        if ctx.retry_count is not None and retry_limit is not None:
            if ctx.retry_count >= retry_limit:
                return SEVERITY_HIGH
        return SEVERITY_MEDIUM if ctx.retry_count is not None else SEVERITY_UNKNOWN

    if domain == DOMAIN_COMPLIANCE:
        if ctx.compliance_hold_active:
            compliance_stuck_limit = _threshold_value(thresholds, K_STUCK_COMPLIANCE_HIGH_HOURS)
            if ctx.workflow_stuck_hours is not None and compliance_stuck_limit is not None:
                if ctx.workflow_stuck_hours > compliance_stuck_limit:
                    return SEVERITY_CRITICAL
            return SEVERITY_HIGH
        return SEVERITY_UNKNOWN

    if domain == DOMAIN_ORCHESTRATION:
        stuck_limit = _threshold_value(thresholds, K_STUCK_WORKFLOW_HIGH_HOURS)
        if ctx.workflow_stuck_hours is not None and stuck_limit is not None:
            if ctx.workflow_stuck_hours > stuck_limit:
                return SEVERITY_HIGH
        return SEVERITY_HIGH  # orchestration domain always at least HIGH

    if domain == DOMAIN_OBSERVABILITY:
        return SEVERITY_MEDIUM if ctx.is_observability_degraded else SEVERITY_UNKNOWN

    if domain == DOMAIN_ATTRIBUTION:
        return SEVERITY_HIGH  # attribution degradation always HIGH

    if domain == DOMAIN_FINGERPRINT:
        return SEVERITY_MEDIUM if ctx.fingerprint_divergence else SEVERITY_UNKNOWN

    if domain == DOMAIN_REPLAY:
        return SEVERITY_INFO

    return SEVERITY_UNKNOWN


def _classify_recovery_action(
    severity: str,
    domain: str,
    ctx: AlertClassificationContext,  # noqa: ARG001 — reserved for future domain signals
) -> str:
    if severity == SEVERITY_CRITICAL:
        if domain == DOMAIN_SCHEDULER:
            return ACTION_GOVERNED_RECOVERY
        if domain == DOMAIN_COMPLIANCE:
            return ACTION_DEAD_LETTER
        return ACTION_ESCALATION_CANDIDACY
    if severity == SEVERITY_HIGH:
        if domain in (DOMAIN_PROVIDER, DOMAIN_AI, DOMAIN_OBSERVABILITY):
            return ACTION_DEGRADED_CONTINUATION
        return ACTION_ESCALATION_CANDIDACY
    if domain in (DOMAIN_OBSERVABILITY, DOMAIN_AI):
        return ACTION_DEGRADED_CONTINUATION
    return ACTION_NO_OP


def _classify_degradation_state(
    ctx: AlertClassificationContext,
    domain: str,
) -> Tuple[bool, List[str], Optional[str]]:
    flags: List[str] = []
    if domain == DOMAIN_SCHEDULER and ctx.scheduler_lag_ms is not None:
        flags.append("SCHEDULER_HEARTBEAT_MISSED")
    if domain == DOMAIN_SYNCHRONIZATION and ctx.sync_lag_hours is not None:
        flags.append("SYNC_STALE")
    if domain == DOMAIN_AI and ctx.ai_absent_hours is not None:
        flags.append("AI_ABSENT")
    if domain == DOMAIN_AI and ctx.ai_stale_hours is not None:
        flags.append("AI_STALE")
    if domain == DOMAIN_PROVIDER and ctx.circuit_breaker_open:
        flags.append("CIRCUIT_BREAKER_OPEN")
    if domain == DOMAIN_PROVIDER and ctx.provider_outage_active:
        flags.append("PROVIDER_OUTAGE")
    if domain == DOMAIN_PROVIDER and ctx.retry_count is not None:
        flags.append("PROVIDER_RETRY_EXHAUSTED")
    if domain == DOMAIN_COMPLIANCE and ctx.compliance_hold_active:
        flags.append("COMPLIANCE_HOLD_ACTIVE")
    if domain == DOMAIN_FINGERPRINT and ctx.fingerprint_divergence:
        flags.append("FINGERPRINT_DIVERGENCE")
    if domain == DOMAIN_OBSERVABILITY and ctx.is_observability_degraded:
        flags.append("OBSERVABILITY_DEGRADED")
    if domain == DOMAIN_ATTRIBUTION:
        flags.append("ATTRIBUTION_DEGRADED")
    if ctx.workflow_stuck_hours is not None:
        flags.append("WORKFLOW_STUCK")
    return bool(flags), flags, (flags[0] if flags else None)


def _governance_precondition_gate(
    ctx: AlertClassificationContext,
    rule_path: List[str],
    t0: float,
) -> Tuple[Optional[DegradationAlertRecord], List[str]]:
    codes: List[str] = []
    rule_path.append("RULE_0_GOVERNANCE_GATE")

    if not _attribution_complete(ctx):
        codes.append("ATTRIBUTION_INCOMPLETE")
    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
    if ctx.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append("INVALID_EXECUTION_MODE")
    if ctx.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append("INVALID_EXECUTION_TYPE")
    if ctx.execution_type in _REPLAY_TYPES and not ctx.historical_config_version_id:
        codes.append("REPLAY_LINEAGE_INCOMPLETE")
    if ctx.idempotency_key and ctx.idempotency_key in _alert_idempotency_keys:
        codes.append("IDEMPOTENCY_KEY_DUPLICATE")

    if codes:
        blocking_reason = "; ".join(codes)
        record = _make_blocked_alert_record(ctx, codes, rule_path, t0, blocking_reason)
        emit_alert_event_log(record)
        return record, codes

    if ctx.idempotency_key:
        _alert_idempotency_keys.add(ctx.idempotency_key)

    return None, []


def classify_degradation_alert(
    ctx: AlertClassificationContext,
) -> DegradationAlertRecord:
    """
    Classify a degradation condition and return a governance-safe alert record.
    Pure classification — no remediation, no orchestration mutation, no side effects
    other than structured observability emission.
    """
    t0 = time.monotonic()
    rule_path: List[str] = []

    # RULE 0 — Governance precondition gate
    blocked, _ = _governance_precondition_gate(ctx, rule_path, t0)
    if blocked is not None:
        return blocked

    codes: List[str] = []

    # RULE 1 — Maintenance mode shortcut
    if ctx.maintenance_mode_active:
        rule_path.append("RULE_1_MAINTENANCE")
        codes.append("MAINTENANCE_MODE_ACTIVE")
        record = _make_maintenance_alert_record(ctx, codes, rule_path, t0)
        emit_alert_event_log(record)
        return record

    # RULE 2 — Replay / regeneration path (no LIVE effects — INV-4, AP-FP2)
    if ctx.execution_type in _REPLAY_TYPES:
        rule_path.append("RULE_2_REPLAY")
        codes.append("REPLAY_EXECUTION_TYPE")
        thresholds = _resolve_alert_thresholds(ctx)
        record = _make_replay_alert_record(ctx, codes, rule_path, t0, thresholds)
        emit_alert_event_log(record)
        return record

    # RULE 3 — Resolve Config V2 thresholds (UNKNOWN_V0 for missing keys)
    rule_path.append("RULE_3_THRESHOLD_RESOLUTION")
    thresholds = _resolve_alert_thresholds(ctx)

    # RULE 4 — Classify error class from domain signals
    rule_path.append("RULE_4_ERROR_CLASS")
    classified_error = _classify_error_class(ctx)

    # RULE 5 — Validate and normalize degradation domain
    rule_path.append("RULE_5_DOMAIN_VALIDATION")
    domain = ctx.degradation_domain or DOMAIN_UNKNOWN
    if domain not in _VALID_ALERT_DOMAINS:
        domain = DOMAIN_UNKNOWN
        codes.append("DOMAIN_UNKNOWN")

    # RULE 6 — Classify severity (threshold-driven, UNKNOWN_V0-safe)
    rule_path.append("RULE_6_SEVERITY")
    severity = _classify_severity(ctx, thresholds)
    codes.append(f"SEVERITY_{severity}")

    # RULE 7 — Classify recovery action and escalation candidacy
    rule_path.append("RULE_7_RECOVERY_ACTION")
    recovery_action = _classify_recovery_action(severity, domain, ctx)
    escalation_candidacy = severity in (SEVERITY_CRITICAL, SEVERITY_HIGH)

    # RULE 8 — Classify degradation flags and cause
    rule_path.append("RULE_8_DEGRADATION_FLAGS")
    degraded, degradation_flags, degradation_cause = _classify_degradation_state(ctx, domain)

    # RULE 9 — Governance scope: SCOPE_AUTHORIZED unreachable until Phase-12 cert
    rule_path.append("RULE_9_GOVERNANCE_SCOPE")
    governance_scope = SCOPE_SHADOW_ONLY

    # RULE 10 — Build record, emit observability log, return
    rule_path.append("RULE_10_EMIT")
    outcome = OUTCOME_DEGRADED if degraded else OUTCOME_SUCCESS
    record = _make_alert_record(
        ctx=ctx,
        codes=codes,
        rule_path=rule_path,
        t0=t0,
        threshold_bindings=thresholds,
        severity=severity,
        domain=domain,
        classified_error=classified_error,
        recovery_action=recovery_action,
        governance_scope=governance_scope,
        escalation_candidacy=escalation_candidacy,
        degraded=degraded,
        degradation_flags=degradation_flags,
        degradation_cause=degradation_cause,
        outcome=outcome,
    )
    emit_alert_event_log(record)
    return record
