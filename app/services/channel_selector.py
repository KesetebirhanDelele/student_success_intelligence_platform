from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Priority order: CALL → SMS → EMAIL
_PHONE_CHANNELS = ["CALL", "SMS"]
_EMAIL_CHANNEL = "EMAIL"


def select_channel(student: dict, attempt_number: int) -> Optional[str]:
    """
    Select outreach channel for a given attempt.

    Attempt 1 → CALL (if phone available) else EMAIL
    Attempt 2 → SMS  (if phone available) else EMAIL
    Attempt 3 → EMAIL (if email available) else CALL/SMS fallback
    """
    has_phone = bool(student.get("PhoneNumber"))
    has_email = bool(student.get("Email"))

    candidates: list[str] = []
    if has_phone:
        candidates.extend(_PHONE_CHANNELS)
    if has_email:
        candidates.append(_EMAIL_CHANNEL)

    if not candidates:
        logger.warning("Student %s has no contact channels", student.get("UserID"))
        return None

    idx = (attempt_number - 1) % len(candidates)
    channel = candidates[idx]
    logger.debug(
        "Student %s attempt %d → channel %s",
        student.get("UserID"),
        attempt_number,
        channel,
    )
    return channel
