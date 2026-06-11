from sqlalchemy import select

from app.domain.models.position_event import PositionEvent
from app.domain.repositories.base import BaseRepository


class PositionEventRepository(BaseRepository[PositionEvent]):
    model = PositionEvent

    async def list_by_position(self, position_id: int, limit: int = 100, offset: int = 0) -> list[PositionEvent]:
        result = await self.session.execute(
            select(PositionEvent)
            .where(PositionEvent.position_id == position_id)
            .order_by(PositionEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
