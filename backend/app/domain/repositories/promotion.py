from __future__ import annotations

from sqlalchemy import select

from app.domain.models.enums import MarketCode
from app.domain.models.promotion import PromotionCriteria, PromotionEvaluation
from app.domain.repositories.base import BaseRepository


class PromotionCriteriaRepository(BaseRepository[PromotionCriteria]):
    model = PromotionCriteria

    async def list_all(
        self, market: MarketCode | None = None
    ) -> list[PromotionCriteria]:
        stmt = select(PromotionCriteria).order_by(PromotionCriteria.id)
        if market is not None:
            stmt = stmt.where(PromotionCriteria.market == market)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PromotionEvaluationRepository(BaseRepository[PromotionEvaluation]):
    model = PromotionEvaluation

    async def list_by_version(
        self, strategy_version_id: int, limit: int = 50
    ) -> list[PromotionEvaluation]:
        result = await self.session.execute(
            select(PromotionEvaluation)
            .where(PromotionEvaluation.strategy_version_id == strategy_version_id)
            .order_by(PromotionEvaluation.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
