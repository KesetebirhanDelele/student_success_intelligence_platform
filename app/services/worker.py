"""
Governance-safe worker orchestration execution layer.

Bridges OutreachCoordinationRecord → ProviderOrchestrationContext →
ProviderOrchestrationAssessment → transport dispatch.

Workers are coordinators: they consume intents, preserve attribution,
preserve idempotency, preserve replay containment, preserve SHADOW containment.
Workers NEVER directly dispatch providers, bypass governance evaluation,
bypass Rule 0, mutate FINALIZED artifacts, or create hidden execution paths.

Architecture preservation prohibitions (MUST NOT):
  AP-RT1  — no direct provider API calls from this layer
  AP-RT2  — no LIVE effects from replay/regeneration execution types
  AP-RT3  — no evaluation without non-null ACTIVE config_version_id
  AP-RT4  — no execution record without correlation_id propagated
  AP-RT5  — no silent skip of student candidates; all skips produce structured log
  AP-RT6  — no silent absorption of execution failures; all produce audit record
  AP-RT7  — no automation SHADOW→LIVE transition
  AP-RT9  — no hardcoded Config V2 threshold fallbacks; UNKNOWN_V0 only
  AP-RT10 — no duplicate LIVE execution of the same intent
  AP-RT13 — no raw PII in execution records; opaque student ID only
  AP-RT14 — no silent failure swallowing; every exception classified
  AP-RT15 — no orphaned execution cycles without completion log
  FAD-1   — no mutation of FINALIZED coordination artifacts
  FAD-2   — attribution immutably propagated end-to-end
  FAD-3   — execution records reproduce deterministically from same inputs
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.services._ghl_types import ProviderOrchestrationContext
from app.services._outreach_types import OutreachCoordinationRecord, OutreachOrchestrationContext
from app.services._worker_helpers import (
    _build_execution_record,
    _governance_precondition_gate,
    emit_worker_execution_log,
)
from app.services._worker_types import (
    DEFAULT_DISPATCH_CHANNEL,
    INTENT_CHANNEL_MAP,
    OUTCOME_BLOCKED,
    OUTCOME_DISPATCH_DELEGATED,
    OUTCOME_SUPPRESSED,
    SCOPE_AUTHORIZED,
    UNKNOWN_V0,
    WorkerExecutionRecord,
    WorkerJobContext,
    _REPLAY_TYPES,
    _SUPPRESSED_SCOPES,
)
from app.services.ghl import assess_provider_orchestration
from app.services.integrations.ghl import build_ghl_payload, execute_ghl_dispatch

logger = logging.getLogger(__name__)


# ── Context builders ──────────────────────────────────────────────────────────

def _make_job_context(
    coordination_record: OutreachCoordinationRecord,
    student: dict,
    attempt: int,
    job_id: str,
) -> WorkerJobContext:
    """
    Build WorkerJobContext from OutreachCoordinationRecord, student envelope, and attempt.
    Attribution propagated immutably from coordination record (AP-RT4, FAD-2).
    Student ID extracted as opaque string — no PII retained in context (AP-RT13).
    """
    return WorkerJobContext(
        # Governance from coordination record
        governance_scope=coordination_record.governance_scope,
        intent_type=coordination_record.intent_type,
        is_replay=coordination_record.is_replay,
        live_effects_suppressed=coordination_record.live_effects_suppressed,
        dispatch_authorized=coordination_record.dispatch_authorized,
        dispatch_blocked_reason=coordination_record.dispatch_blocked_reason,

        # Attribution — propagated immutably (AP-RT4)
        correlation_id=coordination_record.correlation_id,
        causation_id=coordination_record.causation_id,
        orchestration_cycle_id=coordination_record.orchestration_cycle_id,
        origin_source=coordination_record.origin_source,
        origin_authority=coordination_record.origin_authority,
        actor_identity=coordination_record.actor_identity,
        attribution_timestamp=coordination_record.attribution_timestamp,

        # Config lineage
        config_version_id=coordination_record.config_version_id,
        execution_mode=coordination_record.execution_mode,
        execution_type=coordination_record.execution_type,
        threshold_bindings=dict(coordination_record.threshold_bindings),

        # Idempotency key: student + checkpoint + attempt (AP-RT10)
        idempotency_key=(
            f"{student.get('UserID')}:"
            f"{student.get('PathName')}:"
            f"{attempt}"
        ),

        # Student — opaque ID only (AP-RT13)
        student_id_opaque=str(student.get("UserID")) if student.get("UserID") else None,
        checkpoint_type=coordination_record.checkpoint_type,
        contact_attempt=attempt,

        # Degradation from coordination record
        degraded=coordination_record.degraded,
        degradation_cause=coordination_record.degradation_cause,
        degradation_flags=list(coordination_record.degradation_flags),

        # Compliance
        compliance_hold_active=coordination_record.compliance_hold_active,

        job_id=job_id,
    )


def _make_provider_context(ctx: WorkerJobContext) -> ProviderOrchestrationContext:
    """
    Build ProviderOrchestrationContext from WorkerJobContext.
    Attribution propagated immutably (AP-RT4, AP-GHL15, FAD-2).
    """
    return ProviderOrchestrationContext(
        config_version_id=ctx.config_version_id,
        execution_mode=ctx.execution_mode,
        execution_type=ctx.execution_type,
        config_rule_set=dict(ctx.threshold_bindings),
        compliance_hold_active=ctx.compliance_hold_active,
        idempotency_key=ctx.idempotency_key,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        upstream_intent_id=ctx.orchestration_cycle_id,
        actor_identity=ctx.actor_identity,
        provider_health_state=ctx.provider_health_state,
        circuit_breaker_state=ctx.circuit_breaker_state,
        retry_attempt_count=ctx.contact_attempt,
        student_id_opaque=ctx.student_id_opaque,
    )


def _channel_for_intent(intent_type: Optional[str]) -> str:
    """
    Deterministic intent-to-channel mapping.
    Falls through to DEFAULT_DISPATCH_CHANNEL if intent not in map — never silent.
    """
    return INTENT_CHANNEL_MAP.get(intent_type or "", DEFAULT_DISPATCH_CHANNEL)


# ── Public execution coordinator ──────────────────────────────────────────────

def coordinate_worker_execution(
    coordination_record: OutreachCoordinationRecord,
    student: dict,
    attempt: int,
) -> WorkerExecutionRecord:
    """
    Execute worker orchestration coordination under governance containment.

    Rule 0 gate: blocks if config unresolved, attribution incomplete,
    correlation_id missing, invalid execution_mode, invalid execution_type.

    Suppression chain (in order):
      1. Rule 0 precondition gate — execution_blocked
      2. dispatch_authorized=False — suppressed
      3. Governance scope suppression (_SUPPRESSED_SCOPES) — suppressed
      4. Replay containment (is_replay or _REPLAY_TYPES) — suppressed
      5. live_effects_suppressed — suppressed
      6. compliance_hold — execution_blocked

    AUTHORIZED with all gates passed: builds ProviderOrchestrationContext,
    calls assess_provider_orchestration, builds GHL payload, delegates to
    execute_ghl_dispatch. Returns WorkerExecutionRecord. Never dispatches directly.

    Attribution propagated immutably end-to-end (AP-RT4, FAD-2).
    Student PII never logged (AP-RT13).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    job_id = str(uuid.uuid4())

    ctx = _make_job_context(coordination_record, student, attempt, job_id)

    # ── RULE 0: Governance precondition gate ──────────────────────────────────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        record = _build_execution_record(
            ctx, OUTCOME_BLOCKED, rule_path, codes, t0,
            execution_blocked=True,
            blocking_reason=gate_codes[0] if gate_codes else "PRECONDITION_FAILED",
            dispatch_delegated=False,
            channel=None,
            dispatch_outcome=None,
        )
        emit_worker_execution_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 1: Dispatch authorization check ──────────────────────────────────
    rule_path.append("RULE_1")
    if not coordination_record.dispatch_authorized:
        codes.append("DISPATCH_NOT_AUTHORIZED")
        if coordination_record.orchestration_blocked:
            codes.append("ORCHESTRATION_BLOCKED")
        record = _build_execution_record(
            ctx, OUTCOME_SUPPRESSED, rule_path, codes, t0,
            execution_blocked=False,
            blocking_reason=coordination_record.dispatch_blocked_reason,
            dispatch_delegated=False,
            channel=None,
            dispatch_outcome=None,
            outbound_suppressed=True,
            suppression_reason=coordination_record.dispatch_blocked_reason or "dispatch_not_authorized",
        )
        emit_worker_execution_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 2: Governance scope suppression ──────────────────────────────────
    rule_path.append("RULE_2")
    if ctx.governance_scope in _SUPPRESSED_SCOPES:
        codes.append(f"GOVERNANCE_SCOPE_SUPPRESSED")
        codes.append(ctx.governance_scope)
        record = _build_execution_record(
            ctx, OUTCOME_SUPPRESSED, rule_path, codes, t0,
            execution_blocked=False,
            blocking_reason=f"scope:{ctx.governance_scope}",
            dispatch_delegated=False,
            channel=None,
            dispatch_outcome=None,
            outbound_suppressed=True,
            suppression_reason=f"governance_scope:{ctx.governance_scope}",
        )
        emit_worker_execution_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 3: Replay containment (AP-RT2) ───────────────────────────────────
    rule_path.append("RULE_3")
    if ctx.is_replay or ctx.execution_type in _REPLAY_TYPES:
        codes.append("REPLAY_EXECUTION_SUPPRESSED")
        record = _build_execution_record(
            ctx, OUTCOME_SUPPRESSED, rule_path, codes, t0,
            execution_blocked=False,
            blocking_reason="replay_containment",
            dispatch_delegated=False,
            channel=None,
            dispatch_outcome=None,
            outbound_suppressed=True,
            suppression_reason="replay_containment",
        )
        emit_worker_execution_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 4: Live effects suppression ──────────────────────────────────────
    rule_path.append("RULE_4")
    if ctx.live_effects_suppressed:
        codes.append("LIVE_EFFECTS_SUPPRESSED")
        record = _build_execution_record(
            ctx, OUTCOME_SUPPRESSED, rule_path, codes, t0,
            execution_blocked=False,
            blocking_reason="live_effects_suppressed",
            dispatch_delegated=False,
            channel=None,
            dispatch_outcome=None,
            outbound_suppressed=True,
            suppression_reason="live_effects_suppressed",
        )
        emit_worker_execution_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 5: Compliance hold ────────────────────────────────────────────────
    rule_path.append("RULE_5")
    if ctx.compliance_hold_active:
        codes.append("COMPLIANCE_HOLD_ACTIVE")
        record = _build_execution_record(
            ctx, OUTCOME_BLOCKED, rule_path, codes, t0,
            execution_blocked=True,
            blocking_reason="compliance_hold",
            dispatch_delegated=False,
            channel=None,
            dispatch_outcome=None,
        )
        emit_worker_execution_log(record, ctx.student_id_opaque)
        return record

    # ── RULE 6: Provider delegation ───────────────────────────────────────────
    # All governance gates passed. Build provider context, assess, and delegate
    # to transport layer. Never dispatches provider directly (AP-RT1).
    rule_path.append("RULE_6")
    provider_ctx = _make_provider_context(ctx)
    assessment = assess_provider_orchestration(provider_ctx)

    channel = _channel_for_intent(ctx.intent_type)
    payload = build_ghl_payload(student, channel, attempt)
    dispatch_result = execute_ghl_dispatch(assessment, payload)

    dispatch_outcome = dispatch_result.get("outcome", "unknown")
    result_channel = dispatch_result.get("channel", channel)

    # Merge any reason codes from transport layer
    transport_codes = dispatch_result.get("reason_codes", [])
    codes.extend(transport_codes)

    outbound_suppressed = dispatch_result.get("outbound_suppressed", False)
    suppression_reason: Optional[str] = None
    if outbound_suppressed:
        scope = dispatch_result.get("governance_scope", "")
        suppression_reason = f"transport_scope:{scope}" if scope else "transport_suppressed"

    record = _build_execution_record(
        ctx, OUTCOME_DISPATCH_DELEGATED, rule_path, codes, t0,
        execution_blocked=False,
        blocking_reason=None,
        dispatch_delegated=True,
        channel=result_channel,
        dispatch_outcome=dispatch_outcome,
        outbound_suppressed=outbound_suppressed,
        suppression_reason=suppression_reason,
    )
    emit_worker_execution_log(record, ctx.student_id_opaque)
    return record


