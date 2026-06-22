from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.risk import RiskConfig
from app.domain.models.trade import Trade
from app.services.risk_service import RiskService
from app.services.trade_service import TradeService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)
from app.trading.order.schemas import OrderCreateRequest

KST = ZoneInfo("Asia/Seoul")


class FakeBrokerClient(BrokerClient):
    """주문 실행 흐름 테스트용 — place_order 호출 여부/횟수를 기록한다."""

    def __init__(self) -> None:
        self.place_order_calls: list[OrderRequest] = []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        raise NotImplementedError

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("10000000"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self.place_order_calls.append(order)
        return OrderResult(
            broker_order_id="0000000001",
            order_status=OrderStatus.PENDING,
            ordered_at=datetime.now(KST),
        )

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


async def _create_account_with_risk_config(session: AsyncSession, **config_overrides) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()

    defaults = dict(
        account_id=account.id,
        max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"),
        max_open_positions=5,
        max_trades_per_day=10,
        consecutive_loss_limit=3,
        emergency_stop=False,
    )
    defaults.update(config_overrides)
    session.add(RiskConfig(**defaults))
    await session.flush()

    return account


@pytest.fixture
def order_request_factory():
    def _make(account_id: int, **overrides) -> OrderCreateRequest:
        defaults = dict(
            account_id=account_id,
            symbol_code="005930",
            side=TradeSide.BUY,
            quantity=1,
            price=Decimal("70000"),
            reason="test order",
        )
        defaults.update(overrides)
        return OrderCreateRequest(**defaults)

    return _make


async def test_rejected_order_does_not_call_broker(db_session: AsyncSession, order_request_factory) -> None:
    account = await _create_account_with_risk_config(db_session, emergency_stop=True)
    broker = FakeBrokerClient()
    service = TradeService(db_session, broker, RiskService(db_session, broker))

    result = await service.place_order(order_request_factory(account.id))

    assert result.approved is False
    assert result.rule_name == "emergency_stop"
    assert result.trade is None
    assert broker.place_order_calls == []

    trades = (
        (await db_session.execute(select(Trade).where(Trade.account_id == account.id))).scalars().all()
    )
    assert trades == []


async def test_approved_order_calls_broker_and_saves_trade(
    db_session: AsyncSession, order_request_factory
) -> None:
    account = await _create_account_with_risk_config(db_session)
    broker = FakeBrokerClient()
    service = TradeService(db_session, broker, RiskService(db_session, broker))

    request = order_request_factory(account.id)
    result = await service.place_order(request)

    assert result.approved is True
    assert len(broker.place_order_calls) == 1
    placed = broker.place_order_calls[0]
    assert placed.symbol_code == "005930"
    assert placed.side == TradeSide.BUY
    assert placed.quantity == 1
    assert placed.price == Decimal("70000")

    assert result.trade is not None
    assert result.trade.account_id == account.id
    assert result.trade.symbol_code == "005930"
    assert result.trade.side == TradeSide.BUY
    assert result.trade.quantity == 1
    assert result.trade.entry_price == Decimal("70000")
    assert result.trade.broker_order_id == "0000000001"
    assert result.trade.order_status == OrderStatus.PENDING
    assert result.trade.entry_time is not None

    trades = (
        (await db_session.execute(select(Trade).where(Trade.account_id == account.id))).scalars().all()
    )
    assert len(trades) == 1
    assert trades[0].id == result.trade.id


async def test_us_order_routes_to_overseas_broker_and_records_market(
    db_session: AsyncSession, order_request_factory
) -> None:
    account = await _create_account_with_risk_config(db_session)
    kr_broker = FakeBrokerClient()
    us_broker = FakeBrokerClient()
    service = TradeService(
        db_session, kr_broker, RiskService(db_session, kr_broker), overseas_broker=us_broker
    )

    request = order_request_factory(
        account.id, symbol_code="AAPL", price=Decimal("190.50"), market="US", exchange="NAS"
    )
    result = await service.place_order(request)

    assert result.approved is True
    # 미국 주문은 해외 브로커로만 라우팅된다(국내 브로커는 호출되지 않음).
    assert len(us_broker.place_order_calls) == 1
    assert kr_broker.place_order_calls == []
    placed = us_broker.place_order_calls[0]
    assert placed.exchange == "NAS"
    # 미국 가격은 센트 단위로 보존된다(KR 정수 호가단위로 깎이지 않음).
    assert placed.price == Decimal("190.50")
    assert result.trade is not None
    assert result.trade.market == "US"
    assert result.trade.entry_price == Decimal("190.50")


async def test_us_order_without_overseas_broker_raises(
    db_session: AsyncSession, order_request_factory
) -> None:
    account = await _create_account_with_risk_config(db_session)
    kr_broker = FakeBrokerClient()
    service = TradeService(db_session, kr_broker, RiskService(db_session, kr_broker))

    with pytest.raises(RuntimeError):
        await service.place_order(
            order_request_factory(account.id, symbol_code="AAPL", market="US", exchange="NAS")
        )


async def test_kr_order_defaults_market_kr(
    db_session: AsyncSession, order_request_factory
) -> None:
    account = await _create_account_with_risk_config(db_session)
    broker = FakeBrokerClient()
    service = TradeService(db_session, broker, RiskService(db_session, broker))

    result = await service.place_order(order_request_factory(account.id))

    assert result.trade is not None
    assert result.trade.market == "KR"


async def test_get_and_list_trades(db_session: AsyncSession, order_request_factory) -> None:
    account = await _create_account_with_risk_config(db_session)
    broker = FakeBrokerClient()
    service = TradeService(db_session, broker, RiskService(db_session, broker))

    result = await service.place_order(order_request_factory(account.id))
    assert result.trade is not None

    fetched = await service.get_trade(result.trade.id)
    assert fetched is not None
    assert fetched.id == result.trade.id

    trades = await service.list_trades(account_id=account.id, limit=100, offset=0)
    assert len(trades) == 1
    assert trades[0].id == result.trade.id


async def test_list_trades_orders_by_created_at_desc(db_session: AsyncSession) -> None:
    account = await _create_account_with_risk_config(db_session)
    broker = FakeBrokerClient()
    service = TradeService(db_session, broker, RiskService(db_session, broker))

    older = Trade(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        order_status=OrderStatus.PENDING,
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=KST),
    )
    newer = Trade(
        account_id=account.id,
        symbol_code="000660",
        side=TradeSide.SELL,
        quantity=2,
        order_status=OrderStatus.PENDING,
        created_at=datetime(2026, 6, 11, 9, 0, tzinfo=KST),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    trades_no_account = await service.list_trades(account_id=None, limit=100, offset=0)
    assert [t.id for t in trades_no_account] == [newer.id, older.id]

    trades_for_account = await service.list_trades(account_id=account.id, limit=100, offset=0)
    assert [t.id for t in trades_for_account] == [newer.id, older.id]
