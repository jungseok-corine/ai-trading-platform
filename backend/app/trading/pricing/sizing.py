"""주문 수량(포지션 사이징) 계산.

자동매매에서 고정 수량 대신 현금 기준으로 수량을 유동적으로 정할 수 있게 한다.
- fixed: 고정 주식 수.
- cash_amount: 1회 거래에 투입할 금액(통화) → floor(금액 / 가격).
- cash_pct: 가용 현금의 % → floor((현금 × %/100) / 가격).
순수 계산만 한다(외부 의존 없음).
"""
from decimal import Decimal

VALID_QUANTITY_MODES = frozenset({"fixed", "cash_amount", "cash_pct"})


def compute_order_quantity(
    *,
    mode: str,
    fixed_quantity: int,
    price: Decimal | None,
    cash_amount: float | Decimal | None = None,
    cash_pct: float | Decimal | None = None,
    available_cash: Decimal | None = None,
) -> int:
    """모드에 따라 주문 수량을 계산한다.

    cash_* 모드에서 예산이 1주 가격에 못 미치면 0을 반환한다(호출자가 주문을 건너뛴다).
    가격이 없거나 0 이하이면 0.
    """
    if mode == "fixed":
        return int(fixed_quantity)
    if price is None or price <= 0:
        return 0
    if mode == "cash_amount" and cash_amount:
        return int(Decimal(str(cash_amount)) / price)
    if mode == "cash_pct" and cash_pct and available_cash is not None:
        budget = available_cash * Decimal(str(cash_pct)) / Decimal("100")
        return int(budget / price)
    # 정보 부족(예: cash_pct인데 잔고 모름) → 고정 수량으로 폴백
    return int(fixed_quantity)
