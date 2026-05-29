"""
Shadow Operational Campaign — type definitions.

All campaign types mirror the governed platform contract: pure dataclasses,
no DB/HTTP dependencies, SHADOW-safe by construction.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

# ── Governance constants (identical to production governance layer) ──────────
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

_SUPPRESSED_SCOPES = frozenset({
    SCOPE_SHADOW_ONLY,
    SCOPE_REPLAY_ONLY,
    SCOPE_UNAVAILABLE,
    SCOPE_MAINTENANCE,
    SCOPE_BLOCKED,
    SCOPE_DUPLICATE_SUPPRESSED,
})

_REPLAY_TYPES = frozenset({TYPE_REPLAY, TYPE_REGENERATION})

# ── Campaign status ──────────────────────────────────────────────────────────
CAMPAIGN_STATUS_RUNNING  = "RUNNING"
CAMPAIGN_STATUS_COMPLETE = "COMPLETE"
CAMPAIGN_STATUS_DEGRADED = "DEGRADED"
CAMPAIGN_STATUS_FAILED   = "FAILED"

CERT_OUTCOME_PASSED  = "CERTIFICATION_PASSED"
CERT_OUTCOME_FAILED  = "CERTIFICATION_FAILED"
CERT_OUTCOME_DEGRADED = "CERTIFICATION_DEGRADED"

# ── Failure injection constants ──────────────────────────────────────────────
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


@dataclass
class CampaignRecord:
    """Single record produced during a shadow campaign execution cycle."""
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
    content_hash: Optional[str]
    is_duplicate: bool
    degraded: bool
    degradation_cause: Optional[str]
    degradation_class: Optional[str]
    degradation_severity: Optional[str]
    scheduler_processed: bool
    worker_processed: bool
    prioritization_complete: bool
    transport_generated: bool
    observability_emitted: bool
    provider_assessment_produced: bool
    # INV compliance flags
    inv1_scope_not_mutated: bool = True
    inv2_attribution_not_mutated: bool = True
    inv3_replay_no_live: bool = True
    inv4_shadow_no_dispatch: bool = True
    inv5_rule0_not_bypassed: bool = True
    inv6_correlation_present: bool = True
    inv7_exec_mode_present: bool = True
    # FAD compliance flags
    fad1_finalized_not_mutated: bool = True
    fad2_attribution_immutable: bool = True
    fad3_deterministic: bool = True
    fad4_lineage_append_only: bool = True
    fad5_replay_historical_config: bool = True
    fad6_finalized_lineage_preserved: bool = True


@dataclass
class CampaignMetrics:
    """Aggregated metrics — tracks all 9 required campaign counters."""
    campaign_id: str
    campaign_status: str
    orchestration_count: int = 0
    suppression_count: int = 0
    replay_count: int = 0
    degradation_count: int = 0
    attribution_gap_count: int = 0
    finalized_violation_count: int = 0
    duplicate_suppression_count: int = 0
    config_resolution_failures: int = 0
    provider_suppression_count: int = 0
    # Derived safety counters
    live_effects_total: int = 0
    provider_dispatch_total: int = 0
    authorized_scope_count: int = 0
    inv_violation_count: int = 0
    fad_violation_count: int = 0
    replay_leakage_count: int = 0


@dataclass
class CampaignCycleResult:
    """Result of a single orchestration cycle within a campaign."""
    cycle_id: str
    records_produced: int
    suppressed_count: int
    live_effects_produced: int
    provider_dispatch_count: int
    attribution_complete: bool
    governance_scope: str
    rule_path_summary: str
    degraded: bool
    degradation_cause: Optional[str]


@dataclass
class AttributionCertResult:
    """Attribution continuity certification result."""
    total_records: int
    correlation_gaps: int = 0
    causation_gaps: int = 0
    replay_lineage_gaps: int = 0
    scope_continuity_gaps: int = 0
    total_attribution_gaps: int = 0
    certification_passed: bool = True


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


@dataclass
class ReplayCertResult:
    """Replay campaign certification result."""
    total_records: int
    replay_only_scope_count: int = 0
    historical_config_count: int = 0
    zero_live_effects: bool = True
    zero_provider_dispatches: bool = True
    fingerprint_consistent_count: int = 0
    fingerprint_violations: int = 0
    replay_leakage_count: int = 0
    certification_passed: bool = True


@dataclass
class DegradationRecord:
    """Record produced when a controlled failure is injected."""
    record_id: str
    failure_mode: str
    failure_classification: str
    governance_scope: str
    correlation_id: str
    causation_id: str
    degradation_state: str      # always "deterministic"
    attribution_preserved: bool  # always True
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
    deterministic_count: int = 0
    attribution_preserved_count: int = 0
    zero_live_effects_count: int = 0
    recovery_visible_count: int = 0
    certification_passed: bool = True


@dataclass
class LoadCampaignResult:
    """Load certification result at a specific volume."""
    volume: int
    attribution_complete_count: int = 0
    suppression_intact_count: int = 0
    replay_safe_count: int = 0
    inv_violations: int = 0
    fad_violations: int = 0
    live_effects_total: int = 0
    provider_dispatch_total: int = 0
    authorized_scope_count: int = 0
    certification_passed: bool = True


@dataclass
class GovernanceCertResult:
    """Continuous governance invariant certification result."""
    total_records: int
    inv1_violations: int = 0
    inv2_violations: int = 0
    inv3_violations: int = 0
    inv4_violations: int = 0
    inv5_violations: int = 0
    inv6_violations: int = 0
    inv7_violations: int = 0
    fad1_violations: int = 0
    fad2_violations: int = 0
    fad3_violations: int = 0
    fad4_violations: int = 0
    fad5_violations: int = 0
    fad6_violations: int = 0
    total_inv_violations: int = 0
    total_fad_violations: int = 0
    certification_passed: bool = True


@dataclass
class OperatorReport:
    """Certification report for operator review."""
    report_id: str
    campaign_id: str
    report_timestamp: str
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
    """Final campaign audit — all primary counters must be 0 to pass."""
    total_records: int
    provider_dispatch_count: int = 0
    live_effects_produced: int = 0
    attribution_gap_count: int = 0
    finalized_violation_count: int = 0
    replay_leakage_count: int = 0
    governance_invariant_violations: int = 0
    authorized_scope_count: int = 0
    degradation_deterministic_count: int = 0
    total_degradation_injections: int = 0
    audit_passed: bool = True
