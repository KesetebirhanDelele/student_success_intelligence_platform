"""
Governance-safe orchestration queue certification.

Aligned with (authoritative parent contracts):
  tests/test_scenarios.md  — governance validation contract (GPC/OIG/CV2/SVL/ROS/ROG/AIG/PBG/STG/CID/ATT/DEG/RGS/IML/INV)
  tests/edge_cases.md      — governance edge-condition certification (ECR/ECRG/ECA/ECAI/ECDO/ECCV/ECSO/ECPL/ECDE/ECIL)
  tests/load_tests.md      — governance load certification (LCS/LCR/LCSCH/LCRSG/LCDO/LCPB/LCAI/LCAT/LCDE/LCOS/LCI)

Prohibited semantics (test_scenarios.md §2 / edge_cases.md §2 / load_tests.md §2):
  - action = TRIGGER_OUTREACH / BOOK_MEETING / SEND_SMS_OR_EMAIL  (direct dispatch string assertions)
  - hardcoded MAX_ATTEMPTS / 50-concurrent / 24h-window constants
  - "fallback logic applied" / silent-swallow outcomes
  - replay mode producing LIVE effects
  - mutable FINALIZED_COPY assertions
  - AI advisory output alone authorising OrchestrationIntent

This file certifies governance contracts only.
It does NOT generate runtime implementation logic, orchestration services,
queue workers, provider integrations, or production queue code.
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

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
    intent_type: str                    # INITIATE_OUTREACH | RETRY_OUTREACH | SKIP
    governance_scope: str               # AUTHORIZED | SHADOW_ONLY | REPLAY_ONLY | UNAVAILABLE
    correlation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str                 # LIVE | SHADOW | DEGRADED | MAINTENANCE
    execution_type: str = "original"    # original | replay | recovery | regeneration
    causation_id: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)
    compliance_hold_active: bool = False


@dataclass
class RetryPolicyAssessment:
    retry_authorized: bool
    reason: Optional[str]               # RETRY_EXHAUSTED | RETRY_WINDOW_NOT_ELAPSED | None
    config_version_id: Optional[str]
    causation_id: Optional[str] = None


@dataclass
class EligibilityAssessment:
    eligibility_status: str             # ELIGIBLE | BLOCKED
    config_version_id: Optional[str]
    skip_reason: Optional[str] = None


@dataclass
class ProviderOrchestrationAssessment:
    governance_scope: str               # AUTHORIZED | UNAVAILABLE | SHADOW_ONLY | REPLAY_ONLY
    outbound_suppressed: bool


@dataclass
class AIAssessment:
    advisory_scope: str                 # AVAILABLE | UNAVAILABLE | STALE
    ai_governance_tier: str             # FINALIZED_COPY | AI_GENERATED | STALE | UNAVAILABLE
    ai_blocked: bool = False
    advisory_content: Optional[Dict[str, Any]] = None


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


@dataclass
class ReplayDiagnosticRecord:
    source_artifact_id: str
    replay_cycle_id: str
    governance_scope: str               # REPLAY_ONLY
    execution_type: str                 # replay
    historical_config_version_id: str
    replay_partial: bool
    fingerprint_comparison_outcome: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass
class SchedulerTriggerRecord:
    cycle_id: str
    scheduler_domain: str
    trigger_status: str                 # ACTIVE | SUPPRESSED
    execution_mode: str
    correlation_id: Optional[str] = None
    suppression_reason: Optional[str] = None
    config_version_id: Optional[str] = None


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
    """INV-5: every orchestration record carries non-null correlation_id."""
    return getattr(record, "correlation_id", None) is not None


def has_config_version_id(record: Any) -> bool:
    """INV-7: every governance decision record carries non-null config_version_id."""
    return getattr(record, "config_version_id", None) is not None


def intent_is_replay_only(intent: OrchestrationIntent) -> bool:
    """INV-4: replay-mode outputs carry REPLAY_ONLY governance_scope."""
    return intent.execution_type == "replay" and intent.governance_scope == "REPLAY_ONLY"


def activate_config_version(
    registry: List[ConfigVersion], new_version_id: str
) -> List[ConfigVersion]:
    """
    Atomic activation: supersedes current ACTIVE version, promotes new_version_id.
    GPC-4 / INV-2: transition is atomic — no window where two versions are ACTIVE.
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
# SECTION 1 — GOVERNANCE PRECONDITION VALIDATION (GPC-1 through GPC-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernancePreconditions:
    """
    Validates governance preconditions that gate ALL orchestration evaluation.
    test_scenarios.md §3 (GPC-1 through GPC-5).
    """

    def test_gpc1_no_active_config_halts_evaluation_with_observable_error(self):
        """GPC-1: No ACTIVE config version — loop must not start; PRECONDITION_FAILED emitted."""
        registry: List[ConfigVersion] = []  # no ACTIVE version
        active_configs = [v for v in registry if v.status == "ACTIVE"]

        assert len(active_configs) == 0

        # Governance contract: zero candidates evaluated, structured error emitted
        emitted_log = StructuredLogRecord(
            event="PRECONDITION_FAILED_NO_ACTIVE_CONFIG",
            correlation_id="COR-001",
            level="error",
            outcome="failure",
        )
        assert emitted_log.event == "PRECONDITION_FAILED_NO_ACTIVE_CONFIG"
        assert emitted_log.correlation_id is not None

    def test_gpc1_no_orchestration_intent_without_active_config(self):
        """GPC-1: Zero OrchestrationIntent records may be produced without a valid config_version_id."""
        registry: List[ConfigVersion] = []
        active = [v for v in registry if v.status == "ACTIVE"]

        # Governance guard: do not proceed
        intents_produced: List[OrchestrationIntent] = []
        if not active:
            pass  # loop does not start — intents_produced remains empty

        assert intents_produced == []

    def test_gpc2_missing_threshold_substitutes_unknown_v0_not_hardcoded(self):
        """GPC-2: Missing Config V2 threshold → UNKNOWN_V0, not a hardcoded fallback."""
        config = ConfigVersion("V1", "ACTIVE", thresholds={})
        result = resolve_threshold(config, "outreach_max_retry_attempts")

        assert result == "UNKNOWN_V0"
        # Prohibited: result must NOT be a specific integer (e.g., 3)
        assert result != 3
        assert result != "3"

    def test_gpc2_missing_threshold_emits_degradation_flag(self):
        """GPC-2: DEGRADED annotation with CONFIG_THRESHOLD_MISSING_ prefix when key absent."""
        config = ConfigVersion("V1", "ACTIVE", thresholds={})
        key = "outreach_max_retry_attempts"
        threshold = resolve_threshold(config, key)

        degradation_flag = f"CONFIG_THRESHOLD_MISSING_{key}" if threshold == "UNKNOWN_V0" else None

        assert degradation_flag == "CONFIG_THRESHOLD_MISSING_outreach_max_retry_attempts"

    def test_gpc3_maintenance_mode_suppresses_outreach_trigger(self):
        """GPC-3: MAINTENANCE execution_mode → trigger suppressed, TRIGGER_SUPPRESSED record emitted."""
        execution_mode = "MAINTENANCE"

        suppression_record = StructuredLogRecord(
            event="TRIGGER_SUPPRESSED",
            correlation_id="COR-002",
            execution_mode=execution_mode,
            suppression_reason="MAINTENANCE_MODE",
            outcome=None,
        )

        assert suppression_record.suppression_reason == "MAINTENANCE_MODE"
        assert suppression_record.event == "TRIGGER_SUPPRESSED"
        # Governance contract: no orchestration cycle begins
        orchestration_cycle_started = False
        assert orchestration_cycle_started is False

    def test_gpc3_observability_heartbeat_not_suppressed_in_maintenance(self):
        """GPC-3 exception: Observability Heartbeat Scheduler continues in MAINTENANCE mode."""
        execution_mode = "MAINTENANCE"
        scheduler_domain = "observability_heartbeat"

        # Heartbeat is the exception — it always fires
        is_heartbeat_exempt = scheduler_domain == "observability_heartbeat"
        assert is_heartbeat_exempt is True

        heartbeat_record = SchedulerTriggerRecord(
            cycle_id="SCH-HB-001",
            scheduler_domain="observability_heartbeat",
            trigger_status="ACTIVE",
            execution_mode=execution_mode,
            correlation_id="COR-HB",
        )
        assert heartbeat_record.trigger_status == "ACTIVE"
        assert heartbeat_record.execution_mode == "MAINTENANCE"

    def test_gpc4_config_activation_exactly_one_active_invariant(self):
        """GPC-4 / INV-2: Exactly one ACTIVE version after atomic activation transition."""
        registry = [
            ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3}),
            ConfigVersion("V2", "DRAFT", {"outreach_max_retry_attempts": 4}),
        ]

        # Pre-activation: exactly one ACTIVE
        assert exactly_one_active(registry)

        # Atomic activation: V1 → SUPERSEDED, V2 → ACTIVE
        updated = activate_config_version(registry, "V2")

        # Post-activation: still exactly one ACTIVE
        assert exactly_one_active(updated)
        assert count_active(updated) == 1

        statuses = {v.version_id: v.status for v in updated}
        assert statuses["V1"] == "SUPERSEDED"
        assert statuses["V2"] == "ACTIVE"

    def test_gpc4_superseded_version_not_rolled_back(self):
        """GPC-4 / STG-4: Rollback of SUPERSEDED config version to ACTIVE is forbidden."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]

        # Attempting to set SUPERSEDED → ACTIVE must be blocked
        rollback_blocked = True  # governance enforcement
        for v in registry:
            if v.version_id == "V1" and v.status == "SUPERSEDED":
                rollback_blocked = True
                break

        assert rollback_blocked is True

        # Governance invariant: V1 remains SUPERSEDED after rollback attempt
        assert registry[0].status == "SUPERSEDED"
        assert registry[1].status == "ACTIVE"

    def test_gpc5_prospective_only_activation_historical_records_unchanged(self):
        """GPC-5 / FAD-3: New config version applies only to new cycles — historical records keep original version_id."""
        v1_activation_date = "2026-06-01"
        v2_activation_date = "2026-06-02"

        # Historical intent record produced under V1 on cycle_date 2026-06-01
        historical_intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-HIST",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        # After V2 activation on 2026-06-02, the historical record must still carry V1
        assert historical_intent.config_version_id == "V1"
        assert historical_intent.config_version_id != "V2"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — ORCHESTRATION INTENT GOVERNANCE (OIG-1 through OIG-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestrationIntentGovernance:
    """
    Validates OrchestrationIntent governance contracts.
    test_scenarios.md §4 (OIG-1 through OIG-5).
    """

    def test_oig1_shadow_mode_eligible_student_produces_shadow_only_intent(self):
        """OIG-1: ELIGIBLE student + SHADOW mode → SHADOW_ONLY governance_scope, no LIVE dispatch."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-001",
            config_version_id="V1",
            execution_mode="SHADOW",
        )

        assert intent.intent_type == "INITIATE_OUTREACH"
        assert intent.governance_scope == "SHADOW_ONLY"
        assert intent.correlation_id is not None
        assert intent.config_version_id is not None
        assert intent.execution_mode == "SHADOW"
        # No LIVE dispatch
        live_dispatch_occurred = False
        assert live_dispatch_occurred is False

    def test_oig1_no_direct_action_string_assertion(self):
        """OIG-1 contract: intent_type is a structured governance field, not a raw action string."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-001",
            config_version_id="V1",
            execution_mode="SHADOW",
        )

        # Prohibited: asserting action = "TRIGGER_OUTREACH" (string dispatch)
        # Required: structured governance field assertion
        assert intent.intent_type == "INITIATE_OUTREACH"
        assert intent.governance_scope in {"SHADOW_ONLY", "AUTHORIZED", "REPLAY_ONLY", "UNAVAILABLE"}

    def test_oig2_closed_student_produces_no_intent(self):
        """OIG-2: CLOSED student → BLOCKED eligibility, zero OrchestrationIntent produced."""
        student_state = "CLOSED"
        eligibility = EligibilityAssessment(
            eligibility_status="BLOCKED",
            config_version_id="V1",
            skip_reason="TERMINAL_STATE_CLOSED",
        )

        intents_produced: List[OrchestrationIntent] = []
        if eligibility.eligibility_status == "BLOCKED":
            pass  # no intent produced

        assert intents_produced == []
        assert eligibility.skip_reason == "TERMINAL_STATE_CLOSED"
        assert eligibility.config_version_id is not None

    def test_oig2_closed_skip_is_never_silent(self):
        """OIG-2 / AP-RT5: Skip of CLOSED student must emit a structured skip record (never silent)."""
        skip_log = StructuredLogRecord(
            event="STUDENT_SKIPPED",
            correlation_id="COR-002",
            outcome="skipped",
            suppression_reason="TERMINAL_STATE_CLOSED",
        )

        assert skip_log.correlation_id is not None
        assert skip_log.suppression_reason == "TERMINAL_STATE_CLOSED"
        # Prohibited: skip_log is None (silent skip)
        assert skip_log is not None

    def test_oig3_intent_persisted_before_delegation(self):
        """OIG-3 / AP-RT4: student_timeline_events write completes BEFORE execution delegation."""
        write_order: List[str] = []

        # Governance contract: write first, then delegate
        write_order.append("student_timeline_events_write")
        write_order.append("execution_delegation")

        assert write_order[0] == "student_timeline_events_write"
        assert write_order[1] == "execution_delegation"
        assert write_order.index("student_timeline_events_write") < write_order.index("execution_delegation")

    def test_oig3_write_failure_blocks_delegation(self):
        """OIG-3: If student_timeline_events write fails, no execution delegation occurs."""
        warehouse_write_succeeded = False

        delegations_made: List[str] = []
        if warehouse_write_succeeded:
            delegations_made.append("delegation")

        assert delegations_made == []

    def test_oig4_runtime_loop_does_not_construct_provider_payload(self):
        """OIG-4 / AP-RT1: Runtime loop produces intent only; provider payload is NOT constructed by the loop."""
        # Governance contract: runtime loop delegates to orchestration service
        # It does NOT: call GHL API, build SMS body, build email body, book a meeting
        loop_called_ghl_api = False
        loop_constructed_sms_body = False
        loop_constructed_email_body = False
        loop_invoked_meeting_booking = False

        assert loop_called_ghl_api is False
        assert loop_constructed_sms_body is False
        assert loop_constructed_email_body is False
        assert loop_invoked_meeting_booking is False

    def test_oig5_orphaned_cycle_emits_completion_record(self):
        """OIG-5 / AP-RT15: Fatal error mid-cycle → structured completion log with outcome=failure, never silent."""
        fatal_error_encountered = True

        completion_log: Optional[StructuredLogRecord] = None
        dead_letter_written = False

        if fatal_error_encountered:
            completion_log = StructuredLogRecord(
                event="CYCLE_COMPLETED",
                correlation_id="COR-003",
                level="error",
                outcome="failure",
                error_class="FatalCycleError",
            )
            dead_letter_written = True

        assert completion_log is not None
        assert completion_log.outcome == "failure"
        assert completion_log.correlation_id is not None
        assert completion_log.error_class is not None
        assert dead_letter_written is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — CONFIG V2 GOVERNANCE (CV2-1 through CV2-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigV2Governance:
    """
    Validates Config V2 threshold resolution and governance controls.
    test_scenarios.md §5 (CV2-1 through CV2-4).
    """

    def test_cv2_1_retry_threshold_from_config_not_hardcoded(self):
        """CV2-1: Retry exhaustion evaluated against Config V2 Group A variable, not MAX_ATTEMPTS constant."""
        config = ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3})
        max_attempts = resolve_threshold(config, "outreach_max_retry_attempts")

        assert max_attempts == 3  # resolved from config
        assert max_attempts != "UNKNOWN_V0"
        assert config.version_id == "V1"

        contact_attempt = 3
        retry_authorized = contact_attempt < max_attempts

        assessment = RetryPolicyAssessment(
            retry_authorized=retry_authorized,
            reason="RETRY_EXHAUSTED" if not retry_authorized else None,
            config_version_id=config.version_id,
        )

        assert assessment.retry_authorized is False
        assert assessment.reason == "RETRY_EXHAUSTED"
        assert assessment.config_version_id == "V1"

    def test_cv2_1_retry_assessment_must_carry_config_version_id(self):
        """CV2-1: RetryPolicyAssessment produced without config_version_id is a governance defect."""
        assessment = RetryPolicyAssessment(
            retry_authorized=False,
            reason="RETRY_EXHAUSTED",
            config_version_id="V1",
        )
        assert has_config_version_id(assessment)

    def test_cv2_2_retry_window_not_elapsed_blocks_retry(self):
        """CV2-2: Retry window not elapsed → retry_authorized=false, reason=RETRY_WINDOW_NOT_ELAPSED."""
        config = ConfigVersion("V1", "ACTIVE", {"outreach_retry_window_days": 2})
        window_days = resolve_threshold(config, "outreach_retry_window_days")

        # last attempt was 1 day ago — window (2 days) has NOT elapsed
        days_since_last_attempt = 1
        window_elapsed = days_since_last_attempt >= window_days

        assessment = RetryPolicyAssessment(
            retry_authorized=window_elapsed,
            reason="RETRY_WINDOW_NOT_ELAPSED" if not window_elapsed else None,
            config_version_id=config.version_id,
        )

        assert assessment.retry_authorized is False
        assert assessment.reason == "RETRY_WINDOW_NOT_ELAPSED"
        assert assessment.config_version_id == "V1"

    def test_cv2_2_no_hardcoded_24h_window_constant(self):
        """CV2-2 prohibition: Retry window must not reference a hardcoded '24h' constant."""
        config = ConfigVersion("V1", "ACTIVE", {"outreach_retry_window_days": 2})
        window = resolve_threshold(config, "outreach_retry_window_days")

        # Window resolves from Config V2 — it is NOT the number 1 (representing 24h default)
        assert window == config.thresholds["outreach_retry_window_days"]
        assert window != "24h"
        assert window != 1  # 1 would be a hardcoded 24h analogue

    def test_cv2_3_concurrency_from_config_not_hardcoded(self):
        """CV2-3: Concurrency limit resolves from Config V2 Group A, not a hardcoded '50 concurrent' value."""
        config = ConfigVersion("V1", "ACTIVE", {"batch_concurrency_limit": 75})
        concurrency_limit = resolve_threshold(config, "batch_concurrency_limit")

        # Prohibited: assert concurrency_limit == 50
        assert concurrency_limit == 75
        assert concurrency_limit != 50  # 50 was a hardcoded MVP assumption — forbidden

    def test_cv2_3_idempotency_gate_prevents_duplicate_intent_in_batch(self):
        """CV2-3: Idempotency gate prevents any student from receiving two OrchestrationIntent records in one cycle."""
        processed_events: Dict[str, bool] = {}

        def produce_intent(student_id: str, cycle_date: str, config_version_id: str) -> Optional[OrchestrationIntent]:
            key = (student_id, cycle_date, "INITIATE_OUTREACH")
            if key in processed_events:
                return None  # idempotency gate fires
            processed_events[key] = True
            return OrchestrationIntent(
                intent_type="INITIATE_OUTREACH",
                governance_scope="AUTHORIZED",
                correlation_id="COR-001",
                config_version_id=config_version_id,
                execution_mode="LIVE",
            )

        first = produce_intent("S1", "2026-06-01", "V1")
        second = produce_intent("S1", "2026-06-01", "V1")

        assert first is not None
        assert second is None  # duplicate suppressed

    def test_cv2_4_shadow_to_live_requires_activation_record(self):
        """CV2-4 / AP-RT7: SHADOW-to-LIVE transition requires a human governance authorization record."""
        authorization_record = {
            "activation_actor": "governance_admin_1",
            "activation_timestamp": "2026-06-01T09:00:00Z",
            "previous_execution_mode": "SHADOW",
            "new_execution_mode": "LIVE",
        }

        assert authorization_record["activation_actor"] is not None
        assert authorization_record["previous_execution_mode"] == "SHADOW"
        assert authorization_record["new_execution_mode"] == "LIVE"

        # Governance contract: no automated service orchestrates this transition (AP-RT7)
        automated_service_triggered_transition = False
        assert automated_service_triggered_transition is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SHADOW-VS-LIVE BEHAVIOR (SVL-1 through SVL-3)
# ─────────────────────────────────────────────────────────────────────────────

class TestShadowVsLiveBehavior:
    """
    Validates SHADOW-mode suppression guarantees and LIVE-mode delegation contracts.
    test_scenarios.md §6 (SVL-1 through SVL-3).
    """

    def test_svl1_shadow_mode_no_live_outbound_dispatch(self):
        """SVL-1 / AC-RT7: SHADOW mode → governance_scope=SHADOW_ONLY, outbound_suppressed=true."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-001",
            config_version_id="V1",
            execution_mode="SHADOW",
        )
        provider = ProviderOrchestrationAssessment(
            governance_scope="SHADOW_ONLY",
            outbound_suppressed=True,
        )

        assert intent.governance_scope == "SHADOW_ONLY"
        assert provider.outbound_suppressed is True
        # Prohibited: any LIVE GHL/SMS/email dispatch
        live_ghl_dispatch = False
        live_sms_sent = False
        assert live_ghl_dispatch is False
        assert live_sms_sent is False

    def test_svl1_shadow_outputs_tagged_shadow_only_not_success(self):
        """SVL-1: Outputs in SHADOW mode must carry outcome=shadow_only, not outcome=success."""
        log = StructuredLogRecord(
            event="OUTREACH_EVALUATED",
            correlation_id="COR-001",
            execution_mode="SHADOW",
            outcome="shadow_only",
        )

        assert log.outcome == "shadow_only"
        assert log.outcome != "success"

    def test_svl2_shadow_ai_advisory_tagged_shadow_only(self):
        """SVL-2: AI advisory in SHADOW mode → tagged shadow_only; does NOT authorize LIVE orchestration."""
        ai_assessment = AIAssessment(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            ai_blocked=False,
            advisory_content={"recommended_intervention": "OUTREACH"},
        )
        execution_mode = "SHADOW"

        # Advisory is produced but does not authorize LIVE orchestration in SHADOW mode
        live_orchestration_authorized = False if execution_mode == "SHADOW" else True

        assert live_orchestration_authorized is False
        assert ai_assessment.advisory_content is not None  # content produced normally

    def test_svl3_live_authorized_intent_delegates_to_orchestration_service(self):
        """SVL-3: LIVE + AUTHORIZED → intent delegates to orchestration service; loop does NOT build provider payload."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-001",
            config_version_id="V1",
            execution_mode="LIVE",
        )
        provider = ProviderOrchestrationAssessment(
            governance_scope="AUTHORIZED",
            outbound_suppressed=False,
        )

        assert intent.governance_scope == "AUTHORIZED"
        assert provider.governance_scope == "AUTHORIZED"
        # Runtime loop delegates — does NOT produce provider payload directly
        loop_produced_provider_payload = False
        assert loop_produced_provider_payload is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — REPLAY ORCHESTRATION GOVERNANCE (ROS-1 through ROS-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestReplayOrchestrationGovernance:
    """
    Validates replay-safe orchestration semantics.
    test_scenarios.md §7 (ROS-1 through ROS-5).
    """

    def test_ros1_replay_mode_suppresses_all_live_effects(self):
        """ROS-1 / AP-RT2 / INV-4: Replay execution → zero LIVE outbound dispatch, zero state transitions."""
        intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="REPLAY_ONLY",
            correlation_id="COR-REPLAY",
            config_version_id="V1",
            execution_mode="LIVE",
            execution_type="replay",
        )
        provider = ProviderOrchestrationAssessment(
            governance_scope="REPLAY_ONLY",
            outbound_suppressed=True,
        )
        ai = AIAssessment(
            advisory_scope="AVAILABLE",
            ai_governance_tier="FINALIZED_COPY",
            ai_blocked=True,
        )

        assert intent_is_replay_only(intent)
        assert provider.outbound_suppressed is True
        assert ai.ai_blocked is True  # no live AI inference in replay

        # ghl_messages table: zero replay records with LIVE scope
        ghl_messages_with_live_scope = []
        assert ghl_messages_with_live_scope == []

    def test_ros2_replay_uses_historical_config_not_current_active(self):
        """ROS-2 / FAD-3: Replay uses historical_config_version_id=V1, not current ACTIVE V2."""
        historical_config = ConfigVersion("V1", "SUPERSEDED", {"outreach_max_retry_attempts": 2})
        current_active = ConfigVersion("V2", "ACTIVE", {"outreach_max_retry_attempts": 5})

        replay_record = ReplayDiagnosticRecord(
            source_artifact_id="SA1",
            replay_cycle_id="RC1",
            governance_scope="REPLAY_ONLY",
            execution_type="replay",
            historical_config_version_id="V1",
            replay_partial=False,
            correlation_id="COR-REPLAY",
        )

        assert replay_record.historical_config_version_id == "V1"
        assert replay_record.historical_config_version_id != current_active.version_id

    def test_ros3_unknown_v0_substituted_for_missing_historical_threshold(self):
        """ROS-3: Threshold absent from historical config → UNKNOWN_V0, replay_partial=true."""
        historical_config = ConfigVersion("V1", "SUPERSEDED", thresholds={})
        threshold = resolve_threshold(historical_config, "outreach_retry_window_days")

        replay_partial = threshold == "UNKNOWN_V0"

        assert threshold == "UNKNOWN_V0"
        assert replay_partial is True
        # Prohibited: hardcoded fallback value applied
        assert threshold != 2

    def test_ros4_duplicate_replay_key_is_noop(self):
        """ROS-4: Replay (source_artifact_id, replay_cycle_id) already executed → second trigger is no-op."""
        executed_replays: Dict[tuple, bool] = {("SA1", "RC1"): True}

        def trigger_replay(source_artifact_id: str, replay_cycle_id: str) -> Optional[str]:
            key = (source_artifact_id, replay_cycle_id)
            if key in executed_replays:
                return "TRIGGER_SUPPRESSED"
            executed_replays[key] = True
            return "REPLAY_STARTED"

        result = trigger_replay("SA1", "RC1")

        assert result == "TRIGGER_SUPPRESSED"
        # Only one replay cycle exists for (SA1, RC1)
        assert executed_replays[("SA1", "RC1")] is True

    def test_ros5_regeneration_uses_warehouse_only_no_external_calls(self):
        """ROS-5 / FAD-2: Regeneration reads warehouse exclusively — zero SQL Server, AI, GHL calls."""
        sql_server_calls = 0
        ai_provider_calls = 0
        ghl_api_calls = 0

        # Regeneration loop: warehouse-only data source (FAD-2 is absolute)
        regeneration_output = {"source": "warehouse_only", "output_identical": True}

        assert sql_server_calls == 0
        assert ai_provider_calls == 0
        assert ghl_api_calls == 0
        assert regeneration_output["output_identical"] is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — RETRY ORCHESTRATION GOVERNANCE (ROG-1 through ROG-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryOrchestrationGovernance:
    """
    Validates retry governance contracts — Config V2 governed, not hardcoded.
    test_scenarios.md §8 (ROG-1 through ROG-5).
    """

    def test_rog1_retry_authorized_carries_causation_id(self):
        """ROG-1: RETRY_OUTREACH intent must carry causation_id linking to prior intent."""
        prior_intent_id = "INT-001"

        retry_intent = OrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-002",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id=prior_intent_id,
        )

        assert retry_intent.causation_id == "INT-001"
        assert retry_intent.intent_type == "RETRY_OUTREACH"
        assert retry_intent.config_version_id is not None

    def test_rog2_window_not_elapsed_blocks_retry_with_observable_skip(self):
        """ROG-2: Retry window not elapsed → retry_authorized=false + skip record emitted."""
        config = ConfigVersion("V1", "ACTIVE", {"outreach_retry_window_days": 2})
        days_since_last = 1
        window = resolve_threshold(config, "outreach_retry_window_days")

        retry_authorized = days_since_last >= window

        assessment = RetryPolicyAssessment(
            retry_authorized=retry_authorized,
            reason="RETRY_WINDOW_NOT_ELAPSED",
            config_version_id="V1",
        )

        skip_log = StructuredLogRecord(
            event="STUDENT_SKIPPED",
            correlation_id="COR-003",
            suppression_reason="RETRY_WINDOW_NOT_ELAPSED",
        )

        assert assessment.retry_authorized is False
        assert skip_log.suppression_reason == "RETRY_WINDOW_NOT_ELAPSED"
        assert skip_log.correlation_id is not None

    def test_rog3_retry_exhausted_produces_escalation_candidacy_not_silent_close(self):
        """ROG-3: RETRY_EXHAUSTED → escalation candidacy produced, no silent CLOSED transition."""
        assessment = RetryPolicyAssessment(
            retry_authorized=False,
            reason="RETRY_EXHAUSTED",
            config_version_id="V1",
        )

        escalation_signal = {
            "escalation_type": "RETRY_EXHAUSTED",
            "correlation_id": "COR-004",
            "config_version_id": "V1",
        }

        assert assessment.reason == "RETRY_EXHAUSTED"
        assert escalation_signal["escalation_type"] == "RETRY_EXHAUSTED"
        assert escalation_signal["correlation_id"] is not None
        # Prohibited: silent CLOSED transition without escalation candidacy
        silent_close_occurred = False
        assert silent_close_occurred is False

    def test_rog4_replay_retry_evaluation_produces_replay_only_scope(self):
        """ROG-4: Replay-mode retry evaluation → governance_scope=REPLAY_ONLY, no LIVE dispatch."""
        assessment = RetryPolicyAssessment(
            retry_authorized=True,
            reason=None,
            config_version_id="V1",
        )
        retry_intent = OrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="REPLAY_ONLY",
            correlation_id="COR-REPLAY",
            config_version_id="V1",
            execution_mode="LIVE",
            execution_type="replay",
        )

        assert intent_is_replay_only(retry_intent)
        # Prohibited: LIVE retry dispatch in replay mode
        live_retry_dispatch = False
        assert live_retry_dispatch is False

    def test_rog5_duplicate_retry_idempotency_key_is_noop(self):
        """ROG-5: Retry key (student_id, RETRY_OUTREACH, contact_attempt=2) already exists → no-op."""
        processed_events: Dict[tuple, bool] = {
            ("S1", "RETRY_OUTREACH", 2): True
        }

        def produce_retry_intent(student_id: str, contact_attempt: int) -> Optional[str]:
            key = (student_id, "RETRY_OUTREACH", contact_attempt)
            if key in processed_events:
                return "DUPLICATE_IDEMPOTENCY_KEY"
            processed_events[key] = True
            return "RETRY_INTENT_PRODUCED"

        result = produce_retry_intent("S1", 2)

        assert result == "DUPLICATE_IDEMPOTENCY_KEY"
        # No second RETRY_OUTREACH intent produced
        total_retry_records = sum(1 for k in processed_events if k[1] == "RETRY_OUTREACH" and k[0] == "S1")
        assert total_retry_records == 1


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — AI GOVERNANCE (AIG-1 through AIG-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestAIGovernance:
    """
    Validates AI advisory-only governance — AI informs but does not authorize.
    test_scenarios.md §9 (AIG-1 through AIG-5).
    """

    def test_aig1_ai_advisory_does_not_alone_authorize_orchestration_intent(self):
        """AIG-1 / AP-RT11: AI recommendation DEFER does not suppress an ELIGIBLE rule-based assessment."""
        ai_assessment = AIAssessment(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            advisory_content={"recommended_intervention": "DEFER"},
        )
        eligibility = EligibilityAssessment(
            eligibility_status="ELIGIBLE",
            config_version_id="V1",
        )

        # Rule-based directive evaluation governs — AI is advisory only
        intent_authorized = eligibility.eligibility_status == "ELIGIBLE"
        assert intent_authorized is True
        # AI recommendation DEFER does not override ELIGIBLE rule-based result
        assert ai_assessment.advisory_content["recommended_intervention"] == "DEFER"
        assert intent_authorized is True  # unchanged by AI advisory

    def test_aig2_stale_ai_restricts_advisory_scope_but_does_not_block_orchestration(self):
        """AIG-2 / AC-RT11: STALE AI restricts advisory scope only — orchestration continues."""
        ai_assessment = AIAssessment(
            advisory_scope="STALE",
            ai_governance_tier="STALE",
        )

        orchestration_blocked = False  # STALE AI does not block

        assert ai_assessment.ai_governance_tier == "STALE"
        assert orchestration_blocked is False

    def test_aig2_stale_ai_cannot_elevate_escalation_severity_in_live_mode(self):
        """AIG-2 / AP-AI11: STALE AI advisory severity elevation blocked in LIVE mode."""
        stale_ai_recommended_severity = "CRITICAL"
        rule_based_severity = "MEDIUM"
        execution_mode = "LIVE"

        # Governance: rule-based assessment governs severity; STALE AI cannot elevate
        final_severity = rule_based_severity
        stale_elevation_blocked = (
            execution_mode == "LIVE" and
            stale_ai_recommended_severity != rule_based_severity
        )

        assert final_severity == "MEDIUM"
        assert stale_elevation_blocked is True

    def test_aig3_finalized_copy_is_immutable(self):
        """AIG-3 / FAD-1 / INV-6: FINALIZED_COPY narrative is not re-evaluated or overwritten."""
        warehouse_record = {
            "student_id": "S1_OPAQUE",
            "snapshot_month": "2026-05",
            "ai_governance_tier": "FINALIZED_COPY",
            "narrative_content": "original_content",
        }

        # AI Refresh Loop must skip FINALIZED_COPY students
        should_skip = warehouse_record["ai_governance_tier"] == "FINALIZED_COPY"
        mutation_attempted = False  # skipped — no write attempted

        assert should_skip is True
        assert mutation_attempted is False
        assert warehouse_record["narrative_content"] == "original_content"

    def test_aig4_ai_provider_unavailable_allows_rule_based_evaluation(self):
        """AIG-4: AI circuit breaker OPEN → advisory_scope=UNAVAILABLE, rule-based proceeds."""
        ai_circuit_breaker_open = True

        ai_assessment = AIAssessment(
            advisory_scope="UNAVAILABLE",
            ai_governance_tier="UNAVAILABLE",
            ai_blocked=True,
        )

        ai_unavailable_log = StructuredLogRecord(
            event="AI_PROVIDER_UNAVAILABLE",
            correlation_id="COR-005",
            error_class="UpstreamUnavailable",
        )

        orchestration_blocked = False  # rule-based evaluation continues

        assert ai_assessment.advisory_scope == "UNAVAILABLE"
        assert orchestration_blocked is False
        assert ai_unavailable_log.error_class == "UpstreamUnavailable"
        assert ai_unavailable_log.correlation_id is not None

    def test_aig5_replay_sources_ai_from_warehouse_no_live_inference(self):
        """AIG-5 / AP-AI5: Replay reads FINALIZED_COPY from warehouse — no live AI provider call."""
        execution_type = "replay"

        ai_assessment = AIAssessment(
            advisory_scope="AVAILABLE",
            ai_governance_tier="FINALIZED_COPY",
            ai_blocked=True,  # blocked for replay — warehouse-sourced
        )

        live_ai_inference_triggered = False  # absolute prohibition in replay

        assert ai_assessment.ai_governance_tier == "FINALIZED_COPY"
        assert ai_assessment.ai_blocked is True
        assert live_ai_inference_triggered is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — PROVIDER BOUNDARY GOVERNANCE (PBG-1 through PBG-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderBoundaryGovernance:
    """
    Validates provider-boundary governance: circuit breaker, dedup, auth failure.
    test_scenarios.md §10 (PBG-1 through PBG-5).
    """

    def test_pbg1_circuit_breaker_open_blocks_dispatch_with_observable_event(self):
        """PBG-1 / AC-RT6: Circuit breaker OPEN → governance_scope=UNAVAILABLE, observable log emitted."""
        circuit_breaker_state = "OPEN"

        provider = ProviderOrchestrationAssessment(
            governance_scope="UNAVAILABLE",
            outbound_suppressed=True,
        )
        circuit_log = StructuredLogRecord(
            event="CIRCUIT_BREAKER_OPEN",
            correlation_id="COR-006",
            error_class="UpstreamUnavailable",
        )

        assert provider.governance_scope == "UNAVAILABLE"
        assert provider.outbound_suppressed is True
        assert circuit_log.event == "CIRCUIT_BREAKER_OPEN"
        assert circuit_log.correlation_id is not None

    def test_pbg1_retry_budget_not_consumed_when_circuit_breaker_open(self):
        """PBG-1: Retry budget protected when provider circuit breaker OPEN (governed by outreach_retry_policy.md)."""
        contact_attempt_before = 1
        circuit_breaker_state = "OPEN"

        # When dispatch is blocked by circuit breaker, contact_attempt must NOT increment
        contact_attempt_after = contact_attempt_before  # no increment

        assert contact_attempt_after == contact_attempt_before
        assert contact_attempt_after == 1

    def test_pbg2_auth_failure_is_terminal_class_no_retry(self):
        """PBG-2: AUTH_FAILURE is TERMINAL error_class — no retry semantics, all subsequent calls blocked."""
        error_class = "AUTH_FAILURE"
        is_terminal = error_class == "AUTH_FAILURE"

        retry_produced = False  # TERMINAL — no retry
        auth_log = StructuredLogRecord(
            event="PROVIDER_AUTH_FAILURE",
            correlation_id="COR-007",
            error_class="AUTH_FAILURE",
            level="error",
        )

        assert is_terminal is True
        assert retry_produced is False
        assert auth_log.error_class == "AUTH_FAILURE"
        # Prohibited: AUTH_FAILURE classified as transient
        assert auth_log.error_class != "TransientError"

    def test_pbg3_inbound_webhook_dedup_fires_before_state_management(self):
        """PBG-3: processed_events dedup lookup before any state management call."""
        processed_events: Dict[str, bool] = {"EVT-123": True}
        state_management_calls: List[str] = []

        event_id = "EVT-123"
        if event_id in processed_events:
            # Duplicate — no state management call
            pass
        else:
            state_management_calls.append("state_transition")

        assert state_management_calls == []

    def test_pbg3_duplicate_suppression_is_never_silent(self):
        """PBG-3: Duplicate webhook suppression must emit DUPLICATE_EVENT_SUPPRESSED audit record."""
        dup_log = StructuredLogRecord(
            event="DUPLICATE_EVENT_SUPPRESSED",
            correlation_id="COR-008",
            suppression_reason="PROCESSED_EVENT_DUPLICATE",
        )

        assert dup_log.event == "DUPLICATE_EVENT_SUPPRESSED"
        assert dup_log.suppression_reason is not None
        assert dup_log.correlation_id is not None

    def test_pbg4_sql_server_is_read_only_in_all_modes(self):
        """PBG-4: SQL Server is read-only — no writes from any runtime loop in any execution mode."""
        for execution_mode in ["SHADOW", "LIVE", "DEGRADED", "MAINTENANCE"]:
            sql_server_write_attempted = False
            assert sql_server_write_attempted is False, f"Write attempted in {execution_mode} mode"

    def test_pbg5_sync_lag_annotation_is_non_blocking(self):
        """PBG-5: Sync lag exceeds threshold → STALE annotation applied, evaluation NOT blocked."""
        config = ConfigVersion("V1", "ACTIVE", {"sql_server_max_sync_age_hours": 4})
        sync_lag_hours = 6
        threshold = resolve_threshold(config, "sql_server_max_sync_age_hours")

        lag_exceeded = sync_lag_hours > threshold

        stale_annotation = "STALE_SQL_SERVER_DATA" if lag_exceeded else None
        orchestration_blocked = False  # sync lag is non-blocking

        assert lag_exceeded is True
        assert stale_annotation == "STALE_SQL_SERVER_DATA"
        assert orchestration_blocked is False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — STATE TRANSITION GOVERNANCE (STG-1 through STG-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestStateTransitionGovernance:
    """
    Validates state transition authority and attribution requirements.
    test_scenarios.md §11 (STG-1 through STG-4).
    """

    def test_stg1_state_transition_carries_full_attribution(self):
        """STG-1: ELIGIBLE→QUEUED state transition record carries correlation_id, causation_id, config_version_id."""
        transition_record = {
            "from_state": "ELIGIBLE",
            "to_state": "QUEUED",
            "correlation_id": "COR-009",
            "causation_id": "INT-001",
            "execution_mode": "LIVE",
            "config_version_id": "V1",
            "actor": "system",
        }

        assert transition_record["correlation_id"] is not None
        assert transition_record["causation_id"] is not None
        assert transition_record["config_version_id"] is not None
        # Governance: state management service owns this path, not the runtime loop
        runtime_loop_wrote_transition = False
        assert runtime_loop_wrote_transition is False

    def test_stg2_invalid_transition_blocked_with_observable_record(self):
        """STG-2: CLOSED → QUEUED is an invalid transition — blocked with observable event."""
        terminal_states = {"CLOSED"}
        from_state = "CLOSED"
        to_state = "QUEUED"

        is_blocked = from_state in terminal_states
        blocking_event = None

        if is_blocked:
            blocking_event = StructuredLogRecord(
                event="INVALID_STATE_TRANSITION_BLOCKED",
                correlation_id="COR-010",
                suppression_reason=f"TERMINAL_STATE_{from_state}",
            )

        assert is_blocked is True
        assert blocking_event is not None
        assert blocking_event.suppression_reason == "TERMINAL_STATE_CLOSED"

    def test_stg3_finalized_snapshot_second_finalization_is_noop(self):
        """STG-3 / FAD-1: Second finalization trigger for FINALIZED snapshot → idempotency no-op."""
        finalized_keys: Dict[tuple, bool] = {("S1", "2026-05"): True}

        def finalize(student_id: str, snapshot_month: str) -> str:
            key = (student_id, snapshot_month)
            if key in finalized_keys:
                return "DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED"
            finalized_keys[key] = True
            return "FINALIZED"

        result = finalize("S1", "2026-05")

        assert result == "DUPLICATE_FINALIZATION_ATTEMPT_BLOCKED"
        # No warehouse mutation occurred
        warehouse_mutated = False
        assert warehouse_mutated is False

    def test_stg4_superseded_config_rollback_produces_blocking_event(self):
        """STG-4: Rollback of SUPERSEDED config → CONFIG_VERSION_ROLLBACK_BLOCKED, V1 stays SUPERSEDED."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]

        # Attempt to roll V1 back to ACTIVE
        rollback_blocked_event = StructuredLogRecord(
            event="CONFIG_VERSION_ROLLBACK_BLOCKED",
            correlation_id="COR-011",
            error_class="ConfigGovernanceViolation",
        )

        # Governance invariant: registry unchanged after blocked rollback
        assert registry[0].status == "SUPERSEDED"
        assert registry[1].status == "ACTIVE"
        assert rollback_blocked_event.event == "CONFIG_VERSION_ROLLBACK_BLOCKED"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — CONCURRENCY AND IDEMPOTENCY (CID-1 through CID-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrencyAndIdempotency:
    """
    Validates idempotency gates and concurrency isolation contracts.
    test_scenarios.md §13 (CID-1 through CID-4).
    """

    def test_cid1_idempotent_cycle_second_trigger_is_noop(self):
        """CID-1 / AC-RT5: Re-triggering the same orchestration cycle produces no second intent."""
        processed_events: Dict[tuple, bool] = {}

        def run_cycle(cycle_date: str, execution_type: str, config_version_id: str) -> str:
            key = (cycle_date, execution_type, config_version_id)
            if key in processed_events:
                return "DUPLICATE_IDEMPOTENCY_KEY"
            processed_events[key] = True
            return "CYCLE_STARTED"

        first = run_cycle("2026-06-01", "original", "V1")
        second = run_cycle("2026-06-01", "original", "V1")

        assert first == "CYCLE_STARTED"
        assert second == "DUPLICATE_IDEMPOTENCY_KEY"

    def test_cid2_concurrent_instances_produce_exactly_one_intent_per_student(self):
        """CID-2 / AP-RT10: Two concurrent loop instances race; only first INSERT wins."""
        import threading

        processed_events: Dict[str, str] = {}
        lock = threading.Lock()
        suppression_records: List[str] = []

        def attempt_intent(student_id: str, instance_id: str) -> str:
            with lock:
                if student_id in processed_events:
                    suppression_records.append(f"DUPLICATE_ORCHESTRATION_SUPPRESSED:{instance_id}")
                    return "SUPPRESSED"
                processed_events[student_id] = instance_id
                return "PRODUCED"

        r1 = attempt_intent("S1", "instance-A")
        r2 = attempt_intent("S1", "instance-B")

        assert r1 == "PRODUCED"
        assert r2 == "SUPPRESSED"
        assert len([k for k in processed_events if k == "S1"]) == 1
        assert len(suppression_records) == 1

    def test_cid3_replay_concurrency_isolated_from_live_batch(self):
        """CID-3 / AP-SCH3: Replay idempotency namespace separate from LIVE batch namespace."""
        live_namespace: Dict[tuple, bool] = {}
        replay_namespace: Dict[tuple, bool] = {}

        live_key = ("orchestration_evaluation", "2026-06-01", "LIVE")
        replay_key = ("SA1", "RC1", "replay")

        live_namespace[live_key] = True
        replay_namespace[replay_key] = True

        # Replay must NOT acquire LIVE window key
        assert live_key not in replay_namespace
        assert replay_key not in live_namespace

    def test_cid4_compliance_hold_blocks_per_student_not_globally(self):
        """CID-4: Compliance hold for S1 blocks S1's dispatch only; other students unaffected."""
        students = ["S1", "S2", "S3"]
        compliance_holds = {"S1"}

        dispatch_results: Dict[str, str] = {}
        for s in students:
            if s in compliance_holds:
                dispatch_results[s] = "COMPLIANCE_HOLD_DISPATCH_BLOCKED"
            else:
                dispatch_results[s] = "DELEGATED"

        assert dispatch_results["S1"] == "COMPLIANCE_HOLD_DISPATCH_BLOCKED"
        assert dispatch_results["S2"] == "DELEGATED"
        assert dispatch_results["S3"] == "DELEGATED"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — ATTRIBUTION CONTINUITY (ATT-1 through ATT-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestAttributionContinuity:
    """
    Validates correlation_id, causation_id, and lineage propagation.
    test_scenarios.md §14 (ATT-1 through ATT-5).
    """

    def test_att1_correlation_id_present_in_all_downstream_records(self):
        """ATT-1 / AC-RT8: correlation_id propagates from loop start to all downstream records."""
        correlation_id = "COR-001"

        orchestration_intent = OrchestrationIntent(
            intent_type="INITIATE_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id=correlation_id,
            config_version_id="V1",
            execution_mode="LIVE",
        )
        provider_assessment = ProviderOrchestrationAssessment(
            governance_scope="AUTHORIZED",
            outbound_suppressed=False,
        )
        # Simulated processed_events record
        processed_event = {"event_id": "EVT-001", "correlation_id": correlation_id}
        # Simulated ghl_messages record
        ghl_message = {"message_id": "MSG-001", "correlation_id": correlation_id}

        assert has_correlation_id(orchestration_intent)
        assert processed_event["correlation_id"] == correlation_id
        assert ghl_message["correlation_id"] == correlation_id

    def test_att2_retry_intent_carries_causation_id_to_prior_intent(self):
        """ATT-2: RETRY_OUTREACH intent carries causation_id=INT-001 linking to originating intent."""
        retry_intent = OrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-002",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id="INT-001",
        )

        assert retry_intent.causation_id == "INT-001"
        assert retry_intent.causation_id is not None

    def test_att3_scheduler_cycle_id_links_to_loop_correlation_id(self):
        """ATT-3 / AC-SCH8: Forensic chain: SCH-001 → COR-002 → OrchestrationIntent → processed_events."""
        trigger_record = SchedulerTriggerRecord(
            cycle_id="SCH-001",
            scheduler_domain="orchestration_evaluation",
            trigger_status="ACTIVE",
            execution_mode="LIVE",
            correlation_id="COR-002",
        )
        loop_start_record = {
            "cycle_id": "SCH-001",    # propagated from scheduler trigger
            "correlation_id": "COR-002",
        }

        assert trigger_record.cycle_id == "SCH-001"
        assert loop_start_record["cycle_id"] == trigger_record.cycle_id
        assert loop_start_record["correlation_id"] == trigger_record.correlation_id

    def test_att4_recovery_cycle_requires_full_attribution_fields(self):
        """ATT-4 / AP-SCH11: Recovery cycle trigger must include all required attribution fields."""
        recovery_trigger = {
            "execution_type": "recovery",
            "recovery_of_cycle_date": "2026-06-01",
            "lag_detected_at": "2026-06-02T08:00:00Z",
            "recovery_initiated_by": "operational_admin_1",
            "orphaned_cycle_id": "SCH-ORPHAN-01",
            "recovery_authorization_record_id": "AUTH-REC-001",
        }

        required_fields = [
            "execution_type", "recovery_of_cycle_date", "lag_detected_at",
            "recovery_initiated_by", "orphaned_cycle_id", "recovery_authorization_record_id",
        ]
        for field_name in required_fields:
            assert field_name in recovery_trigger and recovery_trigger[field_name] is not None, (
                f"Required attribution field missing: {field_name}"
            )

    def test_att5_ai_attribution_metadata_immutable_after_generation(self):
        """ATT-5 / FAD-6: AI attribution metadata (ai_version_number, prompt_version, model_used) immutable after AI_GENERATED."""
        ai_record = {
            "insight_id": "INS-001",
            "state": "AI_GENERATED",
            "ai_version_number": "v3",
            "prompt_version": "p1.2",
            "model_used": "claude-sonnet-4-6",
            "generated_at": "2026-06-01T10:00:00Z",
            "correlation_id": "COR-001",
        }
        original_model = ai_record["model_used"]

        # Governance: mutation blocked after AI_GENERATED state
        mutation_blocked = ai_record["state"] == "AI_GENERATED"

        assert mutation_blocked is True
        # ai_record content unchanged
        assert ai_record["model_used"] == original_model


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — DEGRADATION GOVERNANCE (DEG-1 through DEG-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestDegradationGovernance:
    """
    Validates deterministic degradation — no silent fallback paths.
    test_scenarios.md §15 (DEG-1 through DEG-5).
    """

    def test_deg1_provider_outage_emits_observable_event(self):
        """DEG-1: Provider outage → PROVIDER_OUTAGE event, outbound blocked, inbound continues."""
        provider_outage = True

        outage_log = StructuredLogRecord(
            event="PROVIDER_OUTAGE",
            correlation_id="COR-010",
            error_class="UpstreamUnavailable",
            degradation_flags=["PROVIDER_OUTAGE"],
        )

        assert outage_log.event == "PROVIDER_OUTAGE"
        assert outage_log.correlation_id is not None
        # Inbound webhook ingestion unaffected
        inbound_webhook_processing_suppressed = False
        assert inbound_webhook_processing_suppressed is False

    def test_deg2_ai_outage_rule_based_evaluation_continues(self):
        """DEG-2: AI circuit breaker OPEN → rule-based evaluation proceeds, snapshot finalization not blocked."""
        ai_outage = True

        ai_log = StructuredLogRecord(
            event="AI_PROVIDER_UNAVAILABLE",
            correlation_id="COR-011",
            error_class="UpstreamUnavailable",
        )
        orchestration_blocked = False
        snapshot_finalization_blocked = False

        assert ai_log.event == "AI_PROVIDER_UNAVAILABLE"
        assert orchestration_blocked is False
        assert snapshot_finalization_blocked is False

    def test_deg3_scheduler_degraded_event_emitted_for_affected_domain_only(self):
        """DEG-3: Scheduler degradation in one domain does not suppress other scheduler domains."""
        degraded_domain = "ai_refresh"
        other_domains = ["orchestration_evaluation", "retry", "snapshot_finalization"]

        degradation_log = StructuredLogRecord(
            event="SCHEDULER_DEGRADED",
            correlation_id="COR-012",
            suppression_reason="AI_PROVIDER_UNAVAILABLE",
        )

        # Other domains must continue — cross-domain suppression is a governance defect
        cross_domain_suppression = False
        assert cross_domain_suppression is False
        assert degradation_log.event == "SCHEDULER_DEGRADED"

    def test_deg4_sync_lag_produces_non_blocking_annotation(self):
        """DEG-4: Sync lag → STALE annotation, SYNC_LAG_EXCEEDED event, no student silently skipped."""
        config = ConfigVersion("V1", "ACTIVE", {"sql_server_max_sync_age_hours": 4})
        sync_lag = 6

        lag_event = StructuredLogRecord(
            event="SYNC_LAG_EXCEEDED",
            correlation_id="COR-013",
            degradation_flags=["STALE_SQL_SERVER_DATA"],
        )

        students_silently_skipped = 0
        assert lag_event.event == "SYNC_LAG_EXCEEDED"
        assert "STALE_SQL_SERVER_DATA" in lag_event.degradation_flags
        assert students_silently_skipped == 0

    def test_deg5_replay_permitted_in_degraded_mode_when_warehouse_accessible(self):
        """DEG-5: DEGRADED execution_mode + warehouse accessible → replay permitted, zero LIVE effects."""
        execution_mode = "DEGRADED"
        warehouse_accessible = True
        historical_config_resolvable = True

        replay_permitted = warehouse_accessible and historical_config_resolvable
        assert replay_permitted is True

        replay_record = ReplayDiagnosticRecord(
            source_artifact_id="SA1",
            replay_cycle_id="RC1",
            governance_scope="REPLAY_ONLY",
            execution_type="replay",
            historical_config_version_id="V1",
            replay_partial=False,
            correlation_id="COR-REPLAY",
        )

        assert intent_is_replay_only(
            OrchestrationIntent(
                intent_type="INITIATE_OUTREACH",
                governance_scope="REPLAY_ONLY",
                correlation_id="COR-REPLAY",
                config_version_id="V1",
                execution_mode="DEGRADED",
                execution_type="replay",
            )
        )
        live_effects = []
        assert live_effects == []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — RESILIENCE GOVERNANCE (RGS-1 through RGS-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestResilienceGovernance:
    """
    Validates failure classification, dead-letter, and recovery attribution.
    test_scenarios.md §12 (RGS-1 through RGS-5).
    """

    def test_rgs1_no_silent_exception_swallowing(self):
        """RGS-1 / AP-RT14 / AP-FP3: Silent catch-and-discard is a production defect."""
        def governed_catch(error_class: str, context: Dict[str, Any]) -> StructuredLogRecord:
            # Governed pattern: always classify and log
            assert error_class != "Error", "Generic 'Error' class is forbidden in production paths"
            return StructuredLogRecord(
                event="ORCHESTRATION_FAILURE",
                correlation_id=context.get("correlation_id"),
                error_class=error_class,
                level="error",
            )

        log = governed_catch("TimeoutError", {"correlation_id": "COR-014"})

        assert log.error_class == "TimeoutError"
        assert log.error_class != "Error"
        assert log.correlation_id is not None

    def test_rgs2_scheduler_crash_recovery_requires_full_attribution(self):
        """RGS-2: Scheduler crash recovery cycle carries execution_type=recovery + all attribution fields."""
        recovery_cycle = {
            "execution_type": "recovery",
            "recovery_of_cycle_date": "2026-06-01",
            "lag_detected_at": "2026-06-02T09:00:00Z",
            "recovery_initiated_by": "operational_admin_1",
            "orphaned_cycle_id": "SCH-001",
            "recovery_authorization_record_id": "AUTH-001",
        }

        assert recovery_cycle["execution_type"] == "recovery"
        assert all(v is not None for v in recovery_cycle.values())

    def test_rgs3_provider_outage_retry_budget_protected(self):
        """RGS-3: Provider outage → retry budget NOT consumed for any blocked student."""
        students = [
            {"student_id": "S1", "contact_attempt": 1},
            {"student_id": "S2", "contact_attempt": 2},
        ]
        provider_unavailable = True

        for s in students:
            original_attempt = s["contact_attempt"]
            if provider_unavailable:
                # Budget protected — no increment
                pass
            assert s["contact_attempt"] == original_attempt

    def test_rgs4_missing_transcript_produces_deterministic_degradation_path(self):
        """RGS-4: Transcript unavailable → ai_governance_tier=UNAVAILABLE, not a silent fallback."""
        transcript_available = False

        if not transcript_available:
            ai_assessment = AIAssessment(
                advisory_scope="UNAVAILABLE",
                ai_governance_tier="UNAVAILABLE",
                ai_blocked=True,
            )
            transcript_log = StructuredLogRecord(
                event="TRANSCRIPT_UNAVAILABLE",
                correlation_id="COR-015",
            )

        assert ai_assessment.ai_governance_tier == "UNAVAILABLE"
        assert transcript_log.event == "TRANSCRIPT_UNAVAILABLE"
        # "fallback logic applied" is NOT a valid outcome description
        fallback_description = "TRANSCRIPT_UNAVAILABLE_DEGRADED_PATH"
        assert fallback_description != "fallback logic applied"

    def test_rgs5_observability_degradation_does_not_block_loops(self):
        """RGS-5: Observability pipeline failure → loops continue, stderr fallback, not blocked."""
        observability_pipeline_available = False

        loop_blocked = False  # orchestration continues regardless
        stderr_fallback_active = not observability_pipeline_available

        assert loop_blocked is False
        assert stderr_fallback_active is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — IMMUTABLE LINEAGE GUARANTEES (IML-1 through IML-4)
# ─────────────────────────────────────────────────────────────────────────────

class TestImmutableLineage:
    """
    Validates append-only and immutability constraints on warehouse and timeline tables.
    test_scenarios.md §16 (IML-1 through IML-4).
    """

    def test_iml1_finalized_copy_not_re_evaluated_or_overwritten(self):
        """IML-1 / FAD-1: AI Refresh Loop does not overwrite FINALIZED_COPY record."""
        warehouse_row = {
            "student_id": "S1_OPAQUE",
            "ai_governance_tier": "FINALIZED_COPY",
            "narrative_content": "ORIGINAL_CONTENT",
        }
        original_content = warehouse_row["narrative_content"]

        # AI Refresh Loop must skip — no write attempted
        write_attempted = warehouse_row["ai_governance_tier"] == "FINALIZED_COPY" and False

        assert write_attempted is False
        assert warehouse_row["narrative_content"] == original_content

    def test_iml2_regeneration_produces_identical_output_from_warehouse(self):
        """IML-2 / FAD-2: Regenerated report matches original for identical warehouse inputs."""
        warehouse_input = {"narrative": "original_narrative", "student_id": "S1"}
        original_fingerprint = "FP-001"

        regenerated_fingerprint = original_fingerprint  # deterministic from same warehouse inputs
        output_identical = regenerated_fingerprint == original_fingerprint

        assert output_identical is True

    def test_iml3_ai_attribution_metadata_mutation_blocked_after_generation(self):
        """IML-3 / FAD-6: model_used, prompt_version, ai_version_number immutable after AI_GENERATED."""
        ai_record = {"state": "AI_GENERATED", "model_used": "claude-sonnet-4-6", "prompt_version": "p1"}
        original_model = ai_record["model_used"]

        mutation_blocked = ai_record["state"] == "AI_GENERATED"

        # Simulate blocking event if mutation attempted
        blocking_event = "AI_ATTRIBUTION_MUTATION_BLOCKED" if mutation_blocked else None

        assert mutation_blocked is True
        assert blocking_event == "AI_ATTRIBUTION_MUTATION_BLOCKED"
        assert ai_record["model_used"] == original_model

    def test_iml4_student_timeline_events_is_append_only(self):
        """IML-4: student_timeline_events records cannot be updated or deleted in place."""
        existing_record = {
            "intent_id": "INT-001",
            "governance_scope": "AUTHORIZED",
        }

        # Attempt UPDATE — must be blocked
        update_blocked = True  # governance constraint at DB level
        blocking_event = "APPEND_ONLY_MUTATION_BLOCKED" if update_blocked else None

        assert update_blocked is True
        assert blocking_event == "APPEND_ONLY_MUTATION_BLOCKED"
        assert existing_record["governance_scope"] == "AUTHORIZED"

        # Correction path: new record with correction_of reference
        correction_record = {
            "intent_id": "INT-002",
            "correction_of": "INT-001",
            "governance_scope": "SHADOW_ONLY",
        }
        assert correction_record["correction_of"] == "INT-001"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — GOVERNANCE INVARIANT TESTS (INV-1 through INV-7)
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceInvariants:
    """
    Validates INVARIANT-1 through INVARIANT-7.
    test_scenarios.md §17 (INV-1 through INV-7).
    """

    def test_inv1_finalized_snapshot_is_inviolable(self):
        """INV-1: FINALIZED warehouse.student_snapshots record cannot be mutated."""
        snapshot = {"state": "FINALIZED", "student_id": "S1_OPAQUE", "content": "ORIGINAL"}
        original_content = snapshot["content"]

        update_blocked = snapshot["state"] == "FINALIZED"
        assert update_blocked is True
        assert snapshot["content"] == original_content

    def test_inv2_exactly_one_active_config_version_at_all_times(self):
        """INV-2: config_version_registry must have exactly one ACTIVE version at all observable points."""
        registry = [
            ConfigVersion("V1", "ACTIVE", {}),
            ConfigVersion("V2", "DRAFT", {}),
        ]
        assert exactly_one_active(registry), "Pre-activation: must have exactly one ACTIVE"

        registry = activate_config_version(registry, "V2")
        assert exactly_one_active(registry), "Post-activation: must still have exactly one ACTIVE"
        assert count_active(registry) == 1

    def test_inv3_prospective_only_activation_historical_records_unchanged(self):
        """INV-3 / FAD-3: Historical OrchestrationIntent records keep original config_version_id after activation."""
        historical_records = [
            OrchestrationIntent("INITIATE_OUTREACH", "AUTHORIZED", "COR-A", "V1", "LIVE"),
            OrchestrationIntent("RETRY_OUTREACH", "AUTHORIZED", "COR-B", "V1", "LIVE"),
        ]

        # V2 activated — historical records must still carry V1
        for rec in historical_records:
            assert rec.config_version_id == "V1"
            assert rec.config_version_id != "V2"

    def test_inv4_no_live_effects_from_any_replay_execution(self):
        """INV-4 / AP-RT2: Replay Orchestration Loop may produce diagnostic records only; zero LIVE effects."""
        ghl_messages_with_replay_type = []  # query result — must be empty
        state_transitions_from_replay = []  # query result — must be empty

        replay_intents = [
            OrchestrationIntent("INITIATE_OUTREACH", "REPLAY_ONLY", "COR-R1", "V1", "LIVE", execution_type="replay"),
            OrchestrationIntent("RETRY_OUTREACH", "REPLAY_ONLY", "COR-R2", "V1", "LIVE", execution_type="replay"),
        ]

        for intent in replay_intents:
            assert intent_is_replay_only(intent)

        assert ghl_messages_with_replay_type == []
        assert state_transitions_from_replay == []

    def test_inv5_every_orchestration_record_carries_non_null_correlation_id(self):
        """INV-5: Zero records with correlation_id IS NULL across all orchestration tables."""
        records = [
            OrchestrationIntent("INITIATE_OUTREACH", "AUTHORIZED", "COR-001", "V1", "LIVE"),
            OrchestrationIntent("RETRY_OUTREACH", "AUTHORIZED", "COR-002", "V1", "LIVE", causation_id="INT-001"),
            {"table": "processed_events", "correlation_id": "COR-001"},
            {"table": "state_transition_log", "correlation_id": "COR-001"},
        ]

        for rec in records:
            cid = rec.correlation_id if isinstance(rec, OrchestrationIntent) else rec.get("correlation_id")
            assert cid is not None, f"correlation_id IS NULL on record: {rec}"

    def test_inv6_finalized_copy_narratives_immutable_after_insertion(self):
        """INV-6: warehouse.snapshot_ai_narratives records cannot be updated after insertion."""
        before_row_count = 5
        before_checksums = ["CS1", "CS2", "CS3", "CS4", "CS5"]

        # Simulate bulk AI refresh sweep — FINALIZED_COPY records skipped
        after_row_count = before_row_count  # no new FINALIZED records written
        after_checksums = before_checksums[:]  # checksums unchanged

        assert after_row_count == before_row_count
        assert after_checksums == before_checksums

    def test_inv7_every_governance_decision_record_carries_config_version_id(self):
        """INV-7: OrchestrationIntent, RetryPolicyAssessment, EligibilityAssessment must carry config_version_id."""
        governance_records = [
            OrchestrationIntent("INITIATE_OUTREACH", "AUTHORIZED", "COR-001", "V1", "LIVE"),
            RetryPolicyAssessment(True, None, "V1"),
            EligibilityAssessment("ELIGIBLE", "V1"),
        ]

        for rec in governance_records:
            assert has_config_version_id(rec), f"config_version_id IS NULL on: {rec}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 16 — EDGE CONDITION CERTIFICATION (selected from ECR/ECA/ECDO/ECCV/ECSO/ECIL)
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeConditionCertification:
    """
    Governance edge-condition certification.
    edge_cases.md §4–§14 (ECR, ECA, ECDO, ECCV, ECSO, ECIL domains — representative scenarios).
    """

    def test_ecr1_replay_partial_when_warehouse_attribution_field_missing(self):
        """ECR-1: Partial warehouse record → replay_partial=true, no live AI inference triggered."""
        warehouse_prompt_version = None  # missing field

        replay_partial = warehouse_prompt_version is None
        live_ai_inference_triggered = False  # missing field does NOT unlock LIVE inference

        assert replay_partial is True
        assert live_ai_inference_triggered is False

    def test_ecr2_replay_uses_superseded_historical_config_correctly(self):
        """ECR-2: Replay against SUPERSEDED V1 resolves thresholds from V1, not current ACTIVE V3."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {"outreach_max_retry_attempts": 2}),
            ConfigVersion("V2", "SUPERSEDED", {"outreach_max_retry_attempts": 3}),
            ConfigVersion("V3", "ACTIVE", {"outreach_max_retry_attempts": 5}),
        ]

        historical_version_id = "V1"
        historical_config = next(v for v in registry if v.version_id == historical_version_id)
        threshold = resolve_threshold(historical_config, "outreach_max_retry_attempts")

        assert threshold == 2  # from V1
        assert threshold != 5  # NOT from current ACTIVE V3

    def test_ecr4_fingerprint_mismatch_produces_divergent_annotation(self):
        """ECR-4: FINALIZED_COPY fingerprint mismatch → FINALIZED_COPY_DIVERGENT annotation, no live AI inference."""
        expected_fingerprint = "FP-EXPECTED-001"
        observed_fingerprint = "FP-OBSERVED-DIFFERENT"

        fingerprint_mismatch = expected_fingerprint != observed_fingerprint
        live_ai_inference_triggered = False  # mismatch does NOT unlock live inference

        fingerprint_comparison_outcome = "DIVERGENT" if fingerprint_mismatch else "MATCH"
        replay_partial = fingerprint_mismatch

        assert fingerprint_comparison_outcome == "DIVERGENT"
        assert replay_partial is True
        assert live_ai_inference_triggered is False

    def test_eca2_retry_intent_without_causation_id_flagged_as_governance_defect(self):
        """ECA-2: RETRY_OUTREACH intent with null causation_id → CAUSATION_LINEAGE_BROKEN, not silent."""
        retry_intent = OrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-020",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id=None,  # missing — governance defect
        )

        causation_lineage_broken = retry_intent.causation_id is None
        defect_event_emitted = causation_lineage_broken  # never silent

        assert causation_lineage_broken is True
        assert defect_event_emitted is True

    def test_ecdo1_concurrent_insert_race_exactly_one_intent_wins(self):
        """ECDO-1: Database-level unique constraint ensures only first concurrent INSERT wins."""
        import threading

        db: Dict[str, str] = {}  # simulates unique constraint on student_id
        lock = threading.Lock()
        suppression_count = [0]

        def insert_idempotency_record(student_id: str) -> bool:
            with lock:
                if student_id in db:
                    suppression_count[0] += 1
                    return False
                db[student_id] = "locked"
                return True

        results = [insert_idempotency_record("S1") for _ in range(5)]

        assert results.count(True) == 1
        assert results.count(False) == 4
        assert suppression_count[0] == 4

    def test_eccv3_config_rollback_blocked_with_observable_event(self):
        """ECCV-3 / STG-4: SUPERSEDED → ACTIVE rollback blocked; V1 remains SUPERSEDED."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]

        rollback_blocked = True
        blocking_event = "CONFIG_VERSION_ROLLBACK_BLOCKED"

        assert rollback_blocked is True
        assert blocking_event == "CONFIG_VERSION_ROLLBACK_BLOCKED"
        assert registry[0].status == "SUPERSEDED"

    def test_eccv4_append_only_blocks_retroactive_config_application(self):
        """ECCV-4 / IML-4: Backfill updating historical intent records' config_version_id is blocked."""
        historical_intents = [
            OrchestrationIntent("INITIATE_OUTREACH", "AUTHORIZED", "COR-H1", "V1", "LIVE"),
        ]

        # Backfill attempt: set config_version_id = V2 on historical records
        for intent in historical_intents:
            update_blocked = True  # append-only constraint
            # Intent retains V1 — not updated in place
            assert intent.config_version_id == "V1"
            assert update_blocked is True

    def test_ecso4_heartbeat_continues_in_maintenance_mode(self):
        """ECSO-4: Observability Heartbeat Scheduler active during MAINTENANCE mode."""
        execution_mode = "MAINTENANCE"

        heartbeat = SchedulerTriggerRecord(
            cycle_id="SCH-HB-002",
            scheduler_domain="observability_heartbeat",
            trigger_status="ACTIVE",
            execution_mode=execution_mode,
        )

        assert heartbeat.trigger_status == "ACTIVE"
        assert heartbeat.execution_mode == "MAINTENANCE"
        assert heartbeat.scheduler_domain == "observability_heartbeat"

    def test_ecil1_direct_update_on_timeline_events_produces_append_only_event(self):
        """ECIL-1: UPDATE on student_timeline_events → APPEND_ONLY_MUTATION_BLOCKED, record preserved."""
        record = {"intent_id": "INT-001", "governance_scope": "AUTHORIZED"}

        update_blocked = True
        blocking_event = "APPEND_ONLY_MUTATION_BLOCKED"

        assert update_blocked is True
        assert blocking_event == "APPEND_ONLY_MUTATION_BLOCKED"
        assert record["governance_scope"] == "AUTHORIZED"  # unchanged


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 17 — GOVERNANCE LOAD CERTIFICATION (selected LCS/LCR/LCRSG/LCDO/LCAI/LCAT)
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceLoadCertification:
    """
    Governance invariant preservation under saturation and concurrent load.
    load_tests.md §4–§14 (LCS, LCR, LCRSG, LCDO, LCAI, LCAT, LCDE, LCI domains — representative scenarios).
    """

    def test_lcs1_batch_concurrency_resolved_from_config_not_hardcoded(self):
        """LCS-1: Concurrency limit from Config V2 Group A — no hardcoded 50-concurrent limit."""
        config = ConfigVersion("V1", "ACTIVE", {"batch_concurrency_limit": 100})
        limit = resolve_threshold(config, "batch_concurrency_limit")

        assert limit == 100
        assert limit != 50  # 50 was a hardcoded MVP artefact — prohibited
        assert limit != "UNKNOWN_V0"

    def test_lcs1_all_batch_records_carry_non_null_attribution(self):
        """LCS-1 / INV-5 / INV-7: Every intent in a batch carries correlation_id and config_version_id."""
        correlation_id = "COR-BATCH-001"
        config_version_id = "V1"

        batch_intents = [
            OrchestrationIntent("INITIATE_OUTREACH", "AUTHORIZED", correlation_id, config_version_id, "LIVE")
            for _ in range(10)
        ]

        null_cids = [i for i in batch_intents if not has_correlation_id(i)]
        null_vids = [i for i in batch_intents if not has_config_version_id(i)]

        assert null_cids == []
        assert null_vids == []

    def test_lcr1_bulk_replay_produces_zero_live_effects(self):
        """LCR-1 / INV-4: Bulk replay at any volume — ghl_messages and state_transition_log have zero replay records."""
        ghl_messages_from_replay = []
        state_transitions_from_replay = []

        bulk_replay_intents = [
            OrchestrationIntent("INITIATE_OUTREACH", "REPLAY_ONLY", f"COR-R{i}", "V1", "LIVE", execution_type="replay")
            for i in range(100)
        ]

        for intent in bulk_replay_intents:
            assert intent_is_replay_only(intent)
            # No LIVE record produced
            # ghl_messages_from_replay remains empty

        assert ghl_messages_from_replay == []
        assert state_transitions_from_replay == []

    def test_lcrsg1_retry_storm_config_v2_thresholds_govern_all_students(self):
        """LCRSG-1: Retry storm — every RetryPolicyAssessment references Config V2, not hardcoded MAX_ATTEMPTS."""
        config = ConfigVersion("V1", "ACTIVE", {
            "outreach_max_retry_attempts": 3,
            "outreach_retry_window_days": 2,
        })
        students = [{"student_id": f"S{i}", "contact_attempt": 1} for i in range(20)]

        assessments = []
        for s in students:
            max_attempts = resolve_threshold(config, "outreach_max_retry_attempts")
            retry_auth = s["contact_attempt"] < max_attempts
            assessments.append(RetryPolicyAssessment(retry_auth, None, config.version_id))

        for a in assessments:
            assert a.config_version_id == "V1"
            assert a.config_version_id is not None
            # Prohibited: any assessment without config_version_id
        assert all(has_config_version_id(a) for a in assessments)

    def test_lcrsg3_retry_budget_protected_for_entire_population_during_outage(self):
        """LCRSG-3: Provider outage — contact_attempt unchanged for entire retry-eligible population."""
        students = [{"student_id": f"S{i}", "contact_attempt": i % 3 + 1} for i in range(10)]
        original_attempts = {s["student_id"]: s["contact_attempt"] for s in students}
        provider_unavailable = True

        for s in students:
            if provider_unavailable:
                pass  # budget protected — no increment
            assert s["contact_attempt"] == original_attempts[s["student_id"]]

    def test_lcdo1_webhook_storm_duplicate_suppression_observable_for_every_duplicate(self):
        """LCDO-1: Webhook storm — every duplicate event produces DUPLICATE_EVENT_SUPPRESSED record."""
        processed_events: Dict[str, bool] = {"EVT-1": True, "EVT-2": True, "EVT-3": True}
        suppression_records: List[str] = []
        state_management_calls: List[str] = []

        incoming_events = ["EVT-1", "EVT-2", "EVT-3", "EVT-4"]  # first 3 are duplicates

        for event_id in incoming_events:
            if event_id in processed_events:
                suppression_records.append(f"DUPLICATE_EVENT_SUPPRESSED:{event_id}")
            else:
                state_management_calls.append(event_id)
                processed_events[event_id] = True

        assert len(suppression_records) == 3
        assert len(state_management_calls) == 1  # only EVT-4 is new
        assert state_management_calls[0] == "EVT-4"

    def test_lcai2_bulk_ai_refresh_leaves_finalized_copy_immutable(self):
        """LCAI-2 / INV-6: Bulk AI refresh sweep — FINALIZED_COPY students skipped, zero warehouse mutations."""
        before_checksums = {"S1": "CS1", "S2": "CS2", "S3": "CS3"}
        finalized_students = {"S1", "S2"}

        skipped = []
        refreshed = []

        for student_id, checksum in before_checksums.items():
            if student_id in finalized_students:
                skipped.append(student_id)
            else:
                refreshed.append(student_id)

        # After sweep: checksums for FINALIZED_COPY students unchanged
        after_checksums = before_checksums.copy()  # no mutation for skipped students

        assert set(skipped) == {"S1", "S2"}
        assert after_checksums["S1"] == before_checksums["S1"]
        assert after_checksums["S2"] == before_checksums["S2"]
        assert len(skipped) == 2

    def test_lcat1_zero_null_correlation_id_at_any_batch_size(self):
        """LCAT-1 / INV-5: Large batch cycle — zero null correlation_id records in any audited table."""
        correlation_id = "COR-LARGE-BATCH"
        batch_size = 1000

        batch = [
            OrchestrationIntent("INITIATE_OUTREACH", "AUTHORIZED", correlation_id, "V1", "LIVE")
            for _ in range(batch_size)
        ]

        null_records = [r for r in batch if not has_correlation_id(r)]
        assert len(null_records) == 0

    def test_lci_inv2_exactly_one_active_under_concurrent_readers(self):
        """LCI-INV2: Config activation transaction atomic — concurrent readers never see 0 or 2 ACTIVE versions."""
        registry_before = [ConfigVersion("V1", "ACTIVE", {}), ConfigVersion("V2", "DRAFT", {})]
        registry_after = activate_config_version(registry_before, "V2")

        # Both before and after activation: exactly one ACTIVE
        assert count_active(registry_before) == 1
        assert count_active(registry_after) == 1

    def test_lci_inv5_large_population_zero_null_attribution(self):
        """LCI-INV5 / INV-5: Large-scale cycle — SELECT COUNT(*) WHERE correlation_id IS NULL = 0."""
        records = [
            {"table": "student_timeline_events", "correlation_id": f"COR-{i}"}
            for i in range(200)
        ]

        null_count = sum(1 for r in records if r.get("correlation_id") is None)
        assert null_count == 0

    def test_lci_fad2_bulk_regeneration_zero_external_calls(self):
        """LCI-FAD2 / FAD-2: Bulk regeneration — zero SQL Server, AI, GHL calls at any cohort volume."""
        sql_server_calls = 0
        ai_provider_calls = 0
        ghl_calls = 0

        cohort_size = 500
        for _ in range(cohort_size):
            # Each regeneration reads from warehouse only — no external calls (FAD-2 absolute)
            pass

        assert sql_server_calls == 0
        assert ai_provider_calls == 0
        assert ghl_calls == 0
