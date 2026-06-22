import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.market_data import MarketData
from app.domain.repositories.market_data import MarketDataRepository
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.indicators import calculate_sma
from app.trading.strategy.schemas import (
    MarketDataGlobalSummary,
    MarketDataSymbolOverview,
    MarketDataSymbolSummary,
    MarketDataTimeframeSummary,
)

if TYPE_CHECKING:
    from app.trading.broker.kis_overseas_client import KISOverseasClient

log = logging.getLogger(__name__)


def _timeframe_to_nmin(timeframe: str) -> int:
    """'5m'/'1m' 같은 타임프레임 문자열을 해외 분봉 NMIN(분 단위)로 변환한다. 기본 1."""
    m = re.match(r"^(\d+)\s*m$", (timeframe or "").strip().lower())
    return int(m.group(1)) if m else 1


def _candle_ts(business_date: str, trade_time: str) -> datetime:
    """업무일자(YYYYMMDD) + 체결시각(HHMMSS)을 KST datetime으로 변환한다."""
    dt_str = f"{business_date}{trade_time}"
    return datetime.strptime(dt_str, "%Y%m%d%H%M%S").replace(tzinfo=KST)


class MarketDataService:
    """전략(Strategy)이 사용할 시세 데이터를 제공하고, DB에 저장한다.

    session을 주입하면 get_recent_candles 호출 시 market_data 테이블에 upsert한다.
    session이 없으면 브로커 조회만 수행한다(저장 건너뜀).
    """

    def __init__(
        self,
        broker: BrokerClient | None = None,
        session: AsyncSession | None = None,
        overseas_client: "KISOverseasClient | None" = None,
    ) -> None:
        self._broker = broker
        self._session = session
        self._overseas_client = overseas_client

    async def get_recent_candles(
        self,
        symbol_code: str,
        count: int = 30,
        timeframe: str = "1m",
        market: str = "KR",
        exchange: str = "NAS",
    ) -> list[MinuteCandle]:
        """최근 분봉을 오래된 순으로 정렬해 최대 count개 반환한다.

        market="US"이면 KIS 해외 분봉(overseas_client)으로, 그 외(KR)는 국내 broker로 조회한다.
        session이 주입되어 있으면 반환 전에 market_data에 upsert를 시도한다.
        저장 실패는 경고 로그로만 기록하고 전략 실행을 중단하지 않는다.
        """
        if market == "US":
            if self._overseas_client is None:
                raise RuntimeError("US 시장 캔들 조회에 overseas_client가 필요합니다.")
            nmin = _timeframe_to_nmin(timeframe)
            candles = await self._overseas_client.get_overseas_minute_candles(
                symbol_code, exchange=exchange, nmin=nmin
            )
        else:
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

    async def list_candles(
        self,
        symbol_code: str,
        timeframe: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MarketData]:
        if self._session is None:
            raise RuntimeError("list_candles requires session")
        repo = MarketDataRepository(self._session)
        return await repo.list_candles(symbol_code, timeframe, start_at, end_at, limit, offset)

    async def get_symbol_summary(self, symbol_code: str) -> MarketDataSymbolSummary:
        if self._session is None:
            raise RuntimeError("get_symbol_summary requires session")
        repo = MarketDataRepository(self._session)
        rows = await repo.get_symbol_summary_by_timeframe(symbol_code)
        by_timeframe = [
            MarketDataTimeframeSummary(
                timeframe=r["timeframe"],
                count=r["count"],
                oldest_ts=r["oldest_ts"],
                latest_ts=r["latest_ts"],
            )
            for r in rows
        ]
        total_count = sum(r.count for r in by_timeframe)
        oldest_ts = min((r.oldest_ts for r in by_timeframe if r.oldest_ts), default=None)
        latest_ts = max((r.latest_ts for r in by_timeframe if r.latest_ts), default=None)
        return MarketDataSymbolSummary(
            symbol_code=symbol_code,
            total_count=total_count,
            oldest_ts=oldest_ts,
            latest_ts=latest_ts,
            by_timeframe=by_timeframe,
        )

    async def get_global_summary(self) -> MarketDataGlobalSummary:
        if self._session is None:
            raise RuntimeError("get_global_summary requires session")
        repo = MarketDataRepository(self._session)
        rows = await repo.get_global_summary()

        # symbol_code별로 집계
        symbols_map: dict[str, MarketDataSymbolOverview] = {}
        for row in rows:
            code = row["symbol_code"]
            if code not in symbols_map:
                symbols_map[code] = MarketDataSymbolOverview(
                    symbol_code=code,
                    total_count=0,
                    latest_ts=None,
                    timeframes=[],
                )
            overview = symbols_map[code]
            overview.total_count += row["count"]
            overview.timeframes.append(row["timeframe"])
            if row["latest_ts"] is not None:
                if overview.latest_ts is None or row["latest_ts"] > overview.latest_ts:
                    overview.latest_ts = row["latest_ts"]

        symbols = list(symbols_map.values())
        return MarketDataGlobalSummary(
            total_symbols=len(symbols),
            total_rows=sum(s.total_count for s in symbols),
            symbols=symbols,
        )

    @staticmethod
    def calculate_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
        return calculate_sma(candles, period)
