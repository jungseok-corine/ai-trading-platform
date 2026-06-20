from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.market_data import MarketDataRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.trading.analysis.trade_tape import Candle, TradeEvent, build_trade_tape

KST = ZoneInfo("Asia/Seoul")


class TradeTapeService:
    """전략 버전의 '그날 매매 테이프'를 온디맨드로 조립한다 (C-2.52).

    호출될 때만 실행되는 read-only 조립이다(평소 준비 안 함 → 토큰/연산 0, LLM 호출 없음).
    DB의 원본 분봉(market_data)과 체결(trades)에서 압축·사전계산된 번들을 만든다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = StrategyVersionRepository(session)
        self._trade_repo = TradeRepository(session)
        self._md_repo = MarketDataRepository(session)

    async def build_for_version(
        self,
        strategy_version_id: int,
        trading_day: date,
        timeframe: str = "1m",
        window: int = 15,
        coarse: int = 15,
    ) -> dict | None:
        """strategy_version의 trading_day 매매 테이프를 만든다. 버전이 없으면 None."""
        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            return None

        symbol_code = (version.parameters or {}).get("symbol_code", "")
        start = datetime.combine(trading_day, time.min, tzinfo=KST)
        end = start + timedelta(days=1)

        candles_raw = []
        if symbol_code:
            candles_raw = await self._md_repo.get_candles_between(
                symbol_code, timeframe, after_ts=start - timedelta(seconds=1), until_ts=end
            )
        candles = [
            Candle(ts=c.ts, o=float(c.open), h=float(c.high), lo=float(c.low),
                   c=float(c.close), v=float(c.volume))
            for c in candles_raw
        ]

        all_trades = await self._trade_repo.list_by_strategy_version(strategy_version_id)
        trades = [self._to_event(t) for t in all_trades if self._in_day(t, start, end)]

        tape = build_trade_tape(candles, trades, window=window, coarse=coarse)
        tape["meta"] = {
            "strategy_version_id": strategy_version_id,
            "symbol_code": symbol_code,
            "trading_day": trading_day.isoformat(),
            "timeframe": timeframe,
            "trade_count": len(trades),
        }
        return tape

    @staticmethod
    def _in_day(trade, start: datetime, end: datetime) -> bool:
        ref = trade.entry_time or trade.created_at
        return ref is not None and start <= ref < end

    @staticmethod
    def _to_event(trade) -> TradeEvent:
        def _f(v):
            return float(v) if v is not None else None

        return TradeEvent(
            side=trade.side.value if hasattr(trade.side, "value") else str(trade.side),
            quantity=trade.quantity,
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            entry_price=_f(trade.entry_price),
            exit_price=_f(trade.exit_price),
            pnl_amount=_f(trade.pnl_amount),
            pnl_pct=_f(trade.pnl_pct),
        )
