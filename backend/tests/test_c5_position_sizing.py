"""C-5.18: 유동적 주문 수량(포지션 사이징) — fixed/cash_amount/cash_pct."""
from decimal import Decimal

import pydantic
import pytest

from app.trading.pricing.sizing import compute_order_quantity
from app.trading.strategy.schemas import StrategyVersionParameters


def test_fixed_mode() -> None:
    assert compute_order_quantity(
        mode="fixed", fixed_quantity=7, price=Decimal("70000")
    ) == 7


def test_cash_amount_mode() -> None:
    # 1,000,000원 / 70,000원 = 14주(내림)
    assert compute_order_quantity(
        mode="cash_amount", fixed_quantity=1, price=Decimal("70000"),
        cash_amount=1_000_000,
    ) == 14


def test_cash_amount_budget_below_price_returns_zero() -> None:
    # 50,000원 예산 < 70,000원 1주 → 0 (호출자가 건너뜀)
    assert compute_order_quantity(
        mode="cash_amount", fixed_quantity=1, price=Decimal("70000"),
        cash_amount=50_000,
    ) == 0


def test_cash_pct_mode() -> None:
    # 가용현금 10,000,000원의 20% = 2,000,000 / 200,000 = 10주
    assert compute_order_quantity(
        mode="cash_pct", fixed_quantity=1, price=Decimal("200000"),
        cash_pct=20, available_cash=Decimal("10000000"),
    ) == 10


def test_cash_pct_without_balance_falls_back_to_fixed() -> None:
    assert compute_order_quantity(
        mode="cash_pct", fixed_quantity=3, price=Decimal("200000"),
        cash_pct=20, available_cash=None,
    ) == 3


def test_invalid_price_returns_zero() -> None:
    assert compute_order_quantity(
        mode="cash_amount", fixed_quantity=1, price=None, cash_amount=1000
    ) == 0


# --------------------------------------------------------------------------- #
# 스키마 검증
# --------------------------------------------------------------------------- #


def test_schema_accepts_valid_sizing() -> None:
    StrategyVersionParameters(
        strategy_type="rsi_reversion", symbol_code="005930",
        quantity_mode="cash_amount", cash_amount=1_000_000,
    )
    StrategyVersionParameters(
        strategy_type="rsi_reversion", symbol_code="005930",
        quantity_mode="cash_pct", cash_pct=20,
    )


def test_schema_rejects_bad_sizing() -> None:
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(
            strategy_type="rsi_reversion", symbol_code="005930",
            quantity_mode="cash_amount", cash_amount=0,  # 금액 없음
        )
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(
            strategy_type="rsi_reversion", symbol_code="005930",
            quantity_mode="cash_pct", cash_pct=0,  # % 없음
        )
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(
            strategy_type="rsi_reversion", symbol_code="005930",
            quantity_mode="bogus",
        )
