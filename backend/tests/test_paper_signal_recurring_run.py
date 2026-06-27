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
    def __init__(self, real=False, runner=False):
        self.kis_real_trading_enabled = real
        self.paper_signal_session_runner_enabled = runner


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
