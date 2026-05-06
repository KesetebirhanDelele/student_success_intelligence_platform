"""Core outreach orchestration — full pipeline, shadow-safe."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    OutreachHistory,
    ProcessedEvents,
    StateTransitionLog,
    StudentOutreachTracking,
    StudentTriggerData,
)
from app.services.channel_selector import select_channel
from app.services.decision_engine import decide
from app.services.eligibility import check_eligibility
from app.services.integrations.email import build_email_payload, send_email
from app.services.integrations.ghl import build_ghl_payload, trigger_ghl_workflow
from app.services.integrations.sms import build_sms_payload, send_sms
from app.services.integrations.synthflow import build_call_payload, place_call
from app.services.sync import sync_from_mssql
from app.state_machine import StateViolationError, can_transition, validate_transition

logger = logging.getLogger(__name__)

CONCURRENCY_LIMIT = 50
CHECKPOINTS = {"SQL", "SSRS", "SSIS", "POST_COMPLETION"}


async def run_outreach_batch(db: AsyncSession, checkpoint_type: str) -> dict:
    """Full outreach cycle for one checkpoint. Returns summary counts."""
    logger.info("Batch start | mode=%s checkpoint=%s", settings.EXECUTION_MODE, checkpoint_type)

    # Best-effort SQL Server sync before processing
    await sync_from_mssql(db)

    result = await db.execute(select(StudentTriggerData))
    students = result.scalars().all()

    triggered = skipped = retried = errors = 0
    processed = 0

    for student in students:
        if processed >= CONCURRENCY_LIMIT:
            break

        s = {c.key: getattr(student, c.key) for c in student.__table__.columns}
        path = s.get("PathName", "")

        if checkpoint_type == "POST_COMPLETION" and path != "POST_COMPLETION":
            skipped += 1
            continue
        if checkpoint_type != "POST_COMPLETION" and path != checkpoint_type:
            skipped += 1
            continue

        eligibility = check_eligibility(s)

        tracking_row = await db.execute(
            select(StudentOutreachTracking).where(
                StudentOutreachTracking.user_id == s["UserID"],
                StudentOutreachTracking.checkpoint_type == checkpoint_type,
            )
        )
        tracking_obj = tracking_row.scalar_one_or_none()
        tracking = (
            {
                "state": tracking_obj.state,
                "current_attempt": tracking_obj.current_attempt,
                "next_retry_at": tracking_obj.next_retry_at,
            }
            if tracking_obj
            else None
        )

        decision = decide(s, tracking, eligibility)

        try:
            if decision == "TRIGGER_OUTREACH":
                await _execute_outreach(db, s, checkpoint_type, tracking_obj, is_retry=False)
                triggered += 1
            elif decision == "RETRY_OUTREACH":
                await _execute_outreach(db, s, checkpoint_type, tracking_obj, is_retry=True)
                retried += 1
            elif decision == "ESCALATE":
                await _escalate(db, s, checkpoint_type, tracking_obj)
                triggered += 1
            elif decision == "CLOSE":
                await _close_case(db, s, checkpoint_type, tracking_obj, "NO_CONTACT_INFO")
                skipped += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.error("Error processing student %s: %s", s["UserID"], exc, exc_info=True)
            errors += 1

        processed += 1

    summary = {
        "checkpoint_type": checkpoint_type,
        "triggered": triggered,
        "skipped": skipped,
        "retried": retried,
        "errors": errors,
    }
    logger.info("Batch complete | %s", summary)
    return summary


async def _execute_outreach(
    db: AsyncSession,
    student: dict,
    checkpoint_type: str,
    tracking_obj: Optional[StudentOutreachTracking],
    is_retry: bool,
) -> None:
    user_id = student["UserID"]

    if tracking_obj is None:
        tracking_obj = StudentOutreachTracking(
            user_id=user_id,
            checkpoint_type=checkpoint_type,
            state="QUEUED",
            current_attempt=0,
        )
        db.add(tracking_obj)
        await db.flush()
        await _log_transition(db, tracking_obj.id, user_id, "ELIGIBLE", "QUEUED", "batch_trigger")
    else:
        old_state = tracking_obj.state
        target = "RETRY" if is_retry else "QUEUED"
        if not _apply_transition(tracking_obj, target, "retry_trigger" if is_retry else "batch_trigger"):
            return
        await _log_transition(db, tracking_obj.id, user_id, old_state, tracking_obj.state, "retry_trigger" if is_retry else "batch_trigger")

    attempt = tracking_obj.current_attempt + 1
    channel = select_channel(student, attempt)

    if channel is None:
        await _close_case(db, student, checkpoint_type, tracking_obj, "NO_CHANNEL")
        return

    payload, action_label = await _build_payload(student, channel, attempt)
    response = await _dispatch(channel, payload)

    old_state = tracking_obj.state
    if not _apply_transition(tracking_obj, "CONTACTED", action_label):
        return

    tracking_obj.current_attempt = attempt
    tracking_obj.last_contact_at = datetime.now(tz=timezone.utc)
    tracking_obj.next_retry_at = datetime.now(tz=timezone.utc) + timedelta(hours=settings.RETRY_INTERVAL_HOURS)

    await db.flush()
    await _log_transition(db, tracking_obj.id, user_id, old_state, "CONTACTED", action_label)

    db.add(OutreachHistory(
        tracking_id=tracking_obj.id,
        user_id=user_id,
        checkpoint_type=checkpoint_type,
        attempt_number=attempt,
        channel=channel,
        action=action_label,
        execution_mode=settings.EXECUTION_MODE,
        simulated_status="NOT_SENT" if settings.is_shadow else "SENT",
        payload=payload,
        response_payload=response,
        decision="RETRY_OUTREACH" if is_retry else "TRIGGER_OUTREACH",
        state_before=old_state,
        state_after="CONTACTED",
    ))
    await db.commit()


async def _build_payload(student: dict, channel: str, attempt: int) -> tuple[dict, str]:
    if channel == "CALL":
        payload = {
            "synthflow": build_call_payload(student, attempt),
            "ghl": build_ghl_payload(student, channel, attempt),
        }
        action = "CALL_SIMULATED" if settings.is_shadow else "CALL_EXECUTED"
    elif channel == "SMS":
        payload = build_sms_payload(student, attempt)
        action = "SMS_SIMULATED" if settings.is_shadow else "SMS_SENT"
    else:
        payload = build_email_payload(student, attempt)
        action = "EMAIL_SIMULATED" if settings.is_shadow else "EMAIL_SENT"
    return payload, action


async def _dispatch(channel: str, payload: dict) -> dict:
    if channel == "CALL":
        call_resp = await place_call(payload.get("synthflow", {}))
        ghl_resp = await trigger_ghl_workflow(payload.get("ghl", {}))
        return {"call": call_resp, "ghl": ghl_resp}
    if channel == "SMS":
        return await send_sms(payload)
    return await send_email(payload)


async def _escalate(
    db: AsyncSession,
    student: dict,
    checkpoint_type: str,
    tracking_obj: Optional[StudentOutreachTracking],
) -> None:
    if tracking_obj is None:
        return
    user_id = student["UserID"]
    old_state = tracking_obj.state
    if not _apply_transition(tracking_obj, "INTERVENTION_REQUIRED", "escalate"):
        return
    await _log_transition(db, tracking_obj.id, user_id, old_state, "INTERVENTION_REQUIRED", "escalate")
    db.add(OutreachHistory(
        tracking_id=tracking_obj.id,
        user_id=user_id,
        checkpoint_type=checkpoint_type,
        attempt_number=tracking_obj.current_attempt,
        action="ESCALATED",
        execution_mode=settings.EXECUTION_MODE,
        simulated_status="N/A",
        decision="ESCALATE",
        state_before=old_state,
        state_after="INTERVENTION_REQUIRED",
    ))
    await db.commit()


async def _close_case(
    db: AsyncSession,
    student: dict,
    checkpoint_type: str,
    tracking_obj: Optional[StudentOutreachTracking],
    reason: str,
) -> None:
    if tracking_obj is None:
        return
    user_id = student["UserID"]
    old_state = tracking_obj.state
    if not _apply_transition(tracking_obj, "CLOSED", f"close:{reason}"):
        return
    await _log_transition(db, tracking_obj.id, user_id, old_state, "CLOSED", f"close:{reason}")
    db.add(OutreachHistory(
        tracking_id=tracking_obj.id,
        user_id=user_id,
        checkpoint_type=checkpoint_type,
        attempt_number=tracking_obj.current_attempt,
        action="CASE_CLOSED",
        execution_mode=settings.EXECUTION_MODE,
        simulated_status="N/A",
        decision="CLOSE",
        state_before=old_state,
        state_after="CLOSED",
    ))
    await db.commit()


async def execute_manual_action(
    db: AsyncSession,
    user_id: int,
    action_type: str,
    notes: Optional[str],
) -> dict:
    tracking_row = await db.execute(
        select(StudentOutreachTracking).where(StudentOutreachTracking.user_id == user_id)
    )
    tracking_obj = tracking_row.scalar_one_or_none()
    if tracking_obj is None:
        return {"status": "not_found"}

    action_map = {
        "CLOSE_CASE": "CLOSED",
        "BOOK_MEETING": "RESOLVED",
        "FORCE_RETRY": "RETRY",
        "ESCALATE": "INTERVENTION_REQUIRED",
    }
    to_state = action_map.get(action_type)
    if to_state is None:
        return {"status": "invalid_action"}

    if action_type == "FORCE_RETRY" and tracking_obj.current_attempt >= settings.MAX_ATTEMPTS:
        return {
            "status": "max_attempts_reached",
            "current_attempt": tracking_obj.current_attempt,
            "max": settings.MAX_ATTEMPTS,
        }

    old_state = tracking_obj.state
    if not _apply_transition(tracking_obj, to_state, f"manual:{action_type}"):
        return {"status": "invalid_transition", "from": old_state, "to": to_state}

    await _log_transition(
        db, tracking_obj.id, user_id, old_state, to_state,
        f"manual:{action_type}", actor="manual"
    )

    entry = OutreachHistory(
        tracking_id=tracking_obj.id,
        user_id=user_id,
        checkpoint_type=tracking_obj.checkpoint_type,
        attempt_number=tracking_obj.current_attempt,
        action=action_type,
        execution_mode=settings.EXECUTION_MODE,
        simulated_status="N/A",
        decision=action_type,
        state_before=old_state,
        state_after=to_state,
    )
    if notes:
        entry.response_payload = {"notes": notes}
    db.add(entry)
    await db.commit()
    return {"status": "ok", "from_state": old_state, "to_state": to_state}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_transition(tracking_obj: StudentOutreachTracking, to_state: str, trigger: str) -> bool:
    try:
        validate_transition(tracking_obj.state, to_state, trigger)
        tracking_obj.state = to_state
        return True
    except StateViolationError as exc:
        logger.warning("State violation: %s", exc)
        return False


async def _log_transition(
    db: AsyncSession,
    tracking_id: int,
    user_id: int,
    from_state: str,
    to_state: str,
    trigger: str,
    actor: str = "system",
    meta: Optional[dict] = None,
) -> None:
    db.add(StateTransitionLog(
        tracking_id=tracking_id,
        user_id=user_id,
        from_state=from_state,
        to_state=to_state,
        trigger=trigger,
        actor=actor,
        meta=meta,
    ))
    await db.flush()
