"""M2.8: session-specific paper signal run-once.

선택한 단일 active 세션만 1회 평가한다(SignalLog만). 전체 실행/스케줄러/주문/거래 없음.
SignalService는 fake로 주입해 네트워크 없이 결정론적으로 검증한다.
"""
from datetime import datetime, timezone

import app.services.paper_signal_run_once_service as run_once_mod
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import ProposalStatus, StrategyVersionStatus, TradeSide
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
from app.services.paper_signal_run_once_service import (
    ConfirmationRequiredError,
    MissingVersionError,
    PaperSignalSessionRunOnceService,
    RealTradingEnabledError,
    RunnerEnabledError,
    RunOnceSessionNotFoundError,
    SessionNotActiveError,
    UnsupportedStrategyTypeError,
    VersionAutoTradeError,
    VersionNotDraftError,
)

BASE = {"strategy_type": "moving_average_cross", "symbol_code": "005930", "auto_trade_enabled": False}


def _override(s):
    async def _g():
        yield s
    return _g


async def _count(s, m):
    return (await s.execute(select(func.count()).select_from(m))).scalar_one()


class _FakeSettings:
    def __init__(self, real=False, runner=False):
        self.kis_real_trading_enabled = real
        self.paper_signal_session_runner_enabled = runner


class _FakeSignalService:
    """generate_and_log_signal만 흉내. behavior: create | none | raise."""

    def __init__(self, db: AsyncSession, behavior: str = "create"):
        self._db = db
        self.behavior = behavior
        self.calls: list[tuple] = []

    async def generate_and_log_signal(self, strategy, symbol_code, version_id, **kw):
        self.calls.append((symbol_code, version_id))
        if self.behavior == "none":
            return None
        if self.behavior == "raise":
            raise RuntimeError("stale candle / market data error")
        log = SignalLog(
            symbol_code=symbol_code, signal_type=TradeSide.BUY, generated_at=datetime.now(KST),
            candle_ts=datetime(2026, 6, 10, 9, 30, tzinfo=KST), market="KR", timeframe="1m",
            strategy_version_id=version_id,
        )
        self._db.add(log)
        await self._db.flush()
        return log


async def _make_session(db, *, status="active", version_status=StrategyVersionStatus.DRAFT,
                        auto_trade=False, strategy_type="moving_average_cross", symbol="005930",
                        source_type="signal_challenger"):
    rule = ScannerRule(name="RO"); db.add(rule); await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[]); db.add(rv); await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code=symbol,
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand); await db.flush()
    strat = Strategy(name="ROStrat", description="t"); db.add(strat); await db.flush()
    ver = StrategyVersion(strategy_id=strat.id, version_no=1, status=version_status,
                          parameters={"strategy_type": strategy_type, "symbol_code": symbol,
                                      "auto_trade_enabled": auto_trade}); db.add(ver); await db.flush()
    pc = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code=symbol,
                                   suggested_strategy_type="moving_average_cross",
                                   status="approved", source="manual"); db.add(pc); await db.flush()
    sp_id = None
    if source_type == "signal_challenger":
        sp = StrategyProposal(strategy_id=strat.id, title="t",
                              suggested_parameters={"strategy_type": "moving_average_cross"},
                              source="paper_signal_analysis", status=ProposalStatus.PENDING,
                              created_version_id=ver.id)
        db.add(sp); await db.flush()
        sp_id = sp.id
    sess = PaperSignalSession(
        candidate_strategy_proposal_id=(None if source_type == "signal_challenger" else pc.id),
        strategy_version_id=ver.id, candidate_event_id=cand.id, symbol_code=symbol,
        status=status, started_by="t", source_type=source_type,
        source_strategy_proposal_id=sp_id,
    )
    db.add(sess); await db.flush()
    return sess, ver, strat


def _svc(db, behavior="create"):
    return PaperSignalSessionRunOnceService(db, _FakeSignalService(db, behavior))


# --- gates -------------------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session)
    try:
        await _svc(db_session).run_once(sess.id, False, "u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session)
    try:
        await _svc(db_session).run_once(sess.id, True, None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_session_404(db_session: AsyncSession) -> None:
    try:
        await _svc(db_session).run_once(999999, True, "u")
        assert False
    except RunOnceSessionNotFoundError:
        pass


async def test_prepared_session_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session, status="prepared")
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except SessionNotActiveError:
        pass


async def test_stopped_session_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session, status="stopped")
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except SessionNotActiveError:
        pass


async def test_version_not_draft_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session, version_status=StrategyVersionStatus.TESTING)
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except VersionNotDraftError:
        pass


async def test_auto_trade_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session, auto_trade=True)
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except VersionAutoTradeError:
        pass


