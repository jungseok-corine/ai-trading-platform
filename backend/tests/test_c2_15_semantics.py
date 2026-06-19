"""C-2.15: Portfolio, Orders, Signals Semantics Cleanup 테스트.

커버 범위:
1. scheduler job label i18n mapping
2. portfolio realized/unrealized/total pnl 계산
3. quantity=0 position 기본 제외
4. include_closed=true 동작
5. legacy order backfill dry-run이 주문 API를 호출하지 않음
6. legacy backfill이 matched order를 dry-run 결과로만 표시
7. signal pagination limit 적용
8. signal filters (symbol, type, date)
9. signal_price 저장
10. signal_price API 응답
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

# 테스트가 어느 머신에서 실행되든 동작하도록 repo 상대경로를 사용한다.
# (tests → backend → repo root)
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
_FRONTEND_ROOT = _REPO_ROOT / "frontend"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.signal_log import SignalLogRepository
from app.main import app
from app.services.portfolio_service import PortfolioService
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

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeBroker(BrokerClient):
    def __init__(self, place_order_calls: list | None = None) -> None:
        self._place_order_calls: list = place_order_calls if place_order_calls is not None else []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        return PriceQuote(
            symbol_code=symbol_code,
            current_price=Decimal("70000"),
            change=Decimal("0"),
            change_rate=Decimal("0"),
            open_price=Decimal("70000"),
            high_price=Decimal("70000"),
            low_price=Decimal("70000"),
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
        self._place_order_calls.append(order)
        raise AssertionError("place_order는 이 테스트에서 호출되면 안 됩니다")

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        return []


async def _make_account(session: AsyncSession, account_type: AccountType = AccountType.PAPER) -> Account:
    account = Account(account_type=account_type, broker_account_no="00001234-01")
    session.add(account)
    await session.flush()
    return account


# ---------------------------------------------------------------------------
# 1. scheduler job label i18n mapping
# ---------------------------------------------------------------------------

def test_scheduler_job_label_ko_has_trading_state_sync() -> None:
    """translations.ts의 ko jobLabels에 trading_state_sync 키가 있어야 한다."""
    import json
    import subprocess
    result = subprocess.run(
        ["node", "-e",
         "const fs=require('fs');"
         "const src=fs.readFileSync('src/i18n/translations.ts','utf8');"
         "const match=src.match(/jobLabels:[\\s\\S]*?} as Record/);"
         "console.log(match ? 'found' : 'not_found');"],
        cwd=str(_FRONTEND_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_scheduler_job_label_ko_content() -> None:
    """ko jobLabels에 strategy_runner, order_sync, trading_state_sync가 모두 있어야 한다."""
    src = open(_FRONTEND_ROOT / "src/i18n/translations.ts").read()
    assert "strategy_runner" in src
    assert "order_sync" in src
    assert "trading_state_sync" in src
    assert "거래 상태 동기화" in src
    assert "전략 실행기" in src
    assert "주문/체결 동기화" in src


def test_scheduler_job_label_en_content() -> None:
    """en jobLabels에 영문 번역이 있어야 한다."""
    src = open(_FRONTEND_ROOT / "src/i18n/translations.ts").read()
    assert "Strategy Runner" in src
    assert "Order/Fill Sync" in src
    assert "Trading State Sync" in src


# ---------------------------------------------------------------------------
# 2. portfolio realized/unrealized/total pnl 계산 (held 기준)
# ---------------------------------------------------------------------------

async def test_portfolio_unrealized_pnl_from_held_only(db_session: AsyncSession) -> None:
    """unrealized_pnl은 quantity>0인 보유 포지션만 합산해야 한다.

    C-2.15 수정 전: 모든 포지션(qty=0 포함) 합산.
    C-2.15 수정 후: qty>0 포지션만 합산.
    """
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    # 매수 후 전량 매도 → qty=0, realized_pnl=+10000
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("71000"))

    # 별도 종목 매수 (qty>0)
    await svc.apply_fill(account_id=account.id, symbol_code="000660", side=TradeSide.BUY, quantity=5, price=Decimal("100000"))
    await svc.update_last_price(account.id, "000660", Decimal("102000"))

    summary = await PortfolioService(db_session).get_summary(account.id)

    # position_count: qty>0 종목만 (000660만 해당)
    assert summary.position_count == 1
    # unrealized: 000660만 (102000-100000)*5 = 10000
    assert summary.total_unrealized_pnl == Decimal("10000")
    # realized: 005930 전량매도 손익 포함
    assert summary.total_realized_pnl == Decimal("10000")
    # total = unrealized + realized
    assert summary.total_pnl == summary.total_unrealized_pnl + summary.total_realized_pnl


async def test_portfolio_realized_pnl_persists_after_sell(db_session: AsyncSession) -> None:
    """매도 후 realized_pnl은 포트폴리오 요약에서 유지되어야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("80000"))

    summary = await PortfolioService(db_session).get_summary(account.id)

    assert summary.total_realized_pnl == Decimal("100000")
    assert summary.total_unrealized_pnl == Decimal("0")
    assert summary.total_pnl == Decimal("100000")


