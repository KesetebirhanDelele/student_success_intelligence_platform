"""
Governance-safe GHL transport wrapper.

Transport boundary only — never makes governance decisions.
Governance scope is pre-established by the calling orchestration service
via ProviderOrchestrationAssessment from assess_provider_orchestration().

SHADOW_ONLY       : simulate, no live HTTP call (AP-GHL11).
REPLAY_ONLY       : simulate from historical, no live HTTP call (AP-GHL5).
BLOCKED           : dispatch refused, no HTTP call.
UNAVAILABLE       : dispatch deferred, no HTTP call.
DUPLICATE_SUPPRESSED : prior result served, no HTTP call.
AUTHORIZED        : actual GHL API call — requires Phase-12 cert (currently unreachable).

Architecture preservation:
  AP-GHL5  — never dispatch during replay or regeneration
  AP-GHL8  — never silently substitute on provider unavailable
  AP-GHL10 — never log raw student PII
  AP-GHL11 — never emit LIVE scope without Phase-12 cert
  AP-GHL15 — never mutate attribution from input assessment
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.services._ghl_types import (
    SCOPE_AUTHORIZED,
    SCOPE_BLOCKED,
    SCOPE_DUPLICATE_SUPPRESSED,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    ProviderOrchestrationAssessment,
)

logger = logging.getLogger(__name__)

# All scopes where no live HTTP dispatch is permitted
_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY,
    SCOPE_REPLAY_ONLY,
    SCOPE_BLOCKED,
    SCOPE_UNAVAILABLE,
    SCOPE_DUPLICATE_SUPPRESSED,
})

_SCOPE_OUTCOME_MAP = {
    SCOPE_SHADOW_ONLY: "shadow_only",
    SCOPE_REPLAY_ONLY: "suppressed_replay",
    SCOPE_BLOCKED: "blocked",
    SCOPE_UNAVAILABLE: "unavailable",
    SCOPE_DUPLICATE_SUPPRESSED: "duplicate_suppressed",
}


def build_ghl_payload(student: dict, channel: str, attempt: int) -> dict:
    """
    Construct GHL workflow trigger payload.
    Pure function — no side effects, no governance validation.
    Governance is applied at execute_ghl_dispatch().
    PII is included in the payload for GHL delivery only; never logged (AP-GHL10).
    """
    return {
        "locationId": settings.GHL_LOCATION_ID,
        "user": {
            "id": student.get("UserID"),
            "email": student.get("Email"),
            "phone": student.get("PhoneNumber"),
        },
        "workflow": {
            "channel": channel,
            "attempt": attempt,
            "checkpoint": student.get("PathName"),
        },
        "risk": {
            "hwsBehind": student.get("HWsBehind"),
            "avgEffRating": student.get("AvgEffRating"),
            "lastActivityDays": student.get("LastActivityDays"),
        },
    }


def execute_ghl_dispatch(
    assessment: ProviderOrchestrationAssessment,
    payload: dict,
) -> dict:
    """
    Execute GHL dispatch under governance containment.

    Validates assessment before any outbound action. All non-AUTHORIZED
    governance scopes return a structured simulation result — no HTTP call made.
    AUTHORIZED scope requires Phase-12 cert (currently unreachable — AP-GHL11).

    Returns a governance-safe dispatch result dict with:
      governance_scope, provider_event_type, outbound_suppressed,
      correlation_id, execution_mode, execution_type, outcome, reason_codes.
    Never logs PII from payload (AP-GHL10).
    """
    scope = assessment.governance_scope

    if scope in _SUPPRESSED_SCOPES or assessment.outbound_suppressed or assessment.provider_blocked:
        outcome = _SCOPE_OUTCOME_MAP.get(scope, "shadow_only")
        result = _make_dispatch_result(assessment, outcome, None)
        _emit_dispatch_log(assessment, outcome, None)
        return result

    # AUTHORIZED scope — Phase-12 cert required (currently unreachable, AP-GHL11).
    # When Phase-12 cert is granted, this becomes the live dispatch path.
    logger.warning(json.dumps({
        "timestamp": _now_iso(),
        "level": "warning",
        "service": "ghl_transport",
        "event": "live_dispatch_phase12_gate",
        "governance_scope": scope,
        "correlation_id": assessment.correlation_id,
        "execution_mode": assessment.execution_mode,
        "reason_codes": ["LIVE_SCOPE_REQUIRES_PHASE12_CERT"],
    }))
    result = _make_dispatch_result(assessment, "shadow_only", None)
    result["reason_codes"] = list(assessment.reason_codes) + ["LIVE_SCOPE_REQUIRES_PHASE12_CERT"]
    return result


async def _live_ghl_dispatch(
    payload: dict,
    assessment: ProviderOrchestrationAssessment,
) -> dict:
    """
    Live GHL API call — only reachable after Phase-12 certification.
    Currently never called (AP-GHL11). Defined here for Phase-12 activation.
    """
    user_id = payload.get("user", {}).get("id")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                f"{settings.GHL_BASE_URL}/v1/workflows/trigger",
                headers={
                    "Authorization": f"Bearer {settings.GHL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return _make_dispatch_result(
                assessment, "success", r.status_code,
                ghl_workflow_id=data.get("workflowId"),
            )
        except httpx.HTTPError as exc:
            logger.error(json.dumps({
                "timestamp": _now_iso(),
                "level": "error",
                "service": "ghl_transport",
                "event": "ghl_live_dispatch_error",
                "correlation_id": assessment.correlation_id,
                "student_id_opaque": str(user_id) if user_id else None,
                "error_class": type(exc).__name__,
            }))
            raise


def _make_dispatch_result(
    assessment: ProviderOrchestrationAssessment,
    outcome: str,
    provider_response_code: Optional[int],
    ghl_workflow_id: Optional[str] = None,
) -> dict:
    return {
        "governance_scope": assessment.governance_scope,
        "provider_event_type": assessment.provider_event_type,
        "outbound_suppressed": assessment.outbound_suppressed,
        "correlation_id": assessment.correlation_id,
        "causation_id": assessment.causation_id,
        "upstream_intent_id": assessment.upstream_intent_id,
        "origin_source": assessment.origin_source,
        "origin_authority": assessment.origin_authority,
        "execution_mode": assessment.execution_mode,
        "execution_type": assessment.execution_type,
        "is_replay": assessment.is_replay,
        "config_version_id": assessment.config_version_id,
        "degraded": assessment.degraded,
        "degradation_cause": assessment.degradation_cause,
        "provider_blocked": assessment.provider_blocked,
        "blocking_reason": assessment.blocking_reason,
        "outcome": outcome,
        "reason_codes": list(assessment.reason_codes),
        "ghl_workflow_id": ghl_workflow_id,
        "provider_response_code": provider_response_code,
    }


def _emit_dispatch_log(
    assessment: ProviderOrchestrationAssessment,
    outcome: str,
    provider_response_code: Optional[int],
) -> None:
    """Structured dispatch log — PII never logged (AP-GHL10)."""
    is_warn = assessment.degraded or assessment.provider_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": "ghl_transport",
        "event": "ghl_dispatch_result",
        "governance_scope": assessment.governance_scope,
        "provider_event_type": assessment.provider_event_type,
        "outbound_suppressed": assessment.outbound_suppressed,
        "correlation_id": assessment.correlation_id,
        "origin_source": assessment.origin_source,
        "origin_authority": assessment.origin_authority,
        "execution_mode": assessment.execution_mode,
        "execution_type": assessment.execution_type,
        "is_replay": assessment.is_replay,
        "config_version_id": assessment.config_version_id,
        "provider_blocked": assessment.provider_blocked,
        "degraded": assessment.degraded,
        "degradation_cause": assessment.degradation_cause,
        "outcome": outcome,
        "reason_codes": assessment.reason_codes,
        "provider_response_code": provider_response_code,
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
