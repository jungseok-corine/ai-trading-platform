"""C-2.29.1 Status Transition Planner 테스트 (22 tests).

검증 항목:
1.  strategy proposal → new_version status = TESTING
2.  strategy proposal → new_version auto_trade_enabled = False
3.  scanner proposal → new_version status = TESTING
4.  scanner proposal → new_version auto_trade_enabled = None
5.  존재하지 않는 strategy proposal → PlannerProposalNotFoundError
6.  존재하지 않는 scanner proposal → PlannerProposalNotFoundError
7.  plan_valid = True (기본 검증 통과)
8.  RUNNING experiment variant 있는 버전 → blocked_actions 에 추가됨
9.  RUNNING experiment variant 있는 버전 → proposed_action = KEEP
10. RUNNING experiment에 없는 버전은 blocked 안 됨
11. ACTIVE 전략 버전 → safety_warnings에 포함, proposed_action = KEEP
12. ACTIVE 스캐너 버전 → safety_warnings에 포함, proposed_action = KEEP
13. validate: new_version status != TESTING → plan_valid = False
14. validate: strategy new_version.auto_trade_enabled != False → plan_valid = False
15. validate: ACTIVE 신규 생성 시도 → plan_valid = False
16. validate: proposed_action = DRAFT → plan_valid = False (R-5)
17. to_dict() 구조 검증 — strategy
18. to_dict() 구조 검증 — scanner
19. GET /strategy-proposals/{id}/transition-plan → 200 + plan_valid
20. GET /strategy-proposals/{id}/transition-plan → 404 for missing proposal
21. GET /scanner-proposals/{id}/transition-plan → 200 + plan_valid
22. GET /scanner-proposals/{id}/transition-plan → 404 for missing proposal
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import (
    ExperimentStatus,
    MarketCode,
    ScannerRuleStatus,
    StrategyVersionStatus,
    VariantRole,
)
from app.domain.models.experiment import Experiment, ExperimentVariant
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.models.strategy_proposal import StrategyProposal
from app.main import app
from app.services.scanner_service import ScannerService
from app.services.status_transition_planner import (
    BlockedAction,
    NewVersionPlan,
    PlannerProposalNotFoundError,
    StatusTransitionPlan,
    StatusTransitionPlannerService,
    VersionActionPlan,
)
from app.services.strategy_service import StrategyService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


# ── seed helpers ─────────────────────────────────────────────────────────────

async def _seed_strategy_proposal(session: AsyncSession) -> tuple[int, int, int]:
    """전략 + 버전 + pending 제안을 만들고 (strategy_id, version_id, proposal_id) 반환."""
    svc = StrategyService(session)
    strategy = await svc.create_strategy("planner test strategy")
    version = await svc.create_version(
        strategy.id,
        parameters={
            "strategy_type": "volume_confirmed_ma_cross",
            "symbol_code": "005930",
            "volume_multiplier": 1.5,
        },
    )
    proposal = StrategyProposal(
        strategy_id=strategy.id,
        base_version_id=version.id,
        title="플래너 테스트 제안",
        rationale="rationale",
        suggested_parameters={
            "strategy_type": "volume_confirmed_ma_cross",
            "symbol_code": "005930",
            "volume_multiplier": 2.0,
        },
    )
    session.add(proposal)
    await session.commit()
    return strategy.id, version.id, proposal.id


async def _seed_scanner_proposal(session: AsyncSession) -> tuple[int, int]:
    """스캐너 룰 + 버전 + pending 제안을 만들고 (version_id, proposal_id) 반환."""
    svc = ScannerService(session)
    rule = await svc.create_rule("planner test rule")
    version = await svc.create_version(
        rule.id,
        conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    proposal = ScannerRuleProposal(
        scanner_rule_id=rule.id,
        base_version_id=version.id,
        title="스캐너 플래너 테스트",
        rationale="rationale",
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 3.0}}],
    )
    session.add(proposal)
    await session.commit()
    return version.id, proposal.id


async def _attach_running_experiment(
    session: AsyncSession,
    strategy_version_id: int,
    role: VariantRole = VariantRole.CHALLENGER,
) -> tuple[int, int]:
    """RUNNING 실험을 만들고 strategy_version_id를 variant로 연결한다."""
    experiment = Experiment(
        name="running exp",
        market=MarketCode.KR,
        status=ExperimentStatus.RUNNING,
    )
    session.add(experiment)
    await session.flush()
    variant = ExperimentVariant(
        experiment_id=experiment.id,
        strategy_version_id=strategy_version_id,
        role=role,
    )
    session.add(variant)
    await session.commit()
    return experiment.id, variant.id


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_strategy_plan_new_version_status_is_testing(db_session: AsyncSession) -> None:
    """1. strategy proposal → new_version status = TESTING."""
    _, _, proposal_id = await _seed_strategy_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal_id)
    assert plan.new_version.status == StrategyVersionStatus.TESTING.value


@pytest.mark.asyncio
async def test_strategy_plan_new_version_auto_trade_false(db_session: AsyncSession) -> None:
    """2. strategy proposal → new_version auto_trade_enabled = False."""
    _, _, proposal_id = await _seed_strategy_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal_id)
    assert plan.new_version.auto_trade_enabled is False


@pytest.mark.asyncio
async def test_scanner_plan_new_version_status_is_testing(db_session: AsyncSession) -> None:
    """3. scanner proposal → new_version status = TESTING."""
    _, proposal_id = await _seed_scanner_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_scanner_proposal(proposal_id)
    assert plan.new_version.status == ScannerRuleStatus.TESTING.value


@pytest.mark.asyncio
async def test_scanner_plan_no_auto_trade_field(db_session: AsyncSession) -> None:
    """4. scanner proposal → new_version auto_trade_enabled = None (scanner has no auto_trade)."""
    _, proposal_id = await _seed_scanner_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_scanner_proposal(proposal_id)
    assert plan.new_version.auto_trade_enabled is None


@pytest.mark.asyncio
async def test_missing_strategy_proposal_raises_error(db_session: AsyncSession) -> None:
    """5. 존재하지 않는 strategy proposal → PlannerProposalNotFoundError."""
    planner = StatusTransitionPlannerService(db_session)
    with pytest.raises(PlannerProposalNotFoundError):
        await planner.plan_for_strategy_proposal(99999)


@pytest.mark.asyncio
async def test_missing_scanner_proposal_raises_error(db_session: AsyncSession) -> None:
    """6. 존재하지 않는 scanner proposal → PlannerProposalNotFoundError."""
    planner = StatusTransitionPlannerService(db_session)
    with pytest.raises(PlannerProposalNotFoundError):
        await planner.plan_for_scanner_proposal(99999)


@pytest.mark.asyncio
async def test_plan_valid_true_for_normal_proposal(db_session: AsyncSession) -> None:
    """7. plan_valid = True (기본 검증 통과)."""
    _, _, proposal_id = await _seed_strategy_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal_id)
    assert plan.plan_valid is True


@pytest.mark.asyncio
async def test_running_experiment_version_in_blocked_actions(db_session: AsyncSession) -> None:
    """8. RUNNING experiment에 연결된 버전 → blocked_actions에 ARCHIVE_VERSION 추가."""
    _, version_id, proposal_id = await _seed_strategy_proposal(db_session)
    exp_id, _ = await _attach_running_experiment(db_session, version_id)

    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal_id)

    blocked_version_ids = [b.version_id for b in plan.blocked_actions]
    assert version_id in blocked_version_ids
    blocked_action = next(b for b in plan.blocked_actions if b.version_id == version_id)
    assert blocked_action.action == "ARCHIVE_VERSION"
    assert str(exp_id) in blocked_action.reason


@pytest.mark.asyncio
async def test_running_experiment_version_proposed_action_keep(db_session: AsyncSession) -> None:
    """9. RUNNING experiment variant가 있는 버전의 proposed_action = KEEP."""
    _, version_id, proposal_id = await _seed_strategy_proposal(db_session)
    await _attach_running_experiment(db_session, version_id)

    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal_id)

    vp = next(v for v in plan.previous_versions if v.version_id == version_id)
    assert vp.proposed_action == "KEEP"
    assert len(vp.running_experiment_ids) > 0


@pytest.mark.asyncio
async def test_non_running_experiment_version_not_blocked(db_session: AsyncSession) -> None:
    """10. RUNNING 실험에 없는 버전은 blocked 안 됨."""
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("no-block strategy")
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "test", "symbol_code": "000660"},
    )
    # DRAFT 실험 (RUNNING 아님)
    experiment = Experiment(name="draft exp", market=MarketCode.KR, status=ExperimentStatus.DRAFT)
    db_session.add(experiment)
    await db_session.flush()
    variant = ExperimentVariant(
        experiment_id=experiment.id,
        strategy_version_id=version.id,
        role=VariantRole.CHALLENGER,
    )
    db_session.add(variant)
    proposal = StrategyProposal(
        strategy_id=strategy.id,
        base_version_id=version.id,
        title="no-block test",
        rationale="r",
        suggested_parameters={"strategy_type": "test", "symbol_code": "000660"},
    )
    db_session.add(proposal)
    await db_session.commit()

    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal.id)

    blocked_version_ids = [b.version_id for b in plan.blocked_actions]
    assert version.id not in blocked_version_ids
    vp = next(v for v in plan.previous_versions if v.version_id == version.id)
    assert vp.running_experiment_ids == []


@pytest.mark.asyncio
async def test_active_strategy_version_in_safety_warnings(db_session: AsyncSession) -> None:
    """11. ACTIVE 전략 버전 → safety_warnings 포함, proposed_action = KEEP."""
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("active version strategy")
    active_v = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "test", "symbol_code": "005930"},
        status=StrategyVersionStatus.ACTIVE,
    )
    base_v = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "test", "symbol_code": "005930"},
    )
    proposal = StrategyProposal(
        strategy_id=strategy.id,
        base_version_id=base_v.id,
        title="active warning test",
        rationale="r",
        suggested_parameters={"strategy_type": "test", "symbol_code": "005930"},
    )
    db_session.add(proposal)
    await db_session.commit()

    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal.id)

    vp = next(v for v in plan.previous_versions if v.version_id == active_v.id)
    assert vp.proposed_action == "KEEP"
    assert any(str(active_v.id) in w for w in plan.safety_warnings)


@pytest.mark.asyncio
async def test_active_scanner_version_in_safety_warnings(db_session: AsyncSession) -> None:
    """12. ACTIVE 스캐너 버전 → safety_warnings 포함, proposed_action = KEEP."""
    svc = ScannerService(db_session)
    rule = await svc.create_rule("active scanner rule")
    active_v = await svc.create_version(
        rule.id,
        conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.ACTIVE,
    )
    base_v = await svc.create_version(
        rule.id,
        conditions=[{"type": "volume_spike", "params": {"multiplier": 2.5}}],
        status=ScannerRuleStatus.TESTING,
    )
    proposal = ScannerRuleProposal(
        scanner_rule_id=rule.id,
        base_version_id=base_v.id,
        title="scanner active warning",
        rationale="r",
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 3.0}}],
    )
    db_session.add(proposal)
    await db_session.commit()

    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_scanner_proposal(proposal.id)

    vp = next(v for v in plan.previous_versions if v.version_id == active_v.id)
    assert vp.proposed_action == "KEEP"
    assert any(str(active_v.id) in w for w in plan.safety_warnings)


def test_validate_rejects_non_testing_new_version_status() -> None:
    """13. validate: new_version status != TESTING → plan_valid = False."""
    plan = StatusTransitionPlan(
        proposal_id=1,
        proposal_type="strategy",
        new_version=NewVersionPlan(status="active", auto_trade_enabled=False, reason="x"),
        previous_versions=[],
        blocked_actions=[],
        safety_warnings=[],
        plan_valid=True,
    )
    planner = StatusTransitionPlannerService.__new__(StatusTransitionPlannerService)
    result = planner.validate(plan)
    assert result.plan_valid is False
    assert any("TESTING" in w for w in result.safety_warnings)


def test_validate_rejects_auto_trade_true_for_strategy() -> None:
    """14. validate: strategy new_version.auto_trade_enabled != False → plan_valid = False."""
    plan = StatusTransitionPlan(
        proposal_id=1,
        proposal_type="strategy",
        new_version=NewVersionPlan(status="testing", auto_trade_enabled=True, reason="x"),
        previous_versions=[],
        blocked_actions=[],
        safety_warnings=[],
        plan_valid=True,
    )
    planner = StatusTransitionPlannerService.__new__(StatusTransitionPlannerService)
    result = planner.validate(plan)
    assert result.plan_valid is False
    assert any("auto_trade_enabled" in w for w in result.safety_warnings)


def test_validate_rejects_active_new_version() -> None:
    """15. validate: ACTIVE 신규 생성 시도 → plan_valid = False (R-9)."""
    plan = StatusTransitionPlan(
        proposal_id=1,
        proposal_type="strategy",
        new_version=NewVersionPlan(status="active", auto_trade_enabled=False, reason="x"),
        previous_versions=[],
        blocked_actions=[],
        safety_warnings=[],
        plan_valid=True,
    )
    planner = StatusTransitionPlannerService.__new__(StatusTransitionPlannerService)
    result = planner.validate(plan)
    assert result.plan_valid is False
    assert any("ACTIVE" in w or "TESTING" in w for w in result.safety_warnings)


def test_validate_rejects_draft_downgrade() -> None:
    """16. validate: proposed_action = DRAFT → plan_valid = False (R-5)."""
    plan = StatusTransitionPlan(
        proposal_id=1,
        proposal_type="strategy",
        new_version=NewVersionPlan(status="testing", auto_trade_enabled=False, reason="x"),
        previous_versions=[
            VersionActionPlan(
                version_id=42,
                current_status="testing",
                proposed_action="draft",
                reason="downgrade test",
            )
        ],
        blocked_actions=[],
        safety_warnings=[],
        plan_valid=True,
    )
    planner = StatusTransitionPlannerService.__new__(StatusTransitionPlannerService)
    result = planner.validate(plan)
    assert result.plan_valid is False
    assert any("DRAFT" in w for w in result.safety_warnings)


@pytest.mark.asyncio
async def test_to_dict_structure_strategy(db_session: AsyncSession) -> None:
    """17. to_dict() 구조 검증 — strategy."""
    _, _, proposal_id = await _seed_strategy_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_strategy_proposal(proposal_id)
    d = plan.to_dict()

    assert d["proposal_id"] == proposal_id
    assert d["proposal_type"] == "strategy"
    assert "status" in d["new_version"]
    assert "auto_trade_enabled" in d["new_version"]
    assert "reason" in d["new_version"]
    assert isinstance(d["previous_versions"], list)
    assert isinstance(d["blocked_actions"], list)
    assert isinstance(d["safety_warnings"], list)
    assert "plan_valid" in d


@pytest.mark.asyncio
async def test_to_dict_structure_scanner(db_session: AsyncSession) -> None:
    """18. to_dict() 구조 검증 — scanner (auto_trade_enabled 없음)."""
    _, proposal_id = await _seed_scanner_proposal(db_session)
    planner = StatusTransitionPlannerService(db_session)
    plan = await planner.plan_for_scanner_proposal(proposal_id)
    d = plan.to_dict()

    assert d["proposal_type"] == "scanner"
    assert "auto_trade_enabled" not in d["new_version"]
    assert "status" in d["new_version"]
    assert "plan_valid" in d


@pytest.mark.asyncio
async def test_api_get_strategy_transition_plan_200(db_session: AsyncSession) -> None:
    """19. GET /strategy-proposals/{id}/transition-plan → 200 + plan_valid."""
    _, _, proposal_id = await _seed_strategy_proposal(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/strategy-proposals/{proposal_id}/transition-plan")
        assert resp.status_code == 200
        body = resp.json()
        assert body["proposal_id"] == proposal_id
        assert body["proposal_type"] == "strategy"
        assert body["plan_valid"] is True
        assert body["new_version"]["status"] == "testing"
        assert body["new_version"]["auto_trade_enabled"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_get_strategy_transition_plan_404(db_session: AsyncSession) -> None:
    """20. GET /strategy-proposals/{id}/transition-plan → 404 for missing proposal."""
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/strategy-proposals/99999/transition-plan")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_get_scanner_transition_plan_200(db_session: AsyncSession) -> None:
    """21. GET /scanner-proposals/{id}/transition-plan → 200 + plan_valid."""
    _, proposal_id = await _seed_scanner_proposal(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/scanner-proposals/{proposal_id}/transition-plan")
        assert resp.status_code == 200
        body = resp.json()
        assert body["proposal_id"] == proposal_id
        assert body["proposal_type"] == "scanner"
        assert body["plan_valid"] is True
        assert body["new_version"]["status"] == "testing"
        assert "auto_trade_enabled" not in body["new_version"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_get_scanner_transition_plan_404(db_session: AsyncSession) -> None:
    """22. GET /scanner-proposals/{id}/transition-plan → 404 for missing proposal."""
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/scanner-proposals/99999/transition-plan")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
