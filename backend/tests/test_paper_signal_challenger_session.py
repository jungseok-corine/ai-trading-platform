"""M2.5 Phase 2: paper_signal_analysis proposal → prepared challenger PaperSignalSession.

prepared(비실행) 세션만 만든다 — 시작/SignalLog/주문/잡 없음. 런너 비대상.
"""
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import (
    AnalysisRunMode, AnalysisRunStatus, AnalysisRunType, AnalysisTargetType,
    ProposalStatus, StrategyVersionStatus,
)
from app.domain.models.experiment import Experiment
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.models.trade import Trade
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.main import app
from app.services.paper_signal_challenger_session_service import (
    BaselineSessionMissingError,
    ChallengerAutoTradeError,
    ChallengerSessionProposalNotFoundError,
    ChallengerVersionNotDraftError,
    ConfirmationRequiredError,
    DuplicateChallengerSessionError,
    MissingAnalysisRunError,
    MissingChallengerVersionError,
    NotSignalProposalError,
    PaperSignalChallengerSessionService,
    ProposalNotPendingError,
)

BASE_PARAMS = {"strategy_type": "moving_average_cross", "symbol_code": "005930",
               "auto_trade_enabled": False}


def _override_get_db(s):
    async def _g():
        yield s
    return _g


async def _count(s, model) -> int:
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _chain(db: AsyncSession, symbol: str = "005930"):
    """strat + DRAFT base version + baseline PaperSignalSession + analysis run(target=session)."""
    rule = ScannerRule(name="ChSessRule"); db.add(rule); await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[]); db.add(rv); await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code=symbol,
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand); await db.flush()
    strat = Strategy(name="ChSessStrat", description="t"); db.add(strat); await db.flush()
    base = StrategyVersion(strategy_id=strat.id, version_no=1,
                           status=StrategyVersionStatus.DRAFT, parameters=dict(BASE_PARAMS))
    db.add(base); await db.flush()
    pc = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code=symbol,
                                   suggested_strategy_type="moving_average_cross",
                                   status="approved", source="manual")
    db.add(pc); await db.flush()
    baseline = PaperSignalSession(candidate_strategy_proposal_id=pc.id, strategy_version_id=base.id,
                                  candidate_event_id=cand.id, symbol_code=symbol,
                                  status="active", started_by="t")
    db.add(baseline); await db.flush()
    run = AiAnalysisRun(analysis_type=AnalysisRunType.PAPER_SIGNAL_SESSION_ANALYSIS,
                        target_type=AnalysisTargetType.PAPER_SIGNAL_SESSION, target_id=baseline.id,
                        strategy_version_id=base.id, mode=AnalysisRunMode.SINGLE,
                        prompt_type="paper_signal_session", provider="fake", model="fake-1.0",
                        status=AnalysisRunStatus.SUCCEEDED, truncated=False)
    db.add(run); await db.flush()
    db.add(AiModelResponse(run_id=run.id, provider="fake", model="fake-1.0",
                           role="primary_analysis", content="report")); await db.flush()
    return strat, base, baseline, run


async def _challenger_version(db, strat, *, status=StrategyVersionStatus.DRAFT, auto_trade=False,
                              symbol="005930") -> StrategyVersion:
    ver = StrategyVersion(strategy_id=strat.id, version_no=2, status=status,
                          parameters={"strategy_type": "moving_average_cross",
                                      "symbol_code": symbol, "auto_trade_enabled": auto_trade,
                                      "short_window": 5})
    db.add(ver); await db.flush()
    return ver


async def _proposal(db, strat, base, run, challenger, *, source="paper_signal_analysis",
                    status=ProposalStatus.PENDING, created_version="__use__",
                    ai_run="__use__") -> StrategyProposal:
    p = StrategyProposal(
        strategy_id=strat.id, base_version_id=base.id,
        ai_analysis_run_id=run.id if ai_run == "__use__" else ai_run,
        title="challenger session candidate",
        suggested_parameters={**BASE_PARAMS, "short_window": 5},
        source=source, status=status,
        created_version_id=challenger.id if created_version == "__use__" else created_version,
    )
    db.add(p); await db.flush()
    return p


async def _full(db, **proposal_kw):
    strat, base, baseline, run = await _chain(db)
    challenger = await _challenger_version(db, strat)
    prop = await _proposal(db, strat, base, run, challenger, **proposal_kw)
    return strat, base, baseline, run, challenger, prop


# --- gates -------------------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, False, "u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_proposal_404(db_session: AsyncSession) -> None:
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(999999, True, "u")
        assert False
    except ChallengerSessionProposalNotFoundError:
        pass


async def test_non_signal_proposal_rejected(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session, source="ai")
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except NotSignalProposalError:
        pass


async def test_not_pending_rejected(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session, status=ProposalStatus.REJECTED)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except ProposalNotPendingError:
        pass


async def test_missing_created_version_rejected(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session, created_version=None)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except MissingChallengerVersionError:
        pass


async def test_wrong_target_type_rejected(db_session: AsyncSession) -> None:
    strat, base, baseline, run = await _chain(db_session)
    run.target_type = AnalysisTargetType.STRATEGY_VERSION
    await db_session.flush()
    challenger = await _challenger_version(db_session, strat)
    prop = await _proposal(db_session, strat, base, run, challenger)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except MissingAnalysisRunError:
        pass


