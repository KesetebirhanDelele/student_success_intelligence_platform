"""SQL Server → PostgreSQL student sync service."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import fetch_students_from_mssql
from app.models import StudentTriggerData

logger = logging.getLogger(__name__)


async def sync_from_mssql(db: AsyncSession) -> dict:
    """
    Pull all rows from AI_ChatBot_TriggerData (SQL Server) and upsert
    into the local PostgreSQL mirror table.
    """
    students, error = await fetch_students_from_mssql()
    if not students:
        logger.warning("No students returned from SQL Server — %s", error or "unknown reason")
        return {"added": 0, "updated": 0, "connected": False, "error": error}

    added = updated = 0
    for row in students:
        existing = await db.get(StudentTriggerData, row.get("UserID"))
        if existing:
            for key, val in row.items():
                if hasattr(existing, key):
                    setattr(existing, key, val)
            updated += 1
        else:
            db.add(StudentTriggerData(**{k: v for k, v in row.items() if hasattr(StudentTriggerData, k)}))
            added += 1

    await db.commit()
    logger.info("MSSQL sync complete: added=%d updated=%d", added, updated)
    return {"added": added, "updated": updated, "connected": True}
