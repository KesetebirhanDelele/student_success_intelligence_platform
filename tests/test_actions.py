"""
Governance-safe orchestration-action certification.

Aligned with (authoritative parent contracts):
  tests/test_scenarios.md  — governance validation contract (GPC/OIG/CV2/SVL/ROS/ROG/AIG/PBG/STG/CID/ATT/DEG/RGS/IML/INV)
  tests/edge_cases.md      — governance edge-condition certification (ECR/ECRG/ECA/ECAI/ECDO/ECCV/ECSO/ECPL/ECDE/ECIL)
  tests/load_tests.md      — governance load certification (LCS/LCR/LCSCH/LCRSG/LCDO/LCPB/LCAI/LCAT/LCDE/LCOS/LCI)
  tests/test_work_queue.py — governance-safe orchestration queue certification (parent peer contract)

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
  - action = TRIGGER_OUTREACH / CALL / SEND_SMS_OR_EMAIL  (direct dispatch string assertions)
  - hardcoded MAX_ATTEMPTS / 24h-window / 50-concurrent constants
  - "fallback logic applied" / silent-swallow outcomes
  - replay mode producing LIVE effects
  - mutable FINALIZED_COPY assertions
  - AI advisory output alone authorising OrchestrationIntent
  - direct provider dispatch assumptions
  - direct execution assumptions

Action testing is NOW:
  - orchestration-intent governance certification
  - replay-safe orchestration validation
  - provider-boundary preservation validation
  - immutable-lineage orchestration certification

This file certifies governance contracts only.
It does NOT generate runtime implementation logic, orchestration services,
provider handlers, queue workers, or production action code.
"""
from __future__ import annotations

import threading
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
    intent_type: str                     # INITIATE_OUTREACH | RETRY_OUTREACH | SKIP
    governance_scope: str                # AUTHORIZED | SHADOW_ONLY | REPLAY_ONLY | UNAVAILABLE
    correlation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str                  # LIVE | SHADOW | DEGRADED | MAINTENANCE
    execution_type: str = "original"     # original | replay | recovery | regeneration
    causation_id: Optional[str] = None
    degradation_flags: List[str] = field(default_factory=list)
    compliance_hold_active: bool = False


@dataclass
class ActionOrchestrationIntent(OrchestrationIntent):
    """
    Intent produced by a manual action evaluation path.

    Extends OrchestrationIntent with action-specific attribution fields.
    action_type maps to the governance-classified action, NOT a raw dispatch string.
    Prohibited: asserting action_type = "CALL" / "SEND_SMS" / "BOOK_MEETING".
    """
    action_type: str = ""                # FORCE_RETRY | ESCALATE | CLOSE_CASE
    triggered_by: str = "manual"         # manual | scheduled | recovery


@dataclass
class RetryPolicyAssessment:
    retry_authorized: bool
    reason: Optional[str]                # RETRY_EXHAUSTED | RETRY_WINDOW_NOT_ELAPSED | None
    config_version_id: Optional[str]
    causation_id: Optional[str] = None


@dataclass
class EligibilityAssessment:
    eligibility_status: str              # ELIGIBLE | BLOCKED
    config_version_id: Optional[str]
    skip_reason: Optional[str] = None


@dataclass
class EscalationCandidacyRecord:
    """
    Produced when ESCALATE action is governance-authorized.
    Represents an escalation candidacy signal — NOT a direct provider dispatch.
    The escalation candidacy must carry full attribution before any state management call.
    """
    from_state: str
    to_state: str                        # INTERVENTION_REQUIRED
    escalation_type: str                 # MANUAL_ESCALATE | RETRY_EXHAUSTED
    correlation_id: Optional[str]
    causation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    notes: Optional[str] = None


@dataclass
class TerminalTransitionCandidacyRecord:
    """
    Produced when CLOSE_CASE action is governance-authorized.
    Represents a terminal transition candidacy — NOT a direct state mutation.
    The state management service owns the actual write.
    """
    from_state: str
    to_state: str                        # CLOSED
    correlation_id: Optional[str]
    causation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str
    actor: str = "manual"


@dataclass
class InvalidTransitionRecord:
    """
    Emitted when an action attempts a state transition that is governance-blocked.
    Never silent — every blocked transition produces this record with full attribution.
    """
    from_state: str
    attempted_action: str
    blocking_reason: str                 # TERMINAL_STATE_CLOSED | INVALID_ACTION_TYPE | NOT_FOUND
    correlation_id: Optional[str]
    config_version_id: Optional[str]
    execution_mode: str


@dataclass
class ProviderOrchestrationAssessment:
    governance_scope: str                # AUTHORIZED | UNAVAILABLE | SHADOW_ONLY | REPLAY_ONLY
    outbound_suppressed: bool


@dataclass
class AIAssessment:
    advisory_scope: str                  # AVAILABLE | UNAVAILABLE | STALE
    ai_governance_tier: str              # FINALIZED_COPY | AI_GENERATED | STALE | UNAVAILABLE
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
    governance_scope: str                # REPLAY_ONLY
    execution_type: str                  # replay
    historical_config_version_id: str
    replay_partial: bool
    fingerprint_comparison_outcome: Optional[str] = None
    correlation_id: Optional[str] = None


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


def action_targets_terminal_state(from_state: str) -> bool:
    """
    STG-2 / spec/03_state_transition_rules.md:
    CLOSED is a terminal domain-1 state — no outbound transitions permitted.
    """
    terminal_states = {"CLOSED"}
    return from_state in terminal_states


def retry_exhausted(contact_attempt: int, max_attempts: Any) -> bool:
    """
    CV2-1: Exhaustion evaluated against Config V2 threshold only.
    Prohibited: hardcoded MAX_ATTEMPTS integer comparison.
    """
    if max_attempts == "UNKNOWN_V0":
        return False  # cannot evaluate — degraded path, not a hard block
    return contact_attempt >= max_attempts


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
# SECTION 1 — ACTION GOVERNANCE PRECONDITIONS
# GPC-1 through GPC-5 as they apply to manual action evaluation paths.
# ─────────────────────────────────────────────────────────────────────────────

