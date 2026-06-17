import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.market_data import MarketDataRepository
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.indicators import calculate_sma

KST = ZoneInfo("Asia/Seoul")
log = logging.getLogger(__name__)


def _candle_ts(business_date: str, trade_time: str) -> datetime:
    """업무일자(YYYYMMDD) + 체결시각(HHMMSS)을 KST datetime으로 변환한다."""
    dt_str = f"{business_date}{trade_time}"
    return datetime.strptime(dt_str, "%Y%m%d%H%M%S").replace(tzinfo=KST)


class MarketDataService:
    """전략(Strategy)이 사용할 시세 데이터를 제공하고, DB에 저장한다.

    session을 주입하면 get_recent_candles 호출 시 market_data 테이블에 upsert한다.
    session이 없으면 브로커 조회만 수행한다(저장 건너뜀).
    """

    def __init__(self, broker: BrokerClient, session: AsyncSession | None = None) -> None:
        self._broker = broker
        self._session = session

    async def get_recent_candles(
        self,
        symbol_code: str,
        count: int = 30,
        timeframe: str = "1m",
    ) -> list[MinuteCandle]:
        """최근 분봉을 오래된 순으로 정렬해 최대 count개 반환한다.

        session이 주입되어 있으면 반환 전에 market_data에 upsert를 시도한다.
        저장 실패는 경고 로그로만 기록하고 전략 실행을 중단하지 않는다.
        """
        candles = await self._broker.get_minute_candles(symbol_code)
        candles = sorted(candles, key=lambda c: (c.business_date, c.trade_time))
        candles = candles[-count:]

        if self._session is not None:
            try:
                await self.save_candles(symbol_code, timeframe, candles)
            except Exception:
                log.warning(
                    "market_data 저장 실패 (symbol=%s, timeframe=%s) — 전략 실행은 계속 진행",
                    symbol_code,
                    timeframe,
                    exc_info=True,
                )

        return candles

    async def save_candles(
        self,
        symbol_code: str,
        timeframe: str,
        candles: list[MinuteCandle],
    ) -> int:
        """분봉 데이터를 market_data 테이블에 upsert한다.

        동일 (symbol_code, timeframe, ts) 가 이미 존재하면 OHLCV를 업데이트한다.
        flush만 수행하므로 실제 commit은 호출자(generate_and_log_signal 등)의 책임이다.
        """
        if self._session is None:
            raise RuntimeError("save_candles requires session")

        rows = [
            {
                "symbol_code": symbol_code,
                "timeframe": timeframe,
                "ts": _candle_ts(c.business_date, c.trade_time),
                "open": c.open_price,
                "high": c.high_price,
                "low": c.low_price,
                "close": c.close_price,
                "volume": c.volume,
            }
            for c in candles
        ]
        repo = MarketDataRepository(self._session)
        return await repo.upsert_bulk(rows)

    @staticmethod
    def calculate_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
        return calculate_sma(candles, period)
