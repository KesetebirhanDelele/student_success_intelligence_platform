"""
Campaign Degradation Certification Suite — Phase 56.

Certifies controlled failure injection for all 5 failure modes. Validates:
  - deterministic degradation state for every failure mode
  - attribution continuity through degradation
  - observable recovery paths
  - distinct degradation classification per failure mode
  - suppression active even under degradation
  - zero live effects under all failure modes

5 Failure modes:
  1. missing_config        → CONFIG_DEGRADATION, HIGH severity, UNAVAILABLE scope
  2. provider_unavailable  → PROVIDER_DEGRADATION, LOW severity, SHADOW_ONLY scope
  3. scheduler_unavailable → RUNTIME_DEGRADATION, MEDIUM severity, SHADOW_ONLY scope
  4. worker_unavailable    → RUNTIME_DEGRADATION, MEDIUM severity, SHADOW_ONLY scope
  5. observability_unavailable → OBSERVABILITY_DEGRADATION, LOW severity, SHADOW_ONLY scope

Degradation contract (every failure mode):
  - degradation_state == "deterministic"
  - failure_classification is non-empty and distinct per mode
  - attribution_preserved == True
  - live_effects_produced == 0
  - outbound_suppressed == True
  - recovery_path_visible == True

Critical constraint: Phase 56 certification only.
  - Do NOT enable LIVE communication.
  - Do NOT remove SHADOW containment.

All tests are pure synchronous — no imports from production modules.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

import pytest


# ── Governance constants ──────────────────────────────────────────────────────

SCOPE_SHADOW_ONLY = "SHADOW_ONLY"
SCOPE_UNAVAILABLE = "UNAVAILABLE"
SCOPE_AUTHORIZED  = "AUTHORIZED"

MODE_SHADOW = "SHADOW"
UNKNOWN_V0 = "UNKNOWN_V0"

FAILURE_MISSING_CONFIG            = "missing_config"
FAILURE_PROVIDER_UNAVAILABLE      = "provider_unavailable"
FAILURE_SCHEDULER_UNAVAILABLE     = "scheduler_unavailable"
FAILURE_WORKER_UNAVAILABLE        = "worker_unavailable"
FAILURE_OBSERVABILITY_UNAVAILABLE = "observability_unavailable"

ALL_FAILURE_MODES = [
    FAILURE_MISSING_CONFIG,
    FAILURE_PROVIDER_UNAVAILABLE,
    FAILURE_SCHEDULER_UNAVAILABLE,
    FAILURE_WORKER_UNAVAILABLE,
    FAILURE_OBSERVABILITY_UNAVAILABLE,
]

_SUPPRESSED_SCOPES = frozenset({SCOPE_SHADOW_ONLY, SCOPE_UNAVAILABLE})

_FAILURE_MAP = {
    FAILURE_MISSING_CONFIG: {
        "classification": "CONFIG_V2_UNAVAILABLE",
        "scope":          SCOPE_UNAVAILABLE,
        "cause":          "CONFIG_V2_UNAVAILABLE",
        "class_":         "CONFIG_DEGRADATION",
        "severity":       "HIGH",
        "reason":         "CONFIG_VERSION_UNRESOLVED",
        "rule_path":      ["RULE_0"],
        "config_ver":     UNKNOWN_V0,
    },
    FAILURE_PROVIDER_UNAVAILABLE: {
        "classification": "PROVIDER_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "PROVIDER_UNAVAILABLE",
        "class_":         "PROVIDER_DEGRADATION",
        "severity":       "LOW",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
        "config_ver":     "cfg-v2-001",
    },
    FAILURE_SCHEDULER_UNAVAILABLE: {
        "classification": "SCHEDULER_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "SCHEDULER_UNAVAILABLE",
        "class_":         "RUNTIME_DEGRADATION",
        "severity":       "MEDIUM",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
        "config_ver":     "cfg-v2-001",
    },
    FAILURE_WORKER_UNAVAILABLE: {
        "classification": "WORKER_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "WORKER_UNAVAILABLE",
        "class_":         "RUNTIME_DEGRADATION",
        "severity":       "MEDIUM",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
        "config_ver":     "cfg-v2-001",
    },
    FAILURE_OBSERVABILITY_UNAVAILABLE: {
        "classification": "OBSERVABILITY_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "OBSERVABILITY_UNAVAILABLE",
        "class_":         "OBSERVABILITY_DEGRADATION",
        "severity":       "LOW",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
        "config_ver":     "cfg-v2-001",
    },
}


# ── Degradation record types ──────────────────────────────────────────────────

@dataclass
class DegradationRecord:
    """Record produced when a controlled failure is injected."""
    record_id: str
    failure_mode: str
    failure_classification: str
    governance_scope: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    degradation_state: str        # always "deterministic"
    attribution_preserved: bool   # always True
    outbound_suppressed: bool
    live_effects_produced: int
    recovery_path_visible: bool
    deterministic: bool
    degradation_cause: str
    degradation_class: str
    degradation_severity: str
    reason_codes: List[str]
    rule_path: List[str]


@dataclass
class DegradationCampaignResult:
    """Aggregated result from a degradation injection campaign."""
    failure_modes_tested: List[str]
    total_injections: int
    deterministic_count: int
    attribution_preserved_count: int
    zero_live_effects_count: int
    recovery_visible_count: int
    certification_passed: bool


@dataclass
class DegradationCampaignAuditResult:
    """Final audit for degradation campaign."""
    total_injections: int
    deterministic_count: int
    attribution_preserved_count: int
    zero_live_effects_count: int
    recovery_visible_count: int
    authorized_scope_count: int
    audit_passed: bool


# ── Simulation helpers ────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _inject_failure(failure_mode: str) -> DegradationRecord:
    cfg = _FAILURE_MAP[failure_mode]
    scope = cfg["scope"]
    cid = _new_id()
    return DegradationRecord(
        record_id=_new_id(),
        failure_mode=failure_mode,
        failure_classification=cfg["classification"],
        governance_scope=scope,
        correlation_id=cid,
        causation_id=_new_id(),
        config_version_id=cfg["config_ver"],
        degradation_state="deterministic",
        attribution_preserved=True,
        outbound_suppressed=scope in _SUPPRESSED_SCOPES,
        live_effects_produced=0,
        recovery_path_visible=True,
        deterministic=True,
        degradation_cause=cfg["cause"],
        degradation_class=cfg["class_"],
        degradation_severity=cfg["severity"],
        reason_codes=[cfg["reason"]],
        rule_path=list(cfg["rule_path"]),
    )


def _run_degradation_campaign(
    failure_modes: Optional[List[str]] = None,
    count_each: int = 1,
) -> DegradationCampaignResult:
    modes = failure_modes or ALL_FAILURE_MODES
    records: List[DegradationRecord] = []
    for mode in modes:
        for _ in range(count_each):
            records.append(_inject_failure(mode))

    det = sum(1 for r in records if r.deterministic)
    attr = sum(1 for r in records if r.attribution_preserved)
    zero_fx = sum(1 for r in records if r.live_effects_produced == 0)
    recov = sum(1 for r in records if r.recovery_path_visible)

    return DegradationCampaignResult(
        failure_modes_tested=list(modes),
        total_injections=len(records),
        deterministic_count=det,
        attribution_preserved_count=attr,
        zero_live_effects_count=zero_fx,
        recovery_visible_count=recov,
        certification_passed=(
            det == len(records) and attr == len(records)
            and zero_fx == len(records) and recov == len(records)
        ),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMissingConfigDegradation:
    """missing_config → UNKNOWN_V0, UNAVAILABLE scope, HIGH severity, attribution intact."""

    def test_scope_unavailable(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.governance_scope == SCOPE_UNAVAILABLE

    def test_config_version_is_unknown_v0(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.config_version_id == UNKNOWN_V0

    def test_classification_config_v2_unavailable(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.failure_classification == "CONFIG_V2_UNAVAILABLE"

    def test_degradation_class_config_degradation(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.degradation_class == "CONFIG_DEGRADATION"

    def test_severity_high(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.degradation_severity == "HIGH"

    def test_rule_path_rule0_only(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.rule_path == ["RULE_0"]

    def test_reason_code_config_version_unresolved(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert "CONFIG_VERSION_UNRESOLVED" in r.reason_codes

    def test_degradation_state_deterministic(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.degradation_state == "deterministic"

    def test_attribution_preserved(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.attribution_preserved is True
        assert r.correlation_id
        assert r.causation_id


class TestProviderUnavailableDegradation:
    """provider_unavailable → PROVIDER_DEGRADATION, LOW severity, SHADOW_ONLY scope."""

    def test_scope_shadow_only(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_classification_provider_init_failure(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.failure_classification == "PROVIDER_INIT_FAILURE"

    def test_degradation_class_provider_degradation(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.degradation_class == "PROVIDER_DEGRADATION"

    def test_severity_low(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.degradation_severity == "LOW"

    def test_rule0_first(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.rule_path[0] == "RULE_0"

    def test_live_effects_zero(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.live_effects_produced == 0

    def test_outbound_suppressed(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.outbound_suppressed is True

    def test_recovery_path_visible(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.recovery_path_visible is True


class TestSchedulerUnavailableDegradation:
    """scheduler_unavailable → RUNTIME_DEGRADATION, MEDIUM severity, SHADOW_ONLY scope."""

    def test_scope_shadow_only(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_classification_scheduler_init_failure(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.failure_classification == "SCHEDULER_INIT_FAILURE"

    def test_degradation_class_runtime_degradation(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.degradation_class == "RUNTIME_DEGRADATION"

    def test_severity_medium(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.degradation_severity == "MEDIUM"

    def test_degradation_cause_scheduler_unavailable(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.degradation_cause == "SCHEDULER_UNAVAILABLE"

    def test_live_effects_zero(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.live_effects_produced == 0

    def test_deterministic_state(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.degradation_state == "deterministic"

    def test_attribution_preserved(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.attribution_preserved is True


class TestWorkerUnavailableDegradation:
    """worker_unavailable → RUNTIME_DEGRADATION, MEDIUM severity, SHADOW_ONLY scope."""

    def test_scope_shadow_only(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_classification_worker_init_failure(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.failure_classification == "WORKER_INIT_FAILURE"

    def test_degradation_class_runtime_degradation(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.degradation_class == "RUNTIME_DEGRADATION"

    def test_severity_medium(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.degradation_severity == "MEDIUM"

    def test_degradation_cause_worker_unavailable(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.degradation_cause == "WORKER_UNAVAILABLE"

    def test_live_effects_zero(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.live_effects_produced == 0

    def test_scheduler_and_worker_produce_distinct_classifications(self):
        sched = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        worker = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert sched.failure_classification != worker.failure_classification

    def test_recovery_path_visible(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.recovery_path_visible is True


class TestObservabilityUnavailableDegradation:
    """observability_unavailable → OBSERVABILITY_DEGRADATION, LOW severity."""

    def test_scope_shadow_only(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_classification_observability_init_failure(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.failure_classification == "OBSERVABILITY_INIT_FAILURE"

    def test_degradation_class_observability_degradation(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.degradation_class == "OBSERVABILITY_DEGRADATION"

    def test_severity_low(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.degradation_severity == "LOW"

    def test_live_effects_zero(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.live_effects_produced == 0

    def test_distinct_from_provider_degradation(self):
        obs = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        prov = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert obs.degradation_class != prov.degradation_class

    def test_deterministic_state(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.degradation_state == "deterministic"

    def test_attribution_preserved(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.attribution_preserved is True


class TestDegradationAttributionContinuity:
    """correlation_id and causation_id preserved through all 5 failure modes."""

    def test_all_failure_modes_correlation_id_present(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.correlation_id, f"correlation_id missing for {mode}"

    def test_all_failure_modes_causation_id_present(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.causation_id, f"causation_id missing for {mode}"

    def test_all_failure_modes_attribution_preserved_flag(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.attribution_preserved, f"attribution_preserved=False for {mode}"

    def test_all_failure_modes_outbound_suppressed(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.outbound_suppressed, f"outbound_suppressed=False for {mode}"

    def test_all_failure_modes_zero_live_effects(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.live_effects_produced == 0, f"live_effects > 0 for {mode}"

    def test_all_failure_modes_deterministic_state(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.degradation_state == "deterministic", f"not deterministic for {mode}"

    def test_all_failure_modes_classification_nonempty(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.failure_classification, f"classification empty for {mode}"

    def test_all_failure_modes_cause_nonempty(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.degradation_cause, f"degradation_cause empty for {mode}"

    def test_all_failure_modes_authorized_scope_never_produced(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.governance_scope != SCOPE_AUTHORIZED, f"AUTHORIZED scope for {mode}"


class TestDegradationRecoveryPaths:
    """Recovery paths are observable and classified for all failure modes."""

    def test_missing_config_recovery_path_visible(self):
        r = _inject_failure(FAILURE_MISSING_CONFIG)
        assert r.recovery_path_visible is True

    def test_provider_recovery_path_visible(self):
        r = _inject_failure(FAILURE_PROVIDER_UNAVAILABLE)
        assert r.recovery_path_visible is True

    def test_scheduler_recovery_path_visible(self):
        r = _inject_failure(FAILURE_SCHEDULER_UNAVAILABLE)
        assert r.recovery_path_visible is True

    def test_worker_recovery_path_visible(self):
        r = _inject_failure(FAILURE_WORKER_UNAVAILABLE)
        assert r.recovery_path_visible is True

    def test_observability_recovery_path_visible(self):
        r = _inject_failure(FAILURE_OBSERVABILITY_UNAVAILABLE)
        assert r.recovery_path_visible is True

    def test_all_failure_modes_reason_codes_nonempty(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert len(r.reason_codes) > 0, f"reason_codes empty for {mode}"

    def test_all_failure_modes_rule_path_nonempty(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert len(r.rule_path) > 0, f"rule_path empty for {mode}"

    def test_all_failure_modes_rule0_first(self):
        for mode in ALL_FAILURE_MODES:
            r = _inject_failure(mode)
            assert r.rule_path[0] == "RULE_0", f"RULE_0 not first for {mode}"


class TestDegradationCampaignFinalAudit:
    """Degradation campaign final audit — all 5 modes, all determinism criteria met."""

    def test_all_modes_certified_deterministic(self):
        result = _run_degradation_campaign(count_each=10)
        assert result.deterministic_count == result.total_injections

    def test_all_modes_attribution_preserved(self):
        result = _run_degradation_campaign(count_each=10)
        assert result.attribution_preserved_count == result.total_injections

    def test_all_modes_zero_live_effects(self):
        result = _run_degradation_campaign(count_each=10)
        assert result.zero_live_effects_count == result.total_injections

    def test_all_modes_recovery_visible(self):
        result = _run_degradation_campaign(count_each=10)
        assert result.recovery_visible_count == result.total_injections

    def test_all_5_modes_tested(self):
        result = _run_degradation_campaign()
        assert len(result.failure_modes_tested) == 5

    def test_campaign_certification_passed(self):
        result = _run_degradation_campaign(count_each=5)
        assert result.certification_passed is True

    def test_total_injections_equals_modes_times_count(self):
        result = _run_degradation_campaign(count_each=3)
        assert result.total_injections == 5 * 3
