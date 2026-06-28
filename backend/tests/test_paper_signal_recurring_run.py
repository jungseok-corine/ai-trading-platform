"""M2.14A: pair-scoped recurring signal run plan — schema + inert plan management.

계획만 만든다(실행 없음): prepared only · SignalLog/Trade/Order 없음 · 스케줄러/잡 미활성 · 디스패처 없음.
자격 검증은 M2.8/M2.10 코어 재사용. SignalService는 주입하지 않는다(검증 전용).
"""
from datetime import datetime, timezone

import app.services.paper_signal_run_once_service as run_once_mod
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import ProposalStatus, StrategyVersionStatus
from app.domain.models.paper_signal_recurring_run import PaperSignalRecurringRun
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.repositories.paper_signal_recurring_run import (
    PaperSignalRecurringRunRepository,
)
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.models.trade import Trade
from app.main import app
from app.services.paper_signal_pair_run_once_service import (
    BaselineMismatchError,
    NotChallengerSessionError,
    SymbolMismatchError,
)
from app.services.paper_signal_recurring_run_service import (
    DuplicateRecurringPlanError,
    PaperSignalRecurringRunService,
    RecurringBaselineNotFoundError,
    RecurringChallengerNotFoundError,
    RecurringConfirmationRequiredError,
    RecurringInvalidIntervalError,
    RecurringInvalidMaxRunsError,
    RecurringPlanNotActivatableError,
    RecurringPlanNotFoundError,
    RecurringPlanNotStoppableError,
)
from app.services.paper_signal_run_once_service import (
    RealTradingEnabledError,
    RunnerEnabledError,
    SessionNotActiveError,
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
    def __init__(self, real=False, runner=False, dispatcher=False):
        self.kis_real_trading_enabled = real
        self.paper_signal_session_runner_enabled = runner
        self.paper_signal_recurring_plan_dispatcher_enabled = dispatcher


async def _version(db, strat, no, *, status=StrategyVersionStatus.DRAFT, auto=False,
                   strategy_type="moving_average_cross", symbol="005930"):
    v = StrategyVersion(strategy_id=strat.id, version_no=no, status=status,
                        parameters={"strategy_type": strategy_type, "symbol_code": symbol,
                                    "auto_trade_enabled": auto})
    db.add(v); await db.flush()
    return v


async def _session(db, ver, *, status="active", symbol="005930", source_type="candidate_proposal",
                   baseline_id=None, sp_id=None, cand_id=None):
    row = PaperSignalSession(
        candidate_strategy_proposal_id=cand_id, strategy_version_id=(ver.id if ver else None),
        symbol_code=symbol, status=status, started_by="t", source_type=source_type,
        baseline_session_id=baseline_id, source_strategy_proposal_id=sp_id)
    db.add(row); await db.flush()
    return row


async def _make_pair(db, *, symbol="005930", chal_symbol=None, chal_baseline=None,
                     chal_source="signal_challenger", b_auto=False, c_auto=False,
                     b_ver_status=StrategyVersionStatus.DRAFT, c_ver_status=StrategyVersionStatus.DRAFT,
                     b_status="active", c_status="active", c_no_version=False):
    rule = ScannerRule(name="RRule"); db.add(rule); await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[]); db.add(rv); await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code=symbol,
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand); await db.flush()
    strat = Strategy(name="RStrat", description="t"); db.add(strat); await db.flush()
    pc = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code=symbol,
                                   suggested_strategy_type="moving_average_cross",
                                   status="approved", source="manual"); db.add(pc); await db.flush()
    b_ver = await _version(db, strat, 1, status=b_ver_status, auto=b_auto, symbol=symbol)
    baseline = await _session(db, b_ver, status=b_status, symbol=symbol,
                              source_type="candidate_proposal", cand_id=pc.id)
    c_ver = await _version(db, strat, 2, status=c_ver_status, auto=c_auto,
                           symbol=(chal_symbol or symbol))
    sp = StrategyProposal(strategy_id=strat.id, title="t",
                          suggested_parameters={"strategy_type": "moving_average_cross"},
                          source="paper_signal_analysis", status=ProposalStatus.PENDING,
                          created_version_id=c_ver.id); db.add(sp); await db.flush()
    challenger = await _session(db, (None if c_no_version else c_ver), status=c_status,
                                symbol=(chal_symbol or symbol), source_type=chal_source,
                                baseline_id=(chal_baseline if chal_baseline is not None else baseline.id),
                                sp_id=sp.id)
    return baseline, challenger, b_ver, c_ver, strat, sp, pc


def _svc(db):
    return PaperSignalRecurringRunService(db)


async def _create(db, b, c, **kw):
    params = dict(baseline_session_id=b.id, challenger_session_id=c.id,
                  interval_seconds=60, max_runs=30, confirmed=True, confirmed_by="u")
    params.update(kw)
    return await _svc(db).create_prepared_pair_plan(**params)


# --- confirmation gates ------------------------------------------------------
async def test_confirmed_false_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _create(db_session, b, c, confirmed=False)


async def test_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _create(db_session, b, c, confirmed_by=None)


# --- existence ---------------------------------------------------------------
async def test_unknown_baseline_404(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringBaselineNotFoundError):
        await _svc(db_session).create_prepared_pair_plan(
            baseline_session_id=999999, challenger_session_id=c.id,
            interval_seconds=60, max_runs=30, confirmed=True, confirmed_by="u")


async def test_unknown_challenger_404(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringChallengerNotFoundError):
        await _svc(db_session).create_prepared_pair_plan(
            baseline_session_id=b.id, challenger_session_id=999999,
            interval_seconds=60, max_runs=30, confirmed=True, confirmed_by="u")


# --- session/relationship gates (reused from M2.8/M2.10) ---------------------
async def test_baseline_not_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, b_status="stopped")
    with pytest.raises(SessionNotActiveError):
        await _create(db_session, b, c)


async def test_challenger_not_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_status="prepared")
    with pytest.raises(SessionNotActiveError):
        await _create(db_session, b, c)


async def test_challenger_not_signal_challenger_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, chal_source="candidate_proposal")
    with pytest.raises(NotChallengerSessionError):
        await _create(db_session, b, c)


