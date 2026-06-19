"""C-2.22 Market/Theme Context Foundation 테스트."""

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode, TradeSide
from app.domain.repositories.signal_log import SignalLogRepository
from app.main import app
from app.services.market_context_service import MarketContextService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_snapshot_create_and_list_with_market_filter(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            kr_resp = await client.post(
                "/api/v1/market-context/snapshots",
                json={
                    "market": "KR",
                    "time_bucket": "morning",
                    "index_trend": "up",
                    "foreign_flow": "net_buy",
                    "indices": {"kospi_change_pct": 0.8, "kosdaq_change_pct": 1.2},
                    "fx": {"usdkrw": 1380.5, "usdkrw_trend": "up"},
                },
            )
            assert kr_resp.status_code == 201
            body = kr_resp.json()
            assert body["market"] == "KR"
            assert body["indices"]["kospi_change_pct"] == 0.8
            assert body["captured_at"] is not None

            await client.post(
                "/api/v1/market-context/snapshots",
                json={"market": "US", "index_trend": "down"},
            )

            # market 필터
            kr_list = await client.get("/api/v1/market-context/snapshots", params={"market": "KR"})
            assert all(s["market"] == "KR" for s in kr_list.json())
            us_list = await client.get("/api/v1/market-context/snapshots", params={"market": "US"})
            assert all(s["market"] == "US" for s in us_list.json())
            assert len(us_list.json()) >= 1
    finally:
        app.dependency_overrides.clear()


async def test_theme_upsert_is_idempotent(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/api/v1/market-context/themes",
                json={"market": "KR", "code": "semiconductor", "name": "반도체"},
            )
            assert first.status_code == 201
            theme_id = first.json()["id"]

            # 같은 market+code면 새로 만들지 않고 기존 것을 반환
            second = await client.post(
                "/api/v1/market-context/themes",
                json={"market": "KR", "code": "semiconductor", "name": "반도체(중복)"},
            )
            assert second.json()["id"] == theme_id

            themes = await client.get("/api/v1/market-context/themes", params={"market": "KR"})
            assert sum(1 for t in themes.json() if t["code"] == "semiconductor") == 1
    finally:
        app.dependency_overrides.clear()


async def test_tag_symbol_and_list_symbol_themes(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            theme = await client.post(
                "/api/v1/market-context/themes",
                json={"market": "KR", "code": "ai_chip", "name": "AI 반도체"},
            )
            theme_id = theme.json()["id"]

            tag = await client.post(
                "/api/v1/market-context/themes/tag-symbol",
                json={"symbol_code": "005930", "theme_id": theme_id, "market": "KR"},
            )
            assert tag.json()["created"] is True

            # 중복 태깅은 created=false
            tag_dup = await client.post(
                "/api/v1/market-context/themes/tag-symbol",
                json={"symbol_code": "005930", "theme_id": theme_id, "market": "KR"},
            )
            assert tag_dup.json()["created"] is False

            symbol_themes = await client.get("/api/v1/market-context/symbols/005930/themes")
            codes = [t["code"] for t in symbol_themes.json()]
            assert "ai_chip" in codes
    finally:
        app.dependency_overrides.clear()


async def test_attach_snapshot_to_signal(db_session: AsyncSession) -> None:
    """snapshot을 signal_log에 연결하면 context_snapshot_id가 설정되어야 한다."""
    service = MarketContextService(db_session)
    snapshot = await service.create_snapshot(market=MarketCode.KR, time_bucket="morning")

    log = await SignalLogRepository(db_session).create(
        symbol_code="005930",
        signal_type=TradeSide.BUY,
        generated_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    ok = await service.attach_snapshot_to_signal(log.id, snapshot.id)
    assert ok is True

    refreshed = await SignalLogRepository(db_session).get(log.id)
    assert refreshed.context_snapshot_id == snapshot.id


async def test_attach_snapshot_to_missing_signal_returns_false(db_session: AsyncSession) -> None:
    service = MarketContextService(db_session)
    snapshot = await service.create_snapshot(market=MarketCode.KR)
    ok = await service.attach_snapshot_to_signal(999999, snapshot.id)
    assert ok is False
