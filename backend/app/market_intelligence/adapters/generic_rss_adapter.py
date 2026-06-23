"""Generic RSS 피드 수집 어댑터 (C-2.22).

IntelligenceSource.config JSONB에서 feed_url / keyword_filter / max_items를 읽어
임의 RSS 2.0 피드를 수집한다. 특정 언론사 URL을 하드코딩하지 않는다.

설정 예시:
  {
    "feed_url": "https://example.com/rss",
    "keyword_filter": ["반도체", "AI", "금리"],
    "max_items": 50
  }
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.domain.models.enums import (
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.domain.models.intelligence import IntelligenceSource
from app.market_intelligence.adapters.base import (
    AdapterFetchError,
    IntelligenceAdapter,
    IntelligenceEventCandidate,
    IntelligenceRawItem,
    build_dedup_hash,
)

_SCOPE_TO_MARKET: dict[IntelligenceMarketScope, MarketCode | None] = {
    IntelligenceMarketScope.KR: MarketCode.KR,
    IntelligenceMarketScope.US: MarketCode.US,
    IntelligenceMarketScope.GLOBAL: None,
    IntelligenceMarketScope.MIXED: None,
}

_DEFAULT_MAX_ITEMS = 50


class GenericRssAdapter(IntelligenceAdapter):
    """설정 기반 RSS 2.0 피드 수집 어댑터.

    source_key / market_scope는 IntelligenceSource 레코드에서 읽는다.
    피드 URL은 source.config["feed_url"]에 저장한다.
    주문·트레이딩과 무관한 read-only 수집 어댑터.
    """

    source_type = IntelligenceSourceType.NEWS
    provider = IntelligenceProvider.RSS

    def __init__(
        self,
        source: IntelligenceSource,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.source_key: str = source.source_key
        self.market_scope: IntelligenceMarketScope = source.market_scope
        self._config: dict[str, Any] = source.config or {}
        self._client = client
        self._market = _SCOPE_TO_MARKET.get(source.market_scope)

    # ── 설정 접근자 ──────────────────────────────────────────────────────────

    @property
    def _feed_url(self) -> str:
        url = self._config.get("feed_url", "")
        if not url:
            raise AdapterFetchError(
                f"feed_url not configured in source '{self.source_key}'"
            )
        return str(url)

    @property
    def _max_items(self) -> int:
        return int(self._config.get("max_items", _DEFAULT_MAX_ITEMS))

    @property
    def _keyword_filter(self) -> list[str]:
        return [str(k) for k in self._config.get("keyword_filter", [])]

    # ── IntelligenceAdapter 구현 ──────────────────────────────────────────────

    async def fetch(self) -> list[IntelligenceRawItem]:
        """feed_url에서 RSS XML을 가져와 IntelligenceRawItem 목록으로 반환한다."""
        feed_url = self._feed_url
        owns_client = self._client is None
        client = self._client if self._client is not None else httpx.AsyncClient(timeout=10.0)
        try:
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                xml_text = resp.text
            except httpx.HTTPError as e:
                raise AdapterFetchError(
                    f"RSS fetch failed for '{self.source_key}': {e}"
                ) from e
        finally:
            if owns_client:
                await client.aclose()

        return self._parse_rss(xml_text)

    def normalize(self, raw: IntelligenceRawItem) -> IntelligenceEventCandidate:
        """IntelligenceRawItem → IntelligenceEventCandidate."""
        guid = raw.raw_data.get("guid") or raw.raw_data.get("link", "")
        pub_date = raw.raw_data.get("pub_date", "")
        dedup_hash = build_dedup_hash(self.source_key, guid, pub_date)

        description = raw.raw_data.get("description") or None
        summary = description[:500] if description else None

        return IntelligenceEventCandidate(
            source_key=self.source_key,
            event_type="news",
            title=raw.title,
            dedup_hash=dedup_hash,
            occurred_at=raw.occurred_at,
            market=self._market,
            source_ref=raw.source_ref,
            summary=summary,
            raw_payload=raw.raw_data,
        )

    # ── 내부 파서 ─────────────────────────────────────────────────────────────

    def _parse_rss(self, xml_text: str) -> list[IntelligenceRawItem]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            raise AdapterFetchError(
                f"RSS XML parse failed for '{self.source_key}': {e}"
            ) from e

        # RSS 2.0: <rss><channel><item>
        channel = root.find("channel")
        raw_elements = channel.findall("item") if channel is not None else []

        # Atom fallback: <feed><entry>
        if not raw_elements:
            atom_ns = "http://www.w3.org/2005/Atom"
            raw_elements = root.findall(f"{{{atom_ns}}}entry")

        keywords = self._keyword_filter
        items: list[IntelligenceRawItem] = []

        for elem in raw_elements[: self._max_items]:
            title = _elem_text(elem, "title") or ""
            link = _elem_text(elem, "link") or _elem_text(elem, "guid") or ""
            pub_date = (
                _elem_text(elem, "pubDate")
                or _elem_text(elem, "pubdate")
                or _elem_text(elem, "dc:date")
                or ""
            )
            description = _elem_text(elem, "description") or _elem_text(elem, "summary") or ""
            guid = _elem_text(elem, "guid") or link

            if not title or not link:
                continue

            if keywords:
                searchable = f"{title} {description}"
                if not any(kw in searchable for kw in keywords):
                    continue

            items.append(
                IntelligenceRawItem(
                    raw_id=guid,
                    title=title,
                    raw_data={
                        "title": title,
                        "link": link,
                        "pub_date": pub_date,
                        "description": description,
                        "guid": guid,
                    },
                    occurred_at=_parse_pub_date(pub_date),
                    source_ref=link,
                )
            )

        return items


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _elem_text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    if child is None:
        return None
    return (child.text or "").strip() or None


def _parse_pub_date(pub_date: str) -> datetime | None:
    if not pub_date:
        return None
    # RFC 2822 (표준 RSS pubDate)
    try:
        return parsedate_to_datetime(pub_date)
    except Exception:
        pass
    # ISO 8601 / 단순 날짜 포맷 fallback
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(pub_date, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None
