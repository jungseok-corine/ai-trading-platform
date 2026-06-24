from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.enums import MarketCode
from app.domain.models.intelligence import IntelligenceEvent, IntelligenceSource
from app.domain.repositories.base import BaseRepository


class IntelligenceSourceRepository(BaseRepository[IntelligenceSource]):
    model = IntelligenceSource

    async def get_by_key(self, source_key: str) -> IntelligenceSource | None:
        result = await self.session.execute(
            select(IntelligenceSource).where(IntelligenceSource.source_key == source_key)
        )
        return result.scalar_one_or_none()

    async def list_enabled(self) -> list[IntelligenceSource]:
        result = await self.session.execute(
            select(IntelligenceSource)
            .where(IntelligenceSource.enabled.is_(True))
            .order_by(IntelligenceSource.source_key)
        )
        return list(result.scalars().all())


class IntelligenceEventRepository(BaseRepository[IntelligenceEvent]):
    model = IntelligenceEvent

    async def get_by_dedup_hash(self, dedup_hash: str) -> IntelligenceEvent | None:
        result = await self.session.execute(
            select(IntelligenceEvent).where(IntelligenceEvent.dedup_hash == dedup_hash)
        )
        return result.scalar_one_or_none()

    async def list_by_source(
        self,
        source_id: int,
        limit: int = 50,
    ) -> list[IntelligenceEvent]:
        result = await self.session.execute(
            select(IntelligenceEvent)
            .where(IntelligenceEvent.source_id == source_id)
            .order_by(IntelligenceEvent.collected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def existing_hashes(self, hashes: list[str]) -> set[str]:
        """주어진 dedup_hash 중 이미 저장된 것들의 집합(중복 수집 방지)."""
        if not hashes:
            return set()
        result = await self.session.execute(
            select(IntelligenceEvent.dedup_hash).where(
                IntelligenceEvent.dedup_hash.in_(hashes)
            )
        )
        return {row[0] for row in result.all()}

    async def list_recent(
        self,
        hours: int = 24,
        market: MarketCode | None = None,
        symbol_code: str | None = None,
        limit: int = 50,
    ) -> list[IntelligenceEvent]:
        """최근 N시간 내 수집된 IntelligenceEvent 목록 (최신순)."""
        cutoff = datetime.now(KST) - timedelta(hours=hours)
        stmt = (
            select(IntelligenceEvent)
            .where(IntelligenceEvent.collected_at >= cutoff)
            .order_by(IntelligenceEvent.collected_at.desc())
        )
        if market is not None:
            stmt = stmt.where(IntelligenceEvent.market == market)
        if symbol_code is not None:
            stmt = stmt.where(IntelligenceEvent.symbol_code == symbol_code)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_for_bundle(
        self,
        hours: int = 24,
        market: MarketCode | None = None,
        symbol_code: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """번들용 최근 이벤트 목록 (IntelligenceSource JOIN으로 source_key 포함, dict 반환)."""
        cutoff = datetime.now(KST) - timedelta(hours=hours)
        stmt = (
            select(
                IntelligenceEvent.event_type,
                IntelligenceEvent.title,
                IntelligenceEvent.summary,
                IntelligenceSource.source_key,
                IntelligenceEvent.occurred_at,
                IntelligenceEvent.symbol_code,
                IntelligenceEvent.importance_score,
            )
            .join(IntelligenceSource, IntelligenceEvent.source_id == IntelligenceSource.id)
            .where(IntelligenceEvent.collected_at >= cutoff)
            .order_by(IntelligenceEvent.collected_at.desc())
        )
        if market is not None:
            stmt = stmt.where(IntelligenceEvent.market == market)
        if symbol_code is not None:
            stmt = stmt.where(IntelligenceEvent.symbol_code == symbol_code)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [
            {
                "event_type": r.event_type,
                "title": r.title,
                "summary": r.summary,
                "source_key": r.source_key,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                "symbol_code": r.symbol_code,
                "importance_score": float(r.importance_score) if r.importance_score else None,
            }
            for r in result.all()
        ]
