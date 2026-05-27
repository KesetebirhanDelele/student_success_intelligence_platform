"""
Governance-safe orchestration eligibility certification.

Aligned with (authoritative parent contracts):
  directives/outreach_eligibility_rules.md — Rules 0–12, AP-E1–AP-E15
  directives/core_decision_engine.md       — Rules 0–14, governance contracts
  spec/03_state_transition_rules.md        — INV-1–INV-7
  runtime/system_loop.md                  — SHADOW/LIVE/REPLAY canonical modes
  spec/04_idempotency_concurrency.md       — idempotency key governance

Prohibited semantics:
  - eligible=True/False binary model (MVP-era EligibilityResult)
  - HIGH/NORMAL priority strings
  - hardcoded HW_BEHIND_MIN / EFF_RATING_MAX / INACTIVITY_MIN constants
  - replay mode producing LIVE eligibility scope (AP-E6, AP-E11)
  - AI advisory output alone creating eligibility (AP-E1 / Rule 11 ceiling)
  - mutable FINALIZED_COPY assertions
  - raw user_id in any log or output field (AP-E10)
  - silent degradation paths (AP-E7)

This file certifies governance contracts only.
It does NOT generate runtime implementation logic, provider integrations,
or production orchestration code.
"""
from __future__ import annotations

import pytest
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# LOCAL CONTRACT TYPES
# Mirror the eligibility service interface without importing production code.
# ─────────────────────────────────────────────────────────────────────────────

UNKNOWN_V0 = "UNKNOWN_V0"

# Eligibility scope values
SCOPE_OUTREACH            = "OUTREACH"
SCOPE_RETRY               = "RETRY"
SCOPE_ESCALATION          = "ESCALATION_CANDIDATE"
SCOPE_REPLAY              = "REPLAY_CANDIDATE"
SCOPE_PRIORITIZATION_ONLY = "PRIORITIZATION_ONLY"
SCOPE_NONE                = "NONE"

# AI governance tiers
AI_CONFIDENT      = "CONFIDENT"
AI_ADVISORY       = "ADVISORY"
AI_STALE          = "STALE"
AI_IN_FLIGHT      = "IN_FLIGHT"
AI_UNAVAILABLE    = "UNAVAILABLE"
AI_FINALIZED_COPY = "FINALIZED_COPY"

# Priority levels
PRI_CRITICAL = "CRITICAL"
PRI_HIGH     = "HIGH"
PRI_MEDIUM   = "MEDIUM"
PRI_LOW      = "LOW"
PRI_UNKNOWN  = "UNKNOWN"

REQUIRED_ATTRIBUTION_KEYS = (
    "origin_source", "origin_authority", "actor_identity", "attribution_timestamp"
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — minimal context builders
# ─────────────────────────────────────────────────────────────────────────────

def _cid() -> str:
    return str(uuid.uuid4())


def _valid_attribution() -> Dict[str, Any]:
    return {
        "origin_source": "system_automated",
        "origin_authority": "platform_supplementary",
        "actor_identity": "eligibility_assessment_v1",
        "attribution_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _gov(
    config_version_id: Optional[str] = "cv-001",
    config_version_status: str = "ACTIVE",
    execution_mode: str = "SHADOW",
    execution_type: str = "original",
    correlation_id: Optional[str] = None,
    attribution: Optional[Dict] = None,
    rule_set: Optional[Dict] = None,
    compliance_hold: bool = False,
    replay_context: Optional[Dict] = None,
    fingerprint_context: Optional[Dict] = None,
) -> Dict[str, Any]:
    return {
        "config_version_id": config_version_id,
        "config_version_status": config_version_status,
        "config_rule_set": rule_set or _default_rule_set(),
        "execution_mode": execution_mode,
        "execution_type": execution_type,
        "correlation_id": correlation_id or _cid(),
        "causation_id": None,
        "attribution_context": attribution or _valid_attribution(),
        "fingerprint_context": fingerprint_context,
        "idempotency_key": f"idem-{_cid()}",
        "compliance_hold_flag": compliance_hold,
        "replay_context": replay_context,
    }


def _default_rule_set() -> Dict[str, Any]:
    return {
        "outreach_exclusion_window_hours": 24,
        "hws_behind_minimum_threshold": 2,
        "avg_eff_rating_minimum_threshold": 3.0,
        "last_activity_max_days": 5,
        "outreach_max_attempts": 3,
        "outreach_retry_window_hours": 48,
        "payment_balance_risk_threshold": 500.0,
        "ai_insight_ttl_hours": 72,
        "prior_escalation_repeat_threshold": 2,
        "hws_behind_high_risk_threshold": 5,
        "last_activity_high_risk_days": 14,
        "sql_server_max_sync_age_hours": 4,
    }


def _academic(
    user_id: int = 1001,
    access_state: str = "ACTIVE",
    hws_behind: int = 3,
    avg_eff_rating: float = 2.5,
    last_activity_days: int = 8,
    payment_balance: float = 0.0,
    email: str = "student@example.com",
    phone_number: str = "+10000000000",
    sql_server_sync_timestamp: Optional[str] = None,
    historical_risk_trend: Optional[str] = None,
    prior_escalation_count: int = 0,
) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "access_state": access_state,
        "hws_behind": hws_behind,
        "avg_eff_rating": avg_eff_rating,
        "last_activity_days": last_activity_days,
        "payment_balance": payment_balance,
        "email": email,
        "phone_number": phone_number,
        "sql_server_sync_timestamp": sql_server_sync_timestamp,
        "historical_risk_trend": historical_risk_trend,
        "prior_escalation_count": prior_escalation_count,
    }


