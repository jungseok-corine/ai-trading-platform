"""C-2.27 Intelligence Paper Experiment Autopilot 테스트.

검증 항목:
1.  APPROVED proposal만 materialize 가능
2.  PENDING proposal은 materialize 불가
3.  REJECTED proposal은 materialize 불가
4.  materialize 시 Strategy 생성 또는 재사용
5.  materialize 시 StrategyVersion 생성
6.  StrategyVersion.status가 ACTIVE가 아님 (DRAFT)
7.  StrategyVersion.parameters.auto_trade_enabled=false
8.  suggested_parameters에 auto_trade_enabled=true가 있어도 저장 시 false
9.  materialize 시 Experiment 생성
10. ExperimentVariant가 새 StrategyVersion을 참조
11. proposal.experiment_id가 저장됨
12. 같은 proposal 중복 materialize 방지 (기존 experiment 반환)
13. materialize 시 ExperimentResult는 생성하지 않음
14. conclude 시 Experiment.status=COMPLETED
15. conclude 시 ExperimentResult 저장 (compare persist=True)
16. 종료 조건 max_days 충족 판단
17. 종료 조건 min_trades 충족 판단
18. scheduler 기본 비활성
19. 기존 ResearchPipelineService 미변경
20. 기존 scanner 기반 AssignmentService 미변경
21. 실전 주문 API 호출 없음
22. broker.place_order 호출 없음
23. TR_ID 금지 문자열 없음
24. KIS_REAL_TRADING_ENABLED 변경 없음
25. auto_trade_enabled 자동 true 없음
"""
from __future__ import annotations

import inspect

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
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
from app.domain.models.experiment import ExperimentResult
from app.domain.models.strategy import StrategyVersion
from app.domain.repositories.experiment import ExperimentRepository, ExperimentResultRepository
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.main import app
from app.services.intelligence_experiment_service import (
    IntelligenceExperimentService,
    ProposalNotApprovedError,
)


# ── 세션 오버라이드 ─────────────────────────────────────────────────────────────

def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ── 시드 헬퍼 ─────────────────────────────────────────────────────────────────

async def _seed_approved_proposal(
    session: AsyncSession,
    symbol_code: str = "005930",
    strategy_type: str = "momentum_surge",
    dedup_suffix: str = "",
    auto_trade_in_params: bool = False,
) -> int:
    """IntelligenceSource → Event → Candidate → Proposal(APPROVED) 생성, proposal.id 반환."""
    src_repo = IntelligenceSourceRepository(session)
    src = await src_repo.create(
        source_key=f"test_src_{symbol_code}{dedup_suffix}",
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
        title=f"{symbol_code} 테스트",
        summary="테스트 이벤트",
        dedup_hash=f"ev_{symbol_code}_{strategy_type}{dedup_suffix}",
        status=IntelligenceEventStatus.RAW,
    )
    await session.flush()

    cand_repo = IntelligenceCandidateRepository(session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id,
        symbol_code=symbol_code,
        market=MarketCode.KR,
        score=75,
        why_text="급등 모멘텀",
        source_type="news",
        matched_themes=["momentum"],
        score_components={"base": 75},
        dedup_hash=f"cand_{symbol_code}_{strategy_type}{dedup_suffix}",
        status=IntelligenceCandidateStatus.PROMOTED,
    )
    await session.flush()

    params = {"timeframe": "5m", "quantity": 1, "strategy_type": strategy_type}
    if auto_trade_in_params:
        params["auto_trade_enabled"] = True  # 의도적으로 True — materialize에서 강제 override

    proposal_repo = IntelligenceStrategyProposalRepository(session)
    proposal = await proposal_repo.create(
        intelligence_candidate_id=cand.id,
        symbol_code=symbol_code,
        market=MarketCode.KR,
        suggested_strategy_type=strategy_type,
        suggested_parameters=params,
        rationale="테스트 rationale",
        confidence_score=0.7,
        score_components={"matched_rule": strategy_type},
        source="heuristic",
        status=IntelligenceStrategyProposalStatus.APPROVED,
        dedup_hash=f"prop_{symbol_code}_{strategy_type}{dedup_suffix}",
    )
    await session.flush()
    return proposal.id


