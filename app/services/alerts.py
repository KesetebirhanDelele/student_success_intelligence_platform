"""Alert aggregation service — surfaces operational health issues for the dashboard.

Single exported coroutine: gather_alerts(db, is_shadow, mssql_configured, last_run)

Kept completely stateless: all state is passed in so the function is trivially
testable without touching settings globals or the scheduler module.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudentOutreachTracking

logger = logging.getLogger(__name__)


async def gather_alerts(
    db: AsyncSession,
    *,
    is_shadow: bool,
    mssql_configured: bool,
    last_run: str | None,
) -> list[dict]:
    """Return ordered alert list (CRITICAL first, then WARNING, then INFO).

    Args:
        db:               Active async DB session.
        is_shadow:        True when EXECUTION_MODE == SHADOW.
        mssql_configured: True when MSSQL_HOST/USER/DATABASE are all set.
        last_run:         ISO-8601 string from get_last_run_at(), or None.
    """
    alerts: list[dict] = []
    now = datetime.now(tz=timezone.utc)

    # ── CRITICAL: SQL Server not configured ───────────────────────────────────
    if not mssql_configured:
        alerts.append({
            "severity": "CRITICAL",
            "message": "SQL Server not configured — student sync is unavailable.",
            "student_id": None,
            "recommended_action": (
                "Add MSSQL_HOST, MSSQL_USER, MSSQL_PASS to .env and restart."
            ),
        })

    # ── WARNING: students stuck in CONTACTED > 48 h ───────────────────────────
    stuck_cutoff = now - timedelta(hours=48)
    stuck_result = await db.execute(
        select(StudentOutreachTracking.user_id).where(
            StudentOutreachTracking.state == "CONTACTED",
            StudentOutreachTracking.last_contact_at < stuck_cutoff,
        )
    )
    for row in stuck_result.fetchall():
        alerts.append({
            "severity": "WARNING",
            "message": (
                f"Student {row.user_id} has been in CONTACTED state "
                "for over 48 hours with no response recorded."
            ),
            "student_id": row.user_id,
            "recommended_action": (
                "Investigate student history or use Force Retry / Escalate."
            ),
        })

    # ── WARNING: NO_RESPONSE with missed retry window ─────────────────────────
    missed_result = await db.execute(
        select(StudentOutreachTracking.user_id).where(
            StudentOutreachTracking.state == "NO_RESPONSE",
            StudentOutreachTracking.next_retry_at < now,
        )
    )
    for row in missed_result.fetchall():
        alerts.append({
            "severity": "WARNING",
            "message": (
                f"Student {row.user_id} is in NO_RESPONSE and their retry "
                "window has passed — no retry was triggered."
            ),
            "student_id": row.user_id,
            "recommended_action": (
                "Use Force Retry or verify the scheduler is running."
            ),
        })

    # ── WARNING: scheduler never ran or > 26 h ago ────────────────────────────
    if last_run is None:
        alerts.append({
            "severity": "WARNING",
            "message": (
                "Scheduler has not run since system start. "
                "No automated outreach has been executed."
            ),
            "student_id": None,
            "recommended_action": (
                "Verify scheduler is active and the daily cron is configured correctly."
            ),
        })
    else:
        last_run_dt = datetime.fromisoformat(last_run)
        if (now - last_run_dt) > timedelta(hours=26):
            alerts.append({
                "severity": "WARNING",
                "message": f"Scheduler last ran {last_run} — more than 26 hours ago.",
                "student_id": None,
                "recommended_action": (
                    "Check scheduler logs or trigger a manual batch via Trigger Outreach."
                ),
            })

    # ── INFO: SHADOW mode active ───────────────────────────────────────────────
    if is_shadow:
        alerts.append({
            "severity": "INFO",
            "message": (
                "System is running in SHADOW mode. "
                "No outbound calls, SMS, or emails are being sent."
            ),
            "student_id": None,
            "recommended_action": (
                "This is expected in shadow/testing mode. "
                "Set EXECUTION_MODE=LIVE to enable real outreach."
            ),
        })

    return alerts