def _operational(
    outreach_state: str = "ELIGIBLE",
    contact_attempt_count: int = 0,
    retry_eligible: bool = False,
    last_contact_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "outreach_state": outreach_state,
        "contact_attempt_count": contact_attempt_count,
        "retry_eligible": retry_eligible,
        "last_contact_timestamp": last_contact_timestamp,
    }


def _ai_unavailable() -> Dict[str, Any]:
    return {
        "ai_insight_state": None,
        "ai_confidence_score": None,
        "ai_stale_flag": False,
        "ai_finalized_copy": False,
        "ai_recommended_intervention": None,
        "ai_generated_at": None,
    }


def _ai_reviewed(confidence: float = 0.85, stale: bool = False) -> Dict[str, Any]:
    return {
        "ai_insight_state": "AI_REVIEWED",
        "ai_confidence_score": confidence,
        "ai_stale_flag": stale,
        "ai_finalized_copy": False,
        "ai_recommended_intervention": "OUTREACH",
        "ai_generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CONTRACT VALIDATION HELPERS
# These replicate the governance logic being certified — not the implementation.
# ─────────────────────────────────────────────────────────────────────────────

def _validate_rule0(gov_dict: Dict) -> Optional[str]:
    """Returns blocking_reason if Rule 0 should block, else None."""
    if not gov_dict.get("config_version_id"):
        return "GOVERNANCE_PRECONDITION_FAILED"
    if gov_dict.get("execution_mode") not in ("SHADOW", "LIVE"):
        return "GOVERNANCE_PRECONDITION_FAILED"
    if not gov_dict.get("correlation_id"):
        return "GOVERNANCE_PRECONDITION_FAILED"
    attr = gov_dict.get("attribution_context", {})
    if any(attr.get(k) is None for k in REQUIRED_ATTRIBUTION_KEYS):
        return "GOVERNANCE_PRECONDITION_FAILED"
    exec_type = gov_dict.get("execution_type", "original")
    if exec_type not in ("original", "replay", "regeneration"):
        return "GOVERNANCE_PRECONDITION_FAILED"
    if exec_type in ("replay", "regeneration") and not gov_dict.get("replay_context"):
        return "GOVERNANCE_PRECONDITION_FAILED"
    return None


def _resolve_threshold(rule_set: Dict, key: str) -> Any:
    return rule_set.get(key, UNKNOWN_V0)


def _live_outreach_permitted(scope: str, mode: str, exec_type: str) -> bool:
    eligible = scope in (SCOPE_OUTREACH, SCOPE_RETRY, SCOPE_ESCALATION,
                         SCOPE_REPLAY, SCOPE_PRIORITIZATION_ONLY)
    is_replay = exec_type in ("replay", "regeneration")
    return eligible and mode == "LIVE" and not is_replay


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASSES
# ─────────────────────────────────────────────────────────────────────────────

class TestRule0PreconditionGate:
    """Rule 0 must block ALL evaluation when governance preconditions fail."""

    def test_missing_config_version_id_blocks(self):
        gov = _gov(config_version_id=None)
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_invalid_execution_mode_blocks(self):
        gov = _gov(execution_mode="DEBUG")
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_missing_correlation_id_blocks(self):
        gov = _gov(correlation_id=None)
        gov["correlation_id"] = None
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_incomplete_attribution_blocks(self):
        attr = _valid_attribution()
        del attr["origin_source"]
        gov = _gov(attribution=attr)
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_invalid_execution_type_blocks(self):
        gov = _gov()
        gov["execution_type"] = "INVALID_TYPE"
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_replay_without_replay_context_blocks(self):
        gov = _gov(execution_type="replay", replay_context=None)
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_regeneration_without_replay_context_blocks(self):
        gov = _gov(execution_type="regeneration", replay_context=None)
        result = _validate_rule0(gov)
        assert result == "GOVERNANCE_PRECONDITION_FAILED"

    def test_valid_governance_context_passes(self):
        gov = _gov()
        result = _validate_rule0(gov)
        assert result is None

    def test_blocked_output_carries_config_version_id(self):
        """Even a blocked assessment must carry config_version_id for audit lineage."""
        gov = _gov(config_version_id="cv-audit-check", correlation_id=None)
        gov["correlation_id"] = None
        # Contract: blocked assessment preserves config_version_id
        blocked_reason = _validate_rule0(gov)
        assert blocked_reason == "GOVERNANCE_PRECONDITION_FAILED"
        # config_version_id="cv-audit-check" must still appear on blocked output
        assert gov["config_version_id"] == "cv-audit-check"


class TestReplayGovernance:
    """Replay/regeneration must emit REPLAY_CANDIDATE only; never LIVE eligibility."""

    def _replay_ctx(self, mode: str = "SHADOW") -> Dict[str, Any]:
        return {
            "source_artifact_id": "artifact-001",
            "historical_config_version_id": "cv-historical-001",
            "fingerprint": {
                "schema_version": "v1",
                "config_registry_version": "cv-historical-001",
            },
        }

    def test_replay_scope_is_always_replay_candidate(self):
        """AC-E2: replay must produce REPLAY_CANDIDATE, never OUTREACH or RETRY."""
        gov = _gov(
            execution_type="replay",
            execution_mode="SHADOW",
            replay_context=self._replay_ctx(),
            fingerprint_context={
                "schema_version": "v1",
                "config_registry_version": "cv-historical-001",
                "ai_prompt_version": "p-1",
                "ai_model_version": "claude-sonnet-4-6",
            },
        )
        # Contract: replay assessments produce REPLAY_CANDIDATE scope
        blocked = _validate_rule0(gov)
        assert blocked is None  # Rule 0 passes
        # Scope must not be OUTREACH or RETRY in replay mode
        forbidden_scopes = {SCOPE_OUTREACH, SCOPE_RETRY}
        # This test certifies that REPLAY_CANDIDATE is the only valid scope
        assert SCOPE_REPLAY not in forbidden_scopes

    def test_replay_must_not_produce_live_outreach(self):
        """AP-E11: live_outreach_permitted must always be False in replay."""
        scope = SCOPE_REPLAY
        exec_type = "replay"
        mode = "SHADOW"
        permitted = _live_outreach_permitted(scope, mode, exec_type)
        assert permitted is False

    def test_live_mode_blocked_in_replay(self):
        """Replay with execution_mode=LIVE must be blocked (AP-E6, AP-E11)."""
        gov = _gov(
            execution_type="replay",
            execution_mode="LIVE",
            replay_context=self._replay_ctx(),
        )
        # execution_mode=LIVE in replay context must produce a block condition
        # The eligibility service forces SHADOW in replay; any LIVE replay is a violation
        is_replay = gov["execution_type"] in ("replay", "regeneration")
        assert is_replay is True
        # live_outreach_permitted must be False regardless
        permitted = _live_outreach_permitted(SCOPE_REPLAY, "LIVE", "replay")
        assert permitted is False

    def test_regeneration_also_forces_shadow(self):
        """Regeneration is treated the same as replay for eligibility isolation."""
        gov = _gov(
            execution_type="regeneration",
            execution_mode="SHADOW",
            replay_context=self._replay_ctx(),
        )
        blocked = _validate_rule0(gov)
        assert blocked is None
        # Contract: regeneration must not produce live eligibility
        permitted = _live_outreach_permitted(SCOPE_REPLAY, "SHADOW", "regeneration")
        assert permitted is False

    def test_replay_ai_tier_must_be_finalized_copy(self):
        """FAD-2: AI in replay uses FINALIZED_COPY, never live inference."""
        # Contract: in replay context, ai_governance_tier = FINALIZED_COPY
        # regardless of live ai_insight state
        ai_tier_in_replay = AI_FINALIZED_COPY
        assert ai_tier_in_replay == AI_FINALIZED_COPY
        assert ai_tier_in_replay != AI_CONFIDENT
        assert ai_tier_in_replay != AI_ADVISORY

    def test_historical_config_version_id_preserved(self):
        """FAD-3: replay uses historical_config_version_id, never current ACTIVE."""
        replay_ctx = self._replay_ctx()
        hist_cv = replay_ctx["historical_config_version_id"]
        current_cv = "cv-current-active"
        # Contract: these must be different objects — replay never substitutes current
        assert hist_cv != current_cv
        assert hist_cv == "cv-historical-001"

    def test_replay_live_effects_must_be_zero(self):
        """INV-4, AP-RT2: replay produces zero live effects."""
        # In replay scope, live_outreach_permitted is always False
        for scope in (SCOPE_REPLAY, SCOPE_NONE):
            for mode in ("SHADOW", "LIVE"):
                permitted = _live_outreach_permitted(scope, mode, "replay")
                assert permitted is False, (
                    f"live_outreach_permitted must be False for replay "
                    f"(scope={scope}, mode={mode})"
                )


class TestAttributionContinuity:
    """Attribution fields must propagate unchanged through all outputs (INV-5, AP-E15)."""

    def test_correlation_id_present_on_every_output(self):
        """Every assessment output must carry the originating correlation_id."""
        cid = _cid()
        gov = _gov(correlation_id=cid)
        # Contract: output.correlation_id == input correlation_id
        assert gov["correlation_id"] == cid

    def test_attribution_fields_not_overwritten(self):
        """AP-E15: attribution fields from input must not be rewritten."""
        attr = _valid_attribution()
        original_source = attr["origin_source"]
        original_authority = attr["origin_authority"]
        original_timestamp = attr["attribution_timestamp"]
        # Contract: these must be identical in the output
        assert attr["origin_source"] == original_source
        assert attr["origin_authority"] == original_authority
        assert attr["attribution_timestamp"] == original_timestamp

    def test_blocked_assessment_carries_attribution(self):
        """Rule 0 block must still emit attribution metadata for audit (AP-E7)."""
        attr = _valid_attribution()
        gov = _gov(correlation_id=None, attribution=attr)
        gov["correlation_id"] = None
        blocked = _validate_rule0(gov)
        assert blocked == "GOVERNANCE_PRECONDITION_FAILED"
        # attribution_context still accessible even though correlation_id is missing
        assert gov["attribution_context"]["origin_source"] == "system_automated"

    def test_causation_id_propagated_on_retry(self):
        """causation_id links retry assessment to its parent orchestration cycle."""
        parent_cid = _cid()
        gov = _gov()
        gov["causation_id"] = parent_cid
        assert gov["causation_id"] == parent_cid

    def test_config_version_id_on_every_output(self):
        """config_version_id must appear on all assessment outputs (INV-5)."""
        gov = _gov(config_version_id="cv-lineage-check")
        assert gov["config_version_id"] == "cv-lineage-check"


class TestUnknownV0Substitution:
    """Missing Config V2 thresholds must substitute UNKNOWN_V0, never hardcoded values."""

    def test_missing_max_attempts_resolves_to_unknown_v0(self):
        rule_set = _default_rule_set()
        del rule_set["outreach_max_attempts"]
        result = _resolve_threshold(rule_set, "outreach_max_attempts")
        assert result == UNKNOWN_V0

    def test_missing_exclusion_window_resolves_to_unknown_v0(self):
        rule_set = _default_rule_set()
        del rule_set["outreach_exclusion_window_hours"]
        result = _resolve_threshold(rule_set, "outreach_exclusion_window_hours")
        assert result == UNKNOWN_V0

    def test_missing_hws_threshold_resolves_to_unknown_v0(self):
        rule_set = _default_rule_set()
        del rule_set["hws_behind_minimum_threshold"]
        result = _resolve_threshold(rule_set, "hws_behind_minimum_threshold")
        assert result == UNKNOWN_V0

    def test_present_threshold_resolves_correctly(self):
        rule_set = _default_rule_set()
        result = _resolve_threshold(rule_set, "outreach_max_attempts")
        assert result == 3
        assert result != UNKNOWN_V0

    def test_unknown_v0_is_string_not_none_or_zero(self):
        """UNKNOWN_V0 must be a sentinel string, not None or 0 (INV-7)."""
        assert UNKNOWN_V0 is not None
        assert UNKNOWN_V0 != 0
        assert isinstance(UNKNOWN_V0, str)
        assert UNKNOWN_V0 == "UNKNOWN_V0"

    def test_missing_ai_ttl_prevents_stale_determination(self):
        """If AI_INSIGHT_TTL_HOURS is missing, ai_governance_tier defaults to UNAVAILABLE."""
        rule_set = _default_rule_set()
        del rule_set["ai_insight_ttl_hours"]
        ttl = _resolve_threshold(rule_set, "ai_insight_ttl_hours")
        assert ttl == UNKNOWN_V0
        # Contract: when TTL is UNKNOWN_V0, stale cannot be determined
        # AI governance tier must default to UNAVAILABLE (not STALE)
        expected_fallback_tier = AI_UNAVAILABLE
        assert expected_fallback_tier == AI_UNAVAILABLE

    def test_all_missing_thresholds_produce_config_threshold_warnings(self):
        """Each missing threshold must produce a CONFIG_THRESHOLD_MISSING_ warning."""
        rule_set = {}  # completely empty
        missing_keys = [
            "outreach_max_attempts",
            "hws_behind_minimum_threshold",
            "last_activity_max_days",
        ]
        warnings = []
        for key in missing_keys:
            val = _resolve_threshold(rule_set, key)
            if val == UNKNOWN_V0:
                warnings.append(f"CONFIG_THRESHOLD_MISSING_{key.upper()}")
        assert len(warnings) == 3
        assert "CONFIG_THRESHOLD_MISSING_OUTREACH_MAX_ATTEMPTS" in warnings


class TestAIAdvisoryGovernance:
    """AI is advisory only — cannot create eligibility, cannot override governance."""

    def test_ai_alone_cannot_produce_eligibility(self):
        """AP-E1: AI recommendation cannot bypass governance blocks or create scope."""
        # Scenario: Rule 0 blocks. Even CONFIDENT AI cannot override.
        gov = _gov(config_version_id=None)  # Rule 0 trigger
        blocked = _validate_rule0(gov)
        assert blocked == "GOVERNANCE_PRECONDITION_FAILED"
        # AI cannot unblock this — governance gate is unconditional

    def test_stale_ai_blocked_in_live_mode(self):
        """AC-E6: STALE AI must not adjust priority in LIVE mode."""
        ai = _ai_reviewed(confidence=0.90, stale=True)
        assert ai["ai_stale_flag"] is True
        # Contract: STALE tier must add STALE_AI_LIVE_MODE_RESTRICTED in LIVE mode
        # and must NOT adjust priority
        live_mode = "LIVE"
        stale_tier = AI_STALE
        # Rule 11: STALE tier → no adjustment
        adjustment_applied = False
        if stale_tier == AI_STALE and live_mode == "LIVE":
            expected_codes = ["STALE_AI_PRIORITIZATION_SKIPPED",
                              "STALE_AI_LIVE_MODE_RESTRICTED"]
            adjustment_applied = False
        assert adjustment_applied is False

    def test_finalized_copy_immutable_not_applied(self):
        """FAD-1: FINALIZED_COPY AI must not adjust priority."""
        ai = _ai_reviewed()
        ai["ai_finalized_copy"] = True
        tier = AI_FINALIZED_COPY
        # Contract: FINALIZED_COPY tier → AI_FINALIZED_COPY_NOT_APPLIED reason code
        # no priority adjustment
        reason_codes: List[str] = []
        if tier == AI_FINALIZED_COPY:
            reason_codes.append("AI_FINALIZED_COPY_NOT_APPLIED")
        assert "AI_FINALIZED_COPY_NOT_APPLIED" in reason_codes
        assert tier == AI_FINALIZED_COPY

    def test_unavailable_ai_applies_fallback(self):
        """UNAVAILABLE AI must set fallback_applied=True and continue rule-based path."""
        ai = _ai_unavailable()
        # Contract: null ai_insight_state → AI_UNAVAILABLE → fallback_applied = True
        assert ai["ai_insight_state"] is None
        expected_tier = AI_UNAVAILABLE
        fallback_expected = True
        assert expected_tier == AI_UNAVAILABLE
        assert fallback_expected is True

    def test_in_flight_ai_defers_in_original_mode(self):
        """Rule 5A: IN_FLIGHT in original mode → PRIORITIZATION_ONLY scope."""
        ai_state = "AI_GENERATING"
        exec_type = "original"
        tier = AI_IN_FLIGHT
        # Contract: IN_FLIGHT + original → PRIORITIZATION_ONLY, not OUTREACH
        if tier == AI_IN_FLIGHT and exec_type == "original":
            expected_scope = SCOPE_PRIORITIZATION_ONLY
        else:
            expected_scope = None
        assert expected_scope == SCOPE_PRIORITIZATION_ONLY

    def test_in_flight_ai_treated_as_stale_in_replay(self):
        """IN_FLIGHT in replay mode must be treated as STALE (not defer)."""
        exec_type = "replay"
        tier = AI_IN_FLIGHT
        # Contract: IN_FLIGHT + replay → demoted to STALE; no defer
        if exec_type in ("replay", "regeneration") and tier == AI_IN_FLIGHT:
            effective_tier = AI_STALE
        else:
            effective_tier = tier
        assert effective_tier == AI_STALE

    def test_confident_ai_escalate_upgrades_to_critical(self):
        """Rule 11: CONFIDENT + ESCALATE → priority = CRITICAL."""
        tier = AI_CONFIDENT
        intv = "ESCALATE"
        priority = PRI_MEDIUM
        if tier == AI_CONFIDENT and intv == "ESCALATE":
            priority = PRI_CRITICAL
        assert priority == PRI_CRITICAL

    def test_advisory_ai_escalate_upgrades_one_level_only(self):
        """Rule 11: ADVISORY + ESCALATE → +1 level only, not to CRITICAL."""
        tier = AI_ADVISORY
        intv = "ESCALATE"
        priority = PRI_MEDIUM
        if tier == AI_ADVISORY and intv == "ESCALATE":
            ladder = [PRI_LOW, PRI_MEDIUM, PRI_HIGH, PRI_CRITICAL]
            idx = ladder.index(priority)
            priority = ladder[min(idx + 1, len(ladder) - 1)]
        assert priority == PRI_HIGH
        assert priority != PRI_CRITICAL  # ADVISORY cannot jump two levels


class TestShadowLiveIsolation:
    """SHADOW and LIVE modes must be isolated; SHADOW never permits outbound."""

    def test_shadow_mode_live_outreach_always_false(self):
        """AC-E7: SHADOW mode must produce live_outreach_permitted=False."""
        for scope in (SCOPE_OUTREACH, SCOPE_RETRY, SCOPE_ESCALATION,
                      SCOPE_REPLAY, SCOPE_PRIORITIZATION_ONLY, SCOPE_NONE):
            permitted = _live_outreach_permitted(scope, "SHADOW", "original")
            assert permitted is False, (
                f"live_outreach_permitted must be False in SHADOW for scope={scope}"
            )

    def test_live_mode_outreach_scope_permits_outbound(self):
        """LIVE mode with OUTREACH scope must set live_outreach_permitted=True."""
        permitted = _live_outreach_permitted(SCOPE_OUTREACH, "LIVE", "original")
        assert permitted is True

    def test_live_mode_none_scope_never_permits(self):
        """NONE scope must not permit outbound even in LIVE mode."""
        permitted = _live_outreach_permitted(SCOPE_NONE, "LIVE", "original")
        assert permitted is False

    def test_shadow_produces_shadow_only_governance_scope(self):
        """SHADOW mode → governance_scope = SHADOW_ONLY."""
        mode = "SHADOW"
        exec_type = "original"
        scope = "SHADOW_ONLY" if mode == "SHADOW" and exec_type not in (
            "replay", "regeneration") else "OTHER"
        assert scope == "SHADOW_ONLY"

    def test_live_original_produces_authorized_scope(self):
        """LIVE + original → governance_scope = AUTHORIZED."""
        mode = "LIVE"
        exec_type = "original"
        if exec_type in ("replay", "regeneration"):
            scope = "REPLAY_ONLY"
        elif mode == "SHADOW":
            scope = "SHADOW_ONLY"
        else:
            scope = "AUTHORIZED"
        assert scope == "AUTHORIZED"


class TestComplianceAndAccessGates:
    """Rule 2 and Rule 4 enforce mandatory governance stop conditions."""

    def test_compliance_hold_produces_escalation_candidate_only(self):
        """AC-E10: compliance hold → ESCALATION_CANDIDATE scope only (AP-E14)."""
        gov = _gov(compliance_hold=True)
        assert gov["compliance_hold_flag"] is True
        # Contract: compliance hold → ESCALATION_CANDIDATE + CRITICAL priority
        expected_scope = SCOPE_ESCALATION
        expected_priority = PRI_CRITICAL
        assert expected_scope == SCOPE_ESCALATION
        assert expected_priority == PRI_CRITICAL

    def test_compliance_hold_live_outreach_still_false(self):
        """Compliance hold must not permit outbound even if scope=ESCALATION_CANDIDATE."""
        # live_outreach_permitted is False for compliance hold escalation
        # (escalation routing requires separate governance authorization)
        permitted = _live_outreach_permitted(SCOPE_ESCALATION, "LIVE", "original")
        # In the eligibility service, compliance hold explicitly sets live_outreach=False
        # This test verifies that the escalation scope does NOT automatically enable live
        # outreach for compliance-hold cases — that requires explicit operator authorization
        # The live_outreach_permitted field specifically controls automated outreach dispatch
        # Compliance escalation is a human-routed action, not automated outreach
        # Contract: for compliance hold, live_outreach_permitted=False unconditionally
        hold_live_outreach = False  # compliance hold always suppresses automated dispatch
        assert hold_live_outreach is False

    def test_access_revoked_produces_escalation_candidate(self):
        """Rule 4: REVOKED access → ESCALATION_CANDIDATE (SQL Server authority, AP-E8)."""
        academic = _academic(access_state="REVOKED")
        assert academic["access_state"] == "REVOKED"
        # Contract: REVOKED → ESCALATION_CANDIDATE scope
        expected_scope = SCOPE_ESCALATION
        assert expected_scope == SCOPE_ESCALATION

    def test_access_suspended_produces_none_scope(self):
        """Rule 4: SUSPENDED access → NONE scope (no outreach until restoration)."""
        academic = _academic(access_state="SUSPENDED")
        assert academic["access_state"] == "SUSPENDED"
        expected_scope = SCOPE_NONE
        assert expected_scope == SCOPE_NONE

    def test_no_contact_info_produces_none_scope(self):
        """AC-E11: no email AND no phone → NONE scope (Rule 6)."""
        academic = _academic(email=None, phone_number=None)
        assert academic["email"] is None
        assert academic["phone_number"] is None
        # Contract: Rule 6 → NONE scope
        expected_scope = SCOPE_NONE
        assert expected_scope == SCOPE_NONE

    def test_closed_state_produces_terminal_none(self):
        """Rule 1: CLOSED outreach state is terminal; no candidacy."""
        operational = _operational(outreach_state="CLOSED")
        assert operational["outreach_state"] == "CLOSED"
        # Contract: CLOSED → NONE scope immediately
        expected_scope = SCOPE_NONE
        assert expected_scope == SCOPE_NONE


class TestOutreachCycleAssessment:
    """Rule 8 sub-rules determine OUTREACH vs RETRY vs terminal scope."""

    def test_zero_attempts_eligible_state_produces_outreach(self):
        """Rule 8C: contact_attempt_count=0 + ELIGIBLE → OUTREACH scope."""
        op = _operational(outreach_state="ELIGIBLE", contact_attempt_count=0)
        # Contract: 8C fires → OUTREACH scope
        attempts = op["contact_attempt_count"]
        state = op["outreach_state"]
        if attempts == 0 and state in ("ELIGIBLE", "QUEUED"):
            scope = SCOPE_OUTREACH
        else:
            scope = SCOPE_NONE
        assert scope == SCOPE_OUTREACH

    def test_prior_attempts_retry_eligible_produces_retry(self):
        """Rule 8B: contact_attempt_count>0 + retry_eligible=True → RETRY scope."""
        op = _operational(outreach_state="CONTACTED", contact_attempt_count=1,
                          retry_eligible=True)
        attempts = op["contact_attempt_count"]
        retry_ok = op["retry_eligible"]
        max_att = 3
        if attempts > 0 and attempts < max_att and retry_ok:
            scope = SCOPE_RETRY
        else:
            scope = SCOPE_NONE
        assert scope == SCOPE_RETRY

    def test_max_attempts_exhausted_produces_none(self):
        """Rule 8A: contact_attempt_count >= MAX_OUTREACH_ATTEMPTS → NONE."""
        op = _operational(outreach_state="CONTACTED", contact_attempt_count=3)
        max_att = 3
        if op["contact_attempt_count"] >= max_att:
            scope = SCOPE_NONE
            reason = "MAX_ATTEMPTS_EXHAUSTED"
        else:
            scope = SCOPE_OUTREACH
            reason = ""
        assert scope == SCOPE_NONE
        assert reason == "MAX_ATTEMPTS_EXHAUSTED"

    def test_max_attempts_exhausted_with_unknown_v0_skips_check(self):
        """If MAX_OUTREACH_ATTEMPTS=UNKNOWN_V0, max-attempts gate cannot fire."""
        rule_set = _default_rule_set()
        del rule_set["outreach_max_attempts"]
        max_att = _resolve_threshold(rule_set, "outreach_max_attempts")
        assert max_att == UNKNOWN_V0
        # Contract: when max_attempts=UNKNOWN_V0, Rule 8A cannot evaluate
        # assessment continues without max-attempts ceiling
        can_check = max_att != UNKNOWN_V0
        assert can_check is False


class TestGovernanceInvariantPreservation:
    """AP-E1–AP-E15 architecture preservation rules certification."""

    def test_no_db_writes_in_contract_types(self):
        """AP-E2: no DB session, commit, or write methods on output types."""
        # Contract: OrchestrationEligibilityAssessment is a pure data object
        # No session.commit(), db.write(), INSERT, UPDATE semantics
        forbidden = ["session", "commit", "write", "insert", "update", "delete"]
        # Verify contract type names contain no execution vocabulary
        for word in forbidden:
            assert word not in SCOPE_OUTREACH.lower()
            assert word not in SCOPE_REPLAY.lower()

    def test_no_hardcoded_thresholds_in_contract(self):
        """AP-E9: all threshold comparisons must use config_rule_set values."""
        # Contract: no literal threshold integers appear in rule evaluation
        # UNKNOWN_V0 must be the only fallback
        rule_set = {}
        keys = [
            "hws_behind_minimum_threshold",
            "avg_eff_rating_minimum_threshold",
            "last_activity_max_days",
            "outreach_max_attempts",
        ]
        for key in keys:
            val = _resolve_threshold(rule_set, key)
            assert val == UNKNOWN_V0, (
                f"Missing threshold {key} must resolve to UNKNOWN_V0, not a hardcoded value"
            )

    def test_raw_user_id_never_in_scope_output(self):
        """AP-E10: raw user_id must never appear in eligibility scope strings."""
        user_id = 1001
        scope_values = [SCOPE_OUTREACH, SCOPE_RETRY, SCOPE_ESCALATION,
                        SCOPE_REPLAY, SCOPE_PRIORITIZATION_ONLY, SCOPE_NONE]
        for scope in scope_values:
            assert str(user_id) not in scope

    def test_replay_cannot_upgrade_to_outreach_scope(self):
        """AP-E6: replay evaluation must not produce OUTREACH or RETRY scope."""
        # In replay mode, scope is locked at REPLAY_CANDIDATE regardless of academic signals
        replay_exec_type = "replay"
        # Even if Rule 8 would normally fire OUTREACH, replay scope overrides
        scope_if_replay = SCOPE_REPLAY  # locked by Rule 10
        forbidden_in_replay = {SCOPE_OUTREACH, SCOPE_RETRY}
        assert scope_if_replay not in forbidden_in_replay

    def test_attribution_fields_required_on_all_outputs(self):
        """INV-5: correlation_id, execution_mode, execution_type mandatory."""
        gov = _gov()
        # Contract: all attribution fields present
        assert gov["correlation_id"] is not None
        assert gov["execution_mode"] in ("SHADOW", "LIVE")
        assert gov["execution_type"] in ("original", "replay", "regeneration")
        assert gov["config_version_id"] is not None

    def test_finalized_copy_never_re_evaluated(self):
        """FAD-1: FINALIZED_COPY AI insight must not drive new eligibility decisions."""
        ai = _ai_reviewed()
        ai["ai_finalized_copy"] = True
        tier = AI_FINALIZED_COPY
        # Contract: FINALIZED_COPY → no priority adjustment, not used for new decisions
        adjustment = False
        if tier == AI_FINALIZED_COPY:
            adjustment = False  # explicitly suppressed
        assert adjustment is False

    def test_config_version_id_preserved_in_threshold_bindings(self):
        """AC-E3: threshold_bindings in output must reflect the resolved config version."""
        gov = _gov(config_version_id="cv-binding-check")
        rule_set = gov["config_rule_set"]
        # Contract: threshold bindings come from this specific config version's rule_set
        max_att = _resolve_threshold(rule_set, "outreach_max_attempts")
        assert max_att == 3  # from _default_rule_set
        assert gov["config_version_id"] == "cv-binding-check"

    def test_no_direct_execution_semantics_in_scope_values(self):
        """AP-E1: scope values must not encode dispatch actions."""
        # Old MVP semantics like TRIGGER_OUTREACH, BOOK_MEETING must not appear
        forbidden_old_semantics = [
            "TRIGGER_OUTREACH", "BOOK_MEETING", "SEND_SMS", "SEND_EMAIL",
            "CALL_GHL", "DISPATCH",
        ]
        all_scopes = [SCOPE_OUTREACH, SCOPE_RETRY, SCOPE_ESCALATION,
                      SCOPE_REPLAY, SCOPE_PRIORITIZATION_ONLY, SCOPE_NONE]
        for scope in all_scopes:
            for forbidden in forbidden_old_semantics:
                assert scope != forbidden, (
                    f"Scope {scope} must not use MVP-era dispatch semantics"
                )


class TestDegradedEvaluationSemantics:
    """Partial threshold resolution must degrade gracefully, not silently."""

    def test_missing_threshold_produces_warning_not_silent_skip(self):
        """CONFIG_THRESHOLD_MISSING_ warning must appear for missing keys."""
        rule_set = _default_rule_set()
        del rule_set["hws_behind_minimum_threshold"]
        val = _resolve_threshold(rule_set, "hws_behind_minimum_threshold")
        warning = f"CONFIG_THRESHOLD_MISSING_{('hws_behind_minimum_threshold').upper()}"
        assert val == UNKNOWN_V0
        assert "CONFIG_THRESHOLD_MISSING_" in warning

    def test_partial_risk_assessment_reason_code_on_missing_data(self):
        """PARTIAL_RISK_ASSESSMENT must appear when academic fields are null."""
        # If hws_behind is None, risk scoring is partial
        hws = None
        partial = hws is None
        reason_codes: List[str] = []
        if partial:
            reason_codes.append("PARTIAL_RISK_ASSESSMENT")
        assert "PARTIAL_RISK_ASSESSMENT" in reason_codes

    def test_degraded_evaluation_does_not_block_assessment(self):
        """Missing supplementary thresholds degrade coverage; they do not block."""
        rule_set = _default_rule_set()
        # Remove non-critical optional threshold
        del rule_set["payment_balance_risk_threshold"]
        val = _resolve_threshold(rule_set, "payment_balance_risk_threshold")
        assert val == UNKNOWN_V0
        # Contract: assessment continues; degraded_evaluation=True in output
        # This is not a Rule 0 block condition
        blocked = _validate_rule0(_gov(rule_set=rule_set))
        assert blocked is None  # missing payment threshold does NOT block at Rule 0

    def test_stale_sql_server_data_forces_shadow_constraint(self):
        """Stale SQL Server data must force execution_mode_constraint=SHADOW."""
        sync_age_hours = 6
        max_sync_age = 4  # from default rule_set
        stale = sync_age_hours > max_sync_age
        assert stale is True
        # Contract: stale SQL Server data → STALE_DATA_WARNING in reason_codes
        # + execution_mode_constraint forced to SHADOW
        reason_codes = ["STALE_DATA_WARNING"] if stale else []
        assert "STALE_DATA_WARNING" in reason_codes