# ── 1. APPROVED만 materialize 가능 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_approved_proposal_can_be_materialized(db_session: AsyncSession) -> None:
    """1. APPROVED proposal은 materialize 가능."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t1")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)
    assert result.experiment_id > 0
    assert result.strategy_version_id > 0
    assert not result.already_existed


# ── 2. PENDING은 materialize 불가 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pending_proposal_cannot_be_materialized(db_session: AsyncSession) -> None:
    """2. PENDING proposal은 materialize 불가 (ProposalNotApprovedError)."""
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(
        source_key="src_pending_t2",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
    )
    await db_session.flush()
    ev_repo = IntelligenceEventRepository(db_session)
    ev = await ev_repo.create(
        source_id=src.id, event_type="news", market=MarketCode.KR,
        symbol_code="005380", title="t2", summary="t2",
        dedup_hash="ev_t2", status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()
    cand_repo = IntelligenceCandidateRepository(db_session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id, symbol_code="005380", market=MarketCode.KR,
        score=50, why_text="t2", source_type="news", matched_themes=[],
        score_components={}, dedup_hash="cand_t2",
    )
    await db_session.flush()
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.create(
        intelligence_candidate_id=cand.id, symbol_code="005380", market=MarketCode.KR,
        suggested_strategy_type="moving_average_cross",
        suggested_parameters={}, rationale=None, confidence_score=None,
        score_components=None, source="heuristic",
        status=IntelligenceStrategyProposalStatus.PENDING,
        dedup_hash="prop_t2",
    )
    await db_session.flush()

    svc = IntelligenceExperimentService(db_session)
    with pytest.raises(ProposalNotApprovedError):
        await svc.materialize(proposal.id)


# ── 3. REJECTED는 materialize 불가 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejected_proposal_cannot_be_materialized(db_session: AsyncSession) -> None:
    """3. REJECTED proposal은 materialize 불가."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t3rej")
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    proposal.status = IntelligenceStrategyProposalStatus.REJECTED
    await db_session.flush()

    svc = IntelligenceExperimentService(db_session)
    with pytest.raises(ProposalNotApprovedError):
        await svc.materialize(proposal_id)


# ── 4. materialize 시 Strategy 생성 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_materialize_creates_strategy(db_session: AsyncSession) -> None:
    """4. materialize 시 paper 전용 Strategy가 생성됨."""
    from app.domain.models.strategy import Strategy
    before = (await db_session.execute(select(func.count()).select_from(Strategy))).scalar()

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t4")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    after = (await db_session.execute(select(func.count()).select_from(Strategy))).scalar()
    assert after == before + 1
    assert result.strategy_id > 0


# ── 5. materialize 시 StrategyVersion 생성 ───────────────────────────────────

@pytest.mark.asyncio
async def test_materialize_creates_strategy_version(db_session: AsyncSession) -> None:
    """5. materialize 시 StrategyVersion이 생성됨."""
    before = (await db_session.execute(select(func.count()).select_from(StrategyVersion))).scalar()

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t5")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    after = (await db_session.execute(select(func.count()).select_from(StrategyVersion))).scalar()
    assert after == before + 1
    assert result.strategy_version_id > 0


# ── 6. StrategyVersion.status가 ACTIVE가 아님 ────────────────────────────────

@pytest.mark.asyncio
async def test_materialized_version_is_draft_not_active(db_session: AsyncSession) -> None:
    """6. 생성된 StrategyVersion.status = DRAFT (ACTIVE 아님)."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t6")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    version = await db_session.get(StrategyVersion, result.strategy_version_id)
    assert version is not None
    assert version.status == StrategyVersionStatus.DRAFT
    assert version.status != StrategyVersionStatus.ACTIVE


# ── 7. auto_trade_enabled=false (정상 케이스) ────────────────────────────────

@pytest.mark.asyncio
async def test_materialized_version_has_auto_trade_disabled(db_session: AsyncSession) -> None:
    """7. StrategyVersion.parameters.auto_trade_enabled = False."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t7")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    version = await db_session.get(StrategyVersion, result.strategy_version_id)
    assert version is not None
    assert version.parameters.get("auto_trade_enabled") is False


# ── 8. suggested_parameters에 auto_trade=true가 있어도 강제 false ─────────────

