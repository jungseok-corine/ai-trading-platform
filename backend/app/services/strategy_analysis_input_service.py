"""Phase C-2.0: AI Analysis Input Payload.

strategy_version_id 기준으로 LLM에 바로 넘길 수 있는 structured input payload를 생성한다.
실제 AI API 호출 없음 — 분석 재료 생성만 수행한다.

설계 원칙:
  - StrategyPerformanceService 재사용 (성과 계산 로직 중복 없음)
  - SignalOutcomeService 재사용 (신호 결과 계산 로직 중복 없음)
  - DB 스키마 변경 없음
  - 데이터 부족(신호 없음, market_data 없음, 실제 거래 없음) 시에도 payload 생성
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import OrderStatus
from app.domain.repositories.market_data import MarketDataRepository
from app.domain.repositories.signal_log import SignalLogRepository
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.services.signal_outcome_service import SignalOutcomeService
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.trading_guard_service import TradingGuardService
from app.trading.strategy.schemas import (
    AnalysisInputContext,
    AnalysisInputMarketData,
    AnalysisInputRecentSignal,
    AnalysisInputSignalOutcome5m,
    AnalysisInputStrategyMeta,
    StrategyAnalysisInputRead,
)

_RECENT_SIGNAL_LIMIT = 20
_LIMITATIONS: list[str] = [
    "Signal outcome is based on hypothetical next-candle entry.",
    "Actual trading PnL may be incomplete when pnl_amount is null.",
    "Paper trading order status may lag or differ from real trading."
    " Fill status is synchronized via VTTC0081R daily order execution inquiry when available.",
    "A unified sync pipeline (C-2.11) runs order fill sync then broker balance reconciliation."
    " Trigger manually via POST /accounts/{account_id}/trading-state/sync"
    " or enable the trading_state_sync scheduler job."
    " Paper mode mismatches are auto-corrected against broker holdings;"
    " real mode mismatches generate risk_events.",
    "This is not financial advice.",
]
_PAUSE_SAFETY_NOTE = (
    "IMPORTANT: If trading_paused is true, the AI MUST NOT recommend immediate resumption."
    " Resumption requires human review via POST /api/v1/accounts/{account_id}/trading-guard/resume."
)


class StrategyAnalysisInputService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._signal_repo = SignalLogRepository(session)
        self._md_repo = MarketDataRepository(session)
        self._trade_repo = TradeRepository(session)
        self._perf_svc = StrategyPerformanceService(session)
        self._outcome_svc = SignalOutcomeService(session)
        self._guard_svc = TradingGuardService(session)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def get_analysis_input(
        self, strategy_id: int, version_id: int
    ) -> StrategyAnalysisInputRead | None:
        """strategy_id/version_id 조합이 없으면 None을 반환한다."""
        version = await self._version_repo.get(version_id)
        if version is None or version.strategy_id != strategy_id:
            return None

        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            return None  # defensive — strategy_id FK 보장이지만 안전하게 처리

        # StrategyPerformanceService 재사용 — 중복 계산 없음
        performance = await self._perf_svc.get_version_performance(strategy_id, version_id)
        if performance is None:
            # version 검증 후이므로 이론적으로 도달 불가 — 방어 코드
            return None

        symbol_code: str = version.parameters.get("symbol_code", "")
        market_data = await self._get_market_data_summary(symbol_code)
        recent_signals = await self._get_recent_signals(version_id)
        limitations = list(_LIMITATIONS)
        pending_count = await self._count_pending_trades(version_id)
        if pending_count > 0:
            limitations.append(
                f"{pending_count} order(s) are still in pending/partial status."
                " These are NOT included in fill/PnL calculations."
                " Run order sync (VTTC0081R) to update fill status."
            )

        account_id: int | None = version.parameters.get("account_id")
        trading_paused = False
        pause_reason: str | None = None
        if account_id is not None:
            guard_state = await self._guard_svc.get_state(account_id)
            if guard_state is not None and guard_state.is_paused:
                trading_paused = True
                pause_reason = guard_state.pause_reason
                limitations.append(_PAUSE_SAFETY_NOTE)

        return StrategyAnalysisInputRead(
            strategy=AnalysisInputStrategyMeta(
                strategy_id=strategy_id,
                strategy_name=strategy.name,
                strategy_version_id=version_id,
                version_no=version.version_no,
                status=version.status,
                parameters=version.parameters,
            ),
            performance=performance,
            market_data=market_data,
            recent_signals=recent_signals,
            analysis_context=AnalysisInputContext(
                generated_at=datetime.now(tz=timezone.utc),
                limitations=limitations,
                trading_paused=trading_paused,
                pause_reason=pause_reason,
            ),
        )

    # ------------------------------------------------------------------
    # private helpers

    async def _count_pending_trades(self, version_id: int) -> int:
        trades = await self._trade_repo.list_by_strategy_version(version_id)
        return sum(
            1 for t in trades
            if t.order_status in (OrderStatus.PENDING, OrderStatus.PARTIAL)
        )
    # ------------------------------------------------------------------

    async def _get_market_data_summary(self, symbol_code: str) -> AnalysisInputMarketData:
        """symbol_code 기준 market_data 요약. symbol_code 없으면 빈 요약 반환."""
        if not symbol_code:
            return AnalysisInputMarketData(
                symbols=[], timeframes=[], latest_ts=None, row_count=0
            )

        rows = await self._md_repo.get_symbol_summary_by_timeframe(symbol_code)
        if not rows:
            return AnalysisInputMarketData(
                symbols=[symbol_code], timeframes=[], latest_ts=None, row_count=0
            )

        timeframes = [r["timeframe"] for r in rows]
        latest_ts_values = [r["latest_ts"] for r in rows if r["latest_ts"] is not None]
        latest_ts = max(latest_ts_values) if latest_ts_values else None
        row_count = int(sum(r["count"] for r in rows))

        return AnalysisInputMarketData(
            symbols=[symbol_code],
            timeframes=timeframes,
            latest_ts=latest_ts,
            row_count=row_count,
        )

    async def _get_recent_signals(
        self, version_id: int
    ) -> list[AnalysisInputRecentSignal]:
        """최근 신호 최대 20개와 각 신호의 5분 결과를 반환한다."""
        signals = await self._signal_repo.list_filtered(
            limit=_RECENT_SIGNAL_LIMIT,
            strategy_version_id=version_id,
        )

        results: list[AnalysisInputRecentSignal] = []
        for sig in signals:
            outcome = await self._outcome_svc._compute_outcome(sig)
            outcome_5m: AnalysisInputSignalOutcome5m | None = None
            if outcome.available:
                hr = next(
                    (h for h in outcome.horizons if h.horizon_minutes == 5), None
                )
                if hr and hr.available:
                    outcome_5m = AnalysisInputSignalOutcome5m(
                        directional_return_pct=hr.directional_return_pct,
                        is_win=hr.is_win,
                    )
            results.append(AnalysisInputRecentSignal(
                signal_id=sig.id,
                symbol_code=sig.symbol_code,
                signal_type=sig.signal_type,
                generated_at=sig.generated_at,
                outcome_5m=outcome_5m,
            ))
        return results
