from __future__ import annotations

from sqlalchemy import func, select

from app.domain.models.enums import MarketCode, ScannerRuleStatus
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.repositories.base import BaseRepository


class ScannerRuleRepository(BaseRepository[ScannerRule]):
    model = ScannerRule

    async def list_with_version_counts(
        self, market: MarketCode | None = None
    ) -> list[tuple[ScannerRule, int]]:
        stmt = (
            select(ScannerRule, func.count(ScannerRuleVersion.id))
            .outerjoin(
                ScannerRuleVersion, ScannerRuleVersion.scanner_rule_id == ScannerRule.id
            )
            .group_by(ScannerRule.id)
            .order_by(ScannerRule.id)
        )
        if market is not None:
            stmt = stmt.where(ScannerRule.market == market)
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


class ScannerRuleVersionRepository(BaseRepository[ScannerRuleVersion]):
    model = ScannerRuleVersion

    async def list_by_rule(
        self, scanner_rule_id: int, include_archived: bool = False
    ) -> list[ScannerRuleVersion]:
        stmt = select(ScannerRuleVersion).where(
            ScannerRuleVersion.scanner_rule_id == scanner_rule_id
        )
        if not include_archived:
            stmt = stmt.where(ScannerRuleVersion.status != ScannerRuleStatus.ARCHIVED)
        stmt = stmt.order_by(ScannerRuleVersion.version_no)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[ScannerRuleVersion]:
        """status가 active 또는 testing인 룰 버전을 조회한다 (실행 대상)."""
        result = await self.session.execute(
            select(ScannerRuleVersion).where(
                ScannerRuleVersion.status.in_(
                    [ScannerRuleStatus.ACTIVE, ScannerRuleStatus.TESTING]
                )
            )
        )
        return list(result.scalars().all())

    async def get_max_version_no(self, scanner_rule_id: int) -> int:
        result = await self.session.execute(
            select(func.max(ScannerRuleVersion.version_no)).where(
                ScannerRuleVersion.scanner_rule_id == scanner_rule_id
            )
        )
        return result.scalar() or 0
