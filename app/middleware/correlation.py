"""
Governance-safe attribution continuity middleware.

Public API: AttributionMiddleware (Starlette BaseHTTPMiddleware)
Propagated to: request.state.attribution (AttributionContext)

Governance prohibitions (spec/06 §3, runtime/system_loop.md §11, data/data_lifecycle.md §3):
  - NEVER silently regenerates attribution (RULE 0 blocks contradictory signals)
  - NEVER loses causation lineage (causation_id always propagated from header)
  - NEVER mutates immutable replay lineage (replay contexts carry REPLAY_ONLY scope)
  - NEVER bypasses governance context propagation (all paths emit observability)
  - NEVER logs PII (AP-RT13, spec/06 §12.1)
  - NEVER produces LIVE effects from replay requests (AP-RT2)
  - NEVER allows SCOPE_AUTHORIZED (Phase-12 cert gate — unreachable)

RULE 0  Governance precondition gate (validate explicit attribution headers)
RULE 1  Correlation ID resolution (generate if absent, restore if present)
RULE 2  Execution mode resolution (header → settings → MODE_SHADOW default)
RULE 3  Execution type resolution (header → TYPE_ORIGINAL default)
RULE 4  Governance scope derivation (type + mode → scope)
RULE 5  Attribution completeness assessment (origin_source + origin_authority pair)
RULE 6  Build AttributionContext, propagate to request.state
RULE 7  Emit api_request_received observability log
RULE 8  Handle request (call_next)
RULE 9  Set response attribution headers, emit api_response_dispatched observability
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import settings
from app.middleware._correlation_helpers import (
    _build_attribution_context,
    _derive_governance_scope,
    _generate_correlation_id,
    _governance_precondition_gate,
    _make_blocked_context,
    _make_propagation_record,
    _resolve_correlation_id,
    _resolve_execution_mode,
    _resolve_execution_type,
    emit_propagation_log,
)
from app.middleware._correlation_types import (
    HEADER_ATTRIBUTION_TIMESTAMP,
    HEADER_CAUSATION_ID,
    HEADER_CONFIG_VERSION_ID,
    HEADER_CORRELATION_ID,
    HEADER_EXECUTION_MODE,
    HEADER_EXECUTION_TYPE,
    HEADER_GOVERNANCE_SCOPE,
    HEADER_HISTORICAL_CONFIG_VERSION_ID,
    HEADER_ORCHESTRATION_CYCLE_ID,
    HEADER_ORIGIN_AUTHORITY,
    HEADER_ORIGIN_SOURCE,
    OUTCOME_BLOCKED,
    OUTCOME_PROPAGATED,
)


class AttributionMiddleware(BaseHTTPMiddleware):
    """
    Attribution continuity middleware.

    Propagates governance-safe attribution context to every request.
    Emits structured observability on every path (AP-RT15).
    Blocks requests with contradictory attribution signals (RULE 0 gate).
    Never silently continues without proper attribution lineage.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        t0 = time.monotonic()
        rule_path = []

        # Extract explicit attribution headers (Starlette headers are case-insensitive)
        execution_mode_header: Optional[str] = request.headers.get(HEADER_EXECUTION_MODE)
        execution_type_header: Optional[str] = request.headers.get(HEADER_EXECUTION_TYPE)
        historical_config_version_id: Optional[str] = request.headers.get(
            HEADER_HISTORICAL_CONFIG_VERSION_ID
        )
        origin_source: Optional[str] = request.headers.get(HEADER_ORIGIN_SOURCE)
        origin_authority: Optional[str] = request.headers.get(HEADER_ORIGIN_AUTHORITY)

        # RULE 0: Governance precondition gate
        rule_path.append("RULE_0_GOVERNANCE_GATE")
        blocking_codes = _governance_precondition_gate(
            execution_mode=execution_mode_header,
            execution_type=execution_type_header,
            historical_config_version_id=historical_config_version_id,
            origin_source=origin_source,
            origin_authority=origin_authority,
        )

        if blocking_codes:
            correlation_id = (
                request.headers.get(HEADER_CORRELATION_ID) or _generate_correlation_id()
            )
            blocking_reason = "; ".join(blocking_codes)
            blocked_ctx = _make_blocked_context(
                correlation_id=correlation_id,
                execution_mode=execution_mode_header,
                execution_type=execution_type_header,
                rule_path=rule_path,
            )
            elapsed = int((time.monotonic() - t0) * 1000)
            record = _make_propagation_record(
                ctx=blocked_ctx,
                event="attribution_blocked",
                path=request.url.path,
                method=request.method,
                blocked=True,
                blocking_codes=blocking_codes,
                blocking_reason=blocking_reason,
                outcome=OUTCOME_BLOCKED,
                duration_ms=elapsed,
            )
            emit_propagation_log(record)
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "data": None,
                    "error": {
                        "code": "ATTRIBUTION_GOVERNANCE_GATE_FAILED",
                        "message": "Attribution governance precondition failed",
                        "blocking_codes": blocking_codes,
                    },
                },
                headers={HEADER_CORRELATION_ID: correlation_id},
            )

        # RULE 1: Correlation ID resolution
        rule_path.append("RULE_1_CORRELATION_ID")
        correlation_id, correlation_id_generated = _resolve_correlation_id(
            request.headers.get(HEADER_CORRELATION_ID)
        )

        # RULE 2: Execution mode resolution (header → settings → MODE_SHADOW default)
        rule_path.append("RULE_2_EXECUTION_MODE")
        execution_mode = _resolve_execution_mode(
            header_value=execution_mode_header,
            settings_mode=settings.EXECUTION_MODE.value,
        )

        # RULE 3: Execution type resolution (header → TYPE_ORIGINAL default)
        rule_path.append("RULE_3_EXECUTION_TYPE")
        execution_type = _resolve_execution_type(execution_type_header)

        # RULE 4: Governance scope derivation
        rule_path.append("RULE_4_GOVERNANCE_SCOPE")
        governance_scope = _derive_governance_scope(execution_mode, execution_type)

        # RULE 5: Attribution completeness assessment (no blocking — absence is permitted)
        rule_path.append("RULE_5_ATTRIBUTION_COMPLETENESS")

        # RULE 6: Build AttributionContext, propagate to request.state
        rule_path.append("RULE_6_CONTEXT_BUILD")
        ctx = _build_attribution_context(
            correlation_id=correlation_id,
            causation_id=request.headers.get(HEADER_CAUSATION_ID),
            config_version_id=request.headers.get(HEADER_CONFIG_VERSION_ID),
            execution_mode=execution_mode,
            execution_type=execution_type,
            governance_scope=governance_scope,
            orchestration_cycle_id=request.headers.get(HEADER_ORCHESTRATION_CYCLE_ID),
            origin_source=origin_source,
            origin_authority=origin_authority,
            historical_config_version_id=historical_config_version_id,
            attribution_timestamp=request.headers.get(HEADER_ATTRIBUTION_TIMESTAMP),
            correlation_id_generated=correlation_id_generated,
            rule_path=rule_path,
        )
        request.state.attribution = ctx

        # RULE 7: Emit api_request_received observability log
        rule_path.append("RULE_7_REQUEST_OBSERVABILITY")
        request_record = _make_propagation_record(
            ctx=ctx,
            event="api_request_received",
            path=request.url.path,
            method=request.method,
            blocked=False,
            blocking_codes=[],
            blocking_reason=None,
            outcome=OUTCOME_PROPAGATED,
            duration_ms=None,
        )
        emit_propagation_log(request_record)

        # RULE 8: Handle request
        rule_path.append("RULE_8_REQUEST_DISPATCH")
        response = await call_next(request)

        elapsed = int((time.monotonic() - t0) * 1000)

        # RULE 9: Set response attribution headers, emit api_response_dispatched observability
        rule_path.append("RULE_9_RESPONSE_ATTRIBUTION")
        response.headers[HEADER_CORRELATION_ID] = correlation_id
        response.headers[HEADER_EXECUTION_MODE] = execution_mode
        response.headers[HEADER_GOVERNANCE_SCOPE] = governance_scope
        if ctx.causation_id:
            response.headers[HEADER_CAUSATION_ID] = ctx.causation_id

        response_record = _make_propagation_record(
            ctx=ctx,
            event="api_response_dispatched",
            path=request.url.path,
            method=request.method,
            blocked=False,
            blocking_codes=[],
            blocking_reason=None,
            outcome=OUTCOME_PROPAGATED,
            duration_ms=elapsed,
        )
        emit_propagation_log(response_record)

        return response
