import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EligibilityResult:
    eligible: bool
    priority: str = "MEDIUM"          # LOW | MEDIUM | HIGH
    checkpoint_type: str = ""
    reason_codes: List[str] = field(default_factory=list)


def check_eligibility(
    *,
    user_id: int,
    checkpoint_type: str,
    hws_behind: int,
    avg_eff_rating: float,
    last_activity_days: int,
    email: Optional[str],
    phone_number: Optional[str],
    last_contact_time: Optional[datetime],
    contact_attempt: int,
    state: Optional[str],
    current_time: Optional[datetime] = None,
) -> EligibilityResult:
    """
    Evaluate eligibility in rule order. Returns on first disqualifying rule.
    Priority assignment always runs after eligibility is confirmed.
    """
    now = current_time or datetime.utcnow()

    # Rule 1 — No contact info
    if not email and not phone_number:
        logger.debug("Student %s: no contact info", user_id)
        return EligibilityResult(eligible=False, reason_codes=["NO_CONTACT_INFO"])

    # Rule 2 — Case already closed / resolved
    if state in ("CLOSED", "RESOLVED"):
        logger.debug("Student %s: case already closed", user_id)
        return EligibilityResult(eligible=False, reason_codes=["CASE_ALREADY_CLOSED"])

    # Rule 3 — Contacted within exclusion window
    if last_contact_time:
        window = timedelta(days=settings.exclusion_window_days)
        if (now - last_contact_time) < window:
            logger.debug("Student %s: recently contacted", user_id)
            return EligibilityResult(eligible=False, reason_codes=["RECENTLY_CONTACTED"])

    # Rule 4 — Checkpoint-specific thresholds
    if checkpoint_type == "POST_COMPLETION":
        # Eligible if completed program and not enrolled in IPBC
        # (ipbc_enrolled is tracked in outreach tracking; not in trigger data)
        pass  # Falls through to default eligible
    else:
        # SQL / SSRS / SSIS — academic metric thresholds
        meets_threshold = (
            hws_behind >= settings.min_hw_threshold
            or avg_eff_rating < settings.min_effort_threshold
            or last_activity_days > settings.max_inactivity_days
        )
        if not meets_threshold:
            logger.debug("Student %s: does not meet academic thresholds", user_id)
            return EligibilityResult(
                eligible=False,
                checkpoint_type=checkpoint_type,
                reason_codes=["BELOW_THRESHOLD"],
            )

    # Rule 5 — Default eligible, assign priority
    priority = _assign_priority(hws_behind, avg_eff_rating, last_activity_days)
    return EligibilityResult(
        eligible=True,
        priority=priority,
        checkpoint_type=checkpoint_type,
        reason_codes=["ELIGIBLE_DEFAULT"],
    )


def _assign_priority(hws_behind: int, avg_eff_rating: float, last_activity_days: int) -> str:
    if (
        hws_behind >= 3
        or avg_eff_rating < 2.5
        or last_activity_days > 7
    ):
        return "HIGH"
    if (
        hws_behind >= settings.min_hw_threshold
        or avg_eff_rating < settings.min_effort_threshold
        or last_activity_days > settings.max_inactivity_days
    ):
        return "MEDIUM"
    return "LOW"
