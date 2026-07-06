from __future__ import annotations

from sqlalchemy import or_, select

from app.domain.models.enums import MarketCode
from app.domain.models.strategy_assignment import (
    StrategyAssignmentLog,
    StrategyAssignmentRule,
)
from app.domain.repositories.base import BaseRepository


class StrategyAssignmentRuleRepository(BaseRepository[StrategyAssignmentRule]):
    model = StrategyAssignmentRule

    async def list_all(
        self, market: MarketCode | None = None
    ) -> list[StrategyAssignmentRule]:
        stmt = select(StrategyAssignmentRule).order_by(
            StrategyAssignmentRule.priority.desc(), StrategyAssignmentRule.id
        )
        if market is not None:
            stmt = stmt.where(StrategyAssignmentRule.market == market)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_matching(
        self, scanner_rule_id: int, market: MarketCode
    ) -> list[StrategyAssignmentRule]:
        """후보에 적용 가능한 enabled 규칙 전부를 우선순위 순서로 반환한다 (C-6.22).

        scanner_rule_id가 일치하거나, scanner_rule_id가 NULL(fallback)인 규칙이 대상이다.
        priority 내림차순, 동률이면 scanner_rule_id 지정 규칙을 fallback보다 우선한다.
        """
        stmt = (
            select(StrategyAssignmentRule)
            .where(
                StrategyAssignmentRule.enabled.is_(True),
                StrategyAssignmentRule.market == market,
                or_(
                    StrategyAssignmentRule.scanner_rule_id == scanner_rule_id,
                    StrategyAssignmentRule.scanner_rule_id.is_(None),
                ),
            )
            .order_by(
                StrategyAssignmentRule.priority.desc(),
                StrategyAssignmentRule.scanner_rule_id.is_(None),  # False(지정)가 먼저
                StrategyAssignmentRule.id,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_matching(
        self, scanner_rule_id: int, market: MarketCode
    ) -> StrategyAssignmentRule | None:
        """후보에 적용 가능한 enabled 규칙 중 우선순위가 가장 높은 것을 반환한다."""
        rules = await self.list_matching(scanner_rule_id, market)
        return rules[0] if rules else None


class StrategyAssignmentLogRepository(BaseRepository[StrategyAssignmentLog]):
    model = StrategyAssignmentLog

    async def list_filtered(
        self,
        candidate_event_id: int | None = None,
        symbol_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyAssignmentLog]:
        stmt = select(StrategyAssignmentLog).order_by(StrategyAssignmentLog.id.desc())
        if candidate_event_id is not None:
            stmt = stmt.where(
                StrategyAssignmentLog.candidate_event_id == candidate_event_id
            )
        if symbol_code is not None:
            stmt = stmt.where(StrategyAssignmentLog.symbol_code == symbol_code)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
