"""Shadow Operational Campaign framework — SHADOW containment enforced."""
from .campaign_runner import run_campaign_cycle, run_full_campaign, run_load_campaign
from .attribution_certifier import (
    run_attribution_certification,
    certify_correlation_continuity,
    certify_causation_continuity,
    certify_replay_lineage,
    certify_scope_continuity,
)
from .replay_certifier import run_replay_campaign, make_replay_record
from .degradation_injector import run_degradation_campaign, inject_failure
from .governance_certifier import run_governance_certification
from .operator_report import generate_operator_report, format_report_summary
from ._campaign_types import (
    CampaignRecord, CampaignMetrics, CampaignCycleResult,
    AttributionCertResult, ReplayCampaignRecord, ReplayCertResult,
    DegradationRecord, DegradationCampaignResult, LoadCampaignResult,
    GovernanceCertResult, OperatorReport, CampaignAuditResult,
    ALL_FAILURE_MODES,
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE,
    SCOPE_AUTHORIZED, MODE_SHADOW, MODE_LIVE, UNKNOWN_V0,
    CERT_OUTCOME_PASSED, CERT_OUTCOME_FAILED, CERT_OUTCOME_DEGRADED,
)

__all__ = [
    "run_campaign_cycle",
    "run_full_campaign",
    "run_load_campaign",
    "run_attribution_certification",
    "certify_correlation_continuity",
    "certify_causation_continuity",
    "certify_replay_lineage",
    "certify_scope_continuity",
    "run_replay_campaign",
    "make_replay_record",
    "run_degradation_campaign",
    "inject_failure",
    "run_governance_certification",
    "generate_operator_report",
    "format_report_summary",
    "CampaignRecord",
    "CampaignMetrics",
    "CampaignCycleResult",
    "AttributionCertResult",
    "ReplayCampaignRecord",
    "ReplayCertResult",
    "DegradationRecord",
    "DegradationCampaignResult",
    "LoadCampaignResult",
    "GovernanceCertResult",
    "OperatorReport",
    "CampaignAuditResult",
    "ALL_FAILURE_MODES",
    "SCOPE_SHADOW_ONLY",
    "SCOPE_REPLAY_ONLY",
    "SCOPE_UNAVAILABLE",
    "SCOPE_AUTHORIZED",
    "MODE_SHADOW",
    "MODE_LIVE",
    "UNKNOWN_V0",
    "CERT_OUTCOME_PASSED",
    "CERT_OUTCOME_FAILED",
    "CERT_OUTCOME_DEGRADED",
]
