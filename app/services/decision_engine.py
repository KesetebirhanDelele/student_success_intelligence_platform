from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.services.eligibility import EligibilityResult
from app.state_machine import is_terminal

logger = logging.getLogger(__name__)


def decide(
    student: dict,
    tracking: Optional[dict],
    eligibility: EligibilityResult,
) -> str:
    """
    7-rule deterministic decision engine.
    Returns: TRIGGER_OUTREACH | RETRY_OUTREACH | ESCALATE | CLOSE | NO_ACTION
    """
    user_id = student.get("UserID")

    # Rule 1: no contact info → close
    if not eligibility.eligible and eligibility.skip_reason == "NO_CONTACT_INFO":
        logger.info("Student %s → CLOSE (no contact info)", user_id)
        return "CLOSE"

    # Rule 2: not eligible → no action
    if not eligibility.eligible:
        logger.debug("Student %s → NO_ACTION (%s)", user_id, eligibility.skip_reason)
        return "NO_ACTION"

    # Rule 3: no prior tracking → first outreach
    if tracking is None:
        logger.info("Student %s → TRIGGER_OUTREACH (new)", user_id)
        return "TRIGGER_OUTREACH"

    # Rule 4: terminal state → no action
    if is_terminal(tracking["state"]):
        return "NO_ACTION"

    # Rule 5: retry states — check attempt limit and window
    if tracking["state"] in ("NO_RESPONSE", "RETRY"):
        if tracking["current_attempt"] >= settings.MAX_ATTEMPTS:
            logger.info(
                "Student %s → ESCALATE (max_attempts=%d reached)",
                user_id,
                settings.MAX_ATTEMPTS,
            )
            return "ESCALATE"
        if not _retry_window_passed(tracking.get("next_retry_at")):
            logger.debug("Student %s → NO_ACTION (retry window not passed)", user_id)
            return "NO_ACTION"
        logger.info(
            "Student %s → RETRY_OUTREACH (attempt %d)",
            user_id,
            tracking["current_attempt"] + 1,
        )
        return "RETRY_OUTREACH"

    # Rule 6: high priority student still in CONTACTED — escalate
    if eligibility.priority == "HIGH" and tracking["state"] == "CONTACTED":
        logger.info("Student %s → ESCALATE (high priority, no response yet)", user_id)
        return "ESCALATE"

    # Rule 7: already tracked in a non-terminal active state → no action
    return "NO_ACTION"


def _retry_window_passed(next_retry_at: Optional[datetime]) -> bool:
    if next_retry_at is None:
        return True
    now = datetime.now(tz=timezone.utc)
    if next_retry_at.tzinfo is None:
        next_retry_at = next_retry_at.replace(tzinfo=timezone.utc)
    return now >= next_retry_at
