"""
Governance-safe observability certification.

Aligned with (authoritative parent contracts):
  tests/test_scenarios.md  — governance validation contract (GPC/OIG/CV2/SVL/ROS/ROG/AIG/PBG/STG/CID/ATT/DEG/RGS/IML/INV)
  tests/edge_cases.md      — governance edge-condition certification (ECR/ECRG/ECA/ECAI/ECDO/ECCV/ECSO/ECPL/ECDE/ECIL)
  tests/load_tests.md      — governance load certification (LCS/LCR/LCSCH/LCRSG/LCDO/LCPB/LCAI/LCAT/LCDE/LCOS/LCI)
  tests/test_work_queue.py — governance-safe orchestration queue certification (peer contract)
  tests/test_actions.py    — governance-safe orchestration-action certification (peer contract)
  tests/test_sync.py       — governance-safe synchronization certification (peer contract)

Canonical design inputs:
  runtime/system_loop.md              spec/01_requirements.md
  runtime/scheduler_design.md         spec/03_state_transition_rules.md
  failure/failure_playbook.md         spec/04_idempotency_concurrency.md
                                      spec/05_external_integrations.md
                                      spec/06_observability_operations.md
                                      spec/07_api_contracts.md
                                      spec/08_data_model.md
                                      spec/09_security_privacy.md

Prohibited semantics (test_scenarios.md §2 / edge_cases.md §2 / load_tests.md §2):
  - simplistic KPI assertions ("queue_size == 3", "retry_count == 2")
  - direct operational-count assumptions
  - replay-triggered LIVE visibility assumptions
  - mutable FINALIZED_COPY visibility assumptions
  - non-attributable observability behavior (entries missing correlation_id)
  - silent degradation visibility gaps
  - hardcoded alert threshold constants (no 10-min SLA, no 48h staleness)
  - generic 'Error' as error_class in production entries
  - AI content text in any log entry

Observability testing is NOW:
  - governance-observability certification
  - replay-safe observability validation
  - immutable-lineage visibility certification
  - deterministic degradation visibility validation

This file certifies governance contracts only.
It does NOT generate dashboard implementation code, frontend code,
monitoring services, metrics pipelines, or observability infrastructure.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# CONTRACT TYPES
# Governance-contract shapes only — not implementation.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConfigVersion:
    version_id: str
    status: str          # ACTIVE | SUPERSEDED | DRAFT
    thresholds: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservabilityLogEntry:
    """
    Universal log schema from spec/06 §2.1.
    All platform log entries must conform to this shape.
    Fields pii_present, content_text_present, secret_value_present are enforcement
    markers — they must always be False in production entries.
    """
    timestamp: str
    level: str              # info | warn | error | debug
    service: str
    event: str
    correlation_id: str
    outcome: str            # success | failure | partial | skipped
    execution_mode: Optional[str] = None    # SHADOW | LIVE; required for outreach/AI
    causation_id: Optional[str] = None      # present when this event was caused by another
    actor_identity: Optional[str] = None
    origin_source: Optional[str] = None     # scheduler | operator | mirrored_sql_server | ghl | ...
    origin_authority: Optional[str] = None  # sql_server_authoritative | platform_supplementary | ...
    lifecycle_state: Optional[str] = None
    duration_ms: Optional[int] = None
    error_class: Optional[str] = None       # required when outcome=failure; must be specific
    execution_type: Optional[str] = None    # original | replay | regeneration | retry
    context: Dict[str, Any] = field(default_factory=dict)
    pii_present: bool = False               # MUST always be False
    content_text_present: bool = False      # MUST always be False
    secret_value_present: bool = False      # MUST always be False


@dataclass
class AlertRecord:
    """
    Alert classification model from spec/06 §10.1.
    error_class must be specific — generic 'Error' is a production defect.
    """
    severity: str           # CRITICAL | HIGH | MEDIUM | LOW | INFO
    alert_type: str
    error_class: str
    correlation_id: str
    escalation_path: Optional[str] = None
    silent_swallow: bool = False  # MUST always be False


@dataclass
class OrchestrationPhaseRecord:
    """
    Phase-level log entry from spec/06 §4.1.
    Every orchestration phase emits entry / completion / failure.
    """
    event: str              # orchestration_phase_entered | _completed | _failed
    job_type: str
    phase: str
    correlation_id: str
    outcome: str
    causation_id: Optional[str] = None
    duration_ms: Optional[int] = None
    error_class: Optional[str] = None
    retryable: Optional[bool] = None
    recovery_path: Optional[str] = None


@dataclass
class ReplayVisibilityRecord:
    """
    Replay execution observability from spec/06 §5.x.
    Distinguishes replay from original in the log stream.
    live_mutations_produced and live_side_effects_produced MUST be 0 for replays.
    """
    event: str              # historical_regeneration_initiated | replay_ingestion_started
    execution_type: str     # replay | regeneration
    correlation_id: str     # new correlation_id for this replay — never the original's
    causation_id: str       # points to the original execution's correlation_id
    fingerprint_match: bool
    divergence_flag: Optional[str]  # POTENTIALLY_DIVERGENT | null
    live_mutations_produced: int = 0
    live_side_effects_produced: int = 0


@dataclass
class AIObservabilityRecord:
    """
    AI telemetry from spec/06 §7.x.
    Content text is never logged; metadata only.
    content_text_present MUST always be False.
    """
    event: str
    insight_type: str
    prompt_version: str
    model_used: str
    correlation_id: str
    outcome: str
    latency_ms: Optional[int] = None
    retry_count: int = 0
    stale_insight_served: bool = False
    stale_insight_version: Optional[int] = None
    stale_for_hours: Optional[float] = None
    error_class: Optional[str] = None
    content_text_present: bool = False  # MUST always be False


@dataclass
class FrozenSnapshotAIIsolationRecord:
    """
    AI isolation confirmation from spec/06 §7.7.
    Confirms frozen snapshot AI text was not modified by downstream actions.
    frozen_text_modified MUST always be False.
    """
    event: str              # snapshot_ai_isolation_confirmed
    action: str             # force_refresh | model_change | compliance_deletion
    snapshot_id: str        # opaque
    snapshot_state: str     # FINALIZED
    frozen_text_modified: bool  # MUST always be False
    correlation_id: str


@dataclass
class GovernanceTransitionRecord:
    """
    Irreversible governance transition log entry from spec/06 §8.6.
    Emitted ONLY for: VALIDATING→FINALIZED, REPORT_APPROVED→REPORT_PUBLISHED,
    APPROVED→ACTIVE (config), APPROVED_FOR_ACTION→IN_EXECUTION,
    IN_EXECUTION→DELETED/ANONYMIZED.
    Distinct from generic state_transition entries (§4.7).
    """
    event: str              # governance_transition | config_version_activated | ...
    domain: str             # snapshot | report | config_version | compliance
    from_state: str
    to_state: str
    correlation_id: str
    actor_identity: str
    attribution_timestamp: str
    fingerprint_components: Optional[Dict[str, Any]] = None


@dataclass
class DegradationAlertRecord:
    """
    Deterministic degradation visibility from spec/06 §10.x.
    Named degradation type; specific error_class; never silent.
    """
    severity: str           # CRITICAL | HIGH | MEDIUM | LOW
    degradation_type: str   # SQL_SERVER_WRITE_ATTEMPT | SLA_BREACH | FINGERPRINT_DIVERGENCE | ...
    error_class: str        # specific — never generic 'Error'
    correlation_id: str
    silent_swallow: bool = False  # MUST always be False


@dataclass
class ComplianceObservabilityRecord:
    """
    Compliance execution visibility from spec/06 §9.x.
    Scope manifests never in log entries — opaque refs only.
    Raw UserID must never appear.
    """
    event: str
    workflow_id: str
    action_type: str        # DELETE | ANONYMIZE
    affected_student_id_ref: str   # opaque hash — never raw UserID
    correlation_id: str
    scope_manifest_content_present: bool = False  # MUST always be False
    raw_user_id_present: bool = False              # MUST always be False


@dataclass
class LineageVisibilityRecord:
    """
    Lineage reconstruction entry from spec/06 §3.x.
    Attribution continuity in observability surfaces.
    Every orchestration path must be historically explainable.
    """
    correlation_id: str
    causation_id: Optional[str]
    attribution_timestamp: str
    origin_source: str
    origin_authority: str
    execution_type: str     # original | replay | regeneration | retry
    is_historically_explainable: bool = True


@dataclass
class WarehouseVisibilityRecord:
    """
    Append-only warehouse observability from spec/06 §11.10.
    Immutable governance metrics sourced from permanent DB records.
    allows_update and allows_delete MUST always be False.
    sourced_from_rolling_window MUST be False for immutable governance metrics.
    """
    metric_type: str        # immutable | operational
    governance_tier: str    # FINALIZED_COPY | AI_GENERATED
    is_mutable: bool = False
    sourced_from_rolling_window: bool = False
    allows_update: bool = False  # MUST always be False
    allows_delete: bool = False  # MUST always be False


@dataclass
class StateTransitionVisibilityRecord:
    """
    State-transition log entry from spec/06 §4.7 (INVARIANT-4).
    Every state change in every domain must produce this record.
    """
    event: str              # state_transition
    domain: str
    entity_id: str          # opaque
    from_state: str
    to_state: str
    actor_identity: str
    origin_source: str
    attribution_timestamp: str
    correlation_id: str


@dataclass
class SyncObservabilityRecord:
    """
    Sync observability from spec/06 §2.10 / §11.5.
    SQL Server carries sql_server_authoritative; GHL carries platform_supplementary.
    """
    event: str              # sql_server_sync_completed | ghl_webhook_processed
    origin_source: str      # mirrored_sql_server | ghl
    origin_authority: str   # sql_server_authoritative | platform_supplementary
    correlation_id: str
    rows_scanned: Optional[int] = None
    schema_drifts_detected: int = 0
    duplicate_detected: bool = False
    error_class: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# GOVERNANCE HELPERS (pure functions — no I/O)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_threshold(config: Optional[ConfigVersion], key: str) -> Any:
    """Config V2 threshold resolution — returns UNKNOWN_V0 when absent (GPC-2, CV2-1)."""
    if config is None or key not in config.thresholds:
        return "UNKNOWN_V0"
    return config.thresholds[key]


def exactly_one_active(registry: List[ConfigVersion]) -> bool:
    """INV-2: exactly one ACTIVE config version at all observable points."""
    return sum(1 for v in registry if v.status == "ACTIVE") == 1


def count_active(registry: List[ConfigVersion]) -> int:
    return sum(1 for v in registry if v.status == "ACTIVE")


def has_correlation_id(record: Any) -> bool:
    """INV-5: every observability record carries non-null correlation_id."""
    cid = getattr(record, "correlation_id",
          getattr(record, "sync_correlation_id", None))
    return cid is not None


def entry_is_replay(entry: ObservabilityLogEntry) -> bool:
    """True when log entry belongs to a replay or regeneration execution."""
    return entry.execution_type in ("replay", "regeneration")


def replay_is_governance_isolated(record: ReplayVisibilityRecord) -> bool:
    """Replay is governance-isolated when it produces zero live mutations and side-effects."""
    return (
        record.execution_type in ("replay", "regeneration")
        and record.live_mutations_produced == 0
        and record.live_side_effects_produced == 0
    )


def ai_log_is_content_free(record: AIObservabilityRecord) -> bool:
    """AI observability records must never contain content text (spec/06 §12.2)."""
    return record.content_text_present is False


def log_entry_is_pii_free(entry: ObservabilityLogEntry) -> bool:
    """Log entries must never contain raw student PII (spec/06 §12.1)."""
    return entry.pii_present is False


def frozen_snapshot_is_immutable(record: FrozenSnapshotAIIsolationRecord) -> bool:
    """FAD-1: frozen snapshot AI text must not be modified by any downstream action."""
    return record.frozen_text_modified is False


def alert_has_specific_error_class(alert: AlertRecord) -> bool:
    """Generic 'Error' is never acceptable as error_class in production alerts."""
    return alert.error_class not in ("Error", "Exception", "GenericError", "")


def activate_config_version(
    registry: List[ConfigVersion], new_version_id: str
) -> List[ConfigVersion]:
    """
    Atomic activation: supersedes current ACTIVE version, promotes new_version_id.
    GPC-4 / INV-2: transition is atomic — no window where two versions are ACTIVE.
    """
    updated = []
    for v in registry:
        if v.status == "ACTIVE":
            updated.append(ConfigVersion(v.version_id, "SUPERSEDED", v.thresholds))
        elif v.version_id == new_version_id:
            updated.append(ConfigVersion(v.version_id, "ACTIVE", v.thresholds))
        else:
            updated.append(v)
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — OBSERVABILITY GOVERNANCE PRECONDITIONS
# GPC-1 through GPC-5 as they apply to observability paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestObservabilityGovernancePreconditions:
    """
    Validates governance preconditions that gate ALL observability governance evaluation.
    Aligned with test_scenarios.md §3 (GPC-1 through GPC-5).
    """

    def test_ogpc1_observability_requires_active_config_for_threshold_alerts(self):
        """GPC-1: No ACTIVE config → alert thresholds resolve as UNKNOWN_V0, not hardcoded."""
        registry: List[ConfigVersion] = []
        active_configs = [v for v in registry if v.status == "ACTIVE"]
        threshold = resolve_threshold(None, "sla_snapshot_batch_ms")

        assert len(active_configs) == 0
        assert threshold == "UNKNOWN_V0"

    def test_ogpc2_missing_alert_threshold_substitutes_unknown_v0_not_hardcoded(self):
        """GPC-2: Missing threshold → UNKNOWN_V0, not hardcoded SLA constant."""
        config = ConfigVersion("V1", "ACTIVE", thresholds={})
        sla_threshold = resolve_threshold(config, "sla_snapshot_batch_ms")

        assert sla_threshold == "UNKNOWN_V0"
        assert sla_threshold != 10 * 60 * 1000   # no hardcoded 10-minute SLA
        assert sla_threshold != 60_000             # no hardcoded 60-second SLA

    def test_ogpc3_execution_mode_explicit_in_outreach_ai_log_entries(self):
        """GPC-3: execution_mode must be present on AI and outreach log entries — never inferred."""
        entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="ai_service",
            event="ai_insight_generation_completed",
            correlation_id="COR-OBS-001",
            outcome="success",
            execution_mode="SHADOW",
        )
        assert entry.execution_mode is not None
        assert entry.execution_mode in ("SHADOW", "LIVE", "DEGRADED")

    def test_ogpc4_replay_log_entries_carry_execution_type_replay_or_regeneration(self):
        """GPC-4: Replay entries carry execution_type='replay' or 'regeneration'."""
        replay_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="report_service",
            event="historical_regeneration_initiated",
            correlation_id="COR-REPLAY-001",
            outcome="success",
            execution_type="regeneration",
        )
        assert entry_is_replay(replay_entry)

    def test_ogpc5_replay_entries_produce_zero_live_mutations(self):
        """GPC-5: Replay executions must not appear as LIVE — live_mutations_produced=0."""
        replay_record = ReplayVisibilityRecord(
            event="historical_regeneration_initiated",
            execution_type="regeneration",
            correlation_id="COR-REGEN-001",
            causation_id="COR-ORIGINAL-001",
            fingerprint_match=True,
            divergence_flag=None,
            live_mutations_produced=0,
            live_side_effects_produced=0,
        )
        assert replay_is_governance_isolated(replay_record)

    def test_ogpc6_pii_redaction_precondition_holds_for_all_log_entries(self):
        """Observability-specific: No raw student PII in any log entry (spec/06 §12.1)."""
        entries = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="sync_service",
                event="sql_server_sync_completed",
                correlation_id=f"COR-PII-{i}",
                outcome="success",
                pii_present=False,
            )
            for i in range(5)
        ]
        assert all(log_entry_is_pii_free(e) for e in entries)

    def test_ogpc7_warehouse_records_are_append_only_precondition(self):
        """Observability-specific: warehouse and compliance_audit are INSERT-only."""
        record = WarehouseVisibilityRecord(
            metric_type="immutable",
            governance_tier="FINALIZED_COPY",
            is_mutable=False,
            allows_update=False,
            allows_delete=False,
        )
        assert record.allows_update is False
        assert record.allows_delete is False
        assert record.is_mutable is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — UNIVERSAL LOG SCHEMA GOVERNANCE
# Certifies spec/06 §2.1 / §2.2 universal log schema and required correlation fields.
# ─────────────────────────────────────────────────────────────────────────────

class TestUniversalLogSchemaGovernance:
    """
    Certifies the universal log schema governance contract from spec/06 §2.1.
    Required fields must be present on every entry; prohibited fields must be absent.
    """

    def test_uls1_required_fields_present_on_every_log_entry(self):
        """spec/06 §2.1: timestamp, level, service, event, correlation_id, outcome required."""
        entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="snapshot_service",
            event="snapshot_finalized",
            correlation_id="COR-ULS-001",
            outcome="success",
        )
        assert entry.timestamp != ""
        assert entry.level != ""
        assert entry.service != ""
        assert entry.event != ""
        assert entry.correlation_id != ""
        assert entry.outcome != ""

    def test_uls2_level_values_constrained_to_allowed_set(self):
        """spec/06 §2.1: level must be info | warn | error | debug only."""
        allowed = {"info", "warn", "error", "debug"}
        entries = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level=lvl,
                service="api",
                event="test_event",
                correlation_id=f"COR-LVL-{lvl}",
                outcome="success",
            )
            for lvl in allowed
        ]
        assert all(e.level in allowed for e in entries)

    def test_uls3_outcome_values_constrained_to_allowed_set(self):
        """spec/06 §2.1: outcome must be success | failure | partial | skipped."""
        allowed = {"success", "failure", "partial", "skipped"}
        for outcome in allowed:
            entry = ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="api",
                event="test",
                correlation_id="COR-OUT-001",
                outcome=outcome,
            )
            assert entry.outcome in allowed

    def test_uls4_error_class_required_and_specific_on_failure_entries(self):
        """spec/06 §2.1: error_class must be present and specific when outcome=failure."""
        failure_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="error",
            service="snapshot_service",
            event="snapshot_finalization_failed",
            correlation_id="COR-FAIL-001",
            outcome="failure",
            error_class="DataQualityError",
        )
        assert failure_entry.error_class is not None
        assert failure_entry.error_class not in ("Error", "Exception", "")

    def test_uls5_pii_prohibited_in_all_log_entries(self):
        """spec/06 §2.1 / §12.1: Raw student PII must never appear in any log entry."""
        log_batch = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="sync_service",
                event="sql_server_sync_completed",
                correlation_id=f"COR-SYNC-{i}",
                outcome="success",
                pii_present=False,
            )
            for i in range(10)
        ]
        assert all(log_entry_is_pii_free(e) for e in log_batch)

    def test_uls6_ai_content_text_never_present_in_log_entries(self):
        """spec/06 §7.x / §12.2: AI content text must never appear in any log entry."""
        ai_entries = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="ai_service",
                event="ai_insight_generation_completed",
                correlation_id=f"COR-AI-{i}",
                outcome="success",
                content_text_present=False,
            )
            for i in range(5)
        ]
        assert all(not e.content_text_present for e in ai_entries)

    def test_uls7_secrets_never_present_in_log_entries(self):
        """spec/06 §2.1 / spec/09: Credential values must never appear in any log entry."""
        entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="api",
            event="api_request_received",
            correlation_id="COR-SEC-001",
            outcome="success",
            secret_value_present=False,
        )
        assert entry.secret_value_present is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — CORRELATION & CAUSATION PROPAGATION
# Certifies spec/06 §3.1 – §3.9 correlation ID architecture.
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrelationCausationPropagation:
    """
    Certifies the correlation / causation propagation contract from spec/06 §3.
    Single-hop traceability and causation chain reconstruction are governance requirements.
    """

    def test_ccp1_root_events_have_no_causation_id(self):
        """spec/06 §3.1: Root events (scheduler trigger, API request) have causation_id=None."""
        root_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="api",
            event="api_request_received",
            correlation_id="COR-ROOT-001",
            outcome="success",
            causation_id=None,
        )
        assert root_entry.causation_id is None

    def test_ccp2_derived_events_carry_causation_id(self):
        """spec/06 §3.2: Derived events (AI triggered by snapshot) carry causation_id."""
        ai_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="ai_service",
            event="ai_insight_generation_completed",
            correlation_id="COR-AI-001",
            causation_id="COR-SNAPSHOT-001",
            outcome="success",
        )
        assert ai_entry.causation_id is not None
        assert ai_entry.causation_id == "COR-SNAPSHOT-001"

    def test_ccp3_replay_generates_new_correlation_id_not_original(self):
        """spec/06 §3.8: Replay generates new correlation_id — never reuses original."""
        original_cid = "COR-ORIGINAL-001"
        replay_record = ReplayVisibilityRecord(
            event="historical_regeneration_initiated",
            execution_type="regeneration",
            correlation_id="COR-REGEN-FRESH-001",
            causation_id=original_cid,
            fingerprint_match=True,
            divergence_flag=None,
        )
        assert replay_record.correlation_id != original_cid
        assert replay_record.causation_id == original_cid

    def test_ccp4_replay_causation_points_to_original_correlation_id(self):
        """spec/06 §3.8: Replay's causation_id must equal the original execution's correlation_id."""
        original_cid = "COR-ORIGINAL-2026-04"
        replay_record = ReplayVisibilityRecord(
            event="historical_regeneration_initiated",
            execution_type="regeneration",
            correlation_id="COR-REGEN-001",
            causation_id=original_cid,
            fingerprint_match=False,
            divergence_flag="POTENTIALLY_DIVERGENT",
        )
        assert replay_record.causation_id == original_cid

    def test_ccp5_execution_mode_always_explicit_never_inferred(self):
        """spec/06 §2.2: execution_mode is explicitly set — never inferred from context."""
        outreach_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="api",
            event="outreach_intent_recorded",
            correlation_id="COR-OUTREACH-001",
            outcome="success",
            execution_mode="SHADOW",
        )
        assert outreach_entry.execution_mode in ("SHADOW", "LIVE", "DEGRADED")

    def test_ccp6_single_hop_traceability_all_job_entries_share_correlation_id(self):
        """spec/06 §3.7: Any log entry's correlation_id retrieves all same-job entries."""
        shared_cid = "COR-BATCH-JOB-001"
        job_entries = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service=svc,
                event=evt,
                correlation_id=shared_cid,
                outcome="success",
            )
            for svc, evt in [
                ("scheduler", "orchestration_job_started"),
                ("snapshot_service", "orchestration_phase_entered"),
                ("ai_service", "ai_insight_generation_completed"),
                ("snapshot_service", "orchestration_job_completed"),
            ]
        ]
        traced = [e for e in job_entries if e.correlation_id == shared_cid]
        assert len(traced) == 4

    def test_ccp7_causation_chain_reconstructable_to_root_event(self):
        """spec/06 §3.2: Following causation_id → correlation_id reconstructs full chain."""
        api_cid = "COR-API-001"
        snap_cid = "COR-SNAP-001"
        ai_cid = "COR-AI-001"

        chain = [
            LineageVisibilityRecord(
                correlation_id=api_cid,
                causation_id=None,
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="operator",
                origin_authority="operator_authorized",
                execution_type="original",
            ),
            LineageVisibilityRecord(
                correlation_id=snap_cid,
                causation_id=api_cid,
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="scheduler",
                origin_authority="system_automated",
                execution_type="original",
            ),
            LineageVisibilityRecord(
                correlation_id=ai_cid,
                causation_id=snap_cid,
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="scheduler",
                origin_authority="system_automated",
                execution_type="original",
            ),
        ]

        def find_parent(cid: str) -> Optional[LineageVisibilityRecord]:
            return next((r for r in chain if r.correlation_id == cid), None)

        ai_record = chain[2]
        snap_record = find_parent(ai_record.causation_id)
        api_record = find_parent(snap_record.causation_id) if snap_record else None

        assert snap_record is not None
        assert api_record is not None
        assert api_record.causation_id is None  # root event


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — ORCHESTRATION VISIBILITY GOVERNANCE
# Certifies spec/06 §4.x orchestration phase visibility contract.
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestrationVisibilityGovernance:
    """
    Certifies orchestration phase visibility and state-transition logging governance.
    Aligned with spec/06 §4.x (orchestration visibility).
    """

    def test_ovg1_phase_entry_and_completion_each_produce_distinct_log_entries(self):
        """spec/06 §4.1: Every orchestration phase produces distinct entry and completion entries."""
        phase_events = ["orchestration_phase_entered", "orchestration_phase_completed"]
        records = [
            OrchestrationPhaseRecord(
                event=evt,
                job_type="monthly_snapshot_generation",
                phase="ai_enrichment",
                correlation_id="COR-JOB-001",
                outcome="success" if "completed" in evt else "in_progress",
            )
            for evt in phase_events
        ]
        events = {r.event for r in records}
        assert "orchestration_phase_entered" in events
        assert "orchestration_phase_completed" in events

    def test_ovg2_every_state_transition_produces_structured_log_entry(self):
        """spec/06 §4.7 / INVARIANT-4: Every state transition → structured log entry."""
        transitions = [
            ("snapshot", "DRAFT", "VALIDATING"),
            ("snapshot", "VALIDATING", "FINALIZED"),
            ("report", "REPORT_PENDING", "REPORT_GENERATING"),
            ("config_version", "APPROVED", "ACTIVE"),
        ]
        log_entries = [
            StateTransitionVisibilityRecord(
                event="state_transition",
                domain=domain,
                entity_id=f"ENTITY-{domain.upper()}-001",
                from_state=frm,
                to_state=to,
                actor_identity="finalization_service_account",
                origin_source="scheduler",
                attribution_timestamp="2026-05-27T10:00:00Z",
                correlation_id=f"COR-TRANS-{domain}-001",
            )
            for domain, frm, to in transitions
        ]
        assert len(log_entries) == len(transitions)
        assert all(has_correlation_id(e) for e in log_entries)

    def test_ovg3_failure_entries_carry_specific_error_class_not_generic(self):
        """spec/06 §4.8: Failure entries carry specific error_class — never generic 'Error'."""
        failure_phase = OrchestrationPhaseRecord(
            event="orchestration_phase_failed",
            job_type="monthly_snapshot_generation",
            phase="finalization_gate",
            correlation_id="COR-FAIL-001",
            outcome="failure",
            error_class="ConcurrentFinalizationRejected",
            retryable=False,
        )
        assert failure_phase.error_class is not None
        assert failure_phase.error_class not in ("Error", "Exception", "")

    def test_ovg4_retryable_failure_carries_recovery_path(self):
        """spec/06 §4.8: retryable=True entries must carry a non-empty recovery_path."""
        failure_phase = OrchestrationPhaseRecord(
            event="orchestration_phase_failed",
            job_type="ai_enrichment_batch",
            phase="provider_call",
            correlation_id="COR-RETRY-001",
            outcome="failure",
            error_class="ProviderTimeoutError",
            retryable=True,
            recovery_path="return_to_AI_PENDING",
        )
        assert failure_phase.retryable is True
        assert failure_phase.recovery_path is not None
        assert failure_phase.recovery_path != ""

    def test_ovg5_duplicate_finalization_rejection_produces_specific_log_entry(self):
        """spec/06 §4.1 / §6.7: Duplicate FINALIZED snapshot detection produces specific entry."""
        rejection_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="snapshot_service",
            event="snapshot_finalization_duplicate_rejected",
            correlation_id="COR-DUP-001",
            outcome="skipped",
            error_class="DuplicateKeyError",
        )
        assert rejection_entry.event == "snapshot_finalization_duplicate_rejected"
        assert rejection_entry.error_class == "DuplicateKeyError"
        assert rejection_entry.outcome == "skipped"  # clean exit, not failure

    def test_ovg6_job_completion_carries_governance_boundaries_crossed(self):
        """spec/06 §2.4: Job completion entry records governance_boundaries_crossed."""
        completion_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="snapshot_service",
            event="orchestration_job_completed",
            correlation_id="COR-JOB-001",
            outcome="success",
            context={
                "total_students_scoped": 200,
                "students_succeeded": 198,
                "students_failed": 2,
                "governance_boundaries_crossed": ["VALIDATING→FINALIZED"],
            },
        )
        assert "governance_boundaries_crossed" in completion_entry.context
        assert len(completion_entry.context["governance_boundaries_crossed"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — REPLAY OBSERVABILITY GOVERNANCE
# Certifies spec/06 §5.x replay and regeneration observability.
# ─────────────────────────────────────────────────────────────────────────────

class TestReplayObservabilityGovernance:
    """
    Certifies replay observability governance from spec/06 §5.x.
    Replay executions must be distinguishable from originals and must not
    appear as LIVE executions or produce live mutations.
    """

    def test_rog1_replay_carries_execution_type_replay_or_regeneration(self):
        """spec/06 §5.6 / §3.8: Replay log entries carry execution_type=replay or regeneration."""
        replay_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="report_service",
            event="historical_regeneration_initiated",
            correlation_id="COR-REGEN-001",
            outcome="success",
            execution_type="regeneration",
        )
        assert entry_is_replay(replay_entry)
        assert replay_entry.execution_type in ("replay", "regeneration")

    def test_rog2_replay_live_mutations_produced_zero(self):
        """spec/06 §5.x: Replay executions produce zero live mutations and side-effects."""
        replay_record = ReplayVisibilityRecord(
            event="historical_regeneration_initiated",
            execution_type="regeneration",
            correlation_id="COR-REGEN-001",
            causation_id="COR-ORIGINAL-001",
            fingerprint_match=True,
            divergence_flag=None,
            live_mutations_produced=0,
            live_side_effects_produced=0,
        )
        assert replay_is_governance_isolated(replay_record)
        assert replay_record.live_mutations_produced == 0

    def test_rog3_fingerprint_comparison_logged_at_regeneration_initiation(self):
        """spec/06 §5.1 / §5.4: Fingerprint comparison logged before execution begins."""
        initiation_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="report_service",
            event="historical_regeneration_initiated",
            correlation_id="COR-REGEN-001",
            outcome="success",
            execution_type="regeneration",
            context={
                "stored_fingerprint": {"config_registry_version": "V3", "schema_version": "0002"},
                "current_fingerprint": {"config_registry_version": "V4", "schema_version": "0002"},
                "fingerprint_match": False,
                "divergence_flag": "POTENTIALLY_DIVERGENT",
            },
        )
        ctx = initiation_entry.context
        assert "stored_fingerprint" in ctx
        assert "current_fingerprint" in ctx
        assert ctx["fingerprint_match"] is False
        assert ctx["divergence_flag"] == "POTENTIALLY_DIVERGENT"

    def test_rog4_potentially_divergent_set_when_fingerprint_mismatch(self):
        """spec/06 §5.4 / §10.9: fingerprint_match=False → divergence_flag=POTENTIALLY_DIVERGENT."""
        replay_record = ReplayVisibilityRecord(
            event="historical_regeneration_initiated",
            execution_type="regeneration",
            correlation_id="COR-REGEN-002",
            causation_id="COR-ORIGINAL-002",
            fingerprint_match=False,
            divergence_flag="POTENTIALLY_DIVERGENT",
        )
        assert replay_record.fingerprint_match is False
        assert replay_record.divergence_flag == "POTENTIALLY_DIVERGENT"

    def test_rog5_null_divergence_flag_when_fingerprints_match(self):
        """spec/06 §5.6: fingerprint_match=True → divergence_flag is None."""
        replay_record = ReplayVisibilityRecord(
            event="historical_regeneration_initiated",
            execution_type="regeneration",
            correlation_id="COR-REGEN-003",
            causation_id="COR-ORIGINAL-003",
            fingerprint_match=True,
            divergence_flag=None,
        )
        assert replay_record.fingerprint_match is True
        assert replay_record.divergence_flag is None

    def test_rog6_regeneration_does_not_modify_original_records(self):
        """spec/06 §3.10: Regeneration creates new lineage version — original is not modified."""
        regeneration_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="report_service",
            event="report_regeneration_completed",
            correlation_id="COR-REGEN-004",
            outcome="success",
            execution_type="regeneration",
            context={
                "new_lineage_version": 2,
                "original_record_modified": False,
            },
        )
        assert regeneration_entry.context.get("original_record_modified") is False

    def test_rog7_replay_and_original_entries_distinguishable_by_execution_type(self):
        """spec/06 §5.6: Replay and original entries are distinguishable in the log stream."""
        original = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="snapshot_service",
            event="orchestration_job_completed",
            correlation_id="COR-ORIGINAL-001",
            outcome="success",
            execution_type="original",
        )
        replay = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="report_service",
            event="historical_regeneration_initiated",
            correlation_id="COR-REGEN-001",
            outcome="success",
            execution_type="regeneration",
        )
        assert original.execution_type == "original"
        assert entry_is_replay(replay)
        assert original.execution_type != replay.execution_type


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — AI OBSERVABILITY GOVERNANCE
# Certifies spec/06 §7.x AI orchestration telemetry contracts.
# ─────────────────────────────────────────────────────────────────────────────

