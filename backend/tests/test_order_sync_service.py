from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.services.order_sync_service import OrderSyncService
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
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

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

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
    assert result.matched == 1
    assert result.unmatched == 0
    assert result.unmatched_order_ids == []
    assert result.errors == []

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.FILLED
    assert trade.entry_price == Decimal("69900")
    assert trade.entry_time == recorded_at
    assert trade.slippage == Decimal("-100")
    assert trade.partial_fill == {"odno": "0000000001", "tot_ccld_qty": "10"}


async def test_order_id_matching_ignores_leading_zero_padding_differences(db_session: AsyncSession) -> None:
    """trades.broker_order_id와 KIS 체결조회 응답의 odno가 0 padding이 달라도 매칭되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, side=TradeSide.BUY, broker_order_id="1")

    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000001",
                total_quantity=10,
                filled_quantity=10,
                filled_price=Decimal("69900"),
                cancelled=False,
                raw={"odno": "0000000001", "tot_ccld_qty": "10"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.matched == 1
    assert result.unmatched == 0

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.FILLED


async def test_unmatched_order_is_reported(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    await _create_trade(db_session, account.id, broker_order_id="9999999999")

    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000001",
                total_quantity=10,
                filled_quantity=10,
                filled_price=Decimal("69900"),
                cancelled=False,
                raw={"odno": "0000000001", "tot_ccld_qty": "10"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.checked == 1
    assert result.matched == 0
    assert result.unmatched == 1
    assert result.unmatched_order_ids == ["9999999999"]


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
    # gross pnl = (71000 - 70000) * 10 = 10000
    # commission = round(71000 * 10 * 0.00015) = round(106.5) = 107
    # tax        = round(71000 * 10 * 0.0018)  = 1278
    # net pnl    = 10000 - 107 - 1278 = 8615
    assert trade.commission == Decimal("107")
    assert trade.tax == Decimal("1278")
    assert trade.pnl_amount == Decimal("8615")
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


async def test_buy_fill_applies_to_position(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, side=TradeSide.BUY)

    broker = FakeBrokerClient(
        executions=[
            OrderExecution(
                broker_order_id="0000000001",
                total_quantity=10,
                filled_quantity=10,
                filled_price=Decimal("69900"),
                cancelled=False,
                raw={"odno": "0000000001", "tot_ccld_qty": "10"},
            )
        ]
    )

    result = await OrderSyncService(db_session, broker).sync_pending_orders()
    assert result.errors == []

    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 10

    position = await PositionRepository(db_session).get_by_account_symbol(account.id, "005930")
    assert position is not None
    assert position.quantity == 10
    # commission = round(69900 * 10 * 0.00015) = round(104.85) = 105
    # cost_per_share = 69900 + 105/10 = 69910.5
    assert position.avg_entry_price == Decimal("69910.5")

    await db_session.refresh(trade)
    assert trade.commission == Decimal("105")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    assert len(events) == 1
    assert events[0].trade_id == trade.id
    assert events[0].quantity_delta == 10


async def test_duplicate_sync_does_not_double_apply_position(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, side=TradeSide.BUY)

    execution = OrderExecution(
        broker_order_id="0000000001",
        total_quantity=10,
        filled_quantity=10,
        filled_price=Decimal("69900"),
        cancelled=False,
        raw={"odno": "0000000001", "tot_ccld_qty": "10"},
    )
    broker = FakeBrokerClient(executions=[execution])

    service = OrderSyncService(db_session, broker)
    await service.sync_pending_orders()

    await db_session.refresh(trade)
    # 첫 동기화 후 trade는 FILLED이지만, list_pending_or_partial은 더 이상 반환하지 않으므로
    # 동일 trade를 다시 직접 동기화 대상으로 만들어 중복 호출을 시뮬레이션한다.
    trade.order_status = OrderStatus.PARTIAL
    await db_session.flush()

    await service.sync_pending_orders()

    position = await PositionRepository(db_session).get_by_account_symbol(account.id, "005930")
    assert position is not None
    assert position.quantity == 10
    # commission = round(69900 * 10 * 0.00015) = round(104.85) = 105
    # cost_per_share = 69900 + 105/10 = 69910.5
    assert position.avg_entry_price == Decimal("69910.5")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    assert len(events) == 1


async def test_only_new_partial_increment_is_applied(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, side=TradeSide.BUY)

    service = OrderSyncService(
        db_session,
        FakeBrokerClient(
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
        ),
    )
    await service.sync_pending_orders()

    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 4

    service2 = OrderSyncService(
        db_session,
        FakeBrokerClient(
            executions=[
                OrderExecution(
                    broker_order_id="0000000001",
                    total_quantity=10,
                    filled_quantity=10,
                    filled_price=Decimal("70500"),
                    cancelled=False,
                    raw={"odno": "0000000001", "tot_ccld_qty": "10"},
                )
            ]
        ),
    )
    await service2.sync_pending_orders()

    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 10

    position = await PositionRepository(db_session).get_by_account_symbol(account.id, "005930")
    assert position is not None
    assert position.quantity == 10
    # fill1: commission = round(70000*4*0.00015) = 42 -> cost_per_share = 70000 + 42/4 = 70010.5
    # fill2: commission = round(70500*6*0.00015) = 63 -> cost_per_share = 70500 + 63/6 = 70510.5
    # avg = (70010.5*4 + 70510.5*6) / 10
    assert position.avg_entry_price == Decimal("70310.5")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    assert len(events) == 2
    assert {e.quantity_delta for e in events} == {4, 6}


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


async def test_rate_limit_error_is_classified(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    await _create_trade(db_session, account.id)

    broker = FakeBrokerClient(error=KISAPIError("EGW00201", "초당 거래건수를 초과하였습니다."))
    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.checked == 1
    assert result.updated == 0
    assert len(result.errors) == 1
    assert result.error_category == "rate_limit_or_repeated_call"


async def test_no_pending_orders_skips_daily_executions_call(db_session: AsyncSession) -> None:
    await _create_account(db_session)

    class FailingIfCalledBrokerClient(FakeBrokerClient):
        async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
            raise AssertionError("get_daily_executions should not be called when there are no pending orders")

    result = await OrderSyncService(db_session, FailingIfCalledBrokerClient()).sync_pending_orders()

    assert result.checked == 0
    assert result.updated == 0
    assert result.skipped_reason == "no_pending_orders"
