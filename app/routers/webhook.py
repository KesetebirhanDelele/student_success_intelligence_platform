"""
GHL webhook handler — governance-safe, idempotent, append-only lineage.

Governance alignment:
  FAD-4  — OutreachHistory is append-only; response data is appended as a NEW
            row, never written back onto an existing row (no UPDATE semantics)
  CID-1  — correlation_id extracted from X-Correlation-ID header or generated
  IML-1  — attribution propagated immutably to repository layer
  INV-5  — no persistence without correlation_id
  AP-RT2 — webhook path is original execution; never tagged as replay
"""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentOutreachTracking
from app.repositories.repository import append_outreach_history, record_processed_event
from app.routers._router_helpers import (
    build_request_attribution,
    extract_causation_id,
    extract_correlation_id,
    make_governance_meta,
)
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

    # ── Governance attribution ─────────────────────────────────────────────────
    correlation_id = extract_correlation_id(dict(request.headers))
    causation_id = extract_causation_id(dict(request.headers))
    attribution = build_request_attribution(
        correlation_id,
        causation_id=causation_id,
        execution_type="original",
    )
    meta = make_governance_meta(attribution)

    # ── Idempotency via governance repository layer (INV-5, CID-1) ────────────
    event_hash = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    inserted, pe_record = await record_processed_event(
        db,
        event_hash=event_hash,
        event_type=raw.get("event_type"),
        user_id=raw.get("user_id"),
        attribution=attribution,
        raw_payload=raw,
    )
    if not inserted:
        logger.info(
            "Duplicate webhook event %s — skipped (correlation_id=%s)",
            event_hash, correlation_id,
        )
        return APIResponse.ok(
            {"deduplicated": True, "event_hash": event_hash},
            meta=meta.as_dict(),
        )

    if raw.get("event_type") not in VALID_GHL_EVENTS:
        return APIResponse.fail(
            "INVALID_EVENT",
            f"Unknown event_type: {raw.get('event_type')}",
            meta=meta.as_dict(),
        )

    payload = GHLWebhookPayload(**raw)
    user_id = payload.user_id
    if user_id is None:
        return APIResponse.fail(
            "MISSING_USER_ID",
            "Webhook payload missing user_id",
            meta=meta.as_dict(),
        )

    tracking_row = await db.execute(
        select(StudentOutreachTracking).where(StudentOutreachTracking.user_id == user_id)
    )
    tracking_obj = tracking_row.scalar_one_or_none()
    if tracking_obj is None:
        return APIResponse.fail(
            "NOT_FOUND",
            f"No outreach record for user {user_id}",
            meta=meta.as_dict(),
        )

    old_state = tracking_obj.state
    llm_analysis = None
    to_state: str | None = None

    if payload.event_type in ("CALL_COMPLETED", "SMS_RESPONSE", "EMAIL_RESPONSE"):
        outcome = (payload.outcome or "").lower()
        to_state = (
            "RESPONDED"
            if outcome in ("connected", "responded", "replied", "yes")
            else "NO_RESPONSE"
        )
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
            f"webhook:{payload.event_type}", actor="webhook",
        )

    # ── Append webhook response as NEW governance-safe outreach history row ────
    # FAD-4: OutreachHistory is append-only — no UPDATE on existing rows.
    # Webhook response data is recorded as a distinct event entry, not a
    # mutation of the prior attempt row. This preserves full lineage.
    webhook_payload: dict = {**raw}
    if llm_analysis:
        webhook_payload["llm_analysis"] = llm_analysis

    await append_outreach_history(
        db,
        tracking_id=tracking_obj.id,
        user_id=user_id,
        checkpoint_type=tracking_obj.checkpoint_type,
        attempt_number=tracking_obj.current_attempt,
        attribution=attribution,
        channel="GHL_WEBHOOK",
        action=f"WEBHOOK_{payload.event_type}",
        state_before=old_state,
        state_after=tracking_obj.state,
        payload=webhook_payload,
        decision=f"WEBHOOK_PROCESSED:{payload.event_type}",
    )

    await db.commit()
    logger.info(
        "Webhook processed | user=%s event=%s state=%s→%s correlation_id=%s",
        user_id, payload.event_type, old_state, tracking_obj.state, correlation_id,
    )
    return APIResponse.ok(
        {
            "processed": True,
            "user_id": user_id,
            "new_state": tracking_obj.state,
        },
        meta=meta.as_dict(),
    )