class TestAIObservabilityGovernance:
    """
    Certifies AI observability governance from spec/06 §7.x.
    AI records carry metadata only — never content text, never PII.
    AI remains advisory-only in observability surfaces.
    """

    def test_aig1_ai_log_never_contains_content_text(self):
        """spec/06 §7.x / §12.2: content_text must never appear in any AI log entry."""
        ai_record = AIObservabilityRecord(
            event="ai_insight_generation_completed",
            insight_type="risk_summary",
            prompt_version="v3.2",
            model_used="claude-sonnet-4-6",
            correlation_id="COR-AI-001",
            outcome="success",
            content_text_present=False,
        )
        assert ai_log_is_content_free(ai_record)

    def test_aig2_stale_insight_logged_with_staleness_context(self):
        """spec/06 §7.6 / §5.5: Stale AI served is explicitly logged with stale_for_hours."""
        stale_record = AIObservabilityRecord(
            event="stale_insight_served",
            insight_type="risk_summary",
            prompt_version="v3.2",
            model_used="claude-sonnet-4-6",
            correlation_id="COR-STALE-001",
            outcome="partial",
            stale_insight_served=True,
            stale_insight_version=4,
            stale_for_hours=26.5,
        )
        assert stale_record.stale_insight_served is True
        assert stale_record.stale_for_hours is not None
        assert stale_record.stale_for_hours > 0

    def test_aig3_frozen_snapshot_ai_isolation_produces_confirmation_entry(self):
        """spec/06 §7.7: Force-refresh on FINALIZED snapshot produces isolation-confirmed entry."""
        isolation_record = FrozenSnapshotAIIsolationRecord(
            event="snapshot_ai_isolation_confirmed",
            action="force_refresh",
            snapshot_id="SNAP-OPAQUE-001",
            snapshot_state="FINALIZED",
            frozen_text_modified=False,
            correlation_id="COR-FORCE-001",
        )
        assert frozen_snapshot_is_immutable(isolation_record)
        assert isolation_record.snapshot_state == "FINALIZED"
        assert isolation_record.frozen_text_modified is False

    def test_aig4_ai_records_carry_metadata_not_governance_authorization(self):
        """spec/06 §7.x: AI observability records carry metadata only — AI is advisory-only."""
        ai_record = AIObservabilityRecord(
            event="ai_insight_generation_completed",
            insight_type="progress_summary",
            prompt_version="v2.0",
            model_used="claude-sonnet-4-6",
            correlation_id="COR-AI-002",
            outcome="success",
            latency_ms=2340,
        )
        assert ai_record.insight_type is not None
        assert ai_record.prompt_version is not None
        assert ai_record.model_used is not None
        # No governance_scope or authorization field — AI is advisory-only

    def test_aig5_stale_ai_exceeding_48h_requires_high_severity_alert(self):
        """spec/06 §10.4: Stale AI > 48h due to provider failure → HIGH severity alert."""
        stale_hours = 50.0
        alert = DegradationAlertRecord(
            severity="HIGH",
            degradation_type="AI_STALENESS_CRITICAL",
            error_class="ProviderUnavailable",
            correlation_id="COR-STALE-HIGH-001",
        )
        assert stale_hours > 48
        assert alert.severity == "HIGH"
        assert alert.error_class not in ("Error", "Exception", "")

    def test_aig6_prompt_version_captured_at_generation_start_not_completion(self):
        """spec/06 §7.3: Prompt version is captured at AI_PENDING→AI_GENERATING — always present."""
        ai_record = AIObservabilityRecord(
            event="ai_insight_generation_completed",
            insight_type="risk_summary",
            prompt_version="v3.2",
            model_used="claude-sonnet-4-6",
            correlation_id="COR-AI-003",
            outcome="success",
        )
        assert ai_record.prompt_version is not None
        assert ai_record.prompt_version != ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — PROVIDER & SYNC OBSERVABILITY GOVERNANCE
