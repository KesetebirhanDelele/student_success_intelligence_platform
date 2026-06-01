"""
AI insight endpoints — on-demand generation + governance-safe retrieval.

Governance alignment:
  FAD-1  — FINALIZED insights are read-only; immutability classification exposed
  CID-1  — correlation_id propagated in every response meta
  IML-1  — attribution fields surfaced in every insight item
  RSV-1  — is_replay exposed per item so LIVE/REPLAY records are distinguishable
  AP-RT13 — PII excluded from governance meta
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIInsight, StudentTriggerData
from app.routers._router_helpers import (
    build_finalized_protection_fields,
    build_governance_attribution_fields,
    build_request_attribution,
    extract_causation_id,
    extract_correlation_id,
    make_governance_meta,
    replay_visibility_fields,
)
from app.schemas import APIResponse
from app.services.ai_insights import INSIGHT_TYPES, get_or_generate
from app.services._narrative_generation import generate_all_monthly_narratives

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-insights")


def _insight_item(insight: AIInsight) -> dict:
    """
    Serialize one AIInsight to a governance-aware response item.

    Exposes:
      - content fields (id, insight_type, content, model, timestamps)
      - FINALIZED immutability classification (FAD-1)
      - governance attribution lineage (IML-1, CID-1)
      - replay classification (RSV-1)
    Never exposes PII (AP-RT13).
    """
    return {
        "id": insight.id,
        "insight_type": insight.insight_type,
        "content": insight.content_text,
        "model": insight.model_used,
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
        "expires_at": insight.expires_at.isoformat() if insight.expires_at else None,
        # FINALIZED protection (FAD-1) — mutation_permitted=False blocks writes
        **build_finalized_protection_fields(insight),
        # Governance attribution lineage (IML-1, CID-1)
        **build_governance_attribution_fields(insight),
        # Replay classification (RSV-1) — LIVE vs REPLAY distinguishable
        **replay_visibility_fields(insight),
    }


async def _run_narrative_generation() -> None:
    """Background wrapper — owns its own DB session so the HTTP session can close."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await generate_all_monthly_narratives(db)
    logger.info({"event": "narrative_generation_complete", "result": result})


@router.post("/generate-monthly-narratives-all")
async def generate_monthly_narratives_all(
    background_tasks: BackgroundTasks,
) -> APIResponse:
    """
    Generate the 5 monthly narrative types (risk_summary, progress_summary,
    monthly_narrative, intervention_recommendation, sentiment_analysis) for all
    students using the configured LLM.  Runs as a background task — returns
    immediately.  Idempotent: students with all 5 types already finalized are
    skipped (FAD-1).

    After this completes, call POST /reports/snapshots/backfill-narratives to
    copy the new narratives into existing snapshot_ai_narratives rows, then
    POST /reports/monthly/generate-all to refresh report content.
    """
    background_tasks.add_task(_run_narrative_generation)
    return APIResponse.ok({
        "status": "started",
        "message": (
            "Narrative generation running in background. "
            "Watch Docker logs for progress. "
            "When complete, call POST /reports/snapshots/backfill-narratives "
            "then POST /reports/monthly/generate-all for each month."
        ),
    })


@router.get("/{user_id}/{insight_type}")
async def get_insight(
    user_id: int,
    insight_type: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Return a cached insight if one exists and is not expired (24 h TTL).
    Otherwise generate a new one via the configured LLM and cache it.

    Insight types: OUTREACH_DRAFT | INTERVENTION | RISK_EXPLANATION | INTERVIEW_COACHING

    Response meta exposes full governance attribution for lineage tracing.
    FINALIZED insights are returned with mutation_permitted=False and
    lineage_classification=FINALIZED_READ_ONLY (FAD-1).
    """
    insight_type = insight_type.upper()
    if insight_type not in INSIGHT_TYPES:
        return APIResponse.fail(
            "INVALID_TYPE",
            f"Must be one of: {sorted(INSIGHT_TYPES)}",
        )

    correlation_id = extract_correlation_id(dict(request.headers))
    causation_id = extract_causation_id(dict(request.headers))
    attribution = build_request_attribution(correlation_id, causation_id=causation_id)
    meta = make_governance_meta(attribution)

    student_row = await db.get(StudentTriggerData, user_id)
    student = (
        {c.key: getattr(student_row, c.key) for c in student_row.__table__.columns}
        if student_row
        else {"UserID": user_id}
    )

    result = await get_or_generate(user_id, insight_type, student, db)
    return APIResponse.ok(result, meta=meta.as_dict())


@router.get("/{user_id}")
async def all_insights(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Return all stored insights for a student (no generation).

    Each item exposes:
      - FINALIZED immutability classification (FAD-1)
      - Governance attribution lineage (IML-1, CID-1)
      - Replay classification (RSV-1)

    FINALIZED insights have mutation_permitted=False and
    lineage_classification=FINALIZED_READ_ONLY — callers MUST NOT attempt
    to update or replace them via any write endpoint.
    """
    correlation_id = extract_correlation_id(dict(request.headers))
    causation_id = extract_causation_id(dict(request.headers))
    attribution = build_request_attribution(correlation_id, causation_id=causation_id)
    meta = make_governance_meta(attribution)

    result = await db.execute(
        select(AIInsight)
        .where(AIInsight.user_id == user_id)
        .order_by(AIInsight.created_at.desc())
    )
    items = result.scalars().all()

    finalized_count = sum(1 for i in items if getattr(i, "is_finalized", False))

    return APIResponse.ok(
        {
            "user_id": user_id,
            "count": len(items),
            "finalized_count": finalized_count,
            "finalized_protection": "ACTIVE — FINALIZED insights cannot be mutated (FAD-1)",
            "insights": [_insight_item(i) for i in items],
        },
        meta=meta.as_dict(),
    )
