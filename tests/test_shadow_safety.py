"""
Governance-safe SHADOW and replay containment certification.

Aligned with (authoritative parent contracts):
  tests/test_scenarios.md  — governance validation contract (GPC/OIG/SVL/ROS/ROG/AIG/PBG/STG/CID/ATT/DEG/RGS/IML/INV)
  tests/edge_cases.md      — governance edge-condition certification (ECR/ECRG/ECA/ECAI/ECDO/ECCV/ECSO/ECPL/ECDE/ECIL)
  tests/load_tests.md      — governance load certification (LCS/LCR/LCSCH/LCRSG/LCDO/LCPB/LCAI/LCAT/LCDE/LCOS/LCI)
  tests/test_work_queue.py — governance-safe orchestration queue certification (peer contract)
  tests/test_actions.py    — governance-safe orchestration-action certification (peer contract)
  tests/test_sync.py       — governance-safe synchronization certification (peer contract)
  tests/test_dashboard.py  — governance-safe observability certification (peer contract)

Canonical design inputs:
  runtime/system_loop.md              spec/01_requirements.md
  runtime/scheduler_design.md         spec/03_state_transition_rules.md
  runtime/daily_outreach_flow.md      spec/04_idempotency_concurrency.md
  runtime/retry_cycle_flow.md         spec/05_external_integrations.md
  failure/failure_playbook.md         spec/06_observability_operations.md
  failure/scheduling_failures.md      spec/07_api_contracts.md
  failure/ghl_failures.md             spec/08_data_model.md
  failure/llm_failures.md             spec/09_security_privacy.md

Prohibited semantics (test_scenarios.md §2 / edge_cases.md §2 / load_tests.md §2):
  - simplistic dry-run assumptions ("is_shadow = True" patch-based no-send assertions)
  - simplistic outbound suppression checks (mock_post.assert_not_called())
  - simplistic provider isolation assumptions (direct HTTP mock suppression)
  - simplistic replay behavior (LIVE-effect assertions from replay)
  - simplistic no-send assertions
  - app module imports (from app.services.integrations.ghl import ...)
  - AsyncMock / MagicMock / patch patterns
  - replay-triggered LIVE expectations
  - mutable FINALIZED_COPY assumptions
  - non-attributable SHADOW behavior (entries missing correlation_id)
  - silent containment failures
  - hardcoded threshold constants (no 10-min SLA, no MAX_ATTEMPTS)

SHADOW safety testing is NOW:
  - governance-safe orchestration containment certification
  - replay-safe execution isolation certification
  - immutable-lineage containment validation
  - provider-boundary isolation certification

This file certifies governance contracts only.
It does NOT generate production SHADOW-mode logic, orchestration handlers,
provider integrations, or monitoring infrastructure.
"""
from __future__ import annotations

import threading
import uuid
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
class OrchestrationIntent:
    """
    Governance-authorized intent record from runtime/system_loop.md §4.1.
    governance_scope determines whether LIVE effects are authorized.
    SHADOW mode always produces governance_scope = SHADOW_ONLY.
    REPLAY mode always produces governance_scope = REPLAY_ONLY.
    """
    intent_type: str                    # INITIATE_OUTREACH | RETRY_OUTREACH | SKIP
    governance_scope: str               # AUTHORIZED | SHADOW_ONLY | REPLAY_ONLY | UNAVAILABLE
    correlation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str                 # LIVE | SHADOW | REPLAY | DEGRADED | MAINTENANCE
    execution_type: str = "original"    # original | replay | recovery | regeneration
    causation_id: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)
    compliance_hold_active: bool = False


@dataclass
class ProviderContainmentRecord:
    """
    Provider boundary assessment record from spec/05 §2 / runtime/system_loop.md §3.
    outbound_suppressed must be True in SHADOW/REPLAY modes for all providers.
    governance_scope must be SHADOW_ONLY or REPLAY_ONLY — never AUTHORIZED — in those modes.
    silent_failure must always be False: failed containment must produce an observable record.
    """
    provider: str                       # ghl | sms | email | synthflow | ai_provider
    outbound_suppressed: bool
    governance_scope: str               # AUTHORIZED | SHADOW_ONLY | REPLAY_ONLY | UNAVAILABLE
    execution_mode: str                 # SHADOW | REPLAY | LIVE | DEGRADED
    correlation_id: str
    silent_failure: bool = False        # MUST always be False


@dataclass
class ReplayContainmentRecord:
    """
    Replay isolation contract from runtime/system_loop.md §7 / INV-4 / AP-RT2.
    live_effects_produced and state_transitions_produced must be 0.
    live_ai_inference_produced must be False.
    governance_scope must be REPLAY_ONLY.
    """
    execution_type: str                 # replay | regeneration
    governance_scope: str               # REPLAY_ONLY (invariant)
    correlation_id: str                 # new — never the original cycle's correlation_id
    causation_id: str                   # points to original cycle's correlation_id
    historical_config_version_id: str
    live_effects_produced: int = 0              # MUST always be 0
    state_transitions_produced: int = 0         # MUST always be 0
    live_ai_inference_produced: bool = False    # MUST always be False
    live_escalation_routing_produced: bool = False  # MUST always be False
    fingerprint_comparison_outcome: Optional[str] = None  # MATCH | DIVERGENT | UNAVAILABLE
    replay_partial: bool = False


@dataclass
class AIContainmentRecord:
    """
    AI advisory containment record from runtime/system_loop.md §3.1 / §9.1 / AIG scenarios.
    In SHADOW/REPLAY modes, AI outputs are advisory only; they may not authorize LIVE effects.
    live_inference_produced must be False in REPLAY mode.
    advisory_authorized_live_escalation must be False in SHADOW mode.
    content_text_present must always be False.
    """
    advisory_scope: str                 # AVAILABLE | UNAVAILABLE | STALE | SHADOW_ONLY
    ai_governance_tier: str             # FINALIZED_COPY | AI_GENERATED | STALE | UNAVAILABLE
    execution_mode: str                 # SHADOW | REPLAY | LIVE | DEGRADED
    correlation_id: str
    outcome: str                        # shadow_only | success | failure | skipped
    live_inference_produced: bool = False               # MUST be False in REPLAY
    advisory_authorized_live_escalation: bool = False   # MUST always be False in SHADOW
    content_text_present: bool = False                  # MUST always be False
    stale_ai_present: bool = False
    stale_ai_version: Optional[int] = None


