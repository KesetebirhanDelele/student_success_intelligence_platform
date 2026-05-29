"""
Outreach trigger endpoint — governance-safe batch execution dispatch.

Governance alignment:
  CID-1  — correlation_id extracted from X-Correlation-ID header or generated
  IML-1  — attribution propagated into response meta
  AP-RT13 — PII excluded from response meta
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers._router_helpers import (
    build_request_attribution,
    extract_causation_id,
    extract_correlation_id,
    make_governance_meta,
)
from app.schemas import APIResponse, TriggerOutreachRequest
from app.services.outreach import run_outreach_batch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/outreach/trigger")
async def trigger_outreach(
    body: TriggerOutreachRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Trigger a batch outreach run for a checkpoint type.

    Governance meta is included in the response for correlation tracing.
    Live effects are suppressed when EXECUTION_MODE=SHADOW (visible via
    suppression_codes in meta).
    """
    correlation_id = extract_correlation_id(dict(request.headers))
    causation_id = extract_causation_id(dict(request.headers))
    attribution = build_request_attribution(correlation_id, causation_id=causation_id)
    meta = make_governance_meta(attribution)

    summary = await run_outreach_batch(db, body.checkpoint_type)
    return APIResponse.ok({"summary": summary}, meta=meta.as_dict())
