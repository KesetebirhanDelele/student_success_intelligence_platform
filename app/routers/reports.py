"""Monthly report and snapshot HTTP endpoints.

Routes:
  POST /reports/snapshots/assemble          — assemble snapshot for student + month
  POST /reports/snapshots/assemble-all      — batch assemble for all students
  GET  /reports/monthly/{student_id}/{year}/{month} — retrieve report (historical or current)
  POST /reports/monthly/generate            — on-demand report generation
  POST /reports/monthly/generate-all        — batch report generation for a month
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
from app.services.report import generate_cohort_report, generate_student_report, get_report_content
from app.services.snapshot import assemble_all_active_snapshots, assemble_snapshot

router = APIRouter(prefix="/reports", tags=["reports"])


# ── Request models ────────────────────────────────────────────────────────────

class AssembleSnapshotRequest(BaseModel):
    student_id: int
    year: int
    month: int
    execution_mode: str = "SHADOW"
    config_version_id: Optional[str] = None


class AssembleAllRequest(BaseModel):
    year: int
    month: int
    execution_mode: str = "SHADOW"
    config_version_id: Optional[str] = None


class GenerateReportRequest(BaseModel):
    student_id: int
    year: int
    month: int
    execution_mode: str = "SHADOW"


class GenerateAllRequest(BaseModel):
    year: int
    month: int
    execution_mode: str = "SHADOW"
    cohort_id: Optional[str] = None


# ── Snapshot endpoints ────────────────────────────────────────────────────────

@router.post("/snapshots/assemble")
async def assemble_student_snapshot(
    req: AssembleSnapshotRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Assemble and finalize a warehouse.student_snapshots row for one student + month.
    Idempotent: safe to call multiple times; returns existing snapshot if already FINALIZED.
    """
    snapshot_month = date(req.year, req.month, 1)
    result = await assemble_snapshot(
        student_id=req.student_id,
        snapshot_month=snapshot_month,
        db=db,
        execution_mode=req.execution_mode,
        config_version_id=req.config_version_id,
    )
    return APIResponse.ok(result)


@router.post("/snapshots/assemble-all")
async def assemble_all_snapshots(
    req: AssembleAllRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Assemble snapshots for every student in ai_chatbot_triggerdata for a given month.
    Idempotent per student. Returns summary counts.
    """
    snapshot_month = date(req.year, req.month, 1)
    result = await assemble_all_active_snapshots(
        snapshot_month=snapshot_month,
        db=db,
        execution_mode=req.execution_mode,
        config_version_id=req.config_version_id,
    )
    return APIResponse.ok(result)


# ── Report endpoints ──────────────────────────────────────────────────────────

@router.get("/monthly/{student_id}/{year}/{month}")
async def get_monthly_report(
    student_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Retrieve the most recent published monthly report for a student.
    Historical on-demand: works for any month with a FINALIZED snapshot.
    Returns 404-style error if no report has been generated yet.
    """
    report = await get_report_content(student_id, year, month, db)
    if not report:
        return APIResponse.fail(
            code="REPORT_NOT_FOUND",
            message=(
                f"No published report for student {student_id} "
                f"month {year}-{month:02d}. "
                "Assemble the snapshot first, then call POST /reports/monthly/generate."
            ),
        )
    return APIResponse.ok(report)


@router.post("/monthly/generate")
async def generate_monthly_report(
    req: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Generate (or re-retrieve) the monthly report for one student + month.
    Requires a FINALIZED snapshot to exist. Run POST /reports/snapshots/assemble first.
    Idempotent: returns the existing report if already generated.
    """
    snapshot_month = date(req.year, req.month, 1)
    result = await generate_student_report(
        student_id=req.student_id,
        snapshot_month=snapshot_month,
        db=db,
        execution_mode=req.execution_mode,
    )
    if result.get("status") == "error":
        return APIResponse.fail(code="SNAPSHOT_MISSING", message=result["error"])
    return APIResponse.ok(result)


@router.post("/monthly/generate-all")
async def generate_all_monthly_reports(
    req: GenerateAllRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Generate reports for all students with FINALIZED snapshots for a given month.
    Optionally filter by cohort_id (segment_classification).
    Idempotent per student.
    """
    report_month = date(req.year, req.month, 1)

    if req.cohort_id:
        result = await generate_cohort_report(
            cohort_id=req.cohort_id,
            report_month=report_month,
            db=db,
            execution_mode=req.execution_mode,
        )
    else:
        for segment in [
            "NEWCOMERS", "ENGAGEMENT", "CAP_HOPEFULS",
            "LAUNCH_HOPEFULS", "PLACEMENT_HOPEFULS",
        ]:
            await generate_cohort_report(
                cohort_id=segment,
                report_month=report_month,
                db=db,
                execution_mode=req.execution_mode,
            )
        result = {"report_month": str(report_month), "status": "completed_all_segments"}

    return APIResponse.ok(result)
