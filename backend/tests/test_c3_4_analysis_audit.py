"""C-3.4 AI 분석 실행 감사 뷰 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.enums import (
    AnalysisRunMode,
    AnalysisRunStatus,
    AnalysisRunType,
    AnalysisTargetType,
    ProposalStatus,
)
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.analysis_audit_service import AnalysisAuditService


async def _make_run(session: AsyncSession, model: str = "gpt-5.4") -> AiAnalysisRun:
    run = AiAnalysisRun(
        analysis_type=AnalysisRunType.STRATEGY_PERFORMANCE,
        target_type=AnalysisTargetType.STRATEGY_VERSION,
        target_id=1, mode=AnalysisRunMode.SINGLE, prompt_type="improvement",
        provider="openai", model=model, status=AnalysisRunStatus.SUCCEEDED,
    )
    session.add(run)
    await session.flush()
    return run


async def test_recent_includes_tokens_cost_and_proposals(db_session: AsyncSession) -> None:
    strat = Strategy(name="AuditStrat", description="t")
    db_session.add(strat)
    await db_session.flush()

    run = await _make_run(db_session)
    db_session.add(AiModelResponse(
        run_id=run.id, provider="openai", model="gpt-5.4", role="primary_analysis",
        prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000,
    ))
    # 이 run이 만든 제안 2건
    db_session.add_all([
        StrategyProposal(strategy_id=strat.id, title="p1", suggested_parameters={"x": 1},
                         status=ProposalStatus.PENDING, ai_analysis_run_id=run.id),
        StrategyProposal(strategy_id=strat.id, title="p2", suggested_parameters={"x": 2},
                         status=ProposalStatus.PENDING, ai_analysis_run_id=run.id),
    ])
    await db_session.flush()

    rows = await AnalysisAuditService(db_session).recent(limit=20)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == run.id
    assert row["total_tokens"] == 2_000_000
    assert row["est_cost_usd"] == 12.5  # 2.5 + 10.0
    assert row["proposals_created"] == 2
    assert row["status"] == "succeeded"


async def test_recent_orders_desc_and_limits(db_session: AsyncSession) -> None:
    first = await _make_run(db_session)
    second = await _make_run(db_session)
    rows = await AnalysisAuditService(db_session).recent(limit=1)
    assert len(rows) == 1
    # 가장 최근(second)이 먼저
    assert rows[0]["id"] == second.id
    assert first.id != second.id


async def test_recent_empty(db_session: AsyncSession) -> None:
    assert await AnalysisAuditService(db_session).recent() == []
