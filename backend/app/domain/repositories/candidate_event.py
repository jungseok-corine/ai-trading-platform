from __future__ import annotations

from sqlalchemy import select

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import MarketCode
from app.domain.repositories.base import BaseRepository


class CandidateEventRepository(BaseRepository[CandidateEvent]):
    model = CandidateEvent

    async def list_filtered(
        self,
        scanner_rule_version_id: int | None = None,
        symbol_code: str | None = None,
        market: MarketCode | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CandidateEvent]:
        stmt = select(CandidateEvent).order_by(
            CandidateEvent.triggered_at.desc(), CandidateEvent.id.desc()
        )
        if scanner_rule_version_id is not None:
            stmt = stmt.where(
                CandidateEvent.scanner_rule_version_id == scanner_rule_version_id
            )
        if symbol_code is not None:
            stmt = stmt.where(CandidateEvent.symbol_code == symbol_code)
        if market is not None:
            stmt = stmt.where(CandidateEvent.market == market)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
