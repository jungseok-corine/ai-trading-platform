from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import (
    calculate_sma,
    calculate_volume_ratio,
    calculate_volume_sma,
    candle_timestamp,
)

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext

_VALID_FLOW_MODES = frozenset(
    {"foreign_or_institution", "foreign_and_institution", "smart_money_vs_retail"}
)


def _check_flow_condition(flow, flow_mode: str) -> bool:
    """investor_flow 행에 대해 flow_mode 조건을 평가한다.

    사용 컬럼 (InvestorFlow):
      foreign_net_buy_quantity    — 외국인 순매수 수량 (음수=순매도)
      institution_net_buy_quantity — 기관계 순매수 수량
      individual_net_buy_quantity  — 개인 순매수 수량

    flow_mode:
      foreign_or_institution   : 외국인 > 0 OR 기관 > 0
      foreign_and_institution  : 외국인 > 0 AND 기관 > 0
      smart_money_vs_retail    : (외국인 > 0 OR 기관 > 0) AND 개인 < 0
        ※ 연구용 휴리스틱이며 실전 수익을 보장하지 않음
    """
    fq = flow.foreign_net_buy_quantity or 0
    iq = flow.institution_net_buy_quantity or 0
    pq = flow.individual_net_buy_quantity or 0

    if flow_mode == "foreign_or_institution":
        return fq > 0 or iq > 0
    if flow_mode == "foreign_and_institution":
        return fq > 0 and iq > 0
    if flow_mode == "smart_money_vs_retail":
        return (fq > 0 or iq > 0) and pq < 0
    return False


class FlowConfirmedVolumeMACrossStrategy(Strategy):
    """수급(investor flow) 확인을 추가한 MA cross 전략.

    BUY 조건 (모두 충족):
      1. 골든크로스 (단기SMA > 장기SMA, 이전에는 단기 <= 장기)
      2. volume_ratio >= volume_multiplier
      3. investor flow 조건 (flow_mode에 따름)

    SELL 조건:
      - 데드크로스 (flow 조건 없음, 기존 MA cross와 동일)

    수급 데이터는 일별 확정 데이터이며 실시간 매수세/매도세가 아닙니다.
    look-ahead 방지: SignalService가 캔들 당일 이전 trade_date 데이터만 context에 포함한다.
    """

    name = "flow_confirmed_volume_ma_cross"

    def __init__(
        self,
        short_window: int = 5,
        long_window: int = 20,
        volume_window: int = 20,
        volume_multiplier: Decimal = Decimal("1.5"),
        quantity: int = 1,
        flow_lookback_days: int = 5,
        max_flow_age_days: int = 5,
        flow_mode: str = "foreign_or_institution",
        require_flow_data: bool = True,
    ) -> None:
        self._short_window = short_window
        self._long_window = long_window
        self._volume_window = volume_window
        self._volume_multiplier = volume_multiplier
        self._quantity = quantity
        self._flow_lookback_days = flow_lookback_days
        self._max_flow_age_days = max_flow_age_days
        self._flow_mode = flow_mode
        self._require_flow_data = require_flow_data

    @classmethod
    def from_params(cls, params: dict) -> "FlowConfirmedVolumeMACrossStrategy":
        return cls(
            short_window=params.get("short_window", 5),
            long_window=params.get("long_window", 20),
            volume_window=params.get("volume_window", 20),
            volume_multiplier=Decimal(str(params.get("volume_multiplier", "1.5"))),
            quantity=params.get("quantity", 1),
            flow_lookback_days=params.get("flow_lookback_days", 5),
            max_flow_age_days=params.get("max_flow_age_days", 5),
            flow_mode=params.get("flow_mode", "foreign_or_institution"),
            require_flow_data=bool(params.get("require_flow_data", True)),
        )

    def _evaluate_flow(self, context: StrategyContext | None) -> tuple[bool, dict]:
        """수급 조건을 평가하고 (flow_confirmed, flow_meta) 를 반환한다.

        flow_meta는 indicators JSONB에 저장될 메타데이터다.
        """
        flow_meta: dict = {
            "flow_mode": self._flow_mode,
            "flow_data_available": False,
            "flow_confirmed": False,
            "flow_trade_date": None,
            "flow_data_staleness_days": None,
            "investor_foreign_net_buy_quantity": None,
            "investor_institution_net_buy_quantity": None,
            "investor_individual_net_buy_quantity": None,
            "investor_foreign_net_buy_amount": None,
            "investor_institution_net_buy_amount": None,
            "investor_individual_net_buy_amount": None,
            "investor_flow_amount_unit": "million_krw",
        }

        if context is None or not context.flow_data_available:
            flow_confirmed = not self._require_flow_data
            flow_meta["flow_confirmed"] = flow_confirmed
            if context is not None:
                flow_meta["flow_data_staleness_days"] = context.flow_data_staleness_days
            return flow_confirmed, flow_meta

        # stale 체크
        staleness = context.flow_data_staleness_days
        if staleness is not None and staleness > self._max_flow_age_days:
            flow_confirmed = not self._require_flow_data
            flow_meta["flow_data_staleness_days"] = staleness
            flow_meta["flow_data_available"] = False
            flow_meta["flow_confirmed"] = flow_confirmed
            return flow_confirmed, flow_meta

        flow = context.latest_investor_flow
        if flow is None:
            flow_confirmed = not self._require_flow_data
            flow_meta["flow_confirmed"] = flow_confirmed
            return flow_confirmed, flow_meta

        flow_confirmed = _check_flow_condition(flow, self._flow_mode)

        fa = flow.foreign_net_buy_amount
        ia = flow.institution_net_buy_amount
        pa = flow.individual_net_buy_amount

        flow_meta.update({
            "flow_data_available": True,
            "flow_confirmed": flow_confirmed,
            "flow_trade_date": flow.trade_date.isoformat(),
            "flow_data_staleness_days": staleness,
            "investor_foreign_net_buy_quantity": flow.foreign_net_buy_quantity,
            "investor_institution_net_buy_quantity": flow.institution_net_buy_quantity,
            "investor_individual_net_buy_quantity": flow.individual_net_buy_quantity,
            "investor_foreign_net_buy_amount": str(fa) if fa is not None else None,
            "investor_institution_net_buy_amount": str(ia) if ia is not None else None,
            "investor_individual_net_buy_amount": str(pa) if pa is not None else None,
        })
        return flow_confirmed, flow_meta

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: StrategyContext | None = None,
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

        flow_confirmed, flow_meta = self._evaluate_flow(context)

        price = candles[-1].close_price
        metadata: dict = {
            "short_sma": curr_short,
            "long_sma": curr_long,
            "current_volume": current_volume,
            "volume_sma": vol_sma,
            "volume_ratio": volume_ratio,
            "volume_confirmed": volume_confirmed,
            "candle_ts": candle_timestamp(candles[-1]),
        }
        metadata.update(flow_meta)

        # BUY: 골든크로스 + 거래량 확인 + 수급 확인
        if prev_short <= prev_long and curr_short > curr_long:
            if not volume_confirmed:
                return None
            if not flow_confirmed:
                return None
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=price,
                reason=(
                    f"수급확인골든크로스: 단기SMA({self._short_window})={curr_short:.2f} "
                    f"> 장기SMA({self._long_window})={curr_long:.2f}, "
                    f"volume_ratio={volume_ratio:.2f}>={self._volume_multiplier}, "
                    f"flow_mode={self._flow_mode}"
                ),
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )

        # SELL: 데드크로스 (수급 조건 없음)
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
