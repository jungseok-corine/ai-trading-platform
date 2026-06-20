"""연구 루프 전반부 퍼널 API (C-3.21).

후보 포착→전략 배정→실험의 흐름과 전환율을 집계해 반환한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.research_funnel_service import ResearchFunnelService

router = APIRouter(prefix="/research-funnel", tags=["research-funnel"])


def get_service(session: AsyncSession = Depends(get_db)) -> ResearchFunnelService:
    return ResearchFunnelService(session)


@router.get("")
async def get_funnel(
    days: int = Query(30, ge=1, le=365),
    service: ResearchFunnelService = Depends(get_service),
) -> dict:
    return await service.funnel(days=days)
