"""Paper Experiment Readiness Gate 테스트 (readiness-only).

'준비 승인'은 어떤 상태도 바꾸지 않는다:
- StrategyVersion.status = DRAFT 유지 (runner의 list_active 대상 아님 → 신호 생성 없음)
- Experiment.status = DRAFT 유지, started_at = null 유지
- signal_logs / Trade / StrategyAssignmentLog 미생성, 브로커/주문 호출 없음
- 승인 사실만 제안의 suggested_parameters에 기록.
"""
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import ExperimentStatus, StrategyVersionStatus
from app.domain.models.experiment import Experiment
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.candidate_proposal_experiment_service import (
    CandidateProposalExperimentService,
    ConfirmationRequiredError,
    NotPreparedError,
    ProposalNotApprovedError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _seed_proposal(session: AsyncSession, status: str = "approved") -> CandidateStrategyProposal:
    rule = ScannerRule(name="ReadyRule")
    session.add(rule)
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id, symbol_code="005930",
        triggered_at=datetime.now(timezone.utc), score=90, matched_conditions=["turnover_rank"],
    )
    session.add(cand)
    await session.flush()
    prop = CandidateStrategyProposal(
        candidate_event_id=cand.id, symbol_code="005930",
        suggested_strategy_type="breakout_high", status=status, source="manual",
    )
    session.add(prop)
    await session.flush()
    return prop


async def _approved_and_prepared(session: AsyncSession) -> CandidateStrategyProposal:
    prop = await _seed_proposal(session, status="approved")
    await CandidateProposalExperimentService(session).prepare(prop.id)
    await session.refresh(prop)
    return prop


# --- gate validation ---------------------------------------------------------
async def test_requires_confirmed_true(db_session: AsyncSession) -> None:
    prop = await _approved_and_prepared(db_session)
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.approve_paper_testing_readiness(prop.id, confirmed=False, confirmed_by="u")
        assert False, "expected ConfirmationRequiredError"
    except ConfirmationRequiredError:
        pass


async def test_requires_confirmed_by(db_session: AsyncSession) -> None:
    prop = await _approved_and_prepared(db_session)
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by=None)
        assert False, "expected ConfirmationRequiredError"
    except ConfirmationRequiredError:
        pass


async def test_pending_proposal_cannot_approve(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="pending")
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by="u")
        assert False, "expected ProposalNotApprovedError"
    except ProposalNotApprovedError:
        pass


async def test_rejected_proposal_cannot_approve(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="rejected")
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by="u")
        assert False, "expected ProposalNotApprovedError"
    except ProposalNotApprovedError:
        pass


async def test_unprepared_proposal_cannot_approve(db_session: AsyncSession) -> None:
    prop = await _seed_proposal(db_session, status="approved")  # approved but not prepared
    svc = CandidateProposalExperimentService(db_session)
    try:
        await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by="u")
        assert False, "expected NotPreparedError"
    except NotPreparedError:
        pass


# --- happy path: NO status change -------------------------------------------
async def test_readiness_does_not_change_any_status(db_session: AsyncSession) -> None:
    prop = await _approved_and_prepared(db_session)
    before_signals = await _count(db_session, SignalLog)
    before_trades = await _count(db_session, Trade)
    before_logs = await _count(db_session, StrategyAssignmentLog)

    svc = CandidateProposalExperimentService(db_session)
    result = await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by="tester")

    assert result.ready is True
    assert result.already_ready is False
    assert result.ready_by == "tester"
    assert result.ready_at is not None
    # 반환 상태가 DRAFT 그대로
    assert result.experiment_status == StrategyVersionStatus.DRAFT.value
    assert all(s == StrategyVersionStatus.DRAFT.value for s in result.strategy_version_statuses)
    assert all(v is False for v in result.auto_trade_enabled_values)

    # DB 실제 상태: 실험 DRAFT, started_at null
    experiment = await db_session.get(Experiment, result.experiment_id)
    assert experiment.status == ExperimentStatus.DRAFT
    assert experiment.started_at is None

    # 버전은 DRAFT 그대로
    for vid in result.strategy_version_ids:
        ver = await db_session.get(StrategyVersion, vid)
        assert ver.status == StrategyVersionStatus.DRAFT
        assert ver.parameters.get("auto_trade_enabled") is False

    # 승인 메타가 제안에 기록됨(상태 전환 없이)
    await db_session.refresh(prop)
    assert prop.suggested_parameters.get("_paper_testing_ready_at") is not None
    assert prop.suggested_parameters.get("_paper_testing_ready_by") == "tester"

    # 어떤 실행 흔적도 없음
    assert await _count(db_session, SignalLog) == before_signals
    assert await _count(db_session, Trade) == before_trades
    assert await _count(db_session, StrategyAssignmentLog) == before_logs


async def test_runner_cannot_pick_up_after_readiness(db_session: AsyncSession) -> None:
    """승인 후에도 runner의 list_active(ACTIVE/TESTING) 대상 버전이 0이어야 한다."""
    prop = await _approved_and_prepared(db_session)
    await CandidateProposalExperimentService(db_session).approve_paper_testing_readiness(
        prop.id, confirmed=True, confirmed_by="u"
    )
    runnable = (
        await db_session.execute(
            select(func.count()).select_from(StrategyVersion).where(
                StrategyVersion.status.in_(
                    [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                )
            )
        )
    ).scalar_one()
    assert runnable == 0  # runner가 잡을 수 있는 버전 없음


async def test_readiness_is_idempotent(db_session: AsyncSession) -> None:
    prop = await _approved_and_prepared(db_session)
    svc = CandidateProposalExperimentService(db_session)
    r1 = await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by="u1")
    r2 = await svc.approve_paper_testing_readiness(prop.id, confirmed=True, confirmed_by="u2")
    assert r1.already_ready is False
    assert r2.already_ready is True
    # 최초 승인 시각/승인자 유지
    assert r2.ready_at == r1.ready_at
    assert r2.ready_by == "u1"
    # 여전히 DRAFT
    assert all(s == StrategyVersionStatus.DRAFT.value for s in r2.strategy_version_statuses)


# --- API ---------------------------------------------------------------------
async def test_api_approve_readiness(db_session: AsyncSession) -> None:
    prop = await _approved_and_prepared(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = f"/api/v1/candidate-strategy-proposals/{prop.id}/approve-paper-readiness"
            # missing confirmed -> 422
            r = await client.post(base, json={"confirmed": False, "confirmed_by": "u"})
            assert r.status_code == 422
            # missing confirmed_by -> 422
            r = await client.post(base, json={"confirmed": True})
            assert r.status_code == 422
            # ok -> 200, status unchanged (draft)
            r = await client.post(base, json={"confirmed": True, "confirmed_by": "tester"})
            assert r.status_code == 200
            body = r.json()
            assert body["ready"] is True
            assert body["experiment_status"] == "draft"
            assert all(s == "draft" for s in body["strategy_version_statuses"])
            assert all(v is False for v in body["auto_trade_enabled_values"])
    finally:
        app.dependency_overrides.clear()
