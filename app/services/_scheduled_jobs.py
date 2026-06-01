"""
Async APScheduler job callbacks for SSIP scheduled operations.

Three jobs live here:
  run_monthly_reports     — 1st of month 02:00 UTC: assemble + generate for prior month
  run_daily_mssql_sync    — nightly 01:00 UTC: refresh all SQL Server mirrors
  run_month_end_capture   — last day of month 23:30 UTC: capture historical mirror state

Each function is pure async logic that takes explicit parameters; thin wrappers in
scheduler.py read _scheduler_config and delegate here to keep that file under 500 lines.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Monthly report job ────────────────────────────────────────────────────────

async def run_monthly_reports(
    snapshot_month: date,
    execution_mode: str,
    config_version_id: Optional[str],
) -> None:
    """
    Assemble snapshots for snapshot_month then generate reports for all cohorts.
    SHADOW-safe: writes warehouse tables only, never dispatches providers.
    """
    from app.database import AsyncSessionLocal
    from app.services.snapshot import assemble_all_active_snapshots
    from app.services.report import generate_cohort_report

    correlation_id = str(uuid.uuid4())

    logger.info(json.dumps({
        "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
        "event": "monthly_report_job_started",
        "snapshot_month": str(snapshot_month),
        "execution_mode": execution_mode,
        "correlation_id": correlation_id,
    }))

    try:
        async with AsyncSessionLocal() as db:
            snap_result = await assemble_all_active_snapshots(
                snapshot_month=snapshot_month,
                db=db,
                execution_mode=execution_mode,
                config_version_id=config_version_id,
            )
        logger.info(json.dumps({
            "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
            "event": "monthly_snapshots_assembled",
            "snapshot_month": str(snapshot_month),
            "result": snap_result,
            "correlation_id": correlation_id,
        }))

        segments = [
            "NEWCOMERS", "ENGAGEMENT", "CAP_HOPEFULS",
            "LAUNCH_HOPEFULS", "PLACEMENT_HOPEFULS",
        ]
        total_generated = total_errors = 0
        for segment in segments:
            async with AsyncSessionLocal() as db:
                result = await generate_cohort_report(
                    cohort_id=segment,
                    report_month=snapshot_month,
                    db=db,
                    execution_mode=execution_mode,
                )
                total_generated += result.get("generated", 0)
                total_errors += result.get("errors", 0)

        logger.info(json.dumps({
            "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
            "event": "monthly_report_job_completed",
            "snapshot_month": str(snapshot_month),
            "segments_processed": len(segments),
            "total_generated": total_generated,
            "total_errors": total_errors,
            "execution_mode": execution_mode,
            "correlation_id": correlation_id,
        }))

    except Exception as exc:
        logger.error(json.dumps({
            "timestamp": _now_iso(), "level": "error", "service": "scheduled_jobs",
            "event": "monthly_report_job_failed",
            "error_class": type(exc).__name__,
            "error": str(exc),
            "snapshot_month": str(snapshot_month),
            "correlation_id": correlation_id,
        }))
        raise


# ── Daily MSSQL sync job ──────────────────────────────────────────────────────

async def run_daily_mssql_sync() -> None:
    """
    Refresh all SQL Server mirrors in PostgreSQL so live tabs show current data.
    Runs at 01:00 UTC — one hour before run_monthly_reports (02:00 UTC) so the
    report pipeline always assembles from fresh data on the 1st of each month.
    Covers: JRP students, IPBC students, payment totals, campaign activity.
    """
    from app.database import AsyncSessionLocal
    from app.services.sync import sync_from_mssql, sync_ipbc_students, sync_campaign_activity
    from app.services.payment_sync import sync_payments

    correlation_id = str(uuid.uuid4())
    logger.info(json.dumps({
        "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
        "event": "daily_mssql_sync_job_started", "correlation_id": correlation_id,
    }))

    results: dict = {}
    try:
        async with AsyncSessionLocal() as db:
            results["mssql"] = await sync_from_mssql(db)
        async with AsyncSessionLocal() as db:
            results["ipbc"] = await sync_ipbc_students(db)
        async with AsyncSessionLocal() as db:
            results["payments"] = await sync_payments(db)
        async with AsyncSessionLocal() as db:
            results["campaign_activity"] = await sync_campaign_activity(db)

        logger.info(json.dumps({
            "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
            "event": "daily_mssql_sync_job_completed",
            "statuses": {k: v.get("status", "done") for k, v in results.items()},
            "correlation_id": correlation_id,
        }))

    except Exception as exc:
        logger.error(json.dumps({
            "timestamp": _now_iso(), "level": "error", "service": "scheduled_jobs",
            "event": "daily_mssql_sync_job_failed",
            "error_class": type(exc).__name__,
            "error": str(exc),
            "correlation_id": correlation_id,
        }))
        raise


# ── Month-end state capture job ───────────────────────────────────────────────

async def run_month_end_capture(snapshot_month: date) -> None:
    """
    Capture current SQL Server mirror state into student_mirror_history so
    relative fields (LastActivityDays, LastLoginDays) are historically accurate
    when the 1st-of-month report job assembles snapshots for this month.
    Safe to re-run: ON CONFLICT DO UPDATE overwrites the existing capture.
    """
    from app.database import AsyncSessionLocal
    from app.services.sync import capture_month_state

    correlation_id = str(uuid.uuid4())
    logger.info(json.dumps({
        "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
        "event": "month_end_capture_job_started",
        "snapshot_month": str(snapshot_month),
        "correlation_id": correlation_id,
    }))

    try:
        async with AsyncSessionLocal() as db:
            result = await capture_month_state(snapshot_month, db)

        logger.info(json.dumps({
            "timestamp": _now_iso(), "level": "info", "service": "scheduled_jobs",
            "event": "month_end_capture_job_completed",
            "snapshot_month": str(snapshot_month),
            "captured": result.get("captured", 0),
            "correlation_id": correlation_id,
        }))

    except Exception as exc:
        logger.error(json.dumps({
            "timestamp": _now_iso(), "level": "error", "service": "scheduled_jobs",
            "event": "month_end_capture_job_failed",
            "error_class": type(exc).__name__,
            "error": str(exc),
            "snapshot_month": str(snapshot_month),
            "correlation_id": correlation_id,
        }))
        raise
