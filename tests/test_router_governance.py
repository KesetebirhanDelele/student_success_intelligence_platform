"""
Governance certification suite for the API/router governance alignment layer.

Self-contained: no mocks needed for core governance logic. All router helpers
are pure functions — no AsyncSession, no HTTP stack, no database.

Validates:
  - CID-1  : correlation_id extracted or generated on every request
  - IML-1  : attribution propagated immutably into response meta
  - INV-5  : no response without correlation_id in meta
  - FAD-1  : FINALIZED protection fields correctly exposed
  - RSV-1  : replay classification correctly surfaced
  - AP-RT13: PII never in governance meta fields
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Optional

import pytest

from app.routers._router_helpers import (
    build_finalized_protection_fields,
    build_governance_attribution_fields,
    build_request_attribution,
    check_attribution_complete,
    extract_causation_id,
    extract_correlation_id,
    extract_execution_type,
    governance_scope_for_mode,
    make_governance_meta,
    replay_visibility_fields,
)
from app.routers._router_types import (
    FINALIZED_ACTIVE,
    FINALIZED_READ_ONLY,
    GOVERNANCE_CAUSATION_HEADER,
    GOVERNANCE_CORRELATION_HEADER,
    GOVERNANCE_EXECUTION_TYPE_HEADER,
    REPLAY_EXECUTION_TYPES,
    REQUIRED_ROUTER_ATTRIBUTION,
    SCOPE_LIVE_AUTHORIZED,
    SCOPE_SHADOW_ONLY,
    SUPPRESSION_LIVE_EFFECTS_DISABLED,
    SUPPRESSION_SHADOW_MODE,
    GovernanceMeta,
)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _shadow_attribution(**overrides):
    base = dict(
        correlation_id=_uuid(),
        execution_mode="SHADOW",
        execution_type="original",
        governance_scope=SCOPE_SHADOW_ONLY,
    )
    base.update(overrides)
    from app.repositories._repository_types import AttributionFields
    return AttributionFields(**base)


def _live_attribution(**overrides):
    base = dict(
        correlation_id=_uuid(),
        execution_mode="LIVE",
        execution_type="original",
        governance_scope=SCOPE_LIVE_AUTHORIZED,
    )
    base.update(overrides)
    from app.repositories._repository_types import AttributionFields
    return AttributionFields(**base)


class _FakeInsight:
    """Minimal ORM-like object for FINALIZED protection tests."""
    def __init__(self, is_finalized=False, finalized_at=None,
                 correlation_id=None, causation_id=None,
                 execution_mode="SHADOW", execution_type="original",
                 governance_scope=SCOPE_SHADOW_ONLY,
                 is_replay=False, attribution_complete=False):
        self.is_finalized = is_finalized
        self.finalized_at = finalized_at
        self.correlation_id = correlation_id
        self.causation_id = causation_id
        self.execution_mode = execution_mode
        self.execution_type = execution_type
        self.governance_scope = governance_scope
        self.is_replay = is_replay
        self.attribution_complete = attribution_complete
        self.config_version_id = None


class _FakeHistoryRow:
    """Minimal ORM-like object for attribution/replay field tests."""
    def __init__(self, correlation_id=None, causation_id=None,
                 config_version_id=None, execution_mode="SHADOW",
                 execution_type="original", governance_scope=SCOPE_SHADOW_ONLY,
                 is_replay=False, attribution_complete=False,
                 replay_context=None):
        self.correlation_id = correlation_id
        self.causation_id = causation_id
        self.config_version_id = config_version_id
        self.execution_mode = execution_mode
        self.execution_type = execution_type
        self.governance_scope = governance_scope
        self.is_replay = is_replay
        self.attribution_complete = attribution_complete
        self.replay_context = replay_context


# ── TestExtractCorrelationId ──────────────────────────────────────────────────

class TestExtractCorrelationId:
    def test_header_present_and_valid_returned(self):
        result = extract_correlation_id({GOVERNANCE_CORRELATION_HEADER: "abc-123"})
        assert result == "abc-123"

    def test_absent_header_generates_uuid(self):
        result = extract_correlation_id({})
        assert len(result) == 36
        assert "-" in result

    def test_empty_string_generates_uuid(self):
        result = extract_correlation_id({GOVERNANCE_CORRELATION_HEADER: ""})
        assert len(result) == 36

    def test_whitespace_only_generates_uuid(self):
        result = extract_correlation_id({GOVERNANCE_CORRELATION_HEADER: "   "})
        assert len(result) == 36

    def test_strips_whitespace_from_valid_value(self):
        result = extract_correlation_id({GOVERNANCE_CORRELATION_HEADER: "  test-cid  "})
        assert result == "test-cid"

    def test_never_returns_empty_string(self):
        for headers in [{}, {GOVERNANCE_CORRELATION_HEADER: ""}, {GOVERNANCE_CORRELATION_HEADER: " "}]:
            assert extract_correlation_id(headers) != ""

    def test_two_absent_calls_generate_distinct_ids(self):
        r1 = extract_correlation_id({})
        r2 = extract_correlation_id({})
        assert r1 != r2

    def test_case_sensitive_header_key(self):
        result = extract_correlation_id({"x-correlation-id": "wrong-key"})
        assert result != "wrong-key"


# ── TestExtractCausationId ────────────────────────────────────────────────────

class TestExtractCausationId:
    def test_present_value_returned(self):
        result = extract_causation_id({GOVERNANCE_CAUSATION_HEADER: "caus-id-1"})
        assert result == "caus-id-1"

    def test_absent_returns_none(self):
        assert extract_causation_id({}) is None

    def test_empty_returns_none(self):
        assert extract_causation_id({GOVERNANCE_CAUSATION_HEADER: ""}) is None

    def test_whitespace_returns_none(self):
        assert extract_causation_id({GOVERNANCE_CAUSATION_HEADER: "   "}) is None

    def test_strips_whitespace(self):
        result = extract_causation_id({GOVERNANCE_CAUSATION_HEADER: "  c-id  "})
        assert result == "c-id"


# ── TestExtractExecutionType ──────────────────────────────────────────────────

class TestExtractExecutionType:
    def test_absent_defaults_to_original(self):
        assert extract_execution_type({}) == "original"

    def test_replay_value_returned(self):
        assert extract_execution_type({GOVERNANCE_EXECUTION_TYPE_HEADER: "replay"}) == "replay"

    def test_regeneration_value_returned(self):
        result = extract_execution_type({GOVERNANCE_EXECUTION_TYPE_HEADER: "regeneration"})
        assert result == "regeneration"

    def test_empty_defaults_to_original(self):
        assert extract_execution_type({GOVERNANCE_EXECUTION_TYPE_HEADER: ""}) == "original"


# ── TestGovernanceScopeForMode ────────────────────────────────────────────────

class TestGovernanceScopeForMode:
    def test_shadow_yields_shadow_only(self):
        assert governance_scope_for_mode("SHADOW") == SCOPE_SHADOW_ONLY

    def test_live_yields_live_authorized(self):
        assert governance_scope_for_mode("LIVE") == SCOPE_LIVE_AUTHORIZED

    def test_unknown_mode_yields_live_authorized(self):
        assert governance_scope_for_mode("UNKNOWN") == SCOPE_LIVE_AUTHORIZED


# ── TestBuildRequestAttribution ───────────────────────────────────────────────

class TestBuildRequestAttribution:
    def test_shadow_mode_produces_shadow_only_scope(self):
        attr = build_request_attribution("cid-1", execution_mode="SHADOW")
        assert attr.execution_mode == "SHADOW"
        assert attr.governance_scope == SCOPE_SHADOW_ONLY

    def test_live_mode_produces_live_authorized_scope(self):
        attr = build_request_attribution("cid-1", execution_mode="LIVE")
        assert attr.governance_scope == SCOPE_LIVE_AUTHORIZED

    def test_original_execution_type_not_replay(self):
        attr = build_request_attribution("cid-1", execution_type="original", execution_mode="SHADOW")
        assert attr.is_replay is False

    def test_replay_execution_type_sets_is_replay_true(self):
        attr = build_request_attribution("cid-1", execution_type="replay", execution_mode="SHADOW")
        assert attr.is_replay is True

    def test_regeneration_execution_type_sets_is_replay_true(self):
        attr = build_request_attribution("cid-1", execution_type="regeneration", execution_mode="SHADOW")
        assert attr.is_replay is True

    def test_correlation_id_propagated(self):
        cid = _uuid()
        attr = build_request_attribution(cid, execution_mode="SHADOW")
        assert attr.correlation_id == cid

    def test_causation_id_propagated(self):
        attr = build_request_attribution("cid", causation_id="cause-1", execution_mode="SHADOW")
        assert attr.causation_id == "cause-1"

    def test_config_version_id_propagated(self):
        attr = build_request_attribution("cid", config_version_id="v2", execution_mode="SHADOW")
        assert attr.config_version_id == "v2"

    def test_all_replay_types_covered(self):
        for et in REPLAY_EXECUTION_TYPES:
            attr = build_request_attribution("cid", execution_type=et, execution_mode="SHADOW")
            assert attr.is_replay is True


# ── TestMakeGovernanceMeta ────────────────────────────────────────────────────

class TestMakeGovernanceMeta:
    def test_shadow_mode_adds_both_suppression_codes(self):
        attr = _shadow_attribution()
        meta = make_governance_meta(attr)
        assert SUPPRESSION_SHADOW_MODE in meta.suppression_codes
        assert SUPPRESSION_LIVE_EFFECTS_DISABLED in meta.suppression_codes

    def test_live_mode_has_no_suppression_codes(self):
        attr = _live_attribution()
        meta = make_governance_meta(attr)
        assert meta.suppression_codes == []

    def test_correlation_id_propagated_to_meta(self):
        cid = _uuid()
        attr = _shadow_attribution(correlation_id=cid)
        meta = make_governance_meta(attr)
        assert meta.correlation_id == cid

    def test_causation_id_propagated_to_meta(self):
        attr = _shadow_attribution(causation_id="caus-abc")
        meta = make_governance_meta(attr)
        assert meta.causation_id == "caus-abc"

    def test_execution_mode_propagated_to_meta(self):
        attr = _shadow_attribution()
        meta = make_governance_meta(attr)
        assert meta.execution_mode == "SHADOW"

    def test_governance_scope_propagated_to_meta(self):
        attr = _shadow_attribution()
        meta = make_governance_meta(attr)
        assert meta.governance_scope == SCOPE_SHADOW_ONLY

    def test_is_replay_propagated_to_meta(self):
        attr = _shadow_attribution(is_replay=True, execution_type="replay")
        meta = make_governance_meta(attr)
        assert meta.is_replay is True

    def test_attribution_complete_when_all_required_fields_present(self):
        attr = _shadow_attribution()
        meta = make_governance_meta(attr)
        assert meta.attribution_complete is True

    def test_attribution_incomplete_when_correlation_id_empty(self):
        attr = _shadow_attribution(correlation_id="")
        meta = make_governance_meta(attr)
        assert meta.attribution_complete is False

    def test_attribution_incomplete_when_governance_scope_empty(self):
        attr = _shadow_attribution(governance_scope="")
        meta = make_governance_meta(attr)
        assert meta.attribution_complete is False

    def test_timestamp_present_in_meta(self):
        attr = _shadow_attribution()
        meta = make_governance_meta(attr)
        assert meta.timestamp
        assert "T" in meta.timestamp

    def test_custom_timestamp_used_when_supplied(self):
        attr = _shadow_attribution()
        ts = "2026-01-01T00:00:00+00:00"
        meta = make_governance_meta(attr, timestamp=ts)
        assert meta.timestamp == ts

    def test_as_dict_contains_all_governance_fields(self):
        attr = _shadow_attribution()
        d = make_governance_meta(attr).as_dict()
        for field in ("correlation_id", "execution_mode", "execution_type",
                      "governance_scope", "is_replay", "attribution_complete",
                      "suppression_codes", "timestamp"):
            assert field in d, f"Missing field: {field}"

    def test_as_dict_contains_no_pii(self):
        attr = _shadow_attribution()
        d = make_governance_meta(attr).as_dict()
        pii_keys = {"email", "phone", "first_name", "last_name", "user_id"}
        assert not pii_keys.intersection(d.keys()), "PII found in governance meta"


# ── TestCheckAttributionComplete ─────────────────────────────────────────────

class TestCheckAttributionComplete:
    def test_complete_when_all_required_present(self):
        attr = _shadow_attribution()
        assert check_attribution_complete(attr) is True

    def test_incomplete_when_correlation_id_missing(self):
        attr = _shadow_attribution(correlation_id="")
        assert check_attribution_complete(attr) is False

    def test_incomplete_when_execution_mode_missing(self):
        attr = _shadow_attribution(execution_mode="")
        assert check_attribution_complete(attr) is False

    def test_incomplete_when_governance_scope_missing(self):
        attr = _shadow_attribution(governance_scope="")
        assert check_attribution_complete(attr) is False

    def test_required_fields_defined_by_constant(self):
        assert "correlation_id" in REQUIRED_ROUTER_ATTRIBUTION
        assert "execution_mode" in REQUIRED_ROUTER_ATTRIBUTION
        assert "governance_scope" in REQUIRED_ROUTER_ATTRIBUTION


# ── TestBuildFinalizedProtectionFields ───────────────────────────────────────

class TestBuildFinalizedProtectionFields:
    def test_not_finalized_object_returns_active_classification(self):
        obj = _FakeInsight(is_finalized=False)
        fields = build_finalized_protection_fields(obj)
        assert fields["is_finalized"] is False
        assert fields["mutation_permitted"] is True
        assert fields["lineage_classification"] == FINALIZED_ACTIVE

    def test_finalized_object_returns_read_only_classification(self):
        from datetime import datetime, timezone
        obj = _FakeInsight(
            is_finalized=True,
            finalized_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        fields = build_finalized_protection_fields(obj)
        assert fields["is_finalized"] is True
        assert fields["mutation_permitted"] is False
        assert fields["lineage_classification"] == FINALIZED_READ_ONLY

    def test_finalized_at_is_iso_string(self):
        from datetime import datetime, timezone
        obj = _FakeInsight(
            is_finalized=True,
            finalized_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        fields = build_finalized_protection_fields(obj)
        assert fields["finalized_at"] == "2026-03-15T12:00:00+00:00"

    def test_finalized_at_none_when_not_finalized(self):
        obj = _FakeInsight(is_finalized=False, finalized_at=None)
        fields = build_finalized_protection_fields(obj)
        assert fields["finalized_at"] is None

    def test_object_missing_is_finalized_defaults_to_false(self):
        class NoFinalizedAttr:
            pass
        fields = build_finalized_protection_fields(NoFinalizedAttr())
        assert fields["is_finalized"] is False
        assert fields["mutation_permitted"] is True

    def test_four_fields_always_returned(self):
        obj = _FakeInsight(is_finalized=False)
        fields = build_finalized_protection_fields(obj)
        assert set(fields.keys()) == {
            "is_finalized", "finalized_at", "mutation_permitted", "lineage_classification"
        }


# ── TestBuildGovernanceAttributionFields ─────────────────────────────────────

class TestBuildGovernanceAttributionFields:
    def test_all_attribution_fields_extracted(self):
        obj = _FakeHistoryRow(
            correlation_id="cid-1",
            causation_id="cause-1",
            config_version_id="cfg-v2",
            execution_mode="SHADOW",
            execution_type="original",
            governance_scope=SCOPE_SHADOW_ONLY,
            is_replay=False,
            attribution_complete=True,
        )
        fields = build_governance_attribution_fields(obj)
        assert fields["correlation_id"] == "cid-1"
        assert fields["causation_id"] == "cause-1"
        assert fields["config_version_id"] == "cfg-v2"
        assert fields["execution_mode"] == "SHADOW"
        assert fields["execution_type"] == "original"
        assert fields["governance_scope"] == SCOPE_SHADOW_ONLY
        assert fields["is_replay"] is False
        assert fields["attribution_complete"] is True

    def test_missing_fields_return_none_not_raise(self):
        class Sparse:
            correlation_id = "cid"
        fields = build_governance_attribution_fields(Sparse())
        assert fields["causation_id"] is None
        assert fields["config_version_id"] is None
        assert fields["is_replay"] is False

    def test_eight_fields_always_returned(self):
        obj = _FakeHistoryRow()
        fields = build_governance_attribution_fields(obj)
        assert len(fields) == 8

    def test_no_pii_in_attribution_fields(self):
        obj = _FakeHistoryRow()
        fields = build_governance_attribution_fields(obj)
        pii_keys = {"email", "phone", "first_name", "last_name"}
        assert not pii_keys.intersection(fields.keys())


# ── TestReplayVisibilityFields ────────────────────────────────────────────────

class TestReplayVisibilityFields:
    def test_live_record_has_is_replay_false(self):
        obj = _FakeHistoryRow(is_replay=False)
        fields = replay_visibility_fields(obj)
        assert fields["is_replay"] is False

    def test_replay_record_has_is_replay_true(self):
        obj = _FakeHistoryRow(is_replay=True)
        fields = replay_visibility_fields(obj)
        assert fields["is_replay"] is True

    def test_replay_context_propagated_when_present(self):
        ctx = {"original_correlation_id": "abc", "replay_reason": "audit"}
        obj = _FakeHistoryRow(replay_context=ctx)
        fields = replay_visibility_fields(obj)
        assert fields["replay_context"] == ctx

    def test_replay_context_none_when_absent(self):
        obj = _FakeHistoryRow(replay_context=None)
        fields = replay_visibility_fields(obj)
        assert fields["replay_context"] is None

    def test_two_fields_returned(self):
        obj = _FakeHistoryRow()
        fields = replay_visibility_fields(obj)
        assert set(fields.keys()) == {"is_replay", "replay_context"}


# ── TestGovernanceMetaAsDict ──────────────────────────────────────────────────

class TestGovernanceMetaAsDict:
    def test_all_expected_keys_present(self):
        meta = GovernanceMeta(
            correlation_id="cid",
            execution_mode="SHADOW",
            governance_scope=SCOPE_SHADOW_ONLY,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        d = meta.as_dict()
        for key in (
            "correlation_id", "causation_id", "config_version_id",
            "execution_mode", "execution_type", "governance_scope",
            "is_replay", "attribution_complete", "suppression_codes", "timestamp",
        ):
            assert key in d, f"Missing key: {key}"

    def test_suppression_codes_is_list(self):
        meta = GovernanceMeta(
            correlation_id="cid",
            execution_mode="SHADOW",
            governance_scope=SCOPE_SHADOW_ONLY,
            timestamp="2026-01-01T00:00:00",
            suppression_codes=[SUPPRESSION_SHADOW_MODE],
        )
        d = meta.as_dict()
        assert isinstance(d["suppression_codes"], list)
        assert SUPPRESSION_SHADOW_MODE in d["suppression_codes"]

    def test_is_replay_serialized(self):
        meta = GovernanceMeta(
            correlation_id="cid",
            execution_mode="LIVE",
            governance_scope=SCOPE_LIVE_AUTHORIZED,
            timestamp="2026-01-01T00:00:00",
            is_replay=True,
        )
        assert meta.as_dict()["is_replay"] is True


# ── TestReplayExecutionTypesConstant ─────────────────────────────────────────

class TestReplayExecutionTypesConstant:
    def test_replay_in_set(self):
        assert "replay" in REPLAY_EXECUTION_TYPES

    def test_regeneration_in_set(self):
        assert "regeneration" in REPLAY_EXECUTION_TYPES

    def test_original_not_in_set(self):
        assert "original" not in REPLAY_EXECUTION_TYPES

    def test_is_frozenset(self):
        assert isinstance(REPLAY_EXECUTION_TYPES, frozenset)


# ── TestShadowSuppressionCodes ────────────────────────────────────────────────

class TestShadowSuppressionCodes:
    def test_shadow_suppression_code_defined(self):
        assert SUPPRESSION_SHADOW_MODE == "SHADOW_MODE_ACTIVE"

    def test_live_effects_disabled_code_defined(self):
        assert SUPPRESSION_LIVE_EFFECTS_DISABLED == "LIVE_EFFECTS_SUPPRESSED"

    def test_two_suppression_codes_for_shadow(self):
        attr = _shadow_attribution()
        meta = make_governance_meta(attr)
        assert len(meta.suppression_codes) == 2

    def test_zero_suppression_codes_for_live(self):
        attr = _live_attribution()
        meta = make_governance_meta(attr)
        assert len(meta.suppression_codes) == 0


# ── TestFinalizedClassificationConstants ──────────────────────────────────────

class TestFinalizedClassificationConstants:
    def test_finalized_read_only_constant(self):
        assert FINALIZED_READ_ONLY == "FINALIZED_READ_ONLY"

    def test_finalized_active_constant(self):
        assert FINALIZED_ACTIVE == "ACTIVE"

    def test_not_finalized_gives_active(self):
        obj = _FakeInsight(is_finalized=False)
        assert build_finalized_protection_fields(obj)["lineage_classification"] == FINALIZED_ACTIVE

    def test_finalized_gives_read_only(self):
        from datetime import datetime, timezone
        obj = _FakeInsight(is_finalized=True, finalized_at=datetime.now(timezone.utc))
        assert build_finalized_protection_fields(obj)["lineage_classification"] == FINALIZED_READ_ONLY
