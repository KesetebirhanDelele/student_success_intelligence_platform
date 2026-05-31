"""Snapshot assembly service.

Assembles warehouse.student_snapshots rows from ai_chatbot_triggerdata
plus platform records. No SQL Server queries during assembly (FAD-2).

Public API:
  assemble_snapshot(student_id, snapshot_month, db, ...) -> dict
  finalize_snapshot(snapshot_id, db) -> dict
  assemble_all_active_snapshots(snapshot_month, db, ...) -> dict
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional, Union

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIInsight,
    OutreachHistory,
    StateTransitionLog,
    StudentCampaignActivity,
    StudentTriggerData,
)
from app.services.payment import compute_balance, payment_risk_label

logger = logging.getLogger(__name__)

_NARRATIVE_TYPES = [
    "risk_summary",
    "progress_summary",
    "monthly_narrative",
    "intervention_recommendation",
    "sentiment_analysis",
]

_FINGERPRINT_SCHEMA_VERSION = "0003"
_REPORT_TEMPLATE_VERSION = "1.0"


# ── Segment classifier ────────────────────────────────────────────────────────

def _classify_segment(student: StudentTriggerData) -> str:
    """Derive lifecycle segment from mirror data at snapshot time."""
    section = (student.CurrentSection or "").lower()
    if "launch" in section:
        return "PLACEMENT_HOPEFULS"
    if "cap" in section:
        return "LAUNCH_HOPEFULS"
    att = student.AttendancePercentage or 0.0
    if att > 50.0:
        return "CAP_HOPEFULS"
    if student.IPBCStartDate:
        days_in = (date.today() - student.IPBCStartDate.date()).days
        if days_in <= 90:
            return "NEWCOMERS"
    return "ENGAGEMENT"


def _weeks_in_program(student: StudentTriggerData) -> Optional[int]:
    if not student.IPBCStartDate:
        return None
    return (date.today() - student.IPBCStartDate.date()).days // 7


# ── Outreach summary ──────────────────────────────────────────────────────────

async def _get_outreach_summary(
    student_id: int,
    month_start: datetime,
    month_end: datetime,
    db: AsyncSession,
) -> dict:
    oh = (await db.execute(
        select(OutreachHistory)
        .where(OutreachHistory.user_id == student_id)
        .where(OutreachHistory.created_at >= month_start)
        .where(OutreachHistory.created_at <= month_end)
    )).scalars().all()

    ca = (await db.execute(
        select(StudentCampaignActivity)
        .where(StudentCampaignActivity.student_user_id == student_id)
        .where(StudentCampaignActivity.activity_date >= month_start)
        .where(StudentCampaignActivity.activity_date <= month_end)
    )).scalars().all()

    total = len(oh) + len(ca)
    channels = list(
        {o.channel for o in oh if o.channel}
        | {c.channel for c in ca if c.channel}
    )

    last_contact: Optional[datetime] = None
    for o in oh:
        ts = o.created_at
        if ts and (last_contact is None or ts > last_contact):
            last_contact = ts
    for c in ca:
        ts = c.activity_date
        if ts and (last_contact is None or ts > last_contact):
            last_contact = ts

    breakdown: dict[str, int] = {}
    for o in oh:
        if o.channel:
            breakdown[o.channel] = breakdown.get(o.channel, 0) + 1
    for c in ca:
        if c.channel:
            breakdown[c.channel] = breakdown.get(c.channel, 0) + 1

    days_since: Optional[int] = None
    if last_contact:
        lc_aware = last_contact if last_contact.tzinfo else last_contact.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - lc_aware).days

    total_responses = sum(1 for o in oh if o.state_after == "RESPONDED")

    return {
        "total": total,
        "channels": channels,
        "last_contact": last_contact.date() if last_contact else None,
        "days_since_contact": days_since,
        "breakdown": breakdown,
        "total_responses": total_responses,
    }


# ── AI narrative fetcher ──────────────────────────────────────────────────────

async def _get_ai_narratives(
    student_id: int,
    db: AsyncSession,
) -> tuple[dict, str, bool]:
    """
    Returns (narratives_dict, ai_governance_tier, ai_content_available).
    Reads most recent FINALIZED insight per type.
    """
    narratives: dict[str, Optional[str]] = {}
    any_available = False
    gov_tier = "UNAVAILABLE"

    for insight_type in _NARRATIVE_TYPES:
        result = (await db.execute(
            select(AIInsight)
            .where(AIInsight.user_id == student_id)
            .where(AIInsight.insight_type == insight_type)
            .where(AIInsight.is_finalized == True)  # noqa: E712
            .order_by(AIInsight.created_at.desc())
            .limit(1)
        )).scalars().first()

        if result:
            narratives[insight_type] = result.content_text
            any_available = True
            gov_tier = "FINALIZED_COPY"
        else:
            narratives[insight_type] = None

    return narratives, gov_tier, any_available


# ── State transition fetcher ──────────────────────────────────────────────────

async def _get_state_transitions(
    student_id: int,
    month_start: datetime,
    month_end: datetime,
    db: AsyncSession,
) -> list[dict]:
    rows = (await db.execute(
        select(StateTransitionLog)
        .where(StateTransitionLog.user_id == student_id)
        .where(StateTransitionLog.created_at >= month_start)
        .where(StateTransitionLog.created_at <= month_end)
        .order_by(StateTransitionLog.created_at)
    )).scalars().all()

    return [
        {
            "transition_date": r.created_at.isoformat(),
            "from_state": r.from_state,
            "to_state": r.to_state,
            "trigger": r.trigger,
            "actor": r.actor,
            "correlation_id": r.correlation_id,
            "execution_mode": r.execution_mode,
        }
        for r in rows
    ]


# ── Idempotency check ─────────────────────────────────────────────────────────

async def _existing_finalized_snapshot_id(
    student_id: int,
    snapshot_month: date,
    db: AsyncSession,
) -> Optional[int]:
    row = await db.execute(text(
        "SELECT id FROM warehouse.student_snapshots "
        "WHERE student_id = :sid AND snapshot_month = :month "
        "AND status = 'FINALIZED' LIMIT 1"
    ), {"sid": student_id, "month": snapshot_month})
    result = row.fetchone()
    return result[0] if result else None


# ── Snapshot insert ───────────────────────────────────────────────────────────

async def _insert_snapshot(
    *,
    student_id: int,
    snapshot_month: date,
    student: StudentTriggerData,
    payment_balance: float,
    p_risk: str,
    segment: str,
    weeks: Optional[int],
    outreach: dict,
    narratives: dict,
    state_transitions: list[dict],
    execution_mode: str,
    config_version_id: str,
    correlation_id: Optional[str],
    db: AsyncSession,
) -> int:
    snap_id_result = await db.execute(text("""
        INSERT INTO warehouse.student_snapshots (
            student_id, snapshot_month, status, execution_mode, correlation_id,
            ss_first_name, ss_last_name, ss_email, ss_phone_number, ss_path_name,
            ss_hws_behind, ss_avg_eff_rating, ss_last_activity_days,
            ss_attendance_percentage, ss_current_section, ss_ipbc_start_date,
            ss_past_10_days_logon, ss_total_payments, ss_total_credits,
            ss_payment_balance, ss_class_value, ss_fee_paid, ss_class_fees_paid,
            ss_class_name, ss_class_signups_id, ss_active_status,
            ss_status_i, ss_status_ii, ss_student_start_date, ss_class_start_date,
            ss_last_activity_section, ss_last_login_days, ss_last_submitted,
            segment_classification, payment_risk_label, actual_balance,
            is_bundle_deal, weeks_in_program, days_since_last_submission,
            total_outreach_attempts, total_responses, last_contact_date,
            days_since_last_contact, channel_breakdown_json,
            fingerprint_schema_version, fingerprint_config_registry_version,
            fingerprint_report_template_version, fingerprint_computed_at,
            finalized_at
        ) VALUES (
            :student_id, :snapshot_month, 'FINALIZED', :execution_mode, :correlation_id,
            :first_name, :last_name, :email, :phone, :path_name,
            :hws_behind, :avg_eff_rating, :last_activity_days,
            :attendance_pct, :current_section, :ipbc_start_date,
            :past_10_days_logon, :total_payments, :total_credits,
            :payment_balance, :class_value, :fee_paid, :class_fees_paid,
            :class_name, :class_signups_id, :active_status,
            :status_i, :status_ii, :student_start_date, :class_start_date,
            :last_activity_section, :last_login_days, :last_submitted,
            :segment, :p_risk, :actual_balance,
            :is_bundle, :weeks_in_program, :days_since_sub,
            :total_outreach, :total_responses, :last_contact_date,
            :days_since_contact, :channel_breakdown,
            :fp_schema, :fp_config, :fp_template, now(),
            now()
        )
        RETURNING id
    """), {
        "student_id": student_id,
        "snapshot_month": snapshot_month,
        "execution_mode": execution_mode,
        "correlation_id": uuid.UUID(correlation_id) if correlation_id else None,
        "first_name": student.FirstName,
        "last_name": student.LastName,
        "email": student.Email,
        "phone": student.PhoneNumber,
        "path_name": student.PathName,
        "hws_behind": student.HWsBehind,
        "avg_eff_rating": student.AvgEffRating,
        "last_activity_days": student.LastActivityDays,
        "attendance_pct": student.AttendancePercentage,
        "current_section": student.CurrentSection,
        "ipbc_start_date": student.IPBCStartDate,
        "past_10_days_logon": student.Past10DaysLogon,
        "total_payments": student.Total_Payments,
        "total_credits": student.Total_Credits,
        "payment_balance": student.PaymentBalance,
        "class_value": student.ClassValue,
        "fee_paid": student.FeePaid,
        "class_fees_paid": student.ClassFeesPaid,
        "class_name": student.ClassName,
        "class_signups_id": student.ClassSignupsID,
        "active_status": student.ActiveStatus,
        "status_i": student.StatusI,
        "status_ii": student.StatusII,
        "student_start_date": student.StudentStartDate,
        "class_start_date": student.ClassStartDate,
        "last_activity_section": student.LastActivitySection,
        "last_login_days": student.LastLoginDays,
        "last_submitted": student.LastSubmitted,
        "segment": segment,
        "p_risk": p_risk,
        "actual_balance": payment_balance,
        "is_bundle": student.Total_Credits is not None and float(student.Total_Credits or 0) > 0,
        "weeks_in_program": weeks,
        "days_since_sub": student.LastActivityDays,
        "total_outreach": outreach["total"],
        "total_responses": outreach["total_responses"],
        "last_contact_date": outreach["last_contact"],
        "days_since_contact": outreach["days_since_contact"],
        "channel_breakdown": json.dumps(outreach["breakdown"]),
        "fp_schema": _FINGERPRINT_SCHEMA_VERSION,
        "fp_config": config_version_id,
        "fp_template": _REPORT_TEMPLATE_VERSION,
    })
    snap_row = snap_id_result.fetchone()
    snap_id: int = snap_row[0]

    # Insert AI narratives companion row
    await db.execute(text("""
        INSERT INTO warehouse.snapshot_ai_narratives (
            snapshot_id, risk_summary_text, progress_summary_text,
            monthly_narrative_text, intervention_recommendation_text,
            trend_interpretation_text, copied_at
        ) VALUES (
            :snap_id, :risk_summary, :progress_summary,
            :monthly_narrative, :intervention_recommendation,
            :sentiment, now()
        )
    """), {
        "snap_id": snap_id,
        "risk_summary": narratives.get("risk_summary"),
        "progress_summary": narratives.get("progress_summary"),
        "monthly_narrative": narratives.get("monthly_narrative"),
        "intervention_recommendation": narratives.get("intervention_recommendation"),
        "sentiment": narratives.get("sentiment_analysis"),
    })

    await db.commit()
    return snap_id


# ── Historical student state lookup ──────────────────────────────────────────

def _month_last_day(snapshot_month: date) -> date:
    if snapshot_month.month == 12:
        return date(snapshot_month.year + 1, 1, 1) - timedelta(days=1)
    return date(snapshot_month.year, snapshot_month.month + 1, 1) - timedelta(days=1)


def _adjust_relative_fields(row: dict, snapshot_month: date) -> dict:
    """
    Relative fields (LastActivityDays, LastLoginDays) are computed by SQL Server
    as "days from the sync date" not "days from the snapshot month end."
    When the history was captured N days after the month ended, subtract N to
    approximate the values as they would have been at month-end.
    Activities that happened AFTER month-end show as negative — floor to 0
    (the student was active at or before month-end in those cases).
    """
    captured_at = row.get("captured_at")
    if not captured_at:
        return row

    capture_date = captured_at.date() if hasattr(captured_at, "date") else captured_at
    month_end = _month_last_day(snapshot_month)
    offset = (capture_date - month_end).days  # 0 if captured at month-end, >0 if later

    if offset <= 0:
        return row

    adjusted = dict(row)
    for field in ("LastActivityDays", "LastLoginDays"):
        val = adjusted.get(field)
        if val is not None:
            adjusted[field] = max(0, val - offset)
    return adjusted


async def _get_student_for_month(
    student_id: int,
    snapshot_month: date,
    db: AsyncSession,
) -> Optional[Union[StudentTriggerData, SimpleNamespace]]:
    """
    Return the student's SQL Server mirror state as of snapshot_month.
    Checks student_mirror_history first (month-end captured state).
    Falls back to the live ai_chatbot_triggerdata mirror if no history exists.
    """
    hist_row = (await db.execute(text("""
        SELECT
            "UserID", "FirstName", "LastName", "Email", "PhoneNumber", "PathName",
            "HWsBehind", "AvgEffRating", "LastActivityDays",
            "AttendancePercentage", "CurrentSection", "IPBCStartDate",
            "Past10DaysLogon", "Total_Payments", "Total_Credits", "PaymentBalance",
            "ClassValue", "FeePaid", "ClassFeesPaid", "ClassName", "ClassSignupsID",
            "ActiveStatus", "StatusI", "StatusII", "StudentStartDate", "ClassStartDate",
            "LastActivitySection", "LastLoginDays", "LastSubmitted",
            captured_at
        FROM student_mirror_history
        WHERE snapshot_month = :month AND "UserID" = :uid
    """), {"month": snapshot_month, "uid": student_id})).mappings().first()

    if hist_row:
        adjusted = _adjust_relative_fields(dict(hist_row), snapshot_month)
        return SimpleNamespace(**adjusted)

    return await db.get(StudentTriggerData, student_id)


# ── Public API ────────────────────────────────────────────────────────────────

async def assemble_snapshot(
    student_id: int,
    snapshot_month: date,
    db: AsyncSession,
    execution_mode: str = "SHADOW",
    config_version_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Assemble and finalize a warehouse.student_snapshots row for (student_id, snapshot_month).
    Idempotent: returns existing FINALIZED snapshot if one already exists.
    Reads only from PostgreSQL — no SQL Server queries (FAD-2).
    """
    cfg_ver = config_version_id or "UNKNOWN_V0"
    corr = correlation_id or str(uuid.uuid4())

    existing = await _existing_finalized_snapshot_id(student_id, snapshot_month, db)
    if existing:
        return {
            "status": "exists",
            "snapshot_id": existing,
            "student_id": student_id,
            "snapshot_month": str(snapshot_month),
        }

    student = await _get_student_for_month(student_id, snapshot_month, db)
    if not student:
        return {
            "status": "error",
            "error": f"student {student_id} not found in ai_chatbot_triggerdata",
            "student_id": student_id,
            "snapshot_month": str(snapshot_month),
        }

    if isinstance(student, StudentTriggerData):
        student_dict = {c.key: getattr(student, c.key) for c in student.__table__.columns}
    else:
        student_dict = vars(student)
    payment_bal = compute_balance(student_dict)
    p_risk = payment_risk_label(payment_bal)
    segment = _classify_segment(student)
    weeks = _weeks_in_program(student)

    month_start = datetime(snapshot_month.year, snapshot_month.month, 1, tzinfo=timezone.utc)
    if snapshot_month.month == 12:
        month_end = datetime(snapshot_month.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(snapshot_month.year, snapshot_month.month + 1, 1, tzinfo=timezone.utc)

    outreach = await _get_outreach_summary(student_id, month_start, month_end, db)
    narratives, ai_tier, ai_available = await _get_ai_narratives(student_id, db)
    state_transitions = await _get_state_transitions(student_id, month_start, month_end, db)

    snap_id = await _insert_snapshot(
        student_id=student_id,
        snapshot_month=snapshot_month,
        student=student,
        payment_balance=payment_bal,
        p_risk=p_risk,
        segment=segment,
        weeks=weeks,
        outreach=outreach,
        narratives=narratives,
        state_transitions=state_transitions,
        execution_mode=execution_mode,
        config_version_id=cfg_ver,
        correlation_id=corr,
        db=db,
    )

    logger.info(json.dumps({
        "service": "snapshot", "event": "snapshot_assembled",
        "student_id": student_id, "snapshot_month": str(snapshot_month),
        "snapshot_id": snap_id, "execution_mode": execution_mode,
        "segment": segment, "payment_risk": p_risk, "ai_available": ai_available,
        "correlation_id": corr,
    }))

    return {
        "status": "created",
        "snapshot_id": snap_id,
        "student_id": student_id,
        "snapshot_month": str(snapshot_month),
        "segment": segment,
        "payment_risk": p_risk,
        "ai_available": ai_available,
        "execution_mode": execution_mode,
    }


async def assemble_all_active_snapshots(
    snapshot_month: date,
    db: AsyncSession,
    execution_mode: str = "SHADOW",
    config_version_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Assemble snapshots for all students in ai_chatbot_triggerdata.
    Idempotent per student: skips if FINALIZED snapshot already exists.
    Returns summary counts.
    """
    all_students = (await db.execute(select(StudentTriggerData.UserID))).scalars().all()

    created = 0
    skipped = 0
    errors = 0

    for sid in all_students:
        result = await assemble_snapshot(
            student_id=sid,
            snapshot_month=snapshot_month,
            db=db,
            execution_mode=execution_mode,
            config_version_id=config_version_id,
        )
        if result["status"] == "created":
            created += 1
        elif result["status"] == "exists":
            skipped += 1
        else:
            errors += 1
            logger.warning(json.dumps({
                "service": "snapshot", "event": "snapshot_error",
                "student_id": sid, "error": result.get("error"),
            }))

    return {
        "snapshot_month": str(snapshot_month),
        "total": len(all_students),
        "created": created,
        "skipped_existing": skipped,
        "errors": errors,
        "execution_mode": execution_mode,
    }
