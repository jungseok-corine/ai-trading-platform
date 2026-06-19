from __future__ import annotations

from sqlalchemy import select

from app.domain.models.enums import ProposalStatus
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.base import BaseRepository


class StrategyProposalRepository(BaseRepository[StrategyProposal]):
    model = StrategyProposal

    async def list_filtered(
        self,
        strategy_id: int | None = None,
        status: ProposalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyProposal]:
        stmt = select(StrategyProposal).order_by(StrategyProposal.id.desc())
        if strategy_id is not None:
            stmt = stmt.where(StrategyProposal.strategy_id == strategy_id)
        if status is not None:
            stmt = stmt.where(StrategyProposal.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
