"""Student timeline router — unified chronological event stream."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
from app.services.timeline import build_timeline

router = APIRouter(prefix="/timeline")


@router.get("/{user_id}")
async def student_timeline(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Chronological (newest-first) unified timeline for one student.
    Merges: outreach attempts, state transitions, notes, AI insights, GHL messages.
    """
    events = await build_timeline(user_id, db)
    return APIResponse.ok({"user_id": user_id, "count": len(events), "events": events})
