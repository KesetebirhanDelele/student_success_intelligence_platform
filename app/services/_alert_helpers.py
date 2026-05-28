"""
Internal helpers for the governance-safe degradation observability classification layer.
Not part of the public API. Consumed only by alerts.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._alert_types import (
    ACTION_DEAD_LETTER,
    ACTION_NO_OP,
    BASIS_FALLBACK,
    BASIS_HISTORICAL_REPLAY,
    BASIS_RULE_BASED,
    DOMAIN_UNKNOWN,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    SEVERITY_INFO,
    SEVERITY_UNKNOWN,
    UNKNOWN_V0,
    _ALERT_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    AlertClassificationContext,
    DegradationAlertRecord,
)

logger = logging.getLogger(__name__)

_ALERT_SERVICE_NAME = "degradation_observability"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_alert_id() -> str:
    return str(uuid.uuid4())


def emit_alert_event_log(record: DegradationAlertRecord) -> None:
    """
    Emit structured degradation observability log for every classification path.
    PII never logged — opaque identifiers only (AP-FP13, spec/06 §12.1).
    Observability never suppressed on any path (AP-FP4, AP-FP14).
    """
    is_warn = record.degraded or record.orchestration_blocked or record.severity in ("CRITICAL", "HIGH")
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _ALERT_SERVICE_NAME,
        "event": "alert_blocked" if record.orchestration_blocked else "alert_classified",
        "alert_id": record.alert_id,
        "severity": record.severity,
        "degradation_domain": record.degradation_domain,
        "failure_cause": record.failure_cause,
        "error_class_classified": record.error_class_classified,
        "recovery_action": record.recovery_action,
        "escalation_candidacy": record.escalation_candidacy,
        "governance_scope": record.governance_scope,
        "assessment_basis": record.assessment_basis,
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
        "degraded": record.degraded,
        "degradation_cause": record.degradation_cause,
        "degradation_flags": record.degradation_flags,
        "orchestration_blocked": record.orchestration_blocked,
        "blocking_reason": record.blocking_reason,
        "orchestration_continues": record.orchestration_continues,
        "reason_codes": record.reason_codes,
        "suppression_visible": record.suppression_visible,
        "causation_chain_preserved": record.causation_chain_preserved,
        "append_only_enforced": record.append_only_enforced,
        "replay_lineage_preserved": record.replay_lineage_preserved,
        "alert_lineage_immutable": record.alert_lineage_immutable,
        "alert_emit_authorized": record.alert_emit_authorized,
        "duration_ms": record.duration_ms,
        # student_id_opaque not logged — callers embed it in their correlation context
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _make_blocked_alert_record(
    ctx: AlertClassificationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    blocking_reason: Optional[str],
) -> DegradationAlertRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return DegradationAlertRecord(
        severity=SEVERITY_UNKNOWN,
        degradation_domain=ctx.degradation_domain or DOMAIN_UNKNOWN,
        failure_cause=ctx.failure_cause,
        error_class_classified="GovernancePreconditionError",
        recovery_action=ACTION_DEAD_LETTER,
        escalation_candidacy=False,
        governance_scope=SCOPE_UNAVAILABLE,
        assessment_basis=BASIS_RULE_BASED,
        is_replay=ctx.execution_type in _REPLAY_TYPES,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=ctx.historical_config_version_id,
        threshold_bindings={k: UNKNOWN_V0 for k in _ALERT_THRESHOLD_KEYS},
        alert_id=_make_alert_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_FAILURE,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=True,
        blocking_reason=blocking_reason,
        orchestration_continues=False,
        suppression_visible=True,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        replay_lineage_preserved=True,
        alert_lineage_immutable=True,
        alert_emit_authorized=False,
        student_id_opaque=ctx.student_id_opaque,
    )


def _make_maintenance_alert_record(
    ctx: AlertClassificationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
) -> DegradationAlertRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return DegradationAlertRecord(
        severity=SEVERITY_INFO,
        degradation_domain=ctx.degradation_domain or DOMAIN_UNKNOWN,
        failure_cause=ctx.failure_cause,
        error_class_classified=None,
        recovery_action=ACTION_NO_OP,
        escalation_candidacy=False,
        governance_scope=SCOPE_MAINTENANCE,
        assessment_basis=BASIS_RULE_BASED,
        is_replay=False,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=None,
        threshold_bindings={k: UNKNOWN_V0 for k in _ALERT_THRESHOLD_KEYS},
        alert_id=_make_alert_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_SUCCESS,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=False,
        suppression_visible=True,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        replay_lineage_preserved=True,
        alert_lineage_immutable=True,
        alert_emit_authorized=False,
        student_id_opaque=ctx.student_id_opaque,
    )


def _make_replay_alert_record(
    ctx: AlertClassificationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
) -> DegradationAlertRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    source_missing = not ctx.source_artifact_id
    return DegradationAlertRecord(
        severity=SEVERITY_UNKNOWN,    # no live severity in replay — INV-4, AP-FP2
        degradation_domain=ctx.degradation_domain or DOMAIN_UNKNOWN,
        failure_cause=ctx.failure_cause,
        error_class_classified=None,
        recovery_action=ACTION_NO_OP,
        escalation_candidacy=False,   # no live escalation from replay
        governance_scope=SCOPE_REPLAY_ONLY,
        assessment_basis=BASIS_HISTORICAL_REPLAY,
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
        alert_id=_make_alert_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_DEGRADED if source_missing else OUTCOME_SUCCESS,
        degraded=source_missing,
        degradation_flags=["REPLAY_SOURCE_ARTIFACT_MISSING"] if source_missing else [],
        degradation_cause="REPLAY_SOURCE_ARTIFACT_MISSING" if source_missing else None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=True,    # authorized suppression — replay continues
        suppression_visible=True,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        replay_lineage_preserved=True,   # IML-3 — replay alerts always preserved
        alert_lineage_immutable=True,
        alert_emit_authorized=False,
        student_id_opaque=ctx.student_id_opaque,
    )


def _make_alert_record(
    ctx: AlertClassificationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    severity: str,
    domain: str,
    classified_error: Optional[str],
    recovery_action: str,
    governance_scope: str,
    escalation_candidacy: bool,
    degraded: bool,
    degradation_flags: List[str],
    degradation_cause: Optional[str],
    outcome: str,
) -> DegradationAlertRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return DegradationAlertRecord(
        severity=severity,
        degradation_domain=domain,
        failure_cause=ctx.failure_cause,
        error_class_classified=classified_error,
        recovery_action=recovery_action,
        escalation_candidacy=escalation_candidacy,
        governance_scope=governance_scope,
        assessment_basis=BASIS_CONFIG_GOVERNED if threshold_bindings else BASIS_FALLBACK,
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
        alert_id=_make_alert_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=outcome,
        degraded=degraded,
        degradation_flags=list(degradation_flags),
        degradation_cause=degradation_cause,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=(governance_scope != SCOPE_UNAVAILABLE),
        suppression_visible=True,        # unconditional — AP-FP4; suppression never silent
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,       # unconditional — FAD-4
        replay_lineage_preserved=True,   # unconditional — IML-3
        alert_lineage_immutable=True,    # unconditional — IML-1
        alert_emit_authorized=False,     # Phase-12 cert required
        student_id_opaque=ctx.student_id_opaque,
    )


# Re-export for alerts.py import convenience
from app.services._alert_types import BASIS_CONFIG_GOVERNED  # noqa: E402
