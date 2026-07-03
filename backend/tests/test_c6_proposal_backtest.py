"""C-6.1b: 제안 생성 시 base vs proposed 백테스트 자동 첨부.

안전 검증: verdict는 참고 라벨일 뿐 제안 status를 바꾸지 않는다,
백테스트 실패/스킵이 제안 생성을 막지 않는다.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.models.enums import ProposalStatus, StrategyVersionStatus
from app.domain.models.market_data import MarketData
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.proposal_backtest_service import _verdict
from app.services.proposal_service import ProposalService

SYMBOL = "PB0001"


async def _seed_candles(session: AsyncSession, bars: int = 120) -> None:
    """now 기준 과거 bars개의 1분봉 — MA 교차가 발생하는 패턴."""
    now = datetime.now(timezone.utc)
    closes = ([100] * 30 + [100 + i * 3 for i in range(1, 31)] + [190 - i * 3 for i in range(1, 31)] + [100] * 30)[:bars]
    prev = closes[0]
    for i, c in enumerate(closes):
        session.add(
            MarketData(
                symbol_code=SYMBOL, timeframe="1m",
                ts=now - timedelta(minutes=len(closes) - i),
                open=Decimal(prev), high=Decimal(max(prev, c)),
                low=Decimal(min(prev, c)), close=Decimal(c), volume=1000,
            )
        )
        prev = c
    await session.commit()


async def _strategy_with_version(
    session: AsyncSession, params: dict
) -> tuple[Strategy, StrategyVersion]:
    strategy = Strategy(name="backtest attach test", description="t")
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1, parameters=params,
        status=StrategyVersionStatus.TESTING,
    )
    session.add(version)
    await session.commit()
    return strategy, version


_BASE_PARAMS = {
    "strategy_type": "moving_average_cross",
    "symbol_code": SYMBOL,
    "short_window": 3,
    "long_window": 5,
    "quantity": 1,
    "timeframe": "1m",
    "enabled": True,
}


@pytest.mark.asyncio
async def test_proposal_gets_backtest_summary(db_session: AsyncSession):
    await _seed_candles(db_session)
    strategy, version = await _strategy_with_version(db_session, _BASE_PARAMS)

    proposal = await ProposalService(db_session).create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={**_BASE_PARAMS, "short_window": 4, "long_window": 10},
        title="test proposal",
        base_version_id=version.id,
    )

    assert proposal.status == ProposalStatus.PENDING  # 판정은 사람 — status 불변
    s = proposal.backtest_summary
    assert s is not None and "skipped" not in s
    assert s["base"]["symbols"] == [SYMBOL]
    assert s["base"]["status"] == "succeeded"
    assert s["proposed"]["status"] == "succeeded"
    assert s["verdict"] in {"proposed_better", "base_better", "inconclusive", "insufficient_data"}
    assert "사람" in s["note"]


@pytest.mark.asyncio
async def test_universe_strategy_empty_universe_failed_leg(db_session: AsyncSession):
    """유니버스가 비어 있으면(관심종목 없음) 레그 실패 사유가 남는다."""
    params = {**_BASE_PARAMS, "symbol_code": "", "universe": "watchlist"}
    strategy, version = await _strategy_with_version(db_session, params)

    proposal = await ProposalService(db_session).create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={**params, "short_window": 4},
        title="universe proposal",
        base_version_id=version.id,
    )
    s = proposal.backtest_summary
    assert s is not None
    assert s["base"]["status"] == "failed"
    assert "해석 결과 없음" in s["base"]["error"]
    assert s["verdict"] == "insufficient_data"


@pytest.mark.asyncio
async def test_universe_strategy_aggregates_symbols(db_session: AsyncSession):
    """유니버스 전략은 종목별 백테스트를 집계한다 (C-6.1b 유니버스 지원)."""
    from app.domain.models.watchlist import Watchlist, WatchlistSymbol

    # 두 종목에 데이터 시드 + 관심종목 등록
    now = datetime.now(timezone.utc)
    for sym in ("PB0002", "PB0003"):
        closes = [100] * 30 + [100 + i * 3 for i in range(1, 31)] + [190 - i * 3 for i in range(1, 31)]
        prev = closes[0]
        for i, c in enumerate(closes):
            db_session.add(
                MarketData(
                    symbol_code=sym, timeframe="1m",
                    ts=now - timedelta(minutes=len(closes) - i),
                    open=Decimal(prev), high=Decimal(max(prev, c)),
                    low=Decimal(min(prev, c)), close=Decimal(c), volume=1000,
                )
            )
            prev = c
    wl = Watchlist(name="bt", enabled=True)
    db_session.add(wl)
    await db_session.flush()
    for sym in ("PB0002", "PB0003"):
        db_session.add(WatchlistSymbol(watchlist_id=wl.id, symbol_code=sym, market="KR", enabled=True))
    await db_session.commit()

    params = {**_BASE_PARAMS, "symbol_code": "", "universe": "watchlist"}
    strategy, version = await _strategy_with_version(db_session, params)
    proposal = await ProposalService(db_session).create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={**params, "short_window": 4},
        title="universe aggregate",
        base_version_id=version.id,
    )

    s = proposal.backtest_summary
    assert s is not None and "skipped" not in s
    assert set(s["base"]["symbols"]) == {"PB0002", "PB0003"}
    assert s["base"]["mode"] == "universe"
    assert s["base"]["symbols_used"] == 2
    assert len(s["base"]["per_symbol"]) == 2
    assert s["base"]["trade_count"] == sum(
        leg["trade_count"] for leg in s["base"]["per_symbol"]
    )


@pytest.mark.asyncio
async def test_no_base_version_skipped(db_session: AsyncSession):
    strategy, _ = await _strategy_with_version(db_session, _BASE_PARAMS)
    proposal = await ProposalService(db_session).create_proposal(
        strategy_id=strategy.id,
        suggested_parameters=_BASE_PARAMS,
        title="no base",
        base_version_id=None,
    )
    assert proposal.backtest_summary is not None
    assert "base 버전 없음" in proposal.backtest_summary["skipped"]


@pytest.mark.asyncio
async def test_gate_disabled_no_summary(db_session: AsyncSession, monkeypatch):
    await _seed_candles(db_session)
    strategy, version = await _strategy_with_version(db_session, _BASE_PARAMS)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: Settings(_env_file=None, proposal_backtest_enabled=False),
    )
    proposal = await ProposalService(db_session).create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={**_BASE_PARAMS, "short_window": 4},
        title="gated",
        base_version_id=version.id,
    )
    assert proposal.backtest_summary is None


@pytest.mark.asyncio
async def test_no_market_data_does_not_block_proposal(db_session: AsyncSession):
    """시세 데이터가 없어도 제안 생성은 성공하고 실패가 summary에 기록된다."""
    strategy, version = await _strategy_with_version(db_session, _BASE_PARAMS)
    proposal = await ProposalService(db_session).create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={**_BASE_PARAMS, "short_window": 4},
        title="no data",
        base_version_id=version.id,
    )
    assert proposal.id is not None
    s = proposal.backtest_summary
    assert s is not None
    assert s["base"]["status"] == "failed"
    assert s["verdict"] == "insufficient_data"


# ── verdict 순수 함수 ───────────────────────────────────────────────────

_OK = {"status": "succeeded", "trade_count": 10, "return_pct": 0.0}


def test_verdict_proposed_better():
    assert _verdict({**_OK}, {**_OK, "return_pct": 5.0}) == "proposed_better"


def test_verdict_base_better():
    assert _verdict({**_OK, "return_pct": 5.0}, {**_OK}) == "base_better"


def test_verdict_inconclusive_within_margin():
    assert _verdict({**_OK}, {**_OK, "return_pct": 0.5}) == "inconclusive"


def test_verdict_insufficient_trades():
    assert _verdict({**_OK, "trade_count": 2}, {**_OK, "return_pct": 9.0}) == "insufficient_data"


def test_verdict_failed_leg():
    assert _verdict({"status": "failed"}, {**_OK}) == "insufficient_data"
