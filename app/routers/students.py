from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OutreachHistory, StateTransitionLog, StudentOutreachTracking, StudentTriggerData
from app.schemas import APIResponse

router = APIRouter()


def _risk_level(profile: StudentTriggerData | None) -> str:
    if profile is None:
        return "UNKNOWN"
    if profile.HWsBehind >= 3 or profile.AvgEffRating < 2.5 or profile.LastActivityDays > 7:
        return "HIGH"
    if profile.HWsBehind >= 2 or profile.AvgEffRating < 3.0 or profile.LastActivityDays >= 5:
        return "MEDIUM"
    return "LOW"


@router.get("/students/{user_id}")
async def get_student(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    tracking_row = await db.execute(
        select(StudentOutreachTracking).where(StudentOutreachTracking.user_id == user_id)
    )
    tracking_obj = tracking_row.scalar_one_or_none()
    if tracking_obj is None:
        return JSONResponse(
            status_code=404,
            content=APIResponse.fail(
                "NOT_FOUND",
                f"No outreach record found for student {user_id}. "
                "The student may not be tracked yet or the ID is incorrect.",
            ).model_dump(),
        )

    profile_row = await db.execute(
        select(StudentTriggerData).where(StudentTriggerData.UserID == user_id)
    )
    profile = profile_row.scalar_one_or_none()

    history_rows = await db.execute(
        select(OutreachHistory)
        .where(OutreachHistory.user_id == user_id)
        .order_by(OutreachHistory.created_at.asc())
    )
    history = history_rows.scalars().all()

    transition_rows = await db.execute(
        select(StateTransitionLog)
        .where(StateTransitionLog.user_id == user_id)
        .order_by(StateTransitionLog.created_at.asc())
    )
    transitions = transition_rows.scalars().all()

    return APIResponse.ok({
        "user_id": user_id,
        "checkpoint_type": tracking_obj.checkpoint_type,
        "state": tracking_obj.state,
        "current_attempt": tracking_obj.current_attempt,
        "last_contact_at": tracking_obj.last_contact_at,
        "next_retry_at": tracking_obj.next_retry_at,
        "profile": {
            "first_name": profile.FirstName if profile else None,
            "last_name": profile.LastName if profile else None,
            "email": profile.Email if profile else None,
            "phone": profile.PhoneNumber if profile else None,
            "path": profile.PathName if profile else None,
            "hws_behind": profile.HWsBehind if profile else None,
            "avg_eff_rating": profile.AvgEffRating if profile else None,
            "last_activity_days": profile.LastActivityDays if profile else None,
            "risk_level": _risk_level(profile),
        },
        "history": [
            {
                "id": h.id,
                "attempt_number": h.attempt_number,
                "channel": h.channel,
                "action": h.action,
                "execution_mode": h.execution_mode,
                "simulated_status": h.simulated_status,
                "decision": h.decision,
                "state_before": h.state_before,
                "state_after": h.state_after,
                "created_at": h.created_at,
            }
            for h in history
        ],
        "transitions": [
            {
                "id": t.id,
                "from_state": t.from_state,
                "to_state": t.to_state,
                "trigger": t.trigger,
                "actor": t.actor,
                "created_at": t.created_at,
            }
            for t in transitions
        ],
    })
