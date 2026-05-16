"""Lifecycle tab endpoints — one per student cohort tab.

Each endpoint returns the exact column payload its frontend tab needs.
Filters are applied in PostgreSQL; derived fields (weeks, days, name) are
computed in Python. Campaign activity and latest note are merged via
secondary queries to avoid complex subquery joins.

AttendancePercentage is stored as a raw percentage (0–100 scale).
All six endpoints are read-only and safe in SHADOW mode.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    StudentCampaignActivity, StudentNote, StudentTriggerData,
)
from app.schemas import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lifecycle")


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _raw(s: StudentTriggerData) -> dict:
    """Convert ORM row to plain dict."""
    return {c.key: getattr(s, c.key) for c in s.__table__.columns}


def _name(d: dict) -> str:
    return f"{d.get('FirstName') or ''} {d.get('LastName') or ''}".strip() or f"#{d.get('UserID')}"


def _isostr(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _weeks_in_program(ipbc_start: Any) -> int | None:
    if not ipbc_start:
        return None
    now = datetime.now(tz=timezone.utc)
    if isinstance(ipbc_start, str):
        try:
            ipbc_start = datetime.fromisoformat(ipbc_start.replace("Z", "+00:00"))
        except Exception:
            return None
    if ipbc_start.tzinfo is None:
        ipbc_start = ipbc_start.replace(tzinfo=timezone.utc)
    days = (now - ipbc_start).days
    return max(0, days // 7)


def _hw_submitted_days(last_submitted: Any, fallback_days: int | None) -> int | None:
    """Parse LastSubmitted (ISO string or datetime) → days ago; fall back to LastActivityDays."""
    if not last_submitted:
        return fallback_days
    now = datetime.now(tz=timezone.utc)
    try:
        s = str(last_submitted).strip()
        # Handle "YYYY-MM-DD HH:MM:SS.ffffff" or ISO variants
        s = s.split(".")[0].replace(" ", "T")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return fallback_days


def _active_student(active_status: Any) -> int:
    raw = str(active_status or "").strip().lower()
    return 1 if raw in ("1", "active", "true", "yes") else 0


def _serialize_dates(d: dict, keys: tuple) -> None:
    """In-place ISO-stringify selected datetime keys."""
    for k in keys:
        if d.get(k) and hasattr(d[k], "isoformat"):
            d[k] = d[k].isoformat()


async def _activity_map(user_ids: list[int], db: AsyncSession) -> dict[int, StudentCampaignActivity]:
    """Latest campaign activity per student, keyed by student_user_id."""
    if not user_ids:
        return {}
    result = await db.execute(
        select(StudentCampaignActivity)
        .where(StudentCampaignActivity.student_user_id.in_(user_ids))
        .order_by(StudentCampaignActivity.student_user_id, StudentCampaignActivity.created_at.desc())
    )
    seen: dict[int, StudentCampaignActivity] = {}
    for a in result.scalars().all():
        if a.student_user_id not in seen:
            seen[a.student_user_id] = a
    return seen


async def _note_map(user_ids: list[int], db: AsyncSession) -> dict[int, StudentNote]:
    """Latest internal note per student, keyed by user_id."""
    if not user_ids:
        return {}
    result = await db.execute(
        select(StudentNote)
        .where(StudentNote.user_id.in_(user_ids))
        .order_by(StudentNote.user_id, StudentNote.created_at.desc())
    )
    seen: dict[int, StudentNote] = {}
    for n in result.scalars().all():
        if n.user_id not in seen:
            seen[n.user_id] = n
    return seen


def _merge_activity(rows: list[dict], acts: dict, notes: dict) -> list[dict]:
    """Attach campaign activity and note fields to each student row in-place."""
    for r in rows:
        uid = r.get("UserID")
        a = acts.get(uid)
        n = notes.get(uid)
        r["last_campaign_activity_date"] = _isostr(a.activity_date) if a else None
        r["last_campaign_activity_type"] = a.activity_type if a else None
        r["last_campaign_activity"] = a.activity_label if a else None
        r["campaign_notes"] = n.content if n else None
        r["notes"] = n.content if n else None
    return rows


def _compute_common(rows: list[dict]) -> list[dict]:
    """Compute derived fields present on all tabs."""
    for i, r in enumerate(rows):
        r["row_id"] = i + 1
        r["student_name"] = _name(r)
        r["weeks_in_program"] = _weeks_in_program(r.get("IPBCStartDate") or r.get("StudentStartDate"))
        r["last_hw_submitted_days"] = _hw_submitted_days(r.get("LastSubmitted"), r.get("LastActivityDays"))
        r["active_student"] = _active_student(r.get("ActiveStatus"))
        # Nulls for staff fields not yet sourced
        r.setdefault("mentor_name", None)
        r.setdefault("mentor_email", None)
        r.setdefault("super_mentor_name", None)
        r.setdefault("super_mentor_email", None)
        r.setdefault("instructor_name", None)
        r.setdefault("instructor_email", None)
        r.setdefault("mm_user_id", None)
        r.setdefault("days_to_market", None)
        r.setdefault("plan_name", None)
        r.setdefault("agreement_signed", None)
        r.setdefault("down_payment", None)
        # Engagement-only nulls
        r.setdefault("certified_date", None)
        r.setdefault("ssis_start_date", None)
        r.setdefault("days_old", None)
        r.setdefault("months_back_ssis", None)
        r.setdefault("ssis_completion_days", None)
        # Placement-only nulls
        r.setdefault("last_interview", None)
        r.setdefault("last_interview_days_ago", None)
        r.setdefault("recruiter_interview_count", None)
        r.setdefault("technical_interview_count", None)
        r.setdefault("recruiter_to_technical_ratio", None)
        r.setdefault("avg_interview_prep_score", None)
        r.setdefault("avg_interview_score", None)
        r.setdefault("chat_gpt_prompt", None)
        _serialize_dates(r, ("IPBCStartDate", "StudentStartDate", "ClassStartDate"))
    return rows


# ── Tab endpoints ──────────────────────────────────────────────────────────────

@router.get("/newcomers")
async def newcomers(
    role: str | None = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Students who started within the last 90 days.

    Uses IPBCStartDate when populated; falls back to StudentStartDate so
    class-phase students (who have no IPBC date yet) are still included.
    """
    cutoff = datetime.now() - timedelta(days=90)
    result = await db.execute(
        select(StudentTriggerData)
        .where(
            or_(
                and_(
                    StudentTriggerData.IPBCStartDate.isnot(None),
                    StudentTriggerData.IPBCStartDate >= cutoff,
                ),
                and_(
                    StudentTriggerData.IPBCStartDate.is_(None),
                    StudentTriggerData.StudentStartDate.isnot(None),
                    StudentTriggerData.StudentStartDate >= cutoff,
                ),
            )
        )
        .limit(limit)
    )
    rows = [_raw(s) for s in result.scalars().all()]
    user_ids = [r["UserID"] for r in rows]
    acts, notes = await _activity_map(user_ids, db), await _note_map(user_ids, db)
    rows = _compute_common(_merge_activity(rows, acts, notes))
    logger.info("[LIFECYCLE] newcomers count=%d", len(rows))
    return APIResponse.ok({"tab": "newcomers", "total": len(rows), "rows": rows})