async def test_baseline_session_missing_rejected(db_session: AsyncSession) -> None:
    strat, base, baseline, run = await _chain(db_session)
    run.target_id = 99999999  # 존재하지 않는 세션
    await db_session.flush()
    challenger = await _challenger_version(db_session, strat)
    prop = await _proposal(db_session, strat, base, run, challenger)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except BaselineSessionMissingError:
        pass


async def test_challenger_not_draft_rejected(db_session: AsyncSession) -> None:
    strat, base, baseline, run = await _chain(db_session)
    challenger = await _challenger_version(db_session, strat, status=StrategyVersionStatus.TESTING)
    prop = await _proposal(db_session, strat, base, run, challenger)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except ChallengerVersionNotDraftError:
        pass


async def test_challenger_auto_trade_rejected(db_session: AsyncSession) -> None:
    strat, base, baseline, run = await _chain(db_session)
    challenger = await _challenger_version(db_session, strat, auto_trade=True)
    prop = await _proposal(db_session, strat, base, run, challenger)
    try:
        await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except ChallengerAutoTradeError:
        pass


# --- success / safety --------------------------------------------------------
async def test_success_creates_prepared_session(db_session: AsyncSession) -> None:
    strat, base, baseline, run, challenger, prop = await _full(db_session)
    before_sessions = await _count(db_session, PaperSignalSession)

    prep = await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(
        prop.id, True, "manual_user")

    assert await _count(db_session, PaperSignalSession) == before_sessions + 1  # exactly one
    repo = PaperSignalSessionRepository(db_session)
    sess = await repo.get(prep.session_id)
    assert sess.status == "prepared"
    assert sess.candidate_strategy_proposal_id is None
    assert sess.source_type == "signal_challenger"
    assert sess.source_strategy_proposal_id == prop.id
    assert sess.baseline_session_id == baseline.id
    assert sess.strategy_version_id == challenger.id
    assert sess.symbol_code == baseline.symbol_code
    # payload
    assert prep.status == "prepared"
    assert prep.runner_eligible is False
    assert prep.challenger_version_id == challenger.id
    assert prep.baseline_session_id == baseline.id


async def test_prepared_session_not_runner_eligible(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session)
    prep = await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
    repo = PaperSignalSessionRepository(db_session)
    active = await repo.list_active()
    assert all(s.id != prep.session_id for s in active)  # prepared는 list_active 비대상


async def test_proposal_unchanged_after_prepare(db_session: AsyncSession) -> None:
    *_, challenger, prop = await _full(db_session)
    before_status = prop.status
    before_version = prop.created_version_id
    await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")
    await db_session.refresh(prop)
    assert prop.status == before_status == ProposalStatus.PENDING
    assert prop.created_version_id == before_version == challenger.id


async def test_duplicate_prepared_session_409(db_session: AsyncSession) -> None:
    *_, prop = await _full(db_session)
    svc = PaperSignalChallengerSessionService(db_session)
    await svc.prepare_from_strategy_proposal(prop.id, True, "u")
    try:
        await svc.prepare_from_strategy_proposal(prop.id, True, "u")
        assert False
    except DuplicateChallengerSessionError:
        pass


async def test_no_side_effects(db_session: AsyncSession) -> None:
    strat, base, baseline, run, challenger, prop = await _full(db_session)
    before = {
        "ver": await _count(db_session, StrategyVersion),
        "exp": await _count(db_session, Experiment),
        "sig": await _count(db_session, SignalLog),
        "trade": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
        "rv": await _count(db_session, ScannerRuleVersion),
    }
    base_status = baseline.status

    await PaperSignalChallengerSessionService(db_session).prepare_from_strategy_proposal(prop.id, True, "u")

    assert await _count(db_session, StrategyVersion) == before["ver"]   # 버전 미생성
    assert await _count(db_session, Experiment) == before["exp"]
    assert await _count(db_session, SignalLog) == before["sig"]
    assert await _count(db_session, Trade) == before["trade"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    assert await _count(db_session, ScannerRuleVersion) == before["rv"]
    await db_session.refresh(baseline)
    assert baseline.status == base_status == "active"  # baseline 상태 불변
    await db_session.refresh(challenger)
    assert challenger.status == StrategyVersionStatus.DRAFT  # challenger DRAFT 유지


# --- API ---------------------------------------------------------------------
async def test_api_prepare_session(db_session: AsyncSession) -> None:
    strat, base, baseline, run, challenger, prop = await _full(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            P = "/api/v1/strategy-proposals"
            # confirmed false -> 422
            r0 = await c.post(f"{P}/{prop.id}/prepare-challenger-session",
                              json={"confirmed": False, "confirmed_by": "u"})
            assert r0.status_code == 422
            # unknown -> 404
            r404 = await c.post(f"{P}/999999/prepare-challenger-session",
                                json={"confirmed": True, "confirmed_by": "u"})
            assert r404.status_code == 404
            # success -> 201
            r = await c.post(f"{P}/{prop.id}/prepare-challenger-session",
                             json={"confirmed": True, "confirmed_by": "manual_user"})
            assert r.status_code == 201, r.text
            b = r.json()
            assert b["status"] == "prepared"
            assert b["source_type"] == "signal_challenger"
            assert b["runner_eligible"] is False
            assert b["baseline_session_id"] == baseline.id
            assert b["challenger_version_id"] == challenger.id
            # duplicate -> 409
            r2 = await c.post(f"{P}/{prop.id}/prepare-challenger-session",
                              json={"confirmed": True, "confirmed_by": "u"})
            assert r2.status_code == 409
    finally:
        app.dependency_overrides.clear()
