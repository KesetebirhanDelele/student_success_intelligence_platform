"""Work queue endpoints — 7 named queues with priority scoring."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentOutreachTracking, StudentTriggerData
from app.schemas import APIResponse
from app.services.priority import score_student

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/work-queue")

VALID_QUEUES = frozenset({
    "all_source", "untracked", "eligible",
    "contacted", "intervention", "retry_due", "resolved_closed",
})


@router.get("/summary")
async def work_queue_summary(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Counts for each of the 7 work queues."""
    now = datetime.now(tz=timezone.utc)

    source_q = await db.execute(select(func.count()).select_from(StudentTriggerData))
    total_source = source_q.scalar() or 0

    tracked_result = await db.execute(select(StudentOutreachTracking.user_id).distinct())
    tracked_ids = {row[0] for row in tracked_result.fetchall()}

    state_result = await db.execute(
        select(StudentOutreachTracking.state, func.count().label("cnt"))
        .group_by(StudentOutreachTracking.state)
    )
    by_state: dict[str, int] = {row.state: row.cnt for row in state_result}

    retry_result = await db.execute(
        select(func.count())
        .select_from(StudentOutreachTracking)
        .where(
            StudentOutreachTracking.state == "NO_RESPONSE",
            StudentOutreachTracking.next_retry_at < now,
        )
    )
    retry_due = retry_result.scalar() or 0

    return APIResponse.ok({
        "queues": {
            "all_source": total_source,
            "untracked": total_source - len(tracked_ids),
            "eligible": (
                by_state.get("ELIGIBLE", 0)
                + by_state.get("QUEUED", 0)
                + by_state.get("RETRY", 0)
            ),
            "contacted": by_state.get("CONTACTED", 0),
            "intervention": by_state.get("INTERVENTION_REQUIRED", 0),
            "retry_due": retry_due,
            "resolved_closed": by_state.get("RESOLVED", 0) + by_state.get("CLOSED", 0),
        }
    })


@router.get("/{queue_name}")
async def work_queue_detail(
    queue_name: str,
    path: str | None = Query(None, description="Filter by PathName"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Paginated, priority-sorted student list for a named queue."""
    if queue_name not in VALID_QUEUES:
        return APIResponse.fail(
            "INVALID_QUEUE",
            f"queue_name must be one of: {sorted(VALID_QUEUES)}",
        )

    now = datetime.now(tz=timezone.utc)

    if queue_name in ("all_source", "untracked"):
        return await _source_queue(db, queue_name, path, limit, offset)
    return await _tracking_queue(db, queue_name, path, limit, offset, now)


async def _source_queue(
    db: AsyncSession,
    queue_name: str,
    path_filter: str | None,
    limit: int,
    offset: int,
) -> APIResponse:
    q = select(StudentTriggerData)
    if path_filter:
        q = q.where(StudentTriggerData.PathName == path_filter)

    result = await db.execute(q)
    all_students = result.scalars().all()

    if queue_name == "untracked":
        tracked_result = await db.execute(select(StudentOutreachTracking.user_id).distinct())
        tracked_ids = {row[0] for row in tracked_result.fetchall()}
        students = [s for s in all_students if s.UserID not in tracked_ids]
    else:
        students = list(all_students)

    rows = []
    for s in students:
        d = {c.key: getattr(s, c.key) for c in s.__table__.columns}
        p = score_student(d)
        rows.append({
            "user_id": s.UserID,
            "name": f"{s.FirstName or ''} {s.LastName or ''}".strip() or f"#{s.UserID}",
            "path": s.PathName,
            "hws_behind": s.HWsBehind,
            "eff_rating": s.AvgEffRating,
            "inactivity_days": s.LastActivityDays,
            "priority_score": p.score,
            "priority_level": p.level,
            "recommended_action": p.recommended_action,
            "reason_codes": p.reason_codes,
            "state": None,
            "attempts": 0,
            "last_contact_at": None,
            "next_retry_at": None,
            "checkpoint_type": s.PathName,
        })

    rows.sort(key=lambda r: r["priority_score"], reverse=True)
    total = len(rows)
    return APIResponse.ok({
        "queue": queue_name,
        "total": total,
        "rows": rows[offset: offset + limit],
    })


async def _tracking_queue(
    db: AsyncSession,
    queue_name: str,
    path_filter: str | None,
    limit: int,
    offset: int,
    now: datetime,
) -> APIResponse:
    q = select(StudentOutreachTracking)

    if queue_name == "eligible":
        q = q.where(StudentOutreachTracking.state.in_(["ELIGIBLE", "QUEUED", "RETRY"]))
    elif queue_name == "contacted":
        q = q.where(StudentOutreachTracking.state == "CONTACTED")
    elif queue_name == "intervention":
        q = q.where(StudentOutreachTracking.state == "INTERVENTION_REQUIRED")
    elif queue_name == "retry_due":
        q = q.where(
            StudentOutreachTracking.state == "NO_RESPONSE",
            StudentOutreachTracking.next_retry_at < now,
        )
    elif queue_name == "resolved_closed":
        q = q.where(StudentOutreachTracking.state.in_(["RESOLVED", "CLOSED"]))

    tracking_result = await db.execute(q)
    tracking_rows = tracking_result.scalars().all()

    user_ids = [t.user_id for t in tracking_rows]
    if not user_ids:
        return APIResponse.ok({"queue": queue_name, "total": 0, "rows": []})

    source_result = await db.execute(
        select(StudentTriggerData).where(StudentTriggerData.UserID.in_(user_ids))
    )
    source_map = {s.UserID: s for s in source_result.scalars().all()}

    rows = []
    for t in tracking_rows:
        source = source_map.get(t.user_id)
        if path_filter and (not source or source.PathName != path_filter):
            continue

        d = {c.key: getattr(source, c.key) for c in source.__table__.columns} if source else {}
        p = score_student(d, {"state": t.state, "current_attempt": t.current_attempt})

        rows.append({
            "user_id": t.user_id,
            "name": (
                f"{source.FirstName or ''} {source.LastName or ''}".strip()
                if source else f"#{t.user_id}"
            ),
            "path": source.PathName if source else t.checkpoint_type,
            "hws_behind": source.HWsBehind if source else None,
            "eff_rating": source.AvgEffRating if source else None,
            "inactivity_days": source.LastActivityDays if source else None,
            "priority_score": p.score,
            "priority_level": p.level,
            "recommended_action": p.recommended_action,
            "reason_codes": p.reason_codes,
            "state": t.state,
            "attempts": t.current_attempt,
            "last_contact_at": t.last_contact_at.isoformat() if t.last_contact_at else None,
            "next_retry_at": t.next_retry_at.isoformat() if t.next_retry_at else None,
            "checkpoint_type": t.checkpoint_type,
        })

    rows.sort(key=lambda r: r["priority_score"], reverse=True)
    total = len(rows)
    return APIResponse.ok({
        "queue": queue_name,
        "total": total,
        "rows": rows[offset: offset + limit],
    })
