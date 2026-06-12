from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, PositionEventType, TradeSide
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.services.position_service import PositionService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


async def _create_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


class FakePriceBrokerClient(BrokerClient):
    """심볼별로 고정된 현재가를 반환하는 시세 조회 테스트용 브로커."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices
        self.requested_symbols: list[str] = []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        self.requested_symbols.append(symbol_code)
        price = self._prices[symbol_code]
        return PriceQuote(
            symbol_code=symbol_code,
            current_price=price,
            change=Decimal("0"),
            change_rate=Decimal("0"),
            open_price=price,
            high_price=price,
            low_price=price,
            volume=0,
        )

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        raise NotImplementedError

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("0"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        return []


async def test_first_buy_fill_creates_position(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        symbol_name="삼성전자",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    assert position.account_id == account.id
    assert position.symbol_code == "005930"
    assert position.symbol_name == "삼성전자"
    assert position.quantity == 10
    assert position.avg_entry_price == Decimal("70000")
    assert position.realized_pnl == Decimal("0")
    assert position.last_price == Decimal("70000")
    assert position.unrealized_pnl == Decimal("0")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == PositionEventType.BUY_FILL
    assert event.quantity_delta == 10
    assert event.before_quantity == 0
    assert event.after_quantity == 10
    assert event.before_avg_entry_price == Decimal("0")
    assert event.after_avg_entry_price == Decimal("70000")
    assert event.realized_pnl_delta is None


async def test_buy_fill_with_commission_increases_avg_entry_price(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
        commission=Decimal("105"),
    )

    # cost_per_share = 70000 + 105/10 = 70010.5
    assert position.avg_entry_price == Decimal("70010.5")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    event = events[0]
    assert event.commission == Decimal("105")
    assert event.tax == Decimal("0")
    assert event.realized_pnl_delta_net is None


async def test_additional_buy_fill_updates_avg_price(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )
    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("72000"),
    )

    assert position.quantity == 20
    # (70000*10 + 72000*10) / 20 = 71000
    assert position.avg_entry_price == Decimal("71000")
    assert position.last_price == Decimal("72000")
    assert position.unrealized_pnl == (Decimal("72000") - Decimal("71000")) * 20

    repo = PositionRepository(db_session)
    stored = await repo.get_by_account_symbol(account.id, "005930")
    assert stored is not None
    assert stored.id == position.id


async def test_partial_sell_fill_decreases_quantity_and_realizes_pnl(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )
    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.SELL,
        quantity=4,
        price=Decimal("75000"),
    )

    assert position.quantity == 6
    # avg_entry_price unchanged while quantity remains
    assert position.avg_entry_price == Decimal("70000")
    # realized pnl = (75000 - 70000) * 4
    assert position.realized_pnl == Decimal("20000")
    assert position.last_price == Decimal("75000")
    assert position.unrealized_pnl == (Decimal("75000") - Decimal("70000")) * 6

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    assert len(events) == 2
    sell_event = events[0]
    assert sell_event.event_type == PositionEventType.SELL_FILL
    assert sell_event.quantity_delta == -4
    assert sell_event.before_quantity == 10
    assert sell_event.after_quantity == 6
    assert sell_event.realized_pnl_delta == Decimal("20000")
    assert sell_event.before_avg_entry_price == Decimal("70000")
    assert sell_event.after_avg_entry_price == Decimal("70000")


async def test_sell_fill_with_commission_and_tax_reduces_realized_pnl_net(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )
    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.SELL,
        quantity=4,
        price=Decimal("75000"),
        commission=Decimal("45"),
        tax=Decimal("540"),
    )

    # gross realized pnl = (75000 - 70000) * 4 = 20000
    # net realized pnl   = 20000 - 45 - 540 = 19415
    assert position.realized_pnl == Decimal("19415")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    sell_event = events[0]
    assert sell_event.realized_pnl_delta == Decimal("20000")
    assert sell_event.realized_pnl_delta_net == Decimal("19415")
    assert sell_event.commission == Decimal("45")
    assert sell_event.tax == Decimal("540")


async def test_full_sell_fill_zeroes_quantity_and_resets_avg_price(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )
    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.SELL,
        quantity=10,
        price=Decimal("75000"),
    )

    assert position.quantity == 0
    assert position.avg_entry_price == Decimal("0")
    assert position.realized_pnl == Decimal("50000")
    assert position.unrealized_pnl == Decimal("0")

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    sell_event = events[0]
    assert sell_event.after_quantity == 0
    assert sell_event.after_avg_entry_price == Decimal("0")


async def test_update_last_price_recomputes_unrealized_pnl(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    position = await service.update_last_price(account.id, "005930", Decimal("80000"))

    assert position is not None
    assert position.last_price == Decimal("80000")
    assert position.unrealized_pnl == (Decimal("80000") - Decimal("70000")) * 10


async def test_update_last_price_for_unknown_position_returns_none(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    service = PositionService(db_session)

    position = await service.update_last_price(account.id, "005930", Decimal("80000"))

    assert position is None


async def test_refresh_all_prices_updates_held_positions_and_skips_zero_quantity(
    db_session: AsyncSession,
) -> None:
    account = await _create_account(db_session)

    # quantity != 0 인 포지션
    no_broker_service = PositionService(db_session)
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    # 완전 매도되어 quantity == 0 인 포지션
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="000660",
        side=TradeSide.BUY,
        quantity=5,
        price=Decimal("100000"),
    )
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="000660",
        side=TradeSide.SELL,
        quantity=5,
        price=Decimal("110000"),
    )

    broker = FakePriceBrokerClient({"005930": Decimal("80000"), "000660": Decimal("999999")})
    service = PositionService(db_session, broker)

    updated = await service.refresh_all_prices(account.id)

    assert [p.symbol_code for p in updated] == ["005930"]
    assert broker.requested_symbols == ["005930"]

    repo = PositionRepository(db_session)
    samsung = await repo.get_by_account_symbol(account.id, "005930")
    assert samsung is not None
    assert samsung.last_price == Decimal("80000")
    assert samsung.unrealized_pnl == (Decimal("80000") - Decimal("70000")) * 10

    closed = await repo.get_by_account_symbol(account.id, "000660")
    assert closed is not None
    assert closed.quantity == 0
    # quantity == 0 포지션은 시세 조회 대상이 아니므로 last_price가 변경되지 않는다
    assert closed.last_price == Decimal("110000")
    assert closed.unrealized_pnl == Decimal("0")
