"""
Shadow Operational Campaign Runner.

Orchestrates shadow campaign cycles: scheduler ticks, worker cycles,
orchestration decisions, prioritization, provider assessments,
transport generation, reporting, and observability.

All outbound effects remain suppressed:
  live_effects_produced = 0
  provider_dispatch_count = 0

SHADOW containment is never removed. AUTHORIZED scope is never enabled.
"""
from __future__ import annotations
from typing import List, Optional, Tuple

from ._campaign_types import (
    CampaignRecord, CampaignMetrics, CampaignCycleResult,
    MODE_SHADOW, TYPE_ORIGINAL, TYPE_REPLAY, CAMPAIGN_STATUS_COMPLETE,
)
from ._campaign_helpers import (
    _new_id, _make_campaign_record, _compute_metrics, _certify_attribution,
)


def run_campaign_cycle(
    cycle_id: Optional[str] = None,
    mode: str = MODE_SHADOW,
    count: int = 10,
    include_replay: bool = False,
    include_finalized: bool = False,
    config_missing: bool = False,
) -> Tuple[CampaignCycleResult, List[CampaignRecord]]:
    """Run a single shadow campaign orchestration cycle.

    Simulates: scheduler tick → worker assignment → orchestration decision
    → prioritization → provider assessment → transport generation → observability.
    All stages operate under SHADOW containment.
    """
    cid = cycle_id or _new_id()
    records: List[CampaignRecord] = []

    for _ in range(count):
        records.append(_make_campaign_record(
            cid, mode=mode, exec_type=TYPE_ORIGINAL,
            config_missing=config_missing,
        ))

    if include_replay:
        replay_count = max(1, count // 10)
        for _ in range(replay_count):
            records.append(_make_campaign_record(
                cid, mode=mode, exec_type=TYPE_REPLAY,
                historical_config_version_id=f"hist-cfg-{_new_id()[:8]}",
                source_artifact_id=f"src-{_new_id()[:8]}",
            ))

    if include_finalized:
        records.append(_make_campaign_record(cid, mode=mode, is_finalized=True))

    suppressed = sum(1 for r in records if r.outbound_suppressed)
    effects = sum(r.live_effects_produced for r in records)
    dispatches = sum(r.provider_dispatch_count for r in records)
    attr_ok = all(r.correlation_id and r.causation_id for r in records)
    first_scope = records[0].governance_scope if records else "UNKNOWN"
    first_rule = records[0].rule_path[0] if records and records[0].rule_path else "UNKNOWN"

    result = CampaignCycleResult(
        cycle_id=cid,
        records_produced=len(records),
        suppressed_count=suppressed,
        live_effects_produced=effects,
        provider_dispatch_count=dispatches,
        attribution_complete=attr_ok,
        governance_scope=first_scope,
        rule_path_summary=first_rule,
        degraded=config_missing,
        degradation_cause="CONFIG_V2_UNAVAILABLE" if config_missing else None,
    )
    return result, records


def run_full_campaign(
    campaign_id: Optional[str] = None,
    cycles: int = 3,
    mode: str = MODE_SHADOW,
    count_per_cycle: int = 10,
) -> Tuple[CampaignMetrics, List[CampaignRecord]]:
    """Run a full shadow campaign across multiple orchestration cycles.

    Each cycle: scheduler tick → worker → orchestration → provider assessment.
    Every third cycle includes a replay slice.
    """
    cid = campaign_id or _new_id()
    all_records: List[CampaignRecord] = []

    for i in range(cycles):
        cycle_id = f"cycle-{i + 1}-{_new_id()[:8]}"
        _, records = run_campaign_cycle(
            cycle_id=cycle_id,
            mode=mode,
            count=count_per_cycle,
            include_replay=(i % 3 == 0),
        )
        all_records.extend(records)

    metrics = _compute_metrics(cid, all_records)
    return metrics, all_records


def run_load_campaign(
    campaign_id: Optional[str] = None,
    volume: int = 100,
    mode: str = MODE_SHADOW,
) -> Tuple[CampaignMetrics, List[CampaignRecord]]:
    """Run a load certification campaign at a specific record volume."""
    cid = campaign_id or _new_id()
    cycle_id = f"load-cycle-{_new_id()[:8]}"
    records: List[CampaignRecord] = []

    replay_count = max(1, volume // 10)
    original_count = volume - replay_count

    for _ in range(original_count):
        records.append(_make_campaign_record(cycle_id, mode=mode, exec_type=TYPE_ORIGINAL))
    for _ in range(replay_count):
        records.append(_make_campaign_record(
            cycle_id, mode=mode, exec_type=TYPE_REPLAY,
            historical_config_version_id=f"hist-cfg-{_new_id()[:8]}",
            source_artifact_id=f"src-{_new_id()[:8]}",
        ))

    metrics = _compute_metrics(cid, records)
    return metrics, records
