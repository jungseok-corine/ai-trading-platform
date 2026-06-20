"""C-3.11 거래 활동 요약 테스트."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.trade_activity_service import TradeActivityService


async def _setup(session: AsyncSession):
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50192525-01")
    strat = Strategy(name="ActivityStrat", description="t")
    session.add_all([acc, strat])
    await session.flush()
    sv = StrategyVersion(strategy_id=strat.id, version_no=1,
                         parameters={"strategy_type": "moving_average_cross"})
    session.add(sv)
    await session.flush()
    return acc, sv


def _trade(acc_id, sv_id, pnl):
    return Trade(
        account_id=acc_id, strategy_version_id=sv_id, symbol_code="005930",
        side=TradeSide.BUY, quantity=1, order_status=OrderStatus.FILLED,
        pnl_amount=None if pnl is None else Decimal(str(pnl)),
    )


async def test_summary_aggregates_wins_losses(db_session: AsyncSession) -> None:
    acc, sv = await _setup(db_session)
    db_session.add_all([
        _trade(acc.id, sv.id, 1000),   # win
        _trade(acc.id, sv.id, -400),   # loss
        _trade(acc.id, sv.id, 200),    # win
        _trade(acc.id, sv.id, None),   # 미청산 → 건수만
    ])
    await db_session.flush()

    out = await TradeActivityService(db_session).summary(days=30)
    o = out["overall"]
    assert o["trades"] == 4 and o["closed"] == 3
    assert o["wins"] == 2 and o["losses"] == 1
    assert o["total_pnl"] == 800.0
    assert o["win_rate"] == round(2 / 3 * 100, 1)
    assert o["avg_pnl"] == round(800 / 3, 2)
    # 전략별 라벨
    assert out["by_strategy"][0]["label"] == "ActivityStrat v1"


async def test_equity_curve_accumulates(db_session: AsyncSession) -> None:
    from datetime import datetime, timezone

    acc, sv = await _setup(db_session)
    t1 = _trade(acc.id, sv.id, 1000)
    t1.exit_time = datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc)
    t2 = _trade(acc.id, sv.id, -300)
    t2.exit_time = datetime(2026, 6, 19, 15, 0, tzinfo=timezone.utc)
    t3 = _trade(acc.id, sv.id, 500)
    t3.exit_time = datetime(2026, 6, 19, 16, 0, tzinfo=timezone.utc)
    db_session.add_all([t1, t2, t3])
    await db_session.flush()

    curve = await TradeActivityService(db_session).equity_curve(days=365)
    assert [p["date"] for p in curve] == ["2026-06-18", "2026-06-19"]
    assert curve[0]["cumulative_pnl"] == 1000.0
    # 둘째 날: -300 + 500 = +200, 누적 1200
    assert curve[1]["realized_pnl"] == 200.0
    assert curve[1]["cumulative_pnl"] == 1200.0


async def test_summary_window_excludes_old(db_session: AsyncSession) -> None:
    acc, sv = await _setup(db_session)
    old = _trade(acc.id, sv.id, 500)
    db_session.add(old)
    await db_session.flush()
    old.created_at = datetime.now(timezone.utc) - timedelta(days=40)
    await db_session.flush()

    out = await TradeActivityService(db_session).summary(days=30)
    assert out["overall"]["trades"] == 0
