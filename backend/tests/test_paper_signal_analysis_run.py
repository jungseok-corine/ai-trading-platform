"""Paper Signal Session AI 분석 run 테스트 (V1: 리포트 전용, fake provider).

AiAnalysisRun/AiModelResponse만 만든다 — 제안/전략/실험/세션/주문/체결 변경 없음.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import (
    AnalysisRunStatus,
    AnalysisTargetType,
    ExperimentStatus,
    StrategyVersionStatus,
    TradeSide,
)
from app.domain.models.experiment import Experiment
from app.domain.models.market_data import MarketData
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.ai_analysis.schemas import AnalysisProviderError
from app.services.paper_signal_analysis_run_service import (
    ConfirmationRequiredError,
    InvalidHorizonError,
    PaperSignalAnalysisRunService,
    SessionNotFoundError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


def _ts(minute: int) -> datetime:
    return datetime(2026, 6, 10, 9, 0, 0, tzinfo=KST) + timedelta(minutes=minute)


async def _full_chain(db: AsyncSession, n_signals: int = 1) -> PaperSignalSession:
    rule = ScannerRule(name="AIRunRule")
    db.add(rule)
    await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    db.add(rv)
    await db.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id, symbol_code="005930", triggered_at=datetime.now(KST),
        score=88, matched_conditions=["turnover_rank"], facts={"volume_ratio": 3.2},
    )
    db.add(cand)
    await db.flush()
    strat = Strategy(name="AIRunStrat", description="t")
    db.add(strat)
    await db.flush()
    ver = StrategyVersion(
        strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.DRAFT,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                    "auto_trade_enabled": False},
    )
    db.add(ver)
    await db.flush()
    exp = Experiment(name="AIRunExp", status=ExperimentStatus.DRAFT)
    db.add(exp)
    await db.flush()
    prop = CandidateStrategyProposal(
        candidate_event_id=cand.id, symbol_code="005930",
        suggested_strategy_type="breakout_high", status="approved", source="manual",
        rationale="돌파형", confidence=0.88, experiment_id=exp.id, prepared_at=datetime.now(KST),
        suggested_parameters={"_paper_testing_ready_at": "2026-06-10T00:00:00+00:00",
                              "_paper_testing_ready_by": "manual_user"},
    )
    db.add(prop)
    await db.flush()
    sess = PaperSignalSession(
        candidate_strategy_proposal_id=prop.id, experiment_id=exp.id, strategy_version_id=ver.id,
        candidate_event_id=cand.id, symbol_code="005930", status="active", started_by="tester",
        run_count=1, signal_count=n_signals,
    )
    db.add(sess)
    await db.flush()
    for _ in range(n_signals):
        db.add(SignalLog(
            symbol_code="005930", signal_type=TradeSide.BUY, generated_at=datetime.now(KST),
            candle_ts=_ts(30), market="KR", timeframe="1m", paper_signal_session_id=sess.id,
        ))
    db.add_all([
        MarketData(symbol_code="005930", timeframe="1m", ts=_ts(31), open=Decimal(100),
                   high=Decimal(101), low=Decimal(99), close=Decimal(100), volume=1000),
        MarketData(symbol_code="005930", timeframe="1m", ts=_ts(60), open=Decimal(110),
                   high=Decimal(112), low=Decimal(109), close=Decimal(110), volume=1000),
    ])
    await db.flush()
    return sess


# --- gate ---------------------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    try:
        await PaperSignalAnalysisRunService(db_session).create_run(sess.id, confirmed=False, confirmed_by="u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_confirmed_by_missing_rejected(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    try:
        await PaperSignalAnalysisRunService(db_session).create_run(sess.id, confirmed=True, confirmed_by=None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_session_404(db_session: AsyncSession) -> None:
    try:
        await PaperSignalAnalysisRunService(db_session).create_run(999999, confirmed=True, confirmed_by="u")
        assert False
    except SessionNotFoundError:
        pass


async def test_invalid_horizon_422(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    try:
        await PaperSignalAnalysisRunService(db_session).create_run(
            sess.id, horizon_minutes=7, confirmed=True, confirmed_by="u"
        )
        assert False
    except InvalidHorizonError:
        pass


# --- happy path (fake provider) ----------------------------------------------
async def test_fake_provider_creates_run_and_response(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    run = await PaperSignalAnalysisRunService(db_session).create_run(
        sess.id, horizon_minutes=30, provider="fake", confirmed=True, confirmed_by="tester"
    )
    assert run.status == AnalysisRunStatus.SUCCEEDED
    assert run.target_type == AnalysisTargetType.PAPER_SIGNAL_SESSION
    assert run.target_id == sess.id
    assert run.strategy_version_id == sess.strategy_version_id
    assert run.provider == "fake"
    assert run.prompt_length is not None and run.prompt_length <= 20_000
    # input_payload는 분석 입력을 담는다
    assert run.input_payload["session"]["paper_signal_session_id"] == sess.id
    assert run.input_payload["candidate_proposal"]["suggested_strategy_type"] == "breakout_high"
    assert "outcome_summary" in run.input_payload
    # AiModelResponse 1건 생성
    responses = await db_session.execute(
        select(AiModelResponse).where(AiModelResponse.run_id == run.id)
    )
    rlist = list(responses.scalars().all())
    assert len(rlist) == 1
    assert rlist[0].content is not None


async def test_input_payload_recent_signals_bounded(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session, n_signals=15)
    run = await PaperSignalAnalysisRunService(db_session).create_run(
        sess.id, confirmed=True, confirmed_by="u"
    )
    assert len(run.input_payload["outcome_summary"]["recent_signals"]) <= 10


async def test_list_runs_for_session(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    svc = PaperSignalAnalysisRunService(db_session)
    await svc.create_run(sess.id, confirmed=True, confirmed_by="u")
    await svc.create_run(sess.id, confirmed=True, confirmed_by="u")
    runs = await svc.list_runs_for_session(sess.id)
    assert len(runs) == 2
    assert all(r.target_id == sess.id for r in runs)


async def test_provider_failure_records_failed_run(db_session: AsyncSession, monkeypatch) -> None:
    sess = await _full_chain(db_session)

    class _FailProvider:
        def provider_name(self) -> str:
            return "fake"

        def default_model(self) -> str:
            return "fake-1.0"

        async def analyze(self, prompt, *, model=None, timeout_seconds=None):
            raise AnalysisProviderError(provider="fake", message="boom", retryable=False)

    monkeypatch.setattr(
        "app.services.paper_signal_analysis_run_service.get_analysis_provider",
        lambda name: _FailProvider(),
    )
    run = await PaperSignalAnalysisRunService(db_session).create_run(
        sess.id, confirmed=True, confirmed_by="u"
    )
    assert run.status == AnalysisRunStatus.FAILED
    assert run.error_message == "boom"
    responses = (await db_session.execute(
        select(AiModelResponse).where(AiModelResponse.run_id == run.id)
    )).scalars().all()
    assert len(list(responses)) == 1
    assert list(responses)[0].error_message == "boom"


async def test_run_does_not_mutate_other_domain(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    before = {
        "proposals": await _count(db_session, CandidateStrategyProposal),
        "versions": await _count(db_session, StrategyVersion),
        "experiments": await _count(db_session, Experiment),
        "signals": await _count(db_session, SignalLog),
        "trades": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
        "sessions": await _count(db_session, PaperSignalSession),
    }
    await PaperSignalAnalysisRunService(db_session).create_run(sess.id, confirmed=True, confirmed_by="u")
    assert await _count(db_session, CandidateStrategyProposal) == before["proposals"]
    assert await _count(db_session, StrategyVersion) == before["versions"]
    assert await _count(db_session, Experiment) == before["experiments"]
    assert await _count(db_session, SignalLog) == before["signals"]
    assert await _count(db_session, Trade) == before["trades"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    assert await _count(db_session, PaperSignalSession) == before["sessions"]
    # 상태 불변
    exp = await db_session.get(Experiment, sess.experiment_id)
    ver = await db_session.get(StrategyVersion, sess.strategy_version_id)
    assert exp.status == ExperimentStatus.DRAFT
    assert ver.status == StrategyVersionStatus.DRAFT
    await db_session.refresh(sess)
    assert sess.status == "active"


# --- API ---------------------------------------------------------------------
async def test_api_create_and_list_runs(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = f"/api/v1/paper-signal-sessions/{sess.id}/analysis-runs"
            # confirmed missing -> 422
            r = await client.post(base, json={"confirmed": False, "confirmed_by": "u"})
            assert r.status_code == 422
            # invalid horizon -> 422
            r = await client.post(base, json={"confirmed": True, "confirmed_by": "u", "horizon_minutes": 7})
            assert r.status_code == 422
            # ok -> 201
            r = await client.post(base, json={"confirmed": True, "confirmed_by": "tester", "provider": "fake"})
            assert r.status_code == 201
            body = r.json()
            assert body["target_type"] == "paper_signal_session"
            assert body["status"] == "succeeded"
            assert len(body["responses"]) == 1
            # list
            r = await client.get(base)
            assert r.status_code == 200 and len(r.json()) >= 1
            # unknown session -> 404
            r = await client.post("/api/v1/paper-signal-sessions/999999/analysis-runs",
                                  json={"confirmed": True, "confirmed_by": "u"})
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