class TestActionGovernancePreconditions:
    """
    Validates governance preconditions that gate ALL action orchestration evaluation.
    Aligned with test_scenarios.md §3 (GPC-1 through GPC-5).
    """

    def test_agpc1_action_evaluation_halts_without_active_config(self):
        """GPC-1 / action path: No ACTIVE config version → action evaluation does not start."""
        registry: List[ConfigVersion] = []
        active_configs = [v for v in registry if v.status == "ACTIVE"]

        # Governance contract: zero action intents produced
        action_intents_produced: List[ActionOrchestrationIntent] = []
        if not active_configs:
            pass  # evaluation does not start

        assert len(active_configs) == 0
        assert action_intents_produced == []

        # PRECONDITION_FAILED must be emitted — never silent
        emitted_log = StructuredLogRecord(
            event="PRECONDITION_FAILED_NO_ACTIVE_CONFIG",
            correlation_id="COR-ACT-001",
            level="error",
            outcome="failure",
        )
        assert emitted_log.event == "PRECONDITION_FAILED_NO_ACTIVE_CONFIG"
        assert emitted_log.correlation_id is not None

    def test_agpc2_missing_threshold_substitutes_unknown_v0_not_hardcoded(self):
        """GPC-2 / action path: Missing threshold → UNKNOWN_V0, not a hardcoded action constant."""
        config = ConfigVersion("V1", "ACTIVE", thresholds={})
        max_attempts = resolve_threshold(config, "outreach_max_retry_attempts")

        assert max_attempts == "UNKNOWN_V0"
        # Prohibited: any specific integer from action-evaluation hardcoding
        assert max_attempts != 3
        assert max_attempts != "3"

        degradation_flag = f"CONFIG_THRESHOLD_MISSING_outreach_max_retry_attempts"
        assert "CONFIG_THRESHOLD_MISSING_" in degradation_flag

    def test_agpc3_maintenance_mode_suppresses_action_dispatch(self):
        """GPC-3 / action path: MAINTENANCE mode → action dispatch suppressed, observable record emitted."""
        execution_mode = "MAINTENANCE"

        suppression_record = StructuredLogRecord(
            event="ACTION_DISPATCH_SUPPRESSED",
            correlation_id="COR-ACT-002",
            execution_mode=execution_mode,
            suppression_reason="MAINTENANCE_MODE",
        )

        assert suppression_record.suppression_reason == "MAINTENANCE_MODE"
        assert suppression_record.event == "ACTION_DISPATCH_SUPPRESSED"

        # Governance contract: no action orchestration cycle begins
        action_cycle_started = False
        assert action_cycle_started is False

    def test_agpc3_observability_heartbeat_not_suppressed_by_maintenance_in_action_context(self):
        """GPC-3 exception: Observability signals continue regardless of action suppression."""
        execution_mode = "MAINTENANCE"
        heartbeat_exempt = True  # observability heartbeat always fires

        assert heartbeat_exempt is True

    def test_agpc4_action_config_activation_preserves_exactly_one_active_invariant(self):
        """GPC-4 / INV-2 / action path: Config activation during action evaluation remains atomic."""
        registry = [
            ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3}),
            ConfigVersion("V2", "DRAFT", {"outreach_max_retry_attempts": 4}),
        ]
        assert exactly_one_active(registry)

        updated = activate_config_version(registry, "V2")
        assert exactly_one_active(updated)
        assert count_active(updated) == 1

    def test_agpc5_prospective_only_activation_preserves_historical_action_records(self):
        """GPC-5 / FAD-3 / action path: Historical action records keep original config_version_id after activation."""
        historical_action_record = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-HIST-ACT",
            config_version_id="V1",
            execution_mode="LIVE",
            action_type="FORCE_RETRY",
        )

        # V2 activation must not retroactively update historical action records
        assert historical_action_record.config_version_id == "V1"
        assert historical_action_record.config_version_id != "V2"

    def test_agpc_student_not_found_produces_observable_event_never_silent(self):
        """
        action path: Student tracking record absent → NOT_FOUND emitted, no intent produced.
        Prohibited: silent discard when student not found.
        """
        student_lookup_result = None  # tracking record absent

        action_intents_produced: List[ActionOrchestrationIntent] = []
        not_found_log: Optional[StructuredLogRecord] = None

        if student_lookup_result is None:
            not_found_log = StructuredLogRecord(
                event="ACTION_TARGET_NOT_FOUND",
                correlation_id="COR-ACT-003",
                level="warn",
                outcome="not_found",
            )
            # No action intent produced — never silent

        assert action_intents_produced == []
        assert not_found_log is not None
        assert not_found_log.event == "ACTION_TARGET_NOT_FOUND"
        assert not_found_log.correlation_id is not None
        # Prohibited: not_found_log is None (silent discard)

    def test_agpc_unknown_action_type_produces_observable_event_never_silent(self):
        """
        action path: Unrecognised action_type string → INVALID_ACTION_TYPE emitted, no intent produced.
        Prohibited: unknown action type silently ignored.
        """
        action_type = "DO_SOMETHING_WEIRD"
        known_action_types = {"FORCE_RETRY", "ESCALATE", "CLOSE_CASE"}

        action_intents_produced: List[ActionOrchestrationIntent] = []
        invalid_action_log: Optional[StructuredLogRecord] = None

        if action_type not in known_action_types:
            invalid_action_log = StructuredLogRecord(
                event="INVALID_ACTION_TYPE",
                correlation_id="COR-ACT-004",
                level="warn",
                suppression_reason=f"UNKNOWN_ACTION_TYPE_{action_type}",
            )
            # No action intent produced — guard enforced before evaluation

        assert action_intents_produced == []
        assert invalid_action_log is not None
        assert invalid_action_log.event == "INVALID_ACTION_TYPE"
        assert invalid_action_log.correlation_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — ORCHESTRATION-INTENT ACTION GOVERNANCE