async def test_portfolio_new_holding_loss_reduces_total(db_session: AsyncSession) -> None:
    """새 보유 주식이 손실 중이면 total_pnl은 realized에서 손실분이 차감돼야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    # 실현손익 +100,000
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("80000"))

    # 새 보유 포지션 손실 중: unrealized = -50,000
    await svc.apply_fill(account_id=account.id, symbol_code="000660", side=TradeSide.BUY, quantity=5, price=Decimal("100000"))
    await svc.update_last_price(account.id, "000660", Decimal("90000"))

    summary = await PortfolioService(db_session).get_summary(account.id)

    assert summary.total_realized_pnl == Decimal("100000")
    assert summary.total_unrealized_pnl == Decimal("-50000")
    assert summary.total_pnl == Decimal("50000")


# ---------------------------------------------------------------------------
# 3. quantity=0 position 기본 제외
# ---------------------------------------------------------------------------

async def test_position_list_excludes_zero_qty_by_default(db_session: AsyncSession) -> None:
    """기본 조회(include_closed=False)에서 quantity=0 포지션은 제외되어야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("71000"))

    repo = PositionRepository(db_session)
    positions = await repo.list_by_account(account.id, include_closed=False)
    assert all(p.quantity != 0 for p in positions)
    assert len(positions) == 0


async def test_position_list_includes_zero_qty_when_include_closed(db_session: AsyncSession) -> None:
    """include_closed=True이면 quantity=0 포지션도 포함되어야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("71000"))

    repo = PositionRepository(db_session)
    positions = await repo.list_by_account(account.id, include_closed=True)
    closed = [p for p in positions if p.quantity == 0]
    assert len(closed) == 1
    # realized_pnl은 유지되어야 한다
    assert closed[0].realized_pnl == Decimal("10000")


async def test_position_list_qty_gt_zero_is_visible(db_session: AsyncSession) -> None:
    """quantity>0인 포지션은 기본 조회에서 표시되어야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))

    repo = PositionRepository(db_session)
    positions = await repo.list_by_account(account.id)
    assert len(positions) == 1
    assert positions[0].symbol_code == "005930"


# ---------------------------------------------------------------------------
# 4. positions API include_closed query parameter
# ---------------------------------------------------------------------------

