"""C-3.24 운영 콘솔 엔드포인트 HTTP 스모크 테스트.

서비스 단위 테스트가 잡지 못하는 라우터 결선/직렬화 문제를 ASGI 레벨에서 잡는다.
빈 DB에서도 200을 반환하고 고정 구조를 갖는지만 확인한다(read-only).
"""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


async def _get(client: AsyncClient, url: str) -> dict:
    resp = await client.get(url)
    assert resp.status_code == 200, f"{url} -> {resp.status_code}"
    return resp.json()


async def test_console_endpoints_return_200(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            overview = await _get(client, "/api/v1/operations-overview")
            assert "safety" in overview and "trading" in overview and "cost" in overview

            digest = await _get(client, "/api/v1/operations-digest")
            assert "severity" in digest and "alerts" in digest

            cost = await _get(client, "/api/v1/ai-cost/summary")
            assert "budget" in cost and "by_model" in cost

            safety = await _get(client, "/api/v1/safety-status")
            assert safety["invariants_ok"] is True

            sched = await _get(client, "/api/v1/scheduler-health")
            assert "jobs" in sched

            portfolio = await _get(client, "/api/v1/portfolio-summary")
            assert portfolio["open_positions"] == 0

            for url in (
                "/api/v1/trade-activity",
                "/api/v1/trade-activity/equity-curve",
                "/api/v1/risk-events/summary",
                "/api/v1/proposal-funnel",
                "/api/v1/research-funnel",
                "/api/v1/data-freshness",
                "/api/v1/promotion-readiness",
                "/api/v1/operations-snapshot/trend",
                "/api/v1/analysis-audit",
            ):
                await _get(client, url)
    finally:
        app.dependency_overrides.clear()


async def test_snapshot_record_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/operations-snapshot/record")
            assert resp.status_code == 200
            assert "snapshot_date" in resp.json()
    finally:
        app.dependency_overrides.clear()
