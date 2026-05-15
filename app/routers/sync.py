from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
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