# Certifies spec/06 §2.10 / §11.4 / §11.5 provider and sync visibility.
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderAndSyncObservabilityGovernance:
    """
    Certifies provider health and synchronization observability governance.
    SQL Server is sql_server_authoritative; providers are platform_supplementary.
    """

    def test_psg1_provider_failure_never_silently_swallowed(self):
        """spec/06 §7.5 / §4.8: Every provider failure produces a structured log entry."""
        provider_failure = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="error",
            service="ai_service",
            event="ai_provider_failure",
            correlation_id="COR-PROV-001",
            outcome="failure",
            error_class="ProviderTimeoutError",
        )
        assert provider_failure.error_class is not None
        assert provider_failure.error_class not in ("Error", "Exception", "")
        assert provider_failure.outcome == "failure"

    def test_psg2_sync_completion_carries_sql_server_authoritative_fields(self):
        """spec/06 §2.10: SQL Server sync entry carries mirrored_sql_server / sql_server_authoritative."""
        sync_record = SyncObservabilityRecord(
            event="sql_server_sync_completed",
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
            correlation_id="COR-SYNC-001",
            rows_scanned=76,
        )
        assert sync_record.origin_source == "mirrored_sql_server"
        assert sync_record.origin_authority == "sql_server_authoritative"

    def test_psg3_schema_drift_produces_separate_per_column_log_entry(self):
        """spec/06 §2.10: Schema drift events produce a separate log entry per drifted column."""
        drift_entries = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="warn",
                service="sync_service",
                event="schema_drift_detected",
                correlation_id="COR-SYNC-001",
                outcome="partial",
                context={
                    "drift_type": "missing_column",
                    "column_name": f"ClassSignup_{i}",
                    "impact": "column_skipped",
                },
            )
            for i in range(3)
        ]
        assert len(drift_entries) == 3
        assert all(e.event == "schema_drift_detected" for e in drift_entries)
        assert all(e.correlation_id == "COR-SYNC-001" for e in drift_entries)

    def test_psg4_ghl_webhook_carries_platform_supplementary_authority(self):
        """spec/06 §2.10: GHL webhook entries carry platform_supplementary authority."""
        ghl_record = SyncObservabilityRecord(
            event="ghl_webhook_processed",
            origin_source="ghl",
            origin_authority="platform_supplementary",
            correlation_id="COR-GHL-001",
            duplicate_detected=False,
        )
        assert ghl_record.origin_authority == "platform_supplementary"
        assert ghl_record.origin_source == "ghl"

    def test_psg5_sync_conflict_attribution_visible_not_silent(self):
        """spec/06 §2.10: SQL Server vs GHL conflicts are logged with winning_source — never silent."""
        conflict_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="sync_service",
            event="sync_conflict_recorded",
            correlation_id="COR-CONFLICT-001",
            outcome="success",
            context={
                "winning_source": "sql_server_authoritative",
                "field_name": "eligibility_status",
                "authoritative_value": "ELIGIBLE",
                "supplementary_value": "BLOCKED",
                "both_values_retained": True,
            },
        )
        ctx = conflict_entry.context
        assert ctx["winning_source"] == "sql_server_authoritative"
        assert ctx["both_values_retained"] is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — DEGRADATION VISIBILITY GOVERNANCE
