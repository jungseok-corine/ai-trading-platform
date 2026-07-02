"""인트라데이 변동성 레짐 API (C-6.3). read-only 분류 조회."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.intraday_regime_service import IntradayRegimeService

router = APIRouter(prefix="/intraday-regime", tags=["intraday-regime"])


@router.get("")
async def get_intraday_regime(
    market: str = Query("KR"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    snap = await IntradayRegimeService(session).snapshot(market=market)
    return snap.to_dict()
