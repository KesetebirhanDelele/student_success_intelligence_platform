from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.schemas import APIResponse
from app.services.scheduler import get_last_run_at, get_scheduler_status

router = APIRouter()


async def _check_db() -> bool:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
async def health_check() -> APIResponse:
    db_ok = await _check_db()
    last_run = get_last_run_at()
    return APIResponse.ok({
        "service": "running",
        "execution_mode": settings.EXECUTION_MODE,
        "db_connected": db_ok,
        "mssql_configured": settings.mssql_configured,
        "scheduler_status": get_scheduler_status(),
        "last_scheduler_run": last_run,
        "channels": {
            "call": not settings.is_shadow and bool(settings.SYNTHFLOW_API_KEY),
            "sms": not settings.is_shadow and bool(settings.GHL_API_KEY),
            "email": not settings.is_shadow and bool(settings.GHL_API_KEY),
        },
        "outbound_enabled": not settings.is_shadow,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
