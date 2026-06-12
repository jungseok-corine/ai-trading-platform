from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.trading.pricing.fees import TradingCostCalculator

CALCULATOR = TradingCostCalculator(
    commission_rate=Decimal("0.00015"),
    sell_tax_rate=Decimal("0.0018"),
)


def test_buy_fill_has_commission_but_no_tax() -> None:
    cost = CALCULATOR.calculate(TradeSide.BUY, Decimal("70000"), 10)

    # 70000 * 10 * 0.00015 = 105
    assert cost.commission == Decimal("105")
    assert cost.tax == Decimal("0")
    assert cost.total == Decimal("105")


def test_sell_fill_has_commission_and_tax() -> None:
    cost = CALCULATOR.calculate(TradeSide.SELL, Decimal("70000"), 10)

    # commission = 70000 * 10 * 0.00015 = 105
    # tax        = 70000 * 10 * 0.0018  = 1260
    assert cost.commission == Decimal("105")
    assert cost.tax == Decimal("1260")
    assert cost.total == Decimal("1365")


def test_fees_are_rounded_to_won() -> None:
    # 1 * 3 * 0.00015 = 0.00045 -> round half up -> 0
    cost = CALCULATOR.calculate(TradeSide.BUY, Decimal("1"), 3)
    assert cost.commission == Decimal("0")
    assert cost.tax == Decimal("0")
