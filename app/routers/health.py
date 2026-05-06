from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.schemas import APIResponse
from app.services.scheduler import get_scheduler_status

router = APIRouter()


@router.get("/health")
async def health_check() -> APIResponse:
    return APIResponse.ok({
        "service": "running",
        "execution_mode": settings.EXECUTION_MODE,
        "mssql_configured": settings.mssql_configured,
        "scheduler_status": get_scheduler_status(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
