"""Payment and placement-interview sync services (Option B — Gap 2 + Gap 3).

Reads from SQL Server (read-only CCPP); writes to PostgreSQL only.
SHADOW-safe: no GHL/outreach dispatch.

Public API:
  sync_payments(db)              — update ai_chatbot_triggerdata payment fields
  sync_placement_interviews(db)  — upsert vw_ColaberryInterviews_PlacementHopefuls
                                   into student_interview_prep
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# ── SQL Server fetch helpers ──────────────────────────────────────────────────

_PAYMENT_QUERY = """
WITH latest_enrollment AS (
    SELECT
        StudentUserID,
        ClassSignupsID,
        ROW_NUMBER() OVER (
            PARTITION BY StudentUserID ORDER BY CreateDate DESC
        ) AS rn
    FROM ADF_Mentorship_Program
    WHERE IsActive = 1
)
SELECT
    trig.UserID,
    ISNULL(isp.TotalCost, 0)                                         AS ClassValue,
    ISNULL(ps.TotalAmountInPaySimple, 0)
        + ISNULL(ps.TotalAmountInPayPal, 0)                          AS Total_Payments,
    ISNULL(da.DAFees, 0)                                             AS ClassFeesPaid,
    ISNULL(isp.TotalCost, 0)
        - ISNULL(ps.TotalAmountInPaySimple, 0)
        - ISNULL(ps.TotalAmountInPayPal, 0)                          AS PaymentBalance
FROM AI_ChatBot_TriggerData trig
LEFT JOIN latest_enrollment le
       ON le.StudentUserID = trig.UserID AND le.rn = 1
LEFT JOIN ADF_ClassSignups acs
       ON acs.ClassSignupsID = le.ClassSignupsID
LEFT JOIN IPBC_SubscriptionPlan isp
       ON isp.SubscriptionPlanID = acs.SubscriptionPlanID
LEFT JOIN vw_IPBC_Students_Payment_Summary ps
       ON ps.ClassSignupsID = le.ClassSignupsID
LEFT JOIN (
    SELECT
        ClassSignupsID,
        SUM(CASE WHEN PaymentStatus != 'PENDING' THEN Amount ELSE 0 END) AS DAFees
    FROM VW_PAYPAL_DISTINCT_TRANSACTIONS
    WHERE TRANSTYPE = 'T'
    GROUP BY ClassSignupsID
) da ON da.ClassSignupsID = le.ClassSignupsID
"""

_PLACEMENT_INTERVIEW_QUERY = """
SELECT * FROM vw_ColaberryInterviewPreparation_UpcomingInterviews_Processed
"""

# Cross-database query: PlanName + DownPaymentAmt for IPBC students.
# vw_IPBC_DownPaymentTracking lives in the CCPP database (same SQL Server instance).
# We pull both tables separately and join in Python so we can discover the view's
# available columns at runtime rather than hardcoding a join key.
_IPBC_PLAN_QUERY = """
SELECT PlanName, DOWNPAYMENTAMT, AMOUNTPAID, IPBC_StartDate, *
FROM [CCPP].[dbo].[vw_IPBC_DownPaymentTracking]
"""

_IPBC_STUDENT_EMAIL_QUERY = """
SELECT UserID, Email, FirstName, LastName, IPBC_StartDate
FROM [dbo].[AI_Chatbot_TriggerData_IPBC]
"""


def _fetch_sync(query: str) -> tuple[list[dict], Optional[str]]:
    """Synchronous SQL Server fetch — run in a thread via asyncio.to_thread."""
    if not settings.mssql_configured:
        return [], "SQL Server not configured"
    try:
        import pyodbc
        conn = pyodbc.connect(settings.mssql_dsn, timeout=30)
        cursor = conn.cursor()
        cursor.execute(query)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows, None
    except Exception as exc:
        logger.error(json.dumps({
            "service": "payment_sync", "event": "mssql_fetch_failed",
            "error_class": type(exc).__name__, "error": str(exc),
        }))
        return [], str(exc)


# ── Payment sync ──────────────────────────────────────────────────────────────

_PAYMENT_UPDATE_SQL = """
UPDATE ai_chatbot_triggerdata
SET
    "Total_Payments"  = :total_payments,
    "ClassValue"      = :class_value,
    "ClassFeesPaid"   = :class_fees_paid,
    "PaymentBalance"  = :payment_balance
