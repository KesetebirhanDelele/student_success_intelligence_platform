from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StudentOutreachTracking
from app.schemas import APIResponse, OutreachHistoryItem, StudentDetailData

router = APIRouter()


@router.get("/students/{user_id}")
def get_student(user_id: int, db: Session = Depends(get_db)) -> APIResponse:
    records = (
        db.query(StudentOutreachTracking)
        .filter_by(UserID=user_id)
        .order_by(StudentOutreachTracking.ContactAttempt.asc())
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"No outreach records for student {user_id}"},
        )

    latest = records[-1]
    history = [
        OutreachHistoryItem(
            outreach_id=r.OutreachID,
            checkpoint_type=r.CheckpointType,
            state=r.State,
            contact_date=r.ContactDate,
            contact_attempt=r.ContactAttempt,
            call_connected=r.CallConnected or False,
            meeting_booked=r.MeetingBooked or False,
            created_at=r.CreatedAt,
            updated_at=r.UpdatedAt,
        )
        for r in records
    ]

    data = StudentDetailData(
        user_id=user_id,
        state=latest.State,
        attempt_count=latest.ContactAttempt,
        history=history,
    )
    return APIResponse.ok(data.model_dump())
