"""DART 공시 브리지 어댑터 (C-2.22).

기존 DartIngestService가 저장한 news_events(source="dart") 레코드를
IntelligenceEventCandidate로 변환해 intelligence 계층에 통합한다.

중요:
- 기존 DartIngestService / DartProvider를 수정하지 않는다.
- 외부 API를 직접 호출하지 않는다 (DB에서만 읽는다).
- dedup_hash = build_dedup_hash(source_key, rcept_no) 로 중복을 방지한다.
- 주문·트레이딩과 무관한 read-only 브리지 어댑터.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.enums import (
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.domain.models.intelligence import IntelligenceSource
from app.domain.models.news_context import NewsEvent
from app.market_intelligence.adapters.base import (
    IntelligenceAdapter,
    IntelligenceEventCandidate,
    IntelligenceRawItem,
    build_dedup_hash,
)

DART_DISCLOSURE_SOURCE_KEY = "dart_disclosure"
_DEFAULT_LOOKBACK_DAYS = 7


class DartDisclosureAdapter(IntelligenceAdapter):
    """news_events(DART 공시) → IntelligenceEvent 브리지 어댑터.

    DartIngestService가 이미 수집·필터한 공시 레코드를 IntelligenceAdapter
    패턴으로 읽어 intelligence 계층에 통합한다.
    기존 수집 서비스를 건드리지 않고 데이터를 재사용한다.
    """

    source_type = IntelligenceSourceType.DISCLOSURE
    provider = IntelligenceProvider.DART
    market_scope = IntelligenceMarketScope.KR

    def __init__(
        self,
        source: IntelligenceSource,
        session: AsyncSession,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self.source_key: str = source.source_key
        self._session = session
        self._lookback_days = lookback_days

    async def fetch(self) -> list[IntelligenceRawItem]:
        """최근 N일 내 DART 공시(news_events)를 IntelligenceRawItem으로 반환한다."""
        cutoff = datetime.now(KST) - timedelta(days=self._lookback_days)
        result = await self._session.execute(
            select(NewsEvent)
            .where(
                NewsEvent.source == "dart",
                NewsEvent.published_at >= cutoff,
            )
            .order_by(NewsEvent.published_at.desc())
            .limit(500)
        )
        news_events = list(result.scalars().all())

        items: list[IntelligenceRawItem] = []
        for evt in news_events:
            payload = evt.raw_payload or {}
            rcept_no = payload.get("rcept_no", "")

            items.append(
                IntelligenceRawItem(
                    raw_id=rcept_no or str(evt.id),
                    title=evt.headline,
                    raw_data={
                        "rcept_no": rcept_no,
                        "corp_name": payload.get("corp_name", ""),
                        "headline": evt.headline,
                        "url": evt.url,
                        "symbol_code": evt.symbol_code,
                        "published_at": (
                            evt.published_at.isoformat() if evt.published_at else None
                        ),
                        "materiality": payload.get("materiality"),
                        "category": payload.get("category"),
                    },
                    occurred_at=evt.published_at,
                    symbol_code=evt.symbol_code,
                    source_ref=evt.url,
                )
            )

        return items

    def normalize(self, raw: IntelligenceRawItem) -> IntelligenceEventCandidate:
        """IntelligenceRawItem → IntelligenceEventCandidate."""
        rcept_no = raw.raw_data.get("rcept_no") or raw.raw_id
        dedup_hash = build_dedup_hash(self.source_key, rcept_no)

        return IntelligenceEventCandidate(
            source_key=self.source_key,
            event_type="disclosure",
            title=raw.title,
            dedup_hash=dedup_hash,
            occurred_at=raw.occurred_at,
            market=MarketCode.KR,
            symbol_code=raw.symbol_code,
            source_ref=raw.source_ref,
            raw_payload=raw.raw_data,
        )
