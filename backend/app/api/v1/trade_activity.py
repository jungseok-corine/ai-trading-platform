"""거래 활동 요약 API (C-3.11).

최근 거래의 건수·승패·손익을 전체/전략별로 집계해 반환한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.trade_activity_service import TradeActivityService

router = APIRouter(prefix="/trade-activity", tags=["trade-activity"])


def get_service(session: AsyncSession = Depends(get_db)) -> TradeActivityService:
    return TradeActivityService(session)


@router.get("")
async def get_summary(
    days: int = Query(30, ge=1, le=365),
    service: TradeActivityService = Depends(get_service),
) -> dict:
    return await service.summary(days=days)


@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(30, ge=1, le=365),
    service: TradeActivityService = Depends(get_service),
) -> list[dict]:
    return await service.equity_curve(days=days)
