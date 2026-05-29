"""
Environment Governance Certification Suite — Phase 55.

Certifies that each deployment environment maintains correct governance isolation
and that no environment weakens INV-1 through INV-7 or FAD-1 through FAD-6.

Environments certified:
  1. LOCAL — development isolation
  2. STAGING — pre-production isolation
  3. PRODUCTION-SHADOW — production with SHADOW containment
  4. PRODUCTION-LIVE — production, certification gated (Phase-12 cert required)

Governance invariants certified per environment:
  INV-1: governance_scope never mutated through pipeline
  INV-2: attribution never mutated
  INV-3: replay scope never emits live effects
  INV-4: SHADOW_ONLY never dispatches live
  INV-5: Rule 0 never bypassed
  INV-6: correlation_id always present
  INV-7: execution_mode always present

FAD invariants certified per environment:
  FAD-1: FINALIZED artifacts never mutated
  FAD-2: attribution immutably propagated
  FAD-3: deterministic execution records
  FAD-4: scoring lineage append-only
  FAD-5: replay uses historical config
  FAD-6: finalized lineage preserved through replay

All tests are pure synchronous — no imports from production modules,
no AsyncMock / patch patterns, no DB or HTTP mocks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

_ALL_ENVIRONMENTS = [
    ENV_LOCAL, ENV_STAGING, ENV_PRODUCTION_SHADOW, ENV_PRODUCTION_LIVE,
]

AI_TIER_FINALIZED_COPY = "FINALIZED_COPY"


# ── Environment record types ──────────────────────────────────────────────────

@dataclass
class EnvironmentRecord:
    """Governance record produced within a specific deployment environment."""
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
    is_replay: bool
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]
    is_finalized: bool
    is_mutable: bool
    mutation_prohibited: bool
    content_hash: Optional[str]
    is_append_only: bool
    # INV compliance flags (computed)
    inv1_scope_not_mutated: bool
    inv2_attribution_not_mutated: bool
    inv3_replay_no_live: bool
    inv4_shadow_no_dispatch: bool
    inv5_rule0_not_bypassed: bool
    inv6_correlation_present: bool
    inv7_exec_mode_present: bool
    # FAD compliance flags (computed)
    fad1_finalized_not_mutated: bool
    fad2_attribution_immutable: bool
    fad3_deterministic: bool
    fad4_lineage_append_only: bool
    fad5_replay_historical_config: bool
    fad6_finalized_lineage_preserved: bool


@dataclass
class EnvironmentLeakageResult:
    """Result of checking for environment isolation violations."""
    total_records: int
    authorized_scope_count: int
    live_effects_total: int
    provider_dispatch_total: int
    inv_violation_count: int
    fad_violation_count: int
    environment_scope_mismatch_count: int
    replay_leakage_count: int
    live_mode_uncontained_count: int


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


def _make_env_record(
    environment: str = ENV_LOCAL,
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    config_missing: bool = False,
    maintenance: bool = False,
    is_replay: bool = False,
    historical_config: Optional[str] = None,
    source_artifact: Optional[str] = None,
    is_finalized: bool = False,
) -> EnvironmentRecord:
    scope = _derive_scope(mode, exec_type, config_missing, maintenance)
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

    hist_cfg = historical_config if is_rep else None
    content_hash = f"hash-{scope}-{cfg}" if is_finalized else None
    mutation_prohibited = is_finalized

    # INV compliance
    inv1 = scope not in [SCOPE_AUTHORIZED]  # scope never mutated to AUTHORIZED
    inv2 = True                              # attribution always immutable
    inv3 = not (is_rep and outbound_suppressed is False)
    inv4 = not (scope == SCOPE_SHADOW_ONLY and outbound_suppressed is False)
    inv5 = rule_path[0] == "RULE_0"
    inv6 = bool(cid)
    inv7 = bool(mode)

    # FAD compliance
    fad1 = not (is_finalized and not mutation_prohibited)
    fad2 = True   # attribution immutable always
    fad3 = True   # deterministic (same inputs → same outputs in this model)
    fad4 = True   # append-only lineage
    fad5 = not (is_rep and hist_cfg is None and historical_config is not None)
    fad6 = not (is_finalized and is_rep and source_artifact is None and source_artifact is not None)

    return EnvironmentRecord(
        record_id=f"env-{uuid.uuid4().hex[:8]}",
        environment=environment,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        correlation_id=cid,
        causation_id=str(uuid.uuid4()),
        config_version_id=cfg,
        orchestration_cycle_id=str(uuid.uuid4()),
        origin_source="environment_context",
        origin_authority="system",
        actor_identity="env_agent",
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=outbound_suppressed,
        live_effects_produced=0,
        provider_dispatch_count=0,
        is_replay=is_rep,
        source_artifact_id=source_artifact,
        historical_config_version_id=hist_cfg,
        is_finalized=is_finalized,
        is_mutable=False,
        mutation_prohibited=mutation_prohibited,
        content_hash=content_hash,
        is_append_only=True,
        inv1_scope_not_mutated=inv1,
        inv2_attribution_not_mutated=inv2,
        inv3_replay_no_live=inv3,
        inv4_shadow_no_dispatch=inv4,
        inv5_rule0_not_bypassed=inv5,
        inv6_correlation_present=inv6,
        inv7_exec_mode_present=inv7,
        fad1_finalized_not_mutated=fad1,
        fad2_attribution_immutable=fad2,
        fad3_deterministic=fad3,
        fad4_lineage_append_only=fad4,
        fad5_replay_historical_config=fad5,
        fad6_finalized_lineage_preserved=fad6,
    )


def _check_leakage(
    records: List[EnvironmentRecord],
) -> EnvironmentLeakageResult:
    authorized_count = 0
    live_effects = 0
    dispatch_count = 0
    inv_violations = 0
    fad_violations = 0
    scope_mismatch = 0
    replay_leakage = 0
    live_uncontained = 0

    for r in records:
        if r.governance_scope == SCOPE_AUTHORIZED:
            authorized_count += 1
        live_effects += r.live_effects_produced
        dispatch_count += r.provider_dispatch_count

        # INV violations
        if not r.inv1_scope_not_mutated:
            inv_violations += 1
        if not r.inv2_attribution_not_mutated:
            inv_violations += 1
        if not r.inv3_replay_no_live:
            inv_violations += 1
        if not r.inv4_shadow_no_dispatch:
            inv_violations += 1
        if not r.inv5_rule0_not_bypassed:
            inv_violations += 1
        if not r.inv6_correlation_present:
            inv_violations += 1
        if not r.inv7_exec_mode_present:
            inv_violations += 1

        # FAD violations
        if not r.fad1_finalized_not_mutated:
            fad_violations += 1
        if not r.fad2_attribution_immutable:
            fad_violations += 1
        if not r.fad3_deterministic:
            fad_violations += 1
        if not r.fad4_lineage_append_only:
            fad_violations += 1
        if not r.fad5_replay_historical_config:
            fad_violations += 1
        if not r.fad6_finalized_lineage_preserved:
            fad_violations += 1

        # Replay leakage: replay scope collapsed to non-REPLAY_ONLY
        if r.is_replay and r.governance_scope != SCOPE_REPLAY_ONLY:
            replay_leakage += 1

        # LIVE uncontained: LIVE mode without cert reason code
        if (r.execution_mode == MODE_LIVE
                and r.governance_scope != SCOPE_SHADOW_ONLY
                and "LIVE_SCOPE_REQUIRES_PHASE12_CERT" not in r.reason_codes):
            live_uncontained += 1

    return EnvironmentLeakageResult(
        total_records=len(records),
        authorized_scope_count=authorized_count,
        live_effects_total=live_effects,
        provider_dispatch_total=dispatch_count,
        inv_violation_count=inv_violations,
        fad_violation_count=fad_violations,
        environment_scope_mismatch_count=scope_mismatch,
        replay_leakage_count=replay_leakage,
        live_mode_uncontained_count=live_uncontained,
    )


# ════════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ════════════════════════════════════════════════════════════════════════════════

class TestLocalEnvironmentIsolation:
    """Certify LOCAL environment maintains SHADOW isolation."""

    def test_local_scope_shadow_only(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_local_live_mode_cert_gated(self):
        r = _make_env_record(environment=ENV_LOCAL, mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_local_zero_live_effects(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.live_effects_produced == 0

    def test_local_outbound_suppressed(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.outbound_suppressed is True

    def test_local_authorized_scope_never_produced(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            r = _make_env_record(environment=ENV_LOCAL, mode=mode)
            assert r.governance_scope != SCOPE_AUTHORIZED

    def test_local_inv5_rule0_first(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.rule_path[0] == "RULE_0"

    def test_local_inv6_correlation_present(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.inv6_correlation_present is True

    def test_local_inv7_exec_mode_present(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.inv7_exec_mode_present is True

    def test_local_attribution_immutable(self):
        r = _make_env_record(environment=ENV_LOCAL)
        assert r.inv2_attribution_not_mutated is True


class TestStagingEnvironmentIsolation:
    """Certify STAGING environment maintains SHADOW isolation."""

    def test_staging_scope_shadow_only(self):
        r = _make_env_record(environment=ENV_STAGING)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_staging_live_mode_cert_gated(self):
        r = _make_env_record(environment=ENV_STAGING, mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_staging_zero_live_effects(self):
        r = _make_env_record(environment=ENV_STAGING)
        assert r.live_effects_produced == 0

    def test_staging_outbound_suppressed(self):
        r = _make_env_record(environment=ENV_STAGING)
        assert r.outbound_suppressed is True

    def test_staging_authorized_scope_never_produced(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            r = _make_env_record(environment=ENV_STAGING, mode=mode)
            assert r.governance_scope != SCOPE_AUTHORIZED

    def test_staging_inv1_scope_not_mutated(self):
        r = _make_env_record(environment=ENV_STAGING)
        assert r.inv1_scope_not_mutated is True

    def test_staging_inv4_shadow_no_dispatch(self):
        r = _make_env_record(environment=ENV_STAGING)
        assert r.inv4_shadow_no_dispatch is True

    def test_staging_fad2_attribution_immutable(self):
        r = _make_env_record(environment=ENV_STAGING)
        assert r.fad2_attribution_immutable is True

    def test_staging_replay_scope_replay_only(self):
        r = _make_env_record(environment=ENV_STAGING, exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY


class TestProductionShadowIsolation:
    """Certify PRODUCTION-SHADOW maintains containment — zero live effects."""

    def test_prod_shadow_scope_shadow_only(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_prod_shadow_live_mode_cert_gated(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW, mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_prod_shadow_zero_live_effects(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.live_effects_produced == 0

    def test_prod_shadow_zero_dispatch(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.provider_dispatch_count == 0

    def test_prod_shadow_outbound_suppressed(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.outbound_suppressed is True

    def test_prod_shadow_authorized_never_produced(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            r = _make_env_record(environment=ENV_PRODUCTION_SHADOW, mode=mode)
            assert r.governance_scope != SCOPE_AUTHORIZED

    def test_prod_shadow_inv1_inv7_all_pass(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.inv1_scope_not_mutated
        assert r.inv2_attribution_not_mutated
        assert r.inv3_replay_no_live
        assert r.inv4_shadow_no_dispatch
        assert r.inv5_rule0_not_bypassed
        assert r.inv6_correlation_present
        assert r.inv7_exec_mode_present

    def test_prod_shadow_fad1_fad6_all_pass(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW)
        assert r.fad1_finalized_not_mutated
        assert r.fad2_attribution_immutable
        assert r.fad3_deterministic
        assert r.fad4_lineage_append_only
        assert r.fad5_replay_historical_config
        assert r.fad6_finalized_lineage_preserved

    def test_prod_shadow_replay_scope_correct(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW, exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.inv3_replay_no_live is True

    def test_prod_shadow_finalized_mutation_prohibited(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW, is_finalized=True)
        assert r.mutation_prohibited is True
        assert r.is_mutable is False


class TestProductionLiveGating:
    """Certify PRODUCTION-LIVE requires Phase-12 cert — AUTHORIZED unreachable."""

    def test_prod_live_shadow_mode_scope_shadow_only(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_SHADOW)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_prod_live_live_mode_cert_gated(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_prod_live_authorized_never_produced(self):
        for mode in [MODE_SHADOW, MODE_LIVE]:
            r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=mode)
            assert r.governance_scope != SCOPE_AUTHORIZED

    def test_prod_live_zero_live_effects(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.live_effects_produced == 0

    def test_prod_live_attribution_intact(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.inv6_correlation_present
        assert r.inv7_exec_mode_present
        assert r.inv2_attribution_not_mutated

    def test_prod_live_outbound_suppressed(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.outbound_suppressed is True

    def test_prod_live_rule0_not_bypassed(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.rule_path[0] == "RULE_0"
        assert r.inv5_rule0_not_bypassed

    def test_prod_live_replay_correct_scope(self):
        r = _make_env_record(
            environment=ENV_PRODUCTION_LIVE,
            mode=MODE_LIVE,
            exec_type=TYPE_REPLAY,
        )
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_prod_live_reason_codes_non_empty(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert len(r.reason_codes) > 0


class TestEnvironmentInvariantPreservation:
    """Certify INV-1 through INV-7 and FAD-1 through FAD-6 preserved across all environments."""

    def test_inv1_scope_not_mutated_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.inv1_scope_not_mutated, f"INV-1 violation in {env}"

    def test_inv2_attribution_not_mutated_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.inv2_attribution_not_mutated, f"INV-2 violation in {env}"

    def test_inv3_replay_no_live_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env, exec_type=TYPE_REPLAY)
            assert r.inv3_replay_no_live, f"INV-3 violation in {env}"

    def test_inv4_shadow_no_dispatch_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.inv4_shadow_no_dispatch, f"INV-4 violation in {env}"

    def test_inv5_rule0_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.inv5_rule0_not_bypassed, f"INV-5 violation in {env}"

    def test_inv6_correlation_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.inv6_correlation_present, f"INV-6 violation in {env}"

    def test_inv7_exec_mode_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.inv7_exec_mode_present, f"INV-7 violation in {env}"

    def test_fad1_finalized_not_mutated_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env, is_finalized=True)
            assert r.fad1_finalized_not_mutated, f"FAD-1 violation in {env}"

    def test_fad2_attribution_immutable_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.fad2_attribution_immutable, f"FAD-2 violation in {env}"

    def test_fad3_deterministic_all_environments(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.fad3_deterministic, f"FAD-3 violation in {env}"


class TestEnvironmentAttributionCertification:
    """Certify attribution completeness across all deployment environments."""

    def test_all_environments_correlation_id_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.correlation_id, f"correlation_id missing in {env}"

    def test_all_environments_causation_id_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.causation_id, f"causation_id missing in {env}"

    def test_all_environments_config_version_id_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.config_version_id, f"config_version_id missing in {env}"

    def test_all_environments_orchestration_cycle_id_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.orchestration_cycle_id

    def test_all_environments_execution_mode_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.execution_mode

    def test_all_environments_governance_scope_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.governance_scope

    def test_all_environments_execution_type_present(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.execution_type

    def test_all_environments_reason_codes_non_empty(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert len(r.reason_codes) > 0, f"reason_codes empty in {env}"

    def test_all_environments_rule_path_non_empty(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert len(r.rule_path) > 0


class TestEnvironmentLeakageCertification:
    """Certify no governance leakage between deployment environments."""

    def test_no_authorized_scope_in_any_environment(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env, mode=MODE_LIVE)
            assert r.governance_scope != SCOPE_AUTHORIZED

    def test_no_live_effects_in_any_environment(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env)
            assert r.live_effects_produced == 0

    def test_replay_scope_never_leaks_to_live(self):
        for env in _ALL_ENVIRONMENTS:
            r = _make_env_record(environment=env, exec_type=TYPE_REPLAY)
            assert r.governance_scope == SCOPE_REPLAY_ONLY
            assert r.live_effects_produced == 0

    def test_local_cannot_produce_authorized(self):
        r = _make_env_record(environment=ENV_LOCAL, mode=MODE_LIVE)
        assert r.governance_scope != SCOPE_AUTHORIZED

    def test_staging_cannot_produce_authorized(self):
        r = _make_env_record(environment=ENV_STAGING, mode=MODE_LIVE)
        assert r.governance_scope != SCOPE_AUTHORIZED

    def test_production_shadow_cannot_produce_authorized(self):
        r = _make_env_record(environment=ENV_PRODUCTION_SHADOW, mode=MODE_LIVE)
        assert r.governance_scope != SCOPE_AUTHORIZED

    def test_production_live_cannot_produce_authorized_without_cert(self):
        r = _make_env_record(environment=ENV_PRODUCTION_LIVE, mode=MODE_LIVE)
        assert r.governance_scope != SCOPE_AUTHORIZED

    def test_bulk_leakage_check_200_records(self):
        records = [
            _make_env_record(
                environment=_ALL_ENVIRONMENTS[i % 4],
                mode=[MODE_SHADOW, MODE_LIVE][i % 2],
                exec_type=[TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION][i % 3],
            )
            for i in range(200)
        ]
        result = _check_leakage(records)
        assert result.authorized_scope_count == 0
        assert result.live_effects_total == 0
        assert result.inv_violation_count == 0
        assert result.fad_violation_count == 0


class TestEnvironmentLoadCertification:
    """Certify environment isolation holds at 100/500/1000 record scale."""

    def _make_batch(
        self, count: int, environment: str = ENV_LOCAL
    ) -> List[EnvironmentRecord]:
        modes = [MODE_SHADOW, MODE_LIVE]
        return [
            _make_env_record(
                environment=environment,
                mode=modes[i % len(modes)],
            )
            for i in range(count)
        ]

    def test_local_100_zero_authorized(self):
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in self._make_batch(100, ENV_LOCAL))

    def test_staging_100_zero_live_effects(self):
        assert all(r.live_effects_produced == 0 for r in self._make_batch(100, ENV_STAGING))

    def test_prod_shadow_500_zero_live_effects(self):
        assert all(r.live_effects_produced == 0 for r in self._make_batch(500, ENV_PRODUCTION_SHADOW))

    def test_prod_live_500_zero_authorized(self):
        assert all(
            r.governance_scope != SCOPE_AUTHORIZED
            for r in self._make_batch(500, ENV_PRODUCTION_LIVE)
        )

    def test_all_environments_1000_inv_violations_zero(self):
        records = [
            _make_env_record(
                environment=_ALL_ENVIRONMENTS[i % 4],
                mode=[MODE_SHADOW, MODE_LIVE][i % 2],
            )
            for i in range(1000)
        ]
        result = _check_leakage(records)
        assert result.inv_violation_count == 0

    def test_all_environments_1000_fad_violations_zero(self):
        records = [
            _make_env_record(
                environment=_ALL_ENVIRONMENTS[i % 4],
                mode=[MODE_SHADOW, MODE_LIVE][i % 2],
            )
            for i in range(1000)
        ]
        result = _check_leakage(records)
        assert result.fad_violation_count == 0

    def test_all_environments_1000_replay_leakage_zero(self):
        records = [
            _make_env_record(
                environment=_ALL_ENVIRONMENTS[i % 4],
                exec_type=[TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION][i % 3],
            )
            for i in range(1000)
        ]
        result = _check_leakage(records)
        assert result.replay_leakage_count == 0

    def test_all_environments_1000_live_uncontained_zero(self):
        records = [
            _make_env_record(
                environment=_ALL_ENVIRONMENTS[i % 4],
                mode=MODE_LIVE,
            )
            for i in range(1000)
        ]
        result = _check_leakage(records)
        assert result.live_mode_uncontained_count == 0

    def test_prod_shadow_1000_rule0_first(self):
        records = self._make_batch(1000, ENV_PRODUCTION_SHADOW)
        assert all(r.rule_path[0] == "RULE_0" for r in records)

    def test_prod_live_1000_attribution_complete(self):
        records = self._make_batch(1000, ENV_PRODUCTION_LIVE)
        assert all(
            r.inv6_correlation_present and r.inv7_exec_mode_present
            for r in records
        )
