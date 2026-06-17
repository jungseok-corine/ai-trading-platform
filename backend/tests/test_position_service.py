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
    AccountHolding,
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


class FakeHoldingsBrokerClient(BrokerClient):
    """KIS 잔고조회(get_account_positions) 테스트용 — 고정된 보유종목 목록을 반환한다."""

    def __init__(self, holdings: list[AccountHolding]) -> None:
        self._holdings = holdings

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        raise NotImplementedError

    async def get_account_balance(self) -> AccountBalance:
        raise NotImplementedError

    async def get_account_positions(self) -> list[AccountHolding]:
        return self._holdings

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        return []


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

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

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


def _holding(
    symbol_code: str,
    symbol_name: str,
    quantity: int,
    avg_purchase_price: Decimal,
    current_price: Decimal,
) -> AccountHolding:
    evaluation_amount = current_price * quantity
    profit_loss_amount = (current_price - avg_purchase_price) * quantity
    return AccountHolding(
        symbol_code=symbol_code,
        symbol_name=symbol_name,
        quantity=quantity,
        avg_purchase_price=avg_purchase_price,
        current_price=current_price,
        evaluation_amount=evaluation_amount,
        profit_loss_amount=profit_loss_amount,
        profit_loss_rate=Decimal("0"),
    )


async def test_sync_from_broker_creates_position_not_in_db(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    broker = FakeHoldingsBrokerClient(
        [_holding("005930", "삼성전자", 3, Decimal("322916"), Decimal("324500"))]
    )
    service = PositionService(db_session, broker)

    result = await service.sync_from_broker_positions(account.id)

    assert result.created == 1
    assert result.updated == 0
    assert result.zeroed == 0

    repo = PositionRepository(db_session)
    position = await repo.get_by_account_symbol(account.id, "005930")
    assert position is not None
    assert position.symbol_name == "삼성전자"
    assert position.quantity == 3
    assert position.avg_entry_price == Decimal("322916")
    assert position.last_price == Decimal("324500")
    assert position.unrealized_pnl == (Decimal("324500") - Decimal("322916")) * 3
    assert position.realized_pnl == Decimal("0")


async def test_sync_from_broker_corrects_mismatched_existing_position(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)

    # 내부 체결 기록 상으로는 5주를 보유하고 있다고 잘못 알고 있는 상태
    no_broker_service = PositionService(db_session)
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        symbol_name="삼성전자",
        side=TradeSide.BUY,
        quantity=5,
        price=Decimal("300000"),
    )

    # 실제 KIS 잔고는 3주, 평균단가 322916원
    broker = FakeHoldingsBrokerClient(
        [_holding("005930", "삼성전자", 3, Decimal("322916"), Decimal("324500"))]
    )
    service = PositionService(db_session, broker)

    result = await service.sync_from_broker_positions(account.id)

    assert result.created == 0
    assert result.updated == 1
    assert result.zeroed == 0

    repo = PositionRepository(db_session)
    position = await repo.get_by_account_symbol(account.id, "005930")
    assert position is not None
    assert position.quantity == 3
    assert position.avg_entry_price == Decimal("322916")
    assert position.last_price == Decimal("324500")
    assert position.unrealized_pnl == (Decimal("324500") - Decimal("322916")) * 3
    # realized_pnl(내부 체결 기록 기준)은 KIS 잔고 동기화로 변경되지 않는다
    assert position.realized_pnl == Decimal("0")


async def test_sync_from_broker_zeroes_position_not_in_broker_holdings(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)

    no_broker_service = PositionService(db_session)
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="000660",
        symbol_name="SK하이닉스",
        side=TradeSide.BUY,
        quantity=2,
        price=Decimal("100000"),
    )

    # KIS 잔고에는 000660이 없음 (전량 매도되었거나 내부 기록이 잘못된 경우)
    broker = FakeHoldingsBrokerClient([])
    service = PositionService(db_session, broker)

    result = await service.sync_from_broker_positions(account.id)

    assert result.created == 0
    assert result.updated == 0
    assert result.zeroed == 1

    repo = PositionRepository(db_session)
    position = await repo.get_by_account_symbol(account.id, "000660")
    assert position is not None
    assert position.quantity == 0
    assert position.unrealized_pnl == Decimal("0")
    # avg_entry_price/realized_pnl은 과거 체결 이력 참고용으로 유지
    assert position.avg_entry_price == Decimal("100000")


# ── sync_from_broker position_events 테스트 ──────────────────────────────────

async def test_sync_from_broker_create_records_sync_position_event(db_session: AsyncSession) -> None:
    """broker에서 처음 발견된 종목을 positions에 생성할 때 SYNC 이벤트가 기록된다."""
    account = await _create_account(db_session)
    broker = FakeHoldingsBrokerClient(
        [_holding("005930", "삼성전자", 3, Decimal("322916"), Decimal("324500"))]
    )
    service = PositionService(db_session, broker)

    await service.sync_from_broker_positions(account.id)

    repo = PositionRepository(db_session)
    position = await repo.get_by_account_symbol(account.id, "005930")
    assert position is not None

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == PositionEventType.SYNC
    assert event.quantity_delta == 3
    assert event.before_quantity == 0
    assert event.after_quantity == 3
    assert event.before_avg_entry_price == Decimal("0")
    assert event.after_avg_entry_price == Decimal("322916")
    assert event.raw == {"source": "broker_sync"}
    assert event.trade_id is None


