"""C-2.28 Intelligence AI Evolution Loop 테스트.

검증 항목:
1.  COMPLETED 실험만 analyze 가능
2.  RUNNING 실험 analyze → ExperimentNotCompletedError
3.  존재하지 않는 실험 → ExperimentNotFoundError
4.  experiment_id 없는 실험 → ProposalNotFoundForExperimentError
5.  이미 분석된 실험 force=False → analyzed=False 조기 반환
6.  force=True 이면 재분석 실행
7.  trades_count < min_trades → analyzed_no_proposal, StrategyProposal 생성 없음
8.  trades_count >= min_trades + LLM valid JSON → StrategyProposal(PENDING) 생성
9.  생성된 StrategyProposal.auto_trade_enabled=False
10. 생성된 StrategyProposal.status=PENDING (자동 승인 없음)
11. 생성된 StrategyProposal.source="intelligence_evolution"
12. _mark_proposal 후 proposal.evolution_analyzed_at 설정
13. _mark_proposal 후 proposal.evolution_status 설정
14. _mark_proposal 후 proposal.evolution_reason 설정
15. _mark_proposal 후 proposal.evolution_strategy_proposal_id 설정
16. LLM 출력 파싱 실패 → proposal 미생성, analyzed_no_proposal
17. variant 없는 실험 → status=failed
18. version 없는 실험 → status=failed
19. evolution_loop() — pending 목록 처리
20. evolution_loop() — 에러 발생 시 errors에 기록하고 계속 진행
21. evolution_loop() — EvolutionLoopSummary 반환
22. build_evolution_context() 실험 정보 포함
23. build_evolution_context() candidate None 허용
24. API POST /experiments/{id}/analyze 정상 응답
25. API POST /experiments/{id}/analyze 404 experiment not found
26. API POST /experiments/{id}/analyze 422 not completed
27. API POST /experiments/{id}/analyze 404 no linked proposal
28. scheduler 기본 비활성 + IntelligenceStrategyProposalRead에 evolution 필드 포함
"""
from __future__ import annotations

import inspect
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import (
    ExperimentStatus,
    IntelligenceCandidateStatus,
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    IntelligenceStrategyProposalStatus,
    MarketCode,
    StrategyVersionStatus,
)
from app.domain.models.experiment import Experiment, ExperimentResult, ExperimentVariant
from app.domain.repositories.experiment import ExperimentRepository, ExperimentVariantRepository
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.domain.repositories.strategy import StrategyVersionRepository
from app.main import app
from app.services.intelligence_evolution_service import (
    EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL,
    EVOLUTION_STATUS_FAILED,
    EVOLUTION_STATUS_PROPOSAL_CREATED,
    ExperimentNotCompletedError,
    IntelligenceEvolutionService,
    ProposalNotFoundForExperimentError,
)
from app.services.experiment_service import ExperimentNotFoundError


# ── 세션 오버라이드 ─────────────────────────────────────────────────────────────

def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ── 유효한 LLM JSON 픽스처 ─────────────────────────────────────────────────────

VALID_LLM_JSON = json.dumps({
    "verdict": "improve",
    "key_observations": ["거래량 급증 후 반전"],
    "mistakes": ["진입 타이밍 늦음"],
    "hypotheses": [
        {
            "hypothesis": "short_window를 줄이면 진입 빠름",
            "param_change": {"strategy_type": "momentum_surge", "short_window": 5},
            "confidence": 0.8,
            "rationale": "빠른 신호 포착",
        }
    ],
    "risk_notes": "급등 종목 주의",
    "confidence": 0.8,
})


# ── 시드 헬퍼 ─────────────────────────────────────────────────────────────────