async def test_baseline_mismatch_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    other_strat = Strategy(name="OtherB", description="t"); db_session.add(other_strat); await db_session.flush()
    other_ver = await _version(db_session, other_strat, 1)
    other_baseline = await _session(db_session, other_ver, source_type="candidate_proposal")
    with pytest.raises(BaselineMismatchError):
        await _create(db_session, other_baseline, c)


async def test_symbol_mismatch_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, chal_symbol="000660")
    with pytest.raises(SymbolMismatchError):
        await _create(db_session, b, c)


async def test_missing_version_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_no_version=True)
    from app.services.paper_signal_run_once_service import MissingVersionError
    with pytest.raises(MissingVersionError):
        await _create(db_session, b, c)


async def test_version_not_draft_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_ver_status=StrategyVersionStatus.TESTING)
    with pytest.raises(VersionNotDraftError):
        await _create(db_session, b, c)


async def test_auto_trade_enabled_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session, c_auto=True)
    with pytest.raises(VersionAutoTradeError):
        await _create(db_session, b, c)


# --- global gates ------------------------------------------------------------
async def test_real_trading_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(real=True))
    with pytest.raises(RealTradingEnabledError):
        await _create(db_session, b, c)


async def test_runner_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(runner=True))
    with pytest.raises(RunnerEnabledError):
        await _create(db_session, b, c)


# --- parameter ranges --------------------------------------------------------
async def test_interval_too_small_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringInvalidIntervalError):
        await _create(db_session, b, c, interval_seconds=10)


async def test_interval_too_large_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringInvalidIntervalError):
        await _create(db_session, b, c, interval_seconds=99999)


async def test_max_runs_too_small_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringInvalidMaxRunsError):
        await _create(db_session, b, c, max_runs=0)


async def test_max_runs_too_large_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    with pytest.raises(RecurringInvalidMaxRunsError):
        await _create(db_session, b, c, max_runs=100000)


# --- duplicate guard ---------------------------------------------------------
async def test_duplicate_prepared_plan_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    await _create(db_session, b, c)
    with pytest.raises(DuplicateRecurringPlanError):
        await _create(db_session, b, c)


