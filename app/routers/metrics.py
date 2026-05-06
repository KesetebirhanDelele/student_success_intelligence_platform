from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OutreachHistory, StudentOutreachTracking
from app.schemas import APIResponse

router = APIRouter()


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)) -> APIResponse:
    state_result = await db.execute(
        select(StudentOutreachTracking.state, func.count().label("cnt"))
        .group_by(StudentOutreachTracking.state)
    )
    by_state: dict[str, int] = {row.state: row.cnt for row in state_result}
    total = sum(by_state.values())

    contacted_result = await db.execute(
        select(func.count())
        .select_from(StudentOutreachTracking)
        .where(StudentOutreachTracking.current_attempt > 0)
    )
    ever_contacted = contacted_result.scalar() or 0

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
    intervention = by_state.get("INTERVENTION_REQUIRED", 0)
    resolved = by_state.get("RESOLVED", 0)

    return APIResponse.ok({
        "total_tracked": total,
        "by_state": by_state,
        "total_attempts": total_attempts,
        "shadow_executions": shadow_executions,
        "success_rate": round(responded / total, 4) if total else 0.0,
        "meeting_rate": round(resolved / total, 4) if total else 0.0,
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
