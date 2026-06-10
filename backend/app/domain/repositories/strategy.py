from sqlalchemy import select

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy


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
