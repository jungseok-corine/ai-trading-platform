from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import calculate_sma, candle_timestamp


class MovingAverageCrossStrategy(Strategy):
    """단기/장기 이동평균선 교차(골든크로스/데드크로스) 전략.

    - 골든크로스(단기선이 장기선을 상향 돌파): BUY
    - 데드크로스(단기선이 장기선을 하향 돌파): SELL
    - 그 외(교차 없음, 데이터 부족): None
    """

    name = "moving_average_cross"

    @classmethod
    def from_params(cls, params: dict) -> "MovingAverageCrossStrategy":
        return cls(
            short_window=params.get("short_window", 5),
            long_window=params.get("long_window", 20),
            quantity=params.get("quantity", 1),
        )

    def __init__(self, short_window: int = 5, long_window: int = 20, quantity: int = 1) -> None:
        self._short_window = short_window
        self._long_window = long_window
        self._quantity = quantity

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
    ) -> Signal | None:
        # 교차 여부를 판단하려면 직전 시점과 현재 시점의 SMA가 모두 필요하다.
        if len(candles) < self._long_window + 1:
            return None

        prev_candles = candles[:-1]
        prev_short = calculate_sma(prev_candles, self._short_window)
        prev_long = calculate_sma(prev_candles, self._long_window)
        curr_short = calculate_sma(candles, self._short_window)
        curr_long = calculate_sma(candles, self._long_window)

        if prev_short is None or prev_long is None or curr_short is None or curr_long is None:
            return None

        price = candles[-1].close_price
        metadata = {
            "short_ma": curr_short,
            "long_ma": curr_long,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        if prev_short <= prev_long and curr_short > curr_long:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"골든크로스: 단기MA({self._short_window})={curr_short} "
                    f"> 장기MA({self._long_window})={curr_long}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        if prev_short >= prev_long and curr_short < curr_long:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"데드크로스: 단기MA({self._short_window})={curr_short} "
                    f"< 장기MA({self._long_window})={curr_long}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
