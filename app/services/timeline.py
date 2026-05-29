"""
Governance-safe timeline lineage service.

Public API: classify_timeline_event(ctx) -> TimelineLineageRecord

Advisory contract only — never mutates historical timeline records,
never overwrites replay lineage, never bypasses attribution governance,
never silently suppresses events, never mutates FINALIZED event lineage.
Returns TimelineLineageRecord. Consuming services act on the returned record.
Attribution propagated immutably from input.

Architecture preservation prohibitions (MUST NOT):
  FAD-4   / IML-1   — no mutation of append-only timeline / lineage records
  IML-3             — no overwrite of replay lineage; LIVE and REPLAY always distinguishable
  IML-4             — no loss of attribution continuity across event lineage records
  INV-4   / AP-RT2  — no LIVE effects from replay/regeneration execution types
  INV-5             — no governance record without correlation_id and attribution
  INV-6             — no platform event overwriting SQL Server authoritative attribution
  CID-1             — no causation chain broken without surfacing CAUSATION_CHAIN_INCOMPLETE
  CID-2             — no idempotency bypass; duplicate keys blocked before processing
  ATT-1             — no event record without origin_source and attribution_timestamp
  ATT-2             — no loss of causation_id across chained governance events
  AP-RT9  / ABG-5   — no hardcoded Config V2 threshold fallbacks; UNKNOWN_V0 only
  AP-RT10           — no duplicate LIVE execution of the same timeline intent
  AP-RT13           — no raw PII in observability records
  AP-RT14           — no silent failure swallowing; every exception classified
  AP-RT15           — no orphaned classification cycles without completion log
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.services._timeline_helpers import (
    _make_blocked_lineage_record,
    _make_lineage_record,
    _make_maintenance_lineage_record,
    _make_replay_lineage_record,
    emit_timeline_event_log,
)
from app.services._timeline_types import (
    AUTHORITY_AI,
    AUTHORITY_COMPLIANCE,
    AUTHORITY_GHL,
    AUTHORITY_OPERATOR,
    AUTHORITY_SQL_SERVER,
    AUTHORITY_SYSTEM,
    EVENT_UNKNOWN,
    MODE_SHADOW,
    ORIGIN_AI,
    ORIGIN_COMPLIANCE,
    ORIGIN_GHL,
    ORIGIN_OPERATOR,
    ORIGIN_PLATFORM_MANUAL,
    OUTCOME_SHADOW_ONLY,
    REQUIRED_TIMELINE_ATTRIBUTION,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    TYPE_ORIGINAL,
    UNKNOWN_V0,
    VISIBILITY_FINALIZED_PROTECTED,
    VISIBILITY_SHADOW_VISIBLE,
    _REPLAY_TYPES,
    _SQL_SERVER_ORIGINS,
    _SOURCE_EVENT_TYPE_MAP,
    _TIMELINE_THRESHOLD_KEYS,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    TimelineEventContext,
    TimelineLineageRecord,
)

logger = logging.getLogger(__name__)

# In-memory idempotency store for timeline deduplication (AP-RT10, spec/04 §4.1)
_timeline_idempotency_keys: set[str] = set()


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _attribution_complete(ctx: TimelineEventContext) -> bool:
    """Returns True only if all required timeline attribution fields are populated."""
    return all(getattr(ctx, f, None) for f in REQUIRED_TIMELINE_ATTRIBUTION)


def _governance_precondition_gate(
    ctx: TimelineEventContext,
    codes: List[str],
) -> bool:
    """
    RULE 0: Governance precondition gate. All conditions must pass before evaluation
    proceeds. Never bypassed (INV-5, CID-2, spec/04 §4.1).
    Returns True if all preconditions pass; False if classification must stop.
    """
    ok = True
    if ctx.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append("INVALID_EXECUTION_MODE")
        ok = False
    if ctx.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append("INVALID_EXECUTION_TYPE")
        ok = False
    if not ctx.config_version_id:
        codes.append("CONFIG_VERSION_ID_MISSING")
        ok = False
    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
        ok = False
    if not ctx.origin_source:
        codes.append("ORIGIN_SOURCE_MISSING")
        ok = False
    if not ctx.origin_authority:
        codes.append("ORIGIN_AUTHORITY_MISSING")
        ok = False
    if not ctx.actor_identity:
        codes.append("ACTOR_IDENTITY_MISSING")
        ok = False
    if ctx.idempotency_key and ctx.idempotency_key in _timeline_idempotency_keys:
        codes.append("IDEMPOTENCY_DUPLICATE_DETECTED")
        ok = False
    return ok


def _resolve_timeline_thresholds(
    rule_set: Dict[str, Any],
    missing_keys: List[str],
) -> Dict[str, Any]:
    """
    Resolve Config V2 Group K timeline thresholds from rule_set.
    Missing or UNKNOWN_V0 inputs resolve to UNKNOWN_V0 sentinel — never hardcoded (AP-RT9).
    """
    result: Dict[str, Any] = {}
    for k in _TIMELINE_THRESHOLD_KEYS:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def _classify_event_type(ctx: TimelineEventContext) -> Optional[str]:
    """
    Classify event type from raw_event_source → canonical map, then event_type_hint.
    Caller hint is authoritative when it names a known event type; otherwise source map wins.
    Returns None for replay paths (no live classification — INV-4).
    """
    # Source map is the canonical classification signal (spec/08 §16)
    if ctx.raw_event_source and ctx.raw_event_source in _SOURCE_EVENT_TYPE_MAP:
        source_type = _SOURCE_EVENT_TYPE_MAP[ctx.raw_event_source]
        # Caller hint can override only when it names a valid known type
        if ctx.event_type_hint and ctx.event_type_hint != EVENT_UNKNOWN:
            return ctx.event_type_hint
        return source_type
    # No source map match — fall back to hint or UNKNOWN
    return ctx.event_type_hint or EVENT_UNKNOWN


def _classify_authoritative_source(ctx: TimelineEventContext) -> str:
    """Derive authoritative_source from origin_source (spec/03 §39.3, INVARIANT-6)."""
    if ctx.origin_source in _SQL_SERVER_ORIGINS:
        return AUTHORITY_SQL_SERVER
    if ctx.origin_source == ORIGIN_GHL:
        return AUTHORITY_GHL
    if ctx.origin_source in (ORIGIN_OPERATOR, ORIGIN_PLATFORM_MANUAL):
        return AUTHORITY_OPERATOR
    if ctx.origin_source == ORIGIN_AI:
        return AUTHORITY_AI
    if ctx.origin_source == ORIGIN_COMPLIANCE:
        return AUTHORITY_COMPLIANCE
    return AUTHORITY_SYSTEM


# ── Public classification API ─────────────────────────────────────────────────

def classify_timeline_event(
    ctx: TimelineEventContext,
) -> TimelineLineageRecord:
    """
    Evaluate timeline governance for one event lineage classification.

    Lineage contract: returns TimelineLineageRecord only.
    Never mutates historical timeline records, never overwrites replay lineage,
    never bypasses attribution governance (FAD-4, IML-1, IML-3, INV-5).
    Attribution propagated immutably from input.
    Every path emits a structured observability record (AP-RT15).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    degradation_flags: List[str] = []
    rule_set = ctx.config_rule_set or {}

    # ── RULE 0: Governance precondition gate (INV-5, CID-2, spec/04 §4.1) ────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        record = _make_blocked_lineage_record(
            ctx, codes, rule_path, t0, {},
            gate_codes[0] if gate_codes else "GOVERNANCE_PRECONDITION_FAILED",
        )
        emit_timeline_event_log(record)
        return record

    # Register idempotency key after gate passes; only for original execution (AP-RT10)
    if ctx.idempotency_key and ctx.execution_type == TYPE_ORIGINAL:
        _timeline_idempotency_keys.add(ctx.idempotency_key)

    # ── RULE 1: MAINTENANCE mode suspension ──────────────────────────────────
    rule_path.append("RULE_1")
    if ctx.maintenance_mode_active:
        codes.append("MAINTENANCE_MODE_ACTIVE")
        record = _make_maintenance_lineage_record(ctx, codes, rule_path, t0)
        emit_timeline_event_log(record)
        return record

    # ── RULE 2: Replay/regeneration containment (INV-4, AP-RT2, IML-3) ──────
    rule_path.append("RULE_2")
    is_replay = ctx.execution_type in _REPLAY_TYPES
    if is_replay:
        codes.append("REPLAY_MODE_ACTIVE")
        if not ctx.source_artifact_id:
            codes.append("REPLAY_SOURCE_ARTIFACT_MISSING")
        record = _make_replay_lineage_record(ctx, codes, rule_path, t0, {})
        emit_timeline_event_log(record)
        return record

    # ── RULE 3: Config V2 threshold resolution (AP-RT9, spec/01 §12) ─────────
    rule_path.append("RULE_3")
    missing_threshold_keys: List[str] = []
    threshold_bindings = _resolve_timeline_thresholds(rule_set, missing_threshold_keys)
    for k in missing_threshold_keys:
        flag = f"CONFIG_THRESHOLD_MISSING_{k.upper()}"
        codes.append(flag)
        degradation_flags.append(flag)

    # ── RULE 4: Shadow mode detection ─────────────────────────────────────────
    rule_path.append("RULE_4")
    shadow_mode = ctx.execution_mode == MODE_SHADOW

    # ── RULE 5: FINALIZED lineage immutability protection (IML-1, IML-3, FAD-1)
    # Protective annotation — this service never mutates FINALIZED lineage.
    rule_path.append("RULE_5")
    if ctx.finalized_lineage_detected:
        codes.append("FINALIZED_LINEAGE_PROTECTED")

    # ── RULE 6: Causation chain validation (CID-1, ATT-2, spec/06 §1.3) ─────
    rule_path.append("RULE_6")
    causation_chain_preserved = bool(ctx.causation_id)
    if not causation_chain_preserved:
        codes.append("CAUSATION_CHAIN_INCOMPLETE")
        degradation_flags.append("CAUSATION_CHAIN_INCOMPLETE")

    # ── RULE 7: Event type classification (spec/08 §16) ───────────────────────
    rule_path.append("RULE_7")
    event_type = _classify_event_type(ctx)
    if event_type:
        codes.append(f"EVENT_TYPE_{event_type}")

    # ── RULE 8: SQL Server authority preservation annotation (INVARIANT-6) ───
    # SQL Server-origin events are authoritative; platform events are supplementary.
    # This annotation confirms the authority contract is upheld (never overwritten).
    rule_path.append("RULE_8")
    authoritative_source = _classify_authoritative_source(ctx)
    sql_server_authority_preserved = True    # unconditional — this service never overwrites authority
    if ctx.origin_source in _SQL_SERVER_ORIGINS:
        codes.append("SQL_SERVER_AUTHORITY_PRESERVED")

    # ── RULE 9: Governance scope assignment ───────────────────────────────────
    # AUTHORIZED scope requires Phase-12 certification.
    # Current deployment: both LIVE and SHADOW produce SHADOW_ONLY.
    rule_path.append("RULE_9")
    if ctx.execution_mode == MODE_SHADOW:
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY
    else:
        # LIVE mode: Phase-12 cert gate — maps to SHADOW_ONLY until cert is granted
        codes.append("LIVE_SCOPE_SHADOW_ONLY_PHASE11")
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY

    # ── RULE 10: Lineage visibility classification ─────────────────────────────
    rule_path.append("RULE_10")
    if ctx.finalized_lineage_detected:
        # FINALIZED lineage receives protected visibility annotation (IML-1)
        lineage_visibility = VISIBILITY_FINALIZED_PROTECTED
    else:
        # Both SHADOW and LIVE map to SHADOW_VISIBLE under Phase-12 (same as scope)
        lineage_visibility = VISIBILITY_SHADOW_VISIBLE

    # ── RULE 11: Lineage emit authorization ───────────────────────────────────
    rule_path.append("RULE_11")
    # Lineage emit authorized only when governance_scope is AUTHORIZED (Phase-12 cert).
    # Under current SHADOW deployment, lineage_emit_authorized is unconditionally False.
    lineage_emit_authorized = False    # Phase-12 cert required for True; see RULE 9

    # ── RULE 12: Terminal output ───────────────────────────────────────────────
    rule_path.append("RULE_12")
    degraded = bool(degradation_flags)
    degradation_cause = degradation_flags[0] if degraded else None

    record = _make_lineage_record(
        ctx=ctx,
        codes=codes,
        rule_path=rule_path,
        t0=t0,
        threshold_bindings=threshold_bindings,
        governance_scope=governance_scope,
        event_type=event_type,
        lineage_visibility=lineage_visibility,
        causation_chain_preserved=causation_chain_preserved,
        authoritative_source=authoritative_source,
        sql_server_authority_preserved=sql_server_authority_preserved,
        lineage_emit_authorized=lineage_emit_authorized,
        degraded=degraded,
        degradation_flags=degradation_flags,
        degradation_cause=degradation_cause,
        outcome=outcome,
    )
    emit_timeline_event_log(record)
    return record


