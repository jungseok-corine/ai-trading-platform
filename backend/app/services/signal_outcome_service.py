"""Phase C-0: Signal Outcome Analysis.

신호 발생 이후 실제 가격 움직임을 market_data에서 조회해 수익률과 MFE/MAE를 계산한다.
백테스트 엔진이 아님 — 주문 체결/포지션/복리 계산은 포함하지 않는다.

분석 규칙:
  - 진입가(entry_price): 신호 candle_ts 이후 첫 번째 캔들의 open
  - return_pct = (close_at_horizon - entry_price) / entry_price * 100
    BUY: 양수 = 상승 = 좋음
    SELL: 음수 = 하락 = 좋음  (방향 해석은 호출자 책임)
  - MFE/MAE: 신호 방향 기준 조정됨 (항상 양수)
    BUY  MFE = (max_high - entry) / entry * 100
    BUY  MAE = (entry - min_low)  / entry * 100
    SELL MFE = (entry - min_low)  / entry * 100
    SELL MAE = (max_high - entry) / entry * 100
  - horizon: 5, 15, 30, 60분
  - timeframe: 기본 "1m" (전략 러너가 저장하는 단위)
"""
from datetime import datetime, timedelta
from decimal import Decimal, DivisionByZero, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.domain.repositories.market_data import MarketDataRepository
from app.domain.repositories.signal_log import SignalLogRepository
from app.trading.strategy.schemas import (
    SignalOutcomeByHorizon,
    SignalOutcomeBySignalType,
    SignalOutcomeBySymbol,
    SignalOutcomeHorizonResult,
    SignalOutcomeRead,
    SignalOutcomeSummary,
)


HORIZONS: list[int] = [5, 15, 30, 60]
_FETCH_BUFFER_MINUTES = 2  # 마지막 horizon 이후 약간 더 가져와 경계 candle 확보


def _safe_pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """denominator가 0이면 None을 반환한다."""
    try:
        if denominator == 0:
            return None
        return (numerator / denominator * Decimal("100")).quantize(Decimal("0.0001"))
    except (DivisionByZero, InvalidOperation):
        return None


def _is_win(return_pct: Decimal, signal_type: TradeSide) -> bool:
    """신호 방향 기준으로 '이겼는지' 판단한다."""
    if signal_type == TradeSide.BUY:
        return return_pct > 0
    # SELL: 가격이 하락(return_pct < 0)하면 신호가 맞은 것
    return return_pct < 0


