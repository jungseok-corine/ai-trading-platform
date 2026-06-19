"""C-2.35 Autonomous Research Pipeline 테스트."""

from datetime import datetime, timezone
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ScannerRuleStatus
from app.domain.models.investor_flow import InvestorFlow
from app.domain.models.market_data import MarketData
from app.main import app
from app.services.assignment_service import AssignmentService
from app.services.research_pipeline_service import ResearchPipelineService
from app.services.scanner_service import ScannerService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed(session: AsyncSession, status: ScannerRuleStatus = ScannerRuleStatus.TESTING) -> int:
    """market_data + 수급 + 스캐너룰(조건) + 배정규칙을 시드하고 scanner_rule_id 반환."""
    base = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)
    for i in range(25):
        close = Decimal("110") if i == 24 else Decimal("100")
        vol = 5000 if i == 24 else 1000
        session.add(MarketData(symbol_code="005930", timeframe="1m", ts=base.replace(minute=i),
                               open=close, high=close, low=close, close=close, volume=vol))
    session.add(InvestorFlow(symbol_code="005930", trade_date=datetime(2026, 6, 16).date(),
                             foreign_net_buy_quantity=10000))
    await session.commit()

    scanner = ScannerService(session)
    rule = await scanner.create_rule("morning spike")
    await scanner.create_version(
        rule.id,
        conditions=[
            {"type": "volume_spike", "params": {"multiplier": 2.0}},
            {"type": "price_change_pct", "params": {"min_pct": 5.0}},
            {"type": "investor_flow", "params": {"foreign": "net_buy"}},
        ],
        status=status,
    )

    # scanner_rule 전용 배정 규칙
    await AssignmentService(session).create_rule(
        name="vol전략배정",
        strategy_type="volume_confirmed_ma_cross",
        scanner_rule_id=rule.id,
    )
    return rule.id


async def test_run_once_finds_and_assigns(db_session: AsyncSession) -> None:
    await _seed(db_session)
    summary = await ResearchPipelineService(db_session).run_once(symbol_codes=["005930"])

    assert summary.versions == 1
    assert summary.candidates == 1
    assert summary.assignments == 1
    assert summary.per_version[0].matched == 1
    assert summary.per_version[0].assigned == 1

    # 배정 로그가 실제로 남았는지
    logs = await AssignmentService(db_session).list_logs(symbol_code="005930")
    assert len(logs) == 1
    assert logs[0].strategy_type == "volume_confirmed_ma_cross"


async def test_run_once_skips_when_no_active_version(db_session: AsyncSession) -> None:
    # DRAFT 버전만 있으면 active 목록에 안 잡혀 실행 대상이 없다
    await _seed(db_session, status=ScannerRuleStatus.DRAFT)
    summary = await ResearchPipelineService(db_session).run_once(symbol_codes=["005930"])
    assert summary.versions == 0
    assert summary.candidates == 0
    assert summary.assignments == 0


async def test_run_pipeline_via_api(db_session: AsyncSession) -> None:
    await _seed(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/research-pipeline/run",
                json={"symbol_codes": ["005930"]},
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["candidates"] == 1
            assert body["assignments"] == 1
            assert body["per_version"][0]["matched"] == 1
    finally:
        app.dependency_overrides.clear()


async def test_run_once_without_assign(db_session: AsyncSession) -> None:
    await _seed(db_session)
    summary = await ResearchPipelineService(db_session).run_once(
        symbol_codes=["005930"], auto_assign=False
    )
    assert summary.candidates == 1
    assert summary.assignments == 0  # 배정 안 함