# ── Batch cycle runner ────────────────────────────────────────────────────────

async def run_batch_cycle(
    db: Any,
    checkpoint_type: str,
    execution_mode: str = "SHADOW",
    config_version_id: Optional[str] = None,
    attribution_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Governance-safe batch orchestration cycle runner.

    Iterates students for a checkpoint_type, runs the full coordination pipeline:
    outreach.coordinate_orchestration_cycle() → coordinate_worker_execution()

    All outbound behavior is SHADOW_ONLY. Workers coordinate orchestration only.
    No real student-facing communication is produced (AP-RT7, AP-GHL11).

    Attribution context is applied to each OutreachOrchestrationContext built here.
    Returns structured summary dict.
    """
    from sqlalchemy import select
    from app.models import StudentOutreachTracking, StudentTriggerData
    from app.services import outreach
    from app.services._outreach_types import (
        OutreachOrchestrationContext,
        TYPE_ORIGINAL,
    )

    attr = attribution_context or {}
    cycle_correlation_id = str(uuid.uuid4())
    cycle_id = str(uuid.uuid4())

    summary: Dict[str, Any] = {
        "cycle_correlation_id": cycle_correlation_id,
        "checkpoint_type": checkpoint_type,
        "execution_mode": execution_mode,
        "config_version_id": config_version_id or UNKNOWN_V0,
        "total": 0,
        "processed": 0,
        "dispatch_delegated": 0,
        "suppressed": 0,
        "blocked": 0,
        "errors": 0,
        "student_records": [],
    }

    source_result = await db.execute(
        select(StudentTriggerData).where(
            StudentTriggerData.PathName == checkpoint_type
        )
    )
    students = source_result.scalars().all()
    summary["total"] = len(students)

    for student_row in students:
        s = {c.key: getattr(student_row, c.key) for c in student_row.__table__.columns}

        tracking_result = await db.execute(
            select(StudentOutreachTracking).where(
                StudentOutreachTracking.user_id == s["UserID"],
                StudentOutreachTracking.checkpoint_type == checkpoint_type,
            )
        )
        tracking_obj = tracking_result.scalar_one_or_none()
        attempt = (tracking_obj.current_attempt if tracking_obj else 0) + 1

        # Build per-student correlation: causation from cycle, new correlation per student
        student_correlation_id = str(uuid.uuid4())

        ctx = OutreachOrchestrationContext(
            config_version_id=config_version_id,
            execution_mode=execution_mode,
            execution_type=TYPE_ORIGINAL,
            correlation_id=student_correlation_id,
            causation_id=cycle_correlation_id,
            orchestration_cycle_id=cycle_id,
            origin_source=attr.get("origin_source", "batch_worker"),
            origin_authority=attr.get("origin_authority", "system"),
            actor_identity=attr.get("actor_identity", "batch_runner"),
            student_id_opaque=str(s.get("UserID")) if s.get("UserID") else None,
            checkpoint_type=checkpoint_type,
            contact_attempt_count=attempt - 1,
        )

        try:
            coordination_record = outreach.coordinate_orchestration_cycle(ctx)
            exec_record = coordinate_worker_execution(coordination_record, s, attempt)

            summary["processed"] += 1
            if exec_record.dispatch_delegated:
                summary["dispatch_delegated"] += 1
            elif exec_record.execution_blocked:
                summary["blocked"] += 1
            else:
                summary["suppressed"] += 1

            summary["student_records"].append({
                "student_id_opaque": exec_record.student_id_opaque,
                "outcome": exec_record.outcome,
                "governance_scope": exec_record.governance_scope,
                "dispatch_delegated": exec_record.dispatch_delegated,
                "channel": exec_record.channel,
                "reason_codes": exec_record.reason_codes,
                "execution_blocked": exec_record.execution_blocked,
            })

        except Exception as exc:
            summary["errors"] += 1
            summary["processed"] += 1
            logger.error(
                '{"timestamp": "%(ts)s", "level": "error", "service": "worker_execution",'
                ' "event": "batch_cycle_student_error",'
                ' "cycle_correlation_id": "%(cid)s",'
                ' "student_id_opaque": "%(sid)s",'
                ' "error_class": "%(ec)s"}',
                {
                    "ts": __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                    "cid": cycle_correlation_id,
                    "sid": str(s.get("UserID")),
                    "ec": type(exc).__name__,
                },
            )

    return summary