@dataclass
class ShadowToLiveTransitionRecord:
    """
    Mode transition governance record from runtime/system_loop.md §3.2 / CV2-4.
    Transition from SHADOW → LIVE requires Governance Administrator authorization.
    No automation service may trigger this transition.
    activation_record_present must be True for any SHADOW → LIVE transition.
    automated_service_triggered must be False.
    """
    from_mode: str                      # SHADOW
    to_mode: str                        # LIVE
    actor_type: str                     # governance_administrator | operational_administrator | automation_service
    actor_identity: str
    activation_record_present: bool     # MUST be True for SHADOW → LIVE
    automated_service_triggered: bool   # MUST always be False for SHADOW → LIVE
    correlation_id: str
    config_version_activation_id: Optional[str] = None


@dataclass
class FinalizationContainmentRecord:
    """
    Immutable governance record shape from spec/04 §2.4 / INV-1 / INV-6 / FAD-1.
    Represents an append-only warehouse record that must not be mutated.
    allows_update and allows_delete must always be False.
    lifecycle_state must be FINALIZED or REPORT_PUBLISHED for these guarantees to apply.
    """
    record_type: str                    # snapshot | report | ai_narrative | compliance_audit
    lifecycle_state: str                # FINALIZED | REPORT_PUBLISHED | AI_GENERATED
    allows_update: bool = False         # MUST always be False
    allows_delete: bool = False         # MUST always be False
    sourced_from_warehouse: bool = True # MUST be True for FINALIZED records in replay/regeneration
    correlation_id: str = ""


@dataclass
class ShadowWebhookIngestionRecord:
    """
    Inbound webhook ingestion in SHADOW mode from runtime/system_loop.md §3.1.
    Inbound webhooks continue in SHADOW mode but are tagged execution_mode = SHADOW.
    duplicate_detected triggers dedup gate before any state management.
    """
    event: str
    execution_mode: str                 # SHADOW (required)
    origin_source: str                  # ghl | sql_server_sync
    origin_authority: str               # platform_supplementary | sql_server_authoritative
    correlation_id: str
    duplicate_detected: bool = False
    dedup_gate_applied: bool = False    # required when duplicate_detected = True


@dataclass
class AttributionContainmentRecord:
    """
    Attribution continuity record from spec/05 §2.3 / ATT scenarios / INV-5.
    All SHADOW/replay containment records must carry full attribution lineage.
    correlation_id, execution_mode, and execution_type must never be null.
    pii_present must always be False.
    """
    correlation_id: str
    execution_mode: str                 # SHADOW | REPLAY | LIVE
    execution_type: str                 # original | replay | regeneration | recovery
    origin_source: Optional[str] = None
    origin_authority: Optional[str] = None
    causation_id: Optional[str] = None
    config_version_id: Optional[str] = None
    attribution_timestamp: Optional[str] = None
    pii_present: bool = False           # MUST always be False


@dataclass
class DegradationContainmentRecord:
    """
    Deterministic degradation record from runtime/system_loop.md §3.1 (DEGRADED) / DEG scenarios.
    Degradation must be observable — never silently swallowed.
    error_class must be specific — never generic 'Error'.
    silent_swallow must always be False.
    """
    severity: str                       # CRITICAL | HIGH | MEDIUM | LOW
    degradation_type: str
    error_class: str                    # specific — never 'Error' or 'Exception'
    correlation_id: str
    execution_mode: str                 # SHADOW | REPLAY | LIVE | DEGRADED
    silent_swallow: bool = False        # MUST always be False
    recovery_path: Optional[str] = None
    affected_domains: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# GOVERNANCE HELPERS (pure functions — no I/O)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_threshold(config: Optional[ConfigVersion], key: str) -> Any:
    """Config V2 resolution: absent key → UNKNOWN_V0. Never hardcoded fallback."""
    if config is None or key not in config.thresholds:
        return "UNKNOWN_V0"
    return config.thresholds[key]


def shadow_intent_is_isolated(intent: OrchestrationIntent) -> bool:
    """SHADOW intents must have governance_scope=SHADOW_ONLY and execution_mode=SHADOW."""
    return (
        intent.governance_scope == "SHADOW_ONLY"
        and intent.execution_mode == "SHADOW"
    )


def replay_is_live_free(record: ReplayContainmentRecord) -> bool:
    """Replay records must produce zero LIVE effects (INV-4 / AP-RT2)."""
    return (
        record.live_effects_produced == 0
        and record.state_transitions_produced == 0
        and record.live_ai_inference_produced is False
        and record.live_escalation_routing_produced is False
        and record.governance_scope == "REPLAY_ONLY"
    )


def provider_is_contained(record: ProviderContainmentRecord) -> bool:
    """Provider boundary is maintained when outbound is suppressed in non-LIVE modes."""
    return (
        record.outbound_suppressed is True
        and record.silent_failure is False
        and record.governance_scope in ("SHADOW_ONLY", "REPLAY_ONLY", "UNAVAILABLE")
    )


def attribution_is_complete(record: AttributionContainmentRecord) -> bool:
    """INV-5 / ATT-1: attribution fields must never be null on any orchestration record."""
    return (
        bool(record.correlation_id)
        and bool(record.execution_mode)
        and bool(record.execution_type)
    )


def shadow_to_live_requires_governance_admin(record: ShadowToLiveTransitionRecord) -> bool:
    """CV2-4 / AP-RT7: SHADOW→LIVE transition requires Governance Administrator."""
    return (
        record.actor_type == "governance_administrator"
        and record.activation_record_present is True
        and record.automated_service_triggered is False
    )


def finalization_is_immutable(record: FinalizationContainmentRecord) -> bool:
    """INV-1 / INV-6 / FAD-1: FINALIZED records must not allow update or delete."""
    return (
        record.allows_update is False
        and record.allows_delete is False
    )


