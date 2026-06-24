from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import IntelligenceCandidateStatus, MarketCode
from app.domain.models.intelligence_candidate import IntelligenceCandidate
from app.domain.repositories.base import BaseRepository


class IntelligenceCandidateRepository(BaseRepository[IntelligenceCandidate]):
    model = IntelligenceCandidate

    async def existing_hashes(self, hashes: list[str]) -> set[str]:
        """주어진 dedup_hash 중 이미 저장된 것들의 집합(중복 발굴 방지)."""
        if not hashes:
            return set()
        result = await self.session.execute(
            select(IntelligenceCandidate.dedup_hash).where(
                IntelligenceCandidate.dedup_hash.in_(hashes)
            )
        )
        return {row[0] for row in result.all()}

    async def list_recent(
        self,
        status: IntelligenceCandidateStatus | None = None,
        symbol_code: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelligenceCandidate]:
        stmt = select(IntelligenceCandidate).order_by(
            IntelligenceCandidate.created_at.desc(), IntelligenceCandidate.id.desc()
        )
        if status is not None:
            stmt = stmt.where(IntelligenceCandidate.status == status)
        if symbol_code is not None:
            stmt = stmt.where(IntelligenceCandidate.symbol_code == symbol_code)
        if market is not None:
            stmt = stmt.where(IntelligenceCandidate.market == market)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        candidate: IntelligenceCandidate,
        status: IntelligenceCandidateStatus,
    ) -> IntelligenceCandidate:
        candidate.status = status
        await self.session.flush()
        await self.session.refresh(candidate)
        return candidate
