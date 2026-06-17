from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.market_data_service import MarketDataService
from app.trading.strategy.schemas import (
    MarketDataGlobalSummary,
    MarketDataRead,
    MarketDataSymbolSummary,
)

router = APIRouter(prefix="/market-data", tags=["market-data"])

_MAX_LIMIT = 1000
_DEFAULT_LIMIT = 100


def _get_service(session: AsyncSession = Depends(get_db)) -> MarketDataService:
    return MarketDataService(session=session)


@router.get("/summary", response_model=MarketDataGlobalSummary)
async def get_global_summary(
    service: MarketDataService = Depends(_get_service),
) -> MarketDataGlobalSummary:
    """저장된 전체 종목의 캔들 데이터 현황을 반환한다."""
    return await service.get_global_summary()


@router.get("/{symbol_code}/summary", response_model=MarketDataSymbolSummary)
async def get_symbol_summary(
    symbol_code: str,
    service: MarketDataService = Depends(_get_service),
) -> MarketDataSymbolSummary:
    """특정 종목의 캔들 데이터 저장 현황을 반환한다. 데이터가 없으면 count=0."""
    return await service.get_symbol_summary(symbol_code)


@router.get("/{symbol_code}", response_model=list[MarketDataRead])
async def list_candles(
    symbol_code: str,
    timeframe: str | None = Query(default=None, description="예: 1m, 5m, 1d"),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    service: MarketDataService = Depends(_get_service),
) -> list[MarketDataRead]:
    """특정 종목의 캔들 데이터를 시간순(오름차순)으로 반환한다.

    데이터가 없으면 빈 배열([])을 반환한다.
    """
    rows = await service.list_candles(symbol_code, timeframe, start_at, end_at, limit, offset)
    return [MarketDataRead.model_validate(r) for r in rows]