async def test_unsupported_strategy_rejected(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session, strategy_type="not_registered_xyz")
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except UnsupportedStrategyTypeError:
        pass


async def test_real_trading_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    sess, *_ = await _make_session(db_session)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(real=True))
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except RealTradingEnabledError:
        pass


async def test_runner_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    sess, *_ = await _make_session(db_session)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(runner=True))
    try:
        await _svc(db_session).run_once(sess.id, True, "u")
        assert False
    except RunnerEnabledError:
        pass


# --- success / skipped -------------------------------------------------------
async def test_success_creates_one_signal_for_selected_session(db_session: AsyncSession) -> None:
    sess, ver, _ = await _make_session(db_session)
    other, *_ = await _make_session(db_session)  # 다른 active 세션 — 건드리면 안 됨
    sig_before = await _count(db_session, SignalLog)

    svc = _svc(db_session, "create")
    res = await svc.run_once(sess.id, True, "manual_user")

    assert res.signal_created is True and res.signal_id is not None
    assert res.status == "active"
    assert res.orders_created == 0 and res.trades_created == 0 and res.runner_enabled is False
    # 정확히 1개 SignalLog, 선택 세션에만 귀속
    assert await _count(db_session, SignalLog) == sig_before + 1
    log = (await db_session.execute(
        select(SignalLog).where(SignalLog.id == res.signal_id))).scalar_one()
    assert log.paper_signal_session_id == sess.id
    # 카운터 갱신, status 불변
    await db_session.refresh(sess)
    assert sess.status == "active" and sess.run_count == 1 and sess.signal_count == 1
    # 다른 세션은 평가되지 않음
    await db_session.refresh(other)
    assert other.run_count == 0 and other.signal_count == 0
    # signal_service는 선택 세션 1회만 호출
    assert svc._signal_service.calls == [(sess.symbol_code, ver.id)]


async def test_no_signal_returns_skipped(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session)
    res = await _svc(db_session, "none").run_once(sess.id, True, "u")
    assert res.signal_created is False and res.signal_id is None and res.reason
    await db_session.refresh(sess)
    assert sess.run_count == 1 and sess.signal_count == 0 and sess.status == "active"


async def test_market_data_error_returns_skipped_not_crash(db_session: AsyncSession) -> None:
    sess, *_ = await _make_session(db_session)
    res = await _svc(db_session, "raise").run_once(sess.id, True, "u")
    assert res.signal_created is False and "error" in (res.reason or "")
    await db_session.refresh(sess)
    assert sess.status == "active" and sess.last_error is not None


async def test_no_side_effects_and_runner_disabled(db_session: AsyncSession) -> None:
    sess, ver, strat = await _make_session(db_session)
    before = {
        "trade": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
        "exp": await _count(db_session, Experiment),
        "rv": await _count(db_session, ScannerRuleVersion),
        "ver": await _count(db_session, StrategyVersion),
        "sess": await _count(db_session, PaperSignalSession),
    }
    await _svc(db_session, "create").run_once(sess.id, True, "u")
    assert await _count(db_session, Trade) == before["trade"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    assert await _count(db_session, Experiment) == before["exp"]
    assert await _count(db_session, ScannerRuleVersion) == before["rv"]
    assert await _count(db_session, StrategyVersion) == before["ver"]  # 버전 미생성
    assert await _count(db_session, PaperSignalSession) == before["sess"]  # 세션 미생성
    await db_session.refresh(ver)
    assert ver.status == StrategyVersionStatus.DRAFT  # 버전 status 불변


# --- API ---------------------------------------------------------------------
async def test_api_run_once(db_session: AsyncSession) -> None:
    sess, ver, _ = await _make_session(db_session)
    fake = _FakeSignalService(db_session, "create")
    app.dependency_overrides[get_db] = _override(db_session)
    from app.api.v1.candidates import get_run_once_service
    app.dependency_overrides[get_run_once_service] = lambda: PaperSignalSessionRunOnceService(db_session, fake)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            EP = f"/api/v1/paper-signal-sessions/{sess.id}/run-once"
            # confirmed false -> 422
            assert (await c.post(EP, json={"confirmed": False, "confirmed_by": "u"})).status_code == 422
            # unknown -> 404
            assert (await c.post("/api/v1/paper-signal-sessions/999999/run-once",
                                 json={"confirmed": True, "confirmed_by": "u"})).status_code == 404
            # success -> 200
            r = await c.post(EP, json={"confirmed": True, "confirmed_by": "manual_user"})
            assert r.status_code == 200, r.text
            b = r.json()
            assert b["signal_created"] is True
            assert b["orders_created"] == 0 and b["trades_created"] == 0
            assert b["runner_enabled"] is False
            assert b["status"] == "active"
    finally:
        app.dependency_overrides.clear()