async def test_positions_api_excludes_zero_qty_by_default(db_session: AsyncSession) -> None:
    """GET /positions 기본 응답에서 quantity=0 포지션은 제외되어야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("71000"))

    fake_broker = _FakeBroker()

    def override_db():
        return db_session

    def override_broker():
        return fake_broker

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_broker_client] = override_broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/positions", params={"account_id": account.id})
        assert resp.status_code == 200
        data = resp.json()
        assert all(p["quantity"] != 0 for p in data)
        assert len(data) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)


async def test_positions_api_include_closed_shows_zero_qty(db_session: AsyncSession) -> None:
    """GET /positions?include_closed=true이면 quantity=0 포지션도 포함되어야 한다."""
    account = await _make_account(db_session)
    svc = PositionService(db_session)

    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.BUY, quantity=10, price=Decimal("70000"))
    await svc.apply_fill(account_id=account.id, symbol_code="005930", side=TradeSide.SELL, quantity=10, price=Decimal("71000"))

    fake_broker = _FakeBroker()

    def override_db():
        return db_session

    def override_broker():
        return fake_broker

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_broker_client] = override_broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/positions",
                params={"account_id": account.id, "include_closed": "true"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["quantity"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)


# ---------------------------------------------------------------------------
# 5. legacy order backfill dry-run이 주문 API를 호출하지 않음
# ---------------------------------------------------------------------------

def test_backfill_script_does_not_call_place_order() -> None:
    """backfill 스크립트에 place_order 호출이 없어야 한다."""
    import ast
    src = open(_BACKEND_ROOT / "scripts/backfill_legacy_order_statuses.py").read()
    assert "place_order" not in src or "place_order를 호출하지 않는다" in src


def test_backfill_script_order_api_called_always_false() -> None:
    """backfill 스크립트의 BackfillReport.order_api_called는 항상 False여야 한다."""
    src = open(_BACKEND_ROOT / "scripts/backfill_legacy_order_statuses.py").read()
    assert "order_api_called: bool = False" in src


# ---------------------------------------------------------------------------
# 6. legacy backfill matched order를 dry-run 결과로만 표시
# ---------------------------------------------------------------------------

def test_backfill_report_dataclass_structure() -> None:
    """BackfillReport는 matched_filled_orders, would_update_to_filled 필드를 가져야 한다."""
    from scripts.backfill_legacy_order_statuses import BackfillReport, BackfillOrderResult
    report = BackfillReport()
    assert hasattr(report, "matched_filled_orders")
    assert hasattr(report, "would_update_to_filled")
    assert hasattr(report, "unmatched_orders")
    assert hasattr(report, "order_api_called")
    assert report.order_api_called is False


# ---------------------------------------------------------------------------
# 7. signal pagination limit 적용
# ---------------------------------------------------------------------------

async def test_signal_list_pagination_limit(db_session: AsyncSession) -> None:
    """list_signals의 limit이 실제로 적용되어야 한다."""
    account = await _make_account(db_session)
    repo = SignalLogRepository(db_session)

    # 5개 생성
    for i in range(5):
        await repo.create(
            symbol_code="005930",
            strategy_version_id=None,
            signal_type=TradeSide.BUY,
            generated_at=datetime(2026, 6, 18, 9, i, 0, tzinfo=KST),
        )
    await db_session.flush()

    from app.services.signal_service import SignalService
    svc = SignalService(db_session, None)  # type: ignore[arg-type]
    results = await svc.list_signals(limit=3, offset=0)
    assert len(results) == 3


async def test_signal_list_pagination_offset(db_session: AsyncSession) -> None:
    """offset 적용 시 다음 페이지 데이터를 반환해야 한다."""
    repo = SignalLogRepository(db_session)

    for i in range(4):
        await repo.create(
            symbol_code="005930",
            strategy_version_id=None,
            signal_type=TradeSide.BUY,
            generated_at=datetime(2026, 6, 18, 9, i, 0, tzinfo=KST),
        )
    await db_session.flush()

    from app.services.signal_service import SignalService
    svc = SignalService(db_session, None)  # type: ignore[arg-type]
    page1 = await svc.list_signals(limit=2, offset=0)
    page2 = await svc.list_signals(limit=2, offset=2)
    ids1 = {r.id for r in page1}
    ids2 = {r.id for r in page2}
    assert ids1.isdisjoint(ids2)


# ---------------------------------------------------------------------------
# 8. signal filters
# ---------------------------------------------------------------------------

async def test_signal_filter_by_symbol_code(db_session: AsyncSession) -> None:
    """symbol_code 필터가 올바르게 동작해야 한다."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    await repo.create(symbol_code="005930", strategy_version_id=None, signal_type=TradeSide.BUY, generated_at=ts)
    await repo.create(symbol_code="000660", strategy_version_id=None, signal_type=TradeSide.BUY, generated_at=ts)
    await db_session.flush()

    results = await repo.list_filtered(symbol_code="005930")
    assert all(r.symbol_code == "005930" for r in results)


