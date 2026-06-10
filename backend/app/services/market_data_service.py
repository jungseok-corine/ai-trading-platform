from decimal import Decimal

from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.indicators import calculate_sma


class MarketDataService:
    """전략(Strategy)이 사용할 시세 데이터를 제공한다.

    현재는 KIS 분봉 데이터를 직접 조회한다. 추후 market_data 테이블 기반 조회로
    교체하더라도 Strategy/SignalService는 이 서비스 인터페이스만 의존한다.
    """

    def __init__(self, broker: BrokerClient) -> None:
        self._broker = broker

    async def get_recent_candles(self, symbol_code: str, count: int = 30) -> list[MinuteCandle]:
        """최근 분봉을 오래된 순으로 정렬해 최대 count개 반환한다."""
        candles = await self._broker.get_minute_candles(symbol_code)
        candles = sorted(candles, key=lambda c: (c.business_date, c.trade_time))
        return candles[-count:]

    @staticmethod
    def calculate_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
        return calculate_sma(candles, period)
