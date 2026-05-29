"""
Runtime bootstrap governance context — public API.

Governance alignment:
  SHADOW-safe default — system never starts in unrestricted LIVE scope
  Config V2 UNKNOWN_V0 safety semantics — no silent config fallback
  Replay-safe initialization — REPLAY scope isolated from LIVE paths
  Attribution continuity — startup correlation_id propagated to scheduler
  Structured startup observability — classification logged on every path
  AP-RT13 — no PII in startup log

Usage:
  ctx = initialize_runtime_context(
      execution_mode=settings.EXECUTION_MODE.value,
      active_configs=[],        # pass DB query result; [] → UNKNOWN_V0
      attribution={...},        # optional — completeness tracked
      config_rule_set={...},    # optional — scheduler timing source
      scheduler_fallback_hour=settings.SCHEDULER_HOUR,
      scheduler_fallback_minute=settings.SCHEDULER_MINUTE,
      scheduler_fallback_timezone=settings.SCHEDULER_TIMEZONE,
  )
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.bootstrap._bootstrap_helpers import (
    build_scheduler_timing,
    check_attribution_complete,
    classify_execution_mode,
    classify_startup,
    derive_governance_scope,
    emit_startup_log,
    validate_config_v2,
)
from app.bootstrap._bootstrap_types import (
    DEGRADE_ATTRIBUTION_INCOMPLETE,
    RuntimeBootstrapContext,
)


def initialize_runtime_context(
    *,
    execution_mode: str,
    active_configs: Optional[List[Any]] = None,
    attribution: Optional[Dict[str, Any]] = None,
    config_rule_set: Optional[Dict[str, Any]] = None,
    scheduler_fallback_hour: int = 8,
    scheduler_fallback_minute: int = 0,
    scheduler_fallback_timezone: str = "US/Central",
) -> RuntimeBootstrapContext:
    """
    Initialize governance-safe runtime bootstrap context.

    Called once at application startup (main.py on_startup).
    Returns an immutable RuntimeBootstrapContext used to:
      - configure the scheduler with explicit governance context
      - emit structured startup observability
      - validate SHADOW-safe containment

    SHADOW-safe guarantee: system starts in SHADOW_ONLY scope unless
    explicitly authorized via Config V2 governance (Phase-12 cert gate).
    Config V2 absence is an explicit degradation — never a silent fallback.
    Replay isolation: REPLAY/REGENERATION modes receive REPLAY_ONLY scope,
    preventing accidental LIVE effect initialization.

    Parameters
    ----------
    execution_mode:
        From settings.EXECUTION_MODE.value. Invalid values degrade to SHADOW.
    active_configs:
        Active Config V2 rows from DB query. Pass [] when no model exists.
        None or [] → UNKNOWN_V0 + degradation code. >1 → MULTIPLE_ACTIVE.
    attribution:
        Startup attribution dict (origin_source, origin_authority,
        attribution_timestamp). Partial attribution is non-blocking.
    config_rule_set:
        Config V2 rule set for scheduler timing. {} → settings fallbacks.
    scheduler_fallback_hour/minute/timezone:
        Settings-level defaults used when Config V2 is absent.
    """
    degradation_codes: List[str] = []

    # Step 1: Validate and resolve execution_mode — never silently invalid
    resolved_mode, _ = classify_execution_mode(execution_mode, degradation_codes)

    # Step 2: Validate Config V2 availability and exactly-one-ACTIVE invariant
    config_version_id, _ = validate_config_v2(
        active_configs if active_configs is not None else [],
        degradation_codes,
    )

    # Step 3: Derive governance scope — AUTHORIZED is unreachable
    governance_scope = derive_governance_scope(resolved_mode)

    # Step 4: Assess attribution completeness (non-blocking — only tracked)
    attribution_complete = check_attribution_complete(attribution)
    if attribution and not attribution_complete:
        degradation_codes.append(DEGRADE_ATTRIBUTION_INCOMPLETE)

    # Step 5: Classify startup safety state
    startup_classification = classify_startup(resolved_mode, degradation_codes)

    # Step 6: Build scheduler timing from Config V2 (explicit UNKNOWN_V0 fallback)
    timing = build_scheduler_timing(
        config_rule_set=config_rule_set,
        fallback_hour=scheduler_fallback_hour,
        fallback_minute=scheduler_fallback_minute,
        fallback_timezone=scheduler_fallback_timezone,
    )

    ctx = RuntimeBootstrapContext(
        startup_correlation_id=str(uuid.uuid4()),
        execution_mode=resolved_mode,
        governance_scope=governance_scope,
        startup_classification=startup_classification,
        config_version_id=config_version_id,
        # AUTHORIZED scope is unreachable — both flags always True
        shadow_containment_active=(governance_scope != "AUTHORIZED"),
        live_effects_suppressed=(governance_scope != "AUTHORIZED"),
        replay_safe=True,  # guaranteed by governance_scope derivation
        attribution_complete=attribution_complete,
        degradation_state=bool(degradation_codes),
        degradation_codes=degradation_codes,
        startup_timestamp=datetime.now(timezone.utc).isoformat(),
        scheduler_timing=timing,
    )

    emit_startup_log(bootstrap_context=ctx)
    return ctx
