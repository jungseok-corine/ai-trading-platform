"""C-4 정리 스크립트: 토이 전략 아카이브 + 노이즈 로그 리셋 (LIVE 계좌는 보존)."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    OrderStatus,
    PositionEventType,
    StrategyVersionStatus,
    TradeSide,
)
from app.domain.models.position import Position
from app.domain.models.position_event import PositionEvent
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade

from scripts.reset_toy_strategies import run

KST = ZoneInfo("Asia/Seoul")


async def _seed(session: AsyncSession) -> dict:
    paper = Account(account_type=AccountType.PAPER, broker_account_no="PAPER01")
    live = Account(account_type=AccountType.LIVE, broker_account_no="LIVE01")
    session.add_all([paper, live])
    await session.flush()

    strat = Strategy(name="toy", description="t")
    session.add(strat)
    await session.flush()
    active = StrategyVersion(
        strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.ACTIVE,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                    "auto_trade_enabled": True, "account_id": paper.id},
    )
    already = StrategyVersion(
        strategy_id=strat.id, version_no=2, status=StrategyVersionStatus.ARCHIVED,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "000660"},
    )
    session.add_all([active, already])

    # 노이즈 시그널 로그
    for sym in ("005930", "000660"):
        session.add(SignalLog(symbol_code=sym, signal_type=TradeSide.BUY,
                              generated_at=datetime.now(KST), price=Decimal("100"), quantity=1))

    def _trade(acc_id: int) -> Trade:
        return Trade(account_id=acc_id, symbol_code="005930", side=TradeSide.BUY,
                     quantity=1, order_status=OrderStatus.FILLED)

    def _pos(acc_id: int) -> Position:
        return Position(account_id=acc_id, symbol_code="005930", quantity=1)

    paper_trade, live_trade = _trade(paper.id), _trade(live.id)
    paper_pos, live_pos = _pos(paper.id), _pos(live.id)
    session.add_all([paper_trade, live_trade, paper_pos, live_pos])
    await session.flush()

    def _pevent(pos_id: int, trade_id: int) -> PositionEvent:
        return PositionEvent(position_id=pos_id, trade_id=trade_id,
                             event_type=PositionEventType.BUY_FILL, quantity_delta=1,
                             before_quantity=0, after_quantity=1)

    session.add_all([_pevent(paper_pos.id, paper_trade.id), _pevent(live_pos.id, live_trade.id)])
    await session.commit()
    return {"paper": paper.id, "live": live.id, "active": active.id, "already": already.id}


async def _counts(session: AsyncSession) -> dict:
    async def c(model) -> int:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())
    return {
        "signal": await c(SignalLog), "trade": await c(Trade),
        "pos": await c(Position), "pevent": await c(PositionEvent),
    }


async def test_dry_run_changes_nothing(db_session: AsyncSession) -> None:
    ids = await _seed(db_session)
    before = await _counts(db_session)

    result = await run(db_session, apply=False, reset_experiments=False)

    assert result["archive_strategy_versions"] == 1  # ACTIVE 1개만(ARCHIVED 제외)
    assert result["delete_signal_logs"] == 2
    assert result["delete_paper_trades"] == 1
    assert await _counts(db_session) == before  # 실제 변화 없음
    active = await db_session.get(StrategyVersion, ids["active"])
    assert active.status == StrategyVersionStatus.ACTIVE


async def test_apply_archives_and_resets_but_preserves_live(db_session: AsyncSession) -> None:
    ids = await _seed(db_session)

    await run(db_session, apply=True, reset_experiments=False)
    db_session.expire_all()

    # 전략: ACTIVE → ARCHIVED + auto_trade off
    active = await db_session.get(StrategyVersion, ids["active"])
    assert active.status == StrategyVersionStatus.ARCHIVED
    assert active.parameters["auto_trade_enabled"] is False

    # signal_logs 전체 삭제
    after = await _counts(db_session)
    assert after["signal"] == 0

    # PAPER 데이터 삭제, LIVE 데이터 보존
    paper_trades = (await db_session.execute(
        select(func.count()).select_from(Trade).where(Trade.account_id == ids["paper"])
    )).scalar_one()
    live_trades = (await db_session.execute(
        select(func.count()).select_from(Trade).where(Trade.account_id == ids["live"])
    )).scalar_one()
    assert paper_trades == 0
    assert live_trades == 1
    assert after["pos"] == 1  # LIVE position 1개만 남음
    assert after["pevent"] == 1  # LIVE position_event 1개만 남음
