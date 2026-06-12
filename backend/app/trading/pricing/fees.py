from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models.enums import TradeSide

_WON = Decimal("1")


def _round_won(amount: Decimal) -> Decimal:
    """원 단위로 반올림한다 (수수료/세금은 보통 1원 단위로 계산·청구됨)."""
    return amount.quantize(_WON, rounding=ROUND_HALF_UP)


@dataclass
class FillCost:
    """체결 1건에 대해 부과되는 수수료/세금 (원 단위)."""

    commission: Decimal
    tax: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.tax


class TradingCostCalculator:
    """한국 주식 거래 수수료/거래세를 계산한다.

    - commission_rate: 매수/매도 공통 거래 수수료율
    - sell_tax_rate: 매도 시에만 부과되는 증권거래세(+농특세) 합산율

    두 값 모두 app.core.config.Settings에서 가져온 MVP 기본값을 사용하며,
    정확한 수치는 브로커/시장 정책에 따라 달라질 수 있다 (Settings 주석 참고).
    """

    def __init__(self, commission_rate: Decimal, sell_tax_rate: Decimal) -> None:
        self._commission_rate = commission_rate
        self._sell_tax_rate = sell_tax_rate

    def calculate(self, side: TradeSide, price: Decimal, quantity: int) -> FillCost:
        amount = price * quantity
        commission = _round_won(amount * self._commission_rate)
        tax = _round_won(amount * self._sell_tax_rate) if side == TradeSide.SELL else Decimal("0")
        return FillCost(commission=commission, tax=tax)
