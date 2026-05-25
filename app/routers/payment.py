"""Payment reconciliation endpoints — delegates all calculation to services/payment.py."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentTriggerData
from app.schemas import APIResponse
from app.services.payment import build_payment_row
from app.services.segmentation import filter_by_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payment")


@router.get("/reconciliation")
async def payment_reconciliation(
    role: str | None = Query(None),
    risk: str | None = Query(None, description="HIGH | MEDIUM | CLEAR"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Full payment reconciliation table.

    Includes Bundle Deal fix: actual_balance is recalculated where PaymentBalance
    is incorrectly 0 for bundle students with credits.
    """
    result = await db.execute(select(StudentTriggerData))
    rows = [build_payment_row(s) for s in result.scalars().all()]
    rows = filter_by_role(rows, role)

    if risk:
        rows = [r for r in rows if r["payment_risk"] == risk.upper()]

    total_balance = sum(r["actual_balance"] for r in rows)
    bundle_count = sum(1 for r in rows if r["is_bundle_deal"])
    high_risk = sum(1 for r in rows if r["payment_risk"] == "HIGH")
    clear_count = sum(1 for r in rows if r["payment_risk"] == "CLEAR")

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
    return APIResponse.ok(build_payment_row(s))
