"""AI insight endpoints — on-demand generation + cached retrieval."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIInsight, StudentTriggerData
from app.schemas import APIResponse
from app.services.ai_insights import INSIGHT_TYPES, get_or_generate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-insights")


@router.get("/{user_id}/{insight_type}")
async def get_insight(
    user_id: int,
    insight_type: str,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Return a cached insight if one exists and is not expired (24 h TTL).
    Otherwise generate a new one via the configured LLM and cache it.
    Insight types: OUTREACH_DRAFT | INTERVENTION | RISK_EXPLANATION | INTERVIEW_COACHING
    """
    insight_type = insight_type.upper()
    if insight_type not in INSIGHT_TYPES:
        return APIResponse.fail(
            "INVALID_TYPE", f"Must be one of: {sorted(INSIGHT_TYPES)}"
        )

    student_row = await db.get(StudentTriggerData, user_id)
    student = (
        {c.key: getattr(student_row, c.key) for c in student_row.__table__.columns}
        if student_row else {"UserID": user_id}
    )

    result = await get_or_generate(user_id, insight_type, student, db)
    return APIResponse.ok(result)


@router.get("/{user_id}")
async def all_insights(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Return all stored insights for a student (no generation)."""
    result = await db.execute(
        select(AIInsight)
        .where(AIInsight.user_id == user_id)
        .order_by(AIInsight.created_at.desc())
    )
    items = result.scalars().all()
    return APIResponse.ok({
        "user_id": user_id,
        "count": len(items),
        "insights": [
            {
                "id": i.id,
                "insight_type": i.insight_type,
                "content": i.content_text,
                "model": i.model_used,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "expires_at": i.expires_at.isoformat() if i.expires_at else None,
            }
            for i in items
        ],
    })
