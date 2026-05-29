"""
Shadow Operational Campaign — Attribution Certifier.

Continuously validates:
  - correlation continuity
  - causation continuity
  - replay lineage continuity
  - governance scope continuity

Raises observable certification failures on any violation.
"""
from __future__ import annotations
from typing import List, Tuple

from ._campaign_types import CampaignRecord, AttributionCertResult
from ._campaign_helpers import _certify_attribution


def certify_correlation_continuity(records: List[CampaignRecord]) -> Tuple[bool, int]:
    """Returns (passed, gap_count) for correlation_id presence."""
    gaps = sum(1 for r in records if not r.correlation_id)
    return gaps == 0, gaps


def certify_causation_continuity(records: List[CampaignRecord]) -> Tuple[bool, int]:
    """Returns (passed, gap_count) for causation_id presence."""
    gaps = sum(1 for r in records if not r.causation_id)
    return gaps == 0, gaps


def certify_replay_lineage(records: List[CampaignRecord]) -> Tuple[bool, int]:
    """Returns (passed, gap_count) for replay lineage completeness."""
    gaps = sum(
        1 for r in records
        if r.is_replay and not r.historical_config_version_id
    )
    return gaps == 0, gaps


def certify_scope_continuity(records: List[CampaignRecord]) -> Tuple[bool, int]:
    """Returns (passed, gap_count) for governance_scope presence."""
    gaps = sum(1 for r in records if not r.governance_scope)
    return gaps == 0, gaps


def emit_attribution_failure(
    failure_type: str,
    gap_count: int,
    record_count: int,
) -> dict:
    """Produce an observable certification failure record."""
    return {
        "event": "ATTRIBUTION_CERTIFICATION_FAILURE",
        "failure_type": failure_type,
        "gap_count": gap_count,
        "record_count": record_count,
        "certification_passed": False,
    }


def run_attribution_certification(records: List[CampaignRecord]) -> AttributionCertResult:
    """Run full attribution continuity certification across a set of records."""
    return _certify_attribution(records)
