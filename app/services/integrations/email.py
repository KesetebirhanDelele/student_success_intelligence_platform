"""Email integration — shadow-safe. Dispatched via GHL email workflow."""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def build_email_payload(student: dict, attempt: int) -> dict:
    first = student.get("FirstName", "")
    hws = student.get("HWsBehind", 0)
    return {
        "to": student.get("Email"),
        "subject": f"Checking in — {first}",
        "body": (
            f"Hi {first},\n\n"
            f"Your student success advisor noticed you may need some support. "
            f"You currently have {hws} assignment(s) behind. "
            f"We'd love to connect and help you get back on track.\n\n"
            f"Please reply to this email or book a time at your convenience.\n\n"
            f"Best,\nStudent Success Team"
        ),
        "executionMode": settings.EXECUTION_MODE,
        "metadata": {
            "user_id": student.get("UserID"),
            "attempt": attempt,
            "checkpoint": student.get("PathName"),
        },
    }


async def send_email(payload: dict) -> dict:
    """
    SHADOW: log payload, return simulated response.
    LIVE: route through GHL email workflow.
    """
    user_id = payload["metadata"]["user_id"]

    if settings.is_shadow:
        logger.info(
            "[SHADOW] Email | user_id=%s to=%s attempt=%s",
            user_id,
            payload["to"],
            payload["metadata"]["attempt"],
        )
        return {"status": "simulated", "execution_mode": "SHADOW"}

    logger.warning("Email LIVE mode not yet wired — payload logged only")
    return {"status": "not_implemented"}
