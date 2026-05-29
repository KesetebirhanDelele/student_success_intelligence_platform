"""
Governance-safe AI intelligence transport wrapper.

Routes all AI evaluation through the governance-safe AI orchestration layer
(assess_ai_orchestration from app.services.ai_insights). Never calls live AI
providers during SHADOW mode or replay/regeneration execution.

SHADOW mode        : governance assessment returned; no live AI provider call.
REPLAY/REGENERATION: FINALIZED_COPY served from warehouse; no live AI call (AP-AI5).
LIVE mode          : governance assessment produced; actual inference is a downstream
                     service responsibility — this layer returns the AIAssessment only.

Architecture preservation:
  AP-AI1  — never act as workflow authority or orchestration executor
  AP-AI5  — never call live AI provider during replay or regeneration
  AP-AI8  — never silently substitute a different AI provider on unavailability
  AP-AI10 — never log raw student PII (name, contact, transcript text)
  AP-AI15 — never modify attribution fields from input context
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.services._ai_types import (
    AIAssessment,
    AIOrchestrationContext,
    SCOPE_UNAVAILABLE,
    TIER_UNAVAILABLE,
    UNKNOWN_V0,
)
from app.services.ai_insights import assess_ai_orchestration

logger = logging.getLogger(__name__)


def assess_ai_intelligence(ctx: AIOrchestrationContext) -> AIAssessment:
    """
    Evaluate AI orchestration governance for a student intelligence context.

    Routes to assess_ai_orchestration() — the governance-safe advisory layer.
    Returns AIAssessment. Never calls live AI providers directly.
    All replay/SHADOW paths are handled by the governance layer (AP-AI5).

    Consuming services read assessment.ai_governance_tier and
    assessment.advisory_scope to determine what AI content is available
    and how it may influence orchestration decisions (AP-AI1).
    """
    return assess_ai_orchestration(ctx)


async def analyze_transcript(
    transcript: str,
    user_id: int,
    attempt: int,
    checkpoint: str = "",
    *,
    execution_mode: str = "SHADOW",
    execution_type: str = "original",
    correlation_id: Optional[str] = None,
    config_version_id: Optional[str] = None,
    origin_source: Optional[str] = "ghl_webhook",
    origin_authority: Optional[str] = "platform_supplementary",
    actor_identity: Optional[str] = "webhook_handler",
) -> dict:
    """
    Governance-safe transcript analysis entry point.

    Accepts transcript text and student context; builds a minimal
    AIOrchestrationContext and routes to assess_ai_intelligence().

    In SHADOW mode the assessment is produced without live AI inference;
    the transcript is not forwarded to any AI provider.
    In LIVE mode, the assessment governs whether inference may proceed —
    actual inference is a downstream service responsibility.

    Returns a governance-safe result dict compatible with callers expecting
    the legacy {"status": ..., "sentiment": ..., ...} shape, augmented with
    governance metadata. PII from transcript never logged (AP-AI10).
    """
    import uuid as _uuid

    cid = correlation_id or str(_uuid.uuid4())
    vid = config_version_id or UNKNOWN_V0

    ctx = AIOrchestrationContext(
        config_version_id=vid,
        execution_mode=execution_mode,
        execution_type=execution_type,
        correlation_id=cid,
        origin_source=origin_source,
        origin_authority=origin_authority,
        actor_identity=actor_identity,
        # No stored insight — governance will return UNAVAILABLE tier
        ai_insight_id=None,
        ai_insight_state=None,
        student_id_opaque=str(user_id) if user_id else None,
    )

    assessment = assess_ai_intelligence(ctx)

    _emit_transcript_log(assessment, user_id, attempt, checkpoint)

    # Return a shape compatible with legacy callers while exposing governance metadata
    return {
        "status": "governance_assessed",
        "ai_governance_tier": assessment.ai_governance_tier,
        "advisory_scope": assessment.advisory_scope,
        "sentiment": assessment.advisory_sentiment,
        "recommended_action": assessment.advisory_recommended_intervention,
        "confidence": assessment.confidence_score,
        "execution_mode": assessment.execution_mode,
        "governance_scope": assessment.advisory_scope,
        "correlation_id": assessment.correlation_id,
        "config_version_id": assessment.config_version_id,
        "degraded": assessment.degraded,
        "degradation_cause": assessment.degradation_cause,
        "reason_codes": assessment.reason_codes,
        "ai_blocked": assessment.ai_blocked,
    }


def _emit_transcript_log(
    assessment: AIAssessment,
    user_id: int,
    attempt: int,
    checkpoint: str,
) -> None:
    """
    Structured log for transcript evaluation path.
    Transcript text never logged — only governance metadata (AP-AI10).
    """
    is_warn = assessment.degraded or assessment.ai_blocked
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "level": "warning" if is_warn else "info",
        "service": "llm_transport",
        "event": "transcript_analysis_assessed",
        "ai_governance_tier": assessment.ai_governance_tier,
        "advisory_scope": assessment.advisory_scope,
        "execution_mode": assessment.execution_mode,
        "execution_type": assessment.execution_type,
        "is_replay": assessment.is_replay,
        "live_inference_suppressed": assessment.live_inference_suppressed,
        "correlation_id": assessment.correlation_id,
        "config_version_id": assessment.config_version_id,
        "student_id_opaque": str(user_id) if user_id else None,
        "attempt": attempt,
        "checkpoint": checkpoint,
        "degraded": assessment.degraded,
        "degradation_cause": assessment.degradation_cause,
        "ai_blocked": assessment.ai_blocked,
        "reason_codes": assessment.reason_codes,
        "outcome": assessment.outcome,
    }
    log_fn = logger.warning if is_warn else logger.info
    log_fn(json.dumps(entry))


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
