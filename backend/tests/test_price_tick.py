from decimal import Decimal

import pytest

from app.domain.models.enums import TradeSide
from app.trading.pricing.tick import get_tick_size, round_price_to_tick


@pytest.mark.parametrize(
    "price, expected_tick",
    [
        (Decimal("1000"), Decimal("1")),
        (Decimal("1999"), Decimal("1")),
        (Decimal("2000"), Decimal("5")),
        (Decimal("4999"), Decimal("5")),
        (Decimal("5000"), Decimal("10")),
        (Decimal("19999"), Decimal("10")),
        (Decimal("20000"), Decimal("50")),
        (Decimal("49999"), Decimal("50")),
        (Decimal("50000"), Decimal("100")),
        (Decimal("199999"), Decimal("100")),
        (Decimal("200000"), Decimal("500")),
        (Decimal("499999"), Decimal("500")),
        (Decimal("500000"), Decimal("1000")),
        (Decimal("1000000"), Decimal("1000")),
    ],
)
def test_get_tick_size(price: Decimal, expected_tick: Decimal) -> None:
    assert get_tick_size(price) == expected_tick


def test_get_tick_size_rejects_negative_price() -> None:
    with pytest.raises(ValueError):
        get_tick_size(Decimal("-1"))


def test_round_price_to_tick_invalid_buy_price_floors_to_valid_tick() -> None:
    # 299833.3333 -> 50만원 미만 구간(20만~50만)의 호가단위는 500원
    # 299833.3333 / 500 = 599.6666... -> floor(599) * 500 = 299500
    price = Decimal("299833.3333")
    adjusted = round_price_to_tick(price, TradeSide.BUY)
    assert adjusted == Decimal("299500")
    assert adjusted % get_tick_size(adjusted) == 0


def test_round_price_to_tick_invalid_sell_price_ceils_to_valid_tick() -> None:
    # 299833.3333 / 500 = 599.6666... -> ceil(600) * 500 = 300000
    price = Decimal("299833.3333")
    adjusted = round_price_to_tick(price, TradeSide.SELL)
    assert adjusted == Decimal("300000")
    assert adjusted % get_tick_size(adjusted) == 0


def test_round_price_to_tick_already_valid_price_is_unchanged() -> None:
    price = Decimal("70000")  # 5만~20만 구간 -> 호가단위 100, 70000은 이미 유효
    assert round_price_to_tick(price, TradeSide.BUY) == price
    assert round_price_to_tick(price, TradeSide.SELL) == price


def test_round_price_to_tick_returns_integer_decimal() -> None:
    price = Decimal("1234.5678")  # 2000원 미만 구간 -> 호가단위 1
    adjusted_buy = round_price_to_tick(price, TradeSide.BUY)
    adjusted_sell = round_price_to_tick(price, TradeSide.SELL)
    assert adjusted_buy == Decimal("1234")
    assert adjusted_sell == Decimal("1235")
    assert adjusted_buy == adjusted_buy.to_integral_value()
    assert adjusted_sell == adjusted_sell.to_integral_value()


def test_round_price_to_tick_rejects_non_positive_price() -> None:
    with pytest.raises(ValueError):
        round_price_to_tick(Decimal("0"), TradeSide.BUY)
