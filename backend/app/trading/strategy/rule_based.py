"""rule_based 전략 — DSL 스펙(rule_spec)을 해석해 신호를 만든다 (C-7.1).

기존 8종 전략과 동일한 Strategy 인터페이스 — 러너·백테스트·제안 파이프라인이
아무 수정 없이 그대로 사용한다. 임의 코드 실행 없음(rule_dsl 어휘만).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.indicators import candle_timestamp
from app.trading.strategy.rule_dsl import (
    RuleEvaluator,
    RuleSpecError,
    required_bars,
    validate_rule_spec,
)

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext


class RuleBasedStrategy(Strategy):
    name = "rule_based"

    @classmethod
    def from_params(cls, params: dict) -> "RuleBasedStrategy":
        spec = params.get("rule_spec")
        validate_rule_spec(spec)  # 잘못된 스펙은 여기서 즉시 실패 (러너가 건너뜀)
        return cls(spec=spec, quantity=int(params.get("quantity", 1)))

    def __init__(self, spec: dict, quantity: int = 1) -> None:
        self._spec = spec
        self._evaluator = RuleEvaluator(spec)
        self._min_bars = required_bars(spec)
        self._quantity = quantity

    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
        context: "StrategyContext | None" = None,
    ) -> Signal | None:
        if len(candles) < self._min_bars:
            return None

        spec_name = self._spec.get("name", "rule_based")
        metadata = {"rule_spec_name": spec_name, "candle_ts": candle_timestamp(candles[-1])}

        # 청산 우선 (리스크 축소 방향) — entry/exit 동시 충족 시 SELL
        if self._evaluator.exit(candles):
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.SELL,
                quantity=self._quantity,
                price=candles[-1].close_price,
                reason=f"[{spec_name}] exit 조건 충족",
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )
        if self._evaluator.entry(candles):
            return Signal(
                symbol_code=symbol_code,
                side=TradeSide.BUY,
                quantity=self._quantity,
                price=candles[-1].close_price,
                reason=f"[{spec_name}] entry 조건 충족",
                strategy_version_id=strategy_version_id,
                metadata=metadata,
            )
        return None


__all__ = ["RuleBasedStrategy", "RuleSpecError"]
