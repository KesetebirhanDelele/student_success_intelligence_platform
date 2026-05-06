import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse, TriggerOutreachRequest
from app.services.outreach import run_outreach_batch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/outreach/trigger")
async def trigger_outreach(
    body: TriggerOutreachRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    summary = await run_outreach_batch(db, body.checkpoint_type)
    return APIResponse.ok({"summary": summary})
