"""
Internal helpers for governance-safe attribution continuity middleware.
Not part of the public API. Consumed only by correlation.py.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.middleware._correlation_types import (
    CODE_ATTRIBUTION_PARTIAL,
    CODE_INVALID_EXECUTION_MODE,
    CODE_INVALID_EXECUTION_TYPE,
    CODE_REPLAY_LINEAGE_INCOMPLETE,
    MODE_MAINTENANCE,
    MODE_SHADOW,
    OUTCOME_BLOCKED,
    OUTCOME_PROPAGATED,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    TYPE_ORIGINAL,
    _REPLAY_EXECUTION_TYPES,
    _REPLAY_MODES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    AttributionContext,
    PropagationRecord,
)

logger = logging.getLogger(__name__)

_ATTRIBUTION_SERVICE = "attribution_middleware"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_correlation_id() -> str:
    return str(uuid.uuid4())


def _make_propagation_id() -> str:
    return str(uuid.uuid4())


def emit_propagation_log(record: PropagationRecord) -> None:
    """
    Emit structured attribution propagation log on every path.
    PII never logged — no email, phone, or student PII (AP-RT13, spec/06 §12.1).
    Observability never suppressed on any path (AP-RT15, AP-FP4).
    """
    is_warn = record.blocked or record.outcome == OUTCOME_BLOCKED
    entry: Dict[str, Any] = {
        "timestamp": record.timestamp,
        "level": "warning" if is_warn else "info",
        "service": _ATTRIBUTION_SERVICE,
        "event": record.event,
        "propagation_id": record.propagation_id,
        "correlation_id": record.correlation_id,
        "causation_id": record.causation_id,
        "config_version_id": record.config_version_id,
        "execution_mode": record.execution_mode,
        "execution_type": record.execution_type,
        "governance_scope": record.governance_scope,
        "orchestration_cycle_id": record.orchestration_cycle_id,
        "origin_source": record.origin_source,
        "origin_authority": record.origin_authority,
        "historical_config_version_id": record.historical_config_version_id,
        "correlation_id_generated": record.correlation_id_generated,
        "is_replay": record.is_replay,
        "attribution_complete": record.attribution_complete,
        "live_effects_suppressed": record.live_effects_suppressed,
        "blocked": record.blocked,
        "blocking_codes": record.blocking_codes,
        "blocking_reason": record.blocking_reason,
        "path": record.path,
        "method": record.method,
        "outcome": record.outcome,
        "duration_ms": record.duration_ms,
        "rule_path_taken": record.rule_path_taken,
        # attribution_timestamp not logged — source-event time (AP-RT13)
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _check_execution_mode(execution_mode: str) -> List[str]:
    if execution_mode not in _VALID_EXECUTION_MODES:
        return [CODE_INVALID_EXECUTION_MODE]
    return []


def _check_execution_type(execution_type: str) -> List[str]:
    if execution_type not in _VALID_EXECUTION_TYPES:
        return [CODE_INVALID_EXECUTION_TYPE]
    return []


def _check_replay_lineage(
    execution_type: str,
    historical_config_version_id: Optional[str],
) -> List[str]:
    """Replay and regeneration types require historical_config_version_id (IML-3)."""
    if execution_type in _REPLAY_EXECUTION_TYPES and not historical_config_version_id:
        return [CODE_REPLAY_LINEAGE_INCOMPLETE]
    return []


def _check_attribution_partial(
    origin_source: Optional[str],
    origin_authority: Optional[str],
) -> List[str]:
    """Partial attribution is blocked — if one is present, both must be (spec/06 §2.2)."""
    if bool(origin_source) != bool(origin_authority):
        return [CODE_ATTRIBUTION_PARTIAL]
    return []


def _governance_precondition_gate(
    execution_mode: Optional[str],
    execution_type: Optional[str],
    historical_config_version_id: Optional[str],
    origin_source: Optional[str],
    origin_authority: Optional[str],
) -> List[str]:
    """
    RULE 0: Validate explicit governance headers.
    Returns list of blocking codes. Empty list = pass.
    No silent continuation permitted.
    """
    codes: List[str] = []
    if execution_mode is not None:
        codes.extend(_check_execution_mode(execution_mode))
    if execution_type is not None:
        type_codes = _check_execution_type(execution_type)
        codes.extend(type_codes)
        if not type_codes:
            codes.extend(_check_replay_lineage(execution_type, historical_config_version_id))
    codes.extend(_check_attribution_partial(origin_source, origin_authority))
    return codes


def _resolve_correlation_id(header_value: Optional[str]) -> Tuple[str, bool]:
    """RULE 1: Restore from header or generate. Returns (correlation_id, was_generated)."""
    if header_value:
        return header_value, False
    return _generate_correlation_id(), True


def _resolve_execution_mode(header_value: Optional[str], settings_mode: str) -> str:
    """RULE 2: Header takes precedence over settings."""
    if header_value and header_value in _VALID_EXECUTION_MODES:
        return header_value
    return settings_mode


def _resolve_execution_type(header_value: Optional[str]) -> str:
    """RULE 3: Header value when valid; default to TYPE_ORIGINAL."""
    if header_value and header_value in _VALID_EXECUTION_TYPES:
        return header_value
    return TYPE_ORIGINAL


def _derive_governance_scope(execution_mode: str, execution_type: str) -> str:
    """
    RULE 4: Derive governance scope.
    SCOPE_AUTHORIZED is unreachable — Phase-12 cert gate enforced here.
    """
    if execution_type in _REPLAY_EXECUTION_TYPES:
        return SCOPE_REPLAY_ONLY
    if execution_mode in _REPLAY_MODES:
        return SCOPE_REPLAY_ONLY
    if execution_mode == MODE_MAINTENANCE:
        return SCOPE_MAINTENANCE
    return SCOPE_SHADOW_ONLY   # LIVE also maps here — Phase-12 cert gate


def _build_attribution_context(
    correlation_id: str,
    causation_id: Optional[str],
    config_version_id: Optional[str],
    execution_mode: str,
    execution_type: str,
    governance_scope: str,
    orchestration_cycle_id: Optional[str],
    origin_source: Optional[str],
    origin_authority: Optional[str],
    historical_config_version_id: Optional[str],
    attribution_timestamp: Optional[str],
    correlation_id_generated: bool,
    rule_path: List[str],
) -> AttributionContext:
    """RULE 5-6: Build AttributionContext for request.state propagation."""
    is_replay = execution_type in _REPLAY_EXECUTION_TYPES
    attribution_complete = bool(origin_source and origin_authority)
    live_effects_suppressed = governance_scope != "AUTHORIZED"  # always True currently
    return AttributionContext(
        correlation_id=correlation_id,
        causation_id=causation_id,
        config_version_id=config_version_id,
        execution_mode=execution_mode,
        execution_type=execution_type,
        governance_scope=governance_scope,
        orchestration_cycle_id=orchestration_cycle_id,
        origin_source=origin_source,
        origin_authority=origin_authority,
        historical_config_version_id=historical_config_version_id,
        attribution_timestamp=attribution_timestamp,
        correlation_id_generated=correlation_id_generated,
        is_replay=is_replay,
        attribution_complete=attribution_complete,
        live_effects_suppressed=live_effects_suppressed,
        rule_path_taken=list(rule_path),
    )


def _make_blocked_context(
    correlation_id: str,
    execution_mode: Optional[str],
    execution_type: Optional[str],
    rule_path: List[str],
) -> AttributionContext:
    """Build minimal AttributionContext for RULE 0 blocked paths."""
    mode = execution_mode if execution_mode in _VALID_EXECUTION_MODES else MODE_SHADOW
    etype = execution_type if execution_type in _VALID_EXECUTION_TYPES else TYPE_ORIGINAL
    scope = _derive_governance_scope(mode, etype)
    return AttributionContext(
        correlation_id=correlation_id,
        causation_id=None,
        config_version_id=None,
        execution_mode=mode,
        execution_type=etype,
        governance_scope=scope,
        orchestration_cycle_id=None,
        origin_source=None,
        origin_authority=None,
        historical_config_version_id=None,
        attribution_timestamp=None,
        correlation_id_generated=False,
        is_replay=etype in _REPLAY_EXECUTION_TYPES,
        attribution_complete=False,
        live_effects_suppressed=True,
        rule_path_taken=list(rule_path),
    )


def _make_propagation_record(
    ctx: AttributionContext,
    event: str,
    path: str,
    method: str,
    blocked: bool,
    blocking_codes: List[str],
    blocking_reason: Optional[str],
    outcome: str,
    duration_ms: Optional[int],
) -> PropagationRecord:
    return PropagationRecord(
        propagation_id=_make_propagation_id(),
        timestamp=_now_iso(),
        event=event,
        correlation_id=ctx.correlation_id,
        causation_id=ctx.causation_id,
        config_version_id=ctx.config_version_id,
        execution_mode=ctx.execution_mode,
        execution_type=ctx.execution_type,
        governance_scope=ctx.governance_scope,
        orchestration_cycle_id=ctx.orchestration_cycle_id,
        origin_source=ctx.origin_source,
        origin_authority=ctx.origin_authority,
        historical_config_version_id=ctx.historical_config_version_id,
        attribution_timestamp=ctx.attribution_timestamp,
        correlation_id_generated=ctx.correlation_id_generated,
        is_replay=ctx.is_replay,
        attribution_complete=ctx.attribution_complete,
        live_effects_suppressed=ctx.live_effects_suppressed,
        blocked=blocked,
        blocking_codes=list(blocking_codes),
        blocking_reason=blocking_reason,
        path=path,
        method=method,
        outcome=outcome,
        duration_ms=duration_ms,
        rule_path_taken=list(ctx.rule_path_taken),
    )
