"""운영 종합 관제 API (C-3.5).

안전·연구·퍼널·비용의 핵심 헤드라인을 한 번에 반환한다(랜딩 화면용).
기존 read-only 서비스들을 조합만 하며 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.operations_overview_service import OperationsOverviewService

router = APIRouter(prefix="/operations-overview", tags=["operations-overview"])


def get_service(session: AsyncSession = Depends(get_db)) -> OperationsOverviewService:
    return OperationsOverviewService(session)


@router.get("")
async def get_overview(
    days: int = Query(30, ge=1, le=365),
    service: OperationsOverviewService = Depends(get_service),
) -> dict:
    return await service.overview(days=days)
