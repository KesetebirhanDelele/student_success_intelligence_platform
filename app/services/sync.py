"""SQL Server → PostgreSQL student sync service."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import fetch_students_from_mssql
from app.models import StudentTriggerData

logger = logging.getLogger(__name__)

# Fields that must be non-NULL for a row to be accepted into PostgreSQL.
# These map to Mapped[int] / Mapped[float] (NOT NULL) columns in the model.
_REQUIRED_FIELDS: tuple[str, ...] = ("UserID", "HWsBehind", "AvgEffRating")


def _validate_row(row: dict[str, Any]) -> list[str]:
    """Return a list of field names that are missing (None) in this row."""
    return [f for f in _REQUIRED_FIELDS if row.get(f) is None]


async def sync_from_mssql(db: AsyncSession) -> dict:
    """
    Pull all rows from AI_ChatBot_TriggerData (SQL Server) and upsert into the
    local PostgreSQL mirror table.

    Invalid rows (NULL in any NOT NULL column) are skipped and quarantined in
    the returned `failures` list.  Valid rows always persist regardless of how
    many invalid rows are present — one bad record never blocks the rest.

    Return shape:
        {
            "status":          "success" | "partial_success" | "connection_error",
            "rows_scanned":    int,
            "rows_successful": int,
            "rows_failed":     int,
            "added":           int,
            "updated":         int,
            "connected":       bool,
            "error":           str | None,
            "failures": [
                {"user_id": int | None, "reason": str},
                ...
            ]
        }
    """
    students, error = await fetch_students_from_mssql()
    if not students:
        logger.warning("No students returned from SQL Server — %s", error or "unknown reason")
        return {
            "status": "connection_error",
            "rows_scanned": 0,
            "rows_successful": 0,
            "rows_failed": 0,
            "added": 0,
            "updated": 0,
            "connected": False,
            "error": error,
            "failures": [],
        }

    added = updated = 0
    failures: list[dict] = []

    for row in students:
        missing = _validate_row(row)
        if missing:
            user_id = row.get("UserID")
            reason = f"Missing required fields: {', '.join(missing)}"
            failures.append({"user_id": user_id, "reason": reason})
            logger.warning("Skipping UserID=%s during sync — %s", user_id, reason)
            continue

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
            "rows_scanned": len(students),
            "rows_successful": 0,
            "rows_failed": len(students),
            "added": 0,
            "updated": 0,
            "connected": True,
            "error": str(exc),
            "failures": [{"user_id": None, "reason": f"Database commit failed: {exc}"}],
        }

    rows_scanned = len(students)
    rows_successful = added + updated
    rows_failed = len(failures)
    status = "partial_success" if failures else "success"

    logger.info(
        "MSSQL sync complete: status=%s scanned=%d added=%d updated=%d failed=%d",
        status, rows_scanned, added, updated, rows_failed,
    )

    return {
        "status": status,
        "rows_scanned": rows_scanned,
        "rows_successful": rows_successful,
        "rows_failed": rows_failed,
        "added": added,
        "updated": updated,
        "connected": True,
        "error": None,
        "failures": failures,
    }