@pytest.mark.asyncio
async def test_auto_trade_true_in_params_is_overridden_to_false(db_session: AsyncSession) -> None:
    """8. suggested_parameters.auto_trade_enabled=True가 있어도 materialize 후 False."""
    proposal_id = await _seed_approved_proposal(
        db_session, dedup_suffix="_t8", auto_trade_in_params=True
    )
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    version = await db_session.get(StrategyVersion, result.strategy_version_id)
    assert version is not None
    assert version.parameters.get("auto_trade_enabled") is not True
    assert version.parameters.get("auto_trade_enabled") is False


# ── 9. materialize 시 Experiment 생성 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_materialize_creates_experiment(db_session: AsyncSession) -> None:
    """9. materialize 시 Experiment(RUNNING)이 생성됨."""
    from app.domain.models.experiment import Experiment
    before = (await db_session.execute(select(func.count()).select_from(Experiment))).scalar()

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t9")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    after = (await db_session.execute(select(func.count()).select_from(Experiment))).scalar()
    assert after == before + 1

    exp_repo = ExperimentRepository(db_session)
    experiment = await exp_repo.get(result.experiment_id)
    assert experiment is not None
    assert experiment.status == ExperimentStatus.RUNNING
    assert experiment.started_at is not None


# ── 10. ExperimentVariant가 새 StrategyVersion 참조 ──────────────────────────

@pytest.mark.asyncio
async def test_experiment_variant_references_version(db_session: AsyncSession) -> None:
    """10. ExperimentVariant.strategy_version_id = materialize로 생성된 version."""
    from app.domain.repositories.experiment import ExperimentVariantRepository

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t10")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    variant_repo = ExperimentVariantRepository(db_session)
    variants = await variant_repo.list_by_experiment(result.experiment_id)
    assert len(variants) == 1
    assert variants[0].strategy_version_id == result.strategy_version_id


