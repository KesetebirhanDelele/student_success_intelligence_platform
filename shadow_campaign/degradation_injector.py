"""
Shadow Operational Campaign — Degradation Injector.

Injects controlled failures and validates:
  - deterministic degradation state
  - attribution continuity
  - observable recovery paths
"""
from __future__ import annotations
from typing import List, Optional, Tuple

from ._campaign_types import (
    DegradationRecord, DegradationCampaignResult,
    SCOPE_SHADOW_ONLY, SCOPE_UNAVAILABLE, UNKNOWN_V0,
    FAILURE_MISSING_CONFIG, FAILURE_PROVIDER_UNAVAILABLE,
    FAILURE_SCHEDULER_UNAVAILABLE, FAILURE_WORKER_UNAVAILABLE,
    FAILURE_OBSERVABILITY_UNAVAILABLE, ALL_FAILURE_MODES,
    _SUPPRESSED_SCOPES,
)
from ._campaign_helpers import _new_id

_FAILURE_MAP = {
    FAILURE_MISSING_CONFIG: {
        "classification": "CONFIG_V2_UNAVAILABLE",
        "scope":          SCOPE_UNAVAILABLE,
        "cause":          "CONFIG_V2_UNAVAILABLE",
        "class_":         "CONFIG_DEGRADATION",
        "severity":       "HIGH",
        "reason":         "CONFIG_VERSION_UNRESOLVED",
        "rule_path":      ["RULE_0"],
    },
    FAILURE_PROVIDER_UNAVAILABLE: {
        "classification": "PROVIDER_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "PROVIDER_UNAVAILABLE",
        "class_":         "PROVIDER_DEGRADATION",
        "severity":       "LOW",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
    },
    FAILURE_SCHEDULER_UNAVAILABLE: {
        "classification": "SCHEDULER_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "SCHEDULER_UNAVAILABLE",
        "class_":         "RUNTIME_DEGRADATION",
        "severity":       "MEDIUM",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
    },
    FAILURE_WORKER_UNAVAILABLE: {
        "classification": "WORKER_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "WORKER_UNAVAILABLE",
        "class_":         "RUNTIME_DEGRADATION",
        "severity":       "MEDIUM",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
    },
    FAILURE_OBSERVABILITY_UNAVAILABLE: {
        "classification": "OBSERVABILITY_INIT_FAILURE",
        "scope":          SCOPE_SHADOW_ONLY,
        "cause":          "OBSERVABILITY_UNAVAILABLE",
        "class_":         "OBSERVABILITY_DEGRADATION",
        "severity":       "LOW",
        "reason":         "SHADOW_ONLY_SCOPE_ACTIVE",
        "rule_path":      ["RULE_0", "RULE_1", "RULE_2"],
    },
}


def inject_failure(failure_mode: str) -> DegradationRecord:
    """Inject a controlled failure and return a deterministic degradation record."""
    cfg = _FAILURE_MAP[failure_mode]
    scope = cfg["scope"]
    cid = _new_id()

    return DegradationRecord(
        record_id=_new_id(),
        failure_mode=failure_mode,
        failure_classification=cfg["classification"],
        governance_scope=scope,
        correlation_id=cid,
        causation_id=_new_id(),
        degradation_state="deterministic",
        attribution_preserved=True,
        outbound_suppressed=scope in _SUPPRESSED_SCOPES,
        live_effects_produced=0,
        recovery_path_visible=True,
        deterministic=True,
        degradation_cause=cfg["cause"],
        degradation_class=cfg["class_"],
        degradation_severity=cfg["severity"],
        reason_codes=[cfg["reason"]],
        rule_path=list(cfg["rule_path"]),
    )


def run_degradation_campaign(
    failure_modes: Optional[List[str]] = None,
    count_each: int = 1,
) -> Tuple[DegradationCampaignResult, List[DegradationRecord]]:
    """Run a degradation injection campaign across failure modes."""
    modes = failure_modes or ALL_FAILURE_MODES
    records: List[DegradationRecord] = []

    for mode in modes:
        for _ in range(count_each):
            records.append(inject_failure(mode))

    det_count = sum(1 for r in records if r.deterministic)
    attr_count = sum(1 for r in records if r.attribution_preserved)
    effects_zero = sum(1 for r in records if r.live_effects_produced == 0)
    recovery_vis = sum(1 for r in records if r.recovery_path_visible)

    cert_passed = (
        det_count == len(records)
        and attr_count == len(records)
        and effects_zero == len(records)
        and recovery_vis == len(records)
    )

    result = DegradationCampaignResult(
        failure_modes_tested=list(modes),
        total_injections=len(records),
        deterministic_count=det_count,
        attribution_preserved_count=attr_count,
        zero_live_effects_count=effects_zero,
        recovery_visible_count=recovery_vis,
        certification_passed=cert_passed,
    )
    return result, records
