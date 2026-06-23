from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
