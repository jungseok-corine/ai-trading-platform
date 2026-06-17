"""AI Analysis Input Payload (Phase C-2.0) 통합 테스트.

검증 항목:
  1. version not found → None
  2. wrong strategy_id → None
  3. strategy/version 메타데이터 포함 확인
  4. performance 섹션 포함 확인
  5. recent_signals 포함 (outcome_5m 있는 경우, 없는 경우)
  6. market_data summary 포함 확인
  7. 데이터 없는 version도 payload 생성
  8. analysis_context.limitations 포함
  9. API 404 (잘못된 조합)
  10. API 성공 + Decimal/datetime JSON 직렬화 확인
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.main import app
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ts(minute: int, hour: int = 9) -> datetime:
    return datetime(2026, 6, 10, hour, minute, 0, tzinfo=KST)


async def _add_strategy_version(
    session: AsyncSession,
    symbol: str = "005930",
) -> tuple[Strategy, StrategyVersion]:
    strat = Strategy(name="test-strategy", description="ai input test")
    session.add(strat)
    await session.flush()
    ver = StrategyVersion(
        strategy_id=strat.id,
        version_no=1,
        parameters={
            "strategy_type": "moving_average_cross",
            "symbol_code": symbol,
            "short_window": 5,
            "long_window": 20,
        },
    )
    session.add(ver)
    await session.flush()
    return strat, ver


async def _add_signal(
    session: AsyncSession,
    version_id: int,
    signal_type: TradeSide = TradeSide.BUY,
    candle_ts: datetime | None = None,
    symbol: str = "005930",
) -> SignalLog:
    sig = SignalLog(
        symbol_code=symbol,
        strategy_version_id=version_id,
        signal_type=signal_type,
        generated_at=datetime.now(KST),
        candle_ts=candle_ts or _ts(30),
    )
    session.add(sig)
    await session.flush()
    return sig


def _candle(
    session: AsyncSession,
    symbol: str = "005930",
    tf: str = "1m",
    minute: int = 0,
    hour: int = 9,
    open_: int = 100,
    close: int = 105,
) -> MarketData:
    return MarketData(
        symbol_code=symbol,
        timeframe=tf,
        ts=_ts(minute, hour=hour),
        open=Decimal(open_),
        high=Decimal(110),
        low=Decimal(90),
        close=Decimal(close),
        volume=1000,
    )


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _db_override(db_session: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. version not found / wrong strategy
# ---------------------------------------------------------------------------


async def test_analysis_input_version_not_found(db_session: AsyncSession) -> None:
    """존재하지 않는 version_id → None."""
    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strategy_id=1, version_id=99999)
    assert result is None


async def test_analysis_input_wrong_strategy(db_session: AsyncSession) -> None:
    """version_id는 존재하지만 strategy_id가 다르면 None."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strategy_id=strat.id + 999, version_id=ver.id)
    assert result is None


# ---------------------------------------------------------------------------
# 3. strategy/version 메타데이터
# ---------------------------------------------------------------------------


async def test_analysis_input_strategy_metadata(db_session: AsyncSession) -> None:
    """payload.strategy에 strategy/version 메타데이터가 올바르게 포함된다."""
    strat, ver = await _add_strategy_version(db_session, symbol="035720")
    svc = StrategyAnalysisInputService(db_session)

    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    assert result.strategy.strategy_id == strat.id
    assert result.strategy.strategy_name == strat.name
    assert result.strategy.strategy_version_id == ver.id
    assert result.strategy.version_no == ver.version_no
    assert result.strategy.status == ver.status
    assert result.strategy.parameters["symbol_code"] == "035720"


# ---------------------------------------------------------------------------
# 4. performance 섹션
# ---------------------------------------------------------------------------


