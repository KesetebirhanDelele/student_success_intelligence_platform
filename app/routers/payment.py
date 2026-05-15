"""Payment reconciliation endpoints with Bundle Deal fix."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentTriggerData
from app.schemas import APIResponse
from app.services.segmentation import filter_by_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payment")


def _compute_balance(s: dict) -> float:
    """
    Bundle Deal fix: if PaymentBalance == 0 but Total_Credits > 0 and ClassValue > 0,
    the stored PaymentBalance is incorrect.  Compute actual balance as
    ClassValue − Total_Payments − Total_Credits.
    """
    total_payments = float(s.get("Total_Payments") or 0)
    total_credits = float(s.get("Total_Credits") or 0)
    class_value = float(s.get("ClassValue") or 0)
    stored_balance = float(s.get("PaymentBalance") or 0)

    is_bundle_deal = (total_credits > 0 and stored_balance == 0 and class_value > 0)
    if is_bundle_deal:
        return max(0.0, class_value - total_payments - total_credits)
    return stored_balance


def _payment_row(s: StudentTriggerData) -> dict:
    d = {c.key: getattr(s, c.key) for c in s.__table__.columns}
    total_credits = float(d.get("Total_Credits") or 0)
    stored_balance = float(d.get("PaymentBalance") or 0)
    class_value = float(d.get("ClassValue") or 0)
    is_bundle = total_credits > 0 and stored_balance == 0 and class_value > 0

    actual_balance = _compute_balance(d)
    total_payments = float(d.get("Total_Payments") or 0)
    pct_paid = round(total_payments / class_value * 100, 1) if class_value else 0.0

    risk = "HIGH" if actual_balance > 1000 else ("MEDIUM" if actual_balance > 0 else "CLEAR")

    if d.get("IPBCStartDate") and hasattr(d["IPBCStartDate"], "isoformat"):
        d["IPBCStartDate"] = d["IPBCStartDate"].isoformat()

    return {
        **d,
        "display_name": f"{s.FirstName or ''} {s.LastName or ''}".strip() or f"#{s.UserID}",
        "actual_balance": actual_balance,
        "is_bundle_deal": is_bundle,
        "pct_paid": pct_paid,
        "payment_risk": risk,
    }


@router.get("/reconciliation")
async def payment_reconciliation(
    role: str | None = Query(None),
    risk: str | None = Query(None, description="HIGH | MEDIUM | CLEAR"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Full payment reconciliation table.
    Includes Bundle Deal fix: actual_balance recalculated where PaymentBalance is
    incorrectly 0 for bundle students with credits.
    """
    result = await db.execute(select(StudentTriggerData))
    rows = [_payment_row(s) for s in result.scalars().all()]
    rows = filter_by_role(rows, role)

    if risk:
        rows = [r for r in rows if r["payment_risk"] == risk.upper()]

    # Aggregates
    total_balance = sum(r["actual_balance"] for r in rows)
    bundle_count = sum(1 for r in rows if r["is_bundle_deal"])
    high_risk = sum(1 for r in rows if r["payment_risk"] == "HIGH")
    clear_count = sum(1 for r in rows if r["payment_risk"] == "CLEAR")

    # Sort: highest balance first
    rows.sort(key=lambda r: r["actual_balance"], reverse=True)
    total = len(rows)

    return APIResponse.ok({
        "role": role or "Support",
        "risk_filter": risk,
        "total": total,
        "summary": {
            "total_outstanding_balance": round(total_balance, 2),
            "bundle_deal_students": bundle_count,
            "high_risk_count": high_risk,
            "clear_count": clear_count,
            "bundle_fix_note": (
                "Bundle students had PaymentBalance=0 but owe ClassValue−Payments−Credits. "
                "actual_balance column corrects this."
            ),
        },
        "rows": rows[offset: offset + limit],
    })


@router.get("/student/{user_id}")
async def student_payment(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    """Payment detail for a single student including bundle fix."""
    s = await db.get(StudentTriggerData, user_id)
    if not s:
        return APIResponse.fail("NOT_FOUND", f"Student {user_id} not in source mirror.")
    return APIResponse.ok(_payment_row(s))
