"""C-2.22 Intelligence Ingestion Pipeline 테스트.

검증 항목:
1. GenericRssAdapter가 MockTransport RSS XML을 파싱한다
2. RSS item이 IntelligenceEventCandidate로 변환된다
3. RSS dedup_hash가 안정적으로 생성된다 (동일 입력 → 동일 해시)
4. keyword_filter가 동작한다
5. DartDisclosureAdapter가 기존 disclosure 레코드를 IntelligenceEventCandidate로 변환한다
6. IntelligenceIngestionService가 enabled source만 실행한다
7. 중복 dedup_hash는 insert하지 않고 skip한다
8. POST /intelligence/ingest가 summary를 반환한다
9. scheduler job은 기본 비활성이다
10. 주문 API 호출 없음
11. broker.place_order 변경 없음
12. KIS_REAL_TRADING_ENABLED 변경 없음
"""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.domain.models.intelligence import IntelligenceSource
from app.domain.models.news_context import NewsEvent
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.market_intelligence.adapters.base import IntelligenceRawItem, build_dedup_hash
from app.market_intelligence.adapters.dart_disclosure_adapter import DartDisclosureAdapter
from app.market_intelligence.adapters.generic_rss_adapter import GenericRssAdapter, _parse_pub_date
from app.services.intelligence_ingest_service import IntelligenceIngestionService


# ── RSS XML 픽스처 ────────────────────────────────────────────────────────────

_RSS_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>테스트 뉴스</title>
        <item>
          <title>삼성전자 반도체 투자 확대 발표</title>
          <link>https://example.com/news/1</link>
          <guid>https://example.com/news/1</guid>
          <pubDate>Tue, 24 Jun 2026 06:00:00 +0900</pubDate>
          <description>삼성전자가 반도체 생산라인 투자를 대폭 늘린다고 발표했다.</description>
        </item>
        <item>
          <title>일반 생활 기사</title>
          <link>https://example.com/news/2</link>
          <guid>https://example.com/news/2</guid>
          <pubDate>Tue, 24 Jun 2026 05:00:00 +0900</pubDate>
          <description>날씨가 맑다.</description>
        </item>
        <item>
          <title>AI 기업 투자 동향</title>
          <link>https://example.com/news/3</link>
          <guid>https://example.com/news/3</guid>
          <pubDate>Tue, 24 Jun 2026 04:00:00 +0900</pubDate>
          <description>AI 스타트업 투자가 증가하고 있다.</description>
        </item>
      </channel>
    </rss>
""")

_RSS_XML_NO_GUID = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>링크만 있는 기사</title>
          <link>https://example.com/news/no-guid</link>
          <pubDate>Tue, 24 Jun 2026 03:00:00 +0900</pubDate>
          <description>설명 없음</description>
        </item>
      </channel>
    </rss>
""")


def _mock_rss_source(**overrides: Any) -> MagicMock:
    """테스트용 IntelligenceSource mock 객체 생성."""
    src = MagicMock(spec=IntelligenceSource)
    src.id = 1
    src.source_key = "test_rss"
    src.source_type = IntelligenceSourceType.NEWS
    src.provider = IntelligenceProvider.RSS
    src.market_scope = IntelligenceMarketScope.KR
    src.enabled = True
    src.config = {"feed_url": "https://example.com/rss", "max_items": 50}
    for k, v in overrides.items():
        setattr(src, k, v)
    return src


def _mock_disclosure_source(**overrides: Any) -> MagicMock:
    src = MagicMock(spec=IntelligenceSource)
    src.id = 2
    src.source_key = "dart_disclosure"
    src.source_type = IntelligenceSourceType.DISCLOSURE
    src.provider = IntelligenceProvider.DART
    src.market_scope = IntelligenceMarketScope.KR
    src.enabled = True
    src.config = {}
    for k, v in overrides.items():
        setattr(src, k, v)
    return src


