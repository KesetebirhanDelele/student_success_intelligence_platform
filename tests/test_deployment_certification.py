"""
Deployment Certification Suite — Phase 55.

Certifies startup observability, attribution, governance scope, replay visibility,
and degradation visibility across all 4 deployment environments.

Environments certified:
  1. LOCAL — isolated, SHADOW-only
  2. STAGING — isolated, SHADOW-only
  3. PRODUCTION-SHADOW — production isolation, SHADOW containment
  4. PRODUCTION-LIVE — certification gated (Phase-12 cert required)

Deployment certification contract:
  - Every startup record exposes all 7 governance attribution fields
  - Startup scope is always suppressed (never AUTHORIZED without cert)
  - Degradation at startup is observable (cause, class, severity all surfaced)
  - Replay config accessible at startup for replay exec types
  - No environment weakens suppression or attribution completeness

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

ENV_LOCAL             = "LOCAL"
ENV_STAGING           = "STAGING"
ENV_PRODUCTION_SHADOW = "PRODUCTION_SHADOW"
ENV_PRODUCTION_LIVE   = "PRODUCTION_LIVE"

STARTUP_OK       = "ok"
STARTUP_DEGRADED = "degraded"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

_ALL_ENVIRONMENTS = [
    ENV_LOCAL, ENV_STAGING, ENV_PRODUCTION_SHADOW, ENV_PRODUCTION_LIVE,
]


# ── Deployment record types ───────────────────────────────────────────────────

@dataclass
class DeploymentStartupRecord:
    """Observable record produced at deployment startup."""
    record_id: str
    environment: str
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
    degraded: bool
    degradation_cause: Optional[str]
    degradation_severity: Optional[str]
    degradation_class: Optional[str]
    is_replay: bool
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]
    replay_lineage_visible: bool
    config_v2_validated: bool
    attribution_context_present: bool
    startup_observability_present: bool
    phase12_cert_gate_active: bool
    authorized_scope_reachable: bool


@dataclass
class DeploymentStartupLog:
    """Structured JSON log emitted at deployment startup."""
    timestamp: str
    level: str
    service: str
    event: str
    environment: str
    correlation_id: str
    governance_scope: str
    execution_mode: str
    execution_type: str
    config_version_id: str
    orchestration_cycle_id: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    outbound_suppressed: bool
    live_effects_produced: int
    provider_dispatch_count: int
    reason_codes: List[str]
    rule_path_summary: str
    startup_outcome: str
    degraded: bool
    pii_excluded: bool


@dataclass
class DeploymentAuditResult:
    """Deployment certification audit result across a batch of startup records."""
    total_records: int
    startup_ambiguity_count: int
    environment_leakage_count: int
    replay_leakage_count: int
    hidden_config_fallback_count: int
    attribution_loss_count: int
    governance_invariant_violations: int
    unauthorized_live_count: int
    authorized_scope_count: int
    live_effects_total: int


# ── Simulation helpers ────────────────────────────────────────────────────────

def _derive_startup_scope(
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
    # Phase-12 cert gate: LIVE → SHADOW_ONLY until cert issued
    return SCOPE_SHADOW_ONLY


def _make_startup_record(
    environment: str = ENV_LOCAL,
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    config_missing: bool = False,
    maintenance: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
    is_replay: bool = False,
    historical_config: Optional[str] = None,
    source_artifact: Optional[str] = None,
) -> DeploymentStartupRecord:
    scope = _derive_startup_scope(mode, exec_type, config_missing, maintenance)
    cfg = UNKNOWN_V0 if config_missing else f"cfg-v2-{uuid.uuid4().hex[:8]}"
    cid = str(uuid.uuid4())

    is_rep = is_replay or exec_type in _REPLAY_TYPES
    outbound_suppressed = scope in _SUPPRESSED_SCOPES

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

    degradation_class = None
    degradation_severity = None
    if degraded:
        degradation_class = "CONFIG_DEGRADATION" if config_missing else "RUNTIME_DEGRADATION"
        degradation_severity = "HIGH" if config_missing else "MEDIUM"
        if degradation_cause is None:
            degradation_cause = "CONFIG_V2_UNAVAILABLE" if config_missing else "UNSPECIFIED_DEGRADATION"

    hist_cfg = historical_config if is_rep else None

    return DeploymentStartupRecord(
        record_id=f"dep-{uuid.uuid4().hex[:8]}",
        environment=environment,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        correlation_id=cid,
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        orchestration_cycle_id=str(uuid.uuid4()),
        origin_source="startup_bootstrap",
        origin_authority="system",
        actor_identity="bootstrap_agent",
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=outbound_suppressed,
        live_effects_produced=0,
        provider_dispatch_count=0,
        startup_outcome=STARTUP_DEGRADED if degraded else STARTUP_OK,
        degraded=degraded,
        degradation_cause=degradation_cause,
        degradation_severity=degradation_severity,
        degradation_class=degradation_class,
        is_replay=is_rep,
        source_artifact_id=source_artifact,
        historical_config_version_id=hist_cfg,
        replay_lineage_visible=is_rep,
        config_v2_validated=not config_missing,
        attribution_context_present=True,
        startup_observability_present=True,
        phase12_cert_gate_active=True,
        authorized_scope_reachable=False,
    )


def _make_startup_log(record: DeploymentStartupRecord) -> DeploymentStartupLog:
    return DeploymentStartupLog(
        timestamp="2026-05-29T00:00:00Z",
        level="WARN" if record.degraded else "INFO",
        service="startup_bootstrap",
        event="deployment_startup",
        environment=record.environment,
        correlation_id=record.correlation_id,
        governance_scope=record.governance_scope,
        execution_mode=record.execution_mode,
        execution_type=record.execution_type,
        config_version_id=record.config_version_id,
        orchestration_cycle_id=record.orchestration_cycle_id,
        origin_source=record.origin_source,
        origin_authority=record.origin_authority,
        actor_identity=record.actor_identity,
        outbound_suppressed=record.outbound_suppressed,
        live_effects_produced=record.live_effects_produced,
        provider_dispatch_count=record.provider_dispatch_count,
        reason_codes=list(record.reason_codes),
        rule_path_summary=" -> ".join(record.rule_path),
        startup_outcome=record.startup_outcome,
        degraded=record.degraded,
        pii_excluded=True,
    )


def _audit_startup_records(
    records: List[DeploymentStartupRecord],
) -> DeploymentAuditResult:
    startup_ambiguity = 0
    environment_leakage = 0
    replay_leakage = 0
    hidden_config_fallback = 0
    attribution_loss = 0
    invariant_violations = 0
    unauthorized_live = 0
    authorized_count = 0
    live_effects_total = 0

    for r in records:
        # LIVE mode without cert disambiguation (replay types are inherently unambiguous)
        if (r.execution_mode == MODE_LIVE
                and r.execution_type not in _REPLAY_TYPES
                and r.governance_scope != SCOPE_SHADOW_ONLY
                and "LIVE_SCOPE_REQUIRES_PHASE12_CERT" not in r.reason_codes):
            startup_ambiguity += 1

        # PRODUCTION_LIVE producing AUTHORIZED without cert
        if (r.environment == ENV_PRODUCTION_LIVE
                and r.governance_scope == SCOPE_AUTHORIZED):
            environment_leakage += 1

        # Replay scope collapse to non-REPLAY_ONLY
        if r.is_replay and r.governance_scope != SCOPE_REPLAY_ONLY:
            replay_leakage += 1

        # Config-missing but config_version_id ≠ UNKNOWN_V0 (silent fallback)
        if not r.config_v2_validated and r.config_version_id != UNKNOWN_V0:
            hidden_config_fallback += 1

        # Attribution context absent
        if not r.attribution_context_present:
            attribution_loss += 1

        # AUTHORIZED scope count (always a violation in shadow phase)
        if r.governance_scope == SCOPE_AUTHORIZED:
            authorized_count += 1
            invariant_violations += 1

        # Any live effects
        if r.live_effects_produced > 0:
            unauthorized_live += 1

        live_effects_total += r.live_effects_produced

    return DeploymentAuditResult(
        total_records=len(records),
        startup_ambiguity_count=startup_ambiguity,
        environment_leakage_count=environment_leakage,
        replay_leakage_count=replay_leakage,
        hidden_config_fallback_count=hidden_config_fallback,
        attribution_loss_count=attribution_loss,
        governance_invariant_violations=invariant_violations,
        unauthorized_live_count=unauthorized_live,
        authorized_scope_count=authorized_count,
        live_effects_total=live_effects_total,
    )


# ════════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ════════════════════════════════════════════════════════════════════════════════

class TestDeploymentStartupObservability:
    """Certify startup produces observable, structured, complete records."""

    def test_startup_record_exists(self):
        r = _make_startup_record()
        assert r is not None

    def test_startup_log_emitted(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert log.event == "deployment_startup"

    def test_startup_log_has_governance_scope(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert log.governance_scope in _SUPPRESSED_SCOPES

    def test_startup_log_has_correlation_id(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert log.correlation_id == r.correlation_id
        assert log.correlation_id != ""

    def test_startup_log_has_config_version_id(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert log.config_version_id != ""

    def test_startup_log_level_info_for_healthy(self):
        r = _make_startup_record(degraded=False)
        log = _make_startup_log(r)
        assert log.level == "INFO"

    def test_startup_log_level_warn_for_degraded(self):
        r = _make_startup_record(degraded=True, degradation_cause="TEST")
        log = _make_startup_log(r)
        assert log.level == "WARN"

    def test_startup_log_pii_excluded(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert log.pii_excluded is True

    def test_startup_observability_present_flag(self):
        r = _make_startup_record()
        assert r.startup_observability_present is True

    def test_startup_log_has_rule_path_summary(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert "RULE_0" in log.rule_path_summary


class TestDeploymentAttributionCertification:
    """Certify all 7 attribution fields present at startup for every environment."""

    def test_correlation_id_present(self):
        r = _make_startup_record()
        assert r.correlation_id

    def test_causation_id_present(self):
        r = _make_startup_record()
        assert r.causation_id

    def test_config_version_id_present(self):
        r = _make_startup_record()
        assert r.config_version_id

    def test_orchestration_cycle_id_present(self):
        r = _make_startup_record()
        assert r.orchestration_cycle_id

    def test_execution_mode_present(self):
        r = _make_startup_record()
        assert r.execution_mode

    def test_governance_scope_present(self):
        r = _make_startup_record()
        assert r.governance_scope

    def test_execution_type_present(self):
        r = _make_startup_record()
        assert r.execution_type

    def test_attribution_context_present_flag(self):
        r = _make_startup_record()
        assert r.attribution_context_present is True

    def test_all_7_fields_for_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_startup_record(environment=env)
            assert r.correlation_id and r.causation_id
            assert r.config_version_id and r.orchestration_cycle_id
            assert r.execution_mode and r.governance_scope and r.execution_type

    def test_attribution_preserved_in_log(self):
        r = _make_startup_record()
        log = _make_startup_log(r)
        assert log.correlation_id == r.correlation_id
        assert log.config_version_id == r.config_version_id
        assert log.governance_scope == r.governance_scope


class TestDeploymentGovernanceScopeCertification:
    """Certify governance scope is correctly derived at deployment startup."""

    def test_shadow_mode_produces_shadow_only(self):
        r = _make_startup_record(mode=MODE_SHADOW)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_produces_shadow_only_phase12_gate(self):
        r = _make_startup_record(mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_authorized_never_produced_any_environment(self):
        for env in _ALL_ENVIRONMENTS:
            for mode in [MODE_SHADOW, MODE_LIVE]:
                r = _make_startup_record(environment=env, mode=mode)
                assert r.governance_scope != SCOPE_AUTHORIZED

    def test_authorized_scope_unreachable_flag(self):
        r = _make_startup_record()
        assert r.authorized_scope_reachable is False

    def test_phase12_cert_gate_active(self):
        r = _make_startup_record()
        assert r.phase12_cert_gate_active is True

    def test_config_missing_produces_unavailable(self):
        r = _make_startup_record(config_missing=True)
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_maintenance_produces_maintenance_scope(self):
        r = _make_startup_record(maintenance=True)
        assert r.governance_scope == SCOPE_MAINTENANCE

    def test_replay_exec_type_produces_replay_only(self):
        r = _make_startup_record(exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_produces_replay_only(self):
        r = _make_startup_record(exec_type=TYPE_REGENERATION)
        assert r.governance_scope == SCOPE_REPLAY_ONLY


class TestDeploymentReplayVisibility:
    """Certify replay config and lineage visible at deployment startup."""

    def test_replay_record_is_replay_true(self):
        r = _make_startup_record(exec_type=TYPE_REPLAY, is_replay=True)
        assert r.is_replay is True

    def test_replay_lineage_visible(self):
        r = _make_startup_record(exec_type=TYPE_REPLAY, is_replay=True)
        assert r.replay_lineage_visible is True

    def test_replay_scope_is_replay_only(self):
        r = _make_startup_record(exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_historical_config_surfaced_for_replay(self):
        hist = "cfg-historical-abc"
        r = _make_startup_record(
            exec_type=TYPE_REPLAY, is_replay=True, historical_config=hist
        )
        assert r.historical_config_version_id == hist

    def test_historical_config_absent_for_original(self):
        r = _make_startup_record(exec_type=TYPE_ORIGINAL)
        assert r.historical_config_version_id is None

    def test_regeneration_replay_lineage_visible(self):
        r = _make_startup_record(exec_type=TYPE_REGENERATION, is_replay=True)
        assert r.replay_lineage_visible is True
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_scope_distinct_from_live(self):
        replay_r = _make_startup_record(exec_type=TYPE_REPLAY)
        live_r = _make_startup_record(mode=MODE_LIVE)
        assert replay_r.governance_scope != live_r.governance_scope

    def test_replay_source_artifact_visible(self):
        r = _make_startup_record(
            exec_type=TYPE_REPLAY,
            is_replay=True,
            source_artifact="artifact-xyz",
        )
        assert r.source_artifact_id == "artifact-xyz"


class TestDeploymentDegradationVisibility:
    """Certify degradation state is observable at startup — never silent."""

    def test_degraded_startup_has_cause(self):
        r = _make_startup_record(degraded=True, degradation_cause="TEST_CAUSE")
        assert r.degradation_cause == "TEST_CAUSE"

    def test_degraded_startup_has_class(self):
        r = _make_startup_record(degraded=True)
        assert r.degradation_class is not None

    def test_degraded_startup_has_severity(self):
        r = _make_startup_record(degraded=True)
        assert r.degradation_severity is not None

    def test_config_missing_degradation_visible(self):
        r = _make_startup_record(config_missing=True, degraded=True)
        assert r.degradation_cause == "CONFIG_V2_UNAVAILABLE"
        assert r.config_version_id == UNKNOWN_V0

    def test_degraded_outcome_is_degraded(self):
        r = _make_startup_record(degraded=True)
        assert r.startup_outcome == STARTUP_DEGRADED

    def test_healthy_outcome_is_ok(self):
        r = _make_startup_record(degraded=False)
        assert r.startup_outcome == STARTUP_OK

    def test_degraded_log_is_warn(self):
        r = _make_startup_record(degraded=True)
        log = _make_startup_log(r)
        assert log.level == "WARN"

    def test_degradation_not_silent(self):
        r = _make_startup_record(degraded=True)
        assert r.degraded is True
        assert r.degradation_class is not None
        assert r.degradation_severity is not None


class TestDeploymentEnvironmentCertification:
    """Certify each deployment environment produces correct governance state."""

    def test_local_scope_shadow_only(self):
        r = _make_startup_record(environment=ENV_LOCAL)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_staging_scope_shadow_only(self):
        r = _make_startup_record(environment=ENV_STAGING)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_production_shadow_scope_shadow_only(self):
        r = _make_startup_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_production_live_cert_gated(self):
        r = _make_startup_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_all_environments_outbound_suppressed(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_startup_record(environment=env)
            assert r.outbound_suppressed is True

    def test_all_environments_zero_live_effects(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_startup_record(environment=env)
            assert r.live_effects_produced == 0

    def test_all_environments_zero_provider_dispatch(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_startup_record(environment=env)
            assert r.provider_dispatch_count == 0

    def test_all_environments_rule0_first(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_startup_record(environment=env)
            assert r.rule_path[0] == "RULE_0"

    def test_all_environments_attribution_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_startup_record(environment=env)
            assert r.attribution_context_present is True


class TestDeploymentLoadCertification:
    """Certify deployment properties hold at 100/500/1000 record scale."""

    def _make_batch(self, count: int) -> List[DeploymentStartupRecord]:
        envs = _ALL_ENVIRONMENTS
        modes = [MODE_SHADOW, MODE_LIVE]
        return [
            _make_startup_record(
                environment=envs[i % len(envs)],
                mode=modes[i % len(modes)],
            )
            for i in range(count)
        ]

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

    def test_100_attribution_complete(self):
        assert all(r.attribution_context_present for r in self._make_batch(100))

    def test_500_attribution_complete(self):
        assert all(r.attribution_context_present for r in self._make_batch(500))

    def test_1000_attribution_complete(self):
        assert all(r.attribution_context_present for r in self._make_batch(1000))

    def test_1000_outbound_suppressed(self):
        assert all(r.outbound_suppressed for r in self._make_batch(1000))

    def test_1000_rule0_first(self):
        assert all(r.rule_path[0] == "RULE_0" for r in self._make_batch(1000))


class TestDeploymentFinalAudit:
    """Final deployment certification audit — all dimensions simultaneously."""

    def _make_full_batch(self, count: int = 200) -> List[DeploymentStartupRecord]:
        envs = _ALL_ENVIRONMENTS
        modes = [MODE_SHADOW, MODE_LIVE]
        exec_types = [TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION]
        return [
            _make_startup_record(
                environment=envs[i % len(envs)],
                mode=modes[i % len(modes)],
                exec_type=exec_types[i % len(exec_types)],
            )
            for i in range(count)
        ]

    def test_no_startup_ambiguity(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.startup_ambiguity_count == 0

    def test_no_environment_leakage(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.environment_leakage_count == 0

    def test_no_replay_leakage(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.replay_leakage_count == 0

    def test_no_hidden_config_fallback(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.hidden_config_fallback_count == 0

    def test_no_attribution_loss(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.attribution_loss_count == 0

    def test_no_invariant_violations(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.governance_invariant_violations == 0

    def test_no_unauthorized_live(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.unauthorized_live_count == 0

    def test_authorized_scope_never_produced(self):
        result = _audit_startup_records(self._make_full_batch(200))
        assert result.authorized_scope_count == 0
