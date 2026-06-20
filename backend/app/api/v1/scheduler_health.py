"""스케줄러 잡 건강 점검 API (C-3.18).

설정상 활성인 자율 잡이 최근에 돌았는지/마지막이 실패했는지 점검해 반환한다.
read-only 점검으로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.scheduler_health_service import SchedulerHealthService

router = APIRouter(prefix="/scheduler-health", tags=["scheduler-health"])


def get_service(session: AsyncSession = Depends(get_db)) -> SchedulerHealthService:
    return SchedulerHealthService(session)


@router.get("")
async def get_health(
    service: SchedulerHealthService = Depends(get_service),
) -> dict:
    return await service.status()