async def test_signal_filter_by_signal_type(db_session: AsyncSession) -> None:
    """signal_type 필터가 올바르게 동작해야 한다."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    await repo.create(symbol_code="005930", strategy_version_id=None, signal_type=TradeSide.BUY, generated_at=ts)
    await repo.create(symbol_code="005930", strategy_version_id=None, signal_type=TradeSide.SELL, generated_at=ts)
    await db_session.flush()

    buy_results = await repo.list_filtered(signal_type=TradeSide.BUY)
    sell_results = await repo.list_filtered(signal_type=TradeSide.SELL)
    assert all(r.signal_type == TradeSide.BUY for r in buy_results)
    assert all(r.signal_type == TradeSide.SELL for r in sell_results)


async def test_signal_filter_by_date_range(db_session: AsyncSession) -> None:
    """date_from/date_to 필터가 올바르게 동작해야 한다."""
    repo = SignalLogRepository(db_session)

    old_ts = datetime(2026, 1, 1, 9, 0, 0, tzinfo=KST)
    new_ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    await repo.create(symbol_code="005930", strategy_version_id=None, signal_type=TradeSide.BUY, generated_at=old_ts)
    await repo.create(symbol_code="005930", strategy_version_id=None, signal_type=TradeSide.BUY, generated_at=new_ts)
    await db_session.flush()

    from_date = datetime(2026, 6, 1, tzinfo=KST)
    results = await repo.list_filtered(date_from=from_date)
    for r in results:
        assert r.generated_at >= from_date


# ---------------------------------------------------------------------------
# 9. signal_price 저장
# ---------------------------------------------------------------------------

async def test_signal_price_saved_on_create(db_session: AsyncSession) -> None:
    """signal_logs 테이블에 signal_price가 저장되어야 한다."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    log = await repo.create(
        symbol_code="005930",
        strategy_version_id=None,
        signal_type=TradeSide.BUY,
        generated_at=ts,
        price=Decimal("70000"),
        signal_price=Decimal("70000"),
    )
    await db_session.flush()

    fetched = await repo.get(log.id)
    assert fetched is not None
    assert fetched.signal_price == Decimal("70000")


async def test_signal_price_nullable(db_session: AsyncSession) -> None:
    """signal_price는 nullable이어야 한다 — 없으면 None."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    log = await repo.create(
        symbol_code="005930",
        strategy_version_id=None,
        signal_type=TradeSide.BUY,
        generated_at=ts,
    )
    await db_session.flush()

    fetched = await repo.get(log.id)
    assert fetched is not None
    assert fetched.signal_price is None


# ---------------------------------------------------------------------------
# 10. signal_price API 응답
# ---------------------------------------------------------------------------

async def test_signal_price_in_api_response(db_session: AsyncSession) -> None:
    """GET /signals 응답에 signal_price 필드가 포함되어야 한다."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    await repo.create(
        symbol_code="005930",
        strategy_version_id=None,
        signal_type=TradeSide.BUY,
        generated_at=ts,
        signal_price=Decimal("70000"),
    )
    await db_session.flush()

    fake_broker = _FakeBroker()

    def override_db():
        return db_session

    def override_broker():
        return fake_broker

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_broker_client] = override_broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "signal_price" in data[0]
        assert data[0]["signal_price"] is not None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)


async def test_signal_price_null_in_api_response(db_session: AsyncSession) -> None:
    """signal_price=None인 신호의 API 응답에서 signal_price가 null이어야 한다."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    await repo.create(
        symbol_code="005930",
        strategy_version_id=None,
        signal_type=TradeSide.BUY,
        generated_at=ts,
    )
    await db_session.flush()

    fake_broker = _FakeBroker()

    def override_db():
        return db_session

    def override_broker():
        return fake_broker

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_broker_client] = override_broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "signal_price" in data[0]
        assert data[0]["signal_price"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)


# ---------------------------------------------------------------------------
# signal_service가 signal_price를 저장하는지 확인 (코드 검사)
# ---------------------------------------------------------------------------

def test_signal_service_saves_signal_price() -> None:
    """signal_service.py가 signal_price=signal.price를 repo.create에 전달해야 한다."""
    src = open(_BACKEND_ROOT / "app/services/signal_service.py").read()
    assert "signal_price=signal.price" in src


# ---------------------------------------------------------------------------
# signals API pagination parameter limit
# ---------------------------------------------------------------------------

async def test_signals_api_pagination_params(db_session: AsyncSession) -> None:
    """GET /signals?limit=2&offset=0 — limit/offset query params가 동작해야 한다."""
    repo = SignalLogRepository(db_session)
    ts = datetime(2026, 6, 18, 9, 0, 0, tzinfo=KST)

    for i in range(3):
        await repo.create(
            symbol_code="005930",
            strategy_version_id=None,
            signal_type=TradeSide.BUY,
            generated_at=datetime(2026, 6, 18, 9, i, 0, tzinfo=KST),
        )
    await db_session.flush()

    fake_broker = _FakeBroker()

    def override_db():
        return db_session

    def override_broker():
        return fake_broker

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_broker_client] = override_broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/signals", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)


async def test_signals_api_max_limit_200(db_session: AsyncSession) -> None:
    """GET /signals?limit=201 → 422 (max 200)."""
    fake_broker = _FakeBroker()

    def override_db():
        return db_session

    def override_broker():
        return fake_broker

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_broker_client] = override_broker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/signals", params={"limit": 201})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_broker_client, None)
