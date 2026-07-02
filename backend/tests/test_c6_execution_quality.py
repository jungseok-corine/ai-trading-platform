"""C-6.9: 체결 품질(슬리피지·지연) 집계."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.services.execution_quality_service import ExecutionQualityService


async def _pair(
    session: AsyncSession,
    account_id: int,
    *,
    side: TradeSide,
    signal_price: int,
    fill_price: int,
    latency_seconds: int = 3,
    order_status: OrderStatus = OrderStatus.FILLED,
    symbol: str = "005930",
) -> None:
    now = datetime.now(timezone.utc)
    trade = Trade(
        account_id=account_id, symbol_code=symbol, side=side,
        quantity=1, entry_price=Decimal(fill_price),
        entry_time=now + timedelta(seconds=latency_seconds),
        order_status=order_status,
    )
    session.add(trade)
    await session.flush()
    session.add(
        SignalLog(
            symbol_code=symbol, signal_type=side, generated_at=now,
            price=Decimal(signal_price), trade_id=trade.id,
        )
    )
    await session.commit()


async def _account(session: AsyncSession) -> Account:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(acc)
    await session.commit()
    return acc


@pytest.mark.asyncio
async def test_buy_slippage_positive_when_paid_more(db_session: AsyncSession):
    acc = await _account(db_session)
    await _pair(db_session, acc.id, side=TradeSide.BUY, signal_price=10000, fill_price=10100)

    s = await ExecutionQualityService(db_session).summary(days=1)
    assert s["pair_count"] == 1
    assert s["aggregate"]["avg_slippage_pct"] == pytest.approx(1.0, abs=0.01)
    assert s["aggregate"]["adverse_fill_ratio"] == 1.0
    assert s["aggregate"]["avg_latency_seconds"] == pytest.approx(3.0, abs=0.5)


@pytest.mark.asyncio
async def test_sell_slippage_positive_when_received_less(db_session: AsyncSession):
    acc = await _account(db_session)
    await _pair(db_session, acc.id, side=TradeSide.SELL, signal_price=10000, fill_price=9900)

    s = await ExecutionQualityService(db_session).summary(days=1)
    assert s["by_side"]["sell"]["avg_slippage_pct"] == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_favorable_fill_negative_slippage(db_session: AsyncSession):
    acc = await _account(db_session)
    await _pair(db_session, acc.id, side=TradeSide.BUY, signal_price=10000, fill_price=9950)

    s = await ExecutionQualityService(db_session).summary(days=1)
    assert s["aggregate"]["avg_slippage_pct"] == pytest.approx(-0.5, abs=0.01)
    assert s["aggregate"]["adverse_fill_ratio"] == 0.0


@pytest.mark.asyncio
async def test_pending_and_cancelled_trades_excluded(db_session: AsyncSession):
    acc = await _account(db_session)
    await _pair(
        db_session, acc.id, side=TradeSide.BUY, signal_price=10000, fill_price=10100,
        order_status=OrderStatus.CANCELLED,
    )
    s = await ExecutionQualityService(db_session).summary(days=1)
    assert s["pair_count"] == 0
    assert s["aggregate"] == {"count": 0}


@pytest.mark.asyncio
async def test_worst_list_sorted_by_adverse_slippage(db_session: AsyncSession):
    acc = await _account(db_session)
    await _pair(db_session, acc.id, side=TradeSide.BUY, signal_price=10000, fill_price=10300)
    await _pair(db_session, acc.id, side=TradeSide.BUY, signal_price=10000, fill_price=10100)

    s = await ExecutionQualityService(db_session).summary(days=1)
    assert s["pair_count"] == 2
    assert s["worst"][0]["slippage_pct"] >= s["worst"][1]["slippage_pct"]
    assert s["worst"][0]["slippage_pct"] == pytest.approx(3.0, abs=0.01)