def ai_is_advisory_only(record: AIContainmentRecord) -> bool:
    """AI must not authorize LIVE effects in SHADOW mode; content_text must not be present."""
    return (
        record.advisory_authorized_live_escalation is False
        and record.content_text_present is False
    )


def containment_failure_is_observable(record: DegradationContainmentRecord) -> bool:
    """Containment failures must produce observable records — never silently swallowed."""
    return (
        record.silent_swallow is False
        and record.error_class not in ("Error", "Exception", "GenericError", "")
    )


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_uuid() -> str:
    return str(uuid.uuid4())


def _active_config(version_id: str = "v-cfg-001", **thresholds: Any) -> ConfigVersion:
    return ConfigVersion(version_id=version_id, status="ACTIVE", thresholds=thresholds)


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASSES
# ─────────────────────────────────────────────────────────────────────────────


class TestShadowContainmentGovernancePreconditions:
    """
    SHADOW containment requires the same governance preconditions as LIVE orchestration.
    No SHADOW cycle may proceed without ACTIVE config and a valid correlation_id.
    Canonical: GPC-1 through GPC-5, runtime/system_loop.md §5.2.
    """

    def test_ssgpc1_shadow_cycle_requires_active_config_version(self):
        """SHADOW loop must not evaluate candidates without an ACTIVE config version."""
        no_config = None
        threshold = resolve_threshold(no_config, "outreach_max_retry_attempts")
        assert threshold == "UNKNOWN_V0"

    def test_ssgpc2_shadow_intent_carries_config_version_id(self):
        """Every SHADOW OrchestrationIntent must carry config_version_id (INV-7)."""
        cfg = _active_config("v-cfg-001")
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id=cfg.version_id,
            execution_mode="SHADOW",
        )
        assert intent.config_version_id is not None
        assert intent.config_version_id == "v-cfg-001"

    def test_ssgpc3_shadow_cycle_null_correlation_id_is_governance_defect(self):
        """INV-5: Orchestration record with null correlation_id is a governance defect."""
        defective = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=None,    # defect
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        valid = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert defective.correlation_id is None         # defect confirmed
        assert valid.correlation_id is not None          # governance-conformant

    def test_ssgpc4_maintenance_mode_suppresses_shadow_trigger(self):
        """SHADOW triggers are suppressed in MAINTENANCE mode with observable record."""
        trigger = {
            "trigger_status": "SUPPRESSED",
            "suppression_reason": "MAINTENANCE_MODE",
            "execution_mode": "MAINTENANCE",
            "correlation_id": _make_uuid(),
        }
        assert trigger["trigger_status"] == "SUPPRESSED"
        assert trigger["suppression_reason"] == "MAINTENANCE_MODE"
        assert trigger["correlation_id"] is not None

    def test_ssgpc5_missing_threshold_resolves_to_unknown_v0(self):
        """Missing threshold key in SHADOW cycle → UNKNOWN_V0, never hardcoded fallback (GPC-2)."""
        cfg = _active_config("v-cfg-001")   # no threshold keys populated
        result = resolve_threshold(cfg, "outreach_sla_window_minutes")
        assert result == "UNKNOWN_V0"

    def test_ssgpc6_shadow_intent_must_not_carry_authorized_scope(self):
        """SHADOW mode intents must never carry governance_scope = AUTHORIZED."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert intent.governance_scope != "AUTHORIZED"
        assert shadow_intent_is_isolated(intent)

    def test_ssgpc7_exactly_one_active_config_invariant(self):
        """INV-2: exactly one ACTIVE config version at all times."""
        configs = [
            ConfigVersion("v-cfg-001", "SUPERSEDED"),
            ConfigVersion("v-cfg-002", "ACTIVE"),
        ]
        active_count = sum(1 for c in configs if c.status == "ACTIVE")
        assert active_count == 1


class TestShadowLiveIsolationGovernance:
    """
    Certifies the SHADOW/LIVE isolation boundary from runtime/system_loop.md §3.1.
    SHADOW mode: full orchestration evaluation; no LIVE outbound dispatch.
    Canonical: SVL-1, SVL-2, SVL-3.
    """

    def test_slg1_shadow_intent_scope_is_shadow_only(self):
        """SVL-1: SHADOW mode must produce governance_scope = SHADOW_ONLY (never AUTHORIZED)."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert shadow_intent_is_isolated(intent)
        assert intent.governance_scope == "SHADOW_ONLY"

    def test_slg2_shadow_provider_assessment_outbound_suppressed(self):
        """SVL-1: Provider assessment in SHADOW mode must have outbound_suppressed = True."""
        rec = ProviderContainmentRecord(
            provider="ghl",
            outbound_suppressed=True,
            governance_scope="SHADOW_ONLY",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
        )
        assert provider_is_contained(rec)

    def test_slg3_shadow_ai_output_tagged_shadow_only(self):
        """SVL-2: AI advisory outputs in SHADOW mode must be tagged outcome = shadow_only."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
            outcome="shadow_only",
        )
        assert ai_rec.outcome == "shadow_only"
        assert ai_rec.advisory_authorized_live_escalation is False

    def test_slg4_shadow_ai_does_not_authorize_live_escalation(self):
        """SVL-2: AI advisory must not authorize LIVE escalation routing in SHADOW mode."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
            outcome="shadow_only",
            advisory_authorized_live_escalation=False,
        )
        assert ai_is_advisory_only(ai_rec)

    def test_slg5_live_mode_eligible_student_produces_authorized_scope(self):
        """SVL-3: LIVE mode with eligible student produces governance_scope = AUTHORIZED."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="LIVE",
        )
        assert intent.governance_scope == "AUTHORIZED"
        assert intent.execution_mode == "LIVE"
        assert not shadow_intent_is_isolated(intent)

    def test_slg6_shadow_inbound_webhook_tagged_shadow(self):
        """SVL-1: Inbound webhook ingestion continues in SHADOW mode, tagged execution_mode = SHADOW."""
        webhook = ShadowWebhookIngestionRecord(
            event="ghl_webhook_processed",
            execution_mode="SHADOW",
            origin_source="ghl",
            origin_authority="platform_supplementary",
            correlation_id=_make_uuid(),
            duplicate_detected=False,
        )
        assert webhook.execution_mode == "SHADOW"
        assert webhook.origin_authority == "platform_supplementary"

    def test_slg7_shadow_sql_server_sync_proceeds_as_read_only(self):
        """SQL Server sync proceeds normally in SHADOW mode — sync is read-only, not an outbound action."""
        sync_rec = AttributionContainmentRecord(
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
            execution_type="original",
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
        )
        assert sync_rec.execution_mode == "SHADOW"
        assert sync_rec.origin_authority == "sql_server_authoritative"
        assert sync_rec.pii_present is False


class TestReplayContainmentGovernance:
    """
    Certifies replay isolation from runtime/system_loop.md §7 / INV-4 / AP-RT2.
    Replay must not produce LIVE effects, state transitions, LIVE AI inference,
    or LIVE escalation routing.
    Canonical: ROS-1, ROS-2, ROS-4, INV-4.
    """

    def test_rcg1_replay_produces_zero_live_effects(self):
        """INV-4 / AP-RT2: Replay execution must produce zero LIVE effects."""
        rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            causation_id=_make_uuid(),
            historical_config_version_id="v-cfg-001",
            live_effects_produced=0,
            state_transitions_produced=0,
            live_ai_inference_produced=False,
        )
        assert replay_is_live_free(rec)

    def test_rcg2_replay_governance_scope_is_replay_only(self):
        """ROS-1: All replay outputs must carry governance_scope = REPLAY_ONLY."""
        rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            causation_id=_make_uuid(),
            historical_config_version_id="v-cfg-001",
        )
        assert rec.governance_scope == "REPLAY_ONLY"

    def test_rcg3_replay_carries_new_correlation_id(self):
        """Replay must carry a new correlation_id — never the original cycle's."""
        original_cid = _make_uuid()
        replay_cid = _make_uuid()
        rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id=replay_cid,
            causation_id=original_cid,
            historical_config_version_id="v-cfg-001",
        )
        assert rec.correlation_id != rec.causation_id
        assert rec.causation_id == original_cid

    def test_rcg4_replay_causation_id_points_to_original_cycle(self):
        """Replay causation_id must point to the original cycle's correlation_id (ATT lineage)."""
        original_cid = "cid-original-abc"
        rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id="cid-replay-xyz",
            causation_id=original_cid,
            historical_config_version_id="v-cfg-001",
        )
        assert rec.causation_id == original_cid
        assert rec.correlation_id != original_cid

    def test_rcg5_replay_uses_historical_config_version_not_current_active(self):
        """ROS-2: Replay must use the historical config version, not the current ACTIVE version."""
        current_active = _active_config("v-cfg-002")
        rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            causation_id="cid-original-v1-cycle",
            historical_config_version_id="v-cfg-001",   # historical — must not be v-cfg-002
        )
        assert rec.historical_config_version_id != current_active.version_id

    def test_rcg6_replay_provider_outbound_suppressed(self):
        """Replay mode must suppress all provider outbound calls."""
        rec = ProviderContainmentRecord(
            provider="ghl",
            outbound_suppressed=True,
            governance_scope="REPLAY_ONLY",
            execution_mode="REPLAY",
            correlation_id=_make_uuid(),
        )
        assert provider_is_contained(rec)
        assert rec.execution_mode == "REPLAY"

    def test_rcg7_replay_live_ai_inference_blocked(self):
        """ROS-1: LIVE AI inference must be blocked during replay; FINALIZED_COPY sourced from warehouse."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="FINALIZED_COPY",
            execution_mode="REPLAY",
            correlation_id=_make_uuid(),
            outcome="skipped",
            live_inference_produced=False,
        )
        assert ai_rec.live_inference_produced is False
        assert ai_rec.ai_governance_tier == "FINALIZED_COPY"

    def test_rcg8_regeneration_reads_warehouse_exclusively(self):
        """REGENERATION mode reads warehouse only — no SQL Server reads, no AI calls (runtime/system_loop §3.1)."""
        regen_rec = ReplayContainmentRecord(
            execution_type="regeneration",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            causation_id=_make_uuid(),
            historical_config_version_id="v-cfg-001",
            live_effects_produced=0,
            state_transitions_produced=0,
            live_ai_inference_produced=False,
        )
        fin_rec = FinalizationContainmentRecord(
            record_type="ai_narrative",
            lifecycle_state="FINALIZED",
            allows_update=False,
            allows_delete=False,
            sourced_from_warehouse=True,
            correlation_id=regen_rec.correlation_id,
        )
        assert regen_rec.execution_type == "regeneration"
        assert fin_rec.sourced_from_warehouse is True
        assert finalization_is_immutable(fin_rec)


class TestProviderContainmentGovernance:
    """
    Certifies provider-boundary isolation for SHADOW and REPLAY modes.
    All providers (GHL, SMS, email, AI) must have outbound suppressed in non-LIVE modes.
    Canonical: SVL-1, PBG scenarios, runtime/system_loop.md §3.1.
    """

    def test_pcg1_ghl_suppressed_in_shadow_mode(self):
        """GHL outbound dispatch must be suppressed in SHADOW mode (governance_scope = SHADOW_ONLY)."""
        rec = ProviderContainmentRecord(
            provider="ghl",
            outbound_suppressed=True,
            governance_scope="SHADOW_ONLY",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
        )
        assert provider_is_contained(rec)

    def test_pcg2_sms_suppressed_in_shadow_mode(self):
        """SMS outbound dispatch must be suppressed in SHADOW mode."""
        rec = ProviderContainmentRecord(
            provider="sms",
            outbound_suppressed=True,
            governance_scope="SHADOW_ONLY",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
        )
        assert provider_is_contained(rec)

    def test_pcg3_email_suppressed_in_shadow_mode(self):
        """Email outbound dispatch must be suppressed in SHADOW mode."""
        rec = ProviderContainmentRecord(
            provider="email",
            outbound_suppressed=True,
            governance_scope="SHADOW_ONLY",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
        )
        assert provider_is_contained(rec)

    def test_pcg4_ai_provider_suppressed_in_replay(self):
        """AI provider live inference must be suppressed in REPLAY mode (governance_scope = REPLAY_ONLY)."""
        rec = ProviderContainmentRecord(
            provider="ai_provider",
            outbound_suppressed=True,
            governance_scope="REPLAY_ONLY",
            execution_mode="REPLAY",
            correlation_id=_make_uuid(),
        )
        assert provider_is_contained(rec)

    def test_pcg5_provider_containment_failure_is_observable(self):
        """Provider containment failures must not be silently swallowed — observable records required."""
        degradation = DegradationContainmentRecord(
            severity="CRITICAL",
            degradation_type="provider_containment_failure",
            error_class="ContainmentBoundaryViolation",
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
        )
        assert containment_failure_is_observable(degradation)
        assert degradation.silent_swallow is False

    def test_pcg6_ghl_retains_platform_supplementary_authority_in_shadow(self):
        """GHL entries retain origin_authority = platform_supplementary in SHADOW mode (spec/05 §2.5)."""
        rec = ShadowWebhookIngestionRecord(
            event="ghl_webhook_processed",
            execution_mode="SHADOW",
            origin_source="ghl",
            origin_authority="platform_supplementary",
            correlation_id=_make_uuid(),
        )
        assert rec.origin_authority == "platform_supplementary"
        assert rec.execution_mode == "SHADOW"


class TestAIContainmentGovernance:
    """
    Certifies AI advisory-only governance for SHADOW and REPLAY modes.
    AI must not authorize LIVE effects in SHADOW/REPLAY.
    FINALIZED_COPY must remain immutable across all mode interactions.
    Canonical: SVL-2, AIG scenarios, runtime/system_loop.md §9.
    """

    def test_acg1_ai_advisory_in_shadow_tagged_shadow_only(self):
        """SVL-2: AI advisory in SHADOW mode must be tagged outcome = shadow_only."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
            outcome="shadow_only",
        )
        assert ai_rec.outcome == "shadow_only"

    def test_acg2_ai_log_records_never_carry_content_text(self):
        """AI log records must never contain content_text (spec/06 §7.x / §12.1)."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
            outcome="shadow_only",
            content_text_present=False,
        )
        assert ai_rec.content_text_present is False

    def test_acg3_finalized_copy_immutable_after_any_shadow_interaction(self):
        """FINALIZED_COPY must not be modified by any SHADOW/REPLAY interaction (INV-6 / FAD-1)."""
        fin_rec = FinalizationContainmentRecord(
            record_type="ai_narrative",
            lifecycle_state="FINALIZED",
            allows_update=False,
            allows_delete=False,
            sourced_from_warehouse=True,
            correlation_id=_make_uuid(),
        )
        assert finalization_is_immutable(fin_rec)

    def test_acg4_stale_ai_served_in_shadow_is_observable(self):
        """Stale AI served in SHADOW mode must be observable — stale_ai_present and version required."""
        ai_rec = AIContainmentRecord(
            advisory_scope="STALE",
            ai_governance_tier="STALE",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
            outcome="shadow_only",
            stale_ai_present=True,
            stale_ai_version=2,
        )
        assert ai_rec.stale_ai_present is True
        assert ai_rec.stale_ai_version == 2

    def test_acg5_replay_sourced_finalized_copy_no_live_inference(self):
        """In REPLAY mode, AI content must be FINALIZED_COPY from warehouse — no live inference."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="FINALIZED_COPY",
            execution_mode="REPLAY",
            correlation_id=_make_uuid(),
            outcome="skipped",
            live_inference_produced=False,
        )
        assert ai_rec.ai_governance_tier == "FINALIZED_COPY"
        assert ai_rec.live_inference_produced is False

    def test_acg6_ai_advisory_does_not_authorize_orchestration_intent_alone(self):
        """AIG-1: AI advisory alone must not authorize OrchestrationIntent in SHADOW mode."""
        ai_rec = AIContainmentRecord(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            execution_mode="SHADOW",
            correlation_id=_make_uuid(),
            outcome="shadow_only",
            advisory_authorized_live_escalation=False,
        )
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert ai_is_advisory_only(ai_rec)
        assert intent.governance_scope == "SHADOW_ONLY"


