"""
Shadow Operational Campaign — Operator Report Generator.

Generates certification reports showing campaign duration, volumes,
violations, and certification outcome for operator review.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from ._campaign_types import (
    CampaignMetrics, CampaignAuditResult, OperatorReport,
    CERT_OUTCOME_PASSED, CERT_OUTCOME_FAILED, CERT_OUTCOME_DEGRADED,
)


def generate_operator_report(
    campaign_id: str,
    metrics: CampaignMetrics,
    audit_result: CampaignAuditResult,
    duration_seconds: float = 0.0,
) -> OperatorReport:
    """Generate a certification report for operator review."""
    total_violations = metrics.inv_violation_count + metrics.fad_violation_count

    cert_passed = (
        audit_result.audit_passed
        and total_violations == 0
        and metrics.live_effects_total == 0
        and metrics.provider_dispatch_total == 0
        and metrics.authorized_scope_count == 0
    )

    if cert_passed:
        outcome = CERT_OUTCOME_PASSED
    elif not audit_result.audit_passed:
        outcome = CERT_OUTCOME_FAILED
    else:
        outcome = CERT_OUTCOME_DEGRADED

    return OperatorReport(
        report_id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        report_timestamp=datetime.now(timezone.utc).isoformat(),
        campaign_duration_seconds=duration_seconds,
        orchestration_volume=metrics.orchestration_count,
        suppression_volume=metrics.suppression_count,
        replay_volume=metrics.replay_count,
        degradation_events=metrics.degradation_count,
        inv_violations=metrics.inv_violation_count,
        fad_violations=metrics.fad_violation_count,
        live_effects_total=metrics.live_effects_total,
        provider_dispatch_total=metrics.provider_dispatch_total,
        authorized_scope_count=metrics.authorized_scope_count,
        attribution_gap_count=metrics.attribution_gap_count,
        replay_leakage_count=metrics.replay_leakage_count,
        governance_invariant_violations=total_violations,
        certification_outcome=outcome,
        certification_passed=cert_passed,
    )


def format_report_summary(report: OperatorReport) -> str:
    """Format a one-line human-readable report summary for operator output."""
    return (
        f"Campaign {report.campaign_id[:8]}... | "
        f"Orchestration: {report.orchestration_volume} | "
        f"Suppressed: {report.suppression_volume} | "
        f"Replays: {report.replay_volume} | "
        f"Degradations: {report.degradation_events} | "
        f"Live effects: {report.live_effects_total} | "
        f"Dispatches: {report.provider_dispatch_total} | "
        f"INV violations: {report.inv_violations} | "
        f"FAD violations: {report.fad_violations} | "
        f"Outcome: {report.certification_outcome}"
    )
