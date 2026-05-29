"""
Internal helpers for the governance-safe worker orchestration execution layer.
Not part of the public API. Consumed only by worker.py.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services._worker_types import (
    REQUIRED_WORKER_ATTRIBUTION,
    UNKNOWN_V0,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    WorkerExecutionRecord,
    WorkerJobContext,
)

logger = logging.getLogger(__name__)

_SERVICE_NAME = "worker_execution"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event_id() -> str:
    return str(uuid.uuid4())


def _attribution_complete(ctx: WorkerJobContext, codes: List[str]) -> bool:
    """
    Returns True only if all required worker attribution fields are populated.
    Appends a reason code for each missing field (AP-RT4).
    """
    ok = True
    for f in REQUIRED_WORKER_ATTRIBUTION:
        if not getattr(ctx, f, None):
            codes.append(f"ATTRIBUTION_MISSING_{f.upper()}")
            ok = False
    return ok


def _governance_precondition_gate(ctx: WorkerJobContext, codes: List[str]) -> bool:
    """
    RULE 0: Worker governance precondition gate.

    Blocks execution if any of the following are true:
    - config_version_id is null or UNKNOWN_V0
    - execution_mode is not valid
    - execution_type is not valid
    - correlation_id is missing
    - any required attribution field is absent

    Never bypassed (AP-RT4, AP-GHL4, AP-GHL15).
    Returns True if all preconditions pass.
    """
    ok = True

    if not ctx.config_version_id or ctx.config_version_id == UNKNOWN_V0:
        codes.append("CONFIG_VERSION_UNRESOLVED")
        ok = False

    if ctx.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append("EXECUTION_MODE_INVALID")
        ok = False

    if ctx.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append("EXECUTION_TYPE_INVALID")
        ok = False

    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
        ok = False

    attr_codes: List[str] = []
    if not _attribution_complete(ctx, attr_codes):
        # correlation_id already checked above — avoid duplicate code
        deduped = [c for c in attr_codes if c != "ATTRIBUTION_MISSING_CORRELATION_ID"]
        codes.extend(deduped)
        ok = False

    return ok


def _build_execution_record(
    ctx: WorkerJobContext,
    outcome: str,
    rule_path: List[str],
    reason_codes: List[str],
    t0_mono: float,
    *,
    execution_blocked: bool,
    blocking_reason: Optional[str],
    dispatch_delegated: bool,
    channel: Optional[str],
    dispatch_outcome: Optional[str],
    outbound_suppressed: bool = False,
    suppression_reason: Optional[str] = None,
    error_class: Optional[str] = None,
) -> WorkerExecutionRecord:
    """
    Build a WorkerExecutionRecord from context and evaluation results.
    Pure function — no side effects, no logging.
    """
    import time
    duration_ms = int((time.monotonic() - t0_mono) * 1000)

    return WorkerExecutionRecord(
        job_id=ctx.job_id,
        governance_scope=ctx.governance_scope,
        outcome=outcome,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        actor_identity=ctx.actor_identity,
        config_version_id=ctx.config_version_id,
        execution_mode=ctx.execution_mode,
        execution_type=ctx.execution_type,
        intent_type=ctx.intent_type,
        dispatch_delegated=dispatch_delegated,
        dispatch_outcome=dispatch_outcome,
        channel=channel,
        outbound_suppressed=outbound_suppressed,
        suppression_reason=suppression_reason,
        degraded=ctx.degraded,
        degradation_cause=ctx.degradation_cause,
        student_id_opaque=ctx.student_id_opaque,
        checkpoint_type=ctx.checkpoint_type,
        contact_attempt=ctx.contact_attempt,
        event_id=_make_event_id(),
        rule_path_taken=list(rule_path),
        duration_ms=duration_ms,
        reason_codes=list(reason_codes),
        error_class=error_class,
        execution_blocked=execution_blocked,
        blocking_reason=blocking_reason,
    )


def emit_worker_execution_log(
    record: WorkerExecutionRecord,
    student_id_opaque: Optional[str],
) -> None:
    """
    Emit structured worker execution log.
    Student PII never logged — opaque ID only (AP-RT13).
    Observability never suppressed (AP-RT5).
    """
    is_warn = (
        record.execution_blocked
        or record.degraded
        or record.outcome in ("blocked", "execution_error")
    )
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _SERVICE_NAME,
        "event": "worker_execution_result",
        "job_id": record.job_id,
        "event_id": record.event_id,
        "governance_scope": record.governance_scope,
        "outcome": record.outcome,
        "execution_mode": record.execution_mode,
        "execution_type": record.execution_type,
        "correlation_id": record.correlation_id,
        "causation_id": record.causation_id,
        "orchestration_cycle_id": record.orchestration_cycle_id,
        "origin_source": record.origin_source,
        "origin_authority": record.origin_authority,
        "config_version_id": record.config_version_id,
        "intent_type": record.intent_type,
        "dispatch_delegated": record.dispatch_delegated,
        "dispatch_outcome": record.dispatch_outcome,
        "channel": record.channel,
        "outbound_suppressed": record.outbound_suppressed,
        "suppression_reason": record.suppression_reason,
        "execution_blocked": record.execution_blocked,
        "blocking_reason": record.blocking_reason,
        "degraded": record.degraded,
        "degradation_cause": record.degradation_cause,
        "student_id_opaque": student_id_opaque,
        "checkpoint_type": record.checkpoint_type,
        "contact_attempt": record.contact_attempt,
        "rule_path_taken": record.rule_path_taken,
        "reason_codes": record.reason_codes,
        "duration_ms": record.duration_ms,
        "error_class": record.error_class,
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))
