from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OutreachHistory, StudentOutreachTracking
from app.schemas import APIResponse

router = APIRouter()


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)) -> APIResponse:
    # State distribution
    state_result = await db.execute(
        select(StudentOutreachTracking.state, func.count().label("cnt"))
        .group_by(StudentOutreachTracking.state)
    )
    by_state: dict[str, int] = {row.state: row.cnt for row in state_result}
    total = sum(by_state.values())

    # History counts
    attempt_result = await db.execute(select(func.count()).select_from(OutreachHistory))
    total_attempts = attempt_result.scalar() or 0

    shadow_result = await db.execute(
        select(func.count())
        .select_from(OutreachHistory)
        .where(OutreachHistory.execution_mode == "SHADOW")
    )
    shadow_executions = shadow_result.scalar() or 0

    responded = (
        by_state.get("RESPONDED", 0)
        + by_state.get("ANALYZED", 0)
        + by_state.get("RESOLVED", 0)
    )
    meetings = by_state.get("RESOLVED", 0)

    return APIResponse.ok({
        "total_tracked": total,
        "by_state": by_state,
        "total_attempts": total_attempts,
        "shadow_executions": shadow_executions,
        "success_rate": round(responded / total, 4) if total else 0.0,
        "meeting_rate": round(meetings / total, 4) if total else 0.0,
    })
