"""C-2.10 Position Reconciliation Tests.

검증 항목:
  - 브로커/DB 포지션 일치 시 OK 반환
  - BROKER_POSITION_NOT_IN_DB: 브로커에만 있고 DB에 row 없음
  - MISSING_BUY_OR_UNSYNCED_POSITION: 브로커 qty > DB qty
  - DB_POSITION_NOT_IN_BROKER: DB qty > 0이지만 브로커에 없음
  - MISSING_SELL_OR_UNSYNCED_POSITION: DB qty > 브로커 qty
  - AVG_PRICE_MISMATCH: qty 일치, avg price 편차 초과
  - avg price tolerance 이내 → OK
  - paper 계좌: 불일치 시 DB 동기화됨
  - paper 계좌: risk_event 생성 안 됨
  - real 계좌: 불일치 시 risk_event 생성됨
  - real 계좌: DB 수정 안 됨
  - 복수 symbol 비교
  - API 엔드포인트 200 반환
  - AI analysis input limitations에 reconciliation 언급 포함
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType
from app.domain.models.position import Position
from app.services.position_reconciliation_service import (
    PositionReconciliationService,
    ReconciliationMismatchType,
)
from app.trading.broker.schemas import BrokerPositionItem


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _make_account(session: AsyncSession, account_type: AccountType) -> Account:
    account = Account(account_type=account_type, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


async def _make_position(
    session: AsyncSession,
    account_id: int,
    symbol_code: str = "005930",
    quantity: int = 10,
    avg_entry_price: Decimal = Decimal("70000"),
) -> Position:
    position = Position(
        account_id=account_id,
        symbol_code=symbol_code,
        symbol_name="삼성전자",
        quantity=quantity,
        avg_entry_price=avg_entry_price,
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
    )
    session.add(position)
    await session.flush()
    return position


def _make_broker_item(
    symbol_code: str = "005930",
    quantity: int = 10,
    average_price: Decimal = Decimal("70000"),
) -> BrokerPositionItem:
    return BrokerPositionItem(
        symbol_code=symbol_code,
        symbol_name="삼성전자",
        quantity=quantity,
        sellable_quantity=quantity,
        average_price=average_price,
        purchase_amount=average_price * quantity,
        current_price=average_price,
        market_value=average_price * quantity,
        unrealized_pnl=Decimal("0"),
        pnl_rate=Decimal("0"),
    )


class _FakeBroker:
    """포지션 reconciliation 테스트용 fake broker."""

    def __init__(self, broker_positions: list[BrokerPositionItem]) -> None:
        self._positions = broker_positions

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        return self._positions

    async def get_account_positions(self):
        # sync_from_broker_positions()가 내부적으로 호출한다.
        from app.trading.broker.schemas import AccountHolding
        return [
            AccountHolding(
                symbol_code=p.symbol_code,
                symbol_name=p.symbol_name,
                quantity=p.quantity,
                avg_purchase_price=p.average_price,
                current_price=p.current_price,
                evaluation_amount=p.market_value,
                profit_loss_amount=p.unrealized_pnl,
                profit_loss_rate=p.pnl_rate,
            )
            for p in self._positions
        ]

    async def get_current_price(self, symbol_code):
        raise NotImplementedError

    async def get_minute_candles(self, symbol_code, target_time=None, include_past_data=True):
        raise NotImplementedError

    async def get_account_balance(self):
        raise NotImplementedError

    async def place_order(self, order):
        raise NotImplementedError

    async def get_daily_executions(self, start_date=None, end_date=None):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 1. OK — 완전 일치
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_ok_no_mismatches(db_session: AsyncSession) -> None:
    """DB와 브로커가 완전히 일치하면 mismatch_count=0이어야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=10, avg_entry_price=Decimal("70000"))

    broker = _FakeBroker([_make_broker_item(quantity=10, average_price=Decimal("70000"))])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 0
    assert all(c.mismatch_type == ReconciliationMismatchType.OK for c in result.comparisons)
    assert result.synced_to_db is False
    assert result.risk_event_created is False


