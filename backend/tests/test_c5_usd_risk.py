"""C-5.8: USD 리스크 환산 — US 주문(USD) 금액을 KRW 포지션 한도와 비교하도록 환산."""
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.services.risk_service import RiskService
from app.services.trade_service import TradeService
from app.trading.order.schemas import OrderCreateRequest
from app.trading.risk.context import RiskContext
from app.trading.risk.rules import MaxPositionSizeRule
from app.trading.strategy.base import Signal

from tests.test_trade_service import FakeBrokerClient, _create_account_with_risk_config


def _ctx(rate: str = "1350") -> RiskContext:
    return RiskContext(
        account_id=1, account_balance=Decimal("0"), today_realized_pnl=Decimal("0"),
        today_trade_count=0, open_positions_count=0, consecutive_losses=0,
        usd_krw_rate=Decimal(rate),
    )


def _cfg(max_pos: str = "1000000") -> RiskConfig:
    return RiskConfig(
        account_id=1, max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal(max_pos), max_open_positions=5, max_trades_per_day=10,
        consecutive_loss_limit=3, emergency_stop=False,
    )


def _sig(market: str, price: str, qty: int) -> Signal:
    return Signal(
        symbol_code="AAPL" if market == "US" else "005930", side=TradeSide.BUY,
        quantity=qty, price=Decimal(price), reason="t", market=market,
    )


# --------------------------------------------------------------------------- #
# 순수 룰
# --------------------------------------------------------------------------- #


def test_us_order_converted_to_krw_exceeds_limit() -> None:
    # $500 × 10 = $5,000 × 1350 = ₩6,750,000 > 한도 ₩1,000,000 → 거부
    res = MaxPositionSizeRule().check(_sig("US", "500", 10), _cfg("1000000"), _ctx("1350"))
    assert res.approved is False
    assert res.rule_name == "max_position_size"


def test_us_small_order_within_limit() -> None:
    # $50 × 1 = $50 × 1350 = ₩67,500 < ₩1,000,000 → 승인
    res = MaxPositionSizeRule().check(_sig("US", "50", 1), _cfg("1000000"), _ctx("1350"))
    assert res.approved is True


def test_kr_order_not_converted() -> None:
    # 동일 숫자라도 KR이면 환산 없음: ₩5,000 < ₩1,000,000 → 승인
    res = MaxPositionSizeRule().check(_sig("KR", "500", 10), _cfg("1000000"), _ctx("1350"))
    assert res.approved is True


# --------------------------------------------------------------------------- #
# 통합 (TradeService → RiskService)
# --------------------------------------------------------------------------- #


async def test_large_us_order_rejected_by_fx_converted_limit(db_session: AsyncSession) -> None:
    account = await _create_account_with_risk_config(db_session, max_position_size=Decimal("1000000"))
    kr_broker = FakeBrokerClient()
    us_broker = FakeBrokerClient()
    service = TradeService(
        db_session, kr_broker, RiskService(db_session, kr_broker), overseas_broker=us_broker
    )

    # $500 × 10 = $5,000 → 환산 ₩6,750,000 > ₩1,000,000 → 거부, 주문 미실행
    req = OrderCreateRequest(
        account_id=account.id, symbol_code="AAPL", side=TradeSide.BUY,
        quantity=10, price=Decimal("500"), market="US", exchange="NAS",
    )
    result = await service.place_order(req)

    assert result.approved is False
    assert result.rule_name == "max_position_size"
    assert us_broker.place_order_calls == []