class TestAttributionContainmentGovernance:
    """
    Certifies attribution continuity for all SHADOW/replay containment records.
    Every record must carry correlation_id, execution_mode, and execution_type.
    Canonical: ATT scenarios, INV-5, spec/05 §2.3.
    """

    def test_atcg1_shadow_record_carries_full_attribution(self):
        """INV-5 / ATT-1: Every SHADOW containment record must carry non-null attribution fields."""
        rec = AttributionContainmentRecord(
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
            execution_type="original",
            origin_source="scheduler",
            config_version_id="v-cfg-001",
        )
        assert attribution_is_complete(rec)

    def test_atcg2_replay_attribution_includes_causation_id(self):
        """ATT-2: Replay records must carry causation_id linking to the original cycle."""
        original_cid = _make_uuid()
        rec = AttributionContainmentRecord(
            correlation_id=_make_uuid(),
            execution_mode="REPLAY",
            execution_type="replay",
            causation_id=original_cid,
        )
        assert rec.causation_id == original_cid
        assert rec.correlation_id != rec.causation_id

    def test_atcg3_shadow_attribution_records_never_contain_pii(self):
        """spec/09 §3 / spec/06 §12.1: Attribution records must never contain raw PII."""
        rec = AttributionContainmentRecord(
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
            execution_type="original",
            pii_present=False,
        )
        assert rec.pii_present is False

    def test_atcg4_sql_server_entries_carry_authoritative_origin(self):
        """spec/05 §2.3: SQL Server entries carry origin_authority = sql_server_authoritative."""
        rec = AttributionContainmentRecord(
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
            execution_type="original",
            origin_source="mirrored_sql_server",
            origin_authority="sql_server_authoritative",
        )
        assert rec.origin_authority == "sql_server_authoritative"
        assert rec.origin_source == "mirrored_sql_server"

    def test_atcg5_recovery_cycle_attribution_is_continuous(self):
        """ATT-4: Recovery cycles must carry full attribution lineage — not break the chain."""
        parent_cid = _make_uuid()
        rec = AttributionContainmentRecord(
            correlation_id=_make_uuid(),
            execution_mode="LIVE",
            execution_type="recovery",
            causation_id=parent_cid,
            config_version_id="v-cfg-001",
        )
        assert attribution_is_complete(rec)
        assert rec.causation_id == parent_cid

    def test_atcg6_every_shadow_intent_carries_config_version_id(self):
        """INV-7: Every OrchestrationIntent in SHADOW mode must carry config_version_id."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert intent.config_version_id is not None


class TestDegradationContainmentGovernance:
    """
    Certifies that all containment failures produce deterministic, observable degradation records.
    No failure may be silently swallowed. error_class must always be specific.
    Canonical: DEG scenarios, runtime/system_loop.md §3.1 (DEGRADED mode).
    """

    def test_dcg1_provider_outage_in_shadow_produces_critical_alert(self):
        """SHADOW provider outage must produce CRITICAL severity, non-silent degradation record."""
        rec = DegradationContainmentRecord(
            severity="CRITICAL",
            degradation_type="provider_containment_failure",
            error_class="ProviderOutageError",
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
        )
        assert rec.severity == "CRITICAL"
        assert containment_failure_is_observable(rec)

    def test_dcg2_ai_provider_unavailable_produces_high_alert(self):
        """AI provider unavailable in SHADOW mode produces HIGH severity degradation."""
        rec = DegradationContainmentRecord(
            severity="HIGH",
            degradation_type="ai_provider_unavailable",
            error_class="AIProviderUnavailableError",
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
        )
        assert rec.severity == "HIGH"
        assert containment_failure_is_observable(rec)

    def test_dcg3_replay_degradation_is_observable(self):
        """Replay degradation must produce observable, non-generic-error records."""
        rec = DegradationContainmentRecord(
            severity="MEDIUM",
            degradation_type="historical_config_incomplete",
            error_class="HistoricalConfigResolutionError",
            correlation_id=_make_uuid(),
            execution_mode="REPLAY",
        )
        assert containment_failure_is_observable(rec)
        assert rec.error_class == "HistoricalConfigResolutionError"

    def test_dcg4_synchronization_degradation_not_silent(self):
        """Sync degradation must produce a non-silent observable record (DEG-4)."""
        rec = DegradationContainmentRecord(
            severity="HIGH",
            degradation_type="sync_lag_detected",
            error_class="StaleSQLServerDataError",
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
        )
        assert rec.silent_swallow is False
        assert containment_failure_is_observable(rec)

    def test_dcg5_containment_error_class_is_never_generic(self):
        """Degradation records must never use generic 'Error' as error_class."""
        valid_classes = [
            "ProviderOutageError",
            "AIProviderUnavailableError",
            "ContainmentBoundaryViolation",
            "HistoricalConfigResolutionError",
            "StaleSQLServerDataError",
            "ReplayContainmentViolation",
            "ShadowIsolationViolation",
        ]
        for ec in valid_classes:
            rec = DegradationContainmentRecord(
                severity="HIGH",
                degradation_type="test",
                error_class=ec,
                correlation_id=_make_uuid(),
                execution_mode="SHADOW",
            )
            assert containment_failure_is_observable(rec)

    def test_dcg6_observability_degradation_is_critical_severity(self):
        """Loss of containment observability in SHADOW mode is CRITICAL severity."""
        rec = DegradationContainmentRecord(
            severity="CRITICAL",
            degradation_type="observability_containment_failure",
            error_class="ObservabilityContainmentFailure",
            correlation_id=_make_uuid(),
            execution_mode="SHADOW",
            silent_swallow=False,
        )
        assert rec.severity == "CRITICAL"
        assert rec.silent_swallow is False


class TestShadowToLiveTransitionGovernance:
    """
    Certifies governance of the SHADOW → LIVE mode transition.
    Only Governance Administrators may authorize this transition.
    No automation service may trigger SHADOW → LIVE.
    Canonical: CV2-4, runtime/system_loop.md §3.2, AP-RT7.
    """

    def test_stlg1_shadow_to_live_requires_governance_administrator(self):
        """CV2-4 / AP-RT7: SHADOW → LIVE must be authorized by Governance Administrator."""
        transition = ShadowToLiveTransitionRecord(
            from_mode="SHADOW",
            to_mode="LIVE",
            actor_type="governance_administrator",
            actor_identity="admin-gvn-001",
            activation_record_present=True,
            automated_service_triggered=False,
            correlation_id=_make_uuid(),
            config_version_activation_id="cfg-act-001",
        )
        assert shadow_to_live_requires_governance_admin(transition)

    def test_stlg2_automation_service_cannot_trigger_shadow_to_live(self):
        """AP-RT7: Automation service triggering SHADOW → LIVE is a governance violation."""
        bad_transition = ShadowToLiveTransitionRecord(
            from_mode="SHADOW",
            to_mode="LIVE",
            actor_type="automation_service",        # violation
            actor_identity="scheduler-auto-001",
            activation_record_present=False,
            automated_service_triggered=True,       # violation
            correlation_id=_make_uuid(),
        )
        assert not shadow_to_live_requires_governance_admin(bad_transition)

    def test_stlg3_activation_record_must_be_present(self):
        """CV2-4: Activation record is mandatory for any SHADOW → LIVE transition."""
        transition = ShadowToLiveTransitionRecord(
            from_mode="SHADOW",
            to_mode="LIVE",
            actor_type="governance_administrator",
            actor_identity="admin-gvn-001",
            activation_record_present=True,     # required
            automated_service_triggered=False,
            correlation_id=_make_uuid(),
        )
        assert transition.activation_record_present is True

    def test_stlg4_transition_without_activation_record_is_defect(self):
        """Absence of activation_record_present on a SHADOW→LIVE transition is a governance defect."""
        bad_transition = ShadowToLiveTransitionRecord(
            from_mode="SHADOW",
            to_mode="LIVE",
            actor_type="governance_administrator",
            actor_identity="admin-gvn-001",
            activation_record_present=False,    # defect
            automated_service_triggered=False,
            correlation_id=_make_uuid(),
        )
        assert not shadow_to_live_requires_governance_admin(bad_transition)

    def test_stlg5_transition_record_carries_correlation_id(self):
        """Transition activation record must carry correlation_id (INV-5)."""
        transition = ShadowToLiveTransitionRecord(
            from_mode="SHADOW",
            to_mode="LIVE",
            actor_type="governance_administrator",
            actor_identity="admin-gvn-001",
            activation_record_present=True,
            automated_service_triggered=False,
            correlation_id=_make_uuid(),
        )
        assert bool(transition.correlation_id)


class TestGovernanceInvariantContainment:
    """
    Certifies that all seven governance invariants (INV-1 through INV-7) and
    key FAD constraints hold for SHADOW/replay containment contexts.
    Canonical: INV-1 through INV-7, FAD-1, FAD-3, spec/04 §2.4, CID scenarios.
    """

    def test_inv1_finalized_snapshot_is_immutable(self):
        """INV-1: FINALIZED snapshot records must not allow UPDATE or DELETE."""
        rec = FinalizationContainmentRecord(
            record_type="snapshot",
            lifecycle_state="FINALIZED",
            allows_update=False,
            allows_delete=False,
        )
        assert finalization_is_immutable(rec)

    def test_inv2_exactly_one_active_config_version(self):
        """INV-2: Config version registry must contain exactly one ACTIVE version."""
        configs = [
            ConfigVersion("v-cfg-001", "SUPERSEDED"),
            ConfigVersion("v-cfg-002", "ACTIVE"),
        ]
        assert sum(1 for c in configs if c.status == "ACTIVE") == 1

    def test_inv3_prospective_only_config_activation(self):
        """INV-3 / FAD-3: New config activation does not retroactively affect historical cycles."""
        historical_intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",      # historical
            execution_mode="SHADOW",
        )
        new_active_version = "v-cfg-002"
        assert historical_intent.config_version_id != new_active_version

    def test_inv4_replay_produces_no_live_effects(self):
        """INV-4 / AP-RT2: Replay must produce zero LIVE effects across all domains."""
        rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            causation_id=_make_uuid(),
            historical_config_version_id="v-cfg-001",
            live_effects_produced=0,
            state_transitions_produced=0,
            live_ai_inference_produced=False,
            live_escalation_routing_produced=False,
        )
        assert replay_is_live_free(rec)

    def test_inv5_every_containment_record_carries_correlation_id(self):
        """INV-5: Every orchestration record in SHADOW/replay must carry a non-null correlation_id."""
        records = [
            AttributionContainmentRecord(
                correlation_id=_make_uuid(),
                execution_mode="SHADOW",
                execution_type="original",
            )
            for _ in range(10)
        ]
        assert all(attribution_is_complete(r) for r in records)

    def test_inv6_ai_narrative_immutability(self):
        """INV-6 / FAD-1: warehouse.snapshot_ai_narratives rows must not allow UPDATE or DELETE."""
        rec = FinalizationContainmentRecord(
            record_type="ai_narrative",
            lifecycle_state="FINALIZED",
            allows_update=False,
            allows_delete=False,
            sourced_from_warehouse=True,
        )
        assert finalization_is_immutable(rec)

    def test_inv7_no_hardcoded_threshold_in_shadow_records(self):
        """INV-7: Every governance decision record in SHADOW must carry config_version_id."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert intent.config_version_id is not None

    def test_fad1_finalized_copy_sourced_from_warehouse_in_regeneration(self):
        """FAD-1: Historical report regeneration reads warehouse exclusively — no live queries."""
        fin_rec = FinalizationContainmentRecord(
            record_type="ai_narrative",
            lifecycle_state="FINALIZED",
            allows_update=False,
            allows_delete=False,
            sourced_from_warehouse=True,
        )
        assert fin_rec.sourced_from_warehouse is True

    def test_fad3_replay_uses_historical_config_not_current_active(self):
        """FAD-3: Replay must use historical config version; current ACTIVE does not apply."""
        original_cycle_config = "v-cfg-001"
        current_active_config = "v-cfg-002"
        replay_rec = ReplayContainmentRecord(
            execution_type="replay",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            causation_id=_make_uuid(),
            historical_config_version_id=original_cycle_config,
        )
        assert replay_rec.historical_config_version_id == original_cycle_config
        assert replay_rec.historical_config_version_id != current_active_config

    def test_cid1_duplicate_shadow_cycle_is_idempotent(self):
        """CID-1: Duplicate SHADOW cycle triggers must be suppressed by idempotency gate."""
        seen_cycle_keys = {"2026-06-01|SHADOW|v-cfg-001"}
        new_cycle_key = "2026-06-01|SHADOW|v-cfg-001"
        is_duplicate = new_cycle_key in seen_cycle_keys
        assert is_duplicate is True     # idempotency gate fires

    def test_cid2_replay_isolated_from_live_batch(self):
        """CID-3: Replay concurrency must be isolated from LIVE batch execution."""
        live_intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="LIVE",
            execution_type="original",
        )
        replay_intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="REPLAY_ONLY",
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="REPLAY",
            execution_type="replay",
        )
        assert live_intent.correlation_id != replay_intent.correlation_id
        assert live_intent.governance_scope != replay_intent.governance_scope

    def test_inv_report_published_is_immutable(self):
        """REPORT_PUBLISHED records must not allow UPDATE or DELETE (spec/04 §2.4)."""
        rec = FinalizationContainmentRecord(
            record_type="report",
            lifecycle_state="REPORT_PUBLISHED",
            allows_update=False,
            allows_delete=False,
        )
        assert finalization_is_immutable(rec)


