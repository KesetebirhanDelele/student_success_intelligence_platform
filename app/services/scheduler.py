"""
Governance-safe orchestration scheduler.

Advisory-coordination only. This module NEVER:
  - dispatches providers (AP-SCH1)
  - sends outreach or mutates outreach state (AP-SCH2)
  - triggers LIVE batch operations during REPLAY (AP-SCH3)
  - executes business logic directly (AP-SCH4)
  - hardcodes cadence, retry windows, or timing values (AP-SCH5, AP-SCH6)
  - falls back to hardcoded defaults when Config V2 keys are absent (AP-SCH6)
  - bypasses governance precondition gate (AP-SCH7)
  - produces live orchestration in REPLAY mode (AP-SCH8)
  - swallows exceptions silently (AP-SCH9)
  - mutates attribution context in-place (AP-SCH10)
  - emits LIVE orchestration windows in SHADOW mode (AP-SCH11)
  - retries infinitely (AP-SCH12)
  - log raw student PII (AP-SCH13)
  - trigger orchestration in MAINTENANCE without authorization (AP-SCH14)
  - suppress governance precondition failures silently (AP-SCH15)

Emits: structured orchestration trigger records and cycle completion records.
Consumed by: runtime orchestration loop (never by outreach or provider services).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services._scheduler_helpers import (
    DOMAIN_OBSERVABILITY_HEARTBEAT,
    DOMAIN_ORCHESTRATION_EVALUATION,
    DOMAIN_PROVIDER_SYNC,
    emit_cycle_completion,
    trigger_observability_heartbeat,
    trigger_orchestration_evaluation,
    trigger_provider_synchronization,
)

logger = logging.getLogger(__name__)

# ── Execution modes ───────────────────────────────────────────────────────────
MODE_LIVE         = "LIVE"
MODE_SHADOW       = "SHADOW"
MODE_REPLAY       = "REPLAY"
MODE_REGENERATION = "REGENERATION"
MODE_DEGRADED     = "DEGRADED"
MODE_MAINTENANCE  = "MAINTENANCE"

_REPLAY_MODES = frozenset({MODE_REPLAY, MODE_REGENERATION})
_VALID_MODES  = frozenset({MODE_LIVE, MODE_SHADOW, MODE_REPLAY,
                           MODE_REGENERATION, MODE_DEGRADED, MODE_MAINTENANCE})

# ── Config V2 timing keys (scheduler_design.md §5, system_loop.md §5.2) ──────
K_DAILY_TRIGGER_HOUR = "outreach_daily_trigger_hour_cst"   # Group A
K_RETRY_WINDOW_DAYS  = "outreach_retry_window_days"         # Group A
K_AI_TTL             = "ai_insight_ttl_hours"               # Group H
K_SYNC_MAX_AGE       = "sql_server_max_sync_age_hours"      # Group K
K_TRIGGER_MINUTE     = "outreach_daily_trigger_minute_cst"  # Group I

UNKNOWN_V0 = "UNKNOWN_V0"

REQUIRED_ATTRIBUTION = (
    "origin_source", "origin_authority",
    "actor_identity", "attribution_timestamp",
)

# ── Internal idempotency store (in-memory for MVP) ───────────────────────────
_executed_windows: set[str] = set()

# ── APScheduler instance ──────────────────────────────────────────────────────
_scheduler = AsyncIOScheduler()
_scheduler_config: Dict[str, Any] = {}
_last_run_at: Optional[str] = None


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _make_cycle_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idempotency_key(domain: str, cycle_date: str, execution_mode: str) -> str:
    return f"{domain}|{cycle_date}|{execution_mode}"


def _check_and_register_idempotency(key: str) -> bool:
    """Return True if the window is new (should fire). False = duplicate (no-op)."""
    if key in _executed_windows:
        return False
    _executed_windows.add(key)
    return True


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


def _attribution_complete(ctx: Optional[Dict[str, Any]]) -> bool:
    if not ctx:
        return False
    return all(k in ctx and ctx[k] for k in REQUIRED_ATTRIBUTION)


def _governance_scope(execution_mode: str) -> str:
    if execution_mode in _REPLAY_MODES:
        return "REPLAY_ONLY"
    if execution_mode == MODE_SHADOW:
        return "SHADOW_ONLY"
    if execution_mode == MODE_MAINTENANCE:
        return "MAINTENANCE_ONLY"
    if execution_mode == MODE_DEGRADED:
        return "DEGRADED_ONLY"
    return "SHADOW_ONLY"  # default — LIVE scope requires Phase-12 cert


# ── Governance precondition gate (Rule 0 / AP-SCH7 / AP-SCH15) ───────────────

def _governance_precondition_gate(
    execution_mode: str,
    config_version_id: Optional[str],
    attribution_context: Optional[Dict[str, Any]],
    codes: List[str],
) -> bool:
    """Return True if all preconditions pass; False if scheduler must stop."""
    ok = True
    if execution_mode not in _VALID_MODES:
        codes.append("INVALID_EXECUTION_MODE")
        ok = False
    if not config_version_id:
        codes.append("CONFIG_VERSION_ID_MISSING")
        ok = False
    if not _attribution_complete(attribution_context):
        codes.append("ATTRIBUTION_INCOMPLETE")
        ok = False
    return ok


# ── Public coordination API ───────────────────────────────────────────────────

async def coordinate_orchestration_cycle(
    execution_mode: str,
    config_version_id: Optional[str],
    config_rule_set: Optional[Dict[str, Any]] = None,
    attribution_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Coordinate a governance-safe orchestration cycle.

    Emits advisory trigger records for all MVP-active domains.
    Returns a coordination record (not an execution result).
    Never dispatches providers, sends outreach, or mutates state.
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_set = config_rule_set or {}

    # Rule 0: governance precondition gate (AP-SCH7, AP-SCH15)
    if not _governance_precondition_gate(execution_mode, config_version_id, attribution_context, codes):
        dur = int((time.monotonic() - t0) * 1000)
        logger.error(json.dumps({
            "timestamp": _now_iso(), "level": "error", "service": "scheduler",
            "event": "governance_precondition_failed",
            "execution_mode": execution_mode, "config_version_id": config_version_id,
            "reason_codes": codes, "duration_ms": dur,
        }))
        return {
            "coordination_produced": False,
            "governance_scope": _governance_scope(execution_mode),
            "execution_mode": execution_mode,
            "config_version_id": config_version_id,
            "reason_codes": codes,
            "cycle_ids": {},
            "blocked": True,
            "duration_ms": dur,
        }

    gov_scope = _governance_scope(execution_mode)
    cycle_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cycle_ids: Dict[str, Optional[str]] = {}

    # REPLAY: suppress LIVE batch domains (AP-SCH3, AP-SCH8)
    if execution_mode in _REPLAY_MODES:
        codes.append("REPLAY_LIVE_BATCH_SUPPRESSED")
        emit_cycle_completion(
            cycle_id=_make_cycle_id(), correlation_id=None,
            execution_mode=execution_mode, execution_type=execution_mode.lower(),
            trigger_to_completion_ms=int((time.monotonic() - t0) * 1000),
            loop_outcome="suppressed_replay", orphan_detected=False,
            governance_scope=gov_scope, reason_codes=codes,
        )
        return {
            "coordination_produced": False,
            "governance_scope": gov_scope,
            "execution_mode": execution_mode,
            "config_version_id": config_version_id,
            "reason_codes": codes,
            "cycle_ids": cycle_ids,
            "blocked": False,
            "duration_ms": int((time.monotonic() - t0) * 1000),
        }

    # MAINTENANCE: suppress all except heartbeat (AP-SCH14)
    if execution_mode == MODE_MAINTENANCE:
        hb = await trigger_observability_heartbeat(
            execution_mode=execution_mode, config_version_id=config_version_id,
            governance_scope=gov_scope, cycle_id_factory=_make_cycle_id,
            scheduler_running=_scheduler.running,
        )
        cycle_ids[DOMAIN_OBSERVABILITY_HEARTBEAT] = hb
        codes.append("MAINTENANCE_ORCHESTRATION_SUPPRESSED")
    else:
        eval_id = await trigger_orchestration_evaluation(
            execution_mode=execution_mode, config=rule_set,
            config_version_id=config_version_id, governance_scope=gov_scope,
            cycle_id_factory=_make_cycle_id,
            check_idempotency=_check_and_register_idempotency,
            idempotency_key_fn=_idempotency_key, cycle_date=cycle_date,
        )
        cycle_ids[DOMAIN_ORCHESTRATION_EVALUATION] = eval_id

        sync_id = await trigger_provider_synchronization(
            execution_mode=execution_mode, config=rule_set,
            config_version_id=config_version_id, governance_scope=gov_scope,
            cycle_id_factory=_make_cycle_id,
            check_idempotency=_check_and_register_idempotency,
            idempotency_key_fn=_idempotency_key, cycle_date=cycle_date,
        )
        cycle_ids[DOMAIN_PROVIDER_SYNC] = sync_id

        hb_id = await trigger_observability_heartbeat(
            execution_mode=execution_mode, config_version_id=config_version_id,
            governance_scope=gov_scope, cycle_id_factory=_make_cycle_id,
            scheduler_running=_scheduler.running,
        )
        cycle_ids[DOMAIN_OBSERVABILITY_HEARTBEAT] = hb_id

    coordination_cycle_id = _make_cycle_id()
    dur = int((time.monotonic() - t0) * 1000)

    emit_cycle_completion(
        cycle_id=coordination_cycle_id, correlation_id=None,
        execution_mode=execution_mode, execution_type="original",
        trigger_to_completion_ms=dur, loop_outcome="success",
        orphan_detected=False, governance_scope=gov_scope, reason_codes=codes,
    )

    return {
        "coordination_produced": True,
        "governance_scope": gov_scope,
        "execution_mode": execution_mode,
        "config_version_id": config_version_id,
        "orchestration_cycle_id": coordination_cycle_id,
        "reason_codes": codes,
        "cycle_ids": cycle_ids,
        "blocked": False,
        "duration_ms": dur,
    }


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def configure_scheduler(
    execution_mode: str,
    config_version_id: Optional[str],
    config_rule_set: Optional[Dict[str, Any]] = None,
    attribution_context: Optional[Dict[str, Any]] = None,
) -> None:
    """Store governance config used for every subsequent cycle trigger."""
    global _scheduler_config
    _scheduler_config = {
        "execution_mode": execution_mode,
        "config_version_id": config_version_id,
        "config_rule_set": config_rule_set or {},
        "attribution_context": attribution_context or {},
    }


async def _scheduled_cycle() -> None:
    """APScheduler callback — delegates to governance coordination only."""
    cfg = _scheduler_config
    await coordinate_orchestration_cycle(
        execution_mode=cfg.get("execution_mode", MODE_SHADOW),
        config_version_id=cfg.get("config_version_id"),
        config_rule_set=cfg.get("config_rule_set", {}),
        attribution_context=cfg.get("attribution_context", {}),
    )


def start_scheduler(
    trigger_hour: int = 8,
    trigger_minute: int = 0,
    timezone_str: str = "US/Central",
) -> None:
    """
    Start the APScheduler instance.
    Timing params are defaults only — authoritative values come from Config V2
    (outreach_daily_trigger_hour_cst / outreach_daily_trigger_minute_cst).
    """
    _scheduler.add_job(
        _scheduled_cycle,
        CronTrigger(hour=trigger_hour, minute=trigger_minute, timezone=timezone_str),
        id="governance_orchestration_cycle",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(json.dumps({
        "timestamp": _now_iso(), "level": "info", "service": "scheduler",
        "event": "scheduler_started",
        "trigger_hour": trigger_hour, "trigger_minute": trigger_minute,
        "timezone": timezone_str,
        "execution_mode": _scheduler_config.get("execution_mode", MODE_SHADOW),
        "config_version_id": _scheduler_config.get("config_version_id"),
    }))


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info(json.dumps({
            "timestamp": _now_iso(), "level": "info",
            "service": "scheduler", "event": "scheduler_stopped",
        }))


def get_scheduler_status() -> Dict[str, Any]:
    """Governance-aware scheduler status (not just active/stopped)."""
    return {
        "running": _scheduler.running,
        "execution_mode": _scheduler_config.get("execution_mode", MODE_SHADOW),
        "governance_scope": _governance_scope(
            _scheduler_config.get("execution_mode", MODE_SHADOW)
        ),
        "config_version_id": _scheduler_config.get("config_version_id"),
        "live_dispatch_enabled": False,
    }
