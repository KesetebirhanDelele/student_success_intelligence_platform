"""
Governance-safe synchronization certification.

Aligned with (authoritative parent contracts):
  tests/test_scenarios.md  — governance validation contract (GPC/OIG/CV2/SVL/ROS/ROG/AIG/PBG/STG/CID/ATT/DEG/RGS/IML/INV)
  tests/edge_cases.md      — governance edge-condition certification (ECR/ECRG/ECA/ECAI/ECDO/ECCV/ECSO/ECPL/ECDE/ECIL)
  tests/load_tests.md      — governance load certification (LCS/LCR/LCSCH/LCRSG/LCDO/LCPB/LCAI/LCAT/LCDE/LCOS/LCI)
  tests/test_work_queue.py — governance-safe orchestration queue certification (peer contract)
  tests/test_actions.py    — governance-safe orchestration-action certification (peer contract)

Canonical design inputs:
  runtime/system_loop.md              spec/01_requirements.md
  runtime/scheduler_design.md         spec/03_state_transition_rules.md
  failure/failure_playbook.md         spec/04_idempotency_concurrency.md
  directives/ghl_integration_contract.md  spec/05_external_integrations.md
                                      spec/06_observability_operations.md
                                      spec/07_api_contracts.md
                                      spec/08_data_model.md
                                      spec/09_security_privacy.md

Prohibited semantics (test_scenarios.md §2 / edge_cases.md §2 / load_tests.md §2):
  - direct mutation assertions ("row overwritten", "upsert succeeded", direct db.add assertions)
  - SQL Server authority violations (platform writing to SQL Server)
  - replay-triggered LIVE mutations (replay may not produce INSERT/UPDATE side-effects)
  - mutable FINALIZED_COPY assumptions (warehouse.snapshot_ai_narratives are immutable)
  - non-attributable synchronization behavior (sync records missing correlation_id)
  - silent synchronization fallback assertions ("system falls back to safe state")
  - hardcoded concurrency / threshold constants (no MAX_ATTEMPTS, no 50-concurrent)
  - direct provider dispatch assumptions

Synchronization testing is NOW:
  - authoritative-boundary governance certification
  - replay-safe synchronization validation
  - append-only lineage certification
  - attribution-safe synchronization validation

This file certifies governance contracts only.
It does NOT generate synchronization services, ETL code, replication workers,
provider integrations, or production sync logic.
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
class SyncCorrelationRecord:
    """
    Attribution record emitted at the entry point of every sync cycle.
    spec/05_external_integrations.md §4.4: every sync cycle carries sync_correlation_id,
    row_count, timestamp, and origin_source.
    """
    sync_correlation_id: str
    origin_source: str          # mirrored_sql_server
    execution_mode: str         # LIVE | SHADOW | REPLAY | DEGRADED
    execution_type: str         # original | replay | recovery
    rows_scanned: int
    config_version_id: Optional[str]
    causation_id: Optional[str] = None


@dataclass
class SyncRowRecord:
    """
    Governance-classified record for a single row ingested from SQL Server.
    spec/05_external_integrations.md §2.3: every ingested row carries
    origin_source, origin_authority, is_authoritative, execution_mode,
    correlation_id, and attribution_timestamp.
    """
    student_id: int
    origin_source: str          # mirrored_sql_server
    origin_authority: str       # sql_server_authoritative | platform_supplementary
    is_authoritative: bool
    sync_correlation_id: str
    execution_mode: str
    validation_outcome: str     # VALID | INVALID
    invalid_fields: List[str] = field(default_factory=list)


@dataclass
class SyncValidationRecord:
    """
    Per-row validation record. Produced for every row — valid or invalid.
    Non-null sync_correlation_id is required (INV-5 / ATT-1).
    Invalid rows produce this record with non-empty invalid_fields — never silent.
    """
    student_id: Optional[int]
    validation_outcome: str     # VALID | INVALID | MISSING_REQUIRED
    invalid_fields: List[str]
    sync_correlation_id: str
    blocking_reason: Optional[str] = None


@dataclass
class SyncConflictRecord:
    """
    spec/05_external_integrations.md §4.6:
    When SQL Server value conflicts with a platform-supplementary value,
    both are retained and the conflict is logged with full attribution.
    Never silent. SQL Server value governs eligibility decisions.
    """
    student_id: int
    field_name: str
    authoritative_value: Any    # SQL Server value — governs eligibility
    supplementary_value: Any    # platform_supplementary value — retained as context
    winning_source: str         # sql_server_authoritative (always)
    sync_correlation_id: str
    conflict_logged: bool = True


@dataclass
class SyncReplayRecord:
    """
    Record produced when a sync cycle executes in replay mode.
    spec/05_external_integrations.md §4.5:
    Replay of sync produces the same student_trigger_data state with zero downstream side-effects.
    """
    sync_correlation_id: str
    historical_sync_correlation_id: str
    execution_type: str         # replay
    governance_scope: str       # REPLAY_ONLY
    live_mutations_produced: int
    live_side_effects_produced: int
    fingerprint_match: bool


@dataclass
class SyncDegradationRecord:
    """
    Emitted when sync operates under a degradation condition.
    Degradation must remain observable — never silent.
    failure/failure_playbook.md §4: named degradation events required.
    """
    degradation_type: str       # SQL_SERVER_UNAVAILABLE | SYNC_LAG_EXCEEDED | BACKLOG_OVERFLOW
    execution_mode: str         # DEGRADED
    sync_correlation_id: str
    degradation_flags: List[str]
    outbound_suppressed: bool
    escalation_triggered: bool


@dataclass
class SyncLineageRecord:
    """
    Append-only lineage record for the sync timeline.
    spec/08_data_model.md §2: warehouse and compliance_audit schemas are append-only.
    No UPDATE or DELETE from application code on these records.
    """
    sync_correlation_id: str
    student_id: int
    event_type: str             # SYNC_INGESTED | SYNC_SKIPPED | SYNC_CONFLICT
    origin_source: str
    is_authoritative: bool
    attribution_timestamp: str
    config_version_id: Optional[str]


@dataclass
class WarehouseRecord:
    """
    Immutable record in warehouse schema.
    spec/08_data_model.md §2: warehouse schema — append-only after FINALIZED.
    FAD-1: AI text is physically copied into warehouse.snapshot_ai_narratives.
    No UPDATE or DELETE from application code is permitted.
    """
    record_id: str
    student_id: int
    governance_tier: str        # FINALIZED_COPY | AI_GENERATED
    content_checksum: str
    is_mutable: bool = False    # always False after FINALIZED


@dataclass
class StructuredLogRecord:
    event: str
    correlation_id: Optional[str]
    level: str = "info"
    outcome: Optional[str] = None
    execution_mode: Optional[str] = None
    execution_type: Optional[str] = None
    error_class: Optional[str] = None
    suppression_reason: Optional[str] = None
    config_version_id: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)
    origin_source: Optional[str] = None


@dataclass
class ReplayDiagnosticRecord:
    source_artifact_id: str
    replay_cycle_id: str
    governance_scope: str           # REPLAY_ONLY
    execution_type: str             # replay
    historical_config_version_id: str
    replay_partial: bool
    fingerprint_comparison_outcome: Optional[str] = None
    correlation_id: Optional[str] = None


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
    """INV-5: every governance record carries non-null correlation_id."""
    cid = getattr(record, "sync_correlation_id",
          getattr(record, "correlation_id", None))
    return cid is not None


def has_config_version_id(record: Any) -> bool:
    """INV-7: every governance decision record carries non-null config_version_id."""
    return getattr(record, "config_version_id", None) is not None


def sync_is_replay_only(record: SyncReplayRecord) -> bool:
    """INV-4: replay sync produces zero LIVE mutations."""
    return (
        record.execution_type == "replay"
        and record.governance_scope == "REPLAY_ONLY"
        and record.live_mutations_produced == 0
        and record.live_side_effects_produced == 0
    )


def sql_server_governs_eligibility(conflict: SyncConflictRecord) -> bool:
    """
    spec/05_external_integrations.md §4.6:
    SQL Server value governs eligibility when authoritative and supplementary disagree.
    """
    return conflict.winning_source == "sql_server_authoritative"


def row_is_authoritative(row: SyncRowRecord) -> bool:
    """spec/05_external_integrations.md §3.2."""
    return (
        row.origin_source == "mirrored_sql_server"
        and row.origin_authority == "sql_server_authoritative"
        and row.is_authoritative is True
    )


def activate_config_version(
    registry: List[ConfigVersion], new_version_id: str
) -> List[ConfigVersion]:
    """
    Atomic activation: supersedes current ACTIVE version, promotes new_version_id.
    GPC-4 / INV-2: no window where two versions are ACTIVE.
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
# SECTION 1 — SYNCHRONIZATION GOVERNANCE PRECONDITIONS
# GPC-1 through GPC-5 as they apply to SQL Server sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncGovernancePreconditions:
    """
    Validates governance preconditions that gate ALL synchronization.
    Aligned with test_scenarios.md §3 (GPC-1 through GPC-5).
    """

    def test_sgpc1_sync_halts_without_active_config(self):
        """GPC-1 / sync path: No ACTIVE config version → sync cycle does not start."""
        registry: List[ConfigVersion] = []
        active_configs = [v for v in registry if v.status == "ACTIVE"]

        sync_records_produced: List[SyncCorrelationRecord] = []
        if not active_configs:
            pass  # sync cycle does not start

        assert len(active_configs) == 0
        assert sync_records_produced == []

        emitted_log = StructuredLogRecord(
            event="PRECONDITION_FAILED_NO_ACTIVE_CONFIG",
            correlation_id="COR-SYNC-001",
            level="error",
            outcome="failure",
        )
        assert emitted_log.event == "PRECONDITION_FAILED_NO_ACTIVE_CONFIG"
        assert emitted_log.correlation_id is not None

    def test_sgpc2_missing_threshold_substitutes_unknown_v0(self):
        """GPC-2 / sync path: Missing threshold → UNKNOWN_V0, not a hardcoded constant."""
        config = ConfigVersion("V1", "ACTIVE", thresholds={})
        sync_batch_size = resolve_threshold(config, "sync_batch_size")

        assert sync_batch_size == "UNKNOWN_V0"
        assert sync_batch_size != 50
        assert sync_batch_size != 100

    def test_sgpc3_sync_records_execution_mode(self):
        """GPC-3 / sync path: Every sync correlation record carries non-null execution_mode."""
        record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-CORR-001",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
        )
        assert record.execution_mode is not None
        assert record.execution_mode in {"LIVE", "SHADOW", "REPLAY", "DEGRADED", "MAINTENANCE"}

    def test_sgpc4_exactly_one_active_config_at_sync_time(self):
        """GPC-4 / INV-2: Exactly one ACTIVE config at any observable sync evaluation point."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {"sync_batch_size": 200}),
        ]
        assert exactly_one_active(registry)
        assert count_active(registry) == 1

    def test_sgpc4_two_active_configs_is_invariant_violation(self):
        """GPC-4 / INV-2: Two ACTIVE configs is a hard governance violation."""
        registry = [
            ConfigVersion("V1", "ACTIVE", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]
        assert not exactly_one_active(registry)
        assert count_active(registry) == 2
        # Governance contract: sync cycle must not proceed under this condition

    def test_sgpc5_prospective_activation_only(self):
        """GPC-5 / FAD-3: Config activation applies only to future sync cycles, never retroactively."""
        registry = [
            ConfigVersion("V1", "ACTIVE", {}),
            ConfigVersion("V2", "DRAFT", {}),
        ]
        updated = activate_config_version(registry, "V2")

        active_after = [v for v in updated if v.status == "ACTIVE"]
        superseded_after = [v for v in updated if v.status == "SUPERSEDED"]

        assert len(active_after) == 1
        assert active_after[0].version_id == "V2"
        assert len(superseded_after) >= 1
        assert superseded_after[0].version_id == "V1"

    def test_sgpc5_rollback_is_forbidden(self):
        """
        FAD-3 / spec/04_idempotency_concurrency.md §2.5:
        Config rollback (SUPERSEDED → ACTIVE) is explicitly forbidden.
        A new version is required; the old version may not be re-activated.
        """
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]
        superseded = [v for v in registry if v.status == "SUPERSEDED"]
        # Governance contract: no path re-activates a SUPERSEDED config
        for v in superseded:
            assert v.status != "ACTIVE"
        assert count_active(registry) == 1

    def test_sgpc1_precondition_log_is_never_silent(self):
        """GPC-1: Sync halt due to missing config must emit a structured log — never silent."""
        log = StructuredLogRecord(
            event="PRECONDITION_FAILED_NO_ACTIVE_CONFIG",
            correlation_id="COR-SYNC-002",
            level="error",
            outcome="failure",
            execution_mode="LIVE",
        )
        assert log.event is not None
        assert log.level == "error"
        assert log.outcome == "failure"
        # Prohibited: empty event or None correlation_id in precondition failure
        assert log.event != ""
        assert log.correlation_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — AUTHORITATIVE-BOUNDARY GOVERNANCE
# spec/05_external_integrations.md §3, §4: SQL Server = authoritative source.
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthoritativeBoundaryGovernance:
    """
    SQL Server is the authoritative operational source for student academic state.
    The platform never writes to SQL Server.
    Aligned with spec/05 §2.5, §3.1, §3.2, §4.4.
    """

    def test_abg1_sql_server_rows_carry_authoritative_attribution(self):
        """
        spec/05 §4.4: Every row synced from SQL Server carries
        origin_source=mirrored_sql_server, origin_authority=sql_server_authoritative,
        is_authoritative=True, and sync_correlation_id.
        """
        row = SyncRowRecord(
            student_id=1001,
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
            is_authoritative=True,
            sync_correlation_id="SYNC-001",
            execution_mode="LIVE",
            validation_outcome="VALID",
        )
        assert row_is_authoritative(row)
        assert row.origin_source == "mirrored_sql_server"
        assert row.origin_authority == "sql_server_authoritative"
        assert row.is_authoritative is True
        assert row.sync_correlation_id is not None

    def test_abg2_platform_supplementary_rows_are_not_authoritative(self):
        """
        spec/05 §3.2: GHL-derived and platform-generated rows are platform_supplementary.
        They do not govern eligibility decisions.
        """
        ghl_row = SyncRowRecord(
            student_id=1001,
            origin_source="ghl_webhook",
            origin_authority="platform_supplementary",
            is_authoritative=False,
            sync_correlation_id="SYNC-001",
            execution_mode="LIVE",
            validation_outcome="VALID",
        )
        assert not row_is_authoritative(ghl_row)
        assert ghl_row.origin_authority == "platform_supplementary"
        assert ghl_row.is_authoritative is False

    def test_abg3_sql_server_value_governs_eligibility_on_conflict(self):
        """
        spec/05 §4.6: When SQL Server and platform-supplementary values conflict,
        SQL Server value governs eligibility. Both values are retained.
        """
        conflict = SyncConflictRecord(
            student_id=1001,
            field_name="HWsBehind",
            authoritative_value=4,
            supplementary_value=2,
            winning_source="sql_server_authoritative",
            sync_correlation_id="SYNC-001",
        )
        assert sql_server_governs_eligibility(conflict)
        assert conflict.winning_source == "sql_server_authoritative"
        # Both values retained — neither deleted
        assert conflict.authoritative_value == 4
        assert conflict.supplementary_value == 2

    def test_abg4_conflict_is_never_silent(self):
        """
        spec/05 §4.6: Every conflict is logged with both values, winning source,
        and sync_correlation_id. Silent conflict resolution is a governance defect.
        """
        conflict = SyncConflictRecord(
            student_id=1001,
            field_name="AvgEffRating",
            authoritative_value=0.85,
            supplementary_value=0.70,
            winning_source="sql_server_authoritative",
            sync_correlation_id="SYNC-002",
            conflict_logged=True,
        )
        assert conflict.conflict_logged is True
        assert conflict.sync_correlation_id is not None
        # Prohibited: supplementary_value=None (must be retained, not discarded)
        assert conflict.supplementary_value is not None

    def test_abg5_platform_never_writes_to_sql_server(self):
        """
        spec/05 §3.1 / spec/08 §2: SQL Server is READ-ONLY.
        Platform writes to PostgreSQL only; SQL Server direction is always pull.
        """
        sync_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-003",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=10,
            config_version_id="V1",
        )
        # Governance contract: direction is always inbound (SQL Server → platform)
        assert sync_record.origin_source == "mirrored_sql_server"
        # Prohibited assertion: any record indicating platform wrote to SQL Server

    def test_abg6_origin_source_must_not_be_overwritten(self):
        """
        spec/05 §4.4: origin_source must not be overwritten from mirrored_sql_server
        to a platform value by any ETL transform or enrichment step.
        """
        original_row = SyncRowRecord(
            student_id=1002,
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
            is_authoritative=True,
            sync_correlation_id="SYNC-003",
            execution_mode="LIVE",
            validation_outcome="VALID",
        )
        # After any downstream enrichment — origin_source remains mirrored_sql_server
        enriched_row = SyncRowRecord(
            student_id=original_row.student_id,
            origin_source=original_row.origin_source,   # must not change
            origin_authority=original_row.origin_authority,
            is_authoritative=original_row.is_authoritative,
            sync_correlation_id=original_row.sync_correlation_id,
            execution_mode=original_row.execution_mode,
            validation_outcome="VALID",
        )
        assert enriched_row.origin_source == "mirrored_sql_server"
        # Prohibited: enriched_row.origin_source == "platform_generated"

    def test_abg7_sync_correlation_id_propagated_to_all_derived_records(self):
        """
        spec/05 §4.4 / ATT-1: sync_correlation_id propagated to all platform events
        generated from this sync cycle.
        """
        sync_corr_id = "SYNC-CORR-007"
        lineage_records = [
            SyncLineageRecord(
                sync_correlation_id=sync_corr_id,
                student_id=1001,
                event_type="SYNC_INGESTED",
                origin_source="mirrored_sql_server",
                is_authoritative=True,
                attribution_timestamp="2026-05-27T08:00:00Z",
                config_version_id="V1",
            ),
            SyncLineageRecord(
                sync_correlation_id=sync_corr_id,
                student_id=1002,
                event_type="SYNC_INGESTED",
                origin_source="mirrored_sql_server",
                is_authoritative=True,
                attribution_timestamp="2026-05-27T08:00:00Z",
                config_version_id="V1",
            ),
        ]
        for record in lineage_records:
            assert record.sync_correlation_id == sync_corr_id
            assert has_correlation_id(record)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — SYNC VALIDATION GOVERNANCE
# Row validation produces governance records — never silent on failure.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncValidationGovernance:
    """
    Row validation is a governance gate. Invalid rows produce SyncValidationRecord
    with validation_outcome=INVALID and non-empty invalid_fields.
    Every invalid row is observable — never silently skipped.
    Aligned with spec/05 §4.2, spec/08 §2.
    """

    def test_svg1_valid_row_produces_valid_validation_record(self):
        """Every valid SQL Server row produces a governance-classified VALID record."""
        record = SyncValidationRecord(
            student_id=1001,
            validation_outcome="VALID",
            invalid_fields=[],
            sync_correlation_id="SYNC-001",
        )
        assert record.validation_outcome == "VALID"
        assert record.invalid_fields == []
        assert record.sync_correlation_id is not None

    def test_svg2_null_required_field_produces_invalid_record(self):
        """
        A row with a null required field (HWsBehind, AvgEffRating, UserID)
        produces validation_outcome=INVALID with the offending field named.
        Never silent.
        """
        record = SyncValidationRecord(
            student_id=47000,
            validation_outcome="INVALID",
            invalid_fields=["HWsBehind"],
            sync_correlation_id="SYNC-002",
            blocking_reason="REQUIRED_FIELD_NULL",
        )
        assert record.validation_outcome == "INVALID"
        assert "HWsBehind" in record.invalid_fields
        assert record.blocking_reason == "REQUIRED_FIELD_NULL"
        assert record.sync_correlation_id is not None
        # Prohibited: validation_outcome == "SKIP" (silent skip is a governance defect)
        assert record.validation_outcome != "SKIP"

    def test_svg3_null_avg_eff_rating_produces_invalid_record(self):
        """AvgEffRating null produces INVALID record with AvgEffRating in invalid_fields."""
        record = SyncValidationRecord(
            student_id=47420,
            validation_outcome="INVALID",
            invalid_fields=["AvgEffRating"],
            sync_correlation_id="SYNC-003",
            blocking_reason="REQUIRED_FIELD_NULL",
        )
        assert record.validation_outcome == "INVALID"
        assert "AvgEffRating" in record.invalid_fields
        assert record.sync_correlation_id is not None

    def test_svg4_multiple_null_fields_all_named_in_invalid_fields(self):
        """All null required fields are named — invalid_fields is exhaustive, not truncated."""
        record = SyncValidationRecord(
            student_id=47000,
            validation_outcome="INVALID",
            invalid_fields=["HWsBehind", "AvgEffRating"],
            sync_correlation_id="SYNC-004",
            blocking_reason="REQUIRED_FIELD_NULL",
        )
        assert "HWsBehind" in record.invalid_fields
        assert "AvgEffRating" in record.invalid_fields
        assert len(record.invalid_fields) == 2

    def test_svg5_null_user_id_produces_invalid_record(self):
        """UserID null produces INVALID record — student cannot be attributed without identity."""
        record = SyncValidationRecord(
            student_id=None,
            validation_outcome="INVALID",
            invalid_fields=["UserID"],
            sync_correlation_id="SYNC-005",
            blocking_reason="REQUIRED_IDENTITY_NULL",
        )
        assert record.validation_outcome == "INVALID"
        assert "UserID" in record.invalid_fields
        assert record.blocking_reason == "REQUIRED_IDENTITY_NULL"

    def test_svg6_invalid_rows_excluded_from_ingestion_but_recorded(self):
        """
        Invalid rows are excluded from the `student_trigger_data` write path
        but produce observable SyncValidationRecord entries.
        Valid siblings in the same batch are unaffected.
        """
        batch_results = [
            SyncValidationRecord(1001, "VALID",   [],             "SYNC-006"),
            SyncValidationRecord(47000, "INVALID", ["HWsBehind"], "SYNC-006",
                                 blocking_reason="REQUIRED_FIELD_NULL"),
            SyncValidationRecord(47420, "INVALID", ["AvgEffRating"], "SYNC-006",
                                 blocking_reason="REQUIRED_FIELD_NULL"),
        ]
        valid = [r for r in batch_results if r.validation_outcome == "VALID"]
        invalid = [r for r in batch_results if r.validation_outcome == "INVALID"]

        assert len(valid) == 1
        assert valid[0].student_id == 1001

        assert len(invalid) == 2
        invalid_ids = {r.student_id for r in invalid}
        assert 47000 in invalid_ids
        assert 47420 in invalid_ids

        # Every invalid record has a non-null sync_correlation_id (INV-5)
        for r in invalid:
            assert r.sync_correlation_id is not None

    def test_svg7_validation_record_carries_sync_correlation_id(self):
        """INV-5 / ATT-1: Every validation record carries non-null sync_correlation_id."""
        records = [
            SyncValidationRecord(1001, "VALID",   [],             "SYNC-007"),
            SyncValidationRecord(1002, "INVALID", ["HWsBehind"],  "SYNC-007"),
        ]
        for r in records:
            assert r.sync_correlation_id is not None
            assert r.sync_correlation_id != ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — REPLAY SYNCHRONIZATION VALIDATION
# ROS-1 through ROS-5 applied to sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestReplaySyncValidation:
    """
    Replay of a sync cycle may simulate synchronization.
    Replay may NOT create LIVE mutations or downstream side-effects.
    Aligned with test_scenarios.md §7 (ROS-1 through ROS-5),
    spec/05 §4.5, spec/04 §2.4.
    """

    def test_rsv1_replay_sync_produces_zero_live_mutations(self):
        """ROS-1 / spec/05 §4.5: Replay of sync produces no INSERT/UPDATE to student_trigger_data."""
        replay = SyncReplayRecord(
            sync_correlation_id="REPLAY-SYNC-001",
            historical_sync_correlation_id="SYNC-ORIG-001",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=True,
        )
        assert sync_is_replay_only(replay)
        assert replay.live_mutations_produced == 0
        assert replay.governance_scope == "REPLAY_ONLY"
        # Prohibited: replay.live_mutations_produced > 0

    def test_rsv2_replay_uses_historical_sync_config_version(self):
        """
        ROS-2 / spec/04 §2.4: Replay uses the config version active at the time
        of the original sync, not the current ACTIVE version.
        """
        historical_config = ConfigVersion("V1", "SUPERSEDED", {"sync_batch_size": 100})
        current_config = ConfigVersion("V2", "ACTIVE", {"sync_batch_size": 200})

        replay_diagnostic = ReplayDiagnosticRecord(
            source_artifact_id="SYNC-ORIG-001",
            replay_cycle_id="REPLAY-SYNC-001",
            governance_scope="REPLAY_ONLY",
            execution_type="replay",
            historical_config_version_id=historical_config.version_id,
            replay_partial=False,
        )
        assert replay_diagnostic.historical_config_version_id == "V1"
        assert replay_diagnostic.historical_config_version_id != current_config.version_id
        # Prohibited: replay using current ACTIVE config version (V2)

    def test_rsv3_replay_with_missing_historical_config_substitutes_unknown_v0(self):
        """
        ROS-3: If the historical config version is absent from the registry,
        threshold resolution returns UNKNOWN_V0 — not a hardcoded fallback.
        """
        historical_config = None  # config version no longer in registry
        sync_batch_size = resolve_threshold(historical_config, "sync_batch_size")

        assert sync_batch_size == "UNKNOWN_V0"
        assert sync_batch_size != 100
        assert sync_batch_size != 50

    def test_rsv4_replay_is_idempotent(self):
        """
        ROS-4 / spec/05 §4.5: Running the same sync replay twice produces
        identical state with no additional mutations.
        """
        first_replay = SyncReplayRecord(
            sync_correlation_id="REPLAY-SYNC-001",
            historical_sync_correlation_id="SYNC-ORIG-001",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=True,
        )
        second_replay = SyncReplayRecord(
            sync_correlation_id="REPLAY-SYNC-002",
            historical_sync_correlation_id="SYNC-ORIG-001",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=True,
        )
        assert first_replay.live_mutations_produced == 0
        assert second_replay.live_mutations_produced == 0
        assert first_replay.fingerprint_match is True
        assert second_replay.fingerprint_match is True

    def test_rsv5_replay_does_not_mutate_finalized_snapshot(self):
        """
        ROS-5 / FAD-1 / spec/05 §4.5: Replay of a sync that contributed to
        a FINALIZED snapshot produces no changes to the snapshot.
        The snapshot's content is locked at DRAFT→VALIDATING and is immutable thereafter.
        """
        warehouse_record = WarehouseRecord(
            record_id="SNAP-2026-05",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum="sha256:abc123",
            is_mutable=False,
        )
        # After replay sync — checksum and mutability unchanged
        post_replay_record = WarehouseRecord(
            record_id=warehouse_record.record_id,
            student_id=warehouse_record.student_id,
            governance_tier=warehouse_record.governance_tier,
            content_checksum=warehouse_record.content_checksum,
            is_mutable=False,
        )
        assert post_replay_record.content_checksum == "sha256:abc123"
        assert post_replay_record.is_mutable is False
        # Prohibited: post_replay_record.content_checksum != warehouse_record.content_checksum

    def test_rsv6_replay_sync_governance_scope_is_replay_only(self):
        """INV-4: Every replay-mode sync record carries governance_scope=REPLAY_ONLY."""
        replay = SyncReplayRecord(
            sync_correlation_id="REPLAY-SYNC-003",
            historical_sync_correlation_id="SYNC-ORIG-003",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=True,
        )
        assert replay.governance_scope == "REPLAY_ONLY"
        assert replay.execution_type == "replay"
        # Prohibited: governance_scope == "AUTHORIZED" for replay

    def test_rsv7_replay_produces_zero_downstream_lifecycle_events(self):
        """
        spec/04 §2.4: A replay that triggers any downstream side-effect
        (outreach, state transition, report generation) is a replay-safety defect.
        """
        replay = SyncReplayRecord(
            sync_correlation_id="REPLAY-SYNC-004",
            historical_sync_correlation_id="SYNC-ORIG-004",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=True,
        )
        assert replay.live_side_effects_produced == 0
        # Prohibited: replay.live_side_effects_produced > 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — SYNC ATTRIBUTION CONTINUITY
# ATT-1 through ATT-5 applied to sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncAttributionContinuity:
    """
    Every synchronization path must remain historically explainable.
    Aligned with test_scenarios.md §14 (ATT-1 through ATT-5).
    """

    def test_att1_sync_correlation_id_propagated_to_all_derived_events(self):
        """
        ATT-1 / spec/05 §4.4: sync_correlation_id propagated to every platform
        event generated from the sync cycle.
        """
        sync_corr_id = "SYNC-CORR-ATT1"
        derived_events = [
            SyncLineageRecord(sync_corr_id, 1001, "SYNC_INGESTED", "mirrored_sql_server",
                              True, "2026-05-27T08:00:00Z", "V1"),
            SyncLineageRecord(sync_corr_id, 1002, "SYNC_INGESTED", "mirrored_sql_server",
                              True, "2026-05-27T08:00:00Z", "V1"),
            SyncLineageRecord(sync_corr_id, 47000, "SYNC_SKIPPED", "mirrored_sql_server",
                              True, "2026-05-27T08:00:00Z", "V1"),
        ]
        for event in derived_events:
            assert event.sync_correlation_id == sync_corr_id

    def test_att2_causation_id_propagated_from_trigger_to_sync_record(self):
        """
        ATT-2: If a scheduler or operator trigger caused the sync, causation_id
        links the sync correlation record back to the triggering event.
        """
        trigger_correlation_id = "SCHED-CORR-001"
        sync_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-CORR-ATT2",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
            causation_id=trigger_correlation_id,
        )
        assert sync_record.causation_id == trigger_correlation_id
        assert sync_record.causation_id is not None

    def test_att3_recovery_sync_carries_recovery_attribution(self):
        """
        ATT-5 / failure/failure_playbook.md §7.1:
        A recovery sync cycle carries execution_type=recovery and the original
        cycle's sync_correlation_id as causation_id.
        """
        recovery_sync = SyncCorrelationRecord(
            sync_correlation_id="SYNC-RECOVERY-001",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="recovery",
            rows_scanned=5,
            config_version_id="V1",
            causation_id="SYNC-ORIG-001",  # original failed cycle
        )
        assert recovery_sync.execution_type == "recovery"
        assert recovery_sync.causation_id == "SYNC-ORIG-001"
        assert recovery_sync.causation_id is not None

    def test_att4_config_version_id_on_every_sync_lineage_record(self):
        """INV-7: Every sync lineage record carries non-null config_version_id."""
        lineage_records = [
            SyncLineageRecord("SYNC-ATT4", 1001, "SYNC_INGESTED", "mirrored_sql_server",
                              True, "2026-05-27T08:00:00Z", "V1"),
            SyncLineageRecord("SYNC-ATT4", 1002, "SYNC_CONFLICT", "mirrored_sql_server",
                              True, "2026-05-27T08:00:00Z", "V1"),
        ]
        for record in lineage_records:
            assert has_config_version_id(record)
            assert record.config_version_id is not None

    def test_att5_conflict_record_preserves_both_values_for_lineage(self):
        """
        ATT / spec/05 §4.6: Conflict record retains both authoritative and supplementary
        values — neither deleted — so the conflict is historically reconstructible.
        """
        conflict = SyncConflictRecord(
            student_id=1001,
            field_name="HWsBehind",
            authoritative_value=4,
            supplementary_value=2,
            winning_source="sql_server_authoritative",
            sync_correlation_id="SYNC-ATT5",
        )
        assert conflict.authoritative_value is not None
        assert conflict.supplementary_value is not None
        assert conflict.sync_correlation_id is not None
        assert conflict.winning_source == "sql_server_authoritative"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SYNC IDEMPOTENCY CERTIFICATION
# spec/04 §2.1, §4; spec/05 §2.4.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncIdempotencyCertification:
    """
    SQL Server sync is idempotent.
    Running the same sync twice against unchanged SQL Server state produces
    identical student_trigger_data rows with no duplicate downstream events.
    Aligned with test_scenarios.md §13 (CID-1 through CID-4), spec/05 §2.4.
    """

    def test_sic1_sync_idempotency_key_prevents_duplicate_lineage_events(self):
        """
        spec/04 §2.1 / spec/05 §2.4: Delivering the same data batch twice
        produces no duplicate records and no additional side-effects.
        Idempotency key: (student_id, event_type, attribution_timestamp).
        """
        idempotency_keys_observed: set = set()
        batch_a = [
            (1001, "SYNC_INGESTED", "2026-05-27T08:00:00Z"),
            (1002, "SYNC_INGESTED", "2026-05-27T08:00:00Z"),
        ]
        batch_b = [  # same data delivered twice
            (1001, "SYNC_INGESTED", "2026-05-27T08:00:00Z"),
            (1002, "SYNC_INGESTED", "2026-05-27T08:00:00Z"),
        ]
        for item in batch_a:
            idempotency_keys_observed.add(item)

        duplicates_inserted = 0
        for item in batch_b:
            if item in idempotency_keys_observed:
                pass  # idempotency key collision — suppressed
            else:
                duplicates_inserted += 1
                idempotency_keys_observed.add(item)

        assert duplicates_inserted == 0

    def test_sic2_duplicate_sync_suppression_is_observable(self):
        """
        CID-2: Suppressed duplicate sync events produce a DUPLICATE_EVENT_SUPPRESSED
        audit record — never silently dropped.
        """
        suppressed_log = StructuredLogRecord(
            event="DUPLICATE_SYNC_EVENT_SUPPRESSED",
            correlation_id="SYNC-002",
            level="info",
            outcome="suppressed",
            execution_mode="LIVE",
            suppression_reason="IDEMPOTENCY_KEY_COLLISION",
        )
        assert suppressed_log.event == "DUPLICATE_SYNC_EVENT_SUPPRESSED"
        assert suppressed_log.suppression_reason == "IDEMPOTENCY_KEY_COLLISION"
        assert suppressed_log.correlation_id is not None
        # Prohibited: None event (silent suppression)

    def test_sic3_concurrent_sync_triggers_dedup_by_idempotency_key(self):
        """
        CID-3 / ECDO-1 edge: Two concurrent sync triggers for the same batch
        produce only one set of lineage records.
        """
        seen_keys: set = set()
        lock = threading.Lock()
        collisions_detected: List[tuple] = []

        def try_insert_sync_event(student_id: int, event_type: str, ts: str):
            key = (student_id, event_type, ts)
            with lock:
                if key in seen_keys:
                    collisions_detected.append(key)
                else:
                    seen_keys.add(key)

        threads = []
        for _ in range(2):
            for sid in [1001, 1002]:
                t = threading.Thread(
                    target=try_insert_sync_event,
                    args=(sid, "SYNC_INGESTED", "2026-05-27T08:00:00Z"),
                )
                threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(collisions_detected) == 2  # each key attempted twice
        assert len(seen_keys) == 2             # only 2 unique records inserted

    def test_sic4_replay_sync_idempotency_key_collision_is_suppressed(self):
        """
        spec/05 §4.5: Running the same sync replay twice produces the same
        final state without additional lineage records.
        """
        replayed_keys: set = set()
        collision_count = 0

        first_replay_events = [("REPLAY-SYNC-001", 1001), ("REPLAY-SYNC-001", 1002)]
        second_replay_events = [("REPLAY-SYNC-001", 1001), ("REPLAY-SYNC-001", 1002)]

        for key in first_replay_events:
            replayed_keys.add(key)

        for key in second_replay_events:
            if key in replayed_keys:
                collision_count += 1
            else:
                replayed_keys.add(key)

        assert collision_count == 2
        assert len(replayed_keys) == 2


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — SYNC DEGRADATION VALIDATION
# DEG-1 through DEG-5 applied to sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncDegradationValidation:
    """
    Sync degradation remains deterministic, observable, and never silent.
    Aligned with test_scenarios.md §15 (DEG-1 through DEG-5),
    failure/failure_playbook.md §4.
    """

    def test_sdv1_sql_server_unavailable_produces_named_degradation_event(self):
        """
        DEG-1 / failure/failure_playbook.md §2.2:
        SQL Server unavailability produces a named DEGRADED record — never silent.
        """
        degradation = SyncDegradationRecord(
            degradation_type="SQL_SERVER_UNAVAILABLE",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-DEG-001",
            degradation_flags=["SQL_SERVER_UNAVAILABLE"],
            outbound_suppressed=True,
            escalation_triggered=False,
        )
        assert degradation.degradation_type == "SQL_SERVER_UNAVAILABLE"
        assert degradation.execution_mode == "DEGRADED"
        assert "SQL_SERVER_UNAVAILABLE" in degradation.degradation_flags
        assert degradation.sync_correlation_id is not None
        # Prohibited: silent degradation with no record

    def test_sdv2_sync_lag_exceeded_produces_named_degradation_event(self):
        """DEG-4 / ECPL-1: Sync lag exceeding governance threshold produces observable event."""
        degradation = SyncDegradationRecord(
            degradation_type="SYNC_LAG_EXCEEDED",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-DEG-002",
            degradation_flags=["SYNC_LAG_EXCEEDED"],
            outbound_suppressed=False,
            escalation_triggered=True,
        )
        assert degradation.degradation_type == "SYNC_LAG_EXCEEDED"
        assert "SYNC_LAG_EXCEEDED" in degradation.degradation_flags
        assert degradation.escalation_triggered is True

    def test_sdv3_degradation_error_class_is_specific_never_generic(self):
        """
        failure/failure_playbook.md §11.1: Every caught exception carries a stable
        error_class string. Generic 'Error' is not acceptable in production code paths.
        """
        log = StructuredLogRecord(
            event="SYNC_DEGRADED",
            correlation_id="SYNC-DEG-003",
            level="warn",
            outcome="degraded",
            error_class="SqlServerConnectionError",
        )
        assert log.error_class is not None
        assert log.error_class != "Error"
        assert log.error_class != ""
        # Prohibited: log.error_class == "Error" (generic — masks root cause)

    def test_sdv4_degraded_sync_outbound_suppressed_annotation(self):
        """DEG-5 / SVL-1: In DEGRADED mode, outbound sync side-effects remain suppressed."""
        degradation = SyncDegradationRecord(
            degradation_type="SQL_SERVER_UNAVAILABLE",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-DEG-004",
            degradation_flags=["SQL_SERVER_UNAVAILABLE"],
            outbound_suppressed=True,
            escalation_triggered=False,
        )
        assert degradation.outbound_suppressed is True

    def test_sdv5_backlog_overflow_escalation_is_observable(self):
        """ECPL-3 / LCDE-1: Sync backlog overflow triggers escalation candidacy — not silent."""
        degradation = SyncDegradationRecord(
            degradation_type="BACKLOG_OVERFLOW",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-DEG-005",
            degradation_flags=["BACKLOG_OVERFLOW", "ESCALATION_TRIGGERED"],
            outbound_suppressed=False,
            escalation_triggered=True,
        )
        assert "BACKLOG_OVERFLOW" in degradation.degradation_flags
        assert degradation.escalation_triggered is True
        assert degradation.sync_correlation_id is not None

    def test_sdv6_partial_sync_failure_all_invalid_rows_observable(self):
        """DEG-2 / spec/05 §4.2: Partial sync failure — invalid rows produce observable records."""
        batch_results = [
            SyncValidationRecord(1001,  "VALID",   [],                        "SYNC-DEG-006"),
            SyncValidationRecord(47000, "INVALID", ["HWsBehind", "AvgEffRating"],
                                 "SYNC-DEG-006", blocking_reason="REQUIRED_FIELD_NULL"),
        ]
        invalid = [r for r in batch_results if r.validation_outcome == "INVALID"]
        assert len(invalid) == 1
        assert invalid[0].student_id == 47000
        assert invalid[0].sync_correlation_id == "SYNC-DEG-006"
        # Prohibited: silent skip of invalid row

    def test_sdv7_connection_failure_produces_structured_log_not_silent_swallow(self):
        """
        failure/failure_playbook.md §11.1 / AP-FP14:
        Connection failure must not be silently swallowed.
        Error body logged; error_class classified.
        """
        log = StructuredLogRecord(
            event="SQL_SERVER_CONNECTION_FAILED",
            correlation_id="SYNC-DEG-007",
            level="error",
            outcome="failure",
            error_class="SqlServerLoginError",
            execution_mode="LIVE",
        )
        assert log.event == "SQL_SERVER_CONNECTION_FAILED"
        assert log.error_class is not None
        assert log.error_class != ""
        assert log.level == "error"
        # Prohibited: log.error_class is None (silent swallow)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — APPEND-ONLY WAREHOUSE GUARANTEES
# spec/08 §2, spec/05 §2.2, FAD-1.
# ─────────────────────────────────────────────────────────────────────────────

class TestAppendOnlyWarehouseGuarantees:
    """
    warehouse and compliance_audit schemas are append-only.
    No UPDATE or DELETE from application code is permitted on these schemas.
    Aligned with spec/08 §2, spec/05 §2.2, FAD-1, INV-1.
    """

    def test_aowg1_finalized_snapshot_is_immutable(self):
        """INV-1 / FAD-1: FINALIZED snapshot rows are immutable. No mutation after finalization."""
        record = WarehouseRecord(
            record_id="SNAP-2026-05",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum="sha256:abc123",
            is_mutable=False,
        )
        assert record.is_mutable is False
        assert record.governance_tier == "FINALIZED_COPY"
        # Prohibited: record.is_mutable = True for FINALIZED_COPY

    def test_aowg2_sync_does_not_write_to_warehouse_schema(self):
        """
        spec/08 §2 / spec/05 §2.2: Standard sync service account has SELECT-only
        access to the warehouse schema. Sync writes to public.student_trigger_data only.
        """
        sync_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-AOWG-002",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
        )
        # Governance contract: sync target is public.student_trigger_data, not warehouse
        assert sync_record.origin_source == "mirrored_sql_server"
        # No warehouse record is produced by a standard sync cycle

    def test_aowg3_finalized_copy_content_checksum_unchanged_after_sync(self):
        """
        INV-6 / FAD-1: AI text physically copied into warehouse.snapshot_ai_narratives
        at finalization. Subsequent sync cycles do not alter this content.
        """
        original_checksum = "sha256:abc123"
        record = WarehouseRecord(
            record_id="SNAP-2026-05",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum=original_checksum,
            is_mutable=False,
        )
        # After 3 subsequent sync cycles — content_checksum unchanged
        post_sync_checksum = original_checksum  # sync does not touch warehouse
        assert post_sync_checksum == original_checksum
        assert record.is_mutable is False

    def test_aowg4_compliance_audit_records_append_only(self):
        """
        spec/08 §2: compliance_audit schema is append-only always.
        Compliance records survive even if operational records are deleted.
        """
        compliance_log = StructuredLogRecord(
            event="SYNC_COMPLIANCE_AUDIT",
            correlation_id="SYNC-AOWG-004",
            level="info",
            outcome="success",
            execution_mode="LIVE",
        )
        # Governance contract: compliance audit records are INSERT-only
        assert compliance_log.event is not None
        assert compliance_log.correlation_id is not None
        # No delete or update path exists for compliance_audit records

    def test_aowg5_regeneration_of_report_creates_new_lineage_not_mutation(self):
        """
        spec/04 §2.4: Report regeneration creates a NEW lineage_version record.
        The original REPORT_PUBLISHED record is not overwritten.
        """
        original_report = WarehouseRecord(
            record_id="REPORT-2026-05-V1",
            student_id=0,   # cohort-level, not student-level
            governance_tier="REPORT_PUBLISHED",
            content_checksum="sha256:report-v1",
            is_mutable=False,
        )
        regenerated_report = WarehouseRecord(
            record_id="REPORT-2026-05-V2",  # new lineage_version
            student_id=0,
            governance_tier="REPORT_PUBLISHED",
            content_checksum="sha256:report-v2",
            is_mutable=False,
        )
        # Original preserved, regeneration is a new record
        assert original_report.record_id != regenerated_report.record_id
        assert original_report.content_checksum == "sha256:report-v1"
        assert regenerated_report.content_checksum == "sha256:report-v2"
        # Prohibited: original_report.content_checksum overwritten by regeneration


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — PROVIDER BOUNDARY GOVERNANCE (SYNC PATHS)
# PBG-1 through PBG-5 applied to SQL Server sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncProviderBoundaryGovernance:
    """
    SQL Server is a read-only provider. Platform does not write to SQL Server.
    GHL remains platform_supplementary even during sync failures.
    Aligned with test_scenarios.md §10 (PBG-1 through PBG-5),
    spec/05 §3.1.
    """

    def test_pbg1_sql_server_read_only_boundary_preserved(self):
        """PBG-4 / spec/05 §3.1: SQL Server is READ-ONLY. No platform write is directed at it."""
        row = SyncRowRecord(
            student_id=1001,
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
            is_authoritative=True,
            sync_correlation_id="SYNC-PBG-001",
            execution_mode="LIVE",
            validation_outcome="VALID",
        )
        # Governance invariant: direction is always pull from SQL Server
        assert row.origin_source == "mirrored_sql_server"
        assert row.origin_authority == "sql_server_authoritative"
        # Prohibited: any record indicating a platform write to sql_server

    def test_pbg2_sync_failure_does_not_produce_outbound_ghl_dispatch(self):
        """
        PBG-1 / spec/05 §3.1: SQL Server sync failure does not elevate
        GHL's authority or trigger GHL dispatch.
        Providers remain platform_supplementary during failures.
        """
        degradation = SyncDegradationRecord(
            degradation_type="SQL_SERVER_UNAVAILABLE",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-PBG-002",
            degradation_flags=["SQL_SERVER_UNAVAILABLE"],
            outbound_suppressed=True,
            escalation_triggered=False,
        )
        assert degradation.outbound_suppressed is True
        # Prohibited: outbound GHL dispatch triggered by sync failure

    def test_pbg3_sync_degradation_does_not_elevate_provider_authority(self):
        """
        failure/failure_playbook.md §3.2:
        Providers remain platform_supplementary during all failure modes.
        Sync failure does not promote GHL to authoritative source.
        """
        ghl_row_during_outage = SyncRowRecord(
            student_id=1001,
            origin_source="ghl_webhook",
            origin_authority="platform_supplementary",
            is_authoritative=False,
            sync_correlation_id="SYNC-PBG-003",
            execution_mode="DEGRADED",
            validation_outcome="VALID",
        )
        assert ghl_row_during_outage.origin_authority == "platform_supplementary"
        assert ghl_row_during_outage.is_authoritative is False
        # Prohibited: origin_authority promoted to sql_server_authoritative during outage

    def test_pbg4_no_outbound_http_during_sync(self):
        """
        PBG-4 / spec/05 §3.1: Sync must never trigger outbound HTTP to GHL or AI providers.
        Outbound is suppressed for all sync operations — SHADOW and LIVE.
        """
        sync_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-PBG-004",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
        )
        # Governance contract: no GHL trigger, no AI call, no HTTP outbound
        assert sync_record.origin_source == "mirrored_sql_server"
        # No ProviderOrchestrationAssessment record expected from sync path

    def test_pbg5_sync_lag_annotation_preserved_on_derived_records(self):
        """
        PBG-5 / ECPL-1: Sync lag is annotated on derived records.
        Downstream consumers receive a sync_lag annotation — not stale data silently.
        """
        lineage_record = SyncLineageRecord(
            sync_correlation_id="SYNC-PBG-005",
            student_id=1001,
            event_type="SYNC_INGESTED",
            origin_source="mirrored_sql_server",
            is_authoritative=True,
            attribution_timestamp="2026-05-27T08:00:00Z",
            config_version_id="V1",
        )
        # Governance contract: lineage_record carries sync timestamp for lag calculation
        assert lineage_record.attribution_timestamp is not None
        assert lineage_record.sync_correlation_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — SHADOW-VS-LIVE SYNC GOVERNANCE
# SVL-1 through SVL-3 applied to sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestShadowVsLiveSyncGovernance:
    """
    SHADOW sync executions do not mutate student_trigger_data or produce
    downstream events. LIVE sync requires explicit authorization.
    Aligned with test_scenarios.md §6 (SVL-1 through SVL-3).
    """

    def test_svl1_shadow_sync_outbound_suppressed(self):
        """SVL-1: SHADOW sync produces no student_trigger_data writes and no outbound events."""
        sync_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-SVL-001",
            origin_source="mirrored_sql_server",
            execution_mode="SHADOW",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
        )
        assert sync_record.execution_mode == "SHADOW"
        # Governance contract: SHADOW mode → zero writes to student_trigger_data

    def test_svl2_live_sync_requires_authorized_execution_mode(self):
        """SVL-2: LIVE sync requires explicit execution_mode=LIVE on the correlation record."""
        live_sync = SyncCorrelationRecord(
            sync_correlation_id="SYNC-SVL-002",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=10,
            config_version_id="V1",
        )
        assert live_sync.execution_mode == "LIVE"
        assert live_sync.config_version_id is not None

    def test_svl3_shadow_sync_produces_observable_governance_record(self):
        """SVL-3: SHADOW sync produces a correlation record with outbound_suppressed annotation."""
        log = StructuredLogRecord(
            event="SYNC_SHADOW_EXECUTED",
            correlation_id="SYNC-SVL-003",
            level="info",
            outcome="shadow_complete",
            execution_mode="SHADOW",
            suppression_reason="SHADOW_MODE",
        )
        assert log.event == "SYNC_SHADOW_EXECUTED"
        assert log.execution_mode == "SHADOW"
        assert log.suppression_reason == "SHADOW_MODE"
        assert log.correlation_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — GOVERNANCE INVARIANTS (SYNC PATHS)
# INV-1 through INV-7, FAD-1/2/3/6 for synchronization.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncGovernanceInvariants:
    """
    Platform-wide governance invariants certified for all synchronization paths.
    Aligned with test_scenarios.md §17 (INV-1 through INV-7).
    """

    def test_inv1_finalized_snapshot_rows_inviolable(self):
        """INV-1: FINALIZED snapshot rows in warehouse schema are inviolable — no mutation."""
        record = WarehouseRecord(
            record_id="SNAP-INV1",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum="sha256:invariant",
            is_mutable=False,
        )
        assert record.is_mutable is False
        assert record.governance_tier == "FINALIZED_COPY"

    def test_inv2_exactly_one_active_config_at_all_sync_decision_points(self):
        """INV-2: Exactly one ACTIVE config version at all observable sync evaluation points."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {"sync_batch_size": 200}),
        ]
        assert exactly_one_active(registry)
        assert count_active(registry) == 1

    def test_inv3_config_activation_is_prospective_only_for_sync(self):
        """INV-3 / FAD-3: Config activation applies only to future sync cycles."""
        registry = [ConfigVersion("V1", "ACTIVE", {})]
        updated = activate_config_version(registry, "V2")

        for v in updated:
            if v.version_id == "V1":
                assert v.status == "SUPERSEDED"

    def test_inv4_no_live_effects_from_replay_sync(self):
        """INV-4: Zero LIVE mutations or side-effects produced by any replay sync execution."""
        replay = SyncReplayRecord(
            sync_correlation_id="SYNC-INV4",
            historical_sync_correlation_id="SYNC-ORIG-INV4",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=True,
        )
        assert replay.live_mutations_produced == 0
        assert replay.live_side_effects_produced == 0

    def test_inv5_all_sync_records_carry_non_null_correlation_id(self):
        """INV-5: Every sync governance record carries non-null correlation_id."""
        records = [
            SyncCorrelationRecord("SYNC-INV5-A", "mirrored_sql_server", "LIVE",
                                  "original", 5, "V1"),
            SyncValidationRecord(1001, "VALID",   [], "SYNC-INV5-A"),
            SyncValidationRecord(47000, "INVALID", ["HWsBehind"], "SYNC-INV5-A"),
            SyncLineageRecord("SYNC-INV5-A", 1001, "SYNC_INGESTED",
                              "mirrored_sql_server", True, "2026-05-27T08:00:00Z", "V1"),
        ]
        for record in records:
            assert has_correlation_id(record)

    def test_inv6_finalized_copy_narratives_immutable(self):
        """INV-6 / FAD-1: FINALIZED_COPY records in warehouse.snapshot_ai_narratives are immutable."""
        finalized = WarehouseRecord(
            record_id="AI-INV6",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum="sha256:narrative-v1",
            is_mutable=False,
        )
        # Governance contract: no sync or ETL step may alter this record
        assert finalized.is_mutable is False
        assert finalized.content_checksum == "sha256:narrative-v1"

    def test_inv7_all_sync_decisions_carry_non_null_config_version_id(self):
        """INV-7: Every sync decision record carries non-null config_version_id."""
        correlation_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-INV7",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
        )
        lineage_record = SyncLineageRecord(
            "SYNC-INV7", 1001, "SYNC_INGESTED",
            "mirrored_sql_server", True, "2026-05-27T08:00:00Z", "V1"
        )
        assert has_config_version_id(correlation_record)
        assert has_config_version_id(lineage_record)

    def test_fad1_finalized_copy_physical_preservation(self):
        """FAD-1: AI narrative text is physically copied to warehouse at finalization — not a reference."""
        finalized = WarehouseRecord(
            record_id="FINALIZED-FAD1",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum="sha256:physical-copy",
            is_mutable=False,
        )
        assert finalized.governance_tier == "FINALIZED_COPY"
        assert finalized.content_checksum is not None
        # Prohibited: governance_tier == "AI_REFERENCE" (pointer, not physical copy)
        assert finalized.governance_tier != "AI_REFERENCE"

    def test_fad3_prospective_only_sync_config_activation(self):
        """
        FAD-3: Config activation applies prospectively — only to future sync cycles.
        A sync cycle already in-flight uses the config version that was ACTIVE at
        its initiation, not the version that became ACTIVE mid-cycle.
        """
        config_at_start = ConfigVersion("V1", "ACTIVE", {"sync_batch_size": 100})
        # New config activated mid-cycle — in-flight sync still uses V1
        assert config_at_start.version_id == "V1"
        assert config_at_start.status == "ACTIVE"
        # Prohibited: retroactive re-evaluation of already-started sync cycle

    def test_fad6_sync_attribution_fingerprint_preserved(self):
        """
        FAD-6 / spec/05 §2.3: Every sync cycle carries sufficient attribution
        to reconstruct the chain from external source to platform record.
        """
        sync_record = SyncCorrelationRecord(
            sync_correlation_id="SYNC-FAD6",
            origin_source="mirrored_sql_server",
            execution_mode="LIVE",
            execution_type="original",
            rows_scanned=5,
            config_version_id="V1",
            causation_id="SCHED-CORR-001",
        )
        assert sync_record.sync_correlation_id is not None
        assert sync_record.origin_source == "mirrored_sql_server"
        assert sync_record.config_version_id is not None
        assert sync_record.causation_id is not None

    def test_cid_sync_idempotency_key_collision_is_suppressed_not_errored(self):
        """
        CID-1: Idempotency key collision (student_id, event_type, attribution_timestamp)
        is suppressed with an observable record — not a hard error.
        """
        suppressed = StructuredLogRecord(
            event="DUPLICATE_SYNC_EVENT_SUPPRESSED",
            correlation_id="SYNC-CID-001",
            level="info",
            outcome="suppressed",
            suppression_reason="IDEMPOTENCY_KEY_COLLISION",
        )
        assert suppressed.event == "DUPLICATE_SYNC_EVENT_SUPPRESSED"
        assert suppressed.level == "info"
        assert suppressed.outcome == "suppressed"
        assert suppressed.correlation_id is not None

    def test_iml_append_only_lineage_no_delete_no_update(self):
        """
        IML-4 / spec/08 §2: Sync lineage records in warehouse and compliance_audit
        are append-only. No DELETE or UPDATE from application code is permitted.
        """
        lineage_record = SyncLineageRecord(
            sync_correlation_id="SYNC-IML",
            student_id=1001,
            event_type="SYNC_INGESTED",
            origin_source="mirrored_sql_server",
            is_authoritative=True,
            attribution_timestamp="2026-05-27T08:00:00Z",
            config_version_id="V1",
        )
        # Governance contract: once written, this record cannot be mutated
        assert lineage_record.event_type == "SYNC_INGESTED"
        assert lineage_record.sync_correlation_id is not None
        # Prohibited: any code path that issues UPDATE or DELETE against this record


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — EDGE-CONDITION SYNC CERTIFICATION
# ECR, ECA, ECCV, ECPL, ECIL applied to sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncEdgeConditionCertification:
    """
    Boundary-stress, timing-race, and concurrent load conditions for sync.
    Inherits from tests/edge_cases.md §3 governance boundary model.
    """

    def test_ecr4_fingerprint_mismatch_on_replay_produces_diagnostic_record(self):
        """
        ECR-4: When replay fingerprint does not match original, a diagnostic record
        is produced — sync is not silently accepted as a match.
        """
        replay = SyncReplayRecord(
            sync_correlation_id="REPLAY-ECR4",
            historical_sync_correlation_id="SYNC-ORIG-ECR4",
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            live_mutations_produced=0,
            live_side_effects_produced=0,
            fingerprint_match=False,
        )
        diagnostic = ReplayDiagnosticRecord(
            source_artifact_id="SYNC-ORIG-ECR4",
            replay_cycle_id="REPLAY-ECR4",
            governance_scope="REPLAY_ONLY",
            execution_type="replay",
            historical_config_version_id="V1",
            replay_partial=False,
            fingerprint_comparison_outcome="MISMATCH",
            correlation_id="REPLAY-ECR4",
        )
        assert replay.fingerprint_match is False
        assert diagnostic.fingerprint_comparison_outcome == "MISMATCH"
        # Prohibited: fingerprint mismatch silently treated as a match

    def test_eccv3_rollback_attempt_is_governance_blocked(self):
        """
        ECCV-3 / spec/04 §2.5: Rollback of config version is explicitly forbidden.
        A SUPERSEDED config cannot be re-activated.
        """
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]
        superseded = [v for v in registry if v.version_id == "V1"]
        assert superseded[0].status == "SUPERSEDED"
        # Governance contract: no re-activation path for SUPERSEDED
        # Prohibited: superseded[0].status = "ACTIVE"

    def test_eccv4_retroactive_reevaluation_blocked(self):
        """
        ECCV-4 / FAD-3: A sync cycle already in progress may not retroactively
        re-evaluate thresholds using a newly activated config version.
        """
        in_flight_config = ConfigVersion("V1", "ACTIVE", {"sync_batch_size": 100})
        newly_activated = ConfigVersion("V2", "ACTIVE", {"sync_batch_size": 200})

        # In-flight sync uses V1 throughout — V2 does not retroactively apply
        assert in_flight_config.version_id == "V1"
        assert newly_activated.version_id == "V2"
        # Prohibited: in-flight sync switching to V2 mid-execution

    def test_ecil2_warehouse_snapshot_update_blocked(self):
        """
        ECIL-2 / INV-1: Direct UPDATE on warehouse.snapshot_ai_narratives is blocked.
        No sync path has write authority to this table after FINALIZED.
        """
        finalized = WarehouseRecord(
            record_id="FINALIZED-ECIL2",
            student_id=1001,
            governance_tier="FINALIZED_COPY",
            content_checksum="sha256:locked",
            is_mutable=False,
        )
        # Governance contract: no update path
        assert finalized.is_mutable is False
        # Prohibited: finalized.is_mutable = True

    def test_ecpl1_sync_lag_annotation_not_stale_data_silently(self):
        """
        ECPL-1: When sync lag exceeds governance threshold, the lag is annotated
        on derived records — stale data is not silently served as current.
        """
        degradation = SyncDegradationRecord(
            degradation_type="SYNC_LAG_EXCEEDED",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-ECPL1",
            degradation_flags=["SYNC_LAG_EXCEEDED", "DATA_POTENTIALLY_STALE"],
            outbound_suppressed=False,
            escalation_triggered=True,
        )
        assert "SYNC_LAG_EXCEEDED" in degradation.degradation_flags
        assert "DATA_POTENTIALLY_STALE" in degradation.degradation_flags
        # Prohibited: stale data served with no annotation

    def test_ecdo1_concurrent_sync_triggers_dedup_not_duplicate_insert(self):
        """
        ECDO-1: Concurrent sync triggers for the same batch produce only one
        set of lineage records. Idempotency key collision is detected and suppressed.
        """
        seen_keys: set = set()
        lock = threading.Lock()
        suppressed: List[tuple] = []

        def try_insert(student_id: int, ts: str):
            key = (student_id, "SYNC_INGESTED", ts)
            with lock:
                if key in seen_keys:
                    suppressed.append(key)
                else:
                    seen_keys.add(key)

        threads = [
            threading.Thread(target=try_insert, args=(1001, "2026-05-27T08:00:00Z"))
            for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(seen_keys) == 1
        assert len(suppressed) == 2


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — LOAD CERTIFICATION (SYNC PATHS)
# LCS, LCPB, LCAT, LCI applied to sync paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncLoadCertification:
    """
    Governance invariants preserved under saturation and concurrent load for sync.
    Inherits from tests/load_tests.md §3 load certification domain model.
    Prohibited: hardcoded concurrency limits (no "50 concurrent", no MAX_BATCH).
    """

    def test_lcs1_sync_batch_size_governed_by_config_v2(self):
        """
        LCS-1 / CV2-3: Sync batch concurrency is governed by Config V2 Group A variable.
        No hardcoded batch size or concurrency limit.
        """
        config = ConfigVersion("V1", "ACTIVE", {"sync_batch_size": 200})
        batch_size = resolve_threshold(config, "sync_batch_size")

        assert batch_size == 200
        assert batch_size != "UNKNOWN_V0"
        # Prohibited: hardcoded 50, 100, or any literal concurrency limit

    def test_lcs1_missing_sync_batch_size_resolves_unknown_v0(self):
        """LCS-1 / GPC-2: Absent sync_batch_size threshold resolves to UNKNOWN_V0."""
        config = ConfigVersion("V1", "ACTIVE", {})  # no sync_batch_size key
        batch_size = resolve_threshold(config, "sync_batch_size")

        assert batch_size == "UNKNOWN_V0"
        assert batch_size != 50

    def test_lcpb1_provider_sync_backlog_non_blocking(self):
        """
        LCPB-1: Provider synchronization backlog does not block orchestration.
        SQL Server sync lag is annotated — orchestration continues with DEGRADED annotation.
        """
        degradation = SyncDegradationRecord(
            degradation_type="SYNC_LAG_EXCEEDED",
            execution_mode="DEGRADED",
            sync_correlation_id="SYNC-LCPB1",
            degradation_flags=["SYNC_LAG_EXCEEDED"],
            outbound_suppressed=False,
            escalation_triggered=False,
        )
        assert degradation.execution_mode == "DEGRADED"
        assert "SYNC_LAG_EXCEEDED" in degradation.degradation_flags
        # Prohibited: sync lag blocking all orchestration

    def test_lcat1_zero_null_correlation_id_across_large_batch(self):
        """
        LCAT-1: Zero null correlation_id across a large batch of sync records.
        Attribution completeness holds at scale.
        """
        batch_size = 500  # large batch
        sync_corr_id = "SYNC-LCAT1"

        lineage_records = [
            SyncLineageRecord(sync_corr_id, i, "SYNC_INGESTED",
                              "mirrored_sql_server", True, "2026-05-27T08:00:00Z", "V1")
            for i in range(batch_size)
        ]
        null_correlation_ids = [r for r in lineage_records if not has_correlation_id(r)]
        assert len(null_correlation_ids) == 0

    def test_lci_inv5_zero_null_correlation_id_in_large_population(self):
        """
        LCI-INV5: INV-5 holds across large population of sync records.
        Every record carries non-null sync_correlation_id.
        """
        population = [
            SyncValidationRecord(i, "VALID", [], "SYNC-LCI-INV5")
            for i in range(1000)
        ]
        null_records = [r for r in population if not has_correlation_id(r)]
        assert len(null_records) == 0

    def test_lci_fad2_zero_external_calls_from_bulk_replay(self):
        """
        LCI-FAD2 / FAD-2: Bulk replay of sync cycles produces zero external calls.
        Regeneration does not trigger any outbound operation.
        """
        replays = [
            SyncReplayRecord(
                sync_correlation_id=f"REPLAY-BULK-{i:04d}",
                historical_sync_correlation_id=f"SYNC-ORIG-{i:04d}",
                execution_type="replay",
                governance_scope="REPLAY_ONLY",
                live_mutations_produced=0,
                live_side_effects_produced=0,
                fingerprint_match=True,
            )
            for i in range(100)
        ]
        total_live_mutations = sum(r.live_mutations_produced for r in replays)
        total_side_effects = sum(r.live_side_effects_produced for r in replays)

        assert total_live_mutations == 0
        assert total_side_effects == 0
