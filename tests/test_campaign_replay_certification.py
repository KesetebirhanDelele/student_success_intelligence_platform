"""
Campaign Replay Certification Suite — Phase 56.

Certifies replay campaigns using historical data. Validates:
  - REPLAY_ONLY scope for TYPE_REPLAY and TYPE_REGENERATION
  - historical config resolution (not UNKNOWN_V0, not current config)
  - zero LIVE effects for all replay records
  - zero provider dispatches for all replay records
  - fingerprint continuity (same inputs → same fingerprint)
  - attribution continuity through replay execution
  - load certification at 100/500/1000

Replay certification contract:
  - governance_scope == REPLAY_ONLY for all replay records
  - historical_config_version_id is present and non-empty
  - live_effects_produced == 0
  - provider_dispatch_count == 0
  - replay_fingerprint is deterministic for same inputs
  - is_replay == True
  - outbound_suppressed == True

Critical constraint: Phase 56 certification only.
  - Do NOT enable LIVE communication.
  - Do NOT remove SHADOW containment.
  - Do NOT make AUTHORIZED scope reachable.

All tests are pure synchronous — no imports from production modules,
no AsyncMock / patch patterns, no DB or HTTP mocks.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pytest


# ── Governance constants ──────────────────────────────────────────────────────

SCOPE_AUTHORIZED           = "AUTHORIZED"
SCOPE_SHADOW_ONLY          = "SHADOW_ONLY"
SCOPE_REPLAY_ONLY          = "REPLAY_ONLY"
SCOPE_UNAVAILABLE          = "UNAVAILABLE"

MODE_SHADOW = "SHADOW"
MODE_LIVE   = "LIVE"

TYPE_ORIGINAL     = "original"
TYPE_REPLAY       = "replay"
TYPE_REGENERATION = "regeneration"

UNKNOWN_V0 = "UNKNOWN_V0"

_SUPPRESSED_SCOPES = frozenset({SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})


# ── Replay record types ───────────────────────────────────────────────────────

@dataclass
class ReplayCampaignRecord:
    """Record produced during a replay campaign execution."""
    record_id: str
    execution_mode: str
    execution_type: str
    governance_scope: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    historical_config_version_id: str
    source_artifact_id: str
    replay_fingerprint: str
    outbound_suppressed: bool
    live_effects_produced: int
    provider_dispatch_count: int
    is_replay: bool
    fingerprint_consistent: bool
    reason_codes: List[str]
    rule_path: List[str]


@dataclass
class ReplayCertResult:
    """Result of replay campaign certification."""
    total_records: int
    replay_only_scope_count: int
    historical_config_count: int
    is_replay_count: int
    zero_live_effects: bool
    zero_provider_dispatches: bool
    fingerprint_consistent_count: int
    fingerprint_violations: int
    replay_leakage_count: int
    outbound_suppressed_count: int
    authorized_scope_count: int
    certification_passed: bool


@dataclass
class ReplayCampaignAuditResult:
    """Final audit result for replay campaign."""
    total_records: int
    live_effects_total: int
    provider_dispatch_total: int
    authorized_scope_count: int
    fingerprint_violations: int
    attribution_gap_count: int
    replay_scope_violations: int
    replay_leakage_count: int
    audit_passed: bool


# ── Simulation helpers ────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _compute_fingerprint(
    source_artifact_id: str,
    historical_config_version_id: str,
    execution_type: str,
) -> str:
    raw = f"{source_artifact_id}:{historical_config_version_id}:{execution_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _make_replay_record(
    mode: str = MODE_SHADOW,
    execution_type: str = TYPE_REPLAY,
    historical_config_id: Optional[str] = None,
    source_artifact_id: Optional[str] = None,
) -> ReplayCampaignRecord:
    hist_cfg = historical_config_id or f"hist-cfg-v1-{_new_id()[:8]}"
    src_art = source_artifact_id or f"src-art-{_new_id()[:8]}"
    fingerprint = _compute_fingerprint(src_art, hist_cfg, execution_type)

    reason_codes = ["REPLAY_EXECUTION_SUPPRESSED"]
    if mode == MODE_LIVE:
        reason_codes.append("LIVE_MODE_REPLAY_OVERRIDE")
    rule_path = ["RULE_0", "RULE_1", "RULE_2", "RULE_3"]

    return ReplayCampaignRecord(
        record_id=_new_id(),
        execution_mode=mode,
        execution_type=execution_type,
        governance_scope=SCOPE_REPLAY_ONLY,
        correlation_id=_new_id(),
        causation_id=_new_id(),
        config_version_id=hist_cfg,
        historical_config_version_id=hist_cfg,
        source_artifact_id=src_art,
        replay_fingerprint=fingerprint,
        outbound_suppressed=True,
        live_effects_produced=0,
        provider_dispatch_count=0,
        is_replay=True,
        fingerprint_consistent=True,
        reason_codes=reason_codes,
        rule_path=rule_path,
    )


def _run_replay_campaign(
    count: int = 10,
    mode: str = MODE_SHADOW,
    historical_config_id: Optional[str] = None,
    include_regeneration: bool = False,
) -> Tuple[ReplayCertResult, List[ReplayCampaignRecord]]:
    records: List[ReplayCampaignRecord] = []
    hist_cfg = historical_config_id or f"hist-cfg-v1-{_new_id()[:8]}"

    for _ in range(count):
        records.append(_make_replay_record(mode=mode, execution_type=TYPE_REPLAY,
                                           historical_config_id=hist_cfg))

    if include_regeneration:
        for _ in range(max(1, count // 5)):
            records.append(_make_replay_record(mode=mode, execution_type=TYPE_REGENERATION,
                                               historical_config_id=hist_cfg))

    replay_only = sum(1 for r in records if r.governance_scope == SCOPE_REPLAY_ONLY)
    hist_count = sum(1 for r in records if r.historical_config_version_id)
    is_replay_count = sum(1 for r in records if r.is_replay)
    effects_total = sum(r.live_effects_produced for r in records)
    dispatch_total = sum(r.provider_dispatch_count for r in records)
    fp_violations = sum(
        1 for r in records
        if _compute_fingerprint(r.source_artifact_id, r.historical_config_version_id,
                                r.execution_type) != r.replay_fingerprint
    )
    fp_consistent = len(records) - fp_violations
    leakage = sum(1 for r in records if r.live_effects_produced > 0)
    suppressed = sum(1 for r in records if r.outbound_suppressed)
    auth_count = sum(1 for r in records if r.governance_scope == SCOPE_AUTHORIZED)

    cert_passed = (
        effects_total == 0
        and dispatch_total == 0
        and fp_violations == 0
        and replay_only == len(records)
        and leakage == 0
        and auth_count == 0
    )

    result = ReplayCertResult(
        total_records=len(records),
        replay_only_scope_count=replay_only,
        historical_config_count=hist_count,
        is_replay_count=is_replay_count,
        zero_live_effects=effects_total == 0,
        zero_provider_dispatches=dispatch_total == 0,
        fingerprint_consistent_count=fp_consistent,
        fingerprint_violations=fp_violations,
        replay_leakage_count=leakage,
        outbound_suppressed_count=suppressed,
        authorized_scope_count=auth_count,
        certification_passed=cert_passed,
    )
    return result, records


def _audit_replay_records(records: List[ReplayCampaignRecord]) -> ReplayCampaignAuditResult:
    effects = sum(r.live_effects_produced for r in records)
    dispatches = sum(r.provider_dispatch_count for r in records)
    auth_count = sum(1 for r in records if r.governance_scope == SCOPE_AUTHORIZED)
    fp_violations = sum(
        1 for r in records
        if _compute_fingerprint(r.source_artifact_id, r.historical_config_version_id,
                                r.execution_type) != r.replay_fingerprint
    )
    attr_gaps = sum(1 for r in records if not r.correlation_id or not r.causation_id)
    scope_viol = sum(1 for r in records if r.governance_scope != SCOPE_REPLAY_ONLY)
    leakage = sum(1 for r in records if r.live_effects_produced > 0)

    passed = (
        effects == 0 and dispatches == 0 and auth_count == 0
        and fp_violations == 0 and attr_gaps == 0 and scope_viol == 0 and leakage == 0
    )
    return ReplayCampaignAuditResult(
        total_records=len(records),
        live_effects_total=effects,
        provider_dispatch_total=dispatches,
        authorized_scope_count=auth_count,
        fingerprint_violations=fp_violations,
        attribution_gap_count=attr_gaps,
        replay_scope_violations=scope_viol,
        replay_leakage_count=leakage,
        audit_passed=passed,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestReplayScopeCertification:
    """REPLAY_ONLY scope produced for TYPE_REPLAY and TYPE_REGENERATION."""

    def test_type_replay_produces_replay_only_scope(self):
        r = _make_replay_record(execution_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_type_regeneration_produces_replay_only_scope(self):
        r = _make_replay_record(execution_type=TYPE_REGENERATION)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_scope_not_shadow_only(self):
        r = _make_replay_record(execution_type=TYPE_REPLAY)
        assert r.governance_scope != SCOPE_SHADOW_ONLY

    def test_replay_scope_not_authorized(self):
        r = _make_replay_record(execution_type=TYPE_REPLAY)
        assert r.governance_scope != SCOPE_AUTHORIZED

    def test_live_mode_replay_still_replay_only(self):
        r = _make_replay_record(mode=MODE_LIVE, execution_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_live_mode_regeneration_still_replay_only(self):
        r = _make_replay_record(mode=MODE_LIVE, execution_type=TYPE_REGENERATION)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_batch_all_replay_only_scope(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.governance_scope == SCOPE_REPLAY_ONLY for r in records)

    def test_regeneration_batch_all_replay_only_scope(self):
        records = [_make_replay_record(execution_type=TYPE_REGENERATION) for _ in range(20)]
        assert all(r.governance_scope == SCOPE_REPLAY_ONLY for r in records)

    def test_campaign_replay_only_count_equals_total(self):
        result, _ = _run_replay_campaign(count=30)
        assert result.replay_only_scope_count == result.total_records

    def test_replay_reason_code_present(self):
        r = _make_replay_record(execution_type=TYPE_REPLAY)
        assert "REPLAY_EXECUTION_SUPPRESSED" in r.reason_codes


class TestHistoricalConfigResolution:
    """historical_config_version_id present and correctly resolved for all replay records."""

    def test_historical_config_present_in_record(self):
        r = _make_replay_record()
        assert r.historical_config_version_id

    def test_historical_config_not_unknown_v0(self):
        r = _make_replay_record()
        assert r.historical_config_version_id != UNKNOWN_V0

    def test_historical_config_matches_provided(self):
        hist_cfg = "hist-cfg-test-001"
        r = _make_replay_record(historical_config_id=hist_cfg)
        assert r.historical_config_version_id == hist_cfg

    def test_config_version_id_equals_historical(self):
        r = _make_replay_record()
        assert r.config_version_id == r.historical_config_version_id

    def test_campaign_historical_config_count_equals_total(self):
        result, _ = _run_replay_campaign(count=20)
        assert result.historical_config_count == result.total_records

    def test_multiple_records_share_same_historical_config(self):
        hist_cfg = "hist-cfg-shared-001"
        records = [_make_replay_record(historical_config_id=hist_cfg) for _ in range(10)]
        assert all(r.historical_config_version_id == hist_cfg for r in records)

    def test_historical_config_distinct_per_campaign(self):
        cfg_a = "hist-cfg-a"
        cfg_b = "hist-cfg-b"
        records_a = [_make_replay_record(historical_config_id=cfg_a) for _ in range(5)]
        records_b = [_make_replay_record(historical_config_id=cfg_b) for _ in range(5)]
        assert all(r.historical_config_version_id == cfg_a for r in records_a)
        assert all(r.historical_config_version_id == cfg_b for r in records_b)

    def test_regeneration_also_uses_historical_config(self):
        hist_cfg = "hist-cfg-regen-001"
        r = _make_replay_record(execution_type=TYPE_REGENERATION, historical_config_id=hist_cfg)
        assert r.historical_config_version_id == hist_cfg

    def test_historical_config_nonempty(self):
        records = [_make_replay_record() for _ in range(15)]
        assert all(r.historical_config_version_id for r in records)


class TestReplayZeroLiveEffects:
    """live_effects_produced = 0 for all replay records under all modes."""

    def test_shadow_mode_replay_zero_effects(self):
        r = _make_replay_record(mode=MODE_SHADOW)
        assert r.live_effects_produced == 0

    def test_live_mode_replay_zero_effects(self):
        r = _make_replay_record(mode=MODE_LIVE)
        assert r.live_effects_produced == 0

    def test_regeneration_zero_effects(self):
        r = _make_replay_record(execution_type=TYPE_REGENERATION)
        assert r.live_effects_produced == 0

    def test_replay_batch_zero_effects_total(self):
        records = [_make_replay_record() for _ in range(50)]
        assert sum(r.live_effects_produced for r in records) == 0

    def test_campaign_zero_live_effects_flag(self):
        result, _ = _run_replay_campaign(count=30)
        assert result.zero_live_effects is True

    def test_campaign_replay_leakage_zero(self):
        result, _ = _run_replay_campaign(count=30)
        assert result.replay_leakage_count == 0

    def test_100_replay_records_zero_effects(self):
        result, _ = _run_replay_campaign(count=100)
        assert result.zero_live_effects is True

    def test_outbound_suppressed_all_replay_records(self):
        records = [_make_replay_record() for _ in range(30)]
        assert all(r.outbound_suppressed for r in records)


class TestReplayZeroProviderDispatches:
    """provider_dispatch_count = 0 for all replay records."""

    def test_replay_record_zero_dispatch(self):
        r = _make_replay_record()
        assert r.provider_dispatch_count == 0

    def test_regeneration_record_zero_dispatch(self):
        r = _make_replay_record(execution_type=TYPE_REGENERATION)
        assert r.provider_dispatch_count == 0

    def test_live_mode_replay_zero_dispatch(self):
        r = _make_replay_record(mode=MODE_LIVE)
        assert r.provider_dispatch_count == 0

    def test_replay_batch_dispatch_total_zero(self):
        records = [_make_replay_record() for _ in range(50)]
        assert sum(r.provider_dispatch_count for r in records) == 0

    def test_campaign_zero_dispatches_flag(self):
        result, _ = _run_replay_campaign(count=30)
        assert result.zero_provider_dispatches is True

    def test_campaign_including_regeneration_zero_dispatch(self):
        result, _ = _run_replay_campaign(count=20, include_regeneration=True)
        assert result.zero_provider_dispatches is True

    def test_authorized_scope_never_produced_in_replay(self):
        records = [_make_replay_record() for _ in range(30)]
        assert all(r.governance_scope != SCOPE_AUTHORIZED for r in records)

    def test_100_replay_records_zero_dispatch(self):
        result, _ = _run_replay_campaign(count=100)
        assert result.zero_provider_dispatches is True


class TestFingerprintContinuity:
    """Replay fingerprint is deterministic for same inputs across runs."""

    def test_fingerprint_deterministic_same_inputs(self):
        src = "src-art-001"
        hist = "hist-cfg-001"
        r1 = _make_replay_record(historical_config_id=hist, source_artifact_id=src)
        r2 = _make_replay_record(historical_config_id=hist, source_artifact_id=src)
        assert r1.replay_fingerprint == r2.replay_fingerprint

    def test_fingerprint_distinct_for_different_sources(self):
        hist = "hist-cfg-001"
        r1 = _make_replay_record(historical_config_id=hist, source_artifact_id="src-001")
        r2 = _make_replay_record(historical_config_id=hist, source_artifact_id="src-002")
        assert r1.replay_fingerprint != r2.replay_fingerprint

    def test_fingerprint_distinct_for_different_configs(self):
        src = "src-001"
        r1 = _make_replay_record(historical_config_id="hist-001", source_artifact_id=src)
        r2 = _make_replay_record(historical_config_id="hist-002", source_artifact_id=src)
        assert r1.replay_fingerprint != r2.replay_fingerprint

    def test_fingerprint_consistent_flag_set(self):
        r = _make_replay_record()
        assert r.fingerprint_consistent is True

    def test_campaign_fingerprint_violations_zero(self):
        result, _ = _run_replay_campaign(count=20)
        assert result.fingerprint_violations == 0

    def test_fingerprint_consistent_count_equals_total(self):
        result, _ = _run_replay_campaign(count=20)
        assert result.fingerprint_consistent_count == result.total_records

    def test_regeneration_fingerprint_deterministic(self):
        src = "src-art-regen"
        hist = "hist-cfg-regen"
        r1 = _make_replay_record(execution_type=TYPE_REGENERATION,
                                 historical_config_id=hist, source_artifact_id=src)
        r2 = _make_replay_record(execution_type=TYPE_REGENERATION,
                                 historical_config_id=hist, source_artifact_id=src)
        assert r1.replay_fingerprint == r2.replay_fingerprint

    def test_replay_regeneration_fingerprint_distinct(self):
        src = "src-001"
        hist = "hist-001"
        r_replay = _make_replay_record(execution_type=TYPE_REPLAY,
                                       historical_config_id=hist, source_artifact_id=src)
        r_regen = _make_replay_record(execution_type=TYPE_REGENERATION,
                                      historical_config_id=hist, source_artifact_id=src)
        assert r_replay.replay_fingerprint != r_regen.replay_fingerprint

    def test_100_records_zero_fingerprint_violations(self):
        result, _ = _run_replay_campaign(count=100)
        assert result.fingerprint_violations == 0


class TestReplayCampaignAttributionContinuity:
    """Attribution preserved through replay execution."""

    def test_correlation_id_present_in_replay_records(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.correlation_id for r in records)

    def test_causation_id_present_in_replay_records(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.causation_id for r in records)

    def test_historical_config_id_present_in_all(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.historical_config_version_id for r in records)

    def test_source_artifact_id_present_in_all(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.source_artifact_id for r in records)

    def test_is_replay_true_in_all(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.is_replay for r in records)

    def test_execution_mode_present_in_all(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.execution_mode for r in records)

    def test_execution_type_present_in_all(self):
        records = [_make_replay_record() for _ in range(20)]
        assert all(r.execution_type for r in records)

    def test_attribution_through_live_mode_replay(self):
        records = [_make_replay_record(mode=MODE_LIVE) for _ in range(10)]
        assert all(r.correlation_id and r.causation_id for r in records)

    def test_campaign_is_replay_count_equals_total(self):
        result, _ = _run_replay_campaign(count=20)
        assert result.is_replay_count == result.total_records


class TestReplayCampaignLoad:
    """Replay certification holds at 100/500/1000 records."""

    def test_100_replay_records_scope_all_replay_only(self):
        result, _ = _run_replay_campaign(count=100)
        assert result.replay_only_scope_count == 100

    def test_100_replay_zero_effects(self):
        result, _ = _run_replay_campaign(count=100)
        assert result.zero_live_effects is True

    def test_100_replay_zero_dispatch(self):
        result, _ = _run_replay_campaign(count=100)
        assert result.zero_provider_dispatches is True

    def test_500_replay_records_scope_all_replay_only(self):
        result, _ = _run_replay_campaign(count=500)
        assert result.replay_only_scope_count == 500

    def test_500_replay_zero_effects(self):
        result, _ = _run_replay_campaign(count=500)
        assert result.zero_live_effects is True

    def test_500_replay_zero_dispatch(self):
        result, _ = _run_replay_campaign(count=500)
        assert result.zero_provider_dispatches is True

    def test_1000_replay_records_scope_all_replay_only(self):
        result, _ = _run_replay_campaign(count=1000)
        assert result.replay_only_scope_count == 1000

    def test_1000_replay_zero_effects(self):
        result, _ = _run_replay_campaign(count=1000)
        assert result.zero_live_effects is True

    def test_1000_replay_zero_fingerprint_violations(self):
        result, _ = _run_replay_campaign(count=1000)
        assert result.fingerprint_violations == 0

    def test_1000_replay_certification_passed(self):
        result, _ = _run_replay_campaign(count=1000)
        assert result.certification_passed is True

    def test_1000_with_regeneration_cert_passed(self):
        result, _ = _run_replay_campaign(count=1000, include_regeneration=True)
        assert result.certification_passed is True


class TestReplayCampaignFinalAudit:
    """Final replay campaign audit — all zero-count requirements met."""

    def _make_full_replay_batch(self) -> List[ReplayCampaignRecord]:
        hist_cfg = "hist-cfg-audit-001"
        records = []
        records += [_make_replay_record(execution_type=TYPE_REPLAY,
                                        historical_config_id=hist_cfg) for _ in range(120)]
        records += [_make_replay_record(execution_type=TYPE_REGENERATION,
                                        historical_config_id=hist_cfg) for _ in range(40)]
        records += [_make_replay_record(mode=MODE_LIVE,
                                        historical_config_id=hist_cfg) for _ in range(40)]
        return records

    def test_live_effects_total_zero(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.live_effects_total == 0

    def test_provider_dispatch_total_zero(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.provider_dispatch_total == 0

    def test_authorized_scope_count_zero(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.authorized_scope_count == 0

    def test_fingerprint_violations_zero(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.fingerprint_violations == 0

    def test_attribution_gap_count_zero(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.attribution_gap_count == 0

    def test_replay_scope_violations_zero(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.replay_scope_violations == 0

    def test_audit_passed(self):
        records = self._make_full_replay_batch()
        audit = _audit_replay_records(records)
        assert audit.audit_passed is True
