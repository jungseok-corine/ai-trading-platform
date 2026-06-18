"""C-2.12 Trading Guard Tests.

검증 항목:
  1. reconcile real mode 불일치 시 auto_paused=True
  2. reconcile paper mode 불일치 시 auto_paused=False (no auto-pause)
  3. auto_pause: TradingGuardState 생성, is_paused=True, source=RECONCILIATION
  4. auto_pause 두 번째 호출: 이미 pause 상태이면 paused_at 유지, reason 갱신
  5. is_paused: 상태 없으면 False
  6. is_paused: pause 상태이면 True
  7. manual_pause: source=MANUAL, is_paused=True
  8. resume: is_paused=False, resolved_at 설정
  9. TradeService: pause 상태이면 주문 차단 (rule_name=trading_paused)
  10. StrategyRunner: pause 상태이면 auto-trade 스킵
  11. API GET /status: guard 없으면 is_paused=False
  12. API POST /pause: 수동 pause 성공
  13. API POST /resume: pause 상태에서 resume 성공
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, PauseSource
from app.domain.models.position import Position
from app.services.position_reconciliation_service import PositionReconciliationService
from app.services.trading_guard_service import TradingGuardService
from app.trading.broker.schemas import BrokerPositionItem


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _make_account(session: AsyncSession, account_type: AccountType) -> Account:
    account = Account(account_type=account_type, broker_account_no="TG-TEST-01")
    session.add(account)
    await session.flush()
    return account


async def _make_position(
    session: AsyncSession,
    account_id: int,
    symbol_code: str = "005930",
    quantity: int = 10,
) -> Position:
    pos = Position(
        account_id=account_id,
        symbol_code=symbol_code,
        symbol_name="삼성전자",
        quantity=quantity,
        avg_entry_price=Decimal("70000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
    )
    session.add(pos)
    await session.flush()
    return pos


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
    def __init__(self, broker_positions: list[BrokerPositionItem]) -> None:
        self._positions = broker_positions

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        return self._positions

    async def get_account_positions(self):
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

    async def get_current_price(self, symbol_code): raise NotImplementedError
    async def get_minute_candles(self, *a, **kw): raise NotImplementedError
    async def get_account_balance(self): raise NotImplementedError
    async def place_order(self, order): raise NotImplementedError
    async def get_daily_executions(self, *a, **kw): raise NotImplementedError


# ---------------------------------------------------------------------------
# 1. reconcile real mode 불일치 → auto_paused=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_real_mode_sets_auto_paused(db_session: AsyncSession) -> None:
    """real 계좌 불일치 시 result.auto_paused=True여야 한다."""
    account = await _make_account(db_session, AccountType.LIVE)
    await _make_position(db_session, account.id, quantity=10)

    broker = _FakeBroker([])  # DB에만 있고 브로커에 없음
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.auto_paused is True
    assert result.risk_event_created is True

    guard_svc = TradingGuardService(db_session)
    assert await guard_svc.is_paused(account.id) is True


# ---------------------------------------------------------------------------
# 2. reconcile paper mode 불일치 → auto_paused=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_paper_mode_no_auto_pause(db_session: AsyncSession) -> None:
    """paper 계좌 불일치 시 auto_pause는 발동하지 않아야 한다."""
    account = await _make_account(db_session, AccountType.PAPER)
    await _make_position(db_session, account.id, quantity=5)

    broker = _FakeBroker([_make_broker_item(quantity=10)])
    result = await PositionReconciliationService(db_session, broker).reconcile(account.id)

    assert result.auto_paused is False
    assert result.synced_to_db is True

    guard_svc = TradingGuardService(db_session)
    assert await guard_svc.is_paused(account.id) is False


# ---------------------------------------------------------------------------
# 3. auto_pause: 새 TradingGuardState 생성, source=RECONCILIATION
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_pause_creates_state(db_session: AsyncSession) -> None:
    """auto_pause() 최초 호출 시 is_paused=True인 상태가 생성된다."""
    account = await _make_account(db_session, AccountType.LIVE)
    svc = TradingGuardService(db_session)

    state = await svc.auto_pause(
        account_id=account.id,
        reason="qty mismatch: 005930",
        source=PauseSource.RECONCILIATION,
    )

    assert state.is_paused is True
    assert state.pause_source == PauseSource.RECONCILIATION
    assert state.paused_by == "system"
    assert state.pause_reason == "qty mismatch: 005930"
    assert state.paused_at is not None


# ---------------------------------------------------------------------------
# 4. auto_pause 두 번째 호출: paused_at 유지, reason 갱신
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_pause_updates_existing_state(db_session: AsyncSession) -> None:
    """이미 pause 상태이면 paused_at은 유지하고 reason/source를 갱신한다."""
    account = await _make_account(db_session, AccountType.LIVE)
    svc = TradingGuardService(db_session)

    first = await svc.auto_pause(
        account_id=account.id,
        reason="first reason",
        source=PauseSource.RECONCILIATION,
    )
    original_paused_at = first.paused_at

    second = await svc.auto_pause(
        account_id=account.id,
        reason="second reason",
        source=PauseSource.ORDER_SYNC,
    )

    assert second.paused_at == original_paused_at
    assert second.pause_reason == "second reason"
    assert second.pause_source == PauseSource.ORDER_SYNC


# ---------------------------------------------------------------------------
# 5. is_paused: guard 상태 없으면 False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_paused_no_state_returns_false(db_session: AsyncSession) -> None:
    """TradingGuardState가 없으면 is_paused()는 False여야 한다."""
    account = await _make_account(db_session, AccountType.LIVE)
    svc = TradingGuardService(db_session)
    assert await svc.is_paused(account.id) is False


# ---------------------------------------------------------------------------
# 6. is_paused: pause 상태이면 True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_paused_paused_state_returns_true(db_session: AsyncSession) -> None:
    """auto_pause() 후 is_paused()는 True여야 한다."""
    account = await _make_account(db_session, AccountType.LIVE)
    svc = TradingGuardService(db_session)
    await svc.auto_pause(account.id, reason="test", source=PauseSource.MANUAL)
    assert await svc.is_paused(account.id) is True


# ---------------------------------------------------------------------------
# 7. manual_pause: source=MANUAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_pause_sets_manual_source(db_session: AsyncSession) -> None:
    """manual_pause() 호출 시 pause_source=MANUAL이어야 한다."""
    account = await _make_account(db_session, AccountType.LIVE)
    svc = TradingGuardService(db_session)

    state = await svc.manual_pause(account_id=account.id, reason="operator request")

    assert state.is_paused is True
    assert state.pause_source == PauseSource.MANUAL
    assert state.paused_by == "user"


# ---------------------------------------------------------------------------
# 8. resume: is_paused=False, resolved_at 설정
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_clears_pause(db_session: AsyncSession) -> None:
    """resume() 후 is_paused=False이고 resolved_at이 설정된다."""
    account = await _make_account(db_session, AccountType.LIVE)
    svc = TradingGuardService(db_session)

    await svc.auto_pause(account.id, reason="test", source=PauseSource.RECONCILIATION)
    state = await svc.resume(
        account_id=account.id,
        resolved_by="operator@example.com",
        resolution_note="manually verified positions",
    )

    assert state.is_paused is False
    assert state.resolved_at is not None
    assert state.resolved_by == "operator@example.com"
    assert state.resolution_note == "manually verified positions"
    assert await svc.is_paused(account.id) is False


# ---------------------------------------------------------------------------
# 9. TradeService: pause 상태이면 주문 차단
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_service_blocks_order_when_paused(db_session: AsyncSession) -> None:
    """TradingGuard가 paused이면 execute_signal이 trading_paused로 거부한다."""
    from app.services.trade_service import TradeService
    from app.trading.strategy.base import Signal
    from app.domain.models.enums import TradeSide

    account = await _make_account(db_session, AccountType.LIVE)
    guard_svc = TradingGuardService(db_session)
    await guard_svc.auto_pause(account.id, reason="test", source=PauseSource.RECONCILIATION)

    broker_mock = AsyncMock()
    risk_service_mock = AsyncMock()
    trade_svc = TradeService(db_session, broker_mock, risk_service_mock)

    signal = Signal(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("70000"),
        reason="test",
    )
    result = await trade_svc.execute_signal(account.id, signal)

    assert result.approved is False
    assert result.rule_name == "trading_paused"
    broker_mock.place_order.assert_not_called()


# ---------------------------------------------------------------------------
# 10. StrategyRunner: pause 상태이면 auto-trade 스킵
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_runner_skips_when_paused(db_session: AsyncSession) -> None:
    """TradingGuard가 paused이면 _attempt_auto_trade가 주문 시도를 건너뛴다."""
    from app.services.strategy_runner_service import StrategyRunnerService

    account = await _make_account(db_session, AccountType.LIVE)
    guard_svc = TradingGuardService(db_session)
    await guard_svc.auto_pause(account.id, reason="test", source=PauseSource.RECONCILIATION)

    # strategy_version 준비
    from app.domain.models.strategy import Strategy, StrategyVersion
    from app.domain.models.enums import StrategyVersionStatus
    strategy = Strategy(name="TestStrategy")
    db_session.add(strategy)
    await db_session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        status=StrategyVersionStatus.ACTIVE,
        parameters={
            "strategy_type": "moving_average_cross",
            "symbol_code": "005930",
            "enabled": True,
            "auto_trade_enabled": True,
            "account_id": account.id,
            "quantity": 1,
        },
    )
    db_session.add(version)
    await db_session.flush()

    from app.domain.models.signal_log import SignalLog
    from app.domain.models.enums import TradeSide, TradeAttemptStatus
    from datetime import datetime
    from zoneinfo import ZoneInfo

    fake_log = SignalLog(
        id=9999,
        strategy_version_id=version.id,
        symbol_code="005930",
        signal_type=TradeSide.BUY,
        generated_at=datetime.now(ZoneInfo("Asia/Seoul")),
        price=Decimal("70000"),
        quantity=1,
        trade_attempt_status=TradeAttemptStatus.NOT_ATTEMPTED,
    )

    trade_svc_mock = AsyncMock()
    signal_svc_mock = AsyncMock()
    signal_svc_mock.generate_and_log_signal = AsyncMock(return_value=fake_log)
    runner = StrategyRunnerService(db_session, signal_svc_mock, trade_svc_mock)

    result = await runner._run_version(version)

    assert result is not None
    assert result.trade_attempted is False
    trade_svc_mock.execute_signal.assert_not_called()


# ---------------------------------------------------------------------------
# 11. API GET /status: guard 없으면 is_paused=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_get_status_no_guard_returns_not_paused(db_session_with_factory) -> None:
    """GET /accounts/{id}/trading-guard/status: guard 상태 없으면 is_paused=false."""
    from httpx import ASGITransport, AsyncClient
    from app.api.deps import get_broker_client
    from app.db.session import get_db
    from app.main import app

    session, _factory = db_session_with_factory
    account = await _make_account(session, AccountType.LIVE)

    def _override_db():
        async def _get():
            yield session
        return _get

    app.dependency_overrides[get_db] = _override_db()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/v1/accounts/{account.id}/trading-guard/status")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_paused"] is False
    assert data["account_id"] == account.id


# ---------------------------------------------------------------------------
# 12. API POST /pause: 수동 pause 성공
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_post_pause(db_session_with_factory) -> None:
    """POST /accounts/{id}/trading-guard/pause: 수동 pause 후 is_paused=true."""
    from httpx import ASGITransport, AsyncClient
    from app.db.session import get_db
    from app.main import app

    session, _factory = db_session_with_factory
    account = await _make_account(session, AccountType.LIVE)

    def _override_db():
        async def _get():
            yield session
        return _get

    app.dependency_overrides[get_db] = _override_db()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/accounts/{account.id}/trading-guard/pause",
                json={"reason": "scheduled maintenance"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_paused"] is True
    assert data["pause_source"] == "manual"


# ---------------------------------------------------------------------------
# 13. API POST /resume: pause → resume 성공; 비pause 상태면 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_post_resume_success_and_not_paused_error(db_session_with_factory) -> None:
    """POST /resume: pause 상태에서는 200, 비pause 상태에서는 400."""
    from httpx import ASGITransport, AsyncClient
    from app.db.session import get_db
    from app.main import app

    session, _factory = db_session_with_factory
    account = await _make_account(session, AccountType.LIVE)

    # 먼저 pause
    guard_svc = TradingGuardService(session)
    await guard_svc.auto_pause(account.id, reason="test", source=PauseSource.RECONCILIATION)

    def _override_db():
        async def _get():
            yield session
        return _get

    app.dependency_overrides[get_db] = _override_db()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # resume 성공
            resp_ok = await client.post(
                f"/api/v1/accounts/{account.id}/trading-guard/resume",
                json={"resolution_note": "positions verified"},
            )
            # 이미 resume 상태에서 또 resume → 400
            resp_err = await client.post(
                f"/api/v1/accounts/{account.id}/trading-guard/resume",
                json={"resolution_note": "should fail"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp_ok.status_code == 200
    assert resp_ok.json()["is_paused"] is False

    assert resp_err.status_code == 400