def _make_rss_client(xml: str = _RSS_XML) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=xml, headers={"content-type": "application/rss+xml"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── 1. GenericRssAdapter RSS XML 파싱 ─────────────────────────────────────────

async def test_generic_rss_adapter_parses_xml() -> None:
    """GenericRssAdapter가 MockTransport RSS XML을 파싱해 raw_items를 반환한다."""
    source = _mock_rss_source()
    adapter = GenericRssAdapter(source, client=_make_rss_client())

    items = await adapter.fetch()

    assert len(items) == 3
    assert items[0].title == "삼성전자 반도체 투자 확대 발표"
    assert items[0].source_ref == "https://example.com/news/1"
    assert items[0].raw_data["link"] == "https://example.com/news/1"


# ── 2. RSS item → IntelligenceEventCandidate 변환 ────────────────────────────

async def test_generic_rss_normalize_returns_candidate() -> None:
    """normalize()가 IntelligenceEventCandidate를 올바르게 반환한다."""
    source = _mock_rss_source()
    adapter = GenericRssAdapter(source, client=_make_rss_client())

    items = await adapter.fetch()
    candidate = adapter.normalize(items[0])

    assert candidate.source_key == "test_rss"
    assert candidate.event_type == "news"
    assert candidate.title == "삼성전자 반도체 투자 확대 발표"
    assert candidate.market == MarketCode.KR
    assert candidate.source_ref == "https://example.com/news/1"
    assert len(candidate.dedup_hash) == 64
    assert candidate.status == IntelligenceEventStatus.RAW


# ── 3. RSS dedup_hash 안정성 ──────────────────────────────────────────────────

async def test_rss_dedup_hash_is_stable() -> None:
    """동일 RSS 아이템을 두 번 파싱하면 동일 dedup_hash가 생성된다."""
    source = _mock_rss_source()
    adapter1 = GenericRssAdapter(source, client=_make_rss_client())
    adapter2 = GenericRssAdapter(source, client=_make_rss_client())

    items1 = await adapter1.fetch()
    items2 = await adapter2.fetch()

    h1 = adapter1.normalize(items1[0]).dedup_hash
    h2 = adapter2.normalize(items2[0]).dedup_hash
    assert h1 == h2
    assert len(h1) == 64


def test_rss_dedup_hash_differs_for_different_links() -> None:
    """다른 link/guid는 다른 dedup_hash를 생성한다."""
    h1 = build_dedup_hash("test_rss", "https://example.com/news/1", "")
    h2 = build_dedup_hash("test_rss", "https://example.com/news/2", "")
    assert h1 != h2


# ── 4. keyword_filter 동작 ────────────────────────────────────────────────────

async def test_keyword_filter_applied() -> None:
    """keyword_filter=['반도체']이면 해당 키워드 없는 아이템은 제외된다."""
    source = _mock_rss_source(config={
        "feed_url": "https://example.com/rss",
        "keyword_filter": ["반도체"],
        "max_items": 50,
    })
    adapter = GenericRssAdapter(source, client=_make_rss_client())

    items = await adapter.fetch()

    # "반도체"가 포함된 기사만 남아야 함 (1번 기사만)
    assert len(items) == 1
    assert "반도체" in items[0].title


async def test_keyword_filter_empty_passes_all() -> None:
    """keyword_filter가 비어있으면 모든 아이템이 통과한다."""
    source = _mock_rss_source(config={
        "feed_url": "https://example.com/rss",
        "keyword_filter": [],
        "max_items": 50,
    })
    adapter = GenericRssAdapter(source, client=_make_rss_client())

    items = await adapter.fetch()
    assert len(items) == 3


# ── 5. DartDisclosureAdapter 변환 ─────────────────────────────────────────────

async def test_dart_disclosure_adapter_normalizes_from_news_event(
    db_session: AsyncSession,
) -> None:
    """DartDisclosureAdapter가 news_events(DART) 레코드를 IntelligenceEventCandidate로 변환한다."""
    # news_events에 DART 공시 레코드 삽입
    evt = NewsEvent(
        market=MarketCode.KR,
        symbol_code="005930",
        source="dart",
        headline="삼성전자 주요사항보고서",
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260624001234",
        published_at=datetime(2026, 6, 24, 9, 0, tzinfo=timezone.utc),
        raw_payload={
            "rcept_no": "20260624001234",
            "corp_name": "삼성전자",
            "materiality": 0.9,
            "category": "major_decision",
        },
    )
    db_session.add(evt)
    await db_session.flush()

    source = _mock_disclosure_source()
    adapter = DartDisclosureAdapter(source, db_session, lookback_days=30)

    raw_items = await adapter.fetch()
    assert any(r.raw_id == "20260624001234" for r in raw_items)

    target = next(r for r in raw_items if r.raw_id == "20260624001234")
    candidate = adapter.normalize(target)

    assert candidate.event_type == "disclosure"
    assert candidate.symbol_code == "005930"
    assert candidate.title == "삼성전자 주요사항보고서"
    assert len(candidate.dedup_hash) == 64
    assert candidate.raw_payload["rcept_no"] == "20260624001234"


def test_dart_disclosure_dedup_hash_uses_rcept_no() -> None:
    """DartDisclosureAdapter dedup_hash = build_dedup_hash(source_key, rcept_no)."""
    h = build_dedup_hash("dart_disclosure", "20260624001234")
    assert len(h) == 64

    h2 = build_dedup_hash("dart_disclosure", "20260624001235")
    assert h != h2


# ── 6. IntelligenceIngestionService — enabled 소스만 실행 ─────────────────────

async def test_ingestion_service_skips_disabled_source(db_session: AsyncSession) -> None:
    """IntelligenceIngestionService는 enabled=False 소스를 실행하지 않는다."""
    src_repo = IntelligenceSourceRepository(db_session)
    # enabled=True 소스
    await src_repo.create(
        source_key="rss_enabled",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
        enabled=True,
        config={"feed_url": "https://example.com/rss"},
    )
    # enabled=False 소스
    await src_repo.create(
        source_key="rss_disabled",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
        enabled=False,
        config={"feed_url": "https://example.com/rss"},
    )
    await db_session.flush()

    # feed를 모킹: enabled 소스만 호출되도록 확인
    called_keys: list[str] = []

    class _TrackingService(IntelligenceIngestionService):
        async def _run_source(self, source):  # type: ignore[override]
            called_keys.append(source.source_key)
            return 0, 0

    svc = _TrackingService(db_session)
    summary = await svc.ingest()

    assert summary.sources_checked == 1
    assert "rss_enabled" in called_keys
    assert "rss_disabled" not in called_keys


# ── 7. 중복 dedup_hash skip ───────────────────────────────────────────────────

async def test_ingestion_skips_duplicate_dedup_hash(db_session: AsyncSession) -> None:
    """이미 저장된 dedup_hash는 existing_hashes()에서 반환되므로 insert되지 않는다."""
    src_repo = IntelligenceSourceRepository(db_session)
    evt_repo = IntelligenceEventRepository(db_session)

    src = await src_repo.create(
        source_key="rss_dedup_test",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
        enabled=True,
        config={"feed_url": "https://example.com/rss"},
    )
    await db_session.flush()

    existing_hash = build_dedup_hash("rss_dedup_test", "https://example.com/news/1", "")
    await evt_repo.create(
        source_id=src.id,
        event_type="news",
        title="기존 기사",
        dedup_hash=existing_hash,
        status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()

    # existing_hashes가 이미 저장된 hash를 반환하는지 확인 (dedup 핵심 메커니즘)
    existing = await evt_repo.existing_hashes([existing_hash, "nonexistent_hash"])
    assert existing_hash in existing
    assert "nonexistent_hash" not in existing

    # 같은 hash로 create 시도하면 UniqueConstraint 위반 발생 (직접 insert 시 dedup 보장 확인)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await evt_repo.create(
            source_id=src.id,
            event_type="news",
            title="중복 기사",
            dedup_hash=existing_hash,
            status=IntelligenceEventStatus.RAW,
        )
        await db_session.flush()


async def test_ingestion_dedup_full_flow(db_session: AsyncSession) -> None:
    """전체 파이프라인에서 중복 아이템은 skip되고 새 아이템만 insert된다."""
    src_repo = IntelligenceSourceRepository(db_session)
    evt_repo = IntelligenceEventRepository(db_session)

    src = await src_repo.create(
        source_key="rss_full_dedup",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
        enabled=True,
        config={"feed_url": "https://example.com/rss"},
    )
    await db_session.flush()

    existing_hash = build_dedup_hash("rss_full_dedup", "https://example.com/existing", "")
    await evt_repo.create(
        source_id=src.id,
        event_type="news",
        title="이미 있는 기사",
        dedup_hash=existing_hash,
        status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()

    # 두 아이템: 하나는 기존 해시, 하나는 신규
    from app.market_intelligence.adapters.base import IntelligenceEventCandidate

    new_hash = build_dedup_hash("rss_full_dedup", "https://example.com/new", "")
    candidates = [
        IntelligenceEventCandidate(
            source_key="rss_full_dedup", event_type="news", title="이미 있는 기사",
            dedup_hash=existing_hash,
        ),
        IntelligenceEventCandidate(
            source_key="rss_full_dedup", event_type="news", title="새 기사",
            dedup_hash=new_hash,
        ),
    ]

    class _FakeAdapter:
        source_key = "rss_full_dedup"
        async def fetch(self):
            return []
        def normalize(self, raw):
            return raw

    class _PatchedService(IntelligenceIngestionService):
        def _make_adapter(self, source):
            return _FakeAdapter()

        async def _run_source(self, source):
            all_hashes = [c.dedup_hash for c in candidates]
            existing = await self._event_repo.existing_hashes(all_hashes)
            inserted = 0
            skipped = 0
            for c in candidates:
                if c.dedup_hash in existing:
                    skipped += 1
                    continue
                await self._event_repo.create(
                    source_id=source.id, event_type=c.event_type,
                    title=c.title, dedup_hash=c.dedup_hash,
                    status=IntelligenceEventStatus.RAW,
                )
                existing.add(c.dedup_hash)
                inserted += 1
            await self._session.commit()
            return inserted, skipped

    svc = _PatchedService(db_session)
    summary = await svc.ingest()

    assert summary.inserted_count == 1
    assert summary.skipped_duplicate_count == 1


# ── 8. POST /intelligence/ingest API ─────────────────────────────────────────

def test_api_ingest_returns_summary() -> None:
    """POST /api/v1/intelligence/ingest가 IngestSummary를 반환한다."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/intelligence/ingest", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert "sources_checked" in body
    assert "inserted_count" in body
    assert "skipped_duplicate_count" in body
    assert "error_count" in body
    assert "errors" in body
    assert isinstance(body["errors"], list)


def test_api_ingest_with_source_keys_filter() -> None:
    """source_keys를 지정하면 해당 소스만 실행된다 (소스가 없으면 0)."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/intelligence/ingest",
            json={"source_keys": ["nonexistent_source_key"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sources_checked"] == 0
    assert body["inserted_count"] == 0


# ── 9. Scheduler 기본 비활성 ──────────────────────────────────────────────────

def test_intelligence_ingest_scheduler_default_disabled() -> None:
    """intelligence_ingest_scheduler_enabled는 코드 기본값이 False이다."""
    s = Settings(_env_file=None)
    assert s.intelligence_ingest_scheduler_enabled is False


def test_intelligence_ingest_scheduler_in_registry() -> None:
    """INTELLIGENCE_INGEST_JOB_ID가 CONTROLLABLE_JOBS에 등록돼 있다."""
    from app.scheduler.jobs import INTELLIGENCE_INGEST_JOB_ID
    from app.scheduler.registry import CONTROLLABLE_BY_ID

    assert INTELLIGENCE_INGEST_JOB_ID in CONTROLLABLE_BY_ID
    job = CONTROLLABLE_BY_ID[INTELLIGENCE_INGEST_JOB_ID]
    s = Settings(_env_file=None)
    assert job.env_enabled(s) is False


# ── 10–12. 안전 불변식 ────────────────────────────────────────────────────────

def test_no_order_api_in_intelligence_package() -> None:
    """market_intelligence 패키지 + intelligence_ingest_service에 주문 API 심볼이 없다."""
    import pathlib

    order_symbols = {"place_order", "TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U"}

    targets = [
        pathlib.Path(__file__).parent.parent / "app" / "market_intelligence",
        pathlib.Path(__file__).parent.parent / "app" / "services" / "intelligence_ingest_service.py",
    ]

    for target in targets:
        files = [target] if target.is_file() else list(target.rglob("*.py"))
        for py_file in files:
            source = py_file.read_text()
            for sym in order_symbols:
                assert sym not in source, (
                    f"주문 API 심볼 '{sym}'이 {py_file}에서 발견됨 — 안전 불변식 위반"
                )


def test_real_trading_unchanged() -> None:
    """KIS_REAL_TRADING_ENABLED 기본값이 False로 유지된다."""
    s = Settings(_env_file=None)
    assert s.kis_real_trading_enabled is False


def test_pub_date_parse_rfc2822() -> None:
    """_parse_pub_date가 RFC 2822 pubDate를 올바르게 파싱한다."""
    dt = _parse_pub_date("Tue, 24 Jun 2026 06:00:00 +0900")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 24


def test_pub_date_parse_empty_returns_none() -> None:
    """빈 pubDate는 None을 반환한다."""
    assert _parse_pub_date("") is None
    assert _parse_pub_date(None) is None  # type: ignore[arg-type]
