"""
Admin pipeline endpoints — full sync + report generation in two clicks.

  POST /admin/run-pipeline     — sync all students, assemble snapshots, start AI narratives
  POST /admin/finalize-reports — backfill narratives into snapshots, regenerate all reports
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


class RunPipelineRequest(BaseModel):
    year: int
    month: int
    execution_mode: str = "SHADOW"


class FinalizeReportsRequest(BaseModel):
    year: int
    month: int
    execution_mode: str = "SHADOW"


async def _narrative_generation_background() -> None:
    from app.database import AsyncSessionLocal
    from app.services._narrative_generation import generate_all_monthly_narratives
    async with AsyncSessionLocal() as db:
        result = await generate_all_monthly_narratives(db)
    logger.info({"event": "pipeline_narrative_generation_complete", "result": result})


@router.post("/run-pipeline")
async def run_pipeline(
    req: RunPipelineRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Full pipeline — step 1 of 2.

    Runs in order:
      1. Sync JRP students from AI_ChatBot_TriggerData
      2. Sync IPBC students from AI_Chatbot_TriggerData_IPBC
      3. Sync payments
      4. Assemble snapshots for all students for the given month
      5. Start AI narrative generation in the background (one GPT call per student)

    After this returns, watch logs for 'pipeline_narrative_generation_complete'
    then call POST /admin/finalize-reports to backfill + regenerate reports.
    """
    from app.services.sync import sync_from_mssql, sync_ipbc_students
    from app.services.payment_sync import sync_payments
    from app.services.snapshot import assemble_all_active_snapshots

    snapshot_month = date(req.year, req.month, 1)

    # Step 1: JRP students
    jrp = await sync_from_mssql(db)
    logger.info({"event": "pipeline_jrp_sync_done", "rows_scanned": jrp.get("rows_scanned", 0)})

    # Step 2: IPBC students
    ipbc = await sync_ipbc_students(db)
    logger.info({"event": "pipeline_ipbc_sync_done", "rows_scanned": ipbc.get("rows_scanned", 0)})

    # Step 3: Payments
    payments = await sync_payments(db)
    logger.info({"event": "pipeline_payments_sync_done"})

    # Step 4: Assemble snapshots
    snapshots = await assemble_all_active_snapshots(
        snapshot_month=snapshot_month,
        db=db,
        execution_mode=req.execution_mode,
    )
    logger.info({"event": "pipeline_snapshots_done", "result": snapshots})

    # Step 5: Kick off AI narratives in background
    background_tasks.add_task(_narrative_generation_background)

    total_students = (jrp.get("rows_scanned") or 0) + (ipbc.get("rows_scanned") or 0)

    return APIResponse.ok({
        "status": "pipeline_running",
        "students_synced": total_students,
        "jrp_scanned": jrp.get("rows_scanned", 0),
        "ipbc_scanned": ipbc.get("rows_scanned", 0),
        "snapshots": snapshots,
        "ai_narratives": "generating_in_background",
        "next_step": (
            "Watch logs for 'pipeline_narrative_generation_complete' "
            "(~5-10 min), then click Finalize Reports."
        ),
    })


@router.post("/finalize-reports")
async def finalize_reports(
    req: FinalizeReportsRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Full pipeline — step 2 of 2.

    Run only after AI narrative generation has completed (check logs).

    Runs in order:
      1. Backfill finalized AI narratives into snapshot_ai_narratives rows
      2. Generate monthly reports for all students for the given month

    Idempotent: safe to re-run if any step previously failed.
    """
    from sqlalchemy import text
    from app.services.report import generate_cohort_report

    report_month = date(req.year, req.month, 1)

    # Step 1: Backfill narratives
    update_sql = text("""
        UPDATE warehouse.snapshot_ai_narratives san
        SET
            risk_summary_text = COALESCE(san.risk_summary_text,
                (SELECT content_text FROM ai_insights
                 WHERE user_id = ss.student_id AND insight_type = 'risk_summary'
                   AND is_finalized = true ORDER BY created_at DESC LIMIT 1)),
            progress_summary_text = COALESCE(san.progress_summary_text,
                (SELECT content_text FROM ai_insights
                 WHERE user_id = ss.student_id AND insight_type = 'progress_summary'
                   AND is_finalized = true ORDER BY created_at DESC LIMIT 1)),
            monthly_narrative_text = COALESCE(san.monthly_narrative_text,
                (SELECT content_text FROM ai_insights
                 WHERE user_id = ss.student_id AND insight_type = 'monthly_narrative'
                   AND is_finalized = true ORDER BY created_at DESC LIMIT 1)),
            intervention_recommendation_text = COALESCE(san.intervention_recommendation_text,
                (SELECT content_text FROM ai_insights
                 WHERE user_id = ss.student_id AND insight_type = 'intervention_recommendation'
                   AND is_finalized = true ORDER BY created_at DESC LIMIT 1)),
            trend_interpretation_text = COALESCE(san.trend_interpretation_text,
                (SELECT content_text FROM ai_insights
                 WHERE user_id = ss.student_id AND insight_type = 'sentiment_analysis'
                   AND is_finalized = true ORDER BY created_at DESC LIMIT 1))
        FROM warehouse.student_snapshots ss
        WHERE san.snapshot_id = ss.id
          AND (
              san.risk_summary_text IS NULL
           OR san.progress_summary_text IS NULL
           OR san.monthly_narrative_text IS NULL
           OR san.intervention_recommendation_text IS NULL
           OR san.trend_interpretation_text IS NULL
          )
    """)

    count_before = (await db.execute(text(
        "SELECT COUNT(*) FROM warehouse.snapshot_ai_narratives WHERE risk_summary_text IS NULL"
    ))).scalar_one()

    await db.execute(update_sql)
    await db.commit()

    count_after = (await db.execute(text(
        "SELECT COUNT(*) FROM warehouse.snapshot_ai_narratives WHERE risk_summary_text IS NULL"
    ))).scalar_one()

    backfilled = int(count_before - count_after)
    logger.info({"event": "pipeline_backfill_done", "backfilled": backfilled, "still_null": int(count_after)})

    # Step 2: Generate reports for all segments
    report_results = {}
    for segment in ["NEWCOMERS", "ENGAGEMENT", "CAP_HOPEFULS", "LAUNCH_HOPEFULS", "PLACEMENT_HOPEFULS"]:
        result = await generate_cohort_report(
            cohort_id=segment,
            report_month=report_month,
            db=db,
            execution_mode=req.execution_mode,
        )
        report_results[segment] = result
        logger.info({"event": "pipeline_cohort_reports_done", "segment": segment})

    return APIResponse.ok({
        "status": "complete",
        "report_month": str(report_month),
        "narratives_backfilled": backfilled,
        "narratives_still_null": int(count_after),
        "reports": report_results,
    })