# ---------------------------------------------------------------------------
# 2. BROKER_POSITION_NOT_IN_DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_broker_position_not_in_db(db_session: AsyncSession) -> None:
    """브로커에는 있지만 DB에 row가 없으면 BROKER_POSITION_NOT_IN_DB여야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)

    broker = _FakeBroker([_make_broker_item(quantity=5)])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 1
    assert result.comparisons[0].mismatch_type == ReconciliationMismatchType.BROKER_POSITION_NOT_IN_DB
    assert result.comparisons[0].db_quantity is None
    assert result.comparisons[0].broker_quantity == 5


# ---------------------------------------------------------------------------
# 3. MISSING_BUY_OR_UNSYNCED_POSITION — DB qty=0, broker qty>0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_missing_buy_db_qty_zero(db_session: AsyncSession) -> None:
    """DB에 row는 있지만 qty=0이고 브로커에 qty>0이면 MISSING_BUY_OR_UNSYNCED_POSITION이어야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=0)

    broker = _FakeBroker([_make_broker_item(quantity=10)])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 1
    assert result.comparisons[0].mismatch_type == ReconciliationMismatchType.MISSING_BUY_OR_UNSYNCED_POSITION
    assert result.comparisons[0].db_quantity == 0
    assert result.comparisons[0].broker_quantity == 10


# ---------------------------------------------------------------------------
# 4. DB_POSITION_NOT_IN_BROKER
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_db_position_not_in_broker(db_session: AsyncSession) -> None:
    """DB qty>0인데 브로커 응답에 없으면 DB_POSITION_NOT_IN_BROKER여야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=10)

    broker = _FakeBroker([])  # 브로커에 아무것도 없음
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 1
    assert result.comparisons[0].mismatch_type == ReconciliationMismatchType.DB_POSITION_NOT_IN_BROKER
    assert result.comparisons[0].db_quantity == 10
    assert result.comparisons[0].broker_quantity is None


# ---------------------------------------------------------------------------
# 5. MISSING_SELL_OR_UNSYNCED_POSITION — DB qty > broker qty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_missing_sell(db_session: AsyncSession) -> None:
    """DB qty가 브로커 qty보다 크면 MISSING_SELL_OR_UNSYNCED_POSITION이어야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=10)

    broker = _FakeBroker([_make_broker_item(quantity=7)])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 1
    assert result.comparisons[0].mismatch_type == ReconciliationMismatchType.MISSING_SELL_OR_UNSYNCED_POSITION
    assert result.comparisons[0].db_quantity == 10
    assert result.comparisons[0].broker_quantity == 7


# ---------------------------------------------------------------------------
# 6. AVG_PRICE_MISMATCH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_avg_price_mismatch(db_session: AsyncSession) -> None:
    """qty 일치, avg price가 0.5% 이상 벗어나면 AVG_PRICE_MISMATCH여야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=10, avg_entry_price=Decimal("70000"))

    # 브로커 avg는 72000 — 2.86% 차이
    broker = _FakeBroker([_make_broker_item(quantity=10, average_price=Decimal("72000"))])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 1
    assert result.comparisons[0].mismatch_type == ReconciliationMismatchType.AVG_PRICE_MISMATCH


# ---------------------------------------------------------------------------
# 7. avg price tolerance 이내 → OK
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_avg_price_within_tolerance(db_session: AsyncSession) -> None:
    """avg price 차이가 0.5% 이내이면 OK이어야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=10, avg_entry_price=Decimal("70000"))

    # 0.1% 차이 — 허용 범위 이내
    broker = _FakeBroker([_make_broker_item(quantity=10, average_price=Decimal("70070"))])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.mismatch_count == 0
    assert result.comparisons[0].mismatch_type == ReconciliationMismatchType.OK


