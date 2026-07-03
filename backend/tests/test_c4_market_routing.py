"""C-5.2: 멀티마켓 시세 라우팅 + 전략 파라미터 market/exchange 검증."""
from decimal import Decimal
from unittest.mock import AsyncMock

import pydantic
import pytest

from app.services.market_data_service import MarketDataService, _timeframe_to_nmin
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.schemas import StrategyVersionParameters


def _candle() -> MinuteCandle:
    return MinuteCandle(
        business_date="20260622", trade_time="233000",
        open_price=Decimal("250"), high_price=Decimal("251"),
        low_price=Decimal("249"), close_price=Decimal("250.5"), volume=1000,
    )


async def test_us_market_routes_to_overseas_client() -> None:
    broker = AsyncMock()
    overseas = AsyncMock()
    overseas.get_overseas_minute_candles = AsyncMock(return_value=[_candle()])
    svc = MarketDataService(broker, session=None, overseas_client=overseas)

    out = await svc.get_recent_candles("AAPL", market="US", exchange="NAS", timeframe="5m")

    assert len(out) == 1
    overseas.get_overseas_minute_candles.assert_awaited_once()
    kwargs = overseas.get_overseas_minute_candles.call_args.kwargs
    assert kwargs["exchange"] == "NAS"
    assert kwargs["nmin"] == 5  # timeframe '5m' → NMIN 5
    broker.get_minute_candles.assert_not_called()


async def test_kr_market_uses_domestic_broker() -> None:
    broker = AsyncMock()
    broker.get_minute_candles = AsyncMock(return_value=[_candle()])
    overseas = AsyncMock()
    svc = MarketDataService(broker, session=None, overseas_client=overseas)

    await svc.get_recent_candles("005930", market="KR")

    broker.get_minute_candles.assert_awaited_once()
    overseas.get_overseas_minute_candles.assert_not_called()


async def test_us_without_overseas_client_raises() -> None:
    svc = MarketDataService(AsyncMock(), session=None, overseas_client=None)
    with pytest.raises(RuntimeError):
        await svc.get_recent_candles("AAPL", market="US")


def test_timeframe_to_nmin() -> None:
    assert _timeframe_to_nmin("5m") == 5
    assert _timeframe_to_nmin("1m") == 1
    assert _timeframe_to_nmin("15m") == 15
    assert _timeframe_to_nmin("1d") == 1440  # C-6.20: 일봉 = 1440분 (신선도 가드용)
    assert _timeframe_to_nmin("2h") == 1  # 미지원 형식은 1로 폴백


def test_params_market_exchange_validation() -> None:
    StrategyVersionParameters(symbol_code="AAPL", market="US", exchange="NAS")  # ok
    StrategyVersionParameters(symbol_code="005930", market="KR")  # ok (기본)
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(symbol_code="AAPL", market="US", exchange="XXX")
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(symbol_code="AAPL", market="JP")