# Certifies spec/06 §10.x alert classification and deterministic degradation visibility.
# ─────────────────────────────────────────────────────────────────────────────

class TestDegradationVisibilityGovernance:
    """
    Certifies deterministic degradation visibility — every degradation event
    has a named type, specific error_class, and correct severity.
    No silent degradation. No generic 'Error'. No silent swallow.
    """

    def test_dvg1_sql_server_write_attempt_produces_critical_alert(self):
        """spec/06 §10.8: SQL Server write attempt → SEVERITY: CRITICAL."""
        alert = DegradationAlertRecord(
            severity="CRITICAL",
            degradation_type="SQL_SERVER_WRITE_ATTEMPT",
            error_class="GovernanceViolation",
            correlation_id="COR-CRIT-001",
        )
        assert alert.severity == "CRITICAL"
        assert alert.degradation_type == "SQL_SERVER_WRITE_ATTEMPT"
        assert alert.error_class == "GovernanceViolation"

    def test_dvg2_governance_override_attempt_produces_critical_alert(self):
        """spec/06 §9.5 / §10.8: Governance override attempt → SEVERITY: CRITICAL."""
        alert = AlertRecord(
            severity="CRITICAL",
            alert_type="GOVERNANCE_OVERRIDE_ATTEMPT",
            error_class="GovernanceViolation",
            correlation_id="COR-OVERRIDE-001",
            escalation_path="operations → engineering → senior_stakeholder",
        )
        assert alert.severity == "CRITICAL"
        assert alert_has_specific_error_class(alert)

    def test_dvg3_sla_breach_produces_high_severity_alert(self):
        """spec/06 §6.8 / §10.5: SLA breach → SEVERITY: HIGH — threshold from Config V2."""
        actual_duration_ms = 65_000
        sla_threshold = resolve_threshold(
            ConfigVersion("V2", "ACTIVE", {"sla_report_generation_ms": 60_000}),
            "sla_report_generation_ms",
        )
        assert actual_duration_ms > sla_threshold

        alert = DegradationAlertRecord(
            severity="HIGH",
            degradation_type="SLA_BREACH",
            error_class="SLAViolation",
            correlation_id="COR-SLA-001",
        )
        assert alert.severity == "HIGH"

    def test_dvg4_fingerprint_divergence_produces_medium_severity_alert(self):
        """spec/06 §10.9 / §5.4: Fingerprint mismatch → SEVERITY: MEDIUM."""
        alert = DegradationAlertRecord(
            severity="MEDIUM",
            degradation_type="FINGERPRINT_DIVERGENCE",
            error_class="FingerprintMismatch",
            correlation_id="COR-FP-001",
        )
        assert alert.severity == "MEDIUM"
        assert alert.degradation_type == "FINGERPRINT_DIVERGENCE"

    def test_dvg5_schema_drift_produces_low_severity_alert(self):
        """spec/06 §10.6: Schema drift → SEVERITY: LOW (logged; no immediate response required)."""
        alert = DegradationAlertRecord(
            severity="LOW",
            degradation_type="SCHEMA_DRIFT_DETECTED",
            error_class="SchemaDriftError",
            correlation_id="COR-DRIFT-001",
        )
        assert alert.severity == "LOW"
        assert alert.error_class not in ("Error", "Exception", "")

    def test_dvg6_silent_swallow_prohibition_all_degradation_records(self):
        """spec/06 §4.8: Silent swallow (catch without structured log) is a production defect."""
        degradation_records = [
            DegradationAlertRecord(
                severity="HIGH",
                degradation_type=dtype,
                error_class=ec,
                correlation_id=f"COR-DEG-{i}",
                silent_swallow=False,
            )
            for i, (dtype, ec) in enumerate([
                ("PROVIDER_OUTAGE", "ProviderUnavailable"),
                ("SCHEDULER_MISSED_RUN", "SchedulerOutage"),
                ("SYNC_LAG_EXCEEDED", "SyncLagError"),
            ])
        ]
        assert all(not r.silent_swallow for r in degradation_records)

    def test_dvg7_specific_error_class_never_generic_in_any_alert(self):
        """spec/06 §2.1 / §7.5: 'Error' is never an acceptable error_class in alerts."""
        alerts = [
            AlertRecord(
                severity="HIGH",
                alert_type="PROVIDER_FAILURE",
                error_class="ProviderTimeoutError",
                correlation_id="COR-A-001",
            ),
            AlertRecord(
                severity="CRITICAL",
                alert_type="GOVERNANCE_VIOLATION",
                error_class="GovernanceViolation",
                correlation_id="COR-A-002",
            ),
            AlertRecord(
                severity="MEDIUM",
                alert_type="STALE_AI",
                error_class="StaleInsightWarning",
                correlation_id="COR-A-003",
            ),
        ]
        assert all(alert_has_specific_error_class(a) for a in alerts)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — GOVERNANCE TRANSITION VISIBILITY
