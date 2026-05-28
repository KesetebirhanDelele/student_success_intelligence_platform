"""
Internal helpers for the governance-safe orchestration scheduler.
Not part of the public API. Consumed only by scheduler.py.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Domain names (imported here to avoid circular import from scheduler)
DOMAIN_ORCHESTRATION_EVALUATION = "orchestration_evaluation"
DOMAIN_PROVIDER_SYNC            = "provider_synchronization"
DOMAIN_OBSERVABILITY_HEARTBEAT  = "observability_heartbeat"

UNKNOWN_V0 = "UNKNOWN_V0"
K_DAILY_TRIGGER_HOUR = "outreach_daily_trigger_hour_cst"
K_RETRY_WINDOW_DAYS  = "outreach_retry_window_days"
K_SYNC_MAX_AGE       = "sql_server_max_sync_age_hours"

_REPLAY_MODES    = frozenset({"REPLAY", "REGENERATION"})
_MODE_MAINTENANCE = "MAINTENANCE"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_config_thresholds(
    rule_set: Dict[str, Any],
    keys: List[str],
    missing_keys: List[str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for k in keys:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def emit_trigger_record(
    *,
    domain: str,
    cycle_id: str,
    execution_mode: str,
    config_version_id: Optional[str],
    idempotency_key: str,
    idempotency_outcome: str,
    trigger_outcome: str,
    degradation_flags: List[str],
    missing_keys: List[str],
    window_start: str,
    window_end: str,
    governance_scope: str,
    reason_codes: List[str],
) -> None:
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if degradation_flags or missing_keys else "info",
        "service": "scheduler",
        "event": "orchestration_trigger",
        "scheduler_domain": domain,
        "cycle_id": cycle_id,
        "triggered_at": _now_iso(),
        "execution_mode": execution_mode,
        "governance_scope": governance_scope,
        "config_version_id": config_version_id,
        "trigger_window_start": window_start,
        "trigger_window_end": window_end,
        "idempotency_key": idempotency_key,
        "idempotency_check_outcome": idempotency_outcome,
        "trigger_outcome": trigger_outcome,
        "degradation_flags": degradation_flags,
        "config_threshold_missing_keys": missing_keys,
        "reason_codes": reason_codes,
    }
    log_fn = logger.warning if degradation_flags or missing_keys else logger.info
    log_fn(json.dumps(entry))


def emit_cycle_completion(
    *,
    cycle_id: str,
    correlation_id: Optional[str],
    execution_mode: str,
    execution_type: str,
    trigger_to_completion_ms: int,
    loop_outcome: str,
    orphan_detected: bool,
    governance_scope: str,
    reason_codes: List[str],
) -> None:
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "info",
        "service": "scheduler",
        "event": "scheduler_cycle_complete",
        "cycle_id": cycle_id,
        "correlation_id": correlation_id,
        "execution_mode": execution_mode,
        "execution_type": execution_type,
        "governance_scope": governance_scope,
        "trigger_to_completion_ms": trigger_to_completion_ms,
        "loop_outcome": loop_outcome,
        "orphan_detected": orphan_detected,
        "reason_codes": reason_codes,
    }
    logger.info(json.dumps(entry))


async def trigger_orchestration_evaluation(
    *,
    execution_mode: str,
    config: Dict[str, Any],
    config_version_id: Optional[str],
    governance_scope: str,
    cycle_id_factory,
    check_idempotency,
    idempotency_key_fn,
    cycle_date: str,
) -> Optional[str]:
    """Emit orchestration evaluation coordination record. Never dispatches outreach."""
    if execution_mode == _MODE_MAINTENANCE:
        logger.info(json.dumps({
            "service": "scheduler", "event": "TRIGGER_SUPPRESSED",
            "scheduler_domain": DOMAIN_ORCHESTRATION_EVALUATION,
            "reason": "MAINTENANCE_MODE", "execution_mode": execution_mode,
        }))
        return None

    missing_keys: List[str] = []
    _resolve_config_thresholds(config, [K_DAILY_TRIGGER_HOUR, K_RETRY_WINDOW_DAYS], missing_keys)

    idem_key = idempotency_key_fn(DOMAIN_ORCHESTRATION_EVALUATION, cycle_date, execution_mode)
    if not check_idempotency(idem_key):
        emit_trigger_record(
            domain=DOMAIN_ORCHESTRATION_EVALUATION,
            cycle_id="DUPLICATE",
            execution_mode=execution_mode,
            config_version_id=config_version_id,
            idempotency_key=idem_key,
            idempotency_outcome="DUPLICATE_SUPPRESSED",
            trigger_outcome="suppressed",
            degradation_flags=[],
            missing_keys=[],
            window_start=cycle_date,
            window_end=cycle_date,
            governance_scope=governance_scope,
            reason_codes=["IDEMPOTENCY_DUPLICATE"],
        )
        return None

    cycle_id = cycle_id_factory()
    degradation_flags = [f"CONFIG_THRESHOLD_MISSING_{k.upper()}" for k in missing_keys]
    emit_trigger_record(
        domain=DOMAIN_ORCHESTRATION_EVALUATION,
        cycle_id=cycle_id,
        execution_mode=execution_mode,
        config_version_id=config_version_id,
        idempotency_key=idem_key,
        idempotency_outcome="NEW_WINDOW",
        trigger_outcome="emitted",
        degradation_flags=degradation_flags,
        missing_keys=missing_keys,
        window_start=cycle_date + "T00:00:00+00:00",
        window_end=cycle_date + "T23:59:59+00:00",
        governance_scope=governance_scope,
        reason_codes=degradation_flags,
    )
    return cycle_id


async def trigger_provider_synchronization(
    *,
    execution_mode: str,
    config: Dict[str, Any],
    config_version_id: Optional[str],
    governance_scope: str,
    cycle_id_factory,
    check_idempotency,
    idempotency_key_fn,
    cycle_date: str,
) -> Optional[str]:
    """Emit provider sync coordination record. Never reads or writes provider APIs."""
    if execution_mode in _REPLAY_MODES:
        logger.info(json.dumps({
            "service": "scheduler", "event": "TRIGGER_SUPPRESSED",
            "scheduler_domain": DOMAIN_PROVIDER_SYNC,
            "reason": "REPLAY_EXECUTION", "execution_mode": execution_mode,
        }))
        return None
    if execution_mode == _MODE_MAINTENANCE:
        logger.info(json.dumps({
            "service": "scheduler", "event": "TRIGGER_SUPPRESSED",
            "scheduler_domain": DOMAIN_PROVIDER_SYNC,
            "reason": "MAINTENANCE_MODE", "execution_mode": execution_mode,
        }))
        return None

    missing_keys: List[str] = []
    _resolve_config_thresholds(config, [K_SYNC_MAX_AGE], missing_keys)

    idem_key = idempotency_key_fn(DOMAIN_PROVIDER_SYNC, cycle_date, execution_mode)
    if not check_idempotency(idem_key):
        return None

    cycle_id = cycle_id_factory()
    degradation_flags = [f"CONFIG_THRESHOLD_MISSING_{k.upper()}" for k in missing_keys]
    emit_trigger_record(
        domain=DOMAIN_PROVIDER_SYNC,
        cycle_id=cycle_id,
        execution_mode=execution_mode,
        config_version_id=config_version_id,
        idempotency_key=idem_key,
        idempotency_outcome="NEW_WINDOW",
        trigger_outcome="emitted",
        degradation_flags=degradation_flags,
        missing_keys=missing_keys,
        window_start=cycle_date + "T00:00:00+00:00",
        window_end=cycle_date + "T23:59:59+00:00",
        governance_scope=governance_scope,
        reason_codes=degradation_flags,
    )
    return cycle_id


async def trigger_observability_heartbeat(
    *,
    execution_mode: str,
    config_version_id: Optional[str],
    governance_scope: str,
    cycle_id_factory,
    scheduler_running: bool,
) -> Optional[str]:
    """Emit heartbeat record for liveness observability. Always fires (no suppression)."""
    cycle_id = cycle_id_factory()
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "info",
        "service": "scheduler",
        "event": "observability_heartbeat",
        "cycle_id": cycle_id,
        "execution_mode": execution_mode,
        "governance_scope": governance_scope,
        "config_version_id": config_version_id,
        "scheduler_running": scheduler_running,
    }
    logger.info(json.dumps(entry))
    return cycle_id
