from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import calculate_volume_ratio, candle_timestamp

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext


class BreakoutHighStrategy(Strategy):
    """전고점 돌파 전략 (추세 추종, Donchian 채널).

    - BUY: 현재 종가 > 직전 breakout_lookback봉의 최고가 (신고가 돌파).
           volume_confirm=True면 거래량비율 >= volume_multiplier 일 때만 BUY.
    - SELL: 현재 종가 < 직전 exit_lookback봉의 최저가 (하단 이탈).
    - 그 외: None
    - 비교 구간은 현재 캔들을 제외한 직전 N개다(look-ahead 방지).
    """

    name = "breakout_high"

    def __init__(
        self,
        breakout_lookback: int = 20,
        exit_lookback: int = 10,
        volume_confirm: bool = False,
        volume_window: int = 20,
        volume_multiplier: Decimal = Decimal("1.5"),
        quantity: int = 1,
    ) -> None:
        self._breakout_lookback = breakout_lookback
        self._exit_lookback = exit_lookback
        self._volume_confirm = volume_confirm
        self._volume_window = volume_window
        self._volume_multiplier = volume_multiplier
        self._quantity = quantity

    @classmethod
    def from_params(cls, params: dict) -> "BreakoutHighStrategy":
        return cls(
            breakout_lookback=params.get("breakout_lookback", 20),
            exit_lookback=params.get("exit_lookback", 10),
            volume_confirm=bool(params.get("volume_confirm", False)),
            volume_window=params.get("volume_window", 20),
            volume_multiplier=Decimal(str(params.get("volume_multiplier", "1.5"))),
            quantity=params.get("quantity", 1),
        )

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: StrategyContext | None = None,
    ) -> Signal | None:
        if len(candles) < max(self._breakout_lookback, self._exit_lookback) + 1:
            return None

        prior_high = max(c.high_price for c in candles[-self._breakout_lookback - 1 : -1])
        prior_low = min(c.low_price for c in candles[-self._exit_lookback - 1 : -1])
        close = candles[-1].close_price
        volume_ratio = calculate_volume_ratio(candles, self._volume_window)

        metadata = {
            "close": close,
            "prior_high": prior_high,
            "prior_low": prior_low,
            "volume_ratio": volume_ratio,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        # BUY: 신고가 돌파 (+ 선택적 거래량 확인)
        if close > prior_high:
            if self._volume_confirm and not (
                volume_ratio is not None and volume_ratio >= self._volume_multiplier
            ):
                return None
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=close,
                reason=(
                    f"전고점 돌파: 종가={close} > 직전{self._breakout_lookback}봉 고가={prior_high}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 하단 이탈
        if close < prior_low:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=close,
                reason=(
                    f"하단 이탈: 종가={close} < 직전{self._exit_lookback}봉 저가={prior_low}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
