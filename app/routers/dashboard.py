"""Dashboard aggregation endpoints — health, alerts, channel performance, summary, activity."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import OutreachHistory, StudentOutreachTracking
from app.schemas import APIResponse
from app.services.alerts import gather_alerts
from app.services.scheduler import get_last_run_at, get_scheduler_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard")


async def _db_connected() -> bool:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
async def dashboard_health() -> APIResponse:
    db_ok = await _db_connected()
    last_run = get_last_run_at()
    return APIResponse.ok({
        "execution_mode": settings.EXECUTION_MODE,
        "outbound_enabled": not settings.is_shadow,
        "db": {"connected": db_ok},
        "scheduler": {
            "status": get_scheduler_status(),
            "last_run": last_run,
        },
        "mssql": {
            "configured": settings.mssql_configured,
            "host": settings.MSSQL_HOST or None,
        },
        "channels": {
            "call": not settings.is_shadow and bool(settings.SYNTHFLOW_API_KEY),
            "sms": not settings.is_shadow and bool(settings.GHL_API_KEY),
            "email": not settings.is_shadow and bool(settings.GHL_API_KEY),
        },
    })


@router.get("/alerts")
async def dashboard_alerts(db: AsyncSession = Depends(get_db)) -> APIResponse:
    alerts = await gather_alerts(
        db,
        is_shadow=settings.is_shadow,
        mssql_configured=settings.mssql_configured,
        last_run=get_last_run_at(),
    )
    return APIResponse.ok({"alerts": alerts, "count": len(alerts)})


@router.get("/channel-performance")
async def channel_performance(db: AsyncSession = Depends(get_db)) -> APIResponse:
    rows = await db.execute(
        select(
            OutreachHistory.channel,
            func.count().label("attempts"),
            func.count(
                case((OutreachHistory.execution_mode == "SHADOW", 1), else_=None)
            ).label("shadow_count"),
            func.count(
                case(
                    (OutreachHistory.state_after.in_(["RESPONDED", "ANALYZED", "RESOLVED"]), 1),
                    else_=None,
                )
            ).label("responses"),
            func.count(
                case((OutreachHistory.state_after == "NO_RESPONSE", 1), else_=None)
            ).label("no_response_count"),
        )
        .where(OutreachHistory.channel.isnot(None))
        .group_by(OutreachHistory.channel)
    )

    channels = []
    for row in rows.fetchall():
        attempts = row.attempts or 0
        responses = row.responses or 0
        channels.append({
            "channel": row.channel,
            "attempts": attempts,
            "shadow_count": row.shadow_count or 0,
            "responses": responses,
            "no_response": row.no_response_count or 0,
            "success_rate": round(responses / attempts, 4) if attempts else 0.0,
            "simulated": settings.is_shadow,
        })

    return APIResponse.ok({
        "channels": channels,
        "shadow_mode": settings.is_shadow,
        "note": "All channels are simulated — no real communication sent." if settings.is_shadow else None,
    })


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)) -> APIResponse:
    state_result = await db.execute(
        select(StudentOutreachTracking.state, func.count().label("cnt"))
        .group_by(StudentOutreachTracking.state)
    )
    by_state: dict[str, int] = {row.state: row.cnt for row in state_result}
    total = sum(by_state.values())

    contacted_q = await db.execute(
        select(func.count())
        .select_from(StudentOutreachTracking)
        .where(StudentOutreachTracking.current_attempt > 0)
    )
    ever_contacted = contacted_q.scalar() or 0

    attempt_q = await db.execute(select(func.count()).select_from(OutreachHistory))
    total_attempts = attempt_q.scalar() or 0

    shadow_q = await db.execute(
        select(func.count())
        .select_from(OutreachHistory)
        .where(OutreachHistory.execution_mode == "SHADOW")
    )
    shadow_executions = shadow_q.scalar() or 0

    responded = (
        by_state.get("RESPONDED", 0)
        + by_state.get("ANALYZED", 0)
        + by_state.get("RESOLVED", 0)
    )
    intervention = by_state.get("INTERVENTION_REQUIRED", 0)
    resolved = by_state.get("RESOLVED", 0)

    return APIResponse.ok({
        "execution_mode": settings.EXECUTION_MODE,
        "total_tracked": total,
        "by_state": by_state,
        "total_attempts": total_attempts,
        "shadow_executions": shadow_executions,
        "funnel": {
            "tracked": total,
            "contacted": ever_contacted,
            "responded": responded,
            "no_response": by_state.get("NO_RESPONSE", 0),
            "intervention_required": intervention,
            "resolved": resolved,
            "closed": by_state.get("CLOSED", 0),
            "shadow_executions": shadow_executions,
        },
        "conversion": {
            "contacted_rate": round(ever_contacted / total, 4) if total else 0.0,
            "response_rate": round(responded / ever_contacted, 4) if ever_contacted else 0.0,
            "resolution_rate": round(
                resolved / (intervention + resolved), 4
            ) if (intervention + resolved) else 0.0,
        },
    })


@router.get("/kpi-extended")
async def kpi_extended(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Extended KPI aggregates from the expanded StudentTriggerData mirror.
    Includes attendance, engagement, payment, and segment-level metrics.
    """
    from sqlalchemy import func as sqlfunc
    from app.models import StudentTriggerData
    from app.services.segmentation import segment_summary

    src_result = await db.execute(select(StudentTriggerData))
    all_students = src_result.scalars().all()
    total = len(all_students)

    if not total:
        return APIResponse.ok({
            "total_students": 0,
            "note": "No students synced yet. Run SQL Server sync first.",
        })

    # Compute field-level aggregates
    attendance_vals = [float(s.AttendancePercentage or 0) for s in all_students]
    eff_vals = [float(s.AvgEffRating or 0) for s in all_students]
    hw_vals = [int(s.HWsBehind or 0) for s in all_students]
    login_vals = [int(s.Past10DaysLogon or 0) for s in all_students]
    balance_vals = [float(s.PaymentBalance or 0) for s in all_students]

    avg_attendance = round(sum(attendance_vals) / total, 1)
    avg_efficiency = round(sum(eff_vals) / total, 1)
    avg_hw_behind = round(sum(hw_vals) / total, 2)
    total_payment_risk = sum(1 for b in balance_vals if b > 0)

    students_dicts = [
        {c.key: getattr(s, c.key) for c in s.__table__.columns}
        for s in all_students
    ]
    seg_counts = segment_summary(students_dicts)

    section_dist: dict[str, int] = {}
    for s in all_students:
        sec = s.CurrentSection or s.PathName or "Unknown"
        section_dist[sec] = section_dist.get(sec, 0) + 1

    return APIResponse.ok({
        "total_students": total,
        "averages": {
            "attendance_pct": avg_attendance,
            "efficiency_rating": avg_efficiency,
            "hws_behind": avg_hw_behind,
        },
        "engagement": {
            "high_engagement": sum(1 for v in login_vals if v >= 7),
            "low_engagement": sum(1 for v in login_vals if v < 3),
            "hyper_active_count": seg_counts.get("HYPER_ACTIVE", 0),
        },
        "payment": {
            "students_with_balance": total_payment_risk,
            "fully_paid": sum(1 for b in balance_vals if b == 0),
        },
        "segments": seg_counts,
        "sections": section_dist,
        "execution_mode": settings.EXECUTION_MODE,
    })


@router.get("/recent-activity")
async def recent_activity(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    rows = await db.execute(
        select(OutreachHistory)
        .order_by(OutreachHistory.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    items = rows.scalars().all()
    return APIResponse.ok({
        "items": [
            {
                "id": h.id,
                "user_id": h.user_id,
                "checkpoint_type": h.checkpoint_type,
                "attempt_number": h.attempt_number,
                "channel": h.channel,
                "action": h.action,
                "execution_mode": h.execution_mode,
                "simulated_status": h.simulated_status,
                "state_before": h.state_before,
                "state_after": h.state_after,
                "decision": h.decision,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in items
        ]
    })
