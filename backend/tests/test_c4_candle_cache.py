"""C-4.9: run_once 내 종목별 캔들 캐시 — 여러 전략이 같은 종목 캔들을 1회만 조회."""
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.trading.broker.schemas import MinuteCandle

from tests.test_strategy_runner_service import FakeBrokerClient, _make_candles


class CountingBroker(FakeBrokerClient):
    """get_minute_candles 호출을 종목별로 센다."""

    def __init__(self, candles_by_symbol: dict[str, list[MinuteCandle]]) -> None:
        super().__init__(candles_by_symbol)
        self.calls: Counter[str] = Counter()

    async def get_minute_candles(self, symbol_code, target_time=None, include_past_data=True):
        self.calls[symbol_code] += 1
        return await super().get_minute_candles(symbol_code, target_time, include_past_data)


async def _make_version(session: AsyncSession, symbol: str, short: int, long: int) -> None:
    strat = Strategy(name=f"s-{short}-{long}", description="t")
    session.add(strat)
    await session.flush()
    session.add(StrategyVersion(
        strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.ACTIVE,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": symbol,
                    "short_window": short, "long_window": long, "enabled": True},
    ))
    await session.flush()


async def test_candles_fetched_once_per_symbol_across_strategies(db_session: AsyncSession) -> None:
    # 같은 종목(005930)에 전략 3개 + 다른 종목(000660)에 1개
    await _make_version(db_session, "005930", 5, 20)
    await _make_version(db_session, "005930", 3, 10)
    await _make_version(db_session, "005930", 2, 8)
    await _make_version(db_session, "000660", 5, 20)
    await db_session.commit()

    candles = _make_candles([100] * 20 + [200])
    broker = CountingBroker({"005930": candles, "000660": candles})
    runner = StrategyRunnerService(db_session, SignalService(db_session, MarketDataService(broker)))

    results = await runner.run_once()

    # 전략은 4번 실행되지만 캔들 조회는 종목당 1회만
    assert len(results) == 4
    assert broker.calls["005930"] == 1  # 전략 3개가 공유 (캐시 전이라면 3이었을 것)
    assert broker.calls["000660"] == 1
