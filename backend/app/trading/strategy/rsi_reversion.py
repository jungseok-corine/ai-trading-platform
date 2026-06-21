from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import calculate_rsi, candle_timestamp

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext

_MIDLINE = Decimal(50)


class RsiReversionStrategy(Strategy):
    """RSI 평균회귀 전략 (역추세 / 과매도 반등).

    - BUY: 직전 RSI <= oversold 이고 현재 RSI > oversold (과매도 구간을 아래→위로 탈출)
    - SELL: exit_mode="overbought"면 현재 RSI >= overbought,
            exit_mode="midline"이면 RSI가 50을 상향 회귀(직전 <=50, 현재 >50)
    - 그 외: None
    - BUY가 SELL보다 우선한다(같은 캔들에서 둘 다 성립 시 BUY).
    """

    name = "rsi_reversion"

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: Decimal = Decimal("30"),
        overbought: Decimal = Decimal("70"),
        exit_mode: str = "overbought",
        quantity: int = 1,
    ) -> None:
        self._rsi_period = rsi_period
        self._oversold = oversold
        self._overbought = overbought
        self._exit_mode = exit_mode
        self._quantity = quantity

    @classmethod
    def from_params(cls, params: dict) -> "RsiReversionStrategy":
        return cls(
            rsi_period=params.get("rsi_period", 14),
            oversold=Decimal(str(params.get("oversold", "30"))),
            overbought=Decimal(str(params.get("overbought", "70"))),
            exit_mode=params.get("exit_mode", "overbought"),
            quantity=params.get("quantity", 1),
        )

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: StrategyContext | None = None,
    ) -> Signal | None:
        # 교차(아래→위)를 보려면 직전·현재 두 시점의 RSI가 필요 → period+2개
        if len(candles) < self._rsi_period + 2:
            return None

        prev_rsi = calculate_rsi(candles[:-1], self._rsi_period)
        curr_rsi = calculate_rsi(candles, self._rsi_period)
        if prev_rsi is None or curr_rsi is None:
            return None

        price = candles[-1].close_price
        metadata = {
            "rsi": curr_rsi,
            "prev_rsi": prev_rsi,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        # BUY: 과매도 탈출
        if prev_rsi <= self._oversold and curr_rsi > self._oversold:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"RSI 과매도 탈출: RSI({self._rsi_period}) "
                    f"{prev_rsi:.1f}→{curr_rsi:.1f} > {self._oversold}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 과열 또는 중심선 회귀
        if self._exit_mode == "midline":
            sell = prev_rsi <= _MIDLINE < curr_rsi
            reason = f"RSI 중심선 회귀: RSI({self._rsi_period}) {prev_rsi:.1f}→{curr_rsi:.1f} > 50"
        else:
            sell = curr_rsi >= self._overbought
            reason = f"RSI 과열: RSI({self._rsi_period})={curr_rsi:.1f} >= {self._overbought}"

        if sell:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=price,
                reason=reason,
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
