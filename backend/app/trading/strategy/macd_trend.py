from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import calculate_macd, candle_timestamp

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext


class MacdTrendStrategy(Strategy):
    """MACD 추세추종 전략 (모멘텀).

    - BUY: MACD선이 시그널선을 상향 교차(직전 macd<=signal, 현재 macd>signal).
           require_above_zero=True면 현재 MACD>0 일 때만 BUY.
    - SELL: MACD선이 시그널선을 하향 교차(직전 macd>=signal, 현재 macd<signal).
    - 그 외: None
    """

    name = "macd_trend"

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        require_above_zero: bool = False,
        quantity: int = 1,
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._signal_period = signal_period
        self._require_above_zero = require_above_zero
        self._quantity = quantity

    @classmethod
    def from_params(cls, params: dict) -> "MacdTrendStrategy":
        return cls(
            fast_period=params.get("fast_period", 12),
            slow_period=params.get("slow_period", 26),
            signal_period=params.get("signal_period", 9),
            require_above_zero=bool(params.get("require_above_zero", False)),
            quantity=params.get("quantity", 1),
        )

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: StrategyContext | None = None,
    ) -> Signal | None:
        # 교차를 보려면 직전·현재 두 시점의 MACD가 필요.
        # calculate_macd는 slow+signal-1개를 요구하므로 직전까지 보려면 +1.
        if len(candles) < self._slow_period + self._signal_period:
            return None

        prev = calculate_macd(
            candles[:-1], self._fast_period, self._slow_period, self._signal_period
        )
        curr = calculate_macd(
            candles, self._fast_period, self._slow_period, self._signal_period
        )
        if prev is None or curr is None:
            return None

        price = candles[-1].close_price
        metadata = {
            "macd": curr.macd,
            "macd_signal": curr.signal,
            "macd_histogram": curr.histogram,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        # BUY: 시그널선 상향 교차
        if prev.macd <= prev.signal and curr.macd > curr.signal:
            if self._require_above_zero and curr.macd <= 0:
                return None
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"MACD 골든크로스: MACD={curr.macd:.2f} > Signal={curr.signal:.2f}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 시그널선 하향 교차
        if prev.macd >= prev.signal and curr.macd < curr.signal:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"MACD 데드크로스: MACD={curr.macd:.2f} < Signal={curr.signal:.2f}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
