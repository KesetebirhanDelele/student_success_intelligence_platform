from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
from app.services.payment_sync import sync_payments, sync_placement_interviews
from app.services.sync import sync_from_mssql, sync_interview_prep

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


@router.post("/sync/placement-interviews")
async def manual_placement_interview_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """
    Sync vw_ColaberryInterviews_PlacementHopefuls from SQL Server into
    student_interview_prep (raw_data JSONB). Used by Placement Hopefuls UX tab.
    """
    result = await sync_placement_interviews(db)
    return APIResponse.ok(result)
