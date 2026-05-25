"""Priority scoring engine — URGENT / HIGH / MEDIUM / LOW with recommended actions."""
from __future__ import annotations

from dataclasses import dataclass, field

# Score thresholds — score >= threshold maps to that level
URGENT_THRESHOLD = 90
HIGH_THRESHOLD = 60
MEDIUM_THRESHOLD = 30

# Scoring weights
HW_POINTS_EACH = 10   # per HW behind, capped at 5 HWs → max 50
EFF_WEIGHT = 7        # (5.0 - rating) × 7, max 35 at rating 0.0
INACTIVITY_POINTS = 2 # per day, capped at 25 days → max 50


@dataclass
class PriorityResult:
    score: int
    level: str  # URGENT | HIGH | MEDIUM | LOW
    recommended_action: str
    reason_codes: list[str] = field(default_factory=list)


def score_student(student: dict, tracking: dict | None = None) -> PriorityResult:
    """
    Additive priority score 0–135.
      HWsBehind:        0–50 (10 pts each, capped at 5 HWs)
      AvgEffRating:     0–35 ((5.0 - rating) × 7, floor 0)
      LastActivityDays: 0–50 (2 pts/day, capped at 25 days)
    """
    hws = int(student.get("HWsBehind") or 0)
    eff_raw = student.get("AvgEffRating")
    eff = float(eff_raw) if eff_raw is not None else 5.0
    inactivity = int(student.get("LastActivityDays") or 0)

    hw_score = min(hws * HW_POINTS_EACH, 50)
    eff_score = max(0, round((5.0 - eff) * EFF_WEIGHT))
    inactivity_score = min(inactivity * INACTIVITY_POINTS, 50)

    score = hw_score + eff_score + inactivity_score
    reason_codes = [
        f"HW:{hws}(+{hw_score})",
        f"EFF:{eff:.1f}(+{eff_score})",
        f"INACTIVE:{inactivity}d(+{inactivity_score})",
    ]

    level = _level(score)
    recommended_action = _action(level, tracking)

    return PriorityResult(
        score=score,
        level=level,
        recommended_action=recommended_action,
        reason_codes=reason_codes,
    )


def _level(score: int) -> str:
    if score >= URGENT_THRESHOLD:
        return "URGENT"
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def risk_level_for_display(profile: object | None) -> str:
    """Map a student ORM row (or any object with priority fields) to a 3-tier risk label.

    Collapses the 4-tier priority scale (URGENT/HIGH/MEDIUM/LOW) to 3 tiers
    (HIGH/MEDIUM/LOW) for display.  URGENT folds into HIGH.
    Returns "UNKNOWN" when profile is None.

    Accepts any object with HWsBehind, AvgEffRating, LastActivityDays attributes —
    no ORM import needed, no circular dependency risk.
    """
    if profile is None:
        return "UNKNOWN"
    d = {
        "HWsBehind": getattr(profile, "HWsBehind", 0),
        "AvgEffRating": getattr(profile, "AvgEffRating", 5.0),
        "LastActivityDays": getattr(profile, "LastActivityDays", 0),
    }
    level = score_student(d).level
    if level in ("URGENT", "HIGH"):
        return "HIGH"
    return level  # MEDIUM | LOW


def _action(level: str, tracking: dict | None) -> str:
    state = (tracking or {}).get("state", "")
    if state == "INTERVENTION_REQUIRED":
        return "ESCALATE"
    if state == "NO_RESPONSE":
        return "FORCE_RETRY"
    return {
        "URGENT": "ESCALATE",
        "HIGH": "FORCE_RETRY",
        "MEDIUM": "TRIGGER_OUTREACH",
        "LOW": "MONITOR",
    }[level]
