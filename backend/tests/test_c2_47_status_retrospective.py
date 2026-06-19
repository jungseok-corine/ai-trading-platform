"""C-2.47 관제탑에 제안 회고 요약 노출 테스트."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.services.research_status_service import ResearchStatusService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_status_includes_retrospective_summary(db_session: AsyncSession) -> None:
    status = await ResearchStatusService(db_session).status()
    assert status.retrospective == {
        "total": 0,
        "improved": 0,
        "worse": 0,
        "inconclusive": 0,
    }


async def test_status_retrospective_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/research-status")
            assert resp.status_code == 200
            assert "retrospective" in resp.json()
            assert resp.json()["retrospective"]["total"] == 0
    finally:
        app.dependency_overrides.clear()
