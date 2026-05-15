"""Segmentation endpoints — NEWCOMERS, HYPER_ACTIVE, CAP/LAUNCH/PLACEMENT HOPEFULS."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentTriggerData
from app.schemas import APIResponse
from app.services.segmentation import (
    ALL_SEGMENTS, SEGMENT_RULES, classify_student,
    filter_by_role, segment_summary,
)
from app.services.priority import score_student

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/segments")


def _student_dict(s: StudentTriggerData) -> dict:
    return {c.key: getattr(s, c.key) for c in s.__table__.columns}


def _enrich(s: StudentTriggerData) -> dict:
    d = _student_dict(s)
    p = score_student(d)
    d["priority_level"] = p.level
    d["priority_score"] = p.score
    d["recommended_action"] = p.recommended_action
    d["segments"] = classify_student(d)
    d["display_name"] = f"{s.FirstName or ''} {s.LastName or ''}".strip() or f"#{s.UserID}"
    # Serialize datetime
    if d.get("IPBCStartDate") and hasattr(d["IPBCStartDate"], "isoformat"):
        d["IPBCStartDate"] = d["IPBCStartDate"].isoformat()
    return d


@router.get("/summary")
async def segments_summary(
    role: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Counts per segment across all students, with optional role filter."""
    result = await db.execute(select(StudentTriggerData))
    all_students = [_student_dict(s) for s in result.scalars().all()]
    filtered = filter_by_role(all_students, role)
    counts = segment_summary(filtered)
    return APIResponse.ok({
        "role": role or "Support",
        "total_students": len(filtered),
        "segments": counts,
        "rules": SEGMENT_RULES,
    })


@router.get("/{segment_name}")
async def segment_detail(
    segment_name: str,
    role: str | None = Query(None),
    section: str | None = Query(None, description="Instructor section filter"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Students in a named segment, with role/section filtering."""
    seg_upper = segment_name.upper()
    if seg_upper not in ALL_SEGMENTS:
        return APIResponse.fail("INVALID_SEGMENT", f"Must be one of: {ALL_SEGMENTS}")

    result = await db.execute(select(StudentTriggerData))
    enriched = [_enrich(s) for s in result.scalars().all()]
    in_segment = [s for s in enriched if seg_upper in s.get("segments", [])]
    filtered = filter_by_role(in_segment, role, section)

    total = len(filtered)
    page = filtered[offset: offset + limit]
    return APIResponse.ok({
        "segment": seg_upper,
        "rule": SEGMENT_RULES.get(seg_upper),
        "role": role or "Support",
        "total": total,
        "rows": page,
    })
