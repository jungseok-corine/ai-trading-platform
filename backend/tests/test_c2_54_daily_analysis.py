"""C-2.54 일일 AI 분석 잡 + 활동량 게이트 테스트 (fake provider, 네트워크 없음)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import StrategyVersionStatus, TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.main import app
from app.services.daily_analysis_service import DailyAnalysisService
from app.services.strategy_service import StrategyService
from app.trading.analysis.activity import (
    BAND_EXCESSIVE,
    BAND_NONE_QUIET,
    BAND_NORMAL,
    BAND_SPARSE,
    assess_activity,
)

KST = ZoneInfo("Asia/Seoul")
DAY = date(2026, 6, 17)
T0 = datetime(2026, 6, 17, 10, 0, tzinfo=KST)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


# --- 활동량 게이트(순수) ----------------------------------------------------
def test_assess_none_quiet_skips() -> None:
    a = assess_activity(0, range_pct=0.5, notable_count=0)
    assert a.band == BAND_NONE_QUIET
    assert a.should_analyze is False


def test_assess_sparse_but_active_analyzes() -> None:
    # 신호 0인데 시장은 활발(레인지 5%) → 조건 과빡 의심 → 분석
    a = assess_activity(0, range_pct=5.0, notable_count=4)
    assert a.band == BAND_SPARSE
    assert a.should_analyze is True
    assert a.market_active is True
    assert "미발화" in a.reason


def test_assess_normal_and_excessive() -> None:
    assert assess_activity(8, 1.0, 0).band == BAND_NORMAL
    assert assess_activity(40, 1.0, 0).band == BAND_EXCESSIVE


# --- 서비스 (fake provider) -------------------------------------------------
async def _seed_active_version(session, name, symbol, n_signals) -> int:
    svc = StrategyService(session)
    strategy = await svc.create_strategy(name)
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": symbol,
                    "long_window": 20},
        status=StrategyVersionStatus.TESTING,
    )
    for i in range(n_signals):
        session.add(SignalLog(symbol_code=symbol, signal_type=TradeSide.BUY,
                              generated_at=T0 + timedelta(minutes=i),
                              strategy_version_id=version.id))
    await session.commit()
    return version.id


async def test_run_once_analyzes_active_skips_quiet(db_session: AsyncSession) -> None:
    # v1: 신호 5건 + 시장데이터 → 분석. v2: 무신호 + 데이터 없음 → skip.
    v1 = await _seed_active_version(db_session, "active", "005930", 5)
    for i in range(20):
        px = Decimal("100") + Decimal(i) / 10
        db_session.add(MarketData(symbol_code="005930", timeframe="1m",
                                  ts=T0 + timedelta(minutes=i), open=px, high=px + 1,
                                  low=px - 1, close=px, volume=1000))
    await _seed_active_version(db_session, "quiet", "999999", 0)
    await db_session.commit()

    summary = await DailyAnalysisService(db_session).run_once(trading_day=DAY)
    assert summary.versions == 2
    assert summary.analyzed == 1
    assert summary.skipped == 1
    analyzed = next(v for v in summary.per_version if v.strategy_version_id == v1)
    assert analyzed.analyzed is True
    assert analyzed.run_id is not None
    assert analyzed.run_status == "succeeded"  # fake provider


async def test_run_and_record_history(db_session: AsyncSession) -> None:
    await _seed_active_version(db_session, "active", "005930", 5)
    svc = DailyAnalysisService(db_session)
    await svc.run_and_record(trading_day=DAY)
    runs = await svc.list_runs()
    assert len(runs) == 1
    assert runs[0].job_id == "daily_analysis"
    assert runs[0].summary["analyzed"] == 1


async def test_run_via_api(db_session: AsyncSession) -> None:
    await _seed_active_version(db_session, "active", "005930", 5)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/daily-analysis/run",
                                     params={"trading_day": "2026-06-17"})
            assert resp.status_code == 201
            body = resp.json()
            assert body["analyzed"] == 1
            assert body["mode"] == "single"
            assert body["provider"] == "fake"

            runs = await client.get("/api/v1/daily-analysis/runs")
            assert runs.status_code == 200
            assert len(runs.json()) == 1
    finally:
        app.dependency_overrides.clear()
