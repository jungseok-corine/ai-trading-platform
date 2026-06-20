"""데이터 신선도 점검 API (C-3.10).

핵심 데이터 소스의 최신 타임스탬프·경과 시간·stale 여부를 반환한다.
read-only 점검으로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.data_freshness_service import DataFreshnessService

router = APIRouter(prefix="/data-freshness", tags=["data-freshness"])


def get_service(session: AsyncSession = Depends(get_db)) -> DataFreshnessService:
    return DataFreshnessService(session)


@router.get("")
async def get_freshness(
    service: DataFreshnessService = Depends(get_service),
) -> dict:
    return await service.status()
