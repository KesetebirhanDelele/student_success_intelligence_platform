from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse
from app.services.sync import sync_from_mssql

router = APIRouter()


@router.post("/sync/mssql")
async def manual_mssql_sync(db: AsyncSession = Depends(get_db)) -> APIResponse:
    result = await sync_from_mssql(db)
    return APIResponse.ok(result)
