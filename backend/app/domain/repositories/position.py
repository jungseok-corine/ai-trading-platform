from sqlalchemy import select

from app.domain.models.position import Position
from app.domain.repositories.base import BaseRepository


class PositionRepository(BaseRepository[Position]):
    model = Position

    async def get_by_account_symbol(self, account_id: int, symbol_code: str) -> Position | None:
        result = await self.session.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol_code == symbol_code,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_account(
        self,
        account_id: int | None = None,
        include_closed: bool = False,
    ) -> list[Position]:
        stmt = select(Position).order_by(Position.id)
        if account_id is not None:
            stmt = stmt.where(Position.account_id == account_id)
        if not include_closed:
            stmt = stmt.where(Position.quantity != 0)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
