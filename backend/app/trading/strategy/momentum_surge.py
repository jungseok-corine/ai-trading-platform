from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import calculate_volume_ratio, candle_timestamp

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext


class MomentumSurgeStrategy(Strategy):
    """급등 모멘텀 진입 전략 (급등 초입에 올라타기).

    단기간 강한 상승 + 거래량 급증이 동시에 나타나는 '급등 시작' 구간을 포착한다.
    미국 급등주(단기 수십~수백% 변동)처럼 폭발적으로 움직이는 종목을 노린다.

    - BUY: 최근 surge_lookback봉 수익률 >= surge_threshold_pct(%) 이고
           거래량비율 >= volume_multiplier (거래량 급증으로 확인).
    - SELL: 최근 surge_lookback봉 수익률 <= -exit_drop_pct(%) (모멘텀 반전/소멸).
    - 그 외: None.

    상태가 없는 신호 생성기다(보유/진입가 추적 없음). 청산은 SELL 신호로 표현한다.
    급등은 변동이 크므로 거래량 확인을 항상 요구한다(noise 억제).
    """

    name = "momentum_surge"

    def __init__(
        self,
        surge_lookback: int = 5,
        surge_threshold_pct: Decimal = Decimal("5"),
        exit_drop_pct: Decimal = Decimal("3"),
        volume_window: int = 20,
        volume_multiplier: Decimal = Decimal("2"),
        quantity: int = 1,
    ) -> None:
        self._surge_lookback = surge_lookback
        self._surge_threshold_pct = surge_threshold_pct
        self._exit_drop_pct = exit_drop_pct
        self._volume_window = volume_window
        self._volume_multiplier = volume_multiplier
        self._quantity = quantity

    @classmethod
    def from_params(cls, params: dict) -> "MomentumSurgeStrategy":
        return cls(
            surge_lookback=params.get("surge_lookback", 5),
            surge_threshold_pct=Decimal(str(params.get("surge_threshold_pct", "5"))),
            exit_drop_pct=Decimal(str(params.get("exit_drop_pct", "3"))),
            volume_window=params.get("volume_window", 20),
            volume_multiplier=Decimal(str(params.get("volume_multiplier", "2"))),
            quantity=params.get("quantity", 1),
        )

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: StrategyContext | None = None,
    ) -> Signal | None:
        need = max(self._surge_lookback + 1, self._volume_window + 1)
        if len(candles) < need:
            return None

        ref_close = candles[-1 - self._surge_lookback].close_price
        close = candles[-1].close_price
        if ref_close <= 0:
            return None

        ret_pct = (close - ref_close) / ref_close * Decimal("100")
        volume_ratio = calculate_volume_ratio(candles, self._volume_window)

        metadata = {
            "close": close,
            "return_pct": ret_pct,
            "volume_ratio": volume_ratio,
            "candle_ts": candle_timestamp(candles[-1]),
        }

        # BUY: 급등 시작 — 단기 강한 상승 + 거래량 급증 확인
        if ret_pct >= self._surge_threshold_pct and (
            volume_ratio is not None and volume_ratio >= self._volume_multiplier
        ):
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=close,
                reason=(
                    f"급등 진입: {self._surge_lookback}봉 수익률={ret_pct:.1f}% "
                    f">= {self._surge_threshold_pct}%, 거래량비율={volume_ratio:.1f}x"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 모멘텀 반전/소멸
        if ret_pct <= -self._exit_drop_pct:
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=close,
                reason=(
                    f"모멘텀 소멸: {self._surge_lookback}봉 수익률={ret_pct:.1f}% "
                    f"<= -{self._exit_drop_pct}%"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        return None