class SignalOutcomeService:
    DEFAULT_TIMEFRAME = "1m"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._signal_repo = SignalLogRepository(session)
        self._md_repo = MarketDataRepository(session)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    async def get_outcome(self, signal_id: int) -> SignalOutcomeRead | None:
        """단일 신호의 이후 가격 반응을 분석한다. 신호가 없으면 None."""
        signal = await self._signal_repo.get(signal_id)
        if signal is None:
            return None
        return await self._compute_outcome(signal)

    async def get_summary(
        self,
        limit: int = 100,
        signal_type: TradeSide | None = None,
        symbol_code: str | None = None,
    ) -> SignalOutcomeSummary:
        """최근 신호들의 outcome을 집계해 요약한다."""
        signals = await self._signal_repo.list_filtered(
            limit=limit,
            signal_type=signal_type,
            symbol_code=symbol_code,
        )

        all_outcomes = await self._compute_outcomes_batch(signals)
        outcomes = [o for o in all_outcomes if o.available]
        skipped = len(all_outcomes) - len(outcomes)

        return self._aggregate(
            total=len(signals),
            analyzed=outcomes,
            skipped=skipped,
        )

    # ------------------------------------------------------------------
    # computation
    # ------------------------------------------------------------------

    def _ref_ts_or_unavailable(self, signal: SignalLog) -> datetime | SignalOutcomeRead:
        """분석 가능하면 ref_ts(datetime)를, 아니면 _unavailable 결과를 반환한다."""
        # BUY/SELL만 분석 대상 (HOLD 등 추가 시 여기서 skip)
        if signal.signal_type not in (TradeSide.BUY, TradeSide.SELL):
            return self._unavailable(signal, note="unsupported signal_type (skipped)")
        ref_ts = signal.candle_ts or signal.generated_at
        if ref_ts is None:
            return self._unavailable(signal, note="no reference timestamp")
        return ref_ts

    def _outcome_from_candles(
        self, signal: SignalLog, ref_ts: datetime, candles: list[MarketData]
    ) -> SignalOutcomeRead:
        """이미 조회된 캔들(ref_ts 이후 구간)로 outcome을 계산한다."""
        if not candles:
            return self._unavailable(signal, ref_ts=ref_ts, note="no market_data after signal")

        entry_price = candles[0].open
        if entry_price <= 0:
            return self._unavailable(signal, ref_ts=ref_ts, note="invalid entry_price (≤ 0)")

        horizon_results = self._compute_horizons(ref_ts, entry_price, candles, signal.signal_type)
        mfe_pct, mae_pct = self._compute_excursions(signal.signal_type, entry_price, candles)

        return SignalOutcomeRead(
            signal_id=signal.id,
            symbol_code=signal.symbol_code,
            signal_type=signal.signal_type,
            signal_ts=ref_ts,
            timeframe=signal.timeframe or self.DEFAULT_TIMEFRAME,
            entry_price=entry_price,
            horizons=horizon_results,
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            available=True,
            note=None,
        )

    async def _compute_outcome(self, signal: SignalLog) -> SignalOutcomeRead:
        ref = self._ref_ts_or_unavailable(signal)
        if isinstance(ref, SignalOutcomeRead):
            return ref
        ref_ts = ref
        until_ts = ref_ts + timedelta(minutes=HORIZONS[-1] + _FETCH_BUFFER_MINUTES)
        candles = await self._md_repo.get_candles_between(
            symbol_code=signal.symbol_code,
            timeframe=signal.timeframe or self.DEFAULT_TIMEFRAME,
            after_ts=ref_ts,
            until_ts=until_ts,
        )
        return self._outcome_from_candles(signal, ref_ts, candles)

    async def _compute_outcomes_batch(self, signals: list[SignalLog]) -> list[SignalOutcomeRead]:
        """여러 신호의 outcome을 배치로 계산한다 (신호별 candle 조회 N+1 제거).

        심볼별로 필요한 시간 구간을 합쳐 1회씩만 조회하고, 신호별로 인메모리에서
        get_candles_between과 동일한 경계(ts > ref_ts, ts <= until_ts)로 슬라이스한다.
        """
        from collections import defaultdict

        max_until = HORIZONS[-1] + _FETCH_BUFFER_MINUTES
        windows: dict[int, tuple[datetime, datetime]] = {}
        pre: dict[int, SignalOutcomeRead] = {}
        # 같은 종목이라도 신호마다 timeframe이 다를 수 있어 (symbol, timeframe)로 묶는다.
        by_key: dict[tuple[str, str], list[SignalLog]] = defaultdict(list)
        for sig in signals:
            ref = self._ref_ts_or_unavailable(sig)
            if isinstance(ref, SignalOutcomeRead):
                pre[sig.id] = ref
                continue
            windows[sig.id] = (ref, ref + timedelta(minutes=max_until))
            by_key[(sig.symbol_code, sig.timeframe or self.DEFAULT_TIMEFRAME)].append(sig)

        candles_by_key: dict[tuple[str, str], list[MarketData]] = {}
        for (symbol, tf), sigs in by_key.items():
            refs = [windows[s.id] for s in sigs]
            candles_by_key[(symbol, tf)] = await self._md_repo.get_candles_between(
                symbol_code=symbol,
                timeframe=tf,
                after_ts=min(r for r, _ in refs),
                until_ts=max(u for _, u in refs),
            )

        outcomes: list[SignalOutcomeRead] = []
        for sig in signals:
            if sig.id in pre:
                outcomes.append(pre[sig.id])
                continue
            ref_ts, until_ts = windows[sig.id]
            key = (sig.symbol_code, sig.timeframe or self.DEFAULT_TIMEFRAME)
            window = [c for c in candles_by_key.get(key, []) if ref_ts < c.ts <= until_ts]
            outcomes.append(self._outcome_from_candles(sig, ref_ts, window))
        return outcomes

    def _compute_horizons(
        self,
        ref_ts,
        entry_price: Decimal,
        candles: list[MarketData],
        signal_type: TradeSide,
    ) -> list[SignalOutcomeHorizonResult]:
        results = []
        for h in HORIZONS:
            horizon_ts = ref_ts + timedelta(minutes=h)
            # 해당 horizon 이후 첫 번째 캔들 (≥ horizon_ts)
            candle = next((c for c in candles if c.ts >= horizon_ts), None)
            if candle is None:
                results.append(SignalOutcomeHorizonResult(
                    horizon_minutes=h,
                    close_price=None,
                    return_pct=None,
                    available=False,
                    is_win=None,
                    directional_return_pct=None,
                ))
            else:
                ret = _safe_pct(candle.close - entry_price, entry_price)
                if ret is not None:
                    is_win = _is_win(ret, signal_type)
                    dir_ret = ret if signal_type == TradeSide.BUY else -ret
                else:
                    is_win = None
                    dir_ret = None
                results.append(SignalOutcomeHorizonResult(
                    horizon_minutes=h,
                    close_price=candle.close,
                    return_pct=ret,
                    available=ret is not None,
                    is_win=is_win,
                    directional_return_pct=dir_ret,
                ))
        return results

    def _compute_excursions(
        self,
        signal_type: TradeSide,
        entry_price: Decimal,
        candles: list[MarketData],
    ) -> tuple[Decimal | None, Decimal | None]:
        if not candles:
            return None, None
        max_high = max(c.high for c in candles)
        min_low = min(c.low for c in candles)

        if signal_type == TradeSide.BUY:
            mfe = _safe_pct(max_high - entry_price, entry_price)
            mae = _safe_pct(entry_price - min_low, entry_price)
        else:  # SELL
            mfe = _safe_pct(entry_price - min_low, entry_price)
            mae = _safe_pct(max_high - entry_price, entry_price)

        return mfe, mae

    # ------------------------------------------------------------------
    # aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        total: int,
        analyzed: list[SignalOutcomeRead],
        skipped: int,
    ) -> SignalOutcomeSummary:
        by_horizon = self._agg_by_horizon(analyzed)
        by_symbol = self._agg_by_symbol(analyzed)
        by_signal_type = self._agg_by_signal_type(analyzed)
        return SignalOutcomeSummary(
            total_signals=total,
            analyzed_count=len(analyzed),
            skipped_count=skipped,
            by_horizon=by_horizon,
            by_symbol=by_symbol,
            by_signal_type=by_signal_type,
        )

    def _agg_by_horizon(self, outcomes: list[SignalOutcomeRead]) -> list[SignalOutcomeByHorizon]:
        results = []
        for h in HORIZONS:
            returns: list[tuple[Decimal, TradeSide]] = []
            for o in outcomes:
                hr = next((r for r in o.horizons if r.horizon_minutes == h), None)
                if hr and hr.available and hr.return_pct is not None:
                    returns.append((hr.return_pct, o.signal_type))

            if not returns:
                results.append(SignalOutcomeByHorizon(
                    horizon_minutes=h,
                    count=0,
                    avg_return_pct=Decimal("0"),
                    win_rate=Decimal("0"),
                ))
                continue

            avg = sum(r for r, _ in returns) / len(returns)
            wins = sum(1 for r, st in returns if _is_win(r, st))
            results.append(SignalOutcomeByHorizon(
                horizon_minutes=h,
                count=len(returns),
                avg_return_pct=avg.quantize(Decimal("0.0001")),
                win_rate=(Decimal(wins) / len(returns)).quantize(Decimal("0.0001")),
            ))
        return results

    def _agg_by_symbol(self, outcomes: list[SignalOutcomeRead]) -> list[SignalOutcomeBySymbol]:
        groups: dict[str, list[SignalOutcomeRead]] = {}
        for o in outcomes:
            groups.setdefault(o.symbol_code, []).append(o)

        result = []
        for sym, items in sorted(groups.items()):
            win_rate_5m = self._win_rate_at_horizon(items, 5)
            result.append(SignalOutcomeBySymbol(
                symbol_code=sym,
                signal_count=len(items),
                analyzed_count=len(items),
                win_rate_5m=win_rate_5m,
            ))
        return result

    def _agg_by_signal_type(self, outcomes: list[SignalOutcomeRead]) -> list[SignalOutcomeBySignalType]:
        result = []
        for st in (TradeSide.BUY, TradeSide.SELL):
            items = [o for o in outcomes if o.signal_type == st]
            if not items:
                continue
            win_rate_5m = self._win_rate_at_horizon(items, 5)
            result.append(SignalOutcomeBySignalType(
                signal_type=st,
                signal_count=len(items),
                analyzed_count=len(items),
                win_rate_5m=win_rate_5m,
            ))
        return result

    @staticmethod
    def _win_rate_at_horizon(
        outcomes: list[SignalOutcomeRead],
        horizon: int,
    ) -> Decimal | None:
        returns = []
        for o in outcomes:
            hr = next((r for r in o.horizons if r.horizon_minutes == horizon), None)
            if hr and hr.available and hr.return_pct is not None:
                returns.append((hr.return_pct, o.signal_type))
        if not returns:
            return None
        wins = sum(1 for r, st in returns if _is_win(r, st))
        return (Decimal(wins) / len(returns)).quantize(Decimal("0.0001"))

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unavailable(
        signal: SignalLog,
        ref_ts=None,
        note: str | None = None,
    ) -> SignalOutcomeRead:
        ts = ref_ts or signal.candle_ts or signal.generated_at
        return SignalOutcomeRead(
            signal_id=signal.id,
            symbol_code=signal.symbol_code,
            signal_type=signal.signal_type,
            signal_ts=ts,
            timeframe=signal.timeframe or SignalOutcomeService.DEFAULT_TIMEFRAME,
            entry_price=None,
            horizons=[
                SignalOutcomeHorizonResult(
                    horizon_minutes=h,
                    close_price=None,
                    return_pct=None,
                    available=False,
                )
                for h in HORIZONS
            ],
            mfe_pct=None,
            mae_pct=None,
            available=False,
            note=note,
        )
