from __future__ import annotations

from sqlalchemy import func, select

from app.domain.models.enums import OrderStatus
from app.domain.models.trade import Trade
from app.domain.repositories.base import BaseRepository


class TradeRepository(BaseRepository[Trade]):
    model = Trade

    async def list(self, limit: int = 100, offset: int = 0) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .order_by(Trade.created_at.desc(), Trade.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_account(self, account_id: int, limit: int = 100, offset: int = 0) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .where(Trade.account_id == account_id)
            .order_by(Trade.created_at.desc(), Trade.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_strategy_version(self, strategy_version_id: int) -> list[Trade]:
        result = await self.session.execute(
            select(Trade)
            .where(Trade.strategy_version_id == strategy_version_id)
            .order_by(Trade.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_by_strategy_version(self, strategy_version_id: int) -> int:
        """해당 strategy_version_id를 참조하는 trade 개수를 반환한다."""
        result = await self.session.execute(
            select(func.count(Trade.id)).where(
                Trade.strategy_version_id == strategy_version_id
            )
        )
        return result.scalar() or 0

    async def list_pending_or_partial(self) -> list[Trade]:
        result = await self.session.execute(
            select(Trade).where(
                Trade.order_status.in_([OrderStatus.PENDING, OrderStatus.PARTIAL]),
                Trade.broker_order_id.isnot(None),
            )
        )
        return list(result.scalars().all())