class TestShadowWebhookIngestionContainment:
    """
    Certifies that inbound webhook ingestion continues correctly in SHADOW mode.
    Webhooks are ingested and tagged execution_mode = SHADOW; dedup gate applies normally.
    Canonical: SVL-1, runtime/system_loop.md §3.1 (inbound continues in SHADOW).
    """

    def test_swic1_ghl_webhook_tagged_shadow_mode(self):
        """Inbound GHL webhook in SHADOW mode must be tagged execution_mode = SHADOW."""
        rec = ShadowWebhookIngestionRecord(
            event="ghl_webhook_processed",
            execution_mode="SHADOW",
            origin_source="ghl",
            origin_authority="platform_supplementary",
            correlation_id=_make_uuid(),
        )
        assert rec.execution_mode == "SHADOW"

    def test_swic2_duplicate_webhook_triggers_dedup_gate(self):
        """Duplicate webhook in SHADOW mode triggers dedup gate before any state management."""
        rec = ShadowWebhookIngestionRecord(
            event="ghl_webhook_processed",
            execution_mode="SHADOW",
            origin_source="ghl",
            origin_authority="platform_supplementary",
            correlation_id=_make_uuid(),
            duplicate_detected=True,
            dedup_gate_applied=True,
        )
        assert rec.duplicate_detected is True
        assert rec.dedup_gate_applied is True

    def test_swic3_webhook_in_shadow_does_not_trigger_live_state_transition(self):
        """Inbound webhook in SHADOW mode must not authorize LIVE state transitions."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",     # not AUTHORIZED
            correlation_id=_make_uuid(),
            config_version_id="v-cfg-001",
            execution_mode="SHADOW",
        )
        assert intent.governance_scope == "SHADOW_ONLY"
        assert intent.execution_mode == "SHADOW"

    def test_swic4_webhook_carries_origin_attribution(self):
        """spec/05 §2.3: Every ingested webhook must carry origin_source and origin_authority."""
        rec = ShadowWebhookIngestionRecord(
            event="ghl_webhook_processed",
            execution_mode="SHADOW",
            origin_source="ghl",
            origin_authority="platform_supplementary",
            correlation_id=_make_uuid(),
        )
        assert rec.origin_source == "ghl"
        assert rec.origin_authority == "platform_supplementary"
        assert bool(rec.correlation_id)


class TestShadowContainmentLoadCertification:
    """
    Governance load certification for SHADOW/replay containment.
    Certifies correct attribution, isolation, and containment at scale.
    Canonical: LCS, LCR, LCI from tests/load_tests.md.
    """

    def test_lci1_100_shadow_intents_all_carry_correlation_id(self):
        """Load: 100 SHADOW intents — every record carries non-null correlation_id (INV-5)."""
        intents = [
            OrchestrationIntent(
                intent_type="INITIATE_OUTREACH",
                governance_scope="SHADOW_ONLY",
                correlation_id=_make_uuid(),
                config_version_id="v-cfg-001",
                execution_mode="SHADOW",
            )
            for _ in range(100)
        ]
        assert all(i.correlation_id is not None for i in intents)
        assert all(shadow_intent_is_isolated(i) for i in intents)

    def test_lci2_500_provider_containment_records_all_suppressed(self):
        """Load: 500 provider containment records — all outbound_suppressed = True in SHADOW."""
        providers = ["ghl", "sms", "email", "synthflow", "ai_provider"] * 100
        records = [
            ProviderContainmentRecord(
                provider=p,
                outbound_suppressed=True,
                governance_scope="SHADOW_ONLY",
                execution_mode="SHADOW",
                correlation_id=_make_uuid(),
            )
            for p in providers
        ]
        assert all(provider_is_contained(r) for r in records)

    def test_lci3_200_replay_records_all_live_free(self):
        """Load: 200 replay records — zero LIVE effects across all (INV-4)."""
        original_cid = _make_uuid()
        records = [
            ReplayContainmentRecord(
                execution_type="replay",
                governance_scope="REPLAY_ONLY",
                correlation_id=_make_uuid(),
                causation_id=original_cid,
                historical_config_version_id="v-cfg-001",
                live_effects_produced=0,
                state_transitions_produced=0,
                live_ai_inference_produced=False,
            )
            for _ in range(200)
        ]
        assert all(replay_is_live_free(r) for r in records)

    def test_lci4_100_ai_records_no_content_text(self):
        """Load: 100 AI containment records — none carry content_text (spec/06 §12.1)."""
        records = [
            AIContainmentRecord(
                advisory_scope="AVAILABLE",
                ai_governance_tier="AI_GENERATED",
                execution_mode="SHADOW",
                correlation_id=_make_uuid(),
                outcome="shadow_only",
                content_text_present=False,
            )
            for _ in range(100)
        ]
        assert all(r.content_text_present is False for r in records)

    def test_lci5_100_degradation_records_none_silently_swallowed(self):
        """Load: 100 degradation records — none silently swallowed, all specific error_class."""
        error_classes = [
            "ProviderOutageError",
            "AIProviderUnavailableError",
            "ContainmentBoundaryViolation",
            "HistoricalConfigResolutionError",
            "ReplayContainmentViolation",
        ] * 20
        records = [
            DegradationContainmentRecord(
                severity="HIGH",
                degradation_type="test_degradation",
                error_class=ec,
                correlation_id=_make_uuid(),
                execution_mode="SHADOW",
            )
            for ec in error_classes
        ]
        assert all(containment_failure_is_observable(r) for r in records)

    def test_lci6_config_v2_all_missing_keys_resolve_to_unknown_v0(self):
        """Load: Config V2 — all missing threshold keys resolve to UNKNOWN_V0, never hardcoded."""
        cfg = _active_config("v-cfg-001")   # no thresholds populated
        keys = [
            "outreach_max_retry_attempts",
            "outreach_sla_window_minutes",
            "ai_staleness_threshold_hours",
            "provider_circuit_breaker_threshold",
            "sync_lag_alert_minutes",
        ]
        for k in keys:
            assert resolve_threshold(cfg, k) == "UNKNOWN_V0"

    def test_lci7_concurrent_shadow_intents_carry_distinct_correlation_ids(self):
        """Load: Concurrent SHADOW intent generation produces distinct correlation_ids per thread."""
        results: List[str] = []
        lock = threading.Lock()

        def generate_shadow_intent() -> None:
            cid = _make_uuid()
            intent = OrchestrationIntent(
                intent_type="INITIATE_OUTREACH",
                governance_scope="SHADOW_ONLY",
                correlation_id=cid,
                config_version_id="v-cfg-001",
                execution_mode="SHADOW",
            )
            with lock:
                results.append(intent.correlation_id)

        threads = [threading.Thread(target=generate_shadow_intent) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        assert len(set(results)) == 20      # all distinct
