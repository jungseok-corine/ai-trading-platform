"""C-5.7: 미국 체결 동기화 — 시장별 브로커 라우팅 + US 수수료 모델(KR 거래세 미적용)."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.services.order_sync_service import OrderSyncService
from app.trading.broker.schemas import OrderExecution
from app.trading.pricing.fees import TradingCostCalculator

from tests.test_order_sync_service import FakeBrokerClient

KST = ZoneInfo("Asia/Seoul")


def _exec(order_id: str, qty: int, price: str, total: int | None = None) -> OrderExecution:
    return OrderExecution(
        broker_order_id=order_id, total_quantity=total or qty, filled_quantity=qty,
        filled_price=Decimal(price), raw={"odno": order_id},
    )


async def _account(session: AsyncSession) -> Account:
    a = Account(account_type=AccountType.PAPER, broker_account_no="50000000-01")
    session.add(a)
    await session.flush()
    return a


async def _us_trade(session: AsyncSession, account_id: int, **ov) -> Trade:
    d = dict(
        account_id=account_id, symbol_code="AAPL", market="US", side=TradeSide.BUY,
        quantity=2, entry_price=Decimal("190.00"), entry_time=datetime.now(KST),
        order_status=OrderStatus.PENDING, broker_order_id="0030001",
    )
    d.update(ov)
    t = Trade(**d)
    session.add(t)
    await session.flush()
    return t


# --------------------------------------------------------------------------- #
# US 수수료 모델 (단위)
# --------------------------------------------------------------------------- #


def test_us_cost_has_no_kr_tax_and_cent_rounding() -> None:
    settings = get_settings()
    us = TradingCostCalculator.for_market("US", settings)
    kr = TradingCostCalculator.for_market("KR", settings)

    us_sell = us.calculate(TradeSide.SELL, Decimal("200.00"), 2)  # $400
    kr_sell = kr.calculate(TradeSide.SELL, Decimal("200000"), 2)  # ₩400,000

    # US 매도세는 SEC fee 수준(소액) — KR 0.18% 거래세와 자릿수가 다르다.
    assert us_sell.tax < Decimal("0.10")
    assert kr_sell.tax >= Decimal("700")  # 400,000 * 0.0018 = 720
    # US는 센트 단위로 반올림된다.
    assert us_sell.commission == us_sell.commission.quantize(Decimal("0.01"))


# --------------------------------------------------------------------------- #
# 시장별 라우팅
# --------------------------------------------------------------------------- #


async def test_us_trade_synced_via_overseas_broker(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    trade = await _us_trade(db_session, acc.id)
    await db_session.commit()

    kr_broker = FakeBrokerClient([])  # 국내 브로커엔 해당 체결이 없다
    us_broker = FakeBrokerClient([_exec("0030001", 2, "192.00")])

    res = await OrderSyncService(db_session, kr_broker, overseas_broker=us_broker).sync_pending_orders()

    assert res.matched == 1  # US 브로커로 라우팅돼 매칭됨(국내로 갔다면 unmatched였을 것)
    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.FILLED
    assert trade.entry_price == Decimal("192.00")  # BUY 체결가 반영


async def test_us_trade_skipped_without_overseas_broker(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    await _us_trade(db_session, acc.id)
    await db_session.commit()

    # 해외 브로커 미구성 → US 주문은 건너뛰고 에러로 표시(전체 동기화는 죽지 않음)
    res = await OrderSyncService(db_session, FakeBrokerClient([])).sync_pending_orders()
    assert any("US" in e for e in res.errors)
    assert res.matched == 0
