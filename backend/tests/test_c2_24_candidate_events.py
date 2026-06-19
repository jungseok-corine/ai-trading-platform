"""C-2.24 Candidate Event System 테스트."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _make_rule_version(client: AsyncClient, conditions: list[dict]) -> tuple[int, int]:
    rule_id = (
        await client.post("/api/v1/scanner-rules", json={"name": "scan test", "market": "KR"})
    ).json()["id"]
    version_id = (
        await client.post(
            f"/api/v1/scanner-rules/{rule_id}/versions",
            json={"conditions": conditions, "status": "testing"},
        )
    ).json()["id"]
    return rule_id, version_id


async def test_scan_records_only_matching_symbols(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rule_id, version_id = await _make_rule_version(
                client,
                [
                    {"type": "volume_spike", "params": {"multiplier": 2.0}},
                    {"type": "price_change_pct", "params": {"min_pct": 5.0}},
                ],
            )

            scan = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}/scan",
                json={
                    "symbol_facts": {
                        "005930": {"volume_ratio": 2.4, "price_change_pct": 6.1},  # match
                        "000660": {"volume_ratio": 1.1, "price_change_pct": 6.1},  # volume 미충족
                        "035720": {"volume_ratio": 3.0, "price_change_pct": 2.0},  # 상승률 미충족
                    }
                },
            )
            assert scan.status_code == 201
            body = scan.json()
            assert body["scanned"] == 3
            assert body["matched"] == 1
            assert len(body["candidates"]) == 1

            cand = body["candidates"][0]
            assert cand["symbol_code"] == "005930"
            assert cand["market"] == "KR"
            assert cand["score"] == 100
            assert set(cand["matched_conditions"]) == {"volume_spike", "price_change_pct"}
            # facts 스냅샷 보존
            assert cand["facts"]["volume_ratio"] == 2.4
    finally:
        app.dependency_overrides.clear()


async def test_list_candidates_with_filters(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rule_id, version_id = await _make_rule_version(
                client, [{"type": "turnover_rank", "params": {"max_rank": 100}}]
            )
            await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}/scan",
                json={
                    "symbol_facts": {
                        "005930": {"turnover_rank": 23},
                        "000660": {"turnover_rank": 80},
                    }
                },
            )

            by_version = await client.get(
                "/api/v1/candidates",
                params={"scanner_rule_version_id": version_id},
            )
            assert by_version.status_code == 200
            assert len(by_version.json()) == 2

            by_symbol = await client.get("/api/v1/candidates", params={"symbol_code": "005930"})
            assert all(c["symbol_code"] == "005930" for c in by_symbol.json())
            assert len(by_symbol.json()) >= 1
    finally:
        app.dependency_overrides.clear()


async def test_scan_links_context_snapshot(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            snapshot_id = (
                await client.post(
                    "/api/v1/market-context/snapshots",
                    json={"market": "KR", "time_bucket": "morning"},
                )
            ).json()["id"]

            rule_id, version_id = await _make_rule_version(
                client, [{"type": "volume_spike", "params": {"multiplier": 2.0}}]
            )
            scan = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}/scan",
                json={
                    "symbol_facts": {"005930": {"volume_ratio": 2.5}},
                    "context_snapshot_id": snapshot_id,
                },
            )
            assert scan.json()["candidates"][0]["context_snapshot_id"] == snapshot_id
    finally:
        app.dependency_overrides.clear()


async def test_scan_unknown_version_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/scanner-rules/1/versions/999999/scan",
                json={"symbol_facts": {"005930": {"volume_ratio": 2.5}}},
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
