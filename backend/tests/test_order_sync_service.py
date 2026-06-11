from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.services.order_sync_service import OrderSyncService
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.schemas import (
    AccountBalance,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

KST = ZoneInfo("Asia/Seoul")


class FakeBrokerClient(BrokerClient):
    """주문체결조회 흐름 테스트용 — 고정된 OrderExecution 목록을 반환한다."""

    def __init__(
        self,
        executions: list[OrderExecution] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._executions = executions or []
        self._error = error

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

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        if self._error is not None:
            raise self._error
        return self._executions


async def _create_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


async def _create_trade(session: AsyncSession, account_id: int, **overrides) -> Trade:
    defaults = dict(
        account_id=account_id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        entry_price=Decimal("70000"),
        entry_time=datetime(2026, 6, 11, 9, 0, tzinfo=KST),
        order_status=OrderStatus.PENDING,
        broker_order_id="0000000001",
    )
    defaults.update(overrides)
    trade = Trade(**defaults)
    session.add(trade)
    await session.flush()
    return trade


async def test_trade_without_broker_order_id_is_skipped(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    await _create_trade(db_session, account.id, broker_order_id=None)

    broker = FakeBrokerClient(executions=[])
    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.checked == 0
    assert result.updated == 0
    assert result.errors == []


async def test_buy_order_fully_filled_updates_entry_and_status(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, side=TradeSide.BUY)

    recorded_at = datetime(2026, 6, 11, 9, 5, 0, tzinfo=KST)
    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000001",
                total_quantity=10,
                filled_quantity=10,
                filled_price=Decimal("69900"),
                cancelled=False,
                recorded_at=recorded_at,
                raw={"odno": "0000000001", "tot_ccld_qty": "10"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.checked == 1
    assert result.updated == 1
    assert result.errors == []

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.FILLED
    assert trade.entry_price == Decimal("69900")
    assert trade.entry_time == recorded_at
    assert trade.slippage == Decimal("-100")
    assert trade.partial_fill == {"odno": "0000000001", "tot_ccld_qty": "10"}


async def test_buy_order_partially_filled_keeps_partial_status(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, side=TradeSide.BUY)

    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000001",
                total_quantity=10,
                filled_quantity=4,
                filled_price=Decimal("70000"),
                cancelled=False,
                raw={"odno": "0000000001", "tot_ccld_qty": "4"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.updated == 1
    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.PARTIAL
    assert trade.partial_fill == {"odno": "0000000001", "tot_ccld_qty": "4"}


async def test_sell_order_filled_computes_pnl(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(
        db_session,
        account.id,
        side=TradeSide.SELL,
        entry_price=Decimal("70000"),
        broker_order_id="0000000002",
    )

    recorded_at = datetime(2026, 6, 11, 10, 0, 0, tzinfo=KST)
    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000002",
                total_quantity=10,
                filled_quantity=10,
                filled_price=Decimal("71000"),
                cancelled=False,
                recorded_at=recorded_at,
                raw={"odno": "0000000002", "tot_ccld_qty": "10"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.updated == 1
    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.FILLED
    assert trade.exit_price == Decimal("71000")
    assert trade.exit_time == recorded_at
    assert trade.pnl_amount == Decimal("10000")
    assert trade.pnl_pct.quantize(Decimal("0.0001")) == Decimal("1.4286")


async def test_cancelled_order_updates_status(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id)

    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000001",
                total_quantity=10,
                filled_quantity=0,
                filled_price=None,
                cancelled=True,
                raw={"odno": "0000000001", "cncl_yn": "Y"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.updated == 1
    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.CANCELLED


async def test_no_matching_execution_leaves_trade_untouched(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, broker_order_id="9999999999")

    broker = FakeBrokerClient(executions=[])
    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.checked == 1
    assert result.updated == 0
    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.PENDING


async def test_broker_error_does_not_raise(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id)

    broker = FakeBrokerClient(error=KISAPIError("1", "조회 실패"))
    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.checked == 1
    assert result.updated == 0
    assert len(result.errors) == 1

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.PENDING
