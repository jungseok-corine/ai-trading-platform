from sqlalchemy import select

from app.domain.models.risk import RiskConfig, RiskEvent
from app.domain.repositories.base import BaseRepository


class RiskConfigRepository(BaseRepository[RiskConfig]):
    model = RiskConfig

    async def get_by_account_id(self, account_id: int) -> RiskConfig | None:
        result = await self.session.execute(
            select(RiskConfig).where(RiskConfig.account_id == account_id)
        )
        return result.scalar_one_or_none()


class RiskEventRepository(BaseRepository[RiskEvent]):
    model = RiskEvent
