"""Tests for governance-safe degradation alert classification (Phase 46)."""
from __future__ import annotations

import app.services.alerts as _alerts_module
from app.services.alerts import classify_degradation_alert
from app.services._alert_types import (
    ACTION_DEAD_LETTER,
    ACTION_DEGRADED_CONTINUATION,
    ACTION_ESCALATION_CANDIDACY,
    ACTION_GOVERNED_RECOVERY,
    ACTION_NO_OP,
    BASIS_HISTORICAL_REPLAY,
    DOMAIN_AI,
    DOMAIN_ATTRIBUTION,
    DOMAIN_COMPLIANCE,
    DOMAIN_FINGERPRINT,
    DOMAIN_OBSERVABILITY,
    DOMAIN_ORCHESTRATION,
    DOMAIN_PROVIDER,
    DOMAIN_REPLAY,
    DOMAIN_SCHEDULER,
    DOMAIN_SYNCHRONIZATION,
    DOMAIN_UNKNOWN,
    K_AI_ABSENT_CRITICAL_HOURS,
    K_AI_STALE_HIGH_HOURS,
    K_PROVIDER_RETRY_LIMIT,
    K_SCHEDULER_HEARTBEAT_MS,
    K_SLA_REPORT_MS,
    K_STUCK_COMPLIANCE_HIGH_HOURS,
    K_STUCK_WORKFLOW_HIGH_HOURS,
    K_SYNC_STALE_HOURS,
    MODE_LIVE,
    MODE_SHADOW,
    OUTCOME_DEGRADED,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    SCOPE_MAINTENANCE,
    SCOPE_REPLAY_ONLY,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    SEVERITY_UNKNOWN,
    TYPE_ORIGINAL,
    TYPE_RECOVERY,
    TYPE_REGENERATION,
    TYPE_REPLAY,
    UNKNOWN_V0,
    _ALERT_THRESHOLD_KEYS,
    AlertClassificationContext,
)

# ── Test helpers ──────────────────────────────────────────────────────────────

_FULL_RULE_SET = {
    K_SCHEDULER_HEARTBEAT_MS: 30_000,
    K_SYNC_STALE_HOURS: 2.0,
    K_AI_STALE_HIGH_HOURS: 4.0,
    K_AI_ABSENT_CRITICAL_HOURS: 24.0,
    K_STUCK_WORKFLOW_HIGH_HOURS: 8.0,
    K_STUCK_COMPLIANCE_HIGH_HOURS: 4.0,
    K_PROVIDER_RETRY_LIMIT: 3,
    K_SLA_REPORT_MS: 60_000,
}


def _live_ctx(**overrides) -> AlertClassificationContext:
    defaults = dict(
        config_version_id="cfg-v2-001",
        execution_mode=MODE_LIVE,
        execution_type=TYPE_ORIGINAL,
        correlation_id="corr-001",
        degradation_domain=DOMAIN_SCHEDULER,
        failure_cause="test_scheduler_lag",
        error_class=None,
        config_rule_set=_FULL_RULE_SET.copy(),
        origin_source="orchestration_engine",
        origin_authority="system_governance",
        actor_identity="scheduler_worker",
    )
    defaults.update(overrides)
    return AlertClassificationContext(**defaults)


def _shadow_ctx(**overrides) -> AlertClassificationContext:
    defaults = dict(
        config_version_id="cfg-v2-001",
        execution_mode=MODE_SHADOW,
        execution_type=TYPE_ORIGINAL,
        correlation_id="corr-shadow-001",
        degradation_domain=DOMAIN_SCHEDULER,
        failure_cause="test_shadow_lag",
        error_class=None,
        config_rule_set=_FULL_RULE_SET.copy(),
        origin_source="orchestration_engine",
        origin_authority="system_governance",
        actor_identity="scheduler_worker",
    )
    defaults.update(overrides)
    return AlertClassificationContext(**defaults)


