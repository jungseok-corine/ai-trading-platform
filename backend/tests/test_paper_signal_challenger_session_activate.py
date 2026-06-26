"""M2.5 Phase 3: prepared challenger PaperSignalSession → active 전환 (사람-게이트).

활성화는 status만 prepared→active로 바꿔 런너 대상 자격만 부여한다. 신호/주문/거래 없음,
잡 미활성, run_due_sessions 미호출.
"""
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
    ActivationSessionNotFoundError,
    ChallengerAutoTradeError,
    ChallengerVersionNotDraftError,
    ConfirmationRequiredError,
    DuplicateActiveChallengerError,
    InconsistentSessionError,
    LinkedProposalInvalidError,
    NotChallengerSessionError,
    PaperSignalChallengerSessionService,
    SessionNotPreparedError,
)

BASE = {"strategy_type": "moving_average_cross", "symbol_code": "005930", "auto_trade_enabled": False}


def _override(s):
    async def _g():
        yield s
    return _g


async def _count(s, m):
    return (await s.execute(select(func.count()).select_from(m))).scalar_one()


async def _chain(db, symbol="005930"):
    rule = ScannerRule(name="P3Rule"); db.add(rule); await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[]); db.add(rv); await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code=symbol,
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand); await db.flush()
    strat = Strategy(name="P3Strat", description="t"); db.add(strat); await db.flush()
    base = StrategyVersion(strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.DRAFT,
                           parameters=dict(BASE)); db.add(base); await db.flush()
    pc = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code=symbol,
                                   suggested_strategy_type="moving_average_cross",
                                   status="approved", source="manual"); db.add(pc); await db.flush()
    baseline = PaperSignalSession(candidate_strategy_proposal_id=pc.id, strategy_version_id=base.id,
                                  candidate_event_id=cand.id, symbol_code=symbol,
                                  status="active", started_by="t"); db.add(baseline); await db.flush()
    run = AiAnalysisRun(analysis_type=AnalysisRunType.PAPER_SIGNAL_SESSION_ANALYSIS,
                        target_type=AnalysisTargetType.PAPER_SIGNAL_SESSION, target_id=baseline.id,
                        strategy_version_id=base.id, mode=AnalysisRunMode.SINGLE,
                        prompt_type="paper_signal_session", provider="fake", model="fake-1.0",
                        status=AnalysisRunStatus.SUCCEEDED, truncated=False); db.add(run); await db.flush()
    db.add(AiModelResponse(run_id=run.id, provider="fake", model="fake-1.0",
                           role="primary_analysis", content="r")); await db.flush()
    return strat, base, baseline, run


async def _challenger(db, strat, *, status=StrategyVersionStatus.DRAFT, auto=False):
    v = StrategyVersion(strategy_id=strat.id, version_no=2, status=status,
                        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                                    "auto_trade_enabled": auto, "short_window": 5}); db.add(v); await db.flush()
    return v


async def _proposal(db, strat, base, run, challenger, *, source="paper_signal_analysis",
                    status=ProposalStatus.PENDING):
    p = StrategyProposal(strategy_id=strat.id, base_version_id=base.id, ai_analysis_run_id=run.id,
                         title="p3", suggested_parameters={**BASE, "short_window": 5}, source=source,
                         status=status, created_version_id=challenger.id); db.add(p); await db.flush()
    return p


async def _prepared(db):
    """완전한 prepared challenger 세션을 만들어 (session, strat, base, baseline, run, challenger, proposal) 반환."""
    strat, base, baseline, run = await _chain(db)
    challenger = await _challenger(db, strat)
    prop = await _proposal(db, strat, base, run, challenger)
    prep = await PaperSignalChallengerSessionService(db).prepare_from_strategy_proposal(prop.id, True, "u")
    repo = PaperSignalSessionRepository(db)
    sess = await repo.get(prep.session_id)
    return sess, strat, base, baseline, run, challenger, prop


# --- gates -------------------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _prepared(db_session)
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, False, "u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _prepared(db_session)
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, True, None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_session_404(db_session: AsyncSession) -> None:
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(999999, True, "u")
        assert False
    except ActivationSessionNotFoundError:
        pass


async def test_non_challenger_session_rejected(db_session: AsyncSession) -> None:
    strat, base, baseline, run = await _chain(db_session)  # baseline is a candidate session
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(baseline.id, True, "u")
        assert False
    except NotChallengerSessionError:
        pass


async def test_not_prepared_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _prepared(db_session)
    svc = PaperSignalChallengerSessionService(db_session)
    await svc.activate_prepared_session(sess.id, True, "u")  # now active
    try:
        await svc.activate_prepared_session(sess.id, True, "u")  # second time → not prepared
        assert False
    except SessionNotPreparedError:
        pass


async def test_inconsistent_missing_source_proposal_rejected(db_session: AsyncSession) -> None:
    # challenger-type prepared 세션이지만 source_strategy_proposal_id 누락
    repo = PaperSignalSessionRepository(db_session)
    sess = await repo.create(candidate_strategy_proposal_id=None, source_type="signal_challenger",
                             source_strategy_proposal_id=None, symbol_code="005930",
                             status="prepared", started_by="t")
    await db_session.flush()
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, True, "u")
        assert False
    except InconsistentSessionError:
        pass


