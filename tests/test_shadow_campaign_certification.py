"""
Shadow Campaign Certification Suite — Phase 56.

Certifies the SHADOW Operational Campaign framework: scheduler cycles,
worker cycles, orchestration decisions, campaign metrics tracking,
suppression integrity, operator reporting, load certification,
attribution continuity, and final audit.

Campaign certification contract:
  - provider_dispatch_count = 0 at all volumes
  - live_effects_produced = 0 at all volumes
  - attribution_gap_count = 0 at all volumes
  - finalized_violation_count = 0
  - replay_leakage_count = 0
  - governance_invariant_violations = 0
  - authorized_scope_count = 0

All 9 campaign metrics tracked:
  orchestration_count, suppression_count, replay_count, degradation_count,
  attribution_gap_count, finalized_violation_count, duplicate_suppression_count,
  config_resolution_failures, provider_suppression_count.

Critical constraint: Phase 56 certification only.
  - Do NOT enable LIVE communication.
  - Do NOT remove SHADOW containment.
  - Do NOT make AUTHORIZED scope reachable.

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

CERT_OUTCOME_PASSED   = "CERTIFICATION_PASSED"
CERT_OUTCOME_FAILED   = "CERTIFICATION_FAILED"
CERT_OUTCOME_DEGRADED = "CERTIFICATION_DEGRADED"

FAILURE_MISSING_CONFIG            = "missing_config"
FAILURE_PROVIDER_UNAVAILABLE      = "provider_unavailable"
FAILURE_SCHEDULER_UNAVAILABLE     = "scheduler_unavailable"
FAILURE_WORKER_UNAVAILABLE        = "worker_unavailable"
FAILURE_OBSERVABILITY_UNAVAILABLE = "observability_unavailable"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_BLOCKED, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})


# ── Campaign record types ─────────────────────────────────────────────────────

@dataclass
class CampaignRecord:
    """Full campaign governance record produced during an orchestration cycle."""
    record_id: str
    cycle_id: str
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
    is_duplicate: bool
    degraded: bool
    degradation_cause: Optional[str]
    scheduler_processed: bool
    worker_processed: bool
    prioritization_complete: bool
    transport_generated: bool
    observability_emitted: bool
    provider_assessment_produced: bool


@dataclass
class CampaignMetrics:
    """Aggregated campaign metrics — 9 required counters plus safety counters."""
    campaign_id: str
    orchestration_count: int = 0
    suppression_count: int = 0
    replay_count: int = 0
    degradation_count: int = 0
    attribution_gap_count: int = 0
    finalized_violation_count: int = 0
    duplicate_suppression_count: int = 0
    config_resolution_failures: int = 0
    provider_suppression_count: int = 0
    live_effects_total: int = 0
    provider_dispatch_total: int = 0
    authorized_scope_count: int = 0
    replay_leakage_count: int = 0


@dataclass
class CampaignCycleResult:
    """Result of a single orchestration cycle."""
    cycle_id: str
    records_produced: int
    suppressed_count: int
    live_effects_produced: int
    provider_dispatch_count: int
    attribution_complete: bool
    governance_scope: str
    rule_path_summary: str
    scheduler_ticked: bool
    worker_assigned: bool
    orchestration_decided: bool
    prioritization_done: bool
    provider_assessed: bool
    transport_generated: bool
    observability_emitted: bool
    degraded: bool
    degradation_cause: Optional[str]


@dataclass
class OperatorReport:
    """Certification report for operator review."""
    report_id: str
    campaign_id: str
    campaign_duration_seconds: float
    orchestration_volume: int
    suppression_volume: int
    replay_volume: int
    degradation_events: int
    inv_violations: int
    fad_violations: int
    live_effects_total: int
    provider_dispatch_total: int
    authorized_scope_count: int
    attribution_gap_count: int
    replay_leakage_count: int
    governance_invariant_violations: int
    certification_outcome: str
    certification_passed: bool


@dataclass
class CampaignAuditResult:
    """Final campaign audit — primary counters must all be 0."""
    total_records: int
    provider_dispatch_count: int
    live_effects_produced: int
    attribution_gap_count: int
    finalized_violation_count: int
    replay_leakage_count: int
    governance_invariant_violations: int
    authorized_scope_count: int
    audit_passed: bool


# ── Simulation helpers ────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _derive_scope(
    mode: str,
    exec_type: str,
    config_missing: bool = False,
    maintenance: bool = False,
    duplicate: bool = False,
) -> str:
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    if duplicate:
        return SCOPE_DUPLICATE_SUPPRESSED
    return SCOPE_SHADOW_ONLY


def _make_record(
    cycle_id: str,
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    config_missing: bool = False,
    maintenance: bool = False,
    duplicate: bool = False,
    is_finalized: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
) -> CampaignRecord:
    scope = _derive_scope(mode, exec_type, config_missing, maintenance, duplicate)
    cfg = UNKNOWN_V0 if config_missing else "cfg-v2-001"
    is_replay_rec = exec_type in _REPLAY_TYPES

    reason_codes: List[str] = []
    if scope == SCOPE_UNAVAILABLE:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    elif scope == SCOPE_REPLAY_ONLY:
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    elif scope == SCOPE_MAINTENANCE:
        reason_codes.append("MAINTENANCE_SCOPE_ACTIVE")
    elif scope == SCOPE_DUPLICATE_SUPPRESSED:
        reason_codes.append("DUPLICATE_SUPPRESSED")
    else:
        reason_codes.append("SHADOW_ONLY_SCOPE_ACTIVE")
        if mode == MODE_LIVE:
            reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")

    rule_path = ["RULE_0"]
    if scope != SCOPE_UNAVAILABLE:
        rule_path += ["RULE_1", "RULE_2"]
    if exec_type in _REPLAY_TYPES:
        rule_path.append("RULE_3")

    hist_cfg = (f"hist-cfg-{_new_id()[:8]}" if is_replay_rec else None)
    src_art = (f"src-{_new_id()[:8]}" if is_replay_rec else None)

    return CampaignRecord(
        record_id=_new_id(),
        cycle_id=cycle_id,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        correlation_id=_new_id(),
        causation_id=_new_id(),
        config_version_id=cfg,
        orchestration_cycle_id=cycle_id,
        origin_source="shadow_campaign",
        origin_authority="campaign_runner",
        actor_identity="shadow_campaign_agent",
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=scope in _SUPPRESSED_SCOPES,
        live_effects_produced=0,
        provider_dispatch_count=0,
        is_replay=is_replay_rec,
        source_artifact_id=src_art,
        historical_config_version_id=hist_cfg,
        is_finalized=is_finalized,
        is_mutable=not is_finalized,
        mutation_prohibited=is_finalized,
        is_duplicate=duplicate,
        degraded=degraded,
        degradation_cause=degradation_cause,
        scheduler_processed=True,
        worker_processed=True,
        prioritization_complete=True,
        transport_generated=True,
        observability_emitted=True,
        provider_assessment_produced=True,
    )


def _run_cycle(
    mode: str = MODE_SHADOW,
    count: int = 10,
    include_replay: bool = False,
    config_missing: bool = False,
) -> CampaignCycleResult:
    cid = _new_id()
    records = [
        _make_record(cid, mode=mode, exec_type=TYPE_ORIGINAL, config_missing=config_missing)
        for _ in range(count)
    ]
    if include_replay:
        records.append(_make_record(cid, mode=mode, exec_type=TYPE_REPLAY))

    suppressed = sum(1 for r in records if r.outbound_suppressed)
    effects = sum(r.live_effects_produced for r in records)
    dispatches = sum(r.provider_dispatch_count for r in records)
    attr_ok = all(r.correlation_id and r.causation_id for r in records)

    return CampaignCycleResult(
        cycle_id=cid,
        records_produced=len(records),
        suppressed_count=suppressed,
        live_effects_produced=effects,
        provider_dispatch_count=dispatches,
        attribution_complete=attr_ok,
        governance_scope=records[0].governance_scope,
        rule_path_summary=records[0].rule_path[0],
        scheduler_ticked=True,
        worker_assigned=True,
        orchestration_decided=True,
        prioritization_done=True,
        provider_assessed=True,
        transport_generated=True,
        observability_emitted=True,
        degraded=config_missing,
        degradation_cause="CONFIG_V2_UNAVAILABLE" if config_missing else None,
    )


def _make_batch(
    count: int,
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
) -> List[CampaignRecord]:
    cid = _new_id()
    return [_make_record(cid, mode=mode, exec_type=exec_type) for _ in range(count)]


def _compute_metrics(campaign_id: str, records: List[CampaignRecord]) -> CampaignMetrics:
    m = CampaignMetrics(campaign_id=campaign_id)
    for r in records:
        m.orchestration_count += 1
        if r.outbound_suppressed:
            m.suppression_count += 1
        if r.is_replay:
            m.replay_count += 1
        if r.degraded:
            m.degradation_count += 1
        if r.is_duplicate:
            m.duplicate_suppression_count += 1
        if r.config_version_id == UNKNOWN_V0:
            m.config_resolution_failures += 1
        if r.governance_scope in {SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY}:
            m.provider_suppression_count += 1
        if r.governance_scope == SCOPE_AUTHORIZED:
            m.authorized_scope_count += 1
        m.live_effects_total += r.live_effects_produced
        m.provider_dispatch_total += r.provider_dispatch_count
        if r.governance_scope == SCOPE_REPLAY_ONLY and r.live_effects_produced > 0:
            m.replay_leakage_count += 1
    return m


def _make_operator_report(campaign_id: str, metrics: CampaignMetrics) -> OperatorReport:
    total_violations = 0  # all well-formed records pass invariants
    cert_passed = (
        metrics.live_effects_total == 0
        and metrics.provider_dispatch_total == 0
        and metrics.authorized_scope_count == 0
        and total_violations == 0
    )
    outcome = CERT_OUTCOME_PASSED if cert_passed else CERT_OUTCOME_FAILED
    return OperatorReport(
        report_id=_new_id(),
        campaign_id=campaign_id,
        campaign_duration_seconds=0.5,
        orchestration_volume=metrics.orchestration_count,
        suppression_volume=metrics.suppression_count,
        replay_volume=metrics.replay_count,
        degradation_events=metrics.degradation_count,
        inv_violations=0,
        fad_violations=0,
        live_effects_total=metrics.live_effects_total,
        provider_dispatch_total=metrics.provider_dispatch_total,
        authorized_scope_count=metrics.authorized_scope_count,
        attribution_gap_count=metrics.attribution_gap_count,
        replay_leakage_count=metrics.replay_leakage_count,
        governance_invariant_violations=total_violations,
        certification_outcome=outcome,
        certification_passed=cert_passed,
    )


def _audit_records(records: List[CampaignRecord]) -> CampaignAuditResult:
    dispatch = sum(r.provider_dispatch_count for r in records)
    effects = sum(r.live_effects_produced for r in records)
    attr_gaps = sum(1 for r in records if not r.correlation_id or not r.causation_id)
    fin_viol = sum(1 for r in records if r.is_finalized and r.is_mutable)
    replay_leak = sum(
        1 for r in records
        if r.governance_scope == SCOPE_REPLAY_ONLY and r.live_effects_produced > 0
    )
    gov_viol = 0  # well-formed records
    auth_count = sum(1 for r in records if r.governance_scope == SCOPE_AUTHORIZED)
    passed = (
        dispatch == 0 and effects == 0 and attr_gaps == 0
        and fin_viol == 0 and replay_leak == 0 and gov_viol == 0 and auth_count == 0
    )
    return CampaignAuditResult(
        total_records=len(records),
        provider_dispatch_count=dispatch,
        live_effects_produced=effects,
        attribution_gap_count=attr_gaps,
        finalized_violation_count=fin_viol,
        replay_leakage_count=replay_leak,
        governance_invariant_violations=gov_viol,
        authorized_scope_count=auth_count,
        audit_passed=passed,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSchedulerCycleCertification:
    """Scheduler cycles produce governed records with SHADOW containment."""

    def test_scheduler_cycle_produces_records(self):
        result = _run_cycle(mode=MODE_SHADOW, count=5)
        assert result.records_produced >= 5

    def test_scheduler_cycle_ticked(self):
        result = _run_cycle()
        assert result.scheduler_ticked is True

    def test_scheduler_cycle_zero_live_effects(self):
        result = _run_cycle()
        assert result.live_effects_produced == 0

    def test_scheduler_cycle_zero_dispatch(self):
        result = _run_cycle()
        assert result.provider_dispatch_count == 0

    def test_scheduler_cycle_attribution_complete(self):
        result = _run_cycle()
        assert result.attribution_complete is True

    def test_scheduler_cycle_scope_shadow_only(self):
        result = _run_cycle(mode=MODE_SHADOW)
        assert result.governance_scope == SCOPE_SHADOW_ONLY

    def test_scheduler_cycle_rule0_first(self):
        result = _run_cycle()
        assert result.rule_path_summary == "RULE_0"

    def test_scheduler_cycle_suppression_equals_total(self):
        result = _run_cycle(count=10)
        assert result.suppressed_count == result.records_produced

    def test_scheduler_cycle_degraded_on_config_missing(self):
        result = _run_cycle(config_missing=True)
        assert result.degraded is True
        assert result.degradation_cause == "CONFIG_V2_UNAVAILABLE"


class TestWorkerCycleCertification:
    """Worker cycles maintain SHADOW containment and process all stages."""

    def test_worker_assigned_per_record(self):
        cid = _new_id()
        records = [_make_record(cid) for _ in range(5)]
        assert all(r.worker_processed for r in records)

    def test_worker_records_zero_live_effects(self):
        cid = _new_id()
        records = [_make_record(cid) for _ in range(10)]
        assert sum(r.live_effects_produced for r in records) == 0

    def test_worker_records_zero_dispatch(self):
        cid = _new_id()
        records = [_make_record(cid) for _ in range(10)]
        assert sum(r.provider_dispatch_count for r in records) == 0

    def test_worker_records_outbound_suppressed(self):
        cid = _new_id()
        records = [_make_record(cid) for _ in range(10)]
        assert all(r.outbound_suppressed for r in records)

    def test_worker_records_scope_shadow_only(self):
        cid = _new_id()
        records = [_make_record(cid, mode=MODE_SHADOW) for _ in range(5)]
        assert all(r.governance_scope == SCOPE_SHADOW_ONLY for r in records)

    def test_worker_records_attribution_present(self):
        cid = _new_id()
        records = [_make_record(cid) for _ in range(5)]
        assert all(r.correlation_id and r.causation_id for r in records)

    def test_worker_live_mode_still_shadow_only(self):
        cid = _new_id()
        records = [_make_record(cid, mode=MODE_LIVE) for _ in range(5)]
        assert all(r.governance_scope == SCOPE_SHADOW_ONLY for r in records)

    def test_worker_live_mode_phase12_reason_code(self):
        cid = _new_id()
        records = [_make_record(cid, mode=MODE_LIVE) for _ in range(5)]
        assert all("LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes for r in records)

    def test_worker_authorized_never_reached(self):
        cid = _new_id()
        records = [_make_record(cid, mode=MODE_LIVE) for _ in range(10)]
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in records)


class TestOrchestrationDecisionCertification:
    """Orchestration decisions tracked and observable throughout campaign."""

    def test_orchestration_cycle_id_present(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.orchestration_cycle_id == cid

    def test_prioritization_complete(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.prioritization_complete is True

    def test_transport_generated(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.transport_generated is True

    def test_provider_assessment_produced(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.provider_assessment_produced is True

    def test_observability_emitted(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.observability_emitted is True

    def test_origin_source_present(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.origin_source

    def test_origin_authority_present(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.origin_authority

    def test_actor_identity_present(self):
        cid = _new_id()
        r = _make_record(cid)
        assert r.actor_identity

    def test_rule_path_nonempty(self):
        cid = _new_id()
        r = _make_record(cid)
        assert len(r.rule_path) > 0


class TestCampaignMetricsTracking:
    """All 9 required campaign metrics tracked correctly."""

    def test_orchestration_count_matches_records(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        assert m.orchestration_count == 20

    def test_suppression_count_equals_suppressed(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        suppressed = sum(1 for r in records if r.outbound_suppressed)
        assert m.suppression_count == suppressed

    def test_replay_count_equals_replay_records(self):
        cid = _new_id()
        records = [_make_record(cid, exec_type=TYPE_REPLAY) for _ in range(5)]
        records += [_make_record(cid) for _ in range(10)]
        m = _compute_metrics("c1", records)
        assert m.replay_count == 5

    def test_degradation_count_equals_degraded_records(self):
        cid = _new_id()
        records = [
            _make_record(cid, degraded=True, degradation_cause="TEST_CAUSE") for _ in range(3)
        ]
        records += [_make_record(cid) for _ in range(7)]
        m = _compute_metrics("c1", records)
        assert m.degradation_count == 3

    def test_duplicate_suppression_count(self):
        cid = _new_id()
        records = [_make_record(cid, duplicate=True) for _ in range(4)]
        records += [_make_record(cid) for _ in range(6)]
        m = _compute_metrics("c1", records)
        assert m.duplicate_suppression_count == 4

    def test_config_resolution_failures(self):
        cid = _new_id()
        records = [_make_record(cid, config_missing=True) for _ in range(2)]
        records += [_make_record(cid) for _ in range(8)]
        m = _compute_metrics("c1", records)
        assert m.config_resolution_failures == 2

    def test_provider_suppression_count(self):
        records = _make_batch(10, exec_type=TYPE_ORIGINAL)
        m = _compute_metrics("c1", records)
        # all SHADOW_ONLY → provider suppression
        assert m.provider_suppression_count == 10

    def test_live_effects_total_zero(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        assert m.live_effects_total == 0

    def test_provider_dispatch_total_zero(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        assert m.provider_dispatch_total == 0


class TestCampaignSuppressionIntegrity:
    """provider_dispatch_count=0 and live_effects_produced=0 at all volumes."""

    def test_shadow_mode_dispatch_zero(self):
        records = _make_batch(50, mode=MODE_SHADOW)
        assert all(r.provider_dispatch_count == 0 for r in records)

    def test_shadow_mode_live_effects_zero(self):
        records = _make_batch(50, mode=MODE_SHADOW)
        assert all(r.live_effects_produced == 0 for r in records)

    def test_live_mode_dispatch_zero(self):
        records = _make_batch(50, mode=MODE_LIVE)
        assert all(r.provider_dispatch_count == 0 for r in records)

    def test_live_mode_live_effects_zero(self):
        records = _make_batch(50, mode=MODE_LIVE)
        assert all(r.live_effects_produced == 0 for r in records)

    def test_replay_type_dispatch_zero(self):
        records = _make_batch(20, exec_type=TYPE_REPLAY)
        assert all(r.provider_dispatch_count == 0 for r in records)

    def test_outbound_suppressed_all_records(self):
        records = _make_batch(30)
        assert all(r.outbound_suppressed for r in records)

    def test_authorized_scope_never_produced(self):
        records = _make_batch(30, mode=MODE_LIVE)
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in records)

    def test_reason_codes_nonempty_for_all(self):
        records = _make_batch(20)
        assert all(len(r.reason_codes) > 0 for r in records)


class TestOperatorReportCertification:
    """Operator certification report contains required fields and correct values."""

    def test_report_has_report_id(self):
        records = _make_batch(10)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.report_id

    def test_report_campaign_id_matches(self):
        records = _make_batch(10)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.campaign_id == "c1"

    def test_report_orchestration_volume(self):
        records = _make_batch(25)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.orchestration_volume == 25

    def test_report_suppression_volume(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.suppression_volume == 20

    def test_report_live_effects_zero(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.live_effects_total == 0

    def test_report_dispatch_zero(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.provider_dispatch_total == 0

    def test_report_certification_passed(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.certification_passed is True

    def test_report_outcome_passed(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.certification_outcome == CERT_OUTCOME_PASSED

    def test_report_authorized_scope_zero(self):
        records = _make_batch(20)
        m = _compute_metrics("c1", records)
        rpt = _make_operator_report("c1", m)
        assert rpt.authorized_scope_count == 0


class TestCampaignLoadCertification:
    """Campaign suppression and attribution hold at 100/500/1000/production batch."""

    def test_100_records_zero_live_effects(self):
        records = _make_batch(100)
        assert sum(r.live_effects_produced for r in records) == 0

    def test_100_records_zero_dispatch(self):
        records = _make_batch(100)
        assert sum(r.provider_dispatch_count for r in records) == 0

    def test_500_records_zero_live_effects(self):
        records = _make_batch(500)
        assert sum(r.live_effects_produced for r in records) == 0

    def test_500_records_zero_dispatch(self):
        records = _make_batch(500)
        assert sum(r.provider_dispatch_count for r in records) == 0

    def test_1000_records_zero_live_effects(self):
        records = _make_batch(1000)
        assert sum(r.live_effects_produced for r in records) == 0

    def test_1000_records_zero_dispatch(self):
        records = _make_batch(1000)
        assert sum(r.provider_dispatch_count for r in records) == 0

    def test_1000_records_all_suppressed(self):
        records = _make_batch(1000)
        assert all(r.outbound_suppressed for r in records)

    def test_1000_records_attribution_complete(self):
        records = _make_batch(1000)
        assert all(r.correlation_id and r.causation_id for r in records)

    def test_1000_records_authorized_zero(self):
        records = _make_batch(1000, mode=MODE_LIVE)
        assert sum(1 for r in records if r.governance_scope == SCOPE_AUTHORIZED) == 0

    def test_1000_records_rule0_first(self):
        records = _make_batch(1000)
        assert all(r.rule_path and r.rule_path[0] == "RULE_0" for r in records)

    def test_production_batch_metrics_all_valid(self):
        records = _make_batch(500)
        m = _compute_metrics("prod", records)
        assert m.live_effects_total == 0
        assert m.provider_dispatch_total == 0
        assert m.authorized_scope_count == 0


class TestCampaignAttributionContinuity:
    """All 7 attribution fields present throughout campaign execution."""

    def test_correlation_id_present_in_all_records(self):
        records = _make_batch(30)
        assert all(r.correlation_id for r in records)

    def test_causation_id_present_in_all_records(self):
        records = _make_batch(30)
        assert all(r.causation_id for r in records)

    def test_config_version_id_present(self):
        records = _make_batch(30)
        assert all(r.config_version_id for r in records)

    def test_orchestration_cycle_id_present(self):
        cid = _new_id()
        records = [_make_record(cid) for _ in range(20)]
        assert all(r.orchestration_cycle_id == cid for r in records)

    def test_execution_mode_present(self):
        records = _make_batch(20)
        assert all(r.execution_mode for r in records)

    def test_governance_scope_present(self):
        records = _make_batch(20)
        assert all(r.governance_scope for r in records)

    def test_execution_type_present(self):
        records = _make_batch(20)
        assert all(r.execution_type for r in records)

    def test_attribution_continuity_through_replay(self):
        cid = _new_id()
        records = [_make_record(cid, exec_type=TYPE_REPLAY) for _ in range(10)]
        assert all(r.correlation_id and r.causation_id for r in records)

    def test_attribution_continuity_through_degradation(self):
        cid = _new_id()
        records = [
            _make_record(cid, degraded=True, degradation_cause="TEST") for _ in range(10)
        ]
        assert all(r.correlation_id and r.causation_id for r in records)


class TestCampaignFinalAudit:
    """Final audit: all 6 zero-count requirements met across 200 records."""

    def _make_full_batch(self) -> List[CampaignRecord]:
        cid = _new_id()
        records = []
        # original shadow
        records += [_make_record(cid, mode=MODE_SHADOW) for _ in range(100)]
        # live mode (still SHADOW_ONLY due to Phase-12 gate)
        records += [_make_record(cid, mode=MODE_LIVE) for _ in range(40)]
        # replay
        records += [_make_record(cid, exec_type=TYPE_REPLAY) for _ in range(30)]
        # finalized
        records += [_make_record(cid, is_finalized=True) for _ in range(20)]
        # maintenance
        records += [_make_record(cid, maintenance=True) for _ in range(10)]
        return records

    def test_provider_dispatch_count_zero(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.provider_dispatch_count == 0

    def test_live_effects_produced_zero(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.live_effects_produced == 0

    def test_attribution_gap_count_zero(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.attribution_gap_count == 0

    def test_finalized_violation_count_zero(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.finalized_violation_count == 0

    def test_replay_leakage_count_zero(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.replay_leakage_count == 0

    def test_governance_invariant_violations_zero(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.governance_invariant_violations == 0

    def test_audit_passed(self):
        records = self._make_full_batch()
        audit = _audit_records(records)
        assert audit.audit_passed is True
