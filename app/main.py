import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import health, outreach, students, metrics, actions, webhook
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Student Success Intelligence Platform",
    description="Automated student outreach decision engine",
    version="0.1.0-mvp",
)


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    logger.info("Starting SSIP | scope=%s", settings.SYSTEM_SCOPE)
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()


# ── Global error handler ──────────────────────────────────────────────────────

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


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health.router, tags=["System"])
app.include_router(outreach.router, tags=["Outreach"])
app.include_router(students.router, tags=["Students"])
app.include_router(metrics.router, tags=["Metrics"])
app.include_router(actions.router, tags=["Actions"])
app.include_router(webhook.router, tags=["Webhooks"])

# Serve minimal dashboard
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    return (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
