"""
Student Success Intelligence Platform — application entry point.

Governance alignment:
  SHADOW-safe startup — RuntimeBootstrapContext enforces SHADOW_ONLY scope
  Config V2 validation — UNKNOWN_V0 emitted when no active config exists
  Scheduler governance wiring — configure_scheduler() called with explicit context
  Attribution continuity — startup_correlation_id propagated to scheduler
  Structured observability — startup/shutdown events logged in JSON
  AP-RT13 — no PII in startup logs
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap.runtime_context import initialize_runtime_context
from app.config import settings
from app.database import init_db, load_active_config_versions, verify_startup_db_state
from app.middleware.correlation import AttributionMiddleware
from app.routers import actions, health, metrics, outreach, students, webhook
from app.routers import ai_insights as ai_insights_router
from app.routers import batch as batch_router
from app.routers import dashboard as dashboard_router
from app.routers import ghl_sync as ghl_sync_router
from app.routers import lifecycle as lifecycle_router
from app.routers import quick_actions as quick_actions_router
from app.routers import notes as notes_router
from app.routers import payment as payment_router
from app.routers import segments as segments_router
from app.routers import source as source_router
from app.routers import student_timeline as timeline_router
from app.routers import sync as sync_router
from app.routers import work_queue as work_queue_router
from app.routers import reports as reports_router
from app.routers import admin as admin_router
from app.services.scheduler import (
    configure_scheduler,
    start_daily_sync_job,
    start_month_end_capture_job,
    start_monthly_report_job,
    start_scheduler,
    stop_scheduler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Student Success Intelligence Platform",
    description="Production-grade automated student outreach decision engine",
    version="2.0.0",
)

app.add_middleware(AttributionMiddleware)


@app.on_event("startup")
async def on_startup() -> None:
    """
    Governance-safe startup sequence.

    Order:
    1. init_db() — tables, column migrations, governance indexes
    2. verify_startup_db_state() — read-only PostgreSQL readiness check (RISK-003)
    3. load_active_config_versions() — resolves ACTIVE Config V2 row (RISK-001 fix)
    4. initialize_runtime_context() — validates execution_mode + Config V2,
       derives governance_scope, builds scheduler timing, emits startup log
    5. configure_scheduler() — wires governance context into scheduler so
       every APScheduler cycle carries explicit attribution (not silent fallback)
    6. start_scheduler() — starts APScheduler with Config-V2-sourced timing

    SHADOW-safe: governance_scope is always SHADOW_ONLY or REPLAY_ONLY at startup
    (AUTHORIZED scope unreachable — Phase-12 cert gate enforced in bootstrap).
    Config V2 absence → UNKNOWN_V0 + degradation_state=True, system still starts.
    """
    await init_db()

    # Startup DB verification — read-only PostgreSQL readiness (RISK-003).
    db_state = await verify_startup_db_state()
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "info" if db_state.get("active_config_count") == 1 else "warning",
        "service": "main",
        "event": "startup_db_verification",
        **db_state,
    }))

    # Load ACTIVE config from DB — replaces static active_configs=[] (RISK-001 fix).
    # Returns [] on any DB error → UNKNOWN_V0 degradation path preserved.
    active_configs = await load_active_config_versions()

    # Runtime bootstrap: validate mode + Config V2, derive scope, emit startup log.
    bootstrap_ctx = initialize_runtime_context(
        execution_mode=settings.EXECUTION_MODE.value,
        active_configs=active_configs,    # DB-resolved; [] → UNKNOWN_V0 degradation
        attribution=None,                 # startup has no inbound attribution headers
        config_rule_set=None,             # Config V2 rule set not yet wired to timing
        scheduler_fallback_hour=settings.SCHEDULER_HOUR,
        scheduler_fallback_minute=settings.SCHEDULER_MINUTE,
        scheduler_fallback_timezone=settings.SCHEDULER_TIMEZONE,
    )

    # Wire bootstrap governance context into scheduler — explicit, not silent fallback.
    configure_scheduler(
        execution_mode=bootstrap_ctx.execution_mode,
        config_version_id=bootstrap_ctx.config_version_id,
        attribution_context={
            "origin_source": "bootstrap",
            "origin_authority": "runtime_context",
            "attribution_timestamp": bootstrap_ctx.startup_timestamp,
            "startup_correlation_id": bootstrap_ctx.startup_correlation_id,
            "actor_identity": "startup_lifecycle",
        },
    )

    timing = bootstrap_ctx.scheduler_timing
    start_scheduler(
        trigger_hour=timing.get("trigger_hour", settings.SCHEDULER_HOUR),
        trigger_minute=timing.get("trigger_minute", settings.SCHEDULER_MINUTE),
        timezone_str=timing.get("timezone_str", settings.SCHEDULER_TIMEZONE),
    )
    start_monthly_report_job(timezone_str="UTC")
    start_daily_sync_job(timezone_str="UTC")
    start_month_end_capture_job(timezone_str="UTC")

    logger.info(json.dumps({
        "timestamp": bootstrap_ctx.startup_timestamp,
        "level": "info",
        "service": "main",
        "event": "application_started",
        "execution_mode": bootstrap_ctx.execution_mode,
        "governance_scope": bootstrap_ctx.governance_scope,
        "startup_classification": bootstrap_ctx.startup_classification,
        "config_version_id": bootstrap_ctx.config_version_id,
        "shadow_containment_active": bootstrap_ctx.shadow_containment_active,
        "degradation_state": bootstrap_ctx.degradation_state,
        "degradation_codes": bootstrap_ctx.degradation_codes,
        "startup_correlation_id": bootstrap_ctx.startup_correlation_id,
    }))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    stop_scheduler()
    logger.info(json.dumps({
        "level": "info",
        "service": "main",
        "event": "application_stopped",
    }))


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        json.dumps({
            "level": "error",
            "service": "main",
            "event": "unhandled_exception",
            "path": str(request.url.path),
            "method": request.method,
            "error_class": type(exc).__name__,
        }),
        exc_info=True,
    )
    # Propagate attribution context from middleware when available (no PII)
    attribution_ctx = getattr(request.state, "attribution", None)
    meta = None
    if attribution_ctx:
        meta = {
            "correlation_id": getattr(attribution_ctx, "correlation_id", None),
            "execution_mode": getattr(attribution_ctx, "execution_mode", None),
            "governance_scope": getattr(attribution_ctx, "governance_scope", None),
        }
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "data": None,
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
            "meta": meta,
        },
    )


# ── Core system routers ────────────────────────────────────────────────────────
app.include_router(health.router, tags=["System"])
app.include_router(outreach.router, tags=["Outreach"])
app.include_router(students.router, tags=["Students"])
app.include_router(metrics.router, tags=["Metrics"])
app.include_router(actions.router, tags=["Actions"])
app.include_router(webhook.router, tags=["Webhooks"])
app.include_router(dashboard_router.router, tags=["Dashboard"])
app.include_router(sync_router.router, tags=["Sync"])
app.include_router(source_router.router, tags=["Source"])
app.include_router(work_queue_router.router, tags=["WorkQueue"])
app.include_router(batch_router.router, tags=["Batch"])

# ── Phase 4 operational intelligence routers ──────────────────────────────────
app.include_router(segments_router.router, tags=["Segments"])
app.include_router(payment_router.router, tags=["Payment"])
app.include_router(timeline_router.router, tags=["Timeline"])
app.include_router(ai_insights_router.router, tags=["AIInsights"])
app.include_router(notes_router.router, tags=["Notes"])
app.include_router(ghl_sync_router.router, tags=["GHLSync"])
app.include_router(lifecycle_router.router, tags=["Lifecycle"])
app.include_router(quick_actions_router.router, tags=["QuickActions"])
app.include_router(reports_router.router, tags=["Reports"])
app.include_router(admin_router.router, tags=["Admin"])

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