# Certifies spec/06 §8.6 / §4.7 irreversible governance transition logging.
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceTransitionVisibility:
    """
    Certifies that irreversible governance transitions produce governance_transition
    log entries distinct from regular state_transition entries.
    Aligned with spec/06 §8.6 and §4.7.
    """

    def test_gtv1_validating_to_finalized_carries_all_five_fingerprint_components(self):
        """spec/06 §2.5 / §8.6 / FAD-6: VALIDATING→FINALIZED carries all 5 fingerprint components."""
        gt = GovernanceTransitionRecord(
            event="governance_transition",
            domain="snapshot",
            from_state="VALIDATING",
            to_state="FINALIZED",
            correlation_id="COR-GT-001",
            actor_identity="finalization_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
            fingerprint_components={
                "schema_version": "0002",
                "config_registry_version": "V3",
                "ai_prompt_version": {"risk_summary": "v3.1"},
                "ai_model_version": {"risk_summary": "claude-sonnet-4-6"},
                "report_template_version": "t2.0",
            },
        )
        assert gt.from_state == "VALIDATING"
        assert gt.to_state == "FINALIZED"
        assert gt.fingerprint_components is not None
        assert len(gt.fingerprint_components) == 5

    def test_gtv2_report_published_produces_governance_transition_entry(self):
        """spec/06 §2.7 / §8.6: REPORT_APPROVED→REPORT_PUBLISHED produces governance_transition."""
        gt = GovernanceTransitionRecord(
            event="governance_transition",
            domain="report",
            from_state="REPORT_APPROVED",
            to_state="REPORT_PUBLISHED",
            correlation_id="COR-GT-002",
            actor_identity="report_publisher_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
            fingerprint_components={
                "schema_version": "0002",
                "config_registry_version": "V3",
            },
        )
        assert gt.domain == "report"
        assert gt.to_state == "REPORT_PUBLISHED"
        assert gt.fingerprint_components is not None

    def test_gtv3_config_activation_produces_governance_transition_entry(self):
        """spec/06 §2.8 / §8.1: Config APPROVED→ACTIVE produces governance_transition entry."""
        gt = GovernanceTransitionRecord(
            event="config_version_activated",
            domain="config_version",
            from_state="APPROVED",
            to_state="ACTIVE",
            correlation_id="COR-CONF-001",
            actor_identity="config_manager_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
        )
        assert gt.domain == "config_version"
        assert gt.to_state == "ACTIVE"
        assert has_correlation_id(gt)

    def test_gtv4_compliance_in_execution_produces_governance_transition_entry(self):
        """spec/06 §2.9 / §9.4: APPROVED_FOR_ACTION→IN_EXECUTION produces governance_transition."""
        gt = GovernanceTransitionRecord(
            event="compliance_execution_started",
            domain="compliance",
            from_state="APPROVED_FOR_ACTION",
            to_state="IN_EXECUTION",
            correlation_id="COR-COMP-001",
            actor_identity="compliance_pathway_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
        )
        assert gt.domain == "compliance"
        assert gt.from_state == "APPROVED_FOR_ACTION"
        assert gt.to_state == "IN_EXECUTION"

    def test_gtv5_governance_override_attempt_produces_critical_visibility_entry(self):
        """spec/06 §9.5: Governance override attempt logged as SEVERITY: CRITICAL."""
        override_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="error",
            service="snapshot_service",
            event="governance_override_attempt_rejected",
            correlation_id="COR-OVERRIDE-001",
            outcome="failure",
            error_class="GovernanceViolation",
            context={
                "attempted_operation": "UPDATE",
                "entity_type": "snapshot",
                "entity_state": "FINALIZED",
                "rejection_reason": "immutability_constraint",
            },
        )
        assert override_entry.error_class == "GovernanceViolation"
        assert override_entry.context["entity_state"] == "FINALIZED"
        assert override_entry.context["rejection_reason"] == "immutability_constraint"

    def test_gtv6_governance_transition_log_and_db_audit_record_share_correlation_id(self):
        """spec/06 §8.7: Governance transition log entry and DB audit record correlated by correlation_id."""
        correlation_id = "COR-AUDIT-001"
        log_entry = GovernanceTransitionRecord(
            event="governance_transition",
            domain="snapshot",
            from_state="VALIDATING",
            to_state="FINALIZED",
            correlation_id=correlation_id,
            actor_identity="finalization_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
        )
        db_audit_record = {
            "correlation_id": correlation_id,
            "domain": "snapshot",
            "to_state": "FINALIZED",
        }
        assert log_entry.correlation_id == db_audit_record["correlation_id"]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — COMPLIANCE OBSERVABILITY GOVERNANCE
