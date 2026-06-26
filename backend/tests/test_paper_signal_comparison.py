"""Paper Signal Session Comparison 테스트 (M2.1, read-only).

두 PaperSignalSession을 신호 outcome으로 나란히 비교한다. 생성/상태변경/주문 없음.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import StrategyVersionStatus, TradeSide
from app.domain.models.experiment import Experiment
from app.domain.models.market_data import MarketData
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.paper_signal_comparison_service import (
    InvalidHorizonError,
    PaperSignalComparisonService,
    SameSessionError,
    SessionNotFoundError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


def _ts(minute: int, hour: int = 9) -> datetime:
    return datetime(2026, 6, 10, hour, 0, 0, tzinfo=KST) + timedelta(minutes=minute)


async def _make_session(
    session: AsyncSession, symbol: str = "005930", with_version: bool = False
) -> PaperSignalSession:
    rule = ScannerRule(name="CompareRule")
    session.add(rule)
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id, symbol_code=symbol,
        triggered_at=datetime.now(KST), score=90, matched_conditions=["turnover_rank"],
    )
    session.add(cand)
    await session.flush()
    prop = CandidateStrategyProposal(
        candidate_event_id=cand.id, symbol_code=symbol,
        suggested_strategy_type="moving_average_cross", status="approved", source="manual",
    )
    session.add(prop)
    await session.flush()

    version_id = None
    if with_version:
        strat = Strategy(name=f"CmpStrat-{symbol}-{cand.id}", description="compare seed")
        session.add(strat)
        await session.flush()
        # DRAFT 버전만 — runner 비대상. (생성하지 않음을 검증하는 테스트와 무관한 seed)
        ver = StrategyVersion(
            strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.DRAFT,
            parameters={"auto_trade_enabled": False},
        )
        session.add(ver)
        await session.flush()
        version_id = ver.id

    sess = PaperSignalSession(
        candidate_strategy_proposal_id=prop.id, symbol_code=symbol,
        status="active", started_by="tester", strategy_version_id=version_id,
    )
    session.add(sess)
    await session.flush()
    return sess


async def _add_signal(session: AsyncSession, sess_id: int, symbol: str = "005930") -> SignalLog:
    log = SignalLog(
        symbol_code=symbol, signal_type=TradeSide.BUY,
        generated_at=datetime.now(KST), candle_ts=_ts(30), market="KR", timeframe="1m",
        paper_signal_session_id=sess_id,
    )
    session.add(log)
    await session.flush()
    return log


def _candle(symbol, minute, o, h, l, c):
    return MarketData(symbol_code=symbol, timeframe="1m", ts=_ts(minute),
                      open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c), volume=1000)


async def _add_candles(session: AsyncSession, symbol: str = "005930") -> None:
    """심볼당 한 번만 호출 — entry 100(09:31) → 30m(10:00) close 110 = BUY +10% win."""
    session.add_all([
        _candle(symbol, 31, 100, 101, 99, 100),
        _candle(symbol, 60, 110, 112, 109, 110),
    ])
    await session.flush()


async def _win_signals(session: AsyncSession, sess_id: int, n: int, symbol: str = "005930") -> None:
    """분석 가능한 WIN 신호 n개를 만든다(캔들은 _add_candles로 따로 심는다)."""
    for _ in range(n):
        await _add_signal(session, sess_id, symbol)
    await session.flush()


# --- service ------------------------------------------------------------------
async def test_unknown_baseline_session(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    try:
        await PaperSignalComparisonService(db_session).compare(999999, sess.id)
        assert False, "expected SessionNotFoundError"
    except SessionNotFoundError:
        pass


async def test_unknown_challenger_session(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    try:
        await PaperSignalComparisonService(db_session).compare(sess.id, 999999)
        assert False, "expected SessionNotFoundError"
    except SessionNotFoundError:
        pass


async def test_same_session_id_rejected(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    try:
        await PaperSignalComparisonService(db_session).compare(sess.id, sess.id)
        assert False, "expected SameSessionError"
    except SameSessionError:
        pass


async def test_invalid_horizon_rejected(db_session: AsyncSession) -> None:
    a = await _make_session(db_session)
    b = await _make_session(db_session)
    try:
        await PaperSignalComparisonService(db_session).compare(a.id, b.id, horizon_minutes=7)
        assert False, "expected InvalidHorizonError"
    except InvalidHorizonError:
        pass


async def test_comparison_returns_both_summaries(db_session: AsyncSession) -> None:
    a = await _make_session(db_session, with_version=True)
    b = await _make_session(db_session, with_version=True)
    await _add_candles(db_session)
    await _win_signals(db_session, a.id, 5)
    await _win_signals(db_session, b.id, 5)

    cmp = await PaperSignalComparisonService(db_session).compare(a.id, b.id, horizon_minutes=30)
    assert cmp.baseline_session_id == a.id
    assert cmp.challenger_session_id == b.id
    assert cmp.horizon_minutes == 30
    assert cmp.symbol_match is True
    assert cmp.baseline["session_id"] == a.id
    assert cmp.challenger["session_id"] == b.id
    assert cmp.baseline["strategy_version_id"] is not None
    assert cmp.challenger["strategy_version_id"] is not None
    assert cmp.baseline["signal_count"] == 5
    assert cmp.challenger["signal_count"] == 5
    assert cmp.baseline["win_rate"] == 100.0
    assert cmp.challenger["win_rate"] == 100.0


async def test_deltas_computed_correctly(db_session: AsyncSession) -> None:
    a = await _make_session(db_session)  # baseline: 5 analyzed wins
    b = await _make_session(db_session)  # challenger: 6 analyzed wins
    await _add_candles(db_session)
    await _win_signals(db_session, a.id, 5)
    await _win_signals(db_session, b.id, 6)

    cmp = await PaperSignalComparisonService(db_session).compare(a.id, b.id, horizon_minutes=30)
    # delta = challenger - baseline
    assert cmp.deltas["signal_count_delta"] == 1
    assert cmp.deltas["analyzed_count_delta"] == 1
    assert cmp.deltas["pending_count_delta"] == 0
    assert cmp.deltas["win_rate_delta"] == 0.0  # 둘 다 100%
    # by_action delta 존재(buy)
    buy_delta = next(d for d in cmp.deltas["by_action"] if d["action"] == "buy")
    assert buy_delta["count_delta"] == 1
    assert buy_delta["analyzed_count_delta"] == 1


async def test_different_symbols_warns_not_fails(db_session: AsyncSession) -> None:
    a = await _make_session(db_session, symbol="005930")
    b = await _make_session(db_session, symbol="000660")
    await _add_candles(db_session, symbol="005930")
    await _add_candles(db_session, symbol="000660")
    await _win_signals(db_session, a.id, 5, symbol="005930")
    await _win_signals(db_session, b.id, 5, symbol="000660")

    cmp = await PaperSignalComparisonService(db_session).compare(a.id, b.id, horizon_minutes=30)
    assert cmp.symbol_match is False
    assert any("different symbols" in w for w in cmp.warnings)


async def test_low_analyzed_count_warns(db_session: AsyncSession) -> None:
    a = await _make_session(db_session)
    b = await _make_session(db_session)
    # 분석 신호 1개씩만 → MIN_ANALYZED_FOR_MEANINGFUL 미만
    await _add_candles(db_session)
    await _win_signals(db_session, a.id, 1)
    await _win_signals(db_session, b.id, 1)

    cmp = await PaperSignalComparisonService(db_session).compare(a.id, b.id, horizon_minutes=30)
    assert any("Low analyzed signal count" in w for w in cmp.warnings)


async def test_compare_is_read_only_no_side_effects(db_session: AsyncSession) -> None:
    a = await _make_session(db_session, with_version=True)
    b = await _make_session(db_session, with_version=True)
    await _add_candles(db_session)
    await _win_signals(db_session, a.id, 5)
    await _win_signals(db_session, b.id, 5)

    before = {
        "sessions": await _count(db_session, PaperSignalSession),
        "signals": await _count(db_session, SignalLog),
        "versions": await _count(db_session, StrategyVersion),
        "experiments": await _count(db_session, Experiment),
        "trades": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
    }
    a_status, b_status = a.status, b.status

    await PaperSignalComparisonService(db_session).compare(a.id, b.id, horizon_minutes=30)

    assert await _count(db_session, PaperSignalSession) == before["sessions"]
    assert await _count(db_session, SignalLog) == before["signals"]
    assert await _count(db_session, StrategyVersion) == before["versions"]
    assert await _count(db_session, Experiment) == before["experiments"]
    assert await _count(db_session, Trade) == before["trades"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    # 상태 불변
    await db_session.refresh(a)
    await db_session.refresh(b)
    assert a.status == a_status == "active"
    assert b.status == b_status == "active"


# --- API ----------------------------------------------------------------------
async def test_api_compare_ok(db_session: AsyncSession) -> None:
    a = await _make_session(db_session, with_version=True)
    b = await _make_session(db_session, with_version=True)
    await _add_candles(db_session)
    await _win_signals(db_session, a.id, 5)
    await _win_signals(db_session, b.id, 5)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(
                f"/api/v1/paper-signal-sessions/{a.id}/compare/{b.id}?horizon_minutes=30"
            )
            assert r.status_code == 200
            body = r.json()
            assert body["baseline_session_id"] == a.id
            assert body["challenger_session_id"] == b.id
            assert body["symbol_match"] is True
            assert "deltas" in body and "warnings" in body
            assert body["baseline"]["win_rate"] == 100.0
    finally:
        app.dependency_overrides.clear()


async def test_api_compare_errors(db_session: AsyncSession) -> None:
    a = await _make_session(db_session)
    b = await _make_session(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # same id -> 422
            r_same = await client.get(f"/api/v1/paper-signal-sessions/{a.id}/compare/{a.id}")
            assert r_same.status_code == 422
            # invalid horizon -> 422
            r_h = await client.get(
                f"/api/v1/paper-signal-sessions/{a.id}/compare/{b.id}?horizon_minutes=7"
            )
            assert r_h.status_code == 422
            # unknown session -> 404
            r_404 = await client.get(f"/api/v1/paper-signal-sessions/{a.id}/compare/999999")
            assert r_404.status_code == 404
    finally:
        app.dependency_overrides.clear()
