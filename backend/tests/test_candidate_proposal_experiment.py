"""APPROVED 후보 전략 제안 → Paper 실험 '준비'(DRAFT) 테스트.

준비는 실행이 아니다 — StrategyVersion/Experiment 모두 DRAFT, auto_trade=False,
StrategyAssignmentLog/Trade 미생성.
"""
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import ExperimentStatus, StrategyVersionStatus
from app.domain.models.experiment import Experiment, ExperimentVariant
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.candidate_proposal_experiment_service import (
    CandidateProposalExperimentService,
    ProposalNotApprovedError,
    ProposalNotFoundError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _seed_proposal(
    session: AsyncSession, status: str = "approved", strategy_type: str = "breakout_high"
) -> CandidateStrategyProposal:
    rule = ScannerRule(name="ExpPrepRule")
    session.add(rule)
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id, symbol_code="005930",
        triggered_at=datetime.now(timezone.utc), score=90,
        matched_conditions=["turnover_rank"],
    )
    session.add(cand)
    await session.flush()
    prop = CandidateStrategyProposal(
        candidate_event_id=cand.id, symbol_code="005930",
        suggested_strategy_type=strategy_type, status=status, source="manual",
        suggested_parameters={"fast": 5},
    )
    session.add(prop)
    await session.flush()
    return prop


async def test_pending_proposal_cannot_prepare(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="pending")
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.prepare(prop.id)
        assert False, "expected ProposalNotApprovedError"
    except ProposalNotApprovedError:
        pass
    assert await _count(db_session, Experiment) == 0


async def test_rejected_proposal_cannot_prepare(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="rejected")
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.prepare(prop.id)
        assert False, "expected ProposalNotApprovedError"
    except ProposalNotApprovedError:
        pass
    assert await _count(db_session, Experiment) == 0


async def test_unknown_proposal_raises(db_session: AsyncSession) -> None:
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.prepare(999999)
        assert False, "expected ProposalNotFoundError"
    except ProposalNotFoundError:
        pass


async def test_approved_prepares_draft_experiment(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="approved")
    before_logs = await _count(db_session, StrategyAssignmentLog)
    before_trades = await _count(db_session, Trade)

    svc = CandidateProposalExperimentService(db_session)
    result = await svc.prepare(prop.id)

    # 실험/버전은 DRAFT, auto_trade=False
    assert result.experiment_status == ExperimentStatus.DRAFT.value
    assert result.strategy_version_status == StrategyVersionStatus.DRAFT.value
    assert result.auto_trade_enabled is False
    assert result.already_prepared is False

    # 실제 DB 상태 확인
    exp = await db_session.get(Experiment, result.experiment_id)
    assert exp.status == ExperimentStatus.DRAFT  # RUNNING 아님
    assert exp.started_at is None  # 실행 시작 안 함

    ver = await db_session.get(StrategyVersion, result.strategy_version_id)
    assert ver.status == StrategyVersionStatus.DRAFT  # ACTIVE/TESTING 아님
    assert ver.parameters.get("auto_trade_enabled") is False

    # variant 연결됨
    assert await _count(db_session, ExperimentVariant) == 1

    # 제안에 역추적 링크
    await db_session.refresh(prop)
    assert prop.experiment_id == result.experiment_id
    assert prop.prepared_at is not None

    # 실행 흔적 없음
    assert await _count(db_session, StrategyAssignmentLog) == before_logs
    assert await _count(db_session, Trade) == before_trades


async def test_prepare_is_idempotent(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="approved")
    svc = CandidateProposalExperimentService(db_session)
    r1 = await svc.prepare(prop.id)
    r2 = await svc.prepare(prop.id)
    assert r2.already_prepared is True
    assert r1.experiment_id == r2.experiment_id
    assert await _count(db_session, Experiment) == 1  # 두 번째 호출이 새 실험을 안 만듦


async def test_no_active_or_testing_version_created(db_session: AsyncSession) -> None:
    """runner의 list_active는 ACTIVE/TESTING만 잡으므로, 준비 버전이 거기 안 들어가야 한다."""
    prop = await _seed_proposal(db_session, status="approved")
    await CandidateProposalExperimentService(db_session).prepare(prop.id)
    runnable = (
        await db_session.execute(
            select(func.count()).select_from(StrategyVersion).where(
                StrategyVersion.status.in_(
                    [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                )
            )
        )
    ).scalar_one()
    assert runnable == 0


# --- API ---------------------------------------------------------------------
async def test_api_prepare_approved(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="approved")
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/candidate-strategy-proposals/{prop.id}/prepare-paper-experiment"
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["experiment_status"] == "draft"
            assert body["strategy_version_status"] == "draft"
            assert body["auto_trade_enabled"] is False
            assert body["proposal_id"] == prop.id
    finally:
        app.dependency_overrides.clear()


async def test_api_prepare_pending_returns_422(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="pending")
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/candidate-strategy-proposals/{prop.id}/prepare-paper-experiment"
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
