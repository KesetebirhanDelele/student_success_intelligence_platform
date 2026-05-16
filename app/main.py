import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
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
from app.services.scheduler import start_scheduler, stop_scheduler

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


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting SSIP v2 | mode=%s", settings.EXECUTION_MODE)
    await init_db()
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    stop_scheduler()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "data": None,
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
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

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
