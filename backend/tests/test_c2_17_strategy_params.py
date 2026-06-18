"""C-2.17: StrategyVersionParameters 확장 + strategy-types API 테스트."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.trading.strategy.schemas import StrategyVersionParameters


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# 1. moving_average_cross parameters 기존 validation 통과
# ---------------------------------------------------------------------------


def test_moving_average_cross_params_valid() -> None:
    params = StrategyVersionParameters(
        strategy_type="moving_average_cross",
        symbol_code="005930",
        short_window=5,
        long_window=20,
        quantity=1,
    )
    assert params.strategy_type == "moving_average_cross"
    assert params.short_window == 5
    assert params.long_window == 20
    assert params.auto_trade_enabled is False


def test_moving_average_cross_defaults_are_applied() -> None:
    params = StrategyVersionParameters(symbol_code="005930")
    assert params.strategy_type == "moving_average_cross"
    assert params.short_window == 5
    assert params.long_window == 20
    assert params.quantity == 1
    assert params.enabled is True
    assert params.auto_trade_enabled is False


# ---------------------------------------------------------------------------
# 2. volume_confirmed_ma_cross parameters validation 통과
# ---------------------------------------------------------------------------


def test_volume_confirmed_params_valid() -> None:
    params = StrategyVersionParameters(
        strategy_type="volume_confirmed_ma_cross",
        symbol_code="005930",
        short_window=5,
        long_window=20,
        volume_window=20,
        volume_multiplier=1.5,
        quantity=1,
    )
    assert params.strategy_type == "volume_confirmed_ma_cross"
    assert params.volume_window == 20
    assert params.volume_multiplier == 1.5


def test_volume_confirmed_defaults() -> None:
    params = StrategyVersionParameters(
        strategy_type="volume_confirmed_ma_cross",
        symbol_code="005930",
    )
    assert params.volume_window == 20
    assert params.volume_multiplier == 1.5


# ---------------------------------------------------------------------------
# 3. volume_multiplier <= 0 거부
# ---------------------------------------------------------------------------


def test_volume_multiplier_zero_rejected() -> None:
    with pytest.raises(Exception, match="volume_multiplier"):
        StrategyVersionParameters(
            symbol_code="005930",
            volume_multiplier=0,
        )


def test_volume_multiplier_negative_rejected() -> None:
    with pytest.raises(Exception, match="volume_multiplier"):
        StrategyVersionParameters(
            symbol_code="005930",
            volume_multiplier=-1.0,
        )


# ---------------------------------------------------------------------------
# 4. volume_window <= 0 거부
# ---------------------------------------------------------------------------


def test_volume_window_zero_rejected() -> None:
    with pytest.raises(Exception, match="volume_window"):
        StrategyVersionParameters(
            symbol_code="005930",
            volume_window=0,
        )


def test_volume_window_negative_rejected() -> None:
    with pytest.raises(Exception, match="volume_window"):
        StrategyVersionParameters(
            symbol_code="005930",
            volume_window=-5,
        )


# ---------------------------------------------------------------------------
# 5. long_window <= short_window 거부
# ---------------------------------------------------------------------------


def test_long_window_equal_to_short_window_rejected() -> None:
    with pytest.raises(Exception, match="long_window"):
        StrategyVersionParameters(
            symbol_code="005930",
            short_window=10,
            long_window=10,
        )


def test_long_window_less_than_short_window_rejected() -> None:
    with pytest.raises(Exception, match="long_window"):
        StrategyVersionParameters(
            symbol_code="005930",
            short_window=20,
            long_window=5,
        )


# ---------------------------------------------------------------------------
# 6. unknown strategy_type 처리 정책 — 스키마는 허용, runner는 skip
# ---------------------------------------------------------------------------


def test_unknown_strategy_type_accepted_by_schema() -> None:
    """unknown strategy_type은 schema에서 거부하지 않는다 (registry가 runtime에 skip)."""
    params = StrategyVersionParameters(
        strategy_type="future_strategy_v99",
        symbol_code="005930",
    )
    assert params.strategy_type == "future_strategy_v99"


# ---------------------------------------------------------------------------
# 7. API로 volume_confirmed 버전 생성
# ---------------------------------------------------------------------------


async def test_create_volume_confirmed_version_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "Volume Test"})
            assert strategy_resp.status_code == 200
            strategy_id = strategy_resp.json()["id"]

            version_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={
                    "parameters": {
                        "strategy_type": "volume_confirmed_ma_cross",
                        "symbol_code": "005930",
                        "short_window": 5,
                        "long_window": 20,
                        "volume_window": 20,
                        "volume_multiplier": 1.5,
                        "quantity": 1,
                    }
                },
            )
            assert version_resp.status_code == 200
            params = version_resp.json()["parameters"]
            assert params["strategy_type"] == "volume_confirmed_ma_cross"
            assert params["volume_window"] == 20
            assert params["volume_multiplier"] == 1.5
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 8. API로 volume parameters 수정
# ---------------------------------------------------------------------------


async def test_update_volume_parameters_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "Volume Update Test"})
            strategy_id = strategy_resp.json()["id"]

            version_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={
                    "parameters": {
                        "strategy_type": "volume_confirmed_ma_cross",
                        "symbol_code": "005930",
                    }
                },
            )
            version_id = version_resp.json()["id"]

            patch_resp = await client.patch(
                f"/api/v1/strategies/{strategy_id}/versions/{version_id}",
                json={
                    "parameters": {
                        "strategy_type": "volume_confirmed_ma_cross",
                        "symbol_code": "005930",
                        "short_window": 3,
                        "long_window": 15,
                        "volume_window": 30,
                        "volume_multiplier": 2.0,
                    }
                },
            )
            assert patch_resp.status_code == 200
            params = patch_resp.json()["parameters"]
            assert params["volume_window"] == 30
            assert params["volume_multiplier"] == 2.0
            assert params["short_window"] == 3
            assert params["long_window"] == 15
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 9. auto_trade_enabled 기본 false 유지
# ---------------------------------------------------------------------------


def test_auto_trade_enabled_default_is_false() -> None:
    params = StrategyVersionParameters(symbol_code="005930")
    assert params.auto_trade_enabled is False


async def test_auto_trade_false_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "AutoTrade Default"})
            strategy_id = strategy_resp.json()["id"]

            version_resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={
                    "parameters": {
                        "strategy_type": "volume_confirmed_ma_cross",
                        "symbol_code": "005930",
                    }
                },
            )
            params = version_resp.json()["parameters"]
            assert params["auto_trade_enabled"] is False
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 10. strategy-types API 응답 테스트
# ---------------------------------------------------------------------------


async def test_strategy_types_api_returns_known_types(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/strategies/strategy-types")
        assert resp.status_code == 200
        types = resp.json()
        type_keys = {t["strategy_type"] for t in types}
        assert "moving_average_cross" in type_keys
        assert "volume_confirmed_ma_cross" in type_keys
    finally:
        app.dependency_overrides.clear()


async def test_strategy_types_api_includes_volume_params(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/strategies/strategy-types")
        assert resp.status_code == 200
        volume_type = next(t for t in resp.json() if t["strategy_type"] == "volume_confirmed_ma_cross")
        param_names = {p["name"] for p in volume_type["parameters"]}
        assert "volume_window" in param_names
        assert "volume_multiplier" in param_names
    finally:
        app.dependency_overrides.clear()


async def test_strategy_types_api_includes_display_names(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/strategies/strategy-types")
        assert resp.status_code == 200
        for t in resp.json():
            assert "display_name" in t
            assert "display_name_ko" in t
            assert t["display_name"]
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# validation error cases via API
# ---------------------------------------------------------------------------


async def test_api_rejects_long_window_lte_short_window(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "Validation Test"})
            strategy_id = strategy_resp.json()["id"]

            resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={"parameters": {"symbol_code": "005930", "short_window": 20, "long_window": 10}},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_api_rejects_volume_multiplier_zero(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            strategy_resp = await client.post("/api/v1/strategies", json={"name": "Validation Test2"})
            strategy_id = strategy_resp.json()["id"]

            resp = await client.post(
                f"/api/v1/strategies/{strategy_id}/versions",
                json={"parameters": {"symbol_code": "005930", "volume_multiplier": 0}},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
