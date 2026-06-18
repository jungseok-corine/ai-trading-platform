from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import (
    calculate_sma,
    calculate_volume_ratio,
    calculate_volume_sma,
    candle_timestamp,
)


class VolumeConfirmedMovingAverageCrossStrategy(Strategy):
    """거래량 확인(volume confirmation)을 더한 MA cross 전략.

    - BUY: 골든크로스 + 현재 거래량 >= volume_sma * volume_multiplier
    - SELL: 데드크로스 (거래량 조건 없음, 기존 MA cross와 동일)
    - 골든크로스 발생 시 거래량 조건 미충족이면 신호 없음(None)
    - 거래량 spike가 방향을 단정하지는 않는다 — 추세 강도 확인 필터로만 사용
    """

    name = "volume_confirmed_ma_cross"

    def __init__(
        self,
        short_window: int = 5,
        long_window: int = 20,
        volume_window: int = 20,
        volume_multiplier: Decimal = Decimal("1.5"),
        quantity: int = 1,
    ) -> None:
        self._short_window = short_window
        self._long_window = long_window
        self._volume_window = volume_window
        self._volume_multiplier = volume_multiplier
        self._quantity = quantity

    @classmethod
    def from_params(cls, params: dict) -> "VolumeConfirmedMovingAverageCrossStrategy":
        return cls(
            short_window=params.get("short_window", 5),
            long_window=params.get("long_window", 20),
            volume_window=params.get("volume_window", 20),
            volume_multiplier=Decimal(str(params.get("volume_multiplier", "1.5"))),
            quantity=params.get("quantity", 1),
        )

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
    ) -> Signal | None:
        min_required = max(self._long_window, self._volume_window) + 1
        if len(candles) < min_required:
            return None

        prev_candles = candles[:-1]
        prev_short = calculate_sma(prev_candles, self._short_window)
        prev_long = calculate_sma(prev_candles, self._long_window)
        curr_short = calculate_sma(candles, self._short_window)
        curr_long = calculate_sma(candles, self._long_window)

        if prev_short is None or prev_long is None or curr_short is None or curr_long is None:
            return None

        vol_sma = calculate_volume_sma(candles, self._volume_window)
        current_volume = candles[-1].volume
        volume_ratio = calculate_volume_ratio(candles, self._volume_window)
        volume_confirmed = (
            volume_ratio is not None and volume_ratio >= self._volume_multiplier
        )

        price = candles[-1].close_price
        metadata = {
            "short_sma": curr_short,
            "long_sma": curr_long,
            "current_volume": current_volume,
            "volume_sma": vol_sma,
            "volume_ratio": volume_ratio,
            "volume_confirmed": volume_confirmed,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        # BUY: 골든크로스 + 거래량 확인 필터
        if prev_short <= prev_long and curr_short > curr_long:
            if not volume_confirmed:
                return None
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"거래량확인골든크로스: 단기SMA({self._short_window})={curr_short:.2f} "
                    f"> 장기SMA({self._long_window})={curr_long:.2f}, "
                    f"volume_ratio={volume_ratio:.2f} >= {self._volume_multiplier}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 데드크로스 (거래량 조건 없음)
        if prev_short >= prev_long and curr_short < curr_long:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"데드크로스: 단기SMA({self._short_window})={curr_short:.2f} "
                    f"< 장기SMA({self._long_window})={curr_long:.2f}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