# ── 11. proposal.experiment_id 저장 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_proposal_experiment_id_is_set(db_session: AsyncSession) -> None:
    """11. materialize 후 proposal.experiment_id가 설정됨."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t11")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.get(proposal_id)
    assert proposal.experiment_id == result.experiment_id
    assert proposal.materialized_at is not None


# ── 12. 중복 materialize 방지 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_materialize_returns_existing(db_session: AsyncSession) -> None:
    """12. 같은 proposal 두 번 materialize 시 기존 experiment 반환."""
    from app.domain.models.experiment import Experiment
    from app.domain.models.strategy import Strategy

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t12")
    svc = IntelligenceExperimentService(db_session)

    result1 = await svc.materialize(proposal_id)
    assert not result1.already_existed

    strategy_count_after_first = (
        await db_session.execute(select(func.count()).select_from(Strategy))
    ).scalar()
    exp_count_after_first = (
        await db_session.execute(select(func.count()).select_from(Experiment))
    ).scalar()

    result2 = await svc.materialize(proposal_id)
    assert result2.already_existed
    assert result2.experiment_id == result1.experiment_id

    # 두 번째 materialize 후 Strategy/Experiment 수가 증가하지 않음
    strategy_count_after_second = (
        await db_session.execute(select(func.count()).select_from(Strategy))
    ).scalar()
    exp_count_after_second = (
        await db_session.execute(select(func.count()).select_from(Experiment))
    ).scalar()
    assert strategy_count_after_second == strategy_count_after_first
    assert exp_count_after_second == exp_count_after_first


# ── 13. materialize 시 ExperimentResult 없음 ─────────────────────────────────

@pytest.mark.asyncio
async def test_materialize_does_not_create_experiment_result(db_session: AsyncSession) -> None:
    """13. materialize 시 ExperimentResult는 생성하지 않음."""
    before = (
        await db_session.execute(select(func.count()).select_from(ExperimentResult))
    ).scalar()

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t13")
    svc = IntelligenceExperimentService(db_session)
    await svc.materialize(proposal_id)

    after = (
        await db_session.execute(select(func.count()).select_from(ExperimentResult))
    ).scalar()
    assert before == after, f"ExperimentResult가 materialize 시 생성되었음: {after - before}건"


# ── 14. conclude → Experiment.status=COMPLETED ──────────────────────────────

@pytest.mark.asyncio
async def test_conclude_sets_status_completed(db_session: AsyncSession) -> None:
    """14. conclude 시 Experiment.status = COMPLETED."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t14")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)

    await svc.conclude(result.experiment_id)

    exp_repo = ExperimentRepository(db_session)
    experiment = await exp_repo.get(result.experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert experiment.ended_at is not None


# ── 15. conclude → ExperimentResult 저장 ────────────────────────────────────

@pytest.mark.asyncio
async def test_conclude_saves_experiment_result(db_session: AsyncSession) -> None:
    """15. conclude 후 ExperimentResult가 저장됨 (trades 0개여도 저장)."""
    before = (
        await db_session.execute(select(func.count()).select_from(ExperimentResult))
    ).scalar()

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t15")
    svc = IntelligenceExperimentService(db_session)
    result = await svc.materialize(proposal_id)
    await svc.conclude(result.experiment_id)

    after = (
        await db_session.execute(select(func.count()).select_from(ExperimentResult))
    ).scalar()
    assert after > before, "conclude 후 ExperimentResult가 생성되지 않음"


# ── 16. 종료 조건 max_days 판단 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_condition_max_days(db_session: AsyncSession) -> None:
    """16. max_days 충족 여부를 올바르게 판단."""
    from datetime import timedelta, timezone
    from datetime import datetime as dt

    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t16")
    svc = IntelligenceExperimentService(db_session)
    mat = await svc.materialize(proposal_id)

    # started_at을 8일 전으로 조정
    exp_repo = ExperimentRepository(db_session)
    experiment = await exp_repo.get(mat.experiment_id)
    experiment.started_at = dt.now(timezone.utc) - timedelta(days=8)
    await db_session.flush()

    cond = await svc.check_stop_conditions(mat.experiment_id, max_days=7, min_trades=100)
    assert cond.max_days_met is True
    assert cond.can_conclude is True


# ── 17. 종료 조건 min_trades 판단 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_condition_min_trades_not_met(db_session: AsyncSession) -> None:
    """17. 거래 0건이면 min_trades 미충족."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t17")
    svc = IntelligenceExperimentService(db_session)
    mat = await svc.materialize(proposal_id)

    cond = await svc.check_stop_conditions(mat.experiment_id, max_days=100, min_trades=20)
    assert cond.min_trades_met is False
    assert cond.total_trades == 0


@pytest.mark.asyncio
async def test_stop_condition_min_trades_zero_threshold(db_session: AsyncSession) -> None:
    """17b. min_trades=0이면 거래 0건이어도 충족."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_t17b")
    svc = IntelligenceExperimentService(db_session)
    mat = await svc.materialize(proposal_id)

    cond = await svc.check_stop_conditions(mat.experiment_id, max_days=100, min_trades=0)
    assert cond.min_trades_met is True
    assert cond.can_conclude is True


# ── 18. scheduler 기본 비활성 ─────────────────────────────────────────────────

def test_experiment_autopilot_scheduler_default_disabled() -> None:
    """18. intelligence_experiment_autopilot_scheduler_enabled 기본값 False."""
    from app.core.config import Settings
    s = Settings()
    assert s.intelligence_experiment_autopilot_scheduler_enabled is False


# ── 19. 기존 ResearchPipelineService 미변경 ──────────────────────────────────

def test_research_pipeline_service_unchanged() -> None:
    """19. ResearchPipelineService는 IntelligenceExperimentService를 참조하지 않음."""
    import app.services.research_pipeline_service as rps_mod
    source = inspect.getsource(rps_mod)
    assert "IntelligenceExperimentService" not in source
    assert "materialize" not in source


# ── 20. 기존 AssignmentService 미변경 ────────────────────────────────────────

def test_assignment_service_unchanged() -> None:
    """20. AssignmentService는 IntelligenceStrategyProposal을 참조하지 않음."""
    import app.services.assignment_service as asgn_mod
    source = inspect.getsource(asgn_mod)
    assert "IntelligenceStrategyProposal" not in source
    assert "materialize" not in source


# ── 21. 실전 주문 API 호출 없음 ───────────────────────────────────────────────

