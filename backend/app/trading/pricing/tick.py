from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from app.domain.models.enums import TradeSide

# KRX(코스피/코스닥) 호가단위 표 (2023-01-25 개편 이후 코스피/코스닥 공통 기준).
# (가격이 threshold 미만일 때 적용되는 호가단위)
_TICK_TABLE: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("2000"), Decimal("1")),
    (Decimal("5000"), Decimal("5")),
    (Decimal("20000"), Decimal("10")),
    (Decimal("50000"), Decimal("50")),
    (Decimal("200000"), Decimal("100")),
    (Decimal("500000"), Decimal("500")),
)
# 500,000원 이상 구간의 호가단위
_MAX_TICK = Decimal("1000")


def get_tick_size(price: Decimal) -> Decimal:
    """주어진 가격대에 적용되는 KRX 호가단위(원)를 반환한다.

    price < 0이면 ValueError. price == 0은 1원 호가단위를 반환한다(호출자가
    별도로 처리).
    """
    if price < 0:
        raise ValueError("price must be non-negative")
    for threshold, tick in _TICK_TABLE:
        if price < threshold:
            return tick
    return _MAX_TICK


def round_price_to_tick(price: Decimal, side: TradeSide) -> Decimal:
    """주문 가격을 KRX 호가단위에 맞는 정수 가격으로 보정한다.

    정책 (MVP, 보수적):
    - BUY: 호가단위의 배수로 내림(floor) -> Signal이 의도한 가격보다 비싸게 매수 주문을 내지 않는다.
    - SELL: 호가단위의 배수로 올림(ceil) -> Signal이 의도한 가격보다 싸게 매도 주문을 내지 않는다.

    두 경우 모두 결과는 1원 이상의 호가단위 배수(정수)이다.
    """
    if price <= 0:
        raise ValueError("price must be positive")

    tick = get_tick_size(price)
    units = price / tick
    rounding = ROUND_FLOOR if side == TradeSide.BUY else ROUND_CEILING
    rounded_units = units.to_integral_value(rounding=rounding)
    if rounded_units < 1:
        rounded_units = Decimal("1")

    return (rounded_units * tick).quantize(Decimal("1"))


# 미국 주식 최소 호가단위: $0.01 (1주당 1센트, ≥$1.00 종목 기준).
_US_TICK = Decimal("0.01")


def round_us_price_to_cent(price: Decimal, side: TradeSide) -> Decimal:
    """미국 주식 주문 가격을 1센트($0.01) 단위로 보정한다.

    KR 호가단위(정수)와 달리 미국은 센트 단위이므로 소수점을 보존한다.
    정책은 KR과 동일하게 보수적이다: BUY는 내림(floor), SELL은 올림(ceil).
    """
    if price <= 0:
        raise ValueError("price must be positive")

    units = price / _US_TICK
    rounding = ROUND_FLOOR if side == TradeSide.BUY else ROUND_CEILING
    rounded_units = units.to_integral_value(rounding=rounding)
    if rounded_units < 1:
        rounded_units = Decimal("1")

    return (rounded_units * _US_TICK).quantize(_US_TICK)
