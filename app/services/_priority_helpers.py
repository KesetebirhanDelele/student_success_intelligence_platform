"""
Internal helpers for the governance-safe orchestration prioritization advisory service.
Not part of the public API. Consumed only by priority.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._priority_types import (
    BASIS_FALLBACK,
    BASIS_HISTORICAL_REPLAY,
    BASIS_RULE_BASED,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    PRIORITY_UNKNOWN,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    TIER_UNAVAILABLE,
    UNKNOWN_V0,
    _PRIORITY_THRESHOLD_KEYS,
    _REPLAY_TYPES,
    PrioritizationContext,
    PrioritizationRecord,
)

logger = logging.getLogger(__name__)

_PRIORITY_SERVICE_NAME = "orchestration_priority"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event_id() -> str:
    return str(uuid.uuid4())


def emit_priority_event_log(record: PrioritizationRecord) -> None:
    """
    Emit structured prioritization advisory log for every evaluation path.
    PII never logged — opaque identifiers only (AP-D10, AP-RT13).
    Observability never suppressed on any path (AP-E7).
    """
    is_warn = record.degraded or record.orchestration_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _PRIORITY_SERVICE_NAME,
        "event": "priority_blocked" if record.orchestration_blocked else "priority_assessed",
        "event_id": record.event_id,
        "governance_scope": record.governance_scope,
        "advisory_priority": record.advisory_priority,
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
        "error_class": record.error_class,
        "scoring_emit_authorized": record.scoring_emit_authorized,
        "causation_chain_preserved": record.causation_chain_preserved,
        "append_only_enforced": record.append_only_enforced,
        "replay_lineage_preserved": record.replay_lineage_preserved,
        "scoring_lineage_immutable": record.scoring_lineage_immutable,
        "ai_governance_tier": record.ai_governance_tier,
        "ai_confidence_score": record.ai_confidence_score,
        "ai_priority_adjustment_applied": record.ai_priority_adjustment_applied,
        "ai_fallback_applied": record.ai_fallback_applied,
        "risk_contributions": record.risk_contributions,
        "degraded": record.degraded,
        "degradation_cause": record.degradation_cause,
        "degradation_flags": record.degradation_flags,
        "orchestration_blocked": record.orchestration_blocked,
        "blocking_reason": record.blocking_reason,
        "orchestration_continues": record.orchestration_continues,
        "reason_codes": record.reason_codes,
        "duration_ms": record.duration_ms,
        # student_id_opaque not logged — callers embed it in their correlation context
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _make_blocked_priority_record(
    ctx: PrioritizationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    blocking_reason: Optional[str],
) -> PrioritizationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return PrioritizationRecord(
        advisory_priority=PRIORITY_UNKNOWN,
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
        threshold_bindings={k: UNKNOWN_V0 for k in _PRIORITY_THRESHOLD_KEYS},
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
        scoring_factors=[],
        risk_contributions=[],
        ai_governance_tier=TIER_UNAVAILABLE,
        ai_confidence_score=ctx.ai_confidence_score,
        ai_priority_adjustment_applied=False,
        ai_fallback_applied=False,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        replay_lineage_preserved=True,
        scoring_lineage_immutable=True,
        scoring_emit_authorized=False,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=True,
        blocking_reason=blocking_reason,
        orchestration_continues=False,
    )


def _make_maintenance_priority_record(
    ctx: PrioritizationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
) -> PrioritizationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return PrioritizationRecord(
        advisory_priority=PRIORITY_UNKNOWN,
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
        threshold_bindings={k: UNKNOWN_V0 for k in _PRIORITY_THRESHOLD_KEYS},
        event_id=_make_event_id(),
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        rule_path_taken=list(rule_path),
        duration_ms=elapsed,
        outcome=OUTCOME_SUCCESS,
        error_class=None,
        scoring_factors=[],
        risk_contributions=[],
        ai_governance_tier=TIER_UNAVAILABLE,
        ai_confidence_score=ctx.ai_confidence_score,
        ai_priority_adjustment_applied=False,
        ai_fallback_applied=False,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        replay_lineage_preserved=True,
        scoring_lineage_immutable=True,
        scoring_emit_authorized=False,
        degraded=False,
        degradation_flags=[],
        degradation_cause=None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=False,
    )


def _make_replay_priority_record(
    ctx: PrioritizationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
) -> PrioritizationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    source_missing = not ctx.source_artifact_id
    return PrioritizationRecord(
        advisory_priority=PRIORITY_UNKNOWN,    # no live priority in replay — INV-4, AP-D8
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
        scoring_factors=[],
        risk_contributions=[],
        ai_governance_tier=TIER_UNAVAILABLE,
        ai_confidence_score=ctx.ai_confidence_score,
        ai_priority_adjustment_applied=False,
        ai_fallback_applied=False,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,
        replay_lineage_preserved=True,    # IML-3 — replay scoring always preserved
        scoring_lineage_immutable=True,
        scoring_emit_authorized=False,
        degraded=source_missing,
        degradation_flags=["REPLAY_SOURCE_ARTIFACT_MISSING"] if source_missing else [],
        degradation_cause="REPLAY_SOURCE_ARTIFACT_MISSING" if source_missing else None,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=True,    # authorized suppression — replay continues
    )


def _make_priority_record(
    ctx: PrioritizationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    advisory_priority: str,
    governance_scope: str,
    assessment_basis: str,
    scoring_factors: List[Dict[str, Any]],
    risk_contributions: List[str],
    ai_governance_tier: str,
    ai_priority_adjustment_applied: bool,
    ai_fallback_applied: bool,
    degraded: bool,
    degradation_flags: List[str],
    degradation_cause: Optional[str],
    outcome: str,
    scoring_emit_authorized: bool,
) -> PrioritizationRecord:
    elapsed = int((time.monotonic() - t0) * 1000)
    return PrioritizationRecord(
        advisory_priority=advisory_priority,
        governance_scope=governance_scope,
        assessment_basis=assessment_basis,
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
        scoring_factors=list(scoring_factors),
        risk_contributions=list(risk_contributions),
        ai_governance_tier=ai_governance_tier,
        ai_confidence_score=ctx.ai_confidence_score,
        ai_priority_adjustment_applied=ai_priority_adjustment_applied,
        ai_fallback_applied=ai_fallback_applied,
        execution_state_before=ctx.execution_state_before,
        execution_state_after=ctx.execution_state_after,
        causation_chain_preserved=bool(ctx.causation_id),
        append_only_enforced=True,           # unconditional — FAD-4
        replay_lineage_preserved=True,       # unconditional — IML-3
        scoring_lineage_immutable=True,      # unconditional — IML-1
        scoring_emit_authorized=scoring_emit_authorized,
        degraded=degraded,
        degradation_flags=list(degradation_flags),
        degradation_cause=degradation_cause,
        reason_codes=list(codes),
        orchestration_blocked=False,
        blocking_reason=None,
        orchestration_continues=(governance_scope != SCOPE_UNAVAILABLE),
    )
