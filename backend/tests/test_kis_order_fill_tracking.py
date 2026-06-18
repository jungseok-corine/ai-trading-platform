"""C-2.9 KIS Order Fill Tracking Audit Tests.

검증 항목:
  - paper mode → VTTC0081R tr_id 사용
  - real mode 상수 TTTC0081R 존재
  - place_order 응답의 ODNO/org_no가 Trade에 저장됨
  - pending order + filled_qty=0 → PENDING 유지
  - pending order + filled_qty=order_qty → FILLED
  - pending order + filled_qty 일부 → PARTIAL
  - 동일 체결조회 두 번 실행 → position_event 중복 없음
  - delta만 반영됨
  - AI analysis input에 pending orders 경고 포함
  - paper mode limitation note 포함
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from sqlalchemy import select

from app.domain.models.position_event import PositionEvent
from app.services.order_sync_service import OrderSyncService
from app.trading.broker.schemas import OrderExecution, OrderResult

# KIS TR_ID 상수 — 감사 목적으로 직접 import
from app.trading.broker.kis_paper import (
    TR_ID_INQUIRE_DAILY_CCLD,
    TR_ID_INQUIRE_DAILY_CCLD_REAL,
)

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _create_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


async def _create_trade(session: AsyncSession, account_id: int, **overrides) -> Trade:
    from datetime import date as _date

    today = _date.today()
    defaults = dict(
        account_id=account_id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        entry_price=Decimal("70000"),
        entry_time=datetime(today.year, today.month, today.day, 9, 0, tzinfo=KST),
        order_status=OrderStatus.PENDING,
        broker_order_id="0000000001",
    )
    defaults.update(overrides)
    trade = Trade(**defaults)
    session.add(trade)
    await session.flush()
    return trade


def _make_execution(
    broker_order_id: str = "0000000001",
    total_quantity: int = 10,
    filled_quantity: int = 10,
    filled_price: Decimal | None = Decimal("70000"),
    cancelled: bool = False,
    org_no: str | None = "00123",
) -> OrderExecution:
    return OrderExecution(
        broker_order_id=broker_order_id,
        org_no=org_no,
        symbol_code="005930",
        sll_buy_dvsn_cd="02",
        total_quantity=total_quantity,
        filled_quantity=filled_quantity,
        unfilled_quantity=total_quantity - filled_quantity,
        filled_price=filled_price,
        cancelled=cancelled,
        recorded_at=datetime.now(KST).replace(hour=9, minute=5, second=0, microsecond=0),
        raw={
            "odno": broker_order_id,
            "tot_ccld_qty": str(filled_quantity),
            "ord_qty": str(total_quantity),
            "ord_gno_brno": org_no or "",
        },
    )


class _FakeBroker:
    """최소 fake broker — get_daily_executions만 구현한다."""

    def __init__(self, executions: list[OrderExecution]) -> None:
        self._executions = executions

    async def get_current_price(self, symbol_code):
        raise NotImplementedError

    async def get_minute_candles(self, symbol_code, target_time=None, include_past_data=True):
        raise NotImplementedError

    async def get_account_balance(self):
        raise NotImplementedError

    async def get_account_positions(self):
        raise NotImplementedError

    async def place_order(self, order):
        raise NotImplementedError

    async def get_daily_executions(self, start_date=None, end_date=None):
        return self._executions


# ---------------------------------------------------------------------------
# 1. TR_ID 상수 검증
# ---------------------------------------------------------------------------


def test_paper_mode_uses_vttc0081r() -> None:
    """paper mode 일별주문체결조회 TR_ID가 문서 기준 VTTC0081R이어야 한다."""
    assert TR_ID_INQUIRE_DAILY_CCLD == "VTTC0081R"


def test_real_mode_constant_is_tttc0081r() -> None:
    """실전 모드 TR_ID 상수가 문서 기준 TTTC0081R이어야 한다."""
    assert TR_ID_INQUIRE_DAILY_CCLD_REAL == "TTTC0081R"


# ---------------------------------------------------------------------------
# 2. ODNO / org_no 저장 검증
# ---------------------------------------------------------------------------


def test_order_result_has_org_no_field() -> None:
    """OrderResult 스키마가 org_no 필드를 갖고 있어야 한다."""
    result = OrderResult(
        broker_order_id="0000000001",
        org_no="00123",
        order_status=OrderStatus.PENDING,
        ordered_at=datetime(2026, 6, 17, 9, 0, 0, tzinfo=KST),
    )
    assert result.org_no == "00123"
    assert result.broker_order_id == "0000000001"


def test_trade_model_has_org_no_column() -> None:
    """Trade 모델이 org_no 컬럼을 갖고 있어야 한다."""
    trade = Trade(
        account_id=1,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        entry_price=Decimal("70000"),
        order_status=OrderStatus.PENDING,
        broker_order_id="0000000001",
        org_no="00123",
    )
    assert trade.org_no == "00123"


@pytest.mark.asyncio
async def test_org_no_persisted_via_trade_repo(db_session: AsyncSession) -> None:
    """TradeRepository.create에 org_no를 전달하면 DB에 저장되어야 한다."""
    from app.domain.repositories.trade import TradeRepository

    account = await _create_account(db_session)
    from datetime import date

    today = date.today()
    trade = await TradeRepository(db_session).create(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=5,
        entry_price=Decimal("70000"),
        entry_time=datetime(today.year, today.month, today.day, 9, 0, tzinfo=KST),
        order_status=OrderStatus.PENDING,
        broker_order_id="0000000099",
        org_no="00999",
    )
    assert trade.org_no == "00999"
    assert trade.broker_order_id == "0000000099"


# ---------------------------------------------------------------------------
# 3. Order status 업데이트 로직
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filled_qty_zero_keeps_pending(db_session: AsyncSession) -> None:
    """filled_qty=0이면 order_status가 PENDING으로 유지되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id)

    broker = _FakeBroker([_make_execution(filled_quantity=0, filled_price=None)])
    result = await OrderSyncService(db_session, broker).sync_pending_orders()

    assert result.matched == 1
    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.PENDING


