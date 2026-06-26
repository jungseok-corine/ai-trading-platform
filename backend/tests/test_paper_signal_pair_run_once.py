"""M2.10: baseline ↔ challenger pair run-once.

명시한 두 active 세션만 각각 1회 평가한다(SignalLog만, 최대 2개). 전체 실행/스케줄러/주문/거래 없음.
SignalService는 fake로 주입한다(네트워크 없음, 결정론적). 검증 코어는 M2.8과 동일(재사용).
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
from app.main import app
from app.services.paper_signal_pair_run_once_service import (
    BaselineMismatchError,
    NotChallengerSessionError,
    PairBaselineNotFoundError,
    PairChallengerNotFoundError,
    PaperSignalPairRunOnceService,
    SymbolMismatchError,
)
from app.services.paper_signal_run_once_service import (
    ConfirmationRequiredError,
    MissingVersionError,
    RealTradingEnabledError,
    RunnerEnabledError,
    SessionNotActiveError,
    UnsupportedStrategyTypeError,
    VersionAutoTradeError,
    VersionNotDraftError,
)


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
    """version_id별 동작 제어: skip_versions→None, raise_versions→예외, 그 외→SignalLog 생성."""

    def __init__(self, db, skip_versions=None, raise_versions=None):
        self._db = db
        self.skip = set(skip_versions or [])
        self.raise_ = set(raise_versions or [])
        self.calls = []

    async def generate_and_log_signal(self, strategy, symbol_code, version_id, **kw):
        self.calls.append((symbol_code, version_id))
        if version_id in self.raise_:
            raise RuntimeError("stale candle / market data error")
        if version_id in self.skip:
            return None
        log = SignalLog(symbol_code=symbol_code, signal_type=TradeSide.BUY,
                        generated_at=datetime.now(KST),
                        candle_ts=datetime(2026, 6, 10, 9, 30, tzinfo=KST), market="KR",
                        timeframe="1m", strategy_version_id=version_id)
        self._db.add(log)
        await self._db.flush()
        return log


async def _version(db, strat, no, *, status=StrategyVersionStatus.DRAFT, auto=False,
                   strategy_type="moving_average_cross", symbol="005930"):
    v = StrategyVersion(strategy_id=strat.id, version_no=no, status=status,
                        parameters={"strategy_type": strategy_type, "symbol_code": symbol,
                                    "auto_trade_enabled": auto}); db.add(v); await db.flush()
    return v


async def _session(db, ver, *, status="active", symbol="005930", source_type="candidate_proposal",
                   baseline_id=None, sp_id=None, cand_id=None):
    return_obj = PaperSignalSession(
        candidate_strategy_proposal_id=cand_id, strategy_version_id=(ver.id if ver else None),
        symbol_code=symbol, status=status, started_by="t", source_type=source_type,
        baseline_session_id=baseline_id, source_strategy_proposal_id=sp_id)
    db.add(return_obj); await db.flush()
    return return_obj


async def _make_pair(db, *, symbol="005930", chal_symbol=None, chal_baseline=None,
                     chal_source="signal_challenger", b_auto=False, c_auto=False,
                     b_ver_status=StrategyVersionStatus.DRAFT, c_ver_status=StrategyVersionStatus.DRAFT,
                     b_status="active", c_status="active", c_strategy_type="moving_average_cross"):
    rule = ScannerRule(name="PairRule"); db.add(rule); await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[]); db.add(rv); await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code=symbol,
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand); await db.flush()
    strat = Strategy(name="PairStrat", description="t"); db.add(strat); await db.flush()
    pc = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code=symbol,
                                   suggested_strategy_type="moving_average_cross",
                                   status="approved", source="manual"); db.add(pc); await db.flush()
    b_ver = await _version(db, strat, 1, status=b_ver_status, auto=b_auto, symbol=symbol)
    baseline = await _session(db, b_ver, status=b_status, symbol=symbol,
                              source_type="candidate_proposal", cand_id=pc.id)
    c_ver = await _version(db, strat, 2, status=c_ver_status, auto=c_auto,
                           strategy_type=c_strategy_type, symbol=(chal_symbol or symbol))
    sp = StrategyProposal(strategy_id=strat.id, title="t",
                          suggested_parameters={"strategy_type": "moving_average_cross"},
                          source="paper_signal_analysis", status=ProposalStatus.PENDING,
                          created_version_id=c_ver.id); db.add(sp); await db.flush()
    challenger = await _session(db, c_ver, status=c_status, symbol=(chal_symbol or symbol),
                                source_type=chal_source,
                                baseline_id=(chal_baseline if chal_baseline is not None else baseline.id),
                                sp_id=sp.id)
    return baseline, challenger, b_ver, c_ver, strat


def _svc(db, **fakekw):
    return PaperSignalPairRunOnceService(db, _FakeSignalService(db, **fakekw))


# --- gates -------------------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    try:
        await _svc(db_session).run_pair(b.id, c.id, False, "u")
        assert False
    except ConfirmationRequiredError:
        pass


async def test_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, None)
        assert False
    except ConfirmationRequiredError:
        pass


async def test_unknown_baseline_404(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    try:
        await _svc(db_session).run_pair(999999, c.id, True, "u")
        assert False
    except PairBaselineNotFoundError:
        pass


async def test_unknown_challenger_404(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    try:
        await _svc(db_session).run_pair(b.id, 999999, True, "u")
        assert False
    except PairChallengerNotFoundError:
        pass


async def test_baseline_not_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, b_status="stopped")
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except SessionNotActiveError:
        pass


async def test_challenger_not_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_status="prepared")
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except SessionNotActiveError:
        pass


async def test_challenger_not_signal_challenger_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, chal_source="candidate_proposal")
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except NotChallengerSessionError:
        pass


async def test_baseline_mismatch_rejected(db_session: AsyncSession) -> None:
    # challenger가 가리키는 baseline은 b이지만, 다른(유효한) baseline id로 페어를 요청 → 불일치.
    b, c, *_ = await _make_pair(db_session)
    other_strat = Strategy(name="OtherBase", description="t"); db_session.add(other_strat); await db_session.flush()
    other_ver = await _version(db_session, other_strat, 1)
    other_baseline = await _session(db_session, other_ver, source_type="candidate_proposal")
    try:
        await _svc(db_session).run_pair(other_baseline.id, c.id, True, "u")  # c.baseline_session_id != other_baseline.id
        assert False
    except BaselineMismatchError:
        pass


async def test_symbol_mismatch_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, chal_symbol="000660")
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except SymbolMismatchError:
        pass


async def test_challenger_version_not_draft_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_ver_status=StrategyVersionStatus.TESTING)
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except VersionNotDraftError:
        pass


async def test_baseline_auto_trade_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, b_auto=True)
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except VersionAutoTradeError:
        pass


async def test_unsupported_strategy_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_strategy_type="not_registered_xyz")
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except UnsupportedStrategyTypeError:
        pass


async def test_real_trading_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(real=True))
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except RealTradingEnabledError:
        pass


async def test_runner_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(runner=True))
    try:
        await _svc(db_session).run_pair(b.id, c.id, True, "u")
        assert False
    except RunnerEnabledError:
        pass


# --- validation-before-execution: a bad side means NEITHER is evaluated ------
async def test_gate_failure_evaluates_neither_side(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, _ = await _make_pair(db_session, c_ver_status=StrategyVersionStatus.TESTING)
    fake = _FakeSignalService(db_session)
    sig_before = await _count(db_session, SignalLog)
    try:
        await PaperSignalPairRunOnceService(db_session, fake).run_pair(b.id, c.id, True, "u")
        assert False
    except VersionNotDraftError:
        pass
    assert fake.calls == []  # 어느 쪽도 평가하지 않음
    assert await _count(db_session, SignalLog) == sig_before


# --- execution ---------------------------------------------------------------
async def test_success_creates_two_signals_pair_only(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, _ = await _make_pair(db_session)
    other_strat = Strategy(name="Other", description="t"); db_session.add(other_strat); await db_session.flush()
    other_ver = await _version(db_session, other_strat, 1)
    other = await _session(db_session, other_ver, source_type="candidate_proposal")
    sig_before = await _count(db_session, SignalLog)

    svc = PaperSignalPairRunOnceService(db_session, _FakeSignalService(db_session))
    res = await svc.run_pair(b.id, c.id, True, "manual_user")

    assert res.baseline.signal_created is True and res.challenger.signal_created is True
    assert res.orders_created == 0 and res.trades_created == 0 and res.runner_enabled is False
    assert await _count(db_session, SignalLog) == sig_before + 2  # 최대 2
    # 각 SignalLog가 올바른 세션에 귀속
    b_log = (await db_session.execute(select(SignalLog).where(SignalLog.id == res.baseline.signal_id))).scalar_one()
    c_log = (await db_session.execute(select(SignalLog).where(SignalLog.id == res.challenger.signal_id))).scalar_one()
    assert b_log.paper_signal_session_id == b.id
    assert c_log.paper_signal_session_id == c.id
    # 페어만 평가(2회, baseline→challenger 순)
    assert svc._once._signal_service.calls == [(b.symbol_code, b_ver.id), (c.symbol_code, c_ver.id)]
    # 카운터: 두 세션만 갱신, 다른 세션 불변, status 불변
    await db_session.refresh(b); await db_session.refresh(c); await db_session.refresh(other)
    assert b.run_count == 1 and b.signal_count == 1 and b.status == "active"
    assert c.run_count == 1 and c.signal_count == 1 and c.status == "active"
    assert other.run_count == 0 and other.signal_count == 0


async def test_partial_baseline_skip(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, _ = await _make_pair(db_session)
    fake = _FakeSignalService(db_session, skip_versions=[b_ver.id])  # baseline skip
    res = await PaperSignalPairRunOnceService(db_session, fake).run_pair(b.id, c.id, True, "u")
    assert res.baseline.signal_created is False and res.baseline.reason
    assert res.challenger.signal_created is True  # challenger 그대로 진행
    await db_session.refresh(b); await db_session.refresh(c)
    assert b.run_count == 1 and b.signal_count == 0
    assert c.run_count == 1 and c.signal_count == 1  # 성공 SignalLog 롤백 안 함


async def test_market_data_error_one_side_skipped_not_crash(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, _ = await _make_pair(db_session)
    fake = _FakeSignalService(db_session, raise_versions=[c_ver.id])  # challenger 오류
    res = await PaperSignalPairRunOnceService(db_session, fake).run_pair(b.id, c.id, True, "u")
    assert res.baseline.signal_created is True
    assert res.challenger.signal_created is False and "error" in (res.challenger.reason or "")


async def test_no_side_effects(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, _ = await _make_pair(db_session)
    before = {
        "trade": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
        "exp": await _count(db_session, Experiment),
        "rv": await _count(db_session, ScannerRuleVersion),
        "ver": await _count(db_session, StrategyVersion),
        "sess": await _count(db_session, PaperSignalSession),
    }
    await PaperSignalPairRunOnceService(db_session, _FakeSignalService(db_session)).run_pair(b.id, c.id, True, "u")
    assert await _count(db_session, Trade) == before["trade"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
    assert await _count(db_session, Experiment) == before["exp"]
    assert await _count(db_session, ScannerRuleVersion) == before["rv"]
    assert await _count(db_session, StrategyVersion) == before["ver"]
    assert await _count(db_session, PaperSignalSession) == before["sess"]
    await db_session.refresh(b_ver); await db_session.refresh(c_ver)
    assert b_ver.status == StrategyVersionStatus.DRAFT and c_ver.status == StrategyVersionStatus.DRAFT


# --- API ---------------------------------------------------------------------
async def test_api_pair(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, _ = await _make_pair(db_session)
    fake = _FakeSignalService(db_session)
    app.dependency_overrides[get_db] = _override(db_session)
    from app.api.v1.candidates import get_pair_run_once_service
    app.dependency_overrides[get_pair_run_once_service] = lambda: PaperSignalPairRunOnceService(db_session, fake)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cl:
            EP = f"/api/v1/paper-signal-sessions/{b.id}/compare/{c.id}/run-once-pair"
            assert (await cl.post(EP, json={"confirmed": False, "confirmed_by": "u"})).status_code == 422
            assert (await cl.post(f"/api/v1/paper-signal-sessions/999999/compare/{c.id}/run-once-pair",
                                  json={"confirmed": True, "confirmed_by": "u"})).status_code == 404
            r = await cl.post(EP, json={"confirmed": True, "confirmed_by": "manual_user"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["baseline"]["session_id"] == b.id
            assert body["challenger"]["session_id"] == c.id
            assert body["orders_created"] == 0 and body["trades_created"] == 0
            assert body["runner_enabled"] is False
            assert any("SignalLogs only" in w for w in body["warnings"])
    finally:
        app.dependency_overrides.clear()