async def _seed_completed_experiment(
    session: AsyncSession,
    symbol_code: str = "005930",
    dedup_suffix: str = "",
    trades_count: int = 0,
) -> tuple[int, int]:
    """Experiment(COMPLETED) + IntelligenceStrategyProposal(experiment_id 연결) 반환 (experiment_id, proposal_id)."""
    src_repo = IntelligenceSourceRepository(session)
    src = await src_repo.create(
        source_key=f"evo_src_{symbol_code}{dedup_suffix}",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
    )
    await session.flush()

    ev_repo = IntelligenceEventRepository(session)
    ev = await ev_repo.create(
        source_id=src.id,
        event_type="news",
        market=MarketCode.KR,
        symbol_code=symbol_code,
        title=f"{symbol_code} evo 테스트",
        summary="테스트",
        dedup_hash=f"evo_ev_{symbol_code}{dedup_suffix}",
        status=IntelligenceEventStatus.RAW,
    )
    await session.flush()

    cand_repo = IntelligenceCandidateRepository(session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id,
        symbol_code=symbol_code,
        market=MarketCode.KR,
        score=70,
        why_text="급등 모멘텀",
        source_type="news",
        matched_themes=["momentum"],
        score_components={"base": 70},
        dedup_hash=f"evo_cand_{symbol_code}{dedup_suffix}",
        status=IntelligenceCandidateStatus.PROMOTED,
    )
    await session.flush()

    proposal_repo = IntelligenceStrategyProposalRepository(session)
    proposal = await proposal_repo.create(
        intelligence_candidate_id=cand.id,
        symbol_code=symbol_code,
        market=MarketCode.KR,
        suggested_strategy_type="momentum_surge",
        suggested_parameters={"strategy_type": "momentum_surge", "timeframe": "5m", "quantity": 1},
        rationale="테스트 rationale",
        confidence_score=0.7,
        score_components={},
        source="heuristic",
        status=IntelligenceStrategyProposalStatus.APPROVED,
        dedup_hash=f"evo_prop_{symbol_code}{dedup_suffix}",
    )
    await session.flush()

    # Strategy + StrategyVersion
    from app.domain.models.strategy import Strategy, StrategyVersion
    from app.domain.models.enums import VariantRole

    strategy = Strategy(name=f"EvoTest {symbol_code}{dedup_suffix}")
    session.add(strategy)
    await session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        parameters={"strategy_type": "momentum_surge", "short_window": 10, "long_window": 20, "quantity": 1},
        status=StrategyVersionStatus.DRAFT,
    )
    session.add(version)
    await session.flush()

    # Experiment + ExperimentVariant
    from datetime import datetime, timezone, timedelta

    experiment = Experiment(
        name=f"Evo Exp {symbol_code}{dedup_suffix}",
        market=MarketCode.KR,
        status=ExperimentStatus.COMPLETED,
        started_at=datetime.now(timezone.utc) - timedelta(days=3),
        ended_at=datetime.now(timezone.utc),
    )
    session.add(experiment)
    await session.flush()

    variant = ExperimentVariant(
        experiment_id=experiment.id,
        strategy_version_id=version.id,
        role=VariantRole.CHALLENGER,
    )
    session.add(variant)
    await session.flush()

    # ExperimentResult
    if trades_count > 0:
        result = ExperimentResult(
            experiment_variant_id=variant.id,
            trades_count=trades_count,
            win_rate=0.55,
            expectancy=0.02,
            profit_factor=1.2,
            max_drawdown=0.05,
        )
        session.add(result)
        await session.flush()

    # 연결
    proposal.experiment_id = experiment.id
    await session.flush()

    return experiment.id, proposal.id


