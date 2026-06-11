from sqlalchemy import func, select

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy

    async def list_with_version_counts(self) -> list[tuple[Strategy, int]]:
        """전략 목록과 각 전략의 버전 개수를 함께 조회한다."""
        stmt = (
            select(Strategy, func.count(StrategyVersion.id))
            .outerjoin(StrategyVersion, StrategyVersion.strategy_id == Strategy.id)
            .group_by(Strategy.id)
            .order_by(Strategy.id)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


class StrategyVersionRepository(BaseRepository[StrategyVersion]):
    model = StrategyVersion

    async def list_active(self) -> list[StrategyVersion]:
        """status가 active 또는 testing인 전략 버전을 조회한다."""
        result = await self.session.execute(
            select(StrategyVersion).where(
                StrategyVersion.status.in_(
                    [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                )
            )
        )
        return list(result.scalars().all())

    async def list_by_strategy(self, strategy_id: int) -> list[StrategyVersion]:
        result = await self.session.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version_no)
        )
        return list(result.scalars().all())

    async def get_max_version_no(self, strategy_id: int) -> int:
        result = await self.session.execute(
            select(func.max(StrategyVersion.version_no)).where(
                StrategyVersion.strategy_id == strategy_id
            )
        )
        return result.scalar() or 0
