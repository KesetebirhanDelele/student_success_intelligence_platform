from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OutreachHistory, StudentOutreachTracking
from app.schemas import APIResponse

router = APIRouter()


@router.get("/students/{user_id}")
async def get_student(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    tracking_row = await db.execute(
        select(StudentOutreachTracking).where(StudentOutreachTracking.user_id == user_id)
    )
    tracking_obj = tracking_row.scalar_one_or_none()
    if tracking_obj is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"No outreach record for student {user_id}"},
        )

    history_rows = await db.execute(
        select(OutreachHistory)
        .where(OutreachHistory.user_id == user_id)
        .order_by(OutreachHistory.created_at.asc())
    )
    history = history_rows.scalars().all()

    return APIResponse.ok({
        "user_id": user_id,
        "checkpoint_type": tracking_obj.checkpoint_type,
        "state": tracking_obj.state,
        "current_attempt": tracking_obj.current_attempt,
        "last_contact_at": tracking_obj.last_contact_at,
        "next_retry_at": tracking_obj.next_retry_at,
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
    })
