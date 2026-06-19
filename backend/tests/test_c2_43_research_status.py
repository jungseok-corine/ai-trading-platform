"""C-2.43 자율 연구 루프 관제탑 상태 테스트."""

from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ScannerRuleStatus
from app.main import app
from app.services.research_status_service import ResearchStatusService
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_review_service import ScannerReviewService
from app.services.scanner_service import ScannerService

KST = ZoneInfo("Asia/Seoul")


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed(session: AsyncSession) -> None:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("vol")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    # pending 스캐너 제안 1건
    await ScannerProposalService(session).create_proposal(
        scanner_rule_id=rule.id,
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 2.6}}],
        title="강화", base_version_id=sv.id,
    )
    # scanner_review 잡 실행 이력 1건 기록
    await ScannerReviewService(session).review_and_record()


async def test_status_aggregates_jobs_and_pending(db_session: AsyncSession) -> None:
    await _seed(db_session)
    status = await ResearchStatusService(db_session).status()

    job_ids = {j.job_id for j in status.jobs}
    assert job_ids == {"research_pipeline", "scanner_review", "strategy_review", "daily_report"}

    review_job = next(j for j in status.jobs if j.job_id == "scanner_review")
    assert review_job.last_run_at is not None
    assert review_job.status == "success"

    # 아직 안 돈 잡은 last_run_at이 None
    pipeline_job = next(j for j in status.jobs if j.job_id == "research_pipeline")
    assert pipeline_job.last_run_at is None

    assert status.pending["scanner"] == 1
    assert status.pending["total"] == 1
    assert status.active["scanner_versions"] == 1


async def test_status_via_api(db_session: AsyncSession) -> None:
    await _seed(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/research-status")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["jobs"]) == 4
            assert body["pending"]["scanner"] == 1
            assert body["active"]["scanner_versions"] == 1
    finally:
        app.dependency_overrides.clear()


async def test_empty_status(db_session: AsyncSession) -> None:
    status = await ResearchStatusService(db_session).status()
    assert all(j.last_run_at is None for j in status.jobs)
    assert status.pending["total"] == 0
    assert status.active["scanner_versions"] == 0
    assert status.active["strategy_versions"] == 0
