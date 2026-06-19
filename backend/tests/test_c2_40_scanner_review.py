"""C-2.40 스캐너 룰 자동 점검 테스트."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ProposalStatus, ScannerRuleStatus
from app.domain.models.market_data import MarketData
from app.main import app
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_review_service import ScannerReviewService
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


async def _seed_weak_version(session: AsyncSession, name: str, status=ScannerRuleStatus.TESTING) -> int:
    """승률 20%(1승 4패)인 룰 버전을 만든다."""
    scanner = ScannerService(session)
    rule = await scanner.create_rule(name)
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=status,
    )
    wins = {f"{name}_0"}
    for i in range(5):
        sym = f"{name}_{i}"[:12]
        exit_close = "110" if f"{name}_{i}" in wins else "90"
        session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, exit_close)])
        session.add(CandidateEvent(
            scanner_rule_version_id=sv.id, symbol_code=sym, triggered_at=T,
            score=80, matched_conditions=["volume_spike"],
        ))
    await session.commit()
    return sv.id


async def test_review_generates_proposals_for_weak_versions(db_session: AsyncSession) -> None:
    await _seed_weak_version(db_session, "AAA")
    await _seed_weak_version(db_session, "BBB")

    summary = await ScannerReviewService(db_session).review()

    assert summary.versions_reviewed == 2
    assert summary.proposals_created == 2
    assert summary.skipped_existing == 0
    assert len(summary.created_proposal_ids) == 2


async def test_review_skips_versions_with_existing_pending(db_session: AsyncSession) -> None:
    sv_id = await _seed_weak_version(db_session, "AAA")
    service = ScannerReviewService(db_session)
    # 1차 점검 → 제안 생성
    first = await service.review()
    assert first.proposals_created == 1
    # 2차 점검 → pending이 이미 있으니 건너뛴다(중복 방지)
    second = await service.review()
    assert second.versions_reviewed == 1
    assert second.proposals_created == 0
    assert second.skipped_existing == 1
    assert sv_id  # 사용됨


async def test_review_skips_inactive_versions(db_session: AsyncSession) -> None:
    # draft 상태는 list_active에 포함되지 않아 점검 대상이 아니다.
    await _seed_weak_version(db_session, "DRF", status=ScannerRuleStatus.DRAFT)
    summary = await ScannerReviewService(db_session).review()
    assert summary.versions_reviewed == 0
    assert summary.proposals_created == 0


async def test_review_records_run(db_session: AsyncSession) -> None:
    await _seed_weak_version(db_session, "AAA")
    service = ScannerReviewService(db_session)
    await service.review_and_record()
    runs = await service.list_runs()
    assert len(runs) == 1
    assert runs[0].job_id == "scanner_review"
    assert runs[0].summary["proposals_created"] == 1


async def test_review_via_api(db_session: AsyncSession) -> None:
    await _seed_weak_version(db_session, "AAA")
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            run = await client.post("/api/v1/scanner-review/run", json={"horizon_minutes": 30})
            assert run.status_code == 201
            body = run.json()
            assert body["versions_reviewed"] == 1
            assert body["proposals_created"] == 1

            runs = await client.get("/api/v1/scanner-review/runs")
            assert runs.status_code == 200
            assert len(runs.json()) == 1

            # 생성된 제안이 pending으로 조회된다.
            proposals = await ScannerProposalService(db_session).list_proposals(
                status=ProposalStatus.PENDING
            )
            assert len(proposals) == 1
    finally:
        app.dependency_overrides.clear()
