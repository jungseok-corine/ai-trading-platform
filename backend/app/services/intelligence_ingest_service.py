"""Intelligence Ingestion Pipeline 서비스 (C-2.22).

등록된 IntelligenceSource를 순회해 fetch → normalize → dedup → 저장한다.
소스별 어댑터는 (source_type, provider) 쌍으로 선택된다.
한 소스가 실패해도 나머지 소스는 계속 실행하고 오류는 summary에 기록한다.

안전 불변식:
- 주문 API 호출 없음
- 실전 브로커 코드 변경 없음
- KIS_REAL_TRADING_ENABLED 불변
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import IntelligenceProvider, IntelligenceSourceType
from app.domain.models.intelligence import IntelligenceEvent, IntelligenceSource
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.market_intelligence.adapters.base import (
    AdapterFetchError,
    IntelligenceAdapter,
    IntelligenceEventCandidate,
)
from app.market_intelligence.adapters.dart_disclosure_adapter import DartDisclosureAdapter
from app.market_intelligence.adapters.generic_rss_adapter import GenericRssAdapter

logger = logging.getLogger(__name__)


@dataclass
class IngestSummary:
    sources_checked: int = 0
    fetched_count: int = 0
    inserted_count: int = 0
    skipped_duplicate_count: int = 0
    error_count: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources_checked": self.sources_checked,
            "fetched_count": self.fetched_count,
            "inserted_count": self.inserted_count,
            "skipped_duplicate_count": self.skipped_duplicate_count,
            "error_count": self.error_count,
            "errors": self.errors,
        }


# (source_type, provider) → adapter class 레지스트리
_ADAPTER_REGISTRY: dict[
    tuple[IntelligenceSourceType, IntelligenceProvider], type[IntelligenceAdapter]
] = {
    (IntelligenceSourceType.NEWS, IntelligenceProvider.RSS): GenericRssAdapter,
    (IntelligenceSourceType.DISCLOSURE, IntelligenceProvider.DART): DartDisclosureAdapter,
}


class IntelligenceIngestionService:
    """Intelligence pipeline 오케스트레이터.

    1. IntelligenceSource.enabled=True인 소스를 로드
    2. 각 소스에 맞는 어댑터로 fetch → normalize
    3. dedup_hash로 중복 제거 후 IntelligenceEvent 저장
    """

    def __init__(
        self,
        session: AsyncSession,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._session = session
        self._http_client = http_client
        self._source_repo = IntelligenceSourceRepository(session)
        self._event_repo = IntelligenceEventRepository(session)

    async def ingest(
        self,
        source_keys: list[str] | None = None,
    ) -> IngestSummary:
        """enabled 소스를 대상으로 수집 파이프라인을 실행한다.

        source_keys가 지정되면 해당 소스만 실행한다.
        """
        summary = IngestSummary()

        all_sources = await self._source_repo.list_enabled()
        if source_keys:
            sources = [s for s in all_sources if s.source_key in source_keys]
        else:
            sources = all_sources

        summary.sources_checked = len(sources)

        for source in sources:
            try:
                inserted, skipped = await self._run_source(source)
                summary.inserted_count += inserted
                summary.skipped_duplicate_count += skipped
            except Exception as exc:  # noqa: BLE001
                summary.error_count += 1
                summary.errors.append(
                    {"source_key": source.source_key, "error": str(exc)}
                )
                logger.error(
                    "intelligence ingest: source=%s failed: %s",
                    source.source_key,
                    exc,
                )

        return summary

    async def _run_source(self, source: IntelligenceSource) -> tuple[int, int]:
        """단일 소스를 fetch → normalize → dedup → 저장한다.

        Returns: (inserted_count, skipped_duplicate_count)
        """
        adapter = self._make_adapter(source)
        if adapter is None:
            logger.warning(
                "intelligence ingest: no adapter for source=%s type=%s provider=%s",
                source.source_key,
                source.source_type,
                source.provider,
            )
            return 0, 0

        try:
            raw_items = await adapter.fetch()
        except AdapterFetchError as e:
            raise RuntimeError(f"fetch failed: {e}") from e

        if not raw_items:
            return 0, 0

        candidates: list[IntelligenceEventCandidate] = [
            adapter.normalize(raw) for raw in raw_items
        ]

        # 중복 방지: 이미 저장된 hash 조회
        all_hashes = [c.dedup_hash for c in candidates]
        existing = await self._event_repo.existing_hashes(all_hashes)

        inserted = 0
        skipped = 0

        for candidate in candidates:
            if candidate.dedup_hash in existing:
                skipped += 1
                continue

            await self._event_repo.create(
                source_id=source.id,
                event_type=candidate.event_type,
                title=candidate.title,
                dedup_hash=candidate.dedup_hash,
                occurred_at=candidate.occurred_at,
                market=candidate.market,
                symbol_code=candidate.symbol_code,
                summary=candidate.summary,
                source_ref=candidate.source_ref,
                importance_score=candidate.importance_score,
                confidence_score=candidate.confidence_score,
                raw_payload=candidate.raw_payload,
                status=candidate.status,
            )
            existing.add(candidate.dedup_hash)
            inserted += 1

        await self._session.commit()
        logger.info(
            "intelligence ingest: source=%s fetched=%d inserted=%d skipped=%d",
            source.source_key,
            len(raw_items),
            inserted,
            skipped,
        )
        return inserted, skipped

    def _make_adapter(self, source: IntelligenceSource) -> IntelligenceAdapter | None:
        """(source_type, provider) → 어댑터 인스턴스 팩토리."""
        key = (source.source_type, source.provider)
        cls = _ADAPTER_REGISTRY.get(key)
        if cls is None:
            return None

        if cls is GenericRssAdapter:
            return GenericRssAdapter(source, client=self._http_client)
        if cls is DartDisclosureAdapter:
            return DartDisclosureAdapter(source, self._session)
        return None  # 알 수 없는 어댑터
