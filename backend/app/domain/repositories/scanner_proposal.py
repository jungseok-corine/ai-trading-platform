from __future__ import annotations

from sqlalchemy import select

from app.domain.models.enums import ProposalStatus
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.repositories.base import BaseRepository


class ScannerRuleProposalRepository(BaseRepository[ScannerRuleProposal]):
    model = ScannerRuleProposal

    async def list_filtered(
        self,
        scanner_rule_id: int | None = None,
        status: ProposalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ScannerRuleProposal]:
        stmt = select(ScannerRuleProposal).order_by(ScannerRuleProposal.id.desc())
        if scanner_rule_id is not None:
            stmt = stmt.where(ScannerRuleProposal.scanner_rule_id == scanner_rule_id)
        if status is not None:
            stmt = stmt.where(ScannerRuleProposal.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def pending_base_version_ids(self) -> set[int]:
        """pending 상태 제안이 걸려 있는 base_version_id 집합을 반환한다(배치 중복 방지용)."""
        stmt = select(ScannerRuleProposal.base_version_id).where(
            ScannerRuleProposal.status == ProposalStatus.PENDING,
            ScannerRuleProposal.base_version_id.is_not(None),
        )
        result = await self.session.execute(stmt)
        return {row[0] for row in result.all()}
