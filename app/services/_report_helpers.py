"""Report content helpers: trend loaders, outreach intelligence, lifecycle patterns.

Extracted from report.py to keep that module under the 500-line ceiling.

Public API:
  load_trend_data(student_id, report_month, db)        -> dict
  load_outreach_intelligence(student_id, start, end, db) -> dict
  load_lifecycle_patterns(student_id, db)              -> dict
  build_academic_trends(snap, trend_data)              -> dict
  build_engagement_depth(snap, trend_data)             -> dict
  build_financial_trends(snap, trend_data)             -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from datetime import date as date_type
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Trend data loader ─────────────────────────────────────────────────────────

async def load_trend_data(
    student_id: int,
    report_month: date_type,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Load up to 3 months of historical snapshot data from warehouse.student_snapshots.
    Returns trends for academic, engagement, and financial sections.
    history[0] = most recent (current report month), history[-1] = oldest.
    """
    rows = (await db.execute(text("""
        SELECT snapshot_month,
               ss_hws_behind, ss_avg_eff_rating, ss_attendance_percentage,
               ss_last_activity_days, ss_last_login_days, ss_past_10_days_logon,
               actual_balance, ss_current_section, segment_classification
        FROM warehouse.student_snapshots
        WHERE student_id = :sid
          AND status = 'FINALIZED'
          AND snapshot_month <= :month
        ORDER BY snapshot_month DESC
        LIMIT 3
    """), {"sid": student_id, "month": report_month})).mappings().all()

    history = [dict(r) for r in rows]

    def ms(r: dict) -> str:
        return str(r["snapshot_month"])

    hw_velocity = [
        {"month": ms(r), "hws_behind": r["ss_hws_behind"]}
        for r in history
    ]
    efficiency_trend = [
        {"month": ms(r), "avg_eff_rating": r["ss_avg_eff_rating"]}
        for r in history
    ]
    attendance_trend = [
        {"month": ms(r), "attendance_pct": r["ss_attendance_percentage"]}
        for r in history
    ]
    balance_trend = [
        {"month": ms(r), "balance": r["actual_balance"]}
        for r in history
    ]
    section_progression = [
        {"month": ms(r), "section": r["ss_current_section"]}
        for r in history
    ]

    submission_momentum = _derive_submission_momentum(history)

    return {
        "hw_velocity": hw_velocity,
        "efficiency_trend": efficiency_trend,
        "attendance_trend": attendance_trend,
        "balance_trend": balance_trend,
        "section_progression": section_progression,
        "submission_momentum": submission_momentum,
        "months_of_data": len(history),
    }


def _derive_submission_momentum(history: list[dict]) -> str:
    if len(history) < 2:
        return "INSUFFICIENT_DATA"
    curr = history[0].get("ss_last_activity_days")
    prev = history[1].get("ss_last_activity_days")
    if curr is None or prev is None:
        return "INSUFFICIENT_DATA"
    delta = curr - prev
    if delta < -3:
        return "IMPROVING"
    if delta > 3:
        return "DECLINING"
    return "STABLE"


# ── Outreach intelligence loader ──────────────────────────────────────────────

