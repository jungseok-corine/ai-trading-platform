from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, PositionEventType, TradeSide
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.services.position_service import PositionService


async def _create_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


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
