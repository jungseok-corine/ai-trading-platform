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
    """타임프레임 문자열을 분 단위로 변환한다. '5m'→5, '1d'→1440, 기본 1.

    신선도 가드가 이 값×3을 임계로 쓰므로 일봉을 1분으로 취급하면
    일봉 전략의 신호가 항상 차단된다 (C-6.20 수정).
    """
    tf = (timeframe or "").strip().lower()
    if tf in ("1d", "d", "day"):
        return 1440
    m = re.match(r"^(\d+)\s*m$", tf)
    return int(m.group(1)) if m else 1


def _is_daily(timeframe: str) -> bool:
    return (timeframe or "").strip().lower() in ("1d", "d", "day")


def resample_candles(candles: list[MinuteCandle], minutes: int) -> list[MinuteCandle]:
    """1분봉 리스트(오래된 순)를 N분봉으로 집계한다 (C-6.18).

    버킷 = (거래일, 분-of-day // N). open=첫봉 시가, high/low=최대/최소,
    close=마지막봉 종가, volume=합. 버킷 시각은 버킷 시작 시각.
    마지막(진행 중) 버킷도 포함한다 — 라이브 1분봉의 '형성 중 캔들'과 같은 의미.
    """
    if minutes <= 1 or not candles:
        return candles
    buckets: dict[tuple[str, int], list[MinuteCandle]] = {}
    order: list[tuple[str, int]] = []
    for c in candles:
        minute_of_day = int(c.trade_time[:2]) * 60 + int(c.trade_time[2:4])
        key = (c.business_date, minute_of_day // minutes)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)
    out: list[MinuteCandle] = []
    for key in order:
        group = buckets[key]
        start_minute = key[1] * minutes
        out.append(
            MinuteCandle(
                business_date=key[0],
                trade_time=f"{start_minute // 60:02d}{start_minute % 60:02d}00",
                open_price=group[0].open_price,
                high_price=max(g.high_price for g in group),
                low_price=min(g.low_price for g in group),
                close_price=group[-1].close_price,
                volume=sum(g.volume for g in group),
            )
        )
    return out


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
        elif _is_daily(timeframe):
            # C-6.18: 일봉 전략 지원 — 브로커 일봉 조회를 MinuteCandle 형태로 변환.
            candles = await self._kr_daily_candles(symbol_code, count)
        else:
            # C-6.18 버그 수정: KIS 국내 분봉은 항상 1분봉 — 이전에는 timeframe을 무시하고
            # 1분봉을 그대로 돌려줘 모든 '5m' 전략이 사실상 1m 위에서 돌았다.
            # 이제 KIS 최신 1분봉 + DB 축적 1분봉을 병합 후 N분봉으로 리샘플한다(추가 KIS 호출 없음).
            nmin = _timeframe_to_nmin(timeframe)
            candles = await self._broker.get_minute_candles(symbol_code)
            candles = sorted(candles, key=lambda c: (c.business_date, c.trade_time))
            if self._session is not None:
                try:
                    # 원본 1분봉은 항상 '1m'으로 저장 — 리샘플 이력의 재료를 계속 축적.
                    await self.save_candles(symbol_code, "1m", candles)
                except Exception:
                    log.warning("1m market_data 저장 실패 (symbol=%s)", symbol_code, exc_info=True)
            if nmin > 1:
                merged = await self._merge_with_db_1m(symbol_code, candles, count * nmin)
                candles = resample_candles(merged, nmin)

        candles = sorted(candles, key=lambda c: (c.business_date, c.trade_time))
        candles = candles[-count:]

        if self._session is not None and not _is_daily(timeframe) and timeframe != "1m":
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

    async def _kr_daily_candles(self, symbol_code: str, count: int) -> list[MinuteCandle]:
        """국내 일봉을 MinuteCandle 형태(trade_time=153000)로 변환해 반환한다."""
        getter = getattr(self._broker, "get_daily_candles", None)
        if getter is None:
            raise RuntimeError("이 브로커는 일봉 조회(get_daily_candles)를 지원하지 않습니다.")
        dailies = await getter(symbol_code, count=count)
        return [
            MinuteCandle(
                business_date=d.business_date,
                trade_time="153000",
                open_price=d.open_price,
                high_price=d.high_price,
                low_price=d.low_price,
                close_price=d.close_price,
                volume=d.volume,
            )
            for d in sorted(dailies, key=lambda d: d.business_date)
        ]

    async def _merge_with_db_1m(
        self, symbol_code: str, fresh: list[MinuteCandle], minutes_needed: int
    ) -> list[MinuteCandle]:
        """KIS 최신 1분봉(당일 ~30개) 앞에 DB 축적 1분봉 이력을 이어붙인다.

        session이 없으면 fresh만 반환. dedupe 키 = (business_date, trade_time), fresh 우선.
        """
        if self._session is None:
            return fresh
        from datetime import timedelta, timezone  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from app.domain.models.market_data import MarketData  # noqa: PLC0415

        # 필요 분량의 3배 시간 창(장외 갭 감안)에서 최근 1m 행을 가져온다.
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes_needed * 3 + 60)
        stmt = (
            select(MarketData)
            .where(
                MarketData.symbol_code == symbol_code,
                MarketData.timeframe == "1m",
                MarketData.ts >= cutoff,
            )
            .order_by(MarketData.ts.desc())
            .limit(minutes_needed * 2)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        seen = {(c.business_date, c.trade_time) for c in fresh}
        history: list[MinuteCandle] = []
        for row in rows:
            ts_kst = row.ts.astimezone(KST)
            key = (ts_kst.strftime("%Y%m%d"), ts_kst.strftime("%H%M%S"))
            if key in seen:
                continue
            seen.add(key)
            history.append(
                MinuteCandle(
                    business_date=key[0], trade_time=key[1],
                    open_price=row.open, high_price=row.high,
                    low_price=row.low, close_price=row.close, volume=row.volume,
                )
            )
        merged = history + fresh
        return sorted(merged, key=lambda c: (c.business_date, c.trade_time))

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
