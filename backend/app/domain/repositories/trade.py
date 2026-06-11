from sqlalchemy import select

from app.domain.models.enums import OrderStatus
from app.domain.models.trade import Trade
from app.domain.repositories.base import BaseRepository


class TradeRepository(BaseRepository[Trade]):
    model = Trade

    async def list_by_account(self, account_id: int, limit: int = 100, offset: int = 0) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .where(Trade.account_id == account_id)
            .order_by(Trade.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_pending_or_partial(self) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).where(
                Trade.order_status.in_([OrderStatus.PENDING, OrderStatus.PARTIAL]),
                Trade.broker_order_id.isnot(None),
            )
        )
        return list(result.scalars().all())
