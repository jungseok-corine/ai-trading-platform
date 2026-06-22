from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models.enums import TradeSide

_WON = Decimal("1")
_CENT = Decimal("0.01")


@dataclass
class FillCost:
    """체결 1건에 대해 부과되는 수수료/세금 (해당 시장 통화 단위)."""

    commission: Decimal
    tax: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.tax


class TradingCostCalculator:
    """주식 거래 수수료/세금을 계산한다(시장별 통화/반올림 단위).

    - commission_rate: 매수/매도 공통 거래 수수료율
    - sell_tax_rate: 매도 시에만 부과되는 세금/수수료율(KR 증권거래세, US SEC fee 등)
    - rounding_unit: 금액 반올림 단위(KR=1원, US=0.01달러)

    값은 app.core.config.Settings의 MVP 기본값을 사용하며, 정확한 수치는 브로커/시장
    정책에 따라 달라질 수 있다 (Settings 주석 참고).
    """

    def __init__(
        self,
        commission_rate: Decimal,
        sell_tax_rate: Decimal,
        rounding_unit: Decimal = _WON,
    ) -> None:
        self._commission_rate = commission_rate
        self._sell_tax_rate = sell_tax_rate
        self._rounding_unit = rounding_unit

    def _round(self, amount: Decimal) -> Decimal:
        return amount.quantize(self._rounding_unit, rounding=ROUND_HALF_UP)

    def calculate(self, side: TradeSide, price: Decimal, quantity: int) -> FillCost:
        amount = price * quantity
        commission = self._round(amount * self._commission_rate)
        tax = self._round(amount * self._sell_tax_rate) if side == TradeSide.SELL else Decimal("0")
        return FillCost(commission=commission, tax=tax)

    @classmethod
    def for_market(cls, market: str, settings) -> "TradingCostCalculator":
        """시장 코드(KR/US)에 맞는 수수료 계산기를 만든다.

        US는 KR 증권거래세(0.18%)가 없고 가격이 센트 단위이므로 별도 요율/단위를 쓴다.
        """
        if market == "US":
            return cls(
                commission_rate=settings.us_trading_commission_rate,
                sell_tax_rate=settings.us_trading_sell_fee_rate,
                rounding_unit=_CENT,
            )
        return cls(
            commission_rate=settings.trading_commission_rate,
            sell_tax_rate=settings.trading_sell_tax_rate,
            rounding_unit=_WON,
        )