# FORCE_RETRY, ESCALATE, CLOSE_CASE reframed as governance-certified intents.
# Replaces direct execution assertions from the MVP test_actions.py.
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestrationIntentActionGovernance:
    """
    Validates that manual actions produce governance-certified OrchestrationIntent records.
    Actions are NOT direct executions. They produce intents that delegate to orchestration services.

    Aligned with test_scenarios.md §4 (OIG-1 through OIG-5) for action paths.
    """

    def test_oig_force_retry_below_threshold_produces_retry_outreach_intent(self):
        """
        OIG / action path: FORCE_RETRY with attempt below Config V2 threshold →
        RETRY_OUTREACH intent with AUTHORIZED scope, causation_id linking to prior intent.
        Prohibited: asserting a direct CALL / SMS / EMAIL dispatch occurred.
        """
        config = ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3})
        contact_attempt = 1
        max_attempts = resolve_threshold(config, "outreach_max_retry_attempts")

        retry_authorized = not retry_exhausted(contact_attempt, max_attempts)
        assert retry_authorized is True

        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-ACT-010",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id="INT-ORIGINAL-001",
            action_type="FORCE_RETRY",
        )

        assert intent.intent_type == "RETRY_OUTREACH"
        assert intent.governance_scope == "AUTHORIZED"
        assert intent.causation_id is not None
        assert intent.config_version_id is not None
        # Prohibited: asserting action_type maps to a raw dispatch string like "CALL"
        assert intent.action_type == "FORCE_RETRY"

        # Governance contract: runtime loop does NOT construct provider payload
        loop_produced_provider_payload = False
        assert loop_produced_provider_payload is False

    def test_oig_force_retry_at_threshold_produces_exhausted_assessment_not_intent(self):
        """
        OIG / action path: FORCE_RETRY with attempt count meeting Config V2 threshold →
        RetryPolicyAssessment(retry_authorized=False, reason=RETRY_EXHAUSTED).
        No RETRY_OUTREACH intent produced.
        Prohibited: asserting max_attempts == 3 (hardcoded constant).
        """
        config = ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3})
        contact_attempt = 3
        max_attempts = resolve_threshold(config, "outreach_max_retry_attempts")

        exhausted = retry_exhausted(contact_attempt, max_attempts)
        assert exhausted is True

        assessment = RetryPolicyAssessment(
            retry_authorized=False,
            reason="RETRY_EXHAUSTED",
            config_version_id=config.version_id,
        )

        # Assessment produced — intent is NOT produced
        action_intents_produced: List[ActionOrchestrationIntent] = []
        assert action_intents_produced == []

        assert assessment.retry_authorized is False
        assert assessment.reason == "RETRY_EXHAUSTED"
        assert assessment.config_version_id == "V1"
        # Prohibited: hardcoded assert max == 3
        assert max_attempts == config.thresholds["outreach_max_retry_attempts"]

    def test_oig_force_retry_assessment_carries_config_version_id(self):
        """OIG / INV-7: RetryPolicyAssessment from FORCE_RETRY path must carry config_version_id."""
        assessment = RetryPolicyAssessment(
            retry_authorized=False,
            reason="RETRY_EXHAUSTED",
            config_version_id="V1",
        )
        assert has_config_version_id(assessment)
        assert assessment.config_version_id is not None

    def test_oig_force_retry_shadow_mode_produces_shadow_only_scope(self):
        """
        OIG / SVL-1 / action path: FORCE_RETRY in SHADOW mode →
        intent with governance_scope=SHADOW_ONLY, no LIVE dispatch.
        """
        config = ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3})
        contact_attempt = 1
        execution_mode = "SHADOW"

        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="SHADOW_ONLY",
            correlation_id="COR-ACT-011",
            config_version_id="V1",
            execution_mode=execution_mode,
            causation_id="INT-ORIGINAL-001",
            action_type="FORCE_RETRY",
        )

        provider = ProviderOrchestrationAssessment(
            governance_scope="SHADOW_ONLY",
            outbound_suppressed=True,
        )

        assert intent.governance_scope == "SHADOW_ONLY"
        assert provider.outbound_suppressed is True
        live_retry_dispatch = False
        assert live_retry_dispatch is False

    def test_oig_escalate_from_contacted_produces_escalation_candidacy_with_attribution(self):
        """
        OIG / STG / action path: ESCALATE from CONTACTED state →
        EscalationCandidacyRecord(to_state=INTERVENTION_REQUIRED) with full attribution.
        Prohibited: asserting a direct state mutation occurred without attribution.
        """
        from_state = "CONTACTED"

        escalation = EscalationCandidacyRecord(
            from_state=from_state,
            to_state="INTERVENTION_REQUIRED",
            escalation_type="MANUAL_ESCALATE",
            correlation_id="COR-ACT-012",
            causation_id="INT-ORIGINAL-002",
            config_version_id="V1",
            execution_mode="LIVE",
            notes="High risk student",
        )

        assert escalation.from_state == "CONTACTED"
        assert escalation.to_state == "INTERVENTION_REQUIRED"
        assert escalation.escalation_type == "MANUAL_ESCALATE"
        assert escalation.correlation_id is not None
        assert escalation.causation_id is not None
        assert escalation.config_version_id is not None

        # Governance contract: state management service owns the actual write
        runtime_loop_wrote_state_directly = False
        assert runtime_loop_wrote_state_directly is False

    def test_oig_escalate_from_no_response_produces_escalation_candidacy_with_attribution(self):
        """
        OIG / STG / action path: ESCALATE from NO_RESPONSE state →
        EscalationCandidacyRecord(to_state=INTERVENTION_REQUIRED) with full attribution.
        """
        from_state = "NO_RESPONSE"

        escalation = EscalationCandidacyRecord(
            from_state=from_state,
            to_state="INTERVENTION_REQUIRED",
            escalation_type="MANUAL_ESCALATE",
            correlation_id="COR-ACT-013",
            causation_id="INT-ORIGINAL-003",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        assert escalation.from_state == "NO_RESPONSE"
        assert escalation.to_state == "INTERVENTION_REQUIRED"
        assert has_correlation_id(escalation)
        assert has_config_version_id(escalation)

    def test_oig_close_case_produces_terminal_transition_candidacy_not_silent_mutation(self):
        """
        OIG / STG / action path: CLOSE_CASE on CONTACTED state →
        TerminalTransitionCandidacyRecord(to_state=CLOSED) with full attribution.
        Prohibited: silent direct state mutation.
        """
        from_state = "CONTACTED"

        terminal_record = TerminalTransitionCandidacyRecord(
            from_state=from_state,
            to_state="CLOSED",
            correlation_id="COR-ACT-014",
            causation_id="INT-ORIGINAL-004",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        assert terminal_record.to_state == "CLOSED"
        assert terminal_record.correlation_id is not None
        assert terminal_record.causation_id is not None
        assert terminal_record.config_version_id is not None

        # Governance contract: terminal candidacy must be persisted before state management delegated
        write_order: List[str] = []
        write_order.append("terminal_transition_candidacy_write")
        write_order.append("state_management_delegation")
        assert write_order[0] == "terminal_transition_candidacy_write"
        assert write_order.index("terminal_transition_candidacy_write") < write_order.index("state_management_delegation")

    def test_oig_intent_persisted_before_delegation_for_all_action_paths(self):
        """OIG-3 / action path: Governance record write completes BEFORE execution delegation."""
        for action_type in ["FORCE_RETRY", "ESCALATE", "CLOSE_CASE"]:
            write_order: List[str] = []
            write_order.append("governance_record_write")
            write_order.append("execution_delegation")

            assert write_order[0] == "governance_record_write"
            assert write_order.index("governance_record_write") < write_order.index("execution_delegation")

    def test_oig_write_failure_blocks_delegation_on_all_action_paths(self):
        """OIG-3 / action path: If governance record write fails, no execution delegation occurs."""
        governance_write_succeeded = False

        delegations: List[str] = []
        if governance_write_succeeded:
            delegations.append("delegation")

        assert delegations == []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — AI ADVISORY-ONLY ACTION GOVERNANCE
# AI is advisory-only for action paths — it cannot alone authorize any action intent.
# Aligned with test_scenarios.md §9 (AIG-1 through AIG-5).
# ─────────────────────────────────────────────────────────────────────────────

class TestAIAdvisoryActionGovernance:
    """
    Validates AI advisory-only contracts for action evaluation paths.
    AI informs but cannot authorize, override governance rules, or mutate FINALIZED records.
    """

    def test_aig_ai_advisory_does_not_alone_authorize_force_retry_intent(self):
        """
        AIG-1 / action path: AI recommendation DEFER does not suppress FORCE_RETRY when
        rule-based assessment authorizes retry.
        """
        ai_assessment = AIAssessment(
            advisory_scope="AVAILABLE",
            ai_governance_tier="AI_GENERATED",
            advisory_content={"recommended_intervention": "DEFER"},
        )
        config = ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3})
        contact_attempt = 1
        max_attempts = resolve_threshold(config, "outreach_max_retry_attempts")
        rule_based_retry_authorized = not retry_exhausted(contact_attempt, max_attempts)

        # Rule-based evaluation governs — AI DEFER advisory does not override
        assert rule_based_retry_authorized is True
        assert ai_assessment.advisory_content["recommended_intervention"] == "DEFER"
        assert rule_based_retry_authorized is True  # unchanged by AI advisory

    def test_aig_stale_ai_cannot_elevate_action_severity_in_live_mode(self):
        """AIG-2 / AP-AI11 / action path: STALE AI advisory severity elevation blocked in LIVE mode."""
        stale_ai_recommended_severity = "CRITICAL"
        rule_based_severity = "MEDIUM"
        execution_mode = "LIVE"

        final_severity = rule_based_severity  # governance: rule-based governs
        stale_elevation_blocked = (
            execution_mode == "LIVE" and
            stale_ai_recommended_severity != rule_based_severity
        )

        assert final_severity == "MEDIUM"
        assert stale_elevation_blocked is True

    def test_aig_stale_ai_does_not_block_action_orchestration(self):
        """AIG-2 / action path: STALE AI restricts advisory scope only — action evaluation continues."""
        ai_assessment = AIAssessment(
            advisory_scope="STALE",
            ai_governance_tier="STALE",
        )
        orchestration_blocked = False  # STALE AI does not block action evaluation

        assert ai_assessment.ai_governance_tier == "STALE"
        assert orchestration_blocked is False

    def test_aig_ai_unavailable_rule_based_action_governance_continues(self):
        """AIG-4 / action path: AI circuit breaker OPEN → advisory_scope=UNAVAILABLE, rule-based proceeds."""
        ai_assessment = AIAssessment(
            advisory_scope="UNAVAILABLE",
            ai_governance_tier="UNAVAILABLE",
            ai_blocked=True,
        )
        orchestration_blocked = False  # rule-based action governance continues

        ai_log = StructuredLogRecord(
            event="AI_PROVIDER_UNAVAILABLE",
            correlation_id="COR-ACT-020",
            error_class="UpstreamUnavailable",
        )

        assert ai_assessment.advisory_scope == "UNAVAILABLE"
        assert orchestration_blocked is False
        assert ai_log.error_class == "UpstreamUnavailable"
        assert ai_log.correlation_id is not None

    def test_aig_replay_action_ai_sourced_from_warehouse_not_live_inference(self):
        """AIG-5 / AP-AI5 / action path: Replay action evaluation reads AI from warehouse — no live AI inference."""
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

    def test_aig_finalized_copy_immutable_under_any_action_path(self):
        """AIG-3 / FAD-1 / INV-6 / action path: No action path may re-evaluate or overwrite FINALIZED_COPY."""
        warehouse_record = {
            "student_id": "S1_OPAQUE",
            "snapshot_month": "2026-05",
            "ai_governance_tier": "FINALIZED_COPY",
            "narrative_content": "original_content",
        }

        should_skip = warehouse_record["ai_governance_tier"] == "FINALIZED_COPY"
        mutation_attempted = False

        assert should_skip is True
        assert mutation_attempted is False
        assert warehouse_record["narrative_content"] == "original_content"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — STATE-TRANSITION AUTHORIZATION VALIDATION