# --- happy path + no-execution proof ----------------------------------------
async def test_create_returns_prepared_and_inert(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    result = await _create(db_session, b, c, interval_seconds=120, max_runs=5)
    assert result["status"] == "prepared"
    assert result["scope_type"] == "baseline_challenger_pair"
    assert result["baseline_session_id"] == b.id
    assert result["challenger_session_id"] == c.id
    assert result["interval_seconds"] == 120
    assert result["max_runs"] == 5
    assert result["completed_runs"] == 0
    assert result["next_run_at"] is None  # inert — no schedule
    assert result["orders_created"] == 0
    assert result["trades_created"] == 0
    assert result["created_by"] == "u"
    assert len(result["warnings"]) == 3


async def test_create_makes_exactly_one_row_and_no_signal_or_trade(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    signals_before = await _count(db_session, SignalLog)
    trades_before = await _count(db_session, Trade)
    await _create(db_session, b, c)
    assert await _count(db_session, PaperSignalRecurringRun) == 1
    assert await _count(db_session, SignalLog) == signals_before  # no SignalLog
    assert await _count(db_session, Trade) == trades_before  # no Trade


async def test_create_does_not_mutate_session_version_proposal_status(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, strat, sp, pc = await _make_pair(db_session)
    await _create(db_session, b, c)
    await db_session.refresh(b); await db_session.refresh(c)
    await db_session.refresh(b_ver); await db_session.refresh(c_ver)
    await db_session.refresh(sp); await db_session.refresh(pc)
    assert b.status == "active" and c.status == "active"
    assert b_ver.status == StrategyVersionStatus.DRAFT
    assert c_ver.status == StrategyVersionStatus.DRAFT
    assert sp.status == ProposalStatus.PENDING
    assert pc.status == "approved"


# --- stop --------------------------------------------------------------------
async def test_stop_prepared_succeeds(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    stopped = await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    assert stopped["status"] == "stopped"
    assert stopped["stopped_by"] == "u"
    assert stopped["stopped_at"] is not None


async def test_stop_unknown_404(db_session: AsyncSession) -> None:
    with pytest.raises(RecurringPlanNotFoundError):
        await _svc(db_session).stop_plan(999999, confirmed=True, confirmed_by="u")


async def test_stop_already_stopped_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    with pytest.raises(RecurringPlanNotStoppableError):
        await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")


async def test_stop_confirmed_false_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _svc(db_session).stop_plan(created["id"], confirmed=False, confirmed_by="u")


async def test_stop_does_not_create_signal_or_trade(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    signals_before = await _count(db_session, SignalLog)
    trades_before = await _count(db_session, Trade)
    await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    assert await _count(db_session, SignalLog) == signals_before
    assert await _count(db_session, Trade) == trades_before


async def test_stopped_plan_allows_new_prepared_for_same_pair(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    # 종료된 계획이 있어도 같은 페어에 새 prepared 계획 생성은 허용된다.
    again = await _create(db_session, b, c)
    assert again["status"] == "prepared"
    assert again["id"] != created["id"]


# --- read / list -------------------------------------------------------------
async def test_get_by_id_and_list_and_status_filter(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    got = await _svc(db_session).get_plan(created["id"])
    assert got["id"] == created["id"]
    all_plans = await _svc(db_session).list_plans()
    assert any(p["id"] == created["id"] for p in all_plans)
    prepared = await _svc(db_session).list_plans(status="prepared")
    assert all(p["status"] == "prepared" for p in prepared)
    stopped = await _svc(db_session).list_plans(status="stopped")
    assert all(p["status"] == "stopped" for p in stopped)


async def test_get_unknown_404(db_session: AsyncSession) -> None:
    with pytest.raises(RecurringPlanNotFoundError):
        await _svc(db_session).get_plan(999999)


# --- API smoke ---------------------------------------------------------------
async def test_api_create_stop_duplicate_flow(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    app.dependency_overrides[get_db] = _override(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            # 201 create
            r = await ac.post("/api/v1/paper-signal-recurring-runs", json={
                "baseline_session_id": b.id, "challenger_session_id": c.id,
                "interval_seconds": 60, "max_runs": 10,
                "confirmed": True, "confirmed_by": "u"})
            assert r.status_code == 201, r.text
            plan = r.json()
            assert plan["status"] == "prepared"
            assert plan["orders_created"] == 0 and plan["trades_created"] == 0
            # 409 duplicate
            r2 = await ac.post("/api/v1/paper-signal-recurring-runs", json={
                "baseline_session_id": b.id, "challenger_session_id": c.id,
                "interval_seconds": 60, "max_runs": 10,
                "confirmed": True, "confirmed_by": "u"})
            assert r2.status_code == 409, r2.text
            # GET by id
            rg = await ac.get(f"/api/v1/paper-signal-recurring-runs/{plan['id']}")
            assert rg.status_code == 200
            # list
            rl = await ac.get("/api/v1/paper-signal-recurring-runs")
            assert rl.status_code == 200 and len(rl.json()) >= 1
            # stop 200
            rs = await ac.post(
                f"/api/v1/paper-signal-recurring-runs/{plan['id']}/stop",
                json={"confirmed": True, "confirmed_by": "u"})
            assert rs.status_code == 200 and rs.json()["status"] == "stopped"
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_api_confirm_false_422_and_unknown_404(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    app.dependency_overrides[get_db] = _override(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post("/api/v1/paper-signal-recurring-runs", json={
                "baseline_session_id": b.id, "challenger_session_id": c.id,
                "interval_seconds": 60, "max_runs": 10,
                "confirmed": False, "confirmed_by": "u"})
            assert r.status_code == 422, r.text
            rg = await ac.get("/api/v1/paper-signal-recurring-runs/999999")
            assert rg.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


# ============================================================================
# M2.14B-1: activation/deactivation state management (no execution)
# ============================================================================
from app.domain.models.signal_log import SignalLog as _SL  # noqa: E402


async def _activate(db, plan_id, **kw):
    params = dict(confirmed=True, confirmed_by="u"); params.update(kw)
    return await _svc(db).activate_plan(plan_id, **params)


# --- activation gates --------------------------------------------------------
async def test_activate_confirmed_false_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _activate(db_session, created["id"], confirmed=False)


async def test_activate_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _activate(db_session, created["id"], confirmed_by=None)


async def test_activate_unknown_404(db_session: AsyncSession) -> None:
    with pytest.raises(RecurringPlanNotFoundError):
        await _activate(db_session, 999999)


async def test_activate_prepared_succeeds_and_sets_metadata(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c, interval_seconds=60)
    result = await _activate(db_session, created["id"])
    assert result["status"] == "active"
    assert result["next_run_at"] is not None  # future dispatcher metadata
    assert result["completed_runs"] == 0
    assert result["last_run_at"] is None
    assert result["orders_created"] == 0
    assert result["trades_created"] == 0
    assert any("no dispatcher" in w.lower() for w in result["warnings"])


async def test_activate_creates_no_signal_or_trade(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    sl_before = await _count(db_session, _SL)
    tr_before = await _count(db_session, Trade)
    await _activate(db_session, created["id"])
    assert await _count(db_session, _SL) == sl_before
    assert await _count(db_session, Trade) == tr_before


async def test_activate_does_not_mutate_sessions_versions_proposals(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, strat, sp, pc = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _activate(db_session, created["id"])
    await db_session.refresh(b); await db_session.refresh(c)
    await db_session.refresh(b_ver); await db_session.refresh(c_ver)
    await db_session.refresh(sp); await db_session.refresh(pc)
    assert b.status == "active" and c.status == "active"
    assert b_ver.status == StrategyVersionStatus.DRAFT
    assert c_ver.status == StrategyVersionStatus.DRAFT
    assert sp.status == ProposalStatus.PENDING
    assert pc.status == "approved"


async def test_activate_already_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _activate(db_session, created["id"])
    with pytest.raises(RecurringPlanNotActivatableError):
        await _activate(db_session, created["id"])


async def test_activate_stopped_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    with pytest.raises(RecurringPlanNotActivatableError):
        await _activate(db_session, created["id"])


async def test_activate_real_trading_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(real=True))
    with pytest.raises(RealTradingEnabledError):
        await _activate(db_session, created["id"])


async def test_activate_runner_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(runner=True))
    with pytest.raises(RunnerEnabledError):
        await _activate(db_session, created["id"])


# --- activation re-validation (state changed after create) -------------------
async def test_activate_baseline_no_longer_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    b.status = "stopped"; await db_session.flush()
    with pytest.raises(SessionNotActiveError):
        await _activate(db_session, created["id"])


async def test_activate_challenger_no_longer_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    c.status = "stopped"; await db_session.flush()
    with pytest.raises(SessionNotActiveError):
        await _activate(db_session, created["id"])


async def test_activate_relationship_mismatch_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    c.source_type = "candidate_proposal"; await db_session.flush()
    with pytest.raises(NotChallengerSessionError):
        await _activate(db_session, created["id"])


async def test_activate_version_no_longer_draft_rejected(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    c_ver.status = StrategyVersionStatus.TESTING; await db_session.flush()
    with pytest.raises(VersionNotDraftError):
        await _activate(db_session, created["id"])


async def test_activate_auto_trade_enabled_rejected(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    c_ver.parameters = {**c_ver.parameters, "auto_trade_enabled": True}
    await db_session.flush()
    with pytest.raises(VersionAutoTradeError):
        await _activate(db_session, created["id"])


async def test_activate_duplicate_active_for_pair_rejected(db_session: AsyncSession) -> None:
    # 같은 페어에 두 prepared 행을 직접 만들고(서비스 가드 우회) 둘 다 활성화 시도.
    b, c, *_ = await _make_pair(db_session)
    repo = PaperSignalRecurringRunRepository(db_session)
    common = dict(scope_type="baseline_challenger_pair", baseline_session_id=b.id,
                  challenger_session_id=c.id, interval_seconds=60, max_runs=10,
                  completed_runs=0, created_by="u")
    p1 = await repo.create(status="prepared", **common)
    p2 = await repo.create(status="prepared", **common)
    await db_session.commit()
    await _activate(db_session, p1.id)  # first → active
    with pytest.raises(DuplicateRecurringPlanError):
        await _activate(db_session, p2.id)  # second → duplicate active


# --- stop active -------------------------------------------------------------
async def test_stop_active_succeeds_and_clears_next_run_at(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    activated = await _activate(db_session, created["id"])
    assert activated["next_run_at"] is not None
    stopped = await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    assert stopped["status"] == "stopped"
    assert stopped["next_run_at"] is None
    assert stopped["completed_runs"] == 0
    assert stopped["last_run_at"] is None


async def test_stop_active_creates_no_signal_or_trade_and_no_mutation(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, strat, sp, pc = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _activate(db_session, created["id"])
    sl_before = await _count(db_session, _SL)
    tr_before = await _count(db_session, Trade)
    await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    assert await _count(db_session, _SL) == sl_before
    assert await _count(db_session, Trade) == tr_before
    await db_session.refresh(b); await db_session.refresh(c_ver); await db_session.refresh(sp)
    assert b.status == "active"
    assert c_ver.status == StrategyVersionStatus.DRAFT
    assert sp.status == ProposalStatus.PENDING


async def test_stopped_active_allows_new_prepared_for_same_pair(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _activate(db_session, created["id"])
    await _svc(db_session).stop_plan(created["id"], confirmed=True, confirmed_by="u")
    again = await _create(db_session, b, c)  # terminal plan no longer blocks
    assert again["status"] == "prepared"


# --- list active -------------------------------------------------------------
async def test_list_status_active(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)
    await _activate(db_session, created["id"])
    active = await _svc(db_session).list_plans(status="active")
    assert all(p["status"] == "active" for p in active)
    assert any(p["id"] == created["id"] for p in active)


# --- API smoke: activate + stop-active --------------------------------------
async def test_api_activate_and_stop_active_flow(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    app.dependency_overrides[get_db] = _override(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post("/api/v1/paper-signal-recurring-runs", json={
                "baseline_session_id": b.id, "challenger_session_id": c.id,
                "interval_seconds": 60, "max_runs": 10,
                "confirmed": True, "confirmed_by": "u"})
            assert r.status_code == 201
            pid = r.json()["id"]
            ra = await ac.post(f"/api/v1/paper-signal-recurring-runs/{pid}/activate",
                               json={"confirmed": True, "confirmed_by": "u"})
            assert ra.status_code == 200, ra.text
            body = ra.json()
            assert body["status"] == "active" and body["next_run_at"] is not None
            assert body["orders_created"] == 0 and body["trades_created"] == 0
            # activating again → 422
            ra2 = await ac.post(f"/api/v1/paper-signal-recurring-runs/{pid}/activate",
                                json={"confirmed": True, "confirmed_by": "u"})
            assert ra2.status_code == 422
            # stop active → 200
            rs = await ac.post(f"/api/v1/paper-signal-recurring-runs/{pid}/stop",
                               json={"confirmed": True, "confirmed_by": "u"})
            assert rs.status_code == 200 and rs.json()["status"] == "stopped"
            assert rs.json()["next_run_at"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


# ============================================================================
# M2.14B-2: manual tick-once for one active plan (selected-plan, SignalLog-only)
# ============================================================================
from datetime import datetime as _dt, timezone as _tz  # noqa: E402

from app.common.timezone import KST  # noqa: E402
from app.domain.models.enums import TradeSide  # noqa: E402
from app.services.paper_signal_recurring_run_service import (  # noqa: E402
    RecurringPlanExhaustedError,
    RecurringPlanNotTickableError,
)


class _FakeSignalService:
    """version_id별 동작: skip_versions→None(미생성), 그 외→SignalLog 생성. 네트워크 없음."""

    def __init__(self, db, skip_versions=None):
        self._db = db
        self.skip = set(skip_versions or [])
        self.calls = []

    async def generate_and_log_signal(self, strategy, symbol_code, version_id, **kw):
        self.calls.append((symbol_code, version_id))
        if version_id in self.skip:
            return None
        log = SignalLog(symbol_code=symbol_code, signal_type=TradeSide.BUY,
                        generated_at=_dt.now(KST),
                        candle_ts=_dt(2026, 6, 10, 9, 30, tzinfo=KST), market="KR",
                        timeframe="1m", strategy_version_id=version_id)
        self._db.add(log); await self._db.flush()
        return log


def _tick_svc(db, **fakekw):
    return PaperSignalRecurringRunService(db, signal_service=_FakeSignalService(db, **fakekw))


async def _make_active_plan(db, b, c, **create_kw):
    created = await _create(db, b, c, **create_kw)
    await _svc(db).activate_plan(created["id"], confirmed=True, confirmed_by="u")
    return created["id"]


# --- tick success ------------------------------------------------------------
async def test_tick_creates_two_signals_and_advances(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=5, interval_seconds=60)
    sl_before = await _count(db_session, SignalLog)
    result = await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")
    assert result["baseline"]["signal_created"] is True
    assert result["challenger"]["signal_created"] is True
    assert await _count(db_session, SignalLog) == sl_before + 2
    assert result["completed_runs"] == 1
    assert result["last_run_at"] is not None
    assert result["status"] == "active"
    assert result["next_run_at"] is not None
    assert result["orders_created"] == 0 and result["trades_created"] == 0


async def test_tick_only_selected_sessions_third_untouched(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, strat, sp, pc = await _make_pair(db_session)
    # 제3의 active signal_challenger 세션(다른 baseline) — tick이 건드리면 안 됨.
    other_ver = await _version(db_session, strat, 3)
    other_base = await _session(db_session, other_ver, source_type="candidate_proposal")
    other_chal = await _session(db_session, await _version(db_session, strat, 4),
                                source_type="signal_challenger", baseline_id=other_base.id, sp_id=sp.id)
    pid = await _make_active_plan(db_session, b, c, max_runs=5)
    await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")
    sids = {b.id, c.id}
    logs = (await db_session.execute(select(SignalLog.paper_signal_session_id))).scalars().all()
    assert all((s in sids) for s in logs if s is not None)
    await db_session.refresh(other_chal)
    assert other_chal.signal_count == 0  # third session untouched


async def test_tick_skipped_side_still_increments(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=5)
    sl_before = await _count(db_session, SignalLog)
    svc = _tick_svc(db_session, skip_versions={c_ver.id})  # challenger skips
    result = await svc.tick_plan_once(pid, confirmed=True, confirmed_by="u")
    assert result["baseline"]["signal_created"] is True
    assert result["challenger"]["signal_created"] is False
    assert await _count(db_session, SignalLog) == sl_before + 1  # only baseline
    assert result["completed_runs"] == 1  # attempt still counts


async def test_tick_reaches_max_runs_completes(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=1)
    result = await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")
    assert result["status"] == "completed"
    assert result["completed_runs"] == 1
    assert result["next_run_at"] is None


async def test_tick_creates_no_trade(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=5)
    tr_before = await _count(db_session, Trade)
    await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")
    assert await _count(db_session, Trade) == tr_before


async def test_tick_does_not_mutate_sessions_versions_proposals(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, strat, sp, pc = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=5)
    await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")
    await db_session.refresh(b); await db_session.refresh(c)
    await db_session.refresh(b_ver); await db_session.refresh(c_ver)
    await db_session.refresh(sp); await db_session.refresh(pc)
    assert b.status == "active" and c.status == "active"
    assert b_ver.status == StrategyVersionStatus.DRAFT
    assert c_ver.status == StrategyVersionStatus.DRAFT
    assert sp.status == ProposalStatus.PENDING
    assert pc.status == "approved"


# --- tick gates --------------------------------------------------------------
async def test_tick_confirmed_false_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=False, confirmed_by="u")


async def test_tick_missing_confirmed_by_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    with pytest.raises(RecurringConfirmationRequiredError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by=None)


async def test_tick_unknown_404(db_session: AsyncSession) -> None:
    with pytest.raises(RecurringPlanNotFoundError):
        await _tick_svc(db_session).tick_plan_once(999999, confirmed=True, confirmed_by="u")


async def test_tick_prepared_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    created = await _create(db_session, b, c)  # prepared, not activated
    with pytest.raises(RecurringPlanNotTickableError):
        await _tick_svc(db_session).tick_plan_once(created["id"], confirmed=True, confirmed_by="u")


async def test_tick_stopped_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    await _svc(db_session).stop_plan(pid, confirmed=True, confirmed_by="u")
    with pytest.raises(RecurringPlanNotTickableError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_completed_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=1)
    await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")  # → completed
    with pytest.raises(RecurringPlanNotTickableError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_exhausted_rejected(db_session: AsyncSession) -> None:
    # status=active 인데 completed_runs>=max_runs인 방어적 상태를 직접 만든다.
    b, c, *_ = await _make_pair(db_session)
    repo = PaperSignalRecurringRunRepository(db_session)
    plan = await repo.create(status="active", scope_type="baseline_challenger_pair",
                             baseline_session_id=b.id, challenger_session_id=c.id,
                             interval_seconds=60, max_runs=3, completed_runs=3, created_by="u")
    await db_session.commit()
    with pytest.raises(RecurringPlanExhaustedError):
        await _tick_svc(db_session).tick_plan_once(plan.id, confirmed=True, confirmed_by="u")


async def test_tick_real_trading_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(real=True))
    with pytest.raises(RealTradingEnabledError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_runner_enabled_rejected(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    monkeypatch.setattr(run_once_mod, "get_settings", lambda: _FakeSettings(runner=True))
    with pytest.raises(RunnerEnabledError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_baseline_no_longer_active_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    b.status = "stopped"; await db_session.flush()
    with pytest.raises(SessionNotActiveError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_challenger_relationship_changed_rejected(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    c.source_type = "candidate_proposal"; await db_session.flush()
    with pytest.raises(NotChallengerSessionError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_version_no_longer_draft_rejected(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    c_ver.status = StrategyVersionStatus.TESTING; await db_session.flush()
    with pytest.raises(VersionNotDraftError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_auto_trade_enabled_rejected(db_session: AsyncSession) -> None:
    b, c, b_ver, c_ver, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c)
    c_ver.parameters = {**c_ver.parameters, "auto_trade_enabled": True}
    await db_session.flush()
    with pytest.raises(VersionAutoTradeError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")


async def test_tick_validation_failure_does_not_increment(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    pid = await _make_active_plan(db_session, b, c, max_runs=5)
    b.status = "stopped"; await db_session.flush()
    with pytest.raises(SessionNotActiveError):
        await _tick_svc(db_session).tick_plan_once(pid, confirmed=True, confirmed_by="u")
    plan = await PaperSignalRecurringRunRepository(db_session).get(pid)
    assert plan.completed_runs == 0  # no increment on pre-eval validation failure


# --- API smoke ---------------------------------------------------------------
async def test_api_tick_once_flow(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    # 서비스로 prepared+active 준비(실 broker DI 없이).
    pid = await _make_active_plan(db_session, b, c, max_runs=5)

    # tick DI를 fake signal_service로 오버라이드(네트워크 차단).
    from app.api.v1 import paper_signal_recurring_runs as rr_api
    app.dependency_overrides[get_db] = _override(db_session)
    app.dependency_overrides[rr_api.get_recurring_run_tick_service] = (
        lambda: _tick_svc(db_session)
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.post(f"/api/v1/paper-signal-recurring-runs/{pid}/tick-once",
                              json={"confirmed": True, "confirmed_by": "smoke"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "active"
            assert body["completed_runs"] == 1
            assert body["orders_created"] == 0 and body["trades_created"] == 0
            assert body["baseline"]["session_id"] == b.id
            assert body["challenger"]["session_id"] == c.id
            assert any("dispatcher" in w.lower() for w in body["warnings"])
            # tick unknown plan → 404
            r404 = await ac.post("/api/v1/paper-signal-recurring-runs/999999/tick-once",
                                 json={"confirmed": True, "confirmed_by": "smoke"})
            assert r404.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(rr_api.get_recurring_run_tick_service, None)


# --- M2.14B-3b: read-only dispatcher readiness API ---------------------------
from datetime import timedelta as _td  # noqa: E402
import app.services.paper_signal_recurring_run_service as _rr_svc_mod  # noqa: E402

_READINESS_URL = "/api/v1/paper-signal-recurring-runs/dispatcher/readiness"


async def _insert_plan(db, b, c, *, status, next_run_at=None, completed_runs=0,
                       max_runs=30, last_error=None):
    """readiness 카운트 테스트용 row 직접 삽입(서비스 우회 — 다양한 상태를 만들기 위함)."""
    row = PaperSignalRecurringRun(
        status=status, scope_type="baseline_challenger_pair",
        baseline_session_id=b.id, challenger_session_id=c.id,
        interval_seconds=60, max_runs=max_runs, completed_runs=completed_runs,
        next_run_at=next_run_at, last_error=last_error, created_by="t")
    db.add(row); await db.flush()
    return row


async def _get_readiness(db_session):
    app.dependency_overrides[get_db] = _override(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r = await ac.get(_READINESS_URL)
        return r
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_readiness_endpoint_200_shape(db_session: AsyncSession) -> None:
    r = await _get_readiness(db_session)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dispatcher_stage"] == "service_core_direct_invocation_only"
    # 서비스 코어(3c)는 존재하지만 스케줄/노출 디스패처는 미구현 → 외부 실행 불가.
    assert body["dispatcher_implemented"] is False
    assert body["service_core_implemented"] is True
    assert body["scheduler_dispatcher_implemented"] is False
    assert body["api_execution_endpoint_registered"] is False
    assert body["scheduler_job_registered"] is False
    assert body["can_execute"] is False
    assert body["execution_blocked_reason"] == "scheduler_and_api_execution_not_implemented"
    assert "scheduler_job_not_registered" in body["readiness_blockers"]
    assert "api_execution_endpoint_not_registered" in body["readiness_blockers"]
    # 안전 불변식 표식
    inv = body["safety_invariants"]
    assert inv["scans_recurring_runs_only"] is True
    assert inv["global_runner_forbidden"] is True
    assert inv["orders_forbidden"] is True and inv["trades_forbidden"] is True
    assert inv["broker_kis_forbidden"] is True
    # 읽기 전용/무실행 경고
    joined = " ".join(body["warnings"]).lower()
    assert "read-only" in joined
    assert "no signallog" in joined or "no plans are ticked" in joined


async def test_readiness_default_flags_safe(db_session: AsyncSession) -> None:
    r = await _get_readiness(db_session)
    cfg = r.json()["config"]
    assert cfg["paper_signal_recurring_plan_dispatcher_enabled"] is False
    assert cfg["paper_signal_session_runner_enabled"] is False
    assert cfg["kis_real_trading_enabled"] is False


async def test_readiness_route_not_shadowed_by_plan_id(db_session: AsyncSession) -> None:
    # 정적 dispatcher/readiness 라우트가 /{plan_id}(int)로 파싱되지 않아야 한다.
    r = await _get_readiness(db_session)
    assert r.status_code == 200, r.text
    assert r.json()["dispatcher_stage"] == "service_core_direct_invocation_only"
    # 참고: 단일 세그먼트 /dispatcher는 {plan_id:int} 파싱 실패로 422 (별 라우트임을 방증).
    app.dependency_overrides[get_db] = _override(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as ac:
            r2 = await ac.get("/api/v1/paper-signal-recurring-runs/dispatcher")
        assert r2.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_readiness_counts_correct(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    now = datetime.now(timezone.utc)
    await _insert_plan(db_session, b, c, status="prepared")
    await _insert_plan(db_session, b, c, status="stopped")
    await _insert_plan(db_session, b, c, status="completed")
    await _insert_plan(db_session, b, c, status="failed", last_error="boom")
    # active 4종(상호 배타): due / not_due / missing_next / exhausted
    await _insert_plan(db_session, b, c, status="active",
                       next_run_at=now - _td(seconds=60), completed_runs=0)          # due
    await _insert_plan(db_session, b, c, status="active",
                       next_run_at=now + _td(hours=1), completed_runs=0,
                       last_error="warn")                                            # not_due
    await _insert_plan(db_session, b, c, status="active",
                       next_run_at=None, completed_runs=0)                           # missing_next
    await _insert_plan(db_session, b, c, status="active",
                       next_run_at=now - _td(seconds=60), completed_runs=30,
                       max_runs=30)                                                  # exhausted
    r = await _get_readiness(db_session)
    pc = r.json()["plan_counts"]
    assert pc["total"] == 8
    assert pc["prepared"] == 1 and pc["stopped"] == 1
    assert pc["completed"] == 1 and pc["failed"] == 1
    assert pc["active"] == 4
    assert pc["due_active"] == 1
    assert pc["not_due_active"] == 1
    assert pc["active_missing_next_run_at"] == 1
    assert pc["active_exhausted"] == 1
    assert pc["with_last_error"] == 2


async def test_readiness_no_mutation(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    now = datetime.now(timezone.utc)
    plan = await _insert_plan(db_session, b, c, status="active",
                              next_run_at=now - _td(seconds=60), completed_runs=3)
    before_plans = await _count(db_session, PaperSignalRecurringRun)
    before_signals = await _count(db_session, SignalLog)
    before_trades = await _count(db_session, Trade)
    snap = (plan.status, plan.completed_runs, plan.last_run_at, plan.next_run_at, plan.last_error)

    r = await _get_readiness(db_session)
    assert r.status_code == 200

    await db_session.refresh(plan)
    assert (plan.status, plan.completed_runs, plan.last_run_at, plan.next_run_at,
            plan.last_error) == snap
    assert await _count(db_session, PaperSignalRecurringRun) == before_plans
    assert await _count(db_session, SignalLog) == before_signals
    assert await _count(db_session, Trade) == before_trades


async def test_readiness_no_execution_path(db_session: AsyncSession, monkeypatch) -> None:
    b, c, *_ = await _make_pair(db_session)
    await _insert_plan(db_session, b, c, status="active",
                       next_run_at=datetime.now(timezone.utc) - _td(seconds=60))

    def _boom(*a, **k):
        raise AssertionError("execution path must not be called by readiness")

    # readiness가 어떤 실행 경로도 호출하지 않음을 보장(스파이).
    monkeypatch.setattr(_rr_svc_mod.PaperSignalRecurringRunService, "tick_plan_once", _boom)
    before_signals = await _count(db_session, SignalLog)
    before_trades = await _count(db_session, Trade)

    r = await _get_readiness(db_session)
    assert r.status_code == 200
    assert r.json()["can_execute"] is False
    assert await _count(db_session, SignalLog) == before_signals
    assert await _count(db_session, Trade) == before_trades


async def test_readiness_flag_true_still_non_executing(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _FakeSettings(dispatcher=True))
    before_signals = await _count(db_session, SignalLog)
    before_trades = await _count(db_session, Trade)

    r = await _get_readiness(db_session)
    assert r.status_code == 200
    body = r.json()
    # 플래그는 True로 보고되지만 실행은 여전히 불가.
    assert body["config"]["paper_signal_recurring_plan_dispatcher_enabled"] is True
    assert body["can_execute"] is False
    assert body["execution_blocked_reason"] == "scheduler_and_api_execution_not_implemented"
    assert await _count(db_session, SignalLog) == before_signals
    assert await _count(db_session, Trade) == before_trades


# ============================================================================
# M2.14B-3c: disabled-by-default dispatcher service core (direct invocation only)
# ============================================================================
from sqlalchemy.dialects import postgresql as _pg  # noqa: E402
from app.services.paper_signal_recurring_run_service import (  # noqa: E402
    MAX_DISPATCH_BATCH,
)


def _disp_settings(dispatcher=False, real=False, runner=False):
    return _FakeSettings(real=real, runner=runner, dispatcher=dispatcher)


async def _due_active(db, b, c, *, next_offset=-60, completed_runs=0, max_runs=5):
    """due active 계획을 직접 삽입(next_run_at = now+next_offset초)."""
    return await _insert_plan(
        db, b, c, status="active",
        next_run_at=datetime.now(timezone.utc) + _td(seconds=next_offset),
        completed_runs=completed_runs, max_runs=max_runs)


# --- A. disabled-by-default / blocked ---------------------------------------
async def test_dispatch_disabled_by_default_noop(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    plan = await _due_active(db_session, b, c)
    sl_before = await _count(db_session, SignalLog)
    snap = (plan.status, plan.completed_runs, plan.last_run_at, plan.next_run_at)

    res = await _svc(db_session).dispatch_due_recurring_plans_once()
    assert res["config_enabled"] is False
    assert res["can_execute"] is False
    assert res["blocked_reason"] == "dispatcher_disabled"
    assert res["selected_plan_ids"] == [] and res["processed_plan_ids"] == []
    assert res["plans_selected"] == 0 and res["plans_processed"] == 0
    assert res["signals_created"] == 0
    assert res["orders_created"] == 0 and res["trades_created"] == 0
    # 무변경
    assert await _count(db_session, SignalLog) == sl_before
    await db_session.refresh(plan)
    assert (plan.status, plan.completed_runs, plan.last_run_at, plan.next_run_at) == snap


# --- B. config true but safe gates ------------------------------------------
async def test_dispatch_blocked_real_trading(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings",
                        lambda: _disp_settings(dispatcher=True, real=True))
    b, c, *_ = await _make_pair(db_session)
    await _due_active(db_session, b, c)
    sl_before = await _count(db_session, SignalLog)
    res = await _svc(db_session).dispatch_due_recurring_plans_once()
    assert res["config_enabled"] is True and res["can_execute"] is False
    assert res["blocked_reason"] == "real_trading_enabled"
    assert res["plans_selected"] == 0 and res["signals_created"] == 0
    assert await _count(db_session, SignalLog) == sl_before
    assert await _count(db_session, Trade) == 0


async def test_dispatch_blocked_runner_enabled(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings",
                        lambda: _disp_settings(dispatcher=True, runner=True))
    b, c, *_ = await _make_pair(db_session)
    await _due_active(db_session, b, c)
    sl_before = await _count(db_session, SignalLog)
    res = await _svc(db_session).dispatch_due_recurring_plans_once()
    assert res["blocked_reason"] == "global_runner_enabled"
    assert res["can_execute"] is False and res["plans_selected"] == 0
    assert await _count(db_session, SignalLog) == sl_before
    assert await _count(db_session, Trade) == 0


# --- C. due plan selection (repo, paper_signal_recurring_runs only) ----------
async def test_select_due_only_eligible(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    now = datetime.now(timezone.utc)
    await _insert_plan(db_session, b, c, status="prepared")
    await _insert_plan(db_session, b, c, status="stopped")
    await _insert_plan(db_session, b, c, status="completed")
    await _insert_plan(db_session, b, c, status="failed")
    await _insert_plan(db_session, b, c, status="active", next_run_at=now + _td(hours=1))  # not due
    await _insert_plan(db_session, b, c, status="active", next_run_at=None)  # missing next
    await _insert_plan(db_session, b, c, status="active",
                       next_run_at=now - _td(seconds=60), completed_runs=5, max_runs=5)  # exhausted
    due = await _insert_plan(db_session, b, c, status="active", next_run_at=now - _td(seconds=60))
    repo = PaperSignalRecurringRunRepository(db_session)
    rows = await repo.select_due_for_dispatch(now, 10)
    assert [r.id for r in rows] == [due.id]


async def test_select_due_batch_limit_and_order(db_session: AsyncSession) -> None:
    b, c, *_ = await _make_pair(db_session)
    now = datetime.now(timezone.utc)
    p_old = await _insert_plan(db_session, b, c, status="active", next_run_at=now - _td(seconds=300))
    p_mid = await _insert_plan(db_session, b, c, status="active", next_run_at=now - _td(seconds=120))
    p_new = await _insert_plan(db_session, b, c, status="active", next_run_at=now - _td(seconds=10))
    repo = PaperSignalRecurringRunRepository(db_session)
    rows = await repo.select_due_for_dispatch(now, 2)
    # next_run_at asc → 가장 오래 due된 둘만(batch limit 준수).
    assert [r.id for r in rows] == [p_old.id, p_mid.id]
    assert p_new.id not in [r.id for r in rows]


async def test_select_due_uses_row_lock(db_session: AsyncSession, monkeypatch) -> None:
    repo = PaperSignalRecurringRunRepository(db_session)
    captured = {}
    orig = db_session.execute

    async def _spy(stmt, *a, **k):
        try:
            captured["sql"] = str(stmt.compile(dialect=_pg.dialect()))
        except Exception:
            captured["sql"] = ""
        return await orig(stmt, *a, **k)

    monkeypatch.setattr(db_session, "execute", _spy)
    await repo.select_due_for_dispatch(datetime.now(timezone.utc), 10)
    sql = captured["sql"].upper()
    assert "FOR UPDATE" in sql and "SKIP LOCKED" in sql


# --- D. direct invocation execution (dispatcher enabled) --------------------
async def test_dispatch_executes_due_plan(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _disp_settings(dispatcher=True))
    b, c, *_ = await _make_pair(db_session)
    plan = await _due_active(db_session, b, c, max_runs=5)
    sl_before = await _count(db_session, SignalLog)
    res = await _tick_svc(db_session).dispatch_due_recurring_plans_once()
    assert res["can_execute"] is True and res["blocked_reason"] is None
    assert res["plans_selected"] == 1 and res["plans_processed"] == 1
    assert res["selected_plan_ids"] == [plan.id] and res["processed_plan_ids"] == [plan.id]
    assert res["signals_created"] == 2
    assert res["orders_created"] == 0 and res["trades_created"] == 0
    assert await _count(db_session, SignalLog) == sl_before + 2
    await db_session.refresh(plan)
    assert plan.completed_runs == 1
    assert plan.last_run_at is not None
    assert plan.status == "active" and plan.next_run_at is not None


async def test_dispatch_max_runs_completes(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _disp_settings(dispatcher=True))
    b, c, *_ = await _make_pair(db_session)
    plan = await _due_active(db_session, b, c, completed_runs=0, max_runs=1)
    res = await _tick_svc(db_session).dispatch_due_recurring_plans_once()
    assert res["completed_plan_ids"] == [plan.id]
    await db_session.refresh(plan)
    assert plan.status == "completed" and plan.next_run_at is None and plan.completed_runs == 1


async def test_dispatch_third_session_untouched(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _disp_settings(dispatcher=True))
    b, c, b_ver, c_ver, strat, sp, pc = await _make_pair(db_session)
    other_base = await _session(db_session, await _version(db_session, strat, 3),
                                source_type="candidate_proposal")
    other_chal = await _session(db_session, await _version(db_session, strat, 4),
                                source_type="signal_challenger", baseline_id=other_base.id, sp_id=sp.id)
    await _due_active(db_session, b, c, max_runs=5)
    await _tick_svc(db_session).dispatch_due_recurring_plans_once()
    await db_session.refresh(other_chal)
    assert other_chal.signal_count == 0


async def test_dispatch_batch_limit_clamped(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _disp_settings(dispatcher=True))
    res = await _svc(db_session).dispatch_due_recurring_plans_once(batch_limit=999)
    assert res["requested_batch_limit"] == 999
    assert res["effective_batch_limit"] == MAX_DISPATCH_BATCH
    res0 = await _svc(db_session).dispatch_due_recurring_plans_once(batch_limit=0)
    assert res0["effective_batch_limit"] == 1


# --- E. no global/duplicate execution paths ---------------------------------
async def test_dispatch_selection_source_is_recurring_repo(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _disp_settings(dispatcher=True))
    b, c, *_ = await _make_pair(db_session)
    await _due_active(db_session, b, c, max_runs=5)
    svc = _tick_svc(db_session)
    calls = {"select_due": 0}
    orig = svc._repo.select_due_for_dispatch

    async def _spy(now, limit):
        calls["select_due"] += 1
        return await orig(now, limit)

    monkeypatch.setattr(svc._repo, "select_due_for_dispatch", _spy)
    # PaperSignalSession 스캔(list_active)은 디스패처가 호출하면 안 된다 — 존재하면 폭파시켜 증명.
    if hasattr(svc._session_repo, "list_active"):
        monkeypatch.setattr(svc._session_repo, "list_active",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("list_active called")))
    res = await svc.dispatch_due_recurring_plans_once()
    assert calls["select_due"] == 1  # 선택 소스는 recurring repo만
    assert res["plans_processed"] == 1


# --- F. sequential dispatch does not double-tick (next_run_at advanced) ------
async def test_dispatch_sequential_no_double_tick(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(_rr_svc_mod, "get_settings", lambda: _disp_settings(dispatcher=True))
    b, c, *_ = await _make_pair(db_session)
    plan = await _due_active(db_session, b, c, max_runs=5)
    svc = _tick_svc(db_session)
    fixed_now = datetime.now(timezone.utc)
    res1 = await svc.dispatch_due_recurring_plans_once(now=fixed_now)
    assert res1["processed_plan_ids"] == [plan.id]
    # 같은 now로 즉시 재호출 — next_run_at이 미래로 밀려 더 이상 due 아님 → 중복 tick 없음.
    res2 = await svc.dispatch_due_recurring_plans_once(now=fixed_now)
    assert res2["plans_selected"] == 0 and res2["processed_plan_ids"] == []
    await db_session.refresh(plan)
    assert plan.completed_runs == 1  # 단 1회만 증가


# --- G. readiness endpoint stays read-only after core added -----------------
async def test_readiness_reports_service_core_but_not_executable(
    db_session: AsyncSession
) -> None:
    b, c, *_ = await _make_pair(db_session)
    await _due_active(db_session, b, c)
    sl_before = await _count(db_session, SignalLog)
    r = await _get_readiness(db_session)
    assert r.status_code == 200
    body = r.json()
    assert body["service_core_implemented"] is True
    assert body["scheduler_dispatcher_implemented"] is False
    assert body["api_execution_endpoint_registered"] is False
    assert body["can_execute"] is False
    # readiness가 디스패처를 실행하지 않음(무변경).
    assert await _count(db_session, SignalLog) == sl_before
