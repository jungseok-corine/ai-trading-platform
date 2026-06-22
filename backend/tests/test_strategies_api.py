from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import StrategyVersionStatus
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_strategies_api_full_flow(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/strategies", json={"name": "MA Cross", "description": "이동평균 교차 전략"}
            )
            assert create_resp.status_code == 200
            strategy = create_resp.json()
            assert strategy["name"] == "MA Cross"
            assert strategy["version_count"] == 0
            strategy_id = strategy["id"]

            list_resp = await client.get("/api/v1/strategies")
            assert list_resp.status_code == 200
            strategies = list_resp.json()
            assert any(s["id"] == strategy_id and s["version_count"] == 0 for s in strategies)

            empty_versions_resp = await client.get(f"/api/v1/strategies/{strategy_id}/versions")
            assert empty_versions_resp.status_code == 200
            assert empty_versions_resp.json() == []

            create_version_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={
                    "parameters": {
                        "symbol_code": "005930",
                        "short_window": 5,
                        "long_window": 20,
                        "quantity": 1,
                        "timeframe": "1m",
                    },
                    "change_description": "초기 버전",
                },
            )
            assert create_version_resp.status_code == 200
            version = create_version_resp.json()
            assert version["strategy_id"] == strategy_id
            assert version["version_no"] == 1
            assert version["status"] == "draft"
            assert version["parameters"]["symbol_code"] == "005930"
            assert version["parameters"]["strategy_type"] == "moving_average_cross"
            assert version["parameters"]["auto_trade_enabled"] is False
            version_id = version["id"]

            list_versions_resp = await client.get(f"/api/v1/strategies/{strategy_id}/versions")
            assert list_versions_resp.status_code == 200
            assert len(list_versions_resp.json()) == 1

            list_resp_after = await client.get("/api/v1/strategies")
            updated_strategy = next(s for s in list_resp_after.json() if s["id"] == strategy_id)
            assert updated_strategy["version_count"] == 1

            # 두번째 버전 생성 -> version_no가 2여야 한다
            second_version_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={"parameters": {"symbol_code": "005930"}},
            )
            assert second_version_resp.json()["version_no"] == 2

            # status를 testing으로 변경
            patch_resp = await client.patch(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}",
                json={"status": "testing"},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["status"] == "testing"
            # parameters는 변경되지 않아야 한다
            assert patch_resp.json()["parameters"]["symbol_code"] == "005930"

            # status를 active로 변경
            patch_active_resp = await client.patch(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}",
                json={"status": "active"},
            )
            assert patch_active_resp.json()["status"] == "active"
    finally:
        app.dependency_overrides.clear()


async def test_create_version_with_auto_trade_requires_account_id(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/v1/strategies", json={"name": "Auto Trade Strategy"})
            strategy_id = create_resp.json()["id"]

            resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={
                    "parameters": {
                        "symbol_code": "005930",
                        "auto_trade_enabled": True,
                    }
                },
            )
            assert resp.status_code == 422

            resp_ok = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={
                    "parameters": {
                        "symbol_code": "005930",
                        "auto_trade_enabled": True,
                        "account_id": 1,
                    }
                },
            )
            assert resp_ok.status_code == 200
            assert resp_ok.json()["parameters"]["auto_trade_enabled"] is True
    finally:
        app.dependency_overrides.clear()


async def test_update_unknown_version_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/v1/strategies", json={"name": "Strategy"})
            strategy_id = create_resp.json()["id"]

            resp = await client.patch(
                f"/api/v1/strategies/{strategy_id}/versions/999999",
                json={"status": "active"},
            )
            assert resp.status_code == 404

            resp_unknown_strategy = await client.get("/api/v1/strategies/999999/versions")
            assert resp_unknown_strategy.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_patch_parameters_fills_in_defaults_for_omitted_fields(db_session: AsyncSession) -> None:
    """parameters를 PATCH할 때 생략된 필드(strategy_type, enabled 등)는 기본값으로 채워져야 하며,
    JSONB에서 사라지면 안 된다 (StrategyRunnerService가 strategy_type으로 매칭하기 때문)."""
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/v1/strategies", json={"name": "Patch Defaults Test"})
            strategy_id = create_resp.json()["id"]

            create_version_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={"parameters": {"symbol_code": "005930"}},
            )
            version_id = create_version_resp.json()["id"]

            # account_id, auto_trade_enabled만 지정해 PATCH (strategy_type, enabled는 생략)
            patch_resp = await client.patch(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}",
                json={
                    "parameters": {
                        "symbol_code": "005930",
                        "account_id": 1,
                        "auto_trade_enabled": True,
                    }
                },
            )
            assert patch_resp.status_code == 200
            parameters = patch_resp.json()["parameters"]
            assert parameters["strategy_type"] == "moving_average_cross"
            assert parameters["enabled"] is True
            assert parameters["account_id"] == 1
            assert parameters["auto_trade_enabled"] is True
    finally:
        app.dependency_overrides.clear()


async def test_list_active_versions_includes_active_status(db_session: AsyncSession) -> None:
    """StrategyVersionRepository.list_active()는 status가 active 또는 testing인 버전을 반환한다."""
    from app.domain.repositories.strategy import StrategyVersionRepository
    from app.services.strategy_service import StrategyService

    service = StrategyService(db_session)
    strategy = await service.create_strategy("List Active Test")
    await service.create_version(
        strategy.id,
        parameters={"symbol_code": "005930"},
        status=StrategyVersionStatus.ACTIVE,
    )
    await service.create_version(
        strategy.id,
        parameters={"symbol_code": "000660"},
        status=StrategyVersionStatus.DRAFT,
    )

    active = await StrategyVersionRepository(db_session).list_active()
    symbol_codes = {v.parameters["symbol_code"] for v in active}
    assert "005930" in symbol_codes
    assert "000660" not in symbol_codes


async def test_update_strategy_name_and_description(db_session: AsyncSession) -> None:
    """PATCH /strategies/{id}로 이름/설명을 수정할 수 있다(같은 이름 구분용)."""
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = (await client.post(
                "/api/v1/strategies", json={"name": "[유니버스] RSI 평균회귀", "description": "C-4"}
            )).json()
            sid = created["id"]

            resp = await client.patch(
                f"/api/v1/strategies/{sid}",
                json={"name": "[관심종목] RSI 평균회귀", "description": "KR 관심종목 전용"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["name"] == "[관심종목] RSI 평균회귀"
            assert body["description"] == "KR 관심종목 전용"

            # 부분 수정(설명만)
            resp2 = await client.patch(f"/api/v1/strategies/{sid}", json={"description": "설명만 변경"})
            assert resp2.status_code == 200
            assert resp2.json()["name"] == "[관심종목] RSI 평균회귀"  # 이름 유지
            assert resp2.json()["description"] == "설명만 변경"

            # 없는 전략
            assert (await client.patch("/api/v1/strategies/999999", json={"name": "x"})).status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
