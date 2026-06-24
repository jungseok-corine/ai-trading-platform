from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ExperimentStatus, IntelligenceStrategyProposalStatus, MarketCode
from app.domain.models.experiment import Experiment
from app.domain.models.intelligence_strategy_proposal import IntelligenceStrategyProposal
from app.domain.repositories.base import BaseRepository


class IntelligenceStrategyProposalRepository(BaseRepository[IntelligenceStrategyProposal]):
    model = IntelligenceStrategyProposal

    async def existing_for_candidate(
        self, intelligence_candidate_id: int
    ) -> IntelligenceStrategyProposal | None:
        """같은 후보에 PENDING/APPROVED 제안이 있으면 반환 (중복 방지용)."""
        result = await self.session.execute(
            select(IntelligenceStrategyProposal)
            .where(
                IntelligenceStrategyProposal.intelligence_candidate_id
                == intelligence_candidate_id,
                IntelligenceStrategyProposal.status.in_(
                    [
                        IntelligenceStrategyProposalStatus.PENDING,
                        IntelligenceStrategyProposalStatus.APPROVED,
                    ]
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        result = await self.session.execute(
            select(IntelligenceStrategyProposal.dedup_hash).where(
                IntelligenceStrategyProposal.dedup_hash.in_(hashes)
            )
        )
        return {row[0] for row in result.all()}

    async def list_recent(
        self,
        status: IntelligenceStrategyProposalStatus | None = None,
        symbol_code: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelligenceStrategyProposal]:
        stmt = select(IntelligenceStrategyProposal).order_by(
            IntelligenceStrategyProposal.created_at.desc(),
            IntelligenceStrategyProposal.id.desc(),
        )
        if status is not None:
            stmt = stmt.where(IntelligenceStrategyProposal.status == status)
        if symbol_code is not None:
            stmt = stmt.where(IntelligenceStrategyProposal.symbol_code == symbol_code)
        if market is not None:
            stmt = stmt.where(IntelligenceStrategyProposal.market == market)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def approve(
        self,
        proposal: IntelligenceStrategyProposal,
        reviewer_note: str | None = None,
    ) -> IntelligenceStrategyProposal:
        """제안을 승인한다. StrategyVersion/StrategyAssignmentLog 생성 없음."""
        proposal.status = IntelligenceStrategyProposalStatus.APPROVED
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.reviewer_note = reviewer_note
        await self.session.flush()
        await self.session.refresh(proposal)
        return proposal

    async def reject(
        self,
        proposal: IntelligenceStrategyProposal,
        reviewer_note: str | None = None,
    ) -> IntelligenceStrategyProposal:
        """제안을 거절한다. IntelligenceCandidate.status 변경 없음."""
        proposal.status = IntelligenceStrategyProposalStatus.REJECTED
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.reviewer_note = reviewer_note
        await self.session.flush()
        await self.session.refresh(proposal)
        return proposal

    async def find_by_experiment_id(
        self, experiment_id: int
    ) -> IntelligenceStrategyProposal | None:
        """experiment_id로 IntelligenceStrategyProposal을 조회한다 (C-2.28)."""
        result = await self.session.execute(
            select(IntelligenceStrategyProposal)
            .where(IntelligenceStrategyProposal.experiment_id == experiment_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_pending_evolution(self) -> list[IntelligenceStrategyProposal]:
        """COMPLETED experiment와 연결됐지만 evolution 분석이 안 된 제안 목록 (C-2.28)."""
        result = await self.session.execute(
            select(IntelligenceStrategyProposal)
            .join(
                Experiment,
                IntelligenceStrategyProposal.experiment_id == Experiment.id,
            )
            .where(
                IntelligenceStrategyProposal.experiment_id.is_not(None),
                IntelligenceStrategyProposal.evolution_analyzed_at.is_(None),
                Experiment.status == ExperimentStatus.COMPLETED,
            )
            .order_by(IntelligenceStrategyProposal.id)
        )
        return list(result.scalars().all())