def _replay_ctx(**overrides) -> AlertClassificationContext:
    defaults = dict(
        config_version_id="cfg-v2-001",
        execution_mode=MODE_LIVE,
        execution_type=TYPE_REPLAY,
        correlation_id="corr-replay-001",
        degradation_domain=DOMAIN_SCHEDULER,
        failure_cause="test_replay",
        error_class=None,
        config_rule_set=_FULL_RULE_SET.copy(),
        origin_source="replay_engine",
        origin_authority="system_governance",
        actor_identity="replay_worker",
        historical_config_version_id="hist-cfg-v2-001",
    )
    defaults.update(overrides)
    return AlertClassificationContext(**defaults)


# ── 1. RULE 0 Governance Preconditions ───────────────────────────────────────

class TestRule0GovernancePreconditions:
    def setup_method(self):
        _alerts_module._alert_idempotency_keys.clear()

    def test_missing_origin_source_blocked(self):
        r = classify_degradation_alert(_live_ctx(origin_source=None))
        assert r.orchestration_blocked is True
        assert "ATTRIBUTION_INCOMPLETE" in r.reason_codes

    def test_missing_origin_authority_blocked(self):
        r = classify_degradation_alert(_live_ctx(origin_authority=None))
        assert r.orchestration_blocked is True
        assert "ATTRIBUTION_INCOMPLETE" in r.reason_codes

    def test_missing_actor_identity_blocked(self):
        r = classify_degradation_alert(_live_ctx(actor_identity=None))
        assert r.orchestration_blocked is True
        assert "ATTRIBUTION_INCOMPLETE" in r.reason_codes

    def test_missing_correlation_id_blocked(self):
        r = classify_degradation_alert(_live_ctx(correlation_id=None))
        assert r.orchestration_blocked is True
        assert "CORRELATION_ID_MISSING" in r.reason_codes

    def test_invalid_execution_mode_blocked(self):
        r = classify_degradation_alert(_live_ctx(execution_mode="INVALID_MODE"))
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_MODE" in r.reason_codes

    def test_invalid_execution_type_blocked(self):
        r = classify_degradation_alert(_live_ctx(execution_type="bad_type"))
        assert r.orchestration_blocked is True
        assert "INVALID_EXECUTION_TYPE" in r.reason_codes

    def test_replay_without_historical_config_blocked(self):
        r = classify_degradation_alert(
            _live_ctx(execution_type=TYPE_REPLAY, historical_config_version_id=None)
        )
        assert r.orchestration_blocked is True
        assert "REPLAY_LINEAGE_INCOMPLETE" in r.reason_codes

    def test_regeneration_without_historical_config_blocked(self):
        r = classify_degradation_alert(
            _live_ctx(execution_type=TYPE_REGENERATION, historical_config_version_id=None)
        )
        assert r.orchestration_blocked is True
        assert "REPLAY_LINEAGE_INCOMPLETE" in r.reason_codes

    def test_duplicate_idempotency_key_blocked(self):
        key = "idem-key-001"
        _alerts_module._alert_idempotency_keys.add(key)
        r = classify_degradation_alert(_live_ctx(idempotency_key=key))
        assert r.orchestration_blocked is True
        assert "IDEMPOTENCY_KEY_DUPLICATE" in r.reason_codes

    def test_blocked_record_outcome_failure(self):
        r = classify_degradation_alert(_live_ctx(correlation_id=None))
        assert r.outcome == OUTCOME_FAILURE

    def test_blocked_record_scope_unavailable(self):
        r = classify_degradation_alert(_live_ctx(origin_source=None))
        assert r.governance_scope == SCOPE_UNAVAILABLE
        assert r.orchestration_continues is False

    def test_blocked_record_invariants(self):
        r = classify_degradation_alert(_live_ctx(origin_source=None))
        assert r.append_only_enforced is True
        assert r.replay_lineage_preserved is True
        assert r.alert_lineage_immutable is True
        assert r.alert_emit_authorized is False
        assert r.suppression_visible is True

    def test_valid_context_not_blocked(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.orchestration_blocked is False


# ── 2. Maintenance Mode ───────────────────────────────────────────────────────

class TestMaintenanceMode:
    def test_maintenance_scope(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.governance_scope == SCOPE_MAINTENANCE

    def test_maintenance_severity_info(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.severity == SEVERITY_INFO

    def test_maintenance_outcome_success(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.outcome == OUTCOME_SUCCESS

    def test_maintenance_recovery_action_noop(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.recovery_action == ACTION_NO_OP

    def test_maintenance_orchestration_not_continues(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.orchestration_continues is False
        assert r.orchestration_blocked is False

    def test_maintenance_invariants(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.append_only_enforced is True
        assert r.replay_lineage_preserved is True
        assert r.alert_lineage_immutable is True
        assert r.alert_emit_authorized is False


# ── 3. Replay Path ────────────────────────────────────────────────────────────

class TestReplayPath:
    def test_replay_type_scope_replay_only(self):
        r = classify_degradation_alert(_replay_ctx(execution_type=TYPE_REPLAY))
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_regeneration_type_scope_replay_only(self):
        r = classify_degradation_alert(
            _replay_ctx(execution_type=TYPE_REGENERATION)
        )
        assert r.governance_scope == SCOPE_REPLAY_ONLY

    def test_replay_is_replay_true(self):
        r = classify_degradation_alert(_replay_ctx())
        assert r.is_replay is True

    def test_replay_live_effects_suppressed(self):
        r = classify_degradation_alert(_replay_ctx())
        assert r.live_effects_suppressed is True

    def test_replay_severity_unknown(self):
        r = classify_degradation_alert(_replay_ctx())
        assert r.severity == SEVERITY_UNKNOWN

    def test_replay_no_escalation(self):
        r = classify_degradation_alert(_replay_ctx())
        assert r.escalation_candidacy is False

    def test_replay_orchestration_continues(self):
        r = classify_degradation_alert(_replay_ctx(source_artifact_id="src-001"))
        assert r.orchestration_continues is True

    def test_replay_assessment_basis_historical(self):
        r = classify_degradation_alert(_replay_ctx())
        assert r.assessment_basis == BASIS_HISTORICAL_REPLAY


# ── 4. Replay Source Artifact ─────────────────────────────────────────────────

class TestReplaySourceArtifact:
    def test_missing_source_artifact_degraded(self):
        r = classify_degradation_alert(_replay_ctx(source_artifact_id=None))
        assert r.degraded is True

    def test_missing_source_artifact_outcome_degraded(self):
        r = classify_degradation_alert(_replay_ctx(source_artifact_id=None))
        assert r.outcome == OUTCOME_DEGRADED

    def test_missing_source_artifact_flag_set(self):
        r = classify_degradation_alert(_replay_ctx(source_artifact_id=None))
        assert "REPLAY_SOURCE_ARTIFACT_MISSING" in r.degradation_flags

    def test_source_artifact_present_not_degraded(self):
        r = classify_degradation_alert(_replay_ctx(source_artifact_id="src-artifact-001"))
        assert r.degraded is False
        assert r.outcome == OUTCOME_SUCCESS


# ── 5. Threshold Resolution ───────────────────────────────────────────────────

class TestThresholdResolution:
    def test_full_rule_set_binds_all_keys(self):
        r = classify_degradation_alert(_live_ctx())
        for key in _ALERT_THRESHOLD_KEYS:
            assert key in r.threshold_bindings

    def test_no_rule_set_all_unknown_v0(self):
        r = classify_degradation_alert(_live_ctx(config_rule_set=None))
        for key in _ALERT_THRESHOLD_KEYS:
            assert r.threshold_bindings[key] == UNKNOWN_V0

    def test_partial_rule_set_missing_keys_unknown_v0(self):
        partial = {K_SCHEDULER_HEARTBEAT_MS: 30_000}
        r = classify_degradation_alert(_live_ctx(config_rule_set=partial))
        assert r.threshold_bindings[K_SCHEDULER_HEARTBEAT_MS] == 30_000
        assert r.threshold_bindings[K_SYNC_STALE_HOURS] == UNKNOWN_V0

    def test_unknown_v0_threshold_does_not_block_classification(self):
        r = classify_degradation_alert(_live_ctx(config_rule_set=None))
        assert r.orchestration_blocked is False

    def test_threshold_bindings_has_exactly_8_keys(self):
        r = classify_degradation_alert(_live_ctx())
        assert len(r.threshold_bindings) == len(_ALERT_THRESHOLD_KEYS)


# ── 6. Scheduler Severity ─────────────────────────────────────────────────────

class TestSchedulerSeverityClassification:
    def test_lag_above_heartbeat_threshold_critical(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_SCHEDULER,
                scheduler_lag_ms=60_000,  # > 30_000 threshold
            )
        )
        assert r.severity == SEVERITY_CRITICAL

    def test_lag_below_heartbeat_threshold_high(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_SCHEDULER,
                scheduler_lag_ms=15_000,  # < 30_000 threshold
            )
        )
        assert r.severity == SEVERITY_HIGH

    def test_lag_with_unknown_v0_threshold_high(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_SCHEDULER,
                scheduler_lag_ms=60_000,
                config_rule_set=None,
            )
        )
        assert r.severity == SEVERITY_HIGH

    def test_workflow_stuck_above_threshold_high(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_SCHEDULER,
                workflow_stuck_hours=10.0,  # > 8.0 threshold
            )
        )
        assert r.severity == SEVERITY_HIGH

    def test_no_scheduler_signals_unknown_severity(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_SCHEDULER)
        )
        assert r.severity == SEVERITY_UNKNOWN

    def test_scheduler_critical_recovery_governed(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_SCHEDULER, scheduler_lag_ms=60_000)
        )
        assert r.recovery_action == ACTION_GOVERNED_RECOVERY


# ── 7. AI Severity ────────────────────────────────────────────────────────────

class TestAISeverityClassification:
    def test_ai_absent_above_threshold_critical(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_AI,
                ai_absent_hours=30.0,  # > 24.0 threshold
            )
        )
        assert r.severity == SEVERITY_CRITICAL

    def test_ai_stale_above_threshold_high(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_AI,
                ai_stale_hours=6.0,  # > 4.0 threshold
            )
        )
        assert r.severity == SEVERITY_HIGH

    def test_ai_stale_with_unknown_v0_medium(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_AI,
                ai_stale_hours=6.0,
                config_rule_set=None,
            )
        )
        assert r.severity == SEVERITY_MEDIUM

    def test_ai_no_signals_unknown(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=DOMAIN_AI))
        assert r.severity == SEVERITY_UNKNOWN

    def test_ai_critical_recovery_escalation(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_AI, ai_absent_hours=30.0)
        )
        assert r.recovery_action == ACTION_ESCALATION_CANDIDACY

    def test_ai_high_recovery_degraded_continuation(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_AI, ai_stale_hours=6.0)
        )
        assert r.recovery_action == ACTION_DEGRADED_CONTINUATION


