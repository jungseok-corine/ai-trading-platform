"""C-2.58 예시 시딩 헬퍼 테스트."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import StrategyVersionStatus
from app.main import app
from app.services.assignment_service import AssignmentService
from app.services.scanner_service import ScannerService
from app.services.seed_service import SeedService
from app.services.strategy_service import StrategyService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_seed_creates_examples(db_session: AsyncSession) -> None:
    summary = await SeedService(db_session).seed_examples()
    assert len(summary.scanners_created) == 3
    assert len(summary.strategies_created) == 3
    assert len(summary.assignment_rules_created) == 2

    scanners = await ScannerService(db_session).list_rules()
    assert len(scanners) == 3
    strategies = await StrategyService(db_session).list_strategies()
    assert len(strategies) == 3
    rules = await AssignmentService(db_session).list_rules()
    assert len(rules) == 2


async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    svc = SeedService(db_session)
    await svc.seed_examples()
    second = await svc.seed_examples()
    # 2회차는 전부 건너뛰고 새로 만들지 않는다
    assert second.scanners_created == []
    assert second.strategies_created == []
    assert second.assignment_rules_created == []
    assert len(second.skipped_existing) == 8  # 3+3+2

    # 중복 생성 안 됨
    assert len(await ScannerService(db_session).list_rules()) == 3
    assert len(await StrategyService(db_session).list_strategies()) == 3


async def test_seed_strategies_are_safe(db_session: AsyncSession) -> None:
    """안전 불변식: 시드 전략은 auto_trade_enabled=False·status=TESTING."""
    await SeedService(db_session).seed_examples()
    strat_svc = StrategyService(db_session)
    for strategy, _ in await strat_svc.list_strategies():
        versions = await strat_svc.list_versions(strategy.id)
        for v in versions:
            assert v.status == StrategyVersionStatus.TESTING
            assert v.parameters.get("auto_trade_enabled") is False


async def test_seed_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/seed/examples")
            assert resp.status_code == 201
            body = resp.json()
            assert len(body["scanners_created"]) == 3
            assert len(body["assignment_rules_created"]) == 2
    finally:
        app.dependency_overrides.clear()
