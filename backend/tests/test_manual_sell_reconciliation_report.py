"""MANUAL-SELL-RECON-2 — read-only KIS vs DB reconciliation report 테스트.

핵심: report는 DB를 수정하지 않는다(SELECT만). broker는 read-only(get_broker_positions)만 호출.
기존 reconcile/sync write 경로는 호출하지 않는다.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType
from app.domain.models.position import Position
from app.domain.models.risk import RiskConfig
from app.domain.models.trade import Trade
from app.main import app
from app.services.manual_reconciliation_report_service import (
    ManualReconciliationReportService,
)
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import BrokerPositionItem

KST = ZoneInfo("Asia/Seoul")


class FakeBroker(BrokerClient):
    """get_broker_positions만 의미있게 구현한 read-only fake."""

    def __init__(self, broker_positions: list[BrokerPositionItem]) -> None:
        self._broker_positions = broker_positions
        self.get_broker_positions_calls = 0

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        self.get_broker_positions_calls += 1
        return self._broker_positions

    # 아래는 호출되면 안 되는 경로 — 호출 시 즉시 실패.
    async def get_current_price(self, symbol_code):  # noqa: ANN001
        raise AssertionError("get_current_price must not be called")

    async def get_minute_candles(self, symbol_code, target_time=None, include_past_data=True):  # noqa: ANN001
        raise AssertionError("get_minute_candles must not be called")

    async def get_account_balance(self):
        raise AssertionError("get_account_balance must not be called")

    async def get_account_positions(self):
        raise AssertionError("get_account_positions must not be called")

    async def place_order(self, order):  # noqa: ANN001
        raise AssertionError("place_order must not be called")

    async def get_daily_executions(self, target_date=None):  # noqa: ANN001
        raise AssertionError("get_daily_executions must not be called")


def _bpi(symbol_code, qty, avg, name="이름") -> BrokerPositionItem:
    return BrokerPositionItem(
        symbol_code=symbol_code, symbol_name=name, quantity=qty, sellable_quantity=qty,
        average_price=Decimal(avg), purchase_amount=Decimal(avg) * qty, current_price=Decimal(avg),
        market_value=Decimal(avg) * qty, unrealized_pnl=Decimal("0"), pnl_rate=Decimal("0"),
    )


async def _make_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    session.add(RiskConfig(
        account_id=account.id, max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"), max_open_positions=5, max_trades_per_day=10,
        consecutive_loss_limit=3, emergency_stop=False,
    ))
    await session.flush()
    return account


async def _add_position(session: AsyncSession, account_id: int, symbol, qty, avg, name="이름") -> None:
    session.add(Position(
        account_id=account_id, symbol_code=symbol, symbol_name=name, quantity=qty,
        avg_entry_price=Decimal(avg),
    ))
    await session.flush()


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# --- Test 1: matched ----------------------------------------------------------
async def test_matched_broker_and_db_position(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "005930", 10, "70000")
    svc = ManualReconciliationReportService(db_session, FakeBroker([_bpi("005930", 10, "70000")]))

    report = await svc.build_report(acc.id)

    assert report.mismatch_count == 0
    assert report.matched_count == 1
    assert report.matched_positions[0].report_type == "matched"


# --- Test 2: broker_sold_db_open ---------------------------------------------
async def test_broker_sold_db_open(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "005380", 3, "531333")
    svc = ManualReconciliationReportService(db_session, FakeBroker([]))  # broker has nothing

    report = await svc.build_report(acc.id)

    assert report.mismatch_count == 1
    assert report.db_only_positions[0].report_type == "broker_sold_db_open"
    assert any("realized_pnl_missing_possible" in w for w in report.warnings)


# --- Test 3: broker_qty_less_than_db_qty -------------------------------------
async def test_broker_qty_less_than_db_qty(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "373220", 4, "374250")
    svc = ManualReconciliationReportService(db_session, FakeBroker([_bpi("373220", 1, "374250")]))

    report = await svc.build_report(acc.id)

    assert report.mismatches[0].report_type == "broker_qty_less_than_db_qty"
    assert any("realized_pnl_missing_possible" in w for w in report.warnings)


# --- Test 4: broker_qty_more_than_db_qty -------------------------------------
async def test_broker_qty_more_than_db_qty(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "000660", 1, "120000")
    svc = ManualReconciliationReportService(db_session, FakeBroker([_bpi("000660", 5, "120000")]))

    report = await svc.build_report(acc.id)

    assert report.mismatches[0].report_type == "broker_qty_more_than_db_qty"


# --- Test 5: broker_holding_db_missing ---------------------------------------
async def test_broker_holding_db_missing(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)  # no DB position
    svc = ManualReconciliationReportService(db_session, FakeBroker([_bpi("035420", 2, "200000")]))

    report = await svc.build_report(acc.id)

    assert report.mismatch_count == 1
    assert report.broker_only_holdings[0].report_type == "broker_holding_db_missing"


# --- Test 6: price_basis_mismatch --------------------------------------------
async def test_price_basis_mismatch(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "005930", 10, "70000")
    # 같은 수량, 평단가 10% 차이(> 0.5% tolerance).
    svc = ManualReconciliationReportService(db_session, FakeBroker([_bpi("005930", 10, "77000")]))

    report = await svc.build_report(acc.id)

    assert report.mismatches[0].report_type == "price_basis_mismatch"


# --- Test 7: realized_pnl_missing_possible warning ---------------------------
async def test_realized_pnl_missing_possible_warning(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "005380", 3, "531333")
    svc = ManualReconciliationReportService(db_session, FakeBroker([]))

    report = await svc.build_report(acc.id)

    assert any(w.startswith("realized_pnl_missing_possible") for w in report.warnings)


# --- Test 8: service performs no DB write ------------------------------------
async def test_service_does_not_mutate_db(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "005380", 3, "531333")
    pos_before = await _count(db_session, Position)
    trade_before = await _count(db_session, Trade)
    svc = ManualReconciliationReportService(db_session, FakeBroker([]))

    await svc.build_report(acc.id)

    # report 생성 후 DB row 수 불변(자동 sync/close 없음).
    assert await _count(db_session, Position) == pos_before
    assert await _count(db_session, Trade) == trade_before
    # broker는 read-only 조회만.
    assert svc._broker.get_broker_positions_calls == 1  # type: ignore[attr-defined]


# --- Test 9: API returns report without DB mutation --------------------------
async def test_api_reconciliation_report_no_mutation(db_session: AsyncSession) -> None:
    acc = await _make_account(db_session)
    await _add_position(db_session, acc.id, "005380", 3, "531333")
    await _add_position(db_session, acc.id, "005930", 10, "70000")
    pos_before = await _count(db_session, Position)

    fake = FakeBroker([_bpi("005930", 10, "70000")])  # 005380 sold in app

    async def _get_db():
        yield db_session

    from app.api.deps import get_broker_client
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_broker_client] = lambda: fake
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/account/{acc.id}/reconciliation-report")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == acc.id
    assert body["broker_holdings_count"] == 1
    assert body["db_open_positions_count"] == 2
    types = {m["report_type"] for m in body["mismatches"]}
    assert "broker_sold_db_open" in types  # 005380
    # DB 변경 없음.
    assert await _count(db_session, Position) == pos_before