# ── 8. Provider Severity ──────────────────────────────────────────────────────

class TestProviderSeverityClassification:
    def test_circuit_breaker_critical(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_PROVIDER, circuit_breaker_open=True)
        )
        assert r.severity == SEVERITY_CRITICAL

    def test_provider_outage_high(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_PROVIDER, provider_outage_active=True)
        )
        assert r.severity == SEVERITY_HIGH

    def test_retry_at_limit_high(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_PROVIDER,
                retry_count=3,  # == 3 limit
            )
        )
        assert r.severity == SEVERITY_HIGH

    def test_retry_with_unknown_v0_threshold_medium(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_PROVIDER,
                retry_count=5,
                config_rule_set=None,
            )
        )
        assert r.severity == SEVERITY_MEDIUM

    def test_provider_no_signals_unknown(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=DOMAIN_PROVIDER))
        assert r.severity == SEVERITY_UNKNOWN

    def test_provider_critical_recovery_escalation(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_PROVIDER, circuit_breaker_open=True)
        )
        assert r.recovery_action == ACTION_ESCALATION_CANDIDACY

    def test_provider_high_recovery_degraded_continuation(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_PROVIDER, provider_outage_active=True)
        )
        assert r.recovery_action == ACTION_DEGRADED_CONTINUATION