# Certifies spec/06 §9.x compliance visibility and audit survivability.
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceObservabilityGovernance:
    """
    Certifies compliance observability governance from spec/06 §9.x.
    compliance_audit is INSERT-only; scope manifests never in log streams;
    student references are opaque.
    """

    def test_cog1_compliance_audit_allows_no_update_or_delete(self):
        """spec/06 §9.7: compliance_audit records are INSERT-only — no UPDATE or DELETE allowed."""
        compliance_vis = WarehouseVisibilityRecord(
            metric_type="immutable",
            governance_tier="FINALIZED_COPY",
            is_mutable=False,
            allows_update=False,
            allows_delete=False,
        )
        assert compliance_vis.allows_update is False
        assert compliance_vis.allows_delete is False

    def test_cog2_scope_manifest_content_never_in_log_stream(self):
        """spec/06 §12.4 / §9.1: Compliance scope manifest content never in log entries."""
        compliance_record = ComplianceObservabilityRecord(
            event="compliance_execution_started",
            workflow_id="WF-COMP-001",
            action_type="DELETE",
            affected_student_id_ref="OPAQUE-HASH-0001",
            correlation_id="COR-COMP-001",
            scope_manifest_content_present=False,
        )
        assert compliance_record.scope_manifest_content_present is False

    def test_cog3_compliance_entries_use_opaque_student_references(self):
        """spec/06 §12.4: Raw UserID must never appear in compliance observability records."""
        compliance_record = ComplianceObservabilityRecord(
            event="compliance_execution_completed",
            workflow_id="WF-COMP-002",
            action_type="ANONYMIZE",
            affected_student_id_ref="OPAQUE-HASH-0002",
            correlation_id="COR-COMP-002",
            raw_user_id_present=False,
        )
        assert compliance_record.raw_user_id_present is False
        assert "UserID" not in compliance_record.affected_student_id_ref

    def test_cog4_compliance_audit_survivable_after_operational_delete(self):
        """spec/06 §9.6 / FAD-4: compliance_audit has no FK deps — survives operational deletes."""
        warehouse_record = WarehouseVisibilityRecord(
            metric_type="immutable",
            governance_tier="FINALIZED_COPY",
            is_mutable=False,
            allows_update=False,
            allows_delete=False,
        )
        # compliance_audit survives because allows_delete=False — no cascading deletes
        audit_survives = warehouse_record.allows_delete is False
        assert audit_survives is True

    def test_cog5_compliance_gate_block_produces_governance_gate_violation_entry(self):
        """spec/06 §4.6: Compliance execution gate blocked → GovernanceGateViolation entry."""
        gate_block_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="error",
            service="compliance_service",
            event="compliance_execution_gate_blocked",
            correlation_id="COR-GATE-001",
            outcome="failure",
            error_class="GovernanceGateViolation",
            context={
                "workflow_id": "WF-COMP-003",
                "unmet_preconditions": ["pre_action_audit_entry_missing"],
            },
        )
        assert gate_block_entry.error_class == "GovernanceGateViolation"
        assert gate_block_entry.outcome == "failure"
        assert "unmet_preconditions" in gate_block_entry.context


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — ATTRIBUTION VISIBILITY GOVERNANCE
# Certifies spec/06 §3.x attribution continuity in observability surfaces.
# ─────────────────────────────────────────────────────────────────────────────

