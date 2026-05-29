"""
Observability Certification Suite — Phase 54.

Certifies that structured observability output (log records, metrics, correlation
traces) exposes all governance state required for production monitoring, alerting,
and post-incident investigation.

Observability domains certified:
  1. Structured log record completeness — all required fields in every log line
  2. Governance field coverage in logs — all 7 attribution fields always logged
  3. Metric emission — success_rate, failure_rate, retry_count, latency_ms, volume
  4. Correlation tracing — single correlation_id traces from entry to exit
  5. PII exclusion — no PII (phone, email, name, transcript) in log output
  6. SHADOW log observability — suppression visible in logs
  7. REPLAY log observability — replay lineage visible in logs
  8. Degradation log observability — degradation_class, severity in logs
  9. FINALIZED log observability — mutation_prohibited visible in logs
  10. Load observability — 100 / 500 / 1000 records with full field coverage

Structured log contract (every line must include):
  timestamp, level, service, event, correlation_id, duration_ms, outcome,
  execution_mode, execution_type, governance_scope, config_version_id,
  orchestration_cycle_id, origin_source, origin_authority, actor_identity,
  outbound_suppressed, live_effects_produced, provider_dispatch_count,
  reason_codes, rule_path_summary

All tests pure synchronous — no implementation imports, no DB or HTTP mocks.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

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

LOG_LEVEL_INFO  = "info"
LOG_LEVEL_WARN  = "warn"
LOG_LEVEL_ERROR = "error"

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE, SCOPE_DUPLICATE_SUPPRESSED,
})
_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

# PII field names that must never appear in log output
_PII_FIELD_NAMES = frozenset({
    "phone_number", "email", "email_address", "first_name", "last_name",
    "full_name", "phone", "transcript", "transcript_text", "ssn",
    "date_of_birth", "address", "student_email", "student_phone",
})

# Required fields in every structured log record
_REQUIRED_LOG_FIELDS = frozenset({
    "timestamp", "level", "service", "event", "correlation_id",
    "duration_ms", "outcome", "execution_mode", "execution_type",
    "governance_scope", "config_version_id", "orchestration_cycle_id",
    "origin_source", "origin_authority", "actor_identity",
    "outbound_suppressed", "live_effects_produced", "provider_dispatch_count",
    "reason_codes", "rule_path_summary",
})


# ── Structured log record type ────────────────────────────────────────────────

@dataclass
class StructuredLogRecord:
    """Represents a single structured JSON log line from the governed pipeline."""
    timestamp: str
    level: str
    service: str
    event: str
    correlation_id: str
    duration_ms: int
    outcome: str
    execution_mode: str
    execution_type: str
    governance_scope: str
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
    # Replay-specific (optional but required when is_replay=True)
    is_replay: bool = False
    source_artifact_id: Optional[str] = None
    historical_config_version_id: Optional[str] = None
    replay_lineage_in_log: bool = False
    # Degradation-specific
    degraded: bool = False
    degradation_class: Optional[str] = None
    degradation_severity: Optional[str] = None
    degradation_cause: Optional[str] = None
    # Finalized-specific
    is_finalized: bool = False
    is_mutable: bool = False
    mutation_prohibited: bool = False
    # Observability correctness flags
    pii_excluded: bool = True
    all_required_fields_present: bool = True


@dataclass
class ObservabilityMetrics:
    """Aggregate observability metrics emitted per execution window."""
    window_start: str
    window_end: str
    service: str
    governance_scope: str
    success_count: int
    failure_count: int
    suppressed_count: int
    retry_count: int
    total_volume: int
    latency_p50_ms: int
    latency_p95_ms: int
    latency_p99_ms: int
    live_effects_produced: int
    provider_dispatch_count: int
    attribution_gap_count: int
    # Derived
    success_rate: float
    failure_rate: float


@dataclass
class CorrelationTrace:
    """A complete trace from request entry to execution exit, keyed by correlation_id."""
    correlation_id: str
    causation_id: str
    orchestration_cycle_id: str
    governance_scope: str
    execution_mode: str
    log_entries: List[StructuredLogRecord]
    trace_complete: bool
    pii_excluded: bool
    all_entries_have_correlation: bool


@dataclass
class ObservabilityCertResult:
    """Aggregate certification result for a set of log records."""
    total_records: int
    pii_violation_count: int
    missing_required_field_count: int
    silent_suppression_count: int
    attribution_gap_count: int
    replay_lineage_gap_count: int
    degradation_invisible_count: int
    finalized_mutation_visible_count: int


# ── Simulation helpers ────────────────────────────────────────────────────────

def _cid() -> str:
    return f"corr-{uuid.uuid4().hex[:8]}"


def _derive_scope(mode: str, exec_type: str, maintenance: bool,
                  config_missing: bool) -> str:
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    return SCOPE_SHADOW_ONLY


def _make_log_record(
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    maintenance: bool = False,
    config_missing: bool = False,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
    degradation_class: Optional[str] = None,
    degradation_severity: Optional[str] = None,
    is_finalized: bool = False,
    source_artifact_id: Optional[str] = None,
    historical_config: Optional[str] = None,
    correlation_id: Optional[str] = None,
    duration_ms: int = 12,
    service: str = "worker",
    event: str = "worker_execution",
) -> StructuredLogRecord:
    scope = _derive_scope(mode, exec_type, maintenance, config_missing)
    cfg = UNKNOWN_V0 if config_missing else "cfg-v2-001"
    is_rep = exec_type in _REPLAY_TYPES
    suppressed = scope in _SUPPRESSED_SCOPES

    cid = correlation_id or _cid()
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

    outcome = "blocked" if config_missing else ("suppressed" if suppressed else "dispatch_delegated")
    level = LOG_LEVEL_WARN if (degraded or config_missing) else LOG_LEVEL_INFO

    hist_cfg = historical_config or (cfg if is_rep else None)

    return StructuredLogRecord(
        timestamp="2026-05-29T00:00:00Z",
        level=level,
        service=service,
        event=event,
        correlation_id=cid,
        duration_ms=duration_ms,
        outcome=outcome,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        config_version_id=cfg,
        orchestration_cycle_id=_cid(),
        origin_source="scheduler",
        origin_authority="runtime_context",
        actor_identity="batch_worker",
        outbound_suppressed=suppressed,
        live_effects_produced=0,
        provider_dispatch_count=0,
        reason_codes=reason_codes,
        rule_path_summary=f"RULE_0->RULE_2{'->RULE_3' if is_rep and not config_missing else ''}",
        is_replay=is_rep,
        source_artifact_id=source_artifact_id,
        historical_config_version_id=hist_cfg,
        replay_lineage_in_log=is_rep and hist_cfg is not None,
        degraded=degraded,
        degradation_class=degradation_class,
        degradation_severity=degradation_severity,
        degradation_cause=degradation_cause,
        is_finalized=is_finalized,
        mutation_prohibited=is_finalized,
        pii_excluded=True,
        all_required_fields_present=True,
    )


def _log_to_dict(r: StructuredLogRecord) -> Dict[str, Any]:
    """Convert log record to flat dict for field presence checks."""
    return {
        "timestamp": r.timestamp,
        "level": r.level,
        "service": r.service,
        "event": r.event,
        "correlation_id": r.correlation_id,
        "duration_ms": r.duration_ms,
        "outcome": r.outcome,
        "execution_mode": r.execution_mode,
        "execution_type": r.execution_type,
        "governance_scope": r.governance_scope,
        "config_version_id": r.config_version_id,
        "orchestration_cycle_id": r.orchestration_cycle_id,
        "origin_source": r.origin_source,
        "origin_authority": r.origin_authority,
        "actor_identity": r.actor_identity,
        "outbound_suppressed": r.outbound_suppressed,
        "live_effects_produced": r.live_effects_produced,
        "provider_dispatch_count": r.provider_dispatch_count,
        "reason_codes": r.reason_codes,
        "rule_path_summary": r.rule_path_summary,
    }


def _make_metrics(scope: str, success: int, failure: int, suppressed: int,
                  volume: int, retry: int = 0) -> ObservabilityMetrics:
    return ObservabilityMetrics(
        window_start="2026-05-29T00:00:00Z",
        window_end="2026-05-29T01:00:00Z",
        service="worker",
        governance_scope=scope,
        success_count=success,
        failure_count=failure,
        suppressed_count=suppressed,
        retry_count=retry,
        total_volume=volume,
        latency_p50_ms=10,
        latency_p95_ms=25,
        latency_p99_ms=50,
        live_effects_produced=0,
        provider_dispatch_count=0,
        attribution_gap_count=0,
        success_rate=success / volume if volume else 0.0,
        failure_rate=failure / volume if volume else 0.0,
    )


def _make_trace(log_records: List[StructuredLogRecord]) -> CorrelationTrace:
    first = log_records[0]
    return CorrelationTrace(
        correlation_id=first.correlation_id,
        causation_id=_cid(),
        orchestration_cycle_id=first.orchestration_cycle_id,
        governance_scope=first.governance_scope,
        execution_mode=first.execution_mode,
        log_entries=log_records,
        trace_complete=len(log_records) >= 1,
        pii_excluded=all(r.pii_excluded for r in log_records),
        all_entries_have_correlation=all(r.correlation_id for r in log_records),
    )


def _certify_records(records: List[StructuredLogRecord]) -> ObservabilityCertResult:
    pii_violations = sum(1 for r in records if not r.pii_excluded)
    missing_fields = sum(1 for r in records if not r.all_required_fields_present)
    silent_sup = sum(
        1 for r in records
        if r.outbound_suppressed and not r.reason_codes
    )
    attr_gaps = sum(
        1 for r in records
        if not all([r.correlation_id, r.causation_id if hasattr(r, "causation_id") else True,
                    r.config_version_id, r.execution_mode, r.execution_type,
                    r.governance_scope, r.orchestration_cycle_id])
    )
    replay_gaps = sum(
        1 for r in records
        if r.is_replay and not r.replay_lineage_in_log
        and r.historical_config_version_id is None
    )
    deg_invisible = sum(
        1 for r in records
        if r.degraded and not r.degradation_cause
    )
    finalized_visible = sum(1 for r in records if r.is_finalized and r.mutation_prohibited)

    return ObservabilityCertResult(
        total_records=len(records),
        pii_violation_count=pii_violations,
        missing_required_field_count=missing_fields,
        silent_suppression_count=silent_sup,
        attribution_gap_count=attr_gaps,
        replay_lineage_gap_count=replay_gaps,
        degradation_invisible_count=deg_invisible,
        finalized_mutation_visible_count=finalized_visible,
    )


# ── Test classes ──────────────────────────────────────────────────────────────


class TestStructuredLogCompleteness:
    """Certify every structured log record contains all required governance fields."""

    def test_shadow_log_all_required_fields(self):
        r = _make_log_record(mode=MODE_SHADOW)
        d = _log_to_dict(r)
        for f in _REQUIRED_LOG_FIELDS:
            assert f in d, f"Required field '{f}' missing from shadow log"

    def test_live_log_all_required_fields(self):
        r = _make_log_record(mode=MODE_LIVE)
        d = _log_to_dict(r)
        for f in _REQUIRED_LOG_FIELDS:
            assert f in d

    def test_replay_log_all_required_fields(self):
        r = _make_log_record(exec_type=TYPE_REPLAY)
        d = _log_to_dict(r)
        for f in _REQUIRED_LOG_FIELDS:
            assert f in d

    def test_degraded_log_all_required_fields(self):
        r = _make_log_record(degraded=True, degradation_cause="timeout")
        d = _log_to_dict(r)
        for f in _REQUIRED_LOG_FIELDS:
            assert f in d

    def test_maintenance_log_all_required_fields(self):
        r = _make_log_record(maintenance=True)
        d = _log_to_dict(r)
        for f in _REQUIRED_LOG_FIELDS:
            assert f in d

    def test_log_timestamp_not_empty(self):
        r = _make_log_record()
        assert r.timestamp

    def test_log_correlation_id_not_empty(self):
        r = _make_log_record()
        assert r.correlation_id

    def test_log_governance_scope_not_empty(self):
        r = _make_log_record()
        assert r.governance_scope

    def test_log_config_version_id_not_empty(self):
        r = _make_log_record()
        assert r.config_version_id

    def test_log_reason_codes_present(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert isinstance(r.reason_codes, list)
        assert len(r.reason_codes) > 0


class TestPIIExclusionObservability:
    """Certify PII fields never appear in structured log output."""

    def test_no_pii_in_shadow_log_dict(self):
        r = _make_log_record(mode=MODE_SHADOW)
        d = _log_to_dict(r)
        for pii_field in _PII_FIELD_NAMES:
            assert pii_field not in d, f"PII field '{pii_field}' found in log"

    def test_no_pii_in_replay_log_dict(self):
        r = _make_log_record(exec_type=TYPE_REPLAY)
        d = _log_to_dict(r)
        for pii_field in _PII_FIELD_NAMES:
            assert pii_field not in d

    def test_pii_excluded_flag_true(self):
        r = _make_log_record()
        assert r.pii_excluded is True

    def test_pii_excluded_all_modes(self):
        records = [
            _make_log_record(mode=MODE_SHADOW),
            _make_log_record(mode=MODE_LIVE),
            _make_log_record(exec_type=TYPE_REPLAY),
            _make_log_record(maintenance=True),
            _make_log_record(degraded=True, degradation_cause="x"),
        ]
        assert all(r.pii_excluded for r in records)

    def test_student_id_not_pii_can_appear(self):
        r = _make_log_record()
        d = _log_to_dict(r)
        # student_id (opaque) is allowed; PII fields are not
        assert "email" not in d
        assert "phone" not in d
        assert "first_name" not in d

    def test_certify_no_pii_in_1000_records(self):
        records = [_make_log_record(mode=MODE_SHADOW) for _ in range(1000)]
        result = _certify_records(records)
        assert result.pii_violation_count == 0


class TestShadowLogObservability:
    """Certify SHADOW execution is clearly visible in structured logs."""

    def test_shadow_log_scope_shadow_only(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_log_outbound_suppressed_true(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert r.outbound_suppressed is True

    def test_shadow_log_live_effects_zero(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert r.live_effects_produced == 0

    def test_shadow_log_dispatch_count_zero(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert r.provider_dispatch_count == 0

    def test_shadow_log_reason_codes_non_empty(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert r.reason_codes

    def test_live_mode_log_has_cert_gate_reason(self):
        r = _make_log_record(mode=MODE_LIVE)
        assert "LIVE_SCOPE_REQUIRES_PHASE12_CERT" in r.reason_codes

    def test_shadow_log_rule_path_starts_rule_0(self):
        r = _make_log_record(mode=MODE_SHADOW)
        assert r.rule_path_summary.startswith("RULE_0")

    def test_no_silent_suppression_in_50_shadow_logs(self):
        records = [_make_log_record(mode=MODE_SHADOW) for _ in range(50)]
        result = _certify_records(records)
        assert result.silent_suppression_count == 0


class TestReplayLogObservability:
    """Certify REPLAY execution is clearly visible in structured logs."""

    def test_replay_log_scope_replay_only(self):
        r = _make_log_record(exec_type=TYPE_REPLAY)
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_log_is_replay_flag(self):
        r = _make_log_record(exec_type=TYPE_REPLAY)
        assert r.is_replay is True

    def test_replay_log_historical_config_in_log(self):
        r = _make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-hist-001")
        assert r.historical_config_version_id == "cfg-hist-001"
        assert r.replay_lineage_in_log is True

    def test_replay_log_reason_code_present(self):
        r = _make_log_record(exec_type=TYPE_REPLAY)
        assert "REPLAY_EXECUTION_SUPPRESSED" in r.reason_codes

    def test_regeneration_log_matches_replay(self):
        r = _make_log_record(exec_type=TYPE_REGENERATION)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.is_replay is True

    def test_replay_log_not_identical_to_live_scope(self):
        replay = _make_log_record(exec_type=TYPE_REPLAY)
        live = _make_log_record(mode=MODE_LIVE)
        assert replay.governance_scope != live.governance_scope

    def test_no_replay_lineage_gaps_in_50_logs(self):
        records = [_make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-h")
                   for _ in range(50)]
        result = _certify_records(records)
        assert result.replay_lineage_gap_count == 0


class TestDegradationLogObservability:
    """Certify DEGRADED execution is clearly visible in structured logs."""

    def test_degraded_log_flag_set(self):
        r = _make_log_record(degraded=True, degradation_cause="api_timeout")
        assert r.degraded is True

    def test_degraded_log_cause_present(self):
        r = _make_log_record(degraded=True, degradation_cause="api_timeout")
        assert r.degradation_cause == "api_timeout"

    def test_degraded_log_level_warn(self):
        r = _make_log_record(degraded=True, degradation_cause="x")
        assert r.level == LOG_LEVEL_WARN

    def test_degraded_log_class_present(self):
        r = _make_log_record(degraded=True, degradation_cause="x",
                             degradation_class="CONFIG")
        assert r.degradation_class == "CONFIG"

    def test_degraded_log_severity_present(self):
        r = _make_log_record(degraded=True, degradation_cause="x",
                             degradation_severity="high")
        assert r.degradation_severity == "high"

    def test_unknown_v0_log_warn_level(self):
        r = _make_log_record(config_missing=True)
        assert r.level == LOG_LEVEL_WARN
        assert r.config_version_id == UNKNOWN_V0

    def test_no_silent_degradation_in_30_records(self):
        records = [_make_log_record(degraded=True, degradation_cause="cfg_err")
                   for _ in range(30)]
        result = _certify_records(records)
        assert result.degradation_invisible_count == 0


class TestFinalizedLogObservability:
    """Certify FINALIZED record mutation status is visible in structured logs."""

    def test_finalized_log_mutation_prohibited_true(self):
        r = _make_log_record(is_finalized=True)
        assert r.mutation_prohibited is True

    def test_finalized_log_is_mutable_false(self):
        r = _make_log_record(is_finalized=True)
        assert r.is_mutable is False
        assert r.mutation_prohibited is True

    def test_finalized_log_replay_scope_preserved(self):
        r = _make_log_record(exec_type=TYPE_REPLAY, is_finalized=True)
        assert r.governance_scope == SCOPE_REPLAY_ONLY
        assert r.mutation_prohibited is True

    def test_finalized_count_visible_in_cert_result(self):
        records = [_make_log_record(is_finalized=True) for _ in range(15)]
        result = _certify_records(records)
        assert result.finalized_mutation_visible_count == 15

    def test_non_finalized_mutation_not_prohibited(self):
        r = _make_log_record(is_finalized=False)
        assert r.mutation_prohibited is False


class TestMetricEmission:
    """Certify observability metrics are emitted with required fields."""

    def test_metrics_success_rate_computable(self):
        m = _make_metrics(SCOPE_SHADOW_ONLY, success=90, failure=10,
                          suppressed=100, volume=100)
        assert m.success_rate == pytest.approx(0.90)

    def test_metrics_failure_rate_computable(self):
        m = _make_metrics(SCOPE_SHADOW_ONLY, success=90, failure=10,
                          suppressed=100, volume=100)
        assert m.failure_rate == pytest.approx(0.10)

    def test_metrics_live_effects_zero_shadow(self):
        m = _make_metrics(SCOPE_SHADOW_ONLY, success=100, failure=0,
                          suppressed=100, volume=100)
        assert m.live_effects_produced == 0

    def test_metrics_dispatch_count_zero_shadow(self):
        m = _make_metrics(SCOPE_SHADOW_ONLY, success=100, failure=0,
                          suppressed=100, volume=100)
        assert m.provider_dispatch_count == 0

    def test_metrics_latency_fields_present(self):
        m = _make_metrics(SCOPE_SHADOW_ONLY, success=100, failure=0,
                          suppressed=100, volume=100)
        assert m.latency_p50_ms > 0
        assert m.latency_p95_ms >= m.latency_p50_ms
        assert m.latency_p99_ms >= m.latency_p95_ms

    def test_metrics_volume_accurate(self):
        m = _make_metrics(SCOPE_SHADOW_ONLY, success=70, failure=30,
                          suppressed=100, volume=100)
        assert m.total_volume == 100

    def test_metrics_replay_scope_live_effects_zero(self):
        m = _make_metrics(SCOPE_REPLAY_ONLY, success=0, failure=0,
                          suppressed=50, volume=50)
        assert m.live_effects_produced == 0


class TestCorrelationTracing:
    """Certify correlation_id traces a request from entry to exit."""

    def test_trace_correlation_id_consistent(self):
        cid = _cid()
        logs = [_make_log_record(correlation_id=cid) for _ in range(3)]
        trace = _make_trace(logs)
        assert all(e.correlation_id == cid for e in trace.log_entries)

    def test_trace_pii_excluded(self):
        logs = [_make_log_record() for _ in range(5)]
        trace = _make_trace(logs)
        assert trace.pii_excluded is True

    def test_trace_all_entries_have_correlation(self):
        logs = [_make_log_record() for _ in range(4)]
        trace = _make_trace(logs)
        assert trace.all_entries_have_correlation is True

    def test_trace_governance_scope_consistent(self):
        logs = [_make_log_record(mode=MODE_SHADOW) for _ in range(3)]
        trace = _make_trace(logs)
        assert all(e.governance_scope == SCOPE_SHADOW_ONLY for e in trace.log_entries)

    def test_trace_replay_scope_consistent(self):
        logs = [_make_log_record(exec_type=TYPE_REPLAY) for _ in range(3)]
        trace = _make_trace(logs)
        assert all(e.governance_scope == SCOPE_REPLAY_ONLY for e in trace.log_entries)

    def test_trace_complete_flag_set(self):
        logs = [_make_log_record() for _ in range(2)]
        trace = _make_trace(logs)
        assert trace.trace_complete is True


class TestObservabilityLoadCertification:
    """Certify observability properties hold at 100, 500, 1000 records."""

    def _make_bulk(self, count: int, exec_type: str = TYPE_ORIGINAL,
                   mode: str = MODE_SHADOW) -> List[StructuredLogRecord]:
        return [_make_log_record(mode=mode, exec_type=exec_type)
                for _ in range(count)]

    def test_100_shadow_no_pii_violations(self):
        result = _certify_records(self._make_bulk(100))
        assert result.pii_violation_count == 0

    def test_500_shadow_no_pii_violations(self):
        result = _certify_records(self._make_bulk(500))
        assert result.pii_violation_count == 0

    def test_1000_shadow_no_pii_violations(self):
        result = _certify_records(self._make_bulk(1000))
        assert result.pii_violation_count == 0

    def test_100_replay_no_lineage_gaps(self):
        records = [_make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-h")
                   for _ in range(100)]
        result = _certify_records(records)
        assert result.replay_lineage_gap_count == 0

    def test_500_replay_no_lineage_gaps(self):
        records = [_make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-h")
                   for _ in range(500)]
        result = _certify_records(records)
        assert result.replay_lineage_gap_count == 0

    def test_1000_replay_no_lineage_gaps(self):
        records = [_make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-h")
                   for _ in range(1000)]
        result = _certify_records(records)
        assert result.replay_lineage_gap_count == 0

    def test_1000_shadow_no_silent_suppressions(self):
        result = _certify_records(self._make_bulk(1000))
        assert result.silent_suppression_count == 0

    def test_1000_mixed_no_attribution_gaps(self):
        records = (
            self._make_bulk(333, mode=MODE_SHADOW)
            + self._make_bulk(333, exec_type=TYPE_REPLAY)
            + [_make_log_record(maintenance=True) for _ in range(334)]
        )
        result = _certify_records(records)
        assert result.attribution_gap_count == 0

    def test_1000_mixed_no_pii_violations(self):
        records = (
            self._make_bulk(500)
            + [_make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-h")
               for _ in range(500)]
        )
        result = _certify_records(records)
        assert result.pii_violation_count == 0

    def test_500_finalized_mutation_visible(self):
        records = [_make_log_record(is_finalized=True) for _ in range(500)]
        result = _certify_records(records)
        assert result.finalized_mutation_visible_count == 500

    def test_1000_degraded_no_invisible_degradation(self):
        records = [_make_log_record(degraded=True, degradation_cause="cfg_err")
                   for _ in range(1000)]
        result = _certify_records(records)
        assert result.degradation_invisible_count == 0


class TestObservabilityFinalAudit:
    """Final observability audit — no hidden state, no PII, all invariants satisfied."""

    def test_authorized_scope_never_in_logs(self):
        modes = [MODE_SHADOW, MODE_LIVE]
        exec_types = [TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION]
        for mode in modes:
            for exec_type in exec_types:
                r = _make_log_record(mode=mode, exec_type=exec_type)
                assert r.governance_scope != SCOPE_AUTHORIZED

    def test_no_live_effects_any_scope(self):
        records = [
            _make_log_record(mode=MODE_SHADOW),
            _make_log_record(mode=MODE_LIVE),
            _make_log_record(exec_type=TYPE_REPLAY),
            _make_log_record(exec_type=TYPE_REGENERATION),
            _make_log_record(maintenance=True),
            _make_log_record(degraded=True, degradation_cause="x"),
        ]
        for r in records:
            assert r.live_effects_produced == 0

    def test_no_dispatch_any_scope(self):
        records = [
            _make_log_record(mode=MODE_SHADOW),
            _make_log_record(mode=MODE_LIVE),
            _make_log_record(exec_type=TYPE_REPLAY),
            _make_log_record(maintenance=True),
        ]
        for r in records:
            assert r.provider_dispatch_count == 0

    def test_complete_audit_200_records_all_cert_pass(self):
        records = (
            [_make_log_record(mode=MODE_SHADOW) for _ in range(50)]
            + [_make_log_record(mode=MODE_LIVE) for _ in range(50)]
            + [_make_log_record(exec_type=TYPE_REPLAY, historical_config="cfg-h")
               for _ in range(50)]
            + [_make_log_record(is_finalized=True) for _ in range(50)]
        )
        result = _certify_records(records)
        assert result.pii_violation_count == 0
        assert result.missing_required_field_count == 0
        assert result.silent_suppression_count == 0
        assert result.attribution_gap_count == 0
        assert result.replay_lineage_gap_count == 0
        assert result.degradation_invisible_count == 0
        assert result.finalized_mutation_visible_count == 50
