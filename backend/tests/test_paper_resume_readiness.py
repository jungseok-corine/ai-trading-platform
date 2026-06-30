"""PAPER-RESUME-1 — read-only limited paper auto-trading resume checklist 테스트.

readiness checklist는 DB를 수정하지 않는다(SELECT only). 자동매매를 켜지 않는다.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    OrderStatus,
    StrategyVersionStatus,
    TradeSide,
)
from app.domain.models.position import Position
from app.domain.models.risk import RiskConfig
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.main import app
from app.services.paper_resume_readiness_service import PaperResumeReadinessService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import BrokerPositionItem

KST = ZoneInfo("Asia/Seoul")


class FakeBroker(BrokerClient):
    def __init__(self, broker_positions: list[BrokerPositionItem] | None = None) -> None:
        self._bp = broker_positions or []

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        return self._bp

    async def get_current_price(self, symbol_code):  # noqa: ANN001
        raise AssertionError("must not be called")

    async def get_minute_candles(self, symbol_code, target_time=None, include_past_data=True):  # noqa: ANN001
        raise AssertionError("must not be called")

    async def get_account_balance(self):
        raise AssertionError("must not be called")

    async def get_account_positions(self):
        raise AssertionError("must not be called")

    async def place_order(self, order):  # noqa: ANN001
        raise AssertionError("place_order must not be called")

    async def get_daily_executions(self, target_date=None):  # noqa: ANN001
        raise AssertionError("must not be called")


class _Settings:
    kis_real_trading_enabled = False
    strategy_scheduler_enabled = True
    paper_signal_session_runner_enabled = False
    paper_signal_recurring_plan_dispatcher_enabled = False


def _patch_settings(monkeypatch, **over) -> None:
    s = _Settings()
    for k, v in over.items():
        setattr(s, k, v)
    monkeypatch.setattr(
        "app.services.paper_resume_readiness_service.get_settings", lambda: s)


def _bpi(symbol_code, qty, avg) -> BrokerPositionItem:
    return BrokerPositionItem(
        symbol_code=symbol_code, symbol_name="x", quantity=qty, sellable_quantity=qty,
        average_price=Decimal(avg), purchase_amount=Decimal(avg) * qty, current_price=Decimal(avg),
        market_value=Decimal(avg) * qty, unrealized_pnl=Decimal("0"), pnl_rate=Decimal("0"))


async def _account(session, account_type=AccountType.PAPER, with_risk=True, **rc) -> Account:
    acc = Account(account_type=account_type, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    if with_risk:
        defaults = dict(
            account_id=acc.id, max_daily_loss_amount=Decimal("100000"),
            max_position_size=Decimal("1000000"), max_open_positions=5, max_trades_per_day=10,
            consecutive_loss_limit=3, emergency_stop=False)
        defaults.update(rc)
        session.add(RiskConfig(**defaults))
        await session.flush()
    return acc


async def _strategy_version(session, account_id, *, auto=False, universe=False) -> None:
    strat = Strategy(name="s")
    session.add(strat)
    await session.flush()
    params = {"account_id": account_id}
    if auto:
        params["auto_trade_enabled"] = True
    if universe:
        params["universe_auto_trade"] = True
    session.add(StrategyVersion(
        strategy_id=strat.id, version_no=1, parameters=params,
        status=StrategyVersionStatus.TESTING))
    await session.flush()


async def _item(report, key):
    return next(i for i in report.items if i.key == key)


def _svc(session, broker=None):
    return PaperResumeReadinessService(session, broker or FakeBroker())


# --- Test 1: live trading enabled -> BLOCKED ---------------------------------
async def test_blocks_if_live_trading_enabled(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch, kis_real_trading_enabled=True)
    acc = await _account(db_session)
    report = await _svc(db_session).build_checklist(acc.id)
    assert report.overall_status == "BLOCKED"
    assert (await _item(report, "live_trading_disabled")).status == "BLOCK"


# --- Test 2: live account -> BLOCKED -----------------------------------------
async def test_blocks_if_account_is_live(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session, account_type=AccountType.LIVE)
    report = await _svc(db_session).build_checklist(acc.id)
    assert report.overall_status == "BLOCKED"
    assert (await _item(report, "account_is_paper")).status == "BLOCK"


# --- Test 3: RiskConfig missing -> BLOCKED -----------------------------------
async def test_blocks_if_risk_config_missing(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session, with_risk=False)
    report = await _svc(db_session).build_checklist(acc.id)
    assert report.overall_status == "BLOCKED"
    assert (await _item(report, "risk_config")).status == "BLOCK"


# --- Test 4: reconciliation mismatch -> WARN, no DB mutation -----------------
async def test_warns_if_reconciliation_mismatch(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session)
    db_session.add(Position(account_id=acc.id, symbol_code="005380", symbol_name="현대차",
                            quantity=3, avg_entry_price=Decimal("531333")))
    await db_session.flush()
    pos_before = (await db_session.execute(select(func.count()).select_from(Position))).scalar_one()
    report = await _svc(db_session, FakeBroker([])).build_checklist(acc.id)  # broker empty
    assert (await _item(report, "reconciliation_state")).status == "WARN"
    assert (await db_session.execute(select(func.count()).select_from(Position))).scalar_one() == pos_before


# --- Test 5: no auto-trade strategy -> WARN ----------------------------------
async def test_warns_if_no_auto_trade_strategy(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session)
    report = await _svc(db_session).build_checklist(acc.id)
    assert (await _item(report, "auto_trade_scope")).status == "WARN"


# --- Test 6: broad universe auto-trade + dispatcher -> BLOCK -----------------
async def test_blocks_full_universe_when_dispatcher_on(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch, paper_signal_recurring_plan_dispatcher_enabled=True)
    acc = await _account(db_session)
    await _strategy_version(db_session, acc.id, universe=True)
    report = await _svc(db_session).build_checklist(acc.id)
    assert (await _item(report, "full_universe_guard")).status == "BLOCK"
    assert report.overall_status == "BLOCKED"


async def test_warns_full_universe_when_dispatcher_off(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session)
    await _strategy_version(db_session, acc.id, universe=True)
    report = await _svc(db_session).build_checklist(acc.id)
    assert (await _item(report, "full_universe_guard")).status == "WARN"


# --- Test 7: today trade count exceeded -> BLOCK -----------------------------
async def test_blocks_if_today_trade_count_exceeded(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session, max_trades_per_day=2)
    for _ in range(2):
        db_session.add(Trade(account_id=acc.id, symbol_code="005930", side=TradeSide.BUY,
                             quantity=1, order_status=OrderStatus.PENDING,
                             entry_time=datetime.now(KST)))
    await db_session.flush()
    report = await _svc(db_session).build_checklist(acc.id)
    assert (await _item(report, "current_trading_state")).status == "BLOCK"
    assert report.overall_status == "BLOCKED"


# --- Test 8: today realized loss exceeded -> BLOCK ---------------------------
async def test_blocks_if_today_realized_loss_exceeded(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session, max_daily_loss_amount=Decimal("100000"))
    db_session.add(Trade(account_id=acc.id, symbol_code="005380", side=TradeSide.SELL,
                         quantity=3, order_status=OrderStatus.FILLED,
                         entry_time=datetime.now(KST), exit_time=datetime.now(KST),
                         pnl_amount=Decimal("-150000")))
    await db_session.flush()
    report = await _svc(db_session).build_checklist(acc.id)
    assert (await _item(report, "current_trading_state")).status == "BLOCK"


# --- Test 9: open positions >= max -> buy WARN, sell PASS --------------------
async def test_buy_warn_when_open_positions_at_limit(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session, max_open_positions=2)
    broker = FakeBroker([_bpi("005930", 1, "70000"), _bpi("000660", 1, "120000"),
                         _bpi("035420", 1, "200000")])  # 3 >= 2
    report = await _svc(db_session, broker).build_checklist(acc.id)
    assert (await _item(report, "buy_readiness")).status == "WARN"
    assert (await _item(report, "sell_readiness")).status == "PASS"


# --- Test 10: happy path -> READY or READY_WITH_WARNINGS ---------------------
async def test_happy_path_ready(db_session: AsyncSession, monkeypatch) -> None:
    _patch_settings(monkeypatch)
    acc = await _account(db_session)
    await _strategy_version(db_session, acc.id, auto=True)  # limited single-symbol auto-trade
    report = await _svc(db_session, FakeBroker([])).build_checklist(acc.id)
    assert report.overall_status in ("READY", "READY_WITH_WARNINGS")
    assert report.block_count == 0


# --- Test 11: API endpoint, no DB mutation -----------------------------------
async def test_api_readiness_no_mutation(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    pos_before = (await db_session.execute(select(func.count()).select_from(Position))).scalar_one()
    fake = FakeBroker([])

    async def _get_db():
        yield db_session

    from app.api.deps import get_broker_client
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_broker_client] = lambda: fake
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/account/{acc.id}/paper-resume-readiness")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == acc.id
    assert body["overall_status"] in ("READY", "READY_WITH_WARNINGS", "BLOCKED")
    assert any(i["key"] == "live_trading_disabled" for i in body["items"])
    assert (await db_session.execute(select(func.count()).select_from(Position))).scalar_one() == pos_before
