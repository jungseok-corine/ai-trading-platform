"""C-2.25 Strategy Assignment Rules 테스트."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _make_candidate(client: AsyncClient) -> tuple[int, int]:
    """scanner rule → version → scan으로 후보 1건을 만들고 (scanner_rule_id, candidate_id) 반환."""
    rule_id = (
        await client.post("/api/v1/scanner-rules", json={"name": "vol spike", "market": "KR"})
    ).json()["id"]
    version_id = (
        await client.post(
            f"/api/v1/scanner-rules/{rule_id}/versions",
            json={
                "conditions": [{"type": "volume_spike", "params": {"multiplier": 2.0}}],
                "status": "testing",
            },
        )
    ).json()["id"]
    scan = await client.post(
        f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}/scan",
        json={"symbol_facts": {"005930": {"volume_ratio": 2.5}}},
    )
    candidate_id = scan.json()["candidates"][0]["id"]
    return rule_id, candidate_id


async def test_create_assignment_rule_and_invalid_type(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.post(
                "/api/v1/assignment-rules",
                json={
                    "name": "거래량급증→volume전략",
                    "strategy_type": "volume_confirmed_ma_cross",
                    "market": "KR",
                    "default_parameters": {"volume_multiplier": 2.0},
                    "priority": 10,
                },
            )
            assert ok.status_code == 201
            assert ok.json()["strategy_type"] == "volume_confirmed_ma_cross"
            assert ok.json()["enabled"] is True

            bad = await client.post(
                "/api/v1/assignment-rules",
                json={"name": "bad", "strategy_type": "does_not_exist"},
            )
            assert bad.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_assign_candidate_records_log(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            scanner_rule_id, candidate_id = await _make_candidate(client)

            await client.post(
                "/api/v1/assignment-rules",
                json={
                    "name": "scanner전용",
                    "strategy_type": "volume_confirmed_ma_cross",
                    "market": "KR",
                    "scanner_rule_id": scanner_rule_id,
                    "default_parameters": {"volume_multiplier": 1.5},
                },
            )

            assign = await client.post(f"/api/v1/candidates/{candidate_id}/assign")
            assert assign.status_code == 200
            log = assign.json()
            assert log["strategy_type"] == "volume_confirmed_ma_cross"
            assert log["symbol_code"] == "005930"
            # default_parameters + strategy_type + symbol_code 병합 확인
            assert log["assigned_parameters"]["volume_multiplier"] == 1.5
            assert log["assigned_parameters"]["strategy_type"] == "volume_confirmed_ma_cross"
            assert log["assigned_parameters"]["symbol_code"] == "005930"

            logs = await client.get(
                "/api/v1/assignment-logs", params={"candidate_event_id": candidate_id}
            )
            assert len(logs.json()) == 1
    finally:
        app.dependency_overrides.clear()


async def test_scanner_specific_rule_beats_fallback(db_session: AsyncSession) -> None:
    """동일 priority면 scanner_rule_id가 지정된 규칙이 fallback(NULL)보다 우선한다."""
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            scanner_rule_id, candidate_id = await _make_candidate(client)

            # fallback (scanner_rule_id 없음)
            await client.post(
                "/api/v1/assignment-rules",
                json={
                    "name": "fallback",
                    "strategy_type": "moving_average_cross",
                    "market": "KR",
                    "priority": 0,
                },
            )
            # scanner 전용
            await client.post(
                "/api/v1/assignment-rules",
                json={
                    "name": "specific",
                    "strategy_type": "flow_confirmed_volume_ma_cross",
                    "market": "KR",
                    "scanner_rule_id": scanner_rule_id,
                    "priority": 0,
                },
            )

            assign = await client.post(f"/api/v1/candidates/{candidate_id}/assign")
            assert assign.status_code == 200
            assert assign.json()["strategy_type"] == "flow_confirmed_volume_ma_cross"
    finally:
        app.dependency_overrides.clear()


async def test_assign_no_matching_rule_returns_204(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            _, candidate_id = await _make_candidate(client)
            # US 마켓 규칙만 존재 → KR 후보에 매칭 안 됨
            await client.post(
                "/api/v1/assignment-rules",
                json={
                    "name": "us only",
                    "strategy_type": "moving_average_cross",
                    "market": "US",
                },
            )
            assign = await client.post(f"/api/v1/candidates/{candidate_id}/assign")
            assert assign.status_code == 204
    finally:
        app.dependency_overrides.clear()


async def test_assign_unknown_candidate_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/candidates/999999/assign")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