# ── 1. COMPLETED 실험만 analyze 가능 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_completed_experiment_succeeds(db_session: AsyncSession) -> None:
    """1. COMPLETED 실험 analyze 시 EvolutionResult 반환."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t1")
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    result = await svc.analyze_experiment(exp_id, min_trades=5)
    assert result.experiment_id == exp_id
    assert result.analyzed is True


# ── 2. RUNNING 실험 → ExperimentNotCompletedError ──────────────────────────────

@pytest.mark.asyncio
async def test_analyze_running_experiment_raises(db_session: AsyncSession) -> None:
    """2. RUNNING 실험 analyze 시 ExperimentNotCompletedError."""
    exp_repo = ExperimentRepository(db_session)
    from datetime import datetime, timezone
    experiment = Experiment(
        name="running exp t2",
        market=MarketCode.KR,
        status=ExperimentStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(experiment)
    await db_session.flush()

    svc = IntelligenceEvolutionService(db_session)
    with pytest.raises(ExperimentNotCompletedError):
        await svc.analyze_experiment(experiment.id)


# ── 3. 존재하지 않는 실험 → ExperimentNotFoundError ──────────────────────────

@pytest.mark.asyncio
async def test_analyze_nonexistent_experiment_raises(db_session: AsyncSession) -> None:
    """3. 존재하지 않는 실험 ID → ExperimentNotFoundError."""
    svc = IntelligenceEvolutionService(db_session)
    with pytest.raises(ExperimentNotFoundError):
        await svc.analyze_experiment(999_999_999)


# ── 4. experiment_id 없는 실험 → ProposalNotFoundForExperimentError ───────────

@pytest.mark.asyncio
async def test_analyze_experiment_without_proposal_raises(db_session: AsyncSession) -> None:
    """4. IntelligenceStrategyProposal이 연결되지 않은 실험 → ProposalNotFoundForExperimentError."""
    from datetime import datetime, timezone

    experiment = Experiment(
        name="orphan exp t4",
        market=MarketCode.KR,
        status=ExperimentStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    db_session.add(experiment)
    await db_session.flush()

    svc = IntelligenceEvolutionService(db_session)
    with pytest.raises(ProposalNotFoundForExperimentError):
        await svc.analyze_experiment(experiment.id)


# ── 5. 이미 분석된 실험 force=False → analyzed=False 반환 ──────────────────────

@pytest.mark.asyncio
async def test_already_analyzed_force_false_returns_early(db_session: AsyncSession) -> None:
    """5. 이미 분석된 실험 force=False → analyzed=False 조기 반환."""
    from datetime import datetime, timezone

    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t5")
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    proposal.evolution_analyzed_at = datetime.now(timezone.utc)
    proposal.evolution_status = EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL
    await db_session.flush()

    svc = IntelligenceEvolutionService(db_session)
    result = await svc.analyze_experiment(exp_id, force=False)
    assert result.analyzed is False
    assert "already analyzed" in result.reason


# ── 6. force=True 이면 재분석 실행 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_true_reanalyzes(db_session: AsyncSession) -> None:
    """6. force=True 이면 이미 분석된 실험도 재분석한다."""
    from datetime import datetime, timezone

    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t6")
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    proposal.evolution_analyzed_at = datetime.now(timezone.utc)
    proposal.evolution_status = EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL
    await db_session.flush()

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    result = await svc.analyze_experiment(exp_id, force=True, min_trades=5)
    assert result.analyzed is True


# ── 7. trades_count < min_trades → analyzed_no_proposal ──────────────────────

@pytest.mark.asyncio
async def test_insufficient_trades_no_proposal(db_session: AsyncSession) -> None:
    """7. trades_count < min_trades → analyzed_no_proposal, StrategyProposal 없음."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t7", trades_count=2)
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 2})
    result = await svc.analyze_experiment(exp_id, min_trades=5)
    assert result.analyzed is True
    assert result.status == EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL
    assert result.strategy_proposal_id is None
    assert result.trades_count == 2


# ── 8. trades_count >= min_trades + valid LLM JSON → StrategyProposal 생성 ───