async def test_version_not_draft_rejected(db_session: AsyncSession) -> None:
    sess, strat, base, baseline, run, challenger, prop = await _prepared(db_session)
    challenger.status = StrategyVersionStatus.TESTING
    await db_session.flush()
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, True, "u")
        assert False
    except ChallengerVersionNotDraftError:
        pass


async def test_version_auto_trade_rejected(db_session: AsyncSession) -> None:
    sess, strat, base, baseline, run, challenger, prop = await _prepared(db_session)
    challenger.parameters = {**(challenger.parameters or {}), "auto_trade_enabled": True}
    await db_session.flush()
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, True, "u")
        assert False
    except ChallengerAutoTradeError:
        pass


async def test_proposal_not_pending_rejected(db_session: AsyncSession) -> None:
    sess, strat, base, baseline, run, challenger, prop = await _prepared(db_session)
    prop.status = ProposalStatus.REJECTED
    await db_session.flush()
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, True, "u")
        assert False
    except LinkedProposalInvalidError:
        pass


async def test_duplicate_active_challenger_409(db_session: AsyncSession) -> None:
    sess, strat, base, baseline, run, challenger, prop = await _prepared(db_session)
    # 같은 source 제안에 대한 또 다른 active challenger 세션을 직접 주입.
    repo = PaperSignalSessionRepository(db_session)
    await repo.create(candidate_strategy_proposal_id=None, source_type="signal_challenger",
                      source_strategy_proposal_id=prop.id, baseline_session_id=baseline.id,
                      strategy_version_id=challenger.id, symbol_code="005930",
                      status="active", started_by="other")
    await db_session.flush()
    try:
        await PaperSignalChallengerSessionService(db_session).activate_prepared_session(sess.id, True, "u")
        assert False
    except DuplicateActiveChallengerError:
        pass


# --- success / safety --------------------------------------------------------
async def test_activation_flips_status_only(db_session: AsyncSession) -> None:
    sess, strat, base, baseline, run, challenger, prop = await _prepared(db_session)
    before = {
        "ver": await _count(db_session, StrategyVersion),
        "exp": await _count(db_session, Experiment),
        "sig": await _count(db_session, SignalLog),
        "trade": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
        "sess": await _count(db_session, PaperSignalSession),
    }
    runner_before = get_settings().paper_signal_session_runner_enabled

    result = await PaperSignalChallengerSessionService(db_session).activate_prepared_session(
        sess.id, True, "manual_user")

    repo = PaperSignalSessionRepository(db_session)
    await db_session.refresh(sess)
    assert sess.status == "active"
    assert sess.started_by == "manual_user"
    assert sess.started_at is not None
    # payload
    assert result.status == "active"
    assert result.runner_eligible is True
    assert result.runner_currently_enabled is False
    assert any("does not create signals immediately" in w for w in result.warnings)
    # list_active now includes it
    active = await repo.list_active()
    assert any(s.id == sess.id for s in active)
    # no new rows anywhere except status flip (session count unchanged)
    assert await _count(db_session, StrategyVersion) == before["ver"]
    assert await _count(db_session, Experiment) == before["exp"]
    assert await _count(db_session, SignalLog) == before["sig"]
    assert await _count(db_session, Trade) == before["trade"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    assert await _count(db_session, PaperSignalSession) == before["sess"]
    # version DRAFT, proposal PENDING, baseline unchanged, runner flag unchanged
    await db_session.refresh(challenger); await db_session.refresh(prop); await db_session.refresh(baseline)
    assert challenger.status == StrategyVersionStatus.DRAFT
    assert prop.status == ProposalStatus.PENDING
    assert baseline.status == "active"  # baseline candidate session unchanged
    assert get_settings().paper_signal_session_runner_enabled == runner_before is False


# --- API ---------------------------------------------------------------------
async def test_api_activate(db_session: AsyncSession) -> None:
    sess, strat, base, baseline, run, challenger, prop = await _prepared(db_session)
    app.dependency_overrides[get_db] = _override(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            EP = f"/api/v1/paper-signal-sessions/{sess.id}/activate"
            # confirmed false -> 422
            assert (await c.post(EP, json={"confirmed": False, "confirmed_by": "u"})).status_code == 422
            # unknown -> 404
            assert (await c.post("/api/v1/paper-signal-sessions/999999/activate",
                                 json={"confirmed": True, "confirmed_by": "u"})).status_code == 404
            # success -> 200
            r = await c.post(EP, json={"confirmed": True, "confirmed_by": "manual_user"})
            assert r.status_code == 200, r.text
            b = r.json()
            assert b["status"] == "active"
            assert b["runner_eligible"] is True
            assert b["runner_currently_enabled"] is False
            assert b["baseline_session_id"] == baseline.id
            # second activation -> 422 (not prepared)
            assert (await c.post(EP, json={"confirmed": True, "confirmed_by": "u"})).status_code == 422
    finally:
        app.dependency_overrides.clear()
