"""보유 포지션·노출 집계 API (C-3.6).

현재 보유 포지션을 시가평가·미실현손익·종목별 노출 비중으로 집계해 반환한다.
read-only 집계로 주문/외부 호출이 없다(시세 갱신은 동기화 잡의 몫).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.portfolio_summary_service import PortfolioSummaryService

router = APIRouter(prefix="/portfolio-summary", tags=["portfolio-summary"])


def get_service(session: AsyncSession = Depends(get_db)) -> PortfolioSummaryService:
    return PortfolioSummaryService(session)


@router.get("")
async def get_summary(
    account_id: int | None = Query(None),
    service: PortfolioSummaryService = Depends(get_service),
) -> dict:
    return await service.summary(account_id=account_id)
