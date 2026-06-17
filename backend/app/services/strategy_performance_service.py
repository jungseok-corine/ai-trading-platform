"""Phase C-1: Strategy Version Performance Metrics.

strategy_version_id 기준으로 signal outcome을 집계해 전략 성과를 반환한다.
실제 체결(trades) 성과도 별도 구역으로 포함한다.

설계 원칙:
  - 온더플라이 계산 (DB 컬럼 업데이트 없음)
  - SignalOutcomeService._compute_outcome() 재사용 — 계산 로직 중복 없음
  - 최대 _SIGNAL_LIMIT개 신호만 분석 (연산 상한)
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import OrderStatus, TradeSide
from app.domain.repositories.signal_log import SignalLogRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.services.signal_outcome_service import HORIZONS, SignalOutcomeService
from app.trading.strategy.schemas import (
    SignalOutcomeRead,
    StrategyVersionActualTradingPerformance,
    StrategyVersionPerformanceByHorizon,
    StrategyVersionPerformanceBySignalType,
    StrategyVersionPerformanceBySymbol,
    StrategyVersionPerformanceRead,
)

_Q4 = Decimal("0.0001")
_SIGNAL_LIMIT = 1000


def _is_win(return_pct: Decimal, signal_type: TradeSide) -> bool:
    if signal_type == TradeSide.BUY:
        return return_pct > 0
    return return_pct < 0


def _avg(*values: Decimal) -> Decimal:
    return sum(values) / Decimal(len(values))


class StrategyPerformanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = StrategyVersionRepository(session)
        self._signal_repo = SignalLogRepository(session)
        self._trade_repo = TradeRepository(session)
        self._outcome_svc = SignalOutcomeService(session)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def get_version_performance(
        self, strategy_id: int, version_id: int
    ) -> StrategyVersionPerformanceRead | None:
        """strategy_id / version_id 조합이 없으면 None을 반환한다."""
        version = await self._version_repo.get(version_id)
        if version is None or version.strategy_id != strategy_id:
            return None

        signals = await self._signal_repo.list_filtered(
            limit=_SIGNAL_LIMIT,
            strategy_version_id=version_id,
        )

        outcomes: list[SignalOutcomeRead] = []
        skipped = 0
        for sig in signals:
            outcome = await self._outcome_svc._compute_outcome(sig)
            if outcome.available:
                outcomes.append(outcome)
            else:
                skipped += 1

        actual_trading = await self._get_actual_trading(version_id)

        return StrategyVersionPerformanceRead(
            strategy_id=strategy_id,
            strategy_version_id=version_id,
            total_signals=len(signals),
            analyzed_signals=len(outcomes),
            skipped_signals=skipped,
            by_horizon=self._agg_by_horizon(outcomes),
            by_signal_type=self._agg_by_signal_type(signals, outcomes),
            by_symbol=self._agg_by_symbol(signals, outcomes),
            actual_trading=actual_trading,
        )

    # ------------------------------------------------------------------
    # aggregation — signal-based performance
    # ------------------------------------------------------------------

    def _agg_by_horizon(
        self, outcomes: list[SignalOutcomeRead]
    ) -> list[StrategyVersionPerformanceByHorizon]:
        results = []
        for h in HORIZONS:
            data = []
            for o in outcomes:
                hr = next((r for r in o.horizons if r.horizon_minutes == h), None)
                if hr and hr.available and hr.return_pct is not None and hr.directional_return_pct is not None:
                    data.append({
                        "return_pct": hr.return_pct,
                        "dir_pct": hr.directional_return_pct,
                        "signal_type": o.signal_type,
                        "mfe": o.mfe_pct,
                        "mae": o.mae_pct,
                    })

            if not data:
                results.append(StrategyVersionPerformanceByHorizon(
                    horizon_minutes=h, count=0,
                    win_rate=Decimal("0"),
                    avg_return_pct=Decimal("0"),
                    avg_directional_return_pct=Decimal("0"),
                    avg_mfe_pct=None, avg_mae_pct=None,
                ))
                continue

            n = Decimal(len(data))
            wins = sum(1 for d in data if _is_win(d["return_pct"], d["signal_type"]))
            mfes = [d["mfe"] for d in data if d["mfe"] is not None]
            maes = [d["mae"] for d in data if d["mae"] is not None]

            results.append(StrategyVersionPerformanceByHorizon(
                horizon_minutes=h,
                count=len(data),
                win_rate=(Decimal(wins) / n).quantize(_Q4),
                avg_return_pct=(sum(d["return_pct"] for d in data) / n).quantize(_Q4),
                avg_directional_return_pct=(sum(d["dir_pct"] for d in data) / n).quantize(_Q4),
                avg_mfe_pct=(sum(mfes) / Decimal(len(mfes))).quantize(_Q4) if mfes else None,
                avg_mae_pct=(sum(maes) / Decimal(len(maes))).quantize(_Q4) if maes else None,
            ))
        return results

    def _agg_by_signal_type(
        self,
        all_signals: list,
        outcomes: list[SignalOutcomeRead],
    ) -> list[StrategyVersionPerformanceBySignalType]:
        result = []
        for st in (TradeSide.BUY, TradeSide.SELL):
            total = [s for s in all_signals if s.signal_type == st]
            if not total:
                continue
            analyzed = [o for o in outcomes if o.signal_type == st]
            win_rate_5m, avg_dir_5m = self._horizon_stats(analyzed, 5)
            result.append(StrategyVersionPerformanceBySignalType(
                signal_type=st,
                signal_count=len(total),
                analyzed_count=len(analyzed),
                win_rate_5m=win_rate_5m,
                avg_directional_return_pct_5m=avg_dir_5m,
            ))
        return result

    def _agg_by_symbol(
        self,
        all_signals: list,
        outcomes: list[SignalOutcomeRead],
    ) -> list[StrategyVersionPerformanceBySymbol]:
        # group total signals by symbol
        sym_totals: dict[str, int] = {}
        for s in all_signals:
            sym_totals[s.symbol_code] = sym_totals.get(s.symbol_code, 0) + 1

        # group outcomes by symbol
        sym_outcomes: dict[str, list[SignalOutcomeRead]] = {}
        for o in outcomes:
            sym_outcomes.setdefault(o.symbol_code, []).append(o)

        result = []
        for sym in sorted(sym_totals):
            analyzed = sym_outcomes.get(sym, [])
            win_rate_5m, avg_dir_5m = self._horizon_stats(analyzed, 5)
            result.append(StrategyVersionPerformanceBySymbol(
                symbol_code=sym,
                signal_count=sym_totals[sym],
                analyzed_count=len(analyzed),
                win_rate_5m=win_rate_5m,
                avg_directional_return_pct_5m=avg_dir_5m,
            ))
        return result

    @staticmethod
    def _horizon_stats(
        outcomes: list[SignalOutcomeRead], horizon: int
    ) -> tuple[Decimal | None, Decimal | None]:
        """(win_rate, avg_directional_return_pct)을 반환한다. 데이터 없으면 (None, None)."""
        data = []
        for o in outcomes:
            hr = next((r for r in o.horizons if r.horizon_minutes == horizon), None)
            if hr and hr.available and hr.return_pct is not None and hr.directional_return_pct is not None:
                data.append((hr.return_pct, hr.directional_return_pct, o.signal_type))
        if not data:
            return None, None
        wins = sum(1 for r, _, st in data if _is_win(r, st))
        win_rate = (Decimal(wins) / Decimal(len(data))).quantize(_Q4)
        avg_dir = (sum(d for _, d, _ in data) / Decimal(len(data))).quantize(_Q4)
        return win_rate, avg_dir

    # ------------------------------------------------------------------
    # actual trading performance
    # ------------------------------------------------------------------

    async def _get_actual_trading(
        self, version_id: int
    ) -> StrategyVersionActualTradingPerformance:
        trades = await self._trade_repo.list_by_strategy_version(version_id)
        filled = [t for t in trades if t.order_status == OrderStatus.FILLED]

        pnl_values = [t.pnl_amount for t in filled if t.pnl_amount is not None]
        total_pnl = sum(pnl_values) if pnl_values else None
        win_count = sum(1 for p in pnl_values if p > 0) if pnl_values else None
        loss_count = sum(1 for p in pnl_values if p <= 0) if pnl_values else None

        return StrategyVersionActualTradingPerformance(
            trade_count=len(trades),
            filled_count=len(filled),
            total_pnl_amount=total_pnl,
            win_trade_count=win_count,
            loss_trade_count=loss_count,
            note=(
                "pnl_amount는 exit_price가 기록된 체결 건만 포함됩니다. "
                "VTS 단건 주문(BUY/SELL 별도) 구조상 pnl_amount가 null인 경우가 많습니다."
            ),
        )
