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
