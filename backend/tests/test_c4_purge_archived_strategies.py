"""C-4 아카이브 전략 하드 삭제 스크립트 테스트 (살아있는 버전 보존 + SET NULL 검증)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, StrategyVersionStatus, TradeSide
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade

from scripts.purge_archived_strategies import run


async def _seed(session: AsyncSession) -> dict:
    # (1) 전부 ARCHIVED → 삭제 대상
    toy = Strategy(name="토이", description="t")
    # (2) 살아있는 TESTING 버전 보유 → 보존
    keep = Strategy(name="유니버스 RSI", description="t")
    # (3) 버전 0개 빈 껍데기 → 삭제 대상
    empty = Strategy(name="빈 전략", description="t")
    session.add_all([toy, keep, empty])
    await session.flush()

    session.add_all([
        StrategyVersion(strategy_id=toy.id, version_no=1, parameters={"symbol_code": "005930"},
                        status=StrategyVersionStatus.ARCHIVED),
        StrategyVersion(strategy_id=toy.id, version_no=2, parameters={"symbol_code": "005930"},
                        status=StrategyVersionStatus.ARCHIVED),
        StrategyVersion(strategy_id=keep.id, version_no=1, parameters={"universe": "watchlist"},
                        status=StrategyVersionStatus.TESTING),
    ])
    # toy 버전을 참조하는 trade → 삭제 시 SET NULL 되어야 함
    acc = Account(account_type=AccountType.PAPER, broker_account_no="P1")
    session.add(acc)
    await session.flush()
    toy_v1 = (await session.execute(
        select(StrategyVersion).where(StrategyVersion.strategy_id == toy.id).limit(1)
    )).scalar_one()
    trade = Trade(account_id=acc.id, strategy_version_id=toy_v1.id, symbol_code="005930",
                  side=TradeSide.BUY, quantity=1, order_status=OrderStatus.FILLED)
    session.add(trade)
    await session.commit()
    return {"toy": toy.id, "keep": keep.id, "empty": empty.id, "trade": trade.id}


async def test_dry_run_lists_but_deletes_nothing(db_session: AsyncSession) -> None:
    ids = await _seed(db_session)
    targets = await run(db_session, apply=False)
    target_ids = {t.strategy_id for t in targets}
    assert ids["toy"] in target_ids
    assert ids["empty"] in target_ids
    assert ids["keep"] not in target_ids  # 살아있는 버전 보유 → 제외
    # 아무것도 삭제 안 됨
    assert await db_session.get(Strategy, ids["toy"]) is not None


async def test_apply_deletes_targets_keeps_live_and_nulls_trade(db_session: AsyncSession) -> None:
    ids = await _seed(db_session)
    await run(db_session, apply=True)
    db_session.expire_all()

    assert await db_session.get(Strategy, ids["toy"]) is None
    assert await db_session.get(Strategy, ids["empty"]) is None
    assert await db_session.get(Strategy, ids["keep"]) is not None  # 보존

    # toy 버전 CASCADE 삭제
    remaining = (await db_session.execute(
        select(func.count()).select_from(StrategyVersion)
        .where(StrategyVersion.strategy_id == ids["toy"])
    )).scalar_one()
    assert remaining == 0

    # 참조 trade는 보존되되 strategy_version_id가 NULL
    trade = await db_session.get(Trade, ids["trade"])
    assert trade is not None
    assert trade.strategy_version_id is None
