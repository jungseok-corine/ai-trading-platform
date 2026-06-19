"""C-2.38 후보 성과 분석 테스트."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import MarketCode, ScannerRuleStatus
from app.domain.models.market_data import MarketData
from app.main import app
from app.services.candidate_outcome_service import CandidateOutcomeService
from app.services.market_context_service import MarketContextService
from app.services.scanner_service import ScannerService

KST = ZoneInfo("Asia/Seoul")
T = datetime(2026, 6, 17, 10, 0, tzinfo=KST)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


def _candle(symbol: str, minute_offset: int, close: str) -> MarketData:
    ts = T + timedelta(minutes=minute_offset)
    c = Decimal(close)
    return MarketData(symbol_code=symbol, timeframe="1m", ts=ts,
                      open=c, high=c, low=c, close=c, volume=1000)


async def _seed(session: AsyncSession) -> int:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("outcome rule")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    snap = await MarketContextService(session).create_snapshot(
        market=MarketCode.KR, time_bucket="morning"
    )

    # 005930: 10:00 종가 100 → 10:30 종가 110 (+10%, win)
    session.add_all([_candle("005930", 0, "100"), _candle("005930", 30, "110")])
    # 000660: 10:00 종가 100 → 10:30 종가 90 (-10%, loss)
    session.add_all([_candle("000660", 0, "100"), _candle("000660", 30, "90")])

    session.add(CandidateEvent(scanner_rule_version_id=sv.id, symbol_code="005930",
                               triggered_at=T, score=80, matched_conditions=["volume_spike"],
                               context_snapshot_id=snap.id))
    session.add(CandidateEvent(scanner_rule_version_id=sv.id, symbol_code="000660",
                               triggered_at=T, score=80,
                               matched_conditions=["volume_spike", "price_change_pct"],
                               context_snapshot_id=snap.id))
    await session.commit()
    return sv.id


async def test_analyze_computes_forward_returns(db_session: AsyncSession) -> None:
    await _seed(db_session)
    result = await CandidateOutcomeService(db_session).analyze(horizon_minutes=30)

    assert result.total == 2
    assert result.analyzed == 2
    assert result.overall["count"] == 2
    assert result.overall["win_rate"] == 50.0  # 1승 1패
    assert result.overall["avg_return_pct"] == 0.0  # +10, -10

    # 시간대: 둘 다 morning
    assert result.by_time_bucket["morning"]["count"] == 2
    # 조건별: volume_spike 둘 다(승률 50), price_change_pct 1개(000660, 손실 → 승률 0)
    assert result.by_condition["volume_spike"]["count"] == 2
    assert result.by_condition["price_change_pct"]["count"] == 1
    assert result.by_condition["price_change_pct"]["win_rate"] == 0.0


async def test_excludes_candidates_without_market_data(db_session: AsyncSession) -> None:
    sv_id = await _seed(db_session)
    # market_data 없는 종목 후보 추가 → analyzed에서 제외
    db_session.add(CandidateEvent(scanner_rule_version_id=sv_id, symbol_code="999999",
                                  triggered_at=T, score=50, matched_conditions=["volume_spike"]))
    await db_session.commit()

    result = await CandidateOutcomeService(db_session).analyze(horizon_minutes=30)
    assert result.total == 3
    assert result.analyzed == 2  # 999999는 데이터 없어 제외


async def test_analysis_via_api(db_session: AsyncSession) -> None:
    await _seed(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/candidates/analysis", params={"horizon_minutes": 30})
            assert resp.status_code == 200
            body = resp.json()
            assert body["analyzed"] == 2
            assert body["overall"]["win_rate"] == 50.0
    finally:
        app.dependency_overrides.clear()
