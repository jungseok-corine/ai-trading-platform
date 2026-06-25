"""Paper Signal Session AI 분석 입력(payload) 테스트 (read-only).

분석 입력은 결정론적 패키징만 한다 — AI 호출/제안 생성/DB 변경 없음.
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
from app.domain.models.trade import Trade
from app.main import app
from app.services.paper_signal_analysis_input_service import (
    InvalidHorizonError,
    PaperSignalAnalysisInputService,
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


async def _full_chain(db: AsyncSession, n_signals: int = 1, with_candles: bool = True) -> PaperSignalSession:
    rule = ScannerRule(name="AIInputRule")
    db.add(rule)
    await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    db.add(rv)
    await db.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id, symbol_code="005930", triggered_at=datetime.now(KST),
        score=88, matched_conditions=["turnover_rank", "volume_spike"],
        facts={"volume_ratio": 3.2, "turnover_rank": 5},
    )
    db.add(cand)
    await db.flush()
    strat = Strategy(name="AIInputStrat", description="t")
    db.add(strat)
    await db.flush()
    ver = StrategyVersion(
        strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.DRAFT,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                    "auto_trade_enabled": False},
    )
    db.add(ver)
    await db.flush()
    exp = Experiment(name="AIInputExp", status=ExperimentStatus.DRAFT)
    db.add(exp)
    await db.flush()
    prop = CandidateStrategyProposal(
        candidate_event_id=cand.id, symbol_code="005930",
        suggested_strategy_type="breakout_high", status="approved", source="manual",
        rationale="거래대금 상위 — 돌파형", confidence=0.88, experiment_id=exp.id,
        prepared_at=datetime.now(KST),
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
    if with_candles:
        db.add_all([
            MarketData(symbol_code="005930", timeframe="1m", ts=_ts(31), open=Decimal(100),
                       high=Decimal(101), low=Decimal(99), close=Decimal(100), volume=1000),
            MarketData(symbol_code="005930", timeframe="1m", ts=_ts(60), open=Decimal(110),
                       high=Decimal(112), low=Decimal(109), close=Decimal(110), volume=1000),
        ])
    await db.flush()
    return sess


async def test_unknown_session_raises(db_session: AsyncSession) -> None:
    try:
        await PaperSignalAnalysisInputService(db_session).build_input(999999, horizon_minutes=30)
        assert False
    except SessionNotFoundError:
        pass


async def test_invalid_horizon_raises(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    try:
        await PaperSignalAnalysisInputService(db_session).build_input(sess.id, horizon_minutes=7)
        assert False
    except InvalidHorizonError:
        pass


async def test_input_includes_session_metadata(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    payload = await PaperSignalAnalysisInputService(db_session).build_input(sess.id, horizon_minutes=30)
    d = payload.to_dict()
    assert d["session"]["paper_signal_session_id"] == sess.id
    assert d["session"]["status"] == "active"
    assert d["session"]["symbol_code"] == "005930"
    assert d["session"]["started_by"] == "tester"
    assert "generated_at" in d
    assert d["horizon_minutes"] == 30


async def test_input_includes_candidate_proposal_traceability(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    d = (await PaperSignalAnalysisInputService(db_session).build_input(sess.id)).to_dict()
    cp = d["candidate_proposal"]
    assert cp["suggested_strategy_type"] == "breakout_high"
    assert cp["rationale"] == "거래대금 상위 — 돌파형"
    assert cp["confidence"] == 0.88
    assert cp["proposal_status"] == "approved"
    assert cp["candidate_score"] == 88
    assert cp["matched_conditions"] == ["turnover_rank", "volume_spike"]
    assert cp["candidate_facts"]["volume_ratio"] == 3.2
    assert cp["readiness_approved_by"] == "manual_user"
    assert cp["prepared_experiment_id"] == sess.experiment_id


async def test_input_includes_experiment_version_and_safety(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    d = (await PaperSignalAnalysisInputService(db_session).build_input(sess.id)).to_dict()
    ev = d["experiment_version"]
    assert ev["experiment_status"] == "draft"
    assert ev["strategy_version_status"] == "draft"
    assert ev["auto_trade_enabled"] is False
    assert ev["signal_only"] is True
    assert ev["trades_count_for_version"] == 0
    safety = d["safety"]
    assert safety["real_trading_enabled"] is False
    assert safety["auto_trade_enabled"] is False
    assert safety["paper_signal_session_runner_enabled"] is False
    assert safety["trades_count"] == 0


async def test_input_includes_outcome_summary(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    d = (await PaperSignalAnalysisInputService(db_session).build_input(sess.id, horizon_minutes=30)).to_dict()
    o = d["outcome_summary"]
    assert o["signal_count"] == 1
    assert o["analyzed_count"] == 1
    assert o["win_rate"] == 100.0


async def test_caps_recent_signals(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session, n_signals=15)
    d = (await PaperSignalAnalysisInputService(db_session).build_input(sess.id)).to_dict()
    assert len(d["outcome_summary"]["recent_signals"]) <= 10


async def test_build_input_does_not_mutate_db(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    before = {
        "runs": await _count(db_session, AiAnalysisRun),
        "responses": await _count(db_session, AiModelResponse),
        "trades": await _count(db_session, Trade),
        "signals": await _count(db_session, SignalLog),
        "sessions": await _count(db_session, PaperSignalSession),
    }
    await PaperSignalAnalysisInputService(db_session).build_input(sess.id, horizon_minutes=30)
    assert await _count(db_session, AiAnalysisRun) == before["runs"]
    assert await _count(db_session, AiModelResponse) == before["responses"]
    assert await _count(db_session, Trade) == before["trades"]
    assert await _count(db_session, SignalLog) == before["signals"]
    assert await _count(db_session, PaperSignalSession) == before["sessions"]
    # 상태 불변
    exp = await db_session.get(Experiment, sess.experiment_id)
    ver = await db_session.get(StrategyVersion, sess.strategy_version_id)
    assert exp.status == ExperimentStatus.DRAFT
    assert ver.status == StrategyVersionStatus.DRAFT
    await db_session.refresh(sess)
    assert sess.status == "active"


# --- API ---------------------------------------------------------------------
async def test_api_analysis_input(db_session: AsyncSession) -> None:
    sess = await _full_chain(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/api/v1/paper-signal-sessions/{sess.id}/analysis-input?horizon_minutes=30")
            assert r.status_code == 200
            body = r.json()
            assert body["session"]["paper_signal_session_id"] == sess.id
            assert body["candidate_proposal"]["suggested_strategy_type"] == "breakout_high"
            assert body["safety"]["real_trading_enabled"] is False
            assert "limitations" in body
            # invalid horizon -> 422
            r2 = await client.get(f"/api/v1/paper-signal-sessions/{sess.id}/analysis-input?horizon_minutes=7")
            assert r2.status_code == 422
            # unknown session -> 404
            r3 = await client.get("/api/v1/paper-signal-sessions/999999/analysis-input")
            assert r3.status_code == 404
    finally:
        app.dependency_overrides.clear()
