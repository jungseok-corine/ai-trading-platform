"""M1: Paper Signal 분석 run → PENDING StrategyProposal 초안 테스트.

PENDING 제안만 만든다 — 승인/버전 생성/실험/세션/주문 변경 없음.
"""
import json
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import (
    AnalysisRunMode,
    AnalysisRunStatus,
    AnalysisRunType,
    AnalysisTargetType,
    ExperimentStatus,
    ProposalStatus,
    StrategyVersionStatus,
)
from app.domain.models.experiment import Experiment
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.models.trade import Trade
from app.main import app
from app.services.paper_signal_improvement_proposal_service import (
    ConfirmationRequiredError,
    DuplicatePendingProposalError,
    InvalidTargetTypeError,
    MissingVersionLinkError,
    NoReportContentError,
    PaperSignalImprovementProposalService,
    RunNotFoundError,
    RunNotSucceededError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _chain(db: AsyncSession) -> PaperSignalSession:
    rule = ScannerRule(name="ImpRule")
    db.add(rule)
    await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    db.add(rv)
    await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code="005930",
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand)
    await db.flush()
    strat = Strategy(name="ImpStrat", description="t")
    db.add(strat)
    await db.flush()
    ver = StrategyVersion(strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.DRAFT,
                          parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                                      "auto_trade_enabled": False})
    db.add(ver)
    await db.flush()
    exp = Experiment(name="ImpExp", status=ExperimentStatus.DRAFT)
    db.add(exp)
    await db.flush()
    sess = PaperSignalSession(candidate_strategy_proposal_id=1, experiment_id=exp.id,
                              strategy_version_id=ver.id, candidate_event_id=cand.id,
                              symbol_code="005930", status="active", started_by="t")
    # candidate_strategy_proposal_id requires an existing proposal row
    prop = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code="005930",
                                     suggested_strategy_type="moving_average_cross", status="approved", source="manual")
    db.add(prop)
    await db.flush()
    sess.candidate_strategy_proposal_id = prop.id
    db.add(sess)
    await db.flush()
    return sess


async def _make_run(db, sess, *, status=AnalysisRunStatus.SUCCEEDED, content="markdown report ...",
                    target_type=AnalysisTargetType.PAPER_SIGNAL_SESSION, strategy_version_id="__use__"):
    vid = sess.strategy_version_id if strategy_version_id == "__use__" else strategy_version_id
    run = AiAnalysisRun(
        analysis_type=AnalysisRunType.PAPER_SIGNAL_SESSION_ANALYSIS,
        target_type=target_type, target_id=sess.id, strategy_version_id=vid,
        mode=AnalysisRunMode.SINGLE, prompt_type="paper_signal_session",
        provider="fake", model="fake-1.0", status=status, truncated=False,
    )
    db.add(run)
    await db.flush()
    if content is not None:
        db.add(AiModelResponse(run_id=run.id, provider="fake", model="fake-1.0",
                               role="primary_analysis", content=content))
        await db.flush()
    return run


# --- gate / validation -------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess)
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, False, "u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_confirmed_by_missing(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess)
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_run_404(db_session: AsyncSession) -> None:
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(999999, True, "u")
        assert False
    except RunNotFoundError:
        pass


async def test_failed_run_rejected(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess, status=AnalysisRunStatus.FAILED)
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "u")
        assert False
    except RunNotSucceededError:
        pass


async def test_non_paper_signal_target_rejected(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess, target_type=AnalysisTargetType.STRATEGY_VERSION)
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "u")
        assert False
    except InvalidTargetTypeError:
        pass


async def test_no_content_rejected(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess, content=None)
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "u")
        assert False
    except NoReportContentError:
        pass


async def test_missing_version_link_rejected(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess, strategy_version_id=None)
    try:
        await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "u")
        assert False
    except MissingVersionLinkError:
        pass


async def test_duplicate_pending_409(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess)
    svc = PaperSignalImprovementProposalService(db_session)
    await svc.create_from_analysis_run(run.id, True, "u")
    try:
        await svc.create_from_analysis_run(run.id, True, "u")
        assert False
    except DuplicatePendingProposalError:
        pass


