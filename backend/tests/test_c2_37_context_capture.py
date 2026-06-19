"""C-2.37 시장 맥락 캡처 + 후보 연결 테스트."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import MarketCode, ScannerRuleStatus
from app.domain.models.investor_flow import InvestorFlow
from app.domain.models.market_context import MarketContextSnapshot
from app.domain.models.market_data import MarketData
from app.domain.models.news_context import UsMarketSnapshot
from app.services.market_context_capture_service import MarketContextCaptureService
from app.services.research_pipeline_service import ResearchPipelineService
from app.services.scanner_service import ScannerService


async def test_capture_includes_time_bucket_and_us(db_session: AsyncSession) -> None:
    db_session.add(UsMarketSnapshot(session_date=datetime(2026, 6, 18).date(),
                                    nasdaq_change_pct=Decimal("1.2")))
    await db_session.commit()

    snap = await MarketContextCaptureService(db_session).capture(
        market=MarketCode.KR, now=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc)
    )
    assert snap.id is not None
    assert snap.time_bucket is not None
    assert snap.us_previous_session is not None
    assert snap.us_previous_session["session_date"] == "2026-06-18"


async def _seed_for_pipeline(session: AsyncSession) -> None:
    base = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)
    for i in range(25):
        close = Decimal("110") if i == 24 else Decimal("100")
        vol = 5000 if i == 24 else 1000
        session.add(MarketData(symbol_code="005930", timeframe="1m", ts=base.replace(minute=i),
                               open=close, high=close, low=close, close=close, volume=vol))
    session.add(InvestorFlow(symbol_code="005930", trade_date=datetime(2026, 6, 16).date(),
                             foreign_net_buy_quantity=10000))
    await session.commit()
    scanner = ScannerService(session)
    rule = await scanner.create_rule("ctx rule")
    await scanner.create_version(
        rule.id,
        conditions=[
            {"type": "volume_spike", "params": {"multiplier": 2.0}},
            {"type": "price_change_pct", "params": {"min_pct": 5.0}},
        ],
        status=ScannerRuleStatus.TESTING,
    )


async def test_pipeline_links_candidates_to_context(db_session: AsyncSession) -> None:
    await _seed_for_pipeline(db_session)
    summary = await ResearchPipelineService(db_session).run_once(symbol_codes=["005930"])

    assert summary.candidates == 1
    assert summary.context_snapshot_id is not None

    # 후보가 그 스냅샷에 연결됐는지
    candidates = (await db_session.execute(select(CandidateEvent))).scalars().all()
    assert len(candidates) == 1
    assert candidates[0].context_snapshot_id == summary.context_snapshot_id

    # 스냅샷이 실제로 존재
    snap = await db_session.get(MarketContextSnapshot, summary.context_snapshot_id)
    assert snap is not None
    assert snap.time_bucket is not None


async def test_no_snapshot_when_no_active_versions(db_session: AsyncSession) -> None:
    # active 버전 없음 → 캡처도 안 함
    summary = await ResearchPipelineService(db_session).run_once(symbol_codes=["005930"])
    assert summary.versions == 0
    assert summary.context_snapshot_id is None
    snaps = (await db_session.execute(select(MarketContextSnapshot))).scalars().all()
    assert len(snaps) == 0
