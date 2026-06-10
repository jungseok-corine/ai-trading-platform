from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_broker_client
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.schemas import MinuteCandle, PriceQuote

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price/{symbol_code}", response_model=PriceQuote)
async def get_price(
    symbol_code: str,
    broker: BrokerClient = Depends(get_broker_client),
) -> PriceQuote:
    try:
        return await broker.get_current_price(symbol_code)
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e


@router.get("/candles/{symbol_code}", response_model=list[MinuteCandle])
async def get_candles(
    symbol_code: str,
    target_time: str | None = Query(
        None, description="조회 기준 시각 HHMMSS (생략 시 현재 시각)"
    ),
    include_past_data: bool = Query(True, description="과거 분봉 데이터 포함 여부"),
    broker: BrokerClient = Depends(get_broker_client),
) -> list[MinuteCandle]:
    try:
        return await broker.get_minute_candles(
            symbol_code, target_time=target_time, include_past_data=include_past_data
        )
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e
