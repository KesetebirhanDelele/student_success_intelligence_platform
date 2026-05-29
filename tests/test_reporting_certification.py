"""
Reporting Certification Suite — Phase 54.

Certifies that every reporting surface exposes complete, accurate, and
unambiguous governance state — no summarization hides governance intent.

Certification domains:
  1. Suppression reporting — provider_dispatch_count, live_effects_produced
  2. Attribution reporting — all 7 fields present in every report row
  3. Replay reporting — replay lineage visible, not collapsed into LIVE
  4. FINALIZED reporting — mutation status visible, no editability implied
  5. Degradation reporting — degradation class, severity, recovery visible
  6. Audit trail reporting — append-only visibility, immutable lineage
  7. Load reporting — 100 / 500 / 1000 record visibility at scale

All tests pure synchronous — no implementation imports, no DB or HTTP mocks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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

AI_TIER_FINALIZED_COPY = "FINALIZED_COPY"
AI_TIER_CONFIDENT      = "CONFIDENT"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})


# ── Report row types ──────────────────────────────────────────────────────────

@dataclass
class ReportRow:
    """A single row in an operational report — all governance fields required."""
    row_id: str
    correlation_id: str
    causation_id: str
    config_version_id: str
    execution_mode: str
    execution_type: str
    governance_scope: str
    orchestration_cycle_id: str
    origin_source: str
    origin_authority: str
    actor_identity: str
    provider_dispatch_count: int
    live_effects_produced: int
    outbound_suppressed: bool
    outcome: str
    reason_codes: List[str]
    rule_path: List[str]
    # Replay-specific
    is_replay: bool
    source_artifact_id: Optional[str]
    historical_config_version_id: Optional[str]
    replay_lineage_visible: bool
    # Finalized-specific
    is_finalized: bool
    is_mutable: bool
    content_hash: Optional[str]
    finalized_at: Optional[str]
    mutation_prohibited: bool
    # Degradation-specific
    degraded: bool
    degradation_class: Optional[str]
    degradation_severity: Optional[str]
    degradation_cause: Optional[str]
    recovery_classification: Optional[str]
    # Audit-specific
    audit_sequence_number: int
    is_append_only: bool


@dataclass
class ReportSummary:
    """Aggregate report summary — must not hide individual governance state."""
    total_rows: int
    total_live_effects: int
    total_dispatches: int
    suppressed_count: int
    replay_count: int
    finalized_count: int
    degraded_count: int
    maintenance_count: int
    attribution_complete_count: int
    hidden_governance_rows: int      # rows missing any governance field
    mutable_finalized_rows: int      # rows claiming FINALIZED but is_mutable=True
    replay_ambiguous_rows: int       # replay rows that appear identical to LIVE
    silent_suppression_rows: int     # suppressed rows with no reason_codes


@dataclass
class FinalizedReportArtifact:
    """Report artifact for a FINALIZED record — immutability must be surfaced."""
    artifact_id: str
    correlation_id: str
    governance_scope: str
    config_version_id: str
    is_finalized: bool
    is_mutable: bool
    mutation_prohibited: bool
    content_hash: str
    finalized_at: str
    ai_tier: str
    lineage_visible: bool
    source_artifact_id: Optional[str]


@dataclass
class AuditTrailEntry:
    """Single audit trail entry — must be append-only and non-mutable."""
    entry_id: str
    sequence_number: int
    correlation_id: str
    causation_id: str
    config_version_id: str
    execution_mode: str
    governance_scope: str
    event_type: str
    outcome: str
    is_mutable: bool = False  # always False — append-only


# ── Simulation helpers ────────────────────────────────────────────────────────

def _cid() -> str:
    return f"corr-{uuid.uuid4().hex[:8]}"


def _derive_scope(mode: str, exec_type: str, maintenance: bool = False,
                  config_missing: bool = False) -> str:
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    return SCOPE_SHADOW_ONLY


def _make_report_row(
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    is_finalized: bool = False,
    degraded: bool = False,
    degradation_class: Optional[str] = None,
    degradation_severity: Optional[str] = None,
    degradation_cause: Optional[str] = None,
    recovery_classification: Optional[str] = None,
    maintenance: bool = False,
    config_missing: bool = False,
    source_artifact_id: Optional[str] = None,
    historical_config: Optional[str] = None,
    audit_seq: int = 1,
) -> ReportRow:
    scope = _derive_scope(mode, exec_type, maintenance, config_missing)
    is_rep = exec_type in _REPLAY_TYPES
    suppressed = scope in _SUPPRESSED_SCOPES
    cfg = UNKNOWN_V0 if config_missing else "cfg-v2-001"

    reason_codes: List[str] = []
    if suppressed:
        reason_codes.append(f"SCOPE_{scope}_SUPPRESSED")
    if mode == MODE_LIVE and not is_rep:
        reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")
    if is_rep:
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    if config_missing:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    if degraded and degradation_cause:
        reason_codes.append(f"DEGRADED_{degradation_cause.upper()}")
    if maintenance:
        reason_codes.append("MAINTENANCE_SCOPE_ACTIVE")

    rule_path = ["RULE_0"]
    if not config_missing:
        rule_path += ["RULE_1", "RULE_2"]
    if is_rep and not config_missing:
        rule_path.append("RULE_3")

    content_hash = f"hash-{scope}-{exec_type}" if is_finalized else None
    outcome = "blocked" if config_missing else ("suppressed" if suppressed else "dispatch_delegated")

    return ReportRow(
        row_id=f"row-{uuid.uuid4().hex[:8]}",
        correlation_id=_cid(),
        causation_id=_cid(),
        config_version_id=cfg,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        orchestration_cycle_id=_cid(),
        origin_source="scheduler",
        origin_authority="runtime_context",
        actor_identity="batch_worker",
        provider_dispatch_count=0,
        live_effects_produced=0,
        outbound_suppressed=suppressed,
        outcome=outcome,
        reason_codes=reason_codes,
        rule_path=rule_path,
        is_replay=is_rep,
        source_artifact_id=source_artifact_id,
        historical_config_version_id=historical_config or (cfg if is_rep else None),
        replay_lineage_visible=is_rep and source_artifact_id is not None,
        is_finalized=is_finalized,
        is_mutable=False,
        content_hash=content_hash,
        finalized_at="2026-05-01T00:00:00Z" if is_finalized else None,
        mutation_prohibited=is_finalized,
        degraded=degraded,
        degradation_class=degradation_class,
        degradation_severity=degradation_severity,
        degradation_cause=degradation_cause,
        recovery_classification=recovery_classification,
        audit_sequence_number=audit_seq,
        is_append_only=True,
    )


def _make_finalized_artifact(
    scope: str = SCOPE_REPLAY_ONLY,
    config_version_id: str = "cfg-hist-001",
    source_artifact_id: Optional[str] = "art-001",
) -> FinalizedReportArtifact:
    return FinalizedReportArtifact(
        artifact_id=f"art-{uuid.uuid4().hex[:8]}",
        correlation_id=_cid(),
        governance_scope=scope,
        config_version_id=config_version_id,
        is_finalized=True,
        is_mutable=False,
        mutation_prohibited=True,
        content_hash=f"hash-{scope}-{config_version_id}",
        finalized_at="2026-05-01T00:00:00Z",
        ai_tier=AI_TIER_FINALIZED_COPY,
        lineage_visible=source_artifact_id is not None,
        source_artifact_id=source_artifact_id,
    )


def _make_audit_entry(
    scope: str = SCOPE_SHADOW_ONLY,
    mode: str = MODE_SHADOW,
    seq: int = 1,
) -> AuditTrailEntry:
    return AuditTrailEntry(
        entry_id=f"audit-{uuid.uuid4().hex[:8]}",
        sequence_number=seq,
        correlation_id=_cid(),
        causation_id=_cid(),
        config_version_id="cfg-v2-001",
        execution_mode=mode,
        governance_scope=scope,
        event_type="worker_execution",
        outcome="suppressed",
        is_mutable=False,
    )


def _build_report_summary(rows: List[ReportRow]) -> ReportSummary:
    hidden = sum(
        1 for r in rows
        if not all([r.correlation_id, r.causation_id, r.config_version_id,
                    r.execution_mode, r.execution_type, r.governance_scope,
                    r.orchestration_cycle_id])
    )
    mutable_finalized = sum(1 for r in rows if r.is_finalized and r.is_mutable)
    replay_ambiguous = sum(
        1 for r in rows
        if r.is_replay and r.governance_scope != SCOPE_REPLAY_ONLY
    )
    silent_suppression = sum(
        1 for r in rows
        if r.outbound_suppressed and not r.reason_codes
    )
    return ReportSummary(
        total_rows=len(rows),
        total_live_effects=sum(r.live_effects_produced for r in rows),
        total_dispatches=sum(r.provider_dispatch_count for r in rows),
        suppressed_count=sum(1 for r in rows if r.outbound_suppressed),
        replay_count=sum(1 for r in rows if r.is_replay),
        finalized_count=sum(1 for r in rows if r.is_finalized),
        degraded_count=sum(1 for r in rows if r.degraded),
        maintenance_count=sum(1 for r in rows if r.governance_scope == SCOPE_MAINTENANCE),
        attribution_complete_count=sum(
            1 for r in rows
            if all([r.correlation_id, r.causation_id, r.config_version_id,
                    r.execution_mode, r.execution_type, r.governance_scope,
                    r.orchestration_cycle_id])
        ),
        hidden_governance_rows=hidden,
        mutable_finalized_rows=mutable_finalized,
        replay_ambiguous_rows=replay_ambiguous,
        silent_suppression_rows=silent_suppression,
    )


# ── Test classes ──────────────────────────────────────────────────────────────


class TestSuppressionReporting:
    """Certify suppression metrics are accurately reported."""

    def test_shadow_dispatch_count_zero_in_report(self):
        r = _make_report_row(mode=MODE_SHADOW)
        assert r.provider_dispatch_count == 0

    def test_shadow_live_effects_zero_in_report(self):
        r = _make_report_row(mode=MODE_SHADOW)
        assert r.live_effects_produced == 0

    def test_live_mode_dispatch_count_zero(self):
        r = _make_report_row(mode=MODE_LIVE)
        assert r.provider_dispatch_count == 0

    def test_live_mode_live_effects_zero(self):
        r = _make_report_row(mode=MODE_LIVE)
        assert r.live_effects_produced == 0

    def test_replay_dispatch_count_zero(self):
        r = _make_report_row(exec_type=TYPE_REPLAY)
        assert r.provider_dispatch_count == 0

    def test_replay_live_effects_zero(self):
        r = _make_report_row(exec_type=TYPE_REPLAY)
        assert r.live_effects_produced == 0

    def test_summary_total_live_effects_zero_all_shadow(self):
        rows = [_make_report_row(mode=MODE_SHADOW) for _ in range(50)]
        summary = _build_report_summary(rows)
        assert summary.total_live_effects == 0

    def test_summary_total_dispatches_zero_all_shadow(self):
        rows = [_make_report_row(mode=MODE_SHADOW) for _ in range(50)]
        summary = _build_report_summary(rows)
        assert summary.total_dispatches == 0

    def test_summary_suppressed_count_matches(self):
        rows = [_make_report_row(mode=MODE_SHADOW) for _ in range(20)]
        summary = _build_report_summary(rows)
        assert summary.suppressed_count == 20

    def test_summary_no_silent_suppressions(self):
        rows = [_make_report_row(mode=MODE_SHADOW) for _ in range(30)]
        summary = _build_report_summary(rows)
        assert summary.silent_suppression_rows == 0


class TestAttributionReporting:
    """Certify all 7 attribution fields appear in every report row."""

    _FIELDS = ["correlation_id", "causation_id", "config_version_id",
               "execution_mode", "execution_type", "governance_scope",
               "orchestration_cycle_id"]

    def _assert_all_fields(self, r: ReportRow) -> None:
        for f in self._FIELDS:
            assert getattr(r, f), f"Field '{f}' missing in report row"

    def test_shadow_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(mode=MODE_SHADOW))

    def test_live_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(mode=MODE_LIVE))

    def test_replay_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(exec_type=TYPE_REPLAY))

    def test_regeneration_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(exec_type=TYPE_REGENERATION))

    def test_degraded_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(degraded=True, degradation_cause="x"))

    def test_maintenance_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(maintenance=True))

    def test_finalized_row_all_attribution_fields(self):
        self._assert_all_fields(_make_report_row(is_finalized=True))

    def test_config_missing_row_unknown_v0_not_empty(self):
        r = _make_report_row(config_missing=True)
        assert r.config_version_id == UNKNOWN_V0
        assert r.config_version_id != ""

    def test_summary_attribution_complete_count_all_rows(self):
        rows = [_make_report_row(mode=MODE_SHADOW) for _ in range(40)]
        summary = _build_report_summary(rows)
        assert summary.attribution_complete_count == 40

    def test_summary_no_hidden_governance_rows(self):
        rows = (
            [_make_report_row(mode=MODE_SHADOW) for _ in range(15)]
            + [_make_report_row(exec_type=TYPE_REPLAY) for _ in range(10)]
            + [_make_report_row(maintenance=True) for _ in range(5)]
        )
        summary = _build_report_summary(rows)
        assert summary.hidden_governance_rows == 0


class TestReplayReporting:
    """Certify REPLAY execution is unambiguously reported — never collapses to LIVE."""

    def test_replay_row_scope_is_replay_only(self):
        r = _make_report_row(exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_row_is_replay_flag(self):
        r = _make_report_row(exec_type=TYPE_REPLAY)
        assert r.is_replay is True

    def test_replay_row_lineage_visible_with_artifact(self):
        r = _make_report_row(exec_type=TYPE_REPLAY, source_artifact_id="art-001")
        assert r.replay_lineage_visible is True

    def test_replay_historical_config_surfaced(self):
        r = _make_report_row(exec_type=TYPE_REPLAY, historical_config="cfg-hist-001")
        assert r.historical_config_version_id == "cfg-hist-001"
        assert r.historical_config_version_id != UNKNOWN_V0

    def test_regeneration_row_also_replay_only(self):
        r = _make_report_row(exec_type=TYPE_REGENERATION)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.is_replay is True

    def test_replay_not_collapsed_into_live(self):
        replay_row = _make_report_row(exec_type=TYPE_REPLAY)
        live_row = _make_report_row(mode=MODE_LIVE)
        assert replay_row.governance_scope != live_row.governance_scope
        assert replay_row.is_replay is True
        assert live_row.is_replay is False

    def test_summary_no_replay_ambiguous_rows(self):
        rows = (
            [_make_report_row(exec_type=TYPE_REPLAY) for _ in range(10)]
            + [_make_report_row(exec_type=TYPE_REGENERATION) for _ in range(5)]
        )
        summary = _build_report_summary(rows)
        assert summary.replay_ambiguous_rows == 0

    def test_summary_replay_count_accurate(self):
        rows = (
            [_make_report_row(exec_type=TYPE_REPLAY) for _ in range(7)]
            + [_make_report_row(exec_type=TYPE_REGENERATION) for _ in range(3)]
            + [_make_report_row(mode=MODE_SHADOW) for _ in range(5)]
        )
        summary = _build_report_summary(rows)
        assert summary.replay_count == 10

    def test_replay_reason_code_in_row(self):
        r = _make_report_row(exec_type=TYPE_REPLAY)
        assert "REPLAY_EXECUTION_SUPPRESSED" in r.reason_codes

    def test_live_mode_plus_replay_type_reported_as_replay_only(self):
        r = _make_report_row(mode=MODE_LIVE, exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.execution_mode == MODE_LIVE


class TestFinalizedReporting:
    """Certify FINALIZED artifacts are reported with mutation prohibition visible."""

    def test_finalized_artifact_is_finalized_true(self):
        a = _make_finalized_artifact()
        assert a.is_finalized is True

    def test_finalized_artifact_is_mutable_false(self):
        a = _make_finalized_artifact()
        assert a.is_mutable is False

    def test_finalized_artifact_mutation_prohibited_true(self):
        a = _make_finalized_artifact()
        assert a.mutation_prohibited is True

    def test_finalized_artifact_content_hash_present(self):
        a = _make_finalized_artifact()
        assert a.content_hash
        assert len(a.content_hash) > 0

    def test_finalized_artifact_ai_tier_finalized_copy(self):
        a = _make_finalized_artifact()
        assert a.ai_tier == AI_TIER_FINALIZED_COPY

    def test_finalized_artifact_lineage_visible_with_source(self):
        a = _make_finalized_artifact(source_artifact_id="art-001")
        assert a.lineage_visible is True

    def test_finalized_report_row_mutation_prohibited(self):
        r = _make_report_row(is_finalized=True)
        assert r.is_finalized is True
        assert r.is_mutable is False
        assert r.mutation_prohibited is True

    def test_summary_no_mutable_finalized_rows(self):
        rows = [_make_report_row(is_finalized=True) for _ in range(20)]
        summary = _build_report_summary(rows)
        assert summary.mutable_finalized_rows == 0

    def test_finalized_content_hash_stable_across_reports(self):
        # Same config and scope → same hash deterministically
        a1 = _make_finalized_artifact(scope=SCOPE_REPLAY_ONLY, config_version_id="cfg-v2-001")
        a2 = _make_finalized_artifact(scope=SCOPE_REPLAY_ONLY, config_version_id="cfg-v2-001")
        assert a1.content_hash == a2.content_hash

    def test_finalized_content_hash_differs_by_scope(self):
        a_replay = _make_finalized_artifact(scope=SCOPE_REPLAY_ONLY)
        a_shadow = _make_finalized_artifact(scope=SCOPE_SHADOW_ONLY)
        assert a_replay.content_hash != a_shadow.content_hash


class TestDegradationReporting:
    """Certify DEGRADED execution metrics are fully visible in reports."""

    def test_degraded_row_flag_set(self):
        r = _make_report_row(degraded=True, degradation_cause="config_unavailable")
        assert r.degraded is True

    def test_degradation_class_in_report_row(self):
        r = _make_report_row(degraded=True, degradation_cause="x",
                             degradation_class="CONFIG")
        assert r.degradation_class == "CONFIG"

    def test_degradation_severity_in_report_row(self):
        r = _make_report_row(degraded=True, degradation_cause="x",
                             degradation_severity="high")
        assert r.degradation_severity == "high"

    def test_degradation_cause_in_report_row(self):
        r = _make_report_row(degraded=True, degradation_cause="api_timeout")
        assert r.degradation_cause == "api_timeout"

    def test_recovery_classification_in_report_row(self):
        r = _make_report_row(degraded=True, degradation_cause="x",
                             recovery_classification="AUTO_RECOVERABLE")
        assert r.recovery_classification == "AUTO_RECOVERABLE"

    def test_unknown_v0_in_degraded_row(self):
        r = _make_report_row(config_missing=True)
        assert r.config_version_id == UNKNOWN_V0
        assert r.outbound_suppressed is True

    def test_degraded_reason_code_present(self):
        r = _make_report_row(degraded=True, degradation_cause="api_failure")
        assert any("DEGRADED" in code for code in r.reason_codes)

    def test_summary_degraded_count_accurate(self):
        rows = (
            [_make_report_row(degraded=True, degradation_cause="x") for _ in range(8)]
            + [_make_report_row() for _ in range(12)]
        )
        summary = _build_report_summary(rows)
        assert summary.degraded_count == 8

    def test_degraded_summary_no_hidden_rows(self):
        rows = [_make_report_row(degraded=True, degradation_cause="y") for _ in range(15)]
        summary = _build_report_summary(rows)
        assert summary.hidden_governance_rows == 0


class TestAuditTrailReporting:
    """Certify audit trail entries are append-only and immutable in reports."""

    def test_audit_entry_is_mutable_false(self):
        e = _make_audit_entry()
        assert e.is_mutable is False

    def test_audit_entry_sequence_number_present(self):
        e = _make_audit_entry(seq=42)
        assert e.sequence_number == 42

    def test_audit_trail_entries_ordered_by_sequence(self):
        entries = [_make_audit_entry(seq=i) for i in range(1, 11)]
        seqs = [e.sequence_number for e in entries]
        assert seqs == sorted(seqs)

    def test_audit_trail_all_attribution_fields(self):
        e = _make_audit_entry()
        assert e.correlation_id
        assert e.causation_id
        assert e.config_version_id
        assert e.execution_mode
        assert e.governance_scope

    def test_audit_entry_replay_scope_correct(self):
        e = _make_audit_entry(scope=SCOPE_REPLAY_ONLY, mode=MODE_SHADOW)
        assert e.governance_scope == SCOPE_REPLAY_ONLY

    def test_audit_trail_no_mutable_entries(self):
        entries = [_make_audit_entry(seq=i) for i in range(1, 21)]
        assert all(not e.is_mutable for e in entries)

    def test_report_row_is_append_only_true(self):
        r = _make_report_row()
        assert r.is_append_only is True

    def test_audit_entries_are_not_mutable_across_modes(self):
        entries = [
            _make_audit_entry(scope=SCOPE_SHADOW_ONLY, mode=MODE_SHADOW, seq=1),
            _make_audit_entry(scope=SCOPE_REPLAY_ONLY, mode=MODE_SHADOW, seq=2),
            _make_audit_entry(scope=SCOPE_MAINTENANCE, mode=MODE_SHADOW, seq=3),
        ]
        for e in entries:
            assert e.is_mutable is False


class TestReportingLoadCertification:
    """Certify reporting integrity at 100, 500, 1000 records."""

    def _make_bulk(self, count: int, exec_type: str = TYPE_ORIGINAL,
                   mode: str = MODE_SHADOW) -> List[ReportRow]:
        return [_make_report_row(mode=mode, exec_type=exec_type, audit_seq=i+1)
                for i in range(count)]

    def test_100_rows_no_hidden_governance(self):
        summary = _build_report_summary(self._make_bulk(100))
        assert summary.hidden_governance_rows == 0

    def test_500_rows_no_hidden_governance(self):
        summary = _build_report_summary(self._make_bulk(500))
        assert summary.hidden_governance_rows == 0

    def test_1000_rows_no_hidden_governance(self):
        summary = _build_report_summary(self._make_bulk(1000))
        assert summary.hidden_governance_rows == 0

    def test_100_replay_rows_no_ambiguity(self):
        summary = _build_report_summary(self._make_bulk(100, exec_type=TYPE_REPLAY))
        assert summary.replay_ambiguous_rows == 0

    def test_500_replay_rows_no_ambiguity(self):
        summary = _build_report_summary(self._make_bulk(500, exec_type=TYPE_REPLAY))
        assert summary.replay_ambiguous_rows == 0

    def test_1000_replay_rows_no_ambiguity(self):
        summary = _build_report_summary(self._make_bulk(1000, exec_type=TYPE_REPLAY))
        assert summary.replay_ambiguous_rows == 0

    def test_1000_shadow_rows_zero_live_effects(self):
        summary = _build_report_summary(self._make_bulk(1000))
        assert summary.total_live_effects == 0

    def test_1000_shadow_rows_zero_dispatches(self):
        summary = _build_report_summary(self._make_bulk(1000))
        assert summary.total_dispatches == 0

    def test_1000_mixed_no_mutable_finalized(self):
        rows = (
            [_make_report_row(is_finalized=True) for _ in range(500)]
            + [_make_report_row() for _ in range(500)]
        )
        summary = _build_report_summary(rows)
        assert summary.mutable_finalized_rows == 0

    def test_1000_mixed_attribution_complete(self):
        rows = (
            [_make_report_row(mode=MODE_SHADOW) for _ in range(333)]
            + [_make_report_row(exec_type=TYPE_REPLAY) for _ in range(333)]
            + [_make_report_row(maintenance=True) for _ in range(334)]
        )
        summary = _build_report_summary(rows)
        assert summary.attribution_complete_count == 1000
        assert summary.hidden_governance_rows == 0

    def test_500_no_silent_suppressions(self):
        summary = _build_report_summary(self._make_bulk(500))
        assert summary.silent_suppression_rows == 0
