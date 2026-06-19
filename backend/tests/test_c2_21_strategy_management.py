"""C-2.21 Strategy Management Cleanup: archive / delete 정책 테스트."""

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import StrategyVersionStatus, TradeSide
from app.domain.repositories.signal_log import SignalLogRepository
from app.main import app
from app.services.strategy_service import StrategyService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _create_strategy(client: AsyncClient, name: str) -> int:
    resp = await client.post("/api/v1/strategies", json={"name": name})
    assert resp.status_code == 200
    return resp.json()["id"]


async def _create_version(client: AsyncClient, strategy_id: int) -> int:
    resp = await client.post(
        f"/api/v1/strategies/{strategy_id}/versions",
        json={"parameters": {"symbol_code": "005930"}},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


async def test_archive_hides_version_and_include_archived_shows_it(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_id = await _create_strategy(client, "Archive Test")
            version_id = await _create_version(client, strategy_id)

            archive_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}/archive"
            )
            assert archive_resp.status_code == 200
            assert archive_resp.json()["status"] == "archived"

            # 기본 목록에서는 archived 제외
            default_list = await client.get(f"/api/v1/strategies/{strategy_id}/versions")
            assert default_list.status_code == 200
            assert all(v["id"] != version_id for v in default_list.json())

            # include_archived=true 면 포함
            with_archived = await client.get(
                f"/api/v1/strategies/{strategy_id}/versions",
                params={"include_archived": "true"},
            )
            assert any(v["id"] == version_id for v in with_archived.json())
    finally:
        app.dependency_overrides.clear()


async def test_delete_draft_without_references(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_id = await _create_strategy(client, "Delete Draft Test")
            version_id = await _create_version(client, strategy_id)  # 기본 status=draft

            del_resp = await client.delete(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}"
            )
            assert del_resp.status_code == 204

            # 삭제 후 목록에서 사라짐 (include_archived 여부와 무관)
            after = await client.get(
                f"/api/v1/strategies/{strategy_id}/versions",
                params={"include_archived": "true"},
            )
            assert all(v["id"] != version_id for v in after.json())
    finally:
        app.dependency_overrides.clear()


async def test_delete_non_draft_returns_409(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_id = await _create_strategy(client, "Delete Non-Draft Test")
            version_id = await _create_version(client, strategy_id)

            # TESTING으로 전환 -> hard delete 금지
            await client.patch(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}",
                json={"status": "testing"},
            )

            del_resp = await client.delete(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}"
            )
            assert del_resp.status_code == 409
            # 정책상 archive는 여전히 가능해야 한다
            archive_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}/archive"
            )
            assert archive_resp.status_code == 200
            assert archive_resp.json()["status"] == "archived"
    finally:
        app.dependency_overrides.clear()


async def test_delete_draft_with_signal_reference_returns_409(db_session: AsyncSession) -> None:
    """DRAFT라도 signal_log 참조가 있으면 hard delete가 금지되어야 한다."""
    service = StrategyService(db_session)
    strategy = await service.create_strategy("Delete With Refs Test")
    version = await service.create_version(
        strategy.id,
        parameters={"symbol_code": "005930"},
        status=StrategyVersionStatus.DRAFT,
    )

    # 이 버전을 참조하는 signal_log 한 건 생성
    await SignalLogRepository(db_session).create(
        symbol_code="005930",
        strategy_version_id=version.id,
        signal_type=TradeSide.BUY,
        generated_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            del_resp = await client.delete(
                f"/api/v1/strategies/{strategy.id}/versions/{version.id}"
            )
            assert del_resp.status_code == 409
            assert "참조" in del_resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


async def test_delete_unknown_version_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_id = await _create_strategy(client, "Delete 404 Test")
            del_resp = await client.delete(
                f"/api/v1/strategies/{strategy_id}/versions/999999"
            )
            assert del_resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
