from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import calculate_sma, candle_timestamp

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext


class PullbackTrendStrategy(Strategy):
    """눌림목 매수 전략 (상승추세 내 되돌림).

    - BUY: 상승추세(현재 종가 > 장기MA) 中, 직전 종가 < 직전 단기MA 이고
           현재 종가 > 현재 단기MA (단기선 아래로 눌렸다가 재탈환).
    - SELL: 종가가 장기MA를 하향 이탈(직전 종가 >= 직전 장기MA, 현재 종가 < 현재 장기MA).
    - 그 외: None
    """

    name = "pullback_trend"

    def __init__(
        self,
        short_window: int = 10,
        long_window: int = 50,
        quantity: int = 1,
    ) -> None:
        self._short_window = short_window
        self._long_window = long_window
        self._quantity = quantity

    @classmethod
    def from_params(cls, params: dict) -> "PullbackTrendStrategy":
        return cls(
            short_window=params.get("short_window", 10),
            long_window=params.get("long_window", 50),
            quantity=params.get("quantity", 1),
        )

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: StrategyContext | None = None,
    ) -> Signal | None:
        # 직전·현재 두 시점의 MA가 필요 → 장기 기간 +1
        if len(candles) < self._long_window + 1:
            return None

        prev_short = calculate_sma(candles[:-1], self._short_window)
        curr_short = calculate_sma(candles, self._short_window)
        prev_long = calculate_sma(candles[:-1], self._long_window)
        curr_long = calculate_sma(candles, self._long_window)
        if prev_short is None or curr_short is None or prev_long is None or curr_long is None:
            return None

        prev_close = candles[-2].close_price
        curr_close = candles[-1].close_price
        price = curr_close
        metadata = {
            "short_ma": curr_short,
            "long_ma": curr_long,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        # BUY: 상승추세 中 단기선 재탈환 (눌림 후 반등)
        uptrend = curr_close > curr_long
        if uptrend and prev_close < prev_short and curr_close > curr_short:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"눌림목 반등: 추세(종가>{self._long_window}MA={curr_long:.2f}) 中 "
                    f"단기MA({self._short_window})={curr_short:.2f} 재탈환"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 장기MA 하향 이탈 (추세 종료)
        if prev_close >= prev_long and curr_close < curr_long:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"추세 이탈: 종가={curr_close} < 장기MA({self._long_window})={curr_long:.2f}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
