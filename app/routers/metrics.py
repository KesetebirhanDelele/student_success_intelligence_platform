from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import StudentOutreachTracking
from app.schemas import APIResponse, MetricsData

router = APIRouter()


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)) -> APIResponse:
    total = db.query(func.count(StudentOutreachTracking.OutreachID)).scalar() or 0

    def count_state(state: str) -> int:
        return db.query(func.count(StudentOutreachTracking.OutreachID)).filter_by(State=state).scalar() or 0

    contacted = count_state("CONTACTED")
    responded = count_state("RESPONDED")
    no_response = count_state("NO_RESPONSE")
    meeting_booked = db.query(func.count(StudentOutreachTracking.OutreachID)).filter_by(MeetingBooked=True).scalar() or 0
    closed = count_state("CLOSED")

    success_rate = round(responded / total, 4) if total > 0 else 0.0
    meeting_rate = round(meeting_booked / total, 4) if total > 0 else 0.0

    data = MetricsData(
        total_outreach=total,
        contacted=contacted,
        responded=responded,
        no_response=no_response,
        meeting_booked=meeting_booked,
        closed=closed,
        success_rate=success_rate,
        meeting_rate=meeting_rate,
    )
    return APIResponse.ok(data.model_dump())
