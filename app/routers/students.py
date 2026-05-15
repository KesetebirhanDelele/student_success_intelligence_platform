from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    OutreachHistory, StateTransitionLog, StudentInterviewPrep,
    StudentOutreachTracking, StudentTriggerData,
)
from app.schemas import APIResponse
from app.services.segmentation import classify_student

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


@router.get("/students/{user_id}/interview-prep")
async def get_interview_prep(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Raw interview prep data for a student (JSONB blob from InterviewPrep sync)."""
    prep = await db.get(StudentInterviewPrep, user_id)
    if not prep:
        return APIResponse.ok({"user_id": user_id, "available": False, "data": None})
    return APIResponse.ok({
        "user_id": user_id,
        "available": True,
        "synced_at": prep.synced_at.isoformat() if prep.synced_at else None,
        "data": prep.raw_data,
    })


@router.get("/students/{user_id}/drawer")
async def get_student_drawer(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Combined payload for the right-drawer panel.
    Returns profile, payment, segments, interview prep, and outreach summary
    in one call to minimize frontend round trips.
    """
    profile_row = await db.get(StudentTriggerData, user_id)
    tracking_rows = await db.execute(
        select(StudentOutreachTracking).where(StudentOutreachTracking.user_id == user_id)
    )
    tracking_list = tracking_rows.scalars().all()

    prep = await db.get(StudentInterviewPrep, user_id)

    profile = None
    payment = None
    segments: list[str] = []

    if profile_row:
        d = {c.key: getattr(profile_row, c.key) for c in profile_row.__table__.columns}
        if d.get("IPBCStartDate") and hasattr(d["IPBCStartDate"], "isoformat"):
            d["IPBCStartDate"] = d["IPBCStartDate"].isoformat()

        # Compute bundle-aware balance
        total_payments = float(d.get("Total_Payments") or 0)
        total_credits = float(d.get("Total_Credits") or 0)
        class_value = float(d.get("ClassValue") or 0)
        stored_balance = float(d.get("PaymentBalance") or 0)
        is_bundle = total_credits > 0 and stored_balance == 0 and class_value > 0
        actual_balance = max(0.0, class_value - total_payments - total_credits) if is_bundle else stored_balance

        segments = classify_student(d)

        profile = {
            "user_id": profile_row.UserID,
            "display_name": f"{profile_row.FirstName or ''} {profile_row.LastName or ''}".strip() or f"#{user_id}",
            "email": profile_row.Email,
            "phone": profile_row.PhoneNumber,
            "path": profile_row.PathName,
            "current_section": profile_row.CurrentSection,
            "hws_behind": profile_row.HWsBehind,
            "avg_eff_rating": profile_row.AvgEffRating,
            "last_activity_days": profile_row.LastActivityDays,
            "attendance_pct": profile_row.AttendancePercentage,
            "past_10_days_logon": profile_row.Past10DaysLogon,
            "ipbc_start_date": d.get("IPBCStartDate"),
            "risk_level": _risk_level(profile_row),
            "segments": segments,
        }

        payment = {
            "class_value": class_value,
            "total_payments": total_payments,
            "total_credits": total_credits,
            "payment_balance_stored": stored_balance,
            "actual_balance": round(actual_balance, 2),
            "is_bundle_deal": is_bundle,
            "fee_paid": profile_row.FeePaid,
            "class_fees_paid": profile_row.ClassFeesPaid,
            "payment_risk": "HIGH" if actual_balance > 1000 else ("MEDIUM" if actual_balance > 0 else "CLEAR"),
        }

    return APIResponse.ok({
        "user_id": user_id,
        "profile": profile,
        "payment": payment,
        "segments": segments,
        "outreach": [
            {
                "checkpoint_type": t.checkpoint_type,
                "state": t.state,
                "current_attempt": t.current_attempt,
                "last_contact_at": t.last_contact_at.isoformat() if t.last_contact_at else None,
                "next_retry_at": t.next_retry_at.isoformat() if t.next_retry_at else None,
            }
            for t in tracking_list
        ],
        "interview_prep": {
            "available": prep is not None,
            "synced_at": prep.synced_at.isoformat() if prep and prep.synced_at else None,
            "data": prep.raw_data if prep else None,
        },
    })
