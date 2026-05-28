"""
Governance-safe repository persistence layer.

Public API — governance-safe database write operations.
Every write is preceded by a governance precondition gate (RULE 0).
Every path emits a structured PersistenceRecord observability log.
No business logic lives here — only persistence governance.

Governance prohibitions (MUST NOT):
  FAD-4   — no UPDATE or DELETE on append-only lineage tables (outreach_history,
             state_transition_log, student_campaign_activity, student_quick_action_log)
  FAD-1   — no mutation of FINALIZED ai_insights records (is_finalized=True gate)
  IML-1   — attribution fields propagated immutably from caller; never overwritten
  INV-5   — no persistence without correlation_id; blocked at RULE 0
  CID-1   — correlation_id required and preserved on every persisted record
  RSV-1   — replay records tagged is_replay=True; queryable separately from LIVE
  AP-RT13 — PII never logged in PersistenceRecord observability
  AP-RT2  — replay persistence MUST NOT overwrite LIVE records
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIInsight,
    OutreachHistory,
    ProcessedEvents,
    StateTransitionLog,
    StudentCampaignActivity,
    StudentOutreachTracking,
    StudentQuickActionLog,
)
from app.repositories._repository_helpers import (
    _check_attribution_complete,
    _governance_persistence_gate,
    _make_persistence_record,
    emit_persistence_log,
)
from app.repositories._repository_types import (
    PERSIST_CLASS_APPEND_ONLY,
    PERSIST_CLASS_FINALIZED_ARTIFACT,
    PERSIST_CLASS_IDEMPOTENCY_STORE,
    PERSIST_CLASS_MUTABLE_OPERATIONAL,
    PERSIST_OUTCOME_BLOCKED,
    PERSIST_OUTCOME_DUPLICATE_REJECTED,
    PERSIST_OUTCOME_FINALIZED_PROTECTED,
    PERSIST_OUTCOME_SUCCESS,
    TYPE_ORIGINAL,
    _REPLAY_EXECUTION_TYPES,
    AttributionFields,
    PersistenceRecord,
)

# In-memory idempotency stores per table (spec/04 §4.1, AP-RT10)
_outreach_history_idempotency_keys: set = set()
_processed_events_idempotency_keys: set = set()


# ── append_outreach_history ───────────────────────────────────────────────────

async def append_outreach_history(
    session: AsyncSession,
    *,
    tracking_id: int,
    user_id: int,
    checkpoint_type: str,
    attempt_number: int,
    attribution: AttributionFields,
    idempotency_key: Optional[str] = None,
    channel: Optional[str] = None,
    action: Optional[str] = None,
    simulated_status: str = "NOT_SENT",
    payload: Optional[dict] = None,
    decision: Optional[str] = None,
    state_before: Optional[str] = None,
    state_after: Optional[str] = None,
    replay_context: Optional[dict] = None,
) -> Tuple[Optional[OutreachHistory], PersistenceRecord]:
    """
    Append-only insert to outreach_history.
    NEVER issues UPDATE. RULE 0 blocks duplicate LIVE idempotency keys (FAD-4, IML-1).
    Replay records receive is_replay=True; distinguishable from LIVE (RSV-1).
    """
    t0 = time.monotonic()
    rule_path = ["RULE_0_GOVERNANCE_GATE"]

    blocking_codes = _governance_persistence_gate(
        attribution=attribution,
        idempotency_key=idempotency_key,
        idempotency_store=_outreach_history_idempotency_keys,
        table_name="outreach_history",
    )

    if blocking_codes:
        record = _make_persistence_record(
            attribution=attribution,
            event="outreach_history_append_blocked",
            table_name="outreach_history",
            persistence_class=PERSIST_CLASS_APPEND_ONLY,
            blocked=True,
            blocking_codes=blocking_codes,
            blocking_reason=blocking_codes[0],
            outcome=PERSIST_OUTCOME_BLOCKED,
            record_id=None,
            idempotency_key=idempotency_key,
            duration_ms=int((time.monotonic() - t0) * 1000),
            rule_path=rule_path,
        )
        emit_persistence_log(record)
        return None, record

    rule_path.append("RULE_1_APPEND_INSERT")
    if idempotency_key and attribution.execution_type not in _REPLAY_EXECUTION_TYPES:
        _outreach_history_idempotency_keys.add(idempotency_key)

    history = OutreachHistory(
        tracking_id=tracking_id,
        user_id=user_id,
        checkpoint_type=checkpoint_type,
        attempt_number=attempt_number,
        channel=channel,
        action=action,
        execution_mode=attribution.execution_mode,
        simulated_status=simulated_status,
        payload=payload,
        decision=decision,
        state_before=state_before,
        state_after=state_after,
        # Governance attribution (IML-1 — propagated immutably from caller)
        correlation_id=attribution.correlation_id,
        causation_id=attribution.causation_id,
        config_version_id=attribution.config_version_id,
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
        orchestration_cycle_id=attribution.orchestration_cycle_id,
        origin_source=attribution.origin_source,
        origin_authority=attribution.origin_authority,
        is_replay=attribution.is_replay,
        attribution_complete=_check_attribution_complete(attribution),
        idempotency_key=idempotency_key,
        replay_context=replay_context,
    )
    session.add(history)
    await session.flush()

    elapsed = int((time.monotonic() - t0) * 1000)
    record = _make_persistence_record(
        attribution=attribution,
        event="outreach_history_appended",
        table_name="outreach_history",
        persistence_class=PERSIST_CLASS_APPEND_ONLY,
        blocked=False,
        blocking_codes=[],
        blocking_reason=None,
        outcome=PERSIST_OUTCOME_SUCCESS,
        record_id=history.id,
        idempotency_key=idempotency_key,
        duration_ms=elapsed,
        rule_path=rule_path,
    )
    emit_persistence_log(record)
    return history, record


# ── append_state_transition ───────────────────────────────────────────────────

async def append_state_transition(
    session: AsyncSession,
    *,
    tracking_id: int,
    user_id: int,
    from_state: str,
    to_state: str,
    trigger: str,
    attribution: AttributionFields,
    actor: str = "system",
    meta: Optional[dict] = None,
) -> Tuple[Optional[StateTransitionLog], PersistenceRecord]:
    """
    Append-only insert to state_transition_log — immutable audit trail (FAD-4, IML-1).
    NEVER issues UPDATE. Every state change persisted with full attribution lineage.
    """
    t0 = time.monotonic()
    rule_path = ["RULE_0_GOVERNANCE_GATE"]

    blocking_codes = _governance_persistence_gate(
        attribution=attribution,
        idempotency_key=None,
        idempotency_store=set(),
        table_name="state_transition_log",
    )

    if blocking_codes:
        record = _make_persistence_record(
            attribution=attribution,
            event="state_transition_append_blocked",
            table_name="state_transition_log",
            persistence_class=PERSIST_CLASS_APPEND_ONLY,
            blocked=True,
            blocking_codes=blocking_codes,
            blocking_reason=blocking_codes[0],
            outcome=PERSIST_OUTCOME_BLOCKED,
            record_id=None,
            idempotency_key=None,
            duration_ms=int((time.monotonic() - t0) * 1000),
            rule_path=rule_path,
        )
        emit_persistence_log(record)
        return None, record

    rule_path.append("RULE_1_APPEND_INSERT")
    transition = StateTransitionLog(
        tracking_id=tracking_id,
        user_id=user_id,
        from_state=from_state,
        to_state=to_state,
        trigger=trigger,
        actor=actor,
        meta=meta,
        correlation_id=attribution.correlation_id,
        causation_id=attribution.causation_id,
        config_version_id=attribution.config_version_id,
        execution_mode=attribution.execution_mode,
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
        origin_source=attribution.origin_source,
        origin_authority=attribution.origin_authority,
        is_replay=attribution.is_replay,
        attribution_complete=_check_attribution_complete(attribution),
    )
    session.add(transition)
    await session.flush()

    elapsed = int((time.monotonic() - t0) * 1000)
    record = _make_persistence_record(
        attribution=attribution,
        event="state_transition_appended",
        table_name="state_transition_log",
        persistence_class=PERSIST_CLASS_APPEND_ONLY,
        blocked=False,
        blocking_codes=[],
        blocking_reason=None,
        outcome=PERSIST_OUTCOME_SUCCESS,
        record_id=transition.id,
        idempotency_key=None,
        duration_ms=elapsed,
        rule_path=rule_path,
    )
    emit_persistence_log(record)
    return transition, record


# ── protect_finalized_ai_insight ──────────────────────────────────────────────

async def protect_finalized_ai_insight(
    session: AsyncSession,
    *,
    insight: AIInsight,
    attribution: AttributionFields,
) -> Tuple[AIInsight, PersistenceRecord]:
    """
    Mark an AIInsight as finalized. Idempotent: already-finalized emits
    FINALIZED_PROTECTED without error (FAD-1, INV-6, IML-1).
    Once finalized, no mutation is permitted by any subsequent operation.
    """
    t0 = time.monotonic()
    rule_path = ["RULE_0_GOVERNANCE_GATE"]

    blocking_codes = _governance_persistence_gate(
        attribution=attribution,
        idempotency_key=None,
        idempotency_store=set(),
        table_name="ai_insights",
        is_finalized=insight.is_finalized,
    )

    if blocking_codes:
        record = _make_persistence_record(
            attribution=attribution,
            event="ai_insight_finalize_protected",
            table_name="ai_insights",
            persistence_class=PERSIST_CLASS_FINALIZED_ARTIFACT,
            blocked=True,
            blocking_codes=blocking_codes,
            blocking_reason=blocking_codes[0],
            outcome=PERSIST_OUTCOME_FINALIZED_PROTECTED,
            record_id=insight.id,
            idempotency_key=None,
            duration_ms=int((time.monotonic() - t0) * 1000),
            rule_path=rule_path,
        )
        emit_persistence_log(record)
        return insight, record  # already finalized — return unchanged, no error

    rule_path.append("RULE_1_FINALIZE_MARK")
    from datetime import datetime, timezone
    insight.is_finalized = True
    insight.finalized_at = datetime.now(timezone.utc)
    await session.flush()

    elapsed = int((time.monotonic() - t0) * 1000)
    record = _make_persistence_record(
        attribution=attribution,
        event="ai_insight_finalized",
        table_name="ai_insights",
        persistence_class=PERSIST_CLASS_FINALIZED_ARTIFACT,
        blocked=False,
        blocking_codes=[],
        blocking_reason=None,
        outcome=PERSIST_OUTCOME_SUCCESS,
        record_id=insight.id,
        idempotency_key=None,
        duration_ms=elapsed,
        rule_path=rule_path,
    )
    emit_persistence_log(record)
    return insight, record


# ── record_processed_event ────────────────────────────────────────────────────

async def record_processed_event(
    session: AsyncSession,
    *,
    event_hash: str,
    event_type: Optional[str],
    user_id: Optional[int],
    attribution: AttributionFields,
    raw_payload: Optional[dict] = None,
) -> Tuple[bool, PersistenceRecord]:
    """
    Idempotency store insert. Duplicate event_hash → (False, DUPLICATE_REJECTED record).
    Governance attribution persisted for idempotency lineage tracing (INV-5, CID-1).
    Returns (inserted: bool, PersistenceRecord).
    """
    t0 = time.monotonic()
    rule_path = ["RULE_0_GOVERNANCE_GATE"]

    blocking_codes = _governance_persistence_gate(
        attribution=attribution,
        idempotency_key=event_hash,
        idempotency_store=_processed_events_idempotency_keys,
        table_name="processed_events",
    )
    # Filter to only non-idempotency blocks for the gate; idempotency duplicate
    # on processed_events is handled as a normal "already processed" path, not a hard block.
    hard_blocks = [c for c in blocking_codes if c != "IDEMPOTENCY_DUPLICATE"]

    if hard_blocks:
        record = _make_persistence_record(
            attribution=attribution,
            event="processed_event_blocked",
            table_name="processed_events",
            persistence_class=PERSIST_CLASS_IDEMPOTENCY_STORE,
            blocked=True,
            blocking_codes=hard_blocks,
            blocking_reason=hard_blocks[0],
            outcome=PERSIST_OUTCOME_BLOCKED,
            record_id=None,
            idempotency_key=event_hash,
            duration_ms=int((time.monotonic() - t0) * 1000),
            rule_path=rule_path,
        )
        emit_persistence_log(record)
        return False, record

    rule_path.append("RULE_1_IDEMPOTENCY_CHECK")
    existing = await session.execute(
        select(ProcessedEvents).where(ProcessedEvents.event_hash == event_hash)
    )
    if existing.scalar_one_or_none():
        elapsed = int((time.monotonic() - t0) * 1000)
        record = _make_persistence_record(
            attribution=attribution,
            event="processed_event_duplicate_rejected",
            table_name="processed_events",
            persistence_class=PERSIST_CLASS_IDEMPOTENCY_STORE,
            blocked=False,
            blocking_codes=["IDEMPOTENCY_DUPLICATE"],
            blocking_reason="IDEMPOTENCY_DUPLICATE",
            outcome=PERSIST_OUTCOME_DUPLICATE_REJECTED,
            record_id=None,
            idempotency_key=event_hash,
            duration_ms=elapsed,
            rule_path=rule_path,
        )
        emit_persistence_log(record)
        return False, record

    rule_path.append("RULE_2_INSERT")
    event_row = ProcessedEvents(
        event_hash=event_hash,
        event_type=event_type,
        user_id=user_id,
        raw_payload=raw_payload,
        correlation_id=attribution.correlation_id,
        execution_mode=attribution.execution_mode,
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
    )
    session.add(event_row)
    await session.flush()

    elapsed = int((time.monotonic() - t0) * 1000)
    record = _make_persistence_record(
        attribution=attribution,
        event="processed_event_recorded",
        table_name="processed_events",
        persistence_class=PERSIST_CLASS_IDEMPOTENCY_STORE,
        blocked=False,
        blocking_codes=[],
        blocking_reason=None,
        outcome=PERSIST_OUTCOME_SUCCESS,
        record_id=event_row.id,
        idempotency_key=event_hash,
        duration_ms=elapsed,
        rule_path=rule_path,
    )
    emit_persistence_log(record)
    return True, record