async def load_outreach_intelligence(
    student_id: int,
    month_start: datetime,
    month_end: datetime,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Derive per-channel response rates, time-to-response, and fatigue signal
    from outreach_history for the given month window.
    """
    rows = (await db.execute(text("""
        SELECT channel, state_before, state_after, created_at
        FROM outreach_history
        WHERE user_id = :sid
          AND created_at >= :start AND created_at < :end
        ORDER BY created_at
    """), {"sid": student_id, "start": month_start, "end": month_end})).mappings().all()

    records = [dict(r) for r in rows]

    channel_stats: dict[str, dict] = {}
    contacted_times: list[datetime] = []
    responded_times: list[datetime] = []

    for r in records:
        ch = r["channel"] or "UNKNOWN"
        channel_stats.setdefault(ch, {"attempts": 0, "responses": 0})
        channel_stats[ch]["attempts"] += 1
        if r["state_after"] in ("RESPONDED", "ANALYZED", "RESOLVED"):
            channel_stats[ch]["responses"] += 1
            responded_times.append(r["created_at"])
        if r["state_after"] == "CONTACTED":
            contacted_times.append(r["created_at"])

    for stats in channel_stats.values():
        att = stats["attempts"]
        resp = stats["responses"]
        stats["response_rate"] = round(resp / att, 3) if att else 0.0

    total_att = sum(v["attempts"] for v in channel_stats.values())
    total_resp = sum(v["responses"] for v in channel_stats.values())
    fatigue_score = total_att - total_resp

    avg_days_to_response = _compute_avg_days_to_response(contacted_times, responded_times)

    most_responsive = (
        max(channel_stats.items(), key=lambda x: x[1]["response_rate"])[0]
        if channel_stats else None
    )

    return {
        "channel_response_rates": channel_stats,
        "total_attempts": total_att,
        "total_responses": total_resp,
        "fatigue_score": fatigue_score,
        "fatigue_flag": fatigue_score >= 3 and total_resp == 0,
        "avg_days_to_response": avg_days_to_response,
        "most_responsive_channel": most_responsive,
    }


def _compute_avg_days_to_response(
    contacted: list[datetime],
    responded: list[datetime],
) -> Optional[int]:
    if not contacted or not responded:
        return None
    first_contact = min(contacted)
    after_contact = [r for r in responded if r >= first_contact]
    if not after_contact:
        return None
    first_response = min(after_contact)
    delta = first_response - (
        first_contact if first_contact.tzinfo
        else first_contact.replace(tzinfo=timezone.utc)
    )
    return max(0, delta.days)


# ── Lifecycle pattern loader ──────────────────────────────────────────────────

async def load_lifecycle_patterns(
    student_id: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Derive state-machine patterns from state_transition_log and
    student_outreach_tracking for this student (all time, not month-filtered).
    """
    transitions = (await db.execute(text("""
        SELECT from_state, to_state, created_at
        FROM state_transition_log
        WHERE user_id = :sid
        ORDER BY created_at
    """), {"sid": student_id})).mappings().all()

    trans_list = [dict(t) for t in transitions]

    intervention_cycles = sum(
        1 for t in trans_list if t["to_state"] == "INTERVENTION_REQUIRED"
    )

    days_first_contact_to_response = _compute_contact_response_delta(trans_list)

    current_state_row = (await db.execute(text("""
        SELECT state, current_attempt, last_contact_at, next_retry_at
        FROM student_outreach_tracking
        WHERE user_id = :sid
        ORDER BY updated_at DESC
        LIMIT 1
    """), {"sid": student_id})).mappings().first()

    current_state = dict(current_state_row) if current_state_row else {}

    segment_tenure, current_segment = await _compute_segment_tenure(student_id, db)

    return {
        "current_lifecycle_state": current_state.get("state"),
        "current_attempt_number": current_state.get("current_attempt"),
        "last_contact_at": (
            current_state["last_contact_at"].isoformat()
            if current_state.get("last_contact_at") else None
        ),
        "next_retry_at": (
            current_state["next_retry_at"].isoformat()
            if current_state.get("next_retry_at") else None
        ),
        "total_state_transitions": len(trans_list),
        "intervention_cycle_count": intervention_cycles,
        "days_first_contact_to_response": days_first_contact_to_response,
        "segment_tenure_months": segment_tenure,
        "current_segment": current_segment,
    }


def _compute_contact_response_delta(trans_list: list[dict]) -> Optional[int]:
    contacted_at: Optional[datetime] = None
    for t in trans_list:
        if t["to_state"] == "CONTACTED" and contacted_at is None:
            contacted_at = t["created_at"]
        if contacted_at and t["to_state"] in ("RESPONDED", "ANALYZED"):
            ca = contacted_at if contacted_at.tzinfo else contacted_at.replace(tzinfo=timezone.utc)
            ra = t["created_at"] if t["created_at"].tzinfo else t["created_at"].replace(tzinfo=timezone.utc)
            return max(0, (ra - ca).days)
    return None


async def _compute_segment_tenure(
    student_id: int,
    db: AsyncSession,
) -> tuple[int, Optional[str]]:
    rows = (await db.execute(text("""
        SELECT snapshot_month, segment_classification
        FROM warehouse.student_snapshots
        WHERE student_id = :sid AND status = 'FINALIZED'
        ORDER BY snapshot_month DESC
        LIMIT 6
    """), {"sid": student_id})).mappings().all()

    if not rows:
        return 0, None

    current_seg = rows[0]["segment_classification"]
    tenure = sum(1 for r in rows if r["segment_classification"] == current_seg)
    return tenure, current_seg


# ── Section builders (pure computation from snap + loaded data) ───────────────

def build_academic_trends(snap: dict, trend_data: dict) -> dict:
    return {
        "hw_velocity":          trend_data.get("hw_velocity", []),
        "efficiency_trend":     trend_data.get("efficiency_trend", []),
        "section_progression":  trend_data.get("section_progression", []),
        "submission_momentum":  trend_data.get("submission_momentum", "INSUFFICIENT_DATA"),
        "months_of_data":       trend_data.get("months_of_data", 1),
    }


def build_engagement_depth(snap: dict, trend_data: dict) -> dict:
    login_days = snap.get("ss_last_login_days") or 0
    activity_days = snap.get("ss_last_activity_days") or 0
    gap = login_days - activity_days

    if activity_days > 14:
        pattern = "INACTIVE"
    elif gap > 5:
        pattern = "ACTIVE_NON_SUBMITTER"
    elif login_days <= 1 and activity_days <= 3:
        pattern = "CONSISTENT"
    else:
        pattern = "MODERATE"

    gap_interpretation = (
        "ACTIVE_NON_SUBMITTER" if gap > 5
        else "INACTIVE" if activity_days > 14
        else "ENGAGED"
    )

    return {
        "login_submission_gap":  gap,
        "gap_interpretation":    gap_interpretation,
        "peak_activity_logins_10d": snap.get("ss_past_10_days_logon"),
        "activity_pattern":      pattern,
        "attendance_trend":      trend_data.get("attendance_trend", []),
    }


def build_financial_trends(snap: dict, trend_data: dict) -> dict:
    class_value = snap.get("ss_class_value") or 0
    total_payments = snap.get("ss_total_payments") or 0
    total_credits = snap.get("ss_total_credits") or 0
    class_fees_paid = snap.get("ss_class_fees_paid") or 0
    fee_paid = snap.get("ss_fee_paid")

    remaining_after_credits = max(0.0, class_value - total_payments - total_credits)
    enrollment_only = fee_paid is True and class_fees_paid == 0

    if snap.get("is_bundle_deal"):
        payment_behavior = "BUNDLE_DEAL"
    elif total_credits > 0:
        payment_behavior = "PARTIAL_CREDIT"
    elif total_payments >= class_value > 0:
        payment_behavior = "FULLY_PAID"
    elif total_payments > 0:
        payment_behavior = "INSTALLMENT"
    else:
        payment_behavior = "UNPAID"

    return {
        "balance_trend":           trend_data.get("balance_trend", []),
        "payment_behavior":        payment_behavior,
        "remaining_after_credits": remaining_after_credits,
        "enrollment_fee_only":     enrollment_only,
        "fee_structure": {
            "enrollment_fee_paid": fee_paid,
            "class_fees_paid":     class_fees_paid,
            "total_credits":       total_credits,
            "class_value":         class_value,
        },
    }
