"""Student segmentation service — classifies students into operational cohorts."""
from __future__ import annotations

from datetime import datetime, timezone

# Rule definitions for documentation / UI display
SEGMENT_RULES: dict[str, str] = {
    "NEWCOMERS":          "IPBCStartDate within last 90 days",
    "HYPER_ACTIVE":       "Past10DaysLogon >= 7 AND AvgEffRating > 90",
    "CAP_HOPEFULS":       "AttendancePercentage > 50 AND IPBCStartDate not null",
    "LAUNCH_HOPEFULS":    "AttendancePercentage > 70 AND LastActivitySection contains 'CAP Project'",
    "PLACEMENT_HOPEFULS": "AttendancePercentage > 70 AND LastActivitySection contains 'Launch'",
}

ALL_SEGMENTS = list(SEGMENT_RULES.keys())

# Role → allowed sections filter (None = no restriction)
ROLE_SECTION_FILTER: dict[str, list[str] | None] = {
    "Support":        None,
    "Mentor":         None,   # no assignment table yet — show all
    "Instructor":     None,   # caller passes explicit section
    "Placement Team": ["Launch", "Placement"],
}


def _section(student: dict) -> str:
    """Return the best available section string for a student."""
    return str(
        student.get("LastActivitySection")
        or student.get("CurrentSection")
        or student.get("PathName")
        or ""
    )


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

    section = _section(student)
    attendance = float(student.get("AttendancePercentage") or 0)
    has_ipbc_start = student.get("IPBCStartDate") is not None

    # CAP_HOPEFULS: in IPBC programme, attendance > 50%
    if has_ipbc_start and attendance > 50:
        segments.append("CAP_HOPEFULS")

    # LAUNCH_HOPEFULS: nearing Launch, attendance > 70%, in CAP Project section
    if attendance > 70 and "CAP Project" in section:
        segments.append("LAUNCH_HOPEFULS")

    # PLACEMENT_HOPEFULS: in Launch/placement pipeline, attendance > 70%
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
                kw in _section(s)
                for kw in ["Launch", "Placement"]
            )
        ]

    if role == "Instructor" and section:
        return [s for s in students if section in _section(s)]

    return students
