"""C-3.5 운영 종합 관제 합본 테스트."""

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
from app.services.operations_overview_service import OperationsOverviewService


async def test_overview_composes_sections(db_session: AsyncSession) -> None:
    strat = Strategy(name="OpsStrat", description="t")
    db_session.add(strat)
    await db_session.flush()
    sv = StrategyVersion(
        strategy_id=strat.id, version_no=1,
        parameters={"strategy_type": "moving_average_cross"},
    )
    db_session.add(sv)
    await db_session.flush()
    # 승인 제안(버전 생성) + pending 제안
    db_session.add_all([
        StrategyProposal(strategy_id=strat.id, title="a", suggested_parameters={"x": 1},
                         status=ProposalStatus.APPROVED, created_version_id=sv.id),
        StrategyProposal(strategy_id=strat.id, title="b", suggested_parameters={"x": 2},
                         status=ProposalStatus.PENDING),
    ])
    # 비용 기록
    run = AiAnalysisRun(
        analysis_type=AnalysisRunType.STRATEGY_PERFORMANCE,
        target_type=AnalysisTargetType.STRATEGY_VERSION, target_id=1,
        mode=AnalysisRunMode.SINGLE, prompt_type="improvement",
        provider="openai", model="gpt-5.4", status=AnalysisRunStatus.SUCCEEDED,
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(AiModelResponse(
        run_id=run.id, provider="openai", model="gpt-5.4", role="primary_analysis",
        prompt_tokens=1_000_000, completion_tokens=0, total_tokens=1_000_000,
    ))
    await db_session.flush()

    out = await OperationsOverviewService(db_session).overview(days=30)

    # 안전: 기본 불변식 정상
    assert out["safety"]["invariants_ok"] is True
    # 연구: pending 1건
    assert out["research"]["pending_total"] == 1
    # 승격 기준 미등록 → ready 0
    assert out["research"]["promotion_ready"] == 0
    # 퍼널: 생성 2, 승인 1, 버전 1
    assert out["funnel"]["generated"] == 2
    assert out["funnel"]["approved"] == 1
    assert out["funnel"]["versions_created"] == 1
    # 비용: gpt-5.4 1M input @2.5 = 2.5
    assert out["cost"]["est_cost_usd"] == 2.5
    assert out["cost"]["responses"] == 1
    assert "retrospective" in out
    # 거래/리스크 헤드라인 블록 존재(데이터 없으면 0/None)
    assert out["trading"]["closed_trades"] == 0
    assert out["trading"]["risk_rejection_rate"] is None