@pytest.mark.asyncio
async def test_sufficient_trades_creates_proposal(db_session: AsyncSession) -> None:
    """8. trades_count >= min_trades + valid LLM JSON → StrategyProposal 생성."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t8", trades_count=10)

    fake_response = MagicMock()
    fake_response.id = 1
    fake_response.role = "synthesis"
    fake_response.content = VALID_LLM_JSON

    fake_run = MagicMock()
    fake_run.id = None
    fake_run.responses = [fake_response]

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=fake_run)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 10})
    result = await svc.analyze_experiment(exp_id, min_trades=5)
    assert result.analyzed is True
    assert result.status == EVOLUTION_STATUS_PROPOSAL_CREATED
    assert result.strategy_proposal_id is not None


# ── 9. 생성된 StrategyProposal.auto_trade_enabled=False ─────────────────────

@pytest.mark.asyncio
async def test_created_proposal_auto_trade_disabled(db_session: AsyncSession) -> None:
    """9. 생성된 StrategyProposal의 suggested_parameters.auto_trade_enabled=False."""
    from app.domain.models.strategy_proposal import StrategyProposal

    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t9", trades_count=10)

    fake_response = MagicMock()
    fake_response.id = 2
    fake_response.role = "synthesis"
    fake_response.content = VALID_LLM_JSON

    fake_run = MagicMock()
    fake_run.id = None
    fake_run.responses = [fake_response]

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=fake_run)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 10})
    result = await svc.analyze_experiment(exp_id, min_trades=5)

    assert result.strategy_proposal_id is not None
    sp = await db_session.get(StrategyProposal, result.strategy_proposal_id)
    assert sp is not None
    params = sp.suggested_parameters or {}
    assert params.get("auto_trade_enabled") is False


# ── 10. 생성된 StrategyProposal.status=PENDING ──────────────────────────────

@pytest.mark.asyncio
async def test_created_proposal_is_pending(db_session: AsyncSession) -> None:
    """10. 생성된 StrategyProposal은 항상 PENDING (자동 승인 없음)."""
    from app.domain.models.enums import ProposalStatus
    from app.domain.models.strategy_proposal import StrategyProposal

    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t10", trades_count=10)

    fake_response = MagicMock()
    fake_response.id = 3
    fake_response.role = "synthesis"
    fake_response.content = VALID_LLM_JSON

    fake_run = MagicMock()
    fake_run.id = None
    fake_run.responses = [fake_response]

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=fake_run)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 10})
    result = await svc.analyze_experiment(exp_id, min_trades=5)

    assert result.strategy_proposal_id is not None
    sp = await db_session.get(StrategyProposal, result.strategy_proposal_id)
    assert sp is not None
    assert sp.status == ProposalStatus.PENDING


# ── 11. 생성된 StrategyProposal.source="intelligence_evolution" ──────────────

@pytest.mark.asyncio
async def test_created_proposal_source_intelligence_evolution(db_session: AsyncSession) -> None:
    """11. 생성된 StrategyProposal.source="intelligence_evolution"."""
    from app.domain.models.strategy_proposal import StrategyProposal

    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t11", trades_count=10)

    fake_response = MagicMock()
    fake_response.id = 4
    fake_response.role = "synthesis"
    fake_response.content = VALID_LLM_JSON

    fake_run = MagicMock()
    fake_run.id = None
    fake_run.responses = [fake_response]

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=fake_run)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 10})
    result = await svc.analyze_experiment(exp_id, min_trades=5)

    assert result.strategy_proposal_id is not None
    sp = await db_session.get(StrategyProposal, result.strategy_proposal_id)
    assert sp is not None
    assert sp.source == "intelligence_evolution"


# ── 12. _mark_proposal 후 evolution_analyzed_at 설정 ─────────────────────────

@pytest.mark.asyncio
async def test_evolution_analyzed_at_set_after_analysis(db_session: AsyncSession) -> None:
    """12. analyze_experiment 후 proposal.evolution_analyzed_at가 설정된다."""
    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t12")
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    await svc.analyze_experiment(exp_id, min_trades=5)

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    assert proposal.evolution_analyzed_at is not None


# ── 13. evolution_status 설정 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evolution_status_set_after_analysis(db_session: AsyncSession) -> None:
    """13. analyze_experiment 후 proposal.evolution_status가 설정된다."""
    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t13")
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    await svc.analyze_experiment(exp_id, min_trades=5)

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    assert proposal.evolution_status is not None
    assert proposal.evolution_status == EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL


# ── 14. evolution_reason 설정 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evolution_reason_set_after_analysis(db_session: AsyncSession) -> None:
    """14. analyze_experiment 후 proposal.evolution_reason이 설정된다."""
    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t14")
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    await svc.analyze_experiment(exp_id, min_trades=5)

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    assert proposal.evolution_reason is not None


# ── 15. evolution_strategy_proposal_id 설정 ───────────────────────────────────

@pytest.mark.asyncio
async def test_evolution_strategy_proposal_id_set(db_session: AsyncSession) -> None:
    """15. 제안 생성 성공 시 proposal.evolution_strategy_proposal_id가 설정된다."""
    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t15", trades_count=10)

    fake_response = MagicMock()
    fake_response.id = 5
    fake_response.role = "synthesis"
    fake_response.content = VALID_LLM_JSON

    fake_run = MagicMock()
    fake_run.id = None
    fake_run.responses = [fake_response]

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=fake_run)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 10})
    result = await svc.analyze_experiment(exp_id, min_trades=5)

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    assert proposal.evolution_strategy_proposal_id == result.strategy_proposal_id


# ── 16. LLM 출력 파싱 실패 → 제안 미생성 ────────────────────────────────────

@pytest.mark.asyncio
async def test_unparseable_llm_output_no_proposal(db_session: AsyncSession) -> None:
    """16. LLM 출력이 파싱 불가능하면 StrategyProposal 미생성."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t16", trades_count=10)

    fake_response = MagicMock()
    fake_response.id = 6
    fake_response.role = "synthesis"
    fake_response.content = "이것은 구조화되지 않은 자유 텍스트입니다. JSON 없음."

    fake_run = MagicMock()
    fake_run.id = None
    fake_run.responses = [fake_response]

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=fake_run)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 10})
    result = await svc.analyze_experiment(exp_id, min_trades=5)
    assert result.strategy_proposal_id is None
    assert result.status == EVOLUTION_STATUS_ANALYZED_NO_PROPOSAL