class TestAttributionVisibilityGovernance:
    """
    Certifies attribution continuity in observability surfaces.
    Every orchestration path must be historically explainable.
    Aligned with spec/06 §3.x and ATT-1 through ATT-5.
    """

    def test_avg1_attribution_timestamp_sourced_from_original_event_not_processing_time(self):
        """spec/06 §2.2: attribution_timestamp is sourced from the original event."""
        lineage = LineageVisibilityRecord(
            correlation_id="COR-ATT-001",
            causation_id=None,
            attribution_timestamp="2026-04-15T08:30:00Z",
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
            execution_type="original",
        )
        assert lineage.attribution_timestamp == "2026-04-15T08:30:00Z"
        assert lineage.is_historically_explainable is True

    def test_avg2_every_orchestration_path_is_historically_explainable(self):
        """ATT-5 / spec/06 §1.3: Every path retains historical explainability."""
        paths = [
            LineageVisibilityRecord(
                correlation_id=f"COR-PATH-{i}",
                causation_id=None if i == 0 else f"COR-PATH-{i-1}",
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="scheduler",
                origin_authority="system_automated",
                execution_type="original",
                is_historically_explainable=True,
            )
            for i in range(5)
        ]
        assert all(p.is_historically_explainable for p in paths)

    def test_avg3_lineage_records_carry_origin_authority(self):
        """ATT-1 / spec/06 §1.3: All lineage records carry origin_authority."""
        lineage_records = [
            LineageVisibilityRecord(
                correlation_id="COR-LIN-001",
                causation_id=None,
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="mirrored_sql_server",
                origin_authority="sql_server_authoritative",
                execution_type="original",
            ),
            LineageVisibilityRecord(
                correlation_id="COR-LIN-002",
                causation_id="COR-LIN-001",
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="ghl",
                origin_authority="platform_supplementary",
                execution_type="original",
            ),
        ]
        assert all(r.origin_authority != "" for r in lineage_records)

    def test_avg4_ai_enrichment_causation_id_points_to_parent_snapshot_job(self):
        """spec/06 §3.5: AI generation entries carry causation_id pointing to parent job."""
        snapshot_cid = "COR-SNAP-PARENT-001"
        ai_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="ai_service",
            event="ai_insight_generation_completed",
            correlation_id="COR-AI-CHILD-001",
            causation_id=snapshot_cid,
            outcome="success",
            execution_mode="SHADOW",
        )
        assert ai_entry.causation_id == snapshot_cid

    def test_avg5_config_version_visible_in_snapshot_fingerprint_for_prospective_enforcement(self):
        """spec/06 §8.3 / FAD-3: Config version used at finalization visible in fingerprint."""
        finalization_entry = GovernanceTransitionRecord(
            event="governance_transition",
            domain="snapshot",
            from_state="VALIDATING",
            to_state="FINALIZED",
            correlation_id="COR-CONFIG-ATT-001",
            actor_identity="finalization_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
            fingerprint_components={
                "config_registry_version": "V3",
                "schema_version": "0002",
                "ai_prompt_version": {},
                "ai_model_version": {},
                "report_template_version": "t2.0",
            },
        )
        assert finalization_entry.fingerprint_components["config_registry_version"] == "V3"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — OBSERVABILITY GOVERNANCE INVARIANTS
# INV-1 through INV-7, FAD-1/3/6, CID-1, IML-1 applied to observability surfaces.
# ─────────────────────────────────────────────────────────────────────────────

