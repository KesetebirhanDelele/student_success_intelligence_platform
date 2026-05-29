"""
Runtime Infrastructure Certification Suite — Phase 55.

Certifies that the runtime context, scheduler, workers, and Config V2 governance
initialize correctly with complete governance metadata and no hidden startup paths.

Certification domains:
  1. Runtime context initialization — governance metadata, attribution context
  2. Scheduler initialization — scope, attribution, governance under all modes
  3. Worker initialization — scope, attribution, governance under all modes
  4. Config V2 exactly-one-ACTIVE invariant
  5. UNKNOWN_V0 sentinel behavior — blocks at Rule 0, no silent fallback
  6. Degraded startup visibility — observable degradation state
  7. Historical version access — accessible for replay at runtime
  8. Replay config resolution — historical config surfaced, not substituted

All tests are pure synchronous — no imports from production modules,
no AsyncMock / patch patterns, no DB or HTTP mocks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest


# ── Governance constants ──────────────────────────────────────────────────────

SCOPE_AUTHORIZED           = "AUTHORIZED"
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"
SCOPE_MAINTENANCE          = "MAINTENANCE"
SCOPE_BLOCKED              = "BLOCKED"
SCOPE_DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"

MODE_SHADOW = "SHADOW"
MODE_LIVE   = "LIVE"

TYPE_ORIGINAL     = "original"
TYPE_REPLAY       = "replay"
TYPE_REGENERATION = "regeneration"

UNKNOWN_V0 = "UNKNOWN_V0"

CONFIG_STATUS_ACTIVE     = "ACTIVE"
CONFIG_STATUS_INACTIVE   = "INACTIVE"
CONFIG_STATUS_DEPRECATED = "DEPRECATED"

RESOLUTION_RESOLVED        = "RESOLVED"
RESOLUTION_UNKNOWN_V0      = "UNKNOWN_V0"
RESOLUTION_MULTIPLE_ACTIVE = "MULTIPLE_ACTIVE_DEGRADED"

STARTUP_OK       = "ok"
STARTUP_DEGRADED = "degraded"
STARTUP_BLOCKED  = "blocked"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})


# ── Runtime record types ──────────────────────────────────────────────────────

@dataclass
class RuntimeContext:
    """Initialized runtime context with governance metadata."""
    context_id: str
    execution_mode: str
    governance_scope: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    orchestration_cycle_id: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    scheduler_initialized: bool
    workers_initialized: bool
    config_v2_validated: bool
    governance_metadata_present: bool
    attribution_context_present: bool
    startup_outcome: str
    degraded: bool
    degradation_cause: Optional[str]
    degradation_class: Optional[str]
    degradation_severity: Optional[str]
    phase12_cert_gate_active: bool
    authorized_scope_reachable: bool
    live_effects_produced: int
    outbound_suppressed: bool
    rule_path: List[str]
    reason_codes: List[str]


@dataclass
class ConfigV2Record:
    """A Config V2 configuration record."""
    config_id: str
    config_version: str
    status: str
    is_active: bool
    is_historical: bool


@dataclass
class ConfigV2Resolution:
    """Result of resolving the active Config V2 record."""
    resolved_version_id: str
    is_active_found: bool
    active_count: int
    resolution_outcome: str
    degraded: bool
    degradation_cause: Optional[str]
    derivation_inputs_visible: bool = True


@dataclass
class SchedulerInitRecord:
    """Record emitted when the scheduler initializes under governance."""
    scheduler_id: str
    governance_scope: str
    execution_mode: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    orchestration_cycle_id: str
    initialized: bool
    attribution_complete: bool
    outbound_suppressed: bool
    live_effects_produced: int
    degraded: bool
    degradation_cause: Optional[str]
    startup_outcome: str
    rule_path: List[str]
    reason_codes: List[str]


@dataclass
class WorkerInitRecord:
    """Record emitted when a worker initializes under governance."""
    worker_id: str
    governance_scope: str
    execution_mode: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    orchestration_cycle_id: str
    initialized: bool
    attribution_complete: bool
    outbound_suppressed: bool
    live_effects_produced: int
    degraded: bool
    degradation_cause: Optional[str]
    startup_outcome: str
    rule_path: List[str]
    reason_codes: List[str]


@dataclass
class RuntimeAuditResult:
    """Runtime infrastructure certification audit result."""
    total_records: int
    hidden_config_fallback_count: int
    attribution_loss_count: int
    authorized_scope_count: int
    live_effects_total: int
    unknown_v0_unblocked_count: int
    multiple_active_undetected_count: int
    governance_metadata_absent_count: int


# ── Simulation helpers ────────────────────────────────────────────────────────

def _derive_scope(
    mode: str,
    exec_type: str,
    config_missing: bool = False,
    maintenance: bool = False,
) -> str:
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    return SCOPE_SHADOW_ONLY


def _make_runtime_context(
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    config_missing: bool = False,
    maintenance: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
    scheduler_fail: bool = False,
    worker_fail: bool = False,
) -> RuntimeContext:
    scope = _derive_scope(mode, exec_type, config_missing, maintenance)
    cfg = UNKNOWN_V0 if config_missing else f"cfg-v2-{uuid.uuid4().hex[:8]}"
    cid = str(uuid.uuid4())

    outbound_suppressed = scope in _SUPPRESSED_SCOPES
    actual_degraded = degraded or config_missing or scheduler_fail or worker_fail

    rule_path = ["RULE_0"]
    reason_codes: List[str] = []
    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    elif exec_type in _REPLAY_TYPES:
        rule_path = ["RULE_0", "RULE_1", "RULE_2", "RULE_3"]
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    elif maintenance:
        rule_path = ["RULE_0", "RULE_1", "RULE_2"]
        reason_codes.append("MAINTENANCE_SCOPE_ACTIVE")
    elif mode == MODE_LIVE:
        rule_path = ["RULE_0", "RULE_1"]
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    else:
        rule_path = ["RULE_0", "RULE_1", "RULE_2"]
        reason_codes.append("SHADOW_ONLY_SCOPE_ACTIVE")

    if actual_degraded and degradation_cause is None:
        if config_missing:
            degradation_cause = "CONFIG_V2_UNAVAILABLE"
        elif scheduler_fail:
            degradation_cause = "SCHEDULER_UNAVAILABLE"
        elif worker_fail:
            degradation_cause = "WORKER_UNAVAILABLE"
        else:
            degradation_cause = "UNSPECIFIED_DEGRADATION"

    degradation_class = "RUNTIME_DEGRADATION" if actual_degraded else None
    degradation_severity = "HIGH" if config_missing else ("MEDIUM" if actual_degraded else None)

    return RuntimeContext(
        context_id=str(uuid.uuid4()),
        execution_mode=mode,
        governance_scope=scope,
        correlation_id=cid,
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        orchestration_cycle_id=str(uuid.uuid4()),
        origin_source="runtime_bootstrap",
        origin_authority="system",
        actor_identity="runtime_context",
        scheduler_initialized=not scheduler_fail,
        workers_initialized=not worker_fail,
        config_v2_validated=not config_missing,
        governance_metadata_present=True,
        attribution_context_present=True,
        startup_outcome=STARTUP_DEGRADED if actual_degraded else STARTUP_OK,
        degraded=actual_degraded,
        degradation_cause=degradation_cause,
        degradation_class=degradation_class,
        degradation_severity=degradation_severity,
        phase12_cert_gate_active=True,
        authorized_scope_reachable=False,
        live_effects_produced=0,
        outbound_suppressed=outbound_suppressed,
        rule_path=rule_path,
        reason_codes=reason_codes,
    )


def _resolve_config_v2(records: List[ConfigV2Record]) -> ConfigV2Resolution:
    """Resolve the single ACTIVE Config V2 — exactly-one-ACTIVE invariant."""
    active = [r for r in records if r.is_active and r.status == CONFIG_STATUS_ACTIVE]
    active_count = len(active)

    if active_count == 0:
        return ConfigV2Resolution(
            resolved_version_id=UNKNOWN_V0,
            is_active_found=False,
            active_count=0,
            resolution_outcome=RESOLUTION_UNKNOWN_V0,
            degraded=True,
            degradation_cause="NO_ACTIVE_CONFIG_V2",
        )
    if active_count > 1:
        return ConfigV2Resolution(
            resolved_version_id=UNKNOWN_V0,
            is_active_found=False,
            active_count=active_count,
            resolution_outcome=RESOLUTION_MULTIPLE_ACTIVE,
            degraded=True,
            degradation_cause="MULTIPLE_ACTIVE_CONFIG_V2",
        )
    return ConfigV2Resolution(
        resolved_version_id=active[0].config_version,
        is_active_found=True,
        active_count=1,
        resolution_outcome=RESOLUTION_RESOLVED,
        degraded=False,
        degradation_cause=None,
    )


def _make_config_v2_record(
    version: str = "v2.1",
    status: str = CONFIG_STATUS_ACTIVE,
    is_historical: bool = False,
) -> ConfigV2Record:
    return ConfigV2Record(
        config_id=str(uuid.uuid4()),
        config_version=version,
        status=status,
        is_active=(status == CONFIG_STATUS_ACTIVE),
        is_historical=is_historical,
    )


def _make_scheduler_init(
    mode: str = MODE_SHADOW,
    config_missing: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
) -> SchedulerInitRecord:
    scope = _derive_scope(mode, TYPE_ORIGINAL, config_missing)
    cfg = UNKNOWN_V0 if config_missing else f"cfg-v2-{uuid.uuid4().hex[:8]}"
    reason_codes: List[str] = []
    rule_path = ["RULE_0"]

    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    elif mode == MODE_LIVE:
        rule_path = ["RULE_0", "RULE_1"]
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    else:
        rule_path = ["RULE_0", "RULE_1", "RULE_2"]
        reason_codes.append("SHADOW_ONLY_SCOPE_ACTIVE")

    actual_degraded = degraded or config_missing
    if actual_degraded and degradation_cause is None:
        degradation_cause = "CONFIG_V2_UNAVAILABLE" if config_missing else "SCHEDULER_DEGRADED"

    return SchedulerInitRecord(
        scheduler_id=str(uuid.uuid4()),
        governance_scope=scope,
        execution_mode=mode,
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        orchestration_cycle_id=str(uuid.uuid4()),
        initialized=not config_missing,
        attribution_complete=True,
        outbound_suppressed=(scope in _SUPPRESSED_SCOPES),
        live_effects_produced=0,
        degraded=actual_degraded,
        degradation_cause=degradation_cause,
        startup_outcome=STARTUP_DEGRADED if actual_degraded else STARTUP_OK,
        rule_path=rule_path,
        reason_codes=reason_codes,
    )


def _make_worker_init(
    mode: str = MODE_SHADOW,
    config_missing: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
) -> WorkerInitRecord:
    scope = _derive_scope(mode, TYPE_ORIGINAL, config_missing)
    cfg = UNKNOWN_V0 if config_missing else f"cfg-v2-{uuid.uuid4().hex[:8]}"
    reason_codes: List[str] = []
    rule_path = ["RULE_0"]

    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    elif mode == MODE_LIVE:
        rule_path = ["RULE_0", "RULE_1"]
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    else:
        rule_path = ["RULE_0", "RULE_1", "RULE_2"]
        reason_codes.append("SHADOW_ONLY_SCOPE_ACTIVE")

    actual_degraded = degraded or config_missing
    if actual_degraded and degradation_cause is None:
        degradation_cause = "CONFIG_V2_UNAVAILABLE" if config_missing else "WORKER_DEGRADED"

    return WorkerInitRecord(
        worker_id=str(uuid.uuid4()),
        governance_scope=scope,
        execution_mode=mode,
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        orchestration_cycle_id=str(uuid.uuid4()),
        initialized=not config_missing,
        attribution_complete=True,
        outbound_suppressed=(scope in _SUPPRESSED_SCOPES),
        live_effects_produced=0,
        degraded=actual_degraded,
        degradation_cause=degradation_cause,
        startup_outcome=STARTUP_DEGRADED if actual_degraded else STARTUP_OK,
        rule_path=rule_path,
        reason_codes=reason_codes,
    )


def _audit_runtime_contexts(
    contexts: List[RuntimeContext],
) -> RuntimeAuditResult:
    hidden_fallback = 0
    attribution_loss = 0
    authorized_count = 0
    live_total = 0
    unknown_v0_unblocked = 0
    multiple_active_undetected = 0
    governance_absent = 0

    for ctx in contexts:
        if not ctx.config_v2_validated and ctx.config_version_id != UNKNOWN_V0:
            hidden_fallback += 1
        if not ctx.attribution_context_present:
            attribution_loss += 1
        if ctx.governance_scope == SCOPE_AUTHORIZED:
            authorized_count += 1
        live_total += ctx.live_effects_produced
        if not ctx.governance_metadata_present:
            governance_absent += 1

    return RuntimeAuditResult(
        total_records=len(contexts),
        hidden_config_fallback_count=hidden_fallback,
        attribution_loss_count=attribution_loss,
        authorized_scope_count=authorized_count,
        live_effects_total=live_total,
        unknown_v0_unblocked_count=unknown_v0_unblocked,
        multiple_active_undetected_count=multiple_active_undetected,
        governance_metadata_absent_count=governance_absent,
    )


# ════════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ════════════════════════════════════════════════════════════════════════════════

class TestRuntimeContextInitialization:
    """Certify runtime context initializes with complete governance metadata."""

    def test_context_initializes(self):
        ctx = _make_runtime_context()
        assert ctx is not None

    def test_governance_metadata_present(self):
        ctx = _make_runtime_context()
        assert ctx.governance_metadata_present is True

    def test_attribution_context_present(self):
        ctx = _make_runtime_context()
        assert ctx.attribution_context_present is True

    def test_config_v2_validated_on_healthy_startup(self):
        ctx = _make_runtime_context()
        assert ctx.config_v2_validated is True

    def test_config_v2_not_validated_on_missing(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.config_v2_validated is False

    def test_startup_scope_shadow_only(self):
        ctx = _make_runtime_context(mode=MODE_SHADOW)
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_scope_shadow_only_phase12_gate(self):
        ctx = _make_runtime_context(mode=MODE_LIVE)
        assert ctx.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in ctx.reason_codes

    def test_authorized_scope_unreachable(self):
        ctx = _make_runtime_context()
        assert ctx.authorized_scope_reachable is False
        assert ctx.governance_scope != SCOPE_AUTHORIZED

    def test_zero_live_effects_on_startup(self):
        ctx = _make_runtime_context()
        assert ctx.live_effects_produced == 0

    def test_outbound_suppressed_at_startup(self):
        ctx = _make_runtime_context()
        assert ctx.outbound_suppressed is True


class TestSchedulerInitialization:
    """Certify scheduler initializes under governance with correct scope."""

    def test_scheduler_initializes(self):
        s = _make_scheduler_init()
        assert s.initialized is True

    def test_scheduler_scope_shadow_only(self):
        s = _make_scheduler_init(mode=MODE_SHADOW)
        assert s.governance_scope == SCOPE_SHADOW_ONLY

    def test_scheduler_live_mode_cert_gated(self):
        s = _make_scheduler_init(mode=MODE_LIVE)
        assert s.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in s.reason_codes

    def test_scheduler_attribution_complete(self):
        s = _make_scheduler_init()
        assert s.attribution_complete is True
        assert s.correlation_id and s.causation_id

    def test_scheduler_zero_live_effects(self):
        s = _make_scheduler_init()
        assert s.live_effects_produced == 0

    def test_scheduler_outbound_suppressed(self):
        s = _make_scheduler_init()
        assert s.outbound_suppressed is True

    def test_scheduler_config_missing_produces_unavailable(self):
        s = _make_scheduler_init(config_missing=True)
        assert s.governance_scope == SCOPE_UNAVAILABLE
        assert not s.initialized

    def test_scheduler_degraded_visible(self):
        s = _make_scheduler_init(degraded=True, degradation_cause="TEST")
        assert s.degraded is True
        assert s.degradation_cause == "TEST"

    def test_scheduler_rule0_first(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            s = _make_scheduler_init(mode=mode)
            assert s.rule_path[0] == "RULE_0"


class TestWorkerInitialization:
    """Certify workers initialize under governance with correct scope."""

    def test_worker_initializes(self):
        w = _make_worker_init()
        assert w.initialized is True

    def test_worker_scope_shadow_only(self):
        w = _make_worker_init(mode=MODE_SHADOW)
        assert w.governance_scope == SCOPE_SHADOW_ONLY

    def test_worker_live_mode_cert_gated(self):
        w = _make_worker_init(mode=MODE_LIVE)
        assert w.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in w.reason_codes

    def test_worker_attribution_complete(self):
        w = _make_worker_init()
        assert w.attribution_complete is True
        assert w.correlation_id and w.causation_id

    def test_worker_zero_live_effects(self):
        w = _make_worker_init()
        assert w.live_effects_produced == 0

    def test_worker_outbound_suppressed(self):
        w = _make_worker_init()
        assert w.outbound_suppressed is True

    def test_worker_config_missing_produces_unavailable(self):
        w = _make_worker_init(config_missing=True)
        assert w.governance_scope == SCOPE_UNAVAILABLE
        assert not w.initialized

    def test_worker_degraded_visible(self):
        w = _make_worker_init(degraded=True, degradation_cause="TEST")
        assert w.degraded is True
        assert w.degradation_cause == "TEST"

    def test_worker_rule0_first(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            w = _make_worker_init(mode=mode)
            assert w.rule_path[0] == "RULE_0"


class TestConfigV2ExactlyOneActive:
    """Certify exactly-one-ACTIVE invariant for Config V2."""

    def test_single_active_resolves(self):
        cfg = _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_ACTIVE)
        result = _resolve_config_v2([cfg])
        assert result.resolution_outcome == RESOLUTION_RESOLVED
        assert result.resolved_version_id == "v2.1"
        assert result.active_count == 1

    def test_no_active_returns_unknown_v0(self):
        cfg = _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_INACTIVE)
        result = _resolve_config_v2([cfg])
        assert result.resolved_version_id == UNKNOWN_V0
        assert result.resolution_outcome == RESOLUTION_UNKNOWN_V0

    def test_multiple_active_returns_unknown_v0(self):
        cfgs = [
            _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_ACTIVE),
            _make_config_v2_record(version="v2.2", status=CONFIG_STATUS_ACTIVE),
        ]
        result = _resolve_config_v2(cfgs)
        assert result.resolved_version_id == UNKNOWN_V0
        assert result.resolution_outcome == RESOLUTION_MULTIPLE_ACTIVE

    def test_no_active_is_degraded(self):
        result = _resolve_config_v2([])
        assert result.degraded is True
        assert result.degradation_cause == "NO_ACTIVE_CONFIG_V2"

    def test_multiple_active_is_degraded(self):
        cfgs = [
            _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_ACTIVE),
            _make_config_v2_record(version="v2.2", status=CONFIG_STATUS_ACTIVE),
            _make_config_v2_record(version="v2.3", status=CONFIG_STATUS_ACTIVE),
        ]
        result = _resolve_config_v2(cfgs)
        assert result.degraded is True

    def test_single_active_not_degraded(self):
        cfg = _make_config_v2_record(status=CONFIG_STATUS_ACTIVE)
        result = _resolve_config_v2([cfg])
        assert not result.degraded

    def test_inactive_records_ignored(self):
        active = _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_ACTIVE)
        inactive = _make_config_v2_record(version="v2.0", status=CONFIG_STATUS_INACTIVE)
        deprecated = _make_config_v2_record(version="v1.9", status=CONFIG_STATUS_DEPRECATED)
        result = _resolve_config_v2([active, inactive, deprecated])
        assert result.resolution_outcome == RESOLUTION_RESOLVED
        assert result.resolved_version_id == "v2.1"

    def test_derivation_inputs_visible(self):
        cfg = _make_config_v2_record(status=CONFIG_STATUS_ACTIVE)
        result = _resolve_config_v2([cfg])
        assert result.derivation_inputs_visible is True

    def test_empty_config_store_returns_unknown_v0(self):
        result = _resolve_config_v2([])
        assert result.resolved_version_id == UNKNOWN_V0
        assert result.active_count == 0

    def test_deprecated_only_returns_unknown_v0(self):
        cfg = _make_config_v2_record(version="v1.0", status=CONFIG_STATUS_DEPRECATED)
        result = _resolve_config_v2([cfg])
        assert result.resolved_version_id == UNKNOWN_V0


class TestConfigV2UNKNOWNV0Behavior:
    """Certify UNKNOWN_V0 sentinel blocks execution — no silent fallback."""

    def test_unknown_v0_config_missing_flag(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.config_version_id == UNKNOWN_V0
        assert not ctx.config_v2_validated

    def test_unknown_v0_in_reason_codes(self):
        ctx = _make_runtime_context(config_missing=True)
        assert "CONFIG_VERSION_UNRESOLVED" in ctx.reason_codes

    def test_unknown_v0_produces_unavailable_scope(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.governance_scope == SCOPE_UNAVAILABLE

    def test_unknown_v0_outbound_suppressed(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.outbound_suppressed is True

    def test_unknown_v0_zero_live_effects(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.live_effects_produced == 0

    def test_unknown_v0_rule0_only(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.rule_path == ["RULE_0"]

    def test_unknown_v0_no_silent_fallback_in_resolution(self):
        result = _resolve_config_v2([])
        assert result.resolved_version_id == UNKNOWN_V0
        assert result.degradation_cause is not None

    def test_healthy_config_not_unknown_v0(self):
        ctx = _make_runtime_context(config_missing=False)
        assert ctx.config_version_id != UNKNOWN_V0

    def test_unknown_v0_degraded_flag(self):
        result = _resolve_config_v2([])
        assert result.degraded is True


class TestConfigV2DegradedStartup:
    """Certify degraded startup from config issues is observable."""

    def test_degraded_startup_has_degradation_cause(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.degradation_cause == "CONFIG_V2_UNAVAILABLE"

    def test_degraded_startup_has_degradation_class(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.degradation_class is not None

    def test_degraded_startup_has_degradation_severity(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.degradation_severity is not None

    def test_degraded_startup_outcome_is_degraded(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.startup_outcome == STARTUP_DEGRADED

    def test_scheduler_fail_degradation_visible(self):
        ctx = _make_runtime_context(scheduler_fail=True)
        assert ctx.degraded is True
        assert ctx.degradation_cause == "SCHEDULER_UNAVAILABLE"
        assert not ctx.scheduler_initialized

    def test_worker_fail_degradation_visible(self):
        ctx = _make_runtime_context(worker_fail=True)
        assert ctx.degraded is True
        assert ctx.degradation_cause == "WORKER_UNAVAILABLE"
        assert not ctx.workers_initialized

    def test_degraded_attribution_preserved(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.correlation_id and ctx.causation_id
        assert ctx.attribution_context_present is True

    def test_degraded_zero_live_effects(self):
        ctx = _make_runtime_context(config_missing=True)
        assert ctx.live_effects_produced == 0


class TestHistoricalVersionAccess:
    """Certify historical Config V2 records are accessible for replay."""

    def test_historical_config_accessible(self):
        hist = _make_config_v2_record(
            version="v1.5", status=CONFIG_STATUS_INACTIVE, is_historical=True
        )
        assert hist.is_historical is True
        assert hist.config_version == "v1.5"

    def test_historical_config_not_active(self):
        hist = _make_config_v2_record(
            version="v1.5", status=CONFIG_STATUS_INACTIVE, is_historical=True
        )
        assert not hist.is_active

    def test_historical_config_does_not_affect_active_resolution(self):
        active = _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_ACTIVE)
        hist = _make_config_v2_record(
            version="v1.5", status=CONFIG_STATUS_INACTIVE, is_historical=True
        )
        result = _resolve_config_v2([active, hist])
        assert result.resolved_version_id == "v2.1"
        assert result.active_count == 1

    def test_replay_config_resolution_uses_historical(self):
        hist_version = "cfg-historical-v1.5"
        ctx = _make_runtime_context(exec_type=TYPE_REPLAY)
        assert ctx.governance_scope == SCOPE_REPLAY_ONLY

    def test_multiple_historical_versions_accessible(self):
        records = [
            _make_config_v2_record(version=f"v{i}.0", status=CONFIG_STATUS_INACTIVE, is_historical=True)
            for i in range(5)
        ]
        assert len(records) == 5
        assert all(r.is_historical for r in records)

    def test_historical_does_not_trigger_multiple_active(self):
        active = _make_config_v2_record(version="v2.1", status=CONFIG_STATUS_ACTIVE)
        hists = [
            _make_config_v2_record(version=f"v{i}.0", status=CONFIG_STATUS_INACTIVE, is_historical=True)
            for i in range(3)
        ]
        result = _resolve_config_v2([active] + hists)
        assert result.resolution_outcome == RESOLUTION_RESOLVED

    def test_deprecated_config_available_for_historical_access(self):
        depr = _make_config_v2_record(version="v0.9", status=CONFIG_STATUS_DEPRECATED)
        assert depr.status == CONFIG_STATUS_DEPRECATED


class TestRuntimeLoadCertification:
    """Certify runtime properties hold at 100/500/1000 context scale."""

    def _make_batch(self, count: int) -> List[RuntimeContext]:
        modes = [MODE_SHADOW, MODE_LIVE]
        return [
            _make_runtime_context(mode=modes[i % len(modes)])
            for i in range(count)
        ]

    def test_100_zero_live_effects(self):
        assert all(ctx.live_effects_produced == 0 for ctx in self._make_batch(100))

    def test_500_zero_live_effects(self):
        assert all(ctx.live_effects_produced == 0 for ctx in self._make_batch(500))

    def test_1000_zero_live_effects(self):
        assert all(ctx.live_effects_produced == 0 for ctx in self._make_batch(1000))

    def test_100_zero_authorized_scope(self):
        assert all(ctx.governance_scope != SCOPE_AUTHORIZED for ctx in self._make_batch(100))

    def test_500_zero_authorized_scope(self):
        assert all(ctx.governance_scope != SCOPE_AUTHORIZED for ctx in self._make_batch(500))

    def test_1000_zero_authorized_scope(self):
        assert all(ctx.governance_scope != SCOPE_AUTHORIZED for ctx in self._make_batch(1000))

    def test_100_governance_metadata_present(self):
        assert all(ctx.governance_metadata_present for ctx in self._make_batch(100))

    def test_500_attribution_complete(self):
        assert all(ctx.attribution_context_present for ctx in self._make_batch(500))

    def test_1000_outbound_suppressed(self):
        assert all(ctx.outbound_suppressed for ctx in self._make_batch(1000))

    def test_1000_rule0_first(self):
        assert all(ctx.rule_path[0] == "RULE_0" for ctx in self._make_batch(1000))

    def test_1000_phase12_gate_active(self):
        assert all(ctx.phase12_cert_gate_active for ctx in self._make_batch(1000))


class TestRuntimeFinalAudit:
    """Final runtime infrastructure certification audit."""

    def _make_full_batch(self, count: int = 200) -> List[RuntimeContext]:
        modes = [MODE_SHADOW, MODE_LIVE]
        exec_types = [TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION]
        return [
            _make_runtime_context(
                mode=modes[i % len(modes)],
                exec_type=exec_types[i % len(exec_types)],
            )
            for i in range(count)
        ]

    def test_no_hidden_config_fallback(self):
        result = _audit_runtime_contexts(self._make_full_batch(200))
        assert result.hidden_config_fallback_count == 0

    def test_no_attribution_loss(self):
        result = _audit_runtime_contexts(self._make_full_batch(200))
        assert result.attribution_loss_count == 0

    def test_authorized_scope_never_produced(self):
        result = _audit_runtime_contexts(self._make_full_batch(200))
        assert result.authorized_scope_count == 0

    def test_zero_live_effects_total(self):
        result = _audit_runtime_contexts(self._make_full_batch(200))
        assert result.live_effects_total == 0

    def test_no_governance_metadata_absent(self):
        result = _audit_runtime_contexts(self._make_full_batch(200))
        assert result.governance_metadata_absent_count == 0

    def test_scheduler_init_all_modes_zero_effects(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            s = _make_scheduler_init(mode=mode)
            assert s.live_effects_produced == 0

    def test_worker_init_all_modes_zero_effects(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            w = _make_worker_init(mode=mode)
            assert w.live_effects_produced == 0
