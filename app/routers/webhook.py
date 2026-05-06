"""GHL webhook handler — idempotent, full state transitions + LLM analysis."""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OutreachHistory, ProcessedEvents, StudentOutreachTracking
from app.schemas import APIResponse, GHLWebhookPayload, VALID_GHL_EVENTS
from app.services.integrations.llm import analyze_transcript
from app.services.outreach import _log_transition
from app.state_machine import can_transition

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/ghl-update")
async def ghl_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    raw = await request.json()

    # Idempotency check
    event_hash = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    existing = await db.execute(
        select(ProcessedEvents).where(ProcessedEvents.event_hash == event_hash)
    )
    if existing.scalar_one_or_none():
        logger.info("Duplicate event %s — skipped", event_hash)
        return APIResponse.ok({"deduplicated": True})

    db.add(ProcessedEvents(
        event_hash=event_hash,
        event_type=raw.get("event_type"),
        user_id=raw.get("user_id"),
        raw_payload=raw,
    ))
    await db.flush()

    if raw.get("event_type") not in VALID_GHL_EVENTS:
        return APIResponse.fail("INVALID_EVENT", f"Unknown event_type: {raw.get('event_type')}")

    payload = GHLWebhookPayload(**raw)
    user_id = payload.user_id
    if user_id is None:
        return APIResponse.fail("MISSING_USER_ID", "Webhook payload missing user_id")

    tracking_row = await db.execute(
        select(StudentOutreachTracking).where(StudentOutreachTracking.user_id == user_id)
    )
    tracking_obj = tracking_row.scalar_one_or_none()
    if tracking_obj is None:
        return APIResponse.fail("NOT_FOUND", f"No outreach record for user {user_id}")

    old_state = tracking_obj.state
    llm_analysis = None
    to_state: str | None = None

    if payload.event_type in ("CALL_COMPLETED", "SMS_RESPONSE", "EMAIL_RESPONSE"):
        outcome = (payload.outcome or "").lower()
        to_state = "RESPONDED" if outcome in ("connected", "responded", "replied", "yes") else "NO_RESPONSE"
        if payload.transcript:
            llm_analysis = await analyze_transcript(
                payload.transcript,
                user_id,
                tracking_obj.current_attempt,
                tracking_obj.checkpoint_type,
            )

    elif payload.event_type == "TRANSCRIPT_READY":
        if payload.transcript:
            llm_analysis = await analyze_transcript(
                payload.transcript,
                user_id,
                tracking_obj.current_attempt,
                tracking_obj.checkpoint_type,
            )
        to_state = "ANALYZED"

    if to_state and to_state != old_state and can_transition(old_state, to_state):
        tracking_obj.state = to_state
        await _log_transition(
            db, tracking_obj.id, user_id, old_state, to_state,
            f"webhook:{payload.event_type}", actor="webhook"
        )

    # Update latest history entry with response data + LLM output
    history_row = await db.execute(
        select(OutreachHistory)
        .where(OutreachHistory.user_id == user_id)
        .order_by(OutreachHistory.created_at.desc())
        .limit(1)
    )
    latest = history_row.scalar_one_or_none()
    if latest:
        latest.response_payload = raw
        if llm_analysis:
            latest.llm_analysis = llm_analysis

    await db.commit()
    logger.info(
        "Webhook processed | user=%s event=%s state=%s→%s",
        user_id, payload.event_type, old_state, tracking_obj.state,
    )
    return APIResponse.ok({
        "processed": True,
        "user_id": user_id,
        "new_state": tracking_obj.state,
    })
