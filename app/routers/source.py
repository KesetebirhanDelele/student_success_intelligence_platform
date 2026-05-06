"""Source analysis endpoints — PathName discovery and source vs tracking comparison."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentOutreachTracking, StudentTriggerData
from app.schemas import APIResponse
from app.services.priority import score_student

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/source")


@router.get("/paths")
async def source_paths(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Distinct PathName values present in the local source mirror."""
    result = await db.execute(
        select(StudentTriggerData.PathName)
        .where(StudentTriggerData.PathName.isnot(None))
        .distinct()
        .order_by(StudentTriggerData.PathName)
    )
    paths = [row[0] for row in result.fetchall() if row[0]]
    return APIResponse.ok({"paths": paths, "count": len(paths)})


@router.get("/summary")
async def source_summary(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Per-PathName breakdown: total source rows, tracked vs untracked,
    risk distribution (URGENT/HIGH/MEDIUM/LOW) via priority scoring.
    """
    source_result = await db.execute(select(StudentTriggerData))
    all_students = source_result.scalars().all()

    tracked_result = await db.execute(
        select(StudentOutreachTracking.user_id).distinct()
    )
    tracked_ids = {row[0] for row in tracked_result.fetchall()}

    by_path: dict[str, dict] = {}

    for student in all_students:
        path = student.PathName or "UNKNOWN"
        if path not in by_path:
            by_path[path] = {
                "path": path,
                "total": 0,
                "tracked": 0,
                "untracked": 0,
                "risk": {"URGENT": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
            }
        entry = by_path[path]
        entry["total"] += 1

        student_dict = {c.key: getattr(student, c.key) for c in student.__table__.columns}
        if student.UserID in tracked_ids:
            entry["tracked"] += 1
        else:
            entry["untracked"] += 1

        priority = score_student(student_dict)
        entry["risk"][priority.level] += 1

    paths = sorted(by_path.values(), key=lambda x: x["total"], reverse=True)
    total_source = sum(p["total"] for p in paths)
    total_tracked = sum(p["tracked"] for p in paths)

    return APIResponse.ok({
        "total_source": total_source,
        "total_tracked": total_tracked,
        "total_untracked": total_source - total_tracked,
        "by_path": paths,
    })