def test_no_order_api_in_experiment_service() -> None:
    """21. IntelligenceExperimentService 소스에 주문 TR_ID 없음."""
    import app.services.intelligence_experiment_service as svc_mod
    source = inspect.getsource(svc_mod)
    for forbidden in ["TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U"]:
        assert forbidden not in source, f"{forbidden!r}이 experiment service에 포함됨"


# ── 22. broker.place_order 호출 없음 ────────────────────────────────────────

def test_no_place_order_in_experiment_service() -> None:
    """22. IntelligenceExperimentService에 place_order 없음."""
    import app.services.intelligence_experiment_service as svc_mod
    source = inspect.getsource(svc_mod)
    assert "place_order" not in source


# ── 23. TR_ID 금지 문자열 없음 ─────────────────────────────────────────────

def test_no_trading_tr_id_in_experiment_service() -> None:
    """23. 실전/모의 주문 TR_ID가 service 파일에 없음."""
    import app.services.intelligence_experiment_service as svc_mod
    source = inspect.getsource(svc_mod)
    # 기존 테스트와 동일 패턴
    assert "TTTC0012U" not in source and "VTTC0011U" not in source


# ── 24. KIS_REAL_TRADING_ENABLED 변경 없음 ──────────────────────────────────

def test_kis_real_trading_still_disabled() -> None:
    """24. KIS_REAL_TRADING_ENABLED 기본값 여전히 False."""
    from app.core.config import Settings
    assert Settings().kis_real_trading_enabled is False


# ── 25. auto_trade_enabled 자동 true 없음 ────────────────────────────────────

def test_no_auto_trade_enabled_true_in_service() -> None:
    """25. IntelligenceExperimentService 소스에 auto_trade_enabled=True/true 패턴 없음."""
    import app.services.intelligence_experiment_service as svc_mod
    source = inspect.getsource(svc_mod)
    # False로 강제 override하는 코드는 있어도 True 설정 코드는 없어야 함
    assert '"auto_trade_enabled": True' not in source
    assert "'auto_trade_enabled': True" not in source
    assert "auto_trade_enabled = True" not in source


# ── API smoke 테스트 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_materialize_smoke(db_session: AsyncSession) -> None:
    """API POST /intelligence/strategy-proposals/{id}/materialize 기본 동작."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_api1")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/intelligence/strategy-proposals/{proposal_id}/materialize"
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["proposal_id"] == proposal_id
        assert data["experiment_id"] > 0
        assert data["strategy_version_id"] > 0
        assert data["already_existed"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_conclude_smoke(db_session: AsyncSession) -> None:
    """API POST /intelligence/experiments/{id}/conclude 기본 동작."""
    proposal_id = await _seed_approved_proposal(db_session, dedup_suffix="_api2")
    svc = IntelligenceExperimentService(db_session)
    mat = await svc.materialize(proposal_id)

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/intelligence/experiments/{mat.experiment_id}/conclude"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["experiment_id"] == mat.experiment_id
        assert "winner_variant_id" in data
        assert "variants_count" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_pending_proposal_materialize_returns_422(db_session: AsyncSession) -> None:
    """API: PENDING proposal materialize 시 422."""
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(
        source_key="src_pending_api",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
    )
    await db_session.flush()
    ev_repo = IntelligenceEventRepository(db_session)
    ev = await ev_repo.create(
        source_id=src.id, event_type="news", market=MarketCode.KR,
        symbol_code="000660", title="x", summary="x",
        dedup_hash="ev_api_pending", status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()
    cand_repo = IntelligenceCandidateRepository(db_session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id, symbol_code="000660", market=MarketCode.KR,
        score=50, why_text="x", source_type="news", matched_themes=[],
        score_components={}, dedup_hash="cand_api_pending",
    )
    await db_session.flush()
    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposal = await proposal_repo.create(
        intelligence_candidate_id=cand.id, symbol_code="000660", market=MarketCode.KR,
        suggested_strategy_type="moving_average_cross",
        suggested_parameters={}, rationale=None, confidence_score=None,
        score_components=None, source="heuristic",
        status=IntelligenceStrategyProposalStatus.PENDING,
        dedup_hash="prop_api_pending",
    )
    await db_session.flush()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/intelligence/strategy-proposals/{proposal.id}/materialize"
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
