"""
Shadow Operational Campaign — Governance Certifier.

Continuously verifies INV-1 through INV-7 and FAD-1 through FAD-6
during operational execution.
"""
from __future__ import annotations
from typing import List

from ._campaign_types import (
    CampaignRecord, GovernanceCertResult,
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_AUTHORIZED,
    _SUPPRESSED_SCOPES, _REPLAY_TYPES,
)
from ._campaign_helpers import _certify_governance


def verify_inv1_scope_not_mutated(records: List[CampaignRecord]) -> int:
    return sum(1 for r in records if not r.inv1_scope_not_mutated)


def verify_inv2_attribution_not_mutated(records: List[CampaignRecord]) -> int:
    return sum(1 for r in records if not r.inv2_attribution_not_mutated)


def verify_inv3_replay_no_live(records: List[CampaignRecord]) -> int:
    return sum(
        1 for r in records
        if r.execution_type in _REPLAY_TYPES and r.live_effects_produced > 0
    )


def verify_inv4_shadow_no_dispatch(records: List[CampaignRecord]) -> int:
    return sum(
        1 for r in records
        if r.governance_scope == SCOPE_SHADOW_ONLY and r.provider_dispatch_count > 0
    )


def verify_inv5_rule0_first(records: List[CampaignRecord]) -> int:
    return sum(
        1 for r in records
        if not r.rule_path or r.rule_path[0] != "RULE_0"
    )


def verify_inv6_correlation_present(records: List[CampaignRecord]) -> int:
    return sum(1 for r in records if not r.correlation_id)


def verify_inv7_exec_mode_present(records: List[CampaignRecord]) -> int:
    return sum(1 for r in records if not r.execution_mode)


def verify_fad1_finalized_not_mutated(records: List[CampaignRecord]) -> int:
    return sum(1 for r in records if r.is_finalized and r.is_mutable)


def verify_fad5_replay_historical_config(records: List[CampaignRecord]) -> int:
    return sum(
        1 for r in records
        if r.execution_type in _REPLAY_TYPES and not r.historical_config_version_id
    )


def run_governance_certification(records: List[CampaignRecord]) -> GovernanceCertResult:
    """Run full INV-1–INV-7 + FAD-1–FAD-6 certification over campaign records."""
    result = _certify_governance(records)
    # Augment with explicit invariant checks
    result.inv3_violations = max(result.inv3_violations, verify_inv3_replay_no_live(records))
    result.inv4_violations = max(result.inv4_violations, verify_inv4_shadow_no_dispatch(records))
    result.inv5_violations = max(result.inv5_violations, verify_inv5_rule0_first(records))
    result.inv6_violations = max(result.inv6_violations, verify_inv6_correlation_present(records))
    result.fad1_violations = max(result.fad1_violations, verify_fad1_finalized_not_mutated(records))
    result.fad5_violations = max(result.fad5_violations, verify_fad5_replay_historical_config(records))
    result.total_inv_violations = (
        result.inv1_violations + result.inv2_violations + result.inv3_violations
        + result.inv4_violations + result.inv5_violations + result.inv6_violations
        + result.inv7_violations
    )
    result.total_fad_violations = (
        result.fad1_violations + result.fad2_violations + result.fad3_violations
        + result.fad4_violations + result.fad5_violations + result.fad6_violations
    )
    result.certification_passed = (
        result.total_inv_violations == 0 and result.total_fad_violations == 0
    )
    return result
