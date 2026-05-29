"""
Internal helpers for runtime bootstrap governance.

Not part of the public API — consumed only by runtime_context.py.
All helpers are pure functions: no DB, no HTTP, no FastAPI dependencies.
Directly testable without infrastructure.

Governance responsibilities:
  SHADOW-safe execution mode validation (never silent LIVE default)
  Config V2 exactly-one-ACTIVE invariant validation
  Governance scope derivation (AUTHORIZED unreachable — Phase-12 cert gate)
  Startup classification (SHADOW_SAFE / REPLAY_SAFE / MAINTENANCE / DEGRADED)
  Attribution completeness assessment
  Scheduler timing construction from Config V2 with explicit UNKNOWN_V0 fallback
  Structured startup observability emission (no PII — AP-RT13)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.bootstrap._bootstrap_types import (
    BOOTSTRAP_MODE_MAINTENANCE,
    BOOTSTRAP_MODE_SHADOW,
    DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE,
    DEGRADE_CONFIG_V2_NO_ACTIVE,
    DEGRADE_CONFIG_V2_UNAVAILABLE,
    DEGRADE_EXECUTION_MODE_INVALID,
    REQUIRED_BOOTSTRAP_ATTRIBUTION,
    SCOPE_DEGRADED,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    STARTUP_CLASS_DEGRADED,
    STARTUP_CLASS_MAINTENANCE,
    STARTUP_CLASS_REPLAY_SAFE,
    STARTUP_CLASS_SHADOW_SAFE,
    UNKNOWN_V0,
    _REPLAY_BOOTSTRAP_MODES,
    _VALID_BOOTSTRAP_MODES,
)

logger = logging.getLogger(__name__)

_BOOTSTRAP_SERVICE = "bootstrap"

# Config V2 key names (scheduler_design.md §5, system_loop.md §5.2)
_K_TRIGGER_HOUR   = "outreach_daily_trigger_hour_cst"
_K_TRIGGER_MINUTE = "outreach_daily_trigger_minute_cst"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_execution_mode(
    execution_mode: str,
    codes: List[str],
) -> Tuple[str, bool]:
    """
    Validate execution_mode against allowed values.
    Invalid mode → degrade to SHADOW explicitly, append DEGRADE code.
    Returns (resolved_mode, was_valid).

    SHADOW is the explicit safe default — not a silent fallback.
    """
    if execution_mode in _VALID_BOOTSTRAP_MODES:
        return execution_mode, True
    codes.append(DEGRADE_EXECUTION_MODE_INVALID)
    return BOOTSTRAP_MODE_SHADOW, False


def derive_governance_scope(execution_mode: str) -> str:
    """
    Derive startup governance scope from execution_mode.

    AUTHORIZED is unreachable — Phase-12 cert gate enforced here.
    LIVE maps to SHADOW_ONLY until Phase-12 certification.
    """
    if execution_mode in _REPLAY_BOOTSTRAP_MODES:
        return SCOPE_REPLAY_ONLY
    if execution_mode == BOOTSTRAP_MODE_MAINTENANCE:
        return SCOPE_MAINTENANCE
    if execution_mode == "DEGRADED":
        return SCOPE_DEGRADED
    # SHADOW and LIVE both map to SHADOW_ONLY — AUTHORIZED requires Phase-12 cert
    return SCOPE_SHADOW_ONLY


def classify_startup(
    execution_mode: str,
    degradation_codes: List[str],
) -> str:
    """
    Classify startup safety state.
    Degradation takes precedence over mode-specific classification.
    """
    if degradation_codes:
        return STARTUP_CLASS_DEGRADED
    if execution_mode in _REPLAY_BOOTSTRAP_MODES:
        return STARTUP_CLASS_REPLAY_SAFE
    if execution_mode == BOOTSTRAP_MODE_MAINTENANCE:
        return STARTUP_CLASS_MAINTENANCE
    return STARTUP_CLASS_SHADOW_SAFE


def validate_config_v2(
    active_configs: List[Any],
    codes: List[str],
) -> Tuple[str, bool]:
    """
    Validate Config V2 availability and exactly-one-ACTIVE invariant.
    Returns (config_version_id, valid).

    Never silently falls back — degradation is explicit:
    - None list → DEGRADE_CONFIG_V2_UNAVAILABLE
    - Empty list → DEGRADE_CONFIG_V2_NO_ACTIVE
    - Multiple entries → DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE
    - Single entry → extract version_id, return valid
    """
    if active_configs is None:
        codes.append(DEGRADE_CONFIG_V2_UNAVAILABLE)
        return UNKNOWN_V0, False
    if len(active_configs) == 0:
        codes.append(DEGRADE_CONFIG_V2_NO_ACTIVE)
        return UNKNOWN_V0, False
    if len(active_configs) > 1:
        codes.append(DEGRADE_CONFIG_V2_MULTIPLE_ACTIVE)
        return UNKNOWN_V0, False
    cfg = active_configs[0]
    version_id = (
        getattr(cfg, "version_id", None)
        or getattr(cfg, "id", None)
        or str(cfg)
    )
    return str(version_id), True


def check_attribution_complete(
    attribution: Optional[Dict[str, Any]],
) -> bool:
    """
    Attribution is complete when all required fields are present and non-empty.
    Partial attribution is allowed at startup (non-blocking) — completeness
    is tracked but does not prevent startup.
    """
    if not attribution:
        return False
    return all(attribution.get(k) for k in REQUIRED_BOOTSTRAP_ATTRIBUTION)


def build_scheduler_timing(
    config_rule_set: Optional[Dict[str, Any]],
    fallback_hour: int,
    fallback_minute: int,
    fallback_timezone: str,
) -> Dict[str, Any]:
    """
    Build scheduler timing config from Config V2 rule set.

    Config V2 values take precedence over settings-level defaults.
    UNKNOWN_V0 values are treated as absent (fall back to settings).
    Fallback is explicit: config_sourced=False signals UNKNOWN_V0 path.
    """
    rule_set = config_rule_set or {}

    def _get(key: str, fallback: Any) -> Any:
        val = rule_set.get(key)
        if val is not None and val != UNKNOWN_V0:
            return val
        return fallback

    return {
        "trigger_hour": _get(_K_TRIGGER_HOUR, fallback_hour),
        "trigger_minute": _get(_K_TRIGGER_MINUTE, fallback_minute),
        "timezone_str": fallback_timezone,
        "config_sourced": bool(rule_set),
    }


def emit_startup_log(bootstrap_context: Any, event: str = "runtime_bootstrap_complete") -> None:
    """
    Emit structured startup classification log.

    Observability never suppressed (AP-RT15).
    No PII — only governance classification fields (AP-RT13).
    Emits warning level when degradation_state is True.
    """
    is_warn = getattr(bootstrap_context, "degradation_state", False)
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": _BOOTSTRAP_SERVICE,
        "event": event,
        **bootstrap_context.as_log_dict(),
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))
