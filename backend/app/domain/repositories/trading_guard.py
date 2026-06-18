from sqlalchemy import select

from app.domain.models.trading_guard import TradingGuardState
from app.domain.repositories.base import BaseRepository


class TradingGuardRepository(BaseRepository[TradingGuardState]):
    model = TradingGuardState

    async def get_by_account_id(self, account_id: int) -> TradingGuardState | None:
        result = await self.session.execute(
            select(TradingGuardState).where(TradingGuardState.account_id == account_id)
        )
        return result.scalar_one_or_none()
