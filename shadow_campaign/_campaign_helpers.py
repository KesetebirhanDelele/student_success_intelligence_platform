"""
Shadow Operational Campaign — pure helper functions.

All helpers: pure functions, no I/O, no DB, no HTTP.
"""
from __future__ import annotations
import uuid
from typing import List, Optional, Tuple

from ._campaign_types import (
    CampaignRecord, CampaignMetrics, AttributionCertResult, GovernanceCertResult,
    CampaignAuditResult,
    SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY, SCOPE_UNAVAILABLE, SCOPE_MAINTENANCE,
    SCOPE_BLOCKED, SCOPE_DUPLICATE_SUPPRESSED, SCOPE_AUTHORIZED,
    MODE_SHADOW, MODE_LIVE, TYPE_ORIGINAL, TYPE_REPLAY, TYPE_REGENERATION,
    UNKNOWN_V0, _SUPPRESSED_SCOPES, _REPLAY_TYPES,
    CAMPAIGN_STATUS_COMPLETE, CAMPAIGN_STATUS_DEGRADED,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _derive_scope(
    mode: str,
    exec_type: str,
    config_missing: bool = False,
    maintenance: bool = False,
    duplicate: bool = False,
) -> str:
    """Derive governance scope — same priority chain as the production governance layer."""
    if config_missing:
        return SCOPE_UNAVAILABLE
    if exec_type in _REPLAY_TYPES:
        return SCOPE_REPLAY_ONLY
    if maintenance:
        return SCOPE_MAINTENANCE
    if duplicate:
        return SCOPE_DUPLICATE_SUPPRESSED
    # Phase-12 cert gate: LIVE → SHADOW_ONLY until cert issued
    return SCOPE_SHADOW_ONLY


def _make_campaign_record(
    cycle_id: str,
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
    config_missing: bool = False,
    maintenance: bool = False,
    duplicate: bool = False,
    is_finalized: bool = False,
    source_artifact_id: Optional[str] = None,
    historical_config_version_id: Optional[str] = None,
    degraded: bool = False,
    degradation_cause: Optional[str] = None,
    degradation_class: Optional[str] = None,
    degradation_severity: Optional[str] = None,
) -> CampaignRecord:
    scope = _derive_scope(mode, exec_type, config_missing, maintenance, duplicate)
    config_ver = UNKNOWN_V0 if config_missing else "cfg-v2-001"
    is_replay_rec = exec_type in _REPLAY_TYPES

    reason_codes: List[str] = []
    if scope == SCOPE_UNAVAILABLE:
        reason_codes.append("CONFIG_VERSION_UNRESOLVED")
    elif scope == SCOPE_REPLAY_ONLY:
        reason_codes.append("REPLAY_EXECUTION_SUPPRESSED")
    elif scope == SCOPE_MAINTENANCE:
        reason_codes.append("MAINTENANCE_SCOPE_ACTIVE")
    elif scope == SCOPE_DUPLICATE_SUPPRESSED:
        reason_codes.append("DUPLICATE_SUPPRESSED")
    else:
        reason_codes.append("SHADOW_ONLY_SCOPE_ACTIVE")
        if mode == MODE_LIVE:
            reason_codes.append("LIVE_SCOPE_REQUIRES_PHASE12_CERT")

    rule_path = ["RULE_0"]
    if scope != SCOPE_UNAVAILABLE:
        rule_path += ["RULE_1", "RULE_2"]
    if exec_type in _REPLAY_TYPES:
        rule_path.append("RULE_3")

    content_hash = f"hash-{scope}-{config_ver}" if is_finalized else None
    hist_cfg = historical_config_version_id
    if exec_type in _REPLAY_TYPES and hist_cfg is None:
        hist_cfg = f"hist-cfg-v1-{_new_id()[:8]}"
    src_art = source_artifact_id or (f"src-{_new_id()[:8]}" if is_replay_rec else None)

    return CampaignRecord(
        record_id=_new_id(),
        cycle_id=cycle_id,
        execution_mode=mode,
        execution_type=exec_type,
        governance_scope=scope,
        correlation_id=_new_id(),
        causation_id=_new_id(),
        config_version_id=config_ver,
        orchestration_cycle_id=cycle_id,
        origin_source="shadow_campaign",
        origin_authority="campaign_runner",
        actor_identity="shadow_campaign_agent",
        rule_path=rule_path,
        reason_codes=reason_codes,
        outbound_suppressed=scope in _SUPPRESSED_SCOPES,
        live_effects_produced=0,
        provider_dispatch_count=0,
        is_replay=is_replay_rec,
        source_artifact_id=src_art,
        historical_config_version_id=hist_cfg,
        is_finalized=is_finalized,
        is_mutable=not is_finalized,
        mutation_prohibited=is_finalized,
        content_hash=content_hash,
        is_duplicate=duplicate,
        degraded=degraded,
        degradation_cause=degradation_cause,
        degradation_class=degradation_class,
        degradation_severity=degradation_severity,
        scheduler_processed=True,
        worker_processed=True,
        prioritization_complete=True,
        transport_generated=True,
        observability_emitted=True,
        provider_assessment_produced=True,
        inv1_scope_not_mutated=True,
        inv2_attribution_not_mutated=True,
        inv3_replay_no_live=True,
        inv4_shadow_no_dispatch=True,
        inv5_rule0_not_bypassed=True,
        inv6_correlation_present=True,
        inv7_exec_mode_present=True,
        fad1_finalized_not_mutated=True,
        fad2_attribution_immutable=True,
        fad3_deterministic=True,
        fad4_lineage_append_only=True,
        fad5_replay_historical_config=True,
        fad6_finalized_lineage_preserved=True,
    )


def _make_batch(
    cycle_id: str,
    count: int,
    mode: str = MODE_SHADOW,
    exec_type: str = TYPE_ORIGINAL,
) -> List[CampaignRecord]:
    return [_make_campaign_record(cycle_id, mode=mode, exec_type=exec_type) for _ in range(count)]


def _compute_metrics(
    campaign_id: str,
    records: List[CampaignRecord],
) -> CampaignMetrics:
    metrics = CampaignMetrics(
        campaign_id=campaign_id,
        campaign_status=CAMPAIGN_STATUS_COMPLETE,
    )
    for r in records:
        metrics.orchestration_count += 1
        if r.outbound_suppressed:
            metrics.suppression_count += 1
        if r.is_replay:
            metrics.replay_count += 1
        if r.degraded:
            metrics.degradation_count += 1
        if r.is_duplicate:
            metrics.duplicate_suppression_count += 1
        if r.config_version_id == UNKNOWN_V0:
            metrics.config_resolution_failures += 1
        if r.governance_scope in {SCOPE_SHADOW_ONLY, SCOPE_REPLAY_ONLY}:
            metrics.provider_suppression_count += 1
        if r.governance_scope == SCOPE_AUTHORIZED:
            metrics.authorized_scope_count += 1
        metrics.live_effects_total += r.live_effects_produced
        metrics.provider_dispatch_total += r.provider_dispatch_count

        inv_flags = [
            r.inv1_scope_not_mutated, r.inv2_attribution_not_mutated,
            r.inv3_replay_no_live, r.inv4_shadow_no_dispatch,
            r.inv5_rule0_not_bypassed, r.inv6_correlation_present,
            r.inv7_exec_mode_present,
        ]
        fad_flags = [
            r.fad1_finalized_not_mutated, r.fad2_attribution_immutable,
            r.fad3_deterministic, r.fad4_lineage_append_only,
            r.fad5_replay_historical_config, r.fad6_finalized_lineage_preserved,
        ]
        metrics.inv_violation_count += sum(1 for f in inv_flags if not f)
        metrics.fad_violation_count += sum(1 for f in fad_flags if not f)

        if r.governance_scope == SCOPE_REPLAY_ONLY and r.live_effects_produced > 0:
            metrics.replay_leakage_count += 1

    if metrics.degradation_count > 0:
        metrics.campaign_status = CAMPAIGN_STATUS_DEGRADED

    return metrics


def _certify_attribution(records: List[CampaignRecord]) -> AttributionCertResult:
    corr_gaps = sum(1 for r in records if not r.correlation_id)
    caus_gaps = sum(1 for r in records if not r.causation_id)
    replay_gaps = sum(
        1 for r in records if r.is_replay and not r.historical_config_version_id
    )
    scope_gaps = sum(1 for r in records if not r.governance_scope)
    total = corr_gaps + caus_gaps + replay_gaps + scope_gaps
    return AttributionCertResult(
        total_records=len(records),
        correlation_gaps=corr_gaps,
        causation_gaps=caus_gaps,
        replay_lineage_gaps=replay_gaps,
        scope_continuity_gaps=scope_gaps,
        total_attribution_gaps=total,
        certification_passed=total == 0,
    )


def _certify_governance(records: List[CampaignRecord]) -> GovernanceCertResult:
    result = GovernanceCertResult(total_records=len(records))
    for r in records:
        if not r.inv1_scope_not_mutated:         result.inv1_violations += 1
        if not r.inv2_attribution_not_mutated:   result.inv2_violations += 1
        if not r.inv3_replay_no_live:            result.inv3_violations += 1
        if not r.inv4_shadow_no_dispatch:        result.inv4_violations += 1
        if not r.inv5_rule0_not_bypassed:        result.inv5_violations += 1
        if not r.inv6_correlation_present:       result.inv6_violations += 1
        if not r.inv7_exec_mode_present:         result.inv7_violations += 1
        if not r.fad1_finalized_not_mutated:     result.fad1_violations += 1
        if not r.fad2_attribution_immutable:     result.fad2_violations += 1
        if not r.fad3_deterministic:             result.fad3_violations += 1
        if not r.fad4_lineage_append_only:       result.fad4_violations += 1
        if not r.fad5_replay_historical_config:  result.fad5_violations += 1
        if not r.fad6_finalized_lineage_preserved: result.fad6_violations += 1

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


def _audit_campaign_records(records: List[CampaignRecord]) -> CampaignAuditResult:
    dispatch_total = sum(r.provider_dispatch_count for r in records)
    effects_total = sum(r.live_effects_produced for r in records)
    attr_gaps = sum(1 for r in records if not r.correlation_id or not r.causation_id)
    fin_violations = sum(1 for r in records if r.is_finalized and r.is_mutable)
    replay_leakage = sum(
        1 for r in records
        if r.governance_scope == SCOPE_REPLAY_ONLY and r.live_effects_produced > 0
    )
    gov_cert = _certify_governance(records)
    gov_violations = gov_cert.total_inv_violations + gov_cert.total_fad_violations
    auth_count = sum(1 for r in records if r.governance_scope == SCOPE_AUTHORIZED)

    audit_passed = (
        dispatch_total == 0
        and effects_total == 0
        and attr_gaps == 0
        and fin_violations == 0
        and replay_leakage == 0
        and gov_violations == 0
        and auth_count == 0
    )
    return CampaignAuditResult(
        total_records=len(records),
        provider_dispatch_count=dispatch_total,
        live_effects_produced=effects_total,
        attribution_gap_count=attr_gaps,
        finalized_violation_count=fin_violations,
        replay_leakage_count=replay_leakage,
        governance_invariant_violations=gov_violations,
        authorized_scope_count=auth_count,
        audit_passed=audit_passed,
    )
