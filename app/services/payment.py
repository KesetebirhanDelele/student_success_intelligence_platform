"""Payment calculation service — Bundle Deal fix and risk classification.

Exported symbols used by both routers:
  compute_balance(student_dict)   → float   — canonical bundle-aware balance
  payment_risk_label(balance)     → str     — HIGH | MEDIUM | CLEAR
  build_payment_row(orm_row)      → dict    — full reconciliation row for the table
"""
from __future__ import annotations

from app.models import StudentTriggerData


def compute_balance(student: dict) -> float:
    """Bundle Deal fix: if PaymentBalance == 0 but Total_Credits > 0 and
    ClassValue > 0, the stored balance is incorrect.  Compute as
    ClassValue − Total_Payments − Total_Credits.

    Safe to call on every student; non-bundle rows return stored_balance unchanged.
    """
    total_payments = float(student.get("Total_Payments") or 0)
    total_credits = float(student.get("Total_Credits") or 0)
    class_value = float(student.get("ClassValue") or 0)
    stored_balance = float(student.get("PaymentBalance") or 0)

    is_bundle = total_credits > 0 and stored_balance == 0 and class_value > 0
    if is_bundle:
        return max(0.0, class_value - total_payments - total_credits)
    return stored_balance


def payment_risk_label(actual_balance: float) -> str:
    """Classify payment risk from outstanding balance."""
    if actual_balance > 1000:
        return "HIGH"
    if actual_balance > 0:
        return "MEDIUM"
    return "CLEAR"


def build_payment_row(s: StudentTriggerData) -> dict:
    """Full payment row for the reconciliation table.

    Includes bundle fix, pct_paid, and risk classification.
    IPBCStartDate is ISO-serialised in-place so the dict is JSON-safe.
    """
    d = {c.key: getattr(s, c.key) for c in s.__table__.columns}
    total_credits = float(d.get("Total_Credits") or 0)
    stored_balance = float(d.get("PaymentBalance") or 0)
    class_value = float(d.get("ClassValue") or 0)
    is_bundle = total_credits > 0 and stored_balance == 0 and class_value > 0

    actual_bal = compute_balance(d)
    total_payments = float(d.get("Total_Payments") or 0)
    pct_paid = round(total_payments / class_value * 100, 1) if class_value else 0.0

    if d.get("IPBCStartDate") and hasattr(d["IPBCStartDate"], "isoformat"):
        d["IPBCStartDate"] = d["IPBCStartDate"].isoformat()

    return {
        **d,
        "display_name": (
            f"{s.FirstName or ''} {s.LastName or ''}".strip() or f"#{s.UserID}"
        ),
        "actual_balance": actual_bal,
        "is_bundle_deal": is_bundle,
        "pct_paid": pct_paid,
        "payment_risk": payment_risk_label(actual_bal),
    }