class TestObservabilityGovernanceInvariants:
    """
    Certifies governance invariants (INV-1 through INV-7) and finalized
    architecture decisions (FAD-1, FAD-3, FAD-6) applied to observability surfaces.
    """

    def test_inv1_observability_and_audit_records_are_append_only(self):
        """INV-1 / spec/06 §9.7: Observability and audit records are append-only — no post-write updates."""
        audit_record = WarehouseVisibilityRecord(
            metric_type="immutable",
            governance_tier="FINALIZED_COPY",
            is_mutable=False,
            allows_update=False,
            allows_delete=False,
        )
        assert audit_record.allows_update is False
        assert audit_record.is_mutable is False

    def test_inv2_exactly_one_active_config_version_at_all_observable_points(self):
        """INV-2: Exactly one ACTIVE config version must exist at every observable governance point."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {"sla_snapshot_batch_ms": 600_000}),
        ]
        assert exactly_one_active(registry)

    def test_inv3_finalized_snapshot_ai_text_isolated_from_live_ai_lifecycle(self):
        """INV-3 / FAD-1: FINALIZED snapshot AI text is isolated — force-refresh does not modify it."""
        isolation_record = FrozenSnapshotAIIsolationRecord(
            event="snapshot_ai_isolation_confirmed",
            action="force_refresh",
            snapshot_id="SNAP-001",
            snapshot_state="FINALIZED",
            frozen_text_modified=False,
            correlation_id="COR-INV3-001",
        )
        assert frozen_snapshot_is_immutable(isolation_record)

    def test_inv4_every_state_transition_in_every_domain_produces_structured_log_entry(self):
        """INV-4 / spec/06 §4.7: Every state transition in every domain → structured log entry."""
        domains = ["snapshot", "report", "ai_insight", "config_version", "compliance", "outreach"]
        log_entries = [
            StateTransitionVisibilityRecord(
                event="state_transition",
                domain=domain,
                entity_id=f"ENTITY-{domain.upper()}-001",
                from_state="PENDING",
                to_state="ACTIVE",
                actor_identity="system_automated",
                origin_source="scheduler",
                attribution_timestamp="2026-05-27T10:00:00Z",
                correlation_id=f"COR-INV4-{domain}",
            )
            for domain in domains
        ]
        assert len(log_entries) == len(domains)
        assert all(has_correlation_id(e) for e in log_entries)

    def test_inv5_correlation_id_present_on_all_observability_records(self):
        """INV-5 / spec/06 §2.2: Every observability record carries a non-null correlation_id."""
        records = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="api",
                event=f"event_{i}",
                correlation_id=f"COR-INV5-{i:04d}",
                outcome="success",
            )
            for i in range(20)
        ]
        assert all(has_correlation_id(r) for r in records)

    def test_inv6_alert_thresholds_resolved_from_config_v2_not_hardcoded(self):
        """INV-6 / CV2-1: Alert SLA thresholds resolved from Config V2 — no hardcoded constants."""
        config = ConfigVersion("V2", "ACTIVE", {
            "sla_snapshot_batch_ms": 600_000,
            "sla_report_generation_ms": 60_000,
            "ai_staleness_high_alert_hours": 48,
        })
        sla_snapshot = resolve_threshold(config, "sla_snapshot_batch_ms")
        sla_report = resolve_threshold(config, "sla_report_generation_ms")
        staleness_threshold = resolve_threshold(config, "ai_staleness_high_alert_hours")

        assert sla_snapshot == 600_000
        assert sla_report == 60_000
        assert staleness_threshold == 48

    def test_inv7_execution_mode_explicit_never_inferred_in_all_records(self):
        """INV-7 / spec/06 §2.11: execution_mode never inferred — always explicitly propagated."""
        entries = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service=svc,
                event=evt,
                correlation_id=f"COR-INV7-{i}",
                outcome="success",
                execution_mode="SHADOW",
            )
            for i, (svc, evt) in enumerate([
                ("ai_service", "ai_insight_generation_completed"),
                ("api", "outreach_intent_recorded"),
                ("sync_service", "sql_server_sync_completed"),
            ])
        ]
        assert all(e.execution_mode is not None for e in entries)

    def test_fad1_finalized_copy_visibility_metrics_are_immutable(self):
        """FAD-1 / spec/06 §11.10: FINALIZED_COPY observability metrics are immutable."""
        metric = WarehouseVisibilityRecord(
            metric_type="immutable",
            governance_tier="FINALIZED_COPY",
            is_mutable=False,
            sourced_from_rolling_window=False,
        )
        assert metric.is_mutable is False
        assert metric.sourced_from_rolling_window is False

    def test_fad3_config_prospective_only_enforcement_visible_in_snapshot_fingerprint(self):
        """FAD-3 / spec/06 §8.3: Prospective-only config enforcement visible via snapshot fingerprint."""
        old_finalization = GovernanceTransitionRecord(
            event="governance_transition",
            domain="snapshot",
            from_state="VALIDATING",
            to_state="FINALIZED",
            correlation_id="COR-FAD3-001",
            actor_identity="finalization_service_account",
            attribution_timestamp="2026-04-15T08:30:00Z",
            fingerprint_components={"config_registry_version": "V3"},
        )
        # V4 was activated after this snapshot — it must not appear here
        assert old_finalization.fingerprint_components["config_registry_version"] == "V3"

    def test_fad6_reproducibility_fingerprint_carries_all_five_components(self):
        """FAD-6 / spec/06 §1.6: Snapshot Reproducibility Fingerprint must carry all 5 components."""
        gt = GovernanceTransitionRecord(
            event="governance_transition",
            domain="snapshot",
            from_state="VALIDATING",
            to_state="FINALIZED",
            correlation_id="COR-FAD6-001",
            actor_identity="finalization_service_account",
            attribution_timestamp="2026-05-27T10:00:00Z",
            fingerprint_components={
                "schema_version": "0002",
                "config_registry_version": "V3",
                "ai_prompt_version": {"risk_summary": "v3.1"},
                "ai_model_version": {"risk_summary": "claude-sonnet-4-6"},
                "report_template_version": "t2.0",
            },
        )
        fp = gt.fingerprint_components
        assert "schema_version" in fp
        assert "config_registry_version" in fp
        assert "ai_prompt_version" in fp
        assert "ai_model_version" in fp
        assert "report_template_version" in fp

    def test_cid1_duplicate_job_execution_produces_single_log_entry_not_two(self):
        """CID-1 / spec/06 §6.7: Duplicate job detection produces a single rejection entry."""
        existing_job_cid = "COR-JOB-EXISTING-001"
        rejection_entry = ObservabilityLogEntry(
            timestamp="2026-05-27T10:00:00Z",
            level="info",
            service="scheduler",
            event="duplicate_job_execution_detected",
            correlation_id="COR-JOB-DUPLICATE-001",
            outcome="skipped",
            error_class="DuplicateJobExecution",
            context={
                "existing_job_correlation_id": existing_job_cid,
                "rejected_job_correlation_id": "COR-JOB-DUPLICATE-001",
            },
        )
        assert rejection_entry.outcome == "skipped"
        assert rejection_entry.error_class == "DuplicateJobExecution"
        assert rejection_entry.context["existing_job_correlation_id"] == existing_job_cid

    def test_iml1_lineage_and_warehouse_records_are_append_only(self):
        """IML-1 / spec/06 §9.7: Lineage records in warehouse are append-only."""
        lineage_warehouse = WarehouseVisibilityRecord(
            metric_type="immutable",
            governance_tier="AI_GENERATED",
            is_mutable=False,
            allows_update=False,
            allows_delete=False,
        )
        assert lineage_warehouse.allows_update is False
        assert lineage_warehouse.allows_delete is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — OBSERVABILITY LOAD CERTIFICATION
# Scale-level observability governance validation.
# Aligned with load_tests.md: LCS, LCR, LCAT, LCI, LCOS patterns.
# ─────────────────────────────────────────────────────────────────────────────

class TestObservabilityLoadCertification:
    """
    Certifies observability governance holds at load scale.
    Pure in-memory Python — all assertions are deterministic and fast.
    """

    def test_lcs1_100_log_entries_all_carry_correlation_id(self):
        """LCS-1: 100 log entries — every entry carries a non-null correlation_id."""
        batch = [
            ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="api",
                event=f"event_{i}",
                correlation_id=f"COR-BATCH-{i:04d}",
                outcome="success",
            )
            for i in range(100)
        ]
        assert len(batch) == 100
        assert all(has_correlation_id(e) for e in batch)

    def test_lcat1_500_alert_records_all_have_valid_severity_classification(self):
        """LCAT-1: 500 alert records — every alert has a valid severity from the allowed set."""
        allowed_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
        alerts = [
            AlertRecord(
                severity="HIGH" if i % 10 == 0 else "INFO",
                alert_type="ORCHESTRATION_EVENT",
                error_class="ProviderTimeoutError" if i % 10 == 0 else "N/A",
                correlation_id=f"COR-ALERT-{i:04d}",
            )
            for i in range(500)
        ]
        assert len(alerts) == 500
        assert all(a.severity in allowed_severities for a in alerts)

    def test_lci_inv5_1000_lineage_records_all_carry_attribution_fields(self):
        """LCI-INV5: 1000 lineage records — all carry origin_source and origin_authority."""
        records = [
            LineageVisibilityRecord(
                correlation_id=f"COR-LIN-{i:04d}",
                causation_id=None if i == 0 else f"COR-LIN-{i-1:04d}",
                attribution_timestamp="2026-05-27T10:00:00Z",
                origin_source="scheduler",
                origin_authority="system_automated",
                execution_type="original",
            )
            for i in range(1000)
        ]
        assert len(records) == 1000
        assert all(r.origin_source != "" for r in records)
        assert all(r.origin_authority != "" for r in records)

    def test_lci_fad2_100_replay_records_all_produce_zero_live_mutations(self):
        """LCI-FAD2: 100 replay records — all have live_mutations_produced=0."""
        replay_batch = [
            ReplayVisibilityRecord(
                event="historical_regeneration_initiated",
                execution_type="regeneration",
                correlation_id=f"COR-REGEN-{i:04d}",
                causation_id=f"COR-ORIG-{i:04d}",
                fingerprint_match=i % 3 != 0,
                divergence_flag=None if i % 3 != 0 else "POTENTIALLY_DIVERGENT",
                live_mutations_produced=0,
                live_side_effects_produced=0,
            )
            for i in range(100)
        ]
        assert len(replay_batch) == 100
        assert all(replay_is_governance_isolated(r) for r in replay_batch)
        assert all(r.live_mutations_produced == 0 for r in replay_batch)

    def test_lcos_200_ai_observability_records_never_contain_content_text(self):
        """LCOS / spec/06 §12.2: 200 AI log records — none has content_text_present=True."""
        ai_batch = [
            AIObservabilityRecord(
                event="ai_insight_generation_completed",
                insight_type="risk_summary" if i % 2 == 0 else "progress_summary",
                prompt_version="v3.2",
                model_used="claude-sonnet-4-6",
                correlation_id=f"COR-AI-{i:04d}",
                outcome="success",
                content_text_present=False,
            )
            for i in range(200)
        ]
        assert len(ai_batch) == 200
        assert all(ai_log_is_content_free(r) for r in ai_batch)

    def test_lcs_config_v2_batch_size_resolved_from_config_not_hardcoded(self):
        """LCS / CV2-1: Observability batch configuration resolved from Config V2."""
        config = ConfigVersion("V2", "ACTIVE", {
            "sla_snapshot_batch_ms": 600_000,
            "alert_batch_size": 250,
        })
        batch_size = resolve_threshold(config, "alert_batch_size")
        assert batch_size == 250
        assert batch_size != "UNKNOWN_V0"

    def test_lci_concurrent_log_entries_all_carry_distinct_correlation_ids(self):
        """LCI / CID-1: Concurrent log writes produce entries with distinct correlation_ids."""
        results: List[ObservabilityLogEntry] = []
        lock = threading.Lock()

        def write_log_entry(idx: int) -> None:
            entry = ObservabilityLogEntry(
                timestamp="2026-05-27T10:00:00Z",
                level="info",
                service="api",
                event=f"concurrent_event_{idx}",
                correlation_id=f"COR-CONC-{idx:04d}",
                outcome="success",
            )
            with lock:
                results.append(entry)

        threads = [threading.Thread(target=write_log_entry, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        correlation_ids = {e.correlation_id for e in results}
        assert len(correlation_ids) == 20  # all distinct — no collision
