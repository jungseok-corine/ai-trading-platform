"""백테스트 엔진 (C-6.1).

저장된 market_data 위에서 전략 신호 생성기를 히스토리컬 리플레이한다.

안전 경계:
- **주문/브로커/KIS 호출 없음** — DB read + 순수 계산 + backtest_runs 기록만.
- Trade/Position/SignalLog를 만들지 않는다.
- 체결 시뮬레이션: 신호 발생 봉의 **다음 봉 시가** 체결(look-ahead 방지),
  수수료/세금은 기존 TradingCostCalculator 재사용.

포지션 모델(v1): 롱 온리 단일 포지션 — BUY 신호에 현금 전량 매수,
SELL 신호에 전량 청산. 마지막 봉에서 미청산 포지션은 종가로 강제 청산해 지표에 반영.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.backtest_run import BacktestRun
from app.domain.models.enums import TradeSide
from app.domain.models.market_data import MarketData
from app.trading.broker.schemas import MinuteCandle
from app.trading.pricing.fees import TradingCostCalculator
from app.trading.strategy.registry import create_strategy, registered_types

# 리플레이 시 전략에 넘기는 슬라이딩 윈도우 크기(러너의 candle 조회 제한과 같은 취지).
DEFAULT_LOOKBACK = 200
# 한 번의 백테스트에서 리플레이할 최대 봉 수 (동기 실행 보호).
MAX_BARS = 20_000


@dataclass
class _OpenPosition:
    quantity: int
    entry_price: Decimal
    entry_ts: str
    entry_cost: Decimal  # 매수 수수료


class BacktestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def run(
        self,
        *,
        strategy_type: str,
        parameters: dict[str, Any],
        symbol_code: str,
        timeframe: str,
        start_ts: datetime,
        end_ts: datetime,
        market: str = "KR",
        initial_cash: int = 10_000_000,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> BacktestRun:
        """백테스트를 동기 실행하고 결과를 backtest_runs에 기록해 반환한다."""
        run = BacktestRun(
            strategy_type=strategy_type,
            parameters=parameters,
            symbol_code=symbol_code,
            timeframe=timeframe,
            market=market,
            start_ts=start_ts,
            end_ts=end_ts,
            status="failed",
        )

        if strategy_type not in registered_types():
            run.error_message = f"등록되지 않은 strategy_type: {strategy_type}"
            return await self._persist(run)

        strategy = create_strategy(strategy_type, parameters)
        if strategy is None:
            run.error_message = f"전략 생성 실패: {strategy_type}"
            return await self._persist(run)

        candles = await self._load_candles(symbol_code, timeframe, start_ts, end_ts)
        if len(candles) < 2:
            run.error_message = (
                f"market_data에 캔들이 부족합니다 ({len(candles)}건) — "
                "symbol/timeframe/기간을 확인하세요."
            )
            return await self._persist(run)

        result = self._replay(strategy, symbol_code, candles, market, initial_cash, lookback)
        run.status = "succeeded"
        run.metrics = result["metrics"]
        run.simulated_trades = result["trades"]
        return await self._persist(run)

    async def _persist(self, run: BacktestRun) -> BacktestRun:
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def _load_candles(
        self, symbol_code: str, timeframe: str, start_ts: datetime, end_ts: datetime
    ) -> list[MinuteCandle]:
        stmt = (
            select(MarketData)
            .where(
                MarketData.symbol_code == symbol_code,
                MarketData.timeframe == timeframe,
                MarketData.ts >= start_ts,
                MarketData.ts <= end_ts,
            )
            .order_by(MarketData.ts)
            .limit(MAX_BARS)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            MinuteCandle(
                business_date=row.ts.strftime("%Y%m%d"),
                trade_time=row.ts.strftime("%H%M%S"),
                open_price=row.open,
                high_price=row.high,
                low_price=row.low,
                close_price=row.close,
                volume=row.volume,
            )
            for row in rows
        ]

    def _replay(
        self,
        strategy,
        symbol_code: str,
        candles: list[MinuteCandle],
        market: str,
        initial_cash: int,
        lookback: int,
    ) -> dict[str, Any]:
        cost_calc = TradingCostCalculator.for_market(market, self._settings)
        cash = Decimal(initial_cash)
        position: _OpenPosition | None = None
        trades: list[dict[str, Any]] = []
        equity_curve: list[Decimal] = []

        for i in range(1, len(candles) - 1):
            window = candles[max(0, i - lookback + 1) : i + 1]
            signal = strategy.generate_signal(symbol_code, window)
            next_bar = candles[i + 1]
            fill_price = next_bar.open_price

            if signal is not None and signal.side == TradeSide.BUY and position is None:
                qty = int(cash / fill_price) if fill_price > 0 else 0
                if qty > 0:
                    fee = cost_calc.calculate(TradeSide.BUY, fill_price, qty)
                    cash -= fill_price * qty + fee.total
                    position = _OpenPosition(
                        quantity=qty,
                        entry_price=fill_price,
                        entry_ts=_bar_ts(next_bar),
                        entry_cost=fee.total,
                    )
            elif signal is not None and signal.side == TradeSide.SELL and position is not None:
                cash += self._close(position, fill_price, _bar_ts(next_bar), cost_calc, trades, forced=False)
                position = None

            mark = candles[i].close_price
            equity_curve.append(cash + (position.quantity * mark if position else Decimal(0)))

        # 미청산 포지션은 마지막 봉 종가로 강제 청산 (지표 왜곡 방지)
        if position is not None:
            last = candles[-1]
            cash += self._close(position, last.close_price, _bar_ts(last), cost_calc, trades, forced=True)
            position = None
        equity_curve.append(cash)

        metrics = self._metrics(trades, equity_curve, Decimal(initial_cash), candles)
        # 에쿼티 커브 (C-6.14): UI 차트용 다운샘플 (최대 200포인트, 시작점 = 초기 자본)
        metrics["equity_curve"] = _downsample(
            [float(initial_cash)] + [float(e) for e in equity_curve], max_points=200
        )
        return {"trades": trades, "metrics": metrics}

    def _close(
        self,
        position: _OpenPosition,
        price: Decimal,
        ts: str,
        cost_calc: TradingCostCalculator,
        trades: list[dict[str, Any]],
        *,
        forced: bool,
    ) -> Decimal:
        fee = cost_calc.calculate(TradeSide.SELL, price, position.quantity)
        proceeds = price * position.quantity - fee.total
        pnl = proceeds - position.entry_price * position.quantity - position.entry_cost
        trades.append(
            {
                "entry_ts": position.entry_ts,
                "exit_ts": ts,
                "entry_price": str(position.entry_price),
                "exit_price": str(price),
                "quantity": position.quantity,
                "pnl": str(pnl),
                "fees": str(position.entry_cost + fee.total),
                "forced_close": forced,
            }
        )
        return proceeds

    def _metrics(
        self,
        trades: list[dict[str, Any]],
        equity_curve: list[Decimal],
        initial_cash: Decimal,
        candles: list[MinuteCandle],
    ) -> dict[str, Any]:
        pnls = [Decimal(t["pnl"]) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        total_pnl = sum(pnls, Decimal(0))

        # MDD: 에쿼티 곡선 기준
        peak = initial_cash
        mdd = Decimal(0)
        for eq in equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                mdd = max(mdd, (peak - eq) / peak)

        # 벤치마크: 단순 보유(첫 봉 시가 → 마지막 봉 종가)
        first_open = candles[0].open_price
        last_close = candles[-1].close_price
        buy_hold_return = (
            (last_close - first_open) / first_open if first_open > 0 else Decimal(0)
        )

        avg_win = sum(wins, Decimal(0)) / len(wins) if wins else Decimal(0)
        avg_loss = sum(losses, Decimal(0)) / len(losses) if losses else Decimal(0)
        win_rate = Decimal(len(wins)) / len(pnls) if pnls else None
        expectancy = (
            win_rate * avg_win + (1 - win_rate) * avg_loss if win_rate is not None else None
        )

        return {
            "bars": len(candles),
            "trade_count": len(trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": float(win_rate) if win_rate is not None else None,
            "total_pnl": str(total_pnl),
            "return_pct": float(total_pnl / initial_cash * 100),
            "avg_win": str(avg_win),
            "avg_loss": str(avg_loss),
            "expectancy": str(expectancy) if expectancy is not None else None,
            "max_drawdown_pct": float(mdd * 100),
            "buy_hold_return_pct": float(buy_hold_return * 100),
            "total_fees": str(sum((Decimal(t["fees"]) for t in trades), Decimal(0))),
        }

    async def get(self, run_id: int) -> BacktestRun | None:
        return await self._session.get(BacktestRun, run_id)

    async def list_recent(self, limit: int = 20) -> list[BacktestRun]:
        stmt = select(BacktestRun).order_by(BacktestRun.id.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())


def _bar_ts(candle: MinuteCandle) -> str:
    return f"{candle.business_date} {candle.trade_time}"


def _downsample(points: list[float], max_points: int) -> list[float]:
    """균등 간격 다운샘플. 마지막 포인트(최종 에쿼티)는 항상 보존한다."""
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    sampled = [points[int(i * step)] for i in range(max_points - 1)]
    sampled.append(points[-1])
    return sampled
