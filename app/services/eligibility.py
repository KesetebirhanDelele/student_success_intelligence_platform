from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

HW_BEHIND_MIN = 2
EFF_RATING_MAX = 3.0
INACTIVITY_MIN = 5
HIGH_RISK_HW = 3
HIGH_RISK_EFF = 2.5
HIGH_RISK_INACTIVITY = 7


@dataclass
class EligibilityResult:
    eligible: bool
    priority: str = "NORMAL"   # HIGH | NORMAL
    checkpoint_type: str = ""
    reason_codes: list[str] = field(default_factory=list)
    skip_reason: str = ""


def check_eligibility(student: dict) -> EligibilityResult:
    """5 ordered rules. Returns on first disqualification."""
    user_id = student.get("UserID")
    path = student.get("PathName", "")

    # Rule 1: contact info required
    has_phone = bool(student.get("PhoneNumber"))
    has_email = bool(student.get("Email"))
    if not has_phone and not has_email:
        return EligibilityResult(eligible=False, skip_reason="NO_CONTACT_INFO")

    # Rule 2: POST_COMPLETION — always eligible (no academic thresholds)
    if path == "POST_COMPLETION":
        return EligibilityResult(
            eligible=True,
            priority="NORMAL",
            checkpoint_type=path,
            reason_codes=["POST_COMPLETION_TRACK"],
        )

    # Rule 3: homeworks behind threshold
    hws = student.get("HWsBehind", 0)
    if hws < HW_BEHIND_MIN:
        return EligibilityResult(eligible=False, skip_reason="HW_THRESHOLD_NOT_MET")

    # Rule 4: effort rating threshold
    eff = student.get("AvgEffRating", 5.0)
    if eff >= EFF_RATING_MAX:
        return EligibilityResult(eligible=False, skip_reason="EFFORT_THRESHOLD_NOT_MET")

    # Rule 5: inactivity threshold
    inactivity = student.get("LastActivityDays", 0)
    if inactivity < INACTIVITY_MIN:
        return EligibilityResult(eligible=False, skip_reason="ACTIVITY_THRESHOLD_NOT_MET")

    is_high = (
        hws >= HIGH_RISK_HW
        or eff < HIGH_RISK_EFF
        or inactivity > HIGH_RISK_INACTIVITY
    )
    priority = "HIGH" if is_high else "NORMAL"

    logger.debug("Student %s eligible | priority=%s path=%s", user_id, priority, path)
    return EligibilityResult(
        eligible=True,
        priority=priority,
        checkpoint_type=path,
        reason_codes=[f"HW:{hws}", f"EFF:{eff:.1f}", f"INACTIVITY:{inactivity}d"],
    )
