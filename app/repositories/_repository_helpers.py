"""
Internal helpers for governance-safe repository persistence layer.
Not part of the public API. Consumed only by repository.py.

All helpers are pure functions — no AsyncSession dependencies.
This makes the governance logic directly testable without a database.

Governance prohibitions enforced here:
  FAD-4   — append-only enforcement; no UPDATE/DELETE semantics on lineage tables
  FAD-1   — FINALIZED artifact mutation blocked before any DB operation
  IML-1   — attribution immutability; fields propagated unchanged
  INV-5   — no governance record without correlation_id and attribution
  CID-1   — correlation_id presence validated before every persistence operation
  RSV-1   — replay records tagged is_replay=True; distinguishable from LIVE
  AP-RT13 — PII never logged
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.repositories._repository_types import (
    CODE_ATTRIBUTION_INCOMPLETE,
    CODE_CORRELATION_ID_MISSING,
    CODE_EXECUTION_MODE_MISSING,
    CODE_EXECUTION_TYPE_MISSING,
    CODE_FINALIZED_MUTATION_BLOCKED,
    CODE_GOVERNANCE_SCOPE_MISSING,
    CODE_IDEMPOTENCY_DUPLICATE,
    CODE_INVALID_EXECUTION_MODE,
    CODE_INVALID_EXECUTION_TYPE,
    CODE_REPLAY_LIVE_OVERWRITE_BLOCKED,
    PERSIST_CLASS_APPEND_ONLY,
    PERSIST_OUTCOME_BLOCKED,
    PERSIST_OUTCOME_DUPLICATE_REJECTED,
    PERSIST_OUTCOME_FINALIZED_PROTECTED,
    REQUIRED_PERSISTENCE_ATTRIBUTION,
    TYPE_ORIGINAL,
    _REPLAY_EXECUTION_TYPES,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    AttributionFields,
    PersistenceRecord,
)

logger = logging.getLogger(__name__)

_PERSISTENCE_SERVICE = "repository_persistence"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_persistence_id() -> str:
    return str(uuid.uuid4())


def emit_persistence_log(record: PersistenceRecord) -> None:
    """
    Emit structured persistence observability log on every path.
    PII never logged — no email, phone, student name (AP-RT13).
    Never suppressed on any path (FAD-4, INV-5).
    """
    is_warn = record.blocked or record.outcome in (
        PERSIST_OUTCOME_BLOCKED,
        PERSIST_OUTCOME_FINALIZED_PROTECTED,
        PERSIST_OUTCOME_DUPLICATE_REJECTED,
    )
    entry: Dict[str, Any] = {
        "timestamp": record.timestamp,
        "level": "warning" if is_warn else "info",
        "service": _PERSISTENCE_SERVICE,
        "event": record.event,
        "persistence_id": record.persistence_id,
        "table_name": record.table_name,
        "persistence_class": record.persistence_class,
        "correlation_id": record.correlation_id,
        "causation_id": record.causation_id,
        "execution_mode": record.execution_mode,
        "execution_type": record.execution_type,
        "governance_scope": record.governance_scope,
        "is_replay": record.is_replay,
        "attribution_complete": record.attribution_complete,
        "outcome": record.outcome,
        "blocked": record.blocked,
        "blocking_codes": record.blocking_codes,
        "blocking_reason": record.blocking_reason,
        "record_id": record.record_id,
        "idempotency_key": record.idempotency_key,
        "duration_ms": record.duration_ms,
        "rule_path_taken": record.rule_path_taken,
        # PII fields intentionally excluded: user_id, email, phone, name
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _check_attribution_fields(attribution: AttributionFields) -> List[str]:
    """
    Validate minimum governance attribution for persistence.
    All four REQUIRED_PERSISTENCE_ATTRIBUTION fields must be non-empty (INV-5, CID-1).
    """
    codes: List[str] = []
    if not attribution.correlation_id:
        codes.append(CODE_CORRELATION_ID_MISSING)
    if not attribution.execution_mode:
        codes.append(CODE_EXECUTION_MODE_MISSING)
    elif attribution.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append(CODE_INVALID_EXECUTION_MODE)
    if not attribution.execution_type:
        codes.append(CODE_EXECUTION_TYPE_MISSING)
    elif attribution.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append(CODE_INVALID_EXECUTION_TYPE)
    if not attribution.governance_scope:
        codes.append(CODE_GOVERNANCE_SCOPE_MISSING)
    return codes


def _check_attribution_complete(attribution: AttributionFields) -> bool:
    """
    Returns True when all REQUIRED_PERSISTENCE_ATTRIBUTION fields are non-empty.
    Used to set attribution_complete flag on persisted rows (INV-5).
    """
    return all(getattr(attribution, f, None) for f in REQUIRED_PERSISTENCE_ATTRIBUTION)


def _check_finalized_protection(
    is_finalized: bool,
    table_name: str,
    record_id: Optional[int],
) -> List[str]:
    """
    FINALIZED mutation guard. Returns CODE_FINALIZED_MUTATION_BLOCKED when
    is_finalized=True, preventing any overwrite (FAD-1, INV-1, INV-6).
    """
    if is_finalized:
        return [CODE_FINALIZED_MUTATION_BLOCKED]
    return []


def _check_replay_live_overwrite(
    is_replay: bool,
    target_is_live: bool,
) -> List[str]:
    """
    Replay governance — replay execution MUST NOT overwrite LIVE persistence records.
    Returns CODE_REPLAY_LIVE_OVERWRITE_BLOCKED when replay attempts to overwrite
    a LIVE record (RSV-1, INV-4, AP-RT2).
    """
    if is_replay and target_is_live:
        return [CODE_REPLAY_LIVE_OVERWRITE_BLOCKED]
    return []


def _check_idempotency(
    idempotency_key: Optional[str],
    idempotency_store: set,
    execution_type: str,
) -> List[str]:
    """
    Idempotency deduplication gate. Rejects duplicate LIVE persistence.
    Replay/regeneration types are exempt — replay-safe duplication is permitted
    (replay records are distinguishable via is_replay=True, RSV-1, spec/04 §4.1).
    """
    if not idempotency_key:
        return []
    if execution_type in _REPLAY_EXECUTION_TYPES:
        return []  # replay duplication permitted
    if idempotency_key in idempotency_store:
        return [CODE_IDEMPOTENCY_DUPLICATE]
    return []


def _governance_persistence_gate(
    attribution: AttributionFields,
    idempotency_key: Optional[str],
    idempotency_store: set,
    table_name: str,
    is_finalized: bool = False,
    target_is_live: bool = False,
) -> List[str]:
    """
    RULE 0: Governance precondition gate for all persistence operations.
    Returns blocking codes. Empty list = gate passes.

    Checks (in order):
      1. Attribution field presence and validity (INV-5, CID-1)
      2. FINALIZED mutation protection (FAD-1, INV-1)
      3. Replay-over-LIVE overwrite protection (RSV-1, INV-4)
      4. Idempotency deduplication for LIVE execution (spec/04 §4.1)
    """
    codes: List[str] = []
    codes.extend(_check_attribution_fields(attribution))
    codes.extend(_check_finalized_protection(is_finalized, table_name, None))
    codes.extend(_check_replay_live_overwrite(attribution.is_replay, target_is_live))
    codes.extend(_check_idempotency(idempotency_key, idempotency_store, attribution.execution_type))
    return codes


def _make_persistence_record(
    attribution: AttributionFields,
    event: str,
    table_name: str,
    persistence_class: str,
    blocked: bool,
    blocking_codes: List[str],
    blocking_reason: Optional[str],
    outcome: str,
    record_id: Optional[int],
    idempotency_key: Optional[str],
    duration_ms: Optional[int],
    rule_path: Optional[List[str]] = None,
) -> PersistenceRecord:
    return PersistenceRecord(
        persistence_id=_make_persistence_id(),
        timestamp=_now_iso(),
        event=event,
        table_name=table_name,
        persistence_class=persistence_class,
        correlation_id=attribution.correlation_id,
        causation_id=attribution.causation_id,
        execution_mode=attribution.execution_mode,
        execution_type=attribution.execution_type,
        governance_scope=attribution.governance_scope,
        is_replay=attribution.is_replay,
        attribution_complete=_check_attribution_complete(attribution),
        outcome=outcome,
        blocked=blocked,
        blocking_codes=list(blocking_codes),
        blocking_reason=blocking_reason,
        record_id=record_id,
        idempotency_key=idempotency_key,
        duration_ms=duration_ms,
        rule_path_taken=list(rule_path) if rule_path else [],
    )