async def test_analysis_input_performance_included(db_session: AsyncSession) -> None:
    """payload.performance에 성과 집계 섹션이 포함된다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisInputService(db_session)

    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    p = result.performance
    assert p.strategy_id == strat.id
    assert p.strategy_version_id == ver.id
    assert isinstance(p.total_signals, int)
    assert isinstance(p.by_horizon, list)
    assert len(p.by_horizon) == 4  # 5/15/30/60분


# ---------------------------------------------------------------------------
# 5. recent_signals (with / without outcome_5m)
# ---------------------------------------------------------------------------


async def test_analysis_input_recent_signals_without_market_data(
    db_session: AsyncSession,
) -> None:
    """market_data 없으면 recent_signals의 outcome_5m은 None이다."""
    strat, ver = await _add_strategy_version(db_session)
    await _add_signal(db_session, ver.id)

    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    assert len(result.recent_signals) == 1
    sig = result.recent_signals[0]
    assert sig.signal_id is not None
    assert sig.symbol_code == "005930"
    assert sig.signal_type == TradeSide.BUY
    assert sig.outcome_5m is None


async def test_analysis_input_recent_signals_with_outcome(db_session: AsyncSession) -> None:
    """market_data가 있으면 recent_signals에 outcome_5m이 포함된다."""
    strat, ver = await _add_strategy_version(db_session)
    candle_ts = _ts(30)
    await _add_signal(db_session, ver.id, candle_ts=candle_ts)

    # 신호 후 캔들 (entry: minute=31, horizon 5m: minute=36)
    for minute in range(31, 37):
        md = _candle(db_session, minute=minute, open_=100, close=105)
        session_add = db_session.add
        session_add(md)
    await db_session.flush()

    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    assert len(result.recent_signals) == 1
    sig = result.recent_signals[0]
    assert sig.outcome_5m is not None
    assert sig.outcome_5m.is_win is True  # BUY + close > entry → win


async def test_analysis_input_recent_signals_capped_at_20(db_session: AsyncSession) -> None:
    """recent_signals는 최대 20개로 제한된다."""
    strat, ver = await _add_strategy_version(db_session)
    for i in range(25):
        sig = SignalLog(
            symbol_code="005930",
            strategy_version_id=ver.id,
            signal_type=TradeSide.BUY,
            generated_at=_ts(i % 59, hour=9),
            candle_ts=_ts(i % 59, hour=9),
        )
        db_session.add(sig)
    await db_session.flush()

    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    assert len(result.recent_signals) <= 20


# ---------------------------------------------------------------------------
# 6. market_data summary
# ---------------------------------------------------------------------------


async def test_analysis_input_market_data_included(db_session: AsyncSession) -> None:
    """market_data가 있으면 symbols/timeframes/latest_ts/row_count가 채워진다."""
    strat, ver = await _add_strategy_version(db_session, symbol="005930")

    for minute in range(5):
        md = _candle(db_session, minute=minute)
        db_session.add(md)
    await db_session.flush()

    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    md_summary = result.market_data
    assert "005930" in md_summary.symbols
    assert "1m" in md_summary.timeframes
    assert md_summary.row_count == 5
    assert md_summary.latest_ts is not None


async def test_analysis_input_market_data_no_data(db_session: AsyncSession) -> None:
    """market_data가 없으면 symbols=[symbol_code], timeframes=[], row_count=0."""
    strat, ver = await _add_strategy_version(db_session, symbol="999999")

    svc = StrategyAnalysisInputService(db_session)
    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    assert result.market_data.symbols == ["999999"]
    assert result.market_data.timeframes == []
    assert result.market_data.row_count == 0
    assert result.market_data.latest_ts is None


# ---------------------------------------------------------------------------
# 7. 데이터 없는 version도 payload 생성
# ---------------------------------------------------------------------------


async def test_analysis_input_empty_version(db_session: AsyncSession) -> None:
    """신호/market_data/거래 모두 없어도 payload가 생성된다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisInputService(db_session)

    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    assert result.performance.total_signals == 0
    assert result.recent_signals == []
    assert result.market_data.row_count == 0
    assert result.performance.actual_trading is not None  # 거래 없어도 actual_trading 객체는 존재


# ---------------------------------------------------------------------------
# 8. analysis_context.limitations
# ---------------------------------------------------------------------------


async def test_analysis_input_context_limitations(db_session: AsyncSession) -> None:
    """analysis_context에 generated_at과 limitations 목록이 포함된다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisInputService(db_session)

    result = await svc.get_analysis_input(strat.id, ver.id)

    assert result is not None
    ctx = result.analysis_context
    assert ctx.generated_at is not None
    assert len(ctx.limitations) >= 3
    assert any("pnl_amount" in lim for lim in ctx.limitations)
    assert any("financial advice" in lim for lim in ctx.limitations)


# ---------------------------------------------------------------------------
# 9. API 404
# ---------------------------------------------------------------------------


async def test_api_analysis_input_404(db_session: AsyncSession) -> None:
    """존재하지 않는 strategy_id/version_id 조합은 404를 반환한다."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/strategies/9999/versions/9999/analysis-input")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. API 성공 + JSON 직렬화
# ---------------------------------------------------------------------------


async def test_api_analysis_input_success_serialization(db_session: AsyncSession) -> None:
    """API가 200을 반환하고 Decimal/datetime이 JSON으로 올바르게 직렬화된다."""
    strat, ver = await _add_strategy_version(db_session)

    # 캔들 추가 (market_data)
    for minute in range(3):
        db_session.add(_candle(db_session, minute=minute))
    await db_session.flush()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-input"
        )

    assert resp.status_code == 200
    body = resp.json()

    # 최상위 섹션 존재 확인
    assert "strategy" in body
    assert "performance" in body
    assert "market_data" in body
    assert "recent_signals" in body
    assert "analysis_context" in body

    # strategy 메타데이터
    assert body["strategy"]["strategy_id"] == strat.id
    assert body["strategy"]["strategy_name"] == strat.name
    assert body["strategy"]["strategy_version_id"] == ver.id

    # performance — Decimal이 문자열로 직렬화됐는지 확인
    by_horizon = body["performance"]["by_horizon"]
    assert len(by_horizon) == 4
    h5 = next(h for h in by_horizon if h["horizon_minutes"] == 5)
    # count=0이어도 win_rate, avg_return_pct 키 존재
    assert "win_rate" in h5
    assert "avg_directional_return_pct" in h5

    # market_data
    assert body["market_data"]["symbols"] == ["005930"]
    assert body["market_data"]["row_count"] == 3

    # analysis_context
    ctx = body["analysis_context"]
    assert "generated_at" in ctx
    assert isinstance(ctx["limitations"], list)
    assert len(ctx["limitations"]) >= 3
