"""C-2.28 News/US Market Context Pipeline 테스트."""

from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_news_create_and_filter(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/v1/news-events",
                json={
                    "headline": "삼성전자 HBM 공급 확대",
                    "published_at": "2026-06-19T09:00:00+09:00",
                    "market": "KR",
                    "symbol_code": "005930",
                    "sentiment": "positive",
                    "themes": ["semiconductor", "ai_chip"],
                },
            )
            assert r.status_code == 201
            assert r.json()["sentiment"] == "positive"
            assert "semiconductor" in r.json()["themes"]

            # 시장 단위 뉴스 (symbol 없음)
            await client.post(
                "/api/v1/news-events",
                json={
                    "headline": "코스피 외국인 순매수 전환",
                    "published_at": "2026-06-19T08:30:00+09:00",
                    "market": "KR",
                },
            )

            by_symbol = await client.get(
                "/api/v1/news-events", params={"symbol_code": "005930"}
            )
            assert all(n["symbol_code"] == "005930" for n in by_symbol.json())
            assert len(by_symbol.json()) == 1
    finally:
        app.dependency_overrides.clear()


async def test_invalid_sentiment_rejected(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/v1/news-events",
                json={
                    "headline": "x",
                    "published_at": "2026-06-19T09:00:00+09:00",
                    "sentiment": "bullish",  # 허용값 아님
                },
            )
            assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_us_snapshot_upsert_idempotent_and_latest(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.put(
                "/api/v1/us-market-snapshots",
                json={
                    "session_date": "2026-06-18",
                    "nasdaq_change_pct": "1.2",
                    "sox_change_pct": "2.1",
                },
            )
            assert first.status_code == 200
            snapshot_id = first.json()["id"]
            assert Decimal(first.json()["nasdaq_change_pct"]) == Decimal("1.2")

            # 같은 날짜 PUT → 갱신 (새 row 안 생김)
            second = await client.put(
                "/api/v1/us-market-snapshots",
                json={"session_date": "2026-06-18", "nasdaq_change_pct": "1.5"},
            )
            assert second.json()["id"] == snapshot_id
            assert Decimal(second.json()["nasdaq_change_pct"]) == Decimal("1.5")

            # 더 최근 날짜
            await client.put(
                "/api/v1/us-market-snapshots",
                json={"session_date": "2026-06-19", "nasdaq_change_pct": "0.3"},
            )
            latest = await client.get("/api/v1/us-market-snapshots/latest")
            assert latest.json()["session_date"] == "2026-06-19"

            all_list = await client.get("/api/v1/us-market-snapshots")
            assert len(all_list.json()) == 2  # 2026-06-18, 2026-06-19
    finally:
        app.dependency_overrides.clear()


async def test_latest_us_snapshot_404_when_empty(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/v1/us-market-snapshots/latest")
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
