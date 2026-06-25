"""Paper Signal Session 테스트 (signal-only).

세션은 SignalLog만 생성한다 — Trade/Order/StrategyAssignmentLog 없음, 상태 전환 없음,
연결 StrategyVersion은 DRAFT 유지(trade-capable runner가 보지 못함).
"""
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.enums import ExperimentStatus, StrategyVersionStatus, TradeSide
from app.domain.models.experiment import Experiment
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.candidate_proposal_experiment_service import (
    CandidateProposalExperimentService,
)
from app.services.paper_signal_service import (
    ConfirmationRequiredError,
    InvalidVersionStateError,
    NotPreparedError,
    NotReadyError,
    PaperSignalService,
    ProposalNotApprovedError,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


class _FakeSignalService:
    """generate_and_log_signal만 흉내내어 SignalLog 1건을 기록한다(주문 경로 없음)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.calls: list[str] = []

    async def generate_and_log_signal(
        self, strategy, symbol_code, strategy_version_id, **kwargs
    ):
        self.calls.append(symbol_code)
        log = SignalLog(
            symbol_code=symbol_code,
            strategy_version_id=strategy_version_id,
            signal_type=TradeSide.BUY,
            generated_at=datetime.now(timezone.utc),
            market="KR",
            timeframe="1m",
        )
        self._session.add(log)
        await self._session.flush()
        return log


async def _seed_approved(session: AsyncSession, status: str = "approved") -> CandidateStrategyProposal:
    rule = ScannerRule(name="SignalRule")
    session.add(rule)
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    cand = CandidateEvent(
        scanner_rule_version_id=rv.id, symbol_code="005930",
        triggered_at=datetime.now(timezone.utc), score=90, matched_conditions=["turnover_rank"],
    )
    session.add(cand)
    await session.flush()
    prop = CandidateStrategyProposal(
        candidate_event_id=cand.id, symbol_code="005930",
        suggested_strategy_type="moving_average_cross", status=status, source="manual",
    )
    session.add(prop)
    await session.flush()
    return prop


async def _prepared(session: AsyncSession) -> CandidateStrategyProposal:
    prop = await _seed_approved(session)
    await CandidateProposalExperimentService(session).prepare(prop.id)
    await session.refresh(prop)
    return prop


async def _ready(session: AsyncSession) -> CandidateStrategyProposal:
    prop = await _prepared(session)
    await CandidateProposalExperimentService(session).approve_paper_testing_readiness(
        prop.id, confirmed=True, confirmed_by="u"
    )
    await session.refresh(prop)
    return prop


# --- start gate --------------------------------------------------------------
async def test_cannot_start_without_confirmed(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    try:
        await PaperSignalService(db_session).start_session_from_candidate_strategy_proposal(
            prop.id, confirmed=False, confirmed_by="u"
        )
        assert False
    except ConfirmationRequiredError:
        pass


async def test_cannot_start_without_confirmed_by(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    try:
        await PaperSignalService(db_session).start_session_from_candidate_strategy_proposal(
            prop.id, confirmed=True, confirmed_by=None
        )
        assert False
    except ConfirmationRequiredError:
        pass


async def test_cannot_start_pending(db_session: AsyncSession) -> None:
    prop = await _seed_approved(db_session, status="pending")
    try:
        await PaperSignalService(db_session).start_session_from_candidate_strategy_proposal(
            prop.id, confirmed=True, confirmed_by="u"
        )
        assert False
    except ProposalNotApprovedError:
        pass


async def test_cannot_start_if_not_prepared(db_session: AsyncSession) -> None:
    prop = await _seed_approved(db_session)  # approved, not prepared
    try:
        await PaperSignalService(db_session).start_session_from_candidate_strategy_proposal(
            prop.id, confirmed=True, confirmed_by="u"
        )
        assert False
    except NotPreparedError:
        pass


async def test_cannot_start_if_not_ready(db_session: AsyncSession) -> None:
    prop = await _prepared(db_session)  # prepared, readiness NOT approved
    try:
        await PaperSignalService(db_session).start_session_from_candidate_strategy_proposal(
            prop.id, confirmed=True, confirmed_by="u"
        )
        assert False
    except NotReadyError:
        pass


async def test_cannot_start_if_version_not_draft(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    # 버전을 DRAFT가 아닌 상태(ARCHIVED)로 바꿔 거부되는지 확인.
    exp = await db_session.get(Experiment, prop.experiment_id)
    from app.domain.models.experiment import ExperimentVariant
    variants = (
        await db_session.execute(
            select(ExperimentVariant).where(ExperimentVariant.experiment_id == exp.id)
        )
    ).scalars().all()
    ver = await db_session.get(StrategyVersion, variants[0].strategy_version_id)
    ver.status = StrategyVersionStatus.ARCHIVED
    await db_session.flush()
    try:
        await PaperSignalService(db_session).start_session_from_candidate_strategy_proposal(
            prop.id, confirmed=True, confirmed_by="u"
        )
        assert False
    except InvalidVersionStateError:
        pass


# --- start happy path --------------------------------------------------------
async def test_start_creates_active_session_no_status_change(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    svc = PaperSignalService(db_session)
    s = await svc.start_session_from_candidate_strategy_proposal(
        prop.id, confirmed=True, confirmed_by="tester"
    )
    assert s.status == "active"
    assert s.started_by == "tester"
    assert s.symbol_code == "005930"
    assert s.strategy_version_id is not None

    # 상태 불변: 실험 DRAFT, 버전 DRAFT
    exp = await db_session.get(Experiment, prop.experiment_id)
    assert exp.status == ExperimentStatus.DRAFT
    assert exp.started_at is None
    ver = await db_session.get(StrategyVersion, s.strategy_version_id)
    assert ver.status == StrategyVersionStatus.DRAFT


async def test_duplicate_active_session_rejected(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    svc = PaperSignalService(db_session)
    await svc.start_session_from_candidate_strategy_proposal(prop.id, True, "u")
    from app.services.paper_signal_service import DuplicateActiveSessionError
    try:
        await svc.start_session_from_candidate_strategy_proposal(prop.id, True, "u")
        assert False
    except DuplicateActiveSessionError:
        pass


async def test_stop_marks_stopped(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    svc = PaperSignalService(db_session)
    s = await svc.start_session_from_candidate_strategy_proposal(prop.id, True, "u")
    stopped = await svc.stop_session(s.id, confirmed_by="u", note="done")
    assert stopped.status == "stopped"
    assert stopped.stopped_at is not None


# --- run_due_sessions --------------------------------------------------------
async def test_run_due_creates_signal_logs_no_trades(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    svc = PaperSignalService(db_session)
    await svc.start_session_from_candidate_strategy_proposal(prop.id, True, "u")

    before_trades = await _count(db_session, Trade)
    before_logs = await _count(db_session, StrategyAssignmentLog)
    before_signals = await _count(db_session, SignalLog)

    # 가짜 signal_service 주입 — SignalLog만 기록.
    runner = PaperSignalService(db_session, _FakeSignalService(db_session))
    summary = await runner.run_due_sessions()

    assert summary.checked == 1
    assert summary.signals_created == 1
    assert await _count(db_session, SignalLog) == before_signals + 1
    # 주문/체결/배정 흔적 없음
    assert await _count(db_session, Trade) == before_trades
    assert await _count(db_session, StrategyAssignmentLog) == before_logs

    # 세션 카운터 갱신, 상태 불변
    sess = (await db_session.execute(select(PaperSignalSession))).scalars().first()
    assert sess.run_count == 1
    assert sess.signal_count == 1
    assert sess.last_run_at is not None
    ver = await db_session.get(StrategyVersion, sess.strategy_version_id)
    assert ver.status == StrategyVersionStatus.DRAFT
    exp = await db_session.get(Experiment, sess.experiment_id)
    assert exp.status == ExperimentStatus.DRAFT


async def test_run_due_skips_stopped_sessions(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    svc = PaperSignalService(db_session)
    s = await svc.start_session_from_candidate_strategy_proposal(prop.id, True, "u")
    await svc.stop_session(s.id, confirmed_by="u")

    runner = PaperSignalService(db_session, _FakeSignalService(db_session))
    summary = await runner.run_due_sessions()
    assert summary.checked == 0  # active 세션 없음 → 신호 안 만듦


async def test_scheduler_job_default_disabled() -> None:
    settings = get_settings()
    assert settings.paper_signal_session_runner_enabled is False


# --- API ---------------------------------------------------------------------
async def test_api_start_list_stop(db_session: AsyncSession) -> None:
    prop = await _ready(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # missing confirmed -> 422
            r = await client.post(
                f"/api/v1/candidate-strategy-proposals/{prop.id}/paper-signal-sessions",
                json={"confirmed": False, "confirmed_by": "u"},
            )
            assert r.status_code == 422
            # ok -> 201 active
            r = await client.post(
                f"/api/v1/candidate-strategy-proposals/{prop.id}/paper-signal-sessions",
                json={"confirmed": True, "confirmed_by": "tester"},
            )
            assert r.status_code == 201
            sid = r.json()["id"]
            assert r.json()["status"] == "active"
            # list
            r = await client.get("/api/v1/paper-signal-sessions?status=active")
            assert r.status_code == 200 and len(r.json()) >= 1
            # stop
            r = await client.post(
                f"/api/v1/paper-signal-sessions/{sid}/stop", json={"confirmed_by": "tester"}
            )
            assert r.status_code == 200 and r.json()["status"] == "stopped"
    finally:
        app.dependency_overrides.clear()
