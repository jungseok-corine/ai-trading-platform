"""C-4 유니버스 스타터 전략 시드 스크립트 테스트."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import StrategyVersion

from scripts.create_universe_strategies import run


async def _count_versions(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(StrategyVersion))).scalar_one())


async def test_dry_run_creates_nothing(db_session: AsyncSession) -> None:
    results = await run(db_session, apply=False, universe="watchlist", timeframe="5m")
    assert len(results) == 4
    assert all(r.action == "dry_run" for r in results)
    assert await _count_versions(db_session) == 0


async def test_apply_creates_four_testing_universe_strategies(db_session: AsyncSession) -> None:
    results = await run(db_session, apply=True, universe="watchlist", timeframe="5m")
    assert {r.strategy_type for r in results} == {
        "rsi_reversion", "macd_trend", "breakout_high", "pullback_trend",
    }
    assert all(r.action == "created" for r in results)

    versions = (await db_session.execute(select(StrategyVersion))).scalars().all()
    assert len(versions) == 4
    for v in versions:
        assert v.status == StrategyVersionStatus.TESTING
        assert v.parameters["universe"] == "watchlist"
        assert v.parameters["auto_trade_enabled"] is False


async def test_apply_is_idempotent(db_session: AsyncSession) -> None:
    await run(db_session, apply=True, universe="watchlist", timeframe="5m")
    results = await run(db_session, apply=True, universe="watchlist", timeframe="5m")
    assert all(r.action == "skipped_exists" for r in results)
    assert await _count_versions(db_session) == 4  # 중복 생성 안 됨
