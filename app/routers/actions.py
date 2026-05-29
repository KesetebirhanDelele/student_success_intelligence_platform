"""
Manual action endpoint — governance-safe operator override dispatch.

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
from app.schemas import APIResponse, ManualActionRequest
from app.services.outreach import execute_manual_action

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/actions/manual")
async def manual_action(
    body: ManualActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """
    Execute a manual operator action on a student outreach record.

    Governance meta is included in every response (success and error paths)
    for correlation tracing (CID-1).
    """
    correlation_id = extract_correlation_id(dict(request.headers))
    causation_id = extract_causation_id(dict(request.headers))
    attribution = build_request_attribution(correlation_id, causation_id=causation_id)
    meta = make_governance_meta(attribution)

    result = await execute_manual_action(db, body.user_id, body.action_type, body.notes)

    if result.get("status") == "not_found":
        return APIResponse.fail(
            "NOT_FOUND",
            f"No outreach record for student {body.user_id}",
            meta=meta.as_dict(),
        )
    if result.get("status") == "invalid_transition":
        return APIResponse.fail(
            "INVALID_TRANSITION",
            f"Cannot transition {result['from']} → {result['to']}",
            meta=meta.as_dict(),
        )
    if result.get("status") == "invalid_action":
        return APIResponse.fail(
            "INVALID_ACTION",
            f"Unknown action: {body.action_type}",
            meta=meta.as_dict(),
        )
    if result.get("status") == "max_attempts_reached":
        return APIResponse.fail(
            "MAX_ATTEMPTS_REACHED",
            f"Cannot retry: student has reached the maximum of {result['max']} attempts "
            f"(current: {result['current_attempt']}).",
            meta=meta.as_dict(),
        )

    return APIResponse.ok(result, meta=meta.as_dict())
