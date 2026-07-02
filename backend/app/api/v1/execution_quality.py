"""체결 품질 API (C-6.9). read-only 슬리피지·지연 집계."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.execution_quality_service import ExecutionQualityService

router = APIRouter(prefix="/execution-quality", tags=["execution-quality"])


@router.get("")
async def get_execution_quality(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await ExecutionQualityService(session).summary(days=days)