@router.get("/engagement")
async def engagement(
    role: str | None = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """All students — coursework engagement view. SSIS flag via LastActivitySection."""
    result = await db.execute(select(StudentTriggerData).limit(limit))
    rows = [_raw(s) for s in result.scalars().all()]
    user_ids = [r["UserID"] for r in rows]
    acts, notes = await _activity_map(user_ids, db), await _note_map(user_ids, db)
    rows = _compute_common(_merge_activity(rows, acts, notes))
    logger.info("[LIFECYCLE] engagement count=%d", len(rows))
    return APIResponse.ok({"tab": "engagement", "total": len(rows), "rows": rows})


@router.get("/hw-risk")
async def hw_risk(
    role: str | None = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """All students — homework and progress risk view.

    IPBC gate removed: class-phase students with outstanding homework are the
    primary audience for this tab. IPBCStartDate is NULL for all students until
    they enter the IPBC phase.
    """
    result = await db.execute(select(StudentTriggerData).limit(limit))
    rows = [_raw(s) for s in result.scalars().all()]
    user_ids = [r["UserID"] for r in rows]
    acts, notes = await _activity_map(user_ids, db), await _note_map(user_ids, db)
    rows = _compute_common(_merge_activity(rows, acts, notes))
    logger.info("[LIFECYCLE] hw-risk count=%d", len(rows))
    return APIResponse.ok({"tab": "hw_risk", "total": len(rows), "rows": rows})


@router.get("/cap-hopefuls")
async def cap_hopefuls(
    role: str | None = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Students with AttendancePercentage > 50 — potential CAP candidates.

    IPBC gate removed: attendance is populated for all students regardless of phase.
    AttendancePercentage is stored on a 0-100 scale (normalized from SQL Server's 0-1 fraction).
    """
    result = await db.execute(
        select(StudentTriggerData)
        .where(
            StudentTriggerData.AttendancePercentage.isnot(None),
            StudentTriggerData.AttendancePercentage > 50,
        )
        .limit(limit)
    )
    rows = [_raw(s) for s in result.scalars().all()]
    user_ids = [r["UserID"] for r in rows]
    acts, notes = await _activity_map(user_ids, db), await _note_map(user_ids, db)
    rows = _compute_common(_merge_activity(rows, acts, notes))
    logger.info("[LIFECYCLE] cap-hopefuls count=%d", len(rows))
    return APIResponse.ok({"tab": "cap_hopefuls", "total": len(rows), "rows": rows})


@router.get("/launch-hopefuls")
async def launch_hopefuls(
    role: str | None = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Students nearing Launch — attendance > 70%, section contains 'CAP Project'."""
    result = await db.execute(
        select(StudentTriggerData)
        .where(
            StudentTriggerData.IPBCStartDate.isnot(None),
            StudentTriggerData.AttendancePercentage > 70,
            StudentTriggerData.LastActivitySection.ilike("%CAP Project%"),
        )
        .limit(limit)
    )
    rows = [_raw(s) for s in result.scalars().all()]
    user_ids = [r["UserID"] for r in rows]
    acts, notes = await _activity_map(user_ids, db), await _note_map(user_ids, db)
    rows = _compute_common(_merge_activity(rows, acts, notes))
    logger.info("[LIFECYCLE] launch-hopefuls count=%d", len(rows))
    return APIResponse.ok({"tab": "launch_hopefuls", "total": len(rows), "rows": rows})


@router.get("/placement-hopefuls")
async def placement_hopefuls(
    role: str | None = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Students in Launch/placement pipeline — attendance > 70%, section contains 'Launch'."""
    result = await db.execute(
        select(StudentTriggerData)
        .where(
            StudentTriggerData.IPBCStartDate.isnot(None),
            StudentTriggerData.AttendancePercentage > 70,
            StudentTriggerData.LastActivitySection.ilike("%Launch%"),
        )
        .limit(limit)
    )
    rows = [_raw(s) for s in result.scalars().all()]
    user_ids = [r["UserID"] for r in rows]
    acts, notes = await _activity_map(user_ids, db), await _note_map(user_ids, db)
    rows = _compute_common(_merge_activity(rows, acts, notes))
    logger.info("[LIFECYCLE] placement-hopefuls count=%d", len(rows))
    return APIResponse.ok({"tab": "placement_hopefuls", "total": len(rows), "rows": rows})
