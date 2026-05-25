"""Shared date/time utilities for lifecycle tabs and future warehouse ETL.

All functions are pure (no I/O, no global state) and timezone-aware.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def to_isostr(v: Any) -> str | None:
    """Return ISO-8601 string for a datetime/date, or str(v), or None."""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def weeks_in_program(ipbc_start: Any) -> int | None:
    """Calculate full weeks elapsed since program start.

    Accepts a datetime object, an ISO-8601 string, or None.
    Returns None when the input cannot be parsed.
    """
    if not ipbc_start:
        return None
    now = datetime.now(tz=timezone.utc)
    if isinstance(ipbc_start, str):
        try:
            ipbc_start = datetime.fromisoformat(ipbc_start.replace("Z", "+00:00"))
        except Exception:
            return None
    if ipbc_start.tzinfo is None:
        ipbc_start = ipbc_start.replace(tzinfo=timezone.utc)
    days = (now - ipbc_start).days
    return max(0, days // 7)


def hw_submitted_days(last_submitted: Any, fallback_days: int | None) -> int | None:
    """Parse LastSubmitted → days since last submission.

    Handles "YYYY-MM-DD HH:MM:SS.ffffff" and ISO variants.
    Falls back to LastActivityDays when the field is absent or unparseable.
    """
    if not last_submitted:
        return fallback_days
    now = datetime.now(tz=timezone.utc)
    try:
        s = str(last_submitted).strip().split(".")[0].replace(" ", "T")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return fallback_days


def active_student_flag(active_status: Any) -> int:
    """Return 1 if active_status represents an active student, else 0."""
    raw = str(active_status or "").strip().lower()
    return 1 if raw in ("1", "active", "true", "yes") else 0


def serialize_datetime_fields(d: dict, keys: tuple) -> None:
    """In-place ISO-stringify the named datetime keys in a dict."""
    for k in keys:
        if d.get(k) and hasattr(d[k], "isoformat"):
            d[k] = d[k].isoformat()