# ── 9. Compliance Severity ────────────────────────────────────────────────────

class TestComplianceSeverity:
    def test_compliance_hold_high(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_COMPLIANCE, compliance_hold_active=True)
        )
        assert r.severity == SEVERITY_HIGH

    def test_compliance_hold_with_stuck_above_threshold_critical(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_COMPLIANCE,
                compliance_hold_active=True,
                workflow_stuck_hours=5.0,  # > 4.0 stuck compliance threshold
            )
        )
        assert r.severity == SEVERITY_CRITICAL

    def test_compliance_no_hold_unknown(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_COMPLIANCE, compliance_hold_active=False)
        )
        assert r.severity == SEVERITY_UNKNOWN

    def test_compliance_critical_recovery_dead_letter(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_COMPLIANCE,
                compliance_hold_active=True,
                workflow_stuck_hours=5.0,
            )
        )
        assert r.recovery_action == ACTION_DEAD_LETTER


# ── 10. Degradation Flags ─────────────────────────────────────────────────────

class TestDegradationFlags:
    def test_scheduler_lag_flag(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_SCHEDULER, scheduler_lag_ms=60_000)
        )
        assert "SCHEDULER_HEARTBEAT_MISSED" in r.degradation_flags
        assert r.degraded is True

    def test_sync_stale_flag(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_SYNCHRONIZATION, sync_lag_hours=3.0)
        )
        assert "SYNC_STALE" in r.degradation_flags

    def test_ai_absent_flag(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_AI, ai_absent_hours=30.0)
        )
        assert "AI_ABSENT" in r.degradation_flags

    def test_provider_circuit_breaker_flag(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_PROVIDER, circuit_breaker_open=True)
        )
        assert "CIRCUIT_BREAKER_OPEN" in r.degradation_flags

    def test_compliance_hold_flag(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_COMPLIANCE, compliance_hold_active=True)
        )
        assert "COMPLIANCE_HOLD_ACTIVE" in r.degradation_flags

    def test_fingerprint_divergence_flag(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_FINGERPRINT, fingerprint_divergence=True)
        )
        assert "FINGERPRINT_DIVERGENCE" in r.degradation_flags

    def test_workflow_stuck_flag_added_any_domain(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_ORCHESTRATION, workflow_stuck_hours=10.0)
        )
        assert "WORKFLOW_STUCK" in r.degradation_flags

    def test_no_signals_no_flags_not_degraded(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=DOMAIN_SCHEDULER))
        assert r.degradation_flags == []
        assert r.degraded is False


