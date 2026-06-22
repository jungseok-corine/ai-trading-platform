from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.strategy.base import Signal


@dataclass
class RiskCheckResult:
    approved: bool
    rule_name: str | None = None
    reason: str | None = None


class RiskRule(ABC):
    name: str

    @abstractmethod
    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult: ...


class EmergencyStopRule(RiskRule):
    name = "emergency_stop"

    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        if config.emergency_stop:
            return RiskCheckResult(False, self.name, "비상 정지 활성화 상태")
        return RiskCheckResult(approved=True)


class MaxDailyLossRule(RiskRule):
    name = "max_daily_loss"

    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        if context.today_realized_pnl <= -config.max_daily_loss_amount:
            return RiskCheckResult(
                False, self.name, f"당일 손실 한도 초과: {context.today_realized_pnl}"
            )
        return RiskCheckResult(approved=True)


class MaxPositionSizeRule(RiskRule):
    name = "max_position_size"

    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        order_amount = signal.price * signal.quantity
        # US 주문(USD)은 KRW 한도와 비교하기 위해 환율로 환산한다.
        if signal.market == "US":
            order_amount = order_amount * context.usd_krw_rate
        if order_amount > config.max_position_size:
            return RiskCheckResult(
                False,
                self.name,
                f"주문 금액 한도 초과: {order_amount} > {config.max_position_size}",
            )
        return RiskCheckResult(approved=True)


class MaxOpenPositionsRule(RiskRule):
    name = "max_open_positions"

    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        is_new_position = signal.symbol_code not in context.current_position_value
        if signal.side == TradeSide.BUY and is_new_position:
            if context.open_positions_count >= config.max_open_positions:
                return RiskCheckResult(
                    False,
                    self.name,
                    f"보유 종목 수 한도 초과: {context.open_positions_count} >= {config.max_open_positions}",
                )
        return RiskCheckResult(approved=True)


class MaxTradesPerDayRule(RiskRule):
    name = "max_trades_per_day"

    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        if context.today_trade_count >= config.max_trades_per_day:
            return RiskCheckResult(
                False,
                self.name,
                f"당일 거래 횟수 한도 초과: {context.today_trade_count} >= {config.max_trades_per_day}",
            )
        return RiskCheckResult(approved=True)


class ConsecutiveLossLimitRule(RiskRule):
    name = "consecutive_loss_limit"

    def check(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        if context.consecutive_losses >= config.consecutive_loss_limit:
            return RiskCheckResult(
                False,
                self.name,
                f"연속 손실 횟수 한도 초과: {context.consecutive_losses} >= {config.consecutive_loss_limit}",
            )
        return RiskCheckResult(approved=True)


# emergency_stop을 가장 먼저 평가해 활성화 시 다른 룰 평가 없이 즉시 거부되도록 한다.
DEFAULT_RULES: list[RiskRule] = [
    EmergencyStopRule(),
    MaxDailyLossRule(),
    MaxPositionSizeRule(),
    MaxOpenPositionsRule(),
    MaxTradesPerDayRule(),
    ConsecutiveLossLimitRule(),
]