# ---------------------------------------------------------------------------
# 8. paper 계좌: 불일치 시 DB 동기화
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_paper_mode_syncs_db(db_session: AsyncSession) -> None:
    """paper 계좌에서 불일치 발견 시 synced_to_db=True여야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=5)

    broker = _FakeBroker([_make_broker_item(quantity=10)])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.synced_to_db is True
    assert result.risk_event_created is False


# ---------------------------------------------------------------------------
# 9. paper 계좌: risk_event 생성 안 됨
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_paper_mode_no_risk_event(db_session: AsyncSession) -> None:
    """paper 계좌에서 불일치가 있어도 risk_event는 생성되지 않아야 한다."""
    from sqlalchemy import select
    from app.domain.models.risk import RiskEvent

    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=5)

    broker = _FakeBroker([_make_broker_item(quantity=10)])
    await PositionReconciliationService(db_session, broker).reconcile(account.id)

    rows = await db_session.execute(select(RiskEvent).where(RiskEvent.account_id == account.id))
    assert list(rows.scalars().all()) == []


# ---------------------------------------------------------------------------
# 10. real 계좌: 불일치 시 risk_event 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_real_mode_creates_risk_event(db_session: AsyncSession) -> None:
    """real 계좌에서 불일치 발견 시 risk_event가 생성되어야 한다."""
    from sqlalchemy import select
    from app.domain.models.risk import RiskEvent

    account = await _make_account(db_session, AccountType.LIVE)
    await _make_position(db_session, account.id, quantity=10)

    broker = _FakeBroker([])  # 브로커에 없음
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.risk_event_created is True
    rows = await db_session.execute(select(RiskEvent).where(RiskEvent.account_id == account.id))
    events = list(rows.scalars().all())
    assert len(events) == 1
    assert events[0].rule_name == "position_reconciliation_mismatch"


# ---------------------------------------------------------------------------
# 11. real 계좌: DB 수정 안 됨
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_real_mode_no_db_sync(db_session: AsyncSession) -> None:
    """real 계좌에서 불일치가 있어도 DB position이 변경되지 않아야 한다."""
    account = await _make_account(db_session, AccountType.LIVE)
    position = await _make_position(db_session, account.id, quantity=10)

    broker = _FakeBroker([_make_broker_item(quantity=5)])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.synced_to_db is False
    await db_session.refresh(position)
    assert position.quantity == 10  # DB 변경 없음


# ---------------------------------------------------------------------------
# 12. 복수 symbol 비교
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_multiple_symbols(db_session: AsyncSession) -> None:
    """복수 종목이 있을 때 각 종목을 독립적으로 비교해야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, symbol_code="005930", quantity=10)
    await _make_position(db_session, account.id, symbol_code="000660", quantity=5)

    broker = _FakeBroker([
        _make_broker_item(symbol_code="005930", quantity=10, average_price=Decimal("70000")),
        # 000660은 브로커에 없음 — DB_POSITION_NOT_IN_BROKER
    ])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    types_by_symbol = {c.symbol_code: c.mismatch_type for c in result.comparisons}
    assert types_by_symbol["005930"] == ReconciliationMismatchType.OK
    assert types_by_symbol["000660"] == ReconciliationMismatchType.DB_POSITION_NOT_IN_BROKER
    assert result.mismatch_count == 1


# ---------------------------------------------------------------------------
# 13. API 엔드포인트 200 반환
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_api_endpoint_returns_200(db_session_with_factory) -> None:
    """POST /accounts/{account_id}/positions/reconcile가 200을 반환해야 한다."""
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_broker_client
    from app.db.session import get_db
    from app.main import app

    session, _factory = db_session_with_factory
    account = await _make_account(session, AccountType.PAPER)

    broker = _FakeBroker([])

    def _override_db():
        async def _get():
            yield session
        return _get

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_broker_client] = lambda: broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/v1/accounts/{account.id}/positions/reconcile")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)

    assert resp.status_code == 200
    data = resp.json()
    assert "mismatch_count" in data
    assert data["account_id"] == account.id


# ---------------------------------------------------------------------------
# 14. AI analysis input limitations에 reconciliation 언급
# ---------------------------------------------------------------------------


def test_analysis_input_limitations_has_reconciliation_note() -> None:
    """_LIMITATIONS에 broker balance reconciliation 언급이 있어야 한다."""
    from app.services.strategy_analysis_input_service import _LIMITATIONS

    text = " ".join(_LIMITATIONS)
    assert "reconcil" in text.lower(), (
        "reconciliation mention must be present in _LIMITATIONS"
    )
    assert "broker" in text.lower(), (
        "broker mention must be present in _LIMITATIONS"
    )
