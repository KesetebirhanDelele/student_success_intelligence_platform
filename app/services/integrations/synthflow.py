"""
Governance-safe Synthflow call transport wrapper.

Routes outbound AI phone calls via Synthflow API under governance containment.
All governance scope is pre-established by the calling orchestration service
via ProviderOrchestrationAssessment from assess_provider_orchestration().

SHADOW_ONLY       : simulate, no live call placed (AP-GHL11).
REPLAY_ONLY       : simulate, no live call placed (AP-GHL5).
BLOCKED/UNAVAILABLE: dispatch refused, no call.
AUTHORIZED        : actual Synthflow API call — requires Phase-12 cert.

Architecture preservation:
  AP-GHL5  — never dispatch during replay or regeneration
  AP-GHL8  — never silently substitute on provider unavailable
  AP-GHL10 — never log raw student PII (phone number, name)
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
    SCOPE_BLOCKED,
    SCOPE_DUPLICATE_SUPPRESSED,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    ProviderOrchestrationAssessment,
)

logger = logging.getLogger(__name__)

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


def build_call_payload(student: dict, attempt: int) -> dict:
    """
    Construct Synthflow call dispatch payload.
    Pure function — no side effects, no governance validation.
    Governance is applied at execute_call_dispatch().
    PII included for Synthflow delivery only; never logged (AP-GHL10).
    """
    return {
        "to": student.get("PhoneNumber"),
        "from": settings.SYNTHFLOW_PHONE_NUMBER,
        "metadata": {
            "user_id": student.get("UserID"),
            "attempt": attempt,
            "checkpoint": student.get("PathName"),
            "hws_behind": student.get("HWsBehind"),
            "avg_eff_rating": student.get("AvgEffRating"),
        },
    }


def execute_call_dispatch(
    assessment: ProviderOrchestrationAssessment,
    payload: dict,
) -> dict:
    """
    Execute Synthflow call dispatch under governance containment.

    Validates assessment before any outbound action. All non-AUTHORIZED
    governance scopes return a structured simulation result — no call placed.
    AUTHORIZED scope requires Phase-12 cert (currently unreachable — AP-GHL11).

    Returns governance-safe dispatch result dict. Never logs PII (AP-GHL10).
    """
    scope = assessment.governance_scope

    if scope in _SUPPRESSED_SCOPES or assessment.outbound_suppressed or assessment.provider_blocked:
        outcome = _SCOPE_OUTCOME_MAP.get(scope, "shadow_only")
        result = _make_call_result(assessment, outcome, None, None)
        _emit_call_log(assessment, outcome, None)
        return result

    # AUTHORIZED — Phase-12 cert required (currently unreachable, AP-GHL11)
    logger.warning(json.dumps({
        "timestamp": _now_iso(),
        "level": "warning",
        "service": "synthflow_transport",
        "event": "live_dispatch_phase12_gate",
        "governance_scope": scope,
        "correlation_id": assessment.correlation_id,
        "execution_mode": assessment.execution_mode,
        "reason_codes": ["LIVE_SCOPE_REQUIRES_PHASE12_CERT"],
    }))
    result = _make_call_result(assessment, "shadow_only", None, None)
    result["reason_codes"] = list(assessment.reason_codes) + ["LIVE_SCOPE_REQUIRES_PHASE12_CERT"]
    return result


async def _live_synthflow_dispatch(
    payload: dict,
    assessment: ProviderOrchestrationAssessment,
) -> dict:
    """
    Live Synthflow API call — only reachable after Phase-12 certification.
    Currently never called (AP-GHL11). Defined here for Phase-12 activation.
    """
    user_id = payload.get("metadata", {}).get("user_id")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                "https://api.synthflow.ai/v1/calls",
                headers={
                    "Authorization": f"Bearer {settings.SYNTHFLOW_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return _make_call_result(
                assessment, "success", r.status_code,
                call_id=data.get("callId"),
            )
        except httpx.HTTPError as exc:
            logger.error(json.dumps({
                "timestamp": _now_iso(),
                "level": "error",
                "service": "synthflow_transport",
                "event": "synthflow_live_dispatch_error",
                "correlation_id": assessment.correlation_id,
                "student_id_opaque": str(user_id) if user_id else None,
                "error_class": type(exc).__name__,
            }))
            raise


def _make_call_result(
    assessment: ProviderOrchestrationAssessment,
    outcome: str,
    provider_response_code: Optional[int],
    call_id: Optional[str],
) -> dict:
    return {
        "governance_scope": assessment.governance_scope,
        "provider_event_type": assessment.provider_event_type,
        "outbound_suppressed": assessment.outbound_suppressed,
        "correlation_id": assessment.correlation_id,
        "causation_id": assessment.causation_id,
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
        "channel": "call",
        "outcome": outcome,
        "reason_codes": list(assessment.reason_codes),
        "provider_response_code": provider_response_code,
        "call_id": call_id,
    }


def _emit_call_log(
    assessment: ProviderOrchestrationAssessment,
    outcome: str,
    provider_response_code: Optional[int],
) -> None:
    """Structured call dispatch log — PII never logged (AP-GHL10)."""
    is_warn = assessment.degraded or assessment.provider_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": "synthflow_transport",
        "event": "call_dispatch_result",
        "channel": "call",
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