WHERE "UserID" = :user_id
"""


async def sync_payments(db: AsyncSession) -> dict[str, Any]:
    """
    Pull payment totals from SQL Server and patch ai_chatbot_triggerdata.

    Fields updated per student:
      Total_Payments  = PaySimple + PayPal subscription totals
      ClassValue      = IPBC_SubscriptionPlan.TotalCost
      ClassFeesPaid   = PayPal DA fees (TRANSTYPE='T')
      PaymentBalance  = ClassValue - Total_Payments

    Total_Credits and FeePaid are NOT overwritten — they remain as sourced
    from AI_ChatBot_TriggerData via the regular MSSQL sync.
    """
    rows, error = await asyncio.to_thread(_fetch_sync, _PAYMENT_QUERY)
    if error:
        logger.warning(json.dumps({
            "service": "payment_sync", "event": "payment_fetch_failed", "error": error,
        }))
        return {"synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    updated = skipped = 0
    for row in rows:
        user_id = row.get("UserID")
        if not user_id:
            skipped += 1
            continue

        total_payments = float(row.get("Total_Payments") or 0)
        class_value = float(row.get("ClassValue") or 0)
        class_fees_paid = float(row.get("ClassFeesPaid") or 0)
        payment_balance = float(row.get("PaymentBalance") or 0)

        result = await db.execute(text(_PAYMENT_UPDATE_SQL), {
            "user_id": int(user_id),
            "total_payments": total_payments,
            "class_value": class_value,
            "class_fees_paid": class_fees_paid,
            "payment_balance": payment_balance,
        })
        if result.rowcount > 0:
            updated += 1
        else:
            skipped += 1  # student not in local mirror yet

    await db.commit()
    logger.info(json.dumps({
        "service": "payment_sync", "event": "payment_sync_complete",
        "total_fetched": len(rows), "updated": updated, "skipped": skipped,
    }))
    return {
        "status": "ok",
        "total_fetched": len(rows),
        "updated": updated,
        "skipped": skipped,
        "error": None,
    }


# ── IPBC payment plan sync ───────────────────────────────────────────────────

_PLAN_UPDATE_SQL = """
UPDATE ai_chatbot_triggerdata
SET
    plan_name        = :plan_name,
    down_payment_amt = :down_payment_amt