async def test_sync_from_broker_update_records_sync_position_event(db_session: AsyncSession) -> None:
    """기존 포지션을 broker 값으로 보정할 때 SYNC 이벤트가 기록된다."""
    account = await _create_account(db_session)

    no_broker_service = PositionService(db_session)
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        symbol_name="삼성전자",
        side=TradeSide.BUY,
        quantity=5,
        price=Decimal("300000"),
    )

    broker = FakeHoldingsBrokerClient(
        [_holding("005930", "삼성전자", 3, Decimal("322916"), Decimal("324500"))]
    )
    service = PositionService(db_session, broker)

    await service.sync_from_broker_positions(account.id)

    repo = PositionRepository(db_session)
    position = await repo.get_by_account_symbol(account.id, "005930")
    assert position is not None

    # apply_fill이 BUY_FILL, sync_from_broker가 SYNC 순으로 기록됨
    events = await PositionEventRepository(db_session).list_by_position(position.id)
    sync_events = [e for e in events if e.event_type == PositionEventType.SYNC]
    assert len(sync_events) == 1
    event = sync_events[0]
    assert event.quantity_delta == 3 - 5  # 5→3, delta=-2
    assert event.before_quantity == 5
    assert event.after_quantity == 3
    assert event.before_avg_entry_price == Decimal("300000")
    assert event.after_avg_entry_price == Decimal("322916")
    assert event.raw == {"source": "broker_sync"}


async def test_sync_from_broker_zero_records_sync_position_event(db_session: AsyncSession) -> None:
    """broker 잔고에 없어서 quantity=0으로 보정할 때 SYNC 이벤트가 기록된다."""
    account = await _create_account(db_session)

    no_broker_service = PositionService(db_session)
    await no_broker_service.apply_fill(
        account_id=account.id,
        symbol_code="000660",
        symbol_name="SK하이닉스",
        side=TradeSide.BUY,
        quantity=2,
        price=Decimal("100000"),
    )

    broker = FakeHoldingsBrokerClient([])
    service = PositionService(db_session, broker)

    await service.sync_from_broker_positions(account.id)

    repo = PositionRepository(db_session)
    position = await repo.get_by_account_symbol(account.id, "000660")
    assert position is not None

    events = await PositionEventRepository(db_session).list_by_position(position.id)
    sync_events = [e for e in events if e.event_type == PositionEventType.SYNC]
    assert len(sync_events) == 1
    event = sync_events[0]
    assert event.quantity_delta == -2
    assert event.before_quantity == 2
    assert event.after_quantity == 0
    assert event.before_avg_entry_price == Decimal("100000")
    assert event.raw == {"source": "broker_sync"}


# ── position_mismatch 진단 테스트 ─────────────────────────────────────────────

async def test_diagnose_position_mismatch_no_mismatch(db_session: AsyncSession) -> None:
    """apply_fill로만 변경된 포지션은 불일치가 없다."""
    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    mismatches = await service.diagnose_position_mismatch(account.id)
    assert mismatches == []


async def test_diagnose_position_mismatch_detects_direct_modification(db_session: AsyncSession) -> None:
    """position_events 없이 positions.quantity가 직접 변경된 경우 불일치가 탐지된다."""
    from app.domain.repositories.position import PositionRepository as _PR

    account = await _create_account(db_session)
    service = PositionService(db_session)

    await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    # position_event 없이 직접 quantity 수정 (운영 데이터 불일치 시뮬레이션)
    repo = _PR(db_session)
    position = await repo.get_by_account_symbol(account.id, "005930")
    assert position is not None
    position.quantity = 12  # 10→12, 이벤트 없음
    await repo.update(position)
    await db_session.commit()

    mismatches = await service.diagnose_position_mismatch(account.id)
    assert len(mismatches) == 1
    mismatch = mismatches[0]
    assert mismatch.symbol_code == "005930"
    assert mismatch.position_quantity == 12
    assert mismatch.event_quantity_sum == 10
    assert mismatch.discrepancy == 2


async def test_diagnose_position_mismatch_after_broker_sync_no_mismatch(db_session: AsyncSession) -> None:
    """sync_from_broker 이후에는 SYNC 이벤트가 기록되므로 불일치가 없다."""
    account = await _create_account(db_session)
    broker = FakeHoldingsBrokerClient(
        [_holding("005930", "삼성전자", 2, Decimal("71000"), Decimal("72000"))]
    )
    service = PositionService(db_session, broker)

    await service.sync_from_broker_positions(account.id)

    mismatches = await service.diagnose_position_mismatch(account.id)
    assert mismatches == []
