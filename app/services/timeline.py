"""Unified student timeline — merges all event types chronologically."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIInsight, GHLMessage, OutreachHistory, StateTransitionLog, StudentNote

logger = logging.getLogger(__name__)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _sort_key(event: dict) -> datetime:
    ts = event.get("ts")
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


async def build_timeline(user_id: int, db: AsyncSession) -> list[dict[str, Any]]:
    """
    Return a chronological (newest-first) list of all events for a student.
    Event types: OUTREACH, STATE_CHANGE, NOTE, AI_NOTE, AI_INSIGHT, COMMUNICATION, PAYMENT.
    """
    events: list[dict] = []

    # Outreach attempts
    oh_result = await db.execute(
        select(OutreachHistory)
        .where(OutreachHistory.user_id == user_id)
        .order_by(OutreachHistory.created_at.desc())
        .limit(50)
    )
    for h in oh_result.scalars():
        events.append({
            "ts": _iso(h.created_at),
            "type": "OUTREACH",
            "channel": h.channel,
            "label": f"{h.channel or 'Outreach'} — Attempt #{h.attempt_number}",
            "detail": f"Action: {h.action} | Status: {h.simulated_status} | Mode: {h.execution_mode}",
            "state_before": h.state_before,
            "state_after": h.state_after,
            "badge": h.execution_mode,
        })

    # State transitions
    st_result = await db.execute(
        select(StateTransitionLog)
        .where(StateTransitionLog.user_id == user_id)
        .order_by(StateTransitionLog.created_at.desc())
        .limit(50)
    )
    for t in st_result.scalars():
        events.append({
            "ts": _iso(t.created_at),
            "type": "STATE_CHANGE",
            "channel": None,
            "label": f"State changed: {t.from_state} → {t.to_state}",
            "detail": f"Trigger: {t.trigger} | Actor: {t.actor}",
            "state_before": t.from_state,
            "state_after": t.to_state,
            "badge": t.actor,
        })

    # Notes
    note_result = await db.execute(
        select(StudentNote)
        .where(StudentNote.user_id == user_id)
        .order_by(StudentNote.created_at.desc())
        .limit(30)
    )
    for n in note_result.scalars():
        events.append({
            "ts": _iso(n.created_at),
            "type": "AI_NOTE" if n.is_ai_generated else "NOTE",
            "channel": None,
            "label": f"{'AI Note' if n.is_ai_generated else 'Note'} — {n.author}",
            "detail": n.content[:300],
            "state_before": None,
            "state_after": None,
            "badge": "AI" if n.is_ai_generated else n.author,
        })

    # AI insights
    ai_result = await db.execute(
        select(AIInsight)
        .where(AIInsight.user_id == user_id)
        .order_by(AIInsight.created_at.desc())
        .limit(20)
    )
    for a in ai_result.scalars():
        events.append({
            "ts": _iso(a.created_at),
            "type": "AI_INSIGHT",
            "channel": None,
            "label": f"AI Insight: {a.insight_type}",
            "detail": (a.content_text or "")[:300],
            "state_before": None,
            "state_after": None,
            "badge": a.insight_type,
        })

    # GHL messages (communication sync)
    ghl_result = await db.execute(
        select(GHLMessage)
        .where(GHLMessage.user_id == user_id)
        .order_by(GHLMessage.synced_at.desc())
        .limit(50)
    )
    for m in ghl_result.scalars():
        ts_val = m.ghl_created_at or m.synced_at
        events.append({
            "ts": _iso(ts_val),
            "type": "COMMUNICATION",
            "channel": m.channel,
            "label": f"{m.channel} {m.direction.title()} (GHL)",
            "detail": (m.body or "")[:300],
            "state_before": None,
            "state_after": None,
            "badge": "GHL_READ",
        })

    events.sort(key=_sort_key, reverse=True)
    return events
