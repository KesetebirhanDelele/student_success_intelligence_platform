"""Batch preview (dry-run) and execution endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import StudentOutreachTracking, StudentTriggerData
from app.schemas import APIResponse
from app.services.decision_engine import decide
from app.services.eligibility import check_eligibility
from app.services.priority import score_student

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/batch")


class BatchRunRequest(BaseModel):
    checkpoint_type: str
    limit: int = 50


@router.get("/preview")
async def batch_preview(
    checkpoint_type: str = Query(..., description="PathName to preview"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Dry-run: compute what the next batch would do per student without
    executing any outreach. Safe to call at any time.
    """
    source_result = await db.execute(
        select(StudentTriggerData).where(StudentTriggerData.PathName == checkpoint_type)
    )
    students = source_result.scalars().all()

    decisions: dict[str, int] = {
        "TRIGGER_OUTREACH": 0,
        "RETRY_OUTREACH": 0,
        "ESCALATE": 0,
        "CLOSE": 0,
        "NO_ACTION": 0,
    }
    preview_rows = []
    processed = 0

    for student in students:
        if processed >= limit:
            break
        s = {c.key: getattr(student, c.key) for c in student.__table__.columns}

        tracking_row = await db.execute(
            select(StudentOutreachTracking).where(
                StudentOutreachTracking.user_id == s["UserID"],
                StudentOutreachTracking.checkpoint_type == checkpoint_type,
            )
        )
        tracking_obj = tracking_row.scalar_one_or_none()
        tracking = (
            {
                "state": tracking_obj.state,
                "current_attempt": tracking_obj.current_attempt,
                "next_retry_at": tracking_obj.next_retry_at,
            }
            if tracking_obj
            else None
        )

        eligibility = check_eligibility(s)
        decision = decide(s, tracking, eligibility)
        priority = score_student(s, tracking)

        decisions[decision] = decisions.get(decision, 0) + 1
        preview_rows.append({
            "user_id": s["UserID"],
            "name": f"{s.get('FirstName', '')} {s.get('LastName', '')}".strip() or f"#{s['UserID']}",
            "decision": decision,
            "priority_level": priority.level,
            "priority_score": priority.score,
            "recommended_action": priority.recommended_action,
            "reason_codes": priority.reason_codes,
            "eligible": eligibility.eligible,
            "skip_reason": eligibility.skip_reason or None,
            "current_state": tracking_obj.state if tracking_obj else None,
            "current_attempt": tracking_obj.current_attempt if tracking_obj else 0,
        })
        processed += 1

    preview_rows.sort(key=lambda r: r["priority_score"], reverse=True)

    return APIResponse.ok({
        "checkpoint_type": checkpoint_type,
        "execution_mode": settings.EXECUTION_MODE,
        "shadow": settings.is_shadow,
        "would_process": processed,
        "decisions": decisions,
        "rows": preview_rows,
    })


@router.post("/run")
async def batch_run(
    request: BatchRunRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Execute batch outreach (shadow-safe). Delegates to outreach service."""
    from app.services.outreach import run_outreach_batch

    result = await run_outreach_batch(db, request.checkpoint_type)
    return APIResponse.ok({
        **result,
        "execution_mode": settings.EXECUTION_MODE,
        "shadow": settings.is_shadow,
    })
