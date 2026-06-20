"""C-2.61 공시 알림 (관제탑 노출 + 알림 목록) 테스트."""

from datetime import datetime
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.domain.repositories.news_context import NewsEventRepository
from app.main import app
from app.services.disclosure_alert_service import DisclosureAlertService
from app.services.research_status_service import ResearchStatusService

KST = ZoneInfo("Asia/Seoul")


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _add_dart(session, symbol, headline, category, score, when=None):
    await NewsEventRepository(session).create(
        market=MarketCode.KR, symbol_code=symbol, source="dart", headline=headline,
        url=f"https://dart.fss.or.kr/x?{headline}",
        published_at=when or datetime.now(KST),
        raw_payload={"category": category, "materiality": score, "corp_name": symbol},
    )
    await session.commit()


async def test_recent_alerts_filters_and_sorts(db_session: AsyncSession) -> None:
    await _add_dart(db_session, "005930", "자기주식취득 결정", "high", 0.9)
    await _add_dart(db_session, "000660", "신제품 출시", "medium", 0.6)
    await _add_dart(db_session, "005930", "낮은중요도건", "low", 0.3)  # min_score 미달 제외

    alerts = await DisclosureAlertService(db_session).recent(min_score=0.5)
    assert len(alerts) == 2
    headlines = {a["headline"] for a in alerts}
    assert "낮은중요도건" not in headlines
    assert alerts[0]["category"] in ("high", "medium")


async def test_status_includes_disclosure_alerts(db_session: AsyncSession) -> None:
    await _add_dart(db_session, "005930", "단일판매ㆍ공급계약체결", "high", 0.9)
    status = await ResearchStatusService(db_session).status()
    assert status.disclosure_alerts == 1


async def test_alerts_via_api(db_session: AsyncSession) -> None:
    await _add_dart(db_session, "005930", "유상증자 결정", "high", 0.9)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/dart/alerts")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["category"] == "high"

            status = await client.get("/api/v1/research-status")
            assert status.json()["disclosure_alerts"] == 1
    finally:
        app.dependency_overrides.clear()
