"""M2.2: paper_signal 제안 → DRAFT-only challenger StrategyVersion 준비 테스트.

DRAFT 버전만 만든다 — approve 미호출, TESTING/ACTIVE 없음, 세션/실험/주문/잡 변경 없음.
공유 approve 경로는 paper_signal 제안을 거부한다(가드).
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
    AnalysisRunMode,
    AnalysisRunStatus,
    AnalysisRunType,
    AnalysisTargetType,
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
from app.domain.repositories.strategy import StrategyVersionRepository
from app.main import app
from app.services.paper_signal_challenger_service import (
    ChallengerAlreadyPreparedError,
    ChallengerProposalNotFoundError,
    ConfirmationRequiredError,
    InvalidChallengerParamsError,
    MissingAnalysisRunError,
    MissingBaseVersionError,
    NotSignalProposalError,
    PaperSignalChallengerService,
    ProposalNotPendingError,
)

BASE_PARAMS = {
    "strategy_type": "moving_average_cross",
    "symbol_code": "005930",
    "auto_trade_enabled": False,
}


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _chain(db: AsyncSession):
    """strategy + DRAFT base version + paper_signal_session + AiAnalysisRun(PAPER_SIGNAL_SESSION)."""
    rule = ScannerRule(name="ChalRule")
    db.add(rule)
    await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    db.add(rv)
    await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code="005930",
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand)
    await db.flush()
    strat = Strategy(name="ChalStrat", description="t")
    db.add(strat)
    await db.flush()
    base = StrategyVersion(strategy_id=strat.id, version_no=1,
                           status=StrategyVersionStatus.DRAFT, parameters=dict(BASE_PARAMS))
    db.add(base)
    await db.flush()
    prop_c = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code="005930",
                                       suggested_strategy_type="moving_average_cross",
                                       status="approved", source="manual")
    db.add(prop_c)
    await db.flush()
    sess = PaperSignalSession(candidate_strategy_proposal_id=prop_c.id, strategy_version_id=base.id,
                              candidate_event_id=cand.id, symbol_code="005930",
                              status="active", started_by="t")
    db.add(sess)
    await db.flush()
    run = AiAnalysisRun(
        analysis_type=AnalysisRunType.PAPER_SIGNAL_SESSION_ANALYSIS,
        target_type=AnalysisTargetType.PAPER_SIGNAL_SESSION, target_id=sess.id,
        strategy_version_id=base.id, mode=AnalysisRunMode.SINGLE,
        prompt_type="paper_signal_session", provider="fake", model="fake-1.0",
        status=AnalysisRunStatus.SUCCEEDED, truncated=False,
    )
    db.add(run)
    await db.flush()
    db.add(AiModelResponse(run_id=run.id, provider="fake", model="fake-1.0",
                           role="primary_analysis", content="report"))
    await db.flush()
    return strat, base, sess, run


async def _make_proposal(db: AsyncSession, *, strat, base, run,
                         suggested=None, source="paper_signal_analysis",
                         base_version_id="__use__", ai_run_id="__use__",
                         status=ProposalStatus.PENDING) -> StrategyProposal:
    if suggested is None:
        suggested = {**BASE_PARAMS, "short_window": 5, "long_window": 20}
    prop = StrategyProposal(
        strategy_id=strat.id,
        base_version_id=base.id if base_version_id == "__use__" else base_version_id,
        ai_analysis_run_id=run.id if ai_run_id == "__use__" else ai_run_id,
        title="signal challenger candidate",
        suggested_parameters=suggested,
        source=source,
        status=status,
    )
    db.add(prop)
    await db.flush()
    return prop


# --- gate / validation -------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, False, "u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_proposal_404(db_session: AsyncSession) -> None:
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(999999, True, "u")
        assert False
    except ChallengerProposalNotFoundError:
        pass


async def test_non_signal_proposal_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run, source="ai")
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except NotSignalProposalError:
        pass


async def test_missing_ai_run_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run, ai_run_id=None)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except MissingAnalysisRunError:
        pass


async def test_wrong_target_type_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    run.target_type = AnalysisTargetType.STRATEGY_VERSION
    await db_session.flush()
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except MissingAnalysisRunError:
        pass


async def test_missing_base_version_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run, base_version_id=None)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except MissingBaseVersionError:
        pass


async def test_not_pending_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run,
                                status=ProposalStatus.REJECTED)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except ProposalNotPendingError:
        pass


async def test_invalid_params_rejected(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run,
                                suggested={**BASE_PARAMS, "strategy_type": "not_registered_xyz"})
    before = await _count(db_session, StrategyVersion)
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except InvalidChallengerParamsError:
        pass
    assert await _count(db_session, StrategyVersion) == before  # 생성 안 됨


# --- success / safety --------------------------------------------------------
async def test_success_creates_single_draft_version(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    before_v = await _count(db_session, StrategyVersion)

    prep = await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "manual_user")

    assert await _count(db_session, StrategyVersion) == before_v + 1  # exactly one
    new_ver = await StrategyVersionRepository(db_session).get(prep.challenger_version_id)
    assert new_ver.status == StrategyVersionStatus.DRAFT
    assert new_ver.parameters["auto_trade_enabled"] is False
    assert new_ver.strategy_id == strat.id
    # merged params: base + suggested
    assert new_ver.parameters["short_window"] == 5
    assert new_ver.parameters["strategy_type"] == "moving_average_cross"
    # payload
    assert prep.challenger_status == "draft"
    assert prep.auto_trade_enabled is False
    assert prep.proposal_status == "pending"
    assert prep.source_session_id == sess.id
    assert prep.source_analysis_run_id == run.id
    assert prep.base_version_id == base.id
    assert prep.no_change is False


async def test_proposal_links_version_and_stays_pending(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    prep = await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
    await db_session.refresh(prop)
    assert prop.created_version_id == prep.challenger_version_id  # traceability link
    assert prop.status == ProposalStatus.PENDING  # NOT approved
    assert prop.reviewed_by is None  # review fields untouched


async def test_auto_trade_true_is_overridden(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run,
                                suggested={**BASE_PARAMS, "auto_trade_enabled": True, "short_window": 7})
    prep = await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
    new_ver = await StrategyVersionRepository(db_session).get(prep.challenger_version_id)
    assert new_ver.parameters["auto_trade_enabled"] is False
    assert any("auto_trade_enabled" in w for w in prep.warnings)


async def test_no_change_clone_warns(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run, suggested=dict(BASE_PARAMS))
    prep = await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
    assert prep.no_change is True
    assert any("no parameter change" in w for w in prep.warnings)


async def test_duplicate_preparation_409(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
    try:
        await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")
        assert False
    except ChallengerAlreadyPreparedError:
        pass


async def test_draft_not_runner_eligible_and_no_side_effects(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    before = {
        "exp": await _count(db_session, Experiment),
        "rv": await _count(db_session, ScannerRuleVersion),
        "sig": await _count(db_session, SignalLog),
        "trade": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
        "sess": await _count(db_session, PaperSignalSession),
    }
    sess_status = sess.status

    prep = await PaperSignalChallengerService(db_session).prepare_from_proposal(prop.id, True, "u")

    # no TESTING/ACTIVE anywhere; challenger absent from list_active()
    active = await StrategyVersionRepository(db_session).list_active()
    assert all(v.id != prep.challenger_version_id for v in active)
    assert all(v.status not in (StrategyVersionStatus.TESTING, StrategyVersionStatus.ACTIVE)
               for v in await StrategyVersionRepository(db_session).list_by_strategy(strat.id))
    # no other domain rows created / no session status change
    assert await _count(db_session, Experiment) == before["exp"]
    assert await _count(db_session, ScannerRuleVersion) == before["rv"]
    assert await _count(db_session, SignalLog) == before["sig"]
    assert await _count(db_session, Trade) == before["trade"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    assert await _count(db_session, PaperSignalSession) == before["sess"]
    await db_session.refresh(sess)
    assert sess.status == sess_status == "active"


# --- API + approve-path guard ------------------------------------------------
async def test_api_prepare_and_gates(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # confirmed=false -> 422
            r0 = await c.post(f"/api/v1/strategy-proposals/{prop.id}/prepare-signal-challenger",
                              json={"confirmed": False, "confirmed_by": "u"})
            assert r0.status_code == 422
            # unknown -> 404
            r404 = await c.post("/api/v1/strategy-proposals/999999/prepare-signal-challenger",
                                json={"confirmed": True, "confirmed_by": "u"})
            assert r404.status_code == 404
            # success -> 201
            r = await c.post(f"/api/v1/strategy-proposals/{prop.id}/prepare-signal-challenger",
                             json={"confirmed": True, "confirmed_by": "manual_user"})
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["challenger_status"] == "draft"
            assert body["auto_trade_enabled"] is False
            assert body["proposal_status"] == "pending"
            assert body["challenger_version_id"] > 0
            # duplicate -> 409
            r2 = await c.post(f"/api/v1/strategy-proposals/{prop.id}/prepare-signal-challenger",
                              json={"confirmed": True, "confirmed_by": "u"})
            assert r2.status_code == 409
    finally:
        app.dependency_overrides.clear()


async def test_approve_endpoint_rejects_signal_proposal(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    before_v = await _count(db_session, StrategyVersion)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(f"/api/v1/strategy-proposals/{prop.id}/approve",
                             json={"reviewed_by": "u"})
            assert r.status_code == 422
            assert "prepare-signal-challenger" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()
    # no version created by the blocked approve
    assert await _count(db_session, StrategyVersion) == before_v
    await db_session.refresh(prop)
    assert prop.status == ProposalStatus.PENDING


async def test_bulk_approve_blocks_signal_proposal(db_session: AsyncSession) -> None:
    strat, base, sess, run = await _chain(db_session)
    prop = await _make_proposal(db_session, strat=strat, base=base, run=run)
    before_v = await _count(db_session, StrategyVersion)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/api/v1/strategy-proposals/bulk-review",
                             json={"proposal_ids": [prop.id], "action": "approve"})
            assert r.status_code == 200
            body = r.json()
            assert prop.id not in body["succeeded"]
            assert any(f["id"] == prop.id for f in body["failed"])
    finally:
        app.dependency_overrides.clear()
    assert await _count(db_session, StrategyVersion) == before_v  # nothing materialized