@pytest.mark.asyncio
async def test_filled_qty_equals_order_qty_sets_filled(db_session: AsyncSession) -> None:
    """filled_qty == order_qty이면 FILLED로 변경되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, quantity=10)

    broker = _FakeBroker([_make_execution(total_quantity=10, filled_quantity=10)])
    await OrderSyncService(db_session, broker).sync_pending_orders()

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_partially_filled_sets_partial_status(db_session: AsyncSession) -> None:
    """filled_qty < order_qty이면 PARTIAL로 변경되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, quantity=10)

    broker = _FakeBroker([_make_execution(total_quantity=10, filled_quantity=5)])
    await OrderSyncService(db_session, broker).sync_pending_orders()

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.PARTIAL


@pytest.mark.asyncio
async def test_cancelled_sets_cancelled_status(db_session: AsyncSession) -> None:
    """cncl_yn=Y이고 filled_qty=0이면 CANCELLED로 변경되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id)

    broker = _FakeBroker([
        _make_execution(filled_quantity=0, filled_price=None, cancelled=True)
    ])
    await OrderSyncService(db_session, broker).sync_pending_orders()

    await db_session.refresh(trade)
    assert trade.order_status == OrderStatus.CANCELLED


# ---------------------------------------------------------------------------
# 4. 중복 방지 — 동일 체결조회 두 번 실행
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_execution_twice_no_duplicate_position_events(db_session: AsyncSession) -> None:
    """동일한 체결 결과를 두 번 sync해도 position_event가 한 번만 생성되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, quantity=10)

    execution = _make_execution(total_quantity=10, filled_quantity=10)
    broker = _FakeBroker([execution])

    await OrderSyncService(db_session, broker).sync_pending_orders()
    await db_session.refresh(trade)
    first_applied = trade.position_applied_quantity

    # 두 번째 실행 — trade가 이미 FILLED라 list_pending_or_partial에서 제외됨
    sync_result2 = await OrderSyncService(db_session, broker).sync_pending_orders()

    pe_rows = await db_session.execute(
        select(PositionEvent).where(PositionEvent.trade_id == trade.id)
    )
    events = list(pe_rows.scalars().all())
    assert len(events) == 1
    assert sync_result2.checked == 0  # FILLED 상태이므로 pending 조회에서 제외
    assert first_applied == 10


