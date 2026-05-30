from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
from app.services.payment_sync import sync_payments, sync_placement_interviews
from app.services.sync import (
    sync_campaign_activity, sync_from_mssql, sync_interview_prep,
    sync_ipbc_students, sync_mentorship_assignments,
)

router = APIRouter()


@router.post("/sync/mssql")
async def manual_mssql_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    result = await sync_from_mssql(db)
    return APIResponse.ok(result)


@router.post("/sync/interview-prep")
async def manual_interview_prep_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Sync AI_ChatBot_TriggerData_InterviewPrep into local JSONB store."""
    result = await sync_interview_prep(db)
    return APIResponse.ok(result)


@router.post("/sync/payments")
async def manual_payment_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Sync payment totals from CB_PS_TXN_LOG + VW_PAYPAL_DISTINCT_TRANSACTIONS
    into ai_chatbot_triggerdata. Updates Total_Payments, ClassValue,
    ClassFeesPaid, PaymentBalance per student. SHADOW-safe.
    """
    result = await sync_payments(db)
    return APIResponse.ok(result)


@router.post("/sync/ipbc-students")
async def manual_ipbc_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Sync AI_Chatbot_TriggerData_IPBC → ai_chatbot_triggerdata + mentorship_assignments.
    IPBC students are a separate population from AI_ChatBot_TriggerData (JRP students).
    Must be run before mentor/supermentor tabs will show data for IPBC students.
    """
    result = await sync_ipbc_students(db)
    return APIResponse.ok(result)


@router.post("/sync/mentorship-assignments")
async def manual_mentorship_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Sync ADF_Mentorship_Activity from SQL Server → mentorship_assignments (PostgreSQL)."""
    result = await sync_mentorship_assignments(db)
    return APIResponse.ok(result)


@router.post("/sync/campaign-activity")
async def manual_campaign_activity_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Gap 1 import: RETOOLCALLENGAGEMENT + RetoolEmailEngagement + RetoolNoteEngagement → student_campaign_activity."""
    result = await sync_campaign_activity(db)
    return APIResponse.ok(result)


@router.post("/sync/placement-interviews")
async def manual_placement_interview_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Sync vw_ColaberryInterviews_PlacementHopefuls from SQL Server into
    student_interview_prep (raw_data JSONB). Used by Placement Hopefuls UX tab.
    """
    result = await sync_placement_interviews(db)
    return APIResponse.ok(result)
