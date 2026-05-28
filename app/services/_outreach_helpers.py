"""
Internal helpers for the governance-safe outreach orchestration coordination layer.
Not part of the public API. Consumed only by outreach.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._outreach_types import (
    K_ORCHESTRATION_CONCURRENCY_LIMIT,
    K_OUTREACH_MAX_RETRY_ATTEMPTS,
    K_OUTREACH_RETRY_WINDOW_DAYS,
    K_AI_INSIGHT_TTL_HOURS,
    K_SQL_MAX_SYNC_AGE_HOURS,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    UNKNOWN_V0,
    _ORCHESTRATION_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    OutreachCoordinationRecord,
    OutreachOrchestrationContext,
)

logger = logging.getLogger(__name__)

_OUTREACH_SERVICE_NAME = "outreach_orchestration"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event_id() -> str:
    return str(uuid.uuid4())


def emit_orchestration_event_log(
    record: OutreachCoordinationRecord,
    student_id_opaque: Optional[str],
) -> None:
    """
    Emit structured coordination log for every governance evaluation path.
    PII never logged — opaque student ID only (AP-RT13, AP-DF13, AP-RF13).
    Observability never suppressed on any path (AP-RT15, AP-DF15, AP-RF15).
    """
    is_warn = record.degraded or record.orchestration_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _OUTREACH_SERVICE_NAME,
        "event": "orchestration_blocked" if record.orchestration_blocked else "orchestration_coordinated",
        "event_id": record.event_id,
        "governance_scope": record.governance_scope,
        "intent_type": record.intent_type,
        "is_replay": record.is_replay,
        "live_effects_suppressed": record.live_effects_suppressed,
        "execution_mode": record.execution_mode,
        "execution_type": record.execution_type,
        "correlation_id": record.correlation_id,
        "causation_id": record.causation_id,
        "orchestration_cycle_id": record.orchestration_cycle_id,
        "config_version_id": record.config_version_id,
        "rule_path_taken": record.rule_path_taken,
        "outcome": record.outcome,
        "error_class": record.error_class,
        "dispatch_authorized": record.dispatch_authorized,
        "dispatch_blocked_reason": record.dispatch_blocked_reason,
        "degraded": record.degraded,
        "degradation_cause": record.degradation_cause,
        "degradation_flags": record.degradation_flags,
        "escalation_candidate": record.escalation_candidate,
        "escalation_candidacy_reason": record.escalation_candidacy_reason,
        "compliance_hold_active": record.compliance_hold_active,
        "ai_governance_tier": record.ai_governance_tier,
        "ai_escalation_authority": record.ai_escalation_authority,
        "stale_sql_server_data": record.stale_sql_server_data,
        "orchestration_blocked": record.orchestration_blocked,
        "blocking_reason": record.blocking_reason,
        "orchestration_continues": record.orchestration_continues,
        "reason_codes": record.reason_codes,
        "duration_ms": record.duration_ms,
        "student_id_opaque": student_id_opaque,
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _make_blocked_record(
    ctx: OutreachOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    blocking_reason: Optional[str],
) -> OutreachCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return OutreachCoordinationRecord(
        governance_scope=SCOPE_UNAVAILABLE,
        intent_type=None,
        is_replay=ctx.execution_type in _REPLAY_TYPES,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=ctx.historical_config_version_id,
        threshold_bindings=threshold_bindings,
        event_id=_make_event_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_FAILURE,
        error_class="GovernancePreconditionError",
        student_id_opaque=ctx.student_id_opaque,
        checkpoint_type=ctx.checkpoint_type,
        contact_attempt_count=ctx.contact_attempt_count,
        dispatch_authorized=False,
        dispatch_blocked_reason=blocking_reason,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        escalation_candidate=False,
        escalation_candidacy_reason=None,
        compliance_hold_active=False,
        ai_governance_tier=ctx.ai_governance_tier,
        ai_escalation_authority=False,
        stale_sql_server_data=False,
        reason_codes=list(codes),
        orchestration_blocked=True,
        blocking_reason=blocking_reason,
        orchestration_continues=False,
    )


def _make_maintenance_record(
    ctx: OutreachOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
) -> OutreachCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return OutreachCoordinationRecord(
        governance_scope=SCOPE_MAINTENANCE,
        intent_type=None,
        is_replay=False,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=None,
        threshold_bindings={k: UNKNOWN_V0 for k in _ORCHESTRATION_THRESHOLD_KEYS},
        event_id=_make_event_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_SUCCESS,   # authorized suppression, not a failure
        error_class=None,
        student_id_opaque=ctx.student_id_opaque,
        checkpoint_type=ctx.checkpoint_type,
        contact_attempt_count=ctx.contact_attempt_count,
        dispatch_authorized=False,
        dispatch_blocked_reason="MAINTENANCE_MODE_SUSPENDED",
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        escalation_candidate=False,
        escalation_candidacy_reason=None,
        compliance_hold_active=False,
        ai_governance_tier=None,
        ai_escalation_authority=False,
        stale_sql_server_data=False,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=False,
    )


def _make_replay_record(
    ctx: OutreachOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
) -> OutreachCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    source_missing = not ctx.source_artifact_id
    return OutreachCoordinationRecord(
        governance_scope=SCOPE_REPLAY_ONLY,
        intent_type=None,   # no live intent in replay — historical simulation only (AP-RT2)
        is_replay=True,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=ctx.historical_config_version_id,
        threshold_bindings=threshold_bindings,
        event_id=_make_event_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_DEGRADED if source_missing else OUTCOME_SUCCESS,
        error_class=None,
        student_id_opaque=ctx.student_id_opaque,
        checkpoint_type=ctx.checkpoint_type,
        contact_attempt_count=ctx.contact_attempt_count,
        dispatch_authorized=False,
        dispatch_blocked_reason="REPLAY_LIVE_DISPATCH_PROHIBITED",
        degraded=source_missing,
        degradation_flags=["REPLAY_SOURCE_ARTIFACT_MISSING"] if source_missing else [],
        degradation_cause="REPLAY_SOURCE_ARTIFACT_MISSING" if source_missing else None,
        escalation_candidate=False,
        escalation_candidacy_reason=None,
        compliance_hold_active=ctx.compliance_hold_flag,
        ai_governance_tier=ctx.ai_governance_tier,
        ai_escalation_authority=False,   # no live AI escalation authority in replay
        stale_sql_server_data=False,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=True,
    )


def _make_coordination_record(
    ctx: OutreachOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    governance_scope: str,
    intent_type: Optional[str],
    dispatch_authorized: bool,
    dispatch_blocked_reason: Optional[str],
    degraded: bool,
    degradation_flags: List[str],
    degradation_cause: Optional[str],
    escalation_candidate: bool,
    escalation_candidacy_reason: Optional[str],
    compliance_hold_active: bool,
    ai_governance_tier: Optional[str],
    ai_escalation_authority: bool,
    stale_sql_server_data: bool,
    outcome: str,
) -> OutreachCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return OutreachCoordinationRecord(
        governance_scope=governance_scope,
        intent_type=intent_type,
        is_replay=False,
        live_effects_suppressed=(governance_scope != "AUTHORIZED"),
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=ctx.historical_config_version_id,
        threshold_bindings=threshold_bindings,
        event_id=_make_event_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=outcome,
        error_class=None,
        student_id_opaque=ctx.student_id_opaque,
        checkpoint_type=ctx.checkpoint_type,
        contact_attempt_count=ctx.contact_attempt_count,
        dispatch_authorized=dispatch_authorized,
        dispatch_blocked_reason=dispatch_blocked_reason,
        degraded=degraded,
        degradation_flags=list(degradation_flags),
        degradation_cause=degradation_cause,
        escalation_candidate=escalation_candidate,
        escalation_candidacy_reason=escalation_candidacy_reason,
        compliance_hold_active=compliance_hold_active,
        ai_governance_tier=ai_governance_tier,
        ai_escalation_authority=ai_escalation_authority,
        stale_sql_server_data=stale_sql_server_data,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=(governance_scope != SCOPE_UNAVAILABLE),
    )
