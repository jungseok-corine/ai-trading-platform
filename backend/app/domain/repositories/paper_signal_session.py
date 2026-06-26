from __future__ import annotations

from sqlalchemy import select

from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.repositories.base import BaseRepository


class PaperSignalSessionRepository(BaseRepository[PaperSignalSession]):
    model = PaperSignalSession

    async def list_filtered(
        self, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[PaperSignalSession]:
        stmt = select(PaperSignalSession).order_by(PaperSignalSession.id.desc())
        if status is not None:
            stmt = stmt.where(PaperSignalSession.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[PaperSignalSession]:
        result = await self.session.execute(
            select(PaperSignalSession)
            .where(PaperSignalSession.status == "active")
            .order_by(PaperSignalSession.id)
        )
        return list(result.scalars().all())

    async def find_active_for_proposal(
        self, candidate_strategy_proposal_id: int
    ) -> PaperSignalSession | None:
        result = await self.session.execute(
            select(PaperSignalSession).where(
                PaperSignalSession.candidate_strategy_proposal_id
                == candidate_strategy_proposal_id,
                PaperSignalSession.status == "active",
            )
        )
        return result.scalars().first()

    async def find_open_challenger_for_strategy_proposal(
        self, source_strategy_proposal_id: int
    ) -> PaperSignalSession | None:
        """같은 source StrategyProposal에 대한 미종료 challenger 세션(prepared/active)을 찾는다.

        중복 prepared/active challenger 세션을 막기 위한 가드(M2.5 Phase 2). stopped는 제외한다.
        """
        result = await self.session.execute(
            select(PaperSignalSession).where(
                PaperSignalSession.source_strategy_proposal_id
                == source_strategy_proposal_id,
                PaperSignalSession.source_type == "signal_challenger",
                PaperSignalSession.status.in_(["prepared", "active"]),
            )
        )
        return result.scalars().first()
