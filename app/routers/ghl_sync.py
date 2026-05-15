"""GHL sync control endpoints — read-only, shadow-safe."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
from app.services.ghl_sync import get_sync_status, sync_all_students, sync_student_by_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ghl-sync")


class StudentSyncRequest(BaseModel):
    user_id: int


@router.get("/status")
async def ghl_sync_status(db: AsyncSession = Depends(get_db)) -> APIResponse:
    """GHL sync health: configured status, stored message count, last sync timestamp."""
    status = await get_sync_status(db)
    return APIResponse.ok(status)


@router.post("/student")
async def sync_student(
    req: StudentSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Pull GHL messages for one student by user_id.
    Phone is loaded automatically from the local PostgreSQL mirror.
    Read-only — safe in both SHADOW and LIVE modes.
    """
    logger.info("[GHL_SYNC_ROUTER] Student sync request user_id=%s", req.user_id)
    result = await sync_student_by_user_id(req.user_id, db)
    return APIResponse.ok(result)


@router.post("/batch")
async def sync_batch(
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
) -> APIResponse:
    """
    Batch-sync GHL messages for all students with a phone number (up to `limit`).
    Runs sequentially to respect GHL rate limits.
    Read-only — safe in both SHADOW and LIVE modes.
    """
    logger.info("[GHL_SYNC_ROUTER] Batch sync triggered limit=%d", limit)
    result = await sync_all_students(db, limit=limit)
    return APIResponse.ok(result)
