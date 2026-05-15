"""Student segmentation service — classifies students into operational cohorts."""
from __future__ import annotations

from datetime import datetime, timezone

# Rule definitions for documentation / UI display
SEGMENT_RULES: dict[str, str] = {
    "NEWCOMERS":          "IPBCStartDate within last 90 days",
    "HYPER_ACTIVE":       "Past10DaysLogon >= 7 AND AvgEffRating > 90",
    "CAP_HOPEFULS":       "AttendancePercentage > 30 AND CurrentSection contains IPBC",
    "LAUNCH_HOPEFULS":    "AttendancePercentage > 55 AND CurrentSection contains CAP",
    "PLACEMENT_HOPEFULS": "AttendancePercentage > 70 AND CurrentSection contains Launch",
}

ALL_SEGMENTS = list(SEGMENT_RULES.keys())

# Role → allowed sections filter (None = no restriction)
ROLE_SECTION_FILTER: dict[str, list[str] | None] = {
    "Support":        None,
    "Mentor":         None,   # no assignment table yet — show all
    "Instructor":     None,   # caller passes explicit section
    "Placement Team": ["Launch", "Placement"],
}


def classify_student(student: dict) -> list[str]:
    """Return the list of segment names this student belongs to."""
    segments: list[str] = []
    now = datetime.now(tz=timezone.utc)

    # NEWCOMERS
    start = student.get("IPBCStartDate")
    if start is not None:
        if isinstance(start, str):
            try:
                start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                start = None
        if start is not None:
            if not hasattr(start, "tzinfo") or start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if (now - start).days <= 90:
                segments.append("NEWCOMERS")

    # HYPER_ACTIVE
    logons = int(student.get("Past10DaysLogon") or 0)
    eff = float(student.get("AvgEffRating") or 0)
    if logons >= 7 and eff > 90:
        segments.append("HYPER_ACTIVE")

    section = str(student.get("CurrentSection") or student.get("PathName") or "")
    attendance = float(student.get("AttendancePercentage") or 0)

    if attendance > 30 and "IPBC" in section:
        segments.append("CAP_HOPEFULS")

    if attendance > 55 and "CAP" in section:
        segments.append("LAUNCH_HOPEFULS")

    if attendance > 70 and "Launch" in section:
        segments.append("PLACEMENT_HOPEFULS")

    return segments


def segment_summary(students: list[dict]) -> dict[str, int]:
    """Aggregate count per segment across all students."""
    counts: dict[str, int] = {k: 0 for k in ALL_SEGMENTS}
    for s in students:
        for seg in classify_student(s):
            counts[seg] += 1
    return counts


def filter_by_role(students: list[dict], role: str | None, section: str | None = None) -> list[dict]:
    """
    Apply role-based filtering to a student list.
    Mentor/Support return all (no assignment table yet).
    Placement Team: restrict to Launch + Placement sections.
    Instructor: restrict to one section if section param is provided.
    """
    if not role or role == "Support":
        return students

    if role == "Placement Team":
        return [
            s for s in students
            if any(
                kw in (s.get("CurrentSection") or s.get("PathName") or "")
                for kw in ["Launch", "Placement"]
            )
        ]

    if role == "Instructor" and section:
        return [
            s for s in students
            if section in (s.get("CurrentSection") or s.get("PathName") or "")
        ]

    return students
