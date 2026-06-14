from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_watchlist_crud_and_symbols(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/watchlists", json={"name": "관심종목 A", "description": "코스피 대형주"}
            )
            assert create_resp.status_code == 200
            watchlist = create_resp.json()
            assert watchlist["name"] == "관심종목 A"
            assert watchlist["enabled"] is True
            assert watchlist["symbol_count"] == 0
            watchlist_id = watchlist["id"]

            list_resp = await client.get("/api/v1/watchlists")
            assert list_resp.status_code == 200
            assert any(w["id"] == watchlist_id for w in list_resp.json())

            empty_symbols_resp = await client.get(f"/api/v1/watchlists/{watchlist_id}/symbols")
            assert empty_symbols_resp.status_code == 200
            assert empty_symbols_resp.json() == []

            add_resp = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/symbols",
                json={"symbol_code": "005930", "symbol_name": "삼성전자"},
            )
            assert add_resp.status_code == 200
            symbol = add_resp.json()
            assert symbol["symbol_code"] == "005930"
            assert symbol["symbol_name"] == "삼성전자"
            assert symbol["enabled"] is True
            symbol_id = symbol["id"]

            list_resp_after = await client.get("/api/v1/watchlists")
            updated_watchlist = next(w for w in list_resp_after.json() if w["id"] == watchlist_id)
            assert updated_watchlist["symbol_count"] == 1

            # 비활성화
            patch_resp = await client.patch(
                f"/api/v1/watchlists/{watchlist_id}/symbols/{symbol_id}",
                json={"enabled": False, "note": "잠시 제외"},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["enabled"] is False
            assert patch_resp.json()["note"] == "잠시 제외"

            # 삭제
            delete_resp = await client.delete(f"/api/v1/watchlists/{watchlist_id}/symbols/{symbol_id}")
            assert delete_resp.status_code == 204

            symbols_after_delete = await client.get(f"/api/v1/watchlists/{watchlist_id}/symbols")
            assert symbols_after_delete.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_duplicate_symbol_is_rejected(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/v1/watchlists", json={"name": "중복 테스트"})
            watchlist_id = create_resp.json()["id"]

            ok_resp = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/symbols", json={"symbol_code": "005930"}
            )
            assert ok_resp.status_code == 200

            dup_resp = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/symbols", json={"symbol_code": "005930"}
            )
            assert dup_resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


async def test_symbol_not_found_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/v1/watchlists", json={"name": "404 테스트"})
            watchlist_id = create_resp.json()["id"]

            patch_resp = await client.patch(
                f"/api/v1/watchlists/{watchlist_id}/symbols/999999", json={"enabled": False}
            )
            assert patch_resp.status_code == 404

            delete_resp = await client.delete(f"/api/v1/watchlists/{watchlist_id}/symbols/999999")
            assert delete_resp.status_code == 404

            unknown_watchlist_resp = await client.get("/api/v1/watchlists/999999/symbols")
            assert unknown_watchlist_resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_bulk_create_strategy_versions_from_watchlist(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "MA Cross Bulk"})
            strategy_id = strategy_resp.json()["id"]

            watchlist_resp = await client.post("/api/v1/watchlists", json={"name": "코스피 5종목"})
            watchlist_id = watchlist_resp.json()["id"]

            symbol_codes = ["005930", "000660", "035420", "051910", "207940"]
            for code in symbol_codes:
                resp = await client.post(
                    f"/api/v1/watchlists/{watchlist_id}/symbols", json={"symbol_code": code}
                )
                assert resp.status_code == 200

            # 마지막 종목은 비활성화 -> bulk 생성에서 제외되어야 한다
            symbols = (await client.get(f"/api/v1/watchlists/{watchlist_id}/symbols")).json()
            last_symbol_id = next(s["id"] for s in symbols if s["symbol_code"] == "207940")
            await client.patch(
                f"/api/v1/watchlists/{watchlist_id}/symbols/{last_symbol_id}", json={"enabled": False}
            )

            bulk_resp = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/create-strategy-versions",
                json={
                    "strategy_id": strategy_id,
                    "short_window": 5,
                    "long_window": 20,
                    "timeframe": "5m",
                    "quantity": 1,
                    "account_id": 230,
                    "status": "testing",
                },
            )
            assert bulk_resp.status_code == 200
            body = bulk_resp.json()
            assert body["strategy_id"] == strategy_id
            assert len(body["items"]) == 4
            assert all(item["created"] for item in body["items"])
            created_symbol_codes = {item["symbol_code"] for item in body["items"]}
            assert created_symbol_codes == {"005930", "000660", "035420", "051910"}

            versions_resp = await client.get(f"/api/v1/strategies/{strategy_id}/versions")
            versions = versions_resp.json()
            assert len(versions) == 4
            for v in versions:
                assert v["parameters"]["timeframe"] == "5m"
                assert v["parameters"]["account_id"] == 230
                assert v["parameters"]["auto_trade_enabled"] is False
                assert v["status"] == "testing"

            # 다시 호출하면 중복으로 처리되어 새로 생성되지 않아야 한다
            bulk_resp_2 = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/create-strategy-versions",
                json={"strategy_id": strategy_id, "account_id": 230},
            )
            assert bulk_resp_2.status_code == 200
            body_2 = bulk_resp_2.json()
            assert all(not item["created"] for item in body_2["items"])
            assert all(item["reason"] == "duplicate_symbol_version_exists" for item in body_2["items"])

            versions_after = await client.get(f"/api/v1/strategies/{strategy_id}/versions")
            assert len(versions_after.json()) == 4
    finally:
        app.dependency_overrides.clear()


async def test_bulk_create_rejects_auto_trade_enabled(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "Auto Trade Bulk"})
            strategy_id = strategy_resp.json()["id"]

            watchlist_resp = await client.post("/api/v1/watchlists", json={"name": "Auto Trade Watchlist"})
            watchlist_id = watchlist_resp.json()["id"]
            await client.post(f"/api/v1/watchlists/{watchlist_id}/symbols", json={"symbol_code": "005930"})

            resp = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/create-strategy-versions",
                json={
                    "strategy_id": strategy_id,
                    "account_id": 230,
                    "auto_trade_enabled": True,
                },
            )
            assert resp.status_code == 422

            versions = (await client.get(f"/api/v1/strategies/{strategy_id}/versions")).json()
            assert versions == []
    finally:
        app.dependency_overrides.clear()


async def test_bulk_create_unknown_watchlist_or_strategy_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_unknown_watchlist = await client.post(
                "/api/v1/watchlists/999999/create-strategy-versions",
                json={"strategy_id": 1},
            )
            assert resp_unknown_watchlist.status_code == 404

            watchlist_resp = await client.post("/api/v1/watchlists", json={"name": "전략 없음 테스트"})
            watchlist_id = watchlist_resp.json()["id"]

            resp_unknown_strategy = await client.post(
                f"/api/v1/watchlists/{watchlist_id}/create-strategy-versions",
                json={"strategy_id": 999999},
            )
            assert resp_unknown_strategy.status_code == 404
    finally:
        app.dependency_overrides.clear()
