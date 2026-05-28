"""
Internal helpers for the governance-safe synchronization orchestration coordination layer.
Not part of the public API. Consumed only by sync.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._sync_types import (
    AUTHORITY_SQL_SERVER,
    K_SYNC_BATCH_SIZE,
    K_SYNC_CONFLICT_THRESHOLD,
    K_SYNC_LAG_ESCALATION_HOURS,
    K_SYNC_MAX_RETRY_ATTEMPTS,
    K_SQL_MAX_SYNC_AGE_HOURS,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    UNKNOWN_V0,
    _REPLAY_TYPES,
    _SYNC_THRESHOLD_KEYS,
    SyncCoordinationRecord,
    SyncOrchestrationContext,
)

logger = logging.getLogger(__name__)

_SYNC_SERVICE_NAME = "sync_orchestration"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event_id() -> str:
    return str(uuid.uuid4())


def emit_sync_event_log(
    record: SyncCoordinationRecord,
) -> None:
    """
    Emit structured coordination log for every synchronization governance evaluation path.
    PII never logged — opaque identifiers only (ABG-1, INV-5).
    Observability never suppressed on any path (spec/06 §1.3).
    """
    is_warn = record.degraded or record.orchestration_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _SYNC_SERVICE_NAME,
        "event": "sync_blocked" if record.orchestration_blocked else "sync_coordinated",
        "event_id": record.event_id,
        "governance_scope": record.governance_scope,
        "sync_intent": record.sync_intent,
        "sync_domain": record.sync_domain,
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
        "sync_blocked_reason": record.sync_blocked_reason,
        "degraded": record.degraded,
        "degradation_cause": record.degradation_cause,
        "degradation_flags": record.degradation_flags,
        "sql_server_read_only_enforced": record.sql_server_read_only_enforced,
        "conflict_preservation_required": record.conflict_preservation_required,
        "finalized_artifacts_protected": record.finalized_artifacts_protected,
        "finalized_artifacts_detected": record.finalized_artifacts_detected,
        "append_only_lineage_preserved": record.append_only_lineage_preserved,
        "authoritative_source": record.authoritative_source,
        "rows_scanned": record.rows_scanned,
        "rows_valid": record.rows_valid,
        "rows_invalid": record.rows_invalid,
        "orchestration_blocked": record.orchestration_blocked,
        "blocking_reason": record.blocking_reason,
        "orchestration_continues": record.orchestration_continues,
        "reason_codes": record.reason_codes,
        "duration_ms": record.duration_ms,
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _make_blocked_record(
    ctx: SyncOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    blocking_reason: Optional[str],
) -> SyncCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return SyncCoordinationRecord(
        governance_scope=SCOPE_UNAVAILABLE,
        sync_intent=None,
        is_replay=ctx.execution_type in _REPLAY_TYPES,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SQL_SERVER,
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
        sync_domain=ctx.sync_domain,
        rows_scanned=ctx.rows_scanned,
        rows_valid=ctx.rows_valid,
        rows_invalid=ctx.rows_invalid,
        dispatch_authorized=False,
        sync_blocked_reason=blocking_reason,
        sql_server_read_only_enforced=True,
        conflict_preservation_required=False,
        finalized_artifacts_protected=True,
        finalized_artifacts_detected=ctx.finalized_artifacts_detected,
        append_only_lineage_preserved=True,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=True,
        blocking_reason=blocking_reason,
        orchestration_continues=False,
    )


def _make_maintenance_record(
    ctx: SyncOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
) -> SyncCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return SyncCoordinationRecord(
        governance_scope=SCOPE_MAINTENANCE,
        sync_intent=None,
        is_replay=False,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SQL_SERVER,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=None,
        threshold_bindings={k: UNKNOWN_V0 for k in _SYNC_THRESHOLD_KEYS},
        event_id=_make_event_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_SUCCESS,    # authorized suppression, not a failure
        error_class=None,
        sync_domain=ctx.sync_domain,
        rows_scanned=0,
        rows_valid=0,
        rows_invalid=0,
        dispatch_authorized=False,
        sync_blocked_reason="MAINTENANCE_MODE_SUSPENDED",
        sql_server_read_only_enforced=True,
        conflict_preservation_required=False,
        finalized_artifacts_protected=True,
        finalized_artifacts_detected=0,
        append_only_lineage_preserved=True,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=False,
    )


def _make_replay_record(
    ctx: SyncOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
) -> SyncCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    source_missing = not ctx.source_artifact_id
    return SyncCoordinationRecord(
        governance_scope=SCOPE_REPLAY_ONLY,
        sync_intent=None,    # no live ingestion intent in replay (INV-4, AP-RT2)
        is_replay=True,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SQL_SERVER,
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
        sync_domain=ctx.sync_domain,
        rows_scanned=ctx.rows_scanned,
        rows_valid=ctx.rows_valid,
        rows_invalid=ctx.rows_invalid,
        dispatch_authorized=False,
        sync_blocked_reason="REPLAY_LIVE_SYNC_PROHIBITED",
        sql_server_read_only_enforced=True,
        conflict_preservation_required=False,
        finalized_artifacts_protected=True,     # FINALIZED never touched by replay
        finalized_artifacts_detected=ctx.finalized_artifacts_detected,
        append_only_lineage_preserved=True,
        degraded=source_missing,
        degradation_flags=["REPLAY_SOURCE_ARTIFACT_MISSING"] if source_missing else [],
        degradation_cause="REPLAY_SOURCE_ARTIFACT_MISSING" if source_missing else None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=True,
    )


def _make_coordination_record(
    ctx: SyncOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    governance_scope: str,
    sync_intent: Optional[str],
    dispatch_authorized: bool,
    sync_blocked_reason: Optional[str],
    conflict_preservation_required: bool,
    degraded: bool,
    degradation_flags: List[str],
    degradation_cause: Optional[str],
    outcome: str,
) -> SyncCoordinationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return SyncCoordinationRecord(
        governance_scope=governance_scope,
        sync_intent=sync_intent,
        is_replay=False,
        live_effects_suppressed=(governance_scope != "AUTHORIZED"),
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SQL_SERVER,
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
        sync_domain=ctx.sync_domain,
        rows_scanned=ctx.rows_scanned,
        rows_valid=ctx.rows_valid,
        rows_invalid=ctx.rows_invalid,
        dispatch_authorized=dispatch_authorized,
        sync_blocked_reason=sync_blocked_reason,
        sql_server_read_only_enforced=True,        # unconditional — FAD-5
        conflict_preservation_required=conflict_preservation_required,
        finalized_artifacts_protected=True,        # unconditional — INV-1, INV-6
        finalized_artifacts_detected=ctx.finalized_artifacts_detected,
        append_only_lineage_preserved=True,        # unconditional — FAD-4
        degraded=degraded,
        degradation_flags=list(degradation_flags),
        degradation_cause=degradation_cause,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=(governance_scope != SCOPE_UNAVAILABLE),
    )
