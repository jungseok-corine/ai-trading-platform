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