WHERE "UserID" = :user_id
"""


def _normalize_email(val: Any) -> str:
    return (str(val) or "").strip().lower()


async def sync_ipbc_payment_plans(db: AsyncSession) -> dict[str, Any]:
    """
    Pull IPBC payment plan data from CCPP.dbo.vw_IPBC_DownPaymentTracking and
    patch plan_name + down_payment_amt in ai_chatbot_triggerdata.

    Join strategy (in priority order):
      1. Email match (case-insensitive) — if view has an Email column
      2. Name match (FirstName + LastName) — if view has name columns
    Falls back gracefully with a warning if no join key is available in the view.
    """
    plan_rows, err1 = await asyncio.to_thread(_fetch_sync, _IPBC_PLAN_QUERY)
    student_rows, err2 = await asyncio.to_thread(_fetch_sync, _IPBC_STUDENT_EMAIL_QUERY)

    if err1:
        logger.warning(json.dumps({
            "service": "payment_sync", "event": "ipbc_plan_fetch_failed", "error": err1,
        }))
        return {"synced": 0, "error": err1, "status": "failed"}

    if err2:
        logger.warning(json.dumps({
            "service": "payment_sync", "event": "ipbc_student_email_fetch_failed", "error": err2,
        }))
        return {"synced": 0, "error": err2, "status": "failed"}

    if not plan_rows:
        return {"synced": 0, "error": None, "status": "ok", "note": "no_plan_rows"}

    # Discover join key from view's columns
    view_cols = {k.lower() for k in plan_rows[0].keys()} if plan_rows else set()
    has_email = "email" in view_cols
    has_name = "firstname" in view_cols and "lastname" in view_cols

    # Build lookup from view rows
    plan_by_email: dict[str, dict] = {}
    plan_by_name: dict[str, dict] = {}
    for row in plan_rows:
        if has_email and row.get("Email"):
            plan_by_email[_normalize_email(row["Email"])] = row
        if has_name:
            fn = (row.get("FirstName") or "").strip().lower()
            ln = (row.get("LastName") or "").strip().lower()
            if fn and ln:
                plan_by_name[f"{fn}|{ln}"] = row

    if not has_email and not has_name:
        logger.warning(json.dumps({
            "service": "payment_sync",
            "event": "ipbc_plan_no_join_key",
            "view_cols": sorted(view_cols),
            "note": "vw_IPBC_DownPaymentTracking has neither Email nor FirstName+LastName — cannot match to students",
        }))
        return {"synced": 0, "error": "no_join_key", "status": "failed", "view_cols": sorted(view_cols)}

    updated = skipped = 0
    for student in student_rows:
        uid_raw = student.get("UserID")
        if not uid_raw:
            skipped += 1
            continue
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            skipped += 1
            continue

        plan_row = None
        if has_email and student.get("Email"):
            plan_row = plan_by_email.get(_normalize_email(student["Email"]))
        if plan_row is None and has_name:
            fn = (student.get("FirstName") or "").strip().lower()
            ln = (student.get("LastName") or "").strip().lower()
            if fn and ln:
                plan_row = plan_by_name.get(f"{fn}|{ln}")

        if plan_row is None:
            skipped += 1
            continue

        plan_name = plan_row.get("PlanName") or plan_row.get("planname")
        down_pmt = float(plan_row.get("DOWNPAYMENTAMT") or plan_row.get("downpaymentamt") or 0)

        result = await db.execute(text(_PLAN_UPDATE_SQL), {
            "user_id": uid,
            "plan_name": str(plan_name) if plan_name else None,
            "down_payment_amt": down_pmt,
        })
        if result.rowcount > 0:
            updated += 1
        else:
            skipped += 1

    await db.commit()
    logger.info(json.dumps({
        "service": "payment_sync", "event": "ipbc_plan_sync_complete",
        "plan_rows_fetched": len(plan_rows), "student_rows_fetched": len(student_rows),
        "updated": updated, "skipped": skipped,
        "join_key": "email" if has_email else "name",
    }))
    return {
        "status": "ok",
        "plan_rows_fetched": len(plan_rows),
        "student_rows_fetched": len(student_rows),
        "updated": updated,
        "skipped": skipped,
        "error": None,
    }


# ── Placement interview sync ──────────────────────────────────────────────────

async def sync_placement_interviews(db: AsyncSession) -> dict[str, Any]:
    """
    Pull vw_ColaberryInterviews_PlacementHopefuls from SQL Server and
    upsert into student_interview_prep as raw_data JSONB.

    CandidateID in the view == UserID in the platform.
    Overwrites existing row for the same user_id on each sync.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models import StudentInterviewPrep

    rows, error = await asyncio.to_thread(_fetch_sync, _PLACEMENT_INTERVIEW_QUERY)
    if error:
        logger.warning(json.dumps({
            "service": "payment_sync", "event": "placement_interview_fetch_failed",
            "error": error,
        }))
        return {"synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    now = datetime.now(timezone.utc)
    synced = 0
    for row in rows:
        candidate_id = row.get("CandidateID")
        if not candidate_id:
            continue

        # Serialize datetime fields so JSONB stores ISO strings, not Python objects
        serializable = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                serializable[k] = v.isoformat()
            else:
                serializable[k] = v

        stmt = (
            pg_insert(StudentInterviewPrep)
            .values(user_id=int(candidate_id), raw_data=serializable, synced_at=now)
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={"raw_data": serializable, "synced_at": now},
            )
        )
        await db.execute(stmt)
        synced += 1

    await db.commit()
    logger.info(json.dumps({
        "service": "payment_sync", "event": "placement_interview_sync_complete",
        "total_fetched": len(rows), "synced": synced,
    }))
    return {
        "status": "ok",
        "total_fetched": len(rows),
        "synced": synced,
        "error": None,
    }
