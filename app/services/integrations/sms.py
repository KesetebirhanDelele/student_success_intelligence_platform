"""SMS integration — shadow-safe. Dispatched via GHL SMS workflow."""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def build_sms_payload(student: dict, attempt: int) -> dict:
    first = student.get("FirstName", "")
    hws = student.get("HWsBehind", 0)
    return {
        "to": student.get("PhoneNumber"),
        "body": (
            f"Hi {first}, this is your student success advisor. "
            f"I noticed you're {hws} assignment(s) behind. "
            f"Reply YES to schedule a quick check-in call."
        ),
        "executionMode": settings.EXECUTION_MODE,
        "metadata": {
            "user_id": student.get("UserID"),
            "attempt": attempt,
            "checkpoint": student.get("PathName"),
        },
    }


async def send_sms(payload: dict) -> dict:
    """
    SHADOW: log payload, return simulated response.
    LIVE: route through GHL SMS workflow.
    """
    user_id = payload["metadata"]["user_id"]

    if settings.is_shadow:
        logger.info(
            "[SHADOW] SMS | user_id=%s phone=%s attempt=%s",
            user_id,
            payload["to"],
            payload["metadata"]["attempt"],
        )
        return {"status": "simulated", "execution_mode": "SHADOW"}

    # LIVE: integrate via GHL SMS endpoint or Twilio
    logger.warning("SMS LIVE mode not yet wired — payload logged only")
    return {"status": "not_implemented"}