# ── 17. variant 없는 실험 → failed ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_variants_marks_failed(db_session: AsyncSession) -> None:
    """17. ExperimentVariant가 없는 실험 → evolution_status=failed."""
    from datetime import datetime, timezone

    # proposal만 있고 variant는 없는 실험
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(
        source_key="evo_src_t17",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
    )
    await db_session.flush()
    ev_repo = IntelligenceEventRepository(db_session)
    ev = await ev_repo.create(
        source_id=src.id, event_type="news", market=MarketCode.KR,
        symbol_code="000660", title="t17", summary="t17",
        dedup_hash="evo_ev_t17", status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()
    cand_repo = IntelligenceCandidateRepository(db_session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id, symbol_code="000660", market=MarketCode.KR,
        score=60, why_text="t17", source_type="news", matched_themes=[],
        score_components={}, dedup_hash="evo_cand_t17",
        status=IntelligenceCandidateStatus.PROMOTED,
    )
    await db_session.flush()
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.create(
        intelligence_candidate_id=cand.id, symbol_code="000660",
        market=MarketCode.KR, suggested_strategy_type="momentum_surge",
        suggested_parameters={"strategy_type": "momentum_surge", "quantity": 1},
        rationale="t17", confidence_score=0.6, score_components={},
        source="heuristic", status=IntelligenceStrategyProposalStatus.APPROVED,
        dedup_hash="evo_prop_t17",
    )
    await db_session.flush()

    experiment = Experiment(
        name="no variant exp t17",
        market=MarketCode.KR,
        status=ExperimentStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    db_session.add(experiment)
    await db_session.flush()
    proposal.experiment_id = experiment.id
    await db_session.flush()

    svc = IntelligenceEvolutionService(db_session)
    result = await svc.analyze_experiment(experiment.id)
    assert result.status == EVOLUTION_STATUS_FAILED
    assert result.analyzed is True


# ── 18. version 없는 실험 → failed ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_version_marks_failed(db_session: AsyncSession) -> None:
    """18. StrategyVersion이 없는 variant → evolution_status=failed (version_repo 모킹)."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t18")

    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    # StrategyVersionRepository.get()가 None을 반환하도록 모킹
    svc._version_repo.get = AsyncMock(return_value=None)
    result = await svc.analyze_experiment(exp_id)
    assert result.status == EVOLUTION_STATUS_FAILED
    assert result.analyzed is True


# ── 19. evolution_loop() — pending 목록 처리 ─────────────────────────────────

@pytest.mark.asyncio
async def test_evolution_loop_processes_pending(db_session: AsyncSession) -> None:
    """19. evolution_loop()는 COMPLETED + 미분석 제안을 처리한다."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t19")
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    summary = await svc.evolution_loop(min_trades=5)
    assert summary.checked >= 1
    assert summary.analyzed >= 1


# ── 20. evolution_loop() — 에러 발생 시 계속 진행 ────────────────────────────

@pytest.mark.asyncio
async def test_evolution_loop_continues_on_error(db_session: AsyncSession) -> None:
    """20. evolution_loop() 중 에러 발생 시 errors에 기록하고 나머지 처리 계속."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t20")

    svc = IntelligenceEvolutionService(db_session)

    async def _failing_analyze(experiment_id, force=False, min_trades=5):
        raise RuntimeError("test error")

    svc.analyze_experiment = _failing_analyze
    summary = await svc.evolution_loop(min_trades=5)
    assert len(summary.errors) >= 1
    assert "test error" in summary.errors[0]


# ── 21. evolution_loop() — EvolutionLoopSummary 반환 ─────────────────────────

@pytest.mark.asyncio
async def test_evolution_loop_returns_summary(db_session: AsyncSession) -> None:
    """21. evolution_loop()는 EvolutionLoopSummary를 반환한다."""
    from app.services.intelligence_evolution_service import EvolutionLoopSummary

    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t21")
    svc = IntelligenceEvolutionService(db_session)
    svc._run_analysis = AsyncMock(return_value=None)
    svc._get_result_metrics = AsyncMock(return_value={"trades_count": 0})
    summary = await svc.evolution_loop(min_trades=5)
    assert isinstance(summary, EvolutionLoopSummary)
    d = summary.to_dict()
    assert "checked" in d and "analyzed" in d and "proposals_created" in d


# ── 22. build_evolution_context() 실험 정보 포함 ─────────────────────────────

@pytest.mark.asyncio
async def test_build_evolution_context_contains_experiment_info(db_session: AsyncSession) -> None:
    """22. build_evolution_context()는 실험 ID와 종목을 포함한다."""
    from datetime import datetime, timezone

    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t22", trades_count=5)

    exp_repo = ExperimentRepository(db_session)
    experiment = await exp_repo.get(exp_id)
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    cand_repo = IntelligenceCandidateRepository(db_session)
    candidate = await cand_repo.get(proposal.intelligence_candidate_id)

    svc = IntelligenceEvolutionService(db_session)
    ctx = svc.build_evolution_context(
        experiment=experiment,
        proposal=proposal,
        candidate=candidate,
        result_metrics={"trades_count": 5, "win_rate": 0.55},
        retro_summary={"total": 0, "source": "all"},
    )
    assert str(exp_id) in ctx
    assert "005930" in ctx
    assert "momentum_surge" in ctx


# ── 23. build_evolution_context() candidate None 허용 ────────────────────────

@pytest.mark.asyncio
async def test_build_evolution_context_candidate_none(db_session: AsyncSession) -> None:
    """23. build_evolution_context()에 candidate=None을 전달해도 오류 없음."""
    exp_id, proposal_id = await _seed_completed_experiment(db_session, dedup_suffix="_t23")
    exp_repo = ExperimentRepository(db_session)
    experiment = await exp_repo.get(exp_id)
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)

    svc = IntelligenceEvolutionService(db_session)
    ctx = svc.build_evolution_context(
        experiment=experiment,
        proposal=proposal,
        candidate=None,
        result_metrics={"trades_count": 0},
        retro_summary={"total": 0, "source": "all"},
    )
    assert isinstance(ctx, str)
    assert len(ctx) > 0


# ── 24. API POST /experiments/{id}/analyze 정상 응답 ─────────────────────────

@pytest.mark.asyncio
async def test_api_analyze_returns_201(db_session: AsyncSession) -> None:
    """24. POST /intelligence/experiments/{id}/analyze 정상 요청 시 201 반환."""
    exp_id, _ = await _seed_completed_experiment(db_session, dedup_suffix="_t24")
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # mock _run_analysis and _get_result_metrics via service dependency
            # Use a separate transaction scope by directly calling endpoint
            with (
                __import__("unittest.mock", fromlist=["patch"]).patch(
                    "app.services.intelligence_evolution_service.IntelligenceEvolutionService._run_analysis",
                    new=AsyncMock(return_value=None),
                ),
                __import__("unittest.mock", fromlist=["patch"]).patch(
                    "app.services.intelligence_evolution_service.IntelligenceEvolutionService._get_result_metrics",
                    new=AsyncMock(return_value={"trades_count": 0}),
                ),
            ):
                resp = await client.post(
                    f"/api/v1/intelligence/experiments/{exp_id}/analyze",
                    json={"force": False, "min_trades": 5},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    data = resp.json()
    assert data["experiment_id"] == exp_id
    assert "analyzed" in data


# ── 25. API 404 experiment not found ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_analyze_404_experiment_not_found(db_session: AsyncSession) -> None:
    """25. POST /intelligence/experiments/{id}/analyze — 없는 실험 → 404."""
    await db_session.commit()
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/intelligence/experiments/999999999/analyze",
                json={},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ── 26. API 422 not completed ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_analyze_422_not_completed(db_session: AsyncSession) -> None:
    """26. POST /intelligence/experiments/{id}/analyze — RUNNING 실험 → 422."""
    from datetime import datetime, timezone

    experiment = Experiment(
        name="running exp t26",
        market=MarketCode.KR,
        status=ExperimentStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(experiment)
    await db_session.flush()
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/intelligence/experiments/{experiment.id}/analyze",
                json={},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 422


# ── 27. API 404 no linked proposal ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_analyze_404_no_proposal(db_session: AsyncSession) -> None:
    """27. POST /intelligence/experiments/{id}/analyze — proposal 미연결 → 404."""
    from datetime import datetime, timezone

    experiment = Experiment(
        name="no proposal exp t27",
        market=MarketCode.KR,
        status=ExperimentStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    db_session.add(experiment)
    await db_session.flush()
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/intelligence/experiments/{experiment.id}/analyze",
                json={},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


# ── 28. scheduler 기본 비활성 + evolution 필드 노출 ──────────────────────────

def test_evolution_scheduler_disabled_by_default() -> None:
    """28a. intelligence_evolution_scheduler_enabled 기본값은 False."""
    from app.core.config import Settings

    settings = Settings()
    assert settings.intelligence_evolution_scheduler_enabled is False


def test_intelligence_strategy_proposal_read_exposes_evolution_fields() -> None:
    """28b. IntelligenceStrategyProposalRead 스키마에 evolution 4개 필드가 포함된다."""
    from app.api.v1.intelligence import IntelligenceStrategyProposalRead

    fields = IntelligenceStrategyProposalRead.model_fields
    assert "evolution_analyzed_at" in fields
    assert "evolution_strategy_proposal_id" in fields
    assert "evolution_status" in fields
    assert "evolution_reason" in fields
