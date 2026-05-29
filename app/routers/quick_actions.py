"""
Quick action log endpoints — operator button clicks, campaign activity queries.

All button actions are logged to PostgreSQL only.
No external communication occurs while EXECUTION_MODE=SHADOW.
Every log entry records the execution_mode so the audit trail is unambiguous.

Governance alignment:
  CID-1  — correlation_id extracted from X-Correlation-ID header or generated
  IML-1  — attribution propagated into response meta and log records
  RSV-1  — is_replay exposed in activity/log items
  AP-RT13 — PII excluded from governance meta
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import StudentCampaignActivity, StudentQuickActionLog
from app.routers._router_helpers import (
    build_governance_attribution_fields,
    build_request_attribution,
    extract_causation_id,
    extract_correlation_id,
    make_governance_meta,
    replay_visibility_fields,
)
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
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Log one operator button click. Creates a StudentQuickActionLog record and
    a companion StudentCampaignActivity row so the activity appears in tab columns.
    No outbound communication is triggered — SHADOW mode is enforced at this layer.

    Governance meta in response exposes correlation_id and suppression_codes
    so callers can confirm that live effects were not applied (CID-1, IML-1).
    """
    correlation_id = extract_correlation_id(dict(request.headers))
    causation_id = extract_causation_id(dict(request.headers))
    attribution = build_request_attribution(correlation_id, causation_id=causation_id)
    meta = make_governance_meta(attribution)

    record = StudentQuickActionLog(
        student_user_id=req.student_user_id,
        action_key=req.action_key,
        action_label=req.action_label,
        tab_name=req.tab_name,
        status="LOGGED",
        payload_json=req.payload_json,
        created_by=req.created_by,
        execution_mode=settings.EXECUTION_MODE,
        correlation_id=attribution.correlation_id,
        causation_id=attribution.causation_id,
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
        is_replay=attribution.is_replay,
    )
    db.add(record)

    activity = StudentCampaignActivity(
        student_user_id=req.student_user_id,
        activity_type=req.tab_name.upper(),
        activity_label=req.action_label,
        channel="OPERATOR",
        source="operator",
        created_by=req.created_by,
        execution_mode=settings.EXECUTION_MODE,
        shadow_only=settings.is_shadow,
        correlation_id=attribution.correlation_id,
        causation_id=attribution.causation_id,
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
        is_replay=attribution.is_replay,
    )
    db.add(activity)

    await db.commit()

    logger.info(
        "[QUICK_ACTION] logged student_user_id=%s action=%s tab=%s mode=%s correlation_id=%s",
        req.student_user_id, req.action_key, req.tab_name,
        settings.EXECUTION_MODE, correlation_id,
    )
    return APIResponse.ok(
        {
            "logged": True,
            "id": record.id,
            "shadow_mode": settings.is_shadow,
            "execution_mode": str(settings.EXECUTION_MODE),
            "note": (
                "Action logged. No external communication sent (SHADOW mode)."
                if settings.is_shadow
                else "Action logged."
            ),
        },
        meta=meta.as_dict(),
    )


@router.get("/campaign-activity/{user_id}")
async def get_campaign_activity(
    user_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Campaign activity history for one student, newest first.

    Each item exposes governance attribution and replay classification
    so consumers can distinguish LIVE from REPLAY records (RSV-1).
    """
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
                # Governance attribution lineage (IML-1, CID-1)
                **build_governance_attribution_fields(a),
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
    """
    Quick action log for one student, newest first.

    Each item exposes governance attribution and replay classification
    so consumers can distinguish LIVE from REPLAY records (RSV-1).
    """
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
                # Governance attribution lineage (IML-1, CID-1, RSV-1)
                **build_governance_attribution_fields(l),
            }
            for l in logs
        ],
    })
