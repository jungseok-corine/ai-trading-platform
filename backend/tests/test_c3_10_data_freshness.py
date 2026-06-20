"""C-3.10 데이터 신선도 점검 테스트."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.news_context import NewsEvent
from app.services.data_freshness_service import DataFreshnessService
from app.services.operations_digest_service import OperationsDigestService


async def test_no_data_is_not_stale(db_session: AsyncSession) -> None:
    out = await DataFreshnessService(db_session).status()
    assert out["stale_count"] == 0
    # 데이터 없는 소스는 present=False, stale=False
    for s in out["sources"]:
        assert s["present"] is False
        assert s["stale"] is False


async def test_recent_news_is_fresh(db_session: AsyncSession) -> None:
    db_session.add(NewsEvent(
        market=MarketCode.KR, source="manual", headline="최근 뉴스",
        published_at=datetime.now(timezone.utc),
    ))
    await db_session.flush()
    out = await DataFreshnessService(db_session).status()
    news = next(s for s in out["sources"] if s["source"] == "news")
    assert news["present"] is True
    assert news["stale"] is False
    assert news["age_hours"] is not None


async def test_old_dart_is_stale_and_in_digest(db_session: AsyncSession) -> None:
    old = NewsEvent(
        market=MarketCode.KR, source="dart", headline="오래된 공시",
        published_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old)
    await db_session.flush()
    # created_at을 강제로 과거로(임계 72h 초과)
    old.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db_session.flush()

    out = await DataFreshnessService(db_session).status()
    dart = next(s for s in out["sources"] if s["source"] == "dart")
    assert dart["stale"] is True
    assert "dart" in out["stale_sources"]

    # 다이제스트에도 신선도 경보가 잡힌다
    digest = await OperationsDigestService(db_session).build()
    assert any("데이터 신선도" in a["text"] for a in digest["alerts"])
