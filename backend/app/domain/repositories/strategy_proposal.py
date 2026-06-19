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

    async def pending_base_version_ids(self) -> set[int]:
        """pending 상태 제안이 걸려 있는 base_version_id 집합을 반환한다(배치 중복 방지용)."""
        stmt = select(StrategyProposal.base_version_id).where(
            StrategyProposal.status == ProposalStatus.PENDING,
            StrategyProposal.base_version_id.is_not(None),
        )
        result = await self.session.execute(stmt)
        return {row[0] for row in result.all()}
