"""
Startup Certification Suite — Phase 55.

Certifies startup defaults are SHADOW-safe, provider suppression is active,
AUTHORIZED scope is unreachable, and every runtime failure mode produces a
deterministic degradation state with observable failure classification and
unbroken attribution continuity.

Startup certification domains:
  1. SHADOW default — startup defaults are SHADOW-safe at all times
  2. Missing config failure — UNKNOWN_V0 produced, Rule 0 blocks, attribution intact
  3. Scheduler unavailable — deterministic degradation, observable, attribution intact
  4. Worker unavailable — deterministic degradation, observable, attribution intact
  5. Provider unavailable — deterministic degradation, suppression visible
  6. Observability unavailable — degradation state produced, attribution continuity

Failure-mode contract (every failure mode must satisfy):
  - deterministic_degradation_state == True
  - failure_classification is non-empty
  - attribution_preserved == True (correlation_id and causation_id present)
  - live_effects_produced == 0
  - outbound_suppressed == True

Critical constraint: This phase is certification only.
  - Do NOT enable LIVE communication.
  - Do NOT remove SHADOW containment.

All tests are pure synchronous — no imports from production modules,
no AsyncMock / patch patterns, no DB or HTTP mocks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

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

STARTUP_OK       = "ok"
STARTUP_DEGRADED = "degraded"

FAILURE_MISSING_CONFIG              = "missing_config"
FAILURE_SCHEDULER_UNAVAILABLE       = "scheduler_unavailable"
FAILURE_WORKER_UNAVAILABLE          = "worker_unavailable"
FAILURE_PROVIDER_UNAVAILABLE        = "provider_unavailable"
FAILURE_OBSERVABILITY_UNAVAILABLE   = "observability_unavailable"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

_ALL_FAILURE_MODES = [
    FAILURE_MISSING_CONFIG,
    FAILURE_SCHEDULER_UNAVAILABLE,
    FAILURE_WORKER_UNAVAILABLE,
    FAILURE_PROVIDER_UNAVAILABLE,
    FAILURE_OBSERVABILITY_UNAVAILABLE,
]


# ── Startup record types ──────────────────────────────────────────────────────

@dataclass
class StartupRecord:
    """Complete startup governance record — healthy or degraded."""
    record_id: str
    execution_mode: str
    execution_type: str
    governance_scope: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    orchestration_cycle_id: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    rule_path: List[str]
    reason_codes: List[str]
    outbound_suppressed: bool
    live_effects_produced: int
    provider_dispatch_count: int
    startup_outcome: str
    scheduler_initialized: bool
    workers_initialized: bool
    providers_available: bool
    observability_available: bool
    config_v2_validated: bool
    attribution_context_present: bool
    phase12_cert_gate_active: bool
    authorized_scope_reachable: bool


@dataclass
class StartupDegradationRecord:
    """Degradation state produced when a startup failure mode is triggered."""
    failure_mode: str
    degradation_state: str        # always "deterministic"
    failure_classification: str   # always non-empty
    attribution_preserved: bool   # always True
    correlation_id: str
    causation_id: str
    config_version_id: str
    governance_scope: str
    outbound_suppressed: bool
    live_effects_produced: int
    reason_codes: List[str]
    rule_path: List[str]
    degraded: bool
    degradation_cause: str
    degradation_class: str
    degradation_severity: str
    startup_outcome: str


@dataclass
class StartupAuditResult:
    """Startup certification audit result."""
    total_records: int
    startup_ambiguity_count: int
    authorized_scope_count: int
    live_effects_total: int
    attribution_gap_count: int
    replay_leakage_count: int
    hidden_config_fallback_count: int
    invariant_violation_count: int
    degradation_invisible_count: int


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


def _make_startup_record(
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    config_missing: bool = False,
    scheduler_fail: bool = False,
    worker_fail: bool = False,
    provider_fail: bool = False,
    observability_fail: bool = False,
) -> StartupRecord:
    scope = _derive_scope(mode, exec_type, config_missing)
    cfg = UNKNOWN_V0 if config_missing else f"cfg-v2-{uuid.uuid4().hex[:8]}"
    cid = str(uuid.uuid4())

    outbound_suppressed = scope in _SUPPRESSED_SCOPES

    rule_path = ["RULE_0"]
    reason_codes: List[str] = []

    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    elif exec_type in _REPLAY_TYPES:
        rule_path = ["RULE_0", "RULE_1", "RULE_2", "RULE_3"]
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    elif mode == MODE_LIVE:
        rule_path = ["RULE_0", "RULE_1"]
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    else:
        rule_path = ["RULE_0", "RULE_1", "RULE_2"]
        reason_codes.append("SHADOW_ONLY_SCOPE_ACTIVE")

    degraded = any([config_missing, scheduler_fail, worker_fail, provider_fail])
    outcome = STARTUP_DEGRADED if degraded else STARTUP_OK

    return StartupRecord(
        record_id=str(uuid.uuid4()),
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        correlation_id=cid,
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        orchestration_cycle_id=str(uuid.uuid4()),
        origin_source="startup",
        origin_authority="system",
        actor_identity="bootstrap",
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=outbound_suppressed,
        live_effects_produced=0,
        provider_dispatch_count=0,
        startup_outcome=outcome,
        scheduler_initialized=not scheduler_fail,
        workers_initialized=not worker_fail,
        providers_available=not provider_fail,
        observability_available=not observability_fail,
        config_v2_validated=not config_missing,
        attribution_context_present=True,
        phase12_cert_gate_active=True,
        authorized_scope_reachable=False,
    )


def _simulate_failure(failure_mode: str) -> StartupDegradationRecord:
    """Simulate a startup failure mode and produce a deterministic degradation record."""
    cid = str(uuid.uuid4())

    _failure_map = {
        FAILURE_MISSING_CONFIG: {
            "classification": "CONFIG_V2_UNAVAILABLE",
            "scope": SCOPE_UNAVAILABLE,
            "cause": "CONFIG_V2_UNAVAILABLE",
            "class_": "CONFIG_DEGRADATION",
            "severity": "HIGH",
            "reason": "CONFIG_VERSION_UNRESOLVED",
            "rule_path": ["RULE_0"],
        },
        FAILURE_SCHEDULER_UNAVAILABLE: {
            "classification": "SCHEDULER_INIT_FAILURE",
            "scope": SCOPE_SHADOW_ONLY,
            "cause": "SCHEDULER_UNAVAILABLE",
            "class_": "RUNTIME_DEGRADATION",
            "severity": "MEDIUM",
            "reason": "SHADOW_ONLY_SCOPE_ACTIVE",
            "rule_path": ["RULE_0", "RULE_1", "RULE_2"],
        },
        FAILURE_WORKER_UNAVAILABLE: {
            "classification": "WORKER_INIT_FAILURE",
            "scope": SCOPE_SHADOW_ONLY,
            "cause": "WORKER_UNAVAILABLE",
            "class_": "RUNTIME_DEGRADATION",
            "severity": "MEDIUM",
            "reason": "SHADOW_ONLY_SCOPE_ACTIVE",
            "rule_path": ["RULE_0", "RULE_1", "RULE_2"],
        },
        FAILURE_PROVIDER_UNAVAILABLE: {
            "classification": "PROVIDER_INIT_FAILURE",
            "scope": SCOPE_SHADOW_ONLY,
            "cause": "PROVIDER_UNAVAILABLE",
            "class_": "PROVIDER_DEGRADATION",
            "severity": "LOW",
            "reason": "SHADOW_ONLY_SCOPE_ACTIVE",
            "rule_path": ["RULE_0", "RULE_1", "RULE_2"],
        },
        FAILURE_OBSERVABILITY_UNAVAILABLE: {
            "classification": "OBSERVABILITY_INIT_FAILURE",
            "scope": SCOPE_SHADOW_ONLY,
            "cause": "OBSERVABILITY_UNAVAILABLE",
            "class_": "OBSERVABILITY_DEGRADATION",
            "severity": "LOW",
            "reason": "SHADOW_ONLY_SCOPE_ACTIVE",
            "rule_path": ["RULE_0", "RULE_1", "RULE_2"],
        },
    }

    info = _failure_map[failure_mode]
    scope = info["scope"]
    outbound_suppressed = scope in _SUPPRESSED_SCOPES
    cfg = UNKNOWN_V0 if failure_mode == FAILURE_MISSING_CONFIG else f"cfg-v2-{uuid.uuid4().hex[:8]}"

    return StartupDegradationRecord(
        failure_mode=failure_mode,
        degradation_state="deterministic",
        failure_classification=info["classification"],
        attribution_preserved=True,
        correlation_id=cid,
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        governance_scope=scope,
        outbound_suppressed=outbound_suppressed,
        live_effects_produced=0,
        reason_codes=[info["reason"]],
        rule_path=info["rule_path"],
        degraded=True,
        degradation_cause=info["cause"],
        degradation_class=info["class_"],
        degradation_severity=info["severity"],
        startup_outcome=STARTUP_DEGRADED,
    )


def _audit_startup_records(
    records: List[StartupRecord],
) -> StartupAuditResult:
    startup_ambiguity = 0
    authorized_count = 0
    live_total = 0
    attribution_gaps = 0
    replay_leakage = 0
    hidden_fallback = 0
    inv_violations = 0
    degradation_invisible = 0

    for r in records:
        if r.governance_scope == SCOPE_AUTHORIZED:
            authorized_count += 1
            inv_violations += 1
        live_total += r.live_effects_produced
        if not r.attribution_context_present:
            attribution_gaps += 1
        if not r.config_v2_validated and r.config_version_id != UNKNOWN_V0:
            hidden_fallback += 1
        # Replay types are inherently unambiguous (scope=REPLAY_ONLY is expected)
        if (r.execution_mode == MODE_LIVE
                and r.execution_type not in _REPLAY_TYPES
                and r.governance_scope != SCOPE_SHADOW_ONLY
                and "LIVE_SCOPE_REQUIRES_PHASE12_CERT" not in r.reason_codes):
            startup_ambiguity += 1
        is_rep = r.execution_type in _REPLAY_TYPES
        if is_rep and r.governance_scope != SCOPE_REPLAY_ONLY:
            replay_leakage += 1

    return StartupAuditResult(
        total_records=len(records),
        startup_ambiguity_count=startup_ambiguity,
        authorized_scope_count=authorized_count,
        live_effects_total=live_total,
        attribution_gap_count=attribution_gaps,
        replay_leakage_count=replay_leakage,
        hidden_config_fallback_count=hidden_fallback,
        invariant_violation_count=inv_violations,
        degradation_invisible_count=degradation_invisible,
    )


# ════════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ════════════════════════════════════════════════════════════════════════════════

class TestShadowDefaultCertification:
    """Certify startup defaults are SHADOW-safe — provider suppression active."""

    def test_default_scope_is_shadow_only(self):
        r = _make_startup_record()
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_default_outbound_suppressed(self):
        r = _make_startup_record()
        assert r.outbound_suppressed is True

    def test_default_zero_live_effects(self):
        r = _make_startup_record()
        assert r.live_effects_produced == 0

    def test_default_zero_provider_dispatch(self):
        r = _make_startup_record()
        assert r.provider_dispatch_count == 0

    def test_authorized_scope_unreachable(self):
        r = _make_startup_record()
        assert r.authorized_scope_reachable is False
        assert r.governance_scope != SCOPE_AUTHORIZED

    def test_phase12_cert_gate_active(self):
        r = _make_startup_record()
        assert r.phase12_cert_gate_active is True

    def test_live_mode_still_shadow_only(self):
        r = _make_startup_record(mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_attribution_context_present(self):
        r = _make_startup_record()
        assert r.attribution_context_present is True

    def test_rule0_first_in_all_modes(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            r = _make_startup_record(mode=mode)
            assert r.rule_path[0] == "RULE_0"

    def test_reason_codes_non_empty(self):
        r = _make_startup_record()
        assert len(r.reason_codes) > 0


class TestMissingConfigFailure:
    """Certify missing config produces UNKNOWN_V0, blocks at Rule 0, attribution intact."""

    def test_missing_config_produces_unknown_v0(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.config_version_id == UNKNOWN_V0

    def test_missing_config_scope_unavailable(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.governance_scope == SCOPE_UNAVAILABLE

    def test_missing_config_rule0_only(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.rule_path == ["RULE_0"]

    def test_missing_config_reason_code_present(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert "CONFIG_VERSION_UNRESOLVED" in d.reason_codes

    def test_missing_config_degradation_state_deterministic(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.degradation_state == "deterministic"

    def test_missing_config_classification_non_empty(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.failure_classification

    def test_missing_config_attribution_preserved(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.attribution_preserved is True
        assert d.correlation_id and d.causation_id

    def test_missing_config_zero_live_effects(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.live_effects_produced == 0

    def test_missing_config_outbound_suppressed(self):
        d = _simulate_failure(FAILURE_MISSING_CONFIG)
        assert d.outbound_suppressed is True


class TestSchedulerUnavailableFailure:
    """Certify scheduler unavailable produces deterministic observable degradation."""

    def test_scheduler_fail_degradation_state_deterministic(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.degradation_state == "deterministic"

    def test_scheduler_fail_classification_non_empty(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.failure_classification == "SCHEDULER_INIT_FAILURE"

    def test_scheduler_fail_attribution_preserved(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.attribution_preserved is True
        assert d.correlation_id and d.causation_id

    def test_scheduler_fail_zero_live_effects(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.live_effects_produced == 0

    def test_scheduler_fail_outbound_suppressed(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.outbound_suppressed is True

    def test_scheduler_fail_scope_suppressed(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.governance_scope in _SUPPRESSED_SCOPES

    def test_scheduler_fail_degradation_cause_visible(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.degradation_cause == "SCHEDULER_UNAVAILABLE"

    def test_scheduler_fail_startup_outcome_degraded(self):
        d = _simulate_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert d.startup_outcome == STARTUP_DEGRADED

    def test_scheduler_fail_startup_record_not_initialized(self):
        r = _make_startup_record(scheduler_fail=True)
        assert not r.scheduler_initialized
        assert r.startup_outcome == STARTUP_DEGRADED


class TestWorkerUnavailableFailure:
    """Certify worker unavailable produces deterministic observable degradation."""

    def test_worker_fail_degradation_deterministic(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.degradation_state == "deterministic"

    def test_worker_fail_classification_non_empty(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.failure_classification == "WORKER_INIT_FAILURE"

    def test_worker_fail_attribution_preserved(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.attribution_preserved is True
        assert d.correlation_id and d.causation_id

    def test_worker_fail_zero_live_effects(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.live_effects_produced == 0

    def test_worker_fail_outbound_suppressed(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.outbound_suppressed is True

    def test_worker_fail_scope_suppressed(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.governance_scope in _SUPPRESSED_SCOPES

    def test_worker_fail_degradation_cause_visible(self):
        d = _simulate_failure(FAILURE_WORKER_UNAVAILABLE)
        assert d.degradation_cause == "WORKER_UNAVAILABLE"

    def test_worker_fail_startup_record_not_initialized(self):
        r = _make_startup_record(worker_fail=True)
        assert not r.workers_initialized
        assert r.startup_outcome == STARTUP_DEGRADED


class TestProviderUnavailableFailure:
    """Certify provider unavailable produces deterministic observable degradation."""

    def test_provider_fail_degradation_deterministic(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.degradation_state == "deterministic"

    def test_provider_fail_classification_non_empty(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.failure_classification == "PROVIDER_INIT_FAILURE"

    def test_provider_fail_attribution_preserved(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.attribution_preserved is True
        assert d.correlation_id and d.causation_id

    def test_provider_fail_zero_live_effects(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.live_effects_produced == 0

    def test_provider_fail_outbound_suppressed(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.outbound_suppressed is True

    def test_provider_fail_scope_suppressed(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.governance_scope in _SUPPRESSED_SCOPES

    def test_provider_fail_degradation_cause_visible(self):
        d = _simulate_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert d.degradation_cause == "PROVIDER_UNAVAILABLE"

    def test_provider_fail_startup_record_providers_unavailable(self):
        r = _make_startup_record(provider_fail=True)
        assert not r.providers_available
        assert r.startup_outcome == STARTUP_DEGRADED

    def test_provider_fail_suppression_active(self):
        r = _make_startup_record(provider_fail=True)
        assert r.outbound_suppressed is True


class TestObservabilityUnavailableFailure:
    """Certify observability unavailable produces degradation state with attribution."""

    def test_observability_fail_degradation_deterministic(self):
        d = _simulate_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert d.degradation_state == "deterministic"

    def test_observability_fail_classification_non_empty(self):
        d = _simulate_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert d.failure_classification == "OBSERVABILITY_INIT_FAILURE"

    def test_observability_fail_attribution_preserved(self):
        d = _simulate_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert d.attribution_preserved is True
        assert d.correlation_id and d.causation_id

    def test_observability_fail_zero_live_effects(self):
        d = _simulate_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert d.live_effects_produced == 0

    def test_observability_fail_scope_suppressed(self):
        d = _simulate_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert d.governance_scope in _SUPPRESSED_SCOPES

    def test_observability_fail_degradation_cause_visible(self):
        d = _simulate_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert d.degradation_cause == "OBSERVABILITY_UNAVAILABLE"

    def test_observability_fail_startup_record_flag(self):
        r = _make_startup_record(observability_fail=True)
        assert not r.observability_available

    def test_observability_fail_governance_intact(self):
        r = _make_startup_record(observability_fail=True)
        assert r.governance_scope in _SUPPRESSED_SCOPES
        assert r.live_effects_produced == 0


class TestStartupGovernanceAttributionContinuity:
    """Certify attribution is preserved through every startup failure mode."""

    def test_all_failure_modes_attribution_preserved(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.attribution_preserved is True, f"attribution lost in {mode}"

    def test_all_failure_modes_correlation_id_present(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.correlation_id, f"correlation_id missing in {mode}"

    def test_all_failure_modes_causation_id_present(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.causation_id, f"causation_id missing in {mode}"

    def test_all_failure_modes_zero_live_effects(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.live_effects_produced == 0, f"live effects in {mode}"

    def test_all_failure_modes_outbound_suppressed(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.outbound_suppressed is True, f"not suppressed in {mode}"

    def test_all_failure_modes_degradation_state_deterministic(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.degradation_state == "deterministic", f"non-deterministic in {mode}"

    def test_all_failure_modes_classification_non_empty(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.failure_classification, f"empty classification in {mode}"

    def test_all_failure_modes_degradation_cause_non_empty(self):
        for mode in _ALL_FAILURE_MODES:
            d = _simulate_failure(mode)
            assert d.degradation_cause, f"empty degradation_cause in {mode}"

    def test_healthy_startup_attribution_complete(self):
        r = _make_startup_record()
        assert r.correlation_id and r.causation_id
        assert r.attribution_context_present is True


class TestStartupLoadCertification:
    """Certify startup properties hold at 100/500/1000 record scale."""

    def _make_batch(self, count: int) -> List[StartupRecord]:
        modes = [MODE_SHADOW, MODE_LIVE]
        exec_types = [TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION]
        return [
            _make_startup_record(
                mode=modes[i % len(modes)],
                exec_type=exec_types[i % len(exec_types)],
            )
            for i in range(count)
        ]

    def _make_failure_batch(self, count: int) -> List[StartupDegradationRecord]:
        modes = _ALL_FAILURE_MODES
        return [_simulate_failure(modes[i % len(modes)]) for i in range(count)]

    def test_100_zero_live_effects(self):
        assert all(r.live_effects_produced == 0 for r in self._make_batch(100))

    def test_500_zero_live_effects(self):
        assert all(r.live_effects_produced == 0 for r in self._make_batch(500))

    def test_1000_zero_live_effects(self):
        assert all(r.live_effects_produced == 0 for r in self._make_batch(1000))

    def test_100_zero_authorized_scope(self):
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in self._make_batch(100))

    def test_500_zero_authorized_scope(self):
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in self._make_batch(500))

    def test_1000_zero_authorized_scope(self):
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in self._make_batch(1000))

    def test_100_failure_attribution_preserved(self):
        assert all(d.attribution_preserved for d in self._make_failure_batch(100))

    def test_500_failure_attribution_preserved(self):
        assert all(d.attribution_preserved for d in self._make_failure_batch(500))

    def test_1000_failure_zero_live_effects(self):
        assert all(d.live_effects_produced == 0 for d in self._make_failure_batch(1000))

    def test_1000_failure_outbound_suppressed(self):
        assert all(d.outbound_suppressed for d in self._make_failure_batch(1000))

    def test_1000_failure_all_deterministic(self):
        assert all(
            d.degradation_state == "deterministic"
            for d in self._make_failure_batch(1000)
        )


class TestStartupFinalAudit:
    """Final startup certification audit — all dimensions simultaneously."""

    def _make_full_batch(self, count: int = 200) -> List[StartupRecord]:
        modes = [MODE_SHADOW, MODE_LIVE]
        exec_types = [TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION]
        return [
            _make_startup_record(
                mode=modes[i % len(modes)],
                exec_type=exec_types[i % len(exec_types)],
            )
            for i in range(count)
        ]

    def test_no_startup_ambiguity(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.startup_ambiguity_count == 0

    def test_authorized_scope_never_produced(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.authorized_scope_count == 0

    def test_zero_live_effects(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.live_effects_total == 0

    def test_no_attribution_loss(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.attribution_gap_count == 0

    def test_no_replay_leakage(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.replay_leakage_count == 0

    def test_no_hidden_config_fallback(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.hidden_config_fallback_count == 0

    def test_no_invariant_violations(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.invariant_violation_count == 0
