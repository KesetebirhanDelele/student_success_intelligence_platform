"""Quick action log endpoints — operator button clicks, campaign activity queries.

All button actions are logged to PostgreSQL only.
No external communication occurs while EXECUTION_MODE=SHADOW.
Every log entry records the execution_mode so the audit trail is unambiguous.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import StudentCampaignActivity, StudentQuickActionLog
from app.schemas import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter()


class QuickActionRequest(BaseModel):
    student_user_id: int
    action_key: str
    action_label: str
    tab_name: str
    created_by: str = "operator"
    payload_json: dict | None = None


@router.post("/quick-actions/log")
async def log_quick_action(
    req: QuickActionRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Log one operator button click. Creates a StudentQuickActionLog record and
    a companion StudentCampaignActivity row so the activity appears in tab columns.
    No outbound communication is triggered — SHADOW mode is enforced at this layer.
    """
    record = StudentQuickActionLog(
        student_user_id=req.student_user_id,
        action_key=req.action_key,
        action_label=req.action_label,
        tab_name=req.tab_name,
        status="LOGGED",
        payload_json=req.payload_json,
        created_by=req.created_by,
        execution_mode=settings.EXECUTION_MODE,
    )
    db.add(record)

    # Also append to campaign activity so Last Campaign Activity columns populate
    activity = StudentCampaignActivity(
        student_user_id=req.student_user_id,
        activity_type=req.tab_name.upper(),
        activity_label=req.action_label,
        channel="OPERATOR",
        source="operator",
        created_by=req.created_by,
        execution_mode=settings.EXECUTION_MODE,
        shadow_only=settings.is_shadow,
    )
    db.add(activity)

    await db.commit()

    logger.info(
        "[QUICK_ACTION] logged student_user_id=%s action=%s tab=%s mode=%s",
        req.student_user_id, req.action_key, req.tab_name, settings.EXECUTION_MODE,
    )
    return APIResponse.ok({
        "logged": True,
        "id": record.id,
        "shadow_mode": settings.is_shadow,
        "execution_mode": settings.EXECUTION_MODE,
        "note": "Action logged. No external communication sent (SHADOW mode)." if settings.is_shadow else "Action logged.",
    })


@router.get("/campaign-activity/{user_id}")
async def get_campaign_activity(
    user_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Campaign activity history for one student, newest first."""
    result = await db.execute(
        select(StudentCampaignActivity)
        .where(StudentCampaignActivity.student_user_id == user_id)
        .order_by(StudentCampaignActivity.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    activities = result.scalars().all()
    return APIResponse.ok({
        "user_id": user_id,
        "count": len(activities),
        "activities": [
            {
                "id": a.id,
                "activity_date": a.activity_date.isoformat() if a.activity_date else None,
                "activity_type": a.activity_type,
                "activity_label": a.activity_label,
                "channel": a.channel,
                "source": a.source,
                "created_by": a.created_by,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "execution_mode": a.execution_mode,
                "shadow_only": a.shadow_only,
            }
            for a in activities
        ],
    })


@router.get("/quick-actions/{user_id}")
async def get_quick_action_log(
    user_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Quick action log for one student, newest first."""
    result = await db.execute(
        select(StudentQuickActionLog)
        .where(StudentQuickActionLog.student_user_id == user_id)
        .order_by(StudentQuickActionLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    logs = result.scalars().all()
    return APIResponse.ok({
        "user_id": user_id,
        "count": len(logs),
        "logs": [
            {
                "id": l.id,
                "action_key": l.action_key,
                "action_label": l.action_label,
                "tab_name": l.tab_name,
                "status": l.status,
                "created_by": l.created_by,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "execution_mode": l.execution_mode,
            }
            for l in logs
        ],
    })
