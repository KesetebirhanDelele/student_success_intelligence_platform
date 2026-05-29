"""
Internal helpers for governance-safe API/router layer.
Not part of the public API. Consumed only by routers.

All helpers are pure functions — no AsyncSession or HTTP stack dependencies.
Directly testable without a database or web framework.

Governance responsibilities:
  CID-1  — extract or generate correlation_id on every request
  IML-1  — build AttributionFields propagated immutably to repository layer
  INV-5  — no request proceeds without correlation_id
  AP-RT13 — PII never in meta fields; explicitly excluded
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.repositories._repository_types import AttributionFields
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

_DEFAULT_EXECUTION_TYPE = "original"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


def extract_correlation_id(request_headers: Dict[str, str]) -> str:
    """
    Extract correlation_id from X-Correlation-ID header (CID-1).
    If absent, empty, or whitespace-only, generates a new UUID v4.
    Never returns an empty string — guaranteed non-empty.
    """
    val = request_headers.get(GOVERNANCE_CORRELATION_HEADER, "")
    if val and val.strip():
        return val.strip()
    return _new_uuid()


def extract_causation_id(request_headers: Dict[str, str]) -> Optional[str]:
    """
    Extract optional X-Causation-ID header.
    Returns None if absent or empty.
    """
    val = request_headers.get(GOVERNANCE_CAUSATION_HEADER, "")
    return val.strip() if (val and val.strip()) else None


def extract_execution_type(request_headers: Dict[str, str]) -> str:
    """
    Extract X-Execution-Type header.
    Defaults to 'original'. Valid: 'original', 'replay', 'regeneration'.
    """
    val = request_headers.get(GOVERNANCE_EXECUTION_TYPE_HEADER, "")
    if val and val.strip():
        return val.strip()
    return _DEFAULT_EXECUTION_TYPE


def governance_scope_for_mode(execution_mode: str) -> str:
    """
    Derive governance_scope from execution_mode.
    SHADOW → SHADOW_ONLY; any other value → LIVE_AUTHORIZED.
    """
    if str(execution_mode) == "SHADOW":
        return SCOPE_SHADOW_ONLY
    return SCOPE_LIVE_AUTHORIZED


def build_request_attribution(
    correlation_id: str,
    *,
    causation_id: Optional[str] = None,
    execution_type: str = _DEFAULT_EXECUTION_TYPE,
    config_version_id: Optional[str] = None,
    execution_mode: Optional[str] = None,
) -> AttributionFields:
    """
    Build an AttributionFields from router-layer context (CID-1, IML-1).

    execution_mode defaults to settings.EXECUTION_MODE.
    governance_scope is derived from execution_mode.
    is_replay is derived from execution_type membership in REPLAY_EXECUTION_TYPES.
    """
    mode = str(execution_mode) if execution_mode is not None else str(settings.EXECUTION_MODE)
    scope = governance_scope_for_mode(mode)
    return AttributionFields(
        correlation_id=correlation_id,
        causation_id=causation_id,
        execution_mode=mode,
        execution_type=execution_type,
        governance_scope=scope,
        config_version_id=config_version_id,
        is_replay=(execution_type in REPLAY_EXECUTION_TYPES),
    )


def make_governance_meta(
    attribution: AttributionFields,
    *,
    timestamp: Optional[str] = None,
) -> GovernanceMeta:
    """
    Build a GovernanceMeta from AttributionFields (IML-1, CID-1).

    Derives suppression_codes from execution_mode to expose SHADOW visibility.
    attribution_complete is computed from REQUIRED_ROUTER_ATTRIBUTION fields.
    Never includes PII (AP-RT13).
    """
    suppression: List[str] = []
    if str(attribution.execution_mode) == "SHADOW":
        suppression.append(SUPPRESSION_SHADOW_MODE)
        suppression.append(SUPPRESSION_LIVE_EFFECTS_DISABLED)

    attribution_complete = all(
        getattr(attribution, f, None) for f in REQUIRED_ROUTER_ATTRIBUTION
    )

    return GovernanceMeta(
        correlation_id=attribution.correlation_id,
        causation_id=attribution.causation_id,
        config_version_id=attribution.config_version_id,
        execution_mode=str(attribution.execution_mode),
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
        is_replay=attribution.is_replay,
        attribution_complete=attribution_complete,
        suppression_codes=suppression,
        timestamp=timestamp or _now_iso(),
    )


def check_attribution_complete(attribution: AttributionFields) -> bool:
    """Returns True when all REQUIRED_ROUTER_ATTRIBUTION fields are non-empty."""
    return all(getattr(attribution, f, None) for f in REQUIRED_ROUTER_ATTRIBUTION)


def build_finalized_protection_fields(obj: Any) -> Dict[str, Any]:
    """
    Build FINALIZED immutability metadata for response items (FAD-1).

    Exposes read-only classification, mutation permit status, and finalized_at
    timestamp so consumers can detect and respect FINALIZED protection.
    """
    is_fin = bool(getattr(obj, "is_finalized", False))
    finalized_at_val = getattr(obj, "finalized_at", None)
    return {
        "is_finalized": is_fin,
        "finalized_at": finalized_at_val.isoformat() if finalized_at_val else None,
        "mutation_permitted": not is_fin,
        "lineage_classification": FINALIZED_READ_ONLY if is_fin else FINALIZED_ACTIVE,
    }


def build_governance_attribution_fields(obj: Any) -> Dict[str, Any]:
    """
    Extract governance attribution lineage fields from an ORM object.

    Used to surface attribution context in responses for history/transition items.
    Never includes PII fields (AP-RT13): no email, phone, student name.
    Returns None for absent fields rather than raising AttributeError.
    """
    return {
        "correlation_id": getattr(obj, "correlation_id", None),
        "causation_id": getattr(obj, "causation_id", None),
        "config_version_id": getattr(obj, "config_version_id", None),
        "execution_mode": getattr(obj, "execution_mode", None),
        "execution_type": getattr(obj, "execution_type", None),
        "governance_scope": getattr(obj, "governance_scope", None),
        "is_replay": getattr(obj, "is_replay", False),
        "attribution_complete": getattr(obj, "attribution_complete", False),
    }


def replay_visibility_fields(obj: Any) -> Dict[str, Any]:
    """
    Build replay lineage visibility fields for response items (RSV-1).

    Exposes is_replay and replay_context so consumers can distinguish
    LIVE records from REPLAY records without database queries.
    """
    return {
        "is_replay": getattr(obj, "is_replay", False),
        "replay_context": getattr(obj, "replay_context", None),
    }
