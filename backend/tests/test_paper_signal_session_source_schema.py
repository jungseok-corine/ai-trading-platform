"""M2.5 Phase 1: paper_signal_sessions source-field schema compatibility (Option A).

스키마 기반만 검증한다 — challenger 세션 워크플로/엔드포인트는 이 단계에 없다.
기존 candidate-proposal 세션 동작 보존 + 'prepared' 비실행 상태 표현 + 런너 비대상.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.models.experiment import Experiment
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.domain.models.trade import Trade
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _candidate_proposal(db: AsyncSession, symbol: str = "005930") -> CandidateStrategyProposal:
    rule = ScannerRule(name="SrcRule")
    db.add(rule)
    await db.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    db.add(rv)
    await db.flush()
    cand = CandidateEvent(scanner_rule_version_id=rv.id, symbol_code=symbol,
                          triggered_at=datetime.now(timezone.utc), score=80, matched_conditions=["x"])
    db.add(cand)
    await db.flush()
    prop = CandidateStrategyProposal(candidate_event_id=cand.id, symbol_code=symbol,
                                     suggested_strategy_type="moving_average_cross",
                                     status="approved", source="manual")
    db.add(prop)
    await db.flush()
    return prop


# --- backward compatibility: candidate sessions unchanged --------------------
async def test_candidate_session_create_defaults_source_type(db_session: AsyncSession) -> None:
    prop = await _candidate_proposal(db_session)
    repo = PaperSignalSessionRepository(db_session)
    # 기존 create 경로처럼 source_type 미지정 — 모델 default가 'candidate_proposal'.
    sess = await repo.create(
        candidate_strategy_proposal_id=prop.id, symbol_code="005930",
        status="active", started_by="tester",
    )
    await db_session.flush()
    assert sess.candidate_strategy_proposal_id == prop.id  # 기존 행에 그대로 존재
    assert sess.source_type == "candidate_proposal"  # backfill/default
    assert sess.source_strategy_proposal_id is None
    assert sess.baseline_session_id is None


async def test_find_active_for_proposal_still_works(db_session: AsyncSession) -> None:
    prop = await _candidate_proposal(db_session)
    repo = PaperSignalSessionRepository(db_session)
    sess = await repo.create(candidate_strategy_proposal_id=prop.id, symbol_code="005930",
                             status="active", started_by="t")
    await db_session.flush()
    found = await repo.find_active_for_proposal(prop.id)
    assert found is not None and found.id == sess.id


async def test_duplicate_active_guard_unchanged(db_session: AsyncSession) -> None:
    prop = await _candidate_proposal(db_session)
    repo = PaperSignalSessionRepository(db_session)
    await repo.create(candidate_strategy_proposal_id=prop.id, symbol_code="005930",
                      status="active", started_by="t")
    await db_session.flush()
    # 같은 제안에 이미 active 세션 → 가드가 잡을 수 있어야 한다.
    assert await repo.find_active_for_proposal(prop.id) is not None


# --- prepared status: non-running, runner-invisible -------------------------
async def test_prepared_session_not_in_list_active(db_session: AsyncSession) -> None:
    prop = await _candidate_proposal(db_session)
    repo = PaperSignalSessionRepository(db_session)
    prepared = await repo.create(
        candidate_strategy_proposal_id=None, symbol_code="005930",
        status="prepared", started_by="tester", source_type="signal_challenger",
    )
    active = await repo.create(
        candidate_strategy_proposal_id=prop.id, symbol_code="005930",
        status="active", started_by="tester",
    )
    await db_session.flush()
    listed = await repo.list_active()
    ids = {s.id for s in listed}
    assert active.id in ids          # active는 잡힌다
    assert prepared.id not in ids    # prepared는 런너 비대상


async def test_challenger_session_row_can_be_represented(db_session: AsyncSession) -> None:
    # signal_challenger 세션: candidate FK NULL + source 추적 컬럼.
    prop = await _candidate_proposal(db_session)
    repo = PaperSignalSessionRepository(db_session)
    baseline = await repo.create(candidate_strategy_proposal_id=prop.id, symbol_code="005930",
                                 status="active", started_by="t")
    await db_session.flush()
    # 추적용 StrategyProposal 행이 필요(FK). 최소 생성.
    strat = Strategy(name="SrcStrat", description="t")
    db_session.add(strat)
    await db_session.flush()
    from app.domain.models.enums import ProposalStatus
    from app.domain.models.strategy_proposal import StrategyProposal
    sp = StrategyProposal(strategy_id=strat.id, title="t",
                          suggested_parameters={"strategy_type": "moving_average_cross"},
                          source="paper_signal_analysis", status=ProposalStatus.PENDING)
    db_session.add(sp)
    await db_session.flush()

    challenger = await repo.create(
        candidate_strategy_proposal_id=None, symbol_code="005930",
        status="prepared", started_by="tester", source_type="signal_challenger",
        source_strategy_proposal_id=sp.id, baseline_session_id=baseline.id,
    )
    await db_session.flush()
    assert challenger.candidate_strategy_proposal_id is None
    assert challenger.source_type == "signal_challenger"
    assert challenger.source_strategy_proposal_id == sp.id
    assert challenger.baseline_session_id == baseline.id
    assert challenger.status == "prepared"


# --- safety: schema usage creates no domain/runtime rows --------------------
async def test_schema_usage_creates_no_side_effects(db_session: AsyncSession) -> None:
    before = {
        "ver": await _count(db_session, StrategyVersion),
        "exp": await _count(db_session, Experiment),
        "sig": await _count(db_session, SignalLog),
        "trade": await _count(db_session, Trade),
        "assign": await _count(db_session, StrategyAssignmentLog),
    }
    prop = await _candidate_proposal(db_session)
    repo = PaperSignalSessionRepository(db_session)
    await repo.create(candidate_strategy_proposal_id=None, symbol_code="005930",
                      status="prepared", started_by="t", source_type="signal_challenger")
    await db_session.flush()
    assert await _count(db_session, StrategyVersion) == before["ver"]
    assert await _count(db_session, Experiment) == before["exp"]
    assert await _count(db_session, SignalLog) == before["sig"]
    assert await _count(db_session, Trade) == before["trade"]
    assert await _count(db_session, StrategyAssignmentLog) == before["assign"]
