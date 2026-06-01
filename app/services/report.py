"""Monthly report generation service.

Reads FINALIZED warehouse.student_snapshots rows and assembles
warehouse.monthly_reports with structured report_content_json.

No SQL Server queries, no AI calls (FAD-2).

Public API:
  generate_student_report(student_id, snapshot_month, db, ...) -> dict
  generate_cohort_report(cohort_id, report_month, db, ...) -> dict
  get_report_content(student_id, year, month, db) -> dict | None

Report sections (v1.1):
  identity, risk_priority, academic_performance, academic_trends,
  engagement, engagement_depth, financial, financial_trends,
  outreach_summary, outreach_intelligence, lifecycle_patterns,
  ai_narratives, state_history, governance_metadata
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services._report_helpers import (
    build_academic_trends,
    build_engagement_depth,
    build_financial_trends,
    load_lifecycle_patterns,
    load_outreach_intelligence,
    load_trend_data,
)

logger = logging.getLogger(__name__)

_TEMPLATE_VERSION = "1.2"


# ── Snapshot readers (raw SQL — warehouse schema) ─────────────────────────────

async def _load_finalized_snapshot(
    student_id: int,
    snapshot_month: date,
    db: AsyncSession,
) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT
            ss.id AS snapshot_id,
            ss.student_id, ss.snapshot_month, ss.status,
            ss.execution_mode, ss.finalized_at,
            ss.ss_first_name, ss.ss_last_name, ss.ss_email, ss.ss_phone_number,
            ss.ss_path_name, ss.ss_hws_behind, ss.ss_avg_eff_rating,
            ss.ss_last_activity_days, ss.ss_attendance_percentage,
            ss.ss_current_section, ss.ss_ipbc_start_date,
            ss.ss_total_payments, ss.ss_total_credits, ss.ss_payment_balance,
            ss.ss_class_value, ss.ss_fee_paid, ss.ss_class_fees_paid,
            ss.ss_class_name, ss.ss_active_status, ss.ss_status_i, ss.ss_status_ii,
            ss.ss_last_activity_section, ss.ss_last_login_days, ss.ss_last_submitted,
            ss.segment_classification, ss.payment_risk_label, ss.actual_balance,
            ss.is_bundle_deal, ss.weeks_in_program, ss.days_since_last_submission,
            ss.total_outreach_attempts, ss.total_responses, ss.last_contact_date,
            ss.days_since_last_contact, ss.channel_breakdown_json,
            ss.fingerprint_schema_version, ss.fingerprint_config_registry_version,
            ss.fingerprint_report_template_version, ss.fingerprint_computed_at,
            ss.lineage_version,
            san.risk_summary_text, san.progress_summary_text,
            san.monthly_narrative_text, san.intervention_recommendation_text,
            san.trend_interpretation_text
        FROM warehouse.student_snapshots ss
        LEFT JOIN warehouse.snapshot_ai_narratives san ON san.snapshot_id = ss.id
        WHERE ss.student_id = :sid
          AND ss.snapshot_month = :month
          AND ss.status = 'FINALIZED'
        ORDER BY ss.lineage_version DESC
        LIMIT 1
    """), {"sid": student_id, "month": snapshot_month})).mappings().first()

    return dict(row) if row else None


