"""Paper Signal Session Outcome Board 테스트 (read-only).

세션이 만든 SignalLog의 forward 수익률을 집계한다. 주문/체결/상태전환 없음.
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
from app.domain.models.enums import TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.paper_signal_outcome_service import (
    InvalidHorizonError,
    PaperSignalOutcomeService,
    SessionNotFoundError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


def _ts(minute: int, hour: int = 9) -> datetime:
    # 09:00 기준에서 minute분 더한다(60분 이상 롤오버 허용).
    return datetime(2026, 6, 10, hour, 0, 0, tzinfo=KST) + timedelta(minutes=minute)


async def _make_session(session: AsyncSession, symbol: str = "005930") -> PaperSignalSession:
    rule = ScannerRule(name="OutcomeRule")
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
    sess = PaperSignalSession(
        candidate_strategy_proposal_id=prop.id, symbol_code=symbol,
        status="active", started_by="tester",
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


async def test_empty_session_outcomes(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    board = await PaperSignalOutcomeService(db_session).session_outcomes(sess.id, horizon_minutes=30)
    assert board.signal_count == 0
    assert board.analyzed_count == 0
    assert board.pending_count == 0
    assert board.win_rate is None
    assert board.recent_signals == []


async def test_session_with_pending_no_market_data(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    await _add_signal(db_session, sess.id)
    await _add_signal(db_session, sess.id)
    board = await PaperSignalOutcomeService(db_session).session_outcomes(sess.id, horizon_minutes=30)
    assert board.signal_count == 2
    assert board.analyzed_count == 0  # market_data 없음 → 분석 불가
    assert board.pending_count == 2
    assert board.win_rate is None
    assert all(r.outcome_status == "pending" for r in board.recent_signals)


async def test_session_with_analyzed_outcomes(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    await _add_signal(db_session, sess.id)
    # entry = 09:31 open(100), 30m(10:00) close(110) → BUY +10% win
    db_session.add_all([
        _candle("005930", 31, 100, 101, 99, 100),
        _candle("005930", 60, 110, 112, 109, 110),
    ])
    await db_session.flush()

    board = await PaperSignalOutcomeService(db_session).session_outcomes(sess.id, horizon_minutes=30)
    assert board.signal_count == 1
    assert board.analyzed_count == 1
    assert board.pending_count == 0
    assert board.win_rate == 100.0
    assert board.avg_return_pct is not None and board.avg_return_pct > 0
    assert board.best_return_pct is not None
    assert any(b.action == "buy" for b in board.by_action)
    row = board.recent_signals[0]
    assert row.outcome_status == "analyzed"
    assert row.is_win is True
    assert row.entry_price == 100.0


async def test_filters_by_session(db_session: AsyncSession) -> None:
    sess_a = await _make_session(db_session)
    sess_b = await _make_session(db_session)
    await _add_signal(db_session, sess_a.id)
    await _add_signal(db_session, sess_b.id)
    await _add_signal(db_session, sess_b.id)
    board_a = await PaperSignalOutcomeService(db_session).session_outcomes(sess_a.id, horizon_minutes=30)
    board_b = await PaperSignalOutcomeService(db_session).session_outcomes(sess_b.id, horizon_minutes=30)
    assert board_a.signal_count == 1  # 다른 세션 신호 미포함
    assert board_b.signal_count == 2


async def test_board_is_read_only_no_side_effects(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    await _add_signal(db_session, sess.id)
    db_session.add_all([_candle("005930", 31, 100, 101, 99, 100), _candle("005930", 60, 110, 112, 109, 110)])
    await db_session.flush()

    before_trades = await _count(db_session, Trade)
    before_logs = await _count(db_session, StrategyAssignmentLog)
    before_signals = await _count(db_session, SignalLog)

    await PaperSignalOutcomeService(db_session).session_outcomes(sess.id, horizon_minutes=30)

    assert await _count(db_session, Trade) == before_trades
    assert await _count(db_session, StrategyAssignmentLog) == before_logs
    assert await _count(db_session, SignalLog) == before_signals  # board는 신호를 만들지 않음


async def test_invalid_horizon(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    try:
        await PaperSignalOutcomeService(db_session).session_outcomes(sess.id, horizon_minutes=7)
        assert False, "expected InvalidHorizonError"
    except InvalidHorizonError:
        pass


async def test_unknown_session(db_session: AsyncSession) -> None:
    try:
        await PaperSignalOutcomeService(db_session).session_outcomes(999999, horizon_minutes=30)
        assert False, "expected SessionNotFoundError"
    except SessionNotFoundError:
        pass


# --- API ---------------------------------------------------------------------
async def test_api_outcomes(db_session: AsyncSession) -> None:
    sess = await _make_session(db_session)
    await _add_signal(db_session, sess.id)
    db_session.add_all([_candle("005930", 31, 100, 101, 99, 100), _candle("005930", 60, 110, 112, 109, 110)])
    await db_session.flush()
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/api/v1/paper-signal-sessions/{sess.id}/outcomes?horizon_minutes=30")
            assert r.status_code == 200
            body = r.json()
            assert body["session_id"] == sess.id
            assert body["signal_count"] == 1
            assert body["analyzed_count"] == 1
            assert body["win_rate"] == 100.0
            # invalid horizon -> 422
            r2 = await client.get(f"/api/v1/paper-signal-sessions/{sess.id}/outcomes?horizon_minutes=7")
            assert r2.status_code == 422
    finally:
        app.dependency_overrides.clear()