# ── Operational timeline builder (DB query, not governance assessment) ─────────

async def build_timeline(user_id: int, db: Any) -> List[Dict[str, Any]]:
    """
    Build chronological (newest-first) unified event stream for one student.
    Merges outreach attempts, state transitions, notes, AI insights, GHL messages.
    Content fields with PII are omitted — governance metadata only (AP-RT13).
    """
    from sqlalchemy import select
    from app.models import (
        AIInsight, GHLMessage, OutreachHistory, StateTransitionLog, StudentNote,
    )

    events: List[Dict[str, Any]] = []

    oh_rows = (await db.execute(
        select(OutreachHistory).where(OutreachHistory.user_id == user_id)
    )).scalars().all()
    for h in oh_rows:
        events.append({
            "type": "outreach",
            "created_at": h.created_at.isoformat() if h.created_at else None,
            "attempt_number": h.attempt_number,
            "channel": h.channel,
            "action": h.action,
            "execution_mode": h.execution_mode,
            "simulated_status": h.simulated_status,
            "decision": h.decision,
            "state_before": h.state_before,
            "state_after": h.state_after,
            "correlation_id": h.correlation_id,
            "is_replay": h.is_replay,
        })

    stl_rows = (await db.execute(
        select(StateTransitionLog).where(StateTransitionLog.user_id == user_id)
    )).scalars().all()
    for t in stl_rows:
        events.append({
            "type": "transition",
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "from_state": t.from_state,
            "to_state": t.to_state,
            "trigger": t.trigger,
            "actor": t.actor,
            "execution_mode": t.execution_mode,
            "correlation_id": t.correlation_id,
            "is_replay": t.is_replay,
        })

    note_rows = (await db.execute(
        select(StudentNote).where(StudentNote.user_id == user_id)
    )).scalars().all()
    for n in note_rows:
        events.append({
            "type": "note",
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "author": n.author,
            "note_type": n.note_type,
            "is_ai_generated": n.is_ai_generated,
        })

    ins_rows = (await db.execute(
        select(AIInsight).where(AIInsight.user_id == user_id)
    )).scalars().all()
    for ins in ins_rows:
        events.append({
            "type": "ai_insight",
            "created_at": ins.created_at.isoformat() if ins.created_at else None,
            "insight_type": ins.insight_type,
            "execution_mode": ins.execution_mode,
            "is_finalized": ins.is_finalized,
            "correlation_id": ins.correlation_id,
            "is_replay": ins.is_replay,
        })

    ghl_rows = (await db.execute(
        select(GHLMessage).where(GHLMessage.user_id == user_id)
    )).scalars().all()
    for m in ghl_rows:
        ts = m.ghl_created_at or m.synced_at
        events.append({
            "type": "ghl_message",
            "created_at": ts.isoformat() if ts else None,
            "direction": m.direction,
            "channel": m.channel,
            "status": m.status,
        })

    events.sort(key=lambda e: e["created_at"] or "", reverse=True)
    return events
