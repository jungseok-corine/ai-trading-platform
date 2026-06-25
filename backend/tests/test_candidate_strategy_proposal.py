"""Candidate Strategy Proposal (PENDING) V1 테스트.

제안만 한다 — StrategyVersion / StrategyAssignmentLog / Trade를 만들지 않고,
auto_trade를 건드리지 않는다.
"""
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.candidate_strategy_proposal_service import (
    CandidateNotFoundError,
    CandidateStrategyProposalService,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed_candidate(
    session: AsyncSession,
    symbol: str = "005930",
    score: int = 80,
    matched: list | None = None,
) -> CandidateEvent:
    rule = ScannerRule(name="ProposalRule")
    session.add(rule)
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id,
        symbol_code=symbol,
        triggered_at=datetime.now(timezone.utc),
        score=score,
        matched_conditions=matched if matched is not None else ["volume_spike"],
    )
    session.add(cand)
    await session.flush()
    return cand


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_create_proposal_is_pending(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    p = await svc.create(cand.id)

    assert p.status == "pending"
    assert p.candidate_event_id == cand.id
    assert p.symbol_code == "005930"
    # volume_spike → 거래량 확인형 전략으로 유추
    assert p.suggested_strategy_type == "volume_confirmed_ma_cross"
    assert p.rationale is not None
    assert p.confidence == 0.8  # score 80 → 0.80


async def test_create_proposal_stores_explicit_fields(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session, matched=["price_change_pct"])
    svc = CandidateStrategyProposalService(db_session)
    p = await svc.create(
        cand.id,
        suggested_strategy_type="momentum_surge",
        rationale="명시적 근거",
        confidence=0.9,
        suggested_parameters={"fast": 5, "slow": 20},
    )
    assert p.suggested_strategy_type == "momentum_surge"
    assert p.rationale == "명시적 근거"
    assert p.confidence == 0.9
    assert p.suggested_parameters == {"fast": 5, "slow": 20}


async def test_suggested_parameters_strips_auto_trade(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    p = await svc.create(
        cand.id,
        suggested_strategy_type="moving_average_cross",
        suggested_parameters={"auto_trade_enabled": True, "fast": 5},
    )
    assert "auto_trade_enabled" not in (p.suggested_parameters or {})
    assert p.suggested_parameters == {"fast": 5}


async def test_unknown_candidate_raises(db_session: AsyncSession) -> None:
    svc = CandidateStrategyProposalService(db_session)
    try:
        await svc.create(999999)
        assert False, "expected CandidateNotFoundError"
    except CandidateNotFoundError:
        pass


async def test_invalid_strategy_type_raises(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    try:
        await svc.create(cand.id, suggested_strategy_type="not_a_real_strategy")
        assert False, "expected InvalidStrategyTypeError"
    except Exception as e:  # noqa: BLE001
        assert "unknown strategy_type" in str(e)


async def test_duplicate_pending_returns_existing(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    p1 = await svc.create(cand.id, suggested_strategy_type="moving_average_cross")
    p2 = await svc.create(cand.id, suggested_strategy_type="moving_average_cross")
    assert p1.id == p2.id  # 중복 PENDING은 기존 것을 반환
    assert await _count(db_session, CandidateStrategyProposal) == 1


async def test_list_for_candidate(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    await svc.create(cand.id, suggested_strategy_type="moving_average_cross")
    await svc.create(cand.id, suggested_strategy_type="momentum_surge")
    listed = await svc.list_for_candidate(cand.id)
    assert len(listed) == 2


async def test_create_does_not_create_version_log_or_trade(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    before_versions = await _count(db_session, StrategyVersion)
    before_logs = await _count(db_session, StrategyAssignmentLog)
    before_trades = await _count(db_session, Trade)

    await CandidateStrategyProposalService(db_session).create(cand.id)

    assert await _count(db_session, StrategyVersion) == before_versions
    assert await _count(db_session, StrategyAssignmentLog) == before_logs
    assert await _count(db_session, Trade) == before_trades


async def test_review_only_updates_status(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    p = await svc.create(cand.id)
    before_versions = await _count(db_session, StrategyVersion)

    reviewed = await svc.review(p.id, status="approved", reviewed_by="tester", review_note="ok")
    assert reviewed.status == "approved"
    assert reviewed.reviewed_by == "tester"
    assert reviewed.reviewed_at is not None
    # 승인해도 실행/버전 생성 없음
    assert await _count(db_session, StrategyVersion) == before_versions


async def test_review_rejects_invalid_status(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    svc = CandidateStrategyProposalService(db_session)
    p = await svc.create(cand.id)
    try:
        await svc.review(p.id, status="active")  # 허용되지 않는 상태
        assert False, "expected InvalidReviewStatusError"
    except Exception as e:  # noqa: BLE001
        assert e.__class__.__name__ == "InvalidReviewStatusError"


# --- API ---------------------------------------------------------------------
async def test_api_create_and_list(db_session: AsyncSession) -> None:
    cand = await _seed_candidate(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/candidates/{cand.id}/strategy-proposals", json={}
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["status"] == "pending"
            assert body["candidate_event_id"] == cand.id

            listed = await client.get(
                f"/api/v1/candidates/{cand.id}/strategy-proposals"
            )
            assert listed.status_code == 200
            assert len(listed.json()) == 1

            recent = await client.get("/api/v1/candidate-strategy-proposals?status=pending")
            assert recent.status_code == 200
            assert len(recent.json()) >= 1
    finally:
        app.dependency_overrides.clear()


async def test_api_unknown_candidate_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/candidates/999999/strategy-proposals", json={}
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
