from __future__ import annotations

from sqlalchemy import select

from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.repositories.base import BaseRepository


class CandidateStrategyProposalRepository(BaseRepository[CandidateStrategyProposal]):
    model = CandidateStrategyProposal

    async def list_for_candidate(
        self, candidate_event_id: int
    ) -> list[CandidateStrategyProposal]:
        stmt = (
            select(CandidateStrategyProposal)
            .where(CandidateStrategyProposal.candidate_event_id == candidate_event_id)
            .order_by(CandidateStrategyProposal.id.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[CandidateStrategyProposal]:
        stmt = select(CandidateStrategyProposal).order_by(
            CandidateStrategyProposal.id.desc()
        )
        if status is not None:
            stmt = stmt.where(CandidateStrategyProposal.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_pending_duplicate(
        self, candidate_event_id: int, suggested_strategy_type: str
    ) -> CandidateStrategyProposal | None:
        """같은 후보 + 같은 전략 타입의 PENDING 제안을 찾는다(중복 생성 방지용)."""
        stmt = select(CandidateStrategyProposal).where(
            CandidateStrategyProposal.candidate_event_id == candidate_event_id,
            CandidateStrategyProposal.suggested_strategy_type == suggested_strategy_type,
            CandidateStrategyProposal.status == "pending",
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
