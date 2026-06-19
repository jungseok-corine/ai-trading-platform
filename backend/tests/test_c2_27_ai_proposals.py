"""C-2.27 AI Proposal System 테스트."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.services.strategy_service import StrategyService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _make_strategy_with_version(session: AsyncSession) -> tuple[int, int]:
    svc = StrategyService(session)
    strategy = await svc.create_strategy("Proposal Target")
    version = await svc.create_version(
        strategy.id,
        parameters={
            "strategy_type": "volume_confirmed_ma_cross",
            "symbol_code": "005930",
            "volume_multiplier": 1.5,
        },
    )
    return strategy.id, version.id


async def test_create_proposal_and_diff(db_session: AsyncSession) -> None:
    strategy_id, base_version_id = await _make_strategy_with_version(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create = await client.post(
                "/api/v1/strategy-proposals",
                json={
                    "strategy_id": strategy_id,
                    "base_version_id": base_version_id,
                    "title": "volume_multiplier 1.5→2.0",
                    "rationale": "거래량 2배 이상에서 기대값이 높음",
                    "risk_notes": "기회 감소 가능",
                    "suggested_parameters": {
                        "strategy_type": "volume_confirmed_ma_cross",
                        "symbol_code": "005930",
                        "volume_multiplier": 2.0,
                    },
                },
            )
            assert create.status_code == 201
            assert create.json()["status"] == "pending"
            assert create.json()["source"] == "ai"
            proposal_id = create.json()["id"]

            detail = await client.get(f"/api/v1/strategy-proposals/{proposal_id}")
            diff = detail.json()["diff"]
            changed = {d["key"]: (d["before"], d["after"]) for d in diff}
            assert changed["volume_multiplier"] == [1.5, 2.0] or changed["volume_multiplier"] == (1.5, 2.0)
    finally:
        app.dependency_overrides.clear()


async def test_create_proposal_invalid_strategy_type_422(db_session: AsyncSession) -> None:
    strategy_id, _ = await _make_strategy_with_version(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/strategy-proposals",
                json={
                    "strategy_id": strategy_id,
                    "title": "bad",
                    "suggested_parameters": {"strategy_type": "nope"},
                },
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_approve_creates_draft_version_with_auto_trade_off(db_session: AsyncSession) -> None:
    """승인 시 새 DRAFT 버전이 생성되고, auto_trade_enabled는 강제로 False여야 한다."""
    strategy_id, base_version_id = await _make_strategy_with_version(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_id = (
                await client.post(
                    "/api/v1/strategy-proposals",
                    json={
                        "strategy_id": strategy_id,
                        "base_version_id": base_version_id,
                        "title": "강화안",
                        # AI가 auto_trade를 켜려 시도해도 무시되어야 한다
                        "suggested_parameters": {
                            "strategy_type": "volume_confirmed_ma_cross",
                            "symbol_code": "005930",
                            "volume_multiplier": 2.0,
                            "auto_trade_enabled": True,
                            "account_id": 1,
                        },
                    },
                )
            ).json()["id"]

            approve = await client.post(
                f"/api/v1/strategy-proposals/{proposal_id}/approve",
                json={"reviewed_by": "ojung"},
            )
            assert approve.status_code == 200
            new_version_id = approve.json()["created_version_id"]
            assert approve.json()["proposal"]["status"] == "approved"

            # 생성된 버전 확인: DRAFT + auto_trade_enabled=False (안전장치)
            versions = (
                await client.get(f"/api/v1/strategies/{strategy_id}/versions")
            ).json()
            new_v = next(v for v in versions if v["id"] == new_version_id)
            assert new_v["status"] == "draft"
            assert new_v["parameters"]["auto_trade_enabled"] is False
            assert new_v["parameters"]["volume_multiplier"] == 2.0
    finally:
        app.dependency_overrides.clear()


async def test_cannot_review_twice(db_session: AsyncSession) -> None:
    strategy_id, _ = await _make_strategy_with_version(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_id = (
                await client.post(
                    "/api/v1/strategy-proposals",
                    json={
                        "strategy_id": strategy_id,
                        "title": "once",
                        "suggested_parameters": {
                            "strategy_type": "moving_average_cross",
                            "symbol_code": "005930",
                        },
                    },
                )
            ).json()["id"]

            r1 = await client.post(f"/api/v1/strategy-proposals/{proposal_id}/reject", json={})
            assert r1.status_code == 200
            assert r1.json()["status"] == "rejected"

            # 이미 거절된 제안을 다시 승인 시도 → 409
            r2 = await client.post(f"/api/v1/strategy-proposals/{proposal_id}/approve", json={})
            assert r2.status_code == 409
    finally:
        app.dependency_overrides.clear()


async def test_list_proposals_filter_by_status(db_session: AsyncSession) -> None:
    strategy_id, _ = await _make_strategy_with_version(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for i in range(2):
                await client.post(
                    "/api/v1/strategy-proposals",
                    json={
                        "strategy_id": strategy_id,
                        "title": f"p{i}",
                        "suggested_parameters": {
                            "strategy_type": "moving_average_cross",
                            "symbol_code": "005930",
                        },
                    },
                )
            pending = await client.get(
                "/api/v1/strategy-proposals", params={"status": "pending"}
            )
            assert len(pending.json()) == 2
            approved = await client.get(
                "/api/v1/strategy-proposals", params={"status": "approved"}
            )
            assert approved.json() == []
    finally:
        app.dependency_overrides.clear()