# ── 11. Governance Scope ──────────────────────────────────────────────────────

class TestGovernanceScope:
    def test_shadow_mode_shadow_only_scope(self):
        r = classify_degradation_alert(_shadow_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_shadow_only_scope(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.governance_scope == SCOPE_SHADOW_ONLY

    def test_shadow_live_effects_suppressed(self):
        r = classify_degradation_alert(_shadow_ctx())
        assert r.live_effects_suppressed is True

    def test_live_live_effects_suppressed(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.live_effects_suppressed is True

    def test_orchestration_continues_normal_path(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.orchestration_continues is True

    def test_escalation_candidacy_critical(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_SCHEDULER, scheduler_lag_ms=60_000)
        )
        assert r.escalation_candidacy is True

    def test_escalation_candidacy_high(self):
        r = classify_degradation_alert(
            _live_ctx(
                degradation_domain=DOMAIN_ORCHESTRATION,
                workflow_stuck_hours=10.0,
            )
        )
        assert r.escalation_candidacy is True

    def test_no_escalation_below_high(self):
        r = classify_degradation_alert(
            _live_ctx(degradation_domain=DOMAIN_OBSERVABILITY, is_observability_degraded=True)
        )
        assert r.escalation_candidacy is False


# ── 12. Invariant Fields ──────────────────────────────────────────────────────

class TestInvariantFields:
    def test_append_only_enforced_live_path(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.append_only_enforced is True

    def test_replay_lineage_preserved_live_path(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.replay_lineage_preserved is True

    def test_alert_lineage_immutable_live_path(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.alert_lineage_immutable is True

    def test_suppression_visible_unconditional(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.suppression_visible is True

    def test_alert_emit_authorized_false_live_path(self):
        r = classify_degradation_alert(_live_ctx())
        assert r.alert_emit_authorized is False

    def test_invariants_on_replay_path(self):
        r = classify_degradation_alert(_replay_ctx())
        assert r.append_only_enforced is True
        assert r.replay_lineage_preserved is True
        assert r.alert_lineage_immutable is True
        assert r.alert_emit_authorized is False

    def test_invariants_on_maintenance_path(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        assert r.append_only_enforced is True
        assert r.replay_lineage_preserved is True
        assert r.alert_lineage_immutable is True

    def test_invariants_on_blocked_path(self):
        r = classify_degradation_alert(_live_ctx(origin_source=None))
        assert r.append_only_enforced is True
        assert r.replay_lineage_preserved is True
        assert r.alert_lineage_immutable is True


# ── 13. Attribution and Lineage ───────────────────────────────────────────────

class TestAttributionAndLineage:
    def test_origin_source_propagated(self):
        r = classify_degradation_alert(_live_ctx(origin_source="test_origin"))
        assert r.origin_source == "test_origin"

    def test_origin_authority_propagated(self):
        r = classify_degradation_alert(_live_ctx(origin_authority="test_authority"))
        assert r.origin_authority == "test_authority"

    def test_actor_identity_propagated(self):
        r = classify_degradation_alert(_live_ctx(actor_identity="test_actor"))
        assert r.actor_identity == "test_actor"

    def test_correlation_id_propagated(self):
        r = classify_degradation_alert(_live_ctx(correlation_id="corr-xyz"))
        assert r.correlation_id == "corr-xyz"

    def test_causation_id_propagated_chain_preserved(self):
        r = classify_degradation_alert(_live_ctx(causation_id="cause-001"))
        assert r.causation_id == "cause-001"
        assert r.causation_chain_preserved is True

    def test_causation_chain_not_preserved_when_none(self):
        r = classify_degradation_alert(_live_ctx(causation_id=None))
        assert r.causation_chain_preserved is False

    def test_config_version_id_propagated(self):
        r = classify_degradation_alert(_live_ctx(config_version_id="cfg-v2-test"))
        assert r.config_version_id == "cfg-v2-test"

    def test_student_id_opaque_propagated(self):
        r = classify_degradation_alert(_live_ctx(student_id_opaque="opaque-s-001"))
        assert r.student_id_opaque == "opaque-s-001"


# ── 14. Domain Validation ─────────────────────────────────────────────────────

class TestDomainValidation:
    def test_unknown_domain_string_normalized(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain="not_a_real_domain"))
        assert r.degradation_domain == DOMAIN_UNKNOWN
        assert "DOMAIN_UNKNOWN" in r.reason_codes

    def test_none_domain_normalized_to_unknown(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=None))
        assert r.degradation_domain == DOMAIN_UNKNOWN

    def test_valid_domain_preserved(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=DOMAIN_ORCHESTRATION))
        assert r.degradation_domain == DOMAIN_ORCHESTRATION

    def test_domain_in_record_matches_input(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=DOMAIN_PROVIDER))
        assert r.degradation_domain == DOMAIN_PROVIDER

    def test_error_class_mapped_from_domain(self):
        r = classify_degradation_alert(_live_ctx(degradation_domain=DOMAIN_AI))
        assert r.error_class_classified == "AIDegradationError"


# ── 15. Rule Path Tracking ────────────────────────────────────────────────────

class TestRulePathTracking:
    def test_normal_path_contains_all_rules(self):
        r = classify_degradation_alert(_live_ctx())
        path = r.rule_path_taken
        assert "RULE_0_GOVERNANCE_GATE" in path
        assert "RULE_3_THRESHOLD_RESOLUTION" in path
        assert "RULE_6_SEVERITY" in path
        assert "RULE_10_EMIT" in path

    def test_blocked_path_only_rule_0(self):
        r = classify_degradation_alert(_live_ctx(origin_source=None))
        assert r.rule_path_taken == ["RULE_0_GOVERNANCE_GATE"]

    def test_maintenance_path_rules(self):
        r = classify_degradation_alert(_live_ctx(maintenance_mode_active=True))
        path = r.rule_path_taken
        assert "RULE_0_GOVERNANCE_GATE" in path
        assert "RULE_1_MAINTENANCE" in path
        assert "RULE_10_EMIT" not in path

    def test_replay_path_rules(self):
        r = classify_degradation_alert(_replay_ctx())
        path = r.rule_path_taken
        assert "RULE_0_GOVERNANCE_GATE" in path
        assert "RULE_2_REPLAY" in path
        assert "RULE_6_SEVERITY" not in path