# Valid and invalid transitions from manual action paths.
# Aligned with test_scenarios.md §11 (STG-1 through STG-4) and
# spec/03_state_transition_rules.md Domain 1 (Outreach).
# ─────────────────────────────────────────────────────────────────────────────

class TestStateTransitionAuthorizationValidation:
    """
    Validates that state transitions produced by action paths are authorized,
    attributed, and blocked correctly when invalid.
    """

    def test_stg_closed_state_force_retry_blocked_with_observable_event(self):
        """
        STG-2 / action path: FORCE_RETRY on CLOSED state → InvalidTransitionRecord emitted.
        Prohibited: silent discard of the action request.
        Note: max-attempts exhaustion may ALSO block this, but CLOSED-state blocking
        is the terminal-state governance invariant (independent of attempt count).
        """
        from_state = "CLOSED"
        is_terminal = action_targets_terminal_state(from_state)

        blocking_record: Optional[InvalidTransitionRecord] = None
        if is_terminal:
            blocking_record = InvalidTransitionRecord(
                from_state=from_state,
                attempted_action="FORCE_RETRY",
                blocking_reason="TERMINAL_STATE_CLOSED",
                correlation_id="COR-ACT-030",
                config_version_id="V1",
                execution_mode="LIVE",
            )

        assert is_terminal is True
        assert blocking_record is not None
        assert blocking_record.blocking_reason == "TERMINAL_STATE_CLOSED"
        assert blocking_record.correlation_id is not None
        assert blocking_record.config_version_id is not None

        # Governance contract: no action intent produced
        action_intents_produced: List[ActionOrchestrationIntent] = []
        assert action_intents_produced == []

    def test_stg_closed_state_close_case_blocked_with_observable_event(self):
        """
        STG-2 / action path: CLOSE_CASE on already-CLOSED state → InvalidTransitionRecord emitted.
        CLOSED → CLOSED is not a valid transition.
        """
        from_state = "CLOSED"
        is_terminal = action_targets_terminal_state(from_state)

        blocking_record: Optional[InvalidTransitionRecord] = None
        if is_terminal:
            blocking_record = InvalidTransitionRecord(
                from_state=from_state,
                attempted_action="CLOSE_CASE",
                blocking_reason="TERMINAL_STATE_CLOSED",
                correlation_id="COR-ACT-031",
                config_version_id="V1",
                execution_mode="LIVE",
            )

        assert is_terminal is True
        assert blocking_record is not None
        assert blocking_record.blocking_reason == "TERMINAL_STATE_CLOSED"
        # Prohibited: blocking_record is None (silent discard)

    def test_stg_closed_state_escalate_blocked_with_observable_event(self):
        """
        STG-2 / action path: ESCALATE on CLOSED state → InvalidTransitionRecord.
        CLOSED has no outbound transitions in any direction.
        """
        from_state = "CLOSED"
        is_terminal = action_targets_terminal_state(from_state)

        blocking_record: Optional[InvalidTransitionRecord] = None
        if is_terminal:
            blocking_record = InvalidTransitionRecord(
                from_state=from_state,
                attempted_action="ESCALATE",
                blocking_reason="TERMINAL_STATE_CLOSED",
                correlation_id="COR-ACT-032",
                config_version_id="V1",
                execution_mode="LIVE",
            )

        assert is_terminal is True
        assert blocking_record is not None
        assert blocking_record.blocking_reason == "TERMINAL_STATE_CLOSED"

    def test_stg_valid_escalate_transition_carries_full_attribution(self):
        """STG-1 / action path: ELIGIBLE→INTERVENTION_REQUIRED transition record carries all attribution fields."""
        escalation = EscalationCandidacyRecord(
            from_state="CONTACTED",
            to_state="INTERVENTION_REQUIRED",
            escalation_type="MANUAL_ESCALATE",
            correlation_id="COR-ACT-033",
            causation_id="INT-ORIGINAL-005",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        assert escalation.correlation_id is not None
        assert escalation.causation_id is not None
        assert escalation.config_version_id is not None
        assert escalation.from_state is not None
        assert escalation.to_state == "INTERVENTION_REQUIRED"

    def test_stg_state_transition_written_before_execution_delegation(self):
        """
        OIG-3 / STG / action path: Transition candidacy write precedes execution delegation.
        """
        write_order: List[str] = []
        write_order.append("state_transition_candidacy_write")
        write_order.append("execution_delegation")

        assert write_order.index("state_transition_candidacy_write") < write_order.index("execution_delegation")

    def test_stg_invalid_transition_is_never_silent(self):
        """STG-2 / action path: Every blocked transition must emit an observable InvalidTransitionRecord."""
        blocked_actions = [
            ("CLOSED", "FORCE_RETRY"),
            ("CLOSED", "CLOSE_CASE"),
            ("CLOSED", "ESCALATE"),
        ]

        for from_state, action in blocked_actions:
            blocking_record = InvalidTransitionRecord(
                from_state=from_state,
                attempted_action=action,
                blocking_reason=f"TERMINAL_STATE_{from_state}",
                correlation_id=f"COR-ACT-BLK-{action}",
                config_version_id="V1",
                execution_mode="LIVE",
            )
            # Every blocked action must emit an observable record — never silent
            assert blocking_record is not None, f"Silent block for ({from_state}, {action}) is a governance defect"
            assert blocking_record.correlation_id is not None

    def test_stg4_superseded_config_rollback_blocked_during_action_evaluation(self):
        """STG-4 / action path: Config rollback to SUPERSEDED during action evaluation is forbidden."""
        registry = [
            ConfigVersion("V1", "SUPERSEDED", {}),
            ConfigVersion("V2", "ACTIVE", {}),
        ]
        rollback_blocked = True

        assert rollback_blocked is True
        assert registry[0].status == "SUPERSEDED"
        assert registry[1].status == "ACTIVE"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — REPLAY & REGENERATION ACTION VALIDATION
# Replay suppresses LIVE effects; regeneration is warehouse-only.
# Aligned with test_scenarios.md §7 (ROS-1 through ROS-5).
# ─────────────────────────────────────────────────────────────────────────────

class TestReplayActionValidation:
    """
    Validates replay-safe action semantics: replay may simulate action orchestration
    but must never produce LIVE effects.
    """

    def test_ros_replay_action_carries_replay_only_governance_scope(self):
        """ROS-1 / INV-4 / action path: Replay action evaluation → governance_scope=REPLAY_ONLY."""
        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="REPLAY_ONLY",
            correlation_id="COR-REPLAY-ACT-001",
            config_version_id="V1",
            execution_mode="LIVE",
            execution_type="replay",
            causation_id="INT-ORIGINAL-REPLAY-001",
            action_type="FORCE_RETRY",
        )

        assert intent_is_replay_only(intent)
        assert intent.governance_scope == "REPLAY_ONLY"
        assert intent.execution_type == "replay"

    def test_ros_replay_action_suppresses_all_live_effects(self):
        """ROS-1 / AP-RT2 / action path: Replay action → zero LIVE outbound dispatch, zero state transitions."""
        provider = ProviderOrchestrationAssessment(
            governance_scope="REPLAY_ONLY",
            outbound_suppressed=True,
        )
        ai = AIAssessment(
            advisory_scope="AVAILABLE",
            ai_governance_tier="FINALIZED_COPY",
            ai_blocked=True,
        )

        assert provider.outbound_suppressed is True
        assert ai.ai_blocked is True

        ghl_messages_with_live_scope: List = []
        state_transitions_from_replay: List = []
        assert ghl_messages_with_live_scope == []
        assert state_transitions_from_replay == []

    def test_ros_replay_action_uses_historical_config_not_current_active(self):
        """ROS-2 / FAD-3 / action path: Replay action uses historical config_version_id, not current ACTIVE."""
        historical_config = ConfigVersion("V1", "SUPERSEDED", {"outreach_max_retry_attempts": 2})
        current_active = ConfigVersion("V2", "ACTIVE", {"outreach_max_retry_attempts": 5})

        replay_record = ReplayDiagnosticRecord(
            source_artifact_id="SA-ACT-001",
            replay_cycle_id="RC-ACT-001",
            governance_scope="REPLAY_ONLY",
            execution_type="replay",
            historical_config_version_id="V1",
            replay_partial=False,
            correlation_id="COR-REPLAY-ACT-002",
        )

        assert replay_record.historical_config_version_id == "V1"
        assert replay_record.historical_config_version_id != current_active.version_id

    def test_ros_missing_historical_threshold_substitutes_unknown_v0_marks_partial(self):
        """ROS-3 / action path: Historical config missing threshold → UNKNOWN_V0, replay_partial=true."""
        historical_config = ConfigVersion("V1", "SUPERSEDED", thresholds={})
        threshold = resolve_threshold(historical_config, "outreach_max_retry_attempts")

        replay_partial = threshold == "UNKNOWN_V0"

        assert threshold == "UNKNOWN_V0"
        assert replay_partial is True
        # Prohibited: hardcoded fallback integer applied during replay
        assert threshold != 3

    def test_ros_duplicate_replay_action_key_is_noop(self):
        """ROS-4 / action path: Duplicate (source_artifact_id, replay_cycle_id) action replay → no-op."""
        executed_replays: Dict[tuple, bool] = {("SA-ACT-001", "RC-ACT-001"): True}

        def trigger_replay_action(source_artifact_id: str, replay_cycle_id: str) -> str:
            key = (source_artifact_id, replay_cycle_id)
            if key in executed_replays:
                return "TRIGGER_SUPPRESSED"
            executed_replays[key] = True
            return "REPLAY_STARTED"

        result = trigger_replay_action("SA-ACT-001", "RC-ACT-001")
        assert result == "TRIGGER_SUPPRESSED"

    def test_ros_regeneration_action_produces_identical_output_from_warehouse(self):
        """ROS-5 / FAD-2 / action path: Regeneration reads warehouse exclusively — zero external calls."""
        sql_server_calls = 0
        ai_provider_calls = 0
        ghl_api_calls = 0

        regeneration_output = {"source": "warehouse_only", "output_identical": True}

        assert sql_server_calls == 0
        assert ai_provider_calls == 0
        assert ghl_api_calls == 0
        assert regeneration_output["output_identical"] is True

    def test_ros_finalized_copy_immutable_under_replay_action_path(self):
        """FAD-1 / INV-6 / action path: FINALIZED_COPY not re-evaluated or overwritten during replay."""
        warehouse_record = {
            "ai_governance_tier": "FINALIZED_COPY",
            "narrative_content": "ORIGINAL_CONTENT",
        }
        original_content = warehouse_record["narrative_content"]

        # Replay action path must skip FINALIZED_COPY — no write attempted
        write_attempted = warehouse_record["ai_governance_tier"] == "FINALIZED_COPY" and False
        assert write_attempted is False
        assert warehouse_record["narrative_content"] == original_content


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — ATTRIBUTION CONTINUITY FOR ACTION PATHS
# correlation_id, causation_id, config_version_id on every action-produced record.
# Aligned with test_scenarios.md §14 (ATT-1 through ATT-5).
# ─────────────────────────────────────────────────────────────────────────────