@pytest.mark.asyncio
async def test_delta_fill_only_new_quantity_applied(db_session: AsyncSession) -> None:
    """partial fill 후 추가 체결분만 delta로 반영되어야 한다."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, quantity=10)

    # 1차: 3주 체결
    broker = _FakeBroker([_make_execution(total_quantity=10, filled_quantity=3)])
    await OrderSyncService(db_session, broker).sync_pending_orders()
    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 3
    assert trade.order_status == OrderStatus.PARTIAL

    # 2차: 추가 2주 체결 (누적 5주)
    broker2 = _FakeBroker([_make_execution(total_quantity=10, filled_quantity=5)])
    await OrderSyncService(db_session, broker2).sync_pending_orders()
    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 5
    assert trade.order_status == OrderStatus.PARTIAL

    # position_event는 첫 3 + 두 번째 2 = 2개 생성되어야 함
    pe_rows = await db_session.execute(
        select(PositionEvent).where(PositionEvent.trade_id == trade.id)
    )
    events = list(pe_rows.scalars().all())
    assert len(events) == 2
    quantities = sorted(e.quantity_delta for e in events)
    assert quantities == [2, 3]


@pytest.mark.asyncio
async def test_same_partial_fill_not_doubled(db_session: AsyncSession) -> None:
    """동일한 partial fill 결과를 두 번 sync해도 delta=0이므로 position_event 추가 없음."""
    account = await _create_account(db_session)
    trade = await _create_trade(db_session, account.id, quantity=10)

    broker = _FakeBroker([_make_execution(total_quantity=10, filled_quantity=3)])
    await OrderSyncService(db_session, broker).sync_pending_orders()
    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 3

    # 같은 결과로 두 번째 sync
    await OrderSyncService(db_session, broker).sync_pending_orders()
    await db_session.refresh(trade)
    assert trade.position_applied_quantity == 3

    pe_rows = await db_session.execute(
        select(PositionEvent).where(PositionEvent.trade_id == trade.id)
    )
    events = list(pe_rows.scalars().all())
    assert len(events) == 1  # 두 번째 sync에서 delta=0이므로 추가 생성 없음


# ---------------------------------------------------------------------------
# 5. AI analysis input — pending orders / paper mode note
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_input_paper_mode_limitation_present(db_session: AsyncSession) -> None:
    """AI analysis input limitations에 paper mode / VTTC0081R 언급이 있어야 한다."""
    from app.services.strategy_analysis_input_service import _LIMITATIONS

    paper_note_found = any("VTTC0081R" in lim for lim in _LIMITATIONS)
    assert paper_note_found, "VTTC0081R must be mentioned in _LIMITATIONS"

    paper_trading_found = any("Paper trading" in lim or "paper trading" in lim for lim in _LIMITATIONS)
    assert paper_trading_found, "'Paper trading' must appear in _LIMITATIONS"


@pytest.mark.asyncio
async def test_analysis_input_pending_order_adds_data_quality_note(db_session: AsyncSession) -> None:
    """pending order가 있으면 analysis input limitations에 data quality note가 추가되어야 한다."""
    from app.domain.models.strategy import Strategy, StrategyVersion
    from app.services.strategy_analysis_input_service import StrategyAnalysisInputService

    strategy = Strategy(name="test-strategy")
    db_session.add(strategy)
    await db_session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        status="testing",
        parameters={"symbol_code": "", "short_window": 5, "long_window": 20},
    )
    db_session.add(version)
    await db_session.flush()

    account = await _create_account(db_session)
    # pending order 2개 생성
    await _create_trade(db_session, account.id, strategy_version_id=version.id, broker_order_id="AAA")
    await _create_trade(db_session, account.id, strategy_version_id=version.id, broker_order_id="BBB")

    svc = StrategyAnalysisInputService(db_session)
    payload = await svc.get_analysis_input(strategy.id, version.id)
    assert payload is not None

    limitations_text = " ".join(payload.analysis_context.limitations)
    assert "2 order(s) are still in pending" in limitations_text
    assert "VTTC0081R" in limitations_text


@pytest.mark.asyncio
async def test_analysis_input_no_pending_no_extra_note(db_session: AsyncSession) -> None:
    """pending order가 없으면 pending data quality note가 추가되지 않아야 한다."""
    from app.domain.models.strategy import Strategy, StrategyVersion
    from app.services.strategy_analysis_input_service import StrategyAnalysisInputService

    strategy = Strategy(name="test-no-pending")
    db_session.add(strategy)
    await db_session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        status="testing",
        parameters={"symbol_code": "", "short_window": 5, "long_window": 20},
    )
    db_session.add(version)
    await db_session.flush()

    # 주문 없음
    svc = StrategyAnalysisInputService(db_session)
    payload = await svc.get_analysis_input(strategy.id, version.id)
    assert payload is not None

    limitations_text = " ".join(payload.analysis_context.limitations)
    assert "pending/partial" not in limitations_text
