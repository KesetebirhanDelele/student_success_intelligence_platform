"""
Internal helpers for the governance-safe GHL provider containment orchestration layer.
Not part of the public API. Consumed only by ghl.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._ghl_types import (
    EVENT_DEDUPLICATION_SUPPRESS,
    EVENT_REPLAY_SIMULATION,
    EVENT_SHADOW_SIMULATION,
    SCOPE_BLOCKED,
    SCOPE_DUPLICATE_SUPPRESSED,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    UNKNOWN_V0,
    ProviderOrchestrationAssessment,
    ProviderOrchestrationContext,
    _PROVIDER_THRESHOLD_KEYS,
)

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "ghl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event_id() -> str:
    return str(uuid.uuid4())


def emit_provider_event_log(
    assessment: ProviderOrchestrationAssessment,
    student_id_opaque: Optional[str],
) -> None:
    """
    Emit structured assessment log for every provider interaction path.
    Student PII never logged — opaque ID only (AP-GHL10).
    Observability never suppressed (AP-GHL6).
    """
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if (assessment.degraded or assessment.provider_blocked) else "info",
        "service": "ghl_provider",
        "event": "provider_orchestration_assessment",
        "event_id": assessment.event_id,
        "provider": assessment.provider,
        "provider_event_type": assessment.provider_event_type,
        "governance_scope": assessment.governance_scope,
        "execution_mode": assessment.execution_mode,
        "execution_type": assessment.execution_type,
        "is_replay": assessment.is_replay,
        "outbound_suppressed": assessment.outbound_suppressed,
        "outbound_blocked": assessment.outbound_blocked,
        "historical_provider_context_only": assessment.historical_provider_context_only,
        "config_version_id": assessment.config_version_id,
        "correlation_id": assessment.correlation_id,
        "origin_source": assessment.origin_source,
        "origin_authority": assessment.origin_authority,
        "degraded": assessment.degraded,
        "degradation_cause": assessment.degradation_cause,
        "orchestration_continues": assessment.orchestration_continues,
        "provider_blocked": assessment.provider_blocked,
        "blocking_reason": assessment.blocking_reason,
        "reason_codes": assessment.reason_codes,
        "rule_path_taken": assessment.rule_path_taken,
        "assessment_basis": assessment.assessment_basis,
        "outcome": assessment.outcome,
        "duration_ms": assessment.duration_ms,
        "student_id_opaque": student_id_opaque,
        # Suppress ghl_message_id when outbound suppressed — avoids phantom record confusion
        "ghl_message_id": assessment.ghl_message_id if not assessment.outbound_suppressed else None,
    }
    log_fn = logger.warning if (assessment.degraded or assessment.provider_blocked) else logger.info
    log_fn(json.dumps(entry))


def _make_blocked_assessment(
    ctx: ProviderOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    degradation_cause: Optional[str],
    blocking_reason: Optional[str],
) -> ProviderOrchestrationAssessment:
    return ProviderOrchestrationAssessment(
        provider_event_type=None,
        governance_scope=SCOPE_BLOCKED,
        is_replay=ctx.execution_type in {"replay", "regeneration"},
        outbound_suppressed=True,
        historical_provider_context_only=False,
        historical_config_version_id=ctx.historical_config_version_id,
        replay_provider_source=None,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        upstream_intent_id=ctx.upstream_intent_id,
        config_version_id=ctx.config_version_id,
        threshold_bindings=threshold_bindings,
        provider=_PROVIDER_NAME,
        ghl_message_id=ctx.ghl_message_id,
        provider_error_class=None,
        degraded=degradation_cause is not None,
        degradation_cause=degradation_cause,
        outbound_blocked=True,
        orchestration_continues=False,
        event_id=_make_event_id(),
        rule_path_taken=list(rule_path),
        assessment_basis="governance_block",
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        duration_ms=int((time.monotonic() - t0) * 1000),
        outcome="blocked",
        reason_codes=list(codes),
        provider_blocked=True,
        blocking_reason=blocking_reason,
    )


def _make_replay_assessment(
    ctx: ProviderOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
) -> ProviderOrchestrationAssessment:
    return ProviderOrchestrationAssessment(
        provider_event_type=EVENT_REPLAY_SIMULATION,
        governance_scope=SCOPE_REPLAY_ONLY,
        is_replay=True,
        outbound_suppressed=True,
        historical_provider_context_only=True,
        historical_config_version_id=ctx.historical_config_version_id,
        replay_provider_source=ctx.source_artifact_id,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        upstream_intent_id=ctx.upstream_intent_id,
        config_version_id=ctx.config_version_id,
        threshold_bindings={k: UNKNOWN_V0 for k in _PROVIDER_THRESHOLD_KEYS},
        provider=_PROVIDER_NAME,
        ghl_message_id=None,
        provider_error_class=None,
        degraded=False,
        degradation_cause=None,
        outbound_blocked=True,
        orchestration_continues=True,
        event_id=_make_event_id(),
        rule_path_taken=list(rule_path),
        assessment_basis="replay_containment",
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        duration_ms=int((time.monotonic() - t0) * 1000),
        outcome="suppressed_replay",
        reason_codes=list(codes),
        provider_blocked=False,
        blocking_reason=None,
    )


def _make_shadow_assessment(
    ctx: ProviderOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
) -> ProviderOrchestrationAssessment:
    return ProviderOrchestrationAssessment(
        provider_event_type=EVENT_SHADOW_SIMULATION,
        governance_scope=SCOPE_SHADOW_ONLY,
        is_replay=False,
        outbound_suppressed=True,
        historical_provider_context_only=False,
        historical_config_version_id=None,
        replay_provider_source=None,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        upstream_intent_id=ctx.upstream_intent_id,
        config_version_id=ctx.config_version_id,
        threshold_bindings=threshold_bindings,
        provider=_PROVIDER_NAME,
        ghl_message_id=None,
        provider_error_class=None,
        degraded=degraded,
        degradation_cause=degradation_cause,
        outbound_blocked=True,
        orchestration_continues=True,
        event_id=_make_event_id(),
        rule_path_taken=list(rule_path),
        assessment_basis="shadow_containment",
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        duration_ms=int((time.monotonic() - t0) * 1000),
        outcome="suppressed_shadow",
        reason_codes=list(codes),
        provider_blocked=False,
        blocking_reason=None,
    )


def _make_duplicate_assessment(
    ctx: ProviderOrchestrationContext,
    codes: List[str],
    rule_path: List[str],
    t0: float,
    threshold_bindings: Dict[str, Any],
) -> ProviderOrchestrationAssessment:
    return ProviderOrchestrationAssessment(
        provider_event_type=EVENT_DEDUPLICATION_SUPPRESS,
        governance_scope=SCOPE_DUPLICATE_SUPPRESSED,
        is_replay=False,
        outbound_suppressed=True,
        historical_provider_context_only=False,
        historical_config_version_id=None,
        replay_provider_source=None,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        upstream_intent_id=ctx.upstream_intent_id,
        config_version_id=ctx.config_version_id,
        threshold_bindings=threshold_bindings,
        provider=_PROVIDER_NAME,
        ghl_message_id=None,
        provider_error_class=None,
        degraded=False,
        degradation_cause=None,
        outbound_blocked=True,
        orchestration_continues=False,
        event_id=_make_event_id(),
        rule_path_taken=list(rule_path),
        assessment_basis="idempotency_dedup",
        execution_type=ctx.execution_type,
        execution_mode=ctx.execution_mode,
        duration_ms=int((time.monotonic() - t0) * 1000),
        outcome="duplicate_suppressed",
        reason_codes=list(codes),
        provider_blocked=False,
        blocking_reason=None,
    )
