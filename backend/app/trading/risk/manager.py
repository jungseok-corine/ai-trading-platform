from app.domain.models.risk import RiskConfig
from app.trading.risk.context import RiskContext
from app.trading.risk.rules import RiskCheckResult, RiskRule
from app.trading.strategy.base import Signal


class RiskManager:
    """주어진 RiskContext/RiskConfig로 Signal을 판정한다 (DB 접근 없음)."""

    def __init__(self, rules: list[RiskRule]) -> None:
        self._rules = rules

    def validate(self, signal: Signal, config: RiskConfig, context: RiskContext) -> RiskCheckResult:
        for rule in self._rules:
            result = rule.check(signal, config, context)
            if not result.approved:
                return result
        return RiskCheckResult(approved=True)
