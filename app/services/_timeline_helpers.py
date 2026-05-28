"""
Internal helpers for the governance-safe timeline lineage service.
Not part of the public API. Consumed only by timeline.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._timeline_types import (
    AUTHORITY_SYSTEM,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    UNKNOWN_V0,
    VISIBILITY_REPLAY_ONLY,
    VISIBILITY_SHADOW_VISIBLE,
    _REPLAY_TYPES,
    _TIMELINE_THRESHOLD_KEYS,
    TimelineEventContext,
    TimelineLineageRecord,
)

logger = logging.getLogger(__name__)

_TIMELINE_SERVICE_NAME = "timeline_lineage"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event_id() -> str:
    return str(uuid.uuid4())


def emit_timeline_event_log(record: TimelineLineageRecord) -> None:
    """
    Emit structured lineage log for every timeline governance evaluation path.
    PII never logged — opaque identifiers only (AP-RT13, INV-5).
    Observability never suppressed on any path (spec/06 §1.3).
    """
    is_warn = record.degraded or record.orchestration_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _TIMELINE_SERVICE_NAME,
        "event": "timeline_blocked" if record.orchestration_blocked else "timeline_classified",
        "event_id": record.event_id,
        "governance_scope": record.governance_scope,
        "event_type": record.event_type,
        "lineage_visibility": record.lineage_visibility,
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
        "lineage_emit_authorized": record.lineage_emit_authorized,
        "causation_chain_preserved": record.causation_chain_preserved,
        "append_only_enforced": record.append_only_enforced,
        "finalized_lineage_protected": record.finalized_lineage_protected,
        "replay_lineage_preserved": record.replay_lineage_preserved,
        "sql_server_authority_preserved": record.sql_server_authority_preserved,
        "authoritative_source": record.authoritative_source,
        "execution_state_before": record.execution_state_before,
        "execution_state_after": record.execution_state_after,
        "degraded": record.degraded,
        "degradation_cause": record.degradation_cause,
        "degradation_flags": record.degradation_flags,
        "orchestration_blocked": record.orchestration_blocked,
        "blocking_reason": record.blocking_reason,
        "orchestration_continues": record.orchestration_continues,
        "reason_codes": record.reason_codes,
        "duration_ms": record.duration_ms,
        # student_id_opaque is not logged here — callers embed it in their own correlation context
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _make_blocked_lineage_record(
    ctx: TimelineEventContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    blocking_reason: Optional[str],
) -> TimelineLineageRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return TimelineLineageRecord(
        governance_scope=SCOPE_UNAVAILABLE,
        event_type=None,
        lineage_visibility=VISIBILITY_SHADOW_VISIBLE,
        is_replay=ctx.execution_type in _REPLAY_TYPES,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SYSTEM,
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
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        finalized_lineage_protected=True,
        replay_lineage_preserved=True,
        sql_server_authority_preserved=True,
        lineage_emit_authorized=False,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=True,
        blocking_reason=blocking_reason,
        orchestration_continues=False,
    )


def _make_maintenance_lineage_record(
    ctx: TimelineEventContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
) -> TimelineLineageRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return TimelineLineageRecord(
        governance_scope=SCOPE_MAINTENANCE,
        event_type=None,
        lineage_visibility=VISIBILITY_SHADOW_VISIBLE,
        is_replay=False,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SYSTEM,
        config_version_id=ctx.config_version_id,
        historical_config_version_id=None,
        threshold_bindings={k: UNKNOWN_V0 for k in _TIMELINE_THRESHOLD_KEYS},
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
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        finalized_lineage_protected=True,
        replay_lineage_preserved=True,
        sql_server_authority_preserved=True,
        lineage_emit_authorized=False,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=False,
    )


def _make_replay_lineage_record(
    ctx: TimelineEventContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
) -> TimelineLineageRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    source_missing = not ctx.source_artifact_id
    return TimelineLineageRecord(
        governance_scope=SCOPE_REPLAY_ONLY,
        event_type=None,    # no live classification in replay (INV-4, AP-RT2)
        lineage_visibility=VISIBILITY_REPLAY_ONLY,
        is_replay=True,
        live_effects_suppressed=True,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=AUTHORITY_SYSTEM,
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
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        finalized_lineage_protected=True,
        replay_lineage_preserved=True,    # replay lineage always preserved (IML-3)
        sql_server_authority_preserved=True,
        lineage_emit_authorized=False,
        degraded=source_missing,
        degradation_flags=["REPLAY_SOURCE_ARTIFACT_MISSING"] if source_missing else [],
        degradation_cause="REPLAY_SOURCE_ARTIFACT_MISSING" if source_missing else None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=True,    # authorized suppression — replay continues
    )


def _make_lineage_record(
    ctx: TimelineEventContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    governance_scope: str,
    event_type: Optional[str],
    lineage_visibility: str,
    causation_chain_preserved: bool,
    authoritative_source: str,
    sql_server_authority_preserved: bool,
    lineage_emit_authorized: bool,
    degraded: bool,
    degradation_flags: List[str],
    degradation_cause: Optional[str],
    outcome: str,
) -> TimelineLineageRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return TimelineLineageRecord(
        governance_scope=governance_scope,
        event_type=event_type,
        lineage_visibility=lineage_visibility,
        is_replay=False,
        live_effects_suppressed=(governance_scope != "AUTHORIZED"),
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        attribution_timestamp=ctx.attribution_timestamp,
        upstream_correlation_id=ctx.upstream_correlation_id,
        authoritative_source=authoritative_source,
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
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=causation_chain_preserved,
        append_only_enforced=True,          # unconditional — FAD-4
        finalized_lineage_protected=True,   # unconditional — IML-1, IML-3
        replay_lineage_preserved=True,      # unconditional — IML-3
        sql_server_authority_preserved=sql_server_authority_preserved,
        lineage_emit_authorized=lineage_emit_authorized,
        degraded=degraded,
        degradation_flags=list(degradation_flags),
        degradation_cause=degradation_cause,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=(governance_scope != SCOPE_UNAVAILABLE),
    )