async def _load_state_transitions_from_snapshot(
    snapshot_id: int,
    student_id: int,
    snapshot_month: date,
    db: AsyncSession,
) -> list[dict]:
    """Load state transitions for the snapshot month from the platform log."""
    if snapshot_month.month == 12:
        month_end = datetime(snapshot_month.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(snapshot_month.year, snapshot_month.month + 1, 1, tzinfo=timezone.utc)
    month_start = datetime(snapshot_month.year, snapshot_month.month, 1, tzinfo=timezone.utc)

    rows = (await db.execute(text("""
        SELECT from_state, to_state, trigger, actor, correlation_id,
               execution_mode, created_at
        FROM state_transition_log
        WHERE user_id = :sid
          AND created_at >= :start AND created_at < :end
        ORDER BY created_at
    """), {"sid": student_id, "start": month_start, "end": month_end})).mappings().all()

    return [
        {
            "transition_date": r["created_at"].isoformat(),
            "from_state": r["from_state"],
            "to_state": r["to_state"],
            "trigger": r["trigger"],
            "actor": r["actor"],
            "correlation_id": r["correlation_id"],
            "execution_mode": r["execution_mode"],
        }
        for r in rows
    ]


# ── Report content builder ────────────────────────────────────────────────────

def _build_report_content(
    snap: dict,
    state_history: list[dict],
    generated_at: datetime,
    lineage_version: int,
    trend_data: dict,
    outreach_intel: dict,
    lifecycle: dict,
) -> dict:
    """
    Assemble the structured report_content_json from a finalized snapshot row
    plus pre-loaded trend, outreach intelligence, and lifecycle data.
    Section order follows the display grouping: base section then its
    analysis/trend companion, so viewers see related data together.
    """
    ai_available = any([
        snap.get("risk_summary_text"),
        snap.get("progress_summary_text"),
        snap.get("monthly_narrative_text"),
        snap.get("intervention_recommendation_text"),
    ])
    ai_tier = "FINALIZED_COPY" if ai_available else "UNAVAILABLE"

    ipbc_str = None
    if snap.get("ss_ipbc_start_date"):
        ipbc_str = str(snap["ss_ipbc_start_date"])[:10]

    return {
        "report_version": _TEMPLATE_VERSION,
        "student_id": snap["student_id"],
        "snapshot_month": str(snap["snapshot_month"]),
        "generated_at": generated_at.isoformat(),
        "lineage_version": lineage_version,
        "sections": {
            # ── Identity & risk ───────────────────────────────────────────────
            "identity": {
                "full_name": f"{snap.get('ss_first_name') or ''} {snap.get('ss_last_name') or ''}".strip(),
                "user_id": snap["student_id"],
                "email": snap.get("ss_email"),
                "phone": snap.get("ss_phone_number"),
                "program_path": snap.get("ss_path_name"),
                "ipbc_start_date": ipbc_str,
                "weeks_in_program": snap.get("weeks_in_program"),
            },
            "risk_priority": {
                "risk_level": _derive_risk_level(snap),
                "payment_risk_label": snap.get("payment_risk_label") or "UNKNOWN",
                "segment_classification": snap.get("segment_classification"),
            },
            # ── Academic: current state + multi-month trends ──────────────────
            "academic_performance": {
                "hws_behind": snap.get("ss_hws_behind"),
                "avg_eff_rating": snap.get("ss_avg_eff_rating"),
                "hw_submitted_days_ago": snap.get("days_since_last_submission"),
                "attendance_pct": snap.get("ss_attendance_percentage"),
                "active_status": snap.get("ss_active_status") or "Unknown",
                "current_section": snap.get("ss_current_section"),
                "status_i": snap.get("ss_status_i"),
                "status_ii": snap.get("ss_status_ii"),
            },
            "academic_trends": build_academic_trends(snap, trend_data),
            # ── Engagement: current state + depth analysis ────────────────────
            "engagement": {
                "last_activity_days": snap.get("ss_last_activity_days"),
                "last_login_days": snap.get("ss_last_login_days"),
                "current_class_name": snap.get("ss_class_name") or snap.get("ss_current_section"),
                "last_activity_section": snap.get("ss_last_activity_section"),
                "last_submitted": snap.get("ss_last_submitted"),
            },
            "engagement_depth": build_engagement_depth(snap, trend_data),
            # ── Financial: current state + trends ─────────────────────────────
            "financial": {
                "class_value": snap.get("ss_class_value"),
                "total_payments": snap.get("ss_total_payments"),
                "total_credits": snap.get("ss_total_credits"),
                "payment_balance_stored": snap.get("ss_payment_balance"),
                "actual_balance": snap.get("actual_balance"),
                "fee_paid": snap.get("ss_fee_paid"),
                "class_fees_paid": snap.get("ss_class_fees_paid"),
                "is_bundle_deal": snap.get("is_bundle_deal"),
            },
            "financial_trends": build_financial_trends(snap, trend_data),
            # ── Outreach: summary + channel intelligence ──────────────────────
            "outreach_summary": {
                "total_attempts": snap.get("total_outreach_attempts") or 0,
                "channels_used": snap.get("channel_breakdown_json") or {},
                "last_contact_date": str(snap["last_contact_date"]) if snap.get("last_contact_date") else None,
                "days_since_last_contact": snap.get("days_since_last_contact"),
                "total_responses": snap.get("total_responses") or 0,
                "response_received": bool(snap.get("total_responses")),
            },
            "outreach_intelligence": outreach_intel,
            # ── Lifecycle patterns ────────────────────────────────────────────
            "lifecycle_patterns": lifecycle,
            # ── AI narratives ─────────────────────────────────────────────────
            "ai_narratives": {
                "risk_summary": snap.get("risk_summary_text") or "No narrative available at time of finalization.",
                "progress_summary": snap.get("progress_summary_text") or "No narrative available at time of finalization.",
                "monthly_narrative": snap.get("monthly_narrative_text") or "No narrative available at time of finalization.",
                "intervention_recommendation": snap.get("intervention_recommendation_text") or "No narrative available at time of finalization.",
                "sentiment_classification": snap.get("trend_interpretation_text") or "No narrative available at time of finalization.",
                "ai_governance_tier": ai_tier,
                "ai_content_available": ai_available,
            },
            "state_history": state_history,
            "governance_metadata": {
                "snapshot_id": snap["snapshot_id"],
                "snapshot_month": str(snap["snapshot_month"]),
                "lifecycle_state": snap.get("status"),
                "fingerprint_schema_version": snap.get("fingerprint_schema_version"),
                "fingerprint_config_registry_version": snap.get("fingerprint_config_registry_version"),
                "fingerprint_report_template_version": snap.get("fingerprint_report_template_version"),
                "fingerprint_computed_at": snap["fingerprint_computed_at"].isoformat() if snap.get("fingerprint_computed_at") else None,
                "execution_mode_at_finalization": snap.get("execution_mode"),
                "report_generated_date": generated_at.isoformat(),
                "report_lineage_version": lineage_version,
            },
        },
    }


def _derive_risk_level(snap: dict) -> str:
    hws = snap.get("ss_hws_behind") or 0
    inactivity = snap.get("ss_last_activity_days") or 0
    if hws >= 3 or inactivity > 14:
        return "HIGH"
    if hws >= 1 or inactivity > 7:
        return "MEDIUM"
    return "LOW"


# ── Report idempotency key ────────────────────────────────────────────────────

def _report_idempotency_key(
    student_id: int,
    snapshot_month: date,
    lineage_version: int,
) -> str:
    raw = f"student:{student_id}|month:{snapshot_month}|lineage:{lineage_version}|template:{_TEMPLATE_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


# ── Monthly report insert ─────────────────────────────────────────────────────

async def _insert_monthly_report(
    *,
    student_id: int,
    snapshot_month: date,
    snapshot_id: int,
    report_content: dict,
    execution_mode: str,
    lineage_version: int,
    correlation_id: str,
    db: AsyncSession,
) -> int:
    idem_key = _report_idempotency_key(student_id, snapshot_month, lineage_version)
    fp_json = json.dumps({"snapshot_id": snapshot_id})
    content_json = json.dumps(report_content)
    now = datetime.now(timezone.utc)

    result = await db.execute(text("""
        INSERT INTO warehouse.monthly_reports (
            cohort_id, report_month, template_version, lineage_version,
            status, report_idempotency_key, source_snapshot_fingerprint_json,
            report_content_json, generated_at, published_at, generated_by,
            correlation_id, execution_mode
        ) VALUES (
            :cohort_id, :report_month, :template_version, :lineage_version,
            'REPORT_PUBLISHED', :idem_key, :fp_json,
            :content_json, :now, :now, 'report_service',
            :correlation_id, :execution_mode
        )
        ON CONFLICT (report_idempotency_key) DO NOTHING
        RETURNING id
    """), {
        "cohort_id": str(student_id),
        "report_month": snapshot_month,
        "template_version": _TEMPLATE_VERSION,
        "lineage_version": lineage_version,
        "idem_key": idem_key,
        "fp_json": fp_json,
        "content_json": content_json,
        "now": now,
        "correlation_id": uuid.UUID(correlation_id) if correlation_id else None,
        "execution_mode": execution_mode,
    })
    row = result.fetchone()
    if row:
        await db.commit()
        return row[0]

    # Conflict: report already exists — return existing id
    existing = (await db.execute(text(
        "SELECT id FROM warehouse.monthly_reports WHERE report_idempotency_key = :k"
    ), {"k": idem_key})).fetchone()
    return existing[0] if existing else 0


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_student_report(
    student_id: int,
    snapshot_month: date,
    db: AsyncSession,
    execution_mode: str = "SHADOW",
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate a monthly report for one student from their FINALIZED snapshot.
    Idempotent: returns existing report if already generated.
    """
    corr = correlation_id or str(uuid.uuid4())

    snap = await _load_finalized_snapshot(student_id, snapshot_month, db)
    if not snap:
        return {
            "status": "error",
            "error": f"No FINALIZED snapshot for student {student_id} month {snapshot_month}. "
                     "Run POST /reports/snapshots/assemble first.",
            "student_id": student_id,
            "snapshot_month": str(snapshot_month),
        }

    state_history = await _load_state_transitions_from_snapshot(
        snap["snapshot_id"], student_id, snapshot_month, db
    )

    if snapshot_month.month == 12:
        month_end_dt = datetime(snapshot_month.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end_dt = datetime(snapshot_month.year, snapshot_month.month + 1, 1, tzinfo=timezone.utc)
    month_start_dt = datetime(snapshot_month.year, snapshot_month.month, 1, tzinfo=timezone.utc)

    trend_data = await load_trend_data(student_id, snapshot_month, db)
    outreach_intel = await load_outreach_intelligence(student_id, month_start_dt, month_end_dt, db)
    lifecycle = await load_lifecycle_patterns(student_id, db)

    lineage_version = snap.get("lineage_version") or 1
    generated_at = datetime.now(timezone.utc)
    report_content = _build_report_content(
        snap, state_history, generated_at, lineage_version,
        trend_data, outreach_intel, lifecycle,
    )

    report_id = await _insert_monthly_report(
        student_id=student_id,
        snapshot_month=snapshot_month,
        snapshot_id=snap["snapshot_id"],
        report_content=report_content,
        execution_mode=execution_mode,
        lineage_version=lineage_version,
        correlation_id=corr,
        db=db,
    )

    logger.info(json.dumps({
        "service": "report", "event": "monthly_report_generated",
        "student_id": student_id, "snapshot_month": str(snapshot_month),
        "report_id": report_id, "execution_mode": execution_mode,
        "correlation_id": corr,
    }))

    return {
        "status": "ok",
        "report_id": report_id,
        "student_id": student_id,
        "snapshot_month": str(snapshot_month),
        "execution_mode": execution_mode,
        "report_content": report_content,
    }


async def get_report_content(
    student_id: int,
    year: int,
    month: int,
    db: AsyncSession,
) -> Optional[dict]:
    """
    Retrieve the most recent published report for a student + month.
    Returns None if no report exists (snapshot not yet assembled or finalized).
    """
    snapshot_month = date(year, month, 1)
    row = (await db.execute(text("""
        SELECT id, report_content_json, execution_mode, generated_at, lineage_version
        FROM warehouse.monthly_reports
        WHERE cohort_id = :cohort_id
          AND report_month = :report_month
          AND status = 'REPORT_PUBLISHED'
        ORDER BY id DESC
        LIMIT 1
    """), {"cohort_id": str(student_id), "report_month": snapshot_month})).mappings().first()

    if not row:
        return None

    return {
        "report_id": row["id"],
        "student_id": student_id,
        "report_month": str(snapshot_month),
        "execution_mode": row["execution_mode"],
        "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        "lineage_version": row["lineage_version"],
        "report_content": row["report_content_json"],
    }


async def generate_cohort_report(
    cohort_id: str,
    report_month: date,
    db: AsyncSession,
    execution_mode: str = "SHADOW",
) -> dict[str, Any]:
    """
    Generate reports for all students whose cohort_id matches.
    cohort_id matches segment_classification in student_snapshots for the given month.
    """
    rows = (await db.execute(text("""
        SELECT student_id FROM warehouse.student_snapshots
        WHERE snapshot_month = :month
          AND status = 'FINALIZED'
          AND segment_classification = :cohort_id
    """), {"month": report_month, "cohort_id": cohort_id})).fetchall()

    generated = 0
    errors = 0
    for (sid,) in rows:
        result = await generate_student_report(
            student_id=sid,
            snapshot_month=report_month,
            db=db,
            execution_mode=execution_mode,
        )
        if result["status"] == "ok":
            generated += 1
        else:
            errors += 1

    return {
        "cohort_id": cohort_id,
        "report_month": str(report_month),
        "total": len(rows),
        "generated": generated,
        "errors": errors,
        "execution_mode": execution_mode,
    }
