"""RISK-FIX-1F — entry quantity sizing cap.

BUY 진입 수량을 `max_position_size` 한도 내로 사전에 cap하는 순수 함수.
risk check(`MaxPositionSizeRule`) 직전에 적용되어, 한도를 넘던 BUY가 reject되는 대신 허용
가능한 수량으로 줄어든다. SELL/exit는 현재 long-only 구조에서 risk-reducing action이므로 cap하지 않는다.

이 모듈은 순수 계산만 한다 — DB/broker/KIS/주문 호출 없음.
"""
from decimal import Decimal
from math import floor

from app.domain.models.enums import TradeSide


def cap_buy_quantity_by_position_size(
    *,
    side: TradeSide,
    price: Decimal,
    quantity: int,
    max_position_size: Decimal,
    fx_rate: Decimal = Decimal("1"),
) -> int:
    """BUY 진입 수량을 `price * quantity * fx_rate <= max_position_size`가 되도록 cap한다.

    - BUY가 아니면(SELL 등) 수량을 그대로 반환한다(risk-reducing exit는 cap 대상 아님).
    - `fx_rate`는 US(USD) 주문을 KRW 한도와 비교하기 위한 환율이다(MaxPositionSizeRule과 동일 기준).
      KR 주문은 1.
    - `price`(환산 후)가 0 이하이거나 `max_position_size`가 0 이하이면 cap하지 않고 원래 수량을
      반환한다(보수적 — 잘못된 입력으로 수량을 임의로 0으로 만들지 않는다. 이 경우에도
      `MaxPositionSizeRule`이 방어선으로 남는다).
    - 반환값이 0이면 호출측이 no-trade로 처리해야 한다(주문/Trade 생성 금지).
    """
    if side != TradeSide.BUY:
        return quantity

    effective_price = price * fx_rate
    if effective_price <= 0 or max_position_size <= 0:
        return quantity

    max_allowed_quantity = floor(max_position_size / effective_price)
    return min(quantity, max_allowed_quantity)
