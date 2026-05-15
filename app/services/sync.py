"""SQL Server → PostgreSQL sync service (TriggerData + InterviewPrep)."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import fetch_interview_prep_from_mssql, fetch_students_from_mssql
from app.models import StudentInterviewPrep, StudentTriggerData

logger = logging.getLogger(__name__)

# Columns that map to NOT NULL model fields
_REQUIRED_FIELDS: tuple[str, ...] = ("UserID", "HWsBehind", "AvgEffRating")


def _validate_row(row: dict[str, Any]) -> list[str]:
    return [f for f in _REQUIRED_FIELDS if row.get(f) is None]


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert SQL Server–specific types to Python/PostgreSQL-compatible ones."""
    result = dict(row)
    # SQL Server date → datetime (PostgreSQL DateTime needs datetime, not date)
    if isinstance(result.get("IPBCStartDate"), date) and not isinstance(result.get("IPBCStartDate"), datetime):
        result["IPBCStartDate"] = datetime.combine(result["IPBCStartDate"], datetime.min.time())
    # Convert bit/pyodbc booleans if needed
    fee_paid = result.get("FeePaid")
    if fee_paid is not None and not isinstance(fee_paid, bool):
        result["FeePaid"] = bool(fee_paid)
    return result


def _serialize_for_jsonb(row: dict[str, Any]) -> dict[str, Any]:
    """Make a dict safe for JSONB storage (convert dates/datetimes to ISO strings)."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


async def sync_from_mssql(db: AsyncSession) -> dict:
    """
    Upsert all rows from AI_ChatBot_TriggerData into the local PostgreSQL mirror.
    Invalid rows are quarantined in failures[]; valid rows always commit.
    """
    students, error = await fetch_students_from_mssql()
    if not students:
        logger.warning("No students from SQL Server — %s", error or "unknown reason")
        return {
            "status": "connection_error",
            "rows_scanned": 0, "rows_successful": 0, "rows_failed": 0,
            "added": 0, "updated": 0, "connected": False,
            "error": error, "failures": [],
        }

    added = updated = 0
    failures: list[dict] = []

    for raw_row in students:
        missing = _validate_row(raw_row)
        if missing:
            user_id = raw_row.get("UserID")
            reason = f"Missing required fields: {', '.join(missing)}"
            failures.append({"user_id": user_id, "reason": reason})
            logger.warning("Skipping UserID=%s — %s", user_id, reason)
            continue

        row = _coerce_row(raw_row)
        existing = await db.get(StudentTriggerData, row["UserID"])
        if existing:
            for key, val in row.items():
                if hasattr(existing, key):
                    setattr(existing, key, val)
            updated += 1
        else:
            db.add(StudentTriggerData(**{k: v for k, v in row.items() if hasattr(StudentTriggerData, k)}))
            added += 1

    try:
        await db.commit()
    except Exception as exc:
        logger.error("Sync commit failed: %s", exc)
        await db.rollback()
        return {
            "status": "connection_error",
            "rows_scanned": len(students), "rows_successful": 0,
            "rows_failed": len(students), "added": 0, "updated": 0,
            "connected": True, "error": str(exc),
            "failures": [{"user_id": None, "reason": f"Database commit failed: {exc}"}],
        }

    rows_scanned = len(students)
    rows_successful = added + updated
    rows_failed = len(failures)
    status = "partial_success" if failures else "success"

    logger.info(
        "MSSQL TriggerData sync: status=%s scanned=%d added=%d updated=%d failed=%d",
        status, rows_scanned, added, updated, rows_failed,
    )
    return {
        "status": status,
        "rows_scanned": rows_scanned, "rows_successful": rows_successful,
        "rows_failed": rows_failed, "added": added, "updated": updated,
        "connected": True, "error": None, "failures": failures,
    }


async def sync_interview_prep(db: AsyncSession) -> dict:
    """
    Upsert all rows from AI_ChatBot_TriggerData_InterviewPrep as JSONB blobs.
    Schema is unknown so entire row is stored raw.
    """
    rows, error = await fetch_interview_prep_from_mssql()
    if not rows:
        logger.warning("No InterviewPrep rows from SQL Server — %s", error or "unknown")
        return {"status": "connection_error", "rows_scanned": 0, "upserted": 0, "error": error}

    upserted = 0
    for raw in rows:
        user_id = raw.get("UserID")
        if user_id is None:
            continue
        serialized = _serialize_for_jsonb(raw)
        existing = await db.get(StudentInterviewPrep, user_id)
        if existing:
            existing.raw_data = serialized
        else:
            db.add(StudentInterviewPrep(user_id=user_id, raw_data=serialized))
        upserted += 1

    try:
        await db.commit()
    except Exception as exc:
        logger.error("InterviewPrep sync commit failed: %s", exc)
        await db.rollback()
        return {"status": "error", "rows_scanned": len(rows), "upserted": 0, "error": str(exc)}

    logger.info("InterviewPrep sync: upserted=%d", upserted)
    return {"status": "success", "rows_scanned": len(rows), "upserted": upserted, "error": None}
