import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from app.config import settings, SystemScope

logger = logging.getLogger(__name__)


@dataclass
class DecisionResult:
    action_type: str                       # NO_ACTION | TRIGGER_OUTREACH | RETRY_OUTREACH | BOOK_MEETING | CLOSE_CASE
    priority: str = "MEDIUM"
    channel: str = "NONE"                  # CALL | SMS | EMAIL | NONE
    retry_allowed: bool = False
    escalation_required: bool = False
    reason_codes: List[str] = field(default_factory=list)


def decide(
    *,
    user_id: int,
    contact_attempt: int,
    last_contact_time: Optional[datetime],
    call_connected: bool,
    meeting_booked: bool,
    ipbc_enrolled: bool,
    hws_behind: int,
    avg_eff_rating: float,
    last_activity_days: int,
    # LLM fields (ignored in MVP)
    llm_meeting_recommended: Optional[bool] = None,
    current_time: Optional[datetime] = None,
) -> DecisionResult:
    """
    Evaluate 7 decision rules in order. Stop at first match (except Rule 6).
    All rules are scope-gated per meta/project_classification.md.
    """
    now = current_time or datetime.utcnow()
    escalation = False

    # Rule 1 — Termination conditions
    if ipbc_enrolled or meeting_booked:
        logger.info("Student %s: CLOSE_CASE (resolved)", user_id)
        return DecisionResult(
            action_type="CLOSE_CASE",
            channel="NONE",
            retry_allowed=False,
            reason_codes=["CASE_RESOLVED"],
        )

    # Rule 2 — Max attempts reached
    if contact_attempt >= settings.max_attempts:
        logger.info("Student %s: max attempts reached (%d)", user_id, contact_attempt)
        # In MVP there is no channel fallback — close the case
        if settings.enable_channel_fallback:
            return DecisionResult(
                action_type="SEND_SMS_OR_EMAIL",
                channel="SMS",
                retry_allowed=False,
                reason_codes=["MAX_ATTEMPTS_REACHED"],
            )
        return DecisionResult(
            action_type="CLOSE_CASE",
            channel="NONE",
            retry_allowed=False,
            reason_codes=["MAX_ATTEMPTS_REACHED"],
        )

    # Rule 3 — First outreach
    if contact_attempt == 0:
        logger.info("Student %s: initial outreach via CALL", user_id)
        return DecisionResult(
            action_type="TRIGGER_OUTREACH",
            channel="CALL",
            retry_allowed=settings.enable_retry,
            reason_codes=["INITIAL_CONTACT"],
        )

    # Rule 4 — Retry eligibility (STANDARD / PRODUCTION only)
    if settings.enable_retry and not call_connected:
        if _retry_window_passed(last_contact_time, now):
            logger.info("Student %s: retry eligible", user_id)
            return DecisionResult(
                action_type="RETRY_OUTREACH",
                channel="CALL",
                retry_allowed=True,
                reason_codes=["RETRY_ELIGIBLE"],
            )

    # Rule 5 — LLM-driven intervention (PRODUCTION only)
    if settings.enable_llm and llm_meeting_recommended:
        logger.info("Student %s: LLM recommends meeting", user_id)
        return DecisionResult(
            action_type="BOOK_MEETING",
            channel="NONE",
            retry_allowed=False,
            reason_codes=["LLM_MEETING_TRIGGER"],
        )

    # Rule 6 — High-risk escalation (STANDARD / PRODUCTION only)
    # Does NOT stop — continues to Rule 7 to combine with another action
    if settings.enable_escalation:
        if hws_behind >= 3 or avg_eff_rating < 2.5 or last_activity_days > 7:
            logger.warning("Student %s: high-risk escalation", user_id)
            escalation = True

    # Rule 7 — Default
    logger.info("Student %s: no eligible action", user_id)
    return DecisionResult(
        action_type="NO_ACTION",
        channel="NONE",
        retry_allowed=False,
        escalation_required=escalation,
        reason_codes=["NO_ELIGIBLE_ACTION"] + (["HIGH_RISK_STUDENT"] if escalation else []),
    )


def _retry_window_passed(last_contact_time: Optional[datetime], now: datetime) -> bool:
    if last_contact_time is None:
        return True
    scope = settings.SYSTEM_SCOPE
    if scope == SystemScope.MVP:
        return False  # Never retry in MVP
    return (now - last_contact_time) >= timedelta(hours=24)