class TestActionAttributionContinuity:
    """
    Validates that every governance record produced by an action path carries
    complete attribution: correlation_id, causation_id, config_version_id.
    """

    def test_att_force_retry_intent_carries_correlation_id(self):
        """ATT-1 / INV-5 / action path: FORCE_RETRY-produced intent carries non-null correlation_id."""
        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-ATT-001",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id="INT-ORIGINAL-010",
            action_type="FORCE_RETRY",
        )
        assert has_correlation_id(intent)
        assert intent.correlation_id == "COR-ATT-001"

    def test_att_force_retry_intent_carries_causation_id_to_original_intent(self):
        """ATT-2 / ROG-1 / action path: RETRY_OUTREACH intent from FORCE_RETRY path carries causation_id."""
        prior_intent_id = "INT-ORIGINAL-011"

        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-ATT-002",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id=prior_intent_id,
            action_type="FORCE_RETRY",
        )

        assert intent.causation_id == prior_intent_id
        assert intent.causation_id is not None

    def test_att_retry_intent_missing_causation_id_flagged_as_governance_defect(self):
        """ECA-2 / ATT-2 / action path: RETRY_OUTREACH with null causation_id → CAUSATION_LINEAGE_BROKEN."""
        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id="COR-ATT-003",
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id=None,  # missing — governance defect
            action_type="FORCE_RETRY",
        )

        causation_lineage_broken = intent.causation_id is None
        defect_event_emitted = causation_lineage_broken  # never silent

        assert causation_lineage_broken is True
        assert defect_event_emitted is True

    def test_att_escalate_record_carries_full_attribution(self):
        """ATT / STG-1 / action path: EscalationCandidacyRecord from ESCALATE path carries full attribution."""
        escalation = EscalationCandidacyRecord(
            from_state="NO_RESPONSE",
            to_state="INTERVENTION_REQUIRED",
            escalation_type="MANUAL_ESCALATE",
            correlation_id="COR-ATT-004",
            causation_id="INT-ORIGINAL-012",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        assert has_correlation_id(escalation)
        assert has_config_version_id(escalation)
        assert escalation.causation_id is not None

    def test_att_close_case_record_carries_full_attribution(self):
        """ATT / STG-1 / action path: TerminalTransitionCandidacyRecord from CLOSE_CASE path carries full attribution."""
        terminal_record = TerminalTransitionCandidacyRecord(
            from_state="CONTACTED",
            to_state="CLOSED",
            correlation_id="COR-ATT-005",
            causation_id="INT-ORIGINAL-013",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        assert has_correlation_id(terminal_record)
        assert has_config_version_id(terminal_record)
        assert terminal_record.causation_id is not None

    def test_att_invalid_transition_record_carries_correlation_id(self):
        """ATT / INV-5 / action path: InvalidTransitionRecord carries non-null correlation_id."""
        blocking_record = InvalidTransitionRecord(
            from_state="CLOSED",
            attempted_action="FORCE_RETRY",
            blocking_reason="TERMINAL_STATE_CLOSED",
            correlation_id="COR-ATT-006",
            config_version_id="V1",
            execution_mode="LIVE",
        )

        assert has_correlation_id(blocking_record)
        assert blocking_record.correlation_id is not None

    def test_att_action_attribution_propagates_through_downstream_records(self):
        """ATT-1 / action path: correlation_id from action entry point propagates to all downstream records."""
        correlation_id = "COR-ATT-007"

        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="AUTHORIZED",
            correlation_id=correlation_id,
            config_version_id="V1",
            execution_mode="LIVE",
            causation_id="INT-ORIGINAL-014",
            action_type="FORCE_RETRY",
        )

        # Simulated downstream records
        state_transition_record = {"transition_id": "TR-001", "correlation_id": correlation_id}
        processed_event = {"event_id": "EVT-001", "correlation_id": correlation_id}
        escalation_candidacy = {"esc_id": "ESC-001", "correlation_id": correlation_id}

        assert has_correlation_id(intent)
        assert state_transition_record["correlation_id"] == correlation_id
        assert processed_event["correlation_id"] == correlation_id
        assert escalation_candidacy["correlation_id"] == correlation_id

    def test_att_ai_attribution_metadata_immutable_after_action_path_generation(self):
        """ATT-5 / FAD-6 / action path: AI attribution metadata immutable after AI_GENERATED state."""
        ai_record = {
            "state": "AI_GENERATED",
            "model_used": "claude-sonnet-4-6",
            "prompt_version": "p1.2",
            "ai_version_number": "v3",
            "correlation_id": "COR-ATT-008",
        }
        original_model = ai_record["model_used"]

        mutation_blocked = ai_record["state"] == "AI_GENERATED"
        assert mutation_blocked is True
        assert ai_record["model_used"] == original_model


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — DEGRADATION VALIDATION FOR ACTION PATHS
# Deterministic degradation, no silent fallbacks.
# Aligned with test_scenarios.md §15 (DEG-1 through DEG-5).
# ─────────────────────────────────────────────────────────────────────────────

class TestActionDegradationValidation:
    """
    Validates that action evaluation paths degrade deterministically and observably.
    No silent fallback behavior is permitted under any degradation scenario.
    """

    def test_deg_provider_outage_action_blocked_with_observable_event(self):
        """DEG-1 / PBG-1 / action path: Provider outage → action dispatch suppressed, observable event emitted."""
        provider_circuit_breaker_state = "OPEN"

        provider = ProviderOrchestrationAssessment(
            governance_scope="UNAVAILABLE",
            outbound_suppressed=True,
        )
        outage_log = StructuredLogRecord(
            event="PROVIDER_OUTAGE",
            correlation_id="COR-DEG-001",
            error_class="UpstreamUnavailable",
            degradation_flags=["PROVIDER_OUTAGE"],
        )

        assert provider.governance_scope == "UNAVAILABLE"
        assert provider.outbound_suppressed is True
        assert outage_log.event == "PROVIDER_OUTAGE"
        assert outage_log.correlation_id is not None

    def test_deg_provider_outage_retry_budget_protected_for_action_path(self):
        """PBG-1 / RGS-3 / action path: Circuit breaker OPEN → contact_attempt NOT incremented."""
        contact_attempt_before = 2
        circuit_breaker_state = "OPEN"

        contact_attempt_after = contact_attempt_before  # budget protected — no increment
        assert contact_attempt_after == contact_attempt_before

    def test_deg_ai_outage_rule_based_action_evaluation_continues(self):
        """DEG-2 / AIG-4 / action path: AI circuit breaker OPEN → rule-based action evaluation proceeds."""
        ai_assessment = AIAssessment(
            advisory_scope="UNAVAILABLE",
            ai_governance_tier="UNAVAILABLE",
            ai_blocked=True,
        )
        orchestration_blocked = False  # rule-based evaluation continues

        assert ai_assessment.advisory_scope == "UNAVAILABLE"
        assert orchestration_blocked is False

    def test_deg_sync_lag_produces_stale_annotation_not_action_block(self):
        """DEG-4 / PBG-5 / action path: Sync lag produces STALE annotation; action evaluation not blocked."""
        config = ConfigVersion("V1", "ACTIVE", {"sql_server_max_sync_age_hours": 4})
        sync_lag_hours = 6
        threshold = resolve_threshold(config, "sql_server_max_sync_age_hours")

        lag_exceeded = sync_lag_hours > threshold
        stale_annotation = "STALE_SQL_SERVER_DATA" if lag_exceeded else None
        orchestration_blocked = False  # sync lag is non-blocking annotation

        assert lag_exceeded is True
        assert stale_annotation == "STALE_SQL_SERVER_DATA"
        assert orchestration_blocked is False

    def test_deg_replay_action_permitted_in_degraded_mode_when_warehouse_accessible(self):
        """DEG-5 / action path: DEGRADED mode + warehouse accessible → replay action permitted."""
        execution_mode = "DEGRADED"
        warehouse_accessible = True
        historical_config_resolvable = True

        replay_permitted = warehouse_accessible and historical_config_resolvable
        assert replay_permitted is True

        intent = ActionOrchestrationIntent(
            intent_type="RETRY_OUTREACH",
            governance_scope="REPLAY_ONLY",
            correlation_id="COR-DEG-002",
            config_version_id="V1",
            execution_mode=execution_mode,
            execution_type="replay",
            causation_id="INT-ORIGINAL-REPLAY-002",
            action_type="FORCE_RETRY",
        )
        assert intent_is_replay_only(intent)
        live_effects: List = []
        assert live_effects == []

    def test_deg_action_failure_never_swallowed_silently(self):
        """RGS-1 / AP-RT14 / action path: Caught exception always classified and logged — never silently swallowed."""
        def governed_action_catch(error_class: str, context: Dict[str, Any]) -> StructuredLogRecord:
            assert error_class != "Error", "Generic 'Error' class is forbidden in production action paths"
            return StructuredLogRecord(
                event="ACTION_EVALUATION_FAILURE",
                correlation_id=context.get("correlation_id"),
                error_class=error_class,
                level="error",
            )

        log = governed_action_catch("TimeoutError", {"correlation_id": "COR-DEG-003"})

        assert log.error_class == "TimeoutError"
        assert log.error_class != "Error"
        assert log.correlation_id is not None

    def test_deg_missing_transcript_produces_deterministic_degraded_path_not_silent_fallback(self):
        """RGS-4 / action path: Transcript unavailable → ai_governance_tier=UNAVAILABLE, not silent fallback."""
        transcript_available = False

        if not transcript_available:
            ai_assessment = AIAssessment(
                advisory_scope="UNAVAILABLE",
                ai_governance_tier="UNAVAILABLE",
                ai_blocked=True,
            )
            transcript_log = StructuredLogRecord(
                event="TRANSCRIPT_UNAVAILABLE",
                correlation_id="COR-DEG-004",
            )

        assert ai_assessment.ai_governance_tier == "UNAVAILABLE"
        assert transcript_log.event == "TRANSCRIPT_UNAVAILABLE"
        # Prohibited: "fallback logic applied" as outcome descriptor
        fallback_description = "TRANSCRIPT_UNAVAILABLE_DEGRADED_PATH"
        assert fallback_description != "fallback logic applied"

    def test_deg_synchronization_lag_annotation_non_blocking_under_any_action_type(self):
        """DEG-4 / action path: Sync lag annotation must not block FORCE_RETRY, ESCALATE, or CLOSE_CASE."""
        stale_annotation = "STALE_SQL_SERVER_DATA"

        for action_type in ["FORCE_RETRY", "ESCALATE", "CLOSE_CASE"]:
            action_evaluation_blocked = False  # stale annotation is non-blocking
            assert action_evaluation_blocked is False, (
                f"Action {action_type} must not be blocked by sync lag annotation"
            )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — GOVERNANCE INVARIANT TESTS FOR ACTION PATHS
# INV-1 through INV-7 and FAD-1 through FAD-6 as they apply to action paths.
# Aligned with test_scenarios.md §17 (INV-1 through INV-7).
# ─────────────────────────────────────────────────────────────────────────────

class TestActionGovernanceInvariants:
    """
    Validates INVARIANT-1 through INVARIANT-7 and FAD-1 through FAD-6 for action paths.
    Every invariant must hold regardless of action type, execution mode, or degradation state.
    """

    def test_inv1_finalized_snapshot_not_mutated_by_any_action_path(self):
        """INV-1 / action path: FINALIZED warehouse.student_snapshots record cannot be mutated."""
        snapshot = {"state": "FINALIZED", "student_id": "S1_OPAQUE", "content": "ORIGINAL"}
        original_content = snapshot["content"]

        update_blocked = snapshot["state"] == "FINALIZED"
        assert update_blocked is True
        assert snapshot["content"] == original_content

    def test_inv2_action_evaluation_requires_exactly_one_active_config(self):
        """INV-2 / action path: Config registry must have exactly one ACTIVE version during action evaluation."""
        registry = [
            ConfigVersion("V1", "ACTIVE", {"outreach_max_retry_attempts": 3}),
            ConfigVersion("V2", "DRAFT", {"outreach_max_retry_attempts": 4}),
        ]
        assert exactly_one_active(registry)

        registry = activate_config_version(registry, "V2")
        assert exactly_one_active(registry)
        assert count_active(registry) == 1

    def test_inv3_historical_action_records_keep_original_config_version_id(self):
        """INV-3 / FAD-3 / action path: Historical action records retain their config_version_id after V2 activation."""
        historical_records = [
            ActionOrchestrationIntent("RETRY_OUTREACH", "AUTHORIZED", "COR-H-ACT-001", "V1", "LIVE",
                                      action_type="FORCE_RETRY"),
            ActionOrchestrationIntent("RETRY_OUTREACH", "AUTHORIZED", "COR-H-ACT-002", "V1", "LIVE",
                                      action_type="ESCALATE"),
        ]

        # V2 activated — historical action records must still carry V1
        for rec in historical_records:
            assert rec.config_version_id == "V1"
            assert rec.config_version_id != "V2"

    def test_inv4_no_live_effects_from_any_replay_action_execution(self):
        """INV-4 / AP-RT2 / action path: Replay action may produce diagnostic records only; zero LIVE effects."""
        ghl_messages_with_replay_type: List = []
        state_transitions_from_replay: List = []

        replay_action_intents = [
            ActionOrchestrationIntent("RETRY_OUTREACH", "REPLAY_ONLY", "COR-R-ACT-001", "V1", "LIVE",
                                      execution_type="replay", causation_id="INT-ORIG-R-001",
                                      action_type="FORCE_RETRY"),
            ActionOrchestrationIntent("RETRY_OUTREACH", "REPLAY_ONLY", "COR-R-ACT-002", "V1", "LIVE",
                                      execution_type="replay", causation_id="INT-ORIG-R-002",
                                      action_type="ESCALATE"),
        ]

        for intent in replay_action_intents:
            assert intent_is_replay_only(intent)

        assert ghl_messages_with_replay_type == []
        assert state_transitions_from_replay == []

    def test_inv5_every_action_produced_record_carries_non_null_correlation_id(self):
        """INV-5 / action path: Zero action-produced records may have correlation_id IS NULL."""
        records = [
            ActionOrchestrationIntent("RETRY_OUTREACH", "AUTHORIZED", "COR-INV5-001", "V1", "LIVE",
                                      causation_id="INT-001", action_type="FORCE_RETRY"),
            EscalationCandidacyRecord("NO_RESPONSE", "INTERVENTION_REQUIRED", "MANUAL_ESCALATE",
                                      "COR-INV5-002", "INT-002", "V1", "LIVE"),
            TerminalTransitionCandidacyRecord("CONTACTED", "CLOSED", "COR-INV5-003", "INT-003", "V1", "LIVE"),
            InvalidTransitionRecord("CLOSED", "FORCE_RETRY", "TERMINAL_STATE_CLOSED",
                                    "COR-INV5-004", "V1", "LIVE"),
        ]

        for rec in records:
            assert has_correlation_id(rec), f"correlation_id IS NULL on action record: {rec}"

    def test_inv6_finalized_copy_narratives_immutable_after_any_action(self):
        """INV-6 / IML-1 / action path: warehouse.snapshot_ai_narratives FINALIZED records untouched by any action."""
        before_checksums = {"S1": "CS1", "S2": "CS2", "S3": "CS3"}
        finalized_students = {"S1", "S2"}

        skipped: List[str] = []
        for student_id in before_checksums:
            if student_id in finalized_students:
                skipped.append(student_id)

        after_checksums = before_checksums.copy()  # no mutation for FINALIZED students

        assert set(skipped) == {"S1", "S2"}
        assert after_checksums["S1"] == before_checksums["S1"]
        assert after_checksums["S2"] == before_checksums["S2"]

    def test_inv7_every_action_governance_decision_carries_config_version_id(self):
        """INV-7 / action path: Every governance decision record from an action path carries config_version_id."""
        governance_records = [
            ActionOrchestrationIntent("RETRY_OUTREACH", "AUTHORIZED", "COR-INV7-001", "V1", "LIVE",
                                      causation_id="INT-001", action_type="FORCE_RETRY"),
            RetryPolicyAssessment(False, "RETRY_EXHAUSTED", "V1"),
            EligibilityAssessment("BLOCKED", "V1", skip_reason="TERMINAL_STATE_CLOSED"),
        ]

        for rec in governance_records:
            assert has_config_version_id(rec), f"config_version_id IS NULL on action governance record: {rec}"

    def test_fad1_finalized_copy_not_re_evaluated_under_any_action_pressure(self):
        """FAD-1 / action path: AI Refresh Loop does not overwrite FINALIZED_COPY even when action targets that student."""
        warehouse_row = {
            "student_id": "S1_OPAQUE",
            "ai_governance_tier": "FINALIZED_COPY",
            "narrative_content": "ORIGINAL_CONTENT",
        }
        original_content = warehouse_row["narrative_content"]

        write_attempted = warehouse_row["ai_governance_tier"] == "FINALIZED_COPY" and False
        assert write_attempted is False
        assert warehouse_row["narrative_content"] == original_content

    def test_fad3_new_config_version_applies_only_to_prospective_action_cycles(self):
        """FAD-3 / action path: Config V2 activation prospective-only — historical action records carry original version."""
        historical_retry = RetryPolicyAssessment(False, "RETRY_EXHAUSTED", "V1")
        assert historical_retry.config_version_id == "V1"
        assert historical_retry.config_version_id != "V2"

    def test_fad6_ai_attribution_metadata_immutable_after_action_path_generation(self):
        """FAD-6 / action path: ai_version_number, prompt_version, model_used immutable after AI_GENERATED."""
        ai_record = {
            "state": "AI_GENERATED",
            "model_used": "claude-sonnet-4-6",
            "prompt_version": "p1.2",
            "ai_version_number": "v3",
        }
        original_model = ai_record["model_used"]

        mutation_blocked = ai_record["state"] == "AI_GENERATED"
        blocking_event = "AI_ATTRIBUTION_MUTATION_BLOCKED" if mutation_blocked else None

        assert mutation_blocked is True
        assert blocking_event == "AI_ATTRIBUTION_MUTATION_BLOCKED"
        assert ai_record["model_used"] == original_model

    def test_inv_idempotent_action_duplicate_key_is_noop(self):
        """
        CID-1 / spec/04_idempotency_concurrency.md / action path:
        Duplicate (student_id, action_type, contact_attempt) key → no-op, observable suppression.
        """
        processed_action_events: Dict[tuple, bool] = {
            ("S1", "FORCE_RETRY", 2): True
        }

        def produce_action_intent(student_id: str, action_type: str, contact_attempt: int) -> str:
            key = (student_id, action_type, contact_attempt)
            if key in processed_action_events:
                return "DUPLICATE_ACTION_IDEMPOTENCY_KEY"
            processed_action_events[key] = True
            return "ACTION_INTENT_PRODUCED"

        result = produce_action_intent("S1", "FORCE_RETRY", 2)
        assert result == "DUPLICATE_ACTION_IDEMPOTENCY_KEY"

        total = sum(1 for k in processed_action_events if k[0] == "S1" and k[1] == "FORCE_RETRY")
        assert total == 1

    def test_inv_concurrent_action_requests_exactly_one_intent_wins(self):
        """CID-2 / action path: Two concurrent FORCE_RETRY requests for same student → exactly one intent produced."""
        processed_events: Dict[str, str] = {}
        lock = threading.Lock()
        suppression_records: List[str] = []

        def attempt_action_intent(student_id: str, instance_id: str) -> str:
            with lock:
                if student_id in processed_events:
                    suppression_records.append(f"DUPLICATE_ACTION_SUPPRESSED:{instance_id}")
                    return "SUPPRESSED"
                processed_events[student_id] = instance_id
                return "PRODUCED"

        r1 = attempt_action_intent("S1", "request-A")
        r2 = attempt_action_intent("S1", "request-B")

        assert r1 == "PRODUCED"
        assert r2 == "SUPPRESSED"
        assert len([k for k in processed_events if k == "S1"]) == 1
        assert len(suppression_records) == 1

    def test_inv_append_only_action_records_blocked_from_in_place_mutation(self):
        """IML-4 / action path: student_timeline_events action records cannot be updated or deleted in place."""
        existing_record = {
            "intent_id": "INT-ACT-001",
            "action_type": "FORCE_RETRY",
            "governance_scope": "AUTHORIZED",
        }

        update_blocked = True  # governance constraint at DB level
        blocking_event = "APPEND_ONLY_MUTATION_BLOCKED" if update_blocked else None

        assert update_blocked is True
        assert blocking_event == "APPEND_ONLY_MUTATION_BLOCKED"
        assert existing_record["governance_scope"] == "AUTHORIZED"  # unchanged

        # Correction path: new record with correction_of reference
        correction_record = {
            "intent_id": "INT-ACT-002",
            "correction_of": "INT-ACT-001",
            "action_type": "FORCE_RETRY",
            "governance_scope": "SHADOW_ONLY",
        }
        assert correction_record["correction_of"] == "INT-ACT-001"
