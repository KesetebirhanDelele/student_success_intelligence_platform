import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StudentOutreachTracking
from app.schemas import APIResponse, GHLWebhookPayload, VALID_GHL_EVENTS
from app.state_machine import validate_transition, StateViolationError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/ghl-update")
def ghl_webhook(
    payload: GHLWebhookPayload,
    db: Session = Depends(get_db),
) -> APIResponse:
    if payload.event_type not in VALID_GHL_EVENTS:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_INPUT", "message": f"Unknown event_type: {payload.event_type}"},
        )

    # Validate user exists
    record: StudentOutreachTracking | None = (
        db.query(StudentOutreachTracking)
        .filter_by(UserID=payload.user_id)
        .order_by(StudentOutreachTracking.ContactAttempt.desc())
        .first()
    )
    if not record:
        logger.warning("Webhook for unknown user %d", payload.user_id)
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"No outreach record for user {payload.user_id}"},
        )

    now = datetime.utcnow()

    if payload.event_type == "CALL_COMPLETED":
        if payload.call_connected:
            new_state = "RESPONDED"
        else:
            new_state = "NO_RESPONSE"
        record.CallConnected = payload.call_connected or False
        record.CallDuration = payload.call_duration or 0

    elif payload.event_type == "TRANSCRIPT_READY":
        new_state = "ANALYZED"
        record.Transcript = payload.transcript

    elif payload.event_type in ("SMS_RESPONSE", "EMAIL_RESPONSE"):
        new_state = "RESPONDED"

    else:
        new_state = record.State  # no transition for other events

    # Apply state transition
    if new_state != record.State:
        try:
            validate_transition(record.State, new_state)
            record.State = new_state
        except StateViolationError as exc:
            logger.error("Webhook state violation for user %d: %s", payload.user_id, exc)
            raise HTTPException(
                status_code=400,
                detail={"code": "STATE_VIOLATION", "message": str(exc)},
            )

    record.UpdatedAt = now
    db.commit()
    logger.info(
        "Webhook processed for user %d: event=%s new_state=%s",
        payload.user_id, payload.event_type, record.State,
    )
    return APIResponse.ok({})
