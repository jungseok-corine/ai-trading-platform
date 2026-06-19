"""C-2.39 스캐너 룰 개선 제안 테스트."""

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
from app.services.scanner_proposal_generator import (
    ScannerProposalGenerator,
    tighten_conditions,
)
from app.services.scanner_proposal_service import ScannerProposalService
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


async def _seed_low_winrate(session: AsyncSession) -> int:
    """승률이 낮은(20%) 룰 버전을 만든다. 1승 4패."""
    scanner = ScannerService(session)
    rule = await scanner.create_rule("weak rule")
    sv = await scanner.create_version(
        rule.id,
        conditions=[
            {"type": "volume_spike", "params": {"multiplier": 2.0}},
            {"type": "turnover_rank", "params": {"max_rank": 100}},
        ],
        status=ScannerRuleStatus.TESTING,
    )
    # 005930만 +10%(win), 나머지 4종목은 -10%(loss).
    wins = {"005930"}
    symbols = ["005930", "000660", "035420", "051910", "006400"]
    for sym in symbols:
        exit_close = "110" if sym in wins else "90"
        session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, exit_close)])
        session.add(CandidateEvent(
            scanner_rule_version_id=sv.id, symbol_code=sym, triggered_at=T,
            score=80, matched_conditions=["volume_spike", "turnover_rank"],
        ))
    await session.commit()
    return sv.id


def test_tighten_conditions_raises_thresholds() -> None:
    result = tighten_conditions([
        {"type": "volume_spike", "params": {"multiplier": 2.0}},
        {"type": "turnover_rank", "params": {"max_rank": 100}},
        {"type": "price_change_pct", "params": {"min_pct": 5.0}},
        {"type": "time_bucket", "params": {"buckets": ["morning"]}},
    ])
    by_type = {c["type"]: c["params"] for c in result.conditions}
    assert by_type["volume_spike"]["multiplier"] == 2.6  # 2.0 * 1.3
    assert by_type["turnover_rank"]["max_rank"] == 70  # 100 * 0.7
    assert by_type["price_change_pct"]["min_pct"] == 6.5  # 5.0 * 1.3
    # 범주형 조건은 그대로 유지된다.
    assert by_type["time_bucket"]["buckets"] == ["morning"]
    assert len(result.changes) == 3  # time_bucket 제외 3개 강화


async def test_generate_proposes_tightening_on_low_winrate(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv_id)

    assert proposal is not None
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.base_version_id == sv_id
    by_type = {c["type"]: c["params"] for c in proposal.suggested_conditions}
    assert by_type["volume_spike"]["multiplier"] == 2.6
    assert by_type["turnover_rank"]["max_rank"] == 70


async def test_generate_skips_when_winrate_ok(db_session: AsyncSession) -> None:
    """승률이 기준(50%) 이상이면 제안하지 않는다."""
    scanner = ScannerService(db_session)
    rule = await scanner.create_rule("good rule")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    # 5종목 모두 win → 승률 100%.
    for i, sym in enumerate(["005930", "000660", "035420", "051910", "006400"]):
        db_session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, "110")])
        db_session.add(CandidateEvent(
            scanner_rule_version_id=sv.id, symbol_code=sym, triggered_at=T,
            score=80, matched_conditions=["volume_spike"],
        ))
    await db_session.commit()

    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv.id)
    assert proposal is None


async def test_generate_skips_when_too_few_candidates(db_session: AsyncSession) -> None:
    """분석 후보가 MIN 미만이면 제안하지 않는다."""
    scanner = ScannerService(db_session)
    rule = await scanner.create_rule("sparse rule")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    db_session.add_all([_candle("005930", 0, "100"), _candle("005930", 30, "90")])
    db_session.add(CandidateEvent(
        scanner_rule_version_id=sv.id, symbol_code="005930", triggered_at=T,
        score=80, matched_conditions=["volume_spike"],
    ))
    await db_session.commit()

    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv.id)
    assert proposal is None


async def test_approve_creates_draft_version(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    service = ScannerProposalService(db_session)
    generator = ScannerProposalGenerator(db_session)
    proposal = await generator.generate_for_version(sv_id)
    assert proposal is not None

    approved, version = await service.approve(proposal.id, reviewed_by="tester")

    assert approved.status == ProposalStatus.APPROVED
    assert approved.created_version_id == version.id
    # 승인으로 생성된 버전은 항상 DRAFT (자동 활성화 금지).
    assert version.status == ScannerRuleStatus.DRAFT
    by_type = {c["type"]: c["params"] for c in version.conditions}
    assert by_type["volume_spike"]["multiplier"] == 2.6


async def test_reject_does_not_create_version(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    service = ScannerProposalService(db_session)
    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv_id)
    assert proposal is not None

    rejected = await service.reject(proposal.id, review_note="보류")
    assert rejected.status == ProposalStatus.REJECTED
    assert rejected.created_version_id is None


async def test_proposal_lifecycle_via_api(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 생성
            gen = await client.post("/api/v1/scanner-proposals/generate",
                                    json={"version_id": sv_id, "horizon_minutes": 30})
            assert gen.status_code == 200
            pid = gen.json()["id"]

            # 상세 + diff
            detail = await client.get(f"/api/v1/scanner-proposals/{pid}")
            assert detail.status_code == 200
            diff_types = {d["type"] for d in detail.json()["diff"]}
            assert "volume_spike" in diff_types

            # 승인 → 새 버전
            approve = await client.post(f"/api/v1/scanner-proposals/{pid}/approve", json={})
            assert approve.status_code == 200
            assert approve.json()["created_version_id"] is not None

            # 재검토 시도 → 409
            again = await client.post(f"/api/v1/scanner-proposals/{pid}/approve", json={})
            assert again.status_code == 409
    finally:
        app.dependency_overrides.clear()


async def test_generate_returns_204_when_no_change_via_api(db_session: AsyncSession) -> None:
    scanner = ScannerService(db_session)
    rule = await scanner.create_rule("good rule 2")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    for sym in ["005930", "000660", "035420", "051910", "006400"]:
        db_session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, "110")])
        db_session.add(CandidateEvent(
            scanner_rule_version_id=sv.id, symbol_code=sym, triggered_at=T,
            score=80, matched_conditions=["volume_spike"],
        ))
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/scanner-proposals/generate",
                                     json={"version_id": sv.id})
            assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()
