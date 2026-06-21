"""C-4: 유니버스 신호 스캔 — 종목 수동 지정 없이 스캐너 후보/관심종목 전체에 전략을 돌린다."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ScannerRuleStatus, StrategyVersionStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.services.market_data_service import MarketDataService
from app.services.scanner_service import ScannerService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.services.universe_resolver import UniverseResolver

from tests.test_strategy_runner_service import FakeBrokerClient, _make_candles

KST = ZoneInfo("Asia/Seoul")


async def _seed_candidates(session: AsyncSession, symbols: list[str], days_ago: float = 0) -> None:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("universe scan rule")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    ts = datetime.now(KST) - timedelta(days=days_ago)
    for sym in symbols:
        session.add(CandidateEvent(
            scanner_rule_version_id=sv.id, symbol_code=sym, triggered_at=ts, score=80,
        ))
    await session.commit()


# --------------------------------------------------------------------------- #
# UniverseResolver
# --------------------------------------------------------------------------- #


async def test_resolver_scanner_candidates_returns_recent_distinct(db_session: AsyncSession) -> None:
    await _seed_candidates(db_session, ["005930", "000660", "005930"], days_ago=0)
    symbols = await UniverseResolver(db_session).resolve("scanner_candidates", lookback_days=5)
    assert sorted(symbols) == ["000660", "005930"]


async def test_resolver_scanner_candidates_excludes_old(db_session: AsyncSession) -> None:
    await _seed_candidates(db_session, ["005930"], days_ago=0)
    await _seed_candidates(db_session, ["999999"], days_ago=30)
    symbols = await UniverseResolver(db_session).resolve("scanner_candidates", lookback_days=5)
    assert symbols == ["005930"]


async def test_resolver_watchlist_returns_enabled(db_session: AsyncSession) -> None:
    wl = Watchlist(name="관심", enabled=True)
    db_session.add(wl)
    await db_session.flush()
    db_session.add_all([
        WatchlistSymbol(watchlist_id=wl.id, symbol_code="005930", enabled=True),
        WatchlistSymbol(watchlist_id=wl.id, symbol_code="000660", enabled=False),
    ])
    await db_session.commit()
    symbols = await UniverseResolver(db_session).resolve("watchlist")
    assert symbols == ["005930"]


async def test_resolver_unknown_universe_returns_empty(db_session: AsyncSession) -> None:
    assert await UniverseResolver(db_session).resolve("whole_market") == []


# --------------------------------------------------------------------------- #
# Runner — 유니버스 모드
# --------------------------------------------------------------------------- #


async def _create_version(session: AsyncSession, parameters: dict) -> StrategyVersion:
    strategy = Strategy(name="universe test", description="test")
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1, parameters=parameters,
        status=StrategyVersionStatus.ACTIVE,
    )
    session.add(version)
    await session.flush()
    return version


def _runner(session: AsyncSession, broker: FakeBrokerClient) -> StrategyRunnerService:
    return StrategyRunnerService(session, SignalService(session, MarketDataService(broker)))


UNIVERSE_PARAMS = {
    "strategy_type": "moving_average_cross",
    "universe": "scanner_candidates",
    "short_window": 5,
    "long_window": 20,
    "quantity": 1,
    "enabled": True,
}


async def test_universe_mode_runs_across_candidate_symbols(db_session: AsyncSession) -> None:
    await _seed_candidates(db_session, ["005930", "000660"], days_ago=0)
    version = await _create_version(db_session, UNIVERSE_PARAMS)
    golden = _make_candles([100] * 20 + [200])
    broker = FakeBrokerClient({"005930": golden, "000660": golden})

    results = await _runner(db_session, broker).run_once()

    assert {r.symbol_code for r in results} == {"005930", "000660"}
    assert all(r.signal_created for r in results)
    assert all(r.auto_trade_enabled is False for r in results)  # universe는 항상 신호 전용
    assert all(r.strategy_version_id == version.id for r in results)

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert {row.symbol_code for row in rows} == {"005930", "000660"}


async def test_universe_mode_empty_universe_yields_no_results(db_session: AsyncSession) -> None:
    await _create_version(db_session, UNIVERSE_PARAMS)  # 후보 없음
    broker = FakeBrokerClient({})
    results = await _runner(db_session, broker).run_once()
    assert results == []