# --- happy path: fallback (markdown → no-change proposal) ---------------------
async def test_fallback_creates_pending_no_change(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess, content="# 분석\n신호가 적어 결론 보류.")
    before_versions = await _count(db_session, StrategyVersion)

    p = await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "tester")

    assert p.status == ProposalStatus.PENDING
    assert p.source == "paper_signal_analysis"
    assert p.ai_analysis_run_id == run.id
    assert p.base_version_id == sess.strategy_version_id
    assert p.created_version_id is None  # 승인/버전 생성 안 함
    assert "insufficient evidence — no parameter change recommended" in (p.rationale or "")
    # 무변경: suggested_parameters == 현재 버전 파라미터(strategy_type 보존)
    assert p.suggested_parameters.get("strategy_type") == "moving_average_cross"
    # session 추적: run.target_id == session.id
    run2 = await db_session.get(AiAnalysisRun, run.id)
    assert run2.target_id == sess.id
    # StrategyVersion 미생성
    assert await _count(db_session, StrategyVersion) == before_versions


# --- structured JSON path ----------------------------------------------------
async def test_structured_json_creates_validated_proposal(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    report = json.dumps({
        "verdict": "improve",
        "key_observations": ["obs"],
        "mistakes": [],
        "hypotheses": [
            {"hypothesis": "느린 윈도우를 늘려라", "param_change": {"long_window": 25},
             "confidence": 0.9, "rationale": "추세 추종 강화"}
        ],
        "risk_notes": "소표본 주의",
        "confidence": 0.9,
    })
    run = await _make_run(db_session, sess, content=report)
    p = await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "u")
    assert p.status == ProposalStatus.PENDING
    assert p.ai_analysis_run_id == run.id
    assert p.suggested_parameters.get("long_window") == 25  # 검증된 param_change 반영
    assert p.created_version_id is None


# --- no-mutation -------------------------------------------------------------
async def test_no_domain_mutation(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess)
    before = {
        "versions": await _count(db_session, StrategyVersion),
        "experiments": await _count(db_session, Experiment),
        "signals": await _count(db_session, SignalLog),
        "trades": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
    }
    await PaperSignalImprovementProposalService(db_session).create_from_analysis_run(run.id, True, "u")
    assert await _count(db_session, StrategyVersion) == before["versions"]
    assert await _count(db_session, Experiment) == before["experiments"]
    assert await _count(db_session, SignalLog) == before["signals"]
    assert await _count(db_session, Trade) == before["trades"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    # 상태 불변
    ver = await db_session.get(StrategyVersion, sess.strategy_version_id)
    exp = await db_session.get(Experiment, sess.experiment_id)
    assert ver.status == StrategyVersionStatus.DRAFT
    assert exp.status == ExperimentStatus.DRAFT
    await db_session.refresh(sess)
    assert sess.status == "active"


async def test_list_for_analysis_run(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess)
    svc = PaperSignalImprovementProposalService(db_session)
    await svc.create_from_analysis_run(run.id, True, "u")
    listed = await svc.list_for_analysis_run(run.id)
    assert len(listed) == 1
    assert listed[0].ai_analysis_run_id == run.id


# --- API ---------------------------------------------------------------------
async def test_api_create_and_list(db_session: AsyncSession) -> None:
    sess = await _chain(db_session)
    run = await _make_run(db_session, sess)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = f"/api/v1/analysis-runs/{run.id}/improvement-proposals"
            assert (await client.post(base, json={"confirmed": False, "confirmed_by": "u"})).status_code == 422
            assert (await client.post(base, json={"confirmed": True})).status_code == 422
            r = await client.post(base, json={"confirmed": True, "confirmed_by": "tester"})
            assert r.status_code == 201
            body = r.json()
            assert body["status"] == "pending"
            assert body["ai_analysis_run_id"] == run.id
            assert body["source"] == "paper_signal_analysis"
            # duplicate -> 409
            assert (await client.post(base, json={"confirmed": True, "confirmed_by": "u"})).status_code == 409
            # list
            lst = await client.get(base)
            assert lst.status_code == 200 and len(lst.json()) == 1
            # unknown run -> 404
            assert (await client.post("/api/v1/analysis-runs/999999/improvement-proposals",
                                      json={"confirmed": True, "confirmed_by": "u"})).status_code == 404
    finally:
        app.dependency_overrides.clear()
