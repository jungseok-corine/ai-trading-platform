"""C-2.36 파이프라인 실행 이력 테스트."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ScannerRuleStatus
from app.main import app
from app.services.research_pipeline_service import ResearchPipelineService
from app.services.scanner_service import ScannerService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _make_active_version(session: AsyncSession) -> None:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("hist rule")
    await scanner.create_version(
        rule.id,
        conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )


async def test_run_and_record_creates_history(db_session: AsyncSession) -> None:
    await _make_active_version(db_session)
    service = ResearchPipelineService(db_session)

    summary = await service.run_and_record(symbol_codes=[])  # 종목 없음 → 후보 0
    assert summary.versions == 1

    runs = await service.list_runs()
    assert len(runs) == 1
    assert runs[0].job_id == "research_pipeline"
    assert runs[0].status.value == "success"
    assert runs[0].summary["versions"] == 1
    assert runs[0].summary["candidates"] == 0


async def test_run_and_history_via_api(db_session: AsyncSession) -> None:
    await _make_active_version(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 실행 2회
            await client.post("/api/v1/research-pipeline/run", json={"symbol_codes": []})
            await client.post("/api/v1/research-pipeline/run", json={"symbol_codes": []})

            runs = await client.get("/api/v1/research-pipeline/runs")
            assert runs.status_code == 200
            body = runs.json()
            assert len(body) == 2
            assert all(r["job_id"] == "research_pipeline" for r in body)
            assert body[0]["summary"]["versions"] == 1
    finally:
        app.dependency_overrides.clear()
